"""Score the activity A/B test. Written and committed BEFORE collection, 2026-09-22.

The design and every threshold below are registered in docs/REGISTERED-PREDICTIONS.md section 5.
Changing a threshold after the data exists turns a registered test into a fitted one - if a rule
here turns out to be wrong, say so in the write-up and report BOTH the registered verdict and any
revised one, never only the revised one.

    python analysis/score_activity_ab.py C:\\headroom-bench\\results\\activity-ab-<stamp>

What it measures. Every scored run sweeps the same 13 targets. For each target the ENVELOPE is the
best throughput any scored run reached there. A point is DEGRADED if it falls MORE than
DEGRADE_PCT below that envelope. The 2026-09-22 losses were 8-11 pct; a quiet three-run set agreed
to better than 0.1 pct, so 2 pct sits far above the noise and far below the effect.

REVISED BEFORE COLLECTION, 2026-09-22, after an outside preflight review
(docs/gpt-findings/2026-09-22-activity-ab-preflight.md). No threshold changed. What changed:
  - "more than 2 pct" is tested without floating-point subtraction, so an exact 2 pct tie is NOT
    degraded (the first version counted it, and could print a false SUPPORTED)
  - no registered verdict is printed unless the collection is COMPLETE: two warm-ups, then twelve
    valid scored runs in the registered S A A S x 3 order (the first version printed one anyway)
  - an ACTIVE run is valid only if its generator log proves the activity ran across the sweep
  - every scored run must carry exactly the registered 13-point grid
  - descriptive blocks follow the recorded order, not the index after exclusions

What it cannot do. The active condition is a scripted PROXY for agent activity. A null result
weakens the activity hypothesis for that proxy only.
"""
import glob
import json
import math
import os
import sys

import pandas as pd

DEGRADE_PCT = 2.0          # registered
SUPPORT_MARGIN = 4         # registered: active must exceed silent by at least this many points
SUPPORT_MIN_ACTIVE_RUNS = 3  # registered: ...and the losses must appear in at least this many active runs
NULL_MARGIN = 1            # registered: active exceeding silent by at most this is "not supported"
SILENT_LOSSES_MEAN_OTHER_CAUSE = 3  # registered

REGISTERED_ORDER = ["warmup", "warmup"] + ["silent", "active", "active", "silent"] * 3
REGISTERED_POINTS = 13
MAX_ACTIVITY_GAP_S = 15.0  # the generator cycles every 5 s; three missed cycles is not "running"


def findSweepCsv(record, roots):
    recorded = record.get("sweep_csv")
    if recorded and os.path.isfile(recorded):
        return recorded
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", f"*_{record['label']}_sweep.csv"), recursive=True)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None   # ambiguous: refuse rather than guess
    return None


def activityProblems(record, sweep):
    """Why an ACTIVE run cannot count as active, or [] if its generator log proves it ran."""
    path = record.get("event_log")
    if not record.get("load_seen"):
        return ["the load never appeared, so the generator never started"]
    if not path or not os.path.exists(path):
        return ["no generator event log"]
    events = pd.read_csv(path)
    if "ok" not in events.columns:
        return ["event log has no ok column (pre-revision generator)"]
    problems = []
    if record.get("generator_killed"):
        problems.append("generator had to be killed")
    if (events.event == "generator_stop_stop_file").sum() != 1:
        problems.append("generator did not stop on its stop file")
    actions = events[events.event.isin(["pmon", "cpu_burst", "screen_capture"])]
    if (actions.ok != 1).any():
        problems.append(f"{int((actions.ok != 1).sum())} generator action(s) failed")
    pmon = events[events.event == "pmon"].start_unix.sort_values().tolist()
    first, last = float(sweep.window_start_unix.min()), float(sweep.window_end_unix.max())
    starts = events[events.event == "generator_start"].start_unix
    if starts.empty or float(starts.iloc[0]) > first:
        problems.append("generator started after the first measured window")
    if not pmon or pmon[-1] < last - MAX_ACTIVITY_GAP_S:
        problems.append("activity stopped before the last measured window ended")
    inside = [t for t in pmon if first - MAX_ACTIVITY_GAP_S <= t <= last + MAX_ACTIVITY_GAP_S]
    gaps = [b - a for a, b in zip(inside, inside[1:])]
    if gaps and max(gaps) > MAX_ACTIVITY_GAP_S:
        problems.append(f"a {max(gaps):.1f} s gap in activity during the sweep")
    return problems


def loadExperiment(experimentDir, extraRoots=()):
    """Returns (scored runs, problems). Any problem means NO registered verdict."""
    with open(os.path.join(experimentDir, "experiment.json"), encoding="utf-8-sig") as f:
        records = json.load(f)
    if isinstance(records, dict):
        records = [records]
    records = sorted(records, key=lambda r: r["order"])
    problems = []
    conditions = [r["condition"] for r in records]
    if conditions != REGISTERED_ORDER:
        problems.append(f"schedule is {conditions}, not the registered two warm-ups + S A A S x 3")
    roots = [os.path.dirname(os.path.abspath(experimentDir)), *extraRoots]
    runs, grids = [], []
    for r in records:
        if r["condition"] == "warmup":
            continue
        tag = r.get("tag", r["label"])
        if r.get("wrapper_exit") != 0:
            problems.append(f"{tag}: wrapper exit {r.get('wrapper_exit')}")
            continue
        path = findSweepCsv(r, roots)
        if path is None:
            problems.append(f"{tag}: sweep CSV missing or ambiguous")
            continue
        sweep = pd.read_csv(path, encoding="utf-8-sig")
        needed = {"target_frequency_mhz", "bench_throughput", "window_start_unix", "window_end_unix",
                  "temperature_avg_c"}
        if not needed <= set(sweep.columns):
            problems.append(f"{tag}: missing columns {sorted(needed - set(sweep.columns))}")
            continue
        targets = sweep.target_frequency_mhz.tolist()
        if len(targets) != REGISTERED_POINTS or len(set(targets)) != REGISTERED_POINTS:
            problems.append(f"{tag}: {len(targets)} points ({len(set(targets))} unique), not {REGISTERED_POINTS}")
            continue
        if not all(math.isfinite(v) and v > 0 for v in sweep.bench_throughput):
            problems.append(f"{tag}: non-finite or non-positive throughput")
            continue
        if r["condition"] == "active":
            why = activityProblems(r, sweep)
            if why:
                problems.append(f"{tag}: activity not proven - " + "; ".join(why))
                continue
        grids.append(tuple(sorted(targets)))
        runs.append({**r, "sweep": sweep, "path": path})
    if len(set(grids)) > 1:
        problems.append("scored runs do not share one grid")
    return runs, problems


def score(runs):
    table = pd.concat([run["sweep"][["target_frequency_mhz", "bench_throughput"]] for run in runs])
    envelope = table.groupby("target_frequency_mhz").bench_throughput.max()
    perRun = []
    for run in runs:
        sweep = run["sweep"]
        env = envelope.loc[sweep.target_frequency_mhz].values
        tp = sweep.bench_throughput.values
        # "more than DEGRADE_PCT below" without subtraction: an exact tie is NOT degraded.
        isDegraded = tp * 100 < env * (100 - DEGRADE_PCT)
        loss = 100 * (1 - tp / env)
        degraded = [(int(t), round(float(l), 2)) for t, l, d in zip(sweep.target_frequency_mhz, loss, isDegraded) if d]
        perRun.append({"order": run["order"], "tag": run["tag"], "condition": run["condition"],
                       "uptime": run.get("uptime_min_at_start"), "degraded": degraded,
                       "temp_range": (sweep.temperature_avg_c.min(), sweep.temperature_avg_c.max())})
    return perRun


def verdict(perRun):
    active = [r for r in perRun if r["condition"] == "active"]
    silent = [r for r in perRun if r["condition"] == "silent"]
    dA = sum(len(r["degraded"]) for r in active)
    dS = sum(len(r["degraded"]) for r in silent)
    activeRunsHit = sum(1 for r in active if r["degraded"])
    lines = [f"Degraded points (> {DEGRADE_PCT} pct below the per-target envelope): "
             f"ACTIVE {dA} across {len(active)} runs ({activeRunsHit} runs hit), SILENT {dS} across {len(silent)} runs."]
    if dA >= dS + SUPPORT_MARGIN and activeRunsHit >= SUPPORT_MIN_ACTIVE_RUNS:
        code = "SUPPORTED"
        lines.append("VERDICT: ACTIVITY SUPPORTED - the scripted activity produces isolated losses that "
                     "silence does not, on a warm card, with run order balanced.")
    elif dA <= dS + NULL_MARGIN:
        code = "NOT_SUPPORTED"
        lines.append("VERDICT: NOT SUPPORTED FOR THIS PROXY - the scripted activity does not add losses. "
                     "It does not rule out the parts of real agent activity the proxy does not imitate.")
    else:
        code = "INCONCLUSIVE"
        lines.append("VERDICT: INCONCLUSIVE - between the registered thresholds.")
    if dS >= SILENT_LOSSES_MEAN_OTHER_CAUSE:
        lines.append(f"ALSO: {dS} losses in SILENT runs on a warm card - something other than this activity "
                     "produces them.")
    if dA + dS == 0:
        lines.append("ALSO: no losses at all. The 2026-09-22 losses happened on a cold card and/or under real "
                     "agent activity; this run removed the first and imitated the second, so they are still "
                     "not separated.")
    return code, lines


def evaluate(experimentDir, extraRoots=()):
    """Returns (code, lines). code is SUPPORTED / NOT_SUPPORTED / INCONCLUSIVE, or INCOMPLETE."""
    runs, problems = loadExperiment(experimentDir, extraRoots)
    if problems:
        return "INCOMPLETE", (["INCOMPLETE - NO REGISTERED VERDICT. The registration requires two warm-ups "
                               "and twelve valid scored runs in S A A S x 3 order. Problems:"]
                              + [f"  - {p}" for p in problems])
    perRun = score(runs)
    lines = ["Per run, in collection order:"]
    for r in perRun:
        lines.append(f"  {r['order']:>2} {r['tag']:<12} {r['condition']:<7} uptime {r['uptime']} min, "
                     f"temp {r['temp_range'][0]:.1f}-{r['temp_range'][1]:.1f} C, degraded {r['degraded']}")
    blocks = {}
    for r in perRun:   # by RECORDED order: warm-ups are orders 0 and 1
        block = (r["order"] - 2) // 4 + 1
        blocks[block] = blocks.get(block, 0) + len(r["degraded"])
    lines.append(f"Degraded points by block of four (a time trend shows here, not in the verdict): {blocks}")
    code, verdictLines = verdict(perRun)
    lines += verdictLines
    lines.append("This is one chip, one session, and a scripted proxy for agent activity.")
    return code, lines


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python analysis/score_activity_ab.py <experiment directory> [extra search root ...]")
    code, lines = evaluate(sys.argv[1], sys.argv[2:])
    for line in lines:
        print(line)
    return 2 if code == "INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
