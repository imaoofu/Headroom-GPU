"""Checks for score_repeatability.py (REGISTERED-PREDICTIONS section 22); synthetic day folders only.

Expected statistics are derived by hand in the comments, not by calling the scorer's own helpers. The
fixture carries every piece of evidence the hardened scorer requires (GPT Job 94, 2026-10-14): both
attempt ledgers, a copy of the real curve3 profile store, exact workload commands, timestamps, event
reads and the runner as run. Each Job 94 finding has checks of its own below, marked F1-F8.
"""

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import math
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from score_repeatability import (GRID, ITERATIONS, REFERENCE, SCHEDULE, SNAPSHOT, WORKLOADS, chi2_quantile,
                                 load_day, measured_floor, passes, report, score, to_json)

REPO = Path(__file__).resolve().parents[1]
FILER = REPO / "tools" / "rerun15" / "file_repeatability_day.py"


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


FIELDS = ("target_frequency_mhz", "achieved_frequency_avg", "achieved_frequency_min", "achieved_frequency_max",
          "memory_clock_avg_mhz", "memory_clock_min_mhz", "memory_clock_max_mhz", "power_avg_w",
          "temperature_max_c", "power_window_applied", "bench_throughput", "bench_ok", "throttle_masks_seen",
          "energy_avg_power_w", "lock_miss_direction")
OFFSETS = {"xbar_offset_mhz": 0, "sys_offset_mhz": 0, "video_offset_mhz": 0, "demand_core_mv": 0,
           "demand_xbar_mv": 0, "demand_sys_mv": 0, "demand_video_mv": 0}
LOCAL = timezone(timedelta(minutes=-420))
PYTHON = r"C:\Users\Raymond\AppData\Local\Programs\Python\Python312\python.exe"
SCRIPT = r"C:\Users\Raymond\Documents\headroom\tools\frequency-sweep\gpu_workload.py"
RUNNER_TEXT = b"# the runner as run\r\n"
# The fields of a real mVolt+ status record that section 22 checks (day 1's, 2026-10-15), all at stock.
MVOLT_STATUS = {"power_limits": {"requested_mw": 180000, "enforced_mw": 180000, "default_mw": 180000},
                "nvvdd_offsets_uv": {"vmin": 0, "rel": 0, "alt": 0, "ov": 0}, "xbar_offset_mhz": 0,
                "sys_offset_mhz": 0, "video_offset_mhz": 0,
                "voltage_demand_mv": {"Core": 0, "Xbar": 0, "SYS": 0, "Video": 0}}


def efficiency_curve(peak, regret):
    """1.0 at the peak, 1 - regret% at the 1575 reference, 0.9 elsewhere."""
    curve = {t: 0.9 for t in GRID}
    curve[peak] = 1.0
    if peak != REFERENCE:
        curve[REFERENCE] = 1.0 - regret / 100.0
    return curve


def command(workload):
    text = f"{PYTHON} {SCRIPT} --workload {workload} --json --iterations {ITERATIONS[workload]}"
    return text if workload == "resnet50" else text + " --input-seed 20261013"


def make_repo(root, days, section20b=("2026-10-12",)):
    """A repository root holding both ledgers and the real curve3 snapshot. days: [(index, date), ...]
    in attempt order."""
    (root / SNAPSHOT).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / SNAPSHOT, root / SNAPSHOT)
    (root / "docs" / "section20b").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "section20b" / "ATTEMPTS.md").write_text(
        "".join(f"| {i + 1} | pilot session | {i + 1} | {d} | x | y | z |\n" for i, d in enumerate(section20b)),
        encoding="utf-8")
    (root / "docs" / "repeatability").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "repeatability" / "ATTEMPTS.md").write_text(
        "| # | Kind | Day | Local date | Launched from | Directory | Outcome |\n|---|---|---|---|---|---|---|\n"
        "| 1 | qualification | — | 2026-10-14 | x | y | not data |\n"
        + "".join(f"| {i + 2} | **day** | {k} | {d} | x | y | z |\n" for i, (k, d) in enumerate(days)),
        encoding="utf-8")
    return root


def write_day(root, day, date, regret=1.0, peak=1537, edits=None, second_scale=1.0, desk=None, manifest_edit=None,
              start_hour=9, store_bytes=None, mvolt_edit=None):
    """A complete synthetic section 22 day. edits(role, rows) may change one sweep's rows."""
    folder = root / f"day{day}-{date.replace('-', '')}"
    (folder / "wrapper").mkdir(parents=True)
    (folder / "witnesses").mkdir()
    (folder / "runner-Invoke-Rerun15Session.ps1.txt").write_bytes(RUNNER_TEXT)
    clock = datetime.fromisoformat(date).replace(hour=start_hour, tzinfo=LOCAL)
    session_start = clock - timedelta(minutes=10)
    witnesses = {}
    for number in (1, 2):
        store = folder / "witnesses" / f"rep-d{day}-pass{number}-store.cfg"
        if store_bytes is None:
            shutil.copy2(REPO / SNAPSHOT, store)
        else:
            store.write_bytes(store_bytes)
        status = json.loads(json.dumps(MVOLT_STATUS))
        if (mvolt_edit(number, status) if mvolt_edit else None) != "absent":   # "absent": write no record
            (folder / "witnesses" / f"rep-d{day}-pass{number}-mvolt-status.json").write_text(json.dumps(status),
                                                                                       encoding="utf-8")
        witnesses[number] = {"profile_store": f"witnesses/{store.name}", "snapshot": "curve3", "profile_slot": 3,
                             "driver": "616.92", "power_limit_w": 180, "memory_loaded_mhz": 13801,
                             "offsets_mhz": dict(OFFSETS), "restored_byte_for_byte": True,
                             "afterburner_closed": True, "gemm_2475_power_w": 180.1}
    sweeps = {}
    order, descending = SCHEDULE[day]
    for number, pass_order, pass_desc in passes(day):
        witnesses[number]["witnessed_at_unix"] = (clock - timedelta(minutes=1)).timestamp()
        for w in pass_order:
            role = f"pass{number}-{w}"
            curve = efficiency_curve(peak, regret)
            rows = []
            for t in sorted(GRID, reverse=pass_desc):
                scale = second_scale if number == 2 else 1.0
                rows.append({"target_frequency_mhz": t, "achieved_frequency_avg": t - 3, "achieved_frequency_min": t - 8,
                             "achieved_frequency_max": t + 2, "memory_clock_avg_mhz": 13801,
                             "memory_clock_min_mhz": 810, "memory_clock_max_mhz": 13801, "power_avg_w": 100 * scale,
                             "temperature_max_c": 55, "power_window_applied": "True",
                             "bench_throughput": curve[t] * 100 * scale, "bench_ok": "True",
                             "throttle_masks_seen": "0x0000000000000400", "energy_avg_power_w": 103,
                             "lock_miss_direction": "none"})
            if edits:
                rows = edits(role, rows)
            name = f"{clock:%Y%m%d-%H%M%S}_rep-{role}_sweep.csv"
            with (folder / name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            metadata = {"power_limit_enforced_w": "180.00", "session_label": f"rep-{role}", "driver_version": "616.92",
                        "sweep_order": "descending" if pass_desc else "ascending", "workload_command": command(w),
                        "started_at": clock.isoformat(timespec="microseconds")[:-6] + "1-07:00",
                        "ended_at": (clock + timedelta(minutes=8)).isoformat()}
            (folder / name).with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
            clock += timedelta(minutes=10)
            wrapper = f"wrapper/rep-{role}-wrapper-result.json"
            verdict = (desk or {}).get(role, "quiet")
            (folder / wrapper).write_text(json.dumps({"desktopLoad": verdict, "sweepExitCode": 0, "logStopExitCode": 0}),
                                          encoding="utf-8")
            sweeps[role] = {"sweep": name, "wrapper": wrapper, "witness": witnesses[number],
                            "driver_events": {"ok": True, "count": 0, "ids": []}}
    sources = {"Invoke-Rerun15Session.ps1": hashlib.sha256(RUNNER_TEXT).hexdigest().upper(),
               "Invoke-LoggedSweep.ps1": "A" * 64, "gpu_workload.py": "B" * 64, "app_workloads.py": "C" * 64}
    manifest = {"section": "REGISTERED-PREDICTIONS section 22 (day-to-day repeatability)", "dryRun": False,
                "exitCode": 0, "notScoreable": [], "sweeps": sweeps, "sources": sources,
                "driverEventsFinal": {"ok": True, "count": 0, "ids": [], "read_at_unix": clock.timestamp(),
                                      "session_start_unix": session_start.timestamp()},
                "repeatability": {"day": day, "localDate": date, "utcOffsetMinutes": -420, "grid": list(GRID),
                                  "inputSeed": 20261013,
                                  "iterations": {"gemm": 120, "copy": 2660, "reduce": 2870, "resnet50": 424},
                                  "pass1": {"order": list(order), "descending": descending},
                                  "pass2": {"order": list(reversed(order)), "descending": not descending}}}
    if manifest_edit:
        manifest_edit(manifest)
    (folder / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "runner-cleanup.json").write_text(json.dumps({"ok": True, "reset_exit": 0, "store_restored": True,
                                                            "memory_loaded_mhz": 13801, "power_limit_w": 180,
                                                            "errors": []}), encoding="utf-8")
    return folder


DATES = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"]


def run(regrets, peaks=None, **kwargs):
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(i + 1, DATES[i]) for i in range(len(regrets))])
        folders = [write_day(root, i + 1, DATES[i], regret=r, peak=(peaks or [1537] * 5)[i], **kwargs)
                   for i, r in enumerate(regrets)]
        return score(folders, repo=root)


def single(**kwargs):
    with tempfile.TemporaryDirectory() as temporary:
        return load_day(write_day(Path(temporary), 1, DATES[0], **kwargs), repo=REPO)


def status_of(**kwargs):
    """Scored status of one day 1 on DATES[0], with a ledger line for it."""
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(1, DATES[0])])
        return score([write_day(root, 1, DATES[0], **kwargs)], repo=root)["days"][0]["status"]


def mutate_row(role_name, column, value, index=3):
    def edit(role, rows):
        if role == role_name:
            rows[index] = dict(rows[index], **{column: value})
        return rows
    return edit


def mutate_json(role_name, key, value):
    """A manifest_edit is not enough for sweep metadata; this rewrites one role's sweep JSON after writing."""
    def edit(folder):
        manifest = json.loads((folder / "rerun15-inputs.json").read_text(encoding="utf-8"))
        path = (folder / manifest["sweeps"][role_name]["sweep"]).with_suffix(".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        data[key] = value
        path.write_text(json.dumps(data), encoding="utf-8")
    return edit


def status_after(edit):
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(1, DATES[0])])
        folder = write_day(root, 1, DATES[0])
        edit(folder)
        return score([folder], repo=root)["days"][0]["status"]


def main():
    # ------------------------------------------------ hand-derived interval arithmetic
    # Regrets 1, 2, 3, 2, 2: mean 2, SD sqrt((1+0+1+0+0)/4) = 0.7071068.
    # t(1 - 0.05/8, 4) = 4.314656 (checked against SciPy when written); half = 4.314656 * 0.7071068 / sqrt(5)
    # = 1.364414, so the 98.75% interval is 0.635586 to 3.364414: INCONCLUSIVE against 3%.
    r = run([1, 2, 3, 2, 2])
    s = r["workloads"]["gemm"]
    check(r["stage"] == "COMPLETE" and r["D"] == 5, "five scoreable days complete the registration")
    check(abs(s["regret_mean"] - 2.0) < 1e-9 and abs(s["regret_sd"] - 0.7071068) < 1e-6,
          "mean regret 2.000% and day SD 0.7071 pp, from the hand calculation")
    check(abs(s["regret_ci9875"][0] - 0.635586) < 1e-5 and abs(s["regret_ci9875"][1] - 3.364414) < 1e-5,
          "the 98.75% interval is 0.6356 to 3.3644, as derived by hand")
    check(s["outcome"] == "INCONCLUSIVE", "an interval crossing 3% is INCONCLUSIVE")
    # SD interval multipliers at D=5: sqrt(4/11.143287) = 0.599133, sqrt(4/0.484419) = 2.873554 (Job 87's 0.599, 2.874).
    check(abs(s["regret_sd_ci95"][0] / s["regret_sd"] - 0.599133) < 1e-5
          and abs(s["regret_sd_ci95"][1] / s["regret_sd"] - 2.873554) < 1e-5,
          "the SD interval multipliers at five days are 0.5991 and 2.8736, matching Job 87's draft")
    check(abs(chi2_quantile(0.975, 4) - 11.143287) < 1e-5, "the chi-square quantile matches its tabulated value")
    check(run([0.5, 0.6, 0.4, 0.5, 0.5])["workloads"]["copy"]["outcome"] == "WITHIN 3%",
          "small, steady regrets give WITHIN 3%")
    check(run([5.0, 5.2, 4.8, 5.1, 4.9])["workloads"]["reduce"]["outcome"] == "ABOVE 3%",
          "steady regrets near 5% give ABOVE 3%")
    # Regret exactly 3 every day: SD 0, interval [3, 3]: the upper bound touches 3 and passes.
    check(run([3.0] * 5)["workloads"]["gemm"]["outcome"] == "WITHIN 3%",
          "a touching upper bound passes, as registered")
    three = run([1, 2, 3])
    check(three["stage"] == "PARTIAL" and "outcome" in three["workloads"]["gemm"],
          "three scoreable days are a PARTIAL analysis with outcomes")
    two = run([1, 2])
    check(two["stage"] == "DESCRIPTIVE ONLY" and "outcome" not in two["workloads"]["gemm"],
          "two days are descriptive only, with no outcome")

    # ------------------------------------------------ estimands
    moving = run([0, 1, 0, 1, 0], peaks=[1575, 1537, 1575, 1612, 1575])
    m = moving["workloads"]["gemm"]
    check(m["argmax"] == [1575, 1537, 1575, 1612, 1575], "each day's observed peak target is reported")
    check(m["regret"][0] == 0 and abs(m["curve"][REFERENCE]["shape_mean"]) < 1e-12,
          "regret is 0 when the reference is the peak, and the shape is zero at 1575 by construction")

    def tie(role, rows):
        for row in rows:
            if row["target_frequency_mhz"] in (1500, 1537):
                row["bench_throughput"] = 100.0
        return rows
    tied = run([1] * 3, edits=tie)
    check(tied["workloads"]["copy"]["argmax"][0] == 1500, "an exact tie goes to the LOWEST target")
    check(run([1] * 3, peaks=[2317] * 3)["workloads"]["gemm"]["edge_peaks"] == 3, "peaks at the grid top are flagged as edges")
    # Section 20's estimator is the MEAN OF THE TWO DIRECTIONS' EFFICIENCIES. Double pass 2's power with
    # throughput unchanged: at the 1537 peak the efficiencies are 1.0 and 0.5, so the estimator gives
    # 0.75, while a ratio of means would give 200 / 300 = 0.667. Throughput is unchanged, so the gate passes.
    def double_power(role, rows):
        if role.startswith("pass2-"):
            rows = [dict(row, power_avg_w=200) for row in rows]
        return rows
    unequal = run([1] * 3, edits=double_power)
    check(abs(unequal["workloads"]["gemm"]["curve"][1537]["geomean"] - 0.75) < 1e-12,
          "efficiency is the mean of the two directions' ratios (0.75), not a ratio of means (0.667)")

    # ------------------------------------------------ the return gate
    gated = run([1] * 3, second_scale=1.02)
    check(all(d["status"] == "VALID, NOT SCOREABLE" for d in gated["days"]) and gated["D"] == 0,
          "a 2% throughput change between passes fails the return gate: valid, not scoreable")
    held = run([1] * 3, second_scale=1.015)
    check(all(d["status"] == "SCOREABLE" for d in held["days"]), "exactly 1.5% passes the return gate")

    # ------------------------------------------------ validity
    check(single()["status"] == "VALID", "the unmutated synthetic day is valid")
    for column, value, what in (("bench_ok", "False", "a failed benchmark"),
                                ("power_window_applied", "False", "unwindowed power"),
                                ("achieved_frequency_min", "1490", "an achieved clock 47 MHz below target"),
                                ("memory_clock_max_mhz", "16301", "a memory overclock"),
                                ("throttle_masks_seen", "0x0000000000000040", "a hardware thermal slowdown"),
                                ("temperature_max_c", "88", "88 C"),
                                ("power_avg_w", "0", "zero power"),
                                ("bench_throughput", "nan", "non-finite throughput")):
        check(single(edits=mutate_row("pass1-copy", column, value))["status"] == "INVALID", f"{what} invalidates the day")
    capped = single(edits=mutate_row("pass1-copy", "throttle_masks_seen", "0x0000000000000004;0x0000000000000400"))
    check(capped["status"] == "VALID" and capped["power_cap_points"] == 1,
          "a software power-cap reason is counted, not a failure")
    check(single(edits=lambda role, rows: rows[::-1] if role == "pass1-gemm" else rows)["status"] == "INVALID",
          "a sweep run in the wrong direction is invalid")
    check(single(edits=lambda role, rows: rows[:-1] if role == "pass2-reduce" else rows)["status"] == "INVALID",
          "a sweep missing one target is invalid")
    check(single(desk={"pass2-resnet50": "unchecked: log lacks the columns"})["status"] == "INVALID",
          "an unchecked desktop verdict is not quiet, and invalidates the day")

    def retried(m):
        m["sweeps"]["pass1-copy"] = [m["sweeps"]["pass1-copy"], m["sweeps"]["pass1-copy"]]
    check(single(manifest_edit=retried)["status"] == "INVALID", "a retried role is not allowed")

    def wrong_order(m):
        m["repeatability"]["pass1"]["order"] = ["copy", "gemm", "reduce", "resnet50"]
    check(single(manifest_edit=wrong_order)["status"] == "INVALID", "a schedule other than the day's registered one is refused")
    check(single(manifest_edit=lambda m: m.update(dryRun=True))["status"] == "INVALID", "a dry run is never a day")
    check(single(manifest_edit=lambda m: m.update(notScoreable=["pass1-copy"]))["status"] == "INVALID",
          "a role recorded NOT SCOREABLE invalidates the day")

    # ------------------------------------------------ dates (the original checks, with ledgers)
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(i + 1, DATES[i]) for i in range(3)], section20b=("2026-10-21",))
        days = [write_day(root, i + 1, DATES[i]) for i in range(3)]
        dated = score(days, repo=root)
        check([d["status"] for d in dated["days"]] == ["SCOREABLE", "INVALID", "SCOREABLE"],
              "a day on a section 20b date is invalid")

    # ------------------------------------------------ F1: dates and the attempt history
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        # Ledger: day 1 first attempted on 10-20, attempted again on 10-21; day 2 on 10-22.
        make_repo(root, [(1, DATES[0]), (1, DATES[1]), (2, DATES[2])])
        a = write_day(root / "a", 1, DATES[0])
        b = write_day(root / "b", 1, DATES[1])
        c = write_day(root / "c", 2, DATES[2])
        for folders in ([a, b, c], [b, a, c], [c, b, a]):
            got = {Path(d["directory"]).parent.name: d["status"] for d in score(folders, repo=root)["days"]}
            check(got == {"a": "SCOREABLE", "b": "INVALID", "c": "SCOREABLE"},
                  f"F1: only the FIRST attempt at a day is eligible, whatever the argument order ({[f.parent.name for f in folders]})")
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(2, DATES[0])])
        check(score([write_day(root, 2, DATES[0])], repo=root)["days"][0]["status"] == "INVALID",
              "F1: a day 2 with no earlier day 1 attempt breaks index order")
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(1, DATES[1]), (2, DATES[0])])
        got = [d["status"] for d in score([write_day(root, 1, DATES[1]), write_day(root, 2, DATES[0])], repo=root)["days"]]
        check(got == ["SCOREABLE", "INVALID"], "F1: day 2 dated before day 1 breaks index order")
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [])
        check(score([write_day(root, 1, DATES[0])], repo=root)["days"][0]["status"] == "INVALID",
              "F1: a day with no attempt line in the ledger is invalid")
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(1, DATES[0])])
        (root / "docs" / "section20b" / "ATTEMPTS.md").unlink()
        try:
            score([write_day(root, 1, DATES[0])], repo=root)
            refused = False
        except ValueError:
            refused = True
        check(refused, "F1: a missing section 20b ledger stops scoring rather than passing the date rule")
    for date, what in (("2026-99-99", "an impossible local date"), (None, "an absent local date"),
                       ("2026-10-19", "a local date before the day's first sweep")):
        check(status_of(manifest_edit=lambda m, d=date: m["repeatability"].update(localDate=d)) == "INVALID",
              f"F1: {what} is invalid")
    with tempfile.TemporaryDirectory() as temporary:
        # A session launched 23:00 runs past midnight into 10-21, a section 20b date: every occupied date counts.
        root = make_repo(Path(temporary), [(1, DATES[0])], section20b=(DATES[1],))
        late = score([write_day(root, 1, DATES[0], start_hour=23)], repo=root)["days"][0]
        check(late["status"] == "INVALID" and DATES[1] in late["occupied"],
              "F1: a day crossing midnight into a section 20b date is invalid")
    with tempfile.TemporaryDirectory() as temporary:
        # Job 94's bypass: day 1 on A, day 1 again on B, day 2 on A. Day 2 shares A with day 1.
        root = make_repo(Path(temporary), [(1, DATES[0]), (1, DATES[1]), (2, DATES[0])])
        got = [d["status"] for d in score([write_day(root / "a", 1, DATES[0]), write_day(root / "b", 1, DATES[1]),
                                           write_day(root / "c", 2, DATES[0])], repo=root)["days"]]
        check(got == ["SCOREABLE", "INVALID", "INVALID"], "F1: a duplicate day no longer erases the date it occupied")

    # ------------------------------------------------ F2: display-driver event reads
    check(status_of(manifest_edit=lambda m: m.update(driverEventsFinal={"ok": False, "count": None})) == "INVALID",
          "F2: an unreadable event log after cleanup invalidates the day")
    check(status_of(manifest_edit=lambda m: m.pop("driverEventsFinal")) == "INVALID",
          "F2: a day with no final event read is invalid")
    check(status_of(manifest_edit=lambda m: m["sweeps"]["pass2-copy"].pop("driver_events")) == "INVALID",
          "F2: a role with no event read is invalid")
    check(status_of(manifest_edit=lambda m: m["sweeps"]["pass1-gemm"].update(
        driver_events={"ok": True, "count": 1, "ids": [4101]})) == "INVALID", "F2: a display-driver event invalidates the day")

    # ------------------------------------------------ F3: what ran, in what order, from what state
    def ninth(m):
        m["sweeps"]["pass3-gemm"] = dict(m["sweeps"]["pass1-gemm"])
    check(status_of(manifest_edit=ninth) == "INVALID", "F3: a ninth role invalidates the day")
    check(status_after(mutate_json("pass1-gemm", "workload_command", command("gemm").replace("gemm", "membw"))) == "INVALID",
          "F3: a sweep that ran membw under a gemm role is invalid")
    check(status_after(mutate_json("pass1-gemm", "workload_command", command("gemm") + " --dtype fp16")) == "INVALID",
          "F3: an extra precision flag in the command is invalid")
    check(status_after(mutate_json("pass1-resnet50", "workload_command", command("resnet50") + " --input-seed 20261013"))
          == "INVALID", "F3: the study seed forwarded to resnet50 is invalid")
    check(status_after(mutate_json("pass2-copy", "workload_command", command("copy").replace(" --input-seed 20261013", "")))
          == "INVALID", "F3: copy run without the seed is invalid")
    check(status_after(mutate_json("pass1-copy", "session_label", "repdry-pass1-copy")) == "INVALID",
          "F3: a sweep label other than rep-<role> is invalid")
    check(status_after(mutate_json("pass1-copy", "driver_version", "616.56")) == "INVALID", "F3: another driver is invalid")
    check(status_after(mutate_json("pass1-copy", "started_at", "2026-10-20T07:00:00-07:00")) == "INVALID",
          "F3: a role that started before its predecessor is out of order")
    check(status_of(manifest_edit=lambda m: m["repeatability"]["pass2"].update(descending=False)) == "INVALID",
          "F3: a wrong second-pass direction in the record is invalid")

    def witness_edit(**fields):
        def edit(m):
            for role in m["sweeps"]:
                if role.startswith("pass2-"):
                    m["sweeps"][role]["witness"] = dict(m["sweeps"][role]["witness"], **fields)
        return edit
    check(status_of(manifest_edit=witness_edit(restored_byte_for_byte=False)) == "INVALID",
          "F3: a witness without a byte-for-byte restore is invalid")
    check(status_of(manifest_edit=witness_edit(afterburner_closed=False)) == "INVALID",
          "F3: a witness without Afterburner closed is invalid")
    check(status_of(manifest_edit=witness_edit(offsets_mhz={"xbar_offset_mhz": 0})) == "INVALID",
          "F3: a partial mVolt+ offset record is invalid")
    check(status_of(manifest_edit=witness_edit(gemm_2475_power_w=None)) == "INVALID",
          "F3: a witness with no 2475 MHz gemm reading is invalid")
    check(status_of(manifest_edit=witness_edit(witnessed_at_unix=0.0)) == "INVALID",
          "F3: a second-pass witness taken before the first pass is invalid")
    check(status_of(store_bytes=b"[Startup]\r\nFormat=2\r\n[Profile3]\r\nCoreClkBoost=100000\r\n") == "INVALID",
          "F3: a profile store whose sections are not the curve3 snapshot's is invalid")

    # ------------------------------------------------ GPT Job 100 F2: the full mVolt+ status record
    def mv(field, value, which=1):
        def edit(number, status):
            if number == which:
                keys = field.split(".")
                target = status
                for k in keys[:-1]:
                    target = target[k]
                target[keys[-1]] = value
        return edit
    check(status_of(mvolt_edit=mv("voltage_demand_mv.Core", 25)) == "INVALID",
          "Job 100 F2: a non-zero core voltage demand in the full record invalidates the day, though the summary reads 0")
    check(status_of(mvolt_edit=mv("nvvdd_offsets_uv.rel", 1000, which=2)) == "INVALID",
          "Job 100 F2: a non-zero NVVDD offset, absent from the summary, invalidates the day")
    check(status_of(mvolt_edit=lambda number, status: "absent" if number == 1 else None) == "INVALID",
          "Job 100 F2: a missing full mVolt+ status record invalidates the day")
    check(status_of(mvolt_edit=mv("power_limits.enforced_mw", 200000)) == "INVALID",
          "Job 100 F2: a full record showing 200 W enforced invalidates the day")

    # ------------------------------------------------ GPT Job 100 F3: the final event read's coverage
    def stale_final(m):
        final = m["driverEventsFinal"]
        final["read_at_unix"] = final["session_start_unix"]
    check(status_of(manifest_edit=stale_final) == "INVALID",
          "Job 100 F3: a final event read taken before the sweeps does not cover the day")
    check(status_of(manifest_edit=lambda m: m["driverEventsFinal"].pop("session_start_unix")) == "INVALID",
          "Job 100 F3: a final event read with no window start does not cover the day")

    # ------------------------------------------------ GPT Jobs 99 F4 / 100 F1: line endings
    def lf_runner(folder):
        f = folder / "runner-Invoke-Rerun15Session.ps1.txt"
        f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))
    with tempfile.TemporaryDirectory() as temporary:
        root = make_repo(Path(temporary), [(1, DATES[0])])
        folder = write_day(root, 1, DATES[0])
        lf_runner(folder)
        lf = score([folder], repo=root)["days"][0]
        check(lf["status"] == "SCOREABLE" and lf["runner_hash_match"] == "CRLF reconstruction of the filed copy",
              "Jobs 99/100: an LF checkout of the filed runner matches its CRLF launch hash, and says so")

    # ------------------------------------------------ F4: non-finite and absent telemetry
    for column, value, what in (("achieved_frequency_max", "nan", "a NaN achieved maximum"),
                                ("achieved_frequency_min", "nan", "a NaN achieved minimum"),
                                ("temperature_max_c", "nan", "a NaN temperature"),
                                ("throttle_masks_seen", "", "an empty throttle record"),
                                ("achieved_frequency_avg", "1600", "a mean outside its own minimum and maximum")):
        check(single(edits=mutate_row("pass1-copy", column, value))["status"] == "INVALID", f"F4: {what} invalidates the day")
    check(status_after(mutate_json("pass2-gemm", "power_limit_enforced_w", "nan")) == "INVALID",
          "F4: a NaN enforced power limit invalidates the day")

    # ------------------------------------------------ F5: the secondary energy figure
    def no_energy(role, rows):
        if role == "pass2-gemm":
            rows[0] = dict(rows[0], energy_avg_power_w="")
        return rows
    e = run([1] * 3, edits=no_energy)
    check(e["energy"]["gemm"] is None and e["workloads"]["gemm"] is not None,
          "a missing energy figure removes that secondary result only")
    z = run([1] * 3, edits=mutate_row("pass1-reduce", "energy_avg_power_w", "0"))
    check(z["energy"]["reduce"] is None and z["workloads"]["reduce"] is not None and z["D"] == 3,
          "F5: a zero energy figure removes that secondary result only, with no division by zero")

    # ------------------------------------------------ F6: every registered curve output is reported
    full = run([1, 2, 3, 2, 2])
    c = full["workloads"]["gemm"]["curve"][1612]
    check(all(k in c for k in ("ci95", "log_sd_ci95", "shape_ci95", "shape_min", "shape_max")),
          "F6: each target carries its pointwise, log-SD and shape intervals and ranges")
    # At 1612 every day reads 0.9 against a reference of 1 - r/100, so the shape is 100 ln(0.9 / (1 - r/100)).
    shapes = [100 * math.log(0.9 / (1 - x / 100)) for x in (1, 2, 3, 2, 2)]
    check(abs(c["shape_min"] - min(shapes)) < 1e-9 and abs(c["shape_max"] - max(shapes)) < 1e-9,
          "F6: the shape range at 1612 matches 100 ln(0.9 / (1 - r/100)) by hand")
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        report(full)
    text = printed.getvalue()
    check("2317" in text and "peaks by direction" in text and "within 1% of the peak" in text,
          "F6: the report prints all 20 targets, the direction peaks and the near-optimal sets")
    json.dumps(to_json(full))
    check(True, "F6: the results serialize to JSON for --json")

    # ------------------------------------------------ F7: the runner as run
    def other_runner(folder):
        (folder / "runner-Invoke-Rerun15Session.ps1.txt").write_bytes(b"# a later checkout\r\n")
    check(status_after(other_runner) == "INVALID", "F7: a filed runner that is not the one hashed at launch is invalid")
    check(status_of(manifest_edit=lambda m: m.pop("sources")) == "INVALID", "F7: a day without source hashes is invalid")
    spec = importlib.util.spec_from_file_location("file_repeatability_day", FILER)
    filer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(filer)
    with tempfile.TemporaryDirectory() as temporary:
        session = Path(temporary) / "20261020-090000-rep"
        session.mkdir()
        manifest = {"section": "REGISTERED-PREDICTIONS section 22 (day-to-day repeatability)", "dryRun": False,
                    "repeatability": {"day": 1, "localDate": "2026-10-20"},
                    "sweeps": {"pass1-gemm": {"sweep": str(session / "x" / "20261020-090000_rep-pass1-gemm_sweep.csv")}}}
        (session / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
        try:
            filer.plan(session)
            refused = False
        except ValueError:
            refused = True
        check(refused, "F7: the filer refuses a session without the runner's own launch copy")
        (session / "runner-as-run.ps1.txt").write_bytes(RUNNER_TEXT)
        check(filer.plan(session)[1] == "day1-20261020", "the filer plans a complete session")
        manifest["sweeps"]["pass1-gemm"]["sweep"] = manifest["sweeps"]["pass1-gemm"]["sweep"].replace("_rep-", "_repdry-")
        (session / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
        try:
            filer.plan(session)
            refused = False
        except ValueError:
            refused = True
        check(refused, "F3: the filer refuses a repdry- sweep even when the manifest says dryRun false")

    # ------------------------------------------------ F8: a VID curve that returns to its minimum
    with tempfile.TemporaryDirectory() as temporary:
        sweep = Path(temporary) / "x_sweep.csv"
        volts = {t: (0.720 if t <= 1575 else 0.730) for t in GRID}

        def floor(v):
            with open(Path(temporary) / "x_sweep_voltage.csv", "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["target", "voltage", "sampleCount"])
                writer.writerows((t, v[t], 20) for t in GRID)
            return measured_floor(sweep)
        clean = floor(volts)
        check(clean["last_floor_target"] == 1575 and clean["first_rise_target"] == 1612 and not clean["reenters"],
              "F8: a clean floor ends at 1575 and rises at 1612")
        back = floor({**volts, 1687: 0.720})
        check(back["reenters"] and back["last_floor_target"] == 1575, "F8: a return to the minimum is flagged as ambiguous")
        missing = dict(volts)
        missing.pop(2010)
        with open(Path(temporary) / "x_sweep_voltage.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["target", "voltage", "sampleCount"])
            writer.writerows((t, missing[t], 20) for t in GRID if t in missing)
        check(measured_floor(sweep) is None, "F8: a voltage extract missing a grid target gives no floor")


if __name__ == "__main__":
    sys.exit(main())
