"""Section 20b's design and reader, without a GPU: the schedule's balance and determinism, each arm's
exact NVML calls against a fake library, and the reader's lifecycle as a real process in arm A (which
touches no NVML, so this runs anywhere)."""
import ctypes
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design  # noqa: E402
import reader  # noqa: E402


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


class FakeNvml:
    """Records every call; fills fields with a value of the declared type."""

    def __init__(self, fail_field=None, bad_type=None):
        self.calls = []
        self.fail_field = fail_field
        self.bad_type = bad_type
        self.tick = 0

    def nvmlDeviceGetPowerUsage(self, handle, ref):
        self.calls.append(("usage", None))
        ref._obj.value = 150000
        return 0

    def nvmlDeviceGetFieldValues(self, handle, count, array):
        ids = [array[i].fieldId for i in range(count)]
        self.calls.append(("fields", ids))
        self.tick += 1
        for i in range(count):
            array[i].timestamp = 1000 * self.tick
            array[i].latencyUsec = 5
            if array[i].fieldId == self.fail_field:
                array[i].nvmlReturn = 3
                continue
            array[i].nvmlReturn = 0
            if array[i].fieldId == self.bad_type:
                array[i].valueType = 99
                continue
            if array[i].fieldId == 83:
                array[i].valueType = 3
                array[i].value.ull = 10 ** 9 + self.tick
            else:
                array[i].valueType = 1
                array[i].value.ui = 149000
        return 0

    def nvmlShutdown(self):
        self.calls.append(("shutdown", None))


def main():
    check(design.williams_balanced(), "the registered Williams rows are balanced by position and predecessor")
    broken = dict(design.WILLIAMS_ROWS)
    broken[4] = ["EP", "P", "A", "E"]
    check(not design.williams_balanced(broken), "a square with a repeated predecessor pair is refused")

    windows = design.schedule(1)
    check(len(windows) == 144, "a session has 144 windows")
    check(len({(w["row"], w["cell"], w["arm"]) for w in windows}) == 144, "every row/cell/arm occurs exactly once")
    check(all(sum(1 for w in windows if w["arm"] == a) == 36 for a in design.ARMS), "36 windows per arm")
    contiguous = all([w["arm"] for w in windows[i:i + 4]] == design.WILLIAMS_ROWS[windows[i]["row"]]
                     and len({(w["row"], w["cell"]) for w in windows[i:i + 4]}) == 1 for i in range(0, 144, 4))
    check(contiguous, "within each cell the row's four arms run contiguously, in the row's order")
    rows_in_order = [windows[i]["row"] for i in range(0, 144, 36)]
    check(sorted(rows_in_order) == [1, 2, 3, 4], "each Williams row is visited once, as one block of nine cells")
    check(design.schedule(1) == windows, "the schedule is deterministic for a session index")
    check(design.schedule(2) != windows, "a different session index gives a different schedule")
    check([w["index"] for w in windows] == list(range(144)), "window indices run 0..143 in order")
    q = design.qualification_schedule()
    check(len(q) == 36 and {(w["workload"], w["target_mhz"], w["arm"]) for w in q}
          == {(wl, tg, arm) for wl, tg in design.CELLS for arm in design.ARMS},
          "the qualification runs every arm in every cell once, in 36 windows")
    check({w["row"] for w in q} == set(design.WILLIAMS_ROWS)
          and all([w["arm"] for w in q[i:i + 4]] == design.WILLIAMS_ROWS[q[i]["row"]] for i in range(0, 36, 4)),
          "the qualification uses all four Williams rows, each cell's arms in its row's order")
    check(max(design.TARGETS_MHZ) < 2475, "no cell sits at 2475 MHz, where stock gemm meets the 180 W cap")

    expected = {"A": [], "E": [("fields", [83])], "P": [("usage", None), ("fields", [185, 186])],
                "EP": [("usage", None), ("fields", [185, 186, 83])]}
    for mode, calls in expected.items():
        fake = FakeNvml()
        poll = reader.make_poll(mode, None if mode == "A" else fake, None)
        row, made, failed = poll()
        check(fake.calls == calls and made == len(calls) and failed == 0,
              f"arm {mode} makes exactly {calls or 'no NVML calls'}")
        check(set(row) <= set(reader.columns_for(mode)), f"arm {mode}'s row fits its columns")
    row, _, _ = reader.make_poll("EP", FakeNvml(), None)()
    check(row["usage_mw"] == 150000 and row["f83_value"] == 10 ** 9 + 1 and row["f185_value"] == 149000
          and row["f83_type"] == 3, "values decode by their declared NVML type")
    check(reader.columns_for("A") == ["seq", "mono_before", "mono_after", "unix"], "the baseline logs timing only")
    row, made, failed = reader.make_poll("EP", FakeNvml(fail_field=186), None)()
    check(failed == 1 and row["f186_value"] is None and row["f186_ret"] == 3,
          "a failed field is counted and recorded without a value")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        files = {k: tmp / k for k in ("a.csv", "ready.json", "stop", "done.json")}
        summary = reader.run("E", files["a.csv"], files["ready.json"], files["stop"], files["done.json"],
                             nvml=FakeNvml(), handle=None, max_rows=30)
        check(summary["rows"] == 30 and summary["nvml_power_energy_calls"] == 30 and summary["failed_calls"] == 0,
              "an in-process E reader counts one call per poll")
        check(json.loads(files["ready.json"].read_text())["mode"] == "E" and files["done.json"].exists(),
              "it writes its ready and done files")

        out, ready, stop, done = tmp / "b.csv", tmp / "b-ready.json", tmp / "b-stop", tmp / "b-done.json"
        proc = subprocess.Popen([sys.executable, str(HERE / "reader.py"), "--mode", "A", "--out", str(out),
                                 "--ready-file", str(ready), "--stop-file", str(stop), "--done-file", str(done)])
        deadline = time.perf_counter() + 20
        while not ready.exists() and time.perf_counter() < deadline:
            time.sleep(0.05)
        check(ready.exists() and json.loads(ready.read_text())["calls_per_poll"] == 0, "a real A reader reports ready")
        time.sleep(1.5)
        stop.touch()
        proc.wait(timeout=10)
        result = json.loads(done.read_text())
        check(proc.returncode == 0 and result["nvml_power_energy_calls"] == 0 and result["rows"] > 20,
              "a real A reader stops on the stop file, having made no NVML call")
        lines = out.read_text().splitlines()
        monos = [float(l.split(",")[1]) for l in lines[1:]]
        gaps = [(b - a) * 1000 for a, b in zip(monos, monos[1:])]
        check(45 <= statistics.median(gaps) <= 55, f"its schedule is 50 ms (median {statistics.median(gaps):.1f} ms)")
    row, made, failed = reader.make_poll("E", FakeNvml(bad_type=83), None)()
    check(failed == 1 and row["f83_value"] is None and row["f83_type"] == 99,
          "a successful return with an undecodable type counts as a failed read, type kept")
    row, _, _ = reader.make_poll("P", FakeNvml(), None)()
    check(row["usage_mono_before"] <= row["usage_mono_after"] <= row["batch_mono_before"] <= row["batch_mono_after"]
          and row["mono_before"] <= row["usage_mono_before"] and row["batch_mono_after"] <= row["mono_after"],
          "each API call is bracketed separately, inside the poll's own bracket")
    # ---- controller pieces (GPT Job 75, R1-R4), with stand-ins for every process -------------
    import run_core_session as ctl
    cases = {("nvidia-smi.exe", "nvidia-smi -l 1"): True, ("nvidia-smi.exe", '"C:/x/nvidia-smi.exe" -lms 50'): True,
             ("nvidia-smi.exe", "nvidia-smi dmon"): True, ("nvidia-smi.exe", "nvidia-smi pmon -c 1"): True,
             ("nvidia-smi.exe", "nvidia-smi --loop=1"): True,
             ("nvidia-smi.exe", "nvidia-smi --query-gpu=power.draw --format=csv -l 1"): True,
             ("nvidia-smi.exe", "nvidia-smi -lgc 1545,1545"): False,
             ("nvidia-smi.exe", "nvidia-smi --query-gpu=clocks.sm --format=csv"): False,
             ("python.exe", "python tools/power-probe/sample_power.py --hz 20"): True,
             ("python.exe", "python tools/section20b/reader.py --mode EP"): True,
             ("python.exe", "python -m http.server"): False}
    check(all(ctl.is_poller(n, c) == want for (n, c), want in cases.items()),
          "every looping nvidia-smi form and this repository's readers are pollers; one-off queries are not")
    full = {"clocks.sm": "1462", "clocks.mem": "810", "pstate": "P5", "temperature.gpu": "41"}
    check(ctl.witness_complete(full) and not ctl.witness_complete(dict(full, pstate=""))
          and not ctl.witness_complete({"mono": 1.0}) and not ctl.witness_complete(dict(full, **{"clocks.sm": "n/a"})),
          "only a complete numeric readback after reset counts as acknowledged")
    check(not ctl.witness_complete(dict(full, **{"temperature.gpu": "inf"}))
          and not ctl.witness_complete(dict(full, **{"clocks.sm": "nan"})),
          "an infinite or NaN readback after reset is not an acknowledgement (Job 76, R1)")

    class Proc:
        def __init__(self, polls=1, kill_error=False, wait_error=False):
            self.polls, self.kill_error, self.wait_error, self.killed = polls, kill_error, wait_error, False
            self.returncode = None

        def poll(self):
            self.polls -= 1
            return 0 if self.polls < 0 else None

        def kill(self):
            if self.kill_error:
                raise OSError("kill denied")
            self.killed = True

        def wait(self, timeout=None):
            if self.wait_error:
                raise subprocess.TimeoutExpired("x", timeout)
            return 0

        def communicate(self, timeout=None):
            return b"", b""

    rec = {}
    ctl.kill_and_reap(Proc(kill_error=True), rec, "reader")
    check(rec.get("cleanup_errors") and "failure" not in rec, "a failing kill is recorded, not raised")
    rec = {}
    ctl.kill_and_reap(Proc(kill_error=True, wait_error=True), rec, "reader")
    check("inspect" in rec.get("failure", ""), "a child that cannot be stopped is an explicit failure needing inspection")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rec = {}
        ctl.stop_reader(Proc(kill_error=True), tmp / "missing-dir" / "stop", rec)
        check("stop-file" in rec.get("failure", ""), "a stop-file write that fails is recorded and the reader still reaped")
        watch = {"flag": tmp / "flag", "heartbeat": tmp / "hb", "proc": None}
        watch["heartbeat"].write_text("now")
        check(ctl.supervise(Proc(polls=3), watch, 600, sleep=lambda s: None) is None, "a normal benchmark exit is not stopped")
        watch["flag"].write_text("4101 nvlddmkm")
        stopped = ctl.supervise(Proc(polls=50), watch, 600, sleep=lambda s: None)
        check(stopped and "display-driver event" in stopped, "a driver-event flag stops the benchmark mid-window")
        watch["flag"].unlink()
        watch["heartbeat"].unlink()
        stopped = ctl.supervise(Proc(polls=50), watch, 600, sleep=lambda s: None)
        check(stopped and "watcher stopped" in stopped, "a dead watcher stops the benchmark")
        watch["heartbeat"].write_text("now")
        clock = iter(range(0, 10_000, 100))
        stopped = ctl.supervise(Proc(polls=500), watch, 600, now=lambda: next(clock), sleep=lambda s: None)
        check(stopped and "did not finish" in stopped, "a benchmark past its deadline is stopped")

    # ---- GPT Job 76: ownership on interruption, and the watcher's lifecycle ------------------
    import unittest.mock as mock

    class Child:
        """A child that stays alive until killed; optionally refuses to die."""
        def __init__(self, denied=False):
            self.returncode, self.denied, self.trace = None, denied, []

        def poll(self):
            return self.returncode

        def kill(self):
            self.trace.append("kill")
            if self.denied:
                raise OSError("kill denied")
            self.returncode = -9

        def wait(self, timeout=None):
            self.trace.append("wait")
            if self.denied or self.returncode is None:
                raise subprocess.TimeoutExpired("fake", timeout)
            return self.returncode

        def communicate(self, timeout=None):
            return b"", b""

    reset_ok = {"clocks.sm": "210", "clocks.mem": "405", "pstate": "P8", "temperature.gpu": "35"}
    for raised in (KeyboardInterrupt(), RuntimeError("boom")):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reader_child, bench = Child(), Child()
            reader_child.returncode = 0  # the reader exits when told

            def ready(path, seconds):
                path.write_text("{}")
                return True

            def interrupt(*a, **k):
                raise raised

            with mock.patch.object(ctl.subprocess, "Popen", side_effect=[reader_child, bench]), \
                    mock.patch.object(ctl, "run", return_value=(0, "", "")), \
                    mock.patch.object(ctl, "witness", return_value=reset_ok), \
                    mock.patch.object(ctl.time, "sleep", return_value=None), \
                    mock.patch.object(ctl, "wait_for", side_effect=ready), \
                    mock.patch.object(ctl, "supervise", side_effect=interrupt):
                window = dict(index=0, arm="A", target_mhz=1545, workload="gemm", iterations=120, row=1, row_visit=0)
                rec = ctl.run_window(window, tmp, tmp / "log", "python", "since", {})
            name = type(raised).__name__
            check(bench.poll() is not None and "kill" in bench.trace and rec.get("failure") and rec.get("tag") == "w000-A",
                  f"a {name} during supervision kills the benchmark and keeps the partial record (Job 76, R2)")

    def run_main(watcher, tmp):
        watch = {"proc": watcher, "stop": tmp / "watcher.stop", "flag": tmp / "flag", "heartbeat": tmp / "hb"}
        with mock.patch.object(ctl, "provenance", return_value={}), \
                mock.patch.object(ctl, "schedule", return_value=[]), \
                mock.patch.object(ctl, "start_watcher", return_value=watch), \
                mock.patch.object(ctl, "watcher_ready", return_value=None), \
                mock.patch.object(ctl, "preflight", return_value=([], {})), \
                mock.patch.object(ctl, "driver_events", return_value=(True, 0)), \
                mock.patch.object(ctl, "collect", return_value=None), \
                mock.patch.object(ctl, "run", return_value=(0, "", "")), \
                mock.patch.object(ctl, "witness", return_value=reset_ok), \
                mock.patch.object(ctl.ctypes, "windll", create=True) as windll:
            windll.shell32.IsUserAnAdmin.return_value = 1
            code = ctl.main(["--session-index", "1", "--out", str(tmp / "out")])
        return code, json.loads((tmp / "out" / "status.json").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        code, status = run_main(Child(denied=True), Path(tmp))
        check(code == 3 and "could not be stopped" in (status.get("cleanup_failure") or ""),
              "a watcher that cannot be stopped fails the session instead of leaving exit 0 (Job 76, R4)")

    class Exits(Child):
        def __init__(self, code):
            super().__init__()
            self.code = code

        def wait(self, timeout=None):
            self.returncode = self.code
            return self.code

    with tempfile.TemporaryDirectory() as tmp:
        code, status = run_main(Exits(0), Path(tmp))
        check(code == 0 and status["watcher_cleanup"]["exit_code"] == 0, "a watcher that stops cleanly leaves exit 0")
    with tempfile.TemporaryDirectory() as tmp:
        code, status = run_main(Exits(1), Path(tmp))
        check(code == 3 and "exited 1" in (status.get("cleanup_failure") or ""),
              "a watcher that exited non-zero (its subscription failed) fails the session")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        watch = {"proc": Exits(0), "stop": tmp / "watcher.stop", "flag": tmp / "flag", "heartbeat": tmp / "hb"}
        with mock.patch.object(ctl, "provenance", return_value={}), \
                mock.patch.object(ctl, "schedule", return_value=[]), \
                mock.patch.object(ctl, "start_watcher", return_value=watch), \
                mock.patch.object(ctl, "wait_for", return_value=False), \
                mock.patch.object(ctl, "run", return_value=(0, "", "")), \
                mock.patch.object(ctl, "witness", return_value=reset_ok), \
                mock.patch.object(ctl.ctypes, "windll", create=True) as windll:
            windll.shell32.IsUserAnAdmin.return_value = 1
            code = ctl.main(["--session-index", "1", "--out", str(tmp / "out")])
        check(code == 3 and watch["stop"].exists(),
              "a watcher that never becomes ready is still told to stop (Job 76, R4)")

    try:
        ctl.main(["--session-index", "101", "--stage", "pilot", "--out", "unused"])
        check(False, "a confirmation index under the pilot stage is refused")
    except SystemExit:
        check(True, "a confirmation index under the pilot stage is refused before anything runs (R7)")

    if sys.platform == "win32":
        # The watcher itself, on a log any user can trigger: each new PowerShell writes event 400 to
        # "Windows PowerShell" with provider "PowerShell". No admin rights and no GPU are needed.
        def watch_once(match_id, provider_like, flag_dir_exists=True):
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                flag = (tmp if flag_dir_exists else tmp / "missing") / "flag"
                hb, stop = tmp / "hb", tmp / "stop"
                proc = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                         str(HERE / "watch_driver_events.ps1"), "-FlagFile", str(flag),
                                         "-HeartbeatFile", str(hb), "-StopFile", str(stop),
                                         "-LogName", "Windows PowerShell", "-MatchId", str(match_id),
                                         "-ProviderLike", provider_like],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.perf_counter() + 30
                while not hb.exists() and time.perf_counter() < deadline:
                    time.sleep(0.2)
                started = hb.exists()
                subprocess.run(["powershell.exe", "-NoProfile", "-Command", "exit 0"])
                deadline = time.perf_counter() + 12
                while not flag.exists() and proc.poll() is None and time.perf_counter() < deadline:
                    time.sleep(0.2)
                time.sleep(3)
                flagged = flag.read_text() if flag.exists() else None
                alive = proc.poll() is None
                stop.touch()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                return started, flagged, alive, proc.returncode

        started, flagged, _, code = watch_once(400, "no-such-provider")
        check(started, "the driver-event watcher starts and writes its heartbeat")
        check(bool(flagged) and flagged.startswith("400"), "a matching event ID raises the flag within seconds")
        check(code == 0, "the watcher stops on its stop file")
        _, flagged, _, _ = watch_once(0, "*POWERSHELL*")
        check(bool(flagged) and "PowerShell" in flagged,
              "a provider matched case-insensitively by -like raises the flag, as the old query did (Job 76, R4)")
        _, flagged, _, _ = watch_once(1, "no-such-provider")
        check(flagged is None, "an event matching neither the ID nor the provider raises no flag")
        _, flagged, alive, code = watch_once(400, "no-such-provider", flag_dir_exists=False)
        check(flagged is None and not alive and code != 0,
              "a flag that cannot be written stops the watcher with a non-zero exit, not a healthy heartbeat")
    else:
        print("  [SKIP] the event-log watcher is Windows-only")
    print("All section 20b design and reader checks passed.")


if __name__ == "__main__":
    main()
