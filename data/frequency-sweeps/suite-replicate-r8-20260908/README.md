# `suite-replicate-r8-20260908` — the second replicate on driver 616.64, and it retires r7's shift

**Twelve sweeps, 13 of 13 frequencies each, 56 minutes, all complete.** RTX 5060 Ti at stock,
**driver 616.64**, enforced 180 W. Collected 2026-09-08.

**Dataset-grade.** Same suite, same 1236–3090 MHz 13-point grid, iteration counts unchanged since
r1. Schema 0.3.3, so `baseline_util_pct` is recorded per sweep (3.0–3.6% across the twelve, inside
the ~5% protocol bar rather than merely the 10% tool guard). Encoder and decoder 0% throughout.

---

## Why this replicate exists

r7 was the first replicate on driver 616.64 and came in at **54.02%** mean efficiency gain, against
55.40–56.55% for r2–r6 on 616.56. Its own README called that **"borderline and baseline-dependent,
not a clean null"**: outside the 95% prediction interval computed on r2–r6, inside it if r5 was
dropped. One run could not settle it. r8 is the second.

---

## The result: r7 does not reproduce, and the driver comparison is a null

| r1 (610.88) | r2 | r3 | r4 | r5 | r6 (616.56) | r7 (616.64) | **r8 (616.64)** |
|---|---|---|---|---|---|---|---|
| 56.02% | 55.62% | 56.31% | 55.40% | 55.75% | 56.55% | 54.02% | **55.88%** |

**r8 lands inside the r2–r6 range**, between r4 (55.40) and r6 (56.55). It is an ordinary replicate.

### The decisive statistic is not the group means — it is the within-group spread

| group | driver | n | mean | sd | **range** |
|---|---|---|---|---|---|
| r2–r6 | 616.56 | 5 | 55.926 | 0.484 | **1.15** |
| r7, r8 | 616.64 | 2 | 54.950 | 1.315 | **1.86** |

**The two runs on the new driver disagree with each other by MORE than the five runs on the old
driver span in total.** No driver effect can be claimed from a pair whose internal spread exceeds
the entire reference range. Whatever separates r7 from r8 is present *within* 616.64, so it is not
a property of 616.64.

### The formal test agrees, and the earlier projection was wrong about which way

| quantity | value |
|---|---|
| difference (616.64 − 616.56) | **−0.976 points** |
| pooled sd | 0.730 |
| SE of the difference | 0.611 |
| **t** | **−1.597 on 5 df** |
| **p (two-sided)** | **0.171** |

**AN SE COMPUTED FROM THE BASELINE SPREAD ALONE GIVES −2.40 AND IS WRONG.** That was the first
figure this analysis produced. Using only r2–r6's sd ignores the new group's own scatter — which
here is nearly three times larger — and so understates the uncertainty in exactly the direction
that manufactures a result. The pooled estimate is the honest one.

**The pre-registered projection said difference/SE would reach 4.69 at n=2.** It assumed r8
would land near r7. It did not, and the projection is retired rather than quoted. A power
calculation conditioned on the outlier repeating is not a prediction; it is a description of one
branch.

---

## The per-workload view says the same thing

r8 against the r2–r6 range, workload by workload:

| | outside r2–r6 range |
|---|---|
| r7 | 4 of 12 |
| **r8** | **4 of 12** |

**The null expectation is 4.0** — with five reference runs, a sixth draw from the same distribution
falls outside the observed min–max about a third of the time. Both r7 and r8 hit it exactly. What
differs is *which* workloads: r7's excursions were `copy`, `layernorm`, `bgemm128` and `conv`, all
low; r8's are `softmax`, `bgemm32`, `attention` and `gemm`, in both directions. **Non-overlapping
sets of excursions in the same direction-free proportion is what noise looks like, not a driver.**

`gemm` is the largest single mover at 60.1% against a 52.8–57.0% reference range. It is one
workload in one run and no weight is placed on it here.

---

## The invariant worth more than the null

**The median optimum is 1537 MHz in all eight replicates** — r1 through r8, across three driver
versions and eleven days.

| r1 | r2 | r3 | r4 | r5 | r6 | r7 | r8 |
|---|---|---|---|---|---|---|---|
| 1537 | 1537 | 1537 | 1537 | 1537 | 1537 | 1537 | 1537 |

The mean gain moves by a point or two between sessions; **the location of the optimum does not move
at all.** That is the figure §5.5.7 rests on — the optimum sits at the top of this card's voltage
floor, which holds to 1552 MHz — and it is now backed by eight independent collections rather than
by the average of them.

This matters for the paper's structure: the headline quantity is a *frequency*, and the frequency
is the stable part. The efficiency gain attached to it carries session-to-session variance of
roughly ±1 point and should always be quoted with it.

---

## What this settles and what it does not

**Settles:** driver 616.64 does not measurably shift the efficiency gain relative to 616.56.
The honest statement is a null at n=2 per group, p = 0.171, **not** "the driver has no effect" —
this design could not detect a shift smaller than roughly 1.5 points.

**Settles:** r7 was a low run, not the first sight of a new level.

**Does not settle:** what made r7 low. Its baseline was 3.0–3.4%, encoder and decoder 0%, and it
passed every preflight gate r8 passed. The cause of ~1.9 points of between-session variation on a
verified-quiet machine remains unidentified, and this is the same unexplained residue recorded
against the wandering `membw` dip. **It is the project's largest open measurement question.**

**Does not settle:** r1's driver (610.88). One run, and its 56.02% is unremarkable.

---

## Provenance

- Collected 2026-09-08 08:43–09:39 by `tools/frequency-sweep/Invoke-SuiteReplicate.ps1`.
- Stock verified by the script's own probe **before** collecting: memory clock under load
  **13801 MHz** against 13801 expected. `clocks.max.memory` reads 14001 either way and cannot
  distinguish the two — see the 2026-08-30 mislabelling.
- Preflight: encoder 0%, decoder 0%, GPU 3% flat over ten samples, 15591 MiB free, 44 °C.
- Enforced power limit **180.00 W** on every sweep (`power_limit_enforced_w`). Note that
  `power_limit_w` reads 200.00 — that is the *settable* limit, not the enforced one, and reading
  the wrong field would make this look like a 200 W run.
- All twelve reached 13 of 13 planned frequencies. Clocks reset cleanly at the end.
- Analysis: `suiteRowFigures()` from `analysis/claims_consumer.py`, the same reader the paper uses.
