# Section 20b: does polling change what the energy counter reports?

GPT Job 71 designed this test (`docs/submission/drafts/section20b-registration-draft.md`); these tools
implement its **core** arms. The exploratory panel (logger plus HWiNFO) is not built yet.

**This changes GPU state.** `run_core_session.py` locks clocks for every window and resets them
(`nvidia-smi -rgc`) in a `finally` block on every exit path, Ctrl+C included. It needs an elevated shell.

## Files

| file | what it does |
|---|---|
| `design.py` | every fixed constant, the Williams rows and each session's schedule. Imported by the controller **and** the scorer, so the two cannot disagree about what ran |
| `reader.py` | one process per window in every arm, polling at 20 Hz. Arm A makes **no NVML call at all**; E reads field 83; P reads `nvmlDeviceGetPowerUsage` then fields 185/186; EP reads usage then 185/186/83 (`sample_power.py`'s order). Unwanted calls are never made, not made and dropped |
| `run_core_session.py` | the controller: per window, lock the clock, take a witness, 30 s washout with monitoring off, start the arm's reader, run the fixed work, stop the reader and check it exited, then validate the window with `validate.py` and read the event log; it stops at the first invalid window or driver event. Between rows it checks every process's command line for other GPU pollers and for a visible Claude window, and fails closed if it cannot. Its exit code is decided after the clock reset |
| `watch_driver_events.ps1` | runs for the whole session: subscribes to the System log for display-driver events (EventID 4101 or `nvlddmkm`) and writes a flag file the moment one is logged, plus a 2 s heartbeat. The controller supervises each benchmark against it and stops the window at once on a flag or a dead watcher. It makes no GPU query |
| `validate.py` | the per-window rules, shared by controller and scorer: every value recomputed from raw evidence (T from the call brackets, work from the iteration count), every exit code, warm-up, preload, washout, temperatures, boundary clocks, the reader's exact schema and every call's status |
| `test_section20b.py` | schedule balance and determinism, each arm's exact calls against a fake NVML, and the reader's lifecycle as a real process in arm A |

The benchmark side is `tools/frequency-sweep/gpu_workload.py --preload-seconds 1.0 --endpoint-detail`:
a 1 s same-kernel preload after warm-up, both energy-counter calls bracketed on `perf_counter`, the SM
and memory clocks read through NVML just outside the timed region, and every temperature read logged.
Without those flags it behaves exactly as before. Scoring: `analysis/score_section20b.py`
(`analysis/test_score_section20b.py` holds the synthetic fixtures).

## Running

Through the session runner, which restores and witnesses stock first, then closes HWiNFO, Afterburner
and RTSS so nothing else polls the card, and verifies stock again with Afterburner closed:

```powershell
# hardware qualification, 36 windows (every cell once), NOT data, about 45 min
powershell -ExecutionPolicy Bypass -File tools\rerun15\Invoke-Rerun15Session.ps1 -Parts s20b -DryRun -ManageChatGpt
# pilot session N (1-4), 144 windows, about 2 h
powershell -ExecutionPolicy Bypass -File tools\rerun15\Invoke-Rerun15Session.ps1 -Parts s20b -Session N -ManageChatGpt
```

Unattended, from an elevated shell: a minimized window that closes itself when the session ends (the
runner's `session.log` keeps everything the window showed). Never add `-NoExit`: on 2026-10-11 it left
three finished windows open with nobody there to close them.

```powershell
Start-Process powershell.exe -Verb RunAs -WindowStyle Minimized -WorkingDirectory C:\Users\Raymond\Documents\headroom -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','tools\rerun15\Invoke-Rerun15Session.ps1','-Parts','s20b','-Session','N','-ManageChatGpt'
```

Output goes to `C:\headroom-bench\rerun15\<stamp>-s20b\core\`: `schedule.json` (written before the
first window, with the commit and file hashes), `windows.jsonl`, `status.json`, `controller.log`,
`driver-events.json` and one reader CSV per window.

## Limits, stated

- **No HWiNFO desktop-load screen is possible in the core arms**, because HWiNFO polls the card. The
  controller's process inventory and CPU load, before and after each row, stand in for it and are not
  as sensitive.
- Arm A is free of power and energy polling, not of all GPU queries: every arm keeps the benchmark's
  `nvidia-smi` temperature reads, the two direct energy-counter endpoint reads, one counter support
  check when the benchmark opens NVML, and two NVML clock reads outside the timed region.
- Achieved clocks are witnessed at the window boundaries only, not continuously.
- GPT Job 73 (`docs/gpt-findings/2026-10-10-section20b-implementation-review.md`) reviewed the first
  version; F1-F10 are fixed in the second, and F8 (confirmation needs a frozen S, distinct days and
  whole-session replacement limits) is implemented in the scorer. Confirmation sessions are numbered
  from 101.
- GPT Job 75 (`docs/gpt-findings/2026-10-10-section20b-fix-verification.md`) verified those fixes and
  found R1-R8; R1-R6 and R8 are fixed. **Open before confirmation (R7):** a frozen, complete attempt
  ledger recording every attempt and the operational reason for each replacement. The scorer already
  requires real dates, one replacement per session on a later day, and a `--frozen-plan` for S.
- GPT Job 76 (`docs/gpt-findings/2026-10-11-section20b-r-fix-verification.md`) found the remaining
  gaps, all fixed after it: the benchmark is killed if the controller is interrupted mid-window; a
  watcher that never starts is still stopped, and one that cannot be stopped or exits non-zero fails
  the session; the watcher subscribes to every System record and applies the old query's predicate
  (ID 4101, or a provider `-like '*nvlddmkm*'`, case-insensitive), and stops its heartbeat if its
  subscription or flag write fails; the scorer checks the readback after the reset and every field of
  `runner-cleanup.json` (`validate.py`'s shared rules), and reports malformed files as invalid rather
  than crashing; the runner's native calls keep kill and reap errors, and each cleanup step runs
  whatever the one before did. **Still open:** the attempt ledger (R7), and whether a confirmation
  session may share a day with a pilot one, for the registration to decide.
- 2026-10-11: the top target moved from 2475 to 2317 MHz after pilot 1's first attempt hit the stock
  power cap (`docs/section20b/pilot1-attempt1-20261011/`); the 36-window qualification at the new
  target ran clean (`docs/section20b/qualification-20261011/`), and again on the registered code
  (`docs/section20b/qualification-20261011b/`). **Registered 2026-10-11** as
  `docs/REGISTERED-PREDICTIONS.md` §20b. Every attempt goes in `docs/section20b/ATTEMPTS.md`, pushed
  before launch.
- N=1 RTX 5060 Ti; sessions are repeated observations of one chip.
