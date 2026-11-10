# RTX 3070 Ti — twelve-workload suite, 2026-09-04

The first time the extended suite has run on a second architecture. Until now the 3070 Ti carried
only `gemm` and `membw`; §7 named running the identical suite on a second chip as the work that
would let this project ask **whether per-workload optima transfer across architectures.**

They do not.

## The run

All twelve reached **13 of 13** planned frequencies, zero overshoot, encoder and decoder **0% on
every sweep**. Collected in one sitting by the collection kit's `Collect.ps1`.

| | |
|---|---|
| Card | Gigabyte RTX 3070 Ti GAMING OC, **silent BIOS** |
| Driver | 610.88 (that machine's; the 5060 Ti is on 616.56) |
| Configuration | **STOCK** — peak memory 9265 MHz under load against the 9251 reference |
| Grid | 13 points, 852–2130 MHz, `-MinFrequencyPercent 40` |
| Counts | calibrated on this card 2026-09-04; `gemm` left at its default 120 |
| Peak | 280.4 W of a 320 W limit, 69 °C |

**The BIOS position is verified rather than declared.** `power_limit_w` 320.00 and
`max_clock_mhz` 2115 identify the silent position on their own; the OC position reads 350.00 and
2190 in every sweep of `../rtx3070ti-20260825/`. The operator's settings string does not mention
the BIOS, and does not need to.

**`Collect.ps1` has no stock check**, unlike `Invoke-SuiteReplicate.ps1`. Nothing refused this
run on configuration; the memory clock above was checked by hand afterwards. On a machine that is
not yours that is the gap to close.

## The result — workload ranking does not transfer across architectures

Efficiency gain per workload, 5060 Ti as the mean of its five stock replicates:

| workload | 5060 Ti | 3070 Ti | Δ | 5060 rank | 3070 rank |
|---|---|---|---|---|---|
| `bgemm64` | 74.1% | 25.3% | **−48.9** | 1 | **10** |
| `conv` | 73.7% | 27.8% | −45.9 | 2 | 8 |
| `bgemm32` | 70.9% | 39.8% | −31.1 | 3 | 7 |
| `softmax` | 64.3% | 50.2% | −14.2 | 4 | 4 |
| `bgemm1024` | 59.4% | 23.0% | −36.4 | 5 | **12** |
| `layernorm` | 55.2% | 56.4% | +1.3 | 6 | **1** |
| `gemm` | 54.6% | 25.1% | −29.5 | 7 | 11 |
| `attention` | 54.4% | 48.4% | −6.0 | 8 | 5 |
| `copy` | 52.7% | 51.0% | −1.8 | 9 | **2** |
| `reduce` | 38.5% | 50.3% | **+11.7** | 10 | **3** |
| `bgemm256` | 38.1% | 42.6% | +4.5 | 11 | 6 |
| `bgemm128` | 33.9% | 26.6% | −7.4 | 12 | 9 |

**Spearman rank correlation: −0.273.** The card's best workload is the other card's tenth; its
fifth is the other's last. Only `softmax` holds its position.

### The control is what makes this a finding

A rank ordering built from noisy numbers would scramble against anything, including itself. So the
same statistic was computed for the 5060 Ti **against its own five replicates**, all ten pairs:

| | rank correlation |
|---|---|
| 5060 Ti vs itself, ten replicate pairs | **+0.881 to +0.972**, mean **+0.924** |
| 5060 Ti vs 3070 Ti | **−0.273** |

**Within a card the ordering is highly reproducible; across architectures it is not, and the
cross-card figure sits far outside the within-card range.** That also settles the n = 1 worry about
the 3070 Ti: single 5060 Ti replicates rank consistently with one another at +0.88 to +0.97, so a
single replicate's ordering is a reliable thing to have.

### Two further differences

**Mean gain: 55.8% on the 5060 Ti against 38.9% on the 3070 Ti.** Both are enormous — an order of
magnitude outside the 4.95-point replicate noise — so the headline result reproduces on a second
architecture even though its magnitude does not.

**The optimum sits in a different part of each card's range**: median **49.7%** of maximum clock on
the 5060 Ti against **70.2%** on the 3070 Ti. Expressed in MHz the two are not comparable at all;
expressed as a fraction they still differ by twenty points.

## Why this matters to the argument

§5.6.1 shows that under a performance floor, **workload identity is worth most of the available
gain**. That holds within a card and is unaffected here. What this adds is a boundary on it: a
per-workload policy learned on one architecture **does not carry to another**. Anyone deploying
this would have to re-measure per chip generation, which is a cost the constrained result did not
previously have to account for.

It also sharpens the caution around the V100 comparison. If two consumer cards four years apart
disagree this completely on workload ordering, a 2017 datacenter part is not a safe source of
per-workload expectations for current consumer silicon — only of the *shape* of the frequency
response, which is what this paper actually takes from it.

## What this does NOT establish

- **One pair of architectures.** Ampere against Blackwell, one chip each. Nothing here says
  orderings never transfer, only that these two do not.
- **n = 1 on the 3070 Ti.** Mitigated by the within-card control above, not eliminated. Individual
  gains carry no interval; the *ranking* is the load-bearing quantity and it is the one shown to be
  reproducible.
- **Silent BIOS only.** The OC position draws ~23% more power at matched frequency (§5.5.1) and was
  not swept with the suite.
- **Different machines and different drivers** — 610.88 here against 616.56 on the 5060 Ti. The
  r1–r4 analysis found the driver did not explain between-replicate variance on the 5060 Ti, but
  that is not the same as showing it cannot matter across cards.
- **Nothing about tuned configurations.** All twelve sweeps are stock.
