"""Score REGISTERED-PREDICTIONS section 18: which NVML power reading the energy counter agrees with.

Usage: python analysis/score_power_fields.py SESSION_DIRECTORY

Written 2026-10-06 with section 18's registration and before any of its data existed. The session
(tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s19) logs NVML at 20 Hz throughout
(tools/power-probe/sample_power.py, `power-samples.csv`, named in rerun15-inputs.json as
"powerSamples"). For every point of every accepted sweep, over the benchmark's timed window
(window_start_unix to window_end_unix, the same wall clock the logger uses):

- usage20: mean of nvmlDeviceGetPowerUsage at 20 Hz, the value `nvidia-smi power.draw` reports;
- average20 and instant20: means of NVML fields 185 and 186 at 20 Hz;
- sampled2: the sweep's own power_avg_w, `nvidia-smi` sampled at 2 Hz;
- energy: the sweep's own energy_avg_power_w, NVML's energy counter read at the window's edges.

Registered:
- H1: the median absolute per-point difference between instant20 and energy is at most 2%;
- H2: the median absolute per-point difference between usage20 and sampled2 is at most 1%.
Reported, always: the median signed difference of every figure against energy, per configuration.
A point with fewer than 40 logger rows in its window (2 s at 20 Hz) is skipped and counted.
"""
import argparse
import bisect
import csv
import gzip
import json
import statistics
import sys
from pathlib import Path

MIN_ROWS = 40
H1_LIMIT_PCT = 2.0
H2_LIMIT_PCT = 1.0


def load_samples(path):
    times, rows = [], []
    # The committed copy is gzipped (445k rows); the bench copy is plain CSV.
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            try:
                row = {k: float(raw[k]) for k in ("unix", "usage_w", "average_w", "instant_w")}
            except (KeyError, ValueError, TypeError):
                continue
            times.append(row["unix"])
            rows.append(row)
    return times, rows


def window_means(times, rows, start, end):
    lo, hi = bisect.bisect_left(times, start), bisect.bisect_right(times, end)
    chunk = rows[lo:hi]
    if len(chunk) < MIN_ROWS:
        return None
    return {k: statistics.fmean(r[k] for r in chunk) for k in ("usage_w", "average_w", "instant_w")}


def accepted_sweeps(directory, manifest):
    for role, desc in manifest["sweeps"].items():
        if isinstance(desc, list):
            desc = desc[-1]
        path = Path(desc["sweep"])
        yield role, (path if path.is_absolute() else directory / path)


def score(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "rerun15-inputs.json").read_text(encoding="utf-8-sig"))
    if "section 18" not in manifest.get("section", "") and "sections 18 and 19" not in manifest.get("section", ""):
        raise ValueError(f"{directory}: rerun15-inputs.json is not a section 18 session")
    samples = Path(manifest.get("powerSamples") or directory / "power-samples.csv")
    if not samples.is_absolute():
        samples = directory / samples
    times, rows = load_samples(samples)
    if not rows:
        raise ValueError(f"{samples}: no logger rows")
    points, skipped = [], 0
    for role, path in accepted_sweeps(directory, manifest):
        leg = role.rsplit("-", 1)[0]
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                try:
                    start, end = float(raw["window_start_unix"]), float(raw["window_end_unix"])
                    sampled2, energy = float(raw["power_avg_w"]), float(raw["energy_avg_power_w"])
                except (KeyError, ValueError, TypeError):
                    skipped += 1
                    continue
                if raw.get("bench_ok") not in ("True", "true"):
                    skipped += 1
                    continue
                means = window_means(times, rows, start, end)
                if means is None:
                    skipped += 1
                    continue
                points.append({"leg": leg, "role": role, "sampled2": sampled2, "energy": energy,
                               "usage20": means["usage_w"], "average20": means["average_w"],
                               "instant20": means["instant_w"]})
    if not points:
        raise ValueError("no point could be joined to the logger")

    def pct(a, b):
        return 100.0 * (a / b - 1.0)

    h1 = statistics.median(abs(pct(p["instant20"], p["energy"])) for p in points)
    h2 = statistics.median(abs(pct(p["usage20"], p["sampled2"])) for p in points)
    figures = ("sampled2", "usage20", "average20", "instant20")
    against_energy = {f: statistics.median(pct(p[f], p["energy"]) for p in points) for f in figures}
    legs = sorted({p["leg"] for p in points})
    by_leg = {leg: {f: statistics.median(pct(p[f], p["energy"]) for p in points if p["leg"] == leg) for f in figures}
              for leg in legs}
    return {"points": len(points), "skipped": skipped, "h1_median_abs_pct": h1, "h2_median_abs_pct": h2,
            "h1": "HOLDS" if h1 <= H1_LIMIT_PCT else "FAILS", "h2": "HOLDS" if h2 <= H2_LIMIT_PCT else "FAILS",
            "against_energy": against_energy, "by_leg": by_leg}


def report(r):
    print("Section 18 scorer | NVML power readings against the energy counter, per timed window")
    print(f"{r['points']} points joined, {r['skipped']} skipped.")
    print(f"H1, instant at 20 Hz against the energy counter: median absolute {r['h1_median_abs_pct']:.2f}% "
          f"(limit {H1_LIMIT_PCT}%): {r['h1']}.")
    print(f"H2, power.draw at 20 Hz against the sweep's 2 Hz sample: median absolute {r['h2_median_abs_pct']:.2f}% "
          f"(limit {H2_LIMIT_PCT}%): {r['h2']}.")
    print("Median signed difference against the energy counter: "
          + ", ".join(f"{k} {v:+.2f}%" for k, v in r["against_energy"].items()) + ".")
    for leg, row in r["by_leg"].items():
        print(f"  {leg}: " + ", ".join(f"{k} {v:+.2f}%" for k, v in row.items()))
    print("Every figure here is the card's own telemetry; none is a shunt. N=1 chip, one session.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.directory)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Section 18 cannot be scored: {exc}", file=sys.stderr)
        return 2
    report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
