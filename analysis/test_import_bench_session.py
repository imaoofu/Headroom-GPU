"""Checks for import_bench_session.py (GPT Job 88, R4); synthetic kit folders only, no GPU.

The importer was also run on the real 2026-10-11 bench-app live session from the USB kit (into a
scratch folder, not data/): both measured steps accepted, each joined to its own log at -07:00,
manifest verified. That session is not committed, so it cannot be a fixture here.
"""

import copy
import csv
import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from import_bench_session import do_import, plan_import, verify_import


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


# A deliberately foreign offset: if the importer fell back to this computer's zone, the HWiNFO
# rows would land hours away from the benchmark windows and the join would find nothing.
OFFSET = "+05:30"
ZONE = timezone(timedelta(hours=5, minutes=30))
START = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc).timestamp()


def write_sweep(folder, label, gpu="NVIDIA GeForce RTX 4060"):
    folder.mkdir(parents=True)
    csv_path = folder / f"20261013-090000_{label}_sweep.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                         "power_avg_w", "window_start_unix", "window_end_unix"])
        writer.writerow([1500, 1500, 3e11, 100, START, START + 5])
        writer.writerow([1600, 1600, 3.1e11, 105, START + 10, START + 15])
    csv_path.with_suffix(".json").write_text(json.dumps({"gpu_name": gpu}), encoding="utf-8")
    return csv_path


def write_log(path):
    with path.open("w", newline="", encoding="latin-1") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Time", "GPU Clock [MHz]", "GPU Core Voltage [V]",
                         "GPU Crossbar Clock [MHz]", "GPU Power [W]"])
        for seconds, mhz, volts in ((1, 1500, 0.72), (2, 1500, 0.72), (11, 1600, 0.73), (12, 1600, 0.73)):
            local = datetime.fromtimestamp(START + seconds, ZONE)
            writer.writerow([local.strftime("%d.%m.%Y"), local.strftime("%H:%M:%S.%f")[:-3], mhz, volts, 1300, 100])


def kit(root):
    """A results folder like the USB kit's: one sweep step that failed, then its accepted retry."""
    results = root / "F" / "headroom-kit" / "results"
    results.mkdir(parents=True)
    recorded = "F:\\headroom-kit\\results\\"
    sweep = write_sweep(results / "run-newcard-dense-asc", "newcard-dense-asc")
    write_log(results / "hwinfo-asc.csv")
    plan = results / "bench-plan-x.json"
    plan.write_text('{"runs": []}', encoding="utf-8")
    load = {"status": "quiet", "flagged": 0, "unchecked": 0, "log": recorded + "hwinfo-asc.csv",
            "utcOffset": OFFSET, "windows": [{"sweep": recorded + "run-newcard-dense-asc\\" + sweep.name}]}
    session = {"schemaVersion": 1, "planHash": hashlib.sha256(plan.read_bytes()).hexdigest().upper(),
               "status": "PASS", "dryRun": False, "gpuName": "NVIDIA GeForce RTX 4060", "gpuUuid": "GPU-abc",
               "driver": "999.99",
               "finalState": {"clocks": {"verified": True}, "logging": {"stoppedVerified": True}},
               "steps": [
                   {"key": "dense-asc/log-start", "type": "hwinfo-start", "verdict": "PASS", "witness": {}},
                   {"key": "dense-asc/sweep", "type": "sweep", "verdict": "FAIL", "error": "driver reset",
                    "witness": None, "desktopLoad": None},
                   {"key": "dense-asc/sweep", "type": "sweep", "verdict": "PASS", "start": "s", "end": "e",
                    "witness": {"output": recorded + "run-newcard-dense-asc"}, "desktopLoad": load}]}
    return results, session, plan


def add_second_step(results, session, log_folder="desc", log_name="hwinfo-asc.csv"):
    """A second accepted sweep whose log has the SAME basename in another folder (GPT Job 89, I1).

    Its sweep windows sit 60 s after the first's, so only its own log covers them."""
    recorded = "F:\\headroom-kit\\results\\"
    folder = results / "run-newcard-dense-des"
    folder.mkdir(parents=True)
    csv_path = folder / "20261013-090100_newcard-dense-des_sweep.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
                         "power_avg_w", "window_start_unix", "window_end_unix"])
        writer.writerow([1600, 1600, 3.1e11, 105, START + 60, START + 65])
        writer.writerow([1500, 1500, 3e11, 100, START + 70, START + 75])
    csv_path.with_suffix(".json").write_text(json.dumps({"gpu_name": "NVIDIA GeForce RTX 4060"}), encoding="utf-8")
    (results / log_folder).mkdir(exist_ok=True)
    with (results / log_folder / log_name).open("w", newline="", encoding="latin-1") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Time", "GPU Clock [MHz]", "GPU Core Voltage [V]",
                         "GPU Crossbar Clock [MHz]", "GPU Power [W]"])
        for seconds, mhz, volts in ((61, 1600, 0.74), (62, 1600, 0.74), (71, 1500, 0.725), (72, 1500, 0.725)):
            local = datetime.fromtimestamp(START + seconds, ZONE)
            writer.writerow([local.strftime("%d.%m.%Y"), local.strftime("%H:%M:%S.%f")[:-3], mhz, volts, 1300, 100])
    load = {"status": "quiet", "flagged": 0, "unchecked": 0, "log": recorded + log_folder + "\\" + log_name,
            "utcOffset": OFFSET, "windows": [{"sweep": recorded + "run-newcard-dense-des\\" + csv_path.name}]}
    session["steps"].append({"key": "dense-desc/sweep", "type": "sweep", "verdict": "PASS",
                             "witness": {"output": recorded + "run-newcard-dense-des"}, "desktopLoad": load})


def save(results, session):
    path = results / "bench-session-x.json"
    path.write_text(json.dumps(session), encoding="utf-8")
    return path


def refused(edit, expect):
    with tempfile.TemporaryDirectory() as temporary:
        results, session, plan = kit(Path(temporary))
        edit(session, results)
        try:
            plan_import(save(results, session), plan)
        except ValueError as exc:
            return expect in str(exc)
        return False


def last(session):
    return session["steps"][-1]


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        results, session, plan = kit(root)
        session_path = save(results, session)
        _, accepted, rejected = plan_import(session_path, plan)
        check(len(accepted) == 1 and accepted[0]["key"] == "dense-asc/sweep",
              "the last attempt of a step is the accepted one")
        check([r["verdict"] for r in rejected] == ["FAIL"] and rejected[0]["error"] == "driver reset",
              "the earlier failed attempt is listed as rejected with its error")
        check(accepted[0]["folder"] == results / "run-newcard-dense-asc",
              "recorded F:\\ kit paths are found beside the session file, wherever the USB is mounted")
        lines = []
        check(do_import(session_path, plan, root / "dest", out=lines.append) is None and not (root / "dest").exists(),
              "without --write nothing is written")
        manifest = do_import(session_path, plan, root / "dest", write=True, out=lines.append, raw_root=root / "raw")
        dest = root / "dest"
        voltage = dest / "run-newcard-dense-asc" / "20261013-090000_newcard-dense-asc_sweep_voltage.csv"
        with voltage.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        check([float(r["voltage"]) for r in rows] == [0.72, 0.73] and {r["hwinfoUtcOffsetMinutes"] for r in rows} == {"330"},
              "the join used the step's recorded +05:30 offset, not this computer's zone")
        check((root / "raw" / "dest" / "hwinfo-asc.csv").is_file() and not (dest / "hwinfo-asc.csv").exists(),
              "the raw HWiNFO log goes to the gitignored raw folder, not into the data folder")
        check(manifest["session"]["gpuUuid"] == "GPU-abc" and len(manifest["rejected"]) == 1
              and (dest / "bench-session-x.json").is_file() and (dest / "bench-plan-x.json").is_file(),
              "IMPORT.json records the UUID and the rejected attempt; session and plan are kept beside it")
        csv_path = dest / "run-newcard-dense-asc" / "20261013-090000_newcard-dense-asc_sweep.csv"
        summary = verify_import(dest, [csv_path], {"NVIDIA GeForce RTX 4060"})
        check(summary == {"uuid": "GPU-abc", "session": "bench-session-x.json", "accepted": 1, "rejected": 1},
              "the imported folder verifies against its own manifest")
        try:
            do_import(session_path, plan, dest, write=True, out=lines.append, raw_root=root / "raw2")
            again = False
        except ValueError:
            again = True
        check(again, "an existing destination is never written into")
        (dest / "bench-session-x.json").write_text("{}", encoding="utf-8")
        try:
            verify_import(dest, [csv_path], {"NVIDIA GeForce RTX 4060"})
            tampered = False
        except ValueError as exc:
            tampered = "changed" in str(exc)
        check(tampered, "a changed copy of the bench session file is refused")

    # ------------------------------------------------ GPT Job 89's importer findings
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        results, session, plan = kit(root)
        add_second_step(results, session)
        manifest = do_import(save(results, session), plan, root / "dest", write=True, out=lambda _: None,
                             raw_root=root / "raw")
        with (root / "dest" / "run-newcard-dense-des" / "20261013-090100_newcard-dense-des_sweep_voltage.csv").open(
                encoding="utf-8") as handle:
            des = [float(r["voltage"]) for r in csv.DictReader(handle)]
        check(des == [0.74, 0.725] and (root / "raw" / "dest" / "desc" / "hwinfo-asc.csv").is_file()
              and (root / "raw" / "dest" / "hwinfo-asc.csv").is_file()
              and [a["log"]["name"] for a in manifest["accepted"]] == ["hwinfo-asc.csv", "desc/hwinfo-asc.csv"],
              "I1: two logs with one basename in different folders stay two logs, each joined to its own sweep")
        (root / "dest" / "bench-plan-x.json").write_text("{}", encoding="utf-8")
        csv_path = root / "dest" / "run-newcard-dense-asc" / "20261013-090000_newcard-dense-asc_sweep.csv"
        try:
            verify_import(root / "dest", [csv_path])
            plan_changed = False
        except ValueError as exc:
            plan_changed = "plan" in str(exc)
        check(plan_changed, "I4: a copied plan changed after import is refused")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        results, session, plan = kit(root)
        nested = results / "sessions"
        nested.mkdir()
        session_path = nested / "bench-session-x.json"
        session_path.write_text(json.dumps(session), encoding="utf-8")
        _, accepted, _ = plan_import(session_path, plan)
        check(accepted[0]["folder"] == results / "run-newcard-dense-asc",
              "I2: a session file in a subfolder of results still finds its outputs under results")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        results, session, plan = kit(root)
        add_second_step(results, session, log_name="other.csv")
        (results / "desc" / "other.csv").write_text("Date,Time,GPU Clock [MHz],GPU Core Voltage [V]\n",
                                                   encoding="latin-1")
        try:
            do_import(save(results, session), plan, root / "dest", write=True, out=lambda _: None,
                      raw_root=root / "raw")
            failed = False
        except ValueError:
            failed = True
        left = [p.name for p in list(root.iterdir()) + list((root / "raw").iterdir() if (root / "raw").exists() else [])
                if p.name.startswith("dest")]
        check(failed and left == [], "a failed join leaves no destination, staging or raw folder behind")

    # GPT Job 93, R3: the second staging folder cannot be made (a file sits where its parent should be).
    # The first must not be left behind to block a retry.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        results, session, plan = kit(root)
        session_path = save(results, session)
        (root / "blocked").write_text("a file, not a folder", encoding="utf-8")
        try:
            do_import(session_path, plan, root / "dest", write=True, out=lambda _: None, raw_root=root / "blocked")
            raised = False
        except OSError:
            raised = True
        retried = do_import(session_path, plan, root / "dest", write=True, out=lambda _: None, raw_root=root / "raw")
        check(raised and not (root / "dest.importing").exists() and retried is not None,
              "a staging folder that cannot be made leaves nothing behind, and a retry succeeds")

    check(refused(lambda s, r: s.update(dryRun=True), "dry run"), "a dry-run session is refused")
    check(refused(lambda s, r: s.update(status="FAIL"), "not 'PASS'"), "a session that finished FAIL is refused")
    check(refused(lambda s, r: s.update(gpuUuid=""), "GPU UUID"), "a session with no GPU UUID is refused")
    check(refused(lambda s, r: s.update(planHash="00"), "SHA-256"), "a plan other than the session's is refused")
    check(refused(lambda s, r: s["finalState"]["clocks"].update(verified=False), "clock reset"),
          "a session whose clock reset was not verified is refused")
    check(refused(lambda s, r: last(s)["desktopLoad"].update(status="DESKTOP LOAD"), "not 'quiet'"),
          "an accepted step flagged for desktop load is refused")
    check(refused(lambda s, r: last(s)["desktopLoad"].update(status="unchecked"), "not 'quiet'"),
          "an accepted step whose desktop load was never checked is refused")
    check(refused(lambda s, r: last(s).update(verdict="DESKTOP LOAD"), "verdict"),
          "an accepted step whose verdict is not PASS is refused")
    check(refused(lambda s, r: last(s)["desktopLoad"].update(utcOffset=""), "UTC offset"),
          "a step with no recorded UTC offset is refused")
    check(refused(lambda s, r: (r / "run-newcard-dense-asc" / "20261013-090001_extra_sweep.csv").write_text("x"),
                  "not the ones"),
          "a sweep CSV the desktop-load check never read is refused")
    check(refused(lambda s, r: s["steps"].append(copy.deepcopy(s["steps"][1])), "verdict"),
          "a later failed retry replaces an earlier pass as the accepted attempt, and is refused")


if __name__ == "__main__":
    main()
