"""
Known-answer checks for the join pipeline in join_hwinfo_voltage.py.

WHY THIS FUNCTION NEEDS TESTS AT ALL
    join_hwinfo_voltage.py is the only place in this project that turns raw HWiNFO telemetry
    into the voltage numbers behind the central result: that a stock GPU raises voltage as
    frequency climbs while a flattened V/F curve does not. A defect here does not shift a
    decimal. It invents or erases that slope. The file has no test coverage, which is what
    this suite fixes.

    The subtle cases, each of which a careless implementation gets wrong without an error:

    - HWiNFO on this machine emits TWO sensor blocks, so the header can carry two `GPU Clock
      [MHz]` columns. The phantom block sits at a fixed clock, so the loader must pick the
      column with the LARGEST spread, not the first one it sees. Voltage, crossbar and power
      are then resolved to the column nearest the chosen clock.

    - The boundaries are inclusive. A sample exactly at minPower is kept by filterIdle, and a
      sample exactly toleranceMhz away is kept by matchSamples. An off-by-one in either
      direction silently drops the boundary sample and shifts the median.

    - A sample whose power is None is KEPT by filterIdle. An absent power column means the log
      never carried one, and dropping every sample would produce a silently empty join.

    - loadSweep here does NOT filter on bench_ok and does NOT drop overshot clock locks,
      unlike the loader in analysis/analyze_sweep.py. It keeps every non-empty row.

PROVENANCE
    Drafted by a local model (qwen38-headroom via Ollama) from
    tools/local-model/specs/join-hwinfo-voltage-tests.md, then verified here rather than trusted.
    The draft had three defects, all in the tests and none in the module: two floating-point
    equality assertions on computed medians, and a tolerance case whose sample comments measured
    distance from a different reference point than the call passed, so a sample 1 MHz away was
    labelled "26 away, outside" and expected to be dropped.

    Eleven deliberate mutations were then introduced into join_hwinfo_voltage.py - inverting the
    idle filter, making either boundary exclusive, dropping samples with no power reading,
    swapping the median for the mean, reporting a missing crossbar as 0.0, selecting the phantom
    AMD sensor block, taking the first voltage column instead of the nearest, and two loadSweep
    changes - and all eleven were caught. Tests that pass against a broken function are worse
    than no tests, so that check is the reason this file is committed.

    Delete __pycache__ between mutations if repeating this. Stale bytecode has previously run a
    mutated module while the restored source was on screen.

Run: python tools/frequency-sweep/test_join_hwinfo_voltage.py
"""

import sys
from pathlib import Path
import tempfile
import os
import math
import csv
from datetime import datetime, timezone
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
from join_hwinfo_voltage import (loadHwinfo, loadSweep, filterIdle,
                                 matchSamples, summarisePoint, contestedSamples,
                                 selectJoinMode)

failures = []

def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"  Detail: {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")

# Test 1: loadHwinfo picks the MOVING clock column, not the first one.
# Header carries two `GPU Clock [MHz]` columns. The first (index 0) is constant; the
# second (index 2) varies. The loader must choose the varying one.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write("GPU Clock [MHz],GPU Core Voltage [V],GPU Clock [MHz],GPU Core Voltage [V],GPU Crossbar Clock [MHz],GPU Power [W]\n")
    # phantom clock constant at 100, real clock varies
    f.write("100,0.90,1000,1.05,2000,120\n")
    f.write("100,0.90,1200,1.10,2000,140\n")
    f.write("100,0.90,1400,1.15,2000,160\n")
    temp_path1 = f.name

try:
    samples1, indices1 = loadHwinfo(temp_path1)
    # The chosen clock column is the varying one: sample clocks must not all be equal.
    clocks = [s["clock"] for s in samples1]
    check("loadHwinfo picks the moving clock column", len(set(clocks)) > 1,
          f"clocks were {clocks}; expected variation, not a constant phantom")
    # And the chosen index must be the second clock column (index 2), not the first (index 0).
    check("loadHwinfo clock index is the varying column", indices1["clock"] == 2,
          f"clock index was {indices1['clock']}, expected 2")
finally:
    os.unlink(temp_path1)

# Test 2: loadHwinfo resolves voltage to the column nearest the chosen clock,
# with two voltage candidates present.
# In the same layout, voltage candidates are index 1 and index 3. The chosen clock is
# index 2, so the nearest voltage column is index 3 (distance 1), not index 1 (distance 1)
# -- wait, both are distance 1. To make this unambiguous, shift the layout so the chosen
# clock is closer to one voltage column. Rebuild: phantom clock at 0, real clock at 3,
# voltage candidates at 1 and 4. Distances from 3: |1-3|=2, |4-3|=1 -> index 4 wins.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write("GPU Clock [MHz],GPU Core Voltage [V],GPU Crossbar Clock [MHz],GPU Clock [MHz],GPU Core Voltage [V],GPU Power [W]\n")
    f.write("100,0.90,2000,1000,1.05,120\n")
    f.write("100,0.90,2000,1200,1.10,140\n")
    f.write("100,0.90,2000,1400,1.15,160\n")
    temp_path2 = f.name

try:
    samples2, indices2 = loadHwinfo(temp_path2)
    # Chosen clock is index 3 (the varying one). Nearest voltage is index 4.
    check("loadHwinfo voltage resolves to nearest column", indices2["voltage"] == 4,
          f"voltage index was {indices2['voltage']}, expected 4")
    # Sanity: the real voltage values (1.05, 1.10, 1.15) should be what we read, not the
    # phantom 0.90.
    check("loadHwinfo reads the nearest voltage values",
          sorted(s["voltage"] for s in samples2) == [1.05, 1.10, 1.15],
          f"voltages were {sorted(s['voltage'] for s in samples2)}")
finally:
    os.unlink(temp_path2)

# Test 3: loadHwinfo raises SystemExit when the voltage column is missing.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write("GPU Clock [MHz],GPU Crossbar Clock [MHz],GPU Power [W]\n")
    f.write("1000,2000,120\n")
    f.write("1200,2000,140\n")
    temp_path3 = f.name

try:
    raised = False
    try:
        loadHwinfo(temp_path3)
    except SystemExit:
        raised = True
    check("loadHwinfo raises SystemExit when voltage column is missing", raised)
finally:
    os.unlink(temp_path3)

# Test 4: loadHwinfo skips a row whose voltage is not a number, and keeps the surrounding rows.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write("GPU Clock [MHz],GPU Core Voltage [V],GPU Power [W]\n")
    f.write("1000,1.05,120\n")
    f.write("1200,NOT_A_NUMBER,140\n")
    f.write("1400,1.15,160\n")
    temp_path4 = f.name

try:
    samples4, _ = loadHwinfo(temp_path4)
    check("loadHwinfo skips non-numeric voltage row", len(samples4) == 2,
          f"got {len(samples4)} samples, expected 2")
    check("loadHwinfo keeps surrounding rows",
          [s["clock"] for s in samples4] == [1000.0, 1400.0],
          f"clocks were {[s['clock'] for s in samples4]}")
finally:
    os.unlink(temp_path4)

# Test 5: loadHwinfo returns crossbar None and power None when those columns are absent.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write("GPU Clock [MHz],GPU Core Voltage [V]\n")
    f.write("1000,1.05\n")
    f.write("1200,1.10\n")
    temp_path5 = f.name

try:
    samples5, indices5 = loadHwinfo(temp_path5)
    check("loadHwinfo crossbar index is None when absent", indices5["crossbar"] is None)
    check("loadHwinfo power index is None when absent", indices5["power"] is None)
    check("loadHwinfo sample crossbar is None", all(s["crossbar"] is None for s in samples5))
    check("loadHwinfo sample power is None", all(s["power"] is None for s in samples5))
finally:
    os.unlink(temp_path5)

# Test 6: loadSweep parses a file written with a UTF-8 BOM.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
    f.write("target_frequency_mhz,achieved_frequency_avg,bench_throughput,power_avg_w,memory_clock_avg_mhz\n")
    f.write("1000,1000,1000000000,100,1500\n")
    temp_path6 = f.name

try:
    rows6 = loadSweep(temp_path6)
    check("loadSweep parses UTF-8 BOM file", len(rows6) == 1,
          f"got {len(rows6)} rows")
    check("loadSweep BOM row fields parsed",
          rows6[0]["target"] == 1000 and rows6[0]["achieved"] == 1000.0
          and rows6[0]["throughputGbs"] == 1.0 and rows6[0]["powerW"] == 100.0
          and rows6[0]["memoryMhz"] == 1500.0,
          f"row was {rows6[0] if rows6 else None}")
finally:
    os.unlink(temp_path6)

# Test 7: loadSweep keeps a row with bench_ok False and a row whose lock overshot.
# Unlike analysis/analyze_sweep.py, this loader does NOT filter on bench_ok and does NOT
# drop overshot clock locks. Both rows must survive.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("target_frequency_mhz,achieved_frequency_avg,bench_throughput,power_avg_w,memory_clock_avg_mhz,bench_ok,lock_miss_direction\n")
    f.write("1000,1000,1000000000,100,1500,False,above\n")
    f.write("1200,1200,1200000000,120,1500,True,below\n")
    temp_path7 = f.name

try:
    rows7 = loadSweep(temp_path7)
    check("loadSweep keeps bench_ok False and overshot lock row", len(rows7) == 2,
          f"got {len(rows7)} rows, expected 2")
    check("loadSweep keeps both rows' achieved values",
          sorted(r["achieved"] for r in rows7) == [1000.0, 1200.0],
          f"achieved were {sorted(r['achieved'] for r in rows7)}")
finally:
    os.unlink(temp_path7)

# Test 8: loadSweep gives memoryMhz nan when the column is absent.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("target_frequency_mhz,achieved_frequency_avg,bench_throughput,power_avg_w\n")
    f.write("1000,1000,1000000000,100\n")
    temp_path8 = f.name

try:
    rows8 = loadSweep(temp_path8)
    check("loadSweep memoryMhz is nan when column absent",
          math.isnan(rows8[0]["memoryMhz"]),
          f"memoryMhz was {rows8[0]['memoryMhz']!r}; nan != nan, so use math.isnan")
finally:
    os.unlink(temp_path8)

# Test 9: filterIdle keeps a None-power sample.
samples9 = [
    {"clock": 1000.0, "voltage": 1.05, "crossbar": 2000.0, "power": None},
    {"clock": 1200.0, "voltage": 1.10, "crossbar": 2000.0, "power": 140.0},
]
kept9 = filterIdle(samples9, 50.0)
check("filterIdle keeps None-power sample", len(kept9) == 2,
      f"got {len(kept9)} kept, expected 2")

# Test 10: filterIdle keeps a sample exactly at minPower and drops one below it.
samples10 = [
    {"clock": 1000.0, "voltage": 1.05, "crossbar": 2000.0, "power": 50.0},   # exactly at min
    {"clock": 1200.0, "voltage": 1.10, "crossbar": 2000.0, "power": 49.0},   # below min
    {"clock": 1400.0, "voltage": 1.15, "crossbar": 2000.0, "power": 51.0},   # above min
]
kept10 = filterIdle(samples10, 50.0)
check("filterIdle keeps sample exactly at minPower",
      any(s["clock"] == 1000.0 for s in kept10),
      f"kept clocks were {[s['clock'] for s in kept10]}")
check("filterIdle drops sample below minPower",
      not any(s["clock"] == 1200.0 for s in kept10),
      f"kept clocks were {[s['clock'] for s in kept10]}")
check("filterIdle keeps sample above minPower",
      any(s["clock"] == 1400.0 for s in kept10),
      f"kept clocks were {[s['clock'] for s in kept10]}")

# Test 11: the manufactured-slope case. An idle high-voltage sample above the real ones is
# excluded by filterIdle, and this changes the summarised median.
# Two loaded samples at low voltage (1.05, 1.10) and one idle sample at high voltage (1.35).
# The idle sample has a high power reading so that, if it were NOT filtered, it would survive
# filterIdle and pull the median up. We prove the filter is what removes it.
samples11 = [
    {"clock": 1000.0, "voltage": 1.05, "crossbar": 2000.0, "power": 120.0},  # loaded
    {"clock": 1200.0, "voltage": 1.10, "crossbar": 2000.0, "power": 140.0},  # loaded
    {"clock": 1400.0, "voltage": 1.35, "crossbar": 2000.0, "power": 10.0},   # idle, high V
]
# A minPower of 50 drops the idle sample (power 10) and keeps the two loaded ones.
kept11 = filterIdle(samples11, 50.0)
check("filterIdle excludes the idle high-voltage sample", len(kept11) == 2,
      f"got {len(kept11)} kept, expected 2")
voltage11, crossbar11, ratio11 = summarisePoint(kept11, 1100.0)
check("filterIdle + summarisePoint median is the loaded voltage",
      abs(voltage11 - 1.075) < 1e-9,
      f"median voltage was {voltage11!r}, expected 1.075 (median of 1.05 and 1.10)")
# Prove the filter changed the result: without it, the idle sample would be in the median.
voltage11_unfiltered, _, _ = summarisePoint(samples11, 1100.0)
check("idle sample would have changed the median if not filtered",
      voltage11_unfiltered != voltage11,
      f"unfiltered median was {voltage11_unfiltered!r}, filtered was {voltage11!r}")

# Test 12: matchSamples keeps a sample exactly at the tolerance and drops one just outside.
# All distances are from 1000.0, which is what the call below passes. Both boundary samples
# sit exactly ON the tolerance and must be kept; inclusivity is the whole point of the case.
samples12 = [
    {"clock": 1025.0, "voltage": 1.05, "crossbar": 2000.0, "power": 120.0},  # +25, exactly on
    {"clock": 975.0, "voltage": 1.04, "crossbar": 2000.0, "power": 120.0},   # -25, exactly on
    {"clock": 1026.0, "voltage": 1.06, "crossbar": 2000.0, "power": 120.0},  # +26, just outside
    {"clock": 974.0, "voltage": 1.03, "crossbar": 2000.0, "power": 120.0},   # -26, just outside
]
matched12 = matchSamples(samples12, 1000.0, toleranceMhz=25.0)
check("matchSamples keeps both samples exactly at the tolerance",
      any(s["clock"] == 1025.0 for s in matched12) and any(s["clock"] == 975.0 for s in matched12),
      f"matched clocks were {[s['clock'] for s in matched12]}")
check("matchSamples drops samples just outside the tolerance",
      not any(s["clock"] in (1026.0, 974.0) for s in matched12),
      f"matched clocks were {[s['clock'] for s in matched12]}")

# Test 13: matchSamples returns an empty list when nothing is near.
samples13 = [
    {"clock": 1000.0, "voltage": 1.05, "crossbar": 2000.0, "power": 120.0},
]
matched13 = matchSamples(samples13, 5000.0, toleranceMhz=25.0)
check("matchSamples returns empty list when nothing is near", matched13 == [])

# Test 14: summarisePoint returns the median and not the mean.
# Voltages where median != mean: [1.0, 1.0, 1.0, 1.0, 1.5] -> median 1.0, mean 1.1.
samples14 = [
    {"clock": 1000.0, "voltage": 1.0, "crossbar": 2000.0, "power": 120.0},
    {"clock": 1000.0, "voltage": 1.0, "crossbar": 2000.0, "power": 120.0},
    {"clock": 1000.0, "voltage": 1.0, "crossbar": 2000.0, "power": 120.0},
    {"clock": 1000.0, "voltage": 1.0, "crossbar": 2000.0, "power": 120.0},
    {"clock": 1000.0, "voltage": 1.5, "crossbar": 2000.0, "power": 120.0},
]
voltage14, crossbar14, ratio14 = summarisePoint(samples14, 1000.0)
check("summarisePoint returns median not mean", voltage14 == 1.0,
      f"voltage was {voltage14!r}; median is 1.0, mean would be 1.1")

# Test 15: summarisePoint ignores None crossbars but still uses the rest.
samples15 = [
    {"clock": 1000.0, "voltage": 1.05, "crossbar": 2000.0, "power": 120.0},
    {"clock": 1000.0, "voltage": 1.10, "crossbar": None, "power": 120.0},
    {"clock": 1000.0, "voltage": 1.15, "crossbar": 2100.0, "power": 120.0},
]
voltage15, crossbar15, ratio15 = summarisePoint(samples15, 1000.0)
check("summarisePoint ignores None crossbars and uses the rest",
      crossbar15 == 2050.0,
      f"crossbar was {crossbar15!r}, expected 2050.0 (median of 2000 and 2100)")

# Test 16: summarisePoint gives nan crossbar AND nan ratio when every crossbar is None.
samples16 = [
    {"clock": 1000.0, "voltage": 1.05, "crossbar": None, "power": 120.0},
    {"clock": 1000.0, "voltage": 1.10, "crossbar": None, "power": 120.0},
]
voltage16, crossbar16, ratio16 = summarisePoint(samples16, 1000.0)
check("summarisePoint crossbar is nan when all None", math.isnan(crossbar16),
      f"crossbar was {crossbar16!r}")
check("summarisePoint ratio is nan when all crossbar None", math.isnan(ratio16),
      f"ratio was {ratio16!r}")

# Test 17: summarisePoint's ratio equals crossbar divided by achievedMhz, verifiable by hand.
# crossbar median 2000.0, achievedMhz 1000.0 -> ratio 2.0.
samples17 = [
    {"clock": 1000.0, "voltage": 1.05, "crossbar": 2000.0, "power": 120.0},
]
voltage17, crossbar17, ratio17 = summarisePoint(samples17, 1000.0)
check("summarisePoint ratio equals crossbar / achievedMhz",
      crossbar17 == 2000.0 and ratio17 == 2.0,
      f"crossbar was {crossbar17!r}, ratio was {ratio17!r}, expected 2000.0 and 2.0")

# ---------------------------------------------------------------------------
# contestedSamples - the bin-overlap check added 2026-09-15.
#
# ⛔ THE FIRST VERSION OF THIS CHECK COMPARED GRID SPACING AGAINST THE TOLERANCE and flagged 92
# committed sweeps, both RTX 3070 Ti fine sweeps among them. Every one of those was FALSE: a
# hard-locked clock reports at its target, so its samples never reach the neighbour however close
# the grid looks. Re-derived at a 7 MHz bin the 3070 Ti voltages came back identical to three
# decimals. These checks pin the distinction so the geometric version cannot come back.

def point(mhz):
    return {"target": int(mhz), "achieved": float(mhz), "throughputGbs": 1.0,
            "powerW": 100.0, "memoryMhz": 1000.0}


def sample(mhz):
    return {"clock": float(mhz), "voltage": 0.7, "crossbar": None, "power": 100.0}


# Test 18: a fine grid whose samples sit exactly on their targets is NOT contested at a tight bin.
sweepFine = [point(900), point(915), point(945)]
contested18, total18 = contestedSamples([sample(900), sample(915), sample(945)], sweepFine, 7.0)
check("a 15 MHz grid is uncontested at a 7 MHz bin", contested18 == 0 and total18 == 3,
      f"got {contested18} of {total18}")

# Test 19: the SAME grid and the SAME samples ARE contested at the 25 MHz default. This is the
# 2026-09-15 RTX 2060 Super case in miniature - nothing about the data changed, only the bin.
# Worked by hand: 900 is within 25 of both 900 and 915 -> contested. 915 is within 25 of 900 and
# 915, but 945 is 30 away -> contested. 945 is within 25 of 945 only, since 915 is 30 away -> NOT
# contested. So TWO of the three, and the third is clean for the same reason test 20 is.
contested19, _ = contestedSamples([sample(900), sample(915), sample(945)], sweepFine, 25.0)
check("the same 15 MHz grid IS contested at the 25 MHz default", contested19 == 2,
      f"got {contested19}, expected 2 of the 3 samples claimed twice")

# Test 20: THE FALSE-POSITIVE GUARD. Points 30 MHz apart look too close for a 25 MHz bin on
# geometry alone (30 < 50), but samples landing exactly on their locked targets are claimed once
# each. This is the RTX 3070 Ti fine sweep, and it must NOT be flagged.
sweep3070 = [point(1200), point(1245), point(1290), point(1335)]
samples3070 = [sample(1200), sample(1245), sample(1290), sample(1335)]
contested20, _ = contestedSamples(samples3070, sweep3070, 25.0)
check("hard-locked points 45 MHz apart are uncontested at the 25 MHz default - geometry says "
      "possible, the samples say it did not happen", contested20 == 0, f"got {contested20}")

# Test 21: a sample stranded BETWEEN two points is the thing actually being detected.
contested21, _ = contestedSamples([sample(907)], [point(900), point(915)], 10.0)
check("a sample between two points is counted once, not twice", contested21 == 1,
      f"got {contested21}")

# Test 22: no samples means nothing contested, rather than a crash or a divide.
contested22, total22 = contestedSamples([], sweepFine, 25.0)
check("an empty sample list is uncontested", contested22 == 0 and total22 == 0,
      f"got {contested22} of {total22}")

# Test 23: a single sweep point can never contest with itself, at any tolerance.
contested23, _ = contestedSamples([sample(1000)], [point(1000)], 500.0)
check("one point cannot contest with itself even at an absurd tolerance", contested23 == 0,
      f"got {contested23}")

# Time join: two different requested clocks clip to the same achieved clock. A clock join pools
# both voltage levels, but the benchmark windows must recover each one separately. Include one
# low-power reading inside a valid benchmark window: time mode must not silently discard it.
with tempfile.TemporaryDirectory() as directory:
    sweepPath = Path(directory) / "clipped_sweep.csv"
    hwinfoPath = Path(directory) / "hwinfo.csv"
    start = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc).timestamp()
    with sweepPath.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                         "power_avg_w", "window_start_unix", "window_end_unix"])
        writer.writerow([1590, 1500, 300000000000, 100, start, start + 5])
        writer.writerow([1695, 1500, 310000000000, 105, start + 10, start + 15])
    with hwinfoPath.open("w", newline="", encoding="latin-1") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Time", "GPU Clock [MHz]", "GPU Core Voltage [V]",
                         "GPU Crossbar Clock [MHz]", "GPU Power [W]"])
        # HWiNFO does not always zero-pad minutes and seconds (e.g. 22:30:1.879).
        writer.writerow(["21.9.2026", "12:0:1.000", 1500, 0.7, 1300, 100])
        writer.writerow(["21.9.2026", "12:00:02.000", 1500, 0.7, 1300, 100])
        writer.writerow(["21.9.2026", "12:00:11.000", 1500, 0.8, 1400, 20])
        writer.writerow(["21.9.2026", "12:00:12.000", 1500, 0.8, 1400, 105])

    check("complete stamps select the time join by default",
          selectJoinMode(loadSweep(sweepPath), "auto") == "time")
    command = [sys.executable, str(Path(__file__).with_name("join_hwinfo_voltage.py")),
               str(sweepPath), str(hwinfoPath), "--hwinfo-utc-offset=+00:00"]
    result = subprocess.run(command, capture_output=True, text=True)
    outputPath = sweepPath.with_name("clipped_sweep_voltage.csv")
    check("time join succeeds for clipped clocks", result.returncode == 0,
          result.stdout + result.stderr)
    if outputPath.exists():
        with outputPath.open(newline="", encoding="utf-8") as handle:
            merged = list(csv.DictReader(handle))
        check("time join separates equal achieved clocks by benchmark window",
              len(merged) == 2 and [float(p["voltage"]) for p in merged] == [0.7, 0.8]
              and [int(p["sampleCount"]) for p in merged] == [2, 2]
              and [int(p["hwinfoUtcOffsetMinutes"]) for p in merged] == [0, 0], str(merged))
        outputPath.unlink()
    else:
        check("time join writes a voltage extract", False, result.stdout + result.stderr)

    wrongZone = subprocess.run(command[:-1] + ["--hwinfo-utc-offset=-01:00"],
                               capture_output=True, text=True)
    check("wrong time zone refuses an empty join and writes no extract",
          wrongZone.returncode != 0 and not outputPath.exists(),
          wrongZone.stdout + wrongZone.stderr)

    # The normal bench path omits --hwinfo-utc-offset. HWiNFO writes the host's local time,
    # so reconstruct a second log in that zone and verify the automatic interpretation.
    localHwinfoPath = Path(directory) / "hwinfo-local.csv"
    localOffset = None
    with localHwinfoPath.open("w", newline="", encoding="latin-1") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Time", "GPU Clock [MHz]", "GPU Core Voltage [V]",
                         "GPU Crossbar Clock [MHz]", "GPU Power [W]"])
        for seconds, voltage in [(1, 0.7), (2, 0.7), (11, 0.8), (12, 0.8)]:
            localTime = datetime.fromtimestamp(start + seconds).astimezone()
            localOffset = int(localTime.utcoffset().total_seconds() / 60)
            writer.writerow([localTime.strftime("%d.%m.%Y"),
                             localTime.strftime("%H:%M:%S.%f"),
                             1500, voltage, 1300, 100])
    localRun = subprocess.run(command[:3] + [str(localHwinfoPath)],
                              capture_output=True, text=True)
    check("host-local HWiNFO time joins without an explicit UTC offset",
          localRun.returncode == 0, localRun.stdout + localRun.stderr)
    if outputPath.exists():
        with outputPath.open(newline="", encoding="utf-8") as handle:
            localMerged = list(csv.DictReader(handle))
        check("time extract records the inferred host-local UTC offset",
              len(localMerged) == 2
              and [float(p["voltage"]) for p in localMerged] == [0.7, 0.8]
              and [int(p["hwinfoUtcOffsetMinutes"]) for p in localMerged]
              == [localOffset, localOffset], str(localMerged))
        outputPath.unlink()
    else:
        check("host-local time join writes a voltage extract", False,
              localRun.stdout + localRun.stderr)

    with sweepPath.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([1800, 1500, 320000000000, 110, "", ""])
    try:
        selectJoinMode(loadSweep(sweepPath), "auto")
        partialRejected = False
    except SystemExit:
        partialRejected = True
    check("partially stamped sweep is refused rather than silently clock-joined", partialRejected)

# The MEASURED crossbar column (added 2026-09-30 for REGISTERED-PREDICTIONS section 14). Under a
# crossbar clock offset the reported column may show the request; the measured one is the evidence.
with tempfile.TemporaryDirectory() as directory:
    sweepPath = Path(directory) / "xbar_sweep.csv"
    hwinfoPath = Path(directory) / "hwinfo.csv"
    start = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc).timestamp()
    with sweepPath.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                         "power_avg_w", "window_start_unix", "window_end_unix"])
        writer.writerow([1560, 1552, 330000000000, 60, start, start + 5])
    with hwinfoPath.open("w", newline="", encoding="latin-1") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Time", "GPU Clock [MHz]", "GPU Core Voltage [V]",
                         "GPU Crossbar Clock [MHz]", "GPU Power [W]",
                         "GPU Crossbar Clock (measured) [MHz]"])
        # Reported shows the request (1485); measured shows what happened (1340). One blank
        # measured cell must not drop the row's voltage.
        writer.writerow(["30.9.2026", "12:00:01.000", 1552, 0.73, 1485, 60, 1338])
        writer.writerow(["30.9.2026", "12:00:02.000", 1552, 0.73, 1485, 60, 1340])
        writer.writerow(["30.9.2026", "12:00:03.000", 1552, 0.73, 1485, 60, ""])
        writer.writerow(["30.9.2026", "12:00:04.000", 1552, 0.73, 1485, 60, 1342])

    loadedMeasured, indicesMeasured = loadHwinfo(hwinfoPath)
    check("measured crossbar column is found separately from the reported one",
          indicesMeasured["crossbarMeasured"] == 6 and indicesMeasured["crossbar"] == 4,
          str(indicesMeasured))
    check("a blank measured cell keeps the row and records None",
          len(loadedMeasured) == 4 and loadedMeasured[2]["crossbarMeasured"] is None,
          str(loadedMeasured))
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("join_hwinfo_voltage.py")),
                             str(sweepPath), str(hwinfoPath), "--hwinfo-utc-offset=+00:00"],
                            capture_output=True, text=True)
    outputPath = sweepPath.with_name("xbar_sweep_voltage.csv")
    if outputPath.exists():
        with outputPath.open(newline="", encoding="utf-8") as handle:
            merged = list(csv.DictReader(handle))
        check("the extract carries reported AND measured crossbar, each from its own column",
              len(merged) == 1 and float(merged[0]["crossbar"]) == 1485.0
              and float(merged[0]["crossbarMeasured"]) == 1340.0, str(merged))
        check("the measured column is appended after the existing ones",
              list(merged[0].keys())[-1] == "crossbarMeasured", str(list(merged[0].keys())))
    else:
        check("a join with a measured column writes an extract", False, result.stdout + result.stderr)

# Without the measured column, the extract's schema is exactly what it was before 2026-09-30.
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write("GPU Clock [MHz],GPU Core Voltage [V],GPU Crossbar Clock [MHz]" + chr(10))
    f.write("1000,1.05,2000" + chr(10))
    pathNoMeasured = f.name
try:
    samplesNoMeasured, indicesNoMeasured = loadHwinfo(pathNoMeasured)
    check("no measured column: index None and no per-sample key",
          indicesNoMeasured["crossbarMeasured"] is None
          and all("crossbarMeasured" not in s for s in samplesNoMeasured))
finally:
    os.unlink(pathNoMeasured)

# GPT Job 107 (2026-10-18): a repeated header that moves an opening name means every position may
# point at another sensor (an inserted column made this loader read power as voltage), so the join
# refuses. A column APPENDED at the end, proven by a closing header that keeps the opening names, is
# read normally: that is what HWiNFO does when a sensor appears mid-log.
OPEN = "Date,Time,GPU Clock [MHz],GPU Core Voltage [V],GPU Power [W],"   # HWiNFO always leads with Date,Time
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write(OPEN + chr(10))
    f.write("18.10.2026,9:00:00.000,1000,0.72,90," + chr(10))
    f.write("18.10.2026,9:00:01.000,1200,0.73,95,2100," + chr(10))   # a sensor appended after the opening columns
    f.write(OPEN + "GPU Clock (Effective) [MHz]," + chr(10))
    pathAppended = f.name
try:
    samplesAppended, _ = loadHwinfo(pathAppended)
    check("an appended column keeps every reading (voltage 0.72, 0.73)",
          [s["voltage"] for s in samplesAppended] == [0.72, 0.73])
finally:
    os.unlink(pathAppended)

with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="latin-1") as f:
    f.write(OPEN + chr(10))
    f.write("18.10.2026,9:00:00.000,1000,0.72,90," + chr(10))
    f.write("18.10.2026,9:00:01.000,1200,0,0.73,95," + chr(10))      # a value inserted before voltage: positions moved
    f.write("Date,Time,GPU Clock [MHz],GPU Clock (Effective) [MHz],GPU Core Voltage [V],GPU Power [W]," + chr(10))
    pathInserted = f.name
try:
    try:
        loadHwinfo(pathInserted)
        refused = False
    except SystemExit as exit:
        refused = "does not keep the opening column names in place" in str(exit)
    check("a repeated header that moves an opening name makes the join refuse", refused)
finally:
    os.unlink(pathInserted)

if failures:
    print(f"FAILED: {', '.join(failures)}")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
