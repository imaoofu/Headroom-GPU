"""
Locate the efficiency optimum in a measured frequency sweep, and quantify the headroom gap.

WHY THIS EXISTS
    This is the consumer-hardware counterpart of characterize.py, which measures the same gap
    on the published V100 dataset. Given sweep CSVs from Invoke-FrequencySweep.ps1, it answers
    the project's central question directly: how much efficiency does running at the device's
    own sustained maximum give up against running at its optimum, and where is that optimum.

A LESSON ABOUT GRID RESOLUTION, WHICH IS WHY THIS IS A SCRIPT AND NOT A ONE-OFF
    An earlier 3-point sweep (1237 / 2167 / 3090 MHz) found efficiency highest at its LOWEST
    point and concluded the sweep floor was too high to contain the optimum. That conclusion
    was wrong. A 13-point sweep over a wider range puts the optimum at 1552 MHz - comfortably
    INSIDE the original 40%-floor range, simply never sampled by three points.

    The mistake was over-applying this project's own criterion from compare_consumer.py, where
    "the optimum lands on the lowest frequency tested" is the signature of a range that stops
    short. That inference is only valid for a DENSE sweep. On a sparse one, an optimum at the
    lowest sampled point is equally consistent with the optimum sitting between the first and
    second points - which is exactly what happened.

    So: the floor was never the problem, the resolution was. Lowering the floor did earn its
    keep for a different reason - efficiency falls from 1552 MHz down to 464 MHz, which proves
    the optimum is interior rather than an artefact of where the sweep happened to stop.

USAGE
    python analysis/analyze_sweep.py
    python analysis/analyze_sweep.py --pattern "*floor15*"
"""

import argparse
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SWEEPS = REPO_ROOT / "data" / "frequency-sweeps"

# Rows whose clock lock was not applied at all cannot be attributed to a frequency, so they are
# excluded rather than silently averaged in. Undershoot is kept: the card genuinely ran there.
EXCLUDE_DIRECTIONS = {"above"}


def loadSweep(path):
    rows = []
    with open(path, encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            if not raw.get("bench_throughput") or raw.get("bench_ok") not in ("True", "true", None):
                continue
            if raw.get("lock_miss_direction") in EXCLUDE_DIRECTIONS:
                continue
            rows.append({
                # The COMMANDED frequency, kept alongside the achieved one so callers can align
                # rows across configurations. Achieved clocks differ by a few MHz between runs at
                # the same target, so matched-frequency comparisons have to key on the target.
                # audit_claims.py depends on this.
                # None when the column is absent, which is true of some early smoke-test CSVs
                # and of this module's own minimal test fixtures. Consumers that need it must
                # check; audit_claims.py raises rather than matching a None key.
                "target": (int(float(raw["target_frequency_mhz"]))
                           if raw.get("target_frequency_mhz") else None),
                "mhz": float(raw["achieved_frequency_avg"]),
                "throughput": float(raw["bench_throughput"]),
                "power": float(raw["power_avg_w"]),
                "unit": raw.get("bench_throughput_unit", ""),
                "windowed": raw.get("power_window_applied") in ("True", "true"),
                # A DIAGNOSTIC HINT, NOT A MEASUREMENT. Section 5.4.3 establishes that
                # utilization.gpu averaged over ~25 samples decouples from throughput: two
                # passes at 1890 MHz read 99.0% and 92.7% and both delivered 342.3 GB/s. Use it
                # to describe the telemetry, never to argue about work done. None when absent.
                "utilisation": (float(raw["utilization_avg_pct"])
                                if raw.get("utilization_avg_pct") else None),
            })
    for row in rows:
        row["efficiency"] = row["throughput"] / row["power"]
    return sorted(rows, key=lambda r: r["mhz"])


def efficiencyPeak(rows):
    """Select the same maximum-efficiency row used by sweep descriptions."""
    return max(rows, key=lambda r: r["efficiency"])


def describe(name, rows):
    if len(rows) < 3:
        print(f"{name}: only {len(rows)} usable points - skipping.\n")
        return None

    peak = efficiencyPeak(rows)
    fastest = max(rows, key=lambda r: r["mhz"])
    scale = 1e12 if "FLOP" in rows[0]["unit"] else 1e9
    label = "TFLOP/s" if scale == 1e12 else "GB/s"
    best = peak["efficiency"]

    print(f"=== {name} ===")
    for row in rows:
        marker = "  <-- OPTIMUM" if row is peak else ""
        bar = "#" * int(round(40 * row["efficiency"] / best))
        print(f"  {row['mhz']:7.1f} MHz  {row['throughput']/scale:7.2f} {label:>8}  "
              f"{row['power']:6.2f} W  {bar}{marker}")

    # The gap is stated against the device's own SUSTAINED maximum, not its nameplate clock.
    # Sustained max is workload-dependent (the hungrier workload holds a lower clock), so a
    # nameplate denominator would compare against a frequency the card never actually runs.
    print(f"  optimum          : {peak['mhz']:.1f} MHz "
          f"({100*peak['mhz']/fastest['mhz']:.0f}% of sustained max {fastest['mhz']:.1f} MHz)")
    print(f"  efficiency gain  : {100*(peak['efficiency']/fastest['efficiency'] - 1):.1f}%")
    print(f"  performance cost : {100*(1 - peak['throughput']/fastest['throughput']):.1f}%")
    print(f"  power saved      : {100*(1 - peak['power']/fastest['power']):.1f}%")
    if not all(r["windowed"] for r in rows):
        print("  WARNING: some points lack power windowing - their power is diluted by CUDA init.")
    print()
    return {"name": name, "peak": peak, "fastest": fastest}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--pattern", default="*floor15*_sweep.csv",
                        help="Glob of sweep CSVs under data/frequency-sweeps/.")
    args = parser.parse_args()

    paths = sorted(SWEEPS.glob(args.pattern))
    if not paths:
        print(f"No sweeps matching {args.pattern} under {SWEEPS}")
        return 1

    summaries = []
    for path in paths:
        name = path.stem.replace("_sweep", "")
        summary = describe(name, loadSweep(path))
        if summary:
            summaries.append(summary)

    if len(summaries) == 2:
        first, second = summaries
        print("=== workload comparison ===")
        print(f"  optima: {first['peak']['mhz']:.1f} MHz vs {second['peak']['mhz']:.1f} MHz")
        if abs(first["peak"]["mhz"] - second["peak"]["mhz"]) < 1.0:
            print("  Identical to within the grid step. At this resolution the two optima are")
            print("  INDISTINGUISHABLE - which is not the same as equal. Separating them needs a")
            print("  finer sweep around the peak, not a wider one.")
        # The compute/memory distinction shows up in what the optimum COSTS, not where it sits.
        for summary in summaries:
            cost = 100 * (1 - summary["peak"]["throughput"] / summary["fastest"]["throughput"])
            print(f"  {summary['name']}: optimum costs {cost:.1f}% performance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
