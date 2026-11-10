"""Score REGISTERED-PREDICTIONS §13 (Q1): does the load-floor rule hold for LLM decode?

Usage:
    python analysis/score_q1_llm.py [DIRECTORY]

DIRECTORY defaults to data/frequency-sweeps/5060ti-q1-llm-20260927. The criteria are §13 as
registered on 2026-09-27 before collection, with its amendment of 15:10 the same day (memory max
13801-14001 MHz, stock's two loaded states), also before collection. This script only reads.

Efficiency is tokens per joule of board energy: bench_throughput (token/s) over the windowed
power_avg_w. Every row is read, including targets the card cannot reach at stock (the top of the
grid undershoots on every stock sweep), because §13 scores targets, not achieved clocks.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DIR = REPO / "data" / "frequency-sweeps" / "5060ti-q1-llm-20260927"
TARGETS = (465, 682, 900, 1125, 1342, 1560, 1777, 1995, 2212, 2430, 2655, 2872, 3090)
RULE_PICK = 1560
MEMORY_OK = (13801, 14001)
POWER_LIMIT_W = 180.0


def read_sweep(directory, label):
    [csv_path] = sorted(directory.glob(f"*_{label}_sweep.csv"))
    meta = json.loads(csv_path.with_suffix(".json").read_text(encoding="utf-8-sig"))
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = {int(float(r["target_frequency_mhz"])): r for r in csv.DictReader(handle)}
    voltage = {}
    voltage_path = csv_path.with_name(csv_path.stem + "_voltage.csv")
    if voltage_path.is_file():
        with voltage_path.open(encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                # join_hwinfo_voltage.py writes target, voltage (median V), sampleCount.
                target, value = r.get("target"), r.get("voltage")
                if target and value:
                    voltage[int(float(target))] = float(value)
    return meta, rows, voltage


def validity(meta, rows):
    problems = []
    if sorted(rows) != list(TARGETS):
        problems.append(f"targets are {sorted(rows)}, not the registered 13")
    for target, r in rows.items():
        if r["bench_ok"] not in ("True", "true"):
            problems.append(f"{target}: bench not ok")
        if r["power_window_applied"] not in ("True", "true"):
            problems.append(f"{target}: power not windowed")
        memory_max = float(r["memory_clock_max_mhz"])
        if not MEMORY_OK[0] <= memory_max <= MEMORY_OK[1]:
            problems.append(f"{target}: memory max {memory_max:g} outside {MEMORY_OK[0]}-{MEMORY_OK[1]}")
    if float(meta["power_limit_enforced_w"]) != POWER_LIMIT_W:
        problems.append(f"enforced power limit {meta['power_limit_enforced_w']} W, not 180")
    return problems


def efficiency(rows):
    return {t: float(r["bench_throughput"]) / float(r["power_avg_w"]) for t, r in rows.items()}


def score(directory, workload):
    asc_meta, asc, asc_v = read_sweep(directory, f"5060ti-q1-{workload}-asc")
    desc_meta, desc, desc_v = read_sweep(directory, f"5060ti-q1-{workload}-desc")
    problems = [f"asc {p}" for p in validity(asc_meta, asc)] + [f"desc {p}" for p in validity(desc_meta, desc)]
    if asc_meta.get("sweep_order") != "ascending" or desc_meta.get("sweep_order") != "descending":
        problems.append("sweep directions are not ascending then descending")
    if asc_meta["driver_version"] != desc_meta["driver_version"]:
        problems.append("driver changed between directions")
    e_asc, e_desc = efficiency(asc), efficiency(desc)
    e = {t: (e_asc[t] + e_desc[t]) / 2 for t in TARGETS}
    d = max(abs(e_asc[t] - e_desc[t]) / e[t] for t in TARGETS)
    best = max(TARGETS, key=lambda t: e[t])
    max_e = e[best]
    if problems:
        verdict = "UNINTERPRETABLE"
    elif best == RULE_PICK or e[RULE_PICK] >= (1 - d) * max_e:
        verdict = "HOLDS"
    elif best < RULE_PICK:
        verdict = "FAILS BELOW"
    else:
        verdict = "FAILS ABOVE"
    return {"workload": workload, "problems": problems, "e_asc": e_asc, "e_desc": e_desc, "e": e,
            "d": d, "best": best, "max_e": max_e, "verdict": verdict,
            "throughput": {t: (float(asc[t]["bench_throughput"]) + float(desc[t]["bench_throughput"])) / 2
                           for t in TARGETS},
            "achieved": {t: (float(asc[t]["achieved_frequency_avg"]), float(desc[t]["achieved_frequency_avg"]))
                         for t in TARGETS},
            "power": {t: (float(asc[t]["power_avg_w"]) + float(desc[t]["power_avg_w"])) / 2 for t in TARGETS},
            "voltage": {t: (asc_v.get(t), desc_v.get(t)) for t in TARGETS},
            "driver": asc_meta["driver_version"]}


def report(result):
    name = result["workload"]
    print(f"\n{name} | driver {result['driver']} | efficiency = token/s over windowed board W")
    print(" target  achieved asc/desc   tok/s    W      tok/J asc  tok/J desc  mean   rel  V asc/desc")
    for t in TARGETS:
        va, vd = result["voltage"][t]
        volts = f"{va:.3f}/{vd:.3f}" if va is not None and vd is not None else "n/a"
        mark = " <- rule" if t == RULE_PICK else ""
        print(f" {t:6d}  {result['achieved'][t][0]:7.1f}/{result['achieved'][t][1]:7.1f}  "
              f"{result['throughput'][t]:8.2f}  {result['power'][t]:6.2f}  {result['e_asc'][t]:9.4f}  "
              f"{result['e_desc'][t]:10.4f}  {result['e'][t]:6.4f}  {100 * result['e'][t] / result['max_e']:5.1f}%  "
              f"{volts}{mark}")
    print(f"d (session repeat noise) = {100 * result['d']:.2f}%")
    print(f"argmax E = {result['best']} MHz; E(1560) is {100 * result['e'][RULE_PICK] / result['max_e']:.2f}% of it "
          f"(threshold {100 * (1 - result['d']):.2f}%).")
    for p in result["problems"]:
        print(f"NOT INTERPRETABLE: {p}")
    print(f"Section 13 {'PRIMARY' if name == 'decode' else 'SECONDARY'} ({name}): {result['verdict']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", nargs="?", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    results = [score(args.directory, w) for w in ("decode", "prefill")]
    for r in results:
        report(r)
    print("\nOne chip, one session, one 8B Q4_K_M model at batch 1; board energy only; a ~218 MHz grid.")
    return 0 if all(r["verdict"] != "UNINTERPRETABLE" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
