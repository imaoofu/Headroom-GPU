# `hwinfo-logging` — start and stop HWiNFO logging without a human

**Added 2026-09-21.** `Invoke-HwinfoLogging.ps1 -Start -LogPath <abs> | -Stop | -Status`.

**What this unlocks.** Every multi-configuration item on the bench list is costed as *"the
operator must be present"* — `docs/GPU-WORKLIST-5060TI.md` item 4j says so explicitly — and the
only reason is clicking one button between runs. This removes that, which is the difference
between a session that needs Raymond at the desk for six hours and one that runs while he is at
school.

---

## Why the obvious routes are all closed

| route | why not |
|---|---|
| `HWiNFO64.exe -l -max_time=n -poll_rate=n` | **Pro only.** The manual's §5.1 is titled *"Command Line Parameters (Pro Version)"* and the feature table lists *"Automatic sensor logging via command-line"* in the Pro column. `HWiNFO64.INI` here has no license keys |
| HWiNFO shared memory | **12-hour limit** on freeware |
| A computer-use agent clicking the button | **Structurally impossible.** See below |
| `AutoLogging`-style INI key | Does not exist on this build; the INI carries `SensorInterval` and nothing logging-related |

### Why an agent cannot click it, and elevating the agent is not the fix

HWiNFO runs elevated. **UIPI forbids a medium-integrity process from injecting input into an
elevated window**, and the failure is silent — no error, no effect, nothing in a log. Screenshots
keep working, because *reading* the screen is permitted and *injecting* is not. That asymmetry is
exactly what was observed.

Verified 2026-09-21 on the Codex desktop agent: its MSIX manifest declares `runFullTrust`,
`graphicsCaptureProgrammatic` and `graphicsCaptureWithoutBorder` but **no `allowElevation`**, and
no `TrustLevel`. Packaged apps take their integrity level from the manifest via the AppX
activation broker, so **no launch method elevates it** — not `RunAs`, not "Run as administrator",
not `--do-not-de-elevate`, which is a no-op for an app that cannot elevate at all.

**So the clicker must be elevated, not the agent.** Elevated-to-elevated injection is
same-integrity and permitted. Run this script from a **scheduled task registered with highest
privileges**; the agent only needs `schtasks /run`, which works fine unelevated. The agent then
never touches a GUI, never takes a screenshot during a measurement, and cannot contaminate the
run — which matters, because desktop activity beside a sweep cost **9.38% of throughput at every
point** on 2026-09-18.

---

## The two mistakes that cost an hour. Do not "simplify" either.

**1. `PostMessage`, never `SendMessage`, to press the log button.** `SendMessage` is synchronous
and the button opens a **modal** Save As dialog, so it blocks until that dialog closes — meaning
the script that opens the dialog can never be the script that fills it in. The first attempt
deadlocked and had to be killed with the dialog stranded on screen.

**2. `SetWindowTextW` on the filename box is not enough.** It puts the characters in the edit
control but raises no `EN_CHANGE`, so the Vista-style file dialog never updates the name it
intends to use and `IDOK` acts on an empty string. The dialog just sits there and nothing says
why. **`WM_SETTEXT` plus an explicit `EN_CHANGE` to the parent, then `IDOK`.**

Also: controls are found by **text, not HWND** — handles change every time HWiNFO starts. And the
string overload needs `EntryPoint="SendMessageW"` or the P/Invoke fails at call time.

## The control it drives

```
Sensors dialog (#32770, title matches "Sensors")
  └─ Button, dlg ctrl id 1437, text 'Log Start' / 'Log Stop'
```

**The label is the state, so the script reads it instead of assuming.** `Log Start` means
stopped; `Log Stop` means running.

## It verifies by growth, not by the click returning

A toggled label proves the button moved. **Two increasing file sizes prove samples are reaching
the disk**, which is what the run depends on — HWiNFO can hold a handle open and write nothing.
`-Start` fails with exit 7 if the file does not grow, and `-Stop` fails if it is still growing.

It also refuses to overwrite an existing log (one log per configuration is a provenance rule), and
refuses to start a second log while one is running, because the first one's path would then be
unrecoverable.

| exit | meaning |
|---|---|
| 0 | did what was asked and verified it |
| 2 | bad arguments (relative path, missing dir, existing file) |
| 3 | HWiNFO not running |
| 4 | no Sensors window with a log button |
| 5 | already logging / not logging |
| 6 | the Save As dialog never appeared or would not accept |
| 7 | the button toggled but the file disagrees |

## Verified

End-to-end on the real tool, 2026-09-21, freeware HWiNFO 8.50-6020:

```
-Status  Log button reads 'Log Start'.  Logging is stopped.
-Start   button now : 'Log Stop'    size : 22782 then 39102 bytes
-Stop    button now : 'Log Start'   size : 67516 then 67516 bytes   rows : 17
```

**No automated test suite yet, and that is a real gap by this repo's standards.** The GUI path
is hard to test without HWiNFO present, but the argument-validation branches — relative path,
missing directory, existing file, both switches — are pure and cheap to cover. **They are
currently unverified except by reading.** It does not launch HWiNFO itself, deliberately: the
splash and the update nag are extra state to get wrong, and a run that begins by guessing at
dialogs is not a run worth having.

---

# The unattended chain

Three pieces. Register once, then every run is one unelevated command.

```
agent / any unelevated shell
  └─ writes C:\headroom-bench\job.json
  └─ schtasks /run /tn headroom-bench
       └─ Scheduled task, HIGHEST PRIVILEGES, runs one FIXED script
            └─ Invoke-LoggedSweep.ps1
                 ├─ preflight: power limit + pmon, REFUSES on a busy card
                 ├─ Invoke-HwinfoLogging.ps1 -Start
                 ├─ Invoke-FrequencySweep.ps1   (needs admin; has it)
                 ├─ Invoke-HwinfoLogging.ps1 -Stop   (in `finally`)
                 └─ writes wrapper-result.json
```

## Setup, once

```powershell
.\Register-BenchTask.ps1        # from an ELEVATED shell
```

Then per run: write the job, `schtasks /run /tn headroom-bench`, read
`C:\headroom-bench\results\<stamp>_<label>\wrapper-result.json`.

## What registering the task authorises

**Standing elevated execution of ONE FIXED SCRIPT.** That is why the job file is treated as a
*request* and never an instruction:

| field | how it is constrained |
|---|---|
| `workload` | matched against a **whitelist of 13 names**. The job cannot supply a command line — the wrapper builds it |
| output path | **derived** from the label, never supplied, so path traversal has nothing to traverse |
| `label` | `^[a-z0-9][a-z0-9-]{2,63}$` |
| `minMhz` / `maxMhz` | integers 200–4000, max must exceed min |
| `frequencyCount` | 3–40 |
| `iterations` | digits and commas only |
| `appliedSettings` | **required**, 20–600 chars — it is the one field nothing can reconstruct afterwards |

Verified refusals: `"label": "../escape"` and `"workload": "gemm; calc.exe"` both exit 2 without
touching the GPU. The task is registered with **no trigger** — a bench run must never start
because a clock said so; the machine has to be verified quiet first.

## Keep non-ASCII out of string literals in these .ps1 files

Found 2026-09-21, before any of this ran. None of this repo's PowerShell tools carry a BOM, so
PowerShell 5.1 reads them as ANSI. A UTF-8 emoji becomes several cp1252 bytes, and **inside a
quoted string that breaks the terminator and the whole script fails to parse** — which would have
surfaced as a bare syntax error inside the scheduled task, with no sweep and no log.

**In a comment the same mangling is harmless**, which is exactly why the emoji already present
in `Invoke-FrequencySweep.ps1` and `Sync-Kit.ps1` have never caused trouble and this looked safe.
Comments yes, strings no.

## Verified

Three consecutive start/stop cycles in one HWiNFO session, distinct names, one in a directory
with spaces — because a four-run session drives this four times and everything before it had
tested exactly **one** cycle from a freshly opened window:

| cycle | file | start | stop | bytes | rows |
|---|---|---|---|---|---|
| 1 | `cycle-1.csv` | 0 | 0 | 93980 | 30 |
| 2 | `cycle 2 with spaces.csv` | 0 | 0 | 93890 | 30 |
| 3 | `cycle-3.csv` | 0 | 0 | 91766 | 29 |

First data timestamps 20:47:19 / 20:47:43 / 20:48:06 — sequential and non-overlapping, so each
file is its own and none continues a previous log. **That was the failure worth ruling out:** the
Save As dialog remembers the last filename, and a partial replace would silently append a later
run to an earlier log.

Both scripts also run clean under the task's exact invocation,
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File ...`, which is a different code path
from running them in an open shell.

~~**Still unproven: the wrapper has never driven a real sweep.** Every test above used
`-WhatIfOnly` or exercised the logging tool alone. The first live run should be a short one
you are present for.~~

**PROVEN 2026-09-22, with the operator absent: 61 of 61 sweeps.** Every sweep and every log stop
exited 0. Every log was non-empty and recorded **118–121 rows per minute** against the 120 expected
at 0.50 s. That covered 4.6 hours of sweeps between 08:59 and 14:29, including Afterburner profile
changes verified by memory clock. Each run's `wrapper-result.json` is in
`C:\headroom-bench\results\`. **The scheduled task was never registered**; that day's runs
were driven from an already-elevated agent shell. **Two things still need a person:** opening
HWiNFO and its Sensors window, because launching it triggers UAC, and keeping the machine awake and
un-rebooted.

# `experiments/`: multi-sweep runners built on the wrapper

| script | what it is |
|---|---|
| `Run-ActivityAB.ps1` | the activity A/B test, `REGISTERED-PREDICTIONS.md` §5: uptime gate, two warm-ups, then S A A S × 3 on the stock `4i` grid. Scored by `analysis/score_activity_ab.py` |
| `Start-ActivityLoad.ps1` | the "active" condition: a logged, scripted proxy for agent activity. Changes no GPU state |

## Desktop load beside a sweep (added 2026-10-01)

An unidentified desktop load (148–240 frames per second presented, 16–64% GPU bus load in HWiNFO) sat
under §12, the §14 dry run and §10's re-collection, about 10% on `membw`, and the idle-baseline
guard did not see it. Two things now record it:

- **Identified 2026-10-03: the Claude desktop app's visible window** (−6 to −9% `membw`, even when
  covered; `data/frequency-sweeps/5060ti-deskload-20261003/`). Windows' per-process counters show it
  at ~2%, so they cannot gate it; HWiNFO's framerate can.
- `Invoke-LoggedSweep.ps1` **minimizes every visible Claude window** before the preflight, writes
  `gpu-processes-at-start.txt` (the foreground window and every process above 0.1% on any GPU
  engine), and after the sweep runs `check_desktop_load.py` on its own HWiNFO log: the verdict goes
  into `wrapper-result.json` as `desktopLoad`, the detail into `desktop-load-check.txt`, and **exit 8**
  means a window was rendering beside the benchmark. A log without the columns is recorded, not refused.
- `scan_desktop_load_corpus.py` runs the same screen over every committed RTX 5060 Ti sweep against
  whatever raw logs survive (`docs/desktop-load-census-20261003.csv`); `analysis/desktop_load_claims.py`
  maps it onto the paper's claims. Findings: `docs/DESKTOP-LOAD-AUDIT-20261003.md`.
- `check_desktop_load.py <sweep dir> <raw HWiNFO dir> --utc-offset=-07:00` flags every benchmark
  window above 30 fps or 10% bus load. A screen from one day's two clusters, not a validated gate.
