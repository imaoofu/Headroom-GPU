# `rtx2060s-20260912` — a fourth chip, a third architecture, and the first ambiguous floor

**Seventeen dataset-grade sweeps on an MSI Ventus 2X RTX 2060 Super**: two `gemm`/`membw` pairs at
default counts, a full twelve-workload suite, and a low-range `gemm` probe. Turing TU106-410,
TSMC 12 nm, 34 SMs, 256-bit GDDR6. Driver **616.92**, enforced **175 W**, schema 0.3.3. Collected
2026-09-12 on the author's own machine, a shop build owned while on the bench
("an owner's machine" until 2026-09-28, written before the 2026-09-13 clarification), via the USB collection kit.

**Dataset-grade**, except `failed-invocations/`, which is marked and explains itself.

| folder | contents |
|---|---|
| `…_rtx2060-super` | `gemm` + `membw`, default counts. **No HWiNFO coverage** — the log started after it. |
| `…_rtx2060s-asfound` | `gemm` + `membw`, default counts, with voltage |
| `…_rtx2060super-suite` | the twelve-workload suite at calibrated counts |
| `…_rtx2060s-lowrange` | **`gemm` from 405 to 1095 MHz** — the run that found the floor |
| `failed-invocations/` | one sweep whose workload never ran. Not data. |

**The card.** Power limit **175 W default / 185 W maximum**; the default matches the reference
175 W TDP exactly, so there is no raised board power and the card is **consistent with reference
trim, though factory-OC status is not confirmed**. Same driver as `rtx3060-20260910`, which removes
a variable the 5060 Ti legs cannot claim.

---

## Result 1: the wrong-range argument, tested on the architecture it criticises

`compare_consumer.py` argues that both published consumer DVFS datasets sweep above stock and
therefore cannot locate an efficiency optimum. One of them is the **RTX 2070 Super** — same
architecture, same 12 nm node, the near-sibling die to this card — sweeping **95–118% of boost** and
reporting a **3.34%** mean gap.

Swept from 40% instead, this card gives:

| | mean efficiency gain at the optimum |
|---|---|
| published RTX 2070 Super (95–118% of boost) | **3.34%** |
| **this RTX 2060 Super (from 40%)** | **41.57%** |

**A factor of 12.4, on the same architecture.** The median is 37.22% and every one of the twelve
workloads clears 19%; `copy` reaches 83.81%. For scale, the RTX 3060 gives 42.21% and the V100
44.40%.

**The prediction was registered at ">15 points" before the card was measured** — see
`docs/REGISTERED-PREDICTIONS.md` §3d. Until today the wrong-range argument compared *different*
architectures and asserted the range was the difference. It no longer has to.

---

## Result 2: the floor exists, and for the first time it does not decide anything

The load floor is **0.631 V** — **89 mV below** the next lowest of the four cards, and the lowest by
some distance. It holds across an enormous span:

| target MHz | 405 | 465 | 525 | 585 | **630–975** | 1035 | 1095 |
|---|---|---|---|---|---|---|---|
| core V | 0.644 | 0.644 | 0.637 | 0.637 | **0.631** | 0.637 | 0.650 |

**Nineteen millivolts across a 170% rise in core clock**, with seven consecutive points at the
0.631 V minimum. The flat band is **570+ MHz wide**, far wider than any other card here.

**And that is exactly why it cannot settle the question.** The rule needs *where the floor ends*,
and the exit is 6 mV at a time — one quantisation step of the REPORTED voltage:

| floor extent, as read | nearest suite grid point | measured median optimum |
|---|---|---|
| **975 MHz** — strict, last point at the 0.631 minimum | 960 | **1065** (no) |
| **1035 MHz** — allowing one 6 mV sensor step | 1065 | **1065** (yes) |

**The verdict flips on a single sensor step.** This is not a refutation and it is not a
confirmation; it is a **boundary condition nobody had hit**: the rule needs a crisp exit from the
floor, and this card does not provide one. Compare the RTX 3060, which jumps **0.756 → 0.787 V**,
a 31 mV step with no ambiguity at all.

**The registered prediction is refuted and stays refuted.** §3c predicted the median optimum at
**855 or 960 MHz**, from an `asfound` sweep whose grid started at 855 — *above* the floor's top edge.
The floor was misread as "at or below 960" because the sweep never reached it. Measured: **1065 MHz**,
with 5 of 12 workloads on the median, the loosest concentration in the study (others run 6–10).

---

## Result 3: the crossbar has its own floor

Visible only because this is the first sweep in the project to go below 840 MHz:

| target MHz | 405 | 525 | 690 | 810 | 870 | 975 | 1095 |
|---|---|---|---|---|---|---|---|
| crossbar MHz | 870 | 870 | 870 | 870 | 870 | 945 | 1050 |
| xbar / core | **2.148** | 1.657 | 1.261 | 1.074 | 1.000 | 0.969 | 0.959 |

The crossbar **pins at 870 MHz** from 405 through 870 and only begins tracking the core above that —
running more than **twice the core clock** at the bottom. Every other card in this study sits in the
0.94–0.96 band because none was swept low enough to leave it.

**This is one card, one workload, and no mechanism is offered.** It is recorded because §5.7's
crossbar-starvation result treats the ratio as the diagnostic statistic, and the ratio evidently has
a floor of its own that the usual grid never exposes.

---

## A methodological finding that retracts a claim elsewhere

The `asfound` `gemm` and `membw` joins return **byte-identical voltages and byte-identical sample
counts** wherever their achieved clocks match. They are not two measurements.
`join_hwinfo_voltage.py` bins by core clock **with no time filtering**, one HWiNFO log covered both
sweeps, and both visit the same targets — so the two joins read **the same pooled samples**.

**This retracted a claim written into §5.5.7 of the paper the previous day**, where the same
artifact on the 3060's `gemm` and `copy` joins was presented as confirming the floor is
workload-independent. Floor *values* are unaffected — voltage at a locked clock is a property of the
applied curve, and pooling samples taken there reads it correctly. What is gone is any use of two
joins from one log as independent confirmation. **Demonstrating workload-independence needs one
HWiNFO log per workload, which no run in this study has.**

The `asfound` HWiNFO log also ran on through the suite calibration afterwards, so it was
**truncated to the sweep window (11:47:25–12:01:25)** before joining. Free-boost calibration load
clears the 30 W filter and would otherwise have landed in the upper clock bins.

---

## What would settle Result 2

A fine sweep of **13 points between 900 and 1150 MHz**, ~20 MHz apart, to find the exact frequency
where voltage first leaves 0.631 V. That narrows the floor extent from ±60 MHz to ±10 and decides
between the 960 and 1065 readings — without needing a better sensor, which is not available.

It does not fix the underlying issue: **a card whose voltage moves 19 mV across its whole low range
will always make this rule hard to apply.** That limit is the finding.
