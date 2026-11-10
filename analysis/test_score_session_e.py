"""Synthetic Session E decisions for 4c and 4d; no measurement files are written or edited.

The 4d cases read the committed ascending reference sweep, so they also check that the reference
itself gives the registered minimum {975, 1005}.
"""

import csv
import json
import tempfile
from pathlib import Path

import score_session_e
from score_session_e import E2_REGISTRATION, REGISTRATION, score_4c, score_4d

ASCENDING = {900: 0.644, 915: 0.644, 945: 0.637, 960: 0.637, 975: 0.631, 1005: 0.631,
             1020: 0.637, 1035: 0.637, 1065: 0.644, 1080: 0.650, 1095: 0.650, 1125: 0.656,
             1140: 0.662}


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def write_sweep(csv_path, metadata, targets, peak, factor=1.0, achieved_offset=0.0):
    csv_path.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "target_frequency_mhz", "achieved_frequency_avg", "bench_throughput", "power_avg_w",
            "temperature_avg_c", "bench_ok", "lock_miss_direction", "power_window_applied"))
        writer.writeheader()
        for target in targets:
            writer.writerow({"target_frequency_mhz": target,
                             "achieved_frequency_avg": target - achieved_offset,
                             "bench_throughput": (2.0 if target == peak else 1.0) * 100 * factor,
                             "power_avg_w": 100, "temperature_avg_c": 55.0, "bench_ok": "True",
                             "lock_miss_direction": "none", "power_window_applied": "True"})


def write_voltage(csv_path, readings, achieved_offset=0.0):
    with csv_path.with_name(csv_path.stem + "_voltage.csv").open(
            "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("target", "achieved", "voltage", "sampleCount"))
        writer.writeheader()
        for target, voltage in readings.items():
            writer.writerow({"target": target, "achieved": target - achieved_offset,
                             "voltage": voltage, "sampleCount": 60})


def metadata_for(label, power_max="185.00", **extra):
    return {"session_label": label, "gpu_name": "NVIDIA GeForce RTX 2060 SUPER",
            "driver_version": "synthetic-driver", "power_limit_default_w": "175.00",
            "power_limit_enforced_w": "175.00", "power_limit_w": power_max, **extra}


def stock_voltage(target):
    return 0.644 if target <= 1065 else 0.694


def offset_voltage(target):
    # -165 MHz: 1065 reads stock's 1230 (681.2 mV), 1275 reads stock's 1440 (743.8 mV).
    return 0.681 if target <= 1065 else 0.744


def suite_fixture(root, edit_peak=855, edit_peak_by_workload=None, stock_peak=1065,
                  stock3_peak=None, stock3_factor=1.0, upper_only_workload=None,
                  edit_live_in_stock=False, achieved_offset=0.0, power_max="185.00"):
    cfg = score_session_e.REGISTRATION
    first, treated, last = cfg.runs
    for run in cfg.runs:
        for workload in cfg.workloads:
            label = f"{cfg.label_prefix}{run}-{workload}"
            csv_path = root / f"synthetic_{label}_sweep.csv"
            if run == treated:
                peak = (edit_peak_by_workload or {}).get(workload, edit_peak)
            elif run == last and stock3_peak is not None:
                peak = stock3_peak
            else:
                peak = stock_peak
            write_sweep(csv_path, metadata_for(label, power_max),
                        cfg.targets, peak, stock3_factor if run == last else 1.0,
                        achieved_offset)
            if run == treated:
                # upper_only: an offset that moved only the points the editor exposes (>= 700 mV)
                # would leave locked 1065 on the stock 0.644 V point.
                readings = {t: (stock_voltage(t) if workload == upper_only_workload and t <= 1065
                                else offset_voltage(t)) for t in cfg.targets}
            elif run == first and edit_live_in_stock:
                readings = {t: offset_voltage(t) for t in cfg.targets}
            else:
                readings = {t: stock_voltage(t) for t in cfg.targets}
            write_voltage(csv_path, readings, achieved_offset)


def evaluate_4c(**kwargs):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        suite_fixture(root, **kwargs)
        return score_4c(root)


def evaluate_4d(voltages=None, order="descending", label=REGISTRATION.e1_label):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        readings = {**ASCENDING, **(voltages or {})}
        csv_path = root / f"20990101-000000_{label}_sweep.csv"
        write_sweep(csv_path, metadata_for(label, sweep_order=order),
                    sorted(readings, reverse=True), 1005)
        write_voltage(csv_path, readings)
        return score_4d(root)


def raises(function, **kwargs):
    try:
        function(**kwargs)
    except ValueError:
        return True
    return False


def main():
    cfg = REGISTRATION
    workloads = cfg.workloads

    # --------------------------------------------------------------- 4c
    passed = evaluate_4c()
    check(passed["4c"] == "PASS" and passed["medians"]["offset-2"] == 855,
          "the offset moving every optimum to 855 MHz passes")
    check(passed["baseline_matches_registration"] and passed["moved_down_count"] == 12,
          "the synthetic stock median is the registered 1065, and all 12 moved down")
    check(evaluate_4c(edit_peak=960)["4c"] == "PASS", "a median of 960, one step above, passes")
    split = evaluate_4c(edit_peak_by_workload={n: 855 if i < 6 else 960
                                               for i, n in enumerate(workloads)})
    check(split["medians"]["offset-2"] == 907.5 and split["4c"] == "PASS",
          "an even 855/960 split has median 907.5, inside 855-960, and passes")
    check(evaluate_4c(achieved_offset=0.6)["4c"] == "PASS",
          "a 0.6 MHz achieved-clock offset does not change the verdict")
    check(evaluate_4c(edit_peak=1065)["4c"] == "FAIL_NO_MOVEMENT",
          "an unmoved median fails as no movement")
    check(evaluate_4c(edit_peak=1170)["4c"] == "FAIL_NO_MOVEMENT",
          "an upward move fails as no movement")
    partial = evaluate_4c(edit_peak_by_workload={n: 960 if i < 6 else 1065
                                                 for i, n in enumerate(workloads)})
    check(partial["medians"]["offset-2"] == 1012.5 and partial["4c"] == "FAIL_PARTIAL",
          "a half-step move to 1012.5 is partial, not a pass")
    low_stock = evaluate_4c(stock_peak=960, edit_peak=960)
    check(low_stock["4c"] == "FAIL_NO_MOVEMENT" and not low_stock["baseline_matches_registration"],
          "with stock itself at 960, an offset suite at 960 is no movement, and the baseline is flagged")
    check(evaluate_4c(stock3_factor=1.03)["4c"] == "NOT_SCOREABLE",
          "a 3% stock drift is not scoreable")
    check(evaluate_4c(stock3_factor=1.014)["4c"] == "PASS",
          "a 1.4% stock drift is inside the 1.5% limit")
    check(evaluate_4c(stock3_peak=960)["4c"] == "NOT_SCOREABLE",
          "a closing stock median that differs from the opening one is not scoreable")
    offset_check = "offset-2 at 0.672-0.700 V at 1065 and 0.731-0.757 V at 1275 MHz"
    upper = evaluate_4c(upper_only_workload="gemm")
    check(upper["4c"] == "NOT_SCOREABLE" and not upper["checks"][offset_check],
          "a workload reading stock 0.644 V at 1065 under the offset (upper curve only) is not scoreable")
    live = evaluate_4c(edit_live_in_stock=True)
    check(live["4c"] == "NOT_SCOREABLE" and not live["checks"]["stock-1 verified at 1065 MHz"],
          "the offset left live in the opening stock suite is not scoreable")
    check(raises(evaluate_4c, power_max="200.00"), "a wrong power limit is refused")

    # ------------------------------------------------ Session E2 (Amendment 3), same rules
    score_session_e.REGISTRATION = E2_REGISTRATION
    try:
        check(E2_REGISTRATION.targets == tuple(range(855, 2011, 105)) and len(E2_REGISTRATION.targets) == 12,
              "E2 scores the fixed 12-target list 855-2010")
        e2 = evaluate_4c()
        check(e2["4c"] == "PASS" and e2["medians"]["offset-5"] == 855,
              "E2: the offset moving every optimum to 855 passes")
        check(evaluate_4c(edit_peak=1065)["4c"] == "FAIL_NO_MOVEMENT",
              "E2: an unmoved median fails as no movement")
        check(evaluate_4c(upper_only_workload="gemm")["4c"] == "NOT_SCOREABLE",
              "E2: the offset missing below 700 mV is not scoreable")
        check(evaluate_4c(stock3_factor=1.03)["4c"] == "NOT_SCOREABLE",
              "E2: a 3% stock drift is not scoreable")
    finally:
        score_session_e.REGISTRATION = REGISTRATION
    with tempfile.TemporaryDirectory() as temporary:
        # Session E's own offset suite, on its shifted 840..2100 grid, stays unscoreable.
        root = Path(temporary)
        shifted = tuple(range(840, 2101, 105))
        for run in REGISTRATION.runs:
            for workload in REGISTRATION.workloads:
                label = f"rtx2060s-sessione-{run}-{workload}"
                path = root / f"synthetic_{label}_sweep.csv"
                grid = shifted if run == "offset-2" else REGISTRATION.targets
                write_sweep(path, metadata_for(label), grid, grid[1])
                write_voltage(path, {t: stock_voltage(t) for t in grid})
        check(raises(score_4c, directory=root), "a suite on Session E's shifted 840-2100 grid is refused")

    # --------------------------------------------------------------- 4d
    holds = evaluate_4d()
    check(holds["reference_minimum"] == [975, 1005],
          "the committed ascending sweep's minimum set is the registered {975, 1005}")
    check(holds["4d"] == "HOLDS", "the ascending shape measured descending holds")
    between = evaluate_4d({975: 0.634})
    check(between["minimum"] == [975, 1005] and between["4d"] == "HOLDS",
          "a median between two codes (0.634 V) ties with the 0.631 minimum")
    check(evaluate_4d({960: 0.634})["4d"] == "PARTIAL",
          "the minimum widening to 960 MHz without reaching an end is partial")
    check(evaluate_4d({900: 0.631, 915: 0.631, 945: 0.631, 960: 0.631})["4d"]
          == "MINIMUM_REACHES_BOTTOM",
          "the falling limb vanishing puts the minimum at the bottom (the thermal outcome)")
    check(evaluate_4d({1140: 0.625})["4d"] == "MINIMUM_AT_TOP",
          "a minimum at 1140 MHz is reported as the registered words named it")
    check(evaluate_4d({t: 0.631 for t in ASCENDING})["4d"] == "FLAT",
          "a readback flat across the whole band is flat, not either end")
    check(evaluate_4d(order="ascending")["4d"] == "NOT_SCOREABLE",
          "a sweep not recorded as descending is not scoreable")
    check(evaluate_4d({1065: 0.669})["4d"] == "NOT_SCOREABLE",
          "a sweep reading edit voltage at 1065 MHz did not run on stock and is not scoreable")
    check(raises(evaluate_4d, label="rtx2060s-sessione-e1-asc"),
          "no descending E1 sweep present is refused")


if __name__ == "__main__":
    main()
