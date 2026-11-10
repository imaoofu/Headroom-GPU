"""
Does probing beat a fixed frequency UNDER a performance constraint?

WHY THIS EXISTS SEPARATELY FROM predict_optimal_frequency.py
    That script asks: which frequency gives the best performance-per-watt, at any cost?
    It reports a null - the probe model ties a fixed 952 MHz, 0.883% against 0.837% mean
    regret. That null is honest and it stands.

    But it was measured on the version of the problem with almost nothing in it. 952 MHz
    is the true optimum for 24 of 33 workloads, so a constant is nearly the right answer
    everywhere and there is very little per-workload variation left for any model to
    exploit. The model tied because the answer is nearly constant, not because probing
    carries no information.

    analyze_constrained.py then measured the same comparison under a performance floor and
    found the opposite shape: at a 95% floor, per-workload selection gains 28.5% efficiency
    against a fixed frequency's 4.9%. A fixed policy must hold its guarantee on EVERY
    workload it might meet, so it is pinned by the most sensitive one - BiCG, which needs
    1462 MHz - while CNN_1.5M would have been fine at 757. That 23.6-point gap is 83% of
    all gain available at that floor, and it is headroom a predictor could compete for.

    Nothing had competed for it. Neither predictor contained any notion of a floor. This
    module is that comparison.

WHAT THE MODEL HAS TO DO THAT IT DID NOT BEFORE
    Two things, and the second is new.

    1. Predict where efficiency peaks - the old task.
    2. Predict WHERE THE FLOOR STOPS BINDING. Under a constraint the answer is usually
       max(unconstrained optimum, lowest feasible frequency), and at a 95% floor the second
       term is what binds for most workloads. So the task is really "predict the lowest
       frequency at which this workload still retains 95% of its stock performance", which
       is a performance-curve question, not an efficiency-peak question.

    The probes are at 757, 885, 1012 and 1530 MHz. The region the floor actually binds in -
    roughly 1012 to 1530 - contains five grid points and is bracketed by only its endpoints.
    That gap is the difficulty of this task.

MEASUREMENTS ARE NOT PREDICTIONS
    At a probe frequency the value was measured, so the strategy uses the measurement and
    not the model's guess about it. Anything else would be scoring the model on a question
    nobody would ask it in practice. It also means stock is always known-feasible -
    performance is normalised to 1.0 at 1530 MHz - so no strategy can be forced into an
    infeasible corner.

THE METRIC THAT DOES NOT EXIST IN THE UNCONSTRAINED VERSION
    A strategy can now CHEAT. Predicting the performance curve wrongly can put the choice
    below the floor, which buys efficiency the constraint was supposed to forbid. So regret
    alone cannot rank strategies here: a violated floor shows up as NEGATIVE regret, which
    looks like beating the oracle and is not.

    Violations are therefore reported beside every regret figure, and a strategy with lower
    regret and more violations has not won. Read the two columns together or not at all.

THE BASELINES EXIST TO EMBARRASS THE MODEL
    Three of them, and the third is the one that should worry us:

    stock            - do nothing. Always feasible, gains nothing. The floor of the problem.
    best fixed freq  - one frequency that holds the floor on every TRAINING workload. This
                       is 5.6.1's baseline made leave-one-out honest, and it can violate the
                       floor on the held-out workload, which is a real cost of not probing.
    interpolation    - straight lines between the probe points. No fitting at all. If Ridge
                       cannot beat drawing four line segments, the fitting is decoration.

USAGE
    python analysis/predict_constrained_frequency.py
    python analysis/predict_constrained_frequency.py --floors 0.95 0.90
"""

import argparse

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

import sys
from pathlib import Path

# analysis/ holds load_data.py. Added explicitly because Python puts only THIS file's directory
# (analysis/models/) on the path, and every module here is run as a script rather than imported
# as a package - see analysis/models/README.md for why it is not a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from load_data import loadDataset
from predict_optimal_frequency import (
    DEFAULT_PROBE_FREQUENCIES_MHZ,
    buildMatrices,
    buildProbeFeatures,
)

# 0.99 and 1.00 are deliberately absent. analyze_constrained.py documents why: four V100
# workloads record performance ABOVE their own 1530 MHz value at some lower frequency, by up
# to 1.44 points, so a floor inside that band is being applied at finer resolution than the
# data supports. Those rows are unquotable there and would be unquotable here.
DEFAULT_FLOORS = (0.95, 0.90, 0.85)

# Float slop only. The published CSVs carry four decimals, so this never decides a real case.
FEASIBILITY_TOLERANCE = 1e-9


def trueConstrainedOptimum(performance, efficiency, workload, floor):
    """
    The oracle: best efficiency among frequencies this workload ACTUALLY holds the floor at.

    Brute force over the feasible set, matching analyze_constrained.constrainedOptimum rather
    than using the max(unconstrained, lowest-feasible) closed form. The closed form is only
    valid when performance is monotonic in frequency, which the V100 data violates in places,
    and a strategy scored against a shortcut that is wrong for four workloads is scored wrong.
    """
    performanceCurve = performance.loc[workload]
    efficiencyCurve = efficiency.loc[workload]
    feasible = performanceCurve[performanceCurve >= floor - FEASIBILITY_TOLERANCE].index
    return int(efficiencyCurve[feasible].idxmax())


def bestFixedFrequencyHoldingFloor(trainingPerformance, trainingEfficiency, floor):
    """
    One frequency for everything, required to hold the floor on EVERY training workload.

    This is the whole mechanism of 5.6.1. A policy that promises "you keep 95% of your
    performance" has to keep that promise on every workload it might meet, so it cannot pick
    a frequency that is merely fine on average - it is pinned by the most frequency-sensitive
    workload in the training set.

    The highest frequency on the grid is always in the feasible set, since every curve in this
    project is normalised to its own maximum measured frequency - performance is 1.0 there and
    every floor considered is at or below 1.0. So this never returns nothing.
    """
    holdsEverywhere = (trainingPerformance >= floor - FEASIBILITY_TOLERANCE).all(axis=0)
    feasibleFrequencies = holdsEverywhere[holdsEverywhere].index
    if len(feasibleFrequencies) == 0:
        # Not REFERENCE_FREQUENCY_MHZ. That constant is the V100's 1530, which is this grid's
        # maximum only by coincidence; on a consumer sweep it is a frequency the card never ran.
        return int(max(trainingPerformance.columns))
    return int(trainingEfficiency[feasibleFrequencies].mean(axis=0).idxmax())


def spliceProbeMeasurements(predictedCurve, trueCurve, frequencies, probeFrequencies):
    """
    Replace the prediction with the measurement wherever a measurement exists.

    The probes were run. Scoring a strategy on its guess at a frequency it actually measured
    would be measuring the wrong thing, and it would understate every strategy equally rather
    than harmlessly - the reference frequency is a probe, and it is the one point whose
    feasibility must never be in doubt.
    """
    spliced = np.asarray(predictedCurve, dtype=float).copy()
    probeSet = set(probeFrequencies)
    for index, frequency in enumerate(frequencies):
        if int(frequency) in probeSet:
            spliced[index] = float(trueCurve[int(frequency)])
    return spliced


def chooseUnderFloor(performanceCurve, efficiencyCurve, frequencies, floor):
    """
    Most efficient frequency that this pair of curves SAYS holds the floor.

    The curves passed in may be predicted, measured, or a mix. Whether the choice really
    holds the floor is decided later against the true curve - that separation is what makes
    a floor violation visible instead of impossible by construction.

    `floor` may be a scalar or a per-frequency array. The array form exists so a safety margin
    can be demanded where performance was PREDICTED and not where it was measured.
    """
    feasible = np.where(np.asarray(performanceCurve) >= np.asarray(floor) - FEASIBILITY_TOLERANCE)[0]
    if len(feasible) == 0:
        # The grid's own maximum, not REFERENCE_FREQUENCY_MHZ - see bestFixedFrequencyHoldingFloor.
        return int(max(frequencies))
    best = feasible[int(np.argmax(np.asarray(efficiencyCurve)[feasible]))]
    return int(frequencies[best])


def chooseByProbeModel(
    trainingFeatures,
    trainingPerformance,
    trainingEfficiency,
    heldOutFeatures,
    heldOutPerformance,
    heldOutEfficiency,
    frequencies,
    probeFrequencies,
    floor,
):
    """
    Two ridge fits - one for the performance curve, one for the efficiency curve.

    Two models rather than one because the constrained problem asks two questions and only
    one of them is about efficiency. Predicting efficiency alone cannot say which frequencies
    are allowed, and predicting performance alone cannot rank the ones that are.
    """
    features = trainingFeatures.to_numpy()
    performanceModel = Ridge(alpha=1.0).fit(features, trainingPerformance.to_numpy())
    efficiencyModel = Ridge(alpha=1.0).fit(features, trainingEfficiency.to_numpy())

    heldOut = heldOutFeatures.to_numpy().reshape(1, -1)
    predictedPerformance = spliceProbeMeasurements(
        performanceModel.predict(heldOut)[0], heldOutPerformance, frequencies, probeFrequencies
    )
    predictedEfficiency = spliceProbeMeasurements(
        efficiencyModel.predict(heldOut)[0], heldOutEfficiency, frequencies, probeFrequencies
    )
    return chooseUnderFloor(predictedPerformance, predictedEfficiency, frequencies, floor)


def calibrateSafetyMargin(
    trainingFeatures,
    trainingPerformance,
    frequencies,
    probeFrequencies,
    quantile=0.9,
):
    """
    How far does the performance model OVER-predict? Inner leave-one-out, training set only.

    A strategy that treats its own performance prediction as exact will break the floor
    whenever that prediction is optimistic, which on this data is often. The fix is to demand
    a margin - but the margin has to be earned from data the strategy is allowed to see, or it
    is just the answer smuggled in as a hyperparameter.

    So: an inner leave-one-out across the 32 training workloads, giving out-of-sample
    performance predictions for each, and the margin is a high quantile of the over-prediction
    error across all of them. In-sample residuals would have been cheaper and would have
    understated the error, which is the specific way this calibration fails silently.

    Clamped at zero. A model that never over-predicts needs no margin, and a negative margin
    would loosen the constraint rather than tighten it.
    """
    workloads = list(trainingPerformance.index)
    overPredictions = []
    for heldOut in workloads:
        innerMask = [workload != heldOut for workload in workloads]
        model = Ridge(alpha=1.0).fit(
            trainingFeatures[innerMask].to_numpy(), trainingPerformance[innerMask].to_numpy()
        )
        predicted = spliceProbeMeasurements(
            model.predict(trainingFeatures.loc[heldOut].to_numpy().reshape(1, -1))[0],
            trainingPerformance.loc[heldOut],
            frequencies,
            probeFrequencies,
        )
        overPredictions.extend((predicted - trainingPerformance.loc[heldOut].to_numpy()).tolist())
    return float(max(0.0, np.quantile(np.asarray(overPredictions), quantile)))


def perFrequencyFloor(floor, margin, frequencies, probeFrequencies):
    """
    Demand `floor + margin` where performance was predicted, plain `floor` where it was measured.

    Padding a measured point would be inventing uncertainty that does not exist, and it would
    do real damage: the reference frequency is a probe and is the one point whose feasibility
    must never be in doubt.
    """
    probeSet = set(int(frequency) for frequency in probeFrequencies)
    return np.array(
        [floor if int(frequency) in probeSet else floor + margin for frequency in frequencies],
        dtype=float,
    )


def chooseByCalibratedProbeModel(
    trainingFeatures,
    trainingPerformance,
    trainingEfficiency,
    heldOutFeatures,
    heldOutPerformance,
    heldOutEfficiency,
    frequencies,
    probeFrequencies,
    floor,
):
    """The same two ridge fits, required to leave itself room to be wrong about performance."""
    margin = calibrateSafetyMargin(
        trainingFeatures, trainingPerformance, frequencies, probeFrequencies
    )
    features = trainingFeatures.to_numpy()
    performanceModel = Ridge(alpha=1.0).fit(features, trainingPerformance.to_numpy())
    efficiencyModel = Ridge(alpha=1.0).fit(features, trainingEfficiency.to_numpy())

    heldOut = heldOutFeatures.to_numpy().reshape(1, -1)
    predictedPerformance = spliceProbeMeasurements(
        performanceModel.predict(heldOut)[0], heldOutPerformance, frequencies, probeFrequencies
    )
    predictedEfficiency = spliceProbeMeasurements(
        efficiencyModel.predict(heldOut)[0], heldOutEfficiency, frequencies, probeFrequencies
    )
    effectiveFloor = perFrequencyFloor(floor, margin, frequencies, probeFrequencies)
    return chooseUnderFloor(predictedPerformance, predictedEfficiency, frequencies, effectiveFloor), margin


def chooseByInterpolation(
    heldOutPerformance, heldOutEfficiency, frequencies, probeFrequencies, floor
):
    """
    Straight lines between the probes. No fitting, no training workloads, nothing learned.

    This is the baseline that should worry the model most. It uses exactly the same
    measurements the probe model does and spends nothing on them, so any gap between the two
    is what the fitting is actually worth. A tie here means the ridge fit is decoration.
    """
    probes = sorted(int(frequency) for frequency in probeFrequencies)
    performanceCurve = np.interp(
        frequencies, probes, [float(heldOutPerformance[frequency]) for frequency in probes]
    )
    efficiencyCurve = np.interp(
        frequencies, probes, [float(heldOutEfficiency[frequency]) for frequency in probes]
    )
    return chooseUnderFloor(performanceCurve, efficiencyCurve, frequencies, floor)


def evaluateStrategy(performance, efficiency, chosenFrequencyByWorkload, floor):
    """
    Score one strategy on both axes at once: what it gained, and whether it was allowed to.

    Regret can come out NEGATIVE here, and that is not a win - it means the strategy chose a
    frequency below the floor and collected efficiency the constraint forbade. That is why
    violations are returned alongside and never separately.
    """
    regrets, gains, violations, shortfalls, exactMatches = [], [], [], [], []

    for workload, chosenFrequency in chosenFrequencyByWorkload.items():
        efficiencyCurve = efficiency.loc[workload]
        performanceCurve = performance.loc[workload]
        oracle = trueConstrainedOptimum(performance, efficiency, workload, floor)

        regrets.append((efficiencyCurve[oracle] - efficiencyCurve[chosenFrequency]) * 100.0)
        gains.append((efficiencyCurve[chosenFrequency] - 1.0) * 100.0)

        shortfall = (floor - performanceCurve[chosenFrequency]) * 100.0
        violations.append(bool(shortfall > FEASIBILITY_TOLERANCE * 100.0))
        shortfalls.append(max(0.0, shortfall))
        exactMatches.append(chosenFrequency == oracle)

    return {
        "mean_gain_pct": float(np.mean(gains)),
        "mean_regret_pct": float(np.mean(regrets)),
        "worst_regret_pct": float(np.max(regrets)),
        "floor_violations": int(np.sum(violations)),
        "worst_violation_pp": float(np.max(shortfalls)),
        "exact_match_rate": float(np.mean(exactMatches)),
    }


def runLeaveOneWorkloadOut(dataset, floor, probeFrequencies=DEFAULT_PROBE_FREQUENCIES_MHZ):
    """
    Full leave-one-workload-out evaluation at one floor.

    The held-out workload's curve is never seen during fitting, and it is also excluded from
    the fixed baseline's choice of frequency. Leaving it in would let the baseline see the
    workload it is about to be scored on, which on this dataset is not a small effect: at a
    95% floor the policy frequency is set by a single workload, so including or excluding
    that one workload moves the baseline by more than the whole comparison.
    """
    performance, power, efficiency = buildMatrices(dataset)
    features = buildProbeFeatures(performance, power, probeFrequencies)
    frequencies = np.array(efficiency.columns, dtype=int)
    workloads = list(efficiency.index)

    modelChoices, fixedChoices, interpolationChoices, stockChoices = {}, {}, {}, {}
    calibratedChoices = {}
    chosenFixedFrequencies = []
    margins = []

    for heldOutWorkload in workloads:
        trainingMask = [workload != heldOutWorkload for workload in workloads]
        trainingFeatures = features[trainingMask]
        trainingPerformance = performance[trainingMask]
        trainingEfficiency = efficiency[trainingMask]

        modelChoices[heldOutWorkload] = chooseByProbeModel(
            trainingFeatures,
            trainingPerformance,
            trainingEfficiency,
            features.loc[heldOutWorkload],
            performance.loc[heldOutWorkload],
            efficiency.loc[heldOutWorkload],
            frequencies,
            probeFrequencies,
            floor,
        )

        calibratedChoice, margin = chooseByCalibratedProbeModel(
            trainingFeatures,
            trainingPerformance,
            trainingEfficiency,
            features.loc[heldOutWorkload],
            performance.loc[heldOutWorkload],
            efficiency.loc[heldOutWorkload],
            frequencies,
            probeFrequencies,
            floor,
        )
        calibratedChoices[heldOutWorkload] = calibratedChoice
        margins.append(margin)

        fixedFrequency = bestFixedFrequencyHoldingFloor(
            trainingPerformance, trainingEfficiency, floor
        )
        fixedChoices[heldOutWorkload] = fixedFrequency
        chosenFixedFrequencies.append(fixedFrequency)

        interpolationChoices[heldOutWorkload] = chooseByInterpolation(
            performance.loc[heldOutWorkload],
            efficiency.loc[heldOutWorkload],
            frequencies,
            probeFrequencies,
            floor,
        )

        # The grid's own maximum: that is where performance is normalised to 1.0, so it is
        # what 'do nothing' means on ANY grid, not only on the V100's.
        stockChoices[heldOutWorkload] = int(max(frequencies))

    oracleChoices = {
        workload: trueConstrainedOptimum(performance, efficiency, workload, floor)
        for workload in workloads
    }

    scores = pd.DataFrame(
        {
            "stock (do nothing)": evaluateStrategy(performance, efficiency, stockChoices, floor),
            "best fixed frequency": evaluateStrategy(performance, efficiency, fixedChoices, floor),
            "interpolation (no fit)": evaluateStrategy(
                performance, efficiency, interpolationChoices, floor
            ),
            "probe model (ridge)": evaluateStrategy(performance, efficiency, modelChoices, floor),
            "probe model (calibrated)": evaluateStrategy(
                performance, efficiency, calibratedChoices, floor
            ),
            "oracle (upper bound)": evaluateStrategy(performance, efficiency, oracleChoices, floor),
        }
    ).T

    return {
        "scores": scores,
        "model": modelChoices,
        "calibrated": calibratedChoices,
        "fixed": fixedChoices,
        "interpolation": interpolationChoices,
        "oracle": oracleChoices,
        "fixed_frequencies": chosenFixedFrequencies,
        "margins": margins,
    }


def reportFloor(result, floor, performance, efficiency):
    """
    Print one floor's comparison, ranking only the strategies that actually kept the promise.

    The previous version of this function ranked every strategy on regret and printed a verdict
    from whichever branch it fell into, which let it announce that 0.429% and 23.563% were
    "within noise" because neither the beats-branch nor the loses-branch matched. The
    fall-through case must be the one that claims LEAST, and the ranking must exclude strategies
    that broke the constraint - their regret is not a comparable quantity.
    """
    scores = result["scores"]
    total = len(result["model"])

    print(f"[CONSTRAINED] Floor {floor * 100:.0f}% - keep at least this share of stock performance.")
    print(
        f"[CONSTRAINED] The fixed baseline chose "
        f"{pd.Series(result['fixed_frequencies']).mode().iloc[0]} MHz in the majority of folds; "
        f"the calibrated model demanded a mean safety margin of "
        f"{100.0 * float(np.mean(result['margins'])):.2f} points."
    )
    print()
    print(scores.round(3).to_string())
    print()

    # Anything that broke the floor is out of the ranking. Said explicitly, once per strategy,
    # because a reader who skips this paragraph would otherwise read the regret column as a
    # league table and the cheapest-looking row is the one that cheated.
    disqualified = [
        name
        for name in scores.index
        if name != "oracle (upper bound)" and scores.loc[name, "floor_violations"] > 0
    ]
    for name in disqualified:
        print(
            f"[CONSTRAINED] DISQUALIFIED: '{name}' broke the floor on "
            f"{int(scores.loc[name, 'floor_violations'])} of {total} workloads, worst by "
            f"{scores.loc[name, 'worst_violation_pp']:.2f} points. Its "
            f"{scores.loc[name, 'mean_gain_pct']:.1f}% mean gain includes efficiency the "
            f"constraint forbade, so it is not comparable to a strategy that kept the floor."
        )
    if disqualified:
        print()

    feasible = [
        name
        for name in scores.index
        if name not in disqualified and name != "oracle (upper bound)"
    ]
    fixedGain = scores.loc["best fixed frequency", "mean_gain_pct"]
    oracleGain = scores.loc["oracle (upper bound)", "mean_gain_pct"]
    available = oracleGain - fixedGain

    print("[CONSTRAINED] Ranking among strategies that KEPT the floor on every workload:")
    for name in sorted(feasible, key=lambda n: -scores.loc[n, "mean_gain_pct"]):
        gain = scores.loc[name, "mean_gain_pct"]
        share = ""
        if available > 1e-9 and name not in ("best fixed frequency", "stock (do nothing)"):
            share = f"  ({100.0 * (gain - fixedGain) / available:.0f}% of the gap)"
        print(f"[CONSTRAINED]   {gain:6.1f}% mean efficiency gain  {name}{share}")
    print(f"[CONSTRAINED]   {oracleGain:6.1f}% mean efficiency gain  oracle (upper bound)")
    print()

    # The comparison the whole module exists to make.
    if "best fixed frequency" in feasible:
        best = max(feasible, key=lambda n: scores.loc[n, "mean_gain_pct"])
        if best == "best fixed frequency":
            print(
                "[CONSTRAINED] No constraint-respecting strategy beat the fixed frequency. "
                "Probing is not worth its cost at this floor either - report it as a second null."
            )
        else:
            bestGain = scores.loc[best, "mean_gain_pct"]
            print(
                f"[CONSTRAINED] '{best}' beats the fixed baseline {bestGain:.1f}% to "
                f"{fixedGain:.1f}% mean efficiency gain without ever breaking the floor - "
                f"{100.0 * (bestGain - fixedGain) / available:.0f}% of the gap 5.6.1 identified. "
                f"Under a constraint, probing IS worth its cost."
            )

    # And the one that decides whether the FITTING earned anything, separately from the probing.
    if "interpolation (no fit)" in feasible:
        interpolationGain = scores.loc["interpolation (no fit)", "mean_gain_pct"]
        fittedFeasible = [n for n in feasible if n.startswith("probe model")]
        if not fittedFeasible:
            print(
                "[CONSTRAINED] Every fitted variant broke the floor, so on this data the only "
                "constraint-respecting way to use the probes is to interpolate them. The "
                "FITTING has not earned a slide - the probing has."
            )
        else:
            bestFitted = max(fittedFeasible, key=lambda n: scores.loc[n, "mean_gain_pct"])
            bestFittedGain = scores.loc[bestFitted, "mean_gain_pct"]
            if bestFittedGain > interpolationGain + 0.5:
                print(
                    f"[CONSTRAINED] '{bestFitted}' beats plain interpolation between the same "
                    f"probes ({bestFittedGain:.1f}% vs {interpolationGain:.1f}%), so the fitting "
                    f"is carrying weight of its own."
                )
            else:
                print(
                    f"[CONSTRAINED] No fitted variant beats plain interpolation between the same "
                    f"probes ({bestFittedGain:.1f}% vs {interpolationGain:.1f}%). Whatever "
                    f"probing is worth here, the FITTING is not the part earning it."
                )
    print()


def measureInterpolationBias(performance, frequencies, probeFrequencies):
    """
    Why interpolation is safe here, as three measured quantities rather than an argument.

    Returns the share of second differences that curve DOWNWARD, the mean signed error of
    interpolated performance at the unprobed points, and the fraction of those that are
    under-estimates. Concave curve + straight-line interpolation = systematic under-estimate of
    performance = frequencies judged infeasible that were fine = choices biased upward.

    This is a diagnostic, not a result. Its job is to stop "interpolate the probes" being read as
    a general recommendation when it is a consequence of curve shape.
    """
    probes = sorted(int(frequency) for frequency in probeFrequencies)
    probeSet = set(probes)

    concave, convex = 0, 0
    errors = []
    for workload in performance.index:
        curve = performance.loc[workload]
        secondDifferences = np.diff(curve.to_numpy(dtype=float), 2)
        concave += int(np.sum(secondDifferences < 0))
        convex += int(np.sum(secondDifferences > 0))

        interpolated = np.interp(frequencies, probes, [float(curve[f]) for f in probes])
        for index, frequency in enumerate(frequencies):
            if int(frequency) not in probeSet:
                errors.append(interpolated[index] - float(curve[int(frequency)]))

    errors = np.asarray(errors)
    return {
        "concave_share": float(concave / (concave + convex)) if concave + convex else float("nan"),
        "mean_error_pp": float(100.0 * errors.mean()),
        "under_estimate_share": float(np.mean(errors < 0)),
    }


def reportInterpolationBias(performance, frequencies, probeFrequencies):
    """Print the mechanism, and the condition under which it would stop holding."""
    bias = measureInterpolationBias(performance, frequencies, probeFrequencies)
    print("[MECHANISM] Why the no-fit baseline never breaks the floor:")
    print(
        f"[MECHANISM]   performance is predominantly CONCAVE - "
        f"{100.0 * bias['concave_share']:.1f}% of second differences curve downward - so a straight"
    )
    print(
        f"[MECHANISM]   line between probes sits below the true curve. Interpolated performance is"
    )
    print(
        f"[MECHANISM]   an under-estimate {100.0 * bias['under_estimate_share']:.0f}% of the time, "
        f"by a mean {bias['mean_error_pp']:+.2f} points, which biases every choice UPWARD."
    )
    print(
        "[MECHANISM]   Under a floor that bias is free safety. It is a property of the curve SHAPE,"
    )
    print(
        "[MECHANISM]   not of the method: on a CONVEX performance curve the sign flips and"
    )
    print(
        "[MECHANISM]   interpolation would violate the floor more often than the fitted model, not"
    )
    print("[MECHANISM]   less. Do not carry 'interpolate the probes' away without this condition.")
    print()
    return bias


def reportCrossCheck(dataset, floor=0.95):
    """
    Reproduce analyze_constrained.py's headline before trusting anything built on top of it.

    5.6.1 reports 28.5% for per-workload selection and 4.9% for the best fixed frequency at
    1462 MHz, on all 33 workloads with no held-out fold. If the oracle and the full-data fixed
    policy here do not land on those numbers, this module has misunderstood the data and every
    figure it prints is worthless. Checked at run time rather than asserted in a comment.
    """
    performance, _, efficiency = buildMatrices(dataset)
    workloads = list(efficiency.index)

    oracleGain = float(
        np.mean(
            [
                (efficiency.loc[w][trueConstrainedOptimum(performance, efficiency, w, floor)] - 1.0)
                * 100.0
                for w in workloads
            ]
        )
    )
    fixedFrequency = bestFixedFrequencyHoldingFloor(performance, efficiency, floor)
    fixedGain = float(np.mean([(efficiency.loc[w][fixedFrequency] - 1.0) * 100.0 for w in workloads]))

    print(
        f"[CROSS-CHECK] Against analyze_constrained.py at a {floor * 100:.0f}% floor, all 33 "
        f"workloads, no held-out fold:"
    )
    print(
        f"[CROSS-CHECK]   per-workload oracle {oracleGain:.1f}% (5.6.1 reports 28.5%), "
        f"best fixed {fixedGain:.1f}% at {fixedFrequency} MHz (5.6.1 reports 4.9% at 1462 MHz)."
    )
    print()


CONSUMER_PATTERNS = ("stock-suite-20260829/*_sweep.csv", "suite-pilot-20260829/*_sweep.csv")

# Chosen POSITIONALLY to mirror the V100's probes, not selected on this data.
#
# The V100 probes at 757, 885, 1012 and 1530 MHz - grid indices 0, 2, 4 and 12 of 13. The same
# indices on the consumer grid give 1237, 1545, 1852 and 3090. Picking them this way is the
# conservative option and it matters: probes optimised against the consumer curves would be
# fitted to the data they are then evaluated on, and this file exists to embarrass models rather
# than flatter them. If a greedy selection is ever used here it must be selected inside the
# leave-one-out fold, not once over the whole set.
CONSUMER_PROBE_FREQUENCIES_MHZ = (1237, 1545, 1852, 3090)


def loadConsumerDataset(patterns=CONSUMER_PATTERNS, basis="commanded"):
    """
    Build the long-format frame this module expects, from consumer frequency sweeps.

    The V100 arrives as a published matrix; a sweep arrives as one CSV per workload. This turns
    the second into the shape of the first, normalising each workload against the highest
    frequency in its own sweep exactly as analyze_constrained.buildPoints does - so the reference
    is the clock the card actually held at the top of the grid, not a nameplate number.

    basis="commanded" by default, and it has to be. Keyed by achieved clock these sweeps share
    five frequencies out of thirteen, because each workload clamps differently under its own power
    draw, and a pivot on that would be mostly holes. See analyze_constrained.loadSweepCurves.
    """
    import contextlib
    import io

    analysisDirectory = str(Path(__file__).resolve().parents[1])
    if analysisDirectory not in sys.path:
        sys.path.insert(0, analysisDirectory)
    import analyze_constrained as constrained

    curves = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for pattern in patterns:
            curves.update(constrained.loadSweepCurves(pattern, basis=basis))
    if not curves:
        raise FileNotFoundError(f"no sweeps matched {patterns}")

    rows = []
    for name, points in curves.items():
        # Strip the timestamp and label prefix so the workload name is the workload, which is
        # what a leave-one-WORKLOAD-out fold is leaving out.
        workload = name.split("-")[-1]
        for point in points:
            rows.append({
                "workload": workload,
                "frequency_mhz": int(round(point["mhz"])),
                "performance_normalised": point["perf"],
                "power_watts": point["power"],
                "efficiency_normalised": point["eff"],
            })
    frame = pd.DataFrame(rows)
    duplicated = frame.duplicated(subset=["workload", "frequency_mhz"]).sum()
    if duplicated:
        raise ValueError(
            f"{duplicated} duplicate workload/frequency pairs - two sweeps of the same workload "
            f"are in the pattern, and the pivot would silently keep one of them")
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--floors",
        type=float,
        nargs="+",
        default=list(DEFAULT_FLOORS),
        help="performance floors to evaluate, as fractions of stock performance",
    )
    parser.add_argument(
        "--source",
        choices=["v100", "consumer"],
        default="v100",
        help="which dataset to evaluate. 'v100' is the published reference matrix and the "
             "default, so every number elsewhere is unchanged. 'consumer' is this project's own "
             "twelve-workload sweep suite, keyed by COMMANDED frequency because the workloads "
             "clamp to different achieved clocks at one target.",
    )
    arguments = parser.parse_args()

    if arguments.source == "consumer":
        dataset = loadConsumerDataset()
        probes = CONSUMER_PROBE_FREQUENCIES_MHZ
        workloadCount = dataset["workload"].nunique()
        print(f"[SOURCE] Consumer suite: {workloadCount} workloads, "
              f"{dataset['frequency_mhz'].nunique()} commanded frequencies, one card, n=1 each.")
        print("[SOURCE] Probes are the V100's grid POSITIONS carried over, not selected on this")
        print("[SOURCE] data - see CONSUMER_PROBE_FREQUENCIES_MHZ for why that matters.\n")
    else:
        dataset = loadDataset(validate=False)
        probes = DEFAULT_PROBE_FREQUENCIES_MHZ

    performance, _, efficiency = buildMatrices(dataset)

    print(
        f"[CONSTRAINED] Leave-one-workload-out, probing at "
        f"{', '.join(str(frequency) for frequency in probes)} MHz."
    )
    print(
        "[CONSTRAINED] Regret is efficiency given up against each workload's own CONSTRAINED "
        "optimum. Negative regret is not a win - it means the floor was broken."
    )
    print()

    if arguments.source == "v100":
        reportCrossCheck(dataset)
    else:
        # reportCrossCheck validates against analyze_constrained's V100 figures and quotes 5.6.1's
        # published numbers back. There is no consumer equivalent to check against here - 5.6.1.1's
        # consumer table is produced by analyze_constrained --basis commanded, which is a different
        # question from this file's. Skipped rather than run against the wrong reference.
        print("[CROSS-CHECK] Skipped: no consumer reference exists for this comparison.\n")

    reportInterpolationBias(
        performance, np.array(efficiency.columns, dtype=int), probes
    )

    for floor in arguments.floors:
        result = runLeaveOneWorkloadOut(dataset, floor, probeFrequencies=probes)
        reportFloor(result, floor, performance, efficiency)

    if arguments.source == "v100":
        print(
            "[CONSTRAINED] CAVEAT: 33 workloads on one V100, every number in-dataset. This says "
            "nothing about consumer silicon until it is retested there, and the collected data "
            "does not yet have enough same-SKU units to retest it on."
        )
    else:
        print(
            "[CONSTRAINED] CAVEAT: 12 workloads on ONE consumer card, n=1 per workload, every "
            "number in-dataset. Chip-to-chip variation is untested here and needs repeat units "
            "of one SKU this project does not have. Four of the twelve were collected under "
            "looser conditions than the other eight - see suite-pilot-20260829/README.md."
        )


if __name__ == "__main__":
    main()
