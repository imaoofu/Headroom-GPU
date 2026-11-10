"""Score REGISTERED-PREDICTIONS section 10: the 5060 Ti negative control, P5 -> P2 -> P5.

Usage: python analysis/score_control10.py PATH_TO_RESULTS

Registered 2026-09-25 (1c4e10d), witness amended before collection (a7bcd44). Written while the
queue was collecting and before any of its data was read; its tests ran after the queue finished,
so the load of a test run could not sit beside a sweep.

The directory holds 36 sweeps labelled 5060ti-ctrl10-{p5a,p2,p5b}-{workload}. Per workload the
optimum is analyze_sweep.efficiencyPeak on analyze_sweep.loadSweep rows, scored on the TARGET grid,
the same rule as score_session_d.py.
"""
import argparse
import math
import statistics
import sys
from pathlib import Path

from analyze_sweep import efficiencyPeak, loadSweep

LEGS = ("p5a", "p2", "p5b")
WORKLOADS = ("copy", "reduce", "softmax", "layernorm", "bgemm32", "bgemm64", "bgemm128",
             "bgemm256", "bgemm1024", "attention", "conv", "gemm")
STOCK_RETURN_TOLERANCE_PCT = 1.5   # section 10: "no workload ... exceeds 1.5%"
POINTS = 13
# A return equal to the limit passes ("exceeds 1.5%" fails); this margin absorbs float rounding, which
# put an exact 100 -> 98.5 change at 1.5000000000000013% (GPT Job 56, F10).
TOLERANCE_EPSILON = 1e-9


def exceeds_tolerance(value):
    """True when a return is above the registered limit, or is not a finite number at all (F12)."""
    return not math.isfinite(value) or value > STOCK_RETURN_TOLERANCE_PCT + TOLERANCE_EPSILON


def find_files(directory):
    found = {leg: {} for leg in LEGS}
    for path in Path(directory).rglob("*_sweep.csv"):
        for leg in LEGS:
            prefix = f"5060ti-ctrl10-{leg}-"
            if prefix in path.stem:
                workload = path.stem.split(prefix, 1)[1].removesuffix("_sweep")
                if workload not in WORKLOADS:
                    raise ValueError(f"{path}: unknown workload {workload!r}")
                if workload in found[leg]:
                    raise ValueError(f"duplicate {leg}/{workload} sweeps")
                found[leg][workload] = path
    for leg in LEGS:
        missing = sorted(set(WORKLOADS) - set(found[leg]))
        if missing:
            raise ValueError(f"{leg}: missing workload sweeps: {', '.join(missing)}")
    return found


def read_suite(paths):
    suite = {}
    targets = None
    for workload, path in paths.items():
        rows = loadSweep(path)
        grid = sorted(row["target"] for row in rows)
        if len(grid) != POINTS:
            raise ValueError(f"{path}: {len(grid)} usable points, not {POINTS}")
        # A repeated target would overwrite a row by key and still count 13 (GPT Job 56, F11).
        if len(set(grid)) != POINTS:
            raise ValueError(f"{path}: repeated targets in the grid")
        for row in rows:
            if not all(math.isfinite(row[k]) and row[k] > 0 for k in ("throughput", "power", "mhz")):
                raise ValueError(f"{path}: a non-finite or non-positive value at {row['target']} MHz (F12)")
        if targets is None:
            targets = grid
        elif grid != targets:
            raise ValueError(f"{path}: grid differs from the other sweeps")
        suite[workload] = {"rows": {row["target"]: row for row in rows},
                           "optimum": efficiencyPeak(rows)["target"]}
    return suite, targets


def stock_return(first, last, targets):
    """Per workload, median absolute matched-target throughput change, as score_session_d."""
    return {name: statistics.median(
                abs(100.0 * (last[name]["rows"][t]["throughput"] / first[name]["rows"][t]["throughput"] - 1.0))
                for t in targets)
            for name in WORKLOADS}


def score(directory):
    paths = find_files(directory)
    suites, grids = {}, set()
    for leg in LEGS:
        suites[leg], targets = read_suite(paths[leg])
        grids.add(tuple(targets))
    if len(grids) != 1:
        raise ValueError("the three suites do not share one target grid")
    targets = list(grids.pop())
    optima = {leg: {name: suites[leg][name]["optimum"] for name in WORKLOADS} for leg in LEGS}
    medians = {leg: statistics.median(optima[leg].values()) for leg in LEGS}
    drift = stock_return(suites["p5a"], suites["p5b"], targets)
    reasons = []
    if medians["p5a"] != medians["p5b"]:
        reasons.append(f"the P5 medians differ: {medians['p5a']:g} and {medians['p5b']:g}")
    over = sorted(name for name, value in drift.items() if exceeds_tolerance(value))
    if over:
        reasons.append(f"P5 return above {STOCK_RETURN_TOLERANCE_PCT}%: {', '.join(over)}")
    moved = sorted(name for name in WORKLOADS
                   if optima["p2"][name] != optima["p5a"][name] and optima["p2"][name] != optima["p5b"][name])
    if reasons:
        verdict = "NOT_SCOREABLE"
    elif medians["p2"] == medians["p5a"]:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {"targets": targets, "optima": optima, "medians": medians, "drift_pct": drift,
            "not_scoreable_reasons": reasons, "moved": moved, "verdict": verdict}


def report(result):
    print("Section 10 scorer | RTX 5060 Ti | P5 -> P2 -> P5 | optimum = efficiencyPeak on the target grid")
    for leg in LEGS:
        print(f"{leg}: median optimum {result['medians'][leg]:g} MHz")
        print("  " + ", ".join(f"{name}={result['optima'][leg][name]:g}" for name in WORKLOADS))
    print(f"P5 return p5a -> p5b: worst workload {max(result['drift_pct'].values()):.3f}% "
          f"(limit {STOCK_RETURN_TOLERANCE_PCT}%)")
    for reason in result["not_scoreable_reasons"]:
        print(f"Not scoreable: {reason}")
    print(f"P2 optima differing from BOTH P5 optima: {len(result['moved'])} of 12"
          + (f" ({', '.join(result['moved'])})" if result["moved"] else ""))
    print(f"Section 10 verdict (P2 median equals the P5 median): {result['verdict']}")
    print("Reported with the per-workload count above, always. n = 1 chip; the twelve workloads are "
          "repeated outcomes on it.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.directory)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Section 10 cannot be scored: {exc}", file=sys.stderr)
        return 2
    report(result)
    return 0 if result["verdict"] != "NOT_SCOREABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
