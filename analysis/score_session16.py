"""Score REGISTERED-PREDICTIONS section 16: P5 -> P4 -> P2 -> P5 on the RTX 5060 Ti.

Usage: python analysis/score_session16.py SESSION_DIRECTORY

Written 2026-10-06 with section 16's registration and before any of its data existed. The session
directory holds rerun15-inputs.json, written by tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s16,
which maps each role (5060ti-ctrl10-{p5a,p2,p5b}-{workload}, 5060ti-s16-p4-{workload}) to its
sweep. A role re-run after a desktop-load exit holds a list; its last entry is the accepted sweep,
and a role in "notScoreable" makes its whole suite NOT SCOREABLE (section 15 condition 1, adopted).

Per workload the optimum is analyze_sweep.efficiencyPeak on the TARGET grid, exactly as
score_control10.py, whose read_suite and stock_return are reused unchanged:
- gate (section 10's): equal P5 medians and every workload's P5 return within 1.5%;
- control (section 10's): the P2 median equals the P5 median;
- P4 primary: the P4 median is 2010 MHz;
- P4 secondary: at least 9 of 12 P4 optima lie strictly above the opening P5 optimum.
Reported, always: P2 optima differing from both P5 optima, and the P5a/P5b repeat count.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

from score_control10 import STOCK_RETURN_TOLERANCE_PCT, WORKLOADS, exceeds_tolerance, read_suite, stock_return

LEGS = {"p5a": "5060ti-ctrl10-p5a", "p4": "5060ti-s16-p4", "p2": "5060ti-ctrl10-p2", "p5b": "5060ti-ctrl10-p5b"}
P4_PREDICTED_MHZ = 2010
P4_ABOVE_MIN = 9
GRID = (1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090)  # registered


def load_manifest(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "rerun15-inputs.json").read_text(encoding="utf-8-sig"))
    if "section 16" not in manifest.get("section", ""):
        raise ValueError(f"{directory}: rerun15-inputs.json is not a section 16 session")
    return directory, manifest


def leg_paths(directory, manifest, leg):
    paths = {}
    for workload in WORKLOADS:
        role = f"{LEGS[leg]}-{workload}"
        desc = manifest["sweeps"].get(role)
        if desc is None:
            raise ValueError(f"{leg}: role {role} is missing")
        if isinstance(desc, list):
            desc = desc[-1]
        path = Path(desc["sweep"])
        paths[workload] = path if path.is_absolute() else directory / path
    return paths


def score(directory):
    directory, manifest = load_manifest(directory)
    unscoreable = set(manifest.get("notScoreable") or [])
    lost = {leg for leg in LEGS if any(f"{LEGS[leg]}-{w}" in unscoreable for w in WORKLOADS)}
    suites, optima = {}, {}
    for leg in LEGS:
        try:
            suites[leg], targets = read_suite(leg_paths(directory, manifest, leg))
        except ValueError:
            # A suite already NOT SCOREABLE may be incomplete; it must not stop the others from being
            # scored (GPT Job 56, F13). A P5 suite, or any suite not marked lost, still fails loudly.
            if leg in lost and leg not in ("p5a", "p5b"):
                continue
            raise
        if tuple(targets) != GRID:
            raise ValueError(f"{leg}: the grid is not section 16's registered 13 targets")
        optima[leg] = {w: suites[leg][w]["optimum"] for w in WORKLOADS}
    targets = list(GRID)
    medians = {leg: statistics.median(optima[leg].values()) if leg in optima else float("nan") for leg in LEGS}
    drift = stock_return(suites["p5a"], suites["p5b"], targets)

    gate = []
    if medians["p5a"] != medians["p5b"]:
        gate.append(f"the P5 medians differ: {medians['p5a']:g} and {medians['p5b']:g}")
    over = sorted(w for w, v in drift.items() if exceeds_tolerance(v))
    if over:
        gate.append(f"P5 return above {STOCK_RETURN_TOLERANCE_PCT}%: {', '.join(over)}")
    for leg in sorted(lost):
        gate.append(f"{leg} has a role NOT SCOREABLE after a second desktop load")
    # Any P5 failure voids every prediction; a lost P2 or P4 suite voids only its own.
    bracket_failed = len(gate) > len(lost) or bool(lost & {"p5a", "p5b"})

    def verdict(holds, leg):
        if bracket_failed or leg in lost:
            return "NOT_SCOREABLE"
        return "HOLDS" if holds else "FAILS"

    above = sorted(w for w in WORKLOADS if "p4" in optima and optima["p4"][w] > optima["p5a"][w])
    moved = sorted(w for w in WORKLOADS if "p2" in optima
                   and optima["p2"][w] != optima["p5a"][w] and optima["p2"][w] != optima["p5b"][w])
    repeat = sorted(w for w in WORKLOADS if optima["p5a"][w] != optima["p5b"][w])
    return {
        "targets": targets, "optima": optima, "medians": medians, "drift_pct": drift,
        "not_scoreable_reasons": gate,
        "control": verdict(medians["p2"] == medians["p5a"], "p2"),
        "p4_primary": verdict(medians["p4"] == P4_PREDICTED_MHZ, "p4"),
        "p4_secondary": verdict(len(above) >= P4_ABOVE_MIN, "p4"),
        "p4_above": above, "p2_moved": moved, "p5_repeat_changed": repeat,
    }


def report(r):
    print("Section 16 scorer | RTX 5060 Ti | P5 -> P4 -> P2 -> P5 | optimum = efficiencyPeak on the target grid")
    for leg in LEGS:
        if leg not in r["optima"]:
            print(f"{leg}: not read; the suite is NOT SCOREABLE and could not be loaded.")
            continue
        print(f"{leg}: median optimum {r['medians'][leg]:g} MHz; "
              + ", ".join(f"{w}={r['optima'][leg][w]:g}" for w in WORKLOADS))
    print(f"P5 return p5a -> p5b: worst workload {max(r['drift_pct'].values()):.3f}% "
          f"(limit {STOCK_RETURN_TOLERANCE_PCT}%).")
    for reason in r["not_scoreable_reasons"]:
        print(f"Not scoreable: {reason}.")
    print(f"Control (P2 median equals the P5 median): {r['control']}. "
          f"P2 optima differing from both P5 optima: {len(r['p2_moved'])} of 12"
          + (f" ({', '.join(r['p2_moved'])})." if r["p2_moved"] else "."))
    print(f"The two P5 suites themselves differ at {len(r['p5_repeat_changed'])} of 12 workloads"
          + (f" ({', '.join(r['p5_repeat_changed'])})." if r["p5_repeat_changed"] else "."))
    print(f"P4 primary (median {P4_PREDICTED_MHZ} MHz): {r['p4_primary']}, measured {r['medians']['p4']:g} MHz.")
    print(f"P4 secondary (at least {P4_ABOVE_MIN} of 12 strictly above the opening P5): {r['p4_secondary']}, "
          f"{len(r['p4_above'])} of 12.")
    print("N=1 chip, one session, one suite per arm; the twelve workloads are repeated outcomes on it.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.directory)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Section 16 cannot be scored: {exc}", file=sys.stderr)
        return 2
    report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
