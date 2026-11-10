# `curve-rebuild-20260823` — a SECOND INSTANCE of the repair design, not a re-measurement

**Three sweeps of a repaired V/F curve redrawn by hand on 2026-08-23.** Verified quiet — Instant
Replay off, encoder and decoder 0% over 4 samples before start. Driver 610.88, schema 0.3.1.

| file | workload | grid | points |
|---|---|---|---|
| `20260823-201224_…-gemm` | `gemm` | 1236–3090 MHz | 13 |
| `20260823-201715_…-membw` | `membw` | 1236–3090 MHz | 13 |
| `20260823-202324_…-membw-fine` | `membw` | 1400–2100 MHz fine | 10 |

**Dataset-grade.** The fine-grid run is `REPAIR_MEMBW_FINE` in `analysis/claims_consumer.py`.

---

## Read the directory name literally: REBUILT, not reproduced

**This curve is NOT bit-identical to the 2026-08-20 curve that §5.7.4 and §5.7.5 rest on.** That
profile was never saved. The operator redrew it from the design and deliberately altered it
slightly — same design and same qualitative shape (stock voltage slope restored below ~925 mV,
flattened region above it left intact, memory +2500), **different frequencies.**

The difference was **probed before starting, not assumed.** At a locked 3090 target:

| | this rebuild | the 2026-08-20 runs |
|---|---|---|
| `gemm` | 2906.1 MHz mean, 2910 max | 2887.1 and 2898.5 |
| `membw` | 2947.0 | 2909.9 |
| memory under load | 16301 MHz | (+2500 confirmed) |

**So this tests whether §5.7.4's findings belong to the MECHANISM or to one particular hand-drawn
curve.** That is a different and more useful question than re-running the same profile, and it is
why these are not filed as replicates of it. Do not pool them with the 08-20 data.

**All 2026-08-20/21 curve-fixed data predates the contamination finding of §5.4.4 and has no
clean counterpart.** That is the reason this run exists at all.

## Which grid to use, and why the 13-point run is nearly useless for comparison

The **10-point 1400–2100 MHz fine grid** run is directly comparable to the clean-protocol tuned
(`20260822-183112`) and split-curve (`20260822-161921`) runs, which sit on that grid.

The 13-point `membw` run taken twenty minutes earlier **shares no target frequency with them** and
can only be compared against contaminated-era data. It is kept for completeness; prefer the fine
grid for anything quantitative.

## Where this configuration now stands

Band-mean `membw`, against the clean memory-only reference in `../memonly-clean-20260823/`:

| configuration | sweeps | per sweep, GB/s | mean |
|---|---|---|---|
| memory-only (ceiling) | 1 | 368.8 | 368.8 |
| **repaired curve** | 2 | **367.5** (this dir) / 371.1 | **369.3** |
| split curve | 3 | 368.5 / 366.2 / 367.0 | 367.2 |

**This run reads −0.36% against the ceiling and its sibling reads +0.62%.** Between-configuration
spread is 0.56% and within-configuration spread reaches 0.98%, so **no ranking among these three on
`membw` is supported.** Read either single sweep alone and you get a different answer — which is
exactly how §5.7.6 went wrong twice.

**The repaired curve is nonetheless DOMINATED, and that rests on `gemm`, not on `membw`.** The split
curve matches its bandwidth and keeps the compute advantage the repair gives away, so there is no
operating point where the repair is the right choice. On `membw` the honest statement is **"gives up
nothing measurable"**, never "matches".

**The repair has never been stability-tested.** Only the split curve and the original tune have,
and both only for thirty minutes. Say "no failure observed", never "stable".

## Related

`../memonly-clean-20260823/` (the reference, measured 40 minutes later), `../repair-clean-20260824/`
(the second repair sweep), `../splitcurve-clean-20260824/`, `../membw-anomaly-20260819/` (the
mechanism this design repairs, and the full derivation).
