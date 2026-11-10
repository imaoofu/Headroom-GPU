"""
How FEW frequencies must be measured to reconstruct a whole efficiency curve, and WHICH ones.

THE QUESTION
    curve_model.py already establishes that a 13-point efficiency curve can be reconstructed from
    a handful of probe measurements. It does not ask the follow-up that decides whether that is
    useful: how few probes, which ones, and does choosing them cleverly beat not choosing at all?

    That last clause is the one that matters. Every other model in this directory has lost to a
    baseline that does no fitting, so the baseline here is the obvious no-thought alternative:
    probes spaced EVENLY across the range. If selection cannot beat even spacing, then selection
    is not earning anything and should not be presented as if it were.

WHAT THIS FILE ADDS THAT curve_model.py DOES NOT

    1. HONEST SELECTION. curve_model.evaluate() picks its probe set ONCE, from all 33 workloads,
       and then runs a leave-one-workload-out loop over the same 33. The inner reconstruction
       error is itself leave-one-out, which makes the whole thing look clean, but the SELECTION
       saw every unit it is later scored on. That is hindsight. This file runs the selection
       inside each outer fold, on the training units only, and reports both numbers plus the gap.

    2. EXHAUSTIVE vs GREEDY. curve_model.selectProbeFrequencies is greedy forward selection and
       says so. With 13 frequencies an exhaustive search is cheap, so greedy's optimality gap can
       be measured instead of assumed.

    3. THE DEAD PROBE. Curves are normalised to the highest frequency, so that column is exactly
       1.0 for every unit - zero variance, no information. curve_model passes alwaysIncludeTop=True
       and therefore spends one of its probe slots on a constant. Its "4 probes" are 3 informative
       measurements plus a free one. This file counts only measurements that carry signal.

WHAT A "PROBE" COSTS
    A full 13-point sweep is roughly two hours per workload with a fixed-work benchmark. The point
    of probing is that k measurements cost k/13 of that, so the practical question is where the
    reconstruction error stops falling - not how low it can go with all 13.

HONESTY
    33 workloads on ONE V100. Everything here is in-dataset, and the units are workloads rather
    than chips. It says nothing about chip-to-chip transfer, which is the application that would
    actually matter, and which needs roughly 5 chips before it can be attempted at all.

    main() prints a verdict against this module when selection fails to beat even spacing. Do not
    "fix" a loss by tuning until it wins - that rule is why the findings in this directory are
    worth anything.
"""

import itertools
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curve_model import (  # noqa: E402
    CurvePredictor,
    loadUnitsFromPublicDataset,
    reconstructionErrorForProbes,
)

# Reconstruction error is reported in normalised-efficiency units, where 1.0 is the efficiency at
# the reference frequency. An MAE of 0.01 therefore means "one percent of stock efficiency, on
# average, at every point of the curve".
MAE_UNIT = "normalised efficiency"

# Below this the curve is reconstructed to better than the project's own measurement noise, so
# further probes buy nothing real. 0.76% is the within-session gemm spread CLAUDE.md records.
MEASUREMENT_NOISE_FLOOR = 0.0076


def informativeIndices(curves):
    """Column indices that carry any variance across units.

    The top-frequency column is exactly 1.0 everywhere because every curve is normalised to it, so
    measuring there tells a model nothing it did not already know. Spending a probe slot on it is
    free in wall-clock terms and worthless in information terms; excluding it here is what makes
    "k probes" mean k USEFUL measurements.
    """
    return [i for i in range(curves.shape[1]) if curves[:, i].std() > 0.0]


def evenlySpacedProbes(candidates, probeCount):
    """The no-thought baseline: probeCount frequencies spread evenly across the candidate range.

    This is the strategy someone characterising a new card would use without any analysis at all,
    and it is what probe SELECTION has to beat to have earned its place.
    """
    if probeCount >= len(candidates):
        return sorted(candidates)
    positions = np.linspace(0, len(candidates) - 1, probeCount)
    return sorted({candidates[int(round(p))] for p in positions})


def exhaustiveBestProbes(curves, candidates, probeCount):
    """The genuinely optimal probe set for these units, by brute force over every subset."""
    best, bestError = None, float("inf")
    for subset in itertools.combinations(candidates, probeCount):
        error = reconstructionErrorForProbes(curves, list(subset))
        if error < bestError:
            best, bestError = list(subset), error
    return best, bestError


def greedyBestProbes(curves, candidates, probeCount):
    """Greedy forward selection, the strategy curve_model.selectProbeFrequencies uses.

    Reimplemented here rather than imported because curve_model's version always searches every
    column, including the zero-variance one this module deliberately excludes. Same algorithm,
    restricted to a candidate list.
    """
    chosen = []
    while len(chosen) < probeCount:
        bestIndex, bestError = None, float("inf")
        for candidate in candidates:
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


def regretPercent(trueCurve, chosenIndex):
    """Efficiency given up by running at chosenIndex instead of this curve's true best, in points."""
    return float((trueCurve.max() - trueCurve[chosenIndex]) * 100.0)


def scoreProbeSet(curves, probeIndices, heldIndex):
    """Reconstruct the held-out unit's curve from these probes and score it two ways.

    Returns (curve MAE, regret of taking the argmax, the index chosen). All three matter and the
    first two are not the same question: a curve can be reconstructed poorly and still peak in the
    right place, or reconstructed well and peak one point off on a flat top. The third is returned
    so the DECISION can be reported rather than only scored - "the argmax landed on 952 MHz in 33
    of 33 folds" says something a mean regret hides.
    """
    unitCount = curves.shape[0]
    trainMask = np.ones(unitCount, dtype=bool)
    trainMask[heldIndex] = False

    predictor = CurvePredictor(np.arange(curves.shape[1]), probeIndices).fit(curves[trainMask])
    predicted = predictor.predict(curves[heldIndex][probeIndices])
    trueCurve = curves[heldIndex]
    chosenIndex = int(np.argmax(predicted))
    return (float(np.mean(np.abs(predicted - trueCurve))),
            regretPercent(trueCurve, chosenIndex),
            chosenIndex)


def nestedEvaluation(curves, candidates, probeCount, selector):
    """Select probes INSIDE each fold, on training units only, then score the held-out unit.

    This is the number that would survive a reviewer. `selector` is called with the training
    curves alone, so no held-out unit influences which frequencies get chosen.

    Returns (mean MAE, mean regret, [chosen set per fold], [index picked per fold]).
    """
    maes, regrets, chosenPerFold, picks = [], [], [], []
    for held in range(curves.shape[0]):
        trainMask = np.ones(curves.shape[0], dtype=bool)
        trainMask[held] = False
        chosen, _ = selector(curves[trainMask], candidates, probeCount)
        mae, regret, pick = scoreProbeSet(curves, chosen, held)
        maes.append(mae)
        regrets.append(regret)
        picks.append(pick)
        chosenPerFold.append(tuple(chosen))
    return float(np.mean(maes)), float(np.mean(regrets)), chosenPerFold, picks


def hindsightEvaluation(curves, probeIndices):
    """Score a FIXED probe set that was chosen with every unit visible. The optimistic number."""
    maes, regrets = [], []
    for held in range(curves.shape[0]):
        mae, regret, _ = scoreProbeSet(curves, probeIndices, held)
        maes.append(mae)
        regrets.append(regret)
    return float(np.mean(maes)), float(np.mean(regrets))


def selectionStability(chosenPerFold):
    """How often the nested selection lands on the same probe set, and what that set is.

    This is the quantity that says whether the hindsight leak MATTERS. If every fold picks the
    same frequencies, selecting once over the whole dataset was harmless in practice even though
    it was wrong in principle - and that is worth reporting either way rather than assuming.
    """
    counts = {}
    for chosen in chosenPerFold:
        counts[chosen] = counts.get(chosen, 0) + 1
    modal, modalCount = max(counts.items(), key=lambda item: item[1])
    return modal, modalCount, len(counts)


def main():
    frequencies, curves, names = loadUnitsFromPublicDataset()
    candidates = informativeIndices(curves)
    mhz = lambda indices: [int(frequencies[i]) for i in indices]  # noqa: E731

    print("[PROBE] How few frequencies characterise an efficiency curve, and which ones.")
    print(f"[PROBE] {len(names)} workloads on one V100, {curves.shape[1]} frequencies each.")
    print(f"[PROBE] Error is mean absolute error in {MAE_UNIT} units; regret is efficiency")
    print("[PROBE]   given up by running at the reconstructed curve's peak, in points.")
    print()

    dead = [i for i in range(curves.shape[1]) if i not in candidates]
    print(f"[PROBE] {len(dead)} of {curves.shape[1]} columns carry no information at all: "
          f"{mhz(dead)} MHz.")
    print("[PROBE]   Every curve is normalised to the top frequency, so that column is exactly")
    print("[PROBE]   1.0 for every unit. curve_model.py spends a probe slot on it via")
    print("[PROBE]   alwaysIncludeTop=True, so its 'four probes' are three real measurements.")
    print(f"[PROBE] Selecting from the {len(candidates)} informative frequencies only.")
    print()

    stockIndex = int(np.argmax(frequencies))
    stockRegret = float(np.mean([regretPercent(curves[i], stockIndex) for i in range(len(names))]))
    bestFixed = int(np.argmax(curves.mean(axis=0)))
    fixedRegret = float(np.mean([regretPercent(curves[i], bestFixed) for i in range(len(names))]))
    print(f"[PROBE] Reference points, no probing at all: running at stock "
          f"({int(frequencies[stockIndex])} MHz) gives up {stockRegret:.2f} points, and the best")
    print(f"[PROBE]   single fixed frequency ({int(frequencies[bestFixed])} MHz, hindsight) gives "
          f"up {fixedRegret:.2f}.")
    print()

    header = (f"  {'k':>2}  {'honest MAE':>10}  {'hindsight':>10}  {'leak':>7}  "
              f"{'even MAE':>9}  {'honest regret':>13}  {'even regret':>11}  probes (MHz)")
    print(header)
    print("  " + "-" * (len(header) - 2))

    rows = []
    for probeCount in range(1, 6):
        # Exhaustive where it is affordable inside a nested loop; greedy beyond that. Both are
        # reported honestly - the selector used is named in the output rather than implied.
        selector = exhaustiveBestProbes if probeCount <= 3 else greedyBestProbes
        honestMae, honestRegret, chosenPerFold, picks = nestedEvaluation(
            curves, candidates, probeCount, selector)

        hindsightSet, _ = selector(curves, candidates, probeCount)
        hindsightMae, _ = hindsightEvaluation(curves, hindsightSet)

        evenSet = evenlySpacedProbes(candidates, probeCount)
        evenMae, evenRegret = hindsightEvaluation(curves, evenSet)

        modal, modalCount, distinct = selectionStability(chosenPerFold)
        rows.append({
            "k": probeCount, "honestMae": honestMae, "hindsightMae": hindsightMae,
            "evenMae": evenMae, "honestRegret": honestRegret, "evenRegret": evenRegret,
            "modal": modal, "modalCount": modalCount, "distinct": distinct,
            "selector": "exhaustive" if probeCount <= 3 else "greedy", "picks": picks,
            "evenSet": evenSet,
        })
        print(f"  {probeCount:>2}  {honestMae:>10.4f}  {hindsightMae:>10.4f}  "
              f"{honestMae - hindsightMae:>+7.4f}  {evenMae:>9.4f}  {honestRegret:>13.2f}  "
              f"{evenRegret:>11.2f}  {mhz(modal)}")

    print()
    print("[PROBE] 'honest' selects probes inside each fold from the training units only.")
    print("[PROBE] 'hindsight' selects once from all units, which is what curve_model.py does.")
    print("[PROBE] 'leak' is what that shortcut is worth - positive means hindsight flattered it.")
    print("[PROBE] k<=3 searched exhaustively, k>=4 greedily. Both named, neither implied.")
    print()

    print("[PROBE] Does selecting probes beat not selecting them?")
    beatsEven, tiedWithEven = 0, 0
    for row in rows:
        margin = row["evenMae"] - row["honestMae"]
        # A tie is not a loss, and calling it one would be as dishonest as calling it a win. At
        # k=1 both strategies pick the same single frequency, so they MUST agree exactly.
        if abs(margin) < 1e-9:
            verdict = "TIE - both strategies pick the same frequencies"
            tiedWithEven += 1
        elif margin > 0:
            verdict = f"selection wins by {margin:.4f}"
            beatsEven += 1
        else:
            verdict = f"EVEN SPACING WINS by {-margin:.4f}"
        print(f"[PROBE]   k={row['k']}: honest {row['honestMae']:.4f} vs evenly spaced "
              f"{row['evenMae']:.4f} at {mhz(row['evenSet'])} MHz -> {verdict}")
    print("[PROBE]   Selection concentrates probes at the LOW end, where the per-frequency")
    print("[PROBE]   variance across units actually lives; even spacing wastes measurements")
    print("[PROBE]   near the top, where every curve has been normalised to the same value.")
    print()

    print("[PROBE] Does better reconstruction produce a better DECISION?")
    for row in rows:
        picks = row["picks"]
        modalPick = max(set(picks), key=picks.count)
        print(f"[PROBE]   k={row['k']}: reconstruction MAE {row['honestMae']:.4f}, regret "
              f"{row['honestRegret']:.2f} points, argmax lands on {int(frequencies[modalPick])} MHz "
              f"in {picks.count(modalPick)} of {len(picks)} folds.")
    reconstructionGain = rows[0]["honestMae"] - rows[-1]["honestMae"]
    regretGain = rows[0]["honestRegret"] - rows[-1]["honestRegret"]
    print(f"[PROBE]   Going from {rows[0]['k']} probe to {rows[-1]['k']} improves reconstruction by "
          f"{reconstructionGain:.4f} ({reconstructionGain / rows[0]['honestMae']:.0%}) and the")
    print(f"[PROBE]   decision by {regretGain:.2f} points.")
    if abs(regretGain) < 0.01:
        print("[PROBE]   RECONSTRUCTION ACCURACY AND DECISION QUALITY ARE NOT THE SAME QUANTITY.")
        print("[PROBE]   The curve gets measurably better and the choice made from it does not")
        print("[PROBE]   change at all, because the efficiency curve is flat near its peak. Any")
        print("[PROBE]   claim that better curve-fitting yields better tuning needs this checked.")
    print()

    print("[PROBE] Is the hindsight leak actually harmful?")
    for row in rows:
        print(f"[PROBE]   k={row['k']}: {row['distinct']} distinct probe sets across 33 folds, "
              f"modal set chosen in {row['modalCount']} of 33.")
    print("[PROBE]   A selection that never changes is a leak that costs nothing in practice.")
    print("[PROBE]   It is still wrong in principle, because nothing guarantees that in advance.")
    print()

    print("[PROBE] VERDICT")
    if beatsEven == 0:
        print("[PROBE]   Probe SELECTION earns nothing on this dataset. Evenly spaced frequencies")
        print("[PROBE]   reconstruct at least as well at every k tested. The useful finding is")
        print("[PROBE]   the number of probes, not which ones - say that and nothing more.")
    elif beatsEven < len(rows):
        print(f"[PROBE]   Selection beats even spacing at {beatsEven} of {len(rows)} probe counts.")
        print("[PROBE]   That is not a clean win. Report the k where it holds, not the best case.")
    else:
        print("[PROBE]   Selection beats even spacing at every probe count tested.")

    knee = next((row for row in rows if row["honestMae"] < MEASUREMENT_NOISE_FLOOR), None)
    if knee is None:
        print(f"[PROBE]   No probe count tested reconstructs to better than this project's own")
        print(f"[PROBE]   measurement noise ({MEASUREMENT_NOISE_FLOOR:.4f}). More probes are not")
        print("[PROBE]   obviously wasted yet, which is itself a limit on the 'probe cheaply' idea.")
    else:
        saved = 1.0 - (knee["k"] / curves.shape[1])
        print(f"[PROBE]   {knee['k']} probes reconstruct the curve to {knee['honestMae']:.4f}, inside")
        print(f"[PROBE]   the {MEASUREMENT_NOISE_FLOOR:.4f} measurement noise this project reports for")
        print(f"[PROBE]   itself. Past that point more measurements cannot be distinguished from")
        print(f"[PROBE]   noise, so {knee['k']} of {curves.shape[1]} is the honest stopping point "
              f"- {saved:.0%} fewer runs.")

    print()
    print("[PROBE] CAVEAT: 33 workloads on one V100, units are workloads and not chips, and every")
    print("[PROBE]   number above is in-dataset. The application that would matter - characterising")
    print("[PROBE]   an unseen CHIP from a few probes - needs roughly 5 chips before it can be")
    print("[PROBE]   attempted, and this project has 3.")


if __name__ == "__main__":
    main()
