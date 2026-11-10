# RTX 5060 Ti: section 20, where efficiency peaks relative to the floor's end on a fine grid, 2026-10-08

`docs/REGISTERED-PREDICTIONS.md` §20, registered 2026-10-07 before collection (`3129fa0`). Collected
unattended 08:38–14:20 by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20` (copy here as
`runner-Invoke-Rerun15Session.ps1.txt`), launched by `C:\headroom-bench\Run-S20Morning.ps1` after a dry
run the same morning (`C:\headroom-bench\rerun15\20261008-082233-s20dry`, not data, not here). Driver
616.92. **48 sweeps, every one dataset-grade: 0 display-driver events, 0 desktop-load exits, 0
retries.** Operator away at school; Claude minimized; ChatGPT, Codex, Opera, Discord and Obsidian
closed. No 20 Hz NVML logger this time.

Order: **stock (Profile 3) ascending → full tune (P4) ascending → P4 descending → stock
descending**, twelve workloads each with §10's iteration counts. Each configuration has its own
18-point grid at 37.5 MHz (every fifth supported clock): stock 1237–1875 MHz, P4 1672–2310 MHz,
centred on the registered floor ends 1575 and 2010 MHz. Every sweep is schema 0.3.4.

## Verdicts

```
python analysis/score_session20.py data/frequency-sweeps/5060ti-session20-20261008
```

| gate or prediction | stock | P4 |
|---|---|---|
| gate: stock ascending-to-descending, worst workload ≤ 1.5% | 0.300% | - |
| **F1** argmax ≤ floor end + 1 step, 2 misses allowed | 11 of 12 (yes) | 11 of 12 (yes) |
| **F2** median efficiency lost at the floor end ≤ 3% | 2.38% (yes) | 0.12% (yes) |
| **F3** lower 300 MHz above the floor end, 2 misses allowed | 11 of 12 (yes) | 11 of 12 (yes) |
| within one step of the floor end (reported) | 5 | 9 |
| floor end in these voltage extracts (reported, not substituted) | median 1575 | median 2047 |

The miss on both curves is `reduce` (stock 1800 MHz; P4 2310, the top of its grid, so unbracketed).
Per-workload argmaxes, losses and per-direction argmaxes are in the registry and the scorer's output.
Where the loss at the floor end is a fraction of a percent the argmax's location means little: P4
`bgemm32`'s averaged argmax is 1785 MHz although both directions peak at 2010–2047.

## Evidence gates

- Witness per arm, before its first sweep: profile store restored byte for byte from `curve3` and
  Afterburner closed; slot 3 at 180 W with memory 13801 MHz under load, slot 4 at 200 W with 16301;
  mVolt+ offsets and voltage demands 0.
- `gemm` at a locked 2475 MHz after 90 s idle: stock 180.1 / P4 150.2 / P4 148.8 / stock 179.8 W.
- Desktop-load screen: **0 of 864 windows flagged, 4.0–8.0 fps**.
- Back on stock at the end: memory 13801 MHz under load, 180 W.
- GPT Job 65's pre-scoring audit had not landed when this was scored; see the registry.

## Files

| file | what |
|---|---|
| `*_sweep.csv`, `*_sweep.json` | the 48 sweeps |
| `*_sweep_voltage.csv` | `tools/frequency-sweep/join_hwinfo_voltage.py`, joined by time; 864 points, none empty, at least 14 samples each |
| `rerun15-inputs.json` | the scorer's evidence map, paths relative to here |
| `wrapper/` | each sweep's wrapper result, desktop-load check and GPU-users-at-start record |
| `witnesses/` | per arm: the live profile store copied before the arm, mVolt+ status, witness record |
| `session.log` | the runner's log |
| raw HWiNFO logs | gitignored, `data/HWiNFO-Data/5060ti-session20-20261008/` |

Efficiency is throughput over the 2 Hz `power_avg_w`; the energy-counter figure is reported beside it.
Board power is the card's own telemetry, not a shunt. N=1 chip, one session, one sweep per direction
per workload; the twelve workloads are repeated outcomes on it.
