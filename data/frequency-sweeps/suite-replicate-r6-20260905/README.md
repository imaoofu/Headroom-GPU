# `suite-replicate-r6-20260905` — sixth stock replicate of the twelve-workload suite

**Twelve sweeps, 13 of 13 frequencies each, 56 minutes, all complete.** RTX 5060 Ti at stock,
driver 616.56, power limit 180 W enforced (180 W default). Collected 2026-09-05, 13:33–14:24.

**Dataset-grade.** Same suite, same grid (1236–3090 MHz, 13 points), and **iteration counts
unchanged from r1–r5 and deliberately not recalibrated** — the fixed-work property that makes
duration a valid performance metric requires them held constant.

---

## Provenance

**Verified quiet before launch**, over eight samples across 24 s: encoder 0%, decoder 0%, GPU 3–4%
flat, 509 MiB VRAM used, 38 °C. One 14001 MHz memory P-state transient was seen at idle and is
normal — see the tolerance note below.

**Between-session replicate**, like r1–r4. r4/r5 remain the only within-session pair in the set;
do not quote r1–r6 as six independent sessions.

**Run deliberately BEFORE a pending driver update.** The operator intended to install a new
driver later the same day. r6 was collected first so it stays in the **616.56 group with r2–r5**
rather than straddling the change. **r1 is the only replicate on 610.88** and remains the odd one
out. A post-update r7 would be the first controlled test of the driver as a variable — everything
else held, only the driver changed.

## Schema mix: r6 is 0.3.2, r1–r5 are 0.3.1

This is the **first replicate at schema 0.3.2**, which added `free_vram_mb_at_start` and
`min_free_vram_mb_required`. r1–r5 carry no record of VRAM occupancy at all, so **they cannot be
audited retrospectively for a resident model** — the field did not exist when they were taken.

**It does not affect comparability of any throughput, power or efficiency figure.** The added fields
are preflight provenance, not measurement. What it does mean is that the replicate set is
schema-mixed, and any tool reading the whole set must tolerate the field being absent rather than
assume it. r6 recorded **15541–15548 MB free** across all twelve sweeps — clean throughout.

## Tolerance widened before this run, and it would have refused the card otherwise

`Invoke-SuiteReplicate.ps1` carried a 150 MHz memory-clock tolerance against an expected 13801.
The preflight for this run caught the card's **14001 MHz P-state transient**, which is a 200 MHz
departure and would have **refused a perfectly good card at stock.** `Collect.ps1` had been fixed
on 2026-09-05; this copy had not. Widened to 400 MHz — the same value, for the same measured
reason. Two tolerances for one quantity is how they drift apart.

---

## The result: r6 is an ordinary replicate, and its mean being the new maximum is NOT a finding

Mean efficiency gain across the twelve workloads:

| | r1 | r2 | r3 | r4 | r5 | **r6** |
|---|---|---|---|---|---|---|
| mean gain | 56.02% | 55.62% | 56.31% | 55.40% | 55.75% | **56.55%** |

r6 is the highest of the six and sits **outside the r1–r5 range** of 55.40–56.31%.

**Do not report that as an effect.** A range grows monotonically with sample size, and a sixth
sample is the maximum or minimum of six with probability 2/6. This project has caught itself on
exactly this trap before — see the `membw` dip entry in `CLAUDE.md`, where a bimodal split was read
into a continuous distribution of five samples.

**The arithmetic settles it.** Across twelve workloads, the number expected to fall outside a range
built from five prior samples is 12 × 1/3 = **4.0**. Observed: **4** (`reduce`, `gemm` high;
`bgemm128`, `conv` low). Dead on the null.

**Range growth is textbook:**

| n | mean | range |
|---|---|---|
| 2 | 55.82% | 0.40p |
| 3 | 55.98% | 0.69p |
| 4 | 55.84% | 0.91p |
| 5 | 55.82% | 0.91p |
| **6** | **55.94%** | **1.15p** |

**Rank stability is if anything better than typical.** The §5.5.4 control statistic:

| comparison | range | mean |
|---|---|---|
| r1–r5, all 10 pairs | +0.881 to +0.972 | +0.924 |
| **r6 against each of r1–r5** | +0.902 to +0.986 | **+0.940** |
| **r1–r6, all 15 pairs** | **+0.881 to +0.986** | **+0.929** |

r6's workload ordering agrees with the other five *more* closely than they agree among themselves.
Whatever r6 is, it is not an outlier.

## Reproducibility at n = 6

Band-mean spread across all six replicates, averaged over the twelve workloads:

| quantity | mean spread | worst workload |
|---|---|---|
| throughput | 0.65% | 1.02% |
| **power** | **1.03%** | 1.52% |

**Power still reproduces worse than throughput** — the direction §5.4.5 established, holding at n=6.

**These are NOT the 2.07% / 0.87% figures §5.4.5 quotes, and must not be compared to them.**
Those are computed over a different window; these are band means. The ratio here is 1.58× against
§5.4.5's 2.4×, and that difference is a difference of method, not of result. Matching the windows
would be needed to say anything about whether the ratio itself moved — `iterationsIn()` exists
because an aggregate whose window is implicit is a claim nobody can check.

## Sweep health

All twelve reached 13 of 13. Every drifted point is an **undershoot at the top of the grid**
(2 to 4 per sweep, none overshooting): the card cannot sustain 2782/2932/3090 MHz on these
workloads at stock and settles near 2750. `copy` at a 3090 target achieved **2753.4 MHz** against
r5's **2752.9** — half a megahertz apart, so this ceiling is a stable property of the configuration
and not a fault in this run. Temperatures 40–56 °C against an 88 °C ceiling; power 15–132 W against
the 180 W limit. No throttle events, no failed sweeps, clocks verified released afterwards.

## In the paper as of 2026-09-05 — §5.5.4 yes, §5.4.5 no

**§5.5.4 now uses all six.** Mean gain 55.8% → **55.9%**, and the within-card control went from ten
pairs to **fifteen**, +0.881 to +0.986, mean **+0.929**. Four numbers that had sat unpinned or
under-pinned are now claims, including the optimum-fraction figures — establishing that those had
not moved required reverse-engineering which denominator produced them, because the method had never
been written down.

**§5.4.5 deliberately stays at three.** It is a variance decomposition, and r4/r5 are a
within-session pair: pooling all six would mix the two components that section exists to separate.
Recomputing it at n = 6 means rebuilding the session-structure argument first, not just widening a
sample. The section now says so in place rather than leaving a reader to assume three is all there
is.

## Related

`../stock-suite-20260829/` (r1), `../suite-replicate-r2-20260830/`, `../suite-replicate-r3-20260902/`,
`../suite-replicate-r4-20260904/`, `../suite-replicate-r5-20260904/` (r4/r5 are the within-session
pair), `../rtx3070ti-suite-20260904/` (the cross-architecture comparison of §5.5.4).
