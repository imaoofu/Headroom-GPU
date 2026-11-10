"""Score the RTX 5060 Ti NVML offset ladder (REGISTERED-PREDICTIONS.md section 7).

Usage: python analysis/score_offset_ladder.py PATH_TO_4O_RESULTS

The path may contain the 48 wrapper result directories or collected files. Run the
time-based HWiNFO join for each sweep first: the scorer requires each sweep's own
_sweep_voltage.csv. Suites run 0 / -150 / -300 / 0 MHz; the closing stock suite is a
drift bracket, and no rung is scored unless its median equals the opening one.
"""

import argparse
import csv
import json
import math
import re
import statistics
from pathlib import Path

from analyze_sweep import efficiencyPeak, loadSweep


WORKLOADS = (
    "copy", "reduce", "softmax", "layernorm", "bgemm32", "bgemm64",
    "bgemm128", "bgemm256", "bgemm1024", "attention", "conv", "gemm",
)
ITERATIONS = (2660, 2870, 2600, 1597, 2673, 2661, 2467, 1579, 414, 147, 151, 120)
RUNG_MHZ = {"offset0": 0, "offsetm150": -150, "offsetm300": -300, "offset0close": 0}
# The closing stock suite carries no prediction: it must equal the opening median.
PREDICTED = {"offset0": 1545, "offsetm150": 1395, "offsetm300": 1237}
TARGETS = (1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090)


def find_files(root):
    grouped = {rung: {} for rung in RUNG_MHZ}
    for path in root.rglob("*_sweep.csv"):
        for rung in RUNG_MHZ:
            for workload in WORKLOADS:
                label = f"5060ti-4o-{rung}-{workload}"
                if path.stem.endswith(f"{label}_sweep"):
                    if workload in grouped[rung]:
                        raise ValueError(f"duplicate sweep for {rung}/{workload}")
                    grouped[rung][workload] = path
    for rung, files in grouped.items():
        missing = set(WORKLOADS) - set(files)
        if missing:
            raise ValueError(f"{rung}: missing {', '.join(sorted(missing))}")
    return grouped


def read_voltage(path):
    values = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            try:
                target = int(float(raw["target"]))
                achieved = float(raw["achieved"])
                voltage = float(raw["voltage"])
                count = int(float(raw["sampleCount"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: invalid voltage row: {exc}") from exc
            if target in values or count < 1 or not all(
                math.isfinite(number) and number > 0 for number in (achieved, voltage)
            ):
                raise ValueError(f"{path}: duplicate or invalid voltage reading at {target}")
            values[target] = (achieved, voltage)
    if set(values) != set(TARGETS):
        raise ValueError(f"{path}: voltage extract does not cover the 13 registered targets")
    return values


def read_sweep(path, rung, workload, revised=False):
    label = f"5060ti-4o-{rung}-{workload}"
    metadata_path = path.with_suffix(".json")
    voltage_path = path.with_name(path.stem + "_voltage.csv")
    for companion in (metadata_path, voltage_path):
        if not companion.is_file():
            raise ValueError(f"missing companion file: {companion}")
    with metadata_path.open(encoding="utf-8-sig") as handle:
        metadata = json.load(handle)
    if metadata.get("session_label") != label or "RTX 5060 Ti" not in metadata.get("gpu_name", ""):
        raise ValueError(f"{metadata_path}: wrong session label or GPU")
    for field, expected in (("power_limit_w", 200), ("power_limit_enforced_w", 180),
                            ("power_limit_default_w", 180)):
        try:
            actual = float(metadata[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{metadata_path}: invalid {field}") from exc
        if actual != expected:
            raise ValueError(f"{metadata_path}: {field} is {actual}, expected {expected}")
    command = metadata.get("workload_command", "")
    expected_iterations = ITERATIONS[WORKLOADS.index(workload)]
    match = re.search(r"(?:^|\s)--iterations\s+(\d+)(?:\s|$)", command)
    if (not re.search(rf"(?:^|\s)--workload\s+{workload}(?:\s|$)", command)
            or not match or int(match.group(1)) != expected_iterations):
        raise ValueError(f"{metadata_path}: wrong workload or iteration count")
    if not metadata.get("driver_version"):
        raise ValueError(f"{metadata_path}: missing driver version")

    with path.open(encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))
    if len(raw_rows) != len(TARGETS):
        raise ValueError(f"{path}: expected 13 raw sweep rows")
    missed = set()
    for raw in raw_rows:
        held = raw.get("lock_held") in ("True", "true")
        if not held:
            missed.add(int(float(raw["target_frequency_mhz"])))
        # REGISTERED rule: every row must hold its lock. On stock this can never be met at
        # 2932/3090 MHz (24 of 24 committed stock-repro sweeps miss them), so the registered
        # verdict is INVALID by construction. The REVISED rule, defined 2026-09-23 after
        # collection and before any median was computed, keeps rows that missed BELOW target
        # and invalidates a sweep only if a missed row is that workload's optimum.
        lock_ok = held or (revised and raw.get("lock_miss_direction") == "below")
        if (raw.get("bench_ok") not in ("True", "true") or not lock_ok
                or raw.get("power_window_applied") not in ("True", "true")):
            raise ValueError(f"{path}: failed benchmark, missed lock or unwindowed power")
        # The MAXIMUM is the witness, not the average: the average takes in idle memory
        # (810 MHz) between iterations (5060ti-p1-suite-20260922/README.md). Stock has two
        # loaded states, 13801 and 14001; any Afterburner memory offset reads 15801 or more.
        # Corrected 2026-09-23 after collection and BEFORE any median was computed.
        try:
            memory = float(raw["memory_clock_max_mhz"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: invalid memory clock") from exc
        if not math.isfinite(memory) or not 13701 <= memory <= 14101:
            raise ValueError(f"{path}: memory clock does not verify stock Profile 3")

    try:
        rows = loadSweep(path)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{path}: invalid sweep: {exc}") from exc
    # Registered: 15 MHz. The sweep tool itself calls a lock held within 30 MHz
    # (Invoke-FrequencySweep.ps1, lock_held), and stock reaches 2782 only as 2752.5, so the
    # REVISED rule defers to the tool's own definition.
    tolerance = 30 if revised else 15
    if len(rows) != len(TARGETS) or {row["target"] for row in rows} != set(TARGETS):
        raise ValueError(f"{path}: usable rows do not match the fixed 13-point target grid")
    if any(not all(math.isfinite(row[key]) and row[key] > 0
                   for key in ("mhz", "throughput", "power", "efficiency"))
           or (row["target"] not in missed and abs(row["mhz"] - row["target"]) > tolerance)
           for row in rows):
        raise ValueError(f"{path}: invalid value or failed frequency lock")
    volts = read_voltage(voltage_path)
    if any(abs(row["mhz"] - volts[row["target"]][0]) > 10 for row in rows):
        raise ValueError(f"{voltage_path}: achieved clocks disagree with sweep")
    best = efficiencyPeak(rows)
    if best["target"] in missed:
        raise ValueError(f"{path}: the efficiency optimum is a missed-lock row")
    return {"best_target": best["target"], "best_achieved": best["mhz"],
            "driver": metadata["driver_version"], "voltage": volts}


def score(root, revised=False):
    files = find_files(Path(root))
    results = {rung: {work: read_sweep(files[rung][work], rung, work, revised)
                      for work in WORKLOADS} for rung in RUNG_MHZ}
    drivers = {item["driver"] for suite in results.values() for item in suite.values()}
    if len(drivers) != 1:
        raise ValueError(f"driver changed during ladder: {sorted(drivers)}")
    medians = {rung: statistics.median(item["best_target"] for item in suite.values())
               for rung, suite in results.items()}
    rungs = tuple(PREDICTED)
    drift_ok = medians["offset0"] == medians["offset0close"]
    if not drift_ok:
        # A drifted session is uninterpretable, never a pass or a null.
        return {"driver": next(iter(drivers)), "results": results, "medians": medians,
                "drift_ok": False, "per_rung": {rung: "UNINTERPRETABLE" for rung in rungs},
                "nonincreasing": None, "strict_drops": None}
    return {
        "driver": next(iter(drivers)), "results": results, "medians": medians,
        "drift_ok": True,
        "per_rung": {rung: "PASS" if medians[rung] == PREDICTED[rung] else "FAIL"
                     for rung in rungs},
        "nonincreasing": all(medians[a] >= medians[b] for a, b in zip(rungs, rungs[1:])),
        "strict_drops": medians[rungs[0]] > medians[rungs[1]] > medians[rungs[2]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--revised", action="store_true",
                        help="POST HOC: keep below-target missed-lock rows (see read_sweep)")
    args = parser.parse_args()
    if args.revised:
        print("REVISED SCORING, defined after collection and before any median was computed.")
        print("It is NOT the registered verdict; report both.")
    try:
        result = score(args.results, args.revised)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"UNSCOREABLE: {exc}\n")
    print(f"Driver: {result['driver']}; one chip, one suite per offset")
    for rung, offset in RUNG_MHZ.items():
        observed = result["medians"][rung]
        optima = result["results"][rung]
        expected = PREDICTED.get(rung, PREDICTED["offset0"])
        verdict = result["per_rung"].get(rung, "drift bracket")
        print(f"{rung} ({offset} MHz): median target {observed:g}; expected {expected}; "
              f"{verdict}; individual matches "
              f"{sum(item['best_target'] == expected for item in optima.values())}/12")
        print("  " + ", ".join(f"{work}={optima[work]['best_target']} "
                               f"(achieved {optima[work]['best_achieved']:.1f})"
                               for work in WORKLOADS))
    if not result["drift_ok"]:
        print("DRIFT: the opening and closing stock medians differ, so the session drifted.")
        print("No rung is scored. This is uninterpretable, not a pass and not a null.")
    else:
        print("Drift bracket: opening and closing stock medians agree.")
        print("Nonincreasing median trend:", "PASS" if result["nonincreasing"] else "FAIL")
        print("Strict drops 0 > -150 > -300:", "PASS" if result["strict_drops"] else "FAIL")
    print("The -300 rung is edge-limited: 1237 is the lowest grid target, so a pass fits any")
    print("optimum at or below ~1316 MHz. Only the -150 rung locates the move.")
    print("Offset read-back must be verified from the runner log; VID is not rail voltage.")


if __name__ == "__main__":
    main()
