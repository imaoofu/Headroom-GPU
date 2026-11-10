# `membw` on the 10-point grid, three SILENT replicates — 2026-09-22

**Stock Profile 3, 1402–2100 MHz, 10 points, default iterations, driver 616.92.** Grid and
workload match the seven historical runs so these are comparable to them, not merely to each
other. Operator absent, driving agent silent throughout.

## The question, open since 2026-08-24

CLAUDE.md, unchanged for six weeks:

> *"Every verified-quiet `membw` sweep on the 10-point grid has a worst point, and across the
> seven of them the deepest single-point departure runs −0.36%, −0.59%, −1.00%, −1.15%, −2.17%,
> −5.93%, −6.91%. All seven had encoder and decoder verified at 0%. **The variation survives the
> encoder guard, so it is something else, and its cause is unidentified.**"*

**This morning gave that signature a mechanism on `gemm`** — isolated points losing 8–11% while
neighbours are untouched, landing elsewhere each run, and **vanishing as the driving agent went
silent** (4 bad points → 1 → 0). See `../5060ti-finefloor-20260922/`.

## Result

| run | worst single-point departure below the local trend |
|---|---|
| r1 | **−0.43%** at 1627 MHz |
| r2 | **none** — no point falls below its neighbours |
| r3 | **−0.51%** at 1627 MHz |

Cross-replicate spread: **max 0.83%, mean 0.30%** across the ten points.

**The three largest historical dips — −2.17%, −5.93%, −6.91% — do not appear in ANY of three
silent replicates.** The worst seen today is −0.51%, below the smallest historical value bar one.

~~**So the large `membw` dips behave exactly like the `gemm` degradation characterised this
morning: they are activity-driven and they disappear under silence.**~~ **Struck 2026-09-22 — see
the correction under Part one.** That is the most likely
reading of six weeks of "cause unidentified".

## What this does NOT establish, and the limitation is real

**These three runs are on STOCK Profile 3. The seven historical runs were not** — they are
split-curve, repair and memory-only sweeps from the §5.7 configuration comparisons. **This is
therefore not a like-for-like replication of the runs whose dips are in question**, and a
configuration-dependent dip would not be excluded by it.

The inference rests on two things rather than one: the magnitude gap (−6.91% against −0.51%) and
the fact that the same signature was independently demonstrated to be activity-driven on `gemm`
this morning, on this card, under controlled A/B/C. **That is suggestive, not conclusive.**
**The clean test is three silent replicates on the split curve**, which would cost ~20 minutes
and has not been run.

**A small departure may be genuinely real.** Two of three replicates dip at **the same
frequency, 1627 MHz**, by −0.43% and −0.51%. That is consistent with the two smallest historical
values (−0.36%, −0.59%) and is **not** explained away by the activity mechanism, which lands
somewhere different each time. **A reproducible ~0.5% feature at 1627 MHz is a separate, smaller
question that these data raise rather than settle.**

## What the curve itself shows

Throughput saturates hard at the top: 387.6 / 388.3 / 388.8 / 388.8 GB/s at 1860, 1935, 2017 and
2084 MHz, agreeing across all three replicates to **0.01–0.08%**. The bandwidth ceiling is flat
and extremely reproducible — consistent with §3.3.1's *"ceiling near 281 GB/s"* being a property of
the path rather than of any one run, at the higher figure this stock 10-point grid reaches.

---

# The like-for-like test: three silent replicates on the SPLIT CURVE (P5)

The stock replicates above could not exclude a **configuration-dependent** dip, because the seven
historical runs were split-curve, repair and memory-only sweeps. P5 is the split curve — one of
the configurations those runs actually used. Same grid, same workload, agent silent.

Profile verified live: memory **13801 → 16301 → 13801** (+2500 applied, then reverted), 180 W.

| run | worst single-point departure below the local trend |
|---|---|
| P5 r1 | **−0.84%** at 1627 MHz |
| P5 r2 | **−0.85%** at 1627 MHz |
| P5 r3 | −0.15% at 1552 MHz |

Cross-replicate spread: max 1.35%, mean 0.57%.

## ~~Part one is settled: the LARGE dips are activity, not configuration~~

**NARROWED 2026-09-22 by an outside audit (`docs/gpt-findings/2026-09-22-5060ti-session-results-audit.md`).** What the six runs show is
that **the large dips are ABSENT from six silent runs on two configurations**. They do not show
**why**. No activity variable was ever recorded against the historical bad points. The historical
runs also differ from these in session, date and conditions, and on `gemm` the "activity" evidence
is confounded with warm-up (see `../5060ti-finefloor-20260922/`). **Correct form: absent under
silence; machine activity is the leading hypothesis, not a finding.** Settling it needs active and
silent intervals alternated on a warmed card at the same points.

**−2.17%, −5.93% and −6.91% appear in none of six silent replicates across two configurations.**
The worst seen anywhere today is −0.85%. The hole stated in the stock section above is closed:
the large historical dips are not a property of the split curve, and they are the same
activity-driven transient measured on `gemm` in `../5060ti-finefloor-20260922/`.

~~**Six weeks of "cause unidentified" resolves to machine activity during the run.**~~ **It
does not. Still unidentified, with a leading hypothesis.**

## Part two is NEW: ~~a reproducible dip at 1627 MHz~~ a STALL in the rise at 1627 MHz

**CORRECTED 2026-09-22. IT IS NOT A DIP: throughput NEVER FALLS at 1627.** In all six runs it
rises from 1552 to 1627 to 1702 MHz. The outside audit found this (`docs/gpt-findings/2026-09-22-5060ti-session-results-audit.md`).
"Dip" meant *below the straight line between its neighbours*, which is a chord residual. The audit
also showed that the **4 of 6 count depends on the trend rule**: a cubic trend makes all six
negative. **How it got in:** the residual was labelled from its sign, and nobody looked at the
raw throughputs.

**Something is still there, and the check that shows it was run here, not by the audit.**
Chord residuals at EVERY interior point, linear in achieved clock:

| run | 1470 | 1552 | **1627** | 1702 | 1785 | 1860 | 1935 | 2017 |
|---|---|---|---|---|---|---|---|---|
| stock r1 | +0.91 | +0.57 | **−0.43** | +0.65 | +0.26 | +0.24 | +0.02 | +0.06 |
| stock r2 | +0.78 | −0.11 | **+0.11** | +0.63 | +0.35 | +0.11 | +0.06 | +0.05 |
| stock r3 | +0.57 | +0.59 | **−0.51** | +0.60 | +0.51 | +0.06 | +0.05 | +0.08 |
| P5 r1 | +0.75 | +0.69 | **−0.84** | +0.32 | +0.61 | +0.16 | +0.31 | +0.53 |
| P5 r2 | +1.16 | +0.77 | **−0.85** | +0.63 | −0.09 | +0.64 | +0.15 | +0.63 |
| P5 r3 | +0.92 | −0.34 | **−0.12** | +0.78 | +0.23 | −0.02 | +0.52 | +0.55 |

**The curve is concave, so nearly every point sits ABOVE its chord.** 1627 is the one point below
it in **5 of 6 runs**, typically about 1–1.5 points under its neighbours' residuals. **So the rise
flattens between 1552 and 1627 and steepens again to 1702.** That is a change of slope, not a
loss of throughput. The fine grid is still what would show its shape. The original text follows.

**Four of six silent replicates, across two different configurations, dip at exactly 1627 MHz:**

| configuration | replicates dipping at 1627 | magnitude |
|---|---|---|
| stock P3 | 2 of 3 | −0.43%, −0.51% |
| **split curve P5** | **2 of 3** | **−0.84%, −0.85%** |

**The activity mechanism does not explain this.** That one lands on a *different* frequency each
run — it is transient by definition. **A feature that recurs at one frequency, on two
configurations, under verified silence, is a property of the card or the workload.**

**And it is larger on the split curve than on stock** (−0.85% against −0.51%), which is the
direction a memory-path effect would take, since P5 carries +2500 memory. **That is an
observation, not a mechanism — nothing here identifies a cause.**

**It is consistent with the two smallest historical values** (−0.36%, −0.59%), which suggests
the historical seven were a *mixture*: a small reproducible feature plus large activity noise
layered on top. Separating them is what six replicates bought.

**What would settle it:** a fine grid around 1627 MHz — the 10-point grid steps ~78 MHz there, so
the feature's width is entirely unresolved. It could be one narrow notch or a broad shallow bowl.
**Do not write it into the paper before that runs.** n=4 of 6 on a coarse grid is a lead.

## Note on the two configurations' levels

P5 reaches **451 GB/s** at the top against stock's **389** — the split curve's memory overclock,
behaving as the §5.7 record describes. The comparison above is deliberately *within* each
configuration (departure from its own local trend), never across them.
