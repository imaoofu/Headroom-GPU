# Suite replicate r4 — 2026-09-04

The fourth complete collection of the twelve-workload suite at stock, and the fourth separate day.
All twelve reached **13 of 13** planned frequencies, every lock held, clocks reset. 56 minutes by
`tools/frequency-sweep/Invoke-SuiteReplicate.ps1`, the same as r3.

r1 is `../stock-suite-20260829/` plus `../suite-pilot-20260829/`; r2 `../suite-replicate-r2-20260830/`;
r3 `../suite-replicate-r3-20260902/`. **r5 is `../suite-replicate-r5-20260904/` and is NOT a fifth
day** — it was collected back-to-back with this run and exists to measure a different quantity. Its
README carries the joint analysis and is the one to read for what r4 and r5 together establish.

## Why a fourth

r3 gave the first interval. Four points test whether that interval was itself an artifact of three:
§5.4.5's claim is that **power, not throughput, dominates the noise**, and a decomposition resting
on three measurements deserved a fourth before the paper leaned on it.

r1 = 08-29, r2 = 08-30, r3 = 09-02, r4 = **09-04**. Two days after r3.

## Configuration, verified rather than declared

| | |
|---|---|
| Card | Zotac RTX 5060 Ti Twin Edge OC |
| Driver | 616.56 — matching r2 and r3; r1 is the odd one on 610.88 |
| Configuration | **STOCK** — 13801 MHz memory measured under load before collecting |
| Power limit | 180 W default, enforced |
| Baseline | encoder 0%, decoder 0%, GPU 4% flat over 8 samples / 24 s, VRAM 508 MiB, 38 °C |
| Grid | 13 points, `-MinFrequencyPercent 40`, targets 1237–3090 MHz |
| Iteration counts | unchanged from r1–r3, **deliberately not recalibrated** |

Every one of the twelve JSONs records `encoder_util_pct` 0 and `decoder_util_pct` 0.

**The counts were deliberately NOT recalibrated, and that decision is load-bearing.** A
recalibration on this same card earlier the same day returned counts **2 to 18% higher, mean about
8%**, at stock, with nothing about the card changed — calibration runs at whatever clock and load
the machine offers that minute. Using today's counts would have made r4 incomparable with r1–r3
while looking more correct.

Drifted points: 2–4 per sweep, **all undershoot, zero overshoot**, at the top of the range.

## Result — §5.4.5's decomposition holds at n = 4

| quantity | r1/r2/r3 (n=3) | r1–r4 (n=4) |
|---|---|---|
| throughput | 0.87% | **1.03%** |
| power | 2.07% | **2.44%** |
| efficiency | 2.08% | **2.49%** |
| reported gain | 4.34 points | **4.95 points** |

**The finding is the ordering, and it survives exactly.** Power reproduces 2.37× worse than
throughput at n=4 against 2.4× at n=3, and efficiency continues to track power rather than
throughput — 2.49% against 2.44%, with throughput less than half of either. §5.4.5's claim is not
an artifact of three measurements.

**The upward movement of every figure is NOT a finding, and must not be reported as one.** These
are ranges, and **a range grows monotonically with sample size by construction**. Four draws from an
unchanged distribution will span more than three of them. Nothing here says the card became noisier;
the comparison that carries information is the ordering between quantities, which is unchanged.

## Per-workload gain, four days

| workload | r1 | r2 | r3 | r4 | spread |
|---|---|---|---|---|---|
| `bgemm128` | 34.9% | 34.8% | 33.2% | 34.8% | **1.7** |
| `bgemm256` | 39.5% | 39.6% | 38.5% | 36.9% | 2.6 |
| `gemm` | 55.6% | 54.8% | 52.8% | 54.2% | 2.8 |
| `attention` | 53.7% | 56.2% | 53.8% | 56.8% | 3.1 |
| `conv` | 75.6% | 72.1% | 72.7% | 74.6% | 3.4 |
| `bgemm1024` | 61.0% | 60.3% | 56.8% | 59.5% | 4.1 |
| `copy` | 51.3% | 51.3% | 52.6% | 56.7% | 5.4 |
| `reduce` | 37.2% | 37.3% | 42.6% | 36.9% | 5.6 |
| `softmax` | 61.5% | 63.6% | 67.9% | 63.4% | 6.4 |
| `bgemm32` | 74.0% | 73.4% | 67.4% | 70.8% | 6.7 |
| `bgemm64` | 77.0% | 70.0% | 77.8% | 69.6% | 8.2 |
| `layernorm` | 51.0% | 53.8% | 59.8% | 50.5% | **9.3** |

Mean 4.95, median 4.79, max 9.26. Across all sixty sweeps the gains span **32% to 78%**, an order of
magnitude outside this spread — the headline effect is untouched, and only orderings between
workloads separated by less than about five points are unsupported.

## What this does NOT establish

- **Four measurements are not a distribution.** These are ranges, and the caution above about ranges
  growing with n cuts both ways: do not read n=4's figures as tighter evidence than n=3's, only as
  evidence that the *ordering* is stable.
- **One chip**, one configuration, one operator, one room.
- **The counts are frozen, which is a strength for comparability and a limitation for accuracy.**
  Every replicate measures ~9 s of work as calibrated on 2026-08-28, not as the card is today.
