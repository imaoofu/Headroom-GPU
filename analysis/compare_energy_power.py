"""Compare the sampled nvidia-smi power against NVML's integrated energy counter, per sweep point.

Usage: python analysis/compare_energy_power.py SWEEP_CSV_OR_DIRECTORY [...]

Every power figure in this project is nvidia-smi's power reading sampled at 2 Hz and averaged over
the benchmark's timed window (power_avg_w). That reading is the card's own smoothed estimate (Yang
et al. 2024). From sweep schema 0.3.4 the benchmark also reads NVML's cumulative energy counter at
the two edges of its timed region, and energy over that window is an independent average power
(energy_avg_power_w). This prints, for every sweep that carries both:

- the per-point difference, energy power against sampled power, in percent;
- each sweep's efficiency optimum on the TARGET grid (analyze_sweep.efficiencyPeak) computed with
  each power figure, and whether the two agree.

It reads CSVs and writes nothing. Points without both figures, or outside the timed window, are
skipped and counted, as is any point whose throughput or either power is not finite and positive.
The counter ticks about every 100 ms on the RTX 5060 Ti. If each edge's reading is up to one tick
stale and the power is constant, the energy figure over T seconds is off by at most 0.1/T, in either
direction; that conditional bound is printed. Varying power, or other counter behaviour, is not
bounded by it (GPT Job 57, F4: the earlier "0.2/T of quantisation" overstated what a tick can do).

This is a DESCRIPTIVE comparison. It does not enforce section 17's scoreability rule (at least 11 of
12 sweeps, each with at least 12 of 13 points) or print its verdicts; Job 57, F6.
"""
import math
import argparse
import csv
import statistics
import sys
from pathlib import Path

from analyze_sweep import efficiencyPeak

COUNTER_TICK_S = 0.1


def readPoints(path):
    """Rows carrying both power figures, each with its target, throughput and both powers."""
    points, skipped = [], 0
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            try:
                ok = raw.get("bench_ok") in ("True", "true")
                windowed = raw.get("power_window_applied") in ("True", "true")
                energyPower = float(raw.get("energy_avg_power_w") or "nan")
                window = float(raw.get("energy_window_seconds") or "nan")
                point = {"target": int(float(raw["target_frequency_mhz"])),
                         "throughput": float(raw["bench_throughput"]),
                         "sampled": float(raw["power_avg_w"]),
                         "energy": energyPower, "window": window}
            except (KeyError, ValueError, TypeError):
                skipped += 1
                continue
            values = (point["throughput"], point["sampled"], energyPower, window)
            if not (ok and windowed) or not all(math.isfinite(v) and v > 0 for v in values):
                skipped += 1
                continue
            points.append(point)
    return points, skipped


def optimum(points, key):
    rows = [{"target": p["target"], "efficiency": p["throughput"] / p[key]} for p in points]
    return efficiencyPeak(rows)["target"]


def compare(paths):
    sweeps = []
    for path in paths:
        points, skipped = readPoints(path)
        if not points:
            sweeps.append({"path": path, "points": [], "skipped": skipped})
            continue
        diffs = [100 * (p["energy"] / p["sampled"] - 1) for p in points]
        sweeps.append({
            "path": path, "points": points, "skipped": skipped, "diffs_pct": diffs,
            "optimum_sampled": optimum(points, "sampled"), "optimum_energy": optimum(points, "energy"),
            "max_tick_bound_pct": max(100 * COUNTER_TICK_S / p["window"] for p in points),
        })
    return sweeps


def expand(arguments):
    paths = []
    for argument in arguments:
        path = Path(argument)
        paths.extend(sorted(path.rglob("*_sweep.csv")) if path.is_dir() else [path])
    return paths


def report(sweeps):
    usable = [s for s in sweeps if s["points"]]
    print("Energy counter against sampled power | energy_avg_power_w / power_avg_w - 1, per point")
    for s in sweeps:
        name = Path(s["path"]).name
        if not s["points"]:
            print(f"{name}: no point carries both figures ({s['skipped']} skipped); schema 0.3.4 or later needed.")
            continue
        d = s["diffs_pct"]
        agree = "same" if s["optimum_sampled"] == s["optimum_energy"] else "DIFFERENT"
        print(f"{name}: {len(d)} points, median {statistics.median(d):+.2f}%, range {min(d):+.2f} to "
              f"{max(d):+.2f}%; optimum {s['optimum_sampled']} MHz sampled, {s['optimum_energy']} MHz "
              f"by energy ({agree}); one-tick bound at constant power {s['max_tick_bound_pct']:.2f}%"
              + (f"; {s['skipped']} point(s) skipped" if s["skipped"] else ""))
    if not usable:
        return
    every = [x for s in usable for x in s["diffs_pct"]]
    absolute = [abs(x) for x in every]
    same = sum(1 for s in usable if s["optimum_sampled"] == s["optimum_energy"])
    print(f"All: {len(every)} points in {len(usable)} sweep(s); median difference {statistics.median(every):+.2f}%, "
          f"median absolute {statistics.median(absolute):.2f}%, worst {max(absolute):.2f}%.")
    print(f"Efficiency optimum unchanged by the power source in {same} of {len(usable)} sweep(s).")
    print(f"Median optimum across these sweeps: {statistics.median(s['optimum_sampled'] for s in usable):g} MHz "
          f"from sampled power, {statistics.median(s['optimum_energy'] for s in usable):g} MHz from energy.")
    print("Both figures are the card's own telemetry; agreement between them is not a shunt measurement.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    paths = expand(args.paths)
    if not paths:
        print("No sweep CSVs found.", file=sys.stderr)
        return 2
    report(compare(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
