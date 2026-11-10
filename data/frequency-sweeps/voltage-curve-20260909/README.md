# `voltage-curve-20260909` — stock and the repair curve, voltage measured; two predictions hit and one was wrong

**Two `gemm` sweeps, 13 of 13 frequencies each, with HWiNFO core-voltage and crossbar telemetry
joined to both.** RTX 5060 Ti, driver 616.64, schema 0.3.3. Collected 2026-09-09, 22:32 and 22:43,
same session, one profile change between them.

**Dataset-grade.** Standard 1236–3090 MHz 13-point grid.

| file | configuration | Afterburner | enforced PL |
|---|---|---|---|
| `…stock-volt-gemm-p3` | **STOCK** | Profile 3 | **180 W** |
| `…repair-volt-gemm-p2` | the repaired / curve-fixed shape | Profile 2 | 200 W |

**Why these two.** `voltage-curve-20260908` measured voltage on the full tune and the split curve.
Stock and the repair had never been measured on the current profile set — every earlier statement of
**stock's** floor was borrowed from other data, and the 12-workload suite
`repair-suite-p2-20260909` had to *assume* the 0.720 V floor transfers to Profile 2. **This closes
both.** All four configurations now have directly measured voltage.

---

## Prediction 1 — the load floor and its extent. HIT, exactly, on both.

Registered in each sweep's `applied_settings` before it ran: *voltage flat at 0.720 V to roughly
1530 MHz, rising above it.*

| | floor voltage | holds to | next point reads |
|---|---|---|---|
| **stock** | **0.720 V** | **1537 MHz** | 0.755 V |
| **repair** | **0.720 V** | **1537 MHz** | 0.755 V |

**Four configurations now share one measured floor voltage** — stock, repair, split and full tune,
all 0.720 V — and the frequency at which each leaves it matches its decoded curve. That is what
makes a single number predictive across curves.

---

## Prediction 2 — the efficiency optimum at 1537 MHz. HIT on the repair, MISSED on stock.

| | optimum | verdict |
|---|---|---|
| **repair (P2)** | **1537 MHz** | yes |
| **stock (P3)** | **1388 MHz** | one grid step low |

**The miss cost 0.55%.** Stock's efficiency at 1388 MHz is 148.92 against 148.11 at 1537 — the two
candidate points are **0.55% apart**, and the runner-up is the predicted one.

**This is not a surprise and it is not a get-out.** `analysis/models/predict_from_curve.py` measures
the mechanism predictor's regret across 192 sweeps at **0.675% mean**, and `gemm`'s own mean regret
at **0.841%**. A 0.55% miss on a single `gemm` sweep is *exactly* the error budget that analysis
predicts. The optimum is a grid point on a curve that is flat by construction near its peak, so
adjacent points swap between runs.

**The stable statistic is the twelve-workload median, not one workload.** The same stock
configuration measured across twelve workloads earlier the same day (`stock-bracket-20260909`,
replicate `r9`) gave a median optimum of **1537 MHz**. **Do not quote a single-workload optimum as
though it were the configuration's optimum** — that is the error this file exists to record.

---

## Prediction 3 — "the repair's crossbar tracks the core". WRONG, and what replaced it is better.

The registered prediction said Profile 2 carries more voltage per clock in the mid band than any
other profile here, so **if the crossbar-starvation mechanism is right this should be the cleanest
tracking of the four configurations.**

**It is the worst.**

| | xbar/core span | spread |
|---|---|---|
| stock | 0.902 – 1.001 | **0.099** |
| **repair (P2)** | **0.751 – 1.007** | **0.257** |
| full tune, from §5.7 | 0.942 → 0.726 | 0.218 |

The repair's ratio collapses further than the full tune's. **The prediction was wrong because it
reasoned about the mid band and forgot the top.**

### What the data actually says

**In the mid band the prediction was right, and spectacularly so.** Stock and the repair share an
identical V/F curve below 800 mV, and their crossbars agree **to three decimals at seven of eight
points from 1237 to 2317 MHz**:

| | 1237 | 1395 | 1545 | 1702 | 1852 | 2010 | 2167 | 2317 |
|---|---|---|---|---|---|---|---|---|
| stock | 1.001 | 0.945 | 0.941 | 0.951 | 0.971 | 0.970 | 0.902 | 0.903 |
| repair | 1.007 | 0.945 | 0.941 | 0.951 | 0.971 | 0.970 | 0.902 | 0.903 |

**At the top it breaks, and the reason is visible in one row.** From target 2625 to 3090 the
repair's voltage is pinned at **0.920 V** while its core climbs **2610 → 2917 MHz, +307 MHz** — and
the crossbar sits **flat at 2190 MHz** throughout. Ratio 0.839 → 0.751.

**Stock never shows this**, not because its interconnect is better but because its *core* stops
climbing too: power-capped at 180 W, stock flatlines at 2588–2598 MHz across its top four targets
while the crossbar holds 2347. Both pinned together, so no divergence appears.

### The corrected, more general statement

> **The crossbar tracks the core while voltage is rising. Wherever voltage plateaus and the core
> keeps climbing, the crossbar stops.**

That subsumes what `CLAUDE.md` records from 2026-08-19/21. The mechanism there is described as a
property of *the flattened curve* — pin voltage low across a wide frequency range and the crossbar
starves. This shows it is not about flatness *low down* specifically: **the repair has a stock
voltage slope and starves its crossbar anyway, at the top, because its voltage plateaus at 0.920 V
while the card keeps boosting.** Same signature, different part of the curve, different cause for
the plateau — the full tune's is a chosen curve shape, the repair's is running out of curve.

**A wrong prediction produced this.** Had it tracked cleanly, the entry would have read as one more
confirmation and nothing would have been learned.

---

## Provenance

- **Two separate HWiNFO logs**, `hwinfo-20260909-p3-stock-gemm.csv` and
  `hwinfo-20260909-p2-repair-gemm.csv`. The first was stopped by the operator and the second started
  **before** the profile changed. **One log must never span a profile change**:
  `join_hwinfo_voltage.py` bins samples by core clock and would silently merge two configurations
  measured at the same frequency into one median.
- Join by `tools/frequency-sweep/join_hwinfo_voltage.py`, **binning by core clock, not timestamp** —
  the sweep CSV records durations rather than absolute times. `CLAUDE.md` describes this as a
  timestamp join and is wrong on that point.
- 82 of 368 (stock) and 81 of 172 (repair) samples survived the 30 W idle filter. The filter is
  load-bearing: HWiNFO polls through the settle gaps and an idle card sits at **boost** voltage, so
  keeping those samples manufactures a voltage-frequency slope out of nothing.
- **Identity, stock:** the power limit was observed falling **200 W → 180 W** before the sweep
  started, which no PL-111 profile can do; the runner aborts rather than sweeping if it does not.
  180 W is the card's factory default and matches every stock replicate r1–r9.
- **Identity, repair:** the power limit rose **180 W → 200 W** between the two sweeps, ruling out
  stock. **It does not rule out Profile 5** — P2 and P5 have identical curves below 800 mV, so
  the prescribed 2010 MHz fingerprint is blind here. The 12-workload suite settled it the same day:
  P2 draws **15.5% and 16.2% more** power than P5 at 2475 and 2625 MHz. This sweep is consistent —
  its 0.915/0.920 V at those points is far above the ~862 mV P5's curve gives.
- Preflight both runs: encoder 0%, decoder 0%, baseline 4.2% and 5.0%. Both sit at the edge of
  the ~5% the collection protocol asks for, higher than the 0–1.6% of the daytime suites. The
  effect of desktop contention is largest in the mid band, which is where the optimum sits — see
  §5.4.4. **Stock's one-grid-step miss above should be read with that in mind rather than treated as
  a clean null.**
- **NVML P0 graphics clock offset read back as 0 MHz and was never written.**
- Launch temperatures 35 °C and 36 °C, card settled; no cooldown between them beyond the ~70 s
  taken to stop one log, start another and apply the profile. **The repair sweep therefore
  started warmer in the heatsink than the stock sweep did**, which is not visible in
  `temperature.gpu`. Both configurations were measured on the same grid so this affects them
  equally at each point, but it is not a controlled cooldown.
- n=1 per configuration, one chip, one workload. `gemm` only.
- **Profile 2 has never been stability tested.** It is the gentlest curve of the five, which is
  an argument and not a test.
