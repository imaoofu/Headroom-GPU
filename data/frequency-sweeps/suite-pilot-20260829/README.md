# Suite pilot — RTX 5060 Ti at stock, 2026-08-29

**THE HEADLINE BELOW IS STALE, AND THE MARKER MUST NOT BE ADDED. Corrected 2026-09-11.**

These four sweeps began as validation, which is what the text below describes. **They were then
completed into a full replicate.** The eight remaining workloads were collected the same day into
`../stock-suite-20260829/`, whose README says so directly: "With the four in
`../suite-pilot-20260829/` this is all eleven suite workloads plus `gemm` on one card at one
configuration." Together the two directories are **replicate r1** - `REPLICATES_5060[0]` in
`analysis/claims_consumer.py` - and around eight live claims average over it.

**So excluding these four would make the published count LESS accurate, not more.** The
`<!-- dataset-grade: no -->` marker is read in exactly one place, `headerSweepCount()`, and its only
effect is to subtract a directory from the dataset-grade total. Adding it here would drop that total
by four while the sweeps stayed in use - which is the opposite of what the marker is for.

**What IS true of r1, and why several claims exclude it.** The concerns listed below are
real and did not go away when the suite was completed: iteration counts calibrated at a 7% baseline
on a different day, and a remote-controlled machine during the run. r1 also sits on driver 610.88
while r2-r6 are on 616.56. That is why the drift and optimum claims use `REPLICATES_5060[1:]`.
**"Excluded from some analyses for stated reasons" is not the same as "not dataset-grade"**, and
conflating the two is what produced the headline below.


**WRITTEN AS VALIDATION, SUBSEQUENTLY COMPLETED INTO REPLICATE r1.** Read this before using any number here, and read the correction above first - the four sweeps are dataset-grade as part of r1, with the caveats in this section applying to r1 as a whole.

Four sweeps run to check that the extended workload suite works end to end in the sweep harness —
that the kernels run under a locked clock, that the units come out right, and that the throughputs
are physically possible. That is what these are for. They are **not** a designed collection and the
directory README convention requires saying so.

## What was provisional about them, and what still applies to r1

- **n = 1 per workload**, as written. **This reason did not survive**: every stock
  replicate is n = 1 per workload, and r1 through r6 together are what supply the error bars. It
  distinguished these sweeps only while they stood alone.
- **Iteration counts were calibrated at a 7% baseline**, above the protocol's ~5%, and on a
  different day from these sweeps. Counts are a setup constant so this is tolerable for a
  validation run and would not be for a collection.
- **Only four of the eleven suite workloads** when this was written. **Also no longer
  true**: the other eight were collected the same day into `../stock-suite-20260829/`.
- **The machine was being remote-controlled during the run.** Encoder and decoder were verified at
  0% across repeated samples and no NVENC-using remote tool was present, so the video-engine class
  of contamination is excluded — but it was not the undisturbed machine a collection wants.

## Conditions

| | |
|---|---|
| Card | RTX 5060 Ti 16 GB, driver 610.88 |
| Configuration | **STOCK** — verified at 13801 MHz memory under load, power limit 180 W default |
| Precision | fp32, TF32 **off** (the suite default since the conv finding) |
| Baseline | 4% GPU, encoder 0%, decoder 0%, Wallpaper Engine closed, no llama-server or ollama |
| Grid | 13 points, `-MinFrequencyPercent 40`, defaults otherwise |

Clocks reset cleanly after all four sweeps. Every sweep completed 13/13 points with locks held
within ~7 MHz and utilisation 96–99%.

## What it showed

All four ran, produced sane units, and landed inside the card's physical limits. Nothing exceeded
the memory bus or the fp32 ceiling.

| workload | declared FLOP/byte | peak | efficiency optimum | efficiency gain | performance cost | power saved |
|---|---|---|---|---|---|---|
| `copy` | 0 | 354.29 GB/s | 1537 MHz | 51.3% | **9.2%** | 40.0% |
| `bgemm128` | 21.3 | 7.69 TFLOP/s | 1695 MHz | 34.9% | 31.3% | 49.1% |
| `bgemm1024` | 170.7 | 9.20 TFLOP/s | 1537 MHz | 61.0% | 44.0% | 65.2% |
| `conv` | 288 | 5.75 TFLOP/s | 1537 MHz | 75.6% | **44.9%** | 68.6% |

**The performance cost of the unconstrained optimum ranges from 9.2% to 44.9% across the axis.**
That is §5.6.1's mechanism — a fixed policy is pinned by the most frequency-sensitive workload it
might meet — appearing on consumer hardware rather than on the V100. It is the reason the suite was
built, and it is the first sign the design does what it was meant to.

**Do not quote any of it.** n = 1, and see the caveats above.

## Two things to check before a real collection

1. **Three of four optima land on the same grid point, 1537 MHz.** That is either genuinely flat
   curves near the optimum — which is what the V100 showed and would be a finding — or 13 points
   across 40–100% being too coarse to separate them. A denser grid around 1400–1800 MHz would tell
   the two apart, and the answer changes how much §5.6.1's argument can lean on this data.
2. **`bgemm128` is the odd one out** at 1695 MHz with the smallest gain and it is also the workload
   the earlier characterisation put closest to the roofline knee. Whether that is real or noise
   needs the replicate this run does not have.
