"""Synthetic section 10 decisions (P5 -> P2 -> P5); no measurement files are written or edited."""

import csv
import tempfile
from pathlib import Path

from score_control10 import LEGS, WORKLOADS, score

TARGETS = [1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090]


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def fixture(root, peaks=None, factor=None):
    """peaks[leg][workload] -> target with the best efficiency (default 1545 everywhere);
    factor[leg] scales throughput, which moves the P5 return without moving any optimum."""
    for leg in LEGS:
        for workload in WORKLOADS:
            peak = ((peaks or {}).get(leg) or {}).get(workload, 1545)
            scale = (factor or {}).get(leg, 1.0)
            path = root / f"20260925-000000_5060ti-ctrl10-{leg}-{workload}_sweep.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=(
                    "target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                    "power_avg_w", "bench_ok", "lock_miss_direction", "power_window_applied"))
                writer.writeheader()
                for target in TARGETS:
                    writer.writerow({"target_frequency_mhz": target,
                                     "achieved_frequency_avg": target - 0.4,
                                     "bench_throughput": (2.0 if target == peak else 1.0) * 100 * scale,
                                     "power_avg_w": 100, "bench_ok": "True",
                                     "lock_miss_direction": "none", "power_window_applied": "True"})


def evaluate(**kwargs):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture(root, **kwargs)
        return score(root)


def main():
    held = evaluate()
    check(held["verdict"] == "PASS" and held["moved"] == [], "an unmoved control passes with 0 of 12 moved")

    four = {name: 1702 for name in WORKLOADS[:4]}
    leaky = evaluate(peaks={"p2": four})
    check(leaky["verdict"] == "PASS" and len(leaky["moved"]) == 4,
          "a control whose median holds while 4 of 12 move passes, and the 4 are reported")

    six = {name: 1395 for name in WORKLOADS[:6]}
    split = evaluate(peaks={"p2": six})
    check(split["medians"]["p2"] == 1470 and split["verdict"] == "FAIL",
          "a six-six split moves the median (1470) and fails")

    moved = evaluate(peaks={"p2": {name: 1702 for name in WORKLOADS}})
    check(moved["verdict"] == "FAIL", "a control that moves every workload fails")

    unreturned = evaluate(peaks={"p5b": {name: 1395 for name in WORKLOADS}})
    check(unreturned["verdict"] == "NOT_SCOREABLE", "P5 brackets with different medians are NOT SCOREABLE")

    drifted = evaluate(factor={"p5b": 1.02})
    check(drifted["verdict"] == "NOT_SCOREABLE" and "above 1.5%" in drifted["not_scoreable_reasons"][0],
          "a 2% P5 return is NOT SCOREABLE")
    kept = evaluate(factor={"p5b": 1.01})
    check(kept["verdict"] == "PASS", "a 1% P5 return is inside the limit")

    only_one_bracket = {name: 1702 for name in WORKLOADS[:2]}
    partial = evaluate(peaks={"p2": only_one_bracket, "p5a": only_one_bracket})
    check(partial["moved"] == [], "a P2 optimum equal to either P5 optimum is not counted as moved")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture(root)
        (root / "20260925-000000_5060ti-ctrl10-p2-gemm_sweep.csv").unlink()
        try:
            score(root)
        except ValueError as exc:
            check("missing workload sweeps: gemm" in str(exc), "a missing sweep is refused by name")
        else:
            check(False, "a missing sweep is refused by name")


if __name__ == "__main__":
    main()
