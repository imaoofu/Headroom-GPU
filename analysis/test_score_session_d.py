"""Synthetic Session D decisions; no measurement files are written or edited."""

import csv
import json
import tempfile
from pathlib import Path

from score_session_d import (REGISTRATION, collapse_control, score, score_control_replicate,
                              score_replicate)


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def fixture(root, edit1_peak=1170, control_peak=1485, stock4_factor=1.0,
            edit1_floor_end=1170, missing_voltage=False, missed_edit_workload=None,
            achieved_offset=0.0, edit1_peak_by_workload=None):
    # achieved_offset: real sweeps rarely land exactly on target. The first fixtures always did,
    # which is how an exact-equality comparison on achieved clocks passed every test.
    cfg = REGISTRATION
    for run in ("stock-1", "edit1-2", "edit2-3", "stock-4"):
        for workload in cfg.workloads:
            stem = f"synthetic_rtx3070ti-sessiond-{run}-{workload}_sweep"
            csv_path = root / f"{stem}.csv"
            metadata = {
                "session_label": f"rtx3070ti-sessiond-{run}-{workload}",
                "gpu_name": "NVIDIA GeForce RTX 3070 Ti",
                "driver_version": "synthetic-driver",
                "power_limit_default_w": "290.00",
                "power_limit_enforced_w": "290.00",
                "power_limit_w": "320.00",
            }
            csv_path.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=(
                    "target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                    "power_avg_w", "bench_ok", "lock_miss_direction", "power_window_applied",
                ))
                writer.writeheader()
                for target in cfg.targets:
                    achieved = 1500 if run == "edit2-3" and target in cfg.clipped_targets else target
                    achieved -= achieved_offset
                    run_edit1_peak = (edit1_peak_by_workload or {}).get(workload, edit1_peak)
                    peak = (run_edit1_peak if run == "edit1-2" else
                            control_peak if run == "edit2-3" else 1485)
                    efficiency = 2.0 if target == peak else 1.0
                    factor = stock4_factor if run == "stock-4" else 1.0
                    writer.writerow({
                        "target_frequency_mhz": target,
                        "achieved_frequency_avg": achieved,
                        "bench_throughput": efficiency * 100 * factor,
                        "power_avg_w": 100,
                        "bench_ok": "True",
                        "lock_miss_direction": "none",
                        "power_window_applied": "True",
                    })
            if missing_voltage and run == "edit1-2" and workload == "gemm":
                continue
            voltage_path = csv_path.with_name(csv_path.stem + "_voltage.csv")
            with voltage_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=(
                    "target", "achieved", "voltage", "sampleCount",
                ))
                writer.writeheader()
                for target in cfg.targets:
                    achieved = 1500 if run == "edit2-3" and target in cfg.clipped_targets else target
                    achieved -= achieved_offset
                    floor_end =(1485 if run == "edit1-2" and workload == missed_edit_workload
                                 else edit1_floor_end if run == "edit1-2" else
                                 cfg.clipped_targets[-1] if run == "edit2-3" else 1485)
                    writer.writerow({
                        "target": target,
                        "achieved": achieved,
                        "voltage": 0.812 if target <= floor_end else 0.831,
                        "sampleCount": 25,
                    })


def evaluate(**kwargs):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture(root, **kwargs)
        return score(root)


def main():
    passed = evaluate()
    check(passed["eligibility"] == "VALID", "synthetic pass is scoreable")
    check(passed["medians"]["edit1-2"] == 1170, "Edit 1 median uses target-grid optima")

    # Added at review 2026-09-22. Both cases scored wrongly in the first version.
    offset = evaluate(achieved_offset=0.6)
    check(offset["eligibility"] == "VALID" and offset["joint"] == "CAUSAL_CLAIM_REPLICATES_ON_SECOND_CHIP",
          "a 0.6 MHz achieved-clock offset does not change the verdict")
    split = evaluate(edit1_peak_by_workload={name: (1170 if i < 6 else 1275)
                                             for i, name in enumerate(REGISTRATION.workloads)})
    check(split["medians"]["edit1-2"] == 1222.5 and split["4a"] == "PASS",
          "an even 1170/1275 split has median 1222.5, inside the registered range, and passes")
    check(passed["4a"] == "PASS" and passed["4b"] == "PASS",
          "both registered predictions pass")
    check(passed["joint"] == "CAUSAL_CLAIM_REPLICATES_ON_SECOND_CHIP",
          "pass verdict requires manipulation and control")
    check(all(bin_row["count"] == 6 for bin_row in passed["clipped_bins"].values()),
          "six clipped targets collapse to one bin per workload")
    check(passed["floors"]["stock-1"]["top_mhz"] == 1485
          and passed["floors"]["edit1-2"]["top_mhz"] == 1170
          and passed["floors"]["edit2-3"]["top_mhz"] == 1500,
          "voltage extracts determine each floor top")
    check(passed["floors"]["edit1-2"]["first_above_mhz"] == 1275,
          "voltage extracts locate the first rise after Edit 1")

    rows = [{"target": target, "mhz": 1500 if target in REGISTRATION.clipped_targets
             else target, "efficiency": 1.0} for target in REGISTRATION.targets]
    rows[-1]["efficiency"] = 9.0
    collapsed, bin_row = collapse_control(rows)
    check(len(collapsed) == 8 and bin_row["efficiency"] == 1.0,
          "one noisy clipped row cannot win by maximum-of-six selection")

    failed = evaluate(edit1_peak=1485)
    check(failed["4a"] == "FAIL_NO_DOWNWARD_MOVEMENT" and failed["4b"] == "PASS",
          "unchanged Edit 1 optimum fails registered prediction")
    check(failed["joint"] == "CAUSAL_CLAIM_REFUTED_ON_SECOND_CHIP",
          "unchanged Edit 1 gets refutation verdict")

    moved_control = evaluate(control_peak=1170)
    check(moved_control["4a"] == "PASS" and moved_control["4b"] == "FAIL",
          "moved control fails negative control")
    check(moved_control["joint"] == "CONTROL_ALSO_MOVES_ATTRIBUTION_FAILS",
          "moved control changes the attribution verdict")

    both_fail = evaluate(edit1_peak=1485, control_peak=1170)
    check(both_fail["joint"] == "BOTH_PREDICTIONS_FAIL",
          "both failures are distinguished from the control-also-moves case")

    partial_move = evaluate(edit1_peak=1380)
    check(partial_move["4a"] == "FAIL_OTHER_DOWNWARD_BIN"
          and partial_move["joint"] == "EDIT1_MOVED_DOWN_OUTSIDE_REGISTERED_BINS",
          "unpredicted downward movement is reported without a no-movement claim")

    drift = evaluate(stock4_factor=1.03)
    check(drift["eligibility"] == "DRIFT_OR_BASELINE_MISMATCH"
          and drift["4a"] == "NOT_SCOREABLE", "stock return failure blocks effect verdict")

    no_edit = evaluate(edit1_floor_end=1485)
    check(no_edit["eligibility"] == "CURVE_EDIT_NOT_VERIFIED",
          "unchanged load floor cannot support a causal verdict")
    one_missed_edit = evaluate(missed_edit_workload="gemm")
    check(one_missed_edit["eligibility"] == "CURVE_EDIT_NOT_VERIFIED",
          "one unmodified workload is not hidden by a suite median")

    try:
        evaluate(missing_voltage=True)
    except ValueError as exc:
        check("missing companion file" in str(exc), "missing voltage extract is rejected")
    else:
        check(False, "missing voltage extract is rejected")

    replicate_checks()
    control_replicate_checks()


def replicate_fixture(root, edit_peak=1170, stock6_peak=1485, stock6_factor=1.0,
                      edit_floor_end=1170, edit_peak_by_workload=None, achieved_offset=0.4):
    """stock-4, edit1-5 and stock-6 for REGISTERED-PREDICTIONS 8a, written before any 8a data
    existed (2026-09-24). Achieved clocks sit 0.4 MHz off target, as real ones do."""
    cfg = REGISTRATION
    for run in ("stock-4", "edit1-5", "stock-6"):
        for workload in cfg.workloads:
            stem = f"synthetic_rtx3070ti-sessiond-{run}-{workload}_sweep"
            csv_path = root / f"{stem}.csv"
            csv_path.with_suffix(".json").write_text(json.dumps({
                "session_label": f"rtx3070ti-sessiond-{run}-{workload}",
                "gpu_name": "NVIDIA GeForce RTX 3070 Ti", "driver_version": "synthetic-driver",
                "power_limit_default_w": "290.00", "power_limit_enforced_w": "290.00",
                "power_limit_w": "320.00"}), encoding="utf-8")
            if run == "edit1-5":
                peak = (edit_peak_by_workload or {}).get(workload, edit_peak)
            else:
                peak = stock6_peak if run == "stock-6" else 1485
            factor = stock6_factor if run == "stock-6" else 1.0
            floor_end = edit_floor_end if run == "edit1-5" else 1485
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=(
                    "target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                    "power_avg_w", "bench_ok", "lock_miss_direction", "power_window_applied"))
                writer.writeheader()
                for target in cfg.targets:
                    writer.writerow({"target_frequency_mhz": target,
                                     "achieved_frequency_avg": target - achieved_offset,
                                     "bench_throughput": (2.0 if target == peak else 1.0) * 100 * factor,
                                     "power_avg_w": 100, "bench_ok": "True",
                                     "lock_miss_direction": "none", "power_window_applied": "True"})
            with csv_path.with_name(stem + "_voltage.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("target", "achieved", "voltage", "sampleCount"))
                writer.writeheader()
                for target in cfg.targets:
                    writer.writerow({"target": target, "achieved": target - achieved_offset,
                                     "voltage": 0.812 if target <= floor_end else 0.831,
                                     "sampleCount": 25})


def evaluate_replicate(**kwargs):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        replicate_fixture(root, **kwargs)
        return score_replicate(root)


def replicate_checks():
    """REGISTERED-PREDICTIONS 8a, every outcome it names."""
    passed = evaluate_replicate()
    check(passed["8a"] == "PASS" and passed["medians"]["edit1-5"] == 1170,
          "8a: an edit1-5 median of 1170 passes")
    split = evaluate_replicate(edit_peak_by_workload={name: (1170 if i < 6 else 1275)
                                                      for i, name in enumerate(REGISTRATION.workloads)})
    check(split["medians"]["edit1-5"] == 1222.5 and split["8a"] == "PASS",
          "8a: an even 1170/1275 split (median 1222.5) is inside the registered range")
    unmoved = evaluate_replicate(edit_peak=1485)
    check(unmoved["8a"] == "FAIL_NO_MOVEMENT",
          "8a: a median at stock-4's is no movement and counts against the replication")
    elsewhere = evaluate_replicate(edit_peak=1380)
    check(elsewhere["8a"] == "FAIL_OTHER_DOWNWARD_BIN",
          "8a: a downward move outside 1170-1275 is not a pass")
    moved_stock = evaluate_replicate(stock6_peak=1380)
    check(moved_stock["8a"] == "NOT_SCOREABLE"
          and "stock-6 median" in moved_stock["not_scoreable_reasons"][0],
          "8a: a stock-6 median unlike stock-4's makes it NOT SCOREABLE, not a failure")
    drifted = evaluate_replicate(stock6_factor=1.02)
    check(drifted["8a"] == "NOT_SCOREABLE" and "above 1.5%" in drifted["not_scoreable_reasons"][0],
          "8a: a 2% stock-4 to stock-6 change makes it NOT SCOREABLE")
    kept = evaluate_replicate(stock6_factor=1.01)
    check(kept["8a"] == "PASS", "8a: a 1% stock change is within the 1.5% limit")
    no_edit = evaluate_replicate(edit_floor_end=1485)
    check(no_edit["8a"] == "NOT_SCOREABLE" and not no_edit["edit1_floor_ok"],
          "8a: an unedited floor on edit1-5 makes it NOT SCOREABLE")
    # After import all six runs share one directory: each mode must read only its own runs.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture(root)
        stock4 = sorted(root.glob("*sessiond-stock-4-*"))
        for path in stock4:
            path.unlink()
        replicate_fixture(root)
        both = score(root)
        again = score_replicate(root)
    check(both["joint"] == "CAUSAL_CLAIM_REPLICATES_ON_SECOND_CHIP" and again["8a"] == "PASS",
          "4a/4b and 8a score correctly from one directory holding all six runs")


def control_fixture(root, control_peak=1485, stock9_peak=1485, stock7_peak=1485, stock9_factor=1.0,
                    control_floor_end=None, achieved_offset=0.4, control_peak_by_workload=None):
    """stock-7, edit2-8 and stock-9 for REGISTERED-PREDICTIONS 8d, written before any Session D2
    data existed (2026-09-25). Edit 2's six high targets clip to ~1500 MHz and read on the floor."""
    cfg = REGISTRATION
    for run in ("stock-7", "edit2-8", "stock-9"):
        for workload in cfg.workloads:
            stem = f"synthetic_rtx3070ti-sessiond-{run}-{workload}_sweep"
            csv_path = root / f"{stem}.csv"
            csv_path.with_suffix(".json").write_text(json.dumps({
                "session_label": f"rtx3070ti-sessiond-{run}-{workload}",
                "gpu_name": "NVIDIA GeForce RTX 3070 Ti", "driver_version": "synthetic-driver",
                "power_limit_default_w": "290.00", "power_limit_enforced_w": "290.00",
                "power_limit_w": "320.00"}), encoding="utf-8")
            if run == "edit2-8":
                peak = (control_peak_by_workload or {}).get(workload, control_peak)
            else:
                peak = stock9_peak if run == "stock-9" else stock7_peak
            factor = stock9_factor if run == "stock-9" else 1.0
            if run == "edit2-8":
                floor_end = cfg.clipped_targets[-1] if control_floor_end is None else control_floor_end
            else:
                floor_end = 1485
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=(
                    "target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                    "power_avg_w", "bench_ok", "lock_miss_direction", "power_window_applied"))
                writer.writeheader()
                for target in cfg.targets:
                    achieved = 1500 if run == "edit2-8" and target in cfg.clipped_targets else target
                    best = (target in cfg.clipped_targets) if peak == "clipped" else (target == peak)
                    writer.writerow({"target_frequency_mhz": target,
                                     "achieved_frequency_avg": achieved - achieved_offset,
                                     "bench_throughput": (2.0 if best else 1.0) * 100 * factor,
                                     "power_avg_w": 100, "bench_ok": "True",
                                     "lock_miss_direction": "none", "power_window_applied": "True"})
            with csv_path.with_name(stem + "_voltage.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("target", "achieved", "voltage", "sampleCount"))
                writer.writeheader()
                for target in cfg.targets:
                    achieved = 1500 if run == "edit2-8" and target in cfg.clipped_targets else target
                    writer.writerow({"target": target, "achieved": achieved - achieved_offset,
                                     "voltage": 0.812 if target <= floor_end else 0.831,
                                     "sampleCount": 25})


def evaluate_control(**kwargs):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        control_fixture(root, **kwargs)
        return score_control_replicate(root)


def control_replicate_checks():
    """REGISTERED-PREDICTIONS 8d, every outcome it names."""
    held = evaluate_control()
    check(held["8d"] == "PASS" and held["medians"]["edit2-8"] == 1485,
          "8d: a control median of 1485 passes")
    # All six clipped rows best: the bin is their MEDIAN, so one high row alone would not win it.
    clipped = evaluate_control(control_peak="clipped")
    check(clipped["8d"] == "PASS" and clipped["medians"]["edit2-8"] == 1500
          and all(b["count"] == 6 for b in clipped["clipped_bins"].values()),
          "8d: the six clipped targets are one ~1500 MHz bin, which is inside 1485-1500")
    split = evaluate_control(control_peak_by_workload={name: (1380 if i < 6 else 1485)
                                                       for i, name in enumerate(REGISTRATION.workloads)})
    check(split["medians"]["edit2-8"] == 1432.5 and split["8d"] == "FAIL",
          "8d: a 4b-style six-six split at 1432.5 fails again")
    moved = evaluate_control(control_peak=1170)
    check(moved["8d"] == "FAIL", "8d: a control that moves down fails")
    wrong_base = evaluate_control(stock7_peak=1380, stock9_peak=1380)
    check(wrong_base["8d"] == "NOT_SCOREABLE" and "not the registered" in wrong_base["not_scoreable_reasons"][0],
          "8d: a stock-7 median other than 1485 makes it NOT SCOREABLE")
    unreturned = evaluate_control(stock9_peak=1380)
    check(unreturned["8d"] == "NOT_SCOREABLE", "8d: stock-9 unlike stock-7 makes it NOT SCOREABLE")
    drifted = evaluate_control(stock9_factor=1.02)
    check(drifted["8d"] == "NOT_SCOREABLE", "8d: a 2% stock return makes it NOT SCOREABLE")
    no_clip = evaluate_control(control_floor_end=1485)
    check(no_clip["8d"] == "NOT_SCOREABLE" and not no_clip["control_floor_ok"],
          "8d: an Edit 2 that did not hold its clipped targets on the floor is NOT SCOREABLE")
    # Sessions D and D2 will share one data directory: each mode must read only its own runs.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture(root)
        replicate_fixture(root)
        for path in root.glob("synthetic_rtx3070ti-sessiond-stock-4-*"):
            path.unlink()
        replicate_fixture(root)
        control_fixture(root)
        four = score(root)
        eight_a = score_replicate(root)
        eight_d = score_control_replicate(root)
    check(four["joint"] == "CAUSAL_CLAIM_REPLICATES_ON_SECOND_CHIP" and eight_a["8a"] == "PASS"
          and eight_d["8d"] == "PASS", "4a/4b, 8a and 8d score from one directory holding all nine runs")


if __name__ == "__main__":
    main()
