"""
Known-answer checks for loadSweep and describe in analyze_sweep.py.

WHY THIS FUNCTION NEEDS TESTS AT ALL
    loadSweep decides which rows of a sweep CSV enter the analysis and which are silently
    dropped. It filters on three separate conditions - a missing throughput, a bench_ok that
    is not True, and a clock lock that overshot - and a mistake in any of them changes every
    downstream number without producing an error. It gated every published sweep result in
    this project while having no test coverage.

    The subtle case is a CSV with no bench_ok column at all. The condition reads
    `raw.get("bench_ok") not in ("True", "true", None)`, and an absent column makes .get()
    return None, which IS in that tuple - so the row is KEPT. Reading that backwards would
    silently discard an entire file.

PROVENANCE
    Drafted by a local model (qwen3-coder:30b via Ollama) from a specification, then verified
    here rather than trusted. Five deliberate mutations were introduced into loadSweep -
    inverting EXCLUDE_DIRECTIONS, removing the sort, turning the efficiency division into a
    multiplication, accepting bench_ok=False, and making windowed accept any value - and all
    five were caught. Tests that pass against a broken function are worse than no tests, so
    that check is the reason this file is committed.

    Note when repeating that exercise: delete analysis/__pycache__ between mutations. Swapping
    `/` for `*` leaves the file the same size, and stale bytecode ran the mutated version while
    inspect.getsource showed the restored source - which produced a confidently wrong result
    until the cache was cleared.

WHY describe() WAS ADDED, 2026-08-30
    Mutation testing measured this suite at 17%. All eight survivors were in describe(), which
    had no coverage at all, and three of them INVERT a printed ratio - efficiency gain,
    performance cost, percentage of sustained max. Those figures never reach the paper, because
    claims_*.py recomputes every pinned number from the CSVs through audit_claims. They are what
    the operator reads while deciding whether a sweep is worth keeping, which is its own kind of
    load-bearing. The file now stands at 80%; the two remaining survivors are in main().

    describe() computes those ratios inside print() calls, so the checks capture stdout with
    contextlib.redirect_stdout rather than asserting on a return value. Only `peak` and
    `fastest` come back from the function.

PROVENANCE OF THE describe() CHECKS
    Drafted by the local Qwen3.8-27B (UD-IQ4_XS via llama.cpp) from a specification listing the
    eight mutants they had to kill, then verified rather than trusted. TWO were wrong:

      - check 03 asserted the substring "300.00 GB/s", but the label is right-aligned into eight
        columns so the two are not adjacent. It failed on unmutated source immediately.
      - check 04 asserted that the PEAK row draws a full 40-character bar. That is the one row
        where inverting the ratio changes nothing, since the peak row's efficiency IS `best` and
        40*eff/best and 40*best/eff both give 40. It passed against the mutant it was written to
        catch. 04b was added on a non-peak row, where the same inversion gives 120 characters
        instead of 13.

    The second is the more instructive: a check that looks right, passes, and verifies nothing.
    It is the same failure as the model-drafted misalignment check in test_load_data.py, and the
    reason nothing from a local model is committed here without the mutants being re-run against
    it. Re-grading is mechanical - tools/mutation/run_mutants.py on the surviving mutants.

Run: python analysis/test_analyze_sweep.py
"""

import sys
from pathlib import Path
import tempfile
import os

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sweep import loadSweep

failures = []

def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"  Detail: {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")

# Test 1: A row whose `bench_throughput` is empty is dropped.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w,bench_ok\n")
    f.write("1000,,100,True\n")
    f.write("1000,1000,100,True\n")
    temp_path1 = f.name

try:
    result1 = loadSweep(temp_path1)
    check("Empty bench_throughput dropped", len(result1) == 1)
    check("Non-empty bench_throughput kept", result1[0]["throughput"] == 1000.0)
finally:
    os.unlink(temp_path1)

# Test 2: A row whose `bench_ok` is `False` is dropped.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w,bench_ok\n")
    f.write("1000,1000,100,False\n")
    f.write("1000,1000,100,True\n")
    temp_path2 = f.name

try:
    result2 = loadSweep(temp_path2)
    check("False bench_ok dropped", len(result2) == 1)
    check("True bench_ok kept", result2[0]["throughput"] == 1000.0)
finally:
    os.unlink(temp_path2)

# Test 3: Rows whose `bench_ok` is `True` or `true` are both kept.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w,bench_ok\n")
    f.write("1000,1000,100,True\n")
    f.write("1000,1000,100,true\n")
    temp_path3 = f.name

try:
    result3 = loadSweep(temp_path3)
    check("True bench_ok kept", len(result3) == 2)
    check("true bench_ok kept", result3[0]["throughput"] == 1000.0 and result3[1]["throughput"] == 1000.0)
finally:
    os.unlink(temp_path3)

# Test 4: A row whose `lock_miss_direction` is `above` is dropped.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w,lock_miss_direction\n")
    f.write("1000,1000,100,above\n")
    f.write("1000,1000,100,below\n")
    temp_path4 = f.name

try:
    result4 = loadSweep(temp_path4)
    check("above lock_miss_direction dropped", len(result4) == 1)
    check("below lock_miss_direction kept", result4[0]["mhz"] == 1000.0)
finally:
    os.unlink(temp_path4)

# Test 5: Rows whose `lock_miss_direction` is `below` or `none` are both KEPT.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w,lock_miss_direction\n")
    f.write("1000,1000,100,below\n")
    f.write("1000,1000,100,none\n")
    temp_path5 = f.name

try:
    result5 = loadSweep(temp_path5)
    check("below lock_miss_direction kept", len(result5) == 2)
    check("none lock_miss_direction kept", result5[0]["mhz"] == 1000.0 and result5[1]["mhz"] == 1000.0)
finally:
    os.unlink(temp_path5)

# Test 6: Output is sorted by `mhz` ascending even when the input rows are shuffled.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w\n")
    f.write("2000,2000,200\n")
    f.write("1000,1000,100\n")
    temp_path6 = f.name

try:
    result6 = loadSweep(temp_path6)
    check("Output sorted by mhz ascending", result6[0]["mhz"] == 1000.0 and result6[1]["mhz"] == 2000.0)
finally:
    os.unlink(temp_path6)

# Test 7: `efficiency` equals `throughput / power` exactly, for a case you compute by hand.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w\n")
    f.write("1000,1000,100\n")
    temp_path7 = f.name

try:
    result7 = loadSweep(temp_path7)
    check("Efficiency computed correctly", result7[0]["efficiency"] == 10.0)
finally:
    os.unlink(temp_path7)

# Test 8: `windowed` is True for `True` and `true`, and False for `False` or an empty value.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w,power_window_applied\n")
    f.write("1000,1000,100,True\n")
    f.write("1000,1000,100,true\n")
    f.write("1000,1000,100,False\n")
    f.write("1000,1000,100,\n")
    temp_path8 = f.name

try:
    result8 = loadSweep(temp_path8)
    check("windowed=True for True", result8[0]["windowed"] == True)
    check("windowed=True for true", result8[1]["windowed"] == True)
    check("windowed=False for False", result8[2]["windowed"] == False)
    check("windowed=False for empty", result8[3]["windowed"] == False)
finally:
    os.unlink(temp_path8)

# Test 9: A file written with a UTF-8 BOM still parses (the function opens with `utf-8-sig`).
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w\n")
    f.write("1000,1000,100\n")
    temp_path9 = f.name

try:
    result9 = loadSweep(temp_path9)
    check("UTF-8 BOM file parsed", len(result9) == 1)
finally:
    os.unlink(temp_path9)

# Test 10: A CSV with NO `bench_ok` column at all keeps its rows.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w\n")
    f.write("1000,1000,100\n")
    temp_path10 = f.name

try:
    result10 = loadSweep(temp_path10)
    check("No bench_ok column keeps row", len(result10) == 1)
finally:
    os.unlink(temp_path10)

# Test 11: `utilization_avg_pct` is carried through, and its absence is None rather than a
# fabricated 0.0 or 100.0. Section 5.4.3 argues that utilisation DECOUPLES from throughput, so a
# missing reading silently becoming a number would put an invented figure into that argument.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w,utilization_avg_pct\n")
    f.write("1000,1000,100,92.7\n")
    temp_path11 = f.name

try:
    result11 = loadSweep(temp_path11)
    check("utilization_avg_pct is carried through as a float",
          result11[0]["utilisation"] == 92.7,
          f"got {result11[0]['utilisation']!r}")
finally:
    os.unlink(temp_path11)

# Test 12: no utilisation column at all.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("achieved_frequency_avg,bench_throughput,power_avg_w\n")
    f.write("1000,1000,100\n")
    temp_path12 = f.name

try:
    result12 = loadSweep(temp_path12)
    check("A missing utilisation column yields None, not a number",
          result12[0]["utilisation"] is None,
          f"got {result12[0]['utilisation']!r}; a fabricated 0.0 would read as an idle GPU")
finally:
    os.unlink(temp_path12)


import io
import contextlib
from analyze_sweep import describe

def makeRow(mhz, throughput, power, unit, windowed):
    return {
        "mhz": mhz,
        "throughput": throughput,
        "power": power,
        "unit": unit,
        "windowed": windowed,
        "efficiency": throughput / power,
    }

# Peak is the middle row (1000 MHz); fastest is the last row (2000 MHz).
# The two rows are deliberately not mirror images so every inverted ratio
# (mhz, efficiency, throughput) yields a different number than the correct one.
threeRows = [
    makeRow(500.0, 100e9, 100.0, "GB/s", True),    # eff 1.0e9
    makeRow(1000.0, 300e9, 100.0, "GB/s", True),   # eff 3.0e9 (peak)
    makeRow(2000.0, 400e9, 200.0, "GB/s", True),   # eff 2.0e9 (fastest)
]

# --- 1. short-circuit threshold ---
# Two rows: a correct <3 threshold skips, a mutated <2 threshold proceeds.
twoRows = [
    makeRow(500.0, 100e9, 100.0, "GB/s", True),
    makeRow(1000.0, 300e9, 100.0, "GB/s", True),
]
bufShort = io.StringIO()
with contextlib.redirect_stdout(bufShort):
    resShort = describe("short case", twoRows)
outShort = bufShort.getvalue()
check("01. describe returns None and prints a skip notice for fewer than 3 rows",
      resShort is None and "only 2 usable points" in outShort,
      f"returned={resShort!r}, output={outShort!r}")

# --- 2. fastest selection ---
# Peak is 1000 MHz, true fastest is 2000 MHz. Correct: 50% of sustained max.
# A min() mutant picks 500 MHz and prints 200%.
bufFastest = io.StringIO()
with contextlib.redirect_stdout(bufFastest):
    describe("fastest case", threeRows)
outFastest = bufFastest.getvalue()
check("02. optimum is reported as 50% of the sustained max (fastest row by mhz)",
      "50% of sustained max 2000.0 MHz" in outFastest,
      outFastest)

# --- 3. scale selection ---
# GB/s fixture: correct scale 1e9 -> 300.00 GB/s. Mutated scale 1e12 -> 0.00 GB/s.
bufScale = io.StringIO()
with contextlib.redirect_stdout(bufScale):
    describe("scale case", threeRows)
outScale = bufScale.getvalue()
check("03. GB/s throughput is printed on the 1e9 scale, not the 1e12 one",
      "300.00" in outScale and "TFLOP/s" not in outScale,
      outScale)

# --- 4. bar length direction ---
# Peak row (eff 3.0e9) must draw the full 40-char bar. A mutant that divides
# best by the row's efficiency gives the peak a 1-char bar.
bufBar = io.StringIO()
with contextlib.redirect_stdout(bufBar):
    describe("bar case", threeRows)
outBar = bufBar.getvalue()
peakLine = [l for l in outBar.splitlines() if "<-- OPTIMUM" in l]
check("04. the peak row draws the full 40-character bar",
      len(peakLine) == 1 and peakLine[0].count("#") == 40,
      f"peakLine={peakLine!r}")

# The peak row is the ONE row where inverting the bar ratio changes nothing, because its
# efficiency IS `best`: 40*eff/best and 40*best/eff both give 40. Checking only the peak row
# therefore passes against the inverted form. A non-peak row is what makes the direction
# observable - the 500 MHz row sits at a third of peak efficiency, so 13 characters against
# the inverted form's 120.
lowLine = [l for l in outBar.splitlines() if l.strip().startswith("500.0 MHz")]
check("04b. a row at a third of peak efficiency draws a proportionally SHORTER bar",
      len(lowLine) == 1 and lowLine[0].count("#") == 13,
      f"lowLine={lowLine!r}")

# --- 5. mhz percentage ---
# Correct: 100*peak/fastest = 50%. Mutant: 100*fastest/peak = 200%.
# (Same fixture as check 02, but asserted as an independent substring.)
check("05. optimum mhz is printed as 50% of the sustained max",
      "50% of sustained max" in outFastest,
      outFastest)

# --- 6. efficiency gain ---
# Correct: 100*(3.0/2.0 - 1) = 50.0%. Mutant: 100*(2.0/3.0 - 1) = -33.3%.
bufEff = io.StringIO()
with contextlib.redirect_stdout(bufEff):
    describe("efficiency case", threeRows)
outEff = bufEff.getvalue()
check("06. efficiency gain is reported as 50.0%",
      "efficiency gain  : 50.0%" in outEff,
      outEff)

# --- 7. performance cost ---
# Correct: 100*(1 - 300/400) = 25.0%. Mutant: 100*(1 - 400/300) = -33.3%.
bufPerf = io.StringIO()
with contextlib.redirect_stdout(bufPerf):
    describe("performance case", threeRows)
outPerf = bufPerf.getvalue()
check("07. performance cost is reported as 25.0%",
      "performance cost : 25.0%" in outPerf,
      outPerf)

# --- 8. windowing warning polarity ---
# All rows windowed: correct code prints no warning; an inverted all(...) prints one.
bufNoWarn = io.StringIO()
with contextlib.redirect_stdout(bufNoWarn):
    describe("no warning case", threeRows)
outNoWarn = bufNoWarn.getvalue()
check("08. no power-windowing warning when every row is windowed",
      "WARNING: some points lack power windowing" not in outNoWarn,
      outNoWarn)

# One row unwindowed: correct code prints the warning; an inverted all(...) does not.
mixedRows = [
    makeRow(500.0, 100e9, 100.0, "GB/s", True),
    makeRow(1000.0, 300e9, 100.0, "GB/s", True),
    makeRow(2000.0, 400e9, 200.0, "GB/s", False),
]
bufWarn = io.StringIO()
with contextlib.redirect_stdout(bufWarn):
    describe("warning case", mixedRows)
outWarn = bufWarn.getvalue()
check("09. power-windowing warning appears when a row lacks windowing",
      "WARNING: some points lack power windowing" in outWarn,
      outWarn)


if failures:
    print(f"FAILED: {', '.join(failures)}")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
