# Repaired curve, `membw` replicate - 2026-08-24

One sweep, and it is the one that dissolved the comparison it was meant to sharpen.

## What was measured

`20260824-214928_5060ti-repair-clean-membw-fine-r2_sweep.csv` - the repaired curve on the 10-point
1400-2100 MHz grid, same grid and timings as the memory-only ceiling, the split curve and the
2026-08-23 rebuilt-repair sweep.

Probed before starting, not assumed: core 2902.1 MHz mean at a locked 3090 target (2887 min,
2925 max) at 99% utilisation - the repair signature, against ~2977 for the split curve, ~2947 for
the original tune and ~2610 for stock. Peak `gemm` 17.23 TFLOP/s, below the split curve's 18.2,
which is 5.7.5's finding that the repair gives up the compute advantage. Memory 16301 MHz under
load. Encoder and decoder 0%.

## Why it exists

The repaired curve's -0.39% against the bandwidth ceiling was n=1, and three sweeps of the split
curve had just shown that a single `membw` sweep reads anywhere across a 0.6-point range.

## What it found

**+0.58% against the ceiling** - above it, where the first sweep was 0.39% below. The two repair
sweeps are 0.97 points apart, with no single-point dip to explain it: the second run is
systematically 0.2-1.8% higher at every one of the ten points.

Band-mean throughput across all six verified-quiet sweeps of the three memory-overclocked
configurations:

| configuration | sweeps | per sweep, GB/s | mean | within-configuration spread |
|---|---|---|---|---|
| memory-only (ceiling) | 1 | 368.8 | 368.8 | - |
| repaired curve | 2 | 367.5 / 371.1 | 369.3 | 0.98% |
| split curve | 3 | 368.5 / 366.2 / 367.0 | 367.2 | 0.61% |

**Between configurations: 0.56%. Within one configuration: up to 0.98%. Across all six: 1.32%.**

The configurations are separated by less than a single configuration varies between replicates.
No ranking among them is supported, and the succession of point estimates this comparison produced
over two days - "holds the repair", "-3.18%", "-0.11%", "-0.42%", "-0.47%", "agree to 0.03 points",
"agree to 0.08 points" - were all readings of noise at n=1 or n=2.

## What still holds

  - Against the FULLY TUNED profile the plateau is removed outright, +18.7% mean across the band.
    That is thirty times the noise floor established here and is not in question.
  - The repaired curve is dominated as a configuration to run - but on `gemm`, where eight sweeps
    give non-overlapping ranges. On `membw` the correct statement is that the split curve gives up
    nothing measurable, not that it matches the repair.
  - The memory-only card is still the right reference in principle. It is not a hard ceiling at
    this precision: the repair exceeds it in one of two sweeps, and the reference is itself n=1.

## The lesson

Adding replicates did not sharpen this comparison. It showed the comparison was never resolvable
at this n, and that every number previously quoted from it was a point estimate of noise. That is
a more useful outcome than a tighter figure would have been, and it is only visible because the
replicates were taken.
