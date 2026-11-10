"""Score REGISTERED-PREDICTIONS section 21: section 20's floor-end tests on four application workloads.

Usage: python analysis/score_session21.py SESSION_DIRECTORY

Written 2026-10-08 with section 21's registration and before any of its data existed. One session,
collected by tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s21: stock coarse ascending -> stock fine
ascending -> P4 fine ascending -> P4 fine descending -> stock fine descending -> stock coarse
descending, each over the four application workloads of tools/frequency-sweep/app_workloads.py
(alexnet, resnet50, kmeans, hotspot). rerun15-inputs.json maps each role
("{config}-{grid}-{direction}-{workload}") to its sweep, as in section 20.

Fine grids, floor-end targets, the efficiency estimator (throughput / power_avg_w, averaged over the
two directions), point filtering and per-sweep validation are section 20's, imported from
score_session20 so the two sections cannot drift apart. What differs is the count: four workloads,
so each per-workload test allows ONE miss when all four are usable and none when three are, and a
configuration with fewer than three usable workloads is NOT SCOREABLE.

- gate (fine): every usable stock workload's median absolute matched-target throughput change between
  the stock fine ascending and descending sweeps is at most 1.5%; otherwise A1-A3 are NOT SCOREABLE.
- gate (coarse): the same rule between the two stock coarse sweeps; otherwise A4 is NOT SCOREABLE.
- A1, per configuration: fine-grid efficiency argmax at or below the floor-end target plus one step;
- A2, per configuration: median efficiency lost at the floor-end target at most 3%;
- A3, per configuration: efficiency 300 MHz above the floor end lower than at the floor end;
- A4, stock coarse grid (1237-3090 MHz, 13 points): the efficiency argmax at or below 1702 MHz, the
  first coarse target above the stock floor end;
- reported, always: per-workload argmaxes and losses, per-direction argmaxes, the energy-counter
  figure, the measured floor end, and the coarse argmaxes against the twelve-workload suite's 1545 MHz.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import score_session20 as s20
from score_control10 import STOCK_RETURN_TOLERANCE_PCT, exceeds_tolerance

WORKLOADS = ("alexnet", "resnet50", "kmeans", "hotspot")  # registered
COARSE = (1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090)  # registered
COARSE_BOUND = 1702  # registered: the first coarse target above the stock floor end
SUITE_COARSE_OPTIMUM = 1545  # reported against, not tested
MIN_USABLE = 3
FINE = {"stock": ("stock", "fine"), "p4": ("p4", "fine")}


def allowed_misses(usable):
    return 1 if usable >= 4 else 0


def load_manifest(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "rerun15-inputs.json").read_text(encoding="utf-8-sig"))
    if "section 21" not in manifest.get("section", ""):
        raise ValueError(f"{directory}: rerun15-inputs.json is not a section 21 session")
    return directory, manifest


def pairs(directory, manifest, config, grid_name, grid):
    """{workload: {"asc": rows, "desc": rows}} for workloads complete in both directions, plus the
    unusable list and the sweep paths."""
    lost = set(manifest.get("notScoreable") or [])
    data, unusable, paths = {}, [], {}
    for w in WORKLOADS:
        sweeps = {}
        for d in s20.DIRECTIONS:
            role = f"{config}-{grid_name}-{d}-{w}"
            path = s20.sweep_path(directory, manifest, role)
            if role in lost or path is None:
                break
            rows = s20.read_sweep(path, grid)
            if tuple(sorted(rows)) != tuple(grid):
                break
            sweeps[d] = rows
            paths[role] = path
        if len(sweeps) == 2:
            data[w] = sweeps
        else:
            unusable.append(w)
    return data, unusable, paths


def drift(data, grid):
    return {w: statistics.median(abs(100.0 * (s["desc"][t]["throughput"] / s["asc"][t]["throughput"] - 1.0))
                                 for t in grid) for w, s in data.items()}


def fine_tests(effs, grid, floor):
    t = s20.tests(effs, grid, floor)
    misses = allowed_misses(t["usable"])
    t["allowed_misses"] = misses
    t["f1"] = t["f1_count"] >= t["usable"] - misses
    t["f3"] = t["f3_count"] >= t["usable"] - misses
    return t


def score(directory):
    directory, manifest = load_manifest(directory)
    results, verdicts, reasons, unusable_all, drifts = {}, {}, [], {}, {}

    fine = {}
    for config, (cfg, grid_name) in FINE.items():
        fine[config] = pairs(directory, manifest, cfg, grid_name, s20.GRIDS[config])
        unusable_all[config] = fine[config][1]
    drifts["stock-fine"] = drift(fine["stock"][0], s20.GRIDS["stock"])
    over = sorted(w for w, v in drifts["stock-fine"].items() if exceeds_tolerance(v))
    if over:
        reasons.append(f"stock fine ascending-to-descending change above {STOCK_RETURN_TOLERANCE_PCT}%: {', '.join(over)}")
    for config, grid in s20.GRIDS.items():
        data, _, paths = fine[config]
        if len(data) < MIN_USABLE:
            reasons.append(f"{config} fine has {len(data)} usable workloads, fewer than {MIN_USABLE}")
        results[config] = {}
        for figure in s20.POWER:
            effs = {w: s20.efficiency(s["asc"], s["desc"], figure) for w, s in data.items()}
            effs = {w: e for w, e in effs.items() if e is not None}
            results[config][figure] = fine_tests(effs, grid, s20.FLOOR_END[config]) if effs else None
        results[config]["per_direction_argmax"] = {
            w: {d: max(sorted(s[d]), key=lambda t: s[d][t]["throughput"] / s[d][t]["sampled"]) for d in s20.DIRECTIONS}
            for w, s in data.items()}
        ends = [s20.measured_floor_end(p) for p in paths.values()]
        ends = [e for e in ends if e is not None]
        results[config]["measured_floor_end"] = {"median": statistics.median(ends) if ends else None,
                                                 "range": (min(ends), max(ends)) if ends else None,
                                                 "sweeps": len(ends)}
        void = bool(over) or len(data) < MIN_USABLE
        r = results[config]["sampled"]
        verdicts[f"{config}-A1"] = "NOT_SCOREABLE" if void or r is None else ("HOLDS" if r["f1"] else "FAILS")
        verdicts[f"{config}-A2"] = "NOT_SCOREABLE" if void or r is None else ("HOLDS" if r["f2"] else "FAILS")
        verdicts[f"{config}-A3"] = "NOT_SCOREABLE" if void or r is None else ("HOLDS" if r["f3"] else "FAILS")

    coarse, coarse_unusable, _ = pairs(directory, manifest, "stock", "coarse", COARSE)
    unusable_all["stock-coarse"] = coarse_unusable
    drifts["stock-coarse"] = drift(coarse, COARSE)
    coarse_over = sorted(w for w, v in drifts["stock-coarse"].items() if exceeds_tolerance(v))
    coarse_void = bool(coarse_over) or len(coarse) < MIN_USABLE
    if coarse_over:
        reasons.append(f"stock coarse ascending-to-descending change above {STOCK_RETURN_TOLERANCE_PCT}%: {', '.join(coarse_over)}")
    if len(coarse) < MIN_USABLE:
        reasons.append(f"stock coarse has {len(coarse)} usable workloads, fewer than {MIN_USABLE}")
    coarse_results = {}
    for figure in s20.POWER:
        effs = {w: s20.efficiency(s["asc"], s["desc"], figure) for w, s in coarse.items()}
        effs = {w: e for w, e in effs.items() if e is not None}
        argmax = {w: max(sorted(e), key=e.get) for w, e in effs.items()}  # ties: lowest target
        within = sum(1 for t in argmax.values() if t <= COARSE_BOUND)
        coarse_results[figure] = {"argmax": argmax, "within": within, "usable": len(argmax),
                                  "at_suite_optimum": sum(1 for t in argmax.values() if t == SUITE_COARSE_OPTIMUM),
                                  "a4": within >= len(argmax) - allowed_misses(len(argmax)) if argmax else False}
    results["stock-coarse"] = coarse_results
    verdicts["stock-A4"] = "NOT_SCOREABLE" if coarse_void else ("HOLDS" if coarse_results["sampled"]["a4"] else "FAILS")
    return {"results": results, "verdicts": verdicts, "drift_pct": drifts, "unusable": unusable_all,
            "not_scoreable_reasons": reasons}


def report(r):
    print("Section 21 scorer | RTX 5060 Ti | four application workloads | efficiency = throughput / 2 Hz power, mean of both directions")
    for config, grid in s20.GRIDS.items():
        floor = s20.FLOOR_END[config]
        print(f"== {config} fine: registered floor end {floor} MHz; grid {grid[0]}-{grid[-1]} MHz ==")
        for figure in s20.POWER:
            t = r["results"][config][figure]
            if t is None:
                print(f"  {figure}: no usable workloads.")
                continue
            label = "REGISTERED" if figure == "sampled" else "reported"
            print(f"  {figure} ({label}): A1 {t['f1_count']} of {t['usable']} at or below {floor}+1 step; "
                  f"A2 median loss at {floor} {t['f2_median_loss_pct']:.2f}%; A3 lower at {t['above_target']} in "
                  f"{t['f3_count']} of {t['usable']} (misses allowed {t['allowed_misses']}). Within one step: "
                  f"{t['within_one_step']}; at the lower edge: {t['at_lower_edge']}.")
            if figure == "sampled":
                for w in WORKLOADS:
                    if w in t["argmax"]:
                        d = r["results"][config]["per_direction_argmax"][w]
                        print(f"    {w}: argmax {t['argmax'][w]} MHz ({t['steps'][w]:+d} steps), loss at the floor end "
                              f"{t['loss_pct'][w]:.2f}%, falls above: {t['falls'][w]}; ascending {d['asc']}, descending {d['desc']}")
        for test in ("A1", "A2", "A3"):
            print(f"  {test}: {r['verdicts'][f'{config}-{test}']}")
        m = r["results"][config]["measured_floor_end"]
        if m["median"] is not None:
            print(f"  Measured floor end: median {m['median']:g} MHz, range {m['range'][0]}-{m['range'][1]}, "
                  f"{m['sweeps']} sweeps; reported, not substituted.")
        if r["unusable"][config]:
            print(f"  Unusable workloads: {', '.join(r['unusable'][config])}.")
    print("== stock coarse: 1237-3090 MHz, 13 points ==")
    for figure in s20.POWER:
        c = r["results"]["stock-coarse"][figure]
        label = "REGISTERED" if figure == "sampled" else "reported"
        print(f"  {figure} ({label}): argmax at or below {COARSE_BOUND} MHz in {c['within']} of {c['usable']}; "
              f"at the suite's {SUITE_COARSE_OPTIMUM} MHz: {c['at_suite_optimum']}; "
              + ", ".join(f"{w} {t}" for w, t in c["argmax"].items()))
    print(f"  A4: {r['verdicts']['stock-A4']}")
    for name, values in r["drift_pct"].items():
        if values:
            print(f"Return check {name}: worst workload {max(values.values()):.3f}% (limit {STOCK_RETURN_TOLERANCE_PCT}%).")
    for reason in r["not_scoreable_reasons"]:
        print(f"Not scoreable: {reason}.")
    print("Board power is the card's own telemetry, not a shunt. N=1 chip, one session, four workloads: the CNNs "
          "run seeded random weights on synthetic inputs, and k-means and HotSpot are PyTorch ports on generated inputs.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.directory)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Section 21 cannot be scored: {exc}", file=sys.stderr)
        return 2
    report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
