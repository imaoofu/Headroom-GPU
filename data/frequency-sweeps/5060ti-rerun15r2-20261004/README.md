# RTX 5060 Ti: section 15 R2, the 2026-08-20 pair and its repair, clean, 2026-10-04

`docs/REGISTERED-PREDICTIONS.md` §15 R2, registered `377e1be` before any §15 collection and run in
its own session as decided on 2026-10-03 (its stock roles share R1's names, so one evidence map
holds R1 or R2, not both). Collected unattended 19:15–19:38 by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts r2` (copy here as
`runner-Invoke-Rerun15Session.ps1.txt`), after a dry run at 19:04–19:13 that is not data. Driver
616.92. **4 sweeps, every one dataset-grade: 0 display-driver events, 0 desktop-load exits, 0
retries, 0 preflight refusals.** Operator away; Claude minimized; ChatGPT, Codex, Opera, Discord
and Obsidian closed.

Order: stock (Profile 3) → full tune (P4) → repair (P2) → stock, all `membw` on the 08-20 grid
(1402–2100 MHz, 10 targets), default iterations.

## Verdicts

```
python analysis/score_rerun15.py r2 data/frequency-sweeps/5060ti-rerun15r2-20261004
```

| prediction | result | verdict |
|---|---|---|
| gate: closing stock band mean within 1.5% of opening | **−0.02%** | passes |
| plateau: P4 below opening stock at every target 1560–1867 | ratios 0.960 / 0.944 / 0.922 / 0.910 / 0.908 | **HOLDS** |
| crossbar: P4 within 1300–1360 MHz 1402–1867; stock rising | P4 1312–1350; stock 1335 → 1807, rising at each target | **HOLDS** |
| repair: P2 above P4 at every target 1560–1867, at least +8% at 1867 | P2/P4 1.101 / 1.129 / 1.177 / 1.212 / **1.245** | **HOLDS** |
| load: clean stock band mean at least 3% above the 08-20 stock sweep | **+15.65%** | **HOLDS** |

**R2 HOLDS on every prediction.** Evidence gates: §15's memory rule passed at all 80
point-instrument checks (nvidia-smi samples and HWiNFO; stock 13801, P4 and P2 16301 MHz); desktop
framerate 4–6 fps in every window; every profile witness (section hash, slot, power limit, memory
under load, mVolt+ offsets and voltage demands all 0).

## What it shows, and what it does not

- **The August plateau and the repair are not desktop-load artifacts.** Clean, the full tune is
  4.0–9.2% below stock at 1560–1867 MHz, and the repair is 10.1–24.5% above the full tune there.
  The full tune sits near 350 GB/s across 1560–1867 MHz while stock rises from 365 to 388 GB/s.
- **P4 against stock is not memory-matched** (+2500 against +0), exactly as the 08-20 pair was.
  §15 R1 (`../5060ti-rerun15-20261003/`) is the memory-matched version. P2 against P4 is matched:
  both carry +2500 and 200 W.
- **Today's P4 is not proved identical to the 08-20 "oc" profile** (§12), so the predictions
  are about today's profiles and the 08-20 numbers are compared descriptively only.
- **The load depressed the 08-20 stock sweep by about 16%** in band mean, twice §12's 8%. That
  session predates the Instant Replay finding too, so the 16% is not attributed to the desktop
  window alone.
- One chip, one session, one sweep per arm, one workload. Desktop framerate is a screen, not proof
  of an idle machine.

## Files

| file | what |
|---|---|
| `*_sweep.csv`, `*_sweep.json` | the 4 sweeps; each point carries `memory_clock_samples_mhz` |
| `*_sweep_voltage.csv` | `tools/frequency-sweep/join_hwinfo_voltage.py`, joined by time |
| `rerun15-inputs.json` | the scorer's evidence map, paths relative to here |
| `wrapper/` | each sweep's wrapper result, desktop-load check and GPU-users-at-start record |
| `witnesses/` | per arm: the live profile store copied before the arm, mVolt+ status, witness record |
| `session.log` | the runner's log |
| raw HWiNFO logs | gitignored, `data/HWiNFO-Data/5060ti-rerun15r2-20261004/` |
