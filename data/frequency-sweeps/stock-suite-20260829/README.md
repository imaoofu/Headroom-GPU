# The 5060 Ti stock suite — 2026-08-29

Eight sweeps completing the extended workload suite at stock on the Zotac RTX 5060 Ti Twin Edge OC.
With the four in `../suite-pilot-20260829/` this is **all eleven suite workloads plus `gemm`** on one
card at one configuration — the leg of the paired cross-chip design that lives on hardware this
project owns.

All eight: **13 of 13 planned frequencies, locks held, clocks reset cleanly.** 104 frequency points.

## Conditions

| | |
|---|---|
| Card | Zotac RTX 5060 Ti Twin Edge OC 16 GB, driver 610.88 |
| Configuration | **STOCK** — verified 13801 MHz memory under load, 180 W default limit |
| Precision | fp32, TF32 **off** |
| Baseline at preflight | encoder 0%, decoder 0%, GPU 4% |
| Grid | 13 points, `-MinFrequencyPercent 40`, targets 1237–3090 MHz |
| Iteration counts | `../../../tools/frequency-sweep/SUITE-ITERATIONS.md` |

**The four pilot workloads were collected under looser conditions** — see
`../suite-pilot-20260829/README.md`. Their counts were calibrated at a 7% baseline and the machine
was under remote control. Encoder and decoder were verified at 0% throughout, so the contamination
class §5.4.4 identified is excluded, but the two batches are not identical in provenance and a
comparison that leans on sub-percent differences between them should not be made.

## `gemm` here closes a standing gap

`20260829-145752_5060ti-stock-gemm-1237grid` exists for a second reason. `CLAUDE.md` recorded:

> *"`gemm` gets nothing measurable from the memory overclock, ±1%" cannot be checked clean. The
> clean memory-only `gemm` run is on the 1237–3090 grid and the clean stock `gemm` run is on the
> 465–3090 floor15 grid, which share only their top point.*

This is that missing sweep.

**The result first written here has been RETRACTED the same day.** Against the clean memory-only
runs of 2026-08-22 this sweep gave −1.50%, negative at all 13 targets, and that was written up as
the ±1% claim failing. **It does not fail.** A memory-only sweep collected ninety minutes later in
this same session gives **−0.05%**, and the identical configuration measured today against
2026-08-22 differs by **+1.47%** — cross-session drift that accounts for the whole apparent effect.
See `../memonly-gemm-20260829/README.md`. The original claim stands and the open item is closed in
the direction it was written.

## What the suite shows

Each workload's own efficiency optimum, from its own curve:

| workload | FLOP/byte | eff-optimum | efficiency gain | **performance cost** | power saved |
|---|---|---|---|---|---|
| `copy` | 0 | 1537 MHz | 51.3% | 9.2% | 40.0% |
| `reduce` | 0.25 | 1845 MHz | 37.2% | 4.0% | 30.0% |
| `softmax` | 0.62 | 1537 MHz | 61.5% | 4.7% | 41.0% |
| `layernorm` | 1.00 | 1537 MHz | 51.0% | 12.9% | 42.3% |
| `bgemm32` | 5.33 | 1537 MHz | 74.0% | 5.4% | 45.7% |
| `bgemm64` | 10.67 | 1537 MHz | 77.0% | 4.5% | 46.0% |
| `bgemm128` | 21.33 | 1695 MHz | 34.9% | 31.3% | 49.1% |
| `bgemm256` | 42.67 | 1537 MHz | 39.5% | 41.9% | 58.4% |
| `bgemm1024` | 170.67 | 1537 MHz | 61.0% | 44.0% | 65.2% |
| `attention` | 256 | 1537 MHz | 53.7% | 45.9% | 64.8% |
| `conv` | 288 | 1537 MHz | 75.6% | 44.9% | 68.6% |
| `gemm` | 1365 | 1389 MHz | 55.6% | 47.8% | 66.5% |

**The `attention` row was CORRECTED on 2026-08-30.** It read 55.6% / 46.3% / 65.5%; its own
CSV gives **53.7% / 45.9% / 64.8%**. A transcription error, not a computation one - the other
eleven rows agree with their CSVs to within rounding, checked at the same time. It was found by
collecting a replicate and noticing that the recomputed r1 value disagreed with the table rather
than with r2.

The gain, cost and power columns are now pinned by `5.5-suite-row-*` in `claims_consumer.py`, so
this class of error fails the audit from here. Only the FLOP/byte column had been pinned before,
earlier the same day, and this row is what the rest of the table cost for being left out.

**The performance cost of the optimum tracks arithmetic intensity.** Everything at or below ~11
FLOP/byte gives up 4–13%; everything at or above ~21 gives up 31–48%. The transition sits between
`bgemm64` and `bgemm128`, which is where the roofline knee was measured independently at free boost.
That is §5.6.1's mechanism — a fixed policy is pinned by the most frequency-sensitive workload it
might meet — appearing on consumer silicon across a controlled axis rather than inferred from the
V100's −0.666 correlation.

**Ten of twelve optima land at 1537 MHz** on this grid. At 155 MHz spacing that is partly a
resolution artifact: re-swept at 51 MHz spacing the optima separate into five distinct values
(`../dense-grid-20260829/`). What survives the finer grid is the conclusion rather than the
positions — running everything at one frequency costs a mean 1.94%, because the curves are flat near
their peaks. That is the consumer analogue of the V100's 952 MHz serving 24 of 33, and it should be
cited from the dense grid rather than from this table.

## What CANNOT be computed from these sweeps, and why

A fixed-frequency-versus-per-workload comparison in the style of §5.6.1 **does not work on this
data**, and the reason is worth recording because it is not obvious.

`reportFixedVersusPerWorkload` returns nothing at floors of 85% and above. That is not a bug and not
a finding that no frequency is feasible. **The twelve sweeps share only five exact achieved
frequencies — 1537, 1695, 1845, 2002 and 2310 MHz.** Above 2310 each workload clamps to a different
sustained clock, because each draws different power at the same commanded target: `bgemm128` tops
out at 2565 MHz while `copy` reaches 2751. So the search for a shared fixed frequency is confined to
five points, the highest is 2310, and a compute-bound workload cannot hold 95% of its peak there.

**The underlying point: on consumer hardware the fixed-policy variable is the COMMANDED frequency,
not the achieved one.** A deployment sets `nvidia-smi -lgc 2625` and accepts whatever the card
sustains per workload. The V100 dataset has no clamping, so this distinction never arose and
§5.6.1's analysis inherits an assumption that does not transfer. §5.6.1 already noticed the symptom
on the two-workload consumer pair; twelve workloads make it structural rather than incidental.

Fixing it means analysing the consumer constrained case by commanded target with achieved clocks
reported alongside — not reusing the V100 code path unchanged. **Until that exists, do not quote a
consumer fixed-versus-per-workload gap from this directory.**
