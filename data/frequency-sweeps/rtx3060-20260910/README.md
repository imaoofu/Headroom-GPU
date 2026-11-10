# `rtx3060-20260910` — the mechanism holds on a second architecture, and the floor voltage is NOT a constant

**Fourteen sweeps on a third GPU: a `gemm`/`membw` pair and a full twelve-workload suite, 13 of 13
frequencies each, with HWiNFO core-voltage and crossbar telemetry.** ASUS Phoenix RTX 3060 12 GB,
driver **616.92**, enforced **170 W**, schema 0.3.3. Collected 2026-09-10 on the author's own machine, a shop build owned while on the bench
("an owner's machine" until 2026-09-28, written before the 2026-09-13 clarification), via
the USB collection kit.

**Dataset-grade.** Grid 840–2100 MHz, 13 points, `-MinFrequencyPercent 40`.

| folder | contents |
|---|---|
| `…_rtx3060-asfound` | `gemm` + `membw` at the **default** counts (120 / 1200) |
| `…_rtx3060-suite` | the twelve-workload suite at counts calibrated for this card |

The default `gemm`/`membw` counts are deliberate: they are what make this card's curve comparable
with the 5060 Ti's sweeps and the 3070 Ti's runs. Only the eleven suite workloads were recalibrated,
because a count is a property of a card and one calibrated elsewhere measures something else.

---

## The result: the rule transfers, the constant does not

| configuration | chip | arch | floor V | floor ends | optimum | |
|---|---|---|---|---|---|---|
| stock | 5060 Ti | Blackwell | **0.720** | 1537 | 1537 | yes |
| split (P5) | 5060 Ti | Blackwell | **0.720** | 1530 | 1537 | yes |
| repair (P2) | 5060 Ti | Blackwell | **0.720** | 1530 | 1537 | yes |
| full tune (P4) | 5060 Ti | Blackwell | **0.720** | 2002 | 2002 | yes |
| **stock** | **RTX 3060** | **Ampere** | **0.756** | **1260** | **1260** | yes |

**Two suite-concurrent voltage extracts were added 2026-09-11**, joined from
`hwinfo-rtx3060fullsuite.csv` — which covers the twelve-workload suite itself — against the suite's
`gemm` and `copy` sweeps. **Their agreement is an artifact and was briefly written up as
evidence — retracted 2026-09-12.** `join_hwinfo_voltage.py` bins by core clock with no time
filtering, one log covered the whole suite, and every workload visits the same targets, so the two
joins read **the same pooled samples**. Identical sample counts on all thirteen rows is the tell.

**What survives:** the floor value is correctly read, because voltage at a locked clock is a
property of the applied curve and pooling samples taken there reads it fine. And this is still the
only card whose floor and optimum come from **one session on one configuration** — the 5060 Ti and
3070 Ti read voltage on separate runs.

**The 3060's load floor is 0.756 V, not 0.720.** It holds flat across five grid points — 840, 945,
1050, 1155, 1260 MHz — and the next point reads **0.794 V**. The `gemm` efficiency optimum is
**1260 MHz**. The twelve-workload suite's median optimum is **1260 MHz**, with **nine of twelve
workloads landing on it individually.**

**A different floor voltage is the better outcome.** Had the 3060 also read 0.720 V, the honest
reading would have been that this is a driver constant — interesting but weak. It reads 0.756, so
the floor is a property of the silicon, **and the relationship holds anyway**. That is the
difference between finding a number on one card and finding a rule whose parameter you read off
per card.

**This RETIRES a caveat carried by `analysis/models/predict_from_curve.py` and
`analysis/models/README.md`** — that the 0.720 V floor "was measured on this card and is assumed to
transfer". **It does not transfer.** The rule does. Any application of the predictor to a new card
must measure that card's floor first; borrowing 0.720 V would have put this card's prediction at
~1530 MHz against a true optimum of 1260, a **270 MHz** error.

---

## The crossbar tracks the core more cleanly than anything measured so far

| configuration | xbar/core span | spread |
|---|---|---|
| **RTX 3060 stock** | **0.937 – 0.955** | **0.018** |
| 5060 Ti stock | 0.902 – 1.001 | 0.099 |
| 5060 Ti full tune (§5.7) | 0.942 → 0.726 | 0.218 |
| 5060 Ti repair (P2) | 0.751 – 1.007 | 0.257 |

The ratio never collapses, because the 3060's voltage **rises continuously** until the card
power-caps — at which point core and crossbar pin *together*. That is exactly the corrected
statement from `voltage-curve-20260909`:

> The crossbar tracks the core while voltage is rising. Wherever voltage plateaus and the core keeps
> climbing, the crossbar stops.

Here the core never keeps climbing past its voltage, so there is nothing to starve. **Confirmed on
new hardware, on an architecture the statement was not derived from.**

---

## The headroom gap, three chips

| card | arch | node | TDP | mean gain | median optimum |
|---|---|---|---|---|---|
| RTX 5060 Ti | Blackwell | 5 nm | 180 W | **56.99%** | 1537 MHz |
| **RTX 3060** | **Ampere** | **8 nm** | **170 W** | **42.21%** | **1260 MHz** |
| RTX 3070 Ti | Ampere | 8 nm | 290 W | 38.9% | — |

**Two Ampere parts at 38.9% and 42.2%, one Blackwell part at 57.0%.** That is suggestive and it
is **n=1 per chip**. Do not write an architecture trend from three points, and do not attribute the
spread to node, power budget or architecture — this data cannot separate them. What it supports is
the weaker and still useful claim: **a large stock-to-optimum gap is present on all three, and it is
not a peculiarity of the 5060 Ti.**

---

## The card is power-capped, so its factory-OC status is UNANSWERABLE

The operator was unsure whether this is the OC variant of the ASUS Phoenix. **It cannot be settled
from this data**, and that is recorded rather than guessed:

- `gemm` tops out at **1692 MHz** against a **1777 MHz** rated boost — 94.5% of rated. From the
  1785 MHz target upward the card flatlines at 1678–1691 MHz, **0.919 V, ~165 W against a 170 W
  limit.** It is power-bound, not clock-bound, so **the boost table was never reached and a factory
  OC would be invisible.**
- `membw` — a far lighter power load — reaches **1925 MHz**, above the rated 1777. That is ordinary
  GPU Boost headroom on a stock card and does not settle it either.
- Power limit reads **170 W enforced = 170 W default**, matching the reference TDP exactly. **That
  validates the spec source and says nothing about the clock BIOS** — the 5060 Ti also has
  enforced = default = reference TDP and still measures above its rated boost.

**The honest classification is "could not classify", not "stock".** Temperatures were reported
normal by the operator throughout, which rules out thermal throttling as the cause.

---

## A hypothesis that was wrong, recorded because the reasoning looked sound

The calibrated iteration counts showed `bgemm32` needing **525** iterations against the 5060 Ti's
**2673** — 17.1 ms per iteration against 3.37, a **5.1× gap**, where eight other workloads clustered
at 1.04–1.34×. `bgemm64` (2.14×) and `attention` (2.45×) looked similar. The machine runs a **Ryzen
5 5600X**, materially weaker in single-thread than the 5060 Ti machine's 9700X, and kernel-launch
overhead is single-thread CPU work. **The hypothesis was that these workloads were CPU-launch-bound
on this machine, which would make their durations measure the CPU and their optima meaningless.**

**It is wrong, and the sweep data says so.** Throughput scaling against clock, across the full grid:

| workload | throughput scaling |
|---|---|
| `bgemm32` | **1.00** |
| `bgemm64` | **1.00** |
| `gemm` | **1.00** |
| `bgemm1024` | 0.99 |
| `bgemm256` | 0.97 |
| `bgemm128` | 0.95 |
| `conv` | 0.91 |
| `attention` | 0.78 |
| `softmax` | 0.72 |
| `reduce` | 0.65 |
| `layernorm` | 0.64 |
| `copy` | 0.60 |

`bgemm32` is the **most** clock-sensitive workload in the suite, scaling perfectly linearly. A
launch-bound workload would be flat. The 5.1× is a genuine architectural difference in small batched
GEMM throughput, not CPU overhead.

**And the workloads that ARE clock-insensitive are exactly the bandwidth-bound ones** — `copy`,
`layernorm`, `reduce`, `softmax`. That is the arithmetic-intensity axis appearing unprompted on a
chip it was never fitted to.

**`conv` runs 1.6× FASTER per iteration on the 3060 than on the 5060 Ti** (36.7 ms against 59.6)
and is unexplained. A candidate is TF32: `SUITE-ITERATIONS.md` records that the suite runs fp32 with
TF32 off, "since it was found that PyTorch enables it for convolution and not for matmul", and that
gate may behave differently on Ampere. **Not investigated. Do not use `conv` for any cross-chip
comparison until it is.**

---

## Provenance

- **Collected with the USB kit**, `Collect.ps1` / `Calibrate-Suite.ps1`, on a machine the project
  does not own. **CORRECTED 2026-09-13: that classification was WRONG.** These are builds assembled to sell; nobody else owns them while they are on the bench and no third party's data is on them, so the invariant was never engaged. The stock-only design of THIS run still stands as what was done - but it was a choice, not a constraint, and recording it as a constraint blocked the cross-chip causal replication for weeks. See `docs/REGISTERED-PREDICTIONS.md` §4. **Nothing was applied and nothing was tuned** — stock only, which is the design for
  the cross-machine arm.
- **Two separate HWiNFO logs**, correctly split by the operator: `hwinfo-rtx3060.csv` covers the
  `gemm`/`membw` pair and `hwinfo-rtx3060fullsuite.csv` covers the suite. **The voltage result above
  is joined from the first**, which contains two workloads rather than thirteen — pooling many
  workloads into one clock bin blends their vdroop, since delivered voltage sags with current draw.
- Join by `tools/frequency-sweep/join_hwinfo_voltage.py`, binning **by core clock, not timestamp**.
  996 of 1970 samples survived the 30 W idle filter; 61–165 samples per grid point, far more than
  the 4–10 of the 5060 Ti runs.
- **All 14 sweeps reached 13 of 13 frequencies with `bench_ok` true at every point.** Locks held
  everywhere below 1680 MHz; every miss is at 1680 MHz or above and every one is *below* target —
  the power cap, not a tooling fault. The optimum at 1260 MHz sits well inside the
  perfectly-locked region.
- **Memory is stock.** Across all 156 suite rows `memory_clock_min_mhz` takes only 810 (idle) and
  7301; maxima are 7301 and 7501. No offset.
- **Driver 616.92 against the 5060 Ti's 616.64.** A different driver version, recorded because
  nothing here controls for it.
- Host: AMD Ryzen 5 5600X, 6C/12T, 15.9 GB RAM, Windows 11 Pro 26200.
- `machine-info.txt` records `measured_memory_clock_under_load_mhz : 405`, which is an **idle**
  reading — no `-ExpectedMemoryClockMhz` was passed, so nothing compared it. The per-point memory
  columns in the sweep CSVs are the reliable figures and are quoted above.
- **`applied_settings` was left empty on the `asfound` pair.** Nothing was applied, so it hides
  no configuration, but the string is normally where that is asserted. The label and this README
  carry it instead.
- **n=1 suite on one chip.** Every figure here is a single sample; the 5060 Ti needed nine stock
  replicates before its own mean was trustworthy to ±1 point.
