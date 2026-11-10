# `suite-replicate-r7-20260906` — the controlled driver comparison, and it is a null

**Twelve sweeps, 13 of 13 frequencies each, 56 minutes, all complete.** RTX 5060 Ti at stock,
**driver 616.64**, 180 W enforced. Collected 2026-09-06.

**Dataset-grade.** Same suite, same 1236–3090 MHz 13-point grid, iteration counts unchanged since r1.

---

## Why this replicate exists

r1 ran on driver **610.88**, r2–r6 on **616.56**, and r7 on **616.64**. Everything else is held:
same card, same suite, same grid, same iteration counts, same 180 W limit, same machine, same
operator. **The driver is the only intended variable, which no earlier replicate pair can claim.**
§5.4.5 previously observed that the driver did not explain between-replicate variance; that was an
observation on an uncontrolled comparison. This is the controlled test.

**Provenance.** Verified quiet before launch — encoder 0%, decoder 0%, GPU 3–4% flat, 453 MiB used,
44 °C. That clears the **~5% protocol bar**, not merely the 10% tool guard. Stock confirmed by the
script's own probe: memory clock under load **13801 MHz** against an expected 13801. First replicate
at **schema 0.3.3**, so `baseline_util_pct` (3.0–3.4% across the twelve) is recorded per sweep
alongside `free_vram_mb_at_start`.

---

## The result: borderline and baseline-dependent, not a clean null

Mean efficiency gain across the twelve workloads:

| r1 (610.88) | r2 | r3 | r4 | r5 | r6 (616.56) | **r7 (616.64)** |
|---|---|---|---|---|---|---|
| 56.02% | 55.62% | 56.31% | 55.40% | 55.75% | 56.55% | **54.02%** |

r7 sits **1.38 points below the lowest of r2–r6**, and that looks like an effect until it is tested
against the right yardstick.

**Every workload-level test says noise:**

| test | result |
|---|---|
| workloads outside the r2–r6 range | **4 of 12** — the null expectation is exactly 4.0 |
| workloads whose shift exceeds their *own* r2–r6 spread | **1 of 12** (`bgemm128`, 1.49×) |
| median shift as a fraction of that workload's spread | **0.35×** |
| sign test, 8 of 12 below the r2–r6 mean | **two-tailed p = 0.388** |
| band-mean throughput | **−0.78%** (within the 0.65% n=6 spread) |
| band-mean power | **+0.16%** (within 1.03%) |

**THE FIRST VERSION OF THIS SECTION READ THOSE TESTS AS A CLEAN NULL. THAT WAS WRONG, AND THE
ERROR WAS USING AN UNDERPOWERED YARDSTICK.** Single-workload gains carry spreads of 3–10 points, so
almost nothing clears them; the sign test discards magnitude entirely. The **replicate mean** is far
more precise — **sd 0.485 points** across r2–r6 — and it is the right statistic for "did the headline
number move".

Against that yardstick r7 sits **3.93 sd below the r2–r6 mean**, outside the 95% prediction interval
for a new replicate. But the verdict **flips on which baseline replicates are used**, which is the
actual finding:

| baseline | 95% prediction interval | r7 = 54.02 |
|---|---|---|
| r2–r6, the matched-driver group | [54.45, 57.40] | **outside** |
| drop r5 (r4/r5 are one session) | [54.02, 57.92] | *inside* — exactly on the boundary |
| drop r4 instead | [54.47, 57.64] | **outside** |
| all six, incl. r1 on 610.88 | [54.73, 57.15] | **outside** |
| between-session only (r2, r3, r6) | [53.75, 58.57] | *inside* |

**This is neither a null nor an effect. It is underdetermined, and a result whose sign depends on
an arbitrary choice of baseline is not a result.** Report it that way.

**Do not report "the new driver costs 1.9 points of efficiency"** — one replicate cannot support it.
**And do not report "the driver has no effect"** — the first version of this file did, and the
replicate-mean test does not agree.

**What settles it:** the observed difference is 1.90 points against a within-driver sd of 0.485, an
effect size of 3.93. A **second** 616.64 replicate takes difference/SE to **4.69**, which is
decisive in either direction. If it lands near 54 the driver effect is real and is the most
interesting result since §5.7.3; if it lands near 56, r7 was an outlier session and the null stands
properly. Both are publishable. The present state is the one that is not.

## Where the shift comes from, mechanically

**Not from the reference point moving.** Highest-achieved clock shifted a mean of **−1.4 MHz** —
the anchor is stable, so this is not the artifact it could have been.

The shifts are in the *reference efficiency* — the top-of-grid point. On `layernorm` (+2.65%) and
`bgemm128` (+2.37%) the high-clock end got slightly more efficient, which shrinks the headroom there
is to recover and therefore the gain. That is an interpretable observation and it is the thing a
second 616.64 replicate should target.

## Limits

**n = 1 against n = 5**, an asymmetric comparison, and the reason the verdict above is
baseline-sensitive rather than merely uncertain. r7 is also a separate session, so the project's
established **~1.47% cross-session `gemm` drift** applies on top. A second replicate on 616.64 is
the cheapest measurement that would move this from "no effect demonstrated" toward either an effect
or a firmer null.

## A false refusal preceded this run, and the card was never at fault

The first launch attempt refused, reporting the memory clock under load as **810 MHz** — the *idle*
floor — against an expected 13801, which reads as "your overclock is still on." It was not. The
stock-check probe polled for **10 s from process launch**, and a cold `import torch` (plus CUDA init
and a multi-GB allocation) outran that window, so the probe never saw the card under load.

**This was the second time that defect was fixed.** `Collect.ps1` hit it on 2026-09-02 and was
widened to 24 s with the reasoning recorded beside it; this script was left at 10 s, and when its
*tolerance* was corrected on 2026-09-05 the *window* was not. Two probes of one quantity in two
files is how one gets fixed and the other does not.

Both are now 24 s, and a reading at the idle floor reports as `PROBE FAILED` rather than as a
configuration mismatch — telling an operator their card is wrong when it is fine sends them to check
hardware that was never the problem.

Nothing was collected and no clocks were locked by the refused attempt.

## Related

`../stock-suite-20260829/` (r1, 610.88), `../suite-replicate-r2-20260830/` through
`../suite-replicate-r6-20260905/` (616.56), `../driver-61664-probe-20260905/` (the single-workload
probe taken before this suite, not dataset-grade).
