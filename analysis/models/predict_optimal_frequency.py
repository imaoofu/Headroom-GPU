"""
Predict each workload's efficiency-optimal frequency, and check whether that
prediction is worth anything against baselines that require no model at all.

THE TASK
    A workload arrives. You are allowed to measure it at a few cheap probe
    frequencies. Which core frequency should you actually run it at to get the
    best performance-per-watt?

WHY PROBES ARE A FAIR THING TO ASSUME
    Measuring at stock costs nothing - stock is where the card already runs.
    Measuring two or three low frequencies is a few minutes of work. Sweeping all
    thirteen is what we are trying to avoid, so the probe set never includes the
    answer.

VALIDATION
    Leave-one-workload-out. The held-out workload's full curve is never seen during
    fitting. Splitting on rows instead of workloads would let the model see the same
    workload at a neighbouring frequency and score far better than it deserves.

THE BASELINES EXIST TO EMBARRASS THE MODEL
    If a single fixed frequency chosen from the training workloads does as well as
    the fitted model, the fitted model has not earned a slide. That result gets
    printed just as plainly as a win would.
"""

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

# Probe frequencies the model is allowed to measure. Stock is included because it
# is free, and the low end is included because that is where the curve bends.
DEFAULT_PROBE_FREQUENCIES_MHZ = (757, 885, 1012, REFERENCE_FREQUENCY_MHZ)


def buildMatrices(dataset):
    """Reshape the long dataset back into workload-by-frequency matrices."""
    performance = dataset.pivot(
        index="workload", columns="frequency_mhz", values="performance_normalised"
    )
    power = dataset.pivot(index="workload", columns="frequency_mhz", values="power_watts")
    efficiency = dataset.pivot(
        index="workload", columns="frequency_mhz", values="efficiency_normalised"
    )
    return performance, power, efficiency


def buildProbeFeatures(performance, power, probeFrequencies):
    """
    Turn the probe measurements into model features.

    Power is expressed as a ratio against stock rather than raw watts, so the features
    stay dimensionless. That matters for the eventual consumer-GPU comparison: a
    200 W card and a 300 W card can share a feature space, raw watts cannot.
    """
    probeFrequencies = list(probeFrequencies)
    performanceFeatures = performance[probeFrequencies]
    # The grid's own highest frequency, NOT REFERENCE_FREQUENCY_MHZ. On the V100 those are the
    # same number - 1530 is both the dataset's reference and its top point - so this changes
    # nothing there. On a consumer sweep the grid tops out at 3090 and the V100 constant is not a
    # column at all, which raised KeyError rather than producing a wrong number. That it failed
    # loudly is the only reason this was cheap to find.
    referenceFrequency = int(max(power.columns))
    powerFeatures = power[probeFrequencies].div(power[referenceFrequency], axis=0)

    performanceFeatures.columns = [f"performance_at_{frequency}" for frequency in probeFrequencies]
    powerFeatures.columns = [f"power_ratio_at_{frequency}" for frequency in probeFrequencies]
    return pd.concat([performanceFeatures, powerFeatures], axis=1)


def regretFor(efficiency, workload, chosenFrequency):
    """
    Efficiency given up by running `workload` at `chosenFrequency` instead of its best.

    Reported in percentage points of normalised efficiency. Zero means the choice was
    exactly optimal; larger is worse. Regret is the honest metric here because picking
    a neighbouring frequency on a flat curve costs almost nothing, while "wrong answer"
    would score it the same as picking the worst frequency on the grid.
    """
    curve = efficiency.loc[workload]
    return (curve.max() - curve[chosenFrequency]) * 100.0


def evaluateStrategy(efficiency, chosenFrequencyByWorkload):
    """Score one strategy's frequency choices across every workload."""
    regrets = []
    exactMatches = []
    frequencyErrors = []

    for workload, chosenFrequency in chosenFrequencyByWorkload.items():
        curve = efficiency.loc[workload]
        trueOptimum = int(curve.idxmax())
        regrets.append(regretFor(efficiency, workload, chosenFrequency))
        exactMatches.append(chosenFrequency == trueOptimum)
        frequencyErrors.append(abs(chosenFrequency - trueOptimum))

    return {
        "mean_regret_pct": float(np.mean(regrets)),
        "median_regret_pct": float(np.median(regrets)),
        "worst_regret_pct": float(np.max(regrets)),
        "exact_match_rate": float(np.mean(exactMatches)),
        "mean_frequency_error_mhz": float(np.mean(frequencyErrors)),
    }


def chooseByStock(efficiency, workloads):
    """Baseline 0 - do nothing. Run everything at stock, like the card does by default.

    "Stock" is the top of the grid: on the V100 that is 1530 MHz, its published reference, and on
    a consumer sweep it is the highest commanded target, where the card boosts as it pleases.
    Taking the grid maximum rather than the V100 constant makes both cases the same statement -
    do nothing and let the hardware run - and is identical on the V100.
    """
    return {workload: int(max(efficiency.columns)) for workload in workloads}


def chooseByBestFixedFrequency(trainingEfficiency, workloads):
    """
    Baseline 1 - one fixed frequency for everything, learned from the training workloads.

    This is the baseline that should worry us. It needs no per-workload measurement at
    all, so a probe-based model has to clear it by enough to justify the probing.
    """
    meanEfficiencyByFrequency = trainingEfficiency.mean(axis=0)
    bestFixed = int(meanEfficiencyByFrequency.idxmax())
    return {workload: bestFixed for workload in workloads}, bestFixed


def chooseByProbeModel(trainingFeatures, trainingEfficiency, heldOutFeatures, frequencies):
    """
    The actual model - predict the whole efficiency curve from probes, then take its peak.

    Predicting the curve rather than the optimal frequency directly means a wrong answer
    tends to be a neighbouring frequency on a flat part of the curve, not an arbitrary one.
    """
    model = Ridge(alpha=1.0)
    model.fit(trainingFeatures.to_numpy(), trainingEfficiency.to_numpy())
    predictedCurve = model.predict(heldOutFeatures.to_numpy().reshape(1, -1))[0]
    return int(frequencies[int(np.argmax(predictedCurve))])


def runLeaveOneWorkloadOut(dataset, probeFrequencies=DEFAULT_PROBE_FREQUENCIES_MHZ):
    """Run the full evaluation and return a scores table."""
    performance, power, efficiency = buildMatrices(dataset)
    features = buildProbeFeatures(performance, power, probeFrequencies)
    frequencies = np.array(efficiency.columns, dtype=int)
    workloads = list(efficiency.index)

    modelChoices = {}
    fixedChoices = {}
    chosenFixedFrequencies = []

    for heldOutWorkload in workloads:
        trainingMask = [workload != heldOutWorkload for workload in workloads]
        trainingFeatures = features[trainingMask]
        trainingEfficiency = efficiency[trainingMask]

        modelChoices[heldOutWorkload] = chooseByProbeModel(
            trainingFeatures, trainingEfficiency, features.loc[heldOutWorkload], frequencies
        )

        fixedChoice, bestFixed = chooseByBestFixedFrequency(trainingEfficiency, [heldOutWorkload])
        fixedChoices.update(fixedChoice)
        chosenFixedFrequencies.append(bestFixed)

    scores = pd.DataFrame(
        {
            "stock (do nothing)": evaluateStrategy(efficiency, chooseByStock(efficiency, workloads)),
            "best fixed frequency": evaluateStrategy(efficiency, fixedChoices),
            "probe model (ridge)": evaluateStrategy(efficiency, modelChoices),
        }
    ).T

    return scores, modelChoices, fixedChoices, chosenFixedFrequencies


def reportScores(scores, chosenFixedFrequencies, probeFrequencies):
    """Print the comparison, then say plainly whether the model earned its place."""
    print(
        f"[MODEL] Leave-one-workload-out evaluation, probing at "
        f"{', '.join(str(frequency) for frequency in probeFrequencies)} MHz."
    )
    print(
        f"[MODEL] The best-fixed-frequency baseline chose "
        f"{pd.Series(chosenFixedFrequencies).mode().iloc[0]} MHz in the majority of folds."
    )
    print()
    print("[MODEL] Scores (regret = efficiency given up versus each workload's true optimum):")
    print(scores.round(3).to_string())
    print()

    modelRegret = scores.loc["probe model (ridge)", "mean_regret_pct"]
    fixedRegret = scores.loc["best fixed frequency", "mean_regret_pct"]
    stockRegret = scores.loc["stock (do nothing)", "mean_regret_pct"]

    print(
        f"[MODEL] Against doing nothing, choosing a frequency at all recovers "
        f"{stockRegret - min(modelRegret, fixedRegret):.2f} percentage points of efficiency."
    )

    if modelRegret < fixedRegret - 0.05:
        print(
            f"[MODEL] The probe model beats the fixed-frequency baseline "
            f"({modelRegret:.3f}% vs {fixedRegret:.3f}% mean regret). Per-workload probing is "
            f"doing real work here."
        )
    elif modelRegret > fixedRegret + 0.05:
        print(
            f"[MODEL] The probe model LOSES to the fixed-frequency baseline "
            f"({modelRegret:.3f}% vs {fixedRegret:.3f}% mean regret). Report this as the result. "
            f"On this dataset, per-workload probing is not worth its cost."
        )
    else:
        print(
            f"[MODEL] The probe model and the fixed-frequency baseline are within noise of each "
            f"other ({modelRegret:.3f}% vs {fixedRegret:.3f}% mean regret). A model that ties a "
            f"lookup table has not earned a slide - say so."
        )

    print(
        "[MODEL] CAVEAT: 33 workloads on one V100 is a small sample and every number above is "
        "in-dataset. None of it transfers to a consumer GPU without being retested there."
    )


def main():
    dataset = loadDataset(validate=False)
    scores, modelChoices, fixedChoices, chosenFixedFrequencies = runLeaveOneWorkloadOut(dataset)
    reportScores(scores, chosenFixedFrequencies, DEFAULT_PROBE_FREQUENCIES_MHZ)

    print()
    print("[MODEL] Per-workload choices (model vs fixed baseline vs truth):")
    _, _, efficiency = buildMatrices(dataset)
    rows = []
    for workload in efficiency.index:
        rows.append(
            {
                "workload": workload,
                "true_optimum": int(efficiency.loc[workload].idxmax()),
                "model_choice": modelChoices[workload],
                "fixed_choice": fixedChoices[workload],
                "model_regret_pct": round(regretFor(efficiency, workload, modelChoices[workload]), 2),
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
