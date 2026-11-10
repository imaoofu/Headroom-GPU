"""Compare two frequency sweeps point by point.

This tool reports the numeric differences between two sweeps of the same
frequency grid, for REGISTERED-PREDICTIONS section 8c and similar pairs. Drafted by the local model
(queue 2026-09-24, job L2) and reviewed; see docs/local-model-findings/. It does not explain those differences: sweep order,
temperature, time of day and session all differ together, and none of them
can be separated from the data here.
"""

import argparse
import csv
import json
import sys

# target_frequency_mhz added at review (2026-09-24): the local model's draft keyed every row on it
# without requiring it, so a file lacking it failed with a bare KeyError instead of this message.
REQUIRED_SOURCE_COLUMNS = {
    "target_frequency_mhz",
    "achieved_frequency_avg",
    "bench_throughput",
    "power_avg_w",
    "temperature_avg_c",
    "lock_held",
    "bench_ok",
}


def _parse_bool(value):
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError("boolean column must be 'True' or 'False', got %r" % value)


def load_sweep(path):
    sweep = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        missing = REQUIRED_SOURCE_COLUMNS - header
        if missing:
            raise ValueError(
                "%s is missing required columns: %s" % (path, ", ".join(sorted(missing)))
            )
        for row in reader:
            target = int(row["target_frequency_mhz"])
            if target in sweep:
                raise ValueError("%s has duplicate target frequency %d" % (path, target))
            throughput_raw = row["bench_throughput"]
            if throughput_raw is None or throughput_raw.strip() == "":
                raise ValueError("%s has empty bench_throughput at target %d" % (path, target))
            sweep[target] = {
                "achieved": float(row["achieved_frequency_avg"]),
                "throughput": float(throughput_raw),
                "power": float(row["power_avg_w"]),
                "temp": float(row["temperature_avg_c"]),
                "lock_held": _parse_bool(row["lock_held"]),
                "bench_ok": _parse_bool(row["bench_ok"]),
            }
    return sweep


def compare(a, b):
    shared_targets = sorted(set(a) & set(b))
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))

    points = []
    clean_points = []
    for target in shared_targets:
        entry_a = a[target]
        entry_b = b[target]
        throughput_a = entry_a["throughput"]
        throughput_b = entry_b["throughput"]
        power_a = entry_a["power"]
        power_b = entry_b["power"]
        clean = entry_a["lock_held"] and entry_a["bench_ok"] and entry_b["lock_held"] and entry_b["bench_ok"]
        point = {
            "target": target,
            "throughput_a": throughput_a,
            "throughput_b": throughput_b,
            "delta_pct": 100.0 * (throughput_b / throughput_a - 1.0),
            "power_a": power_a,
            "power_b": power_b,
            "eff_a": throughput_a / power_a,
            "eff_b": throughput_b / power_b,
            "temp_a": entry_a["temp"],
            "temp_b": entry_b["temp"],
            "clean": clean,
        }
        points.append(point)
        if clean:
            clean_points.append(point)

    if clean_points:
        deltas = [p["delta_pct"] for p in clean_points]
        mean_delta_pct = sum(deltas) / len(deltas)
        min_delta_pct = min(deltas)
        max_delta_pct = max(deltas)
        argmax_eff_a = max(clean_points, key=lambda p: p["eff_a"])["target"]
        argmax_eff_b = max(clean_points, key=lambda p: p["eff_b"])["target"]
    else:
        mean_delta_pct = None
        min_delta_pct = None
        max_delta_pct = None
        argmax_eff_a = None
        argmax_eff_b = None

    return {
        "points": points,
        "only_a": only_a,
        "only_b": only_b,
        "mean_delta_pct": mean_delta_pct,
        "min_delta_pct": min_delta_pct,
        "max_delta_pct": max_delta_pct,
        "argmax_eff_a": argmax_eff_a,
        "argmax_eff_b": argmax_eff_b,
    }


def print_table(result):
    header = (
        "%10s %14s %14s %10s %10s %10s %14s %14s %10s %10s %6s"
        % (
            "target",
            "thr_a TF/s",
            "thr_b TF/s",
            "delta %",
            "pwr_a W",
            "pwr_b W",
            "eff_a GF/W",
            "eff_b GF/W",
            "tmp_a C",
            "tmp_b C",
            "clean",
        )
    )
    print(header)
    print("-" * len(header))
    for point in result["points"]:
        print(
            "%10d %14.3f %14.3f %+10.2f %10.1f %10.1f %14.2f %14.2f %10.1f %10.1f %6s"
            % (
                point["target"],
                point["throughput_a"] / 1e12,
                point["throughput_b"] / 1e12,
                point["delta_pct"],
                point["power_a"],
                point["power_b"],
                point["eff_a"] / 1e9,
                point["eff_b"] / 1e9,
                point["temp_a"],
                point["temp_b"],
                "yes" if point["clean"] else "no",
            )
        )

    shared_count = len(result["points"])
    clean_count = sum(1 for p in result["points"] if p["clean"])
    print("")
    print("%d targets were shared, %d were clean." % (shared_count, clean_count))
    if result["mean_delta_pct"] is None:
        print("There were no clean points, so no delta statistics are reported.")
    else:
        print(
            "Over clean points, the mean delta was %+.2f%%, the minimum was %+.2f%%, and the maximum was %+.2f%%."
            % (result["mean_delta_pct"], result["min_delta_pct"], result["max_delta_pct"])
        )
    if result["argmax_eff_a"] is None:
        print("There was no clean point, so no efficiency argmax is reported.")
    else:
        print(
            "Sweep A's efficiency argmax was at %d MHz, and sweep B's was at %d MHz."
            % (result["argmax_eff_a"], result["argmax_eff_b"])
        )
    print("")
    print(
        "A difference between two sweeps is not attributed to anything by this tool: "
        "sweep order, temperature, time of day and session all differ together."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare two frequency sweeps point by point.")
    parser.add_argument("sweep_a", help="path to the reference sweep CSV")
    parser.add_argument("sweep_b", help="path to the comparison sweep CSV")
    parser.add_argument("--json", action="store_true", help="print the comparison as JSON")
    args = parser.parse_args(argv)

    try:
        sweep_a = load_sweep(args.sweep_a)
        sweep_b = load_sweep(args.sweep_b)
    except ValueError as exc:
        print(str(exc))
        return 2

    result = compare(sweep_a, sweep_b)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_table(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
