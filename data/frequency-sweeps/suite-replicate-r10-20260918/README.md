<!-- dataset-grade: yes -->

# `suite-replicate-r10-20260918` — the first suite on driver 616.92, operator absent

**Twelve-workload stock suite, Zotac RTX 5060 Ti, driver 616.92, 180 W default, schema 0.3.3.**
Iteration counts from `SUITE-ITERATIONS.md`, unchanged, so this is directly comparable with r1–r9.

**Two things make this replicate worth more than another n:**

1. **The operator was absent for the entire run.** On 2026-09-18 this project measured that the
   operator's own machine use depressed throughput by **9.38% at every point** of a sweep whose
   preflight had passed cleanly minutes earlier. This is the first replicate deliberately collected
   with nobody touching the machine.
2. **First data on driver 616.92.** Every earlier replicate is 616.56 or older. `CLAUDE.md` records
   that a driver update landed between r1 and r2 and says to attribute nothing to it because it was
   confounded; this one is not.

## PROVENANCE: `copy` WAS NOT COLLECTED IN SEQUENCE

`copy` is workload 1 of 12 and **the baseline guard refused it**:

> `REFUSING TO START: GPU is already 21% busy before any workload of ours.`
> `Likely culprits on the GPU right now: msedgewebview2`

The preflight minutes earlier had read **4.2%**. An Edge WebView process started in between. The
other eleven workloads then ran clean across 49 minutes, and `copy` was re-run **~50 minutes after
its intended slot**, at a verified 3.7% baseline.

**So r10 is eleven-in-sequence plus one appended.** This project measures cross-session drift at
**~1.47% on `gemm`**, and `copy` carries an unknown of that order that the other eleven do not.
**Do not quote r10 as a single continuous set**, and prefer r1–r9 for any comparison that turns
on `copy` specifically.

**The guard behaving this way is the system working.** It caught, before collection, exactly the
class of contamination that was only found *after* collection on the fine-floor sweep the same day.
A passing preflight says nothing about what happens during a run.

## Sanity against the series

| | peak `gemm` TFLOP/s |
|---|---|
| r1–r9 | mean **16.227**, sd 0.372, range 15.908–17.055 |
| **r10** | **16.819** — second fastest of the ten |

**In family, and on the high side.** Contamination makes runs *slower*, so a high reading is
evidence against it — consistent with the operator-absent condition being the cleanest available.
It is one replicate; do not read 16.819 as a driver effect. r9 reached 17.055 on the old driver.

## Other conditions

- Baseline **4.2% mean / 5% max**, verified with `nvidia-smi pmon -c 5 -s u` rather than the
  aggregate — `pmon` names the process, the aggregate only says "something".
- Stock verified three ways: PL 180 W, all curve offsets zero, memory **13801** under load. The
  replicate script refuses to start otherwise.
- Encoder and decoder 0. NVIDIA overlay killed. MSI display 239 Hz, Dell 143 Hz on the iGPU.
- **Five points undershoot at the top** (2782 / 2932 / 3090 all landing ~2438 MHz at 174–177 W
  against a 180 W cap). That is the power limit and the tool flags it as expected at the top of the
  range — not a fault, and not usable as a max-boost figure.
- No HWiNFO log. **This replicate has no voltage or crossbar telemetry** and is a throughput and
  power measurement only.
