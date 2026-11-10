"""Synthetic section 20b sessions; no measurement files are read or written.

Each fixture is a complete session directory built from design.schedule with every piece of evidence
the scorer requires, then damaged in one way. The defects are the registration draft's list plus every
mutation GPT Job 73 showed the first scorer accepting (F7, F8, F9): cached T or work that disagrees with
the raw evidence, missing warm-up or preload, an empty temperature record, a non-finite clock, failed
exit codes, a missing background ledger, a failed reset, a wrong seed or constant, failed reader
statuses, malformed brackets, a BOM, and confirmation without a frozen plan."""
import csv
import json
import math
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "section20b"))
import design  # noqa: E402
from reader import columns_for  # noqa: E402
from score_section20b import (classify, confirmation_size, score_session, summarise,  # noqa: E402
                              t_quantile)
from score_section20b import main as score_main  # noqa: E402


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def reader_rows(arm, t0, t1, step=0.05, stale=False, bad_status=False):
    columns = columns_for(arm)
    rows, m, seq = [], t0 - 1.0, 0
    while m <= t1 + 0.5:
        row = {"seq": seq, "mono_before": m, "mono_after": m + 0.0007, "unix": 1.79e9 + m}
        offset = 0.0001
        for column in columns[4:]:
            if column.endswith(("_mono_before", "_mono_after")):
                row[column] = m + offset  # in column order: usage before and after, then the batch
                offset += 0.0001
            elif column.endswith("_ret"):
                row[column] = 999 if bad_status else 0
            elif column.endswith("_type"):
                row[column] = 3 if column.startswith("f83") else 1
            elif column.endswith("_ts_us"):
                row[column] = 0 if stale else int((m + 10000) * 10) * 100000
            elif column.endswith("_latency_us"):
                row[column] = 5
            else:
                row[column] = 150000
        rows.append(row)
        m += step
        seq += 1
    return columns, rows


def make_session(root, index=1, stage="pilot", effect=None, cell_effect=None, mutate=None, reader_step=None,
                 a_reads=False, stale_arm=None, a_last_scale=None, driver_events=0, forbidden=False,
                 drop_last=False, date="2026-10-11", plan_edit=None, status_edit=None, bad_status_arm=None,
                 bom=False, cleanup_ok=True, events_query_ok=True, name=None, cleanup_edit=None):
    """effect[arm] is a % change in counter power; cell_effect[(cell, arm)] overrides per cell.
    a_last_scale multiplies wall throughput of A's last visit to cell 0."""
    effect = effect or {}
    session = Path(root) / (name or f"s{index}-{stage}-{date}")
    session.mkdir(parents=True)
    windows = design.schedule(index)
    plan = {"section": "20b", "kind": "core", "stage": stage, "session_index": index,
            "seed": design.SEED_BASE + index, "washout_seconds": design.WASHOUT_SECONDS,
            "preload_seconds": design.PRELOAD_SECONDS, "warmup_iterations": design.WARMUP_ITERATIONS,
            "started_local_date": date, "provenance": {"commit": "abc123"}, "windows": windows}
    if plan_edit:
        plan_edit(plan)
    (session / "schedule.json").write_text(json.dumps(plan), encoding="utf-8")
    last_a = max(w["index"] for w in windows if w["arm"] == "A" and w["cell"] == 0)
    records = []
    for w in windows:
        base_p = 100.0 + 10 * w["cell"]
        pct = (cell_effect or {}).get((w["cell"], w["arm"]), effect.get(w["arm"], 0.0))
        p = base_p * (1 + pct / 100.0)
        t = 10.0 / a_last_scale if a_last_scale and w["index"] == last_a else 10.0
        size, per_iteration, unit = design.WORKLOAD_SPEC[w["workload"]]
        start = 100.0 * w["index"]
        e0 = 1_000_000_000
        e1 = e0 + round(p * t * 1000.0)
        s_call = {"mono_before": start, "mono_after": start + 0.0004, "value_mj": e0}
        e_call = {"mono_before": start + t, "mono_after": start + t + 0.0004, "value_mj": e1}
        detail = {"energy_start": s_call, "energy_end": e_call,
                  "duration_t_seconds": (e_call["mono_before"] + e_call["mono_after"]) / 2
                  - (s_call["mono_before"] + s_call["mono_after"]) / 2,
                  "work_per_iteration": per_iteration, "work_units": per_iteration * w["iterations"],
                  "work_mono_start": start + 0.001, "work_mono_end": start + t - 0.001,
                  "warmup_iterations": 5, "preload_seconds_requested": 1.0, "preload_seconds": 1.002,
                  "preload_iterations": 300, "energy_support_reads": [{"ok": True, "value_mj": e0 - 5000}],
                  "temperature_reads": [{"value_c": 45.0}, {"value_c": 50.0}],
                  "clocks_before_start": {"sm_mhz": w["target_mhz"] - 8, "mem_mhz": 13801},
                  "clocks_after_end": {"sm_mhz": w["target_mhz"] - 8, "mem_mhz": 13801}}
        tag = f"w{w['index']:03d}-{w['arm']}"
        csv_name = f"{tag}-reader.csv"
        columns, rows = reader_rows(w["arm"], start, start + t, reader_step or 0.05,
                                    stale=(w["arm"] == stale_arm), bad_status=(w["arm"] == bad_status_arm))
        if a_reads and w["arm"] == "A":
            columns, rows = reader_rows("E", start, start + t)
        with (session / csv_name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        calls = len(design.MODE_CALLS[w["arm"]]) * len(rows)
        rec = dict(w, tag=tag, reader_csv=csv_name, lock_exit=0, workload_exit_code=0, reader_exit_code=0,
                   events={"washout_start": start - 40.0, "washout_end": start - 10.0},
                   reader_ready={"mode": w["arm"]},
                   reader_done={"mode": w["arm"], "rows": len(rows), "nvml_power_energy_calls": calls, "failed_calls": 0},
                   result={"ok": True, "aborted": False, "workload": w["workload"], "dtype": "fp32", "size": size,
                           "iterations_requested": w["iterations"], "throughput_unit": unit,
                           "iterations_completed": w["iterations"], "endpoint_detail": detail})
        records.append(rec)
    if mutate:
        records = mutate(records)
    if drop_last:
        records = records[:-1]
    (session / "windows.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    background = [{"when": when, "row_visit": v, "inventory_ok": True, "pollers": [],
                   "claude_visible_windows": 0, "forbidden": ["hwinfo64.exe"] if forbidden and v == 0 else []}
                  for v in range(4) for when in ("before", "after")]
    status = {"complete": not drop_last, "exit_code": 0 if not drop_last else 3, "background": background,
              "failure": "w143: interrupted" if drop_last else None, "preflight_problems": [], "reset_exit": 0,
              "preflight": {"gpu": {"driver_version": "616.92", "power.limit": "180.00", "utilization.gpu": "0",
                                    "utilization.encoder": "0", "utilization.decoder": "0"},
                            "background": {"inventory_ok": True, "forbidden": [], "pollers": [],
                                           "claude_visible_windows": 0}},
              "watcher_cleanup": {"exit_code": 0, "reaped": True, "errors": []},
              "after_reset": {"clocks.sm": "210", "clocks.mem": "405", "pstate": "P8", "temperature.gpu": "38",
                              "mono": 99999.0}}
    if status_edit:
        status_edit(status)
    (session / "status.json").write_text(json.dumps(status), encoding="utf-8")
    prefix = "﻿" if bom else ""
    (session / "driver-events.json").write_text(prefix + json.dumps({"count": driver_events, "query_ok": events_query_ok}),
                                                encoding="utf-8")
    cleanup = {"ok": cleanup_ok, "reset_exit": 0, "store_restored": True, "memory_loaded_mhz": 13801,
               "power_limit_w": 180}
    if cleanup_edit:
        cleanup = cleanup_edit(cleanup)
    (session / "runner-cleanup.json").write_text(prefix + json.dumps(cleanup), encoding="utf-8")
    return session


def edit_detail(position, change):
    def mutate(records):
        change(records[position]["result"]["endpoint_detail"], records[position])
        return records
    return mutate


def main():
    for df, ref in [(1, 50.92303663648572), (3, 5.391949071934058), (7, 3.3352949398170826),
                    (11, 2.980872430052668), (31, 2.6519126890308016), (437, 2.508089206682119)]:
        got = t_quantile(1 - 0.05 / 8, df)
        check(abs(got - ref) < 1e-6, f"t(0.99375, {df}) = {got:.6f} matches scipy's {ref:.6f}")
    for sd, s in [(0.5, 8), (0.7646, 12), (1.0, 18), (2.29376, None), (5.556735, None)]:
        check(confirmation_size(sd) == s, f"a pilot SD of {sd} pp sizes confirmation at S = {s}")
    check(classify(-1.9, 1.9) == "PRACTICALLY EQUIVALENT", "an interval strictly inside the band is equivalent")
    check(classify(-2.0, 1.0) == "INCONCLUSIVE", "an interval touching -2 is inconclusive")
    check(classify(2.0, 3.0) == "INCONCLUSIVE", "an interval touching +2 from above is inconclusive")
    check(classify(2.01, 3.0) == "MATERIAL INCREASE", "an interval wholly above +2 is a material increase")
    check(classify(-3.0, -2.01) == "MATERIAL DECREASE", "an interval wholly below -2 is a material decrease")
    check(classify(0.5, 1.5) == "PRACTICALLY EQUIVALENT", "a nonzero effect inside the band is still equivalent")
    check(classify(1.0, 2.5) == "INCONCLUSIVE", "excluding zero while crossing +2 is inconclusive")

    with tempfile.TemporaryDirectory() as tmp:
        n = iter(range(1000))

        def score(**kw):
            kw.setdefault("name", f"case{next(n)}")
            return score_session(make_session(tmp, **kw))

        clean = score()
        check(clean["valid"] and clean["scoreable"] and not clean["problems"], "a clean session is valid and scoreable")
        check(all(abs(v) < 1e-3 for v in clean["contrasts"].values()), "no effect gives zero contrasts")
        check(set(clean["positions"]) == {0, 1, 2, 3}, "the four row-position summaries are reported")

        c = score(effect={"E": 3.0, "P": -1.0, "EP": 5.0})["contrasts"]
        check(abs(c["d_E"] - 3) < 1e-3 and abs(c["d_P"] + 1) < 1e-3 and abs(c["d_EP"] - 5) < 1e-3
              and abs(c["d_I"] - 3) < 1e-3, "contrasts and the interaction are computed against each row's A")
        c = score(effect={"EP": 4.0})["contrasts"]
        check(abs(c["d_I"] - 4) < 1e-3 and abs(c["d_E"]) < 1e-3, "a large interaction with null singles is reported as such")
        cells = {(cell, "E"): (3.0 if cell < 4 else -3.0 if cell < 8 else 0.0) for cell in range(9)}
        r = score(cell_effect=cells)
        check(abs(r["contrasts"]["d_E"]) < 1e-3 and abs(r["per_cell"][0]["d_E"] - 3) < 1e-3,
              "cancelling cells average to zero while the per-cell values stay visible")

        def invalid(message, needle=None, **kw):
            r = score(**kw)
            ok = not r["valid"] and not r["scoreable"] and (needle is None or any(needle in p for p in r["problems"]))
            check(ok, message + ("" if ok else f" -- problems: {r['problems'][:3]}"))

        invalid("an SM clock 40 MHz off target invalidates", "SM clock",
                mutate=edit_detail(10, lambda d, r: d["clocks_before_start"].update(sm_mhz=r["target_mhz"] + 40)))
        invalid("a NaN SM clock invalidates", "SM clock",
                mutate=edit_detail(10, lambda d, r: d["clocks_after_end"].update(sm_mhz=float("nan"))))
        invalid("a memory clock outside 13801-14001 invalidates", "memory clock",
                mutate=edit_detail(11, lambda d, r: d["clocks_after_end"].update(mem_mhz=7001)))
        invalid("a zero-energy window invalidates", "invalid endpoints",
                mutate=edit_detail(3, lambda d, r: d["energy_end"].update(value_mj=d["energy_start"]["value_mj"])))
        invalid("a non-integer energy counter invalidates", "invalid endpoints",
                mutate=edit_detail(3, lambda d, r: d["energy_end"].update(value_mj=float("nan"))))
        invalid("a cached T that disagrees with the brackets invalidates (F7)", "cached T",
                mutate=edit_detail(5, lambda d, r: d.update(duration_t_seconds=d["duration_t_seconds"] * 2)))
        invalid("cached work that disagrees with the iterations invalidates (F7)", "work",
                mutate=edit_detail(5, lambda d, r: d.update(work_units=d["work_units"] * 2)))
        invalid("a missing bracket field is a recorded problem, not a crash", "brackets",
                mutate=edit_detail(6, lambda d, r: d["energy_start"].pop("mono_before")))
        invalid("no warm-up invalidates", "warm-up", mutate=edit_detail(7, lambda d, r: d.update(warmup_iterations=0)))
        invalid("no preload invalidates", "preload",
                mutate=edit_detail(7, lambda d, r: d.update(preload_seconds_requested=0, preload_seconds=0)))
        invalid("an empty temperature record invalidates", "temperature",
                mutate=edit_detail(8, lambda d, r: d.update(temperature_reads=[])))
        invalid("a temperature at the ceiling invalidates", "temperature",
                mutate=edit_detail(8, lambda d, r: d["temperature_reads"].append({"value_c": 88.0})))
        invalid("a failed support read invalidates", "support",
                mutate=edit_detail(9, lambda d, r: d.update(energy_support_reads=[{"ok": False}])))
        invalid("a short washout invalidates", "washout",
                mutate=edit_detail(2, lambda d, r: r["events"].update(washout_end=r["events"]["washout_start"] + 5)))

        def wrong_work(records):
            records[13]["result"].update(workload="reduce", size=1, dtype="float64")
            return records
        invalid("a benchmark that ran other work than scheduled invalidates (R6)", "scheduled work", mutate=wrong_work)
        invalid("doubled work per iteration, consistently cached, invalidates (R6)", "scheduled work",
                mutate=edit_detail(14, lambda d, r: d.update(work_per_iteration=d["work_per_iteration"] * 2,
                                                             work_units=d["work_units"] * 2)))
        invalid("reversed fixed-work bounds invalidate (R6)", "fixed-work bounds",
                mutate=edit_detail(15, lambda d, r: d.update(work_mono_start=-1, work_mono_end=-2)))

        def exits(records):
            records[12].update(lock_exit=42, workload_exit_code=42, reader_exit_code=42)
            return records
        invalid("non-zero process exit codes invalidate (F7)", "exit", mutate=exits)

        def duplicate(records):
            records[5] = dict(records[4], index=records[5]["index"])
            return records
        invalid("a duplicated window invalidates", mutate=duplicate)

        def swapped(records):
            records[0], records[1] = records[1], records[0]
            return records
        invalid("windows run out of schedule order invalidate", "does not match the schedule", mutate=swapped)

        def swap_plan(plan):
            plan["windows"][0], plan["windows"][1] = plan["windows"][1], plan["windows"][0]
        invalid("a saved schedule that differs from the seed's invalidates", "not design.schedule", plan_edit=swap_plan)
        invalid("a wrong seed invalidates", "seed", plan_edit=lambda p: p.update(seed=1))
        invalid("a wrong washout constant invalidates", "washout_seconds", plan_edit=lambda p: p.update(washout_seconds=10))
        invalid("a missing commit invalidates", "commit", plan_edit=lambda p: p.update(provenance={}))
        invalid("a pilot session numbered outside 1-4 invalidates", "not a pilot index",
                index=101, plan_edit=lambda p: None)
        invalid("power or energy reads in the baseline arm invalidate", "columns", a_reads=True)
        invalid("failed reader statuses invalidate even with a clean summary (F7)", "returned", bad_status_arm="E")

        def short_csv(records):
            records[1]["reader_done"]["rows"] += 3
            return records
        invalid("a reader row count that disagrees with its summary invalidates", "reader rows", mutate=short_csv)

        r = score(stale_arm="E")
        check(r["valid"] and r["stale_max_s"] > 5, "a stale field is reported and does not by itself invalidate")
        invalid("a slow reader cadence invalidates", "cadence", reader_step=0.12)

        r = score(a_last_scale=1.015)
        check(r["valid"] and r["scoreable"] and abs(r["return_worst_pct"] - 1.5) < 1e-6, "a return change of exactly 1.5% passes")
        r = score(a_last_scale=1.0151)
        check(r["valid"] and not r["scoreable"], "a return change above 1.5% leaves the session valid but NOT SCOREABLE")

        invalid("a partial session is invalid", drop_last=True)
        invalid("a display-driver event invalidates", "driver-events", driver_events=1)
        invalid("an event log that could not be read invalidates", "driver-events", events_query_ok=False)
        invalid("a forbidden process invalidates", "forbidden", forbidden=True)
        invalid("a missing background record invalidates (F7)", "no background check",
                status_edit=lambda s: s.update(background=s["background"][:-1]))
        invalid("an external poller in the background record invalidates (F4)", "pollers",
                status_edit=lambda s: s["background"][3].update(pollers=["python sample_power.py --hz 20"]))
        invalid("a visible Claude window invalidates", "Claude",
                status_edit=lambda s: s["background"][2].update(claude_visible_windows=1))
        invalid("a failed clock reset invalidates (F1)", "reset", status_edit=lambda s: s.update(reset_exit=9))
        # GPT Job 91, F4: the raw evidence is checked, not only the cached verdicts.
        invalid("no watcher stop record invalidates (Job 91 F4)", "watcher", status_edit=lambda s: s.pop("watcher_cleanup"))
        invalid("a watcher that exited 3, unreaped, invalidates", "watcher",
                status_edit=lambda s: s.update(watcher_cleanup={"exit_code": 3, "reaped": False, "errors": ["x"]}))
        for field, value in (("driver_version", "999.99"), ("power.limit", "200.00"), ("utilization.gpu", "99"),
                             ("utilization.encoder", "21")):
            invalid(f"a recorded preflight {field} of {value} invalidates despite empty cached problems", "preflight",
                    status_edit=lambda s, f=field, v=value: s["preflight"]["gpu"].update({f: v}))
        invalid("a preflight background with a forbidden process invalidates", "preflight background",
                status_edit=lambda s: s["preflight"]["background"].update(forbidden=["hwinfo64.exe"]))
        invalid("a failed background record followed by a clean duplicate invalidates", "exactly one",
                status_edit=lambda s: s.update(background=[dict(s["background"][0], inventory_ok=False)] + s["background"]))
        invalid("a preflight problem invalidates", "preflight",
                status_edit=lambda s: s.update(preflight_problems=["driver 1.0"]))
        invalid("a runner cleanup that did not restore stock invalidates (F1)", "runner-cleanup", cleanup_ok=False)
        r = score(bom=True)
        check(r["valid"], "PowerShell's byte-order mark in the runner's JSON is read, not a crash (F9)")
        invalid("a background record without its poller and window decisions invalidates (R6)", "lacks",
                status_edit=lambda s: [b.pop("pollers") for b in s["background"][:1]])

        session = make_session(tmp, name="nan-brackets")
        e_csv = sorted(session.glob("w*-E-reader.csv"))[0]
        rows = list(csv.DictReader(e_csv.open(encoding="utf-8")))
        for row in rows:
            row["mono_after"] = row["batch_mono_after"] = "nan"
        with e_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        r = score_session(session)
        check(not r["valid"] and any("timing brackets" in p for p in r["problems"]),
              "NaN reader brackets with valid poll starts invalidate (R6)")
        session = make_session(tmp, name="null-window")
        lines = (session / "windows.jsonl").read_text(encoding="utf-8").splitlines()
        (session / "windows.jsonl").write_text("\n".join(["null"] + lines[1:]) + "\n", encoding="utf-8")
        check(not score_session(session)["valid"], "a null window record is reported as invalid, not a crash (R6)")
        invalid("string provenance is reported as invalid, not a crash (R6)", None,
                plan_edit=lambda p: p.update(provenance="abc123"))
        session = make_session(tmp, name="no-events")
        (session / "driver-events.json").unlink()
        check(not score_session(session)["valid"], "a session without a driver-event record is invalid")
        # ---- GPT Job 76: cleanup evidence is inspected, and malformed fields are reported ----
        contradictory = {"ok": True, "reset_exit": 9, "store_restored": False, "memory_loaded_mhz": 16301,
                         "power_limit_w": 200}
        r = score(cleanup_edit=lambda c: contradictory)
        check(not r["valid"] and any("reset_exit 9" in q and "store_restored" in q and "16301" in q and "200" in q
                                     for q in r["problems"]),
              "a runner record saying ok beside a failed reset, unrestored store, 16301 MHz and 200 W invalidates (Job 76, R1)")
        invalid("a missing readback after the reset invalidates (Job 76, R1)", "readback",
                status_edit=lambda s: s.pop("after_reset"))
        invalid("an infinite temperature in the readback after the reset invalidates (Job 76, R1)", "readback",
                status_edit=lambda s: s["after_reset"].update({"temperature.gpu": "inf"}))
        invalid("an error-only readback after the reset invalidates (Job 76, R1)", "readback",
                status_edit=lambda s: s.update(after_reset={"error": "nvidia-smi failed"}))
        for name in ("driver-events.json", "runner-cleanup.json"):
            session = make_session(tmp, name=f"null-{name}")
            (session / name).write_text("null", encoding="utf-8")
            r = score_session(session)
            check(not r["valid"] and any(name in q for q in r["problems"]), f"a null {name} is invalid, not a crash (Job 76, R6)")
        malformed = {
            "a string session index": dict(plan_edit=lambda p: p.update(session_index="1")),
            "a null scheduled window": dict(plan_edit=lambda p: p.update(windows=[None] + p["windows"][1:])),
            "an integer for the window list": dict(plan_edit=lambda p: p.update(windows=1)),
            "a list as a background 'when'": dict(status_edit=lambda s: s["background"][0].update(when=[])),
            "a list as a window's row": dict(mutate=lambda recs: [dict(recs[0], row=[])] + recs[1:]),
            "an energy counter too large for a float": dict(
                mutate=edit_detail(3, lambda d, rec: d["energy_end"].update(value_mj=10 ** 400))),
        }
        for label, kwargs in malformed.items():
            try:
                r = score(**kwargs)
                check(not r["valid"] and r["problems"], f"{label} is reported as invalid, not a crash (Job 76, R6)")
            except Exception as exc:  # noqa: BLE001 - the point is that nothing escapes
                check(False, f"{label} is reported as invalid, not a crash ({type(exc).__name__}: {exc})")
        session = make_session(tmp, name="garbled")
        (session / "status.json").write_text("{not json", encoding="utf-8")
        check(not score_session(session)["valid"], "unreadable session files are reported as invalid, not a crash")

    def fake(stage, index, values, scoreable=True, date=None, path=None):
        return {"stage": stage, "session_index": index, "scoreable": scoreable, "date": date or f"2026-10-{10 + index % 20:02d}",
                "dir": path or f"/s/{stage}{index}-{date}", "contrasts": {c: values[i] for i, c in enumerate(design.CONTRASTS)}}
    pilot = [fake("pilot", i + 1, [0.1 * i, 0.2 * i, -0.1 * i, 0.05 * i]) for i in range(4)]
    s = summarise(pilot)["pilot"]
    sd_p = math.sqrt(sum((0.2 * i - 0.3) ** 2 for i in range(4)) / 3)
    check(abs(s["s_max"] - sd_p) < 1e-12 and s["S"] == confirmation_size(sd_p), "four pilot sessions size confirmation")
    s = summarise(pilot[:3] + [fake("pilot", 4, [9, 9, 9, 9], scoreable=False)])["pilot"]
    check(s["sessions"] == 3 and "S" not in s, "an unscoreable pilot session leaves the pilot incomplete")
    s = summarise(pilot[:3] + [fake("pilot", 4, [0, 0, 0, 0], date=pilot[0]["date"])])["pilot"]
    check(s.get("state") == "NOT SCOREABLE", "two pilot sessions on the same day are refused")
    s = summarise(pilot + [dict(pilot[0])])["pilot"]
    check(s.get("state") == "NOT SCOREABLE", "the same pilot directory submitted twice is refused")
    attempts = [fake("pilot", 1, [0, 0, 0, 0], scoreable=False, date=f"2026-11-0{i}", path=f"/r{i}") for i in range(1, 4)]
    s = summarise(pilot + attempts)["pilot"]
    check(s.get("state") == "NOT SCOREABLE", "more than one replacement for a session is refused")

    replaced = pilot[:3] + [fake("pilot", 4, [0, 0, 0, 0], scoreable=False, date="2026-10-14", path="/fail4"),
                            fake("pilot", 4, [0.3, 0.6, -0.3, 0.15], date="2026-10-14", path="/redo4")]
    check(summarise(replaced)["pilot"].get("state") == "NOT SCOREABLE", "a replacement on the same day as its failure is refused (R7)")
    replaced[-1] = dict(replaced[-1], date="2026-10-16")
    check("S" in summarise(replaced)["pilot"], "a replacement on a later day completes the pilot")
    bad_date = pilot[:3] + [fake("pilot", 4, [0, 0, 0, 0], date="not-a-date")]
    check(summarise(bad_date)["pilot"].get("state") == "NOT SCOREABLE", "a session without a real date is refused (R7)")

    two_bad = pilot[:2] + [fake("pilot", 3, [0, 0, 0, 0], date="not-a-date"), fake("pilot", 4, [0, 0, 0, 0], date=None)]
    check(summarise(two_bad)["pilot"].get("state") == "NOT SCOREABLE",
          "two sessions without real dates are refused, not a crash sorting them (Job 76, R7)")

    confirm = [fake("confirmation", 101 + i, [0.1 * (i % 3)] * 4, date=f"2026-12-{i + 1:02d}") for i in range(8)]
    out = summarise(pilot + confirm)["confirmation"]
    check(out["state"] == "NOT SCOREABLE", "confirmation without a frozen S issues no intervals (F8)")
    out = summarise(pilot + confirm[:2], {"S": 8})["confirmation"]
    check(out["state"] == "INCOMPLETE" and "intervals" not in out, "two of eight planned confirmations issue no intervals (F8)")
    copies = [dict(confirm[0], session_index=101 + i, dir=f"/c{i}", date=f"2026-12-{i + 1:02d}") for i in range(8)]
    check("intervals" in summarise(pilot + copies, {"S": 8})["confirmation"],
          "eight distinct planned confirmation sessions issue intervals")
    same_day = [dict(c, date="2026-12-01") for c in confirm]
    check(summarise(pilot + same_day, {"S": 8})["confirmation"]["state"] == "NOT SCOREABLE",
          "confirmation sessions on one day are refused")
    reused = confirm[:7] + [dict(pilot[0], stage="confirmation", session_index=108, date="2026-12-31")]
    check(summarise(pilot + reused, {"S": 8})["confirmation"]["state"] == "NOT SCOREABLE",
          "a pilot session resubmitted as confirmation is refused")
    for plan in (1, "x", [8]):
        check(summarise(pilot + confirm, plan)["confirmation"]["state"] == "NOT SCOREABLE",
              f"a frozen plan that is not an object ({plan!r}) is refused, not a crash (Job 76, R7)")
    with tempfile.TemporaryDirectory() as tmp:
        bad_plan = Path(tmp) / "plan.json"
        bad_plan.write_text("{not json", encoding="utf-8")
        session = make_session(tmp, name="cli")
        check(score_main([str(session), "--frozen-plan", str(bad_plan)]) == 1,
              "an unreadable frozen plan is reported with exit 1, not a traceback (Job 76, R7)")
    full = summarise(pilot + confirm, {"S": 8})["confirmation"]["intervals"]["d_E"]
    check(full["low"] < 0.1 < full["high"], "confirmation intervals use the confirmation sessions only")
    print("All section 20b scorer checks passed.")


if __name__ == "__main__":
    main()
