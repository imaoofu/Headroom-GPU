"""Prospective section 15 fixtures. All writes are in TemporaryDirectory, never data/."""

import contextlib
import csv
import datetime
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import score_rerun15 as scorer
import score_control10


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class Fixture:
    def __init__(self, root, part):
        self.root, self.part = root, part
        self.manifest = {"sweeps": {}, "references": {}}
        self.historical = root / "old_sweep.csv"
        for role in scorer.roles_for(part):
            self.manifest["sweeps"][role] = self.sweep(role)
        if part != "r3":
            old = self.sweep("historical-stock", scale=1 / 1.04)
            self.historical = root / old["sweep"]
            self.manifest["references"][part] = old
        self.save()

    def sweep(self, role, scale=1, peak=None):
        directory = self.root / role
        directory.mkdir(exist_ok=True)
        path = directory / "test_sweep.csv"
        grid = scorer.GRID if self.part == "r3" or role.endswith("gemm") else scorer.BAND
        treatment = role.startswith(("curve3-", "p4-"))
        loaded = 16301 if role.startswith(("p4-", "p2-", "rungB-", "rungC-")) else 13801
        peak = peak or (1702 if role.startswith("rungB-") else 1852 if role.startswith("rungC-") else 1545)
        sweep_rows, hw_rows = [], []
        header = ["Date", "Time", "GPU Memory Clock [MHz]", "GPU Bus Load [%]",
                  "GPU Memory Clock [MHz]", "GPU Crossbar Clock [MHz]",
                  "GPU Memory Clock (measured) [MHz]", "GPU Bus Load [%]", "Framerate Presented (avg) [FPS]"]
        for index, target in enumerate(grid):
            start = 1791072000 + index * 10  # Known epoch; logs below use an explicit offset.
            efficiency = 2 if target == peak else 1
            throughput = (target / 5 if self.part != "r3" else efficiency * 100) * scale
            if treatment and role.endswith("membw"):
                throughput *= 0.85
            power = 100 if role.endswith("gemm") or self.part == "r3" else 60
            if role == "curve3-gemm":
                power = 80
            sweep_rows.append({"target_frequency_mhz": target, "achieved_frequency_avg": target - 7,
                               "bench_throughput": throughput, "power_avg_w": power,
                               "bench_ok": "True", "lock_miss_direction": "none", "power_window_applied": "True",
                               "window_start_unix": start, "window_end_unix": start + 4,
                               "memory_clock_samples_mhz": json.dumps([loaded] * 5),
                               "memory_clock_min_mhz": loaded, "memory_clock_max_mhz": loaded,
                               "memory_clock_avg_mhz": loaded})
            for delta in (-1, 0, 1, 2, 3, 4, 5):
                stamp = datetime.datetime.fromtimestamp(start + delta, datetime.timezone.utc) - datetime.timedelta(hours=7)
                hw_rows.append([stamp.strftime("%d.%m.%Y"), stamp.strftime("%H:%M:%S.%f"),
                                405, 99, loaded / 8, 1340 if treatment else target * 0.95,
                                999, 2, 5])  # AMD bus=99 and measured memory=999 must not be used.
        write_csv(path, list(sweep_rows[0]), sweep_rows)
        hw_path = directory / "test-hwinfo.csv"
        with hw_path.open("w", encoding="latin-1", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(hw_rows)
        (directory / "wrapper-result.json").write_text(json.dumps({"desktopLoad": "quiet", "sweepExitCode": 0}), encoding="utf-8-sig")
        snapshot = "rungB" if role.startswith("rungB-") else "rungC" if role.startswith("rungC-") else "curve3"
        cfg = next(scorer.SNAPSHOTS[snapshot].glob("VEN_10DE*.cfg"))
        return {"sweep": str(path.relative_to(self.root)), "hwinfo": str(hw_path.relative_to(self.root)),
                "utc_offset_minutes": -420,
                "witness": {"profile_store": str(cfg), "snapshot": snapshot, "driver": "616.92",
                            "profile_slot": 3 if role.startswith(("stock-", "historical-")) else 4 if role.startswith("p4-") else 2 if role.startswith("p2-") else 1,
                            "witnessed_at_unix": 1791071900,
                            "power_limit_w": 180 if role.startswith(("stock-", "historical-")) else 200,
                            "memory_loaded_mhz": loaded, "offsets_mhz": {"core": 0, "memory": 0, "xbar": 0, "sys": 0},
                            "restored_byte_for_byte": True, "afterburner_closed": True}}

    def save(self):
        (self.root / "rerun15-inputs.json").write_text(json.dumps(self.manifest), encoding="utf-8-sig")

    def rows(self, role):
        return scorer.csv_rows(self.root / self.manifest["sweeps"][role]["sweep"])

    def edit(self, role, action):
        rows = self.rows(role)
        action(rows)
        write_csv(self.root / self.manifest["sweeps"][role]["sweep"], list(rows[0]), rows)

    def wrapper(self, role, **changes):
        d = self.manifest["sweeps"][role]
        path = (self.root / d["sweep"]).parent / "wrapper-result.json"
        w = scorer.json_read(path)
        w.update(changes)
        path.write_text(json.dumps(w), encoding="utf-8-sig")

    def hw_edit(self, role, column, values):
        path = self.root / self.manifest["sweeps"][role]["hwinfo"]
        with path.open(newline="", encoding="latin-1") as handle:
            rows = list(csv.reader(handle))
        for index, value in enumerate(values):
            rows[index + 2][column] = value  # First point in-window, skip the pre-window sample.
        with path.open("w", encoding="latin-1", newline="") as handle:
            csv.writer(handle).writerows(rows)

    def score(self):
        self.save()
        with patch.dict(scorer.HISTORICAL, {self.part: self.historical}):
            # Only human-readable path printing uses ROOT, so allow the temp historical path.
            with patch.object(scorer, "ROOT", self.root):
                return scorer.score(self.part, self.root)


def evaluate(part, action=None):
    with tempfile.TemporaryDirectory() as temporary:
        fixture = Fixture(Path(temporary), part)
        if action:
            action(fixture)
        return fixture.score()


def main():
    for part in ("r1", "r2", "r3"):
        result = evaluate(part)
        check(result["verdict"] == "HOLDS", f"the complete synthetic {part.upper()} passes every prediction with achieved clocks seven MHz below targets")
        check(any("Reported, not scored:" in line for line in result["lines"]), f"{part.upper()} prints its descriptive comparisons separately")

    for part in ("r1", "r2", "r3"):
        role = "stock-close-copy" if part == "r3" else "stock-close-membw"
        result = evaluate(part, lambda f: f.edit(role, lambda rows: [r.update(bench_throughput=str(float(r["bench_throughput"]) * 1.02)) for r in rows]))
        check(result["verdict"] == "NOT SCOREABLE", f"a 2% stock-return drift refuses {part.upper()}")

    quiet_first = evaluate("r1", lambda f: f.edit("curve3-membw", lambda rows: rows[0].update(memory_clock_samples_mhz=json.dumps([810, 13801, 13801, 13801, 13801]))))
    check(quiet_first["verdict"] == "HOLDS" and any("1 low readings" in s for s in quiet_first["lines"]),
          "a single idle first nvidia-smi sample passes and its low count is printed")
    idle_median = evaluate("r1", lambda f: f.edit("curve3-membw", lambda rows: rows[0].update(memory_clock_samples_mhz=json.dumps([810, 810, 810, 13801, 13801]))))
    check(idle_median["verdict"] == "NOT SCOREABLE", "an idle nvidia-smi median refuses the treatment")
    hw_idle = evaluate("r1", lambda f: f.hw_edit("curve3-membw", 4, ["101.2"]))
    check(hw_idle["verdict"] == "HOLDS", "one idle HWiNFO memory reading is allowed independently of nvidia-smi")
    hw_bad = evaluate("r1", lambda f: f.hw_edit("stock-open-membw", 4, ["101.2"] * 3))
    check(hw_bad["verdict"] == "NOT SCOREABLE", "a reference with an idle HWiNFO median is NOT SCOREABLE")
    twice_low = scorer.memory_rule([810, 7001, 13801, 13801, 13801], 13801)
    check(not twice_low["ok"], "two low readings fail even when the loaded median and maximum pass")
    for loaded in (13801, 16301):
        check(scorer.memory_rule([loaded, loaded, loaded, loaded + 200], loaded)["ok"], f"the one-above maximum is allowed for loaded state {loaded}")
        check(not scorer.memory_rule([loaded, loaded, loaded + 201], loaded)["ok"], f"a maximum above the registered state pair fails for {loaded}")
    check(not scorer.memory_rule([13801, 14001], 13801)["ok"], "an even-sample median between loaded states is refused without rounding")
    check(scorer.memory_rule([13801, 13801, 13900, 14001, 13801], 13801)["ok"], "only the written median, maximum and low-count predicates constrain intermediate readings")

    for changes in ({"desktopLoad": "DESKTOP LOAD"}, {"sweepExitCode": 8}):
        result = evaluate("r2", lambda f, changes=changes: f.wrapper("p4-membw", **changes))
        check(result["verdict"] == "NOT SCOREABLE", f"the wrapper desktop-load failure {changes} is refused")
    raw_load = evaluate("r2", lambda f: f.hw_edit("p4-membw", 8, ["31"] * 5))
    check(raw_load["verdict"] == "NOT SCOREABLE", "raw HWiNFO load above 30 fps overrides a quiet wrapper")
    bus_load = evaluate("r2", lambda f: f.hw_edit("stock-open-membw", 7, ["11"] * 5))
    # Section 15 amended 2026-10-03, before collection: framerate alone flags a window, because
    # kernels reach 13-36% bus load by themselves on a quiet desktop.
    check(bus_load["verdict"] == "HOLDS", "11% NVIDIA bus load at a quiet framerate is reported, not refused")
    fps_load = evaluate("r2", lambda f: f.hw_edit("stock-open-membw", 8, ["31"] * 5))
    check(fps_load["verdict"] == "NOT SCOREABLE", "the opening reference is still refused above 30 fps")

    def retry(f):
        first = f.manifest["sweeps"]["p4-membw"]
        f.wrapper("p4-membw", sweepExitCode=8)
        second = f.sweep("p4-retry-membw")
        f.manifest["sweeps"]["p4-membw"] = [first, second]
    check(evaluate("r2", retry)["verdict"] == "HOLDS", "a recorded failed desktop attempt followed by its sole quiet retry passes")

    def second_failure(f):
        retry(f)
        second = f.manifest["sweeps"]["p4-membw"][1]
        path = (f.root / second["sweep"]).parent / "wrapper-result.json"
        path.write_text(json.dumps({"desktopLoad": "DESKTOP LOAD", "sweepExitCode": 8}))
    check(evaluate("r2", second_failure)["verdict"] == "NOT SCOREABLE", "a second desktop failure makes the arm NOT SCOREABLE")

    def same_point(f):
        for w in scorer.WORKLOADS:
            f.manifest["sweeps"][f"rungC-{w}"] = f.sweep(f"rungC-{w}", peak=1702)
    same = evaluate("r3", same_point)
    check(same["predictions"]["tertiary monotone distinct rungs"] == "FAILS", "B and C at the same point refute the tertiary prediction")

    def six_six(f):
        for w in scorer.WORKLOADS[:6]:
            f.manifest["sweeps"][f"rungB-{w}"] = f.sweep(f"rungB-{w}", peak=1545)
    split = evaluate("r3", six_six)
    check(split["predictions"]["rungB primary median"] == "FAILS" and any("1623.5" in line for line in split["lines"]),
          "a six-six split retains its between-grid 1623.5 MHz median and refutes the point prediction")
    check(split["predictions"]["rungB secondary count"] == "FAILS", "six on the predicted target fail the registered seven-of-twelve count")

    def non_stock_median(f):
        for w in scorer.WORKLOADS:
            f.manifest["sweeps"][f"stock-close-{w}"] = f.sweep(f"stock-close-{w}", peak=1702)
            # Change power only, leaving throughput equal to opening at every target.
            f.edit(f"stock-close-{w}", lambda rows: [r.update(bench_throughput=str(200 if int(r["target_frequency_mhz"]) == 1545 else 100),
                                                              power_avg_w=str(25 if int(r["target_frequency_mhz"]) == 1702 else 100)) for r in rows])
    shifted = evaluate("r3", non_stock_median)
    check(shifted["verdict"] == "HOLDS", "R3 does not invent section 10's separate equal-stock-median gate absent from section 15")

    primary_fail = evaluate("r1", lambda f: f.edit("curve3-membw", lambda rows: rows[2].update(bench_throughput=str(1560 / 5))))
    check(primary_fail["predictions"]["primary plateau"] == "FAILS", "equality with opening stock at one plateau target refutes the strict below prediction")
    secondary_fail = evaluate("r1", lambda f: f.edit("curve3-gemm", lambda rows: rows[8].update(power_avg_w="100")))
    check(secondary_fail["predictions"]["secondary gemm power"] == "FAILS", "power equality at 2475 MHz refutes R1's secondary prediction")
    dropped_top = evaluate("r1", lambda f: f.edit("curve3-gemm", lambda rows: rows[9].update(power_avg_w="200")))
    check(dropped_top["predictions"]["secondary gemm power"] == "HOLDS", "2625 MHz is excluded from R1's power prediction as section 15 specifies")
    repair_fail = evaluate("r2", lambda f: f.edit("p2-membw", lambda rows: rows[6].update(bench_throughput=str(1867 / 5 * 0.85 * 1.079))))
    check(repair_fail["predictions"]["repair"] == "FAILS", "a 7.9% repair uplift at 1867 MHz fails the at-least-eight-percent threshold")

    def old_reference_bad(f):
        rows = scorer.csv_rows(f.historical)
        rows[0]["memory_clock_max_mhz"] = "16301"
        write_csv(f.historical, list(rows[0]), rows)
    old_bad = evaluate("r1", old_reference_bad)
    check(old_bad["predictions"]["load uplift"] == "NOT SCOREABLE" and old_bad["predictions"]["primary plateau"] == "HOLDS",
          "a historical reference whose recorded memory maximum leaves the stock pair blocks the load prediction without hiding a clean within-session primary")

    def old_reference_summary_only(f):
        rows = scorer.csv_rows(f.historical)
        for row in rows:
            row.pop("memory_clock_samples_mhz")
            row.update(memory_clock_min_mhz="810", memory_clock_avg_mhz="13259.7")
        write_csv(f.historical, list(rows[0]), rows)
        f.manifest["references"].pop("r1", None)
    old_summary = evaluate("r1", old_reference_summary_only)
    check(old_summary["predictions"]["load uplift"] == "HOLDS",
          "a historical comparator with only recorded min/mean/max memory and an 810 MHz minimum is scored as recorded, as amended section 15 states")
    old_low = evaluate("r1", lambda f: f.manifest["references"].update(r1=f.sweep("historical-stock", scale=1 / 1.029)))
    check(old_low["predictions"]["load uplift"] == "FAILS", "2.9% clean-over-historical band uplift refutes the load prediction")
    exact = evaluate("r1", lambda f: f.manifest["references"].update(r1=f.sweep("historical-stock", scale=1 / 1.03)))
    check(exact["predictions"]["load uplift"] == "HOLDS", "the exact inclusive 3% load threshold passes")

    missing = evaluate("r1", lambda f: f.manifest["sweeps"].pop("stock-gemm"))
    check(missing["verdict"] == "NOT SCOREABLE", "a missing sweep cannot produce an all-holds result")
    summary_only = evaluate("r2", lambda f: f.edit("p4-membw", lambda rows: [r.pop("memory_clock_samples_mhz") for r in rows]))
    check(summary_only["verdict"] == "NOT SCOREABLE", "min/avg/max alone cannot stand in for the registered memory median and count")
    wrong_cfg = evaluate("r3", lambda f: f.manifest["sweeps"]["rungB-copy"]["witness"].update(snapshot="curve3"))
    check(wrong_cfg["verdict"] == "NOT SCOREABLE", "rung B witnessed against the wrong committed snapshot is refused")
    wrong_offset = evaluate("r1", lambda f: f.manifest["sweeps"]["stock-gemm"]["witness"].update(offsets_mhz={"xbar": -100}))
    check(wrong_offset["verdict"] == "NOT SCOREABLE", "a nonzero recorded mVolt+ offset fails the configuration gate")
    wrong_slot = evaluate("r2", lambda f: f.manifest["sweeps"]["p4-membw"]["witness"].update(profile_slot=2))
    check(wrong_slot["verdict"] == "NOT SCOREABLE", "the correct store and live readings cannot substitute for the recorded applied slot")
    late_witness = evaluate("r1", lambda f: f.manifest["sweeps"]["curve3-gemm"]["witness"].update(witnessed_at_unix=1791072001))
    check(late_witness["verdict"] == "NOT SCOREABLE", "a witness recorded after collection starts fails the pre-arm condition")

    for part in ("r1", "r2", "r3"):
        role = "stock-close-copy" if part == "r3" else "stock-close-membw"
        boundary = evaluate(part, lambda f: f.edit(role, lambda rows: [r.update(bench_throughput=str(float(r["bench_throughput"]) * 1.015)) for r in rows]))
        check(boundary["verdict"] == "HOLDS", f"the inclusive 1.5% drift boundary passes {part.upper()}")
    exact_repair = evaluate("r2", lambda f: f.edit("p2-membw", lambda rows: rows[6].update(bench_throughput=str(1867 / 5 * 0.85 * 1.08))))
    check(exact_repair["predictions"]["repair"] == "HOLDS", "the exact inclusive eight-percent repair threshold passes")
    xbar_edge = evaluate("r1", lambda f: f.hw_edit("curve3-membw", 5, ["1300"] * 5))
    check(xbar_edge["predictions"]["crossbar telemetry"] == "HOLDS", "the lower 1300 MHz crossbar boundary is included")
    xbar_fail = evaluate("r1", lambda f: f.hw_edit("curve3-membw", 5, ["1361"] * 5))
    check(xbar_fail["predictions"]["crossbar telemetry"] == "FAILS", "1361 MHz refutes the telemetry window while the plateau can hold")
    stock_flat = evaluate("r1", lambda f: f.hw_edit("stock-open-membw", 5, ["2000"] * 5))
    check(stock_flat["predictions"]["crossbar telemetry"] == "FAILS", "a reversal in stock crossbar clocks refutes the chosen rising-at-each-target reading")
    missing_point = evaluate("r3", lambda f: f.edit("rungB-copy", lambda rows: rows.pop()))
    check(missing_point["verdict"] == "NOT SCOREABLE", "a missing registered target is refused")
    duplicate = evaluate("r1", lambda f: f.edit("curve3-membw", lambda rows: rows.append(dict(rows[0]))))
    check(duplicate["verdict"] == "NOT SCOREABLE", "a duplicated target cannot silently overwrite a point")
    excluded = evaluate("r3", lambda f: f.edit("rungC-gemm", lambda rows: rows[0].update(lock_miss_direction="above")))
    check(excluded["verdict"] == "NOT SCOREABLE", "an excluded overshoot cannot leave a scoreable incomplete suite")
    nan = evaluate("r1", lambda f: f.edit("stock-open-membw", lambda rows: rows[0].update(bench_throughput="nan")))
    zero_power = evaluate("r1", lambda f: f.edit("stock-open-membw", lambda rows: rows[0].update(power_avg_w="0")))
    check(nan["verdict"] == "NOT SCOREABLE" and zero_power["verdict"] == "NOT SCOREABLE", "non-finite throughput and zero board power are refused")

    def incomplete_retry(f):
        retry(f)
        first = f.manifest["sweeps"]["p4-membw"][0]
        path = f.root / first["sweep"]
        rows = scorer.csv_rows(path)[:-1]
        write_csv(path, list(rows[0]), rows)
    check(evaluate("r2", incomplete_retry)["verdict"] == "HOLDS", "an incomplete first sweep with a recorded exit eight may be replaced by the sole clean retry")
    def unjustified_retry(f):
        retry(f)
        first = f.manifest["sweeps"]["p4-membw"][0]
        path = (f.root / first["sweep"]).parent / "wrapper-result.json"
        path.write_text(json.dumps({"desktopLoad": "quiet", "sweepExitCode": 0}))
    check(evaluate("r2", unjustified_retry)["verdict"] == "NOT SCOREABLE", "a retry after a successful attempt is refused to prevent choosing a preferred replicate")

    # Deliberate behavioral mutations: prove these fixtures discriminate plausible wrong scorers.
    real_memory_rule = scorer.memory_rule
    def max_only(values, loaded, hwinfo=False):
        r = real_memory_rule(values, loaded, hwinfo)
        r["ok"] = r["maximum"] in (loaded, loaded + 200)
        return r
    with patch.object(scorer, "memory_rule", max_only):
        mutant = evaluate("r1", lambda f: f.edit("curve3-membw", lambda rows: rows[0].update(memory_clock_samples_mhz=json.dumps([810, 810, 810, 13801, 13801]))))
        check(mutant["verdict"] == "HOLDS" and idle_median["verdict"] == "NOT SCOREABLE", "the idle-median fixture detects a max-only memory-rule mutation")
    real_peak = score_control10.efficiencyPeak
    with patch.object(score_control10, "efficiencyPeak", lambda rows: {**real_peak(rows), "target": real_peak(rows)["mhz"]}):
        mutant = evaluate("r3")
        check(mutant["predictions"]["rungB primary median"] == "FAILS", "the unequal-clock fixture detects an achieved-clock optimum mutation")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        f = Fixture(root, "r3")
        role = "stock-open-copy"
        rows = f.rows(role)
        ns_path = root / "samples.csv"
        ns = [{"timestamp_unix": float(r["window_start_unix"]) + i, "memory_clock_mhz": 13801} for r in rows for i in range(5)]
        ns += [{"timestamp_unix": float(rows[0]["window_start_unix"]) - 1, "memory_clock_mhz": 810}]
        write_csv(ns_path, ["timestamp_unix", "memory_clock_mhz"], ns)
        f.edit(role, lambda rows: [r.pop("memory_clock_samples_mhz") for r in rows])
        f.manifest["sweeps"][role]["nvidia_samples"] = "samples.csv"
        check(f.score()["verdict"] == "HOLDS", "raw nvidia-smi telemetry is joined by absolute window and excludes an out-of-window idle sample")
        # Exercise the actual CLI with a relative directory argument and BOM JSON.
        run = subprocess.run([sys.executable, str(Path(scorer.__file__).resolve()), "r3", root.name], cwd=root.parent,
                             capture_output=True, text=True)
        check(run.returncode == 0 and "The R3 verdict is HOLDS" in run.stdout and "N=1 chip" in run.stdout,
              "the CLI works from another cwd with relative paths, BOM manifests and complete verdict sentences")
        f.manifest["sweeps"][role]["utc_offset_minutes"] = 0
        check(f.score()["verdict"] == "NOT SCOREABLE", "an incorrect collection-time UTC offset yields no in-window HWiNFO readings and is refused")

    with tempfile.TemporaryDirectory() as temporary:
        cfg = Path(temporary) / "store.cfg"
        canonical = next(scorer.SNAPSHOTS["curve3"].glob("VEN_10DE*.cfg"))
        cfg.write_bytes(canonical.read_bytes().replace(b"\r\n", b"\n"))
        check(scorer.section_hash(cfg) == scorer.section_hash(canonical), "section-hash witnesses are independent of checkout line endings")
        text = cfg.read_text(encoding="utf-8-sig")
        cfg.write_text(text.replace("[Profile1]", "[MissingProfile1]"), encoding="utf-8")
        try:
            scorer.section_hash(cfg)
        except ValueError:
            check(True, "a missing mandatory profile section is refused rather than skipped")
        else:
            check(False, "a missing mandatory profile section is refused rather than skipped")

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = scorer.main(["r1", "directory-that-does-not-exist"])
    check(code == 2 and "NOT SCOREABLE" in output.getvalue(), "an absent input manifest exits two with an explicit NOT SCOREABLE sentence")


if __name__ == "__main__":
    main()
