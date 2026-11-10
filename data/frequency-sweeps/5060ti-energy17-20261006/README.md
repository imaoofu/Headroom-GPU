# RTX 5060 Ti: section 17, sampled board power against NVML's energy counter, stock, 2026-10-06

`docs/REGISTERED-PREDICTIONS.md` §17, registered `88973a6` before collection. Collected unattended
18:53–19:46 by a one-off wrapper (copy here as `runner-Run-Energy17.ps1.txt`; its log is
`runner.log`). Stock, Afterburner Profile 3 applied by the wrapper, 180 W read back, driver
616.92, Claude minimized, operator away. **12 sweeps, every one dataset-grade:** all exited 0, 13 of
13 points each, every point power-windowed, memory 13801 MHz under load at 155 of 156 points (one
14001, the graphics P-state). Baseline utilisation 0%, encoder 0%. Sweep schema **0.3.4**, the first
to carry `energy_joules`, `energy_window_seconds` and `energy_avg_power_w`.

A two-point `gemm` test sweep ran first (1545 and 2475 MHz) to check both power figures were
recorded and the card was at stock. It is **not data** and is not committed; it stays on the bench
PC (`C:\headroom-bench\energy\20261006-s17\test`). It read the counter 3.0% and 4.1% above the
sampled power.

No HWiNFO log was taken, so there are no voltage extracts and the desktop-load framerate screen
cannot be applied: in the census these sweeps are **unknown, not quiet**.

## Verdicts

```
python analysis/compare_energy_power.py data/frequency-sweeps/5060ti-energy17-20261006
```

| prediction | result | verdict |
|---|---|---|
| scoreable: ≥ 11 of 12 sweeps with ≥ 12 of 13 points carrying both figures | 12 of 12, 13 of 13 | passes |
| **A:** median absolute per-point difference ≤ 2% | **7.83%** (156 points, every one positive; worst 15.35%) | **FAILS** |
| **B:** optimum unchanged in ≥ 10 of 12, and the suite median unchanged | **8 of 12**; median 1545 MHz both ways | **FAILS** |

Per workload, the median difference (energy over sampled):

| workload | median | range | optimum, sampled → energy |
|---|---|---|---|
| copy | +8.75% | +4.98 to +11.96% | 1702 → **1545** |
| reduce | +8.91% | +6.16 to +12.49% | 1702 |
| softmax | +8.13% | +6.18 to +13.41% | 1545 |
| layernorm | +8.26% | +6.08 to +14.21% | 1395 → **1545** |
| bgemm32 | +8.79% | +6.28 to +13.57% | 1545 |
| bgemm64 | +9.44% | +7.21 to +13.43% | 1395 → **1545** |
| bgemm128 | +9.56% | +5.41 to +15.35% | 1702 → **1545** |
| bgemm256 | +6.98% | +3.28 to +11.85% | 1545 |
| bgemm1024 | +8.05% | +2.79 to +12.43% | 1545 |
| attention | +3.35% | +1.10 to +7.46% | 1545 |
| conv | +3.28% | +1.23 to +6.77% | 1545 |
| gemm | +2.90% | +1.65 to +4.08% | 1545 |

## What it shows, and what it does not

- **The two power figures disagree by more than the registered 2%, always in the same direction:**
  the integrated counter reads higher at every one of 156 points. Median +7.83%.
- **The gap depends on the workload:** about +3% on `gemm`, `conv` and `attention`, about +7 to
  +10% on the others, which have lower arithmetic intensity. That is an observation from one suite;
  why it happens is **not** established here.
- **The gap also scatters point to point by several percent within one sweep.** *This said
  "more than the counter's quantisation (≤ 2.55% for these windows)"; GPT Job 57 (F4) showed that
  bound overstated: a one-tick stale read at each edge moves a constant-power figure by at most
  0.1/T, 0.54–1.28% here, in either direction, and nothing bounds varying power.* Near each optimum the efficiency curve is
  flat, so that scatter is enough to move 4 of 12 per-workload optima by one grid step. The median
  optimum is the same either way.
- **Neither figure is a measurement against a shunt.** Both are the card's own telemetry, so this
  shows they are inconsistent with each other, not which one is right. Candidate explanations, none
  tested: a lag or averaging window in the sampled `power.draw` reading at the edges of the timed
  region; a difference in what each figure includes; sampling of a fluctuating draw at 2 Hz.

## GPT Job 57 audit, 2026-10-07 (`docs/gpt-findings/2026-10-07-section17-audit.md`), rechecked here

Both verdicts stand, and every number above reproduces. Three things it found change how they read:

- **The sampled figure often starts in an idle state.** In **52 of 156** points the first 2 Hz
  sample inside the window reads memory at 810 or 7001 MHz, and the median point's lowest power
  sample is **0.20** of its mean. Dropping one minimum reading per point (an influence check on
  rounded aggregates, not a correction) moves the median gap from **+7.83% to +2.59%**. So a single
  low reading at the window's start carries much of the gap. Why it is low is not established.
- **The two windows are not literally the same.** The counter brackets the timed region from just
  outside it; the 2 Hz samples are selected by host timestamps taken after each query. They agree
  within 15 ms at 155 points. At `reduce` 2625 MHz they differ by **2.18 s**, a candidate backward
  clock adjustment; excluding that point leaves the median at +7.80% and both verdicts unchanged.
- **`compare_energy_power.py` is descriptive**: it does not enforce the scoreability rule, and it
  accepted non-finite values. It now refuses them and prints the corrected tick bound.

N=1 chip, one stock suite.

- One chip, stock, one suite, one session.
