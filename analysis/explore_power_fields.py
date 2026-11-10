"""EXPLORATORY, not registered: why section 18's two predictions failed.

Usage: python analysis/explore_power_fields.py SESSION_DIRECTORY

Written 2026-10-07 AFTER section 18 was scored (both FAIL). Nothing here is a registered test and
no threshold is applied; it reports four descriptive figures from the same 20 Hz NVML log and the
same sweeps. The warm-up reading it probes was written into section 18's amendment before scoring
(REGISTERED-PREDICTIONS.md section 18); the comparisons themselves were chosen afterwards.

1. Whole session: the energy counter's total against power integrated over the log (trapezoid).
2. Per window: instant (field 186) over average (field 185) in the window's first second, and in
   the rest of the window. The average field is a trailing 1 s mean, so it lags at a load step.
3. Per workload: median instant20 over the sweep's 2 Hz sample.
4. Per configuration: median per-window energy-counter figure over the 2 Hz sample.
5. H2's signed direction, which the section 18 amendment requires to be reported when H2 fails:
   the median signed difference of power.draw at 20 Hz from the sweep's 2 Hz sample. The registered
   scorer reports only the absolute median, so it is computed here, with the scorer's 40-row minimum.
6. The per-workload signed differences the section 18 amendment requires beside both tests (added
   2026-10-08 after GPT Job 61 found them missing): each reading against the counter, and H2's
   power.draw-over-sample, median by workload, plus how many windows put the sampled figure below
   the counter.
"""
import argparse
import bisect
import csv
import gzip
import json
import statistics
from pathlib import Path


def load_log(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    rows = []
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            try:
                rows.append({k: float(raw[k]) for k in ("unix", "usage_w", "average_w", "instant_w", "energy_mj")})
            except (KeyError, ValueError, TypeError):
                continue
    rows.sort(key=lambda r: r["unix"])
    return rows


def integrate(rows, key):
    return sum((b["unix"] - a["unix"]) * (a[key] + b[key]) / 2 for a, b in zip(rows, rows[1:]))


def pct(a, b):
    return 100 * (a / b - 1)


def explore(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "rerun15-inputs.json").read_text(encoding="utf-8-sig"))
    log = directory / manifest.get("powerSamples", "power-samples.csv")
    rows = load_log(log)
    times = [r["unix"] for r in rows]
    counter_j = (rows[-1]["energy_mj"] - rows[0]["energy_mj"]) / 1000
    out = {"rows": len(rows), "hours": (times[-1] - times[0]) / 3600, "counter_kj": counter_j / 1000,
           "instant_kj": integrate(rows, "instant_w") / 1000, "average_kj": integrate(rows, "average_w") / 1000}
    first, rest, by_workload, by_leg, usage_vs_sampled = [], [], {}, {}, []
    per_workload, sampled_below = {}, 0
    for role, desc in manifest["sweeps"].items():
        if isinstance(desc, list):
            desc = desc[-1]
        leg, workload = role.rsplit("-", 1)
        with open(directory / desc["sweep"], encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                if raw.get("bench_ok") != "True":
                    continue
                start, end = float(raw["window_start_unix"]), float(raw["window_end_unix"])
                lo, mid, hi = (bisect.bisect_left(times, start), bisect.bisect_right(times, start + 1.0),
                               bisect.bisect_right(times, end))
                head, tail = rows[lo:mid], rows[mid:hi]
                if not head or not tail:
                    continue
                first.append(pct(statistics.fmean(r["instant_w"] for r in head), statistics.fmean(r["average_w"] for r in head)))
                rest.append(pct(statistics.fmean(r["instant_w"] for r in tail), statistics.fmean(r["average_w"] for r in tail)))
                sampled = float(raw["power_avg_w"])
                if hi - lo >= 40:
                    window = rows[lo:hi]
                    usage = statistics.fmean(r["usage_w"] for r in window)
                    counter = float(raw["energy_avg_power_w"])
                    usage_vs_sampled.append(pct(usage, sampled))
                    cell = per_workload.setdefault(workload, {"sampled": [], "usage": [], "instant": [], "h2": []})
                    cell["sampled"].append(pct(sampled, counter))
                    cell["usage"].append(pct(usage, counter))
                    cell["instant"].append(pct(statistics.fmean(r["instant_w"] for r in window), counter))
                    cell["h2"].append(pct(usage, sampled))
                    sampled_below += sampled < counter
                by_workload.setdefault(workload, []).append(pct(statistics.fmean(r["instant_w"] for r in rows[lo:hi]), sampled))
                by_leg.setdefault(leg, []).append(pct(float(raw["energy_avg_power_w"]), sampled))
    out.update(per_workload={w: {k: statistics.median(v) for k, v in c.items()} for w, c in per_workload.items()},
               sampled_below=sampled_below, h2_signed=statistics.median(usage_vs_sampled), h2_points=len(usage_vs_sampled), windows=len(first), first_second=statistics.median(first), rest=statistics.median(rest),
               by_workload={w: statistics.median(v) for w, v in by_workload.items()},
               by_leg={k: (statistics.median(v), min(v), max(v)) for k, v in by_leg.items()},
               all_legs=(statistics.median([x for v in by_leg.values() for x in v]),
                         min(x for v in by_leg.values() for x in v), max(x for v in by_leg.values() for x in v)))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("session")
    r = explore(parser.parse_args().session)
    print("EXPLORATORY, not registered: descriptive figures behind section 18's failures.")
    print(f"Whole session, {r['rows']} logger rows over {r['hours']:.2f} h: energy counter {r['counter_kj']:.1f} kJ; "
          f"integrated instant {r['instant_kj']:.1f} kJ ({pct(r['counter_kj'], r['instant_kj']):+.2f}%); "
          f"integrated average {r['average_kj']:.1f} kJ ({pct(r['counter_kj'], r['average_kj']):+.2f}%).")
    print(f"Instant over average, median of {r['windows']} windows: first second {r['first_second']:+.1f}%, "
          f"rest of window {r['rest']:+.1f}%.")
    print("Instant20 over the 2 Hz sample, median by workload: " + ", ".join(
        f"{w} {v:+.2f}%" for w, v in sorted(r["by_workload"].items(), key=lambda kv: kv[1])) + ".")
    print("Energy counter over the 2 Hz sample, per window, median by configuration: " + ", ".join(
        f"{k} {v[0]:+.2f}%" for k, v in sorted(r["by_leg"].items())) +
          f"; all {r['all_legs'][0]:+.2f}%, range {r['all_legs'][1]:+.1f} to {r['all_legs'][2]:+.1f}%.")
    print(f"H2's signed direction: power.draw at 20 Hz over the 2 Hz sample, median of {r['h2_points']} windows "
          f"{r['h2_signed']:+.2f}%.")
    print(f"Per window the sampled figure is below the counter in {r['sampled_below']} of {r['h2_points']}.")
    print("Per workload, median signed: sampled / power.draw / instant against the counter; H2 power.draw over sample:")
    for w, c in sorted(r["per_workload"].items()):
        print(f"  {w}: {c['sampled']:+.2f}% / {c['usage']:+.2f}% / {c['instant']:+.2f}%; H2 {c['h2']:+.2f}%")
    print("Every figure is the card's own telemetry, none a shunt. N=1 chip, one session.")


if __name__ == "__main__":
    main()
