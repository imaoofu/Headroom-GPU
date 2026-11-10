# RTX 5060 Ti: section 15, clean re-runs of R1 (§12) and R3 (ladder rungs B and C), 2026-10-03

`docs/REGISTERED-PREDICTIONS.md` §15, registered `377e1be` before collection, amended before
collection in `1302dc2` (desktop-load screen on framerate alone). Collected unattended
15:13–19:44 by `tools/rerun15/Invoke-Rerun15Session.ps1` (copy here as
`runner-Invoke-Rerun15Session.ps1.txt`). Driver 616.92. **53 sweeps, every one dataset-grade:
0 display-driver events, 0 desktop-load exits, 0 retries, 0 preflight refusals.** R2 was deferred.

**Why it exists.** On 2026-10-03 the Claude desktop app's visible window was shown to cost 6–9% of
`membw` (`../5060ti-deskload-20261003/`), and its HWiNFO signature sits under §12's pair and both
ladder rungs. This session re-collects them with that load excluded and checked at every sweep.

## Verdicts

```
python analysis/score_rerun15.py r1 data/frequency-sweeps/5060ti-rerun15-20261003
python analysis/score_rerun15.py r3 data/frequency-sweeps/5060ti-rerun15-20261003
```

| part | prediction | result | verdict |
|---|---|---|---|
| R1 | gate: closing stock `membw` band mean within 1.5% of opening | **+0.014%** | passes |
| R1 | **primary:** curve 3 `membw` below opening stock at every target 1560–1867 | ratios 0.936 / 0.922 / 0.901 / 0.890 / 0.885 | **HOLDS** |
| R1 | crossbar: curve 3 within 1300–1360 MHz 1402–1867; stock strictly rising | curve 3 1312–1342; stock 1335 → 1807 | **HOLDS** |
| R1 | secondary: curve 3 `gemm` board power below stock at every target 1545–2475 | **1.001 at 1545** (75.37 against 75.27 W); 0.913 to 0.760 at 1702–2475 | **FAILS** |
| R1 | load: clean opening stock band mean at least 3% above §12's | **+8.16%** | **HOLDS** |
| R3 | gate: worst workload's median absolute stock-to-stock change within 1.5% | **0.063%** (`bgemm128`); the others 0.010–0.033% | passes |
| R3 | **primary:** median optimum 1702 MHz on rung B, 1852 on rung C | **1702 and 1852** | **HOLDS** |
| R3 | secondary: at least 7 of 12 on the predicted point | **7 of 12** (rung B), **9 of 12** (rung C) | **HOLDS** |
| R3 | tertiary: both stock medians ≤ B < C | stock 1545 / B 1702 / C 1852 / stock 1545 | **HOLDS** |

R1's verdict is FAILS because one registered secondary prediction failed; its primary, telemetry
and load predictions hold. R3 HOLDS on every prediction.

**Evidence gates.** Every role passed: §15's memory rule at all 1,360 point-instrument checks
(nvidia-smi samples and HWiNFO, references included); desktop framerate 4–8.8 fps in every window;
every profile witness (section hash, slot, power limit, memory under load, mVolt+ offsets and
voltage demands all 0).

## What it shows, and what it does not

- **The plateau is not a desktop-load artifact.** Measured clean and memory-matched, curve 3 is
  6.4–11.5% below stock at every target 1560–1867, against §12's 7.6–13.7% under load. Reported,
  not scored: ratios 0.936 / 0.901 / 0.885 at 1560 / 1710 / 1867 beside §12's 0.924 / 0.886 / 0.863,
  so the load slightly exaggerated the gap.
- **The load did depress §12's absolute bandwidth**, by about 8%: the clean stock band mean is
  8.16% above §12's opening stock sweep, the size the ABA test predicted.
- **Both ladder rungs reproduce clean**, on their registered points. Rung B lands exactly on the
  7-of-12 threshold; its per-workload optima agree with the 09-23 original at 5 of 12, rung C's
  with its original at 9 of 12. The medians, not the per-workload points, are what reproduce.
- **The `gemm` power secondary fails where the two curves coincide.** At 1545 MHz both arms reach
  1537 MHz and both report 0.720 V (their crossbar clocks still differ, 1455 against 1365 MHz);
  the clean session draws equal power (+0.13%). §12's −3.5% at that target was
  measured under the load. Above the floor, 1702–2475, curve 3 draws 8.7–24.0% less. §12's
  secondary is narrowed accordingly in the registry.
- **A quiet desktop makes this card very reproducible:** stock suites four hours apart agree to a
  median 0.01–0.06% per workload, where the 2026-09 replicate suites spread 0.87% (throughput).
- One chip, one session, one collection per arm. The twelve workloads are repeated outcomes on
  that chip. Desktop framerate is a screen, not proof of an idle machine.

## Files

| file | what |
|---|---|
| `*_sweep.csv`, `*_sweep.json` | the 53 sweeps; each point carries `memory_clock_samples_mhz`, the in-window nvidia-smi readings |
| `*_sweep_voltage.csv` | `tools/frequency-sweep/join_hwinfo_voltage.py`, joined by time |
| `rerun15-inputs.json` | the scorer's evidence map (roles, sweeps, raw logs, wrapper results, witnesses), paths relative to here |
| `wrapper/` | each sweep's wrapper result, desktop-load check and GPU-users-at-start record |
| `witnesses/` | per arm: the live profile store copied before the arm, mVolt+ status, witness record |
| `session.log` | the runner's log |
| raw HWiNFO logs | gitignored, `data/HWiNFO-Data/5060ti-rerun15-20261003/` |

The runner's dry run (14:46–15:05, single-target sweeps) is not data and is not committed; it found
the bus-load false positive that `1302dc2` amended before this session began.
