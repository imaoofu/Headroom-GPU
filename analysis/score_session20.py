"""Score REGISTERED-PREDICTIONS section 20: where efficiency peaks relative to the floor's end, on a fine grid.

Usage: python analysis/score_session20.py SESSION_DIRECTORY

Written 2026-10-07 with section 20's registration and before any of its data existed. One session,
stock ascending -> full tune (P4) ascending -> P4 descending -> stock descending, twelve workloads
each, collected by tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20, whose rerun15-inputs.json
maps each role ("{config}-{direction}-{workload}") to its sweep. A role re-run after a desktop-load
exit holds a list whose last entry is the accepted sweep; a role in "notScoreable" makes that
workload unusable for its configuration.

Each configuration has an 18-point grid at 37.5 MHz (every fifth supported clock) and a REGISTERED
floor-end target, the last target at the 0.720 V load floor in earlier data: stock 1575 MHz (worklist
4h, 2026-09-22: 0.720 V through 1567 MHz achieved, at target 1575) and P4 2010 MHz (section 16's
voltage extracts; P4's decoded floor ends at 2002). The floor end measured in this session's voltage
extracts is reported beside it, never substituted for it.

Per workload, efficiency at each target is throughput / power_avg_w (the 2 Hz `nvidia-smi` figure
every earlier result uses), averaged over the ascending and descending sweeps. That balances
frequency order when matched targets' acquisition midpoints are constant; it does not remove
nonlinear drift, asymmetric timing or thermal history (GPT Job 69; this said "cancels a linear drift"
until 2026-10-08). Points that are not bench_ok, or whose lock overshot, are skipped as
analyze_sweep does; a workload is usable only if both of its sweeps carry all 18 targets.

- gate: every usable stock workload's median absolute matched-target throughput change between the
  ascending and descending stock suites is at most 1.5% (section 15's R3 rule); otherwise every
  prediction is NOT SCOREABLE. A configuration with fewer than 11 usable workloads is NOT SCOREABLE.
- F1 (upper bound), per configuration: the efficiency argmax is at or below the floor-end target plus
  one grid step, in all but at most two of the usable workloads (10 of 12);
- F2 (near-optimal at the floor end), per configuration: the median over usable workloads of the
  efficiency lost at the floor-end target, against that workload's maximum, is at most 3%;
- F3 (falls above), per configuration: efficiency at the floor end plus 300 MHz (8 steps) is below
  efficiency at the floor end, in all but at most two of the usable workloads;
- reported, always: each workload's argmax and its distance from the floor end in grid steps, how
  many sit within one step of the floor end either side (the struck "the optimum IS the floor end"
  reading), how many sit at the grid's lower edge (not bracketed), the per-direction argmaxes, the
  same three tests on the energy-counter figure, and the floor end measured in this session.
"""
import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

from score_control10 import STOCK_RETURN_TOLERANCE_PCT, WORKLOADS, exceeds_tolerance

GRIDS = {  # registered
    "stock": (1237, 1275, 1312, 1350, 1387, 1425, 1462, 1500, 1537, 1575, 1612, 1650, 1687, 1725, 1762,
              1800, 1837, 1875),
    "p4": (1672, 1710, 1747, 1785, 1822, 1860, 1897, 1935, 1972, 2010, 2047, 2085, 2122, 2160, 2197,
           2235, 2272, 2310),
}
FLOOR_END = {"stock": 1575, "p4": 2010}  # registered
ABOVE_STEPS = 8  # floor end + 300 MHz on a 37.5 MHz grid
F2_LIMIT_PCT = 3.0
MIN_USABLE = 11
ALLOWED_MISSES = 2
DIRECTIONS = ("asc", "desc")
POWER = {"sampled": "power_avg_w", "energy": "energy_avg_power_w"}


def load_manifest(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "rerun15-inputs.json").read_text(encoding="utf-8-sig"))
    if "section 20" not in manifest.get("section", ""):
        raise ValueError(f"{directory}: rerun15-inputs.json is not a section 20 session")
    return directory, manifest


def sweep_path(directory, manifest, role):
    desc = manifest["sweeps"].get(role)
    if desc is None:
        return None
    if isinstance(desc, list):
        if not desc:  # an empty retry history is a missing role, not a crash (GPT Job 69)
            return None
        desc = desc[-1]
    path = Path(desc["sweep"])
    return path if path.is_absolute() else directory / path


def read_sweep(path, grid):
    """{target: {throughput, sampled, energy}} for the usable points, refusing malformed input."""
    rows = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            if raw.get("bench_ok") not in ("True", "true") or raw.get("lock_miss_direction") == "above":
                continue
            try:
                targetValue = float(raw["target_frequency_mhz"])
                point = {"throughput": float(raw["bench_throughput"]), "sampled": float(raw["power_avg_w"]),
                         "energy": float(raw.get("energy_avg_power_w") or "nan")}
            except (KeyError, ValueError, TypeError):
                raise ValueError(f"{path}: a point lacks a throughput or power figure")
            if not (math.isfinite(targetValue) and targetValue.is_integer()):
                raise ValueError(f"{path}: target {raw['target_frequency_mhz']} is not a whole MHz")
            target = int(targetValue)
            if target not in grid:
                raise ValueError(f"{path}: target {target} is not on section 20's registered grid")
            if target in rows:
                raise ValueError(f"{path}: target {target} appears twice")
            if not all(math.isfinite(point[k]) and point[k] > 0 for k in ("throughput", "sampled")):
                raise ValueError(f"{path}: a non-finite or non-positive value at {target} MHz")
            rows[target] = point
    return rows


def efficiency(asc, desc, figure):
    """Direction-averaged efficiency per target, or None if the figure is missing anywhere."""
    out = {}
    for t in asc:
        # A zero or missing optional energy figure makes that figure unavailable, never a crash.
        if not all(math.isfinite(d[t][figure]) and d[t][figure] > 0 for d in (asc, desc)):
            return None
        values = [d[t]["throughput"] / d[t][figure] for d in (asc, desc)]
        if not all(math.isfinite(v) and v > 0 for v in values):
            return None
        out[t] = statistics.fmean(values)
    return out


def tests(eff_by_workload, grid, floor):
    """F1, F2 and F3 statistics for one configuration and one power figure."""
    i_floor = grid.index(floor)
    above = grid[i_floor + ABOVE_STEPS]
    # Ties go to the LOWEST target, whatever the CSV row order (GPT Job 69: insertion order decided
    # them before 2026-10-08; section 20 had no exact ties, so no verdict changed).
    argmax = {w: max(sorted(e), key=e.get) for w, e in eff_by_workload.items()}
    steps = {w: grid.index(t) - i_floor for w, t in argmax.items()}
    loss = {w: 100 * (1 - e[floor] / max(e.values())) for w, e in eff_by_workload.items()}
    falls = {w: e[above] < e[floor] for w, e in eff_by_workload.items()}
    n = len(eff_by_workload)
    f1 = sum(1 for s in steps.values() if s <= 1)
    f3 = sum(1 for v in falls.values() if v)
    f2 = statistics.median(loss.values())
    return {"argmax": argmax, "steps": steps, "loss_pct": loss, "falls": falls, "usable": n,
            "f1_count": f1, "f2_median_loss_pct": f2, "f3_count": f3, "above_target": above,
            "within_one_step": sum(1 for s in steps.values() if abs(s) <= 1),
            "at_lower_edge": sum(1 for t in argmax.values() if t == grid[0]),
            "f1": f1 >= n - ALLOWED_MISSES, "f2": f2 <= F2_LIMIT_PCT + 1e-9, "f3": f3 >= n - ALLOWED_MISSES}


def measured_floor_end(sweep_csv):
    """Last target at the sweep's lowest voltage code before the first higher code, from the joined
    voltage extract beside the sweep; None if there is no extract or no rise inside the grid."""
    extract = Path(str(sweep_csv).replace("_sweep.csv", "_sweep_voltage.csv"))
    if not extract.exists():
        return None
    with open(extract, encoding="utf-8-sig", newline="") as handle:
        points = sorted((int(float(r["target"])), float(r["voltage"])) for r in csv.DictReader(handle)
                        if r.get("voltage") not in (None, ""))
    if not points:
        return None
    low = min(v for _, v in points)
    last = None
    for target, volts in points:
        if abs(volts - low) < 1e-9:
            last = target
        elif last is not None:
            return last
    return None


def score(directory):
    directory, manifest = load_manifest(directory)
    lost = set(manifest.get("notScoreable") or [])
    data, unusable, paths = {}, {}, {}
    for config, grid in GRIDS.items():
        data[config], unusable[config] = {}, []
        for w in WORKLOADS:
            sweeps = {}
            for d in DIRECTIONS:
                role = f"{config}-{d}-{w}"
                path = sweep_path(directory, manifest, role)
                if role in lost or path is None:
                    break
                rows = read_sweep(path, grid)
                if tuple(sorted(rows)) != grid:
                    break
                sweeps[d] = rows
                paths[role] = path
            if len(sweeps) == 2:
                data[config][w] = sweeps
            else:
                unusable[config].append(w)

    stock = data["stock"]
    # score_control10.stock_return's rule, over the usable stock workloads only.
    drift = {w: statistics.median(abs(100.0 * (s["desc"][t]["throughput"] / s["asc"][t]["throughput"] - 1.0))
                                  for t in GRIDS["stock"]) for w, s in stock.items()}
    over = sorted(w for w, v in drift.items() if exceeds_tolerance(v))
    reasons = [f"stock ascending-to-descending throughput change above {STOCK_RETURN_TOLERANCE_PCT}%: {', '.join(over)}"] if over else []
    for config in GRIDS:
        if len(data[config]) < MIN_USABLE:
            reasons.append(f"{config} has {len(data[config])} usable workloads, fewer than {MIN_USABLE}")

    results, verdicts = {}, {}
    for config, grid in GRIDS.items():
        results[config] = {}
        for figure in POWER:
            effs = {w: efficiency(s["asc"], s["desc"], figure) for w, s in data[config].items()}
            effs = {w: e for w, e in effs.items() if e is not None}
            results[config][figure] = tests(effs, grid, FLOOR_END[config]) if effs else None
        results[config]["per_direction_argmax"] = {
            w: {d: max(sorted(s[d]), key=lambda t: s[d][t]["throughput"] / s[d][t]["sampled"]) for d in DIRECTIONS}
            for w, s in data[config].items()}
        ends = [measured_floor_end(paths[f"{config}-{d}-{w}"]) for w in data[config] for d in DIRECTIONS]
        ends = [e for e in ends if e is not None]
        results[config]["measured_floor_end"] = {"median": statistics.median(ends) if ends else None,
                                                 "range": (min(ends), max(ends)) if ends else None,
                                                 "sweeps": len(ends)}
        void = bool(over) or len(data[config]) < MIN_USABLE
        r = results[config]["sampled"]
        for test in ("f1", "f2", "f3"):
            verdicts[f"{config}-{test}"] = "NOT_SCOREABLE" if void or r is None else ("HOLDS" if r[test] else "FAILS")
    return {"results": results, "verdicts": verdicts, "drift_pct": drift, "unusable": unusable,
            "not_scoreable_reasons": reasons}


def report(r):
    print("Section 20 scorer | RTX 5060 Ti | efficiency = throughput / 2 Hz power, mean of ascending and descending")
    for config, grid in GRIDS.items():
        floor = FLOOR_END[config]
        print(f"== {config}: registered floor end {floor} MHz; grid {grid[0]}-{grid[-1]} MHz, 37.5 MHz steps ==")
        for figure in POWER:
            t = r["results"][config][figure]
            if t is None:
                print(f"  {figure}: no usable workloads.")
                continue
            label = "REGISTERED" if figure == "sampled" else "reported"
            print(f"  {figure} ({label}): F1 argmax at or below {floor}+1 step in {t['f1_count']} of {t['usable']}; "
                  f"F2 median loss at {floor} {t['f2_median_loss_pct']:.2f}% (limit {F2_LIMIT_PCT}%); "
                  f"F3 lower at {t['above_target']} than at {floor} in {t['f3_count']} of {t['usable']}. "
                  f"Within one step of the floor end: {t['within_one_step']}; at the grid's lower edge: {t['at_lower_edge']}.")
            if figure == "sampled":
                for w in WORKLOADS:
                    if w in t["argmax"]:
                        d = r["results"][config]["per_direction_argmax"][w]
                        print(f"    {w}: argmax {t['argmax'][w]} MHz ({t['steps'][w]:+d} steps), loss at the floor end "
                              f"{t['loss_pct'][w]:.2f}%, falls above: {t['falls'][w]}; ascending {d['asc']}, descending {d['desc']}")
        for test in ("f1", "f2", "f3"):
            print(f"  {test.upper()}: {r['verdicts'][f'{config}-{test}']}")
        m = r["results"][config]["measured_floor_end"]
        if m["median"] is None:
            print("  Measured floor end: no voltage extract with a rise inside the grid.")
        else:
            print(f"  Measured floor end (last target at the lowest voltage code): median {m['median']:g} MHz, "
                  f"range {m['range'][0]}-{m['range'][1]}, over {m['sweeps']} sweeps; reported, not substituted.")
        if r["unusable"][config]:
            print(f"  Unusable workloads: {', '.join(r['unusable'][config])}.")
    if r["drift_pct"]:
        print(f"Stock ascending-to-descending: worst workload {max(r['drift_pct'].values()):.3f}% (limit {STOCK_RETURN_TOLERANCE_PCT}%).")
    for reason in r["not_scoreable_reasons"]:
        print(f"Not scoreable: {reason}.")
    print("Board power is the card's own telemetry, not a shunt. N=1 chip, one session; the twelve workloads are "
          "repeated outcomes on it, and a 37.5 MHz grid still bounds where a peak can be read.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.directory)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Section 20 cannot be scored: {exc}", file=sys.stderr)
        return 2
    report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
