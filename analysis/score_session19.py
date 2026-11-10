"""Score REGISTERED-PREDICTIONS section 19: the key RTX 5060 Ti optima with the energy counter.

Usage: python analysis/score_session19.py SESSION_DIRECTORY

Written 2026-10-06 with section 19's registration and before any of its data existed. One session,
stock -> P5 -> P4 -> rung B -> rung C -> stock, twelve workloads each, collected by
tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s19, whose rerun15-inputs.json maps each role
("{leg}-{workload}") to its sweep. A role re-run after a desktop-load exit holds a list whose last
entry is the accepted sweep; a role in "notScoreable" makes its suite NOT SCOREABLE.

Every sweep is schema 0.3.4 or later and carries two power figures per point: power_avg_w (the
2 Hz `nvidia-smi` sample, the figure every earlier result used) and energy_avg_power_w (NVML's
integrated energy counter over the same window). Section 17 found them a median 7.83% apart.
Per workload the optimum is the TARGET with the highest throughput per watt, computed with each
figure; points that are not bench_ok are skipped, as analyze_sweep does.

- gate (section 15's R3 rule): the two stock suites have the same ENERGY median, and every
  workload's median absolute matched-target throughput change between them is at most 1.5%;
  otherwise every prediction is NOT SCOREABLE;
- predictions, ENERGY figure: stock 1545, P5 1545, P4 2010, rung B 1702, rung C 1852 MHz;
- reported, always: the same medians from the sampled figure, and per leg the workloads whose
  optimum differs between the two figures.
"""
import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

from score_control10 import STOCK_RETURN_TOLERANCE_PCT, WORKLOADS, exceeds_tolerance, stock_return

LEGS = ("stock-open", "p5", "p4", "rungB", "rungC", "stock-close")
PREDICTED = {"stock-open": 1545, "p5": 1545, "p4": 2010, "rungB": 1702, "rungC": 1852, "stock-close": 1545}
POWER = {"energy": "energy_avg_power_w", "sampled": "power_avg_w"}
GRID = (1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090)  # registered


def load_manifest(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "rerun15-inputs.json").read_text(encoding="utf-8-sig"))
    if "section 19" not in manifest.get("section", "") and "sections 18 and 19" not in manifest.get("section", ""):
        raise ValueError(f"{directory}: rerun15-inputs.json is not a section 19 session")
    return directory, manifest


def sweep_path(directory, manifest, role):
    desc = manifest["sweeps"].get(role)
    if desc is None:
        raise ValueError(f"role {role} is missing")
    if isinstance(desc, list):
        desc = desc[-1]
    path = Path(desc["sweep"])
    return path if path.is_absolute() else directory / path


def read_sweep(path):
    """{target: {throughput, energy, sampled}} for every bench_ok point carrying both power figures."""
    rows = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            # Eligibility as analyze_sweep: a successful benchmark, and not a lock that overshot.
            if raw.get("bench_ok") not in ("True", "true") or raw.get("lock_miss_direction") == "above":
                continue
            try:
                targetValue = float(raw["target_frequency_mhz"])
                point = {"throughput": float(raw["bench_throughput"]),
                         "sampled": float(raw["power_avg_w"]),
                         "energy": float(raw["energy_avg_power_w"])}
            except (KeyError, ValueError, TypeError):
                raise ValueError(f"{path}: a point lacks a power figure; schema 0.3.4 or later is required")
            # GPT Job 61: int() truncated 1237.9 to 1237, slipping past the off-grid refusal.
            if not (math.isfinite(targetValue) and targetValue.is_integer()):
                raise ValueError(f"{path}: target {raw['target_frequency_mhz']} is not a whole MHz")
            target = int(targetValue)
            # Hardened before any section 19 data was read, after GPT Job 56 found these gaps in the
            # section 16 scorer: a repeated target, a non-finite value, a grid off the registration.
            if target in rows:
                raise ValueError(f"{path}: target {target} appears twice")
            if not all(math.isfinite(v) and v > 0 for v in point.values()):
                raise ValueError(f"{path}: a non-finite or non-positive value at {target} MHz")
            rows[target] = point
    if tuple(sorted(rows)) != GRID:
        raise ValueError(f"{path}: usable targets are not section 19's registered 13")
    return rows


def optimum(rows, figure):
    return max(rows, key=lambda t: rows[t]["throughput"] / rows[t][figure])


def score(directory):
    directory, manifest = load_manifest(directory)
    lost = set(manifest.get("notScoreable") or [])
    lost_legs = {leg for leg in LEGS if any(f"{leg}-{w}" in lost for w in WORKLOADS)}
    sweeps = {}
    for leg in LEGS:
        try:
            sweeps[leg] = {w: read_sweep(sweep_path(directory, manifest, f"{leg}-{w}")) for w in WORKLOADS}
        except ValueError:
            # An already NOT SCOREABLE treatment suite may be incomplete; it must not stop the rest
            # being scored. A stock suite, or a suite not marked lost, still fails loudly.
            if leg in lost_legs and leg not in ("stock-open", "stock-close"):
                continue
            raise
    read = [leg for leg in LEGS if leg in sweeps]
    optima = {fig: {leg: {w: optimum(sweeps[leg][w], fig) for w in WORKLOADS} for leg in read} for fig in POWER}
    medians = {fig: {leg: (statistics.median(optima[fig][leg].values()) if leg in read else float("nan"))
                     for leg in LEGS} for fig in POWER}

    targets = sorted(set.intersection(*(set(sweeps[leg][w]) for leg in ("stock-open", "stock-close")
                                        for w in WORKLOADS)))
    drift = stock_return(_as_suite(sweeps["stock-open"]), _as_suite(sweeps["stock-close"]), targets)

    reasons, bracket = [], []
    if medians["energy"]["stock-open"] != medians["energy"]["stock-close"]:
        bracket.append(f"the stock energy medians differ: {medians['energy']['stock-open']:g} and "
                       f"{medians['energy']['stock-close']:g}")
    over = sorted(w for w, v in drift.items() if exceeds_tolerance(v))
    if over:
        bracket.append(f"stock return above {STOCK_RETURN_TOLERANCE_PCT}%: {', '.join(over)}")
    reasons = bracket + [f"{leg} has a role NOT SCOREABLE after a second desktop load" for leg in sorted(lost_legs)]
    # A stock-bracket failure voids every prediction; a lost treatment suite voids only its own.
    bracket_failed = bool(bracket) or bool(lost_legs & {"stock-open", "stock-close"})

    verdicts = {}
    for leg in LEGS:
        if bracket_failed or leg in lost_legs:
            verdicts[leg] = "NOT_SCOREABLE"
        else:
            verdicts[leg] = "HOLDS" if medians["energy"][leg] == PREDICTED[leg] else "FAILS"
    differ = {leg: sorted(w for w in WORKLOADS if optima["energy"][leg][w] != optima["sampled"][leg][w]) for leg in read}
    return {"optima": optima, "medians": medians, "drift_pct": drift, "not_scoreable_reasons": reasons,
            "verdicts": verdicts, "figures_differ": differ, "targets": targets}


def _as_suite(sweeps_by_workload):
    """score_control10.stock_return's input shape: {workload: {'rows': {target: throughput}}}."""
    return {w: {"rows": {t: {"throughput": p["throughput"]} for t, p in rows.items()}}
            for w, rows in sweeps_by_workload.items()}


def report(r):
    print("Section 19 scorer | RTX 5060 Ti | optimum = target with the highest throughput per watt, by power figure")
    for leg in LEGS:
        if leg not in r["figures_differ"]:
            print(f"{leg}: not read; the suite is NOT SCOREABLE and could not be loaded.")
            continue
        print(f"{leg}: energy median {r['medians']['energy'][leg]:g} MHz (predicted {PREDICTED[leg]}): "
              f"{r['verdicts'][leg]}; sampled median {r['medians']['sampled'][leg]:g} MHz; optimum differs "
              f"between the two figures at {len(r['figures_differ'][leg])} of 12"
              + (f" ({', '.join(r['figures_differ'][leg])})" if r["figures_differ"][leg] else ""))
    print(f"Stock return: worst workload {max(r['drift_pct'].values()):.3f}% (limit {STOCK_RETURN_TOLERANCE_PCT}%).")
    for reason in r["not_scoreable_reasons"]:
        print(f"Not scoreable: {reason}.")
    print("Both power figures are the card's own telemetry, not a shunt. N=1 chip, one session, one suite per arm.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.directory)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Section 19 cannot be scored: {exc}", file=sys.stderr)
        return 2
    report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
