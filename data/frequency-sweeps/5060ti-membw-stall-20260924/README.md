# RTX 5060 Ti — what is at 1627 MHz on `membw`? (worklist 4n, EXPLORATORY)

**No prediction was registered.** This is a description, and is reported as one.

`docs/GPU-WORKLIST-5060TI.md` 4n: in 5 of 6 silent runs of `5060ti-membw-silent-20260922`, 1627 MHz
was the one point **below the line between its neighbours**, so the rise "stalled" there. That grid
steps ~78 MHz, so the stall's width was unknown.

**The runs:**
- `membw`, **1550–1710 MHz, 13 points** (~13 MHz apart), ascending, default iterations;
- driver 616.92, HWiNFO at 0.50 s, operator away, the Claude app minimized;
- order: stock P3, split curve P5, P5, P3.

Each profile was verified before its sweep: memory under load 13801 / 16301 MHz and power limit
180 / 200 W. Run by `tools/hwinfo-logging/experiments/Run-Queue-20260924.ps1`; log in
`queue-runner.log`. All four wrapper exits were 0.

## What it shows: a staircase, and it lines up with the crossbar clock

`membw` throughput in this range **does not rise smoothly with core clock.** It stays flat across pairs
or triples of adjacent clocks and steps up between them. The treads fall at **the same achieved
clocks in all four runs, on stock and on P5 alike.** P5 sits ~25 GB/s higher throughout, from its
+2500 memory.

The crossbar clock, from the joined HWiNFO extracts (median of the samples inside each point's timed
window), steps in **~23–30 MHz** increments across the range: 1462, 1492, 1522, 1545, 1575, 1605,
1635. **Every tread is one crossbar step:**

| achieved core (MHz) | crossbar (MHz) | P3 r1 / r2 (GB/s) | P5 r1 / r2 (GB/s) |
|---|---|---|---|
| 1545 | 1462 | 360.9 / 360.9 | 379.8 / 379.7 |
| 1560 | 1462 (P3 r1) or 1492 (others) | **361.5 / 364.0** | 386.5 / 386.4 |
| 1575 | 1492 | 365.3 / 365.3 | 386.5 / 386.6 |
| 1582, 1597 | 1522 | 368.6, 368.5 / 368.4, 368.6 | 392.1, 391.9 / 392.1, 392.1 |
| 1612, **1620** | **1545** | 371.3, 370.9 / 371.1, 371.1 | 396.1, 396.1 / 396.3, 396.1 |
| 1635, 1650, ~1660 | 1575 | 374.6, 374.5, 374.3 / 374.6, 374.3, 374.4 | 401.6, 401.4, 401.3 / 402.1, 402.0, 401.2 |
| 1680, 1687 | 1605 | 377.8, 377.6 / 377.9, 377.8 | 407.9, 407.9 / 407.7, 407.9 |
| 1702 | 1635 | 379.9 / 380.1 | 412.5 / 412.3 |

- **The "1627 stall" is the last clock before a crossbar step.** Today, achieved 1612 and 1620 both
  run at crossbar 1545, and 1635 is already at 1575.

  The 2026-09-22 point (target 1635, **achieved 1627 in all six runs**) ran at crossbar **1545 in
  every run**. Its neighbours (1560, 1710) ran at 1470–1492 and 1635–1650. So its crossbar sits
  **below their midpoint in 6 of 6 runs**, which is exactly what put its throughput below the line.
  **The dip scales with that residual**, recomputed here from the committed
  `5060ti-membw-silent-20260922` extracts:

  | run (2026-09-22) | crossbar vs neighbours' midpoint | throughput vs neighbours' midpoint |
  |---|---|---|
  | stock r1 / r3 | −18.5 / −18.5 MHz | −1.61 / −1.90 GB/s |
  | P5 r1 / r2 | −18.5 / −18.5 MHz | −3.35 / −3.41 GB/s |
  | P5 r3 | −8.0 MHz | −0.50 GB/s |
  | stock r2 | −11.0 MHz (its 1560 neighbour's crossbar sat a step lower, at 1470) | **+0.42 GB/s**, the one run not below the line |

  So the "5 of 6" was the crossbar's step structure sampled by a ~78 MHz grid, not something special
  at 1627.
- **The one place the two stock replicates disagree is explained by the same reading.** At 1567 MHz
  target, P3 r1's crossbar sat at 1462 and delivered 361.5 GB/s; P3 r2's sat at 1492 and delivered
  364.0.
- It is **not a notch.** Throughput never falls, and the steps continue on both sides of 1627.

**What it does NOT show, per `docs/gpt-findings/2026-09-18-xbar-causal-claim-adversarial-audit.md`:**
the crossbar was **observed, not controlled**, so this is a very tight **association** at ~15 MHz
resolution, **not** a demonstration that the crossbar causes the steps. A shared clock policy moving
the crossbar and some unobserved domain together would look the same. That the crossbar clock gates
bandwidth is also published (CLAUDE.md, the XBAR prior-art section). What is new here is only the
**step structure** measured at this resolution, and the fact that it explains the 1627 point.

One chip, two runs per configuration, one session, ascending only. The crossbar values are
per-window medians of a clock HWiNFO reports; a window can straddle a step, as 1672 MHz on P5 r2
(1567) suggests.

## Is 1627 in the historical data too? (GPT Job 12, done by Claude 2026-09-24)

**Yes, but only on curves that keep the stock slope below the floor, and never on the flattened
full tune.** That split is what the crossbar-step reading above implies: the flattened curve pins
the crossbar, so it has no step at 1627 to stall on. The reading was formed from 09-22 and 09-24
data before this check, so the history is an **out-of-sample consistency check, not a registered
test.**

**Method.** `python analysis/membw_chord_history.py`. It uses the 09-22 README's chord residual,
linear in achieved clock, at every interior point. It reproduces that README's 48-cell table
exactly before being applied to anything else. Only committed CSVs are read. **23** 5060 Ti `membw`
sweeps have an interior point within 15 MHz of 1627 achieved. Excluding the six 09-22 runs (the
original observation) and the four 4n runs above (a 7.5 MHz grid, where the point is 1612 and the
chord is a different quantity) leaves **13 historical sweeps, all on the same 10-point grid with
target 1635**:

| group | sweeps | below its chord at 1627 | residuals |
|---|---:|---:|---|
| **flattened full tune** (08-19 `oc`, 08-20 `oc-volt`, 08-22 `tuned-clean`) | 3 | **0** | +0.24, +0.81, +0.10 |
| **stock slope below the floor**: stock, memory-only, repair, split | 10 | **8** | see below |
| *for comparison: 09-22 silent, the original observation* | 6 | 5 | |

The ten, in date order:

| sweep | residual at 1627 | lowest in its sweep? | crossbar vs neighbours |
|---|---|---|---|
| 08-20 `stock-volt` | +0.45% | | −11.0 MHz |
| 08-20 `memonly-anomaly` | +0.18% | | no extract |
| 08-21 `splitcurve` | −1.21% | no (another point −8.31, a contaminated-era run) | −18.5 MHz |
| 08-22 `splitcurve-r2` | −0.64% | no (another point −5.08) | no extract |
| 08-23 `curverebuilt-fine` | −0.16% | | no extract |
| 08-23 `memonly-clean` | −0.59% | **yes** | no extract |
| 08-24 `splitcurve-clean` | −1.00% | **yes** | no extract |
| 08-24 `splitcurve-clean-r2` | −1.07% | no (another point −6.91) | no extract |
| 08-24 `splitcurve-clean-r3` | −1.02% | no (another point −1.73) | no extract |
| 08-24 `repair-clean-r2` | −1.15% | **yes** | no extract |

**The two that do not fit** are both from 2026-08-20: `stock-volt` (+0.45%) and `memonly-anomaly`
(+0.18%).
- `stock-volt`'s crossbar sits −11.0 MHz from its neighbours' midpoint. That is the same offset as
  09-22 stock r2, the one 09-22 run that was not below its chord (+0.11%).
- `memonly-anomaly` has no crossbar extract, so it cannot be checked the same way.

**Across all nine sweeps with a crossbar extract, historical and 09-22 together,** the residual
follows the crossbar offset:
- **below the chord in all 5** where the crossbar sits −18.5 MHz from its neighbours' midpoint;
- **above it in all 3** at −11.0 or +0.0 MHz;
- **−0.12%** in the ninth, at −8.0 MHz.

**This also names three of the seven "worst single-point departures" CLAUDE.md has called
unidentified since 2026-08-24.** Its list is −0.36, −0.59, −1.00, −1.15, −2.17, −5.93, −6.91%.
**−0.59, −1.00 and −1.15 are this point**, at 1627 MHz, in `memonly-clean`, `splitcurve-clean` and
`repair-clean-r2`, and they match to two decimals. **−6.91** is `splitcurve-clean-r2`'s point
elsewhere, not 1627. The other three values do not reproduce exactly under the chord rule, so
that list may have used a different trend in part; nothing is claimed about them.

**Limits.**
- One chip, and at most three sweeps per configuration.
- Three of the ten have a much worse point elsewhere (−5.08 to −8.31%), so their 1627 value sits
  inside larger noise. Two of those three are pre-guard runs from 08-21 and 08-22.
- The crossbar is **observed, not controlled** (above).
- A 15 MHz window and a 78 MHz grid cannot give the feature's shape; 4n's fine grid does.

## Files

`*_sweep.csv`, `*_sweep.json`, `*_sweep_voltage.csv` (with `crossbar`) for the four sweeps;
`queue-runner.log`. A refused launch at 09:09 (preflight, Claude app at 21% SM) left an empty
result folder on the collection machine. It held no data and is not imported.
