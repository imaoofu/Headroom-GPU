"""Job 50 fixtures use temporary CSVs, unequal achieved clocks and sparse changes."""
import contextlib
import csv
import io
import itertools
import math
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

import paper_uncertainty as pu
from analyze_sweep import loadSweep
from score_control10 import read_suite, WORKLOADS


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def refused(function, message):
    try:
        function()
    except ValueError:
        check(True, message)
    else:
        check(False, message)


def fixture(root, shifted=False):
    grid = list(range(1000, 2300, 100))
    paths = {}
    for index, workload in enumerate(WORKLOADS):
        optimum = 1000 if index < 6 else 1100
        # One workload crossing the middle order statistic moves the median.
        if shifted and index == 5:
            optimum = 1100
        path = root / f"{workload}.csv"
        paths[workload] = path
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("target_frequency_mhz", "achieved_frequency_avg",
                "bench_throughput", "power_avg_w", "bench_ok", "power_window_applied", "lock_miss_direction"))
            writer.writeheader()
            for target in grid:
                writer.writerow(dict(target_frequency_mhz=target,
                    achieved_frequency_avg=target - (17 if shifted else 7),
                    bench_throughput=200 if target == optimum else 100, power_avg_w=100,
                    bench_ok="True", power_window_applied="True", lock_miss_direction="none"))
    return paths


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first_dir, last_dir = root / "first", root / "last"
        first_dir.mkdir()
        last_dir.mkdir()
        paths = fixture(first_dir)
        changed_paths = fixture(last_dir, shifted=True)
        before, _ = read_suite(paths)
        after, _ = read_suite(changed_paths)
        a = {w: before[w]["optimum"] for w in WORKLOADS}
        b = {w: after[w]["optimum"] for w in WORKLOADS}
        result = pu.compare_edit(a, b, {"repeat": {w: 0 for w in WORKLOADS}})
        check(result["count"] == 1 and result["median_before"] == 1050 and result["median_after"] == 1100,
              "one of twelve optima can change while the median moves fifty MHz between grid points")
        check(a[WORKLOADS[0]] == 1000 and loadSweep(paths[WORKLOADS[0]])[0]["mhz"] == 993,
              "unequal achieved clocks never replace targets in change counts")
        unchanged = {w: {**row, "optimum": a[w]} for w, row in after.items()}
        check(sum(pu.change_vector(a, {w: unchanged[w]["optimum"] for w in WORKLOADS}).values()) == 0,
              "achieved-clock drift alone does not create target-grid changes")
        matrix = [[pu.efficiencyPeak(loadSweep(paths[w]))["mhz"] for w in WORKLOADS]]
        floor = pu.floor_distance(matrix, 1060, 100, 4000)
        check(floor["median"] == 1043 and floor["distance"] == -17 and floor["steps"] == -.17,
              "floor distances use achieved clocks and retain their signed grid-step distance")
        missing = dict(paths)
        missing.pop("gemm")
        fake_inputs = type("Inputs", (), {"path": lambda self, p: p})()
        selected, _, _ = pu.ordinary_suite(fake_inputs, paths)
        check(selected == a, "the production suite adapter returns target optima even when achieved clocks differ")
        refused(lambda: pu.ordinary_suite(fake_inputs, missing), "an incomplete workload suite is refused")

    t = dict(zip("abcd", [1, 1, 1, 0]))
    r = dict(zip("abcd", [0, 0, 1, 1]))
    exact = pu.exact_change_test(t, r)
    check(exact == {"more": 2, "less": 1, "discordant": 3, "p": .5},
          "exact conditional test uses discordances and the inclusive one-sided binomial tail")
    assignments = list(itertools.product((0, 1), repeat=3))
    check(exact["p"] == sum(sum(a) >= 2 for a in assignments) / len(assignments),
          "the exact tail agrees with an independent exhaustive label-swap enumeration")
    check(pu.exact_change_test(t, t)["p"] == 1, "zero discordance produces p one")
    check(pu.exact_change_test({w: 1 for w in WORKLOADS}, {w: 0 for w in WORKLOADS})["p"] == 1/4096,
          "twelve treatment-only discordances use a denominator of 4096")
    check(pu.reference_tail(4, [4, 3, 4]) == .75, "reference rank tails include ties and the candidate itself")
    refused(lambda: pu.exact_change_test({"a": 2}, {"a": 0}), "nonbinary indicators are refused")
    refused(lambda: pu.change_vector({"a": 1}, {"b": 1}), "unpaired workload identities are refused")
    refused(lambda: pu.change_vector({"a": math.nan}, {"a": 1}), "nonfinite optima are refused")

    values = np.array([[100, 200, 300, 400], [200, 300, 400, 500]])
    result = pu.median_bootstrap(values, 3000, 42, suites=True)
    rng = np.random.default_rng(42)
    columns = rng.integers(4, size=(3000, 4))
    rows = rng.integers(2, size=(3000, 2))
    manual = [np.median([np.mean([values[s, w] for s in row_ids]) for w in col_ids])
              for row_ids, col_ids in zip(rows, columns)]
    check(result["median"] == 300 and np.allclose(result["interval"], np.quantile(manual, [.025, .975])),
          "crossed bootstrap preserves workload identity across every sampled suite")
    check(result == pu.median_bootstrap(values, 3000, 42, suites=True), "a fixed seed reproduces the full interval")
    constant = pu.median_bootstrap([[100] * 12] * 3, 100)
    check(constant["interval"] == [100, 100] and constant["suites"] == 3,
          "constant sampled optima produce a zero-width conditional interval without inventing precision")
    refused(lambda: pu.median_bootstrap([]), "empty bootstrap matrices are refused")
    refused(lambda: pu.median_bootstrap([[math.inf]]), "nonfinite bootstrap matrices are refused")
    refused(lambda: pu.median_bootstrap([[1]], 1), "too few resamples are refused")
    refused(lambda: pu.floor_distance([[1]], 1, 0), "zero grid spacing is refused")

    stock = {t: {"throughput": 100} for t in (1477, 1560, 1635, 1710, 1792, 1867, 1942)}
    curve = {t: {"throughput": 90 if 1560 <= t <= 1867 else 1} for t in stock}
    gap = pu.bandwidth_gap(stock, curve, 1000)
    check(len(gap["targets"]) == 5 and np.allclose([gap["mean"], *gap["interval"]], [10, 10, 10]),
          "bandwidth bootstrap pairs the five in-band targets and excludes outside targets")
    # Unequal denominators distinguish the mean of percentage losses from a ratio of means.
    s = {1560: {"throughput": 100}, 1867: {"throughput": 200}}
    c = {1560: {"throughput": 50}, 1867: {"throughput": 200}}
    check(pu.bandwidth_gap(s, c, 100)["mean"] == 25, "bandwidth statistic is mean paired percentage loss")
    refused(lambda: pu.bandwidth_gap(stock, {1560: {"throughput": 100}}), "mismatched target sets are refused")
    refused(lambda: pu.bandwidth_gap({1560: {"throughput": 0}}, {1560: {"throughput": 1}}),
            "zero bandwidth denominators are refused")
    with patch.object(pu.subprocess, "check_output", side_effect=[b"data/one.csv\0", b"data/one.csv\0"]):
        inputs = pu.CommittedInputs()
        refused(lambda: inputs.path(pu.ROOT / "data" / "one.csv"), "a modified committed measurement is refused")
        refused(lambda: inputs.path(pu.ROOT / "data" / "untracked.csv"), "an untracked measurement is refused")
    with patch.object(pu.subprocess, "check_output", side_effect=[b"data/one.json\0", b"data/one.json\0"]):
        inputs = pu.CommittedInputs()
        refused(lambda: inputs.path(pu.ROOT / "data" / "one.json"), "a modified scorer JSON companion is refused")
        refused(lambda: inputs.path(pu.ROOT / "data" / "untracked.json"), "an untracked scorer JSON companion is refused")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        sweep = root / "example_sweep.csv"
        sweep.touch()
        calls = []
        fake_inputs = type("Inputs", (), {"path": lambda self, p: calls.append(p)})()
        pu.guard_scorer_directory(fake_inputs, root)
        check(sweep.with_suffix(".json") in calls and sweep.with_name(sweep.stem + "_voltage.csv") in calls,
              "registered scorer input guarding includes metadata and voltage companions")

    # Integration checks pin behavior, not the paper's existing numeric claims.
    results = pu.build_results(2000)
    check(len(results["floors"]) == 5 and all(f["workloads"] == 12 for f in results["floors"]),
          "all four cards and both Turing floor definitions are reported with twelve workloads")
    check(results["floors"][0]["suites"] == 5 and results["floors"][0]["floor_bracket_distance"] == [-38, -30],
          "the 5060 Ti uses five published replicate suites and both measured floor bracket ends")
    labels = [e["label"] for e in results["edits"]]
    check(all(any(token in label for label in labels) for token in ("original rungB", "original rungC", "clean rungB", "clean rungC")),
          "both original and clean ladder rungs have explicit baseline contrasts")
    check(sum("section10" in label for label in labels) == 2,
          "both collections of the registered split-profile control are analyzed")
    d2 = next(e for e in results["edits"] if e["label"].startswith("D2"))
    check(d2["median_after"] == 1485 and "NOT SCOREABLE" in d2["status"] and not d2["exact"],
          "D2 collapses its clipped bin and retains NOT SCOREABLE without a p-value")
    check(results["edits"][-1]["status"] == "FAIL_NO_MOVEMENT", "E2 retains its registered no-median-movement failure")
    check(results["bandwidth"]["clean"]["mean"] < results["bandwidth"]["loaded"]["mean"],
          "clean and loaded bandwidth sessions are recomputed separately")
    with contextlib.redirect_stdout(io.StringIO()) as output:
        pu.report(results)
    text = output.getvalue()
    check("N=1" in text and "not estimate floor uncertainty" in text and "not randomized" in text,
          "the report states chip N, conditional interval scope and permutation assumptions")
    check(text.isascii(), "all report text is safe for the Windows cp1252 console")


if __name__ == "__main__":
    main()
