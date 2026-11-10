# Headroom Bench

Build-only implementation for the shop USB kit. Sync it with `tools/collection-kit/Sync-Kit.ps1`; the kit must already carry its Python environment and `HWiNFO64.exe`. On the shop PC, double-click `RUN-BENCH.bat` at the kit root and accept one UAC prompt. The app opens the run list written for the card it finds (see below), with its runs preselected. Drag rows to reorder, untick optional runs, double-click a row to edit its JSON, or add a custom sweep. The custom form asks for expected loaded core and memory ranges so it can witness the selected profile before measuring. Press Start. A yellow row differs from the shipped catalog, and the exact change is saved in the session JSON.

The window polls at 1 Hz and keeps measurement work in `Run-Plan.ps1`. Its controls are Start, Pause after step, Stop, and Continue for hands-on steps. The engine can also run without a window from an elevated PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\bench-app\Run-Plan.ps1 -PlanPath C:\absolute\plan.json
```

The session finish estimate uses the current time and unfinished steps, including the current step's remaining estimate. On a resume it skips completed runs and recalculates from the new attempt. An overrunning step is labelled as such. The window shows labelled GPU readings and displays `finalState` checks for HWiNFO logging, clock reset and any surviving bench processes. A red line means cleanup could not verify a stopped state; the session JSON has the details.

For a dry run, supply `-DryRun -MockPath C:\absolute\mock.json -SessionPath C:\absolute\session.json`. Dry runs use mocked telemetry and never call HWiNFO, Afterburner, or a GPU-setting command. The window also accepts `-DryRun -MockPath` for a UI rehearsal, and `-Hidden` with `-DryRun` only: the test suite uses it so the window opens off-screen and invisible instead of flashing on the desktop at every test run. Without `-DryRun`, `-Hidden` is refused.

The app records `bench-plan-<stamp>.json`, `bench-session-<stamp>.json`, a state file, control file, and output text under the USB's `results` folder. A failed or interrupted session may be resumed when reopening the window or with `-Resume -SessionPath <existing session> -PlanPath <original plan>`. Completed steps in completed runs are skipped; an incomplete run starts again, with fresh log and sweep paths. Existing measurement files are never overwritten.

## Desktop load (Job 42, 2026-10-03)

Before measurement, the engine minimizes windows belonging to the catalog's
`minimizeKnownRenderers` list. The default is an empty list on shop machines; the local
5060 Ti test catalog names `claude`. Edit the list in the catalog before generating a plan.
Names are exact process names without `.exe`, paths or wildcards. HWiNFO is refused because
its Sensors window must remain available. An optional `minimize-known-renderers` step
applies the same list at a chosen point in the run sequence.

At session start, on resume, and before each suite or custom sweep, `desktopPreflights`
records the minimization results, foreground window (title, process and PID), and every
process/engine whose two-sample mean utilization exceeds 0.1%. Missing counters or a failed
window operation are recorded with their errors. These observations do not gate a run.

After each suite or sweep, the kit's `python/python.exe` checks every produced sweep CSV
against the step's active HWiNFO log. Each benchmark window gets the median presented
framerate and NVIDIA GPU bus load, sample counts and a status in the step's `desktopLoad`.
The limits come from `tools/hwinfo-logging/check_desktop_load.py`: above 30 fps or above
10% bus load means `DESKTOP LOAD`. Equality does not flag. The NVIDIA bus column is taken
from the GPU block carrying Crossbar Clock when available; ambiguous columns are left
unchecked. Local HWiNFO timestamps use the UTC offset recorded when that log started.

A flagged step pauses the session and shows an operator message. Minimize or close rendering
windows, then press Continue to run later steps or Stop to end safely. A previous Continue
click cannot acknowledge a new warning. Continue retains the flag; the session ends FAIL
if any step's latest measurement is flagged. Resume reruns an incomplete run and can
replace its flagged steps with clean measurements; the old flags stay in history. The
measurements stay on disk for review. Missing
columns, windows or samples are recorded as `unchecked` and do not fail a step. Quiet is
only a screen, not proof of a clean run: these limits came from one day's evidence on
one card and one PC.

The desktop-load additions are tested with synthetic CSVs and dry runs under PowerShell
5.1 and 7. **Live-checked 2026-10-11 on the local RTX 5060 Ti** (`localtest-5060ti.json`, 2026-10-11
revision; `bench-session-20261011-233406.json`, **PASS**, 20 of 20 steps, Raymond present; kit results
copied to `Documents\headroom-results-backup\kit-results-20261011`):
- **window minimization**: the Claude window was minimized and verified at all three checkpoints;
- **foreground capture and GPU counters**: recorded at session start and before each measurement
  step (the bench window in front; `dwm` 3.6%, Claude 0.6% of the 3D engine at start);
- **the desktop-load screen on real HWiNFO logs**: all 17 benchmark windows quiet, median 6.1–6.7 fps
  and 3–7% bus load against the 30 fps and 10% limits;
- final state verified: logging stopped, clocks reset, no bench process left.

**The pause message was not exercised**: nothing was flagged, so it remains tested in dry run only.
The same evening's first attempt (`bench-session-20261011-231432.json`) **FAILED at its first
witness**: the kit lacked `tools/frequency-sweep/app_workloads.py`, which `gpu_workload.py` has imported
since §21 (2026-10-08), so every benchmark on the kit exited 1. It is now in `Sync-Kit.ps1`. After
the sync, the kit's first benchmark took **about 12 minutes to start**, almost all of it PyTorch loading
from the USB stick, cold; the next session's witnesses started normally. A shop run's first step can
sit silent that long.

## Which run list opens

The window opens the catalog whose `card.name` equals `nvidia-smi`'s GPU name, and asks when more than one matches. So Session D opens on the 3070 Ti and **Session E** (`catalog/sessione-2060s.json`, from `build_sessione.py`) on the RTX 2060 Super. **Only when no catalog is written for the card** does it fall back to a generic one whose `namePattern` matches.

## A new card: the generic stock protocol (REGISTERED-PREDICTIONS 11), built 2026-09-25

`catalog/newcard-rtx40-50.json`, from `build_newcard.py`, opens on **any RTX 40- or 50-series desktop card** that has no run list of its own. It was written before any such card was known. It is **stock only**: the validator refuses profiles, witnesses, hash gates and a revert slot in a generic run list, and the power gate requires the card's default limit.

- **What it runs** (~1½–2 h, unattended):
  1. calibrates the 11 suite workloads once (`gemm` stays 120);
  2. a dense `gemm` floor sweep at 40–80% of the clock table's top, 25 points, ascending;
  3. the same sweep descending;
  4. the 12-workload suite with the calibrated counts.
- **Before Start:** a fresh shop build, with no Afterburner or other tuning tool installed. Plug in the USB and double-click `RUN-BENCH.bat`. Nothing else is needed.
- **Afterwards:** import with `python analysis/import_bench_session.py --session <USB>\results\bench-session-<stamp>.json --plan <USB>\results\bench-plan-<stamp>.json --dest data/frequency-sweeps/<card>-newcard-<date>` (it prints its decisions and writes nothing), then again with `--write`. Write the README, then run `python analysis/score_new_card.py <that directory>`. The importer reads the bench session itself: the session must be live and PASS, with a GPU UUID, a matching plan hash and a verified clock reset; each step's **last** attempt is the accepted one, and it must be PASS and desktop-load **quiet** (an `unchecked` step is refused too). Earlier attempts are listed in `IMPORT.json` and never copied. Each CSV is joined by time to its own step's HWiNFO log at the UTC offset recorded when that log started. The raw logs go to `data/HWiNFO-Data/<dest>/`, which is gitignored. `IMPORT.json` hashes every file, and the scorer refuses a directory whose files do not match it, before reading anything. Keep `--dest` under the repository's short path: a 260-character Windows path broke the join in a scratch test.
- **GPT Job 88 (2026-10-12, `docs/gpt-findings/2026-10-13-newcard-kit-readiness.md`) keeps this at
  supervised-practice status.** Fixed the same day: `Sync-Kit.ps1` now refuses to sync when a copied
  script's local import or dot-source does not resolve inside the kit (`check_kit_dependencies.py`;
  it found `ThrottleReasons.ps1` missing, now added); `score_new_card.py` refuses a dense sweep without
  25 distinct points in its stated order, or with a failed benchmark, unwindowed telemetry, a clock
  above its lock or non-positive power, and reports a zero-power suite point instead of crashing;
  `Test-Plan.ps1` requires a generic list to pass a `stockOnly` power gate before measuring and allows
  no other kind; dense sweeps use the kit's short path or refuse a path with a space before locking a
  clock. *R4, the import procedure, was built 2026-10-13: `analysis/import_bench_session.py` and
  the scorer's `IMPORT.json` check (above). It ran on the real 2026-10-11 live session into a scratch
  folder; it has not imported a new card.* *GPT Job 89 audited both fixes the same day
  (`docs/gpt-findings/2026-10-13-import-and-witness-audit.md`); all eight findings were fixed that
  evening: the witness now counts only busy samples inside the probe's own timed region, bounds every
  `nvidia-smi` call, always cleans up the probe and uses Collect's resolved `nvidia-smi`; the importer
  keeps log and output paths relative to `results`, finds `results` above a nested session file,
  verifies the copied plan, hashes before parsing, and stages a failed import away.* *`Collect.ps1`'s memory witness, whose
  ~24 s of polling could miss the loaded state after a slow cold start, was fixed 2026-10-13: it now
  samples until the probe exits and counts only busy samples (`tools/collection-kit/README.md`).*
- **Tested in dry run only**, as of 2026-09-25. It has not run live on any card: calibration, percent-of-top sweeps and the `{session}` paths are exercised only against mocks. **A practice run on the 5060 Ti comes first** (`Bench-Window.ps1 -CatalogPath <kit>\tools\bench-app\catalog\newcard-rtx40-50.json`, since that card has its own run list), with Codex and ChatGPT closed.

## Session E (RTX 2060 Super), built 2026-09-24

E1 (the descending fine floor, REGISTERED-PREDICTIONS 4d), then E2 (stock, edit, stock suites, 4c), then cleanup. Its curve edit only moves points below 0.669 V, so **every profile check is a locked-clock voltage witness** in its own short log, not an unlocked peak: P1 must read 0.630-0.657 V at 1065 MHz, and P2 must read 0.668-0.700 V there and 0.681-0.707 V at 1275 MHz. There is no profile-hash gate until the store is snapshotted. Card values, iteration counts and the memory clock come from this card's committed sweeps; the reasons are beside each value in the builder, and the hands-on steps are in `docs/GPU-WORKLIST-2060S.md`. In dry run, the mock keys a witness `"slot@lock"` when one slot has witnesses at two locks.

## Session D mapping to C0-C10

- C0 power/quiet gates, C1 kit resolution, C2 profile hash, and C3 launching HWiNFO plus a Sensors-window confirmation are one preflight run. C2 hashes only the `[Profile1]`-`[Profile3]` sections (`A1159941DA541EB9`, `Profile-Hash.ps1`), because Afterburner added `[Defaults]` and `[Settings]` to the store on 2026-09-24 without changing its curves. The whole-file hash was `1B08C2D0854460FF`, then `CCE75E81FE322380` for a few hours; this line carried the latter until 2026-09-24.
- C4-C7 are the four 12-workload suites, with the worklist's labels, settings strings, iteration list, memory-clock witness and separate voltage logs. After C7, a 1.5% stock-return gate uses the same per-workload median absolute matched-target throughput change as `score_session_d.py`.
- C5 adds a **separate short HWiNFO log for the locked 1395 MHz voltage witness**. The original worklist asks the person to read voltage in the Sensors window before the suite log starts; an independent short log allows an auditable automated check without spanning profiles.
- C8 uses explicit `gemm` 120 iterations, equal to `gpu_workload.py`'s default, and the worklist's 1200-1590 MHz descending ten-point grid.
- C9 verifies 290/290/320 W and stock core/memory under load. The engine then resets clocks, stops logging, applies P1 and repeats the stock witness. Only after that does it ask the person to uninstall Afterburner and remove its Profiles folder. C10 is the instruction to bring back the USB; scoring stays on the local machine.

**Live-tested 2026-09-23 on the local RTX 5060 Ti** (Ryzen 9700X, driver 616.92), with
`catalog/localtest-5060ti.json`, launched by Raymond from `RUN-BENCH.bat` on the USB and ending
**PASS** after two resumes. It exercised, for real:
- the power, quiet-GPU and profile-hash gates;
- a Sensors confirmation step;
- Afterburner profile apply;
- a locked-clock witness reading **0.720 V** from HWiNFO;
- **HWiNFO 8.52-6060 logs started and stopped automatically**, eight times;
- a one-workload `Collect.ps1` suite (13/13 points);
- a 4-point descending sweep;
- resume twice;
- the cleanup revert and its stock witness.

It found four defects, all fixed the same evening:
- **a CPU with integrated graphics adds a second "GPU Core Voltage" column**, and the reader failed
  every sample. The Ryzen iGPU read 0.725 V, inside the witness window, so picking it would have
  passed on the wrong GPU;
- **PS 5.1 lost the child's exit code**, so a completed suite was reported as failed;
- the resume offer could pick a `.state.json` or `.control.json` sibling;
- a resumed session showed FAIL while running.

**Later the same evening, three more live sessions, all PASS** (`bench-session-20260923-*.json`
on the kit; copied to `Documents\headroom-results-backup\kit-results-20260923`):

| session | machine | what it tested for the first time |
|---|---|---|
| 21:26 | 5060 Ti | Job 16's final check **with HWiNFO open**: logging `stopped (verified)`; preflight applying the stock slot itself before the power gate |
| 21:56 | **3070 Ti** | `shakedown-3070ti.json`, 23/23 on the shop machine: Edit 1 locked 1395 read **0.850 V**, Edit 2 peaked **1515**, C8 fine sweep 10/10 locked |
| 22:25 | 5060 Ti | **Sensors already open before Start**: no second launch, the Sensors step passed **by itself in 0.7 s** (`confirmedBy: auto`), and the session ran start to finish untouched |

And six more defects, found by those runs, all fixed that night:
- a tuned profile left live failed the power gate at step 1. Preflight now checks the hash, applies stock, then gates;
- the step line wrapped and was clipped;
- **an `nvidia-smi` stderr line in the refresh tick raised a modal .NET dialog** that froze the window (PS 5.1 under Stop, even with `2>$null`). The tick is guarded and logs to `<session>.window-errors.txt`;
- **the resume offer ignored which card a session was for**. On the 3070 Ti it offered the 5060 Ti's failed session, and the cleanup then applied that plan's revert slot, which is Edit 2 there;
- the progress bar stopped one short of full;
- **the 3070 Ti stock witness ceiling of 1900 MHz was 10 MHz above a real reading** (1890; 1935 read back after reset). It is now 2115, the card's maximum.

**The quiet gate sums SM across processes.** On this PC the Claude desktop app (1-3%) and `dwm` (~1%)
read 6% at 22:25. HWiNFO has no GPU context and does not appear in `pmon`. The 3070 Ti read 0%.

**Still not tested live:**
- the drift gate;
- Stop in the middle of a suite;
- the manual HWiNFO fallback;
- the run-list chooser with several matching lists;
- **a full 12-workload suite through the app, on any machine** (Session D is the first);
- auto-continue with HWiNFO **launched by the app** rather than opened beforehand.

A shop machine may differ in ways this PC cannot show.

The Session D catalog limits custom sweeps to 405-2115 MHz, the SILENT-BIOS range recorded for this card. The engine checks those bounds again against the live supported-clock table before starting. A different card or BIOS needs its own measured bounds in its catalog.
