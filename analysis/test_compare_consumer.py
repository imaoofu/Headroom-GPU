"""
Known-answer checks for findSpec, efficiencyByCoreFrequency and summarise in
compare_consumer.py.

WHY THIS MODULE
    It produces the claim that the published consumer DVFS datasets cannot locate an
    efficiency optimum because they never sweep below stock. That claim rests entirely on
    placing every dataset on a common axis - swept range as a percentage of rated boost - and
    an arithmetic error in that conversion would turn a correct "nobody measured the right
    range" into a wrong "consumer GPUs have no headroom", which is precisely the backwards
    conclusion the module exists to prevent.

WHY THE FIXTURE HAS ROWS AT A LOWER MEMORY CLOCK
    efficiencyByCoreFrequency must discard everything below the top memory clock before it
    computes anything. The fixture carries two rows at memF 2500 with absurd values; if they
    leak through, pivot_table averages them into the real rows and every downstream number
    changes. A fixture at a single memory clock cannot detect that.

A ROBUSTNESS GAP, DOCUMENTED RATHER THAN HIDDEN
    summarise assumes a non-empty pivot, and fails two different ways depending on what is
    empty. With columns but no rows it reaches `atCeiling / len(pivot)` and raises
    ZeroDivisionError. With no columns either, it dies earlier on `int(pivot.columns.min())`,
    because min() of an empty index is NaN and int(NaN) is a ValueError. Both are asserted
    below. Neither is guarded in the module, and this file does not pretend otherwise.

PROVENANCE
    Drafted by a local model (qwen3-coder:30b via Ollama), then verified rather than trusted.
    The generated file was structurally sound and its fixtures were correct - the first run in
    this series where the arithmetic was right - but it had two problems:

      - It compared floats with == in nine places despite being told to use a tolerance. The
        values happened to be exactly representable, so every one passed. They are now
        tolerance comparisons.
      - Its empty-pivot check caught only ZeroDivisionError, so the ValueError case escaped
        and killed the run before the summary printed. That came from an error in the task
        specification, which named only one of the two failure modes, and not from the model.

    Its weakest check asserted findSpec returned "not None" rather than the row itself; that
    is now an equality against the expected row.

    Nine deliberate mutations were then introduced into compare_consumer.py - reversing the
    findSpec prefix direction, filtering to the lowest memory clock, dropping the 1/time
    inversion, normalising to the lowest core clock, normalising along the wrong axis,
    dropping the x100 on the headroom gap, taking that gap across the wrong axis, counting
    ceiling optima against the lowest column, and swapping swept low with swept high.

    Delete analysis/__pycache__ between mutations; a same-length edit can leave stale bytecode
    running while the source on disk reads correct.

Run: python analysis/test_compare_consumer.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_consumer import findSpec, efficiencyByCoreFrequency, summarise

import pandas as pd

failures = []

TOLERANCE = 1e-9


def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"       {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")


pascalRow = {"boostClock": 1582, "memBandwidth": 484}
specs = {"GeForce GTX 1080 Ti": pascalRow}

check(
    "findSpec matches a case-insensitive prefix and returns the row itself",
    findSpec(specs, "geforce gtx 1080") is pascalRow,
    f"got {findSpec(specs, 'geforce gtx 1080')}",
)
check(
    "findSpec returns None when nothing matches",
    findSpec(specs, "RTX 3080") is None,
)
# The KEY must start with the PREFIX. A longer prefix than the key must not match, or a lookup
# for a Founders Edition would silently return the base card's specs.
check(
    "findSpec matches key-starts-with-prefix, not the reverse",
    findSpec(specs, "GeForce GTX 1080 Ti Founders Edition") is None,
    f"got {findSpec(specs, 'GeForce GTX 1080 Ti Founders Edition')}",
)

# The last two rows sit below the top memory clock and must be discarded before anything else.
rawFrame = pd.DataFrame(
    {
        "appName": ["alpha", "alpha", "beta", "beta", "alpha", "beta"],
        "coreF":   [1000, 2000, 1000, 2000, 1000, 2000],
        "memF":    [5000, 5000, 5000, 5000, 2500, 2500],
        "time/ms": [100.0, 50.0, 200.0, 100.0, 999.0, 999.0],
        "power/W": [200.0, 500.0, 100.0, 400.0, 999.0, 999.0],
    }
)
pivot = efficiencyByCoreFrequency(rawFrame)

check(
    "rows below the top memory clock are excluded, so alpha at 1000 MHz is 1.25",
    abs(pivot.loc["alpha", 1000] - 1.25) < TOLERANCE,
    f"got {pivot.loc['alpha', 1000]}",
)
check(
    "beta at 1000 MHz is 2.0",
    abs(pivot.loc["beta", 1000] - 2.0) < TOLERANCE,
    f"got {pivot.loc['beta', 1000]}",
)
check(
    "the top core frequency column is exactly 1.0 for every app",
    all(abs(pivot.loc[app, 2000] - 1.0) < TOLERANCE for app in pivot.index),
    f"got {list(pivot[2000])}",
)
check(
    "indexed by app name with one column per core frequency at the top memory clock",
    list(pivot.index) == ["alpha", "beta"] and list(pivot.columns) == [1000, 2000],
    f"got index {list(pivot.index)}, columns {list(pivot.columns)}",
)

# Half the time at identical power is twice the efficiency, not half.
sameePower = pd.DataFrame(
    {
        "appName": ["gamma", "gamma"],
        "coreF":   [1000, 2000],
        "memF":    [5000, 5000],
        "time/ms": [100.0, 200.0],
        "power/W": [100.0, 100.0],
    }
)
gamma = efficiencyByCoreFrequency(sameePower)
check(
    "efficiency rises as time falls: the faster point normalises to 2.0, not 0.5",
    abs(gamma.loc["gamma", 1000] - 2.0) < TOLERANCE,
    f"got {gamma.loc['gamma', 1000]}",
)

summary = summarise("fixture", pivot, 2500)

check(
    "mean_headroom_gap_pct is 62.5, from ((1.25 + 2.0) / 2 - 1) * 100",
    abs(summary["mean_headroom_gap_pct"] - 62.5) < TOLERANCE,
    f"got {summary['mean_headroom_gap_pct']}",
)
check(
    "units is 2 and the swept range is 1000 to 2000 MHz",
    summary["units"] == 2
    and summary["swept_low_mhz"] == 1000
    and summary["swept_high_mhz"] == 2000,
    f"got {summary['units']}, {summary['swept_low_mhz']}, {summary['swept_high_mhz']}",
)
check(
    "the swept range as a percentage of a 2500 MHz boost is 40.0 to 80.0",
    abs(summary["swept_low_pct_of_boost"] - 40.0) < TOLERANCE
    and abs(summary["swept_high_pct_of_boost"] - 80.0) < TOLERANCE,
    f"got {summary['swept_low_pct_of_boost']} to {summary['swept_high_pct_of_boost']}",
)
check(
    "neither app peaks at the ceiling, giving 0 and 0.0 percent",
    summary["units_optimal_at_ceiling"] == 0
    and abs(summary["pct_optimal_at_ceiling"] - 0.0) < TOLERANCE,
    f"got {summary['units_optimal_at_ceiling']}, {summary['pct_optimal_at_ceiling']}",
)

oneAtCeiling = pd.DataFrame(
    [[1.0, 2.0], [1.5, 1.0]], index=["app1", "app2"], columns=[1000, 2000]
)
ceilingSummary = summarise("one at ceiling", oneAtCeiling, 2500)
check(
    "exactly one of two apps peaking at the ceiling gives 1 and 50.0 percent",
    ceilingSummary["units_optimal_at_ceiling"] == 1
    and abs(ceilingSummary["pct_optimal_at_ceiling"] - 50.0) < TOLERANCE,
    f"got {ceilingSummary['units_optimal_at_ceiling']}, {ceilingSummary['pct_optimal_at_ceiling']}",
)

noBoost = summarise("no boost clock", pivot, None)
check(
    "a missing boost clock gives None for both percent-of-boost fields rather than raising",
    noBoost["swept_low_pct_of_boost"] is None
    and noBoost["swept_high_pct_of_boost"] is None
    and noBoost["rated_boost_mhz"] is None,
    f"got {noBoost['swept_low_pct_of_boost']}, {noBoost['swept_high_pct_of_boost']}, {noBoost['rated_boost_mhz']}",
)

# Columns but no rows: survives to the unguarded atCeiling / len(pivot).
raised = None
try:
    summarise("no rows", pd.DataFrame(columns=[1000, 2000]), 2500)
except Exception as error:
    raised = type(error)
check(
    "a pivot with columns but no rows raises ZeroDivisionError on the unguarded division",
    raised is ZeroDivisionError,
    f"got {raised.__name__ if raised else 'no exception'}",
)

# No columns either: dies earlier, on int(NaN) from an empty index.
raised = None
try:
    summarise("wholly empty", pd.DataFrame(), 2500)
except Exception as error:
    raised = type(error)
check(
    "a wholly empty pivot raises ValueError first, from int() of an empty column index",
    raised is ValueError,
    f"got {raised.__name__ if raised else 'no exception'}",
)

if failures:
    print(f"{len(failures)} check(s) failed.")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
