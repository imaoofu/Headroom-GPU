"""Synthetic checks for compare_energy_power.py; no measurement files are read or written."""

import csv
import tempfile
from pathlib import Path

from compare_energy_power import compare, readPoints

FIELDS = ("target_frequency_mhz", "bench_throughput", "power_avg_w", "bench_ok",
          "power_window_applied", "energy_avg_power_w", "energy_window_seconds")


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def row(target, throughput, sampled, energy, window=15.0, ok="True", windowed="True"):
    return {"target_frequency_mhz": target, "bench_throughput": throughput, "power_avg_w": sampled,
            "bench_ok": ok, "power_window_applied": windowed,
            "energy_avg_power_w": energy, "energy_window_seconds": window}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Energy 2% above sampled everywhere: a uniform offset cannot move the optimum.
        uniform = root / "a_sweep.csv"
        write(uniform, [row(1545, 100, 50, 51), row(2010, 120, 80, 81.6), row(2475, 130, 110, 112.2)])
        [s] = compare([uniform])
        check(all(abs(d - 2.0) < 1e-9 for d in s["diffs_pct"]), "a uniform 2% offset reads as +2% at every point")
        check(s["optimum_sampled"] == s["optimum_energy"] == 1545, "a uniform offset leaves the optimum where it was")
        check(abs(s["max_tick_bound_pct"] - 100 * 0.1 / 15) < 1e-9, "the constant-power tick bound is one tick over the window")

        # Energy reads high only at the low clock: the optimum moves, and the tool says so.
        tilted = root / "b_sweep.csv"
        write(tilted, [row(1545, 100, 50, 60), row(2010, 120, 62, 62)])
        [s] = compare([tilted])
        check(s["optimum_sampled"] == 1545 and s["optimum_energy"] == 2010, "a frequency-dependent gap can move the optimum")

        # Pre-0.3.4 rows, failed points and unwindowed points are skipped and counted, never used.
        mixed = root / "c_sweep.csv"
        write(mixed, [row(1545, 100, 50, ""), row(2010, 120, 80, 81, ok="False"),
                      row(2475, 130, 110, 111, windowed="False"), row(3090, 140, 150, 151)])
        points, skipped = readPoints(mixed)
        check(len(points) == 1 and skipped == 3, "missing energy, failed and unwindowed points are skipped and counted")

        # GPT Job 57, F6: non-finite, zero or negative values are skipped, not carried into a NaN gap.
        bad = root / "e_sweep.csv"
        write(bad, [row(1545, 100, "nan", 51), row(1702, "nan", 50, 51), row(1852, 100, 50, -1),
                    row(2010, 100, 50, "inf"), row(2167, 100, 0, 51), row(2317, 100, 50, 51)])
        points, skipped = readPoints(bad)
        check(len(points) == 1 and skipped == 5, "non-finite, zero and negative values are skipped and counted")

        old = root / "d_sweep.csv"
        write(old, [row(1545, 100, 50, "", window="")])
        [s] = compare([old])
        check(s["points"] == [] and s["skipped"] == 1, "a sweep with no energy column reports nothing rather than zero")


if __name__ == "__main__":
    main()
