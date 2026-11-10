<!-- dataset-grade: yes -->

# `rtx2060s-finefloor-20260915` — the Turing floor at 15 MHz, and it is not a floor

**One `gemm` sweep, 13 points, 900 → 1140 MHz, stock, MSI Ventus 2X RTX 2060 Super.** Driver
616.92, 175 W enforced, schema 0.3.3, collected 2026-09-15 through the USB kit on the owner's
machine. Baseline 1.6%, encoder and decoder 0, `workload_result_verdict: ok`, 13 of 13 points
returning a benchmark result, 0 drifted / overshot / undershot.

**Why it exists.** The 2026-09-12 sweeps put this card's efficiency verdict on a knife edge: read
strictly, its 0.631 V floor ended at 975 MHz and the load-floor rule *failed*; allowing one 6 mV
sensor step it ended at 1035 and the rule *held*. The coarse grid had exactly one measurement
between 975 and 1095. This run puts five there.

**Throughput here is `gemm` on a 15 MHz grid and is NOT the suite optimum.** The suite optimum
of 1065 MHz quoted below is the median over twelve workloads on the 105 MHz grid, from
`rtx2060s-20260912/`. Two different quantities; do not merge them.

---

## Result 1: the curve has a MINIMUM, not a floor

| MHz | 900 | 915 | 945 | 960 | **975** | **1005** | 1020 | 1035 | 1065 | 1080 | 1095 | 1125 | 1140 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **V** | 0.644 | 0.644 | 0.637 | 0.637 | **0.631** | **0.631** | 0.637 | 0.637 | 0.644 | 0.650 | 0.650 | 0.656 | 0.662 |

**Voltage FALLS by 13 mV from 900 to 975, sits at 0.631 V across 975–1005, then rises by 31 mV to
1140.** It is not flat-then-rising. The 09-12 sweep already showed this shape at the bottom
(405–465 MHz read 0.644, *above* the 0.631 minimum) and it was recorded as a curiosity; at 15 MHz
resolution it is the dominant feature of the band.

**"NON-MONOTONIC CURVE" IS THE WRONG WORDING AND IT IS CORRECTED 2026-09-18.** An outside
reader raised that a fall in *measured* voltage need not mean the vendor's *programmed* mapping
falls — load-line droop, active voltage positioning, or a gap between requested VID and delivered
rail voltage would all produce it. **The defensible sentence is "the reported voltage readback is
non-monotonic."** This project already had evidence the two differ (`CLAUDE.md`: *"0.925 V
requested delivers 0.920 V under ~170 W load"*) and still did not consider it.

**DROOP WAS THEN TESTED AND REFUTED — see `docs/PRIOR-ART-20260918.md` §2.** Droop depends on
current, not frequency, so two workloads at the *same locked clock* decide it. On this card,
`gemm` and `membw` differ by **47.1 W at 1590 MHz and report identical voltage**; on the RTX 3060,
**71.2 W at a matched clock, 0.0 mV difference.** The reported voltage does not respond to load at
all, so it behaves like a requested VID read back from the table.

**Which makes the finding stronger, not weaker.** A VID that falls as clock rises is the curve
lookup returning a lower voltage at a higher clock — more interesting than a measurement artifact.
**Temperature compensation is the leading remaining candidate**, and that is what §4d tests.
Note §4d cannot separate droop from frequency (current tracks frequency in both directions); the
fixed-frequency test above is what settled that, and it needed no hardware.

**A ridge point is defined on a curve that is CONSTANT and then rises.** Schoonhoven et al.'s
Equation 3 is a flat floor plus a linear rise, **fitted from power**, and they never measured a
Turing V/F curve — their only Turing part is in the group where voltage cannot be read and the
floor's shape is *assumed*. A piecewise fit of that form returns a breakpoint whatever the curve
does, so **it could not have reported this shape even if it had hit one.** That is an inference
from the form of the model, not a statement the paper makes.

## Result 2: the strict floor ends at 1005, not 975 — and the verdict now turns on 7.5 MHz

| reading | floor ends | nearest suite grid point | measured optimum | rule |
|---|---|---|---|---|
| strict — last point at the 0.631 minimum | **1005** | 960 | 1065 | fails |
| allowing one 6 mV sensor step | **1035** | 1065 | 1065 | holds |

The suite grid is 855 / 960 / **1065** / 1170, so the tie between 960 and 1065 sits at
**1012.5 MHz**. The strict floor end is **7.5 MHz below it**.

**So the ambiguity is NOT resolved — it is sharpened, and it moved.** The 09-12 reading put the
strict end at 975; it is 1005. The disjunction survives on a margin four times finer than the
sensor code that produced it. **Do not write that this sweep settled the card.**

## Result 3: the sensor DOES dither — the open question is answered

`SESSION-E-RUNSHEET.md` recorded this as **UNKNOWN** and flagged that the idea might be dead
because the committed extracts hold one median per bin. Per-sample, with 63–80 samples per point:

| MHz | 900 | 915 | 945 | 960 | 975 | 1005 → 1140 |
|---|---|---|---|---|---|---|
| minority code share | 8% at 0.650 | **23% at 0.637** | 5% at 0.644 | **26% at 0.631** | 10% at 0.637 | **none — 100% single code** |

**Dither is real and it is confined to 900–975 MHz.** Every point from 1005 upward reports a single
code for every one of its samples. So sub-code resolution is available exactly where the curve is
falling and unavailable where it rises — which is the opposite of convenient, since the rising side
is where the floor end has to be located.

**Not yet used to compute a sub-code voltage.** The duty-cycle estimate needs the sensor's
rounding behaviour established before a ratio means anything, and nothing here establishes it.

---

## THE CONFOUND, AND IT IS NOT SMALL

**The sweep runs low frequency to high, and the card warms up monotonically while it does.**

| MHz | 900 | 975 | 1005 | 1065 | 1095 | 1140 |
|---|---|---|---|---|---|---|
| T avg °C | 42.0 | 54.0 | 55.5 | 57.6 | 58.1 | 58.7 |
| V | 0.644 | 0.631 | 0.631 | 0.644 | 0.650 | 0.662 |

- **900 → 1005: temperature climbs 13.5 °C while voltage falls 13 mV.** Frequency and warm-up are
  perfectly collinear. **The falling limb is not attributable to frequency from this sweep.**
- **1005 → 1140: temperature moves 3.2 °C and has essentially saturated, while voltage rises
  31 mV.** Here the rise *is* attributable to frequency.

**So Result 1's rising half stands and its falling half does not.** And the falling half is the
one that sets where the floor begins — which means "the floor is 345 MHz wide" from the 09-12 data
inherits the same confound, because that sweep also ran low to high.

### How far the confound reaches — bounded from existing data, 2026-09-15

**16 of the 22 sweeps that ever produced a voltage extract warm by 8 °C or more**, and the 5060 Ti
stock sweep behind the 0.720 V floor warms 24.6 °C. So the exposure is project-wide. But the floors
those sweeps report are **flat through the warm-up**:

| card | floor region | voltage across it | temperature across it |
|---|---|---|---|
| RTX 3060 | 840 → 1260 MHz, 5 points | **0.756 V, zero movement** | 38.6 → 48.8 °C (**10.2 °C**) |
| RTX 5060 Ti | 1237 → 1545 MHz, 3 points | **0.720 V, zero movement** | 41.2 → 46.3 °C (5.1 °C) |

**A 10.2 °C warm-up on the 3060 moved the reading by less than one 6 mV code.** The fall measured
here is 13 mV across 13.5 °C — more than double that bound. If temperature drove voltage at this
scale the 3060's floor could not have come back flat across five consecutive points.

**So the flat floors are most likely genuinely flat and the corpus is probably not in danger;
what is unexplained is this card.** The bound comes from a *different card*, and thermal
compensation is per-controller behaviour that need not transfer — the same trap as borrowing a
floor voltage between cards. It narrows the question; it does not close it.

### The discriminating experiment, and it is cheap

**Re-run this exact grid in DESCENDING order**, same session, same settings, ~12 minutes.

- If the voltage minimum stays near **1005 MHz**, it is a property of the V/F curve.
- If it follows the cold end of the run — now the *high*-frequency end — it is thermal, and every
  "load floor" this project has measured on a low-to-high sweep needs re-reading.

Registered as **§4d** in `docs/REGISTERED-PREDICTIONS.md` before collection.

---

## A join defect this sweep exposed

**`join_hwinfo_voltage.py` binned samples within ±25 MHz of each point, against a grid stepping
15 MHz.** 908 of 916 loaded samples were claimed by more than one point. The symptoms were visible
and did not look like a defect: sample counts of 221 and 208 beside neighbours at 137–154, and a
non-monotonic power column. **Every voltage in this directory is binned at ±7 MHz**, which makes
the counts uniform (63–80) and separates 1125 and 1140 into 0.656 and 0.662 V — the wide bin had
merged them into a single 0.659.

**The other 20 committed extracts are UNAFFECTED, and this was checked rather than assumed.**
Re-derived at ±7 MHz, both RTX 3070 Ti fine sweeps return voltages **identical to three decimal
places** with identical sample counts. A hard-locked clock reports at its target, so its samples
never reach the neighbour however close the grid looks. **A first version of the guard tested
grid GEOMETRY and flagged 92 sweeps, all but this one falsely** — the tool now measures the actual
overlap instead, and six checks in `test_join_hwinfo_voltage.py` pin the distinction.

---

## Files

| file | what it is |
|---|---|
| `…_sweep.csv` | 13 points, per-point telemetry and `gemm` throughput |
| `…_sweep.json` | session record — driver, limits, guards, verdicts |
| `…_sweep_voltage.csv` | the join, **±7 MHz bin**, 63–80 samples per point |
| `data/HWiNFO-Data/hwinfo-rtx2060s-finefloor-20260915.csv` | the raw log, 1743 samples at 0.5 s — **kept deliberately**, it is what the dither analysis needs |

**`workload_seconds` at 900 MHz is 203.9 s against ~41 s for the rest.** That is one-time
process startup — CUDA context and cuBLAS init on the session's first launch — and it sits OUTSIDE
the timed region: `bench_seconds` is 34.7 s, exactly on trend. **The throughput at 900 MHz is
valid.** It is also why the run took 12 min 26 s against a 9.7 min projection.

**`distinct_clocks_measured` reads 10 against 13 genuinely distinct achieved clocks.** The sweep
tool groups clocks into 25 MHz buckets, and three adjacent pairs (945/960, 1020/1035, 1065/1080)
fall in one bucket each. All 13 locks held and every achieved clock equals its target exactly. **The
field is a false alarm on a fine grid, not a failed run** — same 25 MHz assumption as the join
defect above, in a second place.
