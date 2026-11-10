"""
Compare the 2026-08-16 consumer dataset against its 2026-08-22 repeat under the clean protocol.

WHY THIS EXISTS
    Section 5.4.4 reports that always-on capture software depresses measured throughput, worst at
    low and mid frequencies, and that it therefore tilts the efficiency curve rather than shifting
    it. Sections 5.4 and 5.4.1 were measured before that was known. This re-measures them with
    NVIDIA Instant Replay disabled and the machine otherwise quiet, and reports what moved.

    It is a script rather than a console session because the last time a comparison like this was
    done by hand, the result existed only in a chat transcript and had to be re-measured the next
    day. Anything that decides a number in the paper has to be re-runnable.

WHAT THIS COMPARISON IS, AND IS NOT
    It is NOT the controlled A/B of section 5.4.4. That one varied a single setting inside one
    session. These two datasets are SIX DAYS apart, so Instant Replay is one known difference
    among an unknown number of others - ambient temperature, driver state, background processes.
    The direction and rough size are trustworthy; attributing all of the change to any one cause
    is not supported, and this script deliberately does not do so.

USAGE
    python analysis/compare_protocol.py
"""

import csv
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SWEEPS = REPO_ROOT / "data" / "frequency-sweeps"

# Rows whose lock overshot cannot be attributed to a frequency, matching analyze_sweep.py.
EXCLUDE_DIRECTIONS = {"above"}

FLOOR15 = [
    ("gemm", "20260816-001048_5060ti-gemm-floor15_sweep.csv",
     "20260822-173451_5060ti-gemm-floor15-rerun_sweep.csv", 1e12, "TFLOP/s"),
    ("membw", "20260816-001734_5060ti-membw-floor15_sweep.csv",
     "20260822-174118_5060ti-membw-floor15-rerun_sweep.csv", 1e9, "GB/s"),
]

FINE = [
    ("gemm", ["20260816-124651_5060ti-gemm-fine-p1_sweep.csv",
              "20260816-131140_5060ti-gemm-fine-p2_sweep.csv"],
     ["20260822-174624_5060ti-gemm-fine-p1-rerun_sweep.csv",
      "20260822-180206_5060ti-gemm-fine-p2-rerun_sweep.csv"]),
    ("membw", ["20260816-125959_5060ti-membw-fine-p1_sweep.csv",
               "20260816-130549_5060ti-membw-fine-p2_sweep.csv"],
     ["20260822-175205_5060ti-membw-fine-p1-rerun_sweep.csv",
      "20260822-175706_5060ti-membw-fine-p2-rerun_sweep.csv"]),
]


def loadSweep(name):
    rows = {}
    with open(SWEEPS / name, encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            if not raw.get("bench_throughput"):
                continue
            if raw.get("lock_miss_direction") in EXCLUDE_DIRECTIONS:
                continue
            rows[int(float(raw["target_frequency_mhz"]))] = {
                "mhz": float(raw["achieved_frequency_avg"]),
                "throughput": float(raw["bench_throughput"]),
                "power": float(raw["power_avg_w"]),
            }
    return rows


def optimum(rows):
    """Optimum target, its achieved clock, and its efficiency gain over the top grid point.

    The gain is stated against the highest SWEPT point rather than a nameplate clock, matching
    analyze_sweep.py, so the denominator is a frequency the card actually ran.
    """
    efficiency = {t: r["throughput"] / r["power"] for t, r in rows.items()}
    best = max(efficiency, key=efficiency.get)
    top = max(rows)
    return best, rows[best]["mhz"], 100 * (efficiency[best] / efficiency[top] - 1)


def reportFloor15():
    print("=" * 78)
    print("SECTION 5.4 - full-range sweeps, 465-3090 MHz")
    print("=" * 78)
    for workload, oldName, newName, scale, unit in FLOOR15:
        old, new = loadSweep(oldName), loadSweep(newName)
        oBest, oMhz, oGain = optimum(old)
        nBest, nMhz, nGain = optimum(new)
        shared = sorted(set(old) & set(new))
        deltas = [100 * (new[t]["throughput"] / old[t]["throughput"] - 1) for t in shared]

        print(f"\n{workload}")
        print(f"  optimum, original : {oBest} MHz target ({oMhz:.1f} achieved), "
              f"gain over top {oGain:+.1f}%")
        print(f"  optimum, rerun    : {nBest} MHz target ({nMhz:.1f} achieved), "
              f"gain over top {nGain:+.1f}%")
        moved = "UNCHANGED" if oBest == nBest else f"MOVED {oBest} -> {nBest} MHz"
        print(f"  optimum location  : {moved}")
        print(f"  gain figure       : {nGain - oGain:+.1f} percentage points")
        print(f"  throughput change : min {min(deltas):+.1f}%  "
              f"mean {statistics.fmean(deltas):+.1f}%  max {max(deltas):+.1f}%")


def passSpread(names):
    a, b = loadSweep(names[0]), loadSweep(names[1])
    shared = sorted(set(a) & set(b))
    return [abs(100 * (b[t]["throughput"] / a[t]["throughput"] - 1)) for t in shared]


def reportFine():
    print()
    print("=" * 78)
    print("SECTION 5.4.1 - fine sweeps, 1200-1897 MHz, two passes each")
    print("=" * 78)
    print("\nPass-to-pass agreement is the reproducibility measure: same settings, same grid,")
    print("minutes apart. It is the closest thing this dataset has to an error bar.\n")
    print(f"  {'workload':<9}{'original mean':>15}{'original max':>14}"
          f"{'rerun mean':>13}{'rerun max':>12}")
    for workload, oldNames, newNames in FINE:
        o, n = passSpread(oldNames), passSpread(newNames)
        print(f"  {workload:<9}{statistics.fmean(o):>14.2f}%{max(o):>13.2f}%"
              f"{statistics.fmean(n):>12.2f}%{max(n):>11.2f}%")


def main():
    reportFloor15()
    reportFine()
    print()
    print("REMINDER: these datasets are six days apart. Instant Replay is one known difference")
    print("among an unknown number of others. Section 5.4.4's single-session A/B is the")
    print("controlled measurement; this is a re-measurement, not an attribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
