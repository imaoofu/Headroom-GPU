"""Recompute Job 50 uncertainty from committed measurements, without writing data.

Run: python analysis/paper_uncertainty.py [--resamples 20000] [--seed 20261004]
Intervals condition on measured grid points and one chip per model. Exact p-values
are assumption-dependent workload comparisons, not randomized intervention tests.
"""
import argparse
import csv
import dataclasses
import json
import math
import statistics
import subprocess
from pathlib import Path

import numpy as np

import claims_consumer as cc
from analyze_sweep import efficiencyPeak, loadSweep
from score_control10 import WORKLOADS, read_suite, stock_return
import score_control10
import score_session_d

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "frequency-sweeps"
RERUN = DATA / "5060ti-rerun15-20261003"
SEED = 20261004
RESAMPLES = 20000


class CommittedInputs:
    """Refuse untracked or modified CSV inputs before existing helpers read them.

    Git's diff applies the repository's line-ending rules. No hashes are re-based.
    Metadata selects roles; no ignored raw HWiNFO log is used by this analysis.
    """
    def __init__(self):
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")
        self.tracked = set(git("ls-files", "-z", "data").split("\0"))
        self.changed = set(git("diff", "HEAD", "--name-only", "-z", "--", "data").split("\0"))
        self.used = set()

    def path(self, value):
        path = Path(value)
        path = path if path.is_absolute() else DATA / path
        relative = path.resolve().relative_to(ROOT).as_posix()
        if relative not in self.tracked or relative in self.changed:
            raise ValueError(f"input is not an unchanged committed file: {relative}")
        self.used.add(relative)
        return path


def validate_matrix(matrix):
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or not values.size or not np.isfinite(values).all():
        raise ValueError("a finite, nonempty suite-by-workload matrix is required")
    return values


def median_bootstrap(matrix, resamples=RESAMPLES, seed=SEED, suites=False):
    """Median of per-workload mean optima; resample workload identities jointly.

    With suites=True, resample complete suite rows as well as workload columns.
    Never independently resample a workload's replicate observations.
    """
    values = validate_matrix(matrix)
    if resamples < 2:
        raise ValueError("at least two bootstrap resamples are required")
    rng = np.random.default_rng(seed)
    rows, columns = values.shape
    workload_ids = rng.integers(columns, size=(resamples, columns))
    if suites:
        suite_ids = rng.integers(rows, size=(resamples, rows))
        samples = values[suite_ids[:, :, None], workload_ids[:, None, :]].mean(axis=1)
    else:
        samples = values.mean(axis=0)[workload_ids]
    medians = np.median(samples, axis=1)
    return {"median": float(np.median(values.mean(axis=0))),
            "interval": np.quantile(medians, [0.025, 0.975]).tolist(),
            "suites": rows, "workloads": columns}


def floor_distance(matrix, floor, step, resamples=RESAMPLES, seed=SEED):
    """Signed median optimum minus last measured floor point, in achieved MHz."""
    if not math.isfinite(floor) or not math.isfinite(step) or step <= 0:
        raise ValueError("finite floor and positive nominal target-grid spacing are required")
    result = median_bootstrap(matrix, resamples, seed)
    both = median_bootstrap(matrix, resamples, seed, suites=True)
    result.update(floor=floor, step=step, distance=result["median"] - floor,
                  steps=(result["median"] - floor) / step,
                  workload_interval=[v - floor for v in result["interval"]],
                  crossed_interval=[v - floor for v in both["interval"]])
    return result


def change_vector(before, after):
    if not before or set(before) != set(after):
        raise ValueError("paired suites must contain the same nonempty workload set")
    if not all(math.isfinite(v) for table in (before, after) for v in table.values()):
        raise ValueError("optima must be finite")
    return {name: int(before[name] != after[name]) for name in sorted(before)}


def exact_change_test(treatment, reference):
    """One-sided exact conditional McNemar tail, including equal-count ties.

    Under H0, treatment-only and reference-only changes are equiprobable,
    independently across discordant workloads. Concordant workloads do not count
    as independent discordances; shared reference suites are never pooled.
    """
    if not treatment or set(treatment) != set(reference):
        raise ValueError("change indicators must name the same workloads")
    if any(v not in (0, 1) for table in (treatment, reference) for v in table.values()):
        raise ValueError("change indicators must be binary")
    more = sum(treatment[w] == 1 and reference[w] == 0 for w in treatment)
    less = sum(treatment[w] == 0 and reference[w] == 1 for w in treatment)
    n = more + less
    return {"more": more, "less": less, "discordant": n,
            "p": sum(math.comb(n, k) for k in range(more, n + 1)) / 2 ** n}


def reference_tail(count, references):
    """Finite-bank upper rank tail; an exact p only with exchangeable suite pairs."""
    if not references:
        raise ValueError("at least one reference count is required")
    return (1 + sum(value >= count for value in references)) / (len(references) + 1)


def compare_edit(before, after, references):
    changes = change_vector(before, after)
    count = sum(changes.values())
    baseline_counts = {label: sum(vector.values()) for label, vector in references.items()}
    if not baseline_counts:
        raise ValueError("an edit needs repeatability reference pairs")
    return {"count": count, "n": len(changes), "changes": changes,
            "median_before": statistics.median(before.values()),
            "median_after": statistics.median(after.values()),
            "reference_counts": baseline_counts,
            "rank_tail": reference_tail(count, list(baseline_counts.values())),
            "exact": {label: exact_change_test(changes, vector)
                      for label, vector in references.items()}}


def bandwidth_gap(stock, curve, resamples=RESAMPLES, seed=SEED):
    """Bootstrap paired targets, mean of percentage losses, not ratio of means."""
    if set(stock) != set(curve):
        raise ValueError("bandwidth arms must have identical target sets")
    targets = sorted(t for t in stock if 1560 <= t <= 1867)
    if not targets or resamples < 2:
        raise ValueError("band has no targets or too few resamples")
    values = []
    for target in targets:
        a, b = stock[target]["throughput"], curve[target]["throughput"]
        if not math.isfinite(a) or not math.isfinite(b) or min(a, b) <= 0:
            raise ValueError("bandwidth measurements must be finite and positive")
        values.append(100 * (1 - b / a))
    values = np.asarray(values)
    rng = np.random.default_rng(seed)
    means = values[rng.integers(len(values), size=(resamples, len(values)))].mean(axis=1)
    return {"targets": targets, "losses": values.tolist(), "mean": float(values.mean()),
            "range": [float(values.min()), float(values.max())],
            "interval": np.quantile(means, [0.025, 0.975]).tolist()}


def unique_paths(inputs, directory, label):
    paths = {}
    for workload in WORKLOADS:
        matches = list(directory.rglob(f"*_{label}-{workload}_sweep.csv"))
        if len(matches) != 1:
            raise ValueError(f"{label}/{workload}: expected one CSV, found {len(matches)}")
        paths[workload] = inputs.path(matches[0])
    return paths


def guard_scorer_directory(inputs, directory):
    """Guard measured CSVs and JSON companions consumed by registered scorers."""
    for path in directory.rglob("*_sweep.csv"):
        inputs.path(path)
        inputs.path(path.with_suffix(".json"))
        inputs.path(path.with_name(path.stem + "_voltage.csv"))


def ordinary_suite(inputs, table):
    paths = {w: inputs.path(p) for w, p in table.items()}
    if set(paths) != set(WORKLOADS):
        raise ValueError("suite must contain all twelve workloads")
    suite, grid = read_suite(paths)
    return {w: suite[w]["optimum"] for w in WORKLOADS}, suite, grid


def floor_bracket(inputs, relative, tolerance=0):
    path = inputs.path(relative)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        readings = sorted((float(r["achieved"]), float(r["voltage"]))
                          for r in csv.DictReader(handle))
    top = (cc._voltageFloorTop(relative) if tolerance == 0
           else cc._voltageFloorTopWithin(relative, tolerance))
    floor_v = cc._voltageFloorValue(relative)
    above = [mhz for mhz, voltage in readings if mhz > top and voltage > floor_v + tolerance + 1e-9]
    return {"last_flat": top, "first_above": min(above) if above else None,
            "voltage": floor_v, "tolerance": tolerance, "source": relative}


def build_results(resamples=RESAMPLES, seed=SEED):
    inputs = CommittedInputs()
    floors = []
    specifications = [
        ("RTX 5060 Ti", cc.REPLICATES_5060[1:], cc._VOLT_5060_STOCK, 0),
        ("RTX 3070 Ti", (cc.SUITE_3070_SWEEPS,), cc._VOLT_3070_SILENT, 0),
        ("RTX 3060", (cc.SUITE_3060,), cc._VOLT_3060_SUITE, 0),
        ("RTX 2060 Super, strict", (cc.SUITE_2060S,), cc._VOLT_2060S_LOWRANGE, 0),
        ("RTX 2060 Super, within 6 mV", (cc.SUITE_2060S,), cc._VOLT_2060S_LOWRANGE, 0.006),
    ]
    for card, tables, voltage, tolerance in specifications:
        matrix, spacings = [], []
        for table in tables:
            _, suite, grid = ordinary_suite(inputs, table)
            matrix.append([efficiencyPeak(list(suite[w]["rows"].values()))["mhz"] for w in WORKLOADS])
            spacings.extend(np.diff(grid).tolist())
        bracket = floor_bracket(inputs, voltage, tolerance)
        result = floor_distance(matrix, bracket["last_flat"], statistics.median(spacings), resamples, seed)
        # Reproduce the claim helper's mean-within-workload then median convention.
        if not math.isclose(result["median"], cc._medianSuiteOptimum(tables), abs_tol=1e-9):
            raise ValueError(f"{card}: optimum disagrees with the claim helper")
        result.update(card=card, bracket=bracket, spacing_range=[min(spacings), max(spacings)])
        if bracket["first_above"] is not None:
            result["distance_to_first_above"] = result["median"] - bracket["first_above"]
            result["floor_bracket_distance"] = [result["distance_to_first_above"], result["distance"]]
            result["bracket_workload_interval"] = [
                result["workload_interval"][0] - (bracket["first_above"] - bracket["last_flat"]),
                result["workload_interval"][1]]
        floors.append(result)
    if floor_bracket(inputs, cc._VOLT_5060_STOCK_R2) != {
            **floors[0]["bracket"], "source": cc._VOLT_5060_STOCK_R2}:
        raise ValueError("5060 Ti voltage-floor replicates disagree")

    abba = {label: ordinary_suite(inputs, table)[0] for label, table in
            (("A1", cc.ABBA_A1), ("A2", cc.ABBA_A2), ("B1", cc.ABBA_B1), ("B2", cc.ABBA_B2))}
    manifest_path = inputs.path(RERUN / "rerun15-inputs.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    def role_path(role):
        return inputs.path(RERUN / manifest["sweeps"][role]["sweep"])
    clean = {}
    clean_suites = {}
    for arm in ("stock-open", "stock-close", "rungB", "rungC"):
        paths = {w: role_path(f"{arm}-{w}") for w in WORKLOADS}
        suite, grid = read_suite(paths)
        clean[arm] = {w: suite[w]["optimum"] for w in WORKLOADS}
        clean_suites[arm] = suite
    drift = stock_return(clean_suites["stock-open"], clean_suites["stock-close"], grid)
    refs5060 = {
        "ABBA full-tune A1/A2 (not stock)": change_vector(abba["A1"], abba["A2"]),
        "ABBA split B1/B2 (not stock)": change_vector(abba["B1"], abba["B2"]),
        "clean factory-stock opening/closing": change_vector(clean["stock-open"], clean["stock-close"]),
    }
    # Also supply a genuine historical within-session factory-stock pair.
    r4 = ordinary_suite(inputs, cc.SUITE_R4_SWEEPS)[0]
    r5 = ordinary_suite(inputs, cc.SUITE_R5_SWEEPS)[0]
    refs5060["factory-stock r4/r5, same session"] = change_vector(r4, r5)
    edits = []
    def add(label, card, before, after, references, status, baseline):
        result = compare_edit(before, after, references)
        result.update(label=label, card=card, status=status, baseline=baseline)
        edits.append(result)
    for first, last in (("B1", "A1"), ("B2", "A2")):
        add(f"ABBA floor edit {last} against {first}", "RTX 5060 Ti", abba[first], abba[last],
            refs5060, "post hoc; two curve regions differ", f"split {first}; memory/power matched")
    repair = ordinary_suite(inputs, cc.REPAIR_P2T1)[0]
    stock9 = ordinary_suite(inputs, cc.BRACKET_STOCK)[0]
    add("original upper-curve control P2", "RTX 5060 Ti", stock9, repair, refs5060,
        "registered; stock comparison also changes memory and power limit", "same-session factory stock r9")
    for first in ("B1", "B2"):
        add(f"original P2 control vs split {first}", "RTX 5060 Ti", abba[first], repair, refs5060,
            "cross-session sensitivity; memory/power matched", f"split {first}")
    # Section 10 is a split-profile control, not a factory-stock contrast.
    for control_dir in (DATA / "5060ti-control10-20260925", DATA / "5060ti-control10r-20261001"):
        control_paths = score_control10.find_files(control_dir)
        for paths in control_paths.values():
            for path in paths.values():
                inputs.path(path)
        control = score_control10.score(control_dir)
        own_refs = {"section10 P5 opening/closing (not stock)":
                    change_vector(control["optima"]["p5a"], control["optima"]["p5b"])}
        add(f"section10 upper-curve control P2 ({control_dir.name})", "RTX 5060 Ti", control["optima"]["p5a"],
            control["optima"]["p2"], {**refs5060, **own_refs},
            f"{control['verdict']}; collected under desktop load", "same-session split P5 opening")
    for rung, directory in (("rungB", DATA / "5060ti-rungB-suite-20260923"),
                             ("rungC", DATA / "5060ti-rungC-suite-20260926")):
        original = ordinary_suite(inputs, unique_paths(inputs, directory, f"5060ti-{rung}-suite"))[0]
        add(f"original {rung} vs split B1", "RTX 5060 Ti", abba["B1"], original, refs5060,
            "cross-session baseline; split is memory/power matched; original desktop load", "ABBA split B1")
        add(f"original {rung} vs stock r9", "RTX 5060 Ti", stock9, original, refs5060,
            "cross-session; memory/power differ; original desktop load", "factory stock r9")
        add(f"clean {rung}", "RTX 5060 Ti", clean["stock-open"], clean[rung], refs5060,
            "registered; factory-stock contrast also changes memory/power", "clean opening stock suite (R3)")

    d_dir = DATA / cc.SESSION_D_DIR
    guard_scorer_directory(inputs, d_dir)
    main, repeat = cc.sessionD("main"), cc.sessionD("replicate")
    d2_dir = DATA / "rtx3070ti-sessiond2-20260925"
    guard_scorer_directory(inputs, d2_dir)
    d2 = {}
    for run in ("stock-7", "edit2-8", "stock-9"):
        paths = unique_paths(inputs, d2_dir, f"rtx3070ti-sessiond-{run}")
        for path in paths.values():
            inputs.path(path.with_name(path.stem + "_voltage.csv"))
        if run != "edit2-8":
            d2[run] = ordinary_suite(inputs, paths)[0]
        else:
            saved = score_session_d.REGISTRATION
            try:
                score_session_d.REGISTRATION = dataclasses.replace(saved,
                    clipped_targets=(1605, 1710, 1815, 1920, 2025, 2130))
                d2[run] = {}
                for w, path in paths.items():
                    options, clipped = score_session_d.collapse_control(loadSweep(path))
                    best = efficiencyPeak(options)
                    d2[run][w] = saved.clipped_achieved_mhz if best is clipped else best["target"]
            finally:
                score_session_d.REGISTRATION = saved
    refs3070 = {
        "D stock-1/stock-4": change_vector(main["optima"]["stock-1"], main["optima"]["stock-4"]),
        "D stock-4/stock-6 (shared stock-4)": change_vector(repeat["optima"]["stock-4"], repeat["optima"]["stock-6"]),
        "D2 stock-7/stock-9 (shifted grid)": change_vector(d2["stock-7"], d2["stock-9"]),
    }
    for label, source, before, after, status in (
            ("D floor edit", main, "stock-1", "edit1-2", main["4a"]),
            ("D floor repeat", repeat, "stock-4", "edit1-5", repeat["8a"]),
            ("D upper-curve control", main, "stock-1", "edit2-3", main["4b"])):
        add(label, "RTX 3070 Ti", source["optima"][before], source["optima"][after], refs3070,
            status, f"same-session {before}; clipped bin handled by existing scorer")
    add("D2 upper-curve control repeat", "RTX 3070 Ti", d2["stock-7"], d2["edit2-8"], refs3070,
        "NOT SCOREABLE; descriptive changed grid and collapsed 1500 MHz bin", "same-session stock-7")
    edits[-1]["exact"] = {}
    edits[-1]["rank_tail"] = None

    e2_dir = DATA / cc.SESSION_E2_DIR
    guard_scorer_directory(inputs, e2_dir)
    e2 = cc.sessionE("e2")
    refs2060 = {"E2 stock-4/stock-6": change_vector(e2["optima"]["stock-4"], e2["optima"]["stock-6"])}
    add("E2 whole-curve offset", "RTX 2060 Super", e2["optima"]["stock-4"], e2["optima"]["offset-5"],
        refs2060, e2["4c"], "same-session stock-4")

    stock = {r["target"]: r for r in loadSweep(role_path("stock-open-membw"))}
    curve = {r["target"]: r for r in loadSweep(role_path("curve3-membw"))}
    clean_gap = bandwidth_gap(stock, curve, resamples, seed)
    for tag in ("stock-membw", "curve3-membw"):
        inputs.path(cc._memmatched(tag))
    loaded_gap = bandwidth_gap(cc._memmatchedRows("stock-membw"), cc._memmatchedRows("curve3-membw"), resamples, seed)
    return {"floors": floors, "edits": edits, "bandwidth": {"clean": clean_gap, "loaded": loaded_gap},
            "references": {"RTX 5060 Ti": {k: sum(v.values()) for k, v in refs5060.items()},
                           "RTX 3070 Ti": {k: sum(v.values()) for k, v in refs3070.items()},
                           "RTX 2060 Super": {k: sum(v.values()) for k, v in refs2060.items()}},
            "clean_stock_worst_drift_pct": max(drift.values()),
            "sources": sorted(inputs.used), "seed": seed, "resamples": resamples}


def format_floor(result):
    lo, hi = result["workload_interval"]
    clo, chi = result["crossed_interval"]
    return (f"{result['card']}: N=1 chip, {result['workloads']} workloads and {result['suites']} suites; "
            f"median achieved optimum {result['median']:.2f} MHz minus last floor point "
            f"{result['floor']:.2f} MHz is {result['distance']:+.2f} MHz "
            f"({result['steps']:+.3f} nominal grid steps of {result['step']:g} MHz); "
            f"the 95% workload bootstrap interval is [{lo:+.2f}, {hi:+.2f}] MHz "
            f"([{lo/result['step']:+.3f}, {hi/result['step']:+.3f}] steps), and the crossed "
            f"suite/workload interval is [{clo:+.2f}, {chi:+.2f}] MHz "
            f"([{clo/result['step']:+.3f}, {chi/result['step']:+.3f}] steps).")


def format_edit(result):
    refs = "; ".join(f"{k}: {v} of {result['n']}" for k, v in result["reference_counts"].items())
    tests = "; ".join(f"{k}: p={v['p']:.6f}, discordant N={v['discordant']} "
                      f"({v['more']} treatment-only, {v['less']} reference-only)"
                      for k, v in result["exact"].items())
    inference = (f"The descriptive upper rank tail is {result['rank_tail']:.6f} with "
                 f"N={len(result['reference_counts'])} reference pairs. The one-sided exact "
                 f"conditional tests are {tests}." if result['rank_tail'] is not None
                 else "No p-value or rank tail is assigned to this NOT SCOREABLE treatment; its count is descriptive.")
    return (f"{result['card']}, {result['label']}: N=1 chip, {result['n']} workloads, one suite per arm; "
            f"{result['count']} of {result['n']} optima change against {result['baseline']}, while "
            f"the suite median changes from {result['median_before']:g} to {result['median_after']:g} MHz. "
            f"The repeatability counts are {refs}. {inference} Status: {result['status']}.")


def format_bandwidth(label, result):
    lo, hi = result["interval"]
    return (f"The {label} bandwidth loss is {result['mean']:.3f}% mean over "
            f"N={len(result['targets'])} paired targets {result['targets']}, with a 95% paired-target "
            f"bootstrap interval [{lo:.3f}, {hi:.3f}]% and pointwise range "
            f"[{result['range'][0]:.3f}, {result['range'][1]:.3f}]%; N=1 chip, one session, "
            "one sweep per arm, and one workload (membw).")


def report(results):
    print(f"All measurements below were recomputed from unchanged committed CSVs, "
          f"using {results['resamples']} bootstrap draws and seed {results['seed']}.")
    print("The role manifest and registered scorers' JSON companions are also checked as unchanged committed inputs.")
    print("Every model has N=1 physical chip; workloads, targets and suites never increase chip N.")
    for result in results["floors"]:
        print(format_floor(result))
        bracket = result["bracket"]
        print(f"The {result['card']} measured floor bracket is last-at-floor {bracket['last_flat']:g} "
              f"and first-above {bracket['first_above']} MHz; nominal grid spacing ranges from "
              f"{result['spacing_range'][0]:g} to {result['spacing_range'][1]:g} MHz, N=1 chip.")
        if "floor_bracket_distance" in result:
            low, high = result["floor_bracket_distance"]
            print(f"For N=1 {result['card']} chip, the signed distance to an endpoint inside that "
                  f"measured bracket ranges from {low:+.2f} to {high:+.2f} MHz "
                  f"({low/result['step']:+.3f} to {high/result['step']:+.3f} steps); this is a "
                  "telemetry-resolution bracket, not a confidence interval.")
    print("These percentile intervals resample this selected workload set and, for the 5060 Ti, "
          "five suite rows (r2-r6, including a same-session r4/r5 pair). They condition on the observed "
          "floor and sampled efficiency argmax; they do not estimate floor uncertainty, sub-grid "
          "optima, independent-session precision, or chip-population uncertainty. A narrow or zero-width "
          "interval on a 105-158 MHz grid cannot resolve the continuous optimum. The 2060 Super's "
          "strict and 6 mV readings are sensitivity definitions, not two confirmed floor ends.")
    for result in results["edits"]:
        print(format_edit(result))
    print("All exact tails are unadjusted sensitivity calculations. Their null requires independent "
          "discordant workloads with equiprobable treatment-only and reference-only changes. Kernel "
          "families share this chip; labels were not randomized, reference pairs can share suites, "
          "and sessions/configurations differ. Therefore these tails do not establish causal "
          "significance. Each reference pair is tested separately, never pooled or selected by "
          "its smallest p-value. Rank tails require exchangeable suite pairs to be p-values and "
          "are descriptive here. ABBA repeats full-tune/split profiles, not factory stock.")
    for label, result in results["bandwidth"].items():
        print(format_bandwidth(label, result))
    print("The bandwidth intervals describe variation across these five fixed target points; "
          "targets are not independent replicate sessions. They do not quantify measurement "
          "repeatability or a population effect. The loaded and clean sessions remain separate.")
    print(f"The clean stock suite's worst-workload median absolute matched-target throughput drift "
          f"is {results['clean_stock_worst_drift_pct']:.6f}%; N=1 chip, two stock suites and 12 workloads.")
    print("No raw HWiNFO logs, live hardware, new collection, registered gates, or causal mediation "
          "were verified by this analysis. Existing scorer verdicts are retained where stated.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    try:
        results = build_results(args.resamples, args.seed)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"Uncertainty analysis cannot run: {exc}\n")
    report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
