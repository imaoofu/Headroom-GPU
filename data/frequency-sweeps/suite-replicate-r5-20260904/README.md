# Suite replicate r5 — 2026-09-04, and the within-versus-between split

**r5 is not a fifth day.** It was collected back-to-back with `../suite-replicate-r4-20260904/` on
the same afternoon, same power-on, no reboot and no driver reload between them. It exists to measure
a quantity the first four replicates structurally cannot: **within-session variance**, against the
**between-session** variance r1–r4 span across four separate days.

**Never quote r1–r5 as five independent replicates.** r4 and r5 are one session.

All twelve reached 13 of 13, every lock held, clocks reset, 56 minutes.

## Configuration

| | |
|---|---|
| Card / driver | Zotac RTX 5060 Ti Twin Edge OC, 616.56 |
| Configuration | **STOCK** — 13801 MHz memory verified under load |
| Baseline | encoder 0%, decoder 0%, GPU 4% flat over 8 samples / 24 s, VRAM 521 MiB |
| Iteration counts | unchanged from r1–r4 |

**The thermal state was matched rather than merely recorded.** r4 began at 38 °C; after it finished
the card was left to fall back to 38 °C — reached in 90 s — and held there over a further 24 s of
sampling before r5 launched. A hot start would have been a second changed variable in a pair whose
whole purpose is isolating one.

## The result: session separation does not measurably matter here

**A range grows with sample size by construction**, so the n=2 within-session pair cannot be
compared against the n=4 between-session range. Comparing them anyway would manufacture a difference
out of arithmetic. The comparison below is at **matched n=2** throughout.

| pair | separation | efficiency | gain |
|---|---|---|---|
| **r4/r5** | **same session** | **1.39%** | **3.24 pts** |
| r1/r2 | 1 day | 1.34% | 1.69 |
| r3/r4 | 2 days | 1.47% | **3.96** |
| r2/r3 | 3 days | 1.43% | 3.49 |
| r1/r3 | 4 days | 1.40% | 3.50 |
| r2/r4 | 5 days | 1.22% | **1.63** |
| r1/r4 | 6 days | 1.40% | 2.35 |

**The within-session pair sits inside the between-session range**, on both quantities: 3.24 points
against a between-session range of 1.63–3.96, and 1.39% efficiency against 1.22–1.47%. Two runs an
hour apart disagree by about as much as two runs six days apart.

**And separation does not accumulate.** Ordered by days apart the gain spreads run 1.69, 3.96, 3.49,
3.50, 1.63, 2.35 — no trend, with the *smallest* disagreement at five days and one of the largest at
two.

### What follows, and what does not

**The variance in these figures is dominated by measurement noise, not by session-to-session
drift.** That is a null, and it is the useful kind: it says the thing the project has been
controlling for is not, for this quantity, the thing that matters.

**It does not retract the ~1.47% cross-session drift measured on `gemm` throughput.** That
measurement stands and was made on a different quantity, on one workload, at peak. What this shows
is that it does not propagate into a *detectable* extra spread on efficiency gains across twelve
workloads — plausibly because efficiency inherits power's 2.44% noise (§5.4.5), which is large
enough to swamp it.

**r3's requirement that replicates be taken on different days was the right precaution and is
now testable rather than assumed.** Imposing it cost nothing and, absent this measurement, dropping
it would have been an untested assumption. The reasoning was correct when written; what changed is
that there is now evidence.

## The per-workload picture, which is where the real instability is

| workload | between (r1–r4) | within (r4/r5) |
|---|---|---|
| `layernorm` | 9.3p | **10.1p** |
| `bgemm64` | 8.2p | 6.7p |
| `attention` | 3.1p | 5.5p |
| `copy` | 5.4p | 4.8p |
| `bgemm128` | 1.7p | 2.8p |
| `bgemm32` | 6.7p | 2.0p |
| `softmax` | 6.4p | 1.8p |
| `reduce` | 5.6p | 1.6p |
| `gemm` | 2.8p | 1.2p |
| `conv` | 3.4p | 1.2p |
| `bgemm256` | 2.6p | 1.0p |
| `bgemm1024` | 4.1p | **0.0p** |

**`layernorm` moves 10.1 points between two runs an hour apart — more than it moves across four
separate days.** That cannot be session drift by construction. Whatever it is belongs to the
workload, and `layernorm` should not carry a quoted gain figure without it.

At the other end `bgemm1024` reproduces to **0.0 points** back-to-back and `bgemm256`, `conv` and
`gemm` to about one. **The workloads differ enormously in stability, and the suite mean hides it** —
the same lesson §5.4.5 recorded when it found the aggregate 0.76% figure was hiding a per-workload
range of 1.1 to 8.8.

## What this does NOT establish

- **One within-session pair is not a distribution.** The six between-session pairs also share
  replicates with one another, so they are not six independent samples either.
- **One chip, one operator, one room, one afternoon.** A machine that is power-cycled, moved, or
  used between runs might behave differently; nothing here tests that.
- **Nothing about `membw` or any tuned configuration.** All sixty sweeps are stock.
