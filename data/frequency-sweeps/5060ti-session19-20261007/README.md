# RTX 5060 Ti: sections 18 and 19, which power reading the energy counter matches and the key optima by energy, 2026-10-07

`docs/REGISTERED-PREDICTIONS.md` §18 and §19, registered 2026-10-06 before collection; §18's
meanings narrowed and §19's scorer hardened during collection, before either's data was read.
Collected unattended 08:57–15:08 by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s19` (copy here
as `runner-Invoke-Rerun15Session.ps1.txt`), after a dry run the same morning
(`C:\headroom-bench\rerun15\20261007-083354-s19dry`, not data, not here). Driver 616.92. **72
sweeps, every one dataset-grade: 0 display-driver events, 0 desktop-load exits, 0 retries.**
Operator away at school; Claude minimized; ChatGPT, Codex, Opera, Discord and Obsidian closed.

Order: **stock (Profile 3) → split (P5) → full tune (P4) → rung B → rung C → stock**, six
twelve-workload suites, grid 1237–3090 MHz in 13 points ascending, §10's iteration counts. Every
sweep is schema 0.3.4, so every point carries both `power_avg_w` (`nvidia-smi`, 2 Hz) and
`energy_avg_power_w` (NVML's energy counter read at the timed region's edges).

## Verdicts

```
python analysis/score_power_fields.py data/frequency-sweeps/5060ti-session19-20261007
python analysis/score_session19.py data/frequency-sweeps/5060ti-session19-20261007
```

| prediction | result | verdict |
|---|---|---|
| **§18 H1:** instant at 20 Hz within 2% of the counter, median absolute | 8.05% | FAILS |
| **§18 H2:** `power.draw` at 20 Hz within 1% of the 2 Hz sample, median absolute | 1.17% (signed median +0.14%) | FAILS |
| **§19** gate: equal stock energy medians; stock return ≤ 1.5% | 1545 and 1545 MHz; worst 0.048% | passes |
| **§19:** energy-figure medians 1545 / 1545 / 2010 / 1702 / 1852 / 1545 MHz | exactly those | HOLDS at every arm |

**Reported, always:** the sampled-figure medians are the same six values. Optima that differ
between the two power figures: stock opening 4, P5 3, P4 6, rung B 3, rung C 3, stock closing 5,
of 12; 21 of those 24 move one grid step, two move two and one moves three. Every **median**
reading sits above the counter here: sampled +2.86%, `power.draw` and the average field +3.24%,
instant +8.04% (medians over 936 points; per configuration and per workload in the registry). Per
window the sampled figure is below the counter in 275 of 936. No single workload's one-step
change could have moved any arm's median (GPT Job 61), so HOLDS does not rule out per-workload
changes.

**§17's sign did not repeat.** §17 (stock, no HWiNFO, no 20 Hz logger) had the counter 7.83%
**above** the sampled figure at every point; here it is below it in every configuration.

## Exploratory, not registered

```
python analysis/explore_power_fields.py data/frequency-sweeps/5060ti-session19-20261007
```

- Whole session: counter 1104.4 kJ against 1113.2 kJ integrated instant (−0.79%) and 1111.6 kJ
  integrated average (−0.64%).
- Instant over average, median per window: first second +82.8%, rest of window +0.9%. The
  averaged field, which is what `power.draw` reports, lags at the window's start.
- Instant over the 2 Hz sample, by workload, +1.79% (`attention`) to +6.70% (`bgemm32`), smallest
  on the three kernels with the longest warm-up, the same pattern as §17.
- This session was polled (HWiNFO 0.5 s, the logger at 20 Hz) and §17 was not. That is one
  candidate for the sign change, not a finding.

## Evidence gates

- Witness per arm, before its first sweep: memory under load 13801 MHz on stock and 16301 on the
  tuned arms, power limit 180 / 200 W, mVolt+ offsets and voltage demands 0, Afterburner closed,
  profile store restored byte for byte (from `curve3` for stock, P5 and P4; `rungB` and `rungC`
  for the rungs; the closing stock arm runs Profile 3 of the `rungC` store, which is stock).
- `gemm` at a locked 2475 MHz after 90 s idle: stock 180.1 / P5 150.7 / P4 151.3 / rung B 149.9 /
  rung C 151.8 / stock 179.8 W (P5 ≤ 163 W gated, the rest recorded).
- Desktop-load screen: **0 of 936 windows flagged, 5.8–11.2 fps**.
- Back on stock at the end: memory 13801 MHz under load, 180 W.

## Files

| file | what |
|---|---|
| `*_sweep.csv`, `*_sweep.json` | the 72 sweeps |
| `*_sweep_voltage.csv` | `tools/frequency-sweep/join_hwinfo_voltage.py`, joined by time; 936 points, none empty, at least 13 samples each |
| `power-samples.csv.gz` | `tools/power-probe/sample_power.py` at 20 Hz for the whole session, 445,145 rows, gzipped (45 MB raw): `unix`, `usage_w` (= `power.draw`), `average_w` (field 185), `instant_w` (field 186), `energy_mj` (the counter), and NVML's own timestamps |
| `rerun15-inputs.json` | the scorers' evidence map, paths relative to here |
| `wrapper/` | each sweep's wrapper result, desktop-load check and GPU-users-at-start record |
| `witnesses/` | per arm: the live profile store copied before the arm, mVolt+ status, witness record |
| `session.log` | the runner's log |
| raw HWiNFO logs | gitignored, `data/HWiNFO-Data/5060ti-session19-20261007/` |

Every power figure here is the card's own telemetry; none is a shunt, so nothing here says which
reading is right. N=1 chip, one session, one suite per arm; the twelve workloads are repeated
outcomes on it.
