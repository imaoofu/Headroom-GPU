# `memonly-clean-20260823` — the clean memory-only reference

**Two sweeps, one configuration: core V/F curve reverted to STOCK, memory kept at +2500 MHz.**
Verified quiet — Instant Replay off, encoder and decoder 0% over 4 samples immediately before start.
Driver 610.88, schema 0.3.1.

| file | workload | grid | points |
|---|---|---|---|
| `20260823-205231_…-membw-fine` | `membw` | 1400–2100 MHz fine | 10 |
| `20260823-205606_…-gemm` | `gemm` | 1236–3090 MHz | 13 |

**Dataset-grade.** Both are read by live claims — the `membw` run is `CLEAN_CEILING_MEMBW` in
`analysis/claims_consumer.py`.

The configuration was **probed, not assumed**: at a locked 3090 target `gemm` read 2593.5 MHz mean,
the stock-curve signature (tuned ~2947, split ~2977, rebuilt repair ~2906), and memory read
16301 MHz under load against a 13801 stock reading, confirming the +2500 offset.

---

## Why it exists

§5.7.6 called memory-only the **ceiling** for `membw` and reported the split curve landing within
0.4% of it at seven of ten points. But that reference (`20260820-181307`) predated the
capture-software finding of §5.4.4, while the split-curve run it was compared against was clean
08-22 data. **Contaminated reference, clean subject.**

The tell was not a suspicion — it was an impossibility. On 2026-08-23 the rebuilt repaired curve,
measured clean on the same grid, **exceeded that "ceiling" at all ten points, by +1.80% to +5.15%.**
Nothing beats a ceiling, so the reference was suspect rather than the measurement. Re-measured here,
memory-only rose **+3.30% mean (+1.86% to +6.25%)**, matching §5.4.4's +4.22% mid-band figure.

## And then the correction these runs enabled was itself withdrawn

**2026-08-24.** The 08-23 fix cleaned *this* side and left the split curve on contaminated 08-22
data, producing an apparent −3.18% deficit and a rewritten "three-way trade" that is no longer in
the paper. Re-measured verified-quiet with replicates, band-mean `membw` throughput:

| configuration | sweeps | per sweep, GB/s | mean | within-config spread |
|---|---|---|---|---|
| memory-only (this dir) | 1 | 368.8 | **368.8** | — |
| repaired curve | 2 | 367.5 / 371.1 | **369.3** | 0.98% |
| split curve | 3 | 368.5 / 366.2 / 367.0 | **367.2** | 0.61% |

**Between configurations: 0.56%. Within one configuration: up to 0.98%.** The curves are closer
together than one curve is to itself. **No ranking among memory-only, repair and split on `membw`
is supported by this data.**

**The lesson is about the shape of the mistake, not the number.** Version one of that paragraph
compared contaminated against contaminated and was *right by accident*. Version two cleaned ONE
side and was wrong on evidence that already existed. **Correcting one half of a pair is not a
partial fix — it converts a symmetric error into an asymmetric one while looking like diligence.**
Before "correcting" any comparison, check the provenance of BOTH sides.

## What this reference is and is not

It is the right reference **in principle**, and on 2026-08-23 "nothing beats a ceiling" correctly
caught a contaminated one.

It is **n = 1**, and the repair exceeds it in one of that configuration's two sweeps (+0.62%).
At this precision it is **not a hard limit** and carries the same fragility as everything measured
against it. Do not treat a run landing above it as impossible.

Cross-session comparisons against it carry the **~1.47% `gemm` drift** this project measured on
one unchanged configuration across days — see `../memonly-gemm-20260829/README.md`.

## Related

`../curve-rebuild-20260823/` (the repair instance measured 40 minutes earlier, on the same grid),
`../repair-clean-20260824/`, `../splitcurve-clean-20260824/`, `../membw-anomaly-20260819/` (the
mechanism, and the contaminated 08-20 reference this replaced).
