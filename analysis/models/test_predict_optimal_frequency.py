"""
Known-answer checks for the scoring and baseline functions in predict_optimal_frequency.py.

WHY THESE
    They produce the 5.2 null - the finding that a probe-based model does not beat a single
    fixed frequency. That null is a headline claim, and until now nothing verified the
    arithmetic behind it. regretFor defines the metric, evaluateStrategy aggregates it, and
    chooseByBestFixedFrequency is the baseline the model has to clear.

    The load-bearing case is chooseByBestFixedFrequency: it picks the frequency with the best
    MEAN efficiency, which can be nobody's individual optimum. The test builds exactly that
    situation, because a baseline that merely copied some workload's optimum would be a
    weaker opponent and would make the null look stronger than it is.

PROVENANCE
    Drafted by a local model (qwen3-coder:30b), then verified rather than trusted. It got
    three things wrong and all three were caught here:

      1. Omitted `import pandas as pd` entirely - the file would not run.
      2. Its exact-match-rate case reused the previous case's dictionary, in which BOTH
         choices were optimal, so the asserted 0.5 was unreachable. Its own comment said
         "one exact, one not" and contradicted its data.
      3. Its best-fixed-frequency case had column means of 1.0, 1.0, 1.0 - a three-way tie
         resolved arbitrarily by idxmax. Its comment computed 1.25/0.5/1.0 by pairing values
         to the wrong columns.

    Then mutation testing found a fourth problem the model could not have known it had: the
    mean_frequency_error_mhz case chose frequencies ABOVE the optimum in both cases, so
    abs() was a no-op and deleting it changed nothing. Rewritten to straddle the optimum in
    both directions.

    All five mutations are now caught: dropping the x100 scaling, inverting the regret sign,
    substituting mean for max in worst_regret_pct, removing abs() from the frequency error,
    and using max instead of mean in the fixed-frequency baseline.

    Delete analysis/__pycache__ between mutations; a same-length edit leaves stale bytecode
    running while the source on disk reads correct.

Run: python analysis/test_predict_optimal_frequency.py
"""

import sys
from pathlib import Path

import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
# analysis/ too, for load_data. The module under test bootstraps this itself, but relying on that
# would make these imports order-dependent for no reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from predict_optimal_frequency import (
    regretFor, evaluateStrategy, chooseByStock, chooseByBestFixedFrequency,
    REFERENCE_FREQUENCY_MHZ,
)

failures = []

def check(description, condition, detail=""):
    if condition:
        print(f"[PASS] {description}")
    else:
        print(f"[FAIL] {description}")
        if detail:
            print(f"  Detail: {detail}")
        failures.append(description)

# Test regretFor
efficiency = pd.DataFrame(
    {757: [1.40, 1.10], 1012: [1.20, 1.60], 1530: [1.00, 1.00]},
    index=pd.Index(["lowPeak", "midPeak"], name="workload"),
)

# 1. Choosing a workload's own best frequency gives EXACTLY zero regret.
check("regretFor: exact match", regretFor(efficiency, "lowPeak", 757) == 0.0)

# 2. A hand-computed case.
check("regretFor: computed case", abs(regretFor(efficiency, "lowPeak", 1012) - 20.0) < 1e-10)

# 3. Regret is in percentage POINTS.
check("regretFor: percentage points", abs(regretFor(efficiency, "lowPeak", 1530) - 40.0) < 1e-10)

# 4. Regret is never negative.
regret = regretFor(efficiency, "lowPeak", 1530)
check("regretFor: never negative", regret >= 0.0)

# Test evaluateStrategy
chosenFrequencyByWorkload = {"lowPeak": 757, "midPeak": 1012}

# 5. A strategy that picks each workload's true optimum scores mean_regret_pct of 0.0
trueOptima = {"lowPeak": 757, "midPeak": 1012}
result = evaluateStrategy(efficiency, trueOptima)
check("evaluateStrategy: perfect strategy", 
      abs(result["mean_regret_pct"] - 0.0) < 1e-10 and 
      abs(result["exact_match_rate"] - 1.0) < 1e-10 and 
      abs(result["mean_frequency_error_mhz"] - 0.0) < 1e-10)

# 6. exact_match_rate is a FRACTION between 0 and 1
# lowPeak's optimum IS 757; midPeak's is 1012, so sending it to 1530 is a miss.
chosen = {"lowPeak": 757, "midPeak": 1530}
result = evaluateStrategy(efficiency, chosen)
check("evaluateStrategy: exact match rate", abs(result["exact_match_rate"] - 0.5) < 1e-10)

# 7. mean_frequency_error_mhz is the mean ABSOLUTE distance in MHz to the true optimum.
# One choice must fall BELOW its optimum and one ABOVE, or abs() is a no-op and the check
# cannot tell it from a plain subtraction. Mutation testing caught exactly that gap here:
# with both choices above their optimum, removing abs() left every number unchanged.
#   lowPeak  optimum 757,  chosen 1530 -> +773
#   midPeak  optimum 1012, chosen 757  -> -255
# mean of absolutes = 514.0; mean of raw differences would be 259.0.
chosen = {"lowPeak": 1530, "midPeak": 757}
result = evaluateStrategy(efficiency, chosen)
expected_error = 514.0
check("evaluateStrategy: frequency error", abs(result["mean_frequency_error_mhz"] - expected_error) < 1e-10)

# 8. worst_regret_pct equals the maximum of the individual regrets
chosen = {"lowPeak": 1530, "midPeak": 1012}
result = evaluateStrategy(efficiency, chosen)
expected_worst = max(regretFor(efficiency, "lowPeak", 1530), regretFor(efficiency, "midPeak", 1012))
check("evaluateStrategy: worst regret", abs(result["worst_regret_pct"] - expected_worst) < 1e-10)

# Test chooseByStock
workloads = ["lowPeak", "midPeak"]
result = chooseByStock(efficiency, workloads)
check("chooseByStock: returns reference frequency", 
      all(result[wl] == REFERENCE_FREQUENCY_MHZ for wl in workloads))

# Test chooseByBestFixedFrequency
# Create a case where individual workloads have different optima
# The point of this case: the mean-optimal frequency is NOBODY's individual best, so a
# strategy that just copies some workload's optimum cannot reach it.
#   prefersLow  best at 757  (1.0)
#   prefersHigh best at 1530 (1.0)
#   column means: 757 -> 0.60, 1012 -> 0.90, 1530 -> 0.60
# so 1012 wins on the mean while being neither workload's own optimum.
trainingEfficiency = pd.DataFrame(
    {757: [1.0, 0.2], 1012: [0.9, 0.9], 1530: [0.2, 1.0]},
    index=pd.Index(["prefersLow", "prefersHigh"], name="workload"),
)
result, bestFixed = chooseByBestFixedFrequency(trainingEfficiency, workloads)
check("chooseByBestFixedFrequency: mean optimal frequency", bestFixed == 1012,
      f"got {bestFixed}")

check("chooseByBestFixedFrequency: same frequency for all workloads", 
      all(result[wl] == bestFixed for wl in workloads))

check("chooseByBestFixedFrequency: returns tuple with int", isinstance(bestFixed, int))

if failures:
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
