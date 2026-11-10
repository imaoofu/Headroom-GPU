# Sample-rate probe — 2026-09-04

**Does power's run-to-run noise come from averaging too few samples, or from the measurement
itself?** §5.4.5 measured power reproducing 2.4× worse than throughput and did not say why. This
answers the first half: **not from too few samples.**

Twenty runs, `gemm` at a single locked frequency, varying only the sampling interval.

## Why this design

The suite data cannot answer the question, because sample count is almost perfectly confounded with
frequency — low clocks run longer and collect more samples. Across the twelve-workload suite the
mean sample count falls monotonically from 29.4 at 1237 MHz to 16.9 at 3090 MHz, so any apparent
relationship between sample count and noise is equally well explained by frequency.

This breaks the confound by holding frequency, workload and iteration count fixed and moving only
`-SampleIntervalSeconds`. Sample count varies **6.2×** with nothing else changing.

| | |
|---|---|
| Card / driver | Zotac RTX 5060 Ti Twin Edge OC, 616.56, **STOCK** |
| Frequency | 1852 MHz, single point, **achieved clock spread 0.00% at every condition** |
| Workload | `gemm`, 120 iterations, unchanged throughout |
| Conditions | sample interval 0.25 / 0.5 / 1.0 / 2.0 s, **five repeats each** |
| Temperature | 49.0–50.1 °C across all conditions |

**Prediction registered before running:** if sampling drives the noise, the power spread falls as
the interval shrinks; if the measurement is the floor, it is flat. Flat was expected.

## Result 1 — more samples does not reduce the noise

| interval | samples | mean power | power sd | power range | throughput range |
|---|---|---|---|---|---|
| 0.25 s | 37.2 | 89.07 W | 1.54 W | 4.69% | **0.15%** |
| 0.5 s | 20.0 | 90.71 W | 1.32 W | 3.53% | **0.08%** |
| 1.0 s | 11.0 | 88.10 W | 0.93 W | 2.27% | **0.01%** |
| 2.0 s | 6.0 | 83.65 W | 1.58 W | 5.18% | **0.01%** |

**The averaging hypothesis is refuted.** Six-fold more samples does not tighten the power figure:
the standard deviation runs 1.54, 1.32, 0.93, 1.58 W with no relationship to sample count, and the
*most*-sampled condition is noisier than the least. Averaging more of this signal does not help.

**The prediction was not confirmed either.** "Flat" was expected; the spread is scattered
between 2.27% and 5.18% without trend. Refuting the sampling hypothesis is not the same as
confirming the alternative, and n = 5 per condition cannot distinguish scatter from structure.

**The controls are what make this decisive.** At one locked frequency the achieved clock
reproduces to **0.00%**, throughput to **0.01–0.15%**, and temperature sits within 1.1 °C — while
power moves by **2.3–5.2%**. With the workload, the clock and the thermal state all pinned, the
variation that remains is in the power measurement and nowhere else. That is §5.4.5's finding
isolated to a single operating point, and it is much starker there: throughput reproduces roughly
**an order of magnitude tighter** than power once frequency clamping and workload differences are
removed from both.

## Result 2 — a 2-second interval under-reports power by ~6%, and that was not predicted

| condition | readings (W) | mean |
|---|---|---|
| 0.25 s | 86.95 · 88.48 · 89.07 · 89.74 · 91.13 | 89.07 |
| 0.5 s | 88.93 · 89.77 · 91.33 · 91.41 · 92.13 | 90.71 |
| 1.0 s | 87.23 · 87.44 · 87.61 · 88.98 · 89.23 | 88.10 |
| **2.0 s** | **81.40 · 83.33 · 83.43 · 84.35 · 85.73** | **83.65** |

**Every 2.0 s reading is below every reading from the other three conditions.** Pooled, the shorter
intervals span 86.95–92.13 W and the 2.0 s condition spans 81.40–85.73 W — **the ranges do not
overlap.** That is a systematic ~5.6 W, ~6.3% under-read, not noise.

It is a threshold rather than a gradient: 0.25, 0.5 and 1.0 s are mutually indistinguishable and
only 2.0 s breaks away. With a ~9 s workload a 2 s interval yields about six samples, few enough
that the ramp-up and ramp-down edges carry disproportionate weight in the average.

**The project's default of 0.5 s sits safely inside the agreeing region.** No committed sweep is
affected. **Do not raise the interval to 2 s or beyond**, and never compare runs taken at different
intervals without checking this first.

## What this does NOT establish

- **It does not explain why the power figure is noisy** — only that averaging is not the reason and
  that the noise is not coming from the workload, the clock or the temperature. Naming the cause
  needs an external power meter, which is limitation 4 and remains outside this study.
- **n = 5 per condition, one frequency, one workload, one card, one sitting.** The 2 s offset is
  five readings against fifteen; clean separation at that size is suggestive, not settled.
- **The 2 s mechanism is a hypothesis.** Too few samples weighting the workload's edges is
  plausible and untested; nothing here measures the sample timing against the workload's own power
  profile.
