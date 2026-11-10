# RTX 5060 Ti: section 21, the floor's end on four application workloads, 2026-10-09

`docs/REGISTERED-PREDICTIONS.md` §21, registered 2026-10-08 before collection (`0d0ee77`). Collected
unattended 08:46–11:55 by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s21` (copy here as
`runner-Invoke-Rerun15Session.ps1.txt`), launched by `C:\headroom-bench\Run-S21Morning.ps1` after a dry
run the same morning (`C:\headroom-bench\rerun15\20261009-082257-s21dry`, not data, not here). Driver
616.92. **24 sweeps, every one dataset-grade: 0 display-driver events, 0 desktop-load exits, 0
retries.** Operator away; Claude minimized; ChatGPT, Codex, Opera, Discord and Obsidian closed. No 20 Hz
NVML logger.

**Workloads** (`tools/frequency-sweep/app_workloads.py`): `alexnet` and `resnet50` forward passes with
**seeded random weights on a synthetic input batch** (not pretrained, not photographs), and `kmeans` and
`hotspot`, this project's **PyTorch ports** on generated inputs, not the Rodinia binaries. Iterations
3484 / 424 / 85 / 14, constant across every sweep. Call them application workloads, never "real
applications" without those caveats.

Order: **stock coarse ascending → stock fine ascending → P4 fine ascending → P4 fine descending → stock
fine descending → stock coarse descending**. Fine grids are §20's (37.5 MHz, 18 points: stock 1237–1875,
P4 1672–2310 MHz); the coarse grid is §10's 13 points, 1237–3090 MHz. Every sweep is schema 0.3.4.

## Verdicts

```
python analysis/score_session21.py data/frequency-sweeps/5060ti-session21-20261009
```

| gate or prediction | stock | P4 |
|---|---|---|
| gate: fine ascending-to-descending, worst workload ≤ 1.5% | 0.104% | - |
| gate: coarse ascending-to-descending, worst workload ≤ 1.5% | 0.083% | - |
| **A1** argmax ≤ floor end + 1 step, 1 miss allowed | 4 of 4 (yes) | 4 of 4 (yes) |
| **A2** median efficiency lost at the floor end ≤ 3% | 0.40% (yes) | 0.55% (yes) |
| **A3** lower 300 MHz above the floor end, 1 miss allowed | 4 of 4 (yes) | 4 of 4 (yes) |
| **A4** coarse argmax ≤ 1702 MHz, 1 miss allowed | 4 of 4 (all at 1545) | - |
| within one step of the floor end (reported) | 3 | 4 |
| floor end in these voltage extracts (reported, not substituted) | median 1575 | median 2047 |

Fine-grid argmaxes, stock: `alexnet` 1537, `resnet50` 1575, `kmeans` 1575, `hotspot` 1500 MHz. P4:
2047, 2047, 2047, 2010. P4's three 2047 peaks are one step above the registered 2010, inside the
allowance. Per-direction argmaxes differ for stock `hotspot` (1500 / 1537), P4 `alexnet` (2010 / 2047)
and P4 `kmeans` (1972 / 2047). The registry has the full per-workload table.

## Evidence gates

- Witness per arm, before its first sweep: profile store restored byte for byte from `curve3`; slot 3
  at 180 W with memory 13801 MHz under load, slot 4 at 200 W with 16301; mVolt+ offsets and voltage
  demands 0.
- `gemm` at a locked 2475 MHz after 90 s idle: stock 180.0 / 180.0, P4 150.9 / 152.1, stock 180.1 /
  180.0 W.
- Desktop-load screen: **0 of 392 windows flagged, 4.0–8.1 fps**.
- Restored at the end: clocks reset, curve 3 store, Profile 3 (stock).
- Claude ran one `nvidia-smi` query and a few log reads at about 09:08–09:09, during the start of
  `s21-stock-coarse-asc-hotspot`. That sweep's windows all screen quiet, and the coarse return check
  (which includes it) is 0.083%.

## Files

| file | what |
|---|---|
| `*_sweep.csv`, `*_sweep.json` | the 24 sweeps |
| `*_sweep_voltage.csv` | `tools/frequency-sweep/join_hwinfo_voltage.py`, joined by time; 392 points, none empty, at least 16 samples each |
| `rerun15-inputs.json` | the scorer's evidence map, paths relative to here |
| `wrapper/` | each sweep's wrapper result, desktop-load check and GPU-users-at-start record |
| `witnesses/` | per arm: the live profile store copied before the arm, mVolt+ status, witness record |
| `session.log` | the runner's log |
| raw HWiNFO logs | gitignored, `data/HWiNFO-Data/5060ti-session21-20261009/` |

Efficiency is throughput over the 2 Hz `power_avg_w`; the energy-counter figure is reported beside it.
Board power is the card's own telemetry, not a shunt. N=1 chip, one session, one sweep per direction
per workload; the four workloads are repeated outcomes on it.
