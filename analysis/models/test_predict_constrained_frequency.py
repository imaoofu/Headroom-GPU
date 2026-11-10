"""
Known-answer checks for predict_constrained_frequency.py.

Written before trusting any number that module prints, and the reason is specific here rather
than general. The module's headline is that a no-fit baseline beats every fitted variant, which
is exactly the shape of result a subtly-broken scorer produces: give the fitted model a slightly
wrong feasibility rule, or let the oracle see something the strategies cannot, and the ranking
inverts without anything looking wrong in the output.

The first run of this module also shipped a verdict function that printed "within noise (0.429%
vs 23.563%)", because its fall-through branch made a positive claim. Nothing in the numbers was
wrong; the sentence about them was. So the verdict logic is tested here too, not just the maths.

Every case below has an answer derivable by hand.

Run: python analysis/test_predict_constrained_frequency.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
# analysis/ too, for load_data. The module under test bootstraps this itself, but relying on that
# would make these imports order-dependent for no reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from predict_constrained_frequency import (  # noqa: E402
    FEASIBILITY_TOLERANCE,
    bestFixedFrequencyHoldingFloor,
    calibrateSafetyMargin,
    chooseByInterpolation,
    chooseUnderFloor,
    evaluateStrategy,
    measureInterpolationBias,
    perFrequencyFloor,
    spliceProbeMeasurements,
    trueConstrainedOptimum,
)

failures = []


def check(description, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {description}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(description)


FREQUENCIES = np.array([1000, 1100, 1200, 1300, 1400, 1500], dtype=int)


def syntheticMatrices():
    """
    Three workloads with hand-computable answers, normalised to 1500 MHz.

    Performance, as a fraction of its own 1500 MHz value:

      MHz        1000   1100   1200   1300   1400   1500
      tolerant   0.96   0.97   0.98   0.99   0.995  1.00     holds 0.95 everywhere
      middling   0.90   0.93   0.96   0.98   0.99   1.00     holds 0.95 from 1200 up
      sensitive  0.70   0.78   0.86   0.93   0.97   1.00     holds 0.95 from 1400 up

    Efficiency, normalised the same way, made to peak at the LOW end for every workload so the
    constrained optimum is always the lowest feasible frequency and can be read off by eye:

      MHz        1000   1100   1200   1300   1400   1500
      all three  1.50   1.40   1.30   1.20   1.10   1.00

    At a 0.95 floor the per-workload answers are therefore 1000, 1200 and 1400 MHz - and the
    single fixed frequency that holds the floor on ALL THREE is 1400, pinned by 'sensitive'.
    """
    performance = pd.DataFrame(
        [
            [0.96, 0.97, 0.98, 0.99, 0.995, 1.00],
            [0.90, 0.93, 0.96, 0.98, 0.99, 1.00],
            [0.70, 0.78, 0.86, 0.93, 0.97, 1.00],
        ],
        index=["tolerant", "middling", "sensitive"],
        columns=FREQUENCIES,
    )
    efficiency = pd.DataFrame(
        [[1.50, 1.40, 1.30, 1.20, 1.10, 1.00]] * 3,
        index=["tolerant", "middling", "sensitive"],
        columns=FREQUENCIES,
    )
    return performance, efficiency


print("predict_constrained_frequency.py - known-answer checks")
print()

performance, efficiency = syntheticMatrices()

# ---------------------------------------------------------------------------------------
print("The oracle picks the best FEASIBLE point, not the best point")
# ---------------------------------------------------------------------------------------
check(
    "tolerant holds the floor everywhere, so the oracle takes the efficiency peak at 1000",
    trueConstrainedOptimum(performance, efficiency, "tolerant", 0.95) == 1000,
    f"got {trueConstrainedOptimum(performance, efficiency, 'tolerant', 0.95)}",
)
check(
    "middling is cut off below 1200, so the oracle takes 1200 and NOT the 1000 peak",
    trueConstrainedOptimum(performance, efficiency, "middling", 0.95) == 1200,
    f"got {trueConstrainedOptimum(performance, efficiency, 'middling', 0.95)}",
)
check(
    "sensitive is cut off below 1400, so the oracle takes 1400",
    trueConstrainedOptimum(performance, efficiency, "sensitive", 0.95) == 1400,
    f"got {trueConstrainedOptimum(performance, efficiency, 'sensitive', 0.95)}",
)
# A floor of 0 must reproduce the UNCONSTRAINED answer for every workload. If it does not, the
# constrained scorer and the unconstrained one are measuring different things and 5.2 cannot be
# compared to anything here.
check(
    "a floor of 0 reduces to the unconstrained optimum for every workload",
    all(
        trueConstrainedOptimum(performance, efficiency, workload, 0.0) == 1000
        for workload in performance.index
    ),
)

# ---------------------------------------------------------------------------------------
print()
print("The fixed baseline is pinned by the most sensitive workload - the whole 5.6.1 mechanism")
# ---------------------------------------------------------------------------------------
check(
    "with all three workloads the fixed frequency is 1400, set by 'sensitive' alone",
    bestFixedFrequencyHoldingFloor(performance, efficiency, 0.95) == 1400,
    f"got {bestFixedFrequencyHoldingFloor(performance, efficiency, 0.95)}",
)
check(
    "drop 'sensitive' and it falls to 1200 - one workload moves the whole policy",
    bestFixedFrequencyHoldingFloor(performance.drop("sensitive"), efficiency.drop("sensitive"), 0.95)
    == 1200,
    f"got {bestFixedFrequencyHoldingFloor(performance.drop('sensitive'), efficiency.drop('sensitive'), 0.95)}",
)
check(
    "keep only 'tolerant' and it falls all the way to the efficiency peak at 1000",
    bestFixedFrequencyHoldingFloor(performance.loc[["tolerant"]], efficiency.loc[["tolerant"]], 0.95)
    == 1000,
)
# The reference frequency has performance 1.0 by construction, so a floor of 1.0 must leave
# exactly one feasible point. A baseline that returned anything else would be promising a
# guarantee it cannot keep.
check(
    "at a floor of 1.0 only the reference frequency is feasible",
    bestFixedFrequencyHoldingFloor(performance, efficiency, 1.0) == 1500,
    f"got {bestFixedFrequencyHoldingFloor(performance, efficiency, 1.0)}",
)

# ---------------------------------------------------------------------------------------
print()
print("chooseUnderFloor separates what a strategy BELIEVES from what is true")
# ---------------------------------------------------------------------------------------
truePerformance = performance.loc["sensitive"].to_numpy()
trueEfficiency = efficiency.loc["sensitive"].to_numpy()
check(
    "given the true curves it reproduces the oracle",
    chooseUnderFloor(truePerformance, trueEfficiency, FREQUENCIES, 0.95) == 1400,
)
# The point of the whole design: a strategy handed an optimistic performance curve picks an
# infeasible frequency, and the function does NOT quietly protect it. If this test fails,
# violations are impossible by construction and the violation column is decorative.
optimistic = np.array([0.99, 0.99, 0.99, 0.99, 0.99, 1.00])
check(
    "given an OPTIMISTIC performance curve it picks 1000, which truly violates the floor",
    chooseUnderFloor(optimistic, trueEfficiency, FREQUENCIES, 0.95) == 1000,
    f"got {chooseUnderFloor(optimistic, trueEfficiency, FREQUENCIES, 0.95)}",
)
check(
    "a per-frequency floor array is honoured, not silently collapsed to its first element",
    chooseUnderFloor(
        truePerformance, trueEfficiency, FREQUENCIES, np.array([0.99, 0.99, 0.99, 0.99, 0.95, 0.95])
    )
    == 1400,
)
# Nothing feasible at all must fall back to the reference frequency, which is the one point
# every floor <= 1.0 admits.
# 1500 is this grid's maximum. The first version of the module returned 1530 here - the V100's
# stock boost clock, hardcoded - which is not on this grid at all and would not be on a consumer
# sweep's either. Pinned to the grid maximum so the constant cannot creep back in.
exactlyOnFloor = np.array([0.95, 0.90, 0.90, 0.90, 0.90, 1.00])
check(
    "a frequency whose performance EQUALS the floor is chosen, not discarded",
    chooseUnderFloor(exactlyOnFloor, trueEfficiency, FREQUENCIES, 0.95) == 1000,
    f"got {chooseUnderFloor(exactlyOnFloor, trueEfficiency, FREQUENCIES, 0.95)}",
)
check(
    "an entirely infeasible curve falls back to the GRID's maximum, not a hardcoded 1530",
    chooseUnderFloor(np.zeros(6), trueEfficiency, FREQUENCIES, 0.95) == 1500,
    f"got {chooseUnderFloor(np.zeros(6), trueEfficiency, FREQUENCIES, 0.95)}",
)
check(
    "and the fixed baseline falls back the same way when no frequency holds the floor",
    bestFixedFrequencyHoldingFloor(performance, efficiency, 1.5) == 1500,
    f"got {bestFixedFrequencyHoldingFloor(performance, efficiency, 1.5)}",
)

# ---------------------------------------------------------------------------------------
print()
print("Measurements override predictions at probe frequencies")
# ---------------------------------------------------------------------------------------
probes = (1000, 1500)
spliced = spliceProbeMeasurements(
    np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]), performance.loc["sensitive"], FREQUENCIES, probes
)
check(
    "probe frequencies take the measured value",
    spliced[0] == 0.70 and spliced[5] == 1.00,
    f"got {spliced[0]} and {spliced[5]}",
)
check(
    "non-probe frequencies keep the prediction, however bad it is",
    list(spliced[1:5]) == [0.0, 0.0, 0.0, 0.0],
    f"got {list(spliced[1:5])}",
)
check(
    "splicing does not mutate the array it was given",
    True,
    "",
)
original = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
spliceProbeMeasurements(original, performance.loc["sensitive"], FREQUENCIES, probes)
check(
    "the caller's prediction array is left untouched",
    original[0] == 0.1,
    f"got {original[0]}",
)

# ---------------------------------------------------------------------------------------
print()
print("The safety margin applies where values were predicted, never where they were measured")
# ---------------------------------------------------------------------------------------
floors = perFrequencyFloor(0.95, 0.03, FREQUENCIES, (1000, 1500))
check(
    "probe frequencies keep the bare floor",
    floors[0] == 0.95 and floors[5] == 0.95,
    f"got {floors[0]} and {floors[5]}",
)
check(
    "predicted frequencies carry floor + margin",
    all(abs(value - 0.98) < 1e-12 for value in floors[1:5]),
    f"got {list(floors[1:5])}",
)
# A zero margin must be exactly the scalar case. If it is not, the calibrated variant and the
# raw one are not comparable and the whole 'does the margin cost anything' question is muddled.
check(
    "a zero margin reduces to a flat floor",
    all(value == 0.95 for value in perFrequencyFloor(0.95, 0.0, FREQUENCIES, (1000, 1500))),
)

# ---------------------------------------------------------------------------------------
print()
print("Scoring reports violations, and does not hide them inside regret")
# ---------------------------------------------------------------------------------------
# 'sensitive' at 1000 MHz: performance 0.70 against a 0.95 floor, so a 25-point violation, and
# efficiency 1.50 against the oracle's 1.10 - NEGATIVE regret. Both must show.
cheating = evaluateStrategy(performance, efficiency, {"sensitive": 1000}, 0.95)
check(
    "a floor-breaking choice is counted as a violation",
    cheating["floor_violations"] == 1,
    f"got {cheating['floor_violations']}",
)
check(
    "the violation size is reported in performance points, 0.95 - 0.70 = 25",
    abs(cheating["worst_violation_pp"] - 25.0) < 1e-9,
    f"got {cheating['worst_violation_pp']}",
)
check(
    "and its regret comes out NEGATIVE, which is the signature of cheating, not of winning",
    cheating["mean_regret_pct"] < 0,
    f"got {cheating['mean_regret_pct']}",
)
honest = evaluateStrategy(performance, efficiency, {"sensitive": 1400}, 0.95)
check(
    "the oracle's own choice scores zero regret and zero violations",
    honest["mean_regret_pct"] == 0.0 and honest["floor_violations"] == 0,
    f"got {honest['mean_regret_pct']} / {honest['floor_violations']}",
)
check(
    "gain is measured against stock, so the oracle's 1.10 efficiency reads as +10%",
    abs(honest["mean_gain_pct"] - 10.0) < 1e-9,
    f"got {honest['mean_gain_pct']}",
)
# Exactly ON the floor is feasible, not a violation. An off-by-one in the comparison here would
# silently disqualify every strategy that lands on a grid point at the boundary.
onTheLine = evaluateStrategy(performance, efficiency, {"sensitive": 1400}, 0.97)
check(
    "performance exactly equal to the floor is feasible, not a violation",
    onTheLine["floor_violations"] == 0,
    f"got {onTheLine['floor_violations']}",
)

# ---------------------------------------------------------------------------------------
print()
print("Interpolation uses only the probes, and is conservative on a concave curve")
# ---------------------------------------------------------------------------------------
# 'sensitive' interpolated between 1000 (0.70) and 1500 (1.00) is a straight line: at 1400 it
# reads 0.94, below the 0.95 floor, so interpolation must reject 1400 even though it is truly
# feasible - and pick 1500. That over-caution is the mechanism the module reports.
interpolated = chooseByInterpolation(
    performance.loc["sensitive"], efficiency.loc["sensitive"], FREQUENCIES, (1000, 1500), 0.95
)
check(
    "interpolation under-reads the concave curve and picks 1500 where the oracle picks 1400",
    interpolated == 1500,
    f"got {interpolated}",
)
check(
    "so it is more conservative than the oracle, never less",
    interpolated >= trueConstrainedOptimum(performance, efficiency, "sensitive", 0.95),
)
# On a workload that is linear between the probes there is nothing to under-read, and
# interpolation must land exactly on the oracle. This separates 'conservative' from 'broken'.
linearPerformance = pd.DataFrame([[0.70, 0.76, 0.82, 0.88, 0.94, 1.00]], index=["linear"], columns=FREQUENCIES)
linearEfficiency = pd.DataFrame([[1.50, 1.40, 1.30, 1.20, 1.10, 1.00]], index=["linear"], columns=FREQUENCIES)
check(
    "on a perfectly linear curve interpolation matches the oracle exactly",
    chooseByInterpolation(
        linearPerformance.loc["linear"], linearEfficiency.loc["linear"], FREQUENCIES, (1000, 1500), 0.95
    )
    == trueConstrainedOptimum(linearPerformance, linearEfficiency, "linear", 0.95),
)

# ---------------------------------------------------------------------------------------
print()
print("The bias diagnostic detects curve shape, and reverses when the shape does")
# ---------------------------------------------------------------------------------------
concaveBias = measureInterpolationBias(performance, FREQUENCIES, (1000, 1500))
check(
    "on the concave synthetic set, interpolation under-estimates performance",
    concaveBias["mean_error_pp"] < 0,
    f"got {concaveBias['mean_error_pp']}",
)
check(
    "and the concave share is above half",
    concaveBias["concave_share"] > 0.5,
    f"got {concaveBias['concave_share']}",
)
# The claim the module makes is directional: on a CONVEX curve the bias flips and interpolation
# becomes dangerous rather than safe. Asserted against a convex curve rather than left as prose,
# because it is the condition that bounds the whole recommendation.
# Deliberately steep. A gentler convex curve flips the sign of the bias without the
# over-estimate ever crossing the floor, which demonstrates the diagnostic but not the danger.
# Interpolated 1000->1500 reads 0.98 at 1400 where the truth is 0.92, so 1400 looks feasible
# against a 0.95 floor and is not.
convex = pd.DataFrame(
    [[0.90, 0.905, 0.91, 0.915, 0.92, 1.00]], index=["convex"], columns=FREQUENCIES
)
convexBias = measureInterpolationBias(convex, FREQUENCIES, (1000, 1500))
check(
    "on a CONVEX curve the sign flips and interpolation OVER-estimates performance",
    convexBias["mean_error_pp"] > 0,
    f"got {convexBias['mean_error_pp']}",
)
check(
    "which is what would make it violate the floor rather than avoid it",
    chooseByInterpolation(
        convex.loc["convex"],
        pd.Series([1.50, 1.40, 1.30, 1.20, 1.10, 1.00], index=FREQUENCIES),
        FREQUENCIES,
        (1000, 1500),
        0.95,
    )
    < trueConstrainedOptimum(
        convex,
        pd.DataFrame([[1.50, 1.40, 1.30, 1.20, 1.10, 1.00]], index=["convex"], columns=FREQUENCIES),
        "convex",
        0.95,
    ),
)

# ---------------------------------------------------------------------------------------
print()
print("The margin is calibrated from training data only, and is never negative")
# ---------------------------------------------------------------------------------------
features = pd.DataFrame(
    {
        "performance_at_1000": performance[1000],
        "performance_at_1500": performance[1500],
    }
)
margin = calibrateSafetyMargin(features, performance, FREQUENCIES, (1000, 1500))
check(
    "the calibrated margin is a non-negative number",
    margin >= 0.0 and np.isfinite(margin),
    f"got {margin}",
)
# A model that never over-predicts needs no padding. Feeding it a set where the fit is exact
# must return exactly zero, or every strategy is being handed free conservatism it did not earn.
exact = pd.DataFrame([[1.0, 1.0, 1.0, 1.0, 1.0, 1.0]] * 3, index=performance.index, columns=FREQUENCIES)
check(
    "a perfectly predictable target needs no margin at all",
    calibrateSafetyMargin(features, exact, FREQUENCIES, (1000, 1500)) == 0.0,
    f"got {calibrateSafetyMargin(features, exact, FREQUENCIES, (1000, 1500))}",
)
# At a low quantile the raw error is genuinely negative here (about -0.058), so this is the case
# that actually exercises the clamp rather than getting zero for free. A negative margin would
# loosen the floor BELOW what the caller asked for, which is the one direction a safety margin
# must never move.
check(
    "a negative raw quantile is clamped to zero, never allowed to loosen the floor",
    calibrateSafetyMargin(features, performance, FREQUENCIES, (1000, 1500), quantile=0.1) == 0.0,
    f"got {calibrateSafetyMargin(features, performance, FREQUENCIES, (1000, 1500), quantile=0.1)}",
)

# ---------------------------------------------------------------------------------------
print()
print("Against the real dataset: the module must reproduce 5.6.1 or it has misread the data")
# ---------------------------------------------------------------------------------------
try:
    from load_data import loadDataset  # noqa: E402
    from predict_optimal_frequency import buildMatrices  # noqa: E402

    realDataset = loadDataset(validate=False)
    realPerformance, _, realEfficiency = buildMatrices(realDataset)
    workloads = list(realEfficiency.index)

    oracleGain = float(
        np.mean(
            [
                (
                    realEfficiency.loc[w][
                        trueConstrainedOptimum(realPerformance, realEfficiency, w, 0.95)
                    ]
                    - 1.0
                )
                * 100.0
                for w in workloads
            ]
        )
    )
    fixed = bestFixedFrequencyHoldingFloor(realPerformance, realEfficiency, 0.95)
    fixedGain = float(
        np.mean([(realEfficiency.loc[w][fixed] - 1.0) * 100.0 for w in workloads])
    )

    check(
        "the oracle reproduces 5.6.1's 28.5% per-workload gain at a 95% floor",
        abs(oracleGain - 28.5) < 0.05,
        f"got {oracleGain:.2f}",
    )
    check(
        "the fixed baseline reproduces 5.6.1's 4.9% at 1462 MHz",
        abs(fixedGain - 4.9) < 0.05 and fixed == 1462,
        f"got {fixedGain:.2f} at {fixed}",
    )
except FileNotFoundError:
    print("  [SKIP] the public dataset is not downloaded - run scripts/Get-Dataset.ps1")

print()
if failures:
    print(f"{len(failures)} check(s) failed.")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
