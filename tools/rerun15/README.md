# Registered-session runner

`Invoke-Rerun15Session.ps1` runs one REGISTERED-PREDICTIONS session on the RTX 5060 Ti, unattended,
from preflight to a scorer-ready evidence map. It **changes GPU state**: it restores Afterburner's
profile store, applies profile slots and locks clocks through the sweep, and it resets all of it on
every exit path. Written for section 15 (hence the name); every later section reuses it.

**Elevated shell, HWiNFO running, and launched DETACHED.** On 2026-10-06 the first section 16
collection was killed at 11:22 by the agent's two-hour limit on a background command, mid-sweep.
Start it as a separate process (the morning launchers below do), never as a tool call that waits.

## Parts

| `-Parts` | registry section | sequence | scorer |
|---|---|---|---|
| `r1` | §15 R1 | stock `membw`/`gemm` → curve 3 → stock | `analysis/score_rerun15.py` |
| `r2` | §15 R2 | stock → P4 → P2 → stock, `membw` | `analysis/score_rerun15.py` |
| `r3` | §15 R3 | stock → rung B → rung C → stock suites | `analysis/score_rerun15.py` |
| `r1r3` | §15 | R1 then R3 | `analysis/score_rerun15.py` |
| `s16` | §16 | P5 → P4 → P2 → P5 suites | `analysis/score_session16.py` |
| `s19` | §18, §19 | stock → P5 → P4 → rung B → rung C → stock suites, 20 Hz NVML logger | `analysis/score_power_fields.py`, `analysis/score_session19.py` |
| `s20` | §20 | stock asc → P4 asc → P4 desc → stock desc, 18-point fine grids | `analysis/score_session20.py` |
| `s21` | §21 | stock coarse asc → stock fine asc → P4 fine asc → P4 fine desc → stock fine desc → stock coarse desc, four application workloads | `analysis/score_session21.py` |
| `s20b` | §20b | stock witnessed, then `tools/section20b/run_core_session.py` (needs `-Session N`) | `analysis/score_section20b.py` |
| `rep` | §22 | one repeatability day (`-Session N`, 1–5): stock, the day's four-workload pass on 20 targets, stock again, the mirrored pass; no role retry; filed by `file_repeatability_day.py` | `analysis/score_repeatability.py` |

**§22 qualification, 2026-10-14** (`-Parts rep -Session 1 -DryRun`, not data): the first try stopped at
pass 2 because the per-role settings note reached 601 characters against the sweep wrapper's 600 limit;
its failure path restored stock and wrote `runner-cleanup.json`. With the note shortened, the second try
ran all eight roles (exit 0, no display-driver events, stock restored), `gemm`/`copy`/`reduce` received
`--input-seed 20261013` and `resnet50` none, and a scratch filing plus `load_day` on those real files
failed only the full-grid rule a one-target dry run must fail.

A suite is twelve workloads with section 10's iteration counts (`$ITER`). The coarse grid is
1237–3090 MHz in 13 points; §20's fine grids are every fifth supported clock (37.5 MHz) around each
configuration's floor end.

## What every session does

- **Preflight refuses** unless: elevated, driver 616.92, no `llama-server`, no mVolt+ window, Opera /
  Discord / Obsidian / games closed, HWiNFO sensors ready, ChatGPT/Codex closed (or `-ManageChatGpt`,
  which closes them and relaunches what was open at the end), and no display-driver event yet.
- **Profile store** restored byte for byte from a committed snapshot (`curve3`, `rungB`, `rungC` in
  `data/afterburner-profiles/`) with Afterburner closed, then section-hash verified.
- **Witness per arm**, saved under `witnesses/`: the live store copy, slot, power limit and memory
  clock under load read live, the driver, mVolt+ offsets and voltage demands (all must be 0), and for
  `s16`/`s19`/`s20` `gemm` power at a locked 2475 MHz after 90 s idle (P5 ≤ 163 W and P2 ≥ 165 W gated).
- **Every sweep** goes through `tools/hwinfo-logging/Invoke-LoggedSweep.ps1`, which minimizes the
  Claude app, logs HWiNFO at 0.50 s and exits 8 on a desktop load. Exit 8 gets one retry after 60 s; a
  second exit 8 marks the role NOT SCOREABLE and the session continues. Preflight refusals (exit 4)
  wait 120 s and ask again, twice. Any other failure, or any display-driver event, ends the session.
- **`finally`**, on every exit: clocks reset, `curve3` store restored, Profile 3 (stock) applied and
  read back, the NVML logger stopped (`s19`), the manifest saved with the exit code.
- `-DryRun` sweeps each list's first target only and one workload per suite. Its output is not data.

## Output

`C:\headroom-bench\rerun15\<stamp>-<part>\`: `session.log`, `witnesses/`, and `rerun15-inputs.json`,
the evidence map every scorer reads (section, roles → sweep CSV, HWiNFO log, wrapper result and
witness; `notScoreable`; `exitCode`). Sweep folders land in `C:\headroom-bench\results\`.

To file a session, copy it into `data/frequency-sweeps/<name>/` as the §16 and §19 directories do:
sweeps and JSONs, `join_hwinfo_voltage.py --join-by time --hwinfo-utc-offset=-07:00` extracts, the
wrapper records under `wrapper/`, `witnesses/`, `session.log`, a copy of this runner as
`runner-Invoke-Rerun15Session.ps1.txt`, and `rerun15-inputs.json` with paths made relative. Raw
HWiNFO logs go to the gitignored `data/HWiNFO-Data/<name>/`.

## Morning launchers (bench-side, not in the repository)

`C:\headroom-bench\Run-S19Morning.ps1`, `Run-S20Morning.ps1` and `Run-S21Morning.ps1` run the part's dry run, check that it
exercised every part (all arms' roles; for `s20`, a descending suite swept descending), and only then
start the real session. Their log is `C:\headroom-bench\s<NN>-morning.log`.

## Limits

One card, one driver and one machine are assumed: the GPU id, driver version, slot meanings and
snapshot names are literals. A clean exit says the session ran as registered; whether its data are
clean is the desktop-load screen's and the scorer's call, and N=1 chip either way.
