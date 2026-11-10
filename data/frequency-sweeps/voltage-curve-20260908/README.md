# `voltage-curve-20260908` — the optimum sits at the end of the voltage floor, and the prediction was registered first

**Two `gemm` sweeps, 13 of 13 frequencies each, ~6 minutes apiece, with HWiNFO core-voltage and
crossbar-clock telemetry joined to both.** RTX 5060 Ti, driver 616.64, enforced 200 W, schema 0.3.3.
Collected 2026-09-08, 40 minutes apart, same session.

**Dataset-grade.** Standard 1236–3090 MHz 13-point grid.

| file | configuration | Afterburner |
|---|---|---|
| `…splitcurve-volt-gemm-p5` | split-region curve | Profile 5 |
| `…fulltune-volt-gemm-p4` | full tune, **plateau raised to 3030 earlier the same day** | Profile 4 |

**Profile 4 here is NOT the Profile 4 that `abba-20260908`'s `a1`/`a2` legs measured.** Its plateau
was raised 3015 → 3030 between the two runs. Both versions are snapshotted in
`data/afterburner-profiles/`, separated by sha256.

---

## The result

| | efficiency optimum | voltage floor | floor holds to | optimum = end of floor? |
|---|---|---|---|---|
| **P5 split** | **1537 MHz** | **0.720 V** | **1537 MHz** | yes |
| **P4 full tune** | **2002 MHz** | **0.720 V** | **2002 MHz** | yes |
| stock (§5.5.7, other data) | 1537 MHz | 0.720 V | 1552 MHz | within one grid step |

**Three configurations. The same floor voltage. Three different frequencies at which that floor
ends. And in every case the efficiency optimum is the last frequency on the floor.**

### The P4 prediction was registered before the measurement existed

The P5 sweep ran first and **observed** a 0.720 V floor holding through 1537 MHz. Profile 4's decoded
curve reaches ~2002 MHz at 720 mV. From those two inputs alone — nothing from the `abba-20260908`
result — the prediction written into P4's own `applied_settings` string, before it was run, was:

> voltage flat near 0.720 V up to roughly 2002 MHz and rising above it, with the efficiency optimum
> at 2002 MHz

**Both halves hit exactly.** The floor holds at 0.720 V through 2002 MHz and rises to 0.755 at the
next point; peak efficiency is at 2002 MHz. The prediction is in the sweep's JSON, timestamped
before the data.

**This is what `abba-20260908` could not claim.** That result was assembled after the fact from two
profiles that happened to exist. This one states the answer first and then measures it.

---

## The crossbar starvation, directly observed

Core voltage and crossbar clock at matched core frequency, both configurations, same workload, same
session:

| core MHz | P5 xbar | P4 xbar | P5 volts | P4 volts |
|---|---|---|---|---|
| 1236 | 1252 | 1245 | 0.720 | 0.720 |
| 1392 | 1320 | 1327 | 0.720 | 0.720 |
| **1537** | 1462 | **1350** | 0.720 | 0.720 |
| **1695** | 1620 | **1365** | 0.755 | **0.720** |
| **1845** | 1792 | **1365** | 0.795 | **0.720** |
| **2002** | 1942 | 1462 | 0.840 | **0.720** |
| 2462 | 1972 | 1950 | 0.845 | 0.840 |
| 2979 | 2190 | 2190 | 0.920 | 0.920 |

**P4's crossbar sits pinned at 1350–1365 MHz across exactly the span where its voltage is pinned at
0.720 V. P5's crossbar tracks the core over the same span, because P5's voltage is rising.** The two
converge above 2400 MHz, where both curves have left the floor.

`CLAUDE.md` records the mechanism from 2026-08-19/21 as "crossbar clock pinned near **1340 MHz**
instead of tracking the core", measured on `membw`. **This reproduces it on `gemm`, a different
workload, weeks later, to within 10–25 MHz** — and it does so on the configuration pair whose
arithmetic-intensity trend was measured the same day in `abba-20260908`.

That matters for how the paper is argued. The ρ = +0.685 correlation between the full tune's
advantage and arithmetic intensity was previously *explained* by reference to a `gemm`/`membw` pair
collected weeks earlier. The mechanism is now measured on the same configurations that produced the
correlation.

---

## The raw log was audited, not just the join's output

The join returns one median per bin and discards the rest — 123 of 203 samples on P5, 87 of 165 on
P4. Those medians were initially taken at face value. Going back to the raw HWiNFO log checks three
things the median hides.

**Voltage resolution is 5 mV, so 0.720 is a reported value and not a rounding artifact.** The log
contains 29 distinct voltages including 0.715, 0.720, 0.725 and 0.730. Adjacent-value gaps run
0.005–0.045 V. If the sensor quantised coarsely, "0.720 across five points" could have been several
different voltages collapsing together. It is not.

**On the floor, the samples are not near 0.720 — they are all exactly 0.720.**

| | floor points | samples | distinct values observed |
|---|---|---|---|
| P4 | 1236 → 2002 MHz (6 points) | **44** | `[0.720]` |
| P5 | 1236 → 1537 MHz (3 points) | **26** | `[0.720]` |

Zero within-bin variance across 70 loaded samples. Per-point counts are low (4–10), but on the floor
that does not weaken anything — there is no tighter measurement than every sample being identical.
The step off the floor is equally sharp: P5's next point reads `[0.755]` on all six of its samples.
Above the floor there is modest spread, 5–10 mV, e.g. `[0.785, 0.790, 0.795]` at 2310 MHz on P4.

**The extracts reproduce.** HWiNFO kept logging after each sweep — P4's log grew from 165 samples at
join time to 453 — and re-running the join on the larger log reproduces both committed extracts
byte-identically. The 30 W filter removes the added idle samples exactly as intended.

### "Voltage floor" is imprecise, and the log says what it should be

**0.720 V is a LOAD floor, not the card's minimum voltage.**

| samples | minimum voltage |
|---|---|
| loaded (>30 W) | **0.720 V** |
| idle (<30 W) | **0.650 V** |

The card demonstrably goes to 0.650 V — it does so at idle in this very log. What 0.720 V represents
is the lowest voltage the vendor will run *active* SMs at. Statements of the form "the card cannot go
below 0.720 V" are wrong; "the card will not run loaded below 0.720 V" is what the data supports.

---

## Why the voltage had to be observed rather than inferred

Every earlier statement of this result related a **decoded intended** curve to a **measured**
optimum, and borrowed the 0.720 V floor from a stock run on different data. Two things were assumed
and are now measured:

**Afterburner's curve is a request, not a guarantee.** This repository already has the
counterexample — requesting 0.925 V delivered 0.920 V under load, vdroop rather than a missing bin.
Here the requested and delivered low-end behaviour agree, but that is now a finding rather than an
assumption.

**The floor voltage was assumed not to move with the applied curve.** It does not: 0.720 V on stock,
on the split curve and on the full tune. Three configurations, one floor voltage. That is what makes
a single number predictive across curves.

**What still is not measured.** The floor's *extent* — the frequency at which it ends — is read
from the decoded profile, not observed independently. The mechanism predicts where the optimum lands
given that extent; it does not predict the extent itself.

---

## Provenance

- HWiNFO at 2 s polling. **Two separate logs**, `hwinfo-20260908-p5-splitcurve-gemm.csv` stopping at
  23:01:04 and `hwinfo-20260908-p4-fullcurve-gemm.csv` starting at 23:01:47, with no overlap.
  **One log must never span a profile change**: `join_hwinfo_voltage.py` bins samples by core
  clock and would silently merge two configurations measured at the same frequency into one median.
- Join by `tools/frequency-sweep/join_hwinfo_voltage.py`. It bins **by core clock, not timestamp** —
  the sweep CSV records durations rather than absolute times. `CLAUDE.md` describes this as a
  timestamp join and is wrong on that point.
- 80 of 203 (P5) and 78 of 165 (P4) samples survived the 30 W idle filter. The filter is load-bearing:
  HWiNFO polls through the settle gaps and an idle card sits at **boost** voltage, so keeping those
  samples manufactures a voltage-frequency slope out of nothing.
- **No pre-run fingerprint probe**, deliberately: a locked probe at 2010 MHz would inject samples
  into the same clock bin the join uses for that sweep point. Identity was established afterwards
  from each sweep's own data.
- **The plateau edit cost a discriminator.** P4 and P5 now share a 3030 plateau, so top achieved
  clock no longer separates them cleanly (2965.9 vs 2979.2). Power at a locked 2010 MHz is the
  remaining check: **77.5 W (P4) against 104.4 W (P5)**, and `memory_clock_max` = 16301 on all 26
  points rules out stock in both.
- **Power at 2010 MHz cannot separate the split curve from stock.** P5 read **104.4 W** here
  against stock's reference 104.0 W. On that check alone this run would have been called stock. It
  was the top achieved clock (2979 versus stock's ~2593) and the memory clock that settled it.
  **Neither check is sufficient alone.**
- Preflight both runs: encoder 0%, decoder 0%, GPU 4% flat over ten samples, ~15.4 GB free. P5
  launched at 44 °C, P4 at 36 °C.
- n=1 per configuration, one chip, one workload. The agreement is exact but the sample is small.
