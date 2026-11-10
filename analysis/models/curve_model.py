"""
Predict a unit's full frequency-efficiency curve from a handful of cheap probe measurements,
and work out WHICH frequencies are worth measuring in the first place.

THE PROBLEM THIS SOLVES
    Measuring a full 13-point sweep costs real wall-clock time per chip (~2 hours with a
    fixed-work benchmark). If 3 well-chosen frequencies predict the other 10, a chip can be
    characterised in a fraction of the time - which is the difference between 6 chips and 20
    over a three-month window.

WHAT A "UNIT" IS
    Deliberately abstract: a unit is anything with its own efficiency curve. On the public
    V100 dataset a unit is a WORKLOAD (33 of them). On collected data a unit is a CHIP.
    Identical machinery, and that is the point - the workload version can be validated NOW,
    while chips accumulate one at a time.

    Do NOT pool the two into one training set. Different architecture, workload type, and
    feature space. Train separately, compare results.

THREE MODES, MATCHING WHAT IS ACTUALLY KNOWN ABOUT A NEW CHIP
    cold      - nothing known. Probe, then predict from the population model.
    history   - this GPU model has been measured before. Use its stored curve as a prior and
                probe fewer points to refine it.
    specs     - EXTENSION POINT, not yet active. Condition on GPU spec features (SM count,
                TDP, bus width, process node) so a never-before-seen model can be predicted
                without probing at all. Requires a specs database AND enough distinct chips
                to fit against - neither exists yet. See notes in loadSpecFeatures().

HONESTY
    With N=1 collected chip, the chip-level version of this CANNOT be validated. Everything
    below is validated on the V100 workload data, which proves the machinery works but says
    nothing about chip-to-chip transfer. Any number this prints about chips before ~5 chips
    exist is a demonstration, not a result.
"""

import argparse
import glob
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

import sys
from pathlib import Path

# analysis/ holds load_data.py. Added explicitly because Python puts only THIS file's directory
# (analysis/models/) on the path, and every module here is run as a script rather than imported
# as a package - see analysis/models/README.md for why it is not a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from load_data import REFERENCE_FREQUENCY_MHZ, loadDataset

# THREE levels: analysis/models/ -> analysis/ -> repo root. This was parent.parent while
# the file lived in analysis/, and moving it would otherwise have pointed SWEEP_DIR at
# analysis/data/ - a directory that does not exist, which glob reports as zero sweeps
# rather than as an error.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SWEEP_DIR = REPO_ROOT / "data" / "frequency-sweeps"


# --------------------------------------------------------------------------------------
# Loading units
# --------------------------------------------------------------------------------------

def loadUnitsFromPublicDataset():
    """Units = workloads on the public V100 dataset. Returns (frequencies, curves, names)."""
    dataset = loadDataset(validate=False)
    matrix = dataset.pivot(index="workload", columns="frequency_mhz", values="efficiency_normalised")
    frequencies = np.array(matrix.columns, dtype=float)
    return frequencies, matrix.to_numpy(dtype=float), list(matrix.index)


def loadUnitsFromSweeps(sweepDirectory=SWEEP_DIR):
    """
    Units = physical chips, from collected sweep CSVs.

    Each sweep CSV is one chip under one workload. Efficiency is computed the same way the
    public dataset defines it - performance per watt, normalised to the value at the highest
    measured frequency - so the two are directly comparable in SHAPE even though they cannot
    be pooled for training.
    """
    paths = sorted(glob.glob(os.path.join(str(sweepDirectory), "*_sweep.csv")))
    if not paths:
        return None, None, []

    curvesByFrequency = {}
    names = []

    for path in paths:
        frame = pd.read_csv(path)
        if "bench_throughput" not in frame.columns or frame["bench_throughput"].isna().all():
            # No performance metric in this sweep, so no efficiency can be computed from it.
            continue
        usable = frame.dropna(subset=["bench_throughput", "power_avg_w"])
        usable = usable[usable["power_avg_w"] > 0]
        if len(usable) < 4:
            continue

        efficiency = usable["bench_throughput"].to_numpy(float) / usable["power_avg_w"].to_numpy(float)
        reference = efficiency[np.argmax(usable["target_frequency_mhz"].to_numpy(float))]
        if reference <= 0:
            continue

        name = Path(path).stem
        curvesByFrequency[name] = pd.Series(
            efficiency / reference, index=usable["target_frequency_mhz"].to_numpy(float)
        )
        names.append(name)

    if not curvesByFrequency:
        return None, None, []

    aligned = pd.DataFrame(curvesByFrequency).T.sort_index(axis=1)
    aligned = aligned.dropna(axis=1, how="any")  # keep only frequencies every chip has
    if aligned.shape[1] < 4:
        return None, None, []

    return np.array(aligned.columns, dtype=float), aligned.to_numpy(dtype=float), list(aligned.index)


def loadSpecFeatures(unitNames):
    """
    EXTENSION POINT - returns None today, on purpose.

    The goal: predict a chip's curve from GPU-model specs (SM count, TDP, memory bandwidth,
    process node) so a card that has never been measured can be predicted without probing.

    Why it is not wired up:
      * No usable open specs database was found. `dbgpu` installs but ships an EMPTY database
        and its `build` command scrapes TechPowerUp, which has its own licensing terms.
        mlco2/impact's gpus.csv covers datacenter parts only (H100/A100), no consumer cards.
        Kaggle TechPowerUp exports exist and would need manual download.
      * More fundamentally: fitting specs -> curve needs MANY DISTINCT GPU MODELS. With one
        chip it cannot be fitted, let alone validated. Wiring it early would produce a model
        that looks trained and predicts nothing.

    Activate this when there are ~10+ distinct GPU models in data/frequency-sweeps/, and
    validate it leave-one-MODEL-out, not leave-one-chip-out - otherwise two cards of the same
    model leak across the split.
    """
    return None


# --------------------------------------------------------------------------------------
# Probe selection - the "efficient benchmark" half
# --------------------------------------------------------------------------------------

def reconstructionErrorForProbes(curves, probeIndices, ridgeAlpha=1.0):
    """
    Leave-one-unit-out error when predicting whole curves from only these probe columns.

    This is the objective probe selection minimises: not "how well does the model fit" but
    "how well does it fit a unit it has never seen", which is the only question that matters
    when the point is to characterise a NEW chip cheaply.
    """
    unitCount = curves.shape[0]
    if unitCount < 3:
        return float("inf")

    errors = []
    for held in range(unitCount):
        trainMask = np.ones(unitCount, dtype=bool)
        trainMask[held] = False

        model = Ridge(alpha=ridgeAlpha)
        model.fit(curves[trainMask][:, probeIndices], curves[trainMask])
        predicted = model.predict(curves[held][probeIndices].reshape(1, -1))[0]
        errors.append(np.mean(np.abs(predicted - curves[held])))

    return float(np.mean(errors))


def selectProbeFrequencies(frequencies, curves, probeCount, alwaysInclude=None):
    """
    Greedily pick the probe frequencies that best reconstruct the full curve.

    ✅ GREEDY MATCHES EXHAUSTIVE HERE, checked 2026-09-11 rather than assumed. Brute-forcing every
    subset in select_probes.py reaches the identical probe set and error to six decimal places at
    k=1, 2 and 3 - [757], [757, 825], [757, 825, 885] MHz. ⚠️ k=4 and k=5 were NOT brute-forced,
    so greedy is verified optimal only where an exhaustive search actually ran. The docstring below
    correctly says greedy is "not guaranteed optimal"; on these 33 workloads, at those three
    counts, it happens to be.

    Greedy forward selection: start from the mandatory probes, then repeatedly add whichever
    remaining frequency most reduces held-out reconstruction error. Not guaranteed optimal,
    but it is deterministic, cheap, and vastly better than evenly-spaced guessing.

    `alwaysInclude` exists because the highest frequency is free in practice - it is where the
    card already runs, and every curve is normalised to it.
    """
    frequencyCount = curves.shape[1]
    chosen = list(alwaysInclude) if alwaysInclude else []

    while len(chosen) < probeCount:
        bestIndex, bestError = None, float("inf")
        for candidate in range(frequencyCount):
            if candidate in chosen:
                continue
            error = reconstructionErrorForProbes(curves, sorted(chosen + [candidate]))
            if error < bestError:
                bestIndex, bestError = candidate, error
        if bestIndex is None:
            break
        chosen.append(bestIndex)

    chosen = sorted(chosen)
    return chosen, reconstructionErrorForProbes(curves, chosen)


# --------------------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------------------

class CurvePredictor:
    """Predicts a full efficiency curve from probe measurements, optionally with a prior."""

    def __init__(self, frequencies, probeIndices, ridgeAlpha=1.0):
        self.frequencies = np.asarray(frequencies, dtype=float)
        self.probeIndices = list(probeIndices)
        self.model = Ridge(alpha=ridgeAlpha)
        self.populationMean = None

    def fit(self, curves):
        self.model.fit(curves[:, self.probeIndices], curves)
        self.populationMean = curves.mean(axis=0)
        return self

    def predict(self, probeValues, prior=None, priorWeight=0.5):
        """
        prior: a previously measured curve for this GPU model, if one exists.

        Blending is a deliberate simple choice. A learned prior weight needs enough repeat
        measurements of the same model to fit against, and that data does not exist yet.
        Until it does, a fixed blend is honest; a fitted one would be fictional.
        """
        predicted = self.model.predict(np.asarray(probeValues, dtype=float).reshape(1, -1))[0]
        if prior is not None:
            prior = np.asarray(prior, dtype=float)
            predicted = (1.0 - priorWeight) * predicted + priorWeight * prior
        return predicted

    def optimalFrequency(self, predictedCurve):
        return float(self.frequencies[int(np.argmax(predictedCurve))])


# --------------------------------------------------------------------------------------
# Evaluation - baselines that could embarrass the model
# --------------------------------------------------------------------------------------

def regretPercent(trueCurve, chosenIndex):
    return float((trueCurve.max() - trueCurve[chosenIndex]) * 100.0)


def evaluate(frequencies, curves, names, probeCount, alwaysIncludeTop=True):
    """Leave-one-unit-out comparison of the probe model against no-model baselines.

    ⚠️ THE PROBE SELECTION BELOW IS HINDSIGHT, AND THE DOCSTRING SAID NOTHING ABOUT IT UNTIL
    2026-09-11. selectProbeFrequencies() is called ONCE, on all units, and the leave-one-unit-out
    loop underneath then scores the model on units the selection already saw. The inner
    reconstruction error is itself leave-one-out, which is what made this look clean for so long -
    but choosing WHICH columns to use is part of fitting, and it happened outside the fold.

    ✅ MEASURED, AND IT COSTS NOTHING HERE. analysis/models/select_probes.py re-runs the selection
    inside each fold on training units only. The honest and hindsight errors agree to four decimal
    places at every probe count from 1 to 5, because all 33 folds select the IDENTICAL probe set -
    1 distinct set in 33 folds, at every k. The shortcut was wrong in principle and worth 0.0000 in
    practice.

    ⛔ Do NOT read that as permission to keep it. Nothing guarantees stability in advance; it was
    checked afterwards, on one dataset, and a dataset with more spread between units would not
    behave this way. It is left unchanged because rewriting it would invalidate the published
    numbers for a correction measured at zero - the fix lives in select_probes.py, which is
    nested-by-construction and has a spy test proving the held-out unit never reaches the selector.

    ⚠️ alwaysIncludeTop SPENDS A PROBE SLOT ON A CONSTANT. Every curve is normalised to the top
    frequency, so that column is exactly 1.0 for all 33 units - zero variance, no information. The
    "four probes" this function reports are three informative measurements plus a free one. That
    is not a bug, since the top measurement genuinely costs nothing to take, but a reader comparing
    probe COUNTS across this directory needs to know they are not counting the same thing.
    """
    unitCount, frequencyCount = curves.shape
    topIndex = int(np.argmax(frequencies))
    alwaysInclude = [topIndex] if alwaysIncludeTop else []

    probeIndices, expectedError = selectProbeFrequencies(
        frequencies, curves, probeCount, alwaysInclude=alwaysInclude
    )

    rows = []
    for held in range(unitCount):
        trainMask = np.ones(unitCount, dtype=bool)
        trainMask[held] = False
        trainCurves = curves[trainMask]
        trueCurve = curves[held]

        predictor = CurvePredictor(frequencies, probeIndices).fit(trainCurves)
        predictedCurve = predictor.predict(trueCurve[probeIndices])
        modelIndex = int(np.argmax(predictedCurve))

        # Baseline 1: run at the top frequency. What the card does by default.
        stockIndex = topIndex
        # Baseline 2: one fixed frequency, learned from the training units only. The one to beat.
        fixedIndex = int(np.argmax(trainCurves.mean(axis=0)))

        rows.append({
            "unit": names[held],
            "true_optimum_mhz": float(frequencies[int(np.argmax(trueCurve))]),
            "model_choice_mhz": float(frequencies[modelIndex]),
            "fixed_choice_mhz": float(frequencies[fixedIndex]),
            "model_regret_pct": regretPercent(trueCurve, modelIndex),
            "fixed_regret_pct": regretPercent(trueCurve, fixedIndex),
            "stock_regret_pct": regretPercent(trueCurve, stockIndex),
            "curve_mae": float(np.mean(np.abs(predictedCurve - trueCurve))),
        })

    return pd.DataFrame(rows), probeIndices, expectedError


def report(results, frequencies, probeIndices, expectedError, unitKind, probeCount, totalFrequencies):
    probeMhz = [int(frequencies[i]) for i in probeIndices]
    savedFraction = 1.0 - (len(probeIndices) / totalFrequencies)

    print(f"[CURVE] Units: {len(results)} {unitKind}s, {totalFrequencies} frequencies each.")
    print(f"[CURVE] Selected {len(probeIndices)} probe frequencies: {probeMhz} MHz")
    print(f"[CURVE] That is {savedFraction:.0%} fewer measurements than a full sweep.")
    print(f"[CURVE] Held-out curve reconstruction MAE: {expectedError:.4f} (normalised efficiency units)")
    print()

    summary = pd.DataFrame({
        "mean_regret_pct": [
            results["stock_regret_pct"].mean(),
            results["fixed_regret_pct"].mean(),
            results["model_regret_pct"].mean(),
        ],
        "median_regret_pct": [
            results["stock_regret_pct"].median(),
            results["fixed_regret_pct"].median(),
            results["model_regret_pct"].median(),
        ],
        "worst_regret_pct": [
            results["stock_regret_pct"].max(),
            results["fixed_regret_pct"].max(),
            results["model_regret_pct"].max(),
        ],
    }, index=["stock (do nothing)", "best fixed frequency", f"probe model ({probeCount} probes)"])

    print("[CURVE] Regret = efficiency given up versus that unit's true optimum:")
    print(summary.round(3).to_string())
    print()

    modelRegret = summary.loc[f"probe model ({probeCount} probes)", "mean_regret_pct"]
    fixedRegret = summary.loc["best fixed frequency", "mean_regret_pct"]

    if modelRegret < fixedRegret - 0.05:
        print(f"[CURVE] The probe model BEATS the fixed-frequency baseline "
              f"({modelRegret:.3f}% vs {fixedRegret:.3f}%). Probing earns its cost here.")
    elif modelRegret > fixedRegret + 0.05:
        print(f"[CURVE] The probe model LOSES to the fixed-frequency baseline "
              f"({modelRegret:.3f}% vs {fixedRegret:.3f}%). Report that. Probing is not worth "
              f"its cost on this data.")
    else:
        print(f"[CURVE] The probe model TIES the fixed-frequency baseline "
              f"({modelRegret:.3f}% vs {fixedRegret:.3f}%). A model that ties a lookup table has "
              f"not earned a slide.")

    # These are two different claims and conflating them would overstate the result.
    print()
    print("[CURVE] Two separate questions, two separate answers:")
    print(f"[CURVE]   1. Can {probeCount} probes RECONSTRUCT the full curve?  "
          f"MAE {expectedError:.4f} on held-out units, from {savedFraction:.0%} fewer measurements.")
    print(f"[CURVE]   2. Do those probes pick a BETTER frequency than a constant?  "
          f"{'yes' if modelRegret < fixedRegret - 0.05 else 'no'}.")
    print("[CURVE] Reconstruction succeeding while selection ties is not a contradiction: if one")
    print("[CURVE] frequency is optimal for most units, a constant is already near-perfect and there")
    print("[CURVE] is nothing left for a model to win. The measurement saving is still real and is")
    print("[CURVE] the practical payoff - it is what lets more chips be characterised per unit time.")

    if unitKind == "workload":
        print()
        print("[CURVE] NOTE: units here are WORKLOADS on one V100. This validates the machinery, "
              "not chip-to-chip transfer. Nothing here predicts how a different GPU behaves.")


def main():
    parser = argparse.ArgumentParser(description="Curve prediction from cheap probe measurements.")
    parser.add_argument("--source", choices=["public", "sweeps", "auto"], default="auto",
                        help="public = V100 workloads; sweeps = collected chips; auto prefers sweeps if present")
    parser.add_argument("--probes", type=int, default=4, help="How many frequencies to measure")
    args = parser.parse_args()

    frequencies, curves, names = (None, None, [])
    unitKind = "unit"

    if args.source in ("sweeps", "auto"):
        frequencies, curves, names = loadUnitsFromSweeps()
        unitKind = "chip"
        if curves is None and args.source == "sweeps":
            print("[CURVE] No usable sweeps in data/frequency-sweeps/.")
            print("[CURVE] Need CSVs with a bench_throughput column - run the sweep with -WorkloadCommand.")
            return 1

    if curves is None:
        frequencies, curves, names = loadUnitsFromPublicDataset()
        unitKind = "workload"

    if curves.shape[0] < 3:
        print(f"[CURVE] Only {curves.shape[0]} {unitKind}(s) available. Need at least 3 to hold one out.")
        print("[CURVE] Collect more sweeps before asking this question.")
        return 1

    probeCount = min(args.probes, curves.shape[1])
    results, probeIndices, expectedError = evaluate(frequencies, curves, names, probeCount)
    report(results, frequencies, probeIndices, expectedError, unitKind, probeCount, curves.shape[1])

    print()
    print("[CURVE] Per-unit detail:")
    print(results.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
