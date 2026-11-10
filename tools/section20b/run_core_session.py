"""Run one section 20b core session (144 windows), or the 36-window hardware qualification.

Usage, elevated (clock locks need administrator rights):
    python tools/section20b/run_core_session.py --session-index N --stage pilot --out DIR [--events-since ISO]
    python tools/section20b/run_core_session.py --qualification --out DIR

Normally launched by tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20b, which restores and
witnesses stock first and closes HWiNFO and Afterburner so nothing else polls the card. This script
then runs the saved schedule (design.schedule): for each window it locks the target clock, takes a
witness outside timing, waits the 30 s washout with energy and power monitoring off, starts that arm's
reader, runs the fixed work (warm-up, 1 s preload, bracketed energy endpoints), stops the reader and
checks it exited, then validates the window with the scorer's own rules (validate.py) and checks the
Windows event log for display-driver events. Before and after every row it checks the full process
inventory, with command lines, for other GPU pollers and for a visible Claude window.

It CHANGES GPU STATE: it locks clocks and resets them (nvidia-smi -rgc) in a finally block on every
exit path, Ctrl+C included. The session's exit code is decided only after that cleanup: a failed reset
is a failed session (GPT Job 73, F1). Any invalid window, driver event, forbidden process, unreadable
process inventory or failed event-log query ends the session; there are no window retries.
"""
import argparse
import csv
import ctypes
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
from design import (CONFIRMATION_INDICES, PILOT_INDICES, PRELOAD_SECONDS, SEED_BASE,  # noqa: E402
                    WARMUP_ITERATIONS, WASHOUT_SECONDS, qualification_schedule, schedule)
from validate import reset_witness_complete, window_metrics  # noqa: E402

WORKLOAD = REPO / "tools" / "frequency-sweep" / "gpu_workload.py"
READER = HERE / "reader.py"
DRIVER = "616.92"
POWER_LIMIT_W = 180.0
# Executables that must not run during a core session. HWiNFO and Afterburner poll the card; the rest
# are section 15 condition 1's desktop loads, the assistants and the local model server.
FORBIDDEN = {"hwinfo64.exe", "msiafterburner.exe", "rtss.exe", "opera.exe", "discord.exe", "obsidian.exe",
             "steam.exe", "epicgameslauncher.exe", "robloxplayerbeta.exe", "chatgpt.exe", "codex.exe",
             "llama-server.exe", "obs64.exe"}
# Command lines that poll or load the GPU through this repository's own tools (GPT Job 73, F4).
# Checked between rows, when no reader or benchmark of ours is running.
SCRIPT_POLLER = re.compile(r"sample_power\.py|section20b[\\/]reader\.py|gpu_workload\.py|llm_workload\.py|"
                           r"Invoke-FrequencySweep|Invoke-LoggedSweep|Log-GpuStability", re.IGNORECASE)
# Processes whose command line must be readable, because any of them could be running a reader.
INSPECT = {"python.exe", "pythonw.exe", "py.exe", "powershell.exe", "pwsh.exe", "nvidia-smi.exe", "cmd.exe"}
WATCHER = HERE / "watch_driver_events.ps1"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def say(log, text):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    print(line, flush=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run(args, timeout=60):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def powershell(command, timeout=60):
    return run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], timeout)


def gpu_query(fields):
    code, out, _ = run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
    values = [v.strip() for v in out.splitlines()[0].split(",")] if code == 0 and out else []
    return dict(zip(fields.split(","), values)) if len(values) == len(fields.split(",")) else None


WITNESS_FIELDS = "clocks.sm,clocks.mem,pstate,temperature.gpu"


def witness():
    """Clocks, P-state and temperature, read outside timing. A GPU query, but not of power or energy.
    At idle the card stays in its previous state until loaded, so in a window this is recorded, never
    gated; after the reset it is the required acknowledgement that the card answered (R1)."""
    query = gpu_query(WITNESS_FIELDS)
    return dict(query or {}, mono=time.perf_counter())


def witness_complete(record):
    """True when every witness field came back and the clocks and temperature are numbers. An idle
    clock does not prove a lock was released; this proves only that the readback succeeded."""
    return reset_witness_complete(record)  # one rule with the scorer; "inf" is not a reading (Job 76, R1)


def tokens(command_line):
    """Command-line words, quotes removed: enough to read nvidia-smi's options."""
    return [w.strip('"') for w in re.findall(r'"[^"]*"|\S+', command_line or "")]


def is_poller(name, command_line):
    """This repository's telemetry or workload scripts, or nvidia-smi in any looping mode
    (-l, -lms, --loop, --loop-ms, dmon, pmon; GPT Job 75, R3)."""
    if SCRIPT_POLLER.search(command_line or ""):
        return True
    if (name or "").lower() != "nvidia-smi.exe" and "nvidia-smi" not in (command_line or "").lower():
        return False
    for word in tokens(command_line)[1:]:
        word = word.lower()
        if word in ("-l", "-lms", "dmon", "pmon") or word.startswith(("--loop", "-l=", "-lms=")):
            return True
    return False


def process_inventory():
    """Every process with its command line, from Win32_Process. Raises on any error, including a
    non-terminating one, an empty list or a malformed record (GPT Job 75, R3)."""
    code, out, err = powershell("$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process -ErrorAction Stop | "
                                "Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
                                "ConvertTo-Json -Compress -Depth 2", timeout=90)
    if code != 0 or not out or err.strip():
        raise RuntimeError(f"process inventory failed: {(err or 'no output')[:200]}")
    data = json.loads(out)
    data = data if isinstance(data, list) else [data]
    if not data or not all(isinstance(p, dict) and isinstance(p.get("ProcessId"), int)
                           and isinstance(p.get("Name"), str) for p in data):
        raise RuntimeError("process inventory empty or malformed")
    return data


def visible_claude_windows(pids):
    """Top-level windows of the Claude app that are visible and not minimized (its rendering costs
    6-9% of membw, CLAUDE.md). Windows only; elsewhere none can exist."""
    if sys.platform != "win32" or not pids:
        return 0
    user32 = ctypes.windll.user32
    found, failed = [], []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _):
        pid = ctypes.c_ulong()
        if user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid)) == 0:
            failed.append(hwnd)
            return True
        if pid.value in pids and user32.IsWindowVisible(ctypes.c_void_p(hwnd)) \
                and not user32.IsIconic(ctypes.c_void_p(hwnd)) and user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd)) > 0:
            found.append(hwnd)
        return True

    # Failure must not read as "no visible window" (GPT Job 75, R3). The callback always returns True,
    # so EnumWindows returning 0 means the enumeration itself failed.
    if not user32.EnumWindows(callback, 0):
        raise OSError("window enumeration failed")
    if failed:
        raise OSError(f"{len(failed)} windows' owning process could not be read")
    return len(found)


def cpu_load():
    code, out, _ = run(["typeperf", r"\Processor(_Total)\% Processor Time", "-sc", "1"], timeout=30)
    if code != 0:
        return None
    # The sample row starts with a date; "Exiting, please wait..." also splits into two fields.
    rows = [r for r in csv.reader(io.StringIO(out)) if len(r) == 2 and r[0][:1].isdigit()]
    try:
        return float(rows[-1][1])
    except (ValueError, IndexError):
        return None


def background():
    """Process inventory, external GPU pollers, a visible Claude window and CPU load. No GPU query.
    Fails closed: an unreadable inventory is itself a problem (GPT Job 73, F4)."""
    record = {"mono": time.perf_counter(), "inventory_ok": False, "forbidden": [], "pollers": [],
              "claude_visible_windows": None, "cpu_pct": cpu_load()}
    try:
        processes = process_inventory()
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        record["error"] = str(exc)
        return record
    own = os.getpid()
    names = {p["Name"].lower() for p in processes}
    record["forbidden"] = sorted(FORBIDDEN & names)
    record["pollers"] = [p.get("CommandLine") for p in processes
                         if p["ProcessId"] != own and is_poller(p["Name"], p.get("CommandLine"))]
    uninspectable = [f"{p['Name']} ({p['ProcessId']})" for p in processes
                     if p["Name"].lower() in INSPECT and not p.get("CommandLine")]
    record["process_count"] = len(processes)
    if uninspectable:
        record["error"] = "command line unreadable for " + ", ".join(uninspectable)
        return record
    try:
        record["claude_visible_windows"] = visible_claude_windows(
            {p["ProcessId"] for p in processes if p["Name"].lower() == "claude.exe"})
    except OSError as exc:
        record["error"] = f"Claude window check failed: {exc}"
        return record
    record["inventory_ok"] = True
    return record


def background_problem(record):
    if not record["inventory_ok"]:
        return "process inventory unreadable: " + record.get("error", "")
    if record["forbidden"]:
        return "forbidden processes: " + ", ".join(record["forbidden"])
    if record["pollers"]:
        return "other GPU pollers: " + " | ".join(record["pollers"])[:400]
    if record["claude_visible_windows"]:
        return f"{record['claude_visible_windows']} Claude window(s) visible"
    return None


def driver_events(since_iso):
    """(query_ok, count) of display-driver events since the session started. 'No events' is a successful
    zero; any other failure to read the log is not (GPT Job 73, F5)."""
    command = ("$s=[datetime]::Parse('SINCE'); try { $e=@(Get-WinEvent -FilterHashtable @{LogName='System';"
               "StartTime=$s} -ErrorAction Stop | Where-Object { $_.Id -eq 4101 -or $_.ProviderName -like '*nvlddmkm*' });"
               " 'OK ' + $e.Count } catch { if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { 'OK 0' }"
               " else { 'ERR ' + $_.Exception.Message } }").replace("SINCE", since_iso)
    try:
        code, out, _ = powershell(command, timeout=60)
    except subprocess.TimeoutExpired:
        return False, None
    last = out.splitlines()[-1] if out else ""
    if code == 0 and last.startswith("OK "):
        return True, int(last.split()[1])
    return False, None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance():
    code, commit, _ = run(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    _, status, _ = run(["git", "-C", str(REPO), "status", "--porcelain"])
    files = [HERE / "design.py", READER, HERE / "validate.py", Path(__file__).resolve(), WORKLOAD,
             REPO / "tools" / "power-probe" / "sample_power.py"]
    return {"commit": commit if code == 0 else None, "working_tree_status": status.splitlines(),
            "file_sha256": {str(p.relative_to(REPO)).replace("\\", "/"): sha256(p) for p in files},
            "python": sys.version, "executable": sys.executable}


def wait_for(path, seconds):
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return path.exists()


def preflight(log):
    problems = []
    code, out, _ = run(["nvidia-smi", "-L"])
    if code != 0 or len([l for l in out.splitlines() if l.startswith("GPU ")]) != 1:
        problems.append("expected exactly one NVIDIA device")
    query = gpu_query("driver_version,power.limit,utilization.gpu,utilization.encoder,utilization.decoder")
    if query is None:
        problems.append("nvidia-smi query failed")
    else:
        if query["driver_version"] != DRIVER:
            problems.append(f"driver {query['driver_version']}, not {DRIVER}")
        if abs(float(query["power.limit"]) - POWER_LIMIT_W) > 0.5:
            problems.append(f"power limit {query['power.limit']} W, not {POWER_LIMIT_W:g}")
        if float(query["utilization.gpu"]) >= 10:
            problems.append(f"idle utilisation {query['utilization.gpu']}%")
        if float(query["utilization.encoder"]) != 0 or float(query["utilization.decoder"]) != 0:
            problems.append("a video engine is busy (Instant Replay or a recorder)")
    bg = background()
    if background_problem(bg):
        problems.append(background_problem(bg))
    say(log, f"Preflight: {query}; background ok={bg['inventory_ok']} forbidden={bg['forbidden']} "
             f"pollers={len(bg['pollers'])} claude-visible={bg['claude_visible_windows']} cpu={bg['cpu_pct']}.")
    return problems, {"gpu": query, "background": bg}


def kill_and_reap(proc, rec, what):
    """Kill a child and wait for it, recording rather than raising any failure (GPT Job 75, R2)."""
    try:
        proc.kill()
    except OSError as exc:
        rec.setdefault("cleanup_errors", []).append(f"{what} kill failed: {exc}")
    try:
        proc.wait(timeout=10)
    except (subprocess.TimeoutExpired, OSError) as exc:
        rec.setdefault("cleanup_errors", []).append(f"{what} could not be reaped: {type(exc).__name__}")
        rec["failure"] = f"{what} could not be stopped; inspect before any further run"


def stop_reader(reader, stop_path, rec):
    """Signal, wait, and if needed kill and reap the reader; record every failure (GPT Job 73, F2)."""
    try:
        stop_path.touch()
    except OSError as exc:
        rec["failure"] = rec.get("failure") or f"reader stop-file write failed: {exc}"
        kill_and_reap(reader, rec, "reader")
    try:
        reader.wait(timeout=10)
    except subprocess.TimeoutExpired:
        rec["failure"] = rec.get("failure") or "reader did not exit within 10 s of the stop file"
        kill_and_reap(reader, rec, "reader")
    except OSError as exc:
        rec["failure"] = rec.get("failure") or f"reader wait failed: {exc}"
    try:
        _, err = reader.communicate(timeout=5)
        if err:
            rec["reader_stderr"] = err.decode("utf-8", "replace")[-1000:]
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass


def supervise(proc, watch, timeout, poll=0.5, now=time.perf_counter, sleep=time.sleep):
    """Wait for the benchmark while watching for a driver event or a dead watcher (GPT Job 75, R4).
    Returns None on a normal exit, else why it was stopped; the caller kills and reaps it."""
    started = now()
    while proc.poll() is None:
        if watch["flag"].exists():
            return "display-driver event during the window: " + watch["flag"].read_text(encoding="utf-8", errors="replace")[:200]
        if not watch_alive(watch):
            return "the driver-event watcher stopped"
        if now() - started > timeout:
            return f"the benchmark did not finish within {timeout:g} s"
        sleep(poll)
    return None


def watch_alive(watch, stale_seconds=15.0):
    """The watcher rewrites its heartbeat every 2 s; older than 15 s, or its process gone, is dead."""
    try:
        age = time.time() - watch["heartbeat"].stat().st_mtime
    except OSError:
        return False
    return age <= stale_seconds and (watch.get("proc") is None or watch["proc"].poll() is None)


def start_watcher(out):
    """Launch the watcher and return its handle at once; the caller owns it from here, so a watcher
    that never becomes ready is still stopped (GPT Job 76, R4). Call watcher_ready next."""
    watch = {"flag": out / "driver-event.flag", "heartbeat": out / "watcher.heartbeat", "stop": out / "watcher.stop"}
    watch["proc"] = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                      "-File", str(WATCHER), "-FlagFile", str(watch["flag"]),
                                      "-HeartbeatFile", str(watch["heartbeat"]), "-StopFile", str(watch["stop"])],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    return watch


def watcher_ready(watch, seconds=30):
    if not wait_for(watch["heartbeat"], seconds):
        raise RuntimeError("the driver-event watcher never started")


def stop_watcher(watch, status):
    """Stop the watcher and record how it ended. A watcher that will not stop, or that exited non-zero
    (it does so when its subscription fails), is a cleanup failure, not a note (GPT Job 76, R4)."""
    rec = {}
    try:
        watch["stop"].touch()
        watch["proc"].wait(timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        kill_and_reap(watch["proc"], rec, "watcher")
    code = watch["proc"].poll()
    status["watcher_cleanup"] = {"exit_code": code, "reaped": code is not None,
                                 "errors": rec.get("cleanup_errors", [])}
    if code is None:
        status["cleanup_failure"] = status.get("cleanup_failure") or "the driver-event watcher could not be stopped"
    elif code != 0:
        status["cleanup_failure"] = status.get("cleanup_failure") or f"the driver-event watcher exited {code}"


def run_window(window, out_dir, log, python, events_since, watch):
    """One window. Any unexpected exception becomes the window's recorded failure, so the partial
    record still reaches windows.jsonl (GPT Job 75, R2)."""
    rec = {}
    try:
        return _run_window(window, out_dir, log, python, events_since, watch, rec)
    except KeyboardInterrupt:
        # Ctrl+C also keeps the partial record; collect writes it and stops the session (GPT Job 76, R2).
        rec.update({k: v for k, v in window.items() if k not in rec})
        rec["failure"] = "interrupted during the window"
        return rec
    except Exception as exc:
        rec.update({k: v for k, v in window.items() if k not in rec})
        rec["failure"] = f"controller error in the window: {type(exc).__name__}: {exc}"
        return rec


def _run_window(window, out_dir, log, python, events_since, watch, rec):
    tag = f"w{window['index']:03d}-{window['arm']}"
    rec.update(window, tag=tag, events={})
    ev = rec["events"]
    target = window["target_mhz"]
    code, _, err = run(["nvidia-smi", "-lgc", f"{target},{target}"])
    rec["lock_exit"] = code
    if code != 0:
        rec["failure"] = f"clock lock failed: {err[:200]}"
        return rec
    rec["witness_before"] = witness()
    ev["washout_start"] = time.perf_counter()
    time.sleep(WASHOUT_SECONDS)
    ev["washout_end"] = time.perf_counter()
    paths = {k: out_dir / f"{tag}-{k}" for k in ("reader.csv", "ready.json", "stop", "done.json")}
    rec["reader_csv"] = paths["reader.csv"].name
    reader = subprocess.Popen([python, str(READER), "--mode", window["arm"], "--out", str(paths["reader.csv"]),
                               "--ready-file", str(paths["ready.json"]), "--stop-file", str(paths["stop"]),
                               "--done-file", str(paths["done.json"])],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    bench = None
    try:
        if not wait_for(paths["ready.json"], 20):
            rec["failure"] = "reader never became ready"
            return rec
        rec["reader_ready"] = json.loads(paths["ready.json"].read_text(encoding="utf-8"))
        ev["workload_launch"] = time.perf_counter()
        stdout_path, stderr_path = out_dir / f"{tag}-workload.out", out_dir / f"{tag}-workload.err"
        with stdout_path.open("w", encoding="utf-8") as so, stderr_path.open("w", encoding="utf-8") as se:
            bench = subprocess.Popen([python, str(WORKLOAD), "--workload", window["workload"],
                                      "--iterations", str(window["iterations"]), "--warmup", str(WARMUP_ITERATIONS),
                                      "--preload-seconds", str(PRELOAD_SECONDS), "--endpoint-detail", "--json"],
                                     stdout=so, stderr=se, creationflags=NO_WINDOW)
            stopped = supervise(bench, watch, 600)
            if stopped:
                kill_and_reap(bench, rec, "benchmark")
                rec["failure"] = stopped
                return rec
        ev["workload_exit"] = time.perf_counter()
        rec["workload_exit_code"] = bench.returncode
        lines = [l for l in stdout_path.read_text(encoding="utf-8").splitlines() if l.strip().startswith("{")]
        rec["result"] = json.loads(lines[-1]) if lines else None
        if rec["result"] is None:
            rec["failure"] = (f"no workload JSON (exit {bench.returncode}): "
                              f"{stderr_path.read_text(encoding='utf-8', errors='replace')[-300:]}")
    finally:
        # The benchmark first: an exception or Ctrl+C inside supervise must not leave it running into
        # the reset (GPT Job 76, R2). Then the reader, whatever happened to the benchmark.
        try:
            if bench is not None and bench.poll() is None:
                kill_and_reap(bench, rec, "benchmark")
                rec["failure"] = rec.get("failure") or "the benchmark was still running when the window ended"
        finally:
            stop_reader(reader, paths["stop"], rec)
        ev["reader_exit"] = time.perf_counter()
        rec["reader_exit_code"] = reader.returncode
        if paths["done.json"].exists():
            rec["reader_done"] = json.loads(paths["done.json"].read_text(encoding="utf-8"))
        elif not rec.get("failure"):
            rec["failure"] = "reader wrote no done file"
    rec["witness_after"] = witness()
    # The scorer's own rules, now, so an invalid window ends the session instead of being found later.
    if not rec.get("failure"):
        _, problems = window_metrics(rec, out_dir)
        if problems:
            rec["failure"] = "; ".join(p.split(": ", 1)[-1] for p in problems)[:600]
    ok, count = driver_events(events_since)
    rec["driver_events"] = {"query_ok": ok, "count": count}
    if not rec.get("failure") and (not ok or count):
        rec["failure"] = "display-driver event" if ok else "the event log could not be read"
    payload = rec.get("result") or {}
    say(log, f"{tag} {window['workload']} {target} MHz row {window['row']}: "
             f"{'OK' if not rec.get('failure') else 'FAILED: ' + rec['failure']}; "
             f"energy power {payload.get('energy_avg_power_w')} W, "
             f"reader rows {(rec.get('reader_done') or {}).get('rows')}.")
    return rec


def collect(windows, out, log, status, events_since, watch):
    """Run every window; return None when complete, else the reason it stopped."""
    with (out / "windows.jsonl").open("a", encoding="utf-8") as sink:
        current = None
        for window in windows:
            if window["row_visit"] != current:
                if current is not None:
                    bg = dict(background(), when="after", row_visit=current)
                    status["background"].append(bg)
                    if background_problem(bg):
                        return background_problem(bg)
                current = window["row_visit"]
                bg = dict(background(), when="before", row_visit=current)
                status["background"].append(bg)
                if background_problem(bg):
                    return background_problem(bg)
            rec = run_window(window, out, log, sys.executable, events_since, watch)
            sink.write(json.dumps(rec) + "\n")
            sink.flush()
            status["windows_done"] += 1
            if rec.get("failure"):
                return f"{rec['tag']}: {rec['failure']}"
        bg = dict(background(), when="after", row_visit=current)
        status["background"].append(bg)
        return background_problem(bg)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session-index", type=int)
    parser.add_argument("--stage", choices=["pilot", "confirmation"], default="pilot")
    parser.add_argument("--qualification", action="store_true")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--events-since", help="ISO time the session runner started; default now")
    args = parser.parse_args(argv)
    if not args.qualification and not args.session_index:
        parser.error("--session-index is required unless --qualification")
    allowed = PILOT_INDICES if args.stage == "pilot" else CONFIRMATION_INDICES
    if not args.qualification and args.session_index not in allowed:
        parser.error(f"session {args.session_index} is not a {args.stage} session ({allowed[0]}-{allowed[-1]})")
    if sys.platform == "win32" and not ctypes.windll.shell32.IsUserAnAdmin():
        print("Not elevated: clock locks need administrator rights.", file=sys.stderr)
        return 2
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    log = out / "controller.log"
    started = datetime.datetime.now().astimezone()
    events_since = args.events_since or started.isoformat()
    windows = qualification_schedule() if args.qualification else schedule(args.session_index)
    kind = "QUALIFICATION (not data)" if args.qualification else f"{args.stage} session {args.session_index}"
    plan = {"section": "20b", "kind": "qualification" if args.qualification else "core",
            "stage": None if args.qualification else args.stage, "session_index": args.session_index,
            "seed": None if args.qualification else SEED_BASE + args.session_index,
            "washout_seconds": WASHOUT_SECONDS, "preload_seconds": PRELOAD_SECONDS,
            "warmup_iterations": WARMUP_ITERATIONS, "started_iso": started.isoformat(),
            "started_local_date": started.date().isoformat(), "events_since": events_since,
            "provenance": provenance(), "windows": windows}
    (out / "schedule.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    say(log, f"Section 20b {kind}: {len(windows)} windows. Schedule saved before the first window.")
    status = {"kind": plan["kind"], "session_index": args.session_index, "complete": False, "failure": None,
              "windows_done": 0, "background": [], "preflight_problems": None}
    watch = None
    try:
        watch = start_watcher(out)
        watcher_ready(watch)
        problems, status["preflight"] = preflight(log)
        ok, count = driver_events(events_since)
        status["preflight"]["driver_events"] = {"query_ok": ok, "count": count}
        if not ok or count:
            problems.append("display-driver events since the runner started" if ok else "the event log could not be read")
        status["preflight_problems"] = problems
        if problems:
            status["failure"] = "preflight: " + "; ".join(problems)
        else:
            status["failure"] = collect(windows, out, log, status, events_since, watch)
            status["complete"] = status["failure"] is None
    except KeyboardInterrupt:
        status["failure"] = "interrupted"
    except Exception as exc:  # recorded, never allowed to skip the reset below
        status["failure"] = f"controller error: {type(exc).__name__}: {exc}"
    finally:
        try:
            code, _, err = run(["nvidia-smi", "-rgc"])
            status["reset_exit"] = code
            if code != 0:
                status["cleanup_failure"] = f"clock reset failed: {err[:200]}"
        except Exception as exc:
            status["reset_exit"] = None
            status["cleanup_failure"] = f"clock reset raised {type(exc).__name__}: {exc}"
        try:
            status["after_reset"] = witness()
            if not witness_complete(status["after_reset"]):
                status["cleanup_failure"] = status.get("cleanup_failure") or "the readback after reset was incomplete"
        except Exception as exc:
            status["after_reset"] = {"error": str(exc)}
            status["cleanup_failure"] = status.get("cleanup_failure") or f"the readback after reset failed: {exc}"
        if watch is not None:
            stop_watcher(watch, status)
        exit_code = 0 if status["complete"] and not status.get("cleanup_failure") else 3
        status["exit_code"] = exit_code
        (out / "status.json").write_text(json.dumps(status, indent=1), encoding="utf-8")
        say(log, f"Clocks reset (exit {status.get('reset_exit')}). Status: "
                 f"{'COMPLETE' if exit_code == 0 else (status['failure'] or status.get('cleanup_failure'))}.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
