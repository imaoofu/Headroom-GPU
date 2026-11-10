# Separating the two tuning knobs — 2026-08-19 / 2026-08-20

**The sweep this file used to skip now has its own section**, at the bottom:
[the split curve's `membw` sweep](#the-split-curves-membw-sweep--collected-data-with-two-defects).
Recorded as a gap 2026-09-11, closed 2026-09-12. Reading it turned up two defects that are
themselves worth more than the sweep is.

> **Folder name is narrower than its contents.** It began as a `membw` investigation and now
> also holds the `gemm` separation run. Kept as-is so existing links stay valid.

The tuned profile changes two independent things: a **memory overclock** (+2500) and a **core
V/F curve** pinned flat near 3000 MHz above ~925 mV. Every earlier result treated them as one
setting. These runs separate them, and the two knobs turn out to do opposite things to the two
workloads.

| | memory overclock | core V/F curve |
|---|---|---|
| `gemm` (compute-bound) | nothing, ±1% | **the whole win**: −18% to −26% power at matched clock, +12% clock ceiling |
| `membw` (bandwidth-bound) | **the whole win**: +3.6% to +16.1% over stock | **actively harmful**: up to −29.6% throughput in the 1560–1867 MHz band |

> **Corrected 2026-09-24** (the paper's copy of this table was pinned that day). **"Up to −29.6%"
> is memory-only's lead over tuned (385.7 against 297.5 GB/s at 1867 MHz), not a loss:** the flattened
> curve costs up to **22.9%** of memory-only's throughput. And **+3.6% to +16.1%** pairs stock at
> 1545/1702/1852/2010 MHz with memory-only at 1560/1710/1867/2025, a day apart (the table below shows
> the pairing). Against the stock sweep on the same 10-point grid, `…stock-volt-membw`, it is **+2.4% to
> +17.1%**.

Neither knob is good for both. That is the result.

---

# Part 1 — The membw plateau: reproduced, then explained

Two focused `membw` sweeps over the same band on the same card, to find out what caused the
1545–1852 MHz plateau recorded in `../oc-comparison-20260819/`.

**These two runs are 21.5 hours apart, not the same session.** Run 1 was 2026-08-19 20:42; run 2
was 2026-08-20 18:13. The gap is unavoidable — it takes a manual Afterburner change to switch
configurations — but it means ambient temperature, driver state and background load were not
held constant between them. See the caveats.

**Answer: the core V/F curve, not the memory overclock.** Reverting the core curve to stock
while keeping memory at +2500 removes the plateau entirely.

## Conditions common to both runs

- RTX 5060 Ti, 1400–2100 MHz, 10 points, 8 s settle, 20 s measure. Identical tool, identical
  targets, identical workload invocation.
- **No stability logger, no local LLM resident, no other GPU work.** The 18 GB
  `qwen3-coder:30b` model was explicitly unloaded first; it had 15.6 GB of the card's 16 GB
  held, which is what wedged an earlier attempt at preflight.
- `bench_ok` true and `lock_held` true at every point in both runs.

## Run 1 — full tuned profile (`*-oc-membw-anomaly`)

Memory +2500, core V/F curve pinned flat near 3000 MHz at and above ~925 mV, power limit 111%.

Run to test whether the plateau was an artifact of the stability logger that ran during the
original tuned sweep. **It was not.** The plateau reproduced to within 1% at every frequency
with nothing else touching the GPU:

| SM MHz | stock (14:33) | tuned run 1 (logger) | tuned run 2 (clean) | run 1 vs run 2 |
|---|---|---|---|---|
| ~1560 | 311.8 | 296.6 | 294.1 | −0.8% |
| ~1710 | 331.8 | 295.3 | 297.8 | +0.8% |
| ~1867 | 341.6 | 294.5 | 297.5 | +1.0% |
| ~2025 | 344.4 | 324.4 | 326.7 | +0.7% |

Five consecutive points from 1560 to 1867 MHz sat inside a 1.2% band while the core clock rose
20%.

This run also added memory-clock telemetry to the sweep tool, which had only ever recorded the
SM clock — the wrong clock for a bandwidth-bound workload. Memory held at exactly 16301 MHz at
every point, `min` equal to `max` equal to `avg`. **No downclock.**

## Run 2 — memory overclock only (`*-memonly-membw-anomaly`)

Memory still +2500; core V/F curve reverted to stock. The separation test.

| target | achieved SM | memory clock | GB/s | power | temp |
|---|---|---|---|---|---|
| 1402 | 1400.3 | 16301 | 291.8 | 51.4 | 42.1 |
| 1477 | 1470.0 | 16301 | 305.6 | 52.8 | 43.2 |
| 1560 | 1552.0 | 16301 | 323.0 | 54.1 | 44.1 |
| 1635 | 1627.0 | 16301 | 342.2 | 56.4 | 45.2 |
| 1710 | 1702.0 | 16301 | 360.1 | 60.6 | 46.4 |
| 1792 | 1785.0 | 16301 | 372.9 | 62.5 | 47.5 |
| 1867 | 1860.0 | 16301 | 385.7 | 64.7 | 48.4 |
| 1942 | 1935.0 | 16301 | 393.5 | 68.5 | 49.6 |
| 2025 | 2017.0 | 16301 | 399.9 | 70.1 | 50.7 |
| 2100 | 2085.4 | 16301 | 400.4 | 70.6 | 51.6 |

Monotone throughout. **No plateau anywhere.**

Two independent confirmations that the profile change did what was intended rather than
silently no-opping: memory still reads 16301 MHz under load, and power at matched clock rose
(56.0 W at ~1470 MHz against the tuned run's 52.8 W at ~1477 MHz) — which is what losing an
undervolt looks like.

## The size of the effect

| SM MHz | mem-OC only | full tuned | throughput | efficiency (GB/s/W) |
|---|---|---|---|---|
| 1477 | 305.6 | 283.6 | +7.8% | +7.6% |
| 1560 | 323.0 | 294.1 | +9.8% | +8.8% |
| 1635 | 342.2 | 296.6 | +15.4% | +11.7% |
| 1710 | 360.1 | 297.8 | +20.9% | +9.3% |
| 1792 | 372.9 | 297.6 | +25.3% | +11.0% |
| 1867 | 385.7 | 297.5 | **+29.6%** | **+12.1%** |
| 2025 | 399.9 | 326.7 | +22.4% | +1.7% |

The flattened curve is not a wash that happens to look odd on a graph. Across the plateau band
memory-only leads it by up to **29.6% in throughput and 12.1% in efficiency** on this workload (the curve costs up to 22.9% of memory-only's throughput; this said "costs up to 29.6% of throughput" until 2026-09-24). It costs more
throughput than it saves power.

Against stock, memory-overclock-only wins on both axes:

| stock MHz | stock GB/s | mem-OC GB/s | throughput | power | efficiency |
|---|---|---|---|---|---|
| 1545 → 1560 | 311.8 | 323.0 | +3.6% | +1.4% | +2.1% |
| 1702 → 1710 | 331.8 | 360.1 | +8.5% | +6.1% | +2.3% |
| 1852 → 1867 | 341.6 | 385.7 | +12.9% | +7.9% | +4.6% |
| 2010 → 2025 | 344.4 | 399.9 | +16.1% | +7.1% | +8.4% |

## What is established, and what is not

**Established:** the plateau is caused by the core V/F curve. It is not the stability logger
(reproduced within 1% without it), not a memory downclock (flat 16301, and it is flat in the
memory-only run too), and not throttling — throttle masks were decoded across every run and
show no power cap, no thermal slowdown, no hardware slowdown. Temperatures stayed at 42–52 °C.

**Not established:** the mechanism by which the curve does it. The working hypothesis is that
locking the SM clock into this band forces a voltage selection below the curve's flattened
region, where the custom and stock curves diverge most. This hardware exposes no voltage
readback, so that remains a hypothesis. What these runs pin down is *which knob* is
responsible, not *how*.

---

# Part 1b — The mechanism, measured: voltage and crossbar clock

Run 4 (`*-oc-volt-membw`, 2026-08-20 21:08) repeats the tuned `membw` sweep with HWiNFO logging
core voltage and interconnect clock alongside. NVML exposes neither - an exhaustive scan of field
IDs 1-259 returns 44 readable fields and no voltage at any scale - so this is the first run in the
project with a voltage number in it.

**A labelling error, corrected from the data rather than the label.** The run was launched with
`-Label memonly-volt` by mistake; the applied configuration was the full tuned profile. The files
were renamed and a `label_correction` field added to the session JSON. The configuration was
confirmed from the measurement, not from memory: throughput is flat at 292.8-302.3 GB/s across
1560-1867 MHz, the plateau signature of the tuned curve, where the memory-only configuration rises
323.0 to 385.7 over the same band.

| target | achieved | GB/s | core voltage | crossbar MHz | crossbar/core |
|---|---|---|---|---|---|
| 1402 | 1400.6 | 280.6 | 0.720 | 1320 | 0.942 |
| 1477 | 1474.8 | 284.2 | 0.720 | 1320 | 0.895 |
| 1560 | 1554.6 | 292.8 | 0.720 | 1342 | 0.863 |
| 1635 | 1628.7 | 299.0 | 0.720 | 1342 | 0.824 |
| 1710 | 1702.7 | 300.4 | 0.720 | 1342 | 0.788 |
| 1792 | 1785.3 | 301.7 | 0.720 | 1350 | 0.756 |
| 1867 | 1859.7 | 302.3 | 0.720 | 1350 | 0.726 |
| 1942 | 1935.0 | 314.9 | 0.720 | 1402 | 0.725 |
| 2025 | 2017.0 | 329.2 | 0.720 | 1470 | 0.729 |
| 2100 | 2092.0 | 345.0 | 0.740 | 1545 | 0.739 |

**Core voltage is 0.720 V at nine of ten points, across a 49% rise in core clock.** It is pinned.

**Throughput tracks the crossbar clock, not the core clock.**

| | plateau band, 1400 to 1860 MHz core | above it, 1860 to 2092 |
|---|---|---|
| core clock | **+32.8%** | +12.5% |
| crossbar clock | **+2.3%** | **+14.4%** |
| throughput | **+7.7%** | **+14.1%** |

Elasticity of throughput to core clock over the full range is **0.51**; to crossbar clock it is
**1.31**. Above the plateau a 14.4% crossbar increase buys a 14.1% throughput increase, very nearly
one for one.

This is the mechanism proposed earlier, now measured rather than inferred. The flattened V/F curve
holds core voltage constant; the crossbar clock - the SM-to-memory-controller interconnect - is tied
to voltage rather than to the locked core clock; so the path *to* memory stalls at ~1320-1350 MHz
while the core rises a third. DRAM was never the constraint, sitting at 16301 MHz throughout.

> **Corrected 2026-09-24; an outside audit found it on 2026-09-18.** *"Sitting at 16301 MHz
> throughout"* is not exact even for this tuned run, which logs **15858–16301 MHz** per point. And it
> is **false for the stock control below**, which logs **13477–13801 MHz**: stock memory, so the
> voltage/crossbar pair is **not memory-clock matched**. The two configurations also **diverge from
> 1477 MHz while both report 0.720 V** (−4.8% at 1477, −5.5% at 1560), so "measured rather than
> inferred" overstates what this data shows. It shows an association plus a repair that worked as
> predicted, not the crossbar isolated as the cause. The paper's §5.7.3 carries the full correction.

## The control, run: it is the curve

Run 5 (`*-stock-volt-membw`, 2026-08-20 21:16) repeats the sweep at **full stock** - no memory
overclock, no curve - with the same logging. The prediction was stated before the data landed: if
the mechanism holds, stock should show voltage *rising* with locked frequency and the crossbar
rising with it. If both were flat here too, the explanation would have failed.

| core | STOCK volts | STOCK xbar | xbar/core | GB/s | TUNED volts | TUNED xbar | xbar/core | GB/s |
|---|---|---|---|---|---|---|---|---|
| 1402 | 0.720 | 1335 | 0.953 | 283.8 | 0.720 | 1320 | 0.942 | 280.6 |
| 1477 | 0.720 | 1402 | 0.954 | 298.5 | 0.720 | 1320 | 0.895 | 284.2 |
| 1560 | 0.720 | 1470 | 0.947 | 309.7 | 0.720 | 1342 | 0.863 | 292.8 |
| 1635 | 0.740 | 1545 | 0.950 | 321.0 | 0.720 | 1342 | 0.824 | 299.0 |
| 1710 | 0.760 | 1642 | 0.965 | 329.4 | 0.720 | 1342 | 0.788 | 300.4 |
| 1792 | 0.780 | 1721 | 0.964 | 334.6 | 0.720 | 1350 | 0.756 | 301.7 |
| 1867 | 0.805 | 1815 | 0.976 | 338.8 | 0.720 | 1350 | 0.726 | 302.3 |
| 1942 | 0.820 | 1875 | 0.969 | 340.4 | 0.720 | 1402 | 0.725 | 314.9 |
| 2025 | 0.840 | 1942 | 0.963 | 342.1 | 0.720 | 1470 | 0.729 | 329.2 |
| 2100 | 0.840 | 1935 | 0.928 | 342.0 | 0.740 | 1545 | 0.739 | 345.0 |

**Voltage.** Stock swings +0.120 V across the range (0.720 to 0.840). Tuned swings +0.020 V. The
flattened curve does exactly what it was configured to do - it holds one voltage - and the
consequence is visible two columns to the right.

**The crossbar-to-core ratio is the cleanest single statistic in this study.** At stock it holds
between 0.928 and 0.976, a spread of 0.048: the interconnect tracks the core clock. Under the
flattened curve it collapses from 0.942 to 0.726, a spread of 0.218: the interconnect decouples from
the core and stops scaling.

**The two configurations agree exactly where their voltages agree.** At 1402 MHz both sit at
0.720 V, both report a crossbar near 1330 MHz, and both deliver ~282 GB/s - despite one card having
a memory overclock and the other not. They separate at 1635 MHz, which is the first point where
stock raises voltage to 0.740 and tuned does not. Divergence begins at the voltage divergence, not
before it.

> **THIS PARAGRAPH IS RETRACTED, 2026-09-24; an outside audit found it on 2026-09-18.** The
> divergence begins **two grid points before** the voltage divergence. At 1477 MHz both report
> 0.720 V while tuned delivers **4.8%** less, with crossbar 1320 against 1402. At 1560 MHz it is
> **5.5%** less, with 1342 against 1470, still at 0.720 V both. So reported voltage is not the state
> variable. Recompute from the two `_voltage.csv` extracts here. **This paragraph did record the
> memory mismatch** (*"one card having a memory overclock and the other not"*), which the paper then
> lost: it said both ran at 16301 MHz until the same date.

## The mechanism, stated as a chain

    flattened V/F curve
      -> core voltage pinned at 0.720 V regardless of locked frequency
      -> crossbar clock pinned near 1340 MHz instead of tracking the core
      -> the SM-to-memory-controller path stops scaling
      -> membw plateaus at ~300 GB/s while DRAM sits idle-capable at 16301 MHz

Every link is measured. The control shows all four moving together when the curve is removed.

**This also explains why the same curve helps `gemm` and hurts `membw`, which had looked like two
unrelated findings.** They are one intervention with one mechanism. `gemm` at ~1365 FLOP per byte
never touches the crossbar hard enough to care, so for it the pinned low voltage is pure benefit -
the 18 to 26% power reduction at matched clock. `membw` at 0.167 FLOP per byte lives on that path,
so the same pinned voltage is pure cost. **The undervolt's benefit and its harm are the same
mechanism seen from two workloads.**

## Caveats

- **HWiNFO was polling throughout.** That is the class of contention this project has already been
  burned by, so the throughput figures from this run are not clean measurements and are not quoted
  as such anywhere - the tuned throughput numbers of record remain those from runs 1 and 2. Voltage
  and crossbar readings are what this run is for.
- **Idle samples must be excluded or the result inverts.** HWiNFO samples every 2 s including the
  8 s settle gaps between points, and those gaps sit at boost voltage. Including them manufactures
  a voltage-frequency slope that does not exist. The join filters on GPU power above 30 W, leaving
  68 of 194 samples, 6-7 per point.
- **HWiNFO reports two GPU sensor blocks on this machine**, one carrying AMD-style names
  (`VDDCR_GFX`, `SoC Clock`, `VCN Clock`) that does not describe this card. The join resolves
  columns by picking the block whose clock actually moves, rather than by fixed index.
- Raw HWiNFO logs are gitignored: 300+ columns of unrelated host sensors. The distilled per-run
  extract is committed beside the sweep.

---

# Part 1c — The fix, predicted from the mechanism and confirmed

If the diagnosis is right, the repair follows from it: leave the flattened region above ~925 mV
alone, and restore the stock voltage slope below it. Then voltage rises with frequency again, the
crossbar scales again, and the high-clock gains — which live entirely in the flattened region —
should be untouched.

Run 6 (`*-curvefixed-membw`, 2026-08-20 21:53) tests that, on the full 13-point grid so both ends
are covered. Memory overclock retained. Four checks were stated before the run:

**1. Did the reshape take?** Yes. Voltage now rises where it was previously pinned:

| locked MHz | full tuned | curve-fixed | crossbar/core (fixed) |
|---|---|---|---|
| 1545 | 0.720 V | 0.720 V | 0.939 |
| 1702 | 0.720 V | **0.755 V** | 0.951 |
| 1852 | 0.720 V | **0.795 V** | 0.963 |
| 2010 | 0.720 V | **0.840 V** | 0.967 |

Voltage spread across the swept range: **curve-fixed 0.175 V, stock 0.120 V, full tuned 0.020 V.**
The crossbar-to-core ratio is back to 0.939–0.967, the stock-like band, from the tuned card's
collapse to 0.726.

**2. Was the memory overclock actually applied?** Yes — 15784–16301 MHz during the run, so the
top-end comparison is like for like.

**3. Is the plateau gone?** Yes, and it lands on the memory-only curve almost exactly:

| MHz | stock | full tuned | memory-only | **curve-fixed** |
|---|---|---|---|---|
| 1545 | 311.8 | 296.6 | 323.0 | **320.3** |
| 1702 | 331.8 | 295.3 | 360.1 | **355.7** |
| 1852 | 341.6 | 294.5 | 385.7 | **383.2** |
| 2010 | 344.4 | 324.4 | 399.9 | **400.2** |

Against the full tuned profile that is **+8.0% at 1545, +20.4% at 1702, +30.1% at 1852.**

**4. Did the top end survive?** Yes. Peak **411.8 GB/s at 2910 MHz achieved**, against full tuned's
414.3 at 2916 and stock's 352.2 at 2753. That is **−0.6% against the tuned peak** — inside
run-to-run noise, and with HWiNFO polling throughout this run and not the tuned one, so if anything
it is understated.

## The result

| | stock | full tuned | curve-fixed |
|---|---|---|---|
| peak `membw` | 352.2 | 414.3 | **411.8** |
| 1852 MHz `membw` | 341.6 | 294.5 | **383.2** |
| efficiency at 2932 MHz | 4.03 | 5.03 | **5.19** |
| power at 2932 MHz | 87.5 W | 82.4 W | **79.4 W** |

**For `membw`, the curve-fixed profile dominates the fully tuned one at every point on the grid**,
and is more efficient than both alternatives across almost the whole range. The defect is gone and
nothing was traded away for it.

This is the strongest evidence in the study that the mechanism is understood rather than merely
described: the repair was derived from the diagnosis, its outcome was stated in advance, and it
behaved as predicted at both ends of the range.

## The cost, predicted in advance and then measured

The prediction, written before the run: the 18–26% matched-frequency power reduction of Part 2 came
from the tuned card sitting at 0.720 V where stock sits at 0.805–0.885, and curve-fixed restores
roughly stock voltage in exactly that band (0.795 at 1852, 0.840 at 2010, 0.885 at 2317), so it
should also restore roughly stock power — which is what the memory-only run did, reproducing stock
power to within 3%. **The honest expectation was that curve-fixed gives up `gemm`'s
matched-frequency power advantage.**

Runs 7 and 8 (`*-curvefixed-gemm`, 22:02, and `*-curvefixed2-gemm`, 22:14) tested it.

**Run 7 is discarded at one point.** Under an 1852 MHz target the card ran at 2854.6 MHz and 151.6 W
— an overshoot of **+1002.6 MHz**, the cap never applied at all. That is the failure mode the sweep
tool's comments describe, where something outside `nvidia-smi` owns the V/F curve. The tool flagged
it. Run 8 is the clean one and everything below comes from it.

**The prediction holds.** Matched-clock power is back to stock:

| locked | stock | tuned | tuned Δ | curve-fixed | fixed Δ |
|---|---|---|---|---|---|
| 1852 | 86.4 W | 70.7 W | **−18.1%** | 87.8 W | +1.7% |
| 2010 | 103.3 W | 76.0 W | **−26.4%** | 103.5 W | +0.2% |
| 2167 | 110.5 W | 88.6 W | **−19.9%** | 112.5 W | +1.8% |
| 2317 | 123.4 W | 101.0 W | **−18.1%** | 124.9 W | +1.2% |

Within 2% of stock everywhere. Same signature as memory-only, same reason.

**And the loss is wider than the four matched points.** On efficiency the original tuned curve beats
curve-fixed from 1545 all the way through 2782 MHz:

| locked | tuned TFLOP/W | curve-fixed | tuned advantage |
|---|---|---|---|
| 1237 | 0.1266 | 0.1284 | −1.4% |
| 1395 | 0.1354 | 0.1365 | −0.8% |
| 1545 | 0.1415 | 0.1375 | +2.9% |
| 1702 | 0.1476 | 0.1344 | +9.8% |
| 1852 | 0.1513 | 0.1242 | **+21.8%** |
| 2010 | 0.1533 | 0.1152 | **+33.1%** |
| 2167 | 0.1442 | 0.1123 | **+28.4%** |
| 2317 | 0.1361 | 0.1114 | +22.2% |
| 2475 | 0.1219 | 0.1079 | +13.0% |
| 2625 | 0.1193 | 0.1085 | +9.9% |
| 2782 | 0.1147 | 0.1089 | +5.4% |
| 2932 | 0.1057 | 0.1078 | −1.9% |
| 3090 | 0.1059 | 0.1075 | −1.4% |

Curve-fixed wins only at the two lowest targets and the two highest. The tuned curve owns the
middle, and the middle is where `gemm`'s efficiency optimum sits — 2010 MHz, which is the single
widest point of the gap.

**At peak the ranking flips, and quoting only that would be cherry-picking.** Curve-fixed reaches
16.82 TFLOP/s at 2898 MHz on 156.5 W; tuned reaches 17.61 at 2948 MHz on 166.3 W. That is 4.5% less
throughput for 5.9% less power, so 1.5% better efficiency — at exactly one point out of thirteen.
Both beat stock, which cannot hold anything above ~2590 MHz and peaks at 15.71.

## The result, both workloads together

| | `membw` | `gemm` |
|---|---|---|
| curve-fixed vs tuned | **wins at every grid point**, up to +30.1% | **loses across 1545–2782 MHz**, by up to 33.1% efficiency |
| curve-fixed vs stock | wins throughout | matched-clock power within 2%, +7.0% peak throughput |

**Neither configuration dominates.** The undervolt's benefit and its harm are one mechanism, so
removing the harm removed the benefit. That is the project's thesis one level up: not only is the
efficiency-optimal *frequency* workload-dependent, so is the efficiency-optimal *hardware
configuration*.

## Why curve-fixed caps at ~2898 MHz — a candidate, not a conclusion

Curve-fixed tops out 50 MHz below the tuned card, which was recorded as unexplained. The voltage
telemetry gives a plain candidate.

**Both curve variants measure 0.895 V** at every target from 2625 MHz upward — variant 1 on its
`membw` sweep (run 6) and variant 2 on its `gemm` sweep (run 8); run 7 was not voltage-logged, so
the two readings come from different workloads. They are identical to the millivolt even though
variant 2 was redrawn specifically to raise the top point by ~10 mV. The raise does not appear in
the telemetry at all, on either workload.

The tuned card's top voltage was never measured: HWiNFO was not running during its `gemm` sweep, and
both voltage-logged runs on that configuration cover only 1402–2100 MHz. The Afterburner editor
showed 0.925 V, which is a setting read off a screen rather than a measurement. If that is right,
curve-fixed is running **30 mV short at the top**, which is enough on its own to explain 50 MHz and
needs no inherent cost of the repair.

Two things favour that reading. `membw` under the same curve lost only 0.6% at peak, which does not
fit a repair-caps-the-top story. And no run of either configuration reports a hardware-slowdown,
thermal or power-brake bit anywhere; `SwPowerCap` appears intermittently on both, and stock reports
no throttle reason at all while still collapsing to ~2590 MHz. The ceiling is the curve, not the
card protecting itself.

**That sweep was run on 2026-08-21, and it refuted the hypothesis.**
`20260821-215215_5060ti-curvefixed925-gemm_sweep.csv` raises the top point to 0.925 V. The
ceiling did not rise — it fell, from 2898.5 MHz to 2876.6 MHz, 21.9 MHz the wrong way. Locking
the curve flat at 925 mV changed nothing further. HWiNFO shows 0.925 V requested delivering
0.920 V under ~170 W, which is ordinary vdroop rather than a missing voltage bin, so the raise
did reach the card and the card does not clock higher for it.

Peak throughput improved slightly, 16.82 → 16.90 TFLOP/s, narrowing the deficit against tuned's
17.61 from −4.5% to −4.0%. The frequency shortfall is 71.5 MHz, 2876.6 against 2948.1.

**So the deficit is real, reproduces, and is unexplained.** Voltage is eliminated by this sweep;
thermals, power limit and throttle state were eliminated earlier. It is still not used to argue
anything about the repair. The hypothesis above is kept rather than deleted — 0.895 V really was
identical to the millivolt on both curve variants, which is what made a failed-to-apply setting
the obvious reading.

## Caveats

- **HWiNFO polled throughout this run** and did not during the original tuned and stock sweeps, so
  cross-run throughput comparisons carry that asymmetry. It biases against curve-fixed, which
  strengthens rather than weakens the conclusion.
- **Sessions are separated by hours.** Same caveat as elsewhere in this folder.
- **n = 1 chip, one curve shape.** How much of the sub-925 mV slope can be given back before the
  crossbar starts starving is unmapped; only the two endpoints have been measured.

---

# Part 2 — gemm: the power finding survives, and belongs to the curve

`../oc-comparison-20260819/` reports that the tuned profile draws **18–26% less power than
stock at identical core clock** on `gemm`, and attributes the efficiency gain to that rather
than to the higher peak clock. That was measured with both knobs applied at once and had never
been separated.

Run 3 (`*-memonly-gemm`, 2026-08-20 18:32) uses the **full default 13-point grid**, the exact
target list both existing `gemm` sweeps used, so all three configurations compare at identical
targets rather than nearest neighbours.

## The matched-frequency comparison, re-tested

| MHz | tuned vs stock: thru / power / effic | mem-only vs stock: thru / power / effic |
|---|---|---|
| 1852 | −2.0% / **−18.1%** / +19.8% | +0.3% / **−0.6%** / +1.0% |
| 2010 | −2.3% / **−26.4%** / +32.7% | −0.7% / **−2.9%** / +2.2% |
| 2167 | +0.8% / **−19.9%** / +25.8% | −0.6% / **+0.9%** / −1.5% |
| 2317 | −1.2% / **−18.1%** / +20.7% | +0.0% / **−2.5%** / +2.6% |

**Memory-only reproduces stock power to within ±3%. The full tuned profile cuts it by 18–26%.**
The power reduction is therefore entirely the core V/F curve. The original finding survives
intact and its attribution was correct — the curve really is functioning as an undervolt.

Temperatures at these four points matched to within 0.6 °C between the mem-only and stock runs,
so this is not thermal.

Memory overclocking does nothing measurable for `gemm`, which is what a compute-bound workload
should do when only memory speed changes. That is a sanity check the experiment passes.

## The curve also raises the ceiling

At stock and at memory-only, `gemm` cannot hold the top three grid points — all of 2782, 2932
and 3090 MHz collapse to ~2590 MHz achieved and ~15.7 TFLOP/s. With the curve applied the card
holds 2775 / 2916 / 2948 MHz and reaches **17.61 TFLOP/s, +12.1%** against stock's own peak of
15.71 TFLOP/s at 2598 MHz. An earlier version of this line said +12.3%, which measured against
stock's LAST grid point (15.68 at 2588 MHz) rather than its best, without saying so.

So for `gemm` the curve is a pure win on both axes: less power at matched clock, and a higher
clock it can actually sustain.

## Why this matters beyond one card

The project's central claim is that the efficiency-optimal *frequency* is workload-dependent.
This is the same claim one level up: the efficiency-optimal *hardware configuration* is
workload-dependent too, and by a large margin. A single "tuned" profile chosen on `gemm` costs
a bandwidth-bound workload up to 22.9% of its throughput (a 29.6% gap to memory-only; "29.6% of its throughput" until 2026-09-24); a profile chosen on `membw` gives up
a 18–26% power reduction on compute-bound work.

## Caveats

- **The `memory_clock_min_mhz` column reads 7001 at four points in run 2** (1560, 1635, 1710,
  1867) against an average near 15850. That is the idle memory P-state caught by a telemetry
  sample landing between benchmark iterations — the same class of artifact as the `GpuIdle`
  throttle bit, which also appears at frequencies performing perfectly well. The evidence that
  it is an artifact and not a real mid-work downclock: the four points with clean
  `min = max = 16301` (1792, 1942, 2025, 2100) sit exactly on the same smooth trend as the four
  with 7001 minima. A genuine downclock during timed work would show as a throughput dip, and
  there is none.
- **Neither leg is contemporaneous, and this is the weakest point of the study.** Run 1 was
  2026-08-19 20:42, run 2 was 2026-08-20 18:13, and the stock leg was 2026-08-19 14:33. All
  three are separated by hours to a full day. Idle temperature was 40–42 °C at the start of
  each, which is the only cross-run control available, and no driver or system change is known
  to have occurred — but "not known to have occurred" is not the same as verified. The size of
  the effect (up to +29.6%) is far outside any plausible day-to-day drift, so the direction of
  the result is safe; the precise percentages are not. Proper interleaving would need the
  profile switched between every point, which Afterburner cannot be scripted to do here.
- **The gemm run has its own timing gap.** It ran 2026-08-20 18:32 against a stock leg from
  2026-08-19 14:28. Temperatures at the four matched-frequency comparison points agree to within
  0.6 °C, which is the relevant control, but the runs are a day apart.
- **Two gemm points outside the comparison band disagree by ~6%.** At 2475 and 2625 MHz the
  mem-only run drew 5.8% and 6.6% more power than stock, with only +1.2 and +2.1 °C to explain
  it. Neither point is part of the matched-frequency finding, but the gap is unexplained and is
  recorded rather than trimmed.
- **At the low end the mem-only gemm run started 4–6 °C warmer** than the stock run (46 °C
  against 41 °C at 1237 MHz), which accounts for its 1.4–3.6% higher power there. The four
  comparison points are unaffected.
- **n = 1 chip**, and one profile. Nothing here generalises to other cards or other curves.
- **Sequential, not interleaved.** Temperature rose 42 → 52 °C within each run. The drift is
  similar in both so it does not obviously bias the comparison, but it is not controlled.


---

# The split curve's `membw` sweep — collected data with two defects

`20260821-222416_5060ti-splitcurve-membw`, plus a paired voltage extract. A genuine 10-point
1402–2100 MHz `membw` sweep of the **split curve**, taken 2026-08-21, a day after every other run
above. Driver 610.88, 200 W limit, 10 of 10 frequencies measured.

**It is collected data, not scaffolding.** But it cannot carry a comparison, for two reasons that
only appear on reading its JSON.

## Defect 1: `applied_settings` is null

The one field nothing else can reconstruct is empty. What "split curve" means here rests entirely
on `session_label: "5060ti-splitcurve-membw"` — a string the operator typed, with no probe of the
card behind it.

**Compare the stability runs of 2026-08-23, two days later, which probe the configuration before
starting and record the reading**: core clock at a locked 3090 target, memory clock under load, and
what each value distinguishes. That habit exists because of gaps like this one. This sweep predates
it.

**Null does NOT mean stock.** The sweep tool's own docstring says so. Treat the configuration as
*claimed* rather than *verified*.

## Defect 2: schema 0.1.0, so no video-engine telemetry

There is no encoder or decoder column, so the quiet-machine check cannot be applied retrospectively.
The run is dated 2026-08-21 — **the day before** §5.4.4 established that NVIDIA Instant Replay
depresses mid-band throughput by ~4.2% and multiplies run-to-run spread fivefold. Instant Replay was
almost certainly on.

## What it shows anyway

Against the two configurations it can be put beside, over all ten shared targets:

| | band-mean `membw` |
|---|---|
| full tuned | 303.1 GB/s |
| **split curve (this sweep)** | **351.4 GB/s** |
| memory-only | 357.5 GB/s |

**Against the fully tuned profile: +15.97% band-mean**, positive at all ten points, +3.0% to
+24.7%. That direction is far outside anything contamination of this size explains, and it agrees
with the rest of Part 2 — the split curve removes the plateau.

**Against memory-only it reads −1.70%, and that number should not be used.** It is
clean-against-contaminated in the wrong direction, one sweep per configuration, and §5.7.6 records
that no ranking among memory-only, repair and split on `membw` is supported at this n — the
configurations sit closer together than one configuration sits to itself.

## It also carries a textbook instance of the wandering dip

| target | 1792 | **1867** | 1942 |
|---|---|---|---|
| GB/s | 363.3 | **344.3** | 387.6 |

**1867 MHz sits 8.31% below the mean of its two neighbours**, and against memory-only at the same
target it reads **−10.8%** where every other point is within 2.8%.

**Do not read this as the plateau.** 1867 MHz is exactly where the *tuned* profile's plateau
ends, so a dip there invites the reading that the split curve inherits it — and the rest of the
table refuses that: the split curve beats tuned by 15.7% at this very point. The dip is the
transient defect this project has documented moving from frequency to frequency between runs. It
landed at 1867 the night before, at 1792 the night after, and CLAUDE.md retired the attempt to
attribute it to capture software on 2026-08-24.

**What it adds to that record: this instance is DEEPER than any of the seven verified-quiet
sweeps**, whose worst points run −0.36% to −6.91%. That is consistent with an unverified machine
and is one more reason not to pool this sweep with them.
