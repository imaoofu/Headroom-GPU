"""
Known-answer checks for recomputeEfficiency and toLongFormat in load_data.py.

WHY THESE TWO
    Every V100 number in this project flows through them. recomputeEfficiency is the
    normalisation that makes efficiency comparable across workloads with different absolute
    power; toLongFormat reshapes three wide matrices into the tidy frame every downstream
    script consumes. A melt-and-merge bug there could pair one workload's power with
    another's performance and still emit a perfectly well-formed table with the right row
    count, which nothing downstream would notice.

    The misalignment check therefore verifies every cell against the matrix it came from
    rather than spot-checking a row.

PROVENANCE
    Drafted by a local model (qwen3-coder:30b via Ollama), then verified rather than trusted.
    Its misalignment check was WRONG - it expected row 1 to hold workload B at 757 MHz when
    rows sort by workload then frequency, making row 1 workload A at 1530 MHz. The function
    was correct; the test was not. Notably the same file asserted the correct ordering in its
    sorting check, so the model contradicted itself two checks apart. Corrected here and
    widened to cover all rows.

    Five deliberate mutations were then introduced into load_data.py - inverting the
    efficiency division, normalising by a shared scalar instead of per workload, normalising
    along the wrong axis, dropping the sort, and leaving frequency as a string - and all five
    were caught.

    Delete analysis/__pycache__ between mutations; a same-length edit can leave stale
    bytecode running while the source on disk reads correct.

Run: python analysis/test_load_data.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_data import recomputeEfficiency, toLongFormat, REFERENCE_FREQUENCY_MHZ
import pandas as pd
import numpy as np

failures = []

def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"  Detail: {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")

# Test recomputeEfficiency
performance = pd.DataFrame(
    {757: [0.50, 0.90], 1530: [1.00, 1.00]},
    index=pd.Index(["compute_bound", "memory_bound"], name="workload"),
)
power = pd.DataFrame(
    {757: [100.0, 50.0], 1530: [200.0, 100.0]},
    index=pd.Index(["compute_bound", "memory_bound"], name="workload"),
)

efficiency = recomputeEfficiency(performance, power)

# 1. The column at 1530 MHz is exactly 1.0 for every workload, whatever the inputs.
check("recomputeEfficiency reference column is 1.0", 
      np.allclose(efficiency[REFERENCE_FREQUENCY_MHZ], 1.0))

# 2. A hand-computed case
expected_compute = [1.0, 1.0]  # 0.50/100 / (1.00/200) = 0.005 / 0.005 = 1.0
expected_memory = [1.8, 1.0]  # 0.90/50 / (1.00/100) = 0.018 / 0.010 = 1.8
check("recomputeEfficiency hand-computed case",
      np.allclose(efficiency.loc["compute_bound"], expected_compute) and
      np.allclose(efficiency.loc["memory_bound"], expected_memory))

# 3. Each workload is normalised by ITS OWN reference
perf_diff_ref = pd.DataFrame(
    {757: [1.0, 1.0], 1530: [2.0, 1.0]},
    index=pd.Index(["workload_a", "workload_b"], name="workload"),
)
pow_diff_ref = pd.DataFrame(
    {757: [100.0, 50.0], 1530: [200.0, 100.0]},
    index=pd.Index(["workload_a", "workload_b"], name="workload"),
)
eff_diff_ref = recomputeEfficiency(perf_diff_ref, pow_diff_ref)
check("recomputeEfficiency workload-specific reference",
      not np.allclose(eff_diff_ref.loc["workload_a"], eff_diff_ref.loc["workload_b"]))

# 4. The returned frame has the same shape, index and columns as the input
check("recomputeEfficiency same shape/index/columns",
      efficiency.shape == performance.shape and
      efficiency.index.equals(performance.index) and
      efficiency.columns.equals(performance.columns))

# Test toLongFormat
perf_long = pd.DataFrame(
    {757: [10.0, 20.0], 1530: [30.0, 40.0]},
    index=pd.Index(["A", "B"], name="workload"),
)
pow_long = pd.DataFrame(
    {757: [100.0, 200.0], 1530: [300.0, 400.0]},
    index=pd.Index(["A", "B"], name="workload"),
)
eff_long = pd.DataFrame(
    {757: [1.0, 2.0], 1530: [3.0, 4.0]},
    index=pd.Index(["A", "B"], name="workload"),
)

result_long = toLongFormat(perf_long, pow_long, eff_long)

# 5. Row count equals workloads x frequencies
check("toLongFormat row count", len(result_long) == 4)

# 6. NO MISALIGNMENT
# Rows are ordered by workload THEN frequency, so row 1 is A at 1530 MHz - not B at 757.
# Every cell is checked against the matrix it came from rather than a spot check, because a
# merge that misaligns one workload against another still produces a well-formed table.
misaligned = []
for rowIndex in range(len(result_long)):
    row = result_long.loc[rowIndex]
    workload = row["workload"]
    frequency = int(row["frequency_mhz"])
    for column, matrix in (("performance_normalised", perf_long),
                           ("power_watts", pow_long),
                           ("efficiency_normalised", eff_long)):
        expected = matrix.loc[workload, frequency]
        if abs(row[column] - expected) > 1e-12:
            misaligned.append(f"row {rowIndex} ({workload} @ {frequency}) {column}: "
                              f"got {row[column]}, matrix holds {expected}")
check("toLongFormat no misalignment", len(misaligned) == 0, "; ".join(misaligned))

# 7. `frequency_mhz` has an integer dtype, not string or object
check("toLongFormat frequency_mhz integer dtype",
      result_long["frequency_mhz"].dtype == int)

# 8. Output is sorted by workload, then by frequency ascending
check("toLongFormat sorted by workload and frequency",
      list(result_long["workload"]) == ["A", "A", "B", "B"] and
      list(result_long["frequency_mhz"]) == [757, 1530, 757, 1530])

# 9. The index is 0..n-1 with no gaps
check("toLongFormat index is 0..n-1",
      list(result_long.index) == [0, 1, 2, 3])

# 10. Column order between the three input matrices does not change the result
perf_rev = perf_long[sorted(perf_long.columns, reverse=True)]
pow_rev = pow_long[sorted(pow_long.columns, reverse=True)]
eff_rev = eff_long[sorted(eff_long.columns, reverse=True)]
result_rev = toLongFormat(perf_rev, pow_rev, eff_rev)
check("toLongFormat column order invariance",
      result_long.equals(result_rev))

if failures:
    print(f"FAILED CHECKS: {', '.join(failures)}")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
