"""
Known-answer checks for characterize.py.

WHY THESE
    This module produces the headline "stock leaves N% efficiency on the table" figure and
    the sensitivity grouping that decides which workloads get called memory-bound. Three of
    its four functions PRINT rather than return, so their thresholds are easy to change
    without anything downstream noticing. Two of those thresholds are boundary conditions
    (>= 0.90, > 80.0) where an off-by-one changes which workloads are claimed as memory-bound
    and whether the "a fixed frequency beats everything" warning fires at all.

    The sensitivity fixture therefore places workloads EXACTLY on 0.90 and EXACTLY on 0.70,
    and the spread fixture sits at exactly 80.0%. A fixture one step away from the boundary
    passes against both the correct code and the off-by-one.

A REAL FINDING, recorded here because it is not a bug and should not be "fixed"
    summariseWorkload calls int() on the optimal frequency, but that int is then placed in a
    pd.Series alongside floats, which upcasts the whole Series to float64. The int() call is
    therefore a no-op on the returned value. buildWorkloadSummary's explicit .astype(int) is
    what actually makes the column integral. Anyone tidying up that .astype(int) as
    "redundant, int() already did it" would silently turn the frequency column back into
    floats. Both halves are asserted below so that edit fails a test.

PROVENANCE
    Drafted by a local model (qwen3-coder:30b via Ollama), then verified rather than trusted.
    Three checks failed against correct code:

      - It asserted the returned optimal_frequency_mhz was a plain Python int. It is not, for
        the upcast reason above. That check came from a mistake in the task specification
        given to the model, not from the model.
      - Its "optimum is at stock" fixture set efficiency to 1.40 at 1530 MHz and expected a
        headroom gap of 0.0. headroom_gap_pct is measured against the constant 1.0, not
        against efficiency_at_stock, and efficiency is normalised so stock IS 1.0 by
        definition. A workload whose optimum is stock must have efficiency 1.00 there. The
        fixture contradicted the normalisation invariant.
      - Its "the two groups do not partition the set" check counted SUBSTRING occurrences in
        the printed text rather than the reported group counts, so it compared 1 + 1 against
        3 and could never pass. Rewritten to parse the actual numbers.

    Seven deliberate mutations were then introduced into characterize.py - dropping the x100
    scaling on the headroom gap, inverting the power-saved sign, taking the highest frequency
    row instead of the lowest, dropping the frequency sort, taking the worst efficiency row
    instead of the best, excluding 0.90 from the insensitive group, and firing the spread
    warning at exactly 80% - and all seven were caught.

    Delete analysis/__pycache__ between mutations; a same-length edit can leave stale
    bytecode running while the source on disk reads correct.

Run: python analysis/test_characterize.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from characterize import (
    summariseWorkload, buildWorkloadSummary, reportOptimumSpread, reportSensitivityGroups,
)

import contextlib
import io
import re

import numpy as np
import pandas as pd

failures = []


def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"       {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")


def captureOutput(function, *arguments):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        function(*arguments)
    return buffer.getvalue()


# Rows are deliberately NOT in frequency order, so anything that trusts row position rather
# than sorting picks the 1530 MHz row and gets caught.
memoryBound = pd.DataFrame(
    {
        "frequency_mhz": [1530, 757, 1012],
        "efficiency_normalised": [1.00, 1.40, 1.20],
        "performance_normalised": [1.00, 0.95, 0.98],
        "power_watts": [160.0, 100.0, 120.0],
    }
)

result = summariseWorkload(memoryBound)

check(
    "optimal_frequency_mhz is 757 for memoryBound",
    result["optimal_frequency_mhz"] == 757,
    f"got {result['optimal_frequency_mhz']}",
)
check(
    "summariseWorkload returns the frequency as a float, not an int",
    isinstance(result["optimal_frequency_mhz"], float),
    f"got {type(result['optimal_frequency_mhz']).__name__}; the int() is undone by pd.Series upcasting",
)
check(
    "headroom_gap_pct is 40.0, in percentage points not a fraction",
    abs(result["headroom_gap_pct"] - 40.0) < 1e-9,
    f"got {result['headroom_gap_pct']}",
)
check(
    "power_saved_pct is 37.5 and positive means power saved",
    abs(result["power_saved_pct"] - 37.5) < 1e-9,
    f"got {result['power_saved_pct']}",
)
check(
    "performance_given_up_pct is 5.0",
    abs(result["performance_given_up_pct"] - 5.0) < 1e-9,
    f"got {result['performance_given_up_pct']}",
)
check(
    "performance_at_lowest_frequency is 0.95, from 757 MHz not from the first row supplied",
    abs(result["performance_at_lowest_frequency"] - 0.95) < 1e-9,
    f"got {result['performance_at_lowest_frequency']}",
)
check(
    "efficiency_at_stock is 1.00, from the 1530 MHz row not the best row",
    abs(result["efficiency_at_stock"] - 1.00) < 1e-9,
    f"got {result['efficiency_at_stock']}",
)

# Efficiency is normalised so stock is 1.0. A workload whose optimum IS stock therefore peaks
# at exactly 1.00, and the gap is measured against that constant.
peaksAtStock = pd.DataFrame(
    {
        "frequency_mhz": [757, 1012, 1530],
        "efficiency_normalised": [0.80, 0.90, 1.00],
        "performance_normalised": [0.70, 0.85, 1.00],
        "power_watts": [120.0, 140.0, 160.0],
    }
)
atStock = summariseWorkload(peaksAtStock)

check(
    "headroom_gap_pct is exactly 0.0 when the optimum is stock",
    abs(atStock["headroom_gap_pct"] - 0.0) < 1e-9,
    f"got {atStock['headroom_gap_pct']}",
)
check(
    "that workload's optimum is 1530 MHz",
    atStock["optimal_frequency_mhz"] == 1530,
    f"got {atStock['optimal_frequency_mhz']}",
)

# zebra before alpha: groupby(sort=False) must preserve first appearance, not sort the names.
dataset = pd.DataFrame(
    {
        "workload": ["zebra", "zebra", "zebra", "alpha", "alpha", "alpha"],
        "frequency_mhz": [1530, 757, 1012, 1012, 1530, 757],
        "efficiency_normalised": [1.00, 1.40, 1.20, 1.25, 1.00, 1.05],
        "performance_normalised": [1.00, 0.95, 0.98, 0.80, 1.00, 0.60],
        "power_watts": [160.0, 100.0, 120.0, 130.0, 150.0, 110.0],
    }
)
summary = buildWorkloadSummary(dataset)

check(
    "one row per workload, index in first-appearance order not alphabetical",
    list(summary.index) == ["zebra", "alpha"],
    f"got {list(summary.index)}",
)
check(
    "buildWorkloadSummary restores an integer dtype on optimal_frequency_mhz",
    np.issubdtype(summary["optimal_frequency_mhz"].dtype, np.integer),
    f"got {summary['optimal_frequency_mhz'].dtype}; the .astype(int) is what does this, not the int() call",
)

zebraDirect = summariseWorkload(dataset[dataset["workload"] == "zebra"])
zebraRow = summary.loc["zebra"]
check(
    "a summary row matches summariseWorkload run on that workload alone",
    (
        zebraRow["optimal_frequency_mhz"] == zebraDirect["optimal_frequency_mhz"]
        and abs(zebraRow["efficiency_at_optimum"] - zebraDirect["efficiency_at_optimum"]) < 1e-9
        and abs(zebraRow["power_saved_pct"] - zebraDirect["power_saved_pct"]) < 1e-9
        and abs(zebraRow["performance_at_lowest_frequency"]
                - zebraDirect["performance_at_lowest_frequency"]) < 1e-9
    ),
    f"row {dict(zebraRow)} against direct {dict(zebraDirect)}",
)

# Exactly 80.0%: the threshold is strictly greater, so this must NOT warn.
spreadAtBoundary = pd.DataFrame(
    {"optimal_frequency_mhz": [757, 757, 757, 757, 1012]},
    index=pd.Index(["w1", "w2", "w3", "w4", "w5"], name="workload"),
)
boundaryOutput = captureOutput(reportOptimumSpread, spreadAtBoundary)

check(
    "spread warning is ABSENT when the most common optimum covers exactly 80.0%",
    "WARNING" not in boundaryOutput,
    "threshold is > 80.0, so 80.0 itself must not fire",
)
check(
    "the 80.0% share is reported in the text",
    "4 of 5 workloads (80%)" in boundaryOutput,
    f"output was: {boundaryOutput.splitlines()[0] if boundaryOutput else '(empty)'}",
)

spreadAllSame = pd.DataFrame(
    {"optimal_frequency_mhz": [757, 757, 757, 757, 757]},
    index=pd.Index(["w1", "w2", "w3", "w4", "w5"], name="workload"),
)
check(
    "spread warning is PRESENT when one frequency is optimal for every workload",
    "WARNING" in captureOutput(reportOptimumSpread, spreadAllSame),
)

# 0.90 must count as insensitive; 0.70 must NOT count as sensitive.
sensitivity = pd.DataFrame(
    {
        "performance_at_lowest_frequency": [0.95, 0.90, 0.80, 0.70, 0.50],
        "optimal_frequency_mhz": [757, 1012, 1012, 1530, 1530],
    },
    index=pd.Index(["w1", "w2", "w3", "w4", "w5"], name="workload"),
)
sensitivityOutput = captureOutput(reportSensitivityGroups, sensitivity)

insensitiveCount = int(re.search(r"(\d+) of \d+ workloads keep at least 90%", sensitivityOutput).group(1))
sensitiveCount = int(re.search(r"(\d+) workloads drop below 70%", sensitivityOutput).group(1))

check(
    "0.90 counts as insensitive, giving 2 of 5",
    insensitiveCount == 2,
    f"got {insensitiveCount}; the boundary is >= 0.90",
)
check(
    "0.70 does NOT count as sensitive, giving 1",
    sensitiveCount == 1,
    f"got {sensitiveCount}; the boundary is < 0.70",
)
check(
    "the two groups do not partition the set: 2 + 1 = 3 of 5 workloads are grouped",
    insensitiveCount + sensitiveCount == 3 and len(sensitivity) == 5,
    f"got {insensitiveCount} + {sensitiveCount} of {len(sensitivity)}; 0.80 and 0.70 fall in neither group",
)

if failures:
    print(f"{len(failures)} check(s) failed.")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
