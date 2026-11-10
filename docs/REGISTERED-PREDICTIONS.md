# Registered predictions

**Predictions written down, committed, and timestamped BEFORE the measurement exists.**

This file is a commitment device. A mechanism that explains results after the fact explains
anything; one that states a number in advance can be wrong in public. Two arms of the load-floor
result were already registered this way — `abba-20260908` and `repair-suite-p2-20260909` both name
the predicted optimum in their READMEs ahead of the data — and this file is where that practice
lives from now on, so a reader does not have to take the claim on trust.

**Rules.**

1. An entry is committed **before** the profile is built or the sweep is run. The commit date is the
   evidence. ⛔ **Never edit a prediction after data exists** — add a result block underneath it and
   leave the original wording alone, wrong or right.
2. Every entry states **what would refute it**, not only what it expects.
3. Every entry states a **safety envelope** before anything is applied to the card.
4. A refuted prediction stays in this file with the refutation written under it. That is the point.
5. 🆕 **2026-09-30. An entry that applies a profile or a clock offset names its exact target list**,
   and its run list carries that list (`targetsMhz`, enforced by `tools/bench-app/Test-Plan.ps1`).
   A grid derived from the supported-clock table moved under §8d (the 3070 Ti's table changed
   overnight) and under §4c-offset (the offset moved the 2060 Super's table top). Both became NOT
   SCOREABLE. A lesson written down after the first did not prevent the second, so the bench now
   refuses such a run list. Entries registered before this date are unaffected.

---

## 1. The floor ladder — registered 2026-09-11. Rung B ✅ COLLECTED 2026-09-23, HOLDS; rung C ✅ COLLECTED 2026-09-26, HOLDS; the four-rung ladder is complete

**Status: profiles not yet built, no data collected.**

### What is being tested

The load-floor mechanism currently rests on configurations that produce **only two distinct predicted
values** — 1530 MHz and 2002 MHz. That is the limitation `analysis/models/predict_from_curve.py`
states about itself: *"configuration is close to a binary variable here."* A rule that has only ever
been asked a yes/no question has not been asked much.

This adds two intermediate rungs so the configuration axis becomes a **four-point monotone ladder**
instead of a switch.

### Design

Both new profiles are **P5's curve with only the region below ~850 mV raised by a fixed offset.**
Everything at and above 860 mV is P5, unchanged and byte-identical.

That region is the right one to move because **P5 below 840 mV is exactly stock** — all 63 points
at or below 840 mV are identical to Profile 3 to the megahertz (1447 / 1530 / 1695 / 1852 / 1987 MHz
at 700 / 720 / 760 / 800 / 840 mV) — and P4 is stock **+465 to +472** across the same span.

⚠️ **The two points at 845 and 850 mV are NOT stock** (+202 and −2 against Profile 3), and 845 mV is
also where P5's curve steps *backward* — 2362 MHz at 845, 2180 at 850. Leave both alone; they sit
above the load floor and outside the region this experiment moves.

| rung | offset below 850 mV | source | clock at 0.720 V | **predicted optimum** |
|---|---|---|---|---|
| A | +0 | P5 / P2 / stock — **have it** | 1530 | 1545 |
| **B** | **+170** | **to build** | ~1700 | **1702** |
| **C** | **+320** | **to build** | ~1850 | **1852** |
| D | +472 | P4 — **have it** | 2002 | 2010 |

⚠️ **Precision is not required.** The prediction depends only on which grid point the floor extent is
nearest to, and the grid steps are ~150 MHz wide. The acceptance windows for the **720 mV** point:

- **Rung B predicts 1702** for any floor extent in **1624–1777 MHz**
- **Rung C predicts 1852** for any floor extent in **1778–1931 MHz**

Aim at 1700 and 1850; anywhere inside those windows registers the same prediction.

### The predictions

**Primary, and the one that counts:**

> **The median efficiency optimum across the twelve-workload suite equals the grid point nearest the
> frequency the applied curve reaches at 0.720 V — 1702 MHz on rung B and 1852 MHz on rung C.**

This has held on **4 of 4** configurations measured so far (stock, split, repair, full tune), median
exact every time.

**Secondary, calibrated against what the mechanism currently achieves per sweep:**

> **At least 7 of the 12 workloads land individually on the predicted grid point** on each rung.

Observed rates on existing configurations are **83% stock, 75% repair, 69% split, 62% full tune**, so
7 of 12 (58%) sits just below the worst case seen. A rung that comes in materially under that is
information even if the median is right.

**Tertiary, the reason the ladder is worth more than another replicate:**

> **The predicted optimum moves monotonically with the offset, and the four measured optima are
> 1545 / 1702 / 1852 / 2010 — evenly spaced, one grid step apart.**

A switch that flips is weak evidence. A quantity that tracks a knob across four levels is not.

### ⛔ What refutes this

- **The median on either new rung lands on a different grid point.** Not "is a bit off" — the median
  is a grid point, so it either matches or it does not.
- **The optima do not increase monotonically** across A → B → C → D.
- **Both new rungs land on the same grid point as each other**, which would mean the optimum snaps
  between two states rather than tracking the curve — the mechanism would be a threshold effect, not
  the relationship claimed.
- **`reduce` is excluded from none of this.** It is sub-optimal in 16 of 16 existing sweeps and is
  expected to miss here too; a prediction that quietly drops its worst case is not a prediction.

### Safety envelope — check before applying

🛑 **Nothing in the profile set is stability tested, and the one hard crash on record is 875 mV at
3000 MHz.** The envelope argument is what makes this design safe rather than the numbers being small:

- **Below 850 mV**, every point of both new curves lies **between stock (+0) and P4 (+472)** at the
  same voltage. Both bounding configurations have run multi-hour suites without a failure.
- **At and above 860 mV**, both curves are **P5 unchanged**, which has also run multi-hour suites.

So no point of either curve is outside a region already exercised for hours. **This is interpolation
inside a tested envelope, not extrapolation past it.**

⛔ **Do NOT build these with the global Core Clock slider.** A global offset raises the top of the
curve too: at +320 the card would reach 3030 MHz at roughly 890 mV, against a known crash at 875 mV /
3000 MHz. **The top of the curve must not move.** Raise the sub-850 mV points only.

### Pre-run verification, to be done before any sweep

Decode each saved profile from `Profiles\*.cfg` and confirm mechanically:

1. Clock at 720 mV falls inside the rung's acceptance window above.
2. Every point at or above 860 mV is **identical to P5**.
3. Every point below 850 mV lies between stock and P4 at the same voltage.
4. The curve is monotonic across the 850/860 boundary.
5. Snapshot the profile store to `data/afterburner-profiles/` **before** collecting, as
   `abba-20260908` had to learn — a slot number is not an identity.

### Result

*(filled after collection, without editing anything above)*

✅ **Rung B, collected 2026-09-23 — primary and secondary both HOLD.**
`data/frequency-sweeps/5060ti-rungB-suite-20260923/`, twelve workloads, unattended, profile store
verified byte-identical to the rung B snapshot and +2500 memory witnessed live at every point.

| registered | measured |
|---|---|
| **primary:** median optimum 1702 | ✅ **1702** |
| **secondary:** at least 7 of 12 on 1702 | ✅ **9 of 12**. copy and bgemm32 at 1852, `reduce` at 2167; none excluded |
| **tertiary:** 1545 / 1702 / 1852 / 2010, monotone | 🟡 **3 of 4 rungs on their points (A, B, D), in order.** C is not collected, so this is not scored |

**Refutation did not occur** for rung B: its median is the predicted grid point. The "both new rungs
on one point" refutation needs rung C. ⚠️ **One chip, one suite, a ~155 MHz grid**; twelve workloads
are repeated outcomes on one card.

**Also measured, not registered:** `gemm` holds 0.720 V through **1695 MHz achieved** on rung B,
where P5 had already risen to 0.755, and matches P5's VID codes from 2317 to 2782 MHz. That is the
above-floor equivalence the pre-run check below could not establish from the file. Details and the
missed-lock pattern above 2317 MHz are in the data README.

**Rung C** can now be built into P1: the rung B store is preserved in its snapshot.

⛔ **Pre-run verification of rung C, 2026-09-26 (built into P1 over rung B, decoded from a snapshot
taken before any sweep).** Check 1 passes: 720 mV reads **1845**, inside 1778–1931. Check 2 passes:
0 differences from P5 at 860 mV and above. Check 4 passes. Check 3 fails at 670–690 mV **for the
same registration defect as rung B**, not a build fault. The floor region, 670–840 mV, is lifted
exactly **+315** (Afterburner's grid had no +320 at 840 mV). The 845 mV point shows rung B's
offset-lag pattern. Check 5: `data/afterburner-profiles/5060ti-profiles-20260926-rungC/`.
**Rung C is ready for collection.**

✅ **Rung C, collected 2026-09-26 — primary, secondary and tertiary all HOLD.**
`data/frequency-sweeps/5060ti-rungC-suite-20260926/`, twelve workloads, unattended, profile store
verified byte-identical to the rung C snapshot and +2500 memory live at every point.

| registered | measured |
|---|---|
| **primary:** median optimum 1852 | ✅ **1852** |
| **secondary:** at least 7 of 12 on 1852 | ✅ **9 of 12**. copy and layernorm at 2010, `reduce` at 2317; none excluded |
| **tertiary:** 1545 / 1702 / 1852 / 2010, monotone | ✅ **all four rungs on their predicted points, in order** |

**No refutation occurred:** the median is the predicted point, the optima rise monotonically A → B →
C → D, and B and C land on different points. ⚠️ **One chip, one suite per rung, the four rungs from
different sessions, a ~155 MHz grid**; twelve workloads are repeated outcomes on one card, and
per-workload optima reproduce only about 9 of 12 between identical runs.

**Also measured, not registered:** `gemm` holds 0.720 V through **1845 MHz achieved** on rung C, where
rung B had risen to 0.745, and matches rung B's VID codes from 2317 to 2932 MHz. A first launch took no
data: its live-profile witness read idle memory (810 MHz) before the load reached the GPU, refused, and
reverted. The witness was re-timed; its acceptance band was not changed (data README).

⛔ **Pre-run verification of rung B, 2026-09-22 (built into P1, decoded from the live store).**
Check 1 passes: 720 mV reads **1702**, inside 1624–1777. Check 2 passes: everything at 850 mV and above is
P5. Check 4 passes: 850 → 860 mV rises. ⛔ **Check 3 FAILS, and the fault is in this registration,
not the build.** "Every point below 850 mV lies between stock and P4" is impossible at **650–690 mV**,
because **P4 IS stock there**, so any raised rung exceeds it: rung B has 997 MHz at 650 mV against P4's
817. The card never runs below 0.720 V under load, so this matters at light load only. But the
envelope argument above is false at those points. ~~⚠️ **845 mV is unresolved.**~~ ✅ **Resolved
2026-09-22:** the editor shows 2362, +0, and a re-save was byte-identical, so the stored (+176, 2362) is
the same state, mispaired by the decoder at an offset boundary. Check 5 is done: snapshot
`data/afterburner-profiles/5060ti-profiles-20260922-rungB/`. **Rung B is ready for collection.**

---

## 2. Profile 1 — ✅ COLLECTED 2026-09-22, THE PREDICTION HOLDS

**Status: swept.** `data/frequency-sweeps/5060ti-p1-suite-20260922/`, twelve workloads
× 13 frequencies, unattended, operator absent.

> **Measured median optimum: 2010 MHz — the registered grid point. Seven of twelve workloads
> land on it individually** (attention, bgemm64, bgemm128, bgemm256, bgemm1024, conv, copy).
> The other five: gemm 1852, bgemm32 1545, layernorm 2167, softmax 2167, reduce 2475.

✅ **Checked by an outside audit against the pre-collection revision `1f6f3d6`, 2026-09-22.** The
registered test was **the median alone**: 2010 MHz, refuted by any other grid point. It passed.
⚠️ **The 7 of 12 is descriptive. No per-workload threshold was registered, so it is not a second
success.** And the test is **coarse**: the registration expected P1 and P4 floor extents 30 MHz
apart, which a ~155 MHz grid cannot resolve. P1 and P4 also differ in power limit and memory
together. Record: `docs/gpt-findings/2026-09-22-5060ti-session-results-audit.md`.

🔑 **What it tests that nothing else did.** The manipulation moved the floor and the optimum
followed; the negative control moved the curve *above* the floor and it did not. **P1 holds the
floor region fixed and changes POWER LIMIT (180 W against P4's 200 W) and MEMORY (+2000 against
+2500)** — the two variables neither existing arm touches. The optimum did not move.

⚠️ **Two variables at once, so a movement would not have identified which caused it.** That
asymmetry is what makes the test admissible: the prediction is refuted *by movement*, whatever its
cause, because the mechanism claims the floor extent is sufficient. **State it that way, never as a
clean single-variable control.**

✅ **Provenance is independently witnessed, not asserted.** P1 carries memory +2000 where stock
carries +0, so the memory clock confirms the profile was live: **13801 MHz before, 15801 after
applying, 13801 after reverting.** The runner refused to sweep unless the post-apply reading
cleared stock, and reverted in a `finally`. ⚠️ Check the memory **maximum**, not the average — the
average is diluted by 810 MHz idle samples between iterations and looks alarming without meaning
anything.

**Original registration follows, unedited:**

P1 is easy to mis-remember as the memory-only profile. It is not: it carries the **same +478 MHz
floor offset as P4**, giving a floor extent of **1972 MHz**. It differs from P4 in **power limit
(100% / 180 W against 111% / 200 W)**, **memory (+2000 against +2500)** and **plateau (2962 against
3030)**.

> **Prediction: P1's median optimum is 2010 MHz — the same grid point as P4** — because 1972 and 2002
> are 30 MHz apart against a ~150 MHz grid, and the mechanism claims the optimum is set by the floor
> extent alone.

🔑 **This is a control on power limit, the one variable neither existing arm touches.** The
manipulation arm moved the floor and the optimum followed; the negative control moved the curve above
the floor and it did not move. P1 holds the floor region fixed and changes power and memory.

⚠️ **It is a two-variable contrast.** That weakens it as a test of *cause* — if the optimum moves, it
will not say which variable did it — but not as a test of the *prediction*, because the mechanism
claims the floor extent is sufficient. Any movement refutes it regardless.

**Refuted by:** a median optimum on any grid point other than 2010.

**Safety:** P1 is an existing, unmodified profile that is milder than P4 at every voltage above
850 mV (lower plateau, lower power limit). No new territory.

### Result

*(empty)*

---

## 3. RTX 2060 Super — PENDING, registered 2026-09-11

**Status: card available, nothing measured.** Turing, **TSMC 12 nm**, 34 SMs, 175 W TDP, 256-bit
GDDR6, 1650 MHz rated boost. A **third architecture and a third process node**, and the first
Turing part this project will sweep itself.

Procedure: `docs/FLOOR-VOLTAGE-PROTOCOL.md`. ⚠️ **Measure the floor FIRST, register the derived
prediction, and only then read the efficiency optimum** — the whole value of this run is that the
prediction is made between two measurements rather than after both.

### 3a. The floor voltage — DECLINED, deliberately

> **This project cannot predict the RTX 2060 Super's load-floor voltage, and does not try.**

Registering a refusal matters as much as registering a number. The floor voltage does **not**
transfer — 0.720 V on Blackwell, 0.756 V on Ampere — and borrowing either would be the exact error
`predict_from_curve.py` warns about. If this run later looks like a success, this paragraph is the
record that the constant was measured and not foreseen.

### 3b. A node hypothesis, registered ONLY so it can be refuted

> **Weak hypothesis, n = 2: floor voltage rises with process node size. 4N reads 0.720 V and
> Samsung 8 nm reads 0.756 V, so 12 nm Turing should read ABOVE 0.756 V.**

⛔ **Two points define a line trivially and this is barely a hypothesis.** It is written down because
a cheap prediction that can be killed is worth more than an expensive one that cannot, and because
if the 2060 Super reads *below* 0.756 the node story is dead on the third card instead of surviving
to a paper. **Refuted by any reading at or below 0.756 V.**

#### ⛔ Correction, same day: this was registered on a miscounted sample, and existing data already weakens it

**The wording above stands unedited, as the rules of this file require.** What follows is the record
that it was written badly.

**n was 3, not 2.** The RTX 3070 Ti's floor — **0.812 V**, holding to 1500 MHz — was already measured
in `data/frequency-sweeps/rtx3070ti-20260825/` and already stated in §5.5 of the paper when the
hypothesis above was written. It was not consulted. **A sample size was asserted rather than
counted**, which is the exact failure this project has a rule against.

🔑 **And the omitted card contradicts the hypothesis.** The RTX 3060 and the RTX 3070 Ti are **the
same architecture on the same process node**, and their floors differ by **56 mV** — larger than the
**36 mV** between the 8 nm parts and the 5 nm one. **Within-node spread exceeds between-node
difference, so node alone cannot determine the floor voltage.** The prediction "12 nm should read
above 0.756 V" may still come true, but it would no longer be evidence for the reason it was
offered.

**Revised, and deliberately weaker:** among the two Ampere parts the floor rises with die size and
power class — 28 SMs / 170 W at 0.756, 48 SMs / 290 W at 0.812 — with architecture plausibly setting
an offset on top. ⚠️ **That is monotone across two points and is a direction to test, not a
prediction.** The 2060 Super at 34 SMs / 175 W on an older node is a reasonable probe of it, and
**no point estimate is registered for it.**

⚠️ **The original 3b remains the thing to score.** If the card reads at or below 0.756 V, 3b is
refuted outright. If above, 3b survives on a test it was too weak to deserve.

### 3c. The mechanism — the real test

> **Once the floor voltage and floor extent are measured, the median efficiency optimum across the
> workload set will be the grid point nearest the floor extent.**

Held on **5 of 5** configurations across two architectures. This is the first chance to break it on
a third. **Refuted by a median landing on any other grid point.**

⚠️ **Stated as a rule rather than a number because the grid is not known until the card reports its
supported clocks.** The derived number goes in the Result block below, written **before** the
efficiency column is read.

### 3d. 🔑 The wrong-range prediction — the sharpest thing this card can do

This is the one worth caring about. `data/external/gtx2070s-*.csv` is a **published** DVFS dataset
for the RTX 2070 Super: same architecture, same 12 nm node, same generation, a near-sibling part. It
sweeps **95–118% of rated boost** and reports a mean headroom gap of **3.34%**, with 20% of apps
optimal at its ceiling.

`CLAUDE.md` argues that figure is an artefact of sweeping the wrong range — that the optimum lives
*below* stock, where that dataset never goes. That argument has never been tested on the same
architecture.

> **Sweeping a 12 nm Turing card from 40% of its supported range will find a stock-to-optimum
> efficiency gap far larger than the 3.34% the published 2070 Super dataset reports — specifically,
> greater than 15 points.**

Basis for 15: the V100 gave 44.4 points and the 5060 Ti's own headroom runs 30–57 points. Fifteen is
deliberately conservative, well under every consumer measurement this project has made.

⛔ **What refutes it:** a gap at or below 15 points would mean Turing genuinely lacks the headroom
this project claims consumer silicon has, and the "published consumer datasets sweep the wrong
range" contribution would need rewriting rather than defending.

⚠️ **It is a sibling, not the same chip.** The 2060 Super has 34 SMs against the 2070 Super's 40 and
a lower boost clock, so this compares architecture-and-range, not part-for-part. A difference could
in principle be the part rather than the range — but the published sweep's floor sits *above* stock,
so it structurally cannot locate an optimum below stock regardless of which part it ran on. That
asymmetry is what makes the comparison worth making anyway.

### Safety

Stock only. No profile, no curve, no overclock, no power-limit change. The card is **underclocked
throughout** — the protocol probes the lower half of the range. Clock locks reset through
`try/finally` and do not survive a reboot.

### Result — floor reading, 2026-09-12

**Written before any efficiency optimum was computed, which is the point of the entry.** Collected
on an MSI Ventus 2X RTX 2060 Super, driver **616.92** — the same driver as the RTX 3060 run. Power
limit **175 W default / 185 W maximum**; the default matches the reference 175 W TDP exactly, so
there is no raised board power and the card is **consistent with reference trim, not confirmed**.
Die **TU106-410**, 34 of the 2070's 36 SMs.

Joined from the `asfound` `gemm` sweep, with the HWiNFO log **truncated to the sweep window
(11:47:25–12:01:25)** because the log ran on through the suite calibration afterwards and that
free-boost load would otherwise have polluted the clock bins.

| target MHz | 855 | 960 | 1065 | 1170 | 1275 | 1380 | 1485 | 1590 |
|---|---|---|---|---|---|---|---|---|
| core V | 0.637 | **0.631** | 0.644 | 0.669 | 0.694 | 0.725 | 0.769 | 0.819 |

⛔ **NO FLOOR WAS OBSERVED INSIDE THE SWEPT RANGE.** The protocol anticipates this case and requires
it be recorded rather than papered over. Voltage rises essentially from the first grid point: the two
lowest readings are 0.637 V at 855 MHz and 0.631 V at 960 MHz, **6 mV apart, which is one step of
this sensor's resolution**, and from 1065 MHz upward it climbs monotonically with no flat region
anywhere.

**This is the first of four cards not to show a floor**, against 0.720 V holding to 1552 MHz on the
5060 Ti, 0.756 V to 1260 MHz on the 3060, and 0.812 V to 1500 MHz on the 3070 Ti. Its lowest reading
is also far below all three.

### The prediction this licenses, registered now

The mechanism says the optimum is the highest frequency the curve reaches at the load floor. If this
card's floor sits **at or below ~0.631 V and therefore at or below 960 MHz** — the reading the data
supports — then:

> **The median suite optimum should land at the BOTTOM of the grid, 855 or 960 MHz.**

⛔ **What refutes it:** a median optimum materially above 960 MHz. That would mean either the rule
fails on Turing, or the floor lies below the swept range and the rule cannot be applied without
sweeping lower — and those two are **not distinguishable from this data**, which is a limit of this
run rather than a hedge.

⚠️ **The swept range starts at 855 MHz** (`-MinFrequencyPercent 40` of a ~2115 MHz ceiling). A floor
below that is invisible here. **A confirmation would therefore be weaker evidence than the 3060's**,
where the floor was visible as five flat points *inside* the range with the optimum at their top
edge. Landing on the bottom grid point is consistent with the mechanism; it is also what a card
would do if its efficiency simply kept improving all the way down.

### ⚠️ And one methodological finding from this run

The `asfound` run's `gemm` and `membw` joins return **byte-identical voltages and byte-identical
sample counts** for every point where their achieved clocks match. They are not two measurements —
`join_hwinfo_voltage.py` bins by core clock with no time filter, one log covered both sweeps, and
both visit the same targets, so the two joins read **the same pooled samples**.

🔑 **This retracts a claim written into §5.5.7 of the paper the previous day**, where the same
artifact on the 3060's `gemm` and `copy` joins was presented as confirming the floor is
workload-independent. The floor *values* are unaffected — voltage at a locked clock is a property of
the applied curve and pooling samples taken there reads it correctly. What is gone is any use of two
joins from one log as independent confirmation. **Demonstrating workload-independence needs a
separate HWiNFO log per workload, which no run in this study has.**

---

---

## Outcomes — RTX 2060 Super, scored 2026-09-12

**Two refuted, one held, one correctly declined.** Full record in
`data/frequency-sweeps/rtx2060s-20260912/README.md`. Nothing above this line has been edited.

### 3a — floor voltage declined ✅ correctly

The measured floor is **0.631 V**, **89 mV below the next lowest of four cards**. Nothing in this
project would have predicted that, and the entry declining to try is the record that it was measured
rather than foreseen.

### 3b — "12 nm should read above 0.756 V" ⛔ REFUTED

**0.631 V. Not above 0.756 — the lowest of all four cards, by a wide margin.** The oldest and
largest process node returned the *lowest* floor voltage, which is the opposite of the direction
registered.

🔑 **The node hypothesis is dead, and it was already weak.** The correction appended to 3b on the day
it was written noted that two Ampere parts sharing an architecture *and* a node differ by 56 mV. A
Turing part now reads 89 mV below either. **Process node does not determine the load-floor voltage,
in any direction, and the four measurements are 0.631 / 0.720 / 0.756 / 0.812 V against nodes of
12 / 5 / 8 / 8 nm.**

### 3c — "median optimum lands on the grid point nearest the floor extent" ⛔ REFUTED AS REGISTERED

Registered: **855 or 960 MHz.** Measured: **1065 MHz**, 5 of 12 workloads on the median.

⚠️ **It was refuted for a reason worth keeping: the prediction was made from a sweep that never
reached the floor.** The `asfound` grid starts at 855 MHz, the floor's top edge is near 975, and the
voltage column read as "still falling" when it was in fact already flat. I recorded "no floor
observed" and derived "floor at or below 960" from it. A low-range sweep from 405 MHz found the
floor immediately.

🔑 **And with the floor located, the rule is neither confirmed nor refuted — it is UNDECIDABLE here**,
which is a third outcome this project had not met:

| floor extent as read | nearest grid point | vs measured 1065 |
|---|---|---|
| 975 MHz — strict, last point at the 0.631 V minimum | 960 | ✗ one step out |
| 1035 MHz — allowing one 6 mV sensor step | 1065 | ✅ exact |

**The verdict turns on a single step of sensor resolution.** The card holds 0.631 V across
**570+ MHz** and leaves it 6 mV at a time; the RTX 3060 by contrast jumps 0.756 → 0.787 V, a 31 mV
step with no ambiguity. **The rule needs a crisp exit from the floor and this card does not supply
one.** That is a boundary condition on the mechanism, not a failure of it — and it is not a
retrofitted excuse, because the ambiguity is visible in the voltage column itself rather than
inferred from the answer.

⛔ **The registration stands refuted regardless.** A prediction that needed a second sweep to become
arguable was wrong when it was made.

### 3d — "gap greater than 15 points" ✅ HELD, and it is the day's strongest result

**41.57% mean efficiency gain**, median 37.22%, every one of twelve workloads above 19%, `copy` at
83.81%.

Against the published **RTX 2070 Super** dataset — same architecture, same 12 nm node, near-sibling
die — which sweeps 95–118% of boost and reports **3.34%**. **A factor of 12.4.**

🔑 **This is the wrong-range argument tested on the architecture it criticises.** Until today it
compared different architectures and asserted the swept range was the difference. A Turing card
swept from 40% now returns a Turing number twelve times the published Turing number, and the
threshold was registered before the card was measured.

---

## Prior registrations, recorded elsewhere

Kept here as pointers so the practice is visible in one place. These were registered in their own
data READMEs before this file existed.

| experiment | registered prediction | outcome |
|---|---|---|
| `abba-20260908` | ⛔ **NOT the optimum — see the correction below** | the optimum result was **unplanned**; the registered prediction **failed** |
| `repair-suite-p2-20260909` | changing the curve *above* the floor moves the optimum **not at all** | ✅ **median** unmoved despite a 570 MHz change; **3–6 of 12 individual workloads move** |

⛔ **THE FIRST ROW WAS FALSE AND IS CORRECTED 2026-09-19.** It read *"the optimum moves with the
floor region of the curve — ✅ +465 MHz in 12 of 12 workloads"*, in the one file whose entire job is
to record what was registered **in advance**.

**What `abba-20260908` actually registered** is in its own sweep JSONs: a **dose-response**
prediction, that Profile 4 — the deeper undervolt — would leave **less than P5's 27.5%** remaining
headroom. **It failed**, and in the opposite direction: 34.32% against 28.27%.

**The load-floor result was found afterwards, in that run's data.** The run's own README says *"It
was not planned"* and commit `0ca60ea` says *"RESULT 1, and it was not planned."* 🔑 **Both were
written honestly at the time; the error was committed later, when this ledger summarised them.**

✅ **Two things keep it from being a bare post-hoc fit.** The 0.720 V floor used to predict +465 was
measured on **other data** rather than fitted to this outcome, and the follow-ups — P2, the RTX 3060,
the RTX 2060 Super — **were** registered before collection. ⚠️ The 2060 Super's was **refuted as
registered**, and a later finer measurement cannot convert that into a success.

🛑 **Found by an outside adversarial audit, verified here by recomputation**, not by internal
review — which had read this table repeatedly. Full record:
`docs/gpt-findings/2026-09-19-load-floor-causal-claim-adversarial-audit.md`.
| `rtx3060-20260910` | the rule holds on a different architecture | ✅ holds — ⛔ but the floor **voltage** does not transfer (0.756 V, not 0.720) |

---

# 4. 🔑 THE CROSS-CHIP CAUSAL REPLICATION — registered 2026-09-13, BEFORE any card is touched

**Registered because two cards became available at once and both leave soon.** An RTX 3070 Ti
(Ampere GA104) and an RTX 2060 Super (Turing TU106), both owned outright — see the ownership
correction below. This is the experiment the 2026-09-13 council session named as the single thing
blocking the paper, and it had been recorded as impossible.

⛔ **THE BLOCKER WAS A MISCLASSIFICATION, NOT A RULE.** `rtx3060-20260910/README.md` states these
were machines Raymond "does not own", and `rtx3070ti-20260825/README.md` calls its card "a
customer's machine". **Both descriptions are wrong.** These are builds assembled to sell; nobody
else owns them while they are on the bench and no third party's data is on them. The safety
invariant — *never automate tuning on machines Raymond does not own* — was never engaged. 🔑 **This
is the second time this project has treated a recorded blocker as real without rechecking it**, and
CLAUDE.md's own warning about that is in the coverage section.

## What is already known, and therefore what is being predicted rather than explored

Both cards' stock floors are already measured, which is what makes these predictions registrable:

| card | floor voltage | stock floor holds to | measured median optimum | rule verdict so far |
|---|---|---|---|---|
| RTX 3070 Ti (GA104) | **0.812–0.819 V** | **1500 MHz** | **1485 MHz** | ✅ observational, holds |
| RTX 2060 Super (TU106) | **0.631 V** | **975 or 1035 MHz** | **1065 MHz** | ⚠️ undecidable |

**Every prior confirmation of the rule on these two cards is OBSERVATIONAL.** Only the 5060 Ti has
a causal arm. That is the n=1 that the council said a reviewer would name in thirty seconds.

## 4a. 3070 Ti — the replication. **The single highest-value prediction in this document.** — COLLECTED 2026-09-24: ✅ PASS (4b ⛔ FAIL; see the result under 4b)

> **Extend the stock floor upward by reshaping only the curve at and below 0.819 V, and the median
> suite optimum will move with the new floor end, in the same direction and by a comparable
> fraction of the shift.**

Success is the optimum tracking the new floor end to within one grid step. ⛔ **A movement in the
wrong direction, or no movement, refutes the causal claim on a second chip and must be reported as
the headline** — the 5060 Ti result would then be a single-chip curiosity rather than a mechanism.

## 4b. 3070 Ti — the negative control, run in the same session or not at all — COLLECTED 2026-09-24: ⛔ FAIL, the control also moved

> **Change the curve only ABOVE the floor voltage, by at least 300 MHz, and the optimum will not
> move.**

⚠️ **The manipulation without its control is worth much less than half the experiment.** A council
reviewer specifically defended this design: sharing chip, session and operator is what a negative
control is *for*. If the session is cut short, run 4b, not a second replicate of 4a.

### ⛔ AMENDMENT, recorded 2026-09-22: the design changed BEFORE collection, and this file never said so

**Found by GPT while writing the Session D scorer (`docs/gpt-findings/2026-09-22-session-d-scorer.md`),
verified here against git.** 4a and 4b above are unedited, as the rules require. **They do not
describe the experiment that will run.**

| | registered above, 2026-09-11 | what will run: `SESSION-D-RUNSHEET.md` |
|---|---|---|
| 4a direction | **extend** the floor **upward** | **shorten** it **downward**: cap ≤0.825 V at 1200 MHz |
| 4a boundary | ≤0.819 V | ≤0.819 V at first (`9ab8ba6`, 09-13), **0.825 V** from `8d2a22e` (09-20) |
| 4a prediction | "moves with the new floor end… comparable fraction" | **median 1485 → 1170 or 1275 MHz**, first stated 09-13 |
| 4b dose | **at least 300 MHz** | **263 MHz**: all the range the card has above its floor |

**Why it changed:** the runsheet gives the reason in its first version (`9ab8ba6`, 2026-09-13). The
card is **power-capped at ~1763 MHz**, so an upward edit has at most +263 MHz of dose, and any result
would be entangled with the power cap. Shortening has −300 MHz available with nothing in the way,
and it is the safe direction.

✅ **What is still a genuine advance prediction:** the runsheet's numbers are committed in git on
2026-09-13 and 2026-09-20. **No Session D data exists as of this amendment.** The mechanism predicts
movement *with* the floor end in either direction, so reversing the direction tests the same
claim.

⛔ **What must be said when this is reported:**
1. §4a as worded above did **not** predict the shortening direction or the 1170/1275 numbers.
   **Cite the runsheet's commits for those, not this file.**
2. The control's dose is **263 MHz, below the 300 MHz registered.** Report the shortfall. Do not
   round it away.

🔑 **How it got in: the same way as the 2026-09-19 registration error.** The run record was right and
the ledger that summarises it drifted. This time the runsheet even said *"predictions are already
registered in §4, do not change them"* while describing the opposite edit. **Whenever a runsheet
changes a design, amend this file in the same commit.**

### ⛔ AMENDMENT 2, recorded 2026-09-23: the curves as BUILT, before collection

**No Session D data exists as of this amendment.** The three curves were built at the machine on
2026-09-23 and decoded from the saved store: `data/afterburner-profiles/3070ti-profiles-20260923/`
(the curve file's SHA-256 begins `1b08c2d0854460ff`). They differ from the runsheet in three places,
all forced or found by the build:

| | runsheet | **as built** |
|---|---|---|
| Edit 1, ≤0.825 V | capped at 1200 | ✅ **1200 from 725 to 825 mV**, the whole floor band (0.812–0.825 V) |
| Edit 1, 0.831–0.869 V | "unchanged", at stock | ⛔ **a forced ramp below stock**: 1215, 1275, 1335, 1395, 1455, 1515, 1575 (stock 1530 → 1620), rejoining stock at 875 mV |
| Edit 1, 718.75 mV | stock 1185 | ⚠️ **1200, 15 MHz above stock**, a light-load point below the floor |
| Edit 2, 0.825 V | stock 1515 | **1500**, 15 MHz under stock |
| Edit 2, ≥0.831 V | flat 1500 | ✅ flat 1500 |

**Why the ramp:** the driver, or Afterburner, would not accept a single step from 1200 at 825 mV to
stock at 831. Inferred from the file, not documented: **no point may sit more than ~60 MHz below its
right-hand neighbour.** The first build put the ramp below 825 mV, inside the floor band, and was
rebuilt so the band stays flat.

**The predictions do not change, and here is why each still applies:**
- **Edit 1's floor end is 1200 MHz**, at every code in the floor band. The runsheet's prediction,
  **median 1485 → 1170 or 1275**, was made for exactly that floor end.
- **Edit 2's floor end moves from ~1515 to 1500** at 825 mV, inside the restated prediction's
  **~1485–1500 MHz achieved** band. Its dose is unchanged: the card's ~1763 MHz ceiling is cut to 1500.

⚠️ **What must be said when this is reported:** Edit 1 is **not a floor-only edit.** It also lowers
0.831–0.869 V, which is part of the region Edit 2 edits. The contrast that survives is the one the
design needs: **Edit 1 changes the clock at the floor voltage (1485–1515 → 1200) and Edit 2 does
not** (at most −15 MHz). The 718.75 mV point is outside the safe-by-construction envelope by 15 MHz,
the same kind of exception as rung B's 650–690 mV points, and is recorded rather than rebuilt.

### Provenance note, 2026-09-24, still before any Session D data

Session D's first launch stopped at its store-hash gate. Afterburner had added `[Defaults]` and
`[Settings]` sections to the 3070 Ti's profile store. **`Profile1`–`Profile3` are identical, key for
key, to the store decoded in Amendment 2**, so the curves above are the curves that will run. The
gate now expects the new whole-file hash `cce75e81fe322380`.
`data/afterburner-profiles/3070ti-profiles-20260924-afterburner-rewrite/README.md`. **Nothing in the
design or the predictions changes.** ⛔ *Superseded the same day, still before data: the gate hashes
only the `[Profile1]`–`[Profile3]` sections, `A1159941DA541EB9`, which is what Session D ran against.*

### Result, collected 2026-09-24 — 4a ✅ PASS, 4b ⛔ FAIL: the control also moved, so the attribution fails on this chip

**Scored by `python analysis/score_session_d.py data/frequency-sweeps/rtx3070ti-sessiond-20260924`**,
the scorer committed before collection. Its output, unedited:

| | value |
|---|---|
| eligibility | **VALID**: stock baseline 1485 MHz as registered; stock-1 → stock-4 worst workload change **0.619%** (limit 1.5%); floor verified on all four suites |
| stock-1 median optimum | **1485 MHz** |
| **4a**, Edit 1 (`edit1-2`) | **1222.5 MHz**, inside the registered 1170–1275 → ✅ **PASS** |
| **4b**, Edit 2 (`edit2-3`) | **1432.5 MHz**, outside the registered 1485–1500 → ⛔ **FAIL** |
| stock-4 median optimum | **1485 MHz** |
| joint verdict | ⛔ **CONTROL_ALSO_MOVES_ATTRIBUTION_FAILS** |

🛑 **Report it as registered: the manipulation moved the optimum as predicted, but the negative
control moved it too, so this chip does not attribute the move to the floor region.** 4b said the
control "is what makes the manipulation worth more than half the experiment", and it did not hold.

**Descriptive context.** None of it changes the verdict, and it is recorded so the verdict is read
correctly.
- **The control's 1432.5 is a six-six split.** The twelve optima fall 1065, 1170, 1275, 1275,
  1380, 1380 | 1485, 1485, 1485, 1500, 1500, 1500, so the median sits between two grid points. All
  three stock suites have seven or more workloads at 1485 or above.
- **Per-workload optima are noisy between identical stock suites.** stock-1 and stock-4 disagree on
  **4 of 12** argmaxes (`copy`, `layernorm`, `bgemm128`, `gemm`), and stock-4 and stock-6 on **3 of
  12**. Against stock-1, the control moved 3 workloads down (`bgemm128`, `conv`, `gemm`) and 2 up
  (`copy`, `reduce`). That is the same order as stock-against-stock, but the registered test is
  the median, and stock's median did not move in any of three stock suites.
- **Edit 2 is not purely above the floor**, per Amendment 2's as-built description: *"stock
  through 818.75 mV, flat 1500 MHz from 825 mV up (825 mV is 15 under stock)"*. The 825 mV point
  is inside the registered floor band (≤0.825 V) and was lowered by 15 MHz. That was known before
  collection and does not excuse the result.
- This is the second partly moving control. The 5060 Ti's moved 4 of 12 workloads but not the
  median (CLAUDE.md, the negative-control entry). **Here the median moved as well.**

⚠️ **n = 1 chip, one session.** Driver 617.14, SILENT BIOS 290/290/320 W. The replicate of the
manipulation is §8a below; the control is not replicated.

## 4c. 2060 Super — the boundary condition, made decidable or shown not to be

> **Reshaping the floor region on a card whose voltage leaves the floor 6 mV at a time will produce
> a floor end that is EITHER sharp enough to locate — in which case the optimum should track it as
> in 4a — OR still undecidable, in which case the ambiguity is a property of the silicon and not of
> the vendor's shipped curve.**

🔑 **Both outcomes are publishable and they say different things**, which is why this is registered
as a disjunction rather than a directional bet. This is the only prediction here whose interesting
result is the negative one. ⚠️ Run the fine floor sweep (~10 min) FIRST — the manipulation cannot be
designed without knowing where the stock floor actually ends on this card.

## 4d. 2060 Super — is the load floor a property of the CURVE, or of a COLD CARD?

**Registered 2026-09-15, after the fine floor sweep and before the descending run.** Nothing about
the card has been touched since; this prediction is written from a result already in hand about a
measurement not yet made.

🔑 **WHY THIS EXISTS.** The fine sweep found the voltage **non-monotonic** — falling 0.644 → 0.631 V
from 900 to 1005 MHz, then rising to 0.662 by 1140. But the sweep runs low frequency to high, and
the card warms 42.0 → 58.7 °C while it does, **so on the falling limb frequency and warm-up are
perfectly collinear.** On the rising limb they are not: temperature has saturated within 3.2 °C
while voltage climbs 31 mV, so that half is attributable to frequency. The falling half is not.

> **Sweeping the identical 900–1140 MHz grid in DESCENDING order, on a card allowed to reach
> thermal steady state the same way, the voltage minimum will remain at 975–1005 MHz.**

| outcome | reading |
|---|---|
| minimum stays at **975–1005** | ✅ The shape belongs to the V/F curve. The non-monotonic Turing floor is real and Result 1 stands whole. |
| minimum **follows the cold end** — now the top of the grid | ⛔ It is thermal. **Every load floor this project has measured came from a low-to-high sweep**, so the 5060 Ti, 3060 and 3070 Ti floors all inherit the same confound and the floor-extent numbers need re-reading. This is the larger finding by a distance. |
| minimum flattens or moves partway | 🟡 Both contribute. Report the split and quote no single floor extent without the sweep direction beside it. |

### 🔑 Evidence gathered BEFORE the run, which moves the prior toward "not thermal"

**Recorded here rather than after, because a prior revised once the answer is known is worth
nothing.** 16 of the 22 sweeps that have ever produced a voltage extract warm by 8 °C or more, and
the 5060 Ti stock sweep that sets the project's 0.720 V floor warms **24.6 °C** — so the exposure
is real and project-wide. But the floors those sweeps report are **flat through the warm-up**:

| card | floor region | voltage across it | temperature across it |
|---|---|---|---|
| RTX 3060 | 840 → 1260 MHz, 5 points | **0.756 V, zero movement** | 38.6 → 48.8 °C (**10.2 °C**) |
| RTX 5060 Ti | 1237 → 1545 MHz, 3 points | **0.720 V, zero movement** | 41.2 → 46.3 °C (5.1 °C) |

⛔ **A 10.2 °C warm-up on the 3060 moved the reading by less than one 6 mV sensor code.** If
temperature were driving voltage at the scale seen on the 2060 Super — **13 mV across 13.5 °C**,
more than double that bound — the 3060's floor could not have come back flat across five
consecutive points.

✅ **So the flat floors are most likely genuinely flat, and the corpus is probably not in danger.**
What remains unexplained is the 2060 Super specifically. ⚠️ **This does not settle it**: the bound
comes from a *different card*, and thermal compensation is a per-controller behaviour that need not
transfer — the same trap as borrowing a floor voltage between cards. The prediction below stands
unchanged.

⚠️ **The honest prior is that this is NOT settled.** Temperature-compensated voltage is ordinary
controller behaviour, and nothing in this project has ever varied sweep direction to look for it.
✅ **Cost: one ~12 minute sweep, stock, no elevation beyond the usual clock lock, nothing applied
and nothing to clean up.** It is the cheapest experiment on the list and it can invalidate a
number that appears in the paper's headline mechanism.

🛑 **Keep the raw HWiNFO log again**, and record the per-point temperatures — they are the
independent variable this time, not a footnote.

### ⛔ Amendment, 2026-09-25, before collection: how Session E scores 4c and 4d

**Written before any Session E data exists.** The card has not been touched since 2026-09-15. The
scorer is `analysis/score_session_e.py`, committed with this amendment. Nothing above is edited:
this section fixes what the words above leave open, and records one inconsistency in them.

**4c, the manipulation (`stock-1` → `edit-2` → `stock-3`).** The prediction under Part 2 of the
run sheet is: *"the median suite optimum moves from **1065 MHz** down toward **855 MHz** (the nearest
suite grid point above the new floor end)"*, and *"if it does not move, the rule's attribution to
the floor region fails on Turing"*.
- **Scoreable** only if all of the following hold. Otherwise the result is NOT SCOREABLE, which is
  not a failure.
  - All 36 suites share one driver, the power limits read 175 / 175 / 185 W, and every sweep has
    the 13-point grid 855–2115 MHz.
  - `stock-3`'s median equals `stock-1`'s, the run sheet's rule: *"if the closing stock run does not
    match the opening one, the result is not interpretable"*.
  - No workload's median absolute matched-target throughput change from `stock-1` to `stock-3`
    exceeds **1.5%**, the Session D and §10 limit.
  - **The edit is verified in the data**: every workload of `edit-2` reads **≥ 0.668 V at every
    target**, because the edit makes every clock above 810 MHz need the 0.669 V point.
  - **Stock is verified**: every workload of both stock suites reads **0.630–0.657 V at 1065 MHz**,
    the plan's witness range.
- **PASS**: `edit-2`'s median lies in **855–960 MHz** and below `stock-1`'s. That is the predicted
  grid point or one step above it, the same two-bin width 4a allowed.
- **FAIL_NO_MOVEMENT**: the median is at or above `stock-1`'s. This is the headline failure named above.
- **FAIL_PARTIAL**: the median moved down, but not into 855–960.
- `stock-1`'s median is scored against the same session, and **reported against the registered
  1065**; a different stock median is stated beside the verdict, not hidden by it.
- ⚠️ **Session E cannot decide 4c's "still undecidable" branch.** The suite grid starts at 855 MHz,
  above the edited floor end of 810, so no Session E sweep samples the edited floor end itself. The
  edit's sharpness is by construction (the 38 mV step from ≤ 0.650 to 0.669 V) and by the witness,
  not measured. Locating it would need a fine sweep under P2 around 810 MHz, which the plan does
  not contain. Report this, and do not read a PASS as having shown the floor end is sharp.

**4d, the descending sweep (`e1-desc`), against `rtx2060s-finefloor-20260915`.**
- **The minimum set** is every target whose voltage lies within **0.003 V** of the sweep's lowest
  reading. That is under half of one 6.25 mV code, so a median that falls between two codes still
  ties with the lower code. The ascending reference gives {975, 1005}.
- **Scoreable** only if all of the following hold:
  - the sweep JSON records `sweep_order: descending`;
  - its targets equal the ascending sweep's 13 (900 … 1140);
  - every target has a voltage reading;
  - it reads **0.630–0.657 V at 1065 MHz**, which confirms it ran on stock.
- **HOLDS**: every target in the minimum set lies within **975–1005 MHz**.
- **FLAT**: the minimum set contains both 900 and 1140.
- **MINIMUM_REACHES_BOTTOM**: it contains 900 (and not 1140). The falling limb has gone.
- **MINIMUM_AT_TOP**: it contains 1140 (and not 900).
- **PARTIAL**: anything else. The minimum widened or moved without reaching either end.
- ⛔ **The registered thermal outcome names the wrong end, recorded here before the data can
  choose.** The table above says a thermal minimum *"follows the cold end — now the top of the
  grid"*. But the mechanism it registers is that the falling limb (0.644 → 0.631 V from 900 to
  975 MHz) is **warm-up lowering the voltage**. A descending sweep measures 900 MHz last, on a warm
  card, so under that mechanism the limb disappears and **the minimum extends to the BOTTOM of the
  grid** (MINIMUM_REACHES_BOTTOM). A minimum at the top would need a cold card to read *lower*,
  the opposite mechanism. **Both are scored and both are reported by name.** The thermal reading
  in the table (⛔, "every floor extent needs re-reading") attaches to MINIMUM_REACHES_BOTTOM,
  and MINIMUM_AT_TOP is reported as what the registered words literally said. The error entered
  when the outcome was phrased as "follows the cold end" without working through which end a
  descending sweep measures warm.
- **Reported beside the verdict, never scored:**
  - per-point temperature in both sweeps;
  - the driver in both sweeps, since the reference ran on 616.92.

### ⛔ Amendment 2, 2026-09-27, before collection: 4c's edit cannot be built, and is replaced by a whole-curve offset

**Written before any Session E data exists.** The bench has not run on this card: the kit's
`results/` holds nothing from 09-27. 4d and the text above are unchanged.

**What happened.** At the machine, Raymond found that Afterburner's curve editor would not move any
point below **700 mV**. Every point the Part 2 edit caps lies below 0.669 V, so the registered edit
**could not be built**, and 4c as registered **will not be run.** That is recorded as NOT RUN, not as
a failure of either branch. The store he saved, with both slots at stock, is committed:
`data/afterburner-profiles/rtx2060s-profiles-20260927/` (curve SHA-256 `e477b20d38c69df4`).

**Found in that snapshot, before designing the replacement.** The stored stock curve has 128 points
from 450 mV, **6.25 mV and 30 MHz apart** below ~1300 MHz: 1005 MHz at 631.2 mV, 1035 at 637.5,
1065 at 643.8, 1170 at 668.8. That matches the measured 0.637 / 0.644 / 0.669 V at 1035 / 1065 /
1170. **So the "6 mV creep" is the stock curve's own staircase.** An edit made above 700 mV cannot
touch it. Writing the capped points into the file by hand was considered and **rejected**: it would
build a curve the tool itself declines to build, with unknown driver behaviour.

**The replacement, 4c-offset.** Profile 2 = stock with a **−165 MHz core-clock offset**
(Afterburner's core slider; `CoreClkBoost` −165000 in the store; memory +0; power limit 100; the curve
untouched). An offset slides the whole curve down, including the points the editor will not expose.
So the 631.2 mV point moves 1005 → 840 MHz and the floor end moves by −165, the **same shift the Part
2 edit was designed to make.** −165 is kept so the numbers stay those already registered.

> **Under a −165 MHz whole-curve offset, the twelve-workload median suite optimum moves from stock's
> down into 855–960 MHz.**

- **Why this band:** 1065 − 165 = 900 MHz, between the grid points 855 and 960. It is the same band,
  the same grid and the same scoring as 4c's PASS above. So FAIL_NO_MOVEMENT and FAIL_PARTIAL are
  defined as there.
- **What it can show, and what it cannot.**
  - ⚠️ **It is not region-targeted.** The offset shifts the whole curve, so a pass shows that the
    optimum follows the **curve's voltage**, not the **floor region**. That is the 5060 Ti §7 result
    (an NVML offset ladder), asked on Turing through Afterburner.
  - A fail means the optimum is tied to **frequency**, not to the curve. On the card where the rule is
    undecidable, that would be the stronger finding.
  - ⛔ **4c's disjunction stays unanswered.** An offset moves the staircase; it does not sharpen it. So
    this says nothing about whether a sharp floor end would be locatable on Turing.
- **Run order and grid: unchanged.** `stock-1` → `offset-2` → `stock-3`, 13 points 855–2115 MHz, and
  the iteration counts of `20260912-124138_rtx2060super-suite`. The run is renamed from `edit-2` to
  `offset-2`, so that no file carries the name of an edit that was never built.
- **Slot witnesses, replacing the edit's.** The reported voltage follows the stored curve (as above),
  so under the offset a locked clock *f* should read what stock reads at *f* + 165.
  - Locked **1065**: expect the 681.2 mV point (stock's 1230). Accept **0.672–0.700 V**. Stock (0.644,
    or 0.650 one warm code up) fails, and so does an offset that did not reach below 700 mV, since that
    would leave 1065 at 0.644.
  - Locked **1275**: expect the 743.8 mV point (stock's 1440). Accept **0.731–0.757 V**. Stock reads
    0.694.
  - Both ranges accept roughly −135 to −195 MHz. They verify that an offset of about that size is live
    across the whole curve, **not** that it is exactly −165. The store is snapshotted again after
    Profile 2 is saved; `CoreClkBoost` there is the record of the exact value.
- **Scoreable** as in the amendment above, except that "the edit is verified in the data" becomes:
  every `offset-2` workload reads **0.672–0.700 V at 1065 MHz** and **0.731–0.757 V at 1275 MHz**.
- **Safe by construction.** A negative offset gives every clock **more** voltage than stock. The power
  limit is unchanged.

**Scorer:** `python analysis/score_session_e.py <dir>` scores 4c-offset. `--4d` is unchanged.

### Result — Session E, collected 2026-09-27 14:26–18:12: 4d ⚠️ PARTIAL, 4c-offset ⛔ NOT SCOREABLE

`data/frequency-sweeps/rtx2060s-sessione-20260927/` (37 sweeps; README carries the tables).
Driver 617.14. Every bench witness passed, including offset-2's at 1065 (**0.681 V**) and 1275
(**0.744 V**), exactly the stored-curve predictions. The stock return is 0.21% at the worst workload.

**4d: PARTIAL.** Descending, the minimum set is **{945, 960, 975, 1005}** against the ascending
reference's {975, 1005}, and 900–915 read 0.637 against 0.644. Both temperature and the curve
contribute. So no floor extent on this card is quoted without its sweep direction. The driver
differs from the reference (617.14 against 616.92), reported beside the verdict as registered.

**4c-offset: NOT SCOREABLE.**
- **The scoreability rule failed:** offset-2 did not run on the registered 855–2115 grid.
- **Why:** the −165 MHz offset moved the supported-clock table's top from 2115 to 2100, so the
  suite's derived grid became 840 … 2100.
- **How it got in:** nobody checked whether an offset changes the table. The kit engine only checks
  the table top at session start.
- **Descriptive, not scored:** the offset median is **1050**, the same grid position as stock's 1065
  (both stock suites 1065, 3 of 12 offset workloads at 945). The optimum did not follow the shift.
  This stays NOT SCOREABLE whatever the re-run (Amendment 3) shows.

### ⛔ Amendment 3, 2026-09-27 evening, before the re-run and AFTER Session E's descriptive result

**Written after seeing Session E's offset suite descriptively:** its median sat at the same grid
position as stock's, so the optimum did not move. **The prediction is not changed by a single
word.** Raymond chose the re-run after that result was known, so both sessions are always reported
together: Session E's as NOT SCOREABLE with its descriptive "no movement", and E2's as the scored
verdict. Neither may be quoted without the other.

**Why a re-run can be scored when Session E could not.** Session E's grid moved because it was
*derived* from the supported-clock table, and the offset moved the table (top 2115 → 2100). E2
removes the derivation: **every suite sweeps one explicit list, 855, 960 … 2010 MHz (12 targets,
105 MHz apart)**, present in both tables. 2115 is dropped, since stock reached only ~1916 there and
nothing above ~1740 is reachable under the offset, so no optimum can sit there.

**Design (Session E2), otherwise Session E's by construction** (`build_sessione2.py` imports every
step from `build_sessione.py`):
- Runs: `stock-4` → `offset-5` → `stock-6`, numbered on from Session E.
- Same slots: P1 stock, P2 stock + −165 MHz, the store of
  `data/afterburner-profiles/rtx2060s-profiles-20260927b-offset/`.
- Same witnesses, iteration counts, memory clock, power gate and drift limit.
- Afterburner stays on the card until E2 is collected.

**Engine changes, made for E2 and tested only in dry run:**
- `Invoke-FrequencySweep.ps1 -TargetFrequenciesMhz` sweeps an exact list and refuses any target
  missing from the clock table. It records `sweep_targets_explicit`.
- `Collect.ps1` passes the list to every sweep of a suite.
- The bench engine skips its mid-session table-top check for a suite with an explicit list, and
  instead checks every suite CSV's targets against the list.
- The kit gets the current engine for E2. Its only live use so far is the 3070 Ti sessions, before
  the new-card changes. ⚠️ **So E2 is also that engine's first live run since those changes.**

**Scoring:** exactly Amendment 2's, on E2's runs and targets:
- **Scoreable** only if every one of the 36 suites has the 12 targets 855–2010, and one driver runs
  throughout.
- The medians of `stock-6` and `stock-4` must be equal.
- No workload may drift more than 1.5% between the stock brackets.
- `offset-5` must read 0.672–0.700 V at 1065 and 0.731–0.757 V at 1275, and both stock suites
  0.630–0.657 V at 1065.
- **PASS** if `offset-5`'s median lies in **855–960** and below `stock-4`'s. **FAIL_NO_MOVEMENT** if
  it is at or above it; **FAIL_PARTIAL** otherwise.
- Scorer: `python analysis/score_session_e.py <E2 dir> --e2`.

**Limits, unchanged:** one chip; whole-curve, not region-targeted; says nothing about 4c's
disjunction.

### ⛔ Result — Session E2, collected 2026-09-27 20:05–23:24: 4c-offset FAIL_NO_MOVEMENT

`data/frequency-sweeps/rtx2060s-sessione2-20260927/` (36 sweeps; the README carries the tables).
Driver 617.14 throughout. **Scoreable:** all 36 suites on the 12 targets 855–2010; stock medians
equal; stock return **0.524%** at the worst workload (limit 1.5%); offset-5 read **0.681 V** at
1065 and **0.744 V** at 1275; both stock suites **0.644 V** at 1065.

- **Verdict: FAIL_NO_MOVEMENT.** The offset median is **1065**, equal to both stock medians.
- **Read beside Session E, as this amendment requires:** Session E's offset suite was NOT
  SCOREABLE and descriptively did not move (1050, the same grid position). E2 is the scored verdict
  and agrees with it.
- **Descriptive, written after seeing the data:** the offset did change the efficiency curve's
  shape in the predicted direction. The median relative efficiency at 855 MHz rose from 92.4–92.7%
  to 97.3%, and the region above the peak fell faster (1380: 92.7–95.4% against 88.2%). The peak
  grid point did not move. So the registered reading, *"the optimum is tied to frequency, not to
  the curve"*, is stronger than the data: the curve mattered, by less than one 105 MHz grid step.
- **Per-workload movement does not rescue it:** two identical stock suites already differ at 6 of
  12 workloads; the offset moves 10 against `stock-4` and 8 against `stock-6`, mostly downward.
- The bench marked the session FAIL at the closing stock-return gate, which hard-coded 13 points
  (E2 has 12). That is a tool defect found here, fixed in `8263896`, and the scorer's own
  stock-return figure above replaces the gate.
- **Contrast:** NVML offsets on the 5060 Ti moved its suite optimum (§7, revised scoring).
  Architecture, offset method and grid all differ between the two, so nothing here says which one
  matters. One chip, one session, one offset size.

**⛔ Corrections to the Result above, 2026-09-28, after an outside audit (GPT Job 31,
`docs/gpt-findings/2026-09-28-sessione-e2-audit.md`).** The verdict, the scoreability checks and
every number reproduced. The descriptive text did not; it is corrected here rather than rewritten:
- ~~"the curve mattered, by less than one 105 MHz grid step"~~ is unsupported. Two offset workloads
  peak at the lowest sampled target, so no sub-grid bound exists. Say instead: *the offset changed
  the measured efficiency profile but did not move the registered median optimum on this 105 MHz
  grid; the displacement of any continuous optimum is unresolved.*
- The 855 MHz rise is **relative to each workload's own peak**. In absolute terms the offset is
  2.1–2.6% **less** efficient there than stock.
- Both per-workload counts (10 and 8) **exceed** the stock pair's 6. The Result's sentence is right
  only in that the registered statistic is the median, which did not move.
- The §7 contrast must say both halves: §7's **registered verdict was INVALID**, and only a post hoc
  revised scoring gave the falling 1545 / 1395 / 1237 MHz ladder.
- 4d's "both temperature and the curve contribute" is the registered reading of PARTIAL, not an
  isolated cause: direction, thermal history and driver all differ, one sweep each way.

## 5. RTX 5060 Ti: do isolated throughput losses come from ACTIVITY? Registered 2026-09-22 — COLLECTED 2026-09-23, ⛔ INCOMPLETE; RE-COLLECTED 2026-09-24, ✅ NOT SUPPORTED FOR THIS PROXY

**Why.** On 2026-09-22, three stock `4i` replicates lost 8–11% at isolated points: **4, then 2, then
0** degraded points, while the driving agent went from busy to silent. An outside audit
(`docs/gpt-findings/2026-09-22-5060ti-session-results-audit.md`) found that **agent activity, run
order and time since a cold start all changed together**. The data cannot say which mattered, and
"replicate and take the maximum" rests on the answer.

**Design, fixed before collection.** Runner `tools/hwinfo-logging/experiments/Run-ActivityAB.ps1`,
scorer `analysis/score_activity_ab.py`, both committed with this entry.

- Stock Profile 3, verified by memory clock under load. `gemm`, 1380–1760 MHz, 13 points,
  ascending: the grid the losses were found on.
- **Warm-up removed:** the run waits for **30 minutes of uptime**, then does **two throwaway
  warm-up sweeps, excluded from scoring**.
- **Order balanced:** **S A A S × 3**, giving 6 silent and 6 active runs, so a linear time trend
  cancels.
- **Only activity differs.** Active runs start `Start-ActivityLoad.ps1` once the GPU is under
  load. It is a logged proxy for the agent's work: `nvidia-smi pmon` every 5 s, plus a 2 s CPU
  burst and a full-screen capture every 15 s. Both conditions do identical load-detection polling.

**Scoring, fixed now.**
- Envelope: the best throughput at each target across the 12 scored runs.
- Degraded point: **more than 2% below** the envelope.
- D_A and D_S are the degraded-point totals in active and silent runs.

| outcome | rule | meaning |
|---|---|---|
| **activity supported** | D_A ≥ D_S + 4 **and** ≥ 3 of 6 active runs hit | the proxy reproduces the losses on a warm card, with order balanced |
| **not supported for this proxy** | D_A ≤ D_S + 1 | the scripted activity adds nothing. ⚠️ It does **not** clear real agent activity, which also streams into an app window |
| inconclusive | anything between | report both totals, no verdict |
| other cause | D_S ≥ 3 | losses occur in silence on a warm card |
| none at all | D_A + D_S = 0 | cold start and real activity are still **not separated** |

**Prediction, made now:** **activity supported.** The 2026-09-22 losses fell as activity fell, and
did not track temperature.

⛔ **If a threshold proves wrong after the data exists, report the registered verdict AND the
revised one, never only the revised one.** One chip, one session, a scripted proxy.

**To run:** Raymond opens HWiNFO and its Sensors window, which needs UAC. Then, from an elevated
shell: `powershell -ExecutionPolicy Bypass -File tools\hwinfo-logging\experiments\Run-ActivityAB.ps1`
(~85 minutes plus the uptime wait). The driving agent stays silent until it exits.

### ⛔ Revised BEFORE collection, 2026-09-22 — five defects fixed; design and thresholds unchanged

An outside preflight review (`docs/gpt-findings/2026-09-22-activity-ab-preflight.md`) found five
defects. Each was reproduced here before fixing. **Two of them could have produced a wrong
registered verdict:**

1. **An exact 2% tie counted as degraded.** `100 × (1 − 98/100)` is 2.0000000000000018 in floating
   point. Four ties could print "SUPPORTED". "More than 2%" is now tested without subtraction.
2. **An active run was scored without proof that the activity ran.** A dead generator would have
   turned "active" into silent, and could have produced a false null. The generator now logs its
   start, every action's success, and its reason for stopping. The scorer requires that log to cover
   the sweep with no gap over 15 s, or the run is invalid.
3. **The stock gate was one-sided.** It accepted any lower memory clock. It now requires 13801 ± 200
   MHz and a 180 W power limit.
4. **An incomplete collection still printed a registered verdict.** It now prints **INCOMPLETE — NO
   REGISTERED VERDICT** unless two warm-ups and twelve valid runs exist in S A A S × 3 order.
5. **The grid was not validated** and blocks used the post-exclusion index. Every run must now carry
   the registered 13 points, and blocks follow the recorded order.

The generator is also stopped in a `finally` block, its time limit went from 15 to 20 minutes, the
exact sweep CSV path is recorded per run, and the uptime and block counts are constants rather than
parameters. **12 synthetic checks** in `analysis/test_score_activity_ab.py`; the tie check was
confirmed to fail on the old comparison. **No threshold, condition or prediction changed.**

### ⛔ Result, collected 2026-09-23 — INCOMPLETE, NO REGISTERED VERDICT

`data/frequency-sweeps/5060ti-activity-ab-20260923/`. Nothing above was edited. All 14 sweeps ran
(two warm-ups, then S A A S × 3), uptime gate met, stock verified, every wrapper exit 0.

**The registered scorer withholds its verdict:** in **3 of 6 ACTIVE runs (03, 06, 11)** the generator
started **0.1–0.2 s after** the first measured window opened, so activity is not proven across that
window. Every other validity check passed. The cause is the runner's load trigger: it waited for GPU
utilisation ≥ 50%, which in those three runs was the sweep's own first point. **The rule is not
relaxed after the fact.** A re-run should start the generator before the sweep.

**Descriptive only, and labelled as such:** there were **zero degraded points in all twelve scored
runs, active and silent, and none in either warm-up**. The worst point anywhere is **0.14%** below the
envelope, against 8–11% on 2026-09-22. That is the same whether the three late runs are excluded or
included. Had the collection been complete, the rules above would have printed *NOT SUPPORTED FOR THIS
PROXY* and *no losses at all*. **That is a counterfactual, not a result.**

It points away from this proxy and toward the cold start, or toward some part of real agent activity
the script does not imitate. It does not separate those two. ⚠️ One chip, one session.

### ⛔ Revised BEFORE re-collection, 2026-09-24: one change, the generator trigger

**No re-collection data exists as of this amendment.** Nothing above, the 2026-09-23 result
included, is edited.

**The only change:** an ACTIVE run's generator now starts when the sweep wrapper's HWiNFO log file
appears, instead of when GPU utilisation first reaches 50%. The wrapper creates that file only
after its preflight passes and before the sweep begins. HWiNFO's own growth check then takes several
seconds, so the generator is running before the first measured window. SILENT runs wait for the
same file and start nothing, so the waiting is identical in both conditions.

**Unchanged:**
- the design (two warm-ups, then S A A S × 3);
- the grid, the uptime gate and the stock checks;
- the generator itself;
- the scorer, `analysis/score_activity_ab.py`, and every threshold in it.

The scorer's rule that an active run is invalid if its generator started after the first measured
window still applies, and now should never trip.

⚠️ **This re-run is not blind.** The 2026-09-23 collection is known to show zero degraded points in
every run, active and silent. That is a descriptive result without a registered verdict, and it
could shape how this one is read. So this re-run is reported **with its own registered verdict,
beside** the 09-23 INCOMPLETE, never merged with it. It runs on 2026-09-24 with the operator absent
and the driving agent idle. HWiNFO was started by `tools/hwinfo-logging/Start-HwinfoSensors.ps1`,
not by hand.

### ✅ Result of the re-collection, 2026-09-24: registered verdict NOT SUPPORTED FOR THIS PROXY

`data/frequency-sweeps/5060ti-activity-ab-20260924/`. Nothing above was edited. All 14 wrapper runs
exited 0, stock was verified, and uptime was 146–206 min.

- **Every active run is valid.** Each generator started 22.0–22.4 s before its first measured
  window. The trigger fix worked.
- **Zero degraded points in all 12 scored runs, active and silent.** The scorer printed:
  *NOT SUPPORTED FOR THIS PROXY — the scripted activity does not add losses*, and *no losses at all*.

It matches the 2026-09-23 counterfactual, and is now a registered verdict rather than a description.
⚠️ **It still does not separate a cold card from real agent activity** as the cause of 2026-09-22's
losses: the proxy is not real activity. One chip, one session.

---

## 6. RTX 5060 Ti: does the load floor survive an NVML clock offset? (worklist 4c) Registered 2026-09-22 — ✅ COLLECTED, HOLDS

**Why.** Guerreiro et al., TPDS 2019, report that voltage shows two regions (constant, then rising)
when the frequency is changed through NVML, but that *"the voltage stays constant across all
frequencies"* when it is changed through clock offsets. Their offset path was `nvidia-settings` on
Maxwell/Pascal/Kepler. **If it holds for `nvmlDeviceSetClockOffsets` on Blackwell, the planned
offset-validation pair (4d) compares two different machine states and validates nothing.**

**Design, fixed before collection.** Runner: `tools/hwinfo-logging/experiments/Run-OffsetPrecondition.ps1`.
Tool: `tools/nvml-offset/Set-NvmlClockOffset.ps1`, which accepts negative offsets only and verifies
each write by reading it back. Stock Profile 3, verified by memory clock. `gemm`, ascending,
**1000–1700 MHz, 15 points, 50 MHz apart.** Runs **A1** (no offset), **B** (**−300 MHz**
P0 graphics offset), **A2** (offset reset to 0, verified). One HWiNFO log per run, at 0.50 s.
The operator is present for the first write.

⛔ **The grid differs from the worklist's 1380–1760, deliberately.** A −300 MHz shift should move the
floor end from ~1570 to ~1270, below that band, so that band could not tell "two regions, shifted"
from "no floor". And 300 MHz is six steps of 50, so B at f pairs with A at f+300 on the same grid.

**Prediction: the offset shifts the V/F curve.** B shows **two regions**: 0.720 V held, then rising.
Its floor end sits within one grid step (50 MHz) of **~1270 MHz**, the A floor end of 1567–1575
minus 300. Equivalently, **B's voltage at target f equals A1's voltage at f+300 within one 5 mV
code**, wherever f+300 is on the grid.

**Refuted by:**
- **B's voltage constant across the whole band.** That would be Guerreiro's offset behaviour. Then 4d
  is cancelled and this gets written up as a Blackwell confirmation of their finding.
- B has two regions, but its floor end is not within 50 MHz of ~1270.

**Registered as OPEN, with no prediction:** whether a locked clock still achieves its target under
the offset, or the lock target itself shifts by 300. The achieved-clock column answers it. Either
way the voltage comparison above is made at achieved clock.

**Validity:** A2 must match A1, with voltage within one 5 mV code at every point and throughput
within ~1%. Otherwise the session drifted, or the reset did not take, and B is not interpretable.
The offset is reset in a `finally` block and read back, whatever happens.

### ✅ Result, collected 2026-09-22 — THE PREDICTION HOLDS

`data/frequency-sweeps/5060ti-nvml-offset-20260922/`. Nothing above was edited.

| registered | measured |
|---|---|
| B shows two regions | ✅ 0.720 V through **1245** achieved, rising from **1290** |
| floor end within 50 MHz of ~1270 | ✅ **1245–1290** |
| V_B(f) = V_A1(f+300) within one 5 mV code | ✅ **≤2 mV** at all 8 on-grid pairs, and **≤3 mV** at 8 pairs against the 09-22 morning stock run |
| *open:* does the lock hold under the offset? | **Yes.** Every point held; achieved clocks within 7.3 MHz of A1 |
| validity: A2 matches A1 | ✅ voltage identical at all 15 points, throughput within 0.78%, reset verified |

**Refutation did not occur:** B's voltage is not constant across the band. ⚠️ One run per condition,
one offset (−300), one workload, one chip. 4d is superseded; its criterion could not hold as worded
(see CLAUDE.md).

⛔ **Two wordings above narrowed the same evening by an outside audit** (`docs/gpt-findings/2026-09-22-5060ti-offset-4c-adversarial-audit.md`);
the verdict is unchanged. **"≤2 mV / ≤3 mV"** interpolated between 5 mV codes. The accurate form is
**identical VID codes at 9 of 9 six-step pairs**. And 4d's criterion is **not a valid prediction**
(retire it), but "superseded" overstates: its wider machine-state question is still open.

## 7. RTX 5060 Ti: does an NVML offset ladder relocate the suite optimum? (worklist 4o) Registered 2026-09-22 — COLLECTED 2026-09-23: registered verdict ⛔ INVALID; revised ✅ all hold

**Why.** 4c showed that a −300 MHz offset moves the 0.720 V floor end from 1567–1575 to 1245–1290,
on **one workload**. This asks whether the **twelve-workload median optimum** follows the floor
when the offset is changed, with no Afterburner slot and no hand-built curve. ⚠️ The curve-shift
mechanism is prior art (170tune, `RELATED-WORK.md` §10). This tests a **predictive rule on one
chip**, not the mechanism.

**Drafted by GPT (Job 10), reviewed and changed before registration.** Draft and review:
`docs/agents/DRAFT-offset-ladder-registration.md`. ⛔ **The draft's −450 rung is DROPPED.** Its
prediction, 1237, is the same grid point as −300's, so it could confirm nothing. **A closing stock
suite replaces it**, as a drift bracket. Chosen by Raymond, 2026-09-22.

**Design, fixed before collection.** Runner: `tools/hwinfo-logging/experiments/Run-OffsetLadder.ps1`.
- Apply stock Profile 3 **before** any offset. Verify memory at 13801 MHz under load and the power
  limit at 180 W enforced / 180 W default.
- **Four suites in this order: 0 / −150 / −300 / 0 MHz**, set with `Set-NvmlClockOffset.ps1`, each
  write verified by read-back. The offset is reset to 0 in `finally` and read back.
- Each suite runs the twelve standard workloads in a fixed order (`copy` … `gemm`). Each sweep is
  ascending, **13 points, 1237–3090 MHz**, with the iteration counts from
  `5060ti-stock-repro-20260922`. **48 sweeps, ~4 h** (one stock suite took 57 min on 09-22).
- HWiNFO logs at 0.50 s, one log per sweep, with the machine quiet and unattended.

**Statistic.** For each workload, take the target with the highest efficiency (timed throughput
over windowed mean power). The **ordinary median of the 12 target optima** is the statistic; a 6/6
split whose median falls between two grid points is **not** rounded. Per-workload optima are
reported but not scored, because two identical stock suites agreed on only 9 of 12.

**Predictions:** floor end 1567–1575 minus the offset, then the nearest grid target.

| suite | predicted floor end | **predicted median** | what a pass can show |
|---|---:|---:|---|
| opening 0 MHz | 1567–1575 | **1545** | baseline |
| −150 MHz | 1417–1425 | **1395** | 🔑 **the only interior test.** 1395 sits between 1237 and 1545, so a pass locates the move |
| −300 MHz | 1267–1275 | **1237** | ⚠️ **edge-limited.** 1237 is the lowest grid target, so a pass fits any optimum at or below ~1316 MHz. It shows a move of at least two steps, **not** a move to ~1270 |
| closing 0 MHz | 1567–1575 | **1545** | drift bracket, not a prediction |

**Refuted by**, per rung: any other median for opening 0, −150 or −300, including a between-grid
median from a 6/6 split. **Trend:** the medians must not increase from 0 to −150 to −300. An upward
step refutes the trend even if a rung passes.

**Validity, separate from refutation:**
- **Drift bracket.** The opening and closing stock medians must be **equal**. If they differ, the
  session drifted and **no rung is scored**. That is reported as uninterpretable, never as a pass or a
  null. Two identical stock suites on 09-22 both gave 1545.
- Every sweep must be complete, with no failed benchmark or missed lock. Each must carry the
  registered grid and iteration count, stock memory and power, one driver across all 48, and **its
  own** time-joined voltage extract.
- The runner's console log must show every offset read-back and the final reset. The CSVs cannot
  prove them.

**Limits, stated now.** One chip, one suite per rung, one session. Twelve workloads are repeated
outcomes on one card, not twelve chips. The reported voltage is a VID lookup, not rail voltage. A
global offset shifts the **whole** curve, unlike the Afterburner rungs, which edit only the floor
region. So agreement between the two ladders would show a shared predictive rule, not the same
electrical state. The grid cannot locate any optimum below 1237.

**Scorer:** `python analysis/score_offset_ladder.py <results-directory>`, after running
`join_hwinfo_voltage.py --join-by time` on each sweep against its own log.

### Result, collected 2026-09-23 — registered verdict INVALID; revised scoring reported beside it

`data/frequency-sweeps/5060ti-offset-ladder-20260923/`. Nothing above was edited. 48 of 48 sweeps
exited 0, and all five offset writes and the final reset were verified by read-back in the console log.

⛔ **Registered verdict: INVALID, by an error in this registration.** "Every sweep must be complete,
with no … missed lock" can never be met on stock: 2932 and 3090 MHz are unreachable, and the stock
suites this design was built from miss them in **24 of 24** sweeps. The scorer also required ±15 MHz
where the sweep tool defines a held lock as ±30, and checked stock memory with the average column
instead of the maximum. The maximum reads 13801–14001 at all 624 points, so memory was stock
throughout. **All three were found after collection and before any median was computed.**

✅ **Revised scoring, POST HOC** (`--revised`): keep rows that missed **below** target, use the tool's
±30 MHz, and invalidate any sweep whose optimum is a missed-lock row. None was.

| registered | measured (revised) |
|---|---|
| opening 0: median 1545 | ✅ **1545**, 10 of 12 |
| **−150: median 1395** (the interior test) | ✅ **1395**, 9 of 12 |
| −300: median 1237 (edge-limited) | ✅ **1237**, 10 of 12 |
| drift bracket: closing = opening | ✅ **1545 = 1545** |
| trend non-increasing | ✅, strictly dropping |

The `gemm` voltage column moves one grid step per −150: the last 0.720 V point runs 1537 → 1387 → 1230
MHz achieved, and the two stock suites read identically. ⚠️ **One chip, one session, one suite per
offset.** −300's pass is edge-limited; only −150 locates the move. **Report both verdicts, always.**

## 8. 3070 Ti: a second Edit 1 suite, plus two fine-sweep checks. Registered 2026-09-23, before collection — COLLECTED 2026-09-24: 8a ✅ PASS, 8b ⛔ FAIL, 8c reported

**No data for any part of this section exists as of registration.** The 3070 Ti's shakedown
(2026-09-23 21:56) and C8 are the only data collected on this card since Amendment 2. Session D's
four registered suites have not run. These runs go on the end of the same unattended session, on
2026-09-24, **after `stock-4` closes the registered bracket**, so nothing here can change how
§4a/§4b are scored. The card is sold in about two days; there will be no later chance.

**Order in the session:**
1. `stock-4`, which is the end of §4a/§4b;
2. the stock fine pair (8c);
3. the Edit 1 fine sweep (8b);
4. `edit1-5`, the replicate suite (8a);
5. `stock-6`, its closing stock suite;
6. cleanup.

Profiles, grid, iterations and labels are those of Session D. The new labels are `rtx3070ti-sessiond-edit1-5`,
`-stock-6`, `-finefloor-asc2`, `-finefloor-desc2` and `-edit1-finefloor`.

### 8a. The replicate: `edit1-5` against `stock-4` and `stock-6`

> **The median suite optimum of `edit1-5` lies in 1170–1275 MHz inclusive**, the same bins as the
> runsheet's §4a prediction, scored by the same rule as `analysis/score_session_d.py` applies to
> `edit1-2`.

**Scoreable only if:**
- `stock-6`'s median equals `stock-4`'s;
- no workload's median absolute throughput change from `stock-4` to `stock-6` exceeds 1.5%;
- the Edit 1 floor check passes on `edit1-5` exactly as it does for `edit1-2`: no clock above
  1200 MHz, within the scorer's tolerance, reads ≤0.825 V, and every target above 1200 reads
  ≥0.831 V.

If any of these fails, the replicate is **NOT SCOREABLE**, not a failure.

**How to report it:**
- ⛔ A median at or above `stock-4`'s is **no movement, and it counts against the replication**.
- If `edit1-2` and `edit1-5` disagree, **report both**. Neither supersedes the other, and there is
  no averaging to a verdict.
- `edit1-5` is n=2 on one chip, one session. It is not a second chip.
- ⚠️ **Its stock bracket is not the design's own.** `stock-4` precedes it after ~25 min of fine
  sweeps, and `stock-6` follows it. Edit 2 is not repeated, so **§4b's control is not replicated.**

### 8b. Where Edit 1's floor ends, measured directly

**The prediction is read from the decoded curve** (Amendment 2):
- a descending locked `gemm` sweep on P2, **1050–1590 MHz, 13 points**, reads ≤0.825 V at every
  target ≤1200 MHz;
- it reads **≥0.831 V at every target above 1215 MHz**;
- at locked **1395 MHz** it reads **0.835–0.870 V**, as the shakedown's 0.850 did.

⛔ **Floor-band voltage above 1215 MHz refutes the as-built reading of Edit 1**, and would call
`edit1-2`'s floor check into question as well.

### 8c. Stock fine pair, ascending then descending. EXPLORATORY: no prediction

It uses the same grid as C8: 1200–1590 MHz, 10 points, `gemm`, 120 iterations, stock P1.

C8 on 2026-09-23 (descending) read **1.1–1.3% below** the 2026-08-27 sweep (ascending) at every
point. Direction and day are confounded in that pair. This pair puts both directions in one
session, and it is reported as the per-point difference, **with no verdict.** ⚠️ It runs after
~5 h of load, so it is warm from the start in both directions, unlike either earlier sweep.

### Results, collected 2026-09-24 — 8a ✅ PASS, 8b ⛔ FAIL, 8c reported

Data: `data/frequency-sweeps/rtx3070ti-sessiond-20260924/`. The 8a scorer was committed while
stock-4 was still collecting (`97a463a`), before any 8a data existed.

**8a ✅ PASS.** `python analysis/score_session_d.py <dir> --replicate`:
- `edit1-5` median optimum **1170 MHz**, inside 1170–1275;
- stock-4 and stock-6 medians are both **1485 MHz**;
- the worst workload's stock-4 → stock-6 change is **1.192%** (limit 1.5%);
- the Edit 1 floor check passes on `edit1-5`.

Reported beside `edit1-2`'s 4a result (**1222.5 MHz**, PASS): the two agree, and neither supersedes
the other. **n = 2 on one chip, one session. The control (4b), which failed, is not replicated.**

**8b ⛔ FAIL: floor-band voltage above 1215 MHz.** Descending locked `gemm` on P2, 1050–1590 MHz:

| target MHz | 1050–1185 (4 points) | **1230** | 1275 | 1320 | 1365 | 1410 | 1455 | 1500 | 1545–1590 |
|---|---|---|---|---|---|---|---|---|---|
| V | 0.819 | **0.819** | 0.838 | 0.844 | 0.850 | 0.850 | 0.856 | 0.863 | 0.869 |

- The first two conditions hold: ≤0.825 V at every target ≤1200 MHz, and the locked-1395 MHz witness
  read **0.850 V**, inside 0.835–0.870.
- **The second fails at 1230 MHz, which reads 0.819 V.** Edit 1's floor ends between **1230 and
  1275 MHz**, not at the as-built reading's 1200. As registered, this **refutes the as-built reading
  of Edit 1** and calls `edit1-2`'s floor check into question. That check passed on the suite grid,
  which has no point between 1170 and 1275, so it could not see 1230. It is the decoder hazard
  CLAUDE.md records: never trust `base + offset` where the offset changes.
- ⚠️ **It does not change how 4a or 8a were scored.** Their registered bins are 1170/1275, and 1170
  is still the highest suite grid point on the floor. But the floor end the predictions assumed was
  wrong by 30 to 75 MHz.

**8c, exploratory, no verdict.** Stock, `gemm`, 1200–1590 MHz, 10 points, in one session:
- **descending minus ascending averages +0.00%**, ranging −0.06% to +0.10%, at 57–60 °C in both;
- **C8 (descending, 2026-09-23) sits 0.64% below both**, −0.57% to −0.72% at every point.

So C8's 1.1–1.3% gap to the 2026-08-27 ascending sweep was **between days, not between
directions**. That matches the ~1.47% cross-session drift CLAUDE.md records on the 5060 Ti.

## 8d. 3070 Ti: the negative control, repeated. Registered 2026-09-25 00:40, before collection — AFTER 4b failed — COLLECTED 2026-09-25: ⛔ NOT SCOREABLE (grid moved); descriptively the control held

**Written after 4b's result was known, and it says so.** That is why it cannot change 4b. **4b
stays FAIL whatever this shows.** It asks one thing: does the control's move repeat?

**Why it is worth the card's last day.** 4b failed at **1432.5 MHz**, a six-six split between the
1380 and 1485 bins. Identical stock suites disagree on 3–4 of 12 per-workload argmaxes, and the
control was never replicated (§8a notes this). One repeat separates "the control moves the optimum
on this chip" from "a near-miss on a noisy median". It does not test whether Edit 2's lowered
825 mV point is responsible; that needs a different curve, and there is no time to build one.

**Design.** A new session, **Session D2**, on the same card:
- SILENT BIOS, and the same Afterburner store, pinned by the `[Profile1]`–`[Profile3]` section hash
  `A1159941DA541EB9`;
- the same grid, iterations and workloads as Session D;
- **three suites, in order:** `stock-7` (P1) → `edit2-8` (P3, Edit 2 unchanged) → `stock-9` (P1);
- labels `rtx3070ti-sessiond-stock-7`, `-edit2-8`, `-stock-9`.

It is scored by `python analysis/score_session_d.py <dir> --control-replicate`, committed before
collection. The rules are 4b's: the six clipped targets form one median-efficiency bin, and the
optimum is scored on the target grid.

> **The median suite optimum of `edit2-8` lies in 1485–1500 MHz inclusive**, 4b's prediction,
> unchanged.

**Scoreable only if:**
- `stock-7`'s median is **1485 MHz**, the registered baseline, and `stock-9`'s median equals it;
- no workload's median absolute matched-target throughput change from `stock-7` to `stock-9`
  exceeds **1.5%**;
- the control floor check passes on `edit2-8` exactly as it does for `edit2-3`.

Otherwise the result is **NOT SCOREABLE**, not a failure.

**How to report it:**
- **PASS:** "4b failed and its repeat passed. The control's move did not repeat. With one of each,
  there is no verdict on the control; the attribution stays unestablished on this chip." ⛔ **Never
  write this as the control holding.**
- **FAIL:** "the control moved twice. On this chip, changing the curve above the floor moves the
  optimum, and the floor-region attribution fails."
- Report it beside 4b, with no averaging. n = 2 control suites on one chip, on two days.
- `stock-7` against Session D's stock suites is descriptive only: a different day, with the
  ~1.5% cross-session drift this project measures.

### ⛔ Result, collected 2026-09-25 — NOT SCOREABLE: the grid was not Session D's

Session D2 ran 08:22–11:43 untouched and ended PASS. **The pre-committed scorer refused it:** the
top six targets were **1605–2130 MHz**, not Session D's 1590–2115. The seven lower targets match
exactly. The card's supported-clock table had 116 entries on Friday against 115 on Thursday; its
cause is unknown, and the same card swept 852–2130 on 2026-09-04. §8d registered Session D's grid,
so **8d is NOT SCOREABLE, not a failure, and 4b stays FAIL.** The scorer was not changed after the
data was seen.

**Descriptive only**, with the registered rules and the collected grid (the six clipped targets as
one bin):
- stock-7, edit2-8 and stock-9 medians are all **1485 MHz**;
- the worst workload's stock return is 0.563%;
- the control floor check passes on all 12.

Had the grid matched, this would read as a pass. **On this chip the control moved once (1432.5,
Session D) and held once (1485, Session D2), on consecutive days. That is a description of two
runs, not a verdict.** Lesson: a registration on this card must name the target list, because the
tool derives it from a table that changes. `data/frequency-sweeps/rtx3070ti-sessiond2-20260925/`.

## 9. RTX 5060 Ti: is the `reduce` residual a workload property or a run-order artifact? (worklist 4m) Registered 2026-09-24, before collection — ✅ COLLECTED THE SAME DAY: WORKLOAD PROPERTY

**No data for this section exists as of registration.**

**Why:** the curve predictor misses all 16 `reduce` curves, every one ABOVE the prediction. Across
twelve committed suites, stock runs put `reduce`'s optimum at 1702 or 1852 against the rule's 1545.
But 14 of the 16 `reduce` legs ran in the same suite position, second, straight after `copy`. The
two explanations predict different things:
- **a workload property** gives the same offset wherever `reduce` runs;
- **an order artifact** gives an offset that follows its position.

**Design:**
- stock Profile 3, verified by memory clock and power limit before the first sweep;
- the suite grid, 1237–3090 MHz, 13 points, ascending;
- the suite iteration counts from `5060ti-stock-repro-20260922`: `copy` 2660, `reduce` 2870;
- eight sweeps in the fixed order **R C C R R C C R**. `reduce` runs **immediately after `copy`**
  twice (sweeps 4 and 8) and **not after `copy`** twice: sweep 1 follows the stock checks and
  sweep 5 follows `reduce`. The balanced order cancels a linear drift;
- labels `5060ti-4m-NN-<workload>`.

**Scoring:** a run's optimum is the grid target with the highest throughput per watt among rows
whose lock held, as the suite analysis defines it.

| outcome | reading |
|---|---|
| all four `reduce` optima **above 1545** | **workload property**: the residual belongs to `reduce` |
| both not-after-copy runs **≤ 1545**, both after-copy runs **above** | **order artifact**: every per-workload residual in the project is suspect |
| anything else | **inconclusive**, reported as the four optima, with nothing more claimed |

⚠️ **The limits, stated now:**
- n = 2 per position, one chip, one session;
- "not after `copy`" mixes two histories (after the stock checks, and after `reduce`), and the
  suites ran `reduce` 1–2 minutes after `copy` on an already-warm card;
- `copy` is the only neighbour tested, so any other kind of order effect is not.

### ✅ Result, collected 2026-09-24: WORKLOAD PROPERTY

`data/frequency-sweeps/5060ti-reduce-order-20260924/`. Nothing above was edited.

**`reduce` optima:**
- 1702 (sweep 1, not after `copy`);
- 1702 (sweep 4, after `copy`);
- 1852 (sweep 5, not after `copy`);
- 1702 (sweep 8, after `copy`).

**All four are above 1545**, so the registered outcome is *workload property*. `copy` optima in the
same session were 1545, 1545, 1702 and 1545. The offset follows the workload, not its position.

⚠️ The curves are flat near the top: every runner-up is within 0.9–2.6% of its optimum. So "above
1545" held 4 of 4, but the exact bin (1702 against 1852) is not stable. n = 2 per position, one chip.

---

## 10. RTX 5060 Ti: the negative control, repeated in one session. Registered 2026-09-25, before collection — 09-25 NOT SCOREABLE; RE-COLLECTED 2026-10-01: ✅ PASS, under desktop load

**Why now.** On the 3070 Ti the above-floor control moved the optimum (§4b FAIL,
2026-09-24). The 5060 Ti's control, `repair-suite-p2-20260909`, has run **once**:
- it held its median (1537 MHz);
- 4 of 12 workloads moved against the stock bracket;
- it had no same-session bracket of its own configuration.

The paper's causal claim now rests on this card, so the control is repeated before anything is
built on it. ⚠️ **It is not the original registration.** That was a single P2 suite, scored against
the P5 legs and the stock suite of earlier sessions.

**Design.** One session, operator absent, driven from the agent's elevated shell through
`tools/hwinfo-logging/Invoke-LoggedSweep.ps1`, as the 2026-09-22 to 09-24 queues were.
- **P5 → P2 → P5**, three twelve-workload suites.
- P5 (split) and P2 (repair) are **identical below 800 mV** and differ by up to 570 MHz above it,
  with the same memory (+2500) and power limit (200 W). Stock is not in the bracket, so the
  comparison changes one thing: the curve above the floor.
- Store verified before collection: all five slots are identical, section for section, to
  `data/afterburner-profiles/5060ti-profiles-20260922-rungB/`. `[Profile2]`, `[Profile3]` and
  `[Profile5]` hash to `86F30A00…`.
- The original control's work exactly: grid 1236–3090 MHz, 13 points, ascending, with its
  iteration counts, which are taken from its sweep JSONs.
- Each slot is verified under load before its suite: memory 16301 MHz and power limit 200 W for
  both. P2 and P5 are told apart by the unlocked `gemm` peak clock. The 09-09 control put P2's top
  achieved clock ~84 MHz below P5's (2888 against 2972), so the witness requires **P5 ≥ 2935 MHz**
  and **P2 ≤ 2925 MHz**. Otherwise the run stops.

> **The median suite optimum of the P2 suite equals the median of each P5 suite**, on the target
> grid, per workload by `analyze_sweep.efficiencyPeak`. It is the same rule and the same statistic
> as §4b and §8d.

**Scoreable only if:**
- the two P5 suites have the **same median**;
- no workload's median absolute matched-target throughput change between them exceeds **1.5%**;
- every slot witness passed.

Otherwise NOT SCOREABLE, which is not a failure.

**Reporting, fixed now:**
- **The per-workload count of P2 optima that differ from both P5 optima is reported beside the
  verdict, always.** A zero median shift is never written as "nothing moved" (CLAUDE.md).
- **PASS:** "the 5060 Ti's control held its median again in a same-session bracket, with *k* of 12
  workloads moving."
- **FAIL:** "the 5060 Ti's control moved in a same-session bracket. With the 3070 Ti's §4b, an
  above-floor edit moved the optimum on both chips, and the floor-region attribution is not
  established on either."
- n = 1 chip; the twelve workloads are repeated outcomes on it.

**What it cannot settle:** the manipulation. The 5060 Ti's manipulation (`abba-20260908`) was found
in a run registered for a different prediction; rung B (§1) is its registered test.

### ⛔ Amendment, 2026-09-25, before collection: the slot witness is replaced

The peak-clock witness above came from the 09-09 locked sweeps and **does not separate the slots
unlocked**. It was measured before any suite ran:
- P5's unlocked `gemm` median was 2872 MHz (max 2925) and P2's 2835 (max 2887);
- the ranges overlap, and P5 never reached the registered 2935;
- a first P5 probe recorded no loaded samples at all.

The run would have stopped at its first check.

**The replacement is `gemm` power at a locked 2475 MHz**, where the decoded curves put P2 near
928 mV and P5 near 862 mV. It was measured A–B–A–B the same morning:

| probe | slot | median power | range |
|---|---|---|---|
| a | P5 | 151.8 W | 146.9–154.3 |
| b | P2 | 176.1 W | 170.8–178.8 |
| c | P5 | 152.9 W | 148.6–156.3 |
| d | P2 | 177.4 W | 171.3–180.7 |

**The witness requires P5 ≤ 163 W and P2 ≥ 165 W** (median of loaded samples after the first six).
These are thresholds between two measured clusters 14 W apart, set from these four probes and
recorded here with them. **Nothing else in §10 changes.** No suite had run.

### ⛔ Result, collected 2026-09-25 — NOT SCOREABLE: the P5 bracket did not return

`python analysis/score_control10.py data/frequency-sweeps/5060ti-control10-20260925`, with the
scorer committed before its data was read (`b2d83b9`):
- all three medians are **1545 MHz**;
- **the P5 return fails in 11 of 12 workloads, the worst by 7.57%** (limit 1.5%);
- P2's optimum differs from both P5 optima in **4 of 12** workloads.

**No verdict on the control, as registered.**

The closing P5 suite ran uniformly slower, from −8.5% at 1237 MHz to −4.5% at 3090, with raised
idle baselines. P2 matches the opening P5 suite within ±0.1% below 2010 MHz. That is the
contamination signature. **Its cause is not established:** Codex tool processes started at 13:43
and 13:47, and the closing suite began at 13:47:32, but nothing shows Codex used the GPU.
Descriptively, against the uncontaminated opening suite, P2 holds the median with 4 of 12 moving,
the same shape as 2026-09-09. Details are in the data README. ⚠️ **A re-collection would need the
Codex and ChatGPT apps closed**, and it would be registered as an amendment before collection, as §5
was.

🔑 **2026-10-03: the contamination signature is now measurable, and it sits on the failed leg.**
HWiNFO's "Framerate Presented" and "GPU Bus Load" flag **142 of 156** closing-P5 windows here,
against **35** in the opening P5 and **29** in P2 (`tools/hwinfo-logging/check_desktop_load.py`). An
ABA test the same day (`data/frequency-sweeps/5060ti-deskload-20261003/`) produced exactly that
signature, and a 6–9% `membw` loss, from **the Claude desktop app's visible window**, and removed it
by minimizing the window. So the visible Claude window is a demonstrated source of this signature;
that it was the source on 09-25 is likely but not shown, since nothing recorded the screen. The
opening suite is also not wholly clean (35 of 156 windows).

### ⛔ Amendment 2, 2026-09-30, before RE-COLLECTION: §10 is collected again, unchanged

**Nothing in the design, witness, scoreability rule, prediction or reporting changes.** The first
collection stands as recorded: NOT SCOREABLE. This registers a second collection, with the
conditions that most plausibly spoiled the first removed:
- **The ChatGPT/Codex desktop app is closed** for the whole run; the runner refuses to start otherwise.
- **The store is verified again, section by section:** `[Profile2]`, `[Profile3]`, `[Profile4]` and
  `[Profile5]` are byte-identical to `data/afterburner-profiles/5060ti-profiles-20260922-rungB/`,
  checked 2026-09-30. Only `[Profile1]` differs; it now holds curve 3 (§12), which §10 does not use.
- **It runs after §14 in the same unattended chain on 2026-10-01**, so it starts only after §14's
  runner has re-applied Profile 3 and reset the mVolt+ XBAR offset. The runner refuses unless
  `mVolt+ --status` reads every offset (XBAR, SYS, video, core, memory) as 0.
- **Same runner, same labels, same scorer.** `Run-ControlRepeat-20261001.ps1` is the 09-25 runner
  with only its log names, its `appliedSettings` text and those two checks changed; the diff is in
  the commit. Its sweeps go to `data/frequency-sweeps/5060ti-control10r-20261001/` and are scored by
  `analysis/score_control10.py`, unchanged since `b2d83b9`.

**The verdict reported for §10 is this collection's**, beside the first's NOT SCOREABLE. If this one is
NOT SCOREABLE too, that is reported, and no third collection is registered.

### Result — re-collected 2026-10-01 09:46–12:41: ✅ PASS, under a desktop load the amendment did not remove

```
python analysis/score_control10.py data/frequency-sweeps/5060ti-control10r-20261001
```

36 sweeps, every wrapper exit 0, 0 display-driver events, mVolt+ offsets all read 0 before the first
suite. **The P5 bracket returned: worst workload 0.635%** against the 1.5% limit (the first collection
failed by 7.57%). **P2's median optimum is 1545 MHz, equal to both P5 medians: PASS.**

| leg | median | per-workload optima |
|---|---|---|
| P5 opening (`p5a`) | **1545** | reduce 2010, softmax 1702, bgemm32 1702, gemm 1395; the other eight 1545 |
| P2, the control | **1545** | copy 1702, reduce 2167; the other ten 1545 |
| P5 closing (`p5b`) | **1545** | copy 1852, reduce 2167, softmax 1702, bgemm32 1702, gemm 1395; the other seven 1545 |

Reported with it, as §10 requires: **P2's optimum differs from both P5 optima in 4 of 12 workloads**
(`bgemm32`, `copy`, `gemm`, `softmax`). n = 1 chip; the twelve workloads are repeated outcomes on it.

⚠️ **The run was not quiet, and closing ChatGPT did not make it so.** HWiNFO records an unidentified
desktop load in **all 468 windows: 148–240 frames per second presented and 16–64% GPU bus load**
(per-window medians). It began at 09:46, when this queue started, and lasted until 14:03; the §14
session just before it was quiet. The P5 bracket returned within 0.635% under it. ⛔ *This said the
legs were "measured under it alike"; GPT Job 40 (verified) notes that equal P5 endpoints do not
exclude a load present only during P2, or one that interacts with the configuration.* **CLAUDE.md
records that desktop load depresses the low and mid band more than the top (§5.4.4)**, which is where
the optima sit, so absolute efficiencies from this run are not clean, and **the PASS is a
within-session comparison under contamination, not a clean replication**; it cannot exclude a shift
that clean conditions would show. The source is not identified; nothing in the run logs which window
was in the foreground.

Also from Job 40: `score_control10.py` reproduces every figure above independently, but **does not
verify the slot witness**; the committed runner log records it (gemm at a locked 2475 MHz: 142.3 W on
P5, 166.2 W on P2, 143.6 W on P5, inside the amended P5 ≤ 163 / P2 ≥ 165 W). P2 differs from the
opening P5 in 5 of 12 workloads, and the two P5 legs differ from each other in 2 (`copy`, `reduce`).

## 11. New cards: a stock protocol and the load-floor rule, registered before any card is known. Registered 2026-09-25

**Why now.** Raymond expects one or two more cards through the shop before publication, most
likely RTX 40- or 50-series; a 5060 Ti would be the **8 GB** variant. This section is written
before any of them is chosen, so neither the protocol nor the criteria can be fitted to the card
that turns up. That is stronger than every registration above, each of which knew its card.

**What runs**, unattended and **stock only**, from `tools/bench-app/catalog/newcard-rtx40-50.json`
(built by `build_newcard.py`):
1. calibration of the 11 suite workloads (`gemm` keeps its default 120);
2. a dense `gemm` floor sweep, **40–80% of the clock table's top, 25 points, ascending**;
3. the same sweep **descending**;
4. the 12-workload suite on the standard grid (40% to the top, 13 points), with the calibrated
   counts.

The engine refuses any profile, witness, hash gate or revert slot in this run list, and it checks
that the power limit is the card's default. **Stock rests on that check and on the card being a
fresh shop build.** ⛔ Do not run it on a machine with Afterburner or any tuning tool installed.

**Definitions, scored by `analysis/score_new_card.py` (committed with this section):**
- **Floor set** of a dense sweep: every target whose voltage lies within **0.003 V** of the
  sweep's lowest reading (under half a 6.25 mV code, as in the Session E amendment).
- **Each sweep is classified as one of:**
  - **FLAT_FLOOR**: the floor set is contiguous, includes the lowest target, has at least two
    points, and excludes the highest target. The **floor end F** is its highest target.
  - **NON_MONOTONIC**: the floor set is not contiguous, or it does not include the lowest target,
    so voltage falls *into* the minimum as on the 2060 Super. The rule is undecidable on the card.
  - **NOT_LOCATED**: the floor set holds only the lowest target (the floor ends at or below 40%) or
    includes the highest (it runs past 80%).

**11a, the rule.** *The median suite optimum lies within half a suite grid step of the floor
end.*
- **F** is the mean of the ascending and descending floor ends.
- **Pass window:** the median optimum M (target grid, `efficiencyPeak`, 12 workloads) must satisfy
  `|M − F| ≤ G/2`, where G is the suite grid's step.
- **Otherwise:** FAIL_BELOW or FAIL_ABOVE.
- **Scoreable** only if all of the following hold:
  - both sweeps are FLAT_FLOOR;
  - 11b agrees;
  - every file comes from one card, one driver, and the default power limit;
  - every dense-sweep point has a voltage reading.
- **UNDECIDABLE** if either sweep is NON_MONOTONIC. That is the 2060 Super's outcome, and it is
  reported as a result, not as a failure.
- ⚠️ **Known in advance, from the 5060 Ti's fine grid:** the efficiency peak can sit *below* the
  floor end on a curve that is flat there (CLAUDE.md, the predictor audit). So the scorer always
  reports **regret at the suite grid point nearest F**, mean and worst, beside the verdict. A
  FAIL_BELOW with small regret is the ridge-point statement holding and the "optimum is the floor
  end" framing failing. Say it in those words.

**11b, sweep direction.** *The ascending and descending floor ends agree within one dense-grid
step* (the larger of the two sweeps' median spacing).
- **AGREE** or **DIFFER**, scored only when both sweeps are FLAT_FLOOR.
- The two floor voltages are reported beside it and not scored. The 3070 Ti's Session D pair read
  0.812 and 0.819 V, one code apart, with the same 1500 MHz end.

**11c, descriptive, no verdict: if the card is an RTX 5060 Ti.**
- **Compared quantities:** its floor voltage and floor end, against this project's 16 GB unit
  (0.720 V, floor end 1567–1575 MHz).
- **The borrowed-floor error:** the grid point nearest 1571 MHz (the 16 GB unit's floor end, as if
  borrowed) against the new card's median optimum. That is the 3060-against-5060 Ti test (270 MHz)
  run within one die.
- ⚠️ **The two units are one die (GB206) with different memory capacity**, not one SKU. Leng et al.
  and Trakosa et al. already report per-chip Vmin offsets; this measures the load-floor voltage,
  which is related but not the same quantity.

**Every card is n = 1.** The twelve workloads are repeated outcomes on it.

### Amendment, 2026-09-28: 11c extends to the RTX 5060. Written before any new card is known

**No new card has arrived or been chosen**, so this is still written before any data from one.
Nothing above is edited. **Why:** a second RTX 5060 Ti may not be obtainable, and the RTX 5060 is
the other desktop GB206 card.

- **11c now covers any desktop GB206 card:** the RTX 5060 Ti (8 GB), as before, and the **RTX 5060**.
  The compared quantities and the borrowed-floor error are unchanged. It stays **descriptive, with
  no verdict**.
- ⚠️ **The RTX 5060 is a cut-down GB206: 30 of 36 SMs, 145 W against 180 W** (specs from
  `data/external/all-gpus.json`, which describes reference cards), on its own board. So a floor voltage or
  floor end that differs from the 16 GB unit's **cannot be attributed** to chip-to-chip variation
  alone: the die configuration and the power limit differ too. One that matches is still one card.
  The scorer labels the variant beside every 11c line so the two cases are never pooled.
- **11a and 11b are unchanged** and apply to the 5060 as to any new card.
- Scorer: `analysis/score_new_card.py`, `gb206_variant()`. Laptop GB206 parts are excluded; they are
  never bench cards.

### Amendment, 2026-09-29: 11a's half step is measured in grid steps. Written before any new card is known

**No new card has arrived, and no `newcard` file exists anywhere under `data/`** (checked by
`find data -iname "*newcard*"`, zero results), so this is written before any data from one.
Nothing above is edited.

**Why.** GPT Job 31 (`docs/gpt-findings/2026-09-28-sessione-e2-audit.md`) found that 11a's pass
window uses **one** G, the suite grid's **median** spacing, for every pair of points. The grid is
not guaranteed to be even in MHz: `Select-SweepFrequencies` in `Invoke-FrequencySweep.ps1` spaces
its 13 points evenly by **index into the card's supported-clock table**, so a table that is denser
in one range gives a grid that is uneven there. A single median spacing can then call a pair a pass
that is several local steps apart, or a failure that sits inside one wide interval.

**The rule, replacing only the pass window of 11a:**
- Map any frequency onto the sorted suite grid as a **fractional grid position**: its index, linear
  between the two grid points that bracket it.
- **PASS** if the median optimum M and the floor end F are **at most 0.5 grid positions apart**.
  Otherwise FAIL_BELOW (M below F) or FAIL_ABOVE, as before.
- On an evenly spaced grid this is **exactly** `|M − F| ≤ G/2`: nothing changes for a card whose
  grid is even.
- The scorer reports the window in MHz, which is asymmetric when the neighbouring intervals differ,
  and the gap in grid positions. **If the superseded median-spacing reading would give a different
  verdict, it prints that too**, so a disagreement is never silent. The verdict is the grid-position
  one.

**Unchanged, deliberately:**
- **11b** keeps "one dense-grid step (the larger of the two sweeps' median spacing)". It was
  registered in those words, and Job 31 raised only 11a's window.
- **The suite must still have 13 distinct targets.** Job 31 also noted that a 12-target suite is
  refused. The registration says 13 points, so a card whose table yields fewer is NOT SCOREABLE
  under 11a rather than scored on a different design. The scorer now also refuses duplicate
  targets explicitly.
- The regret report (at the suite grid point nearest F) and 11c.

**Tests:** `analysis/test_score_new_card.py`. It checks that the two readings agree on an even grid,
at every F in 7 MHz steps across the grid, for every grid point and every midpoint. It also pins one
case in each direction: a 300 MHz interval inside a grid with a 100 MHz median spacing (the new rule
passes, the old one failed), and a run of 20 MHz steps inside a 182 MHz median spacing (the new rule
fails, the old one passed). Putting the median-spacing rule back inside `score()` fails the suite.

## 12. RTX 5060 Ti: the `membw` plateau with memory matched (worklist 4j). Registered 2026-09-26, before collection — ✅ COLLECTED THE SAME DAY: PRIMARY HOLDS, voltage clause fails as worded

**Why.** The only committed pair with voltage and crossbar telemetry
(`membw-anomaly-20260819/…oc-volt-membw` against `…stock-volt-membw`) ran the flattened curve at
**16301** MHz memory and stock at **13801**. An outside audit (2026-09-18) named that the largest
confound in the plateau result. This removes it: **curve 3 is P4's curve exactly, with memory +0**,
so both arms run at 13801.

**Configuration, verified before collection.** Curve 3 is in Profile 1, snapshotted as
`data/afterburner-profiles/5060ti-profiles-20260926-curve3/` (curve file SHA-256 begins
`8ec197f30e21d116`). Its 127 stored points are identical to Profile 4's, memory +0 against P4's
+2500, power limit 111 (200 W) as on P4. Stock is Profile 3 (180 W).

**Design, one session:** stock `membw` → stock `gemm` → curve 3 `membw` → curve 3 `gemm` → stock
`membw` again. `membw` on the old pair's grid (1400–2100 MHz, 10 points, default iterations);
`gemm` on the suite grid (1237–3090 MHz, 13 points, 120 iterations). HWiNFO at 0.50 s; every sweep
joined by time.

**Interpretable only if** the closing stock `membw` sweep's band mean lies within **1.5%** of the
opening one. Otherwise the session drifted, and it is reported as uninterpretable.

**Predictions:**
- **Primary:** at every target from **1560 to 1867** MHz, curve 3's `membw` throughput is **below**
  the opening stock sweep's.
- **Mechanism, telemetry:** curve 3 reads **0.720 V** at every target from 1402 to 1867, and its
  crossbar clock stays within **1300–1360 MHz** over that range, while stock's crossbar rises with
  the core clock.
- **Secondary, `gemm`:** curve 3 draws **less** board power than stock at every matched target from
  1545 to 2625 MHz.

**Refuted by:** curve 3 at or above stock at any target from 1560 to 1867; or curve 3's crossbar
tracking the core clock across that range. **If the primary holds, the memory mismatch did not
create the plateau.** It still does not make XBAR a demonstrated mediator: that needs XBAR held
fixed at fixed core curve and memory, which this card cannot do.

**Limits, stated now.** One chip, one session, one sweep per arm. The power limits differ (200 W
against 180 W). Neither binds for `membw` below 2100 MHz, which draws well under 100 W, but stock
`gemm` can reach its limit near the top of the grid, so the `gemm` prediction stops at 2625. The
2026-08-20 "oc" profile is not proved identical to today's P4, so compare within this session, not
against the old pair.

### Result — collected 2026-09-26, the same afternoon

`data/frequency-sweeps/5060ti-memmatched-20260926/`. Memory max exactly 13801 at every point of all
five sweeps.

| registered | measured |
|---|---|
| **gate:** closing stock `membw` within 1.5% | ✅ **−0.41%**, interpretable |
| **primary:** curve 3 below stock at every target 1560–1867 | ✅ **HOLDS**, −7.6% to −13.7% |
| crossbar 1300–1360 on curve 3, 1402–1867, stock rising | ✅ 1312–1342; stock 1335 → 1800 |
| **0.720 V** on curve 3 at every target 1402–1867 | ⛔ **FAILS as worded**: 0.725 at 1402 and 1477, 0.7225 at 1560 |
| **secondary:** curve 3 `gemm` power below stock 1545–2625 | ✅ −3.5% to −22.7% (2625 not clock-matched: stock at its 180 W limit). ⛔ **Narrowed 2026-10-03 by §15 R1, measured clean: equal at 1545 (+0.13%), below from 1702.** The −3.5% at 1545 was measured beside the desktop load |

**No refutation occurred. The memory mismatch did not create the plateau.** The voltage clause fails
by one 5 mV code at the lowest targets, where **stock also reads 0.725** in this session, so it is not
a curve 3 property; curve 3's voltage stays flat while stock's rises to 0.805. **Not seen before
collection and not registered:** at 1477 both arms read 0.725 V while curve 3 is already 5.6% slower
with its crossbar at 1312 against 1410, so memory-matched data reproduces that the reported voltage is
not the state variable. A first launch refused at the curve 3 arm (20% SM straight after the arm's own
witness load) and its data is not used; the whole session was re-run.

## 13. RTX 5060 Ti: does the load-floor rule hold for LLM decode? Registered 2026-09-27, before collection — ✅ COLLECTED THE SAME DAY: decode HOLDS, prefill HOLDS

**Why.** The rule this paper credits to the ridge-point literature (Schoonhoven et al.) says running
below the voltage floor cannot improve efficiency, because performance falls with f while voltage
stays constant. That premise needs performance to fall with f. Memory-bound LLM decode may not:
Maliakel et al. (CCGrid 2026) report decode latency within ~1% from 180 to 2842 MHz on one RTX PRO
6000 Blackwell. This card's own memory-bound kernel follows the rule: `membw` peaks at target 1560
(achieved 1552), the grid point at the floor's edge (GPT Job 27, verified). Prior art:
`docs/gpt-findings/2026-09-26-llm-decode-floor-and-undervolt-prior-art.md`. **Neither outcome is
assumed; both are reportable.**

**Workload,** reviewed and committed before this registration (`0d8ced7`, `7f4d56a`):
`tools/frequency-sweep/llm_workload.py`.
- llama-bench build `d222767c7`, model `Qwen3-8B-Q4_K_M.gguf` (SHA-256 `d98cdcbd…5745785`).
- `llm-decode`: 256 generated tokens × 5 counted repetitions after 1 lead-in.
- `llm-prefill`: 512 prompt tokens × 200 counted repetitions after 15 lead-in.
- Batch 1, full offload, flash attention, f16 KV cache.
- Efficiency = tokens per joule of board energy.
- The stock smoke test showed decode memory-bound: 97% utilisation, ~373 GB/s of model reads,
  scaling with the memory clock.

**Configuration:** stock Profile 3 (180 W, memory +0), verified live by power limit 180 W and memory
13801 under load. NVML offset 0. HWiNFO at 0.50 s with every sweep time-joined.

**Design, one session:** decode ascending → decode descending → prefill ascending → prefill
descending. Grid **465–3090 MHz, 13 points**, the `floor15` grid (targets 465, 682, 900, 1125, 1342,
**1560**, 1777, 1995, 2212, 2430, 2655, 2872, 3090). **The rule's pick is 1560**: the grid point
nearest the measured stock floor end, 1567–1575 MHz achieved. ChatGPT, Codex and `llama-server`
closed.

**Definitions.** For each workload:
- E_asc(t) and E_desc(t) are efficiency at target t in each direction.
- E(t) is their mean.
- **d** = max over t of |E_asc(t) − E_desc(t)| / E(t), the session's own repeat noise.

**Interpretable only if:** both directions complete; every point `bench_ok`; memory max 13801 at every
point (memory at max under load was confirmed down to 465 MHz in the floor15 runs); and power limit
180 W throughout. Otherwise the result is reported as uninterpretable, not scored.

**Primary prediction (decode), the rule's:** **E(1560) is within d of the maximum of E over all
targets.**
- **HOLDS** if argmax E is 1560, or E(1560) ≥ (1 − d) · max E.
- **FAILS BELOW** if the maximum lies at a target under 1560 and exceeds E(1560) by more than d. The
  Maliakel-like outcome: report the target and the gain.
- **FAILS ABOVE** if the maximum lies at a target over 1560 and exceeds E(1560) by more than d.

**Secondary (prefill),** same rule and scoring. Compute-bound, so the rule is expected to hold. **If
prefill fails too,** the session or the workload is suspect rather than decode being special, and
that is reported.

**Descriptive, not scored:**
- decode and prefill throughput at 465 against 1560 (the elasticity);
- voltage at every target, including whether it stays at 0.720 V below 1560, which this card's data
  has never shown below 1378;
- where each workload's efficiency peaks, and how flat the curve is.

**Limits, stated now:**
- One chip, one session.
- One 8B Q4_K_M model at batch 1 on one llama.cpp build, with synthetic tokens.
- Board energy only, not the system.
- A ~218 MHz grid, so "at 1560" means within half a step of the floor end.
- **This tests the rule for one decode workload on one card.** It does not establish an LLM-wide
  optimum, and a FAILS BELOW would repeat Maliakel et al.'s direction on consumer silicon with a
  measured floor. It would not make that direction new.

### ⛔ Amendment, 2026-09-27 15:10, before collection: "memory max 13801" is wrong as worded

**No sweep has run.** The first launch (15:06) refused at the runner's stock witness, which read
**14001 MHz** under load against its 13801 ± 100 tolerance. The runner then reverted to stock and
read 13801. No sweep started and no data exists.

🔑 **14001 is stock, not an offset.** It is this card's other loaded memory state, already
documented in the repository:
- `5060ti-offset-ladder-20260923` reads a maximum of **13801–14001 MHz at all 624 points** at stock;
- `suite-replicate-r6-20260905` hit the same 14001 transient at preflight;
- `Collect.ps1` and `Invoke-SuiteReplicate.ps1` were widened to **±400 MHz** for this reason.

The one memory offset this card's slots carry, +2500, reads **16301**. §13 was written from the
floor15 runs, which read 13801, without checking the rest of the corpus.

**So, fixed before any data exists:**
- The interpretability condition "memory max 13801 at every point" becomes **"memory max within
  13801–14001 MHz at every point"**, stock's two loaded states. Any higher reading (a live offset)
  still makes the result uninterpretable.
- The runner's stock witness tolerance widens from ±100 to **±400**, the value `Collect.ps1` uses.
  It still excludes 16301.

**Nothing else changes.** The error entered the same way as the r6 one: a tolerance was copied
from the runs at hand, not from the card's documented states.

### ✅ Result, collected 2026-09-27 15:11–16:03 — decode HOLDS, prefill HOLDS

`data/frequency-sweeps/5060ti-q1-llm-20260927/`, scored by `python analysis/score_q1_llm.py`
(committed with the data, tested by `analysis/test_score_q1_llm.py`). All four sweeps completed, and
every interpretability condition held: every point `bench_ok` and windowed, driver 616.92 in both
directions, enforced limit 180 W, **memory max 13801 at every point** (the amendment's 14001 was
never reached).

| | argmax E, asc / desc / mean | E(1560) | d | verdict |
|---|---|---|---|---|
| **decode** (primary) | **1560 / 1560 / 1560** | 100% | 2.14% | ✅ **HOLDS** |
| prefill (secondary) | 1560 / 1560 / 1560 | 100% | 13.42% | ✅ HOLDS |

- Decode's neighbours sit at 95.2% (1342) and 94.8% (1777). So the peak is at the floor's edge by
  more than twice d, not a tie within noise.
- ⚠️ **Prefill's d comes from one point:** the first point of prefill ascending, 465 MHz, read 585
  tok/s against 709 descending, at matching power and temperature. **Cause not identified.** The
  verdict does not depend on d, because the argmax is 1560 itself.

**Descriptive, as registered:**
- **Elasticity: decode is not flat in core clock here.** It gives 22.1 tok/s at 465 against 60.3 at
  1560 (37%), and 76.4 at the top. So the rule's premise, that performance falls with f, holds for
  decode on this card. Maliakel et al.'s flat decode latency was on a different card, model,
  framework and batch. **This is a difference between setups, not a refutation.**
- **Voltage 0.720 V at every target from 465 to 1560, in all four sweeps**, first rising at 1777
  (0.770–0.780). This card's data had never shown the floor below 1378.
- Efficiency is flat within ~5% from 1342 to 1777, and falls to ~61% by the top of the grid.

**Limits, unchanged from registration:** one chip, one session, one 8B model at batch 1, board
energy only, and a ~218 MHz grid. ⚠️ **This extends the rule to one decode workload on one card.**
Maliakel et al. found the opposite behaviour on another setup, so the result depends on the setup,
and it is written that way.

## 14. RTX 5060 Ti: does the crossbar clock alone set `membw` throughput? (ROADMAP 5b) Registered 2026-09-30, before mVolt+ is installed — COLLECTED 2026-10-01: NOT SCOREABLE as registered; S FULL, C LIFTS, N LIFTS only in a post hoc memory-rule sensitivity analysis (audited, Job 40)

**Why.** The bandwidth plateau is an association (submission §5.4, long draft §5.7.3; §12 above).
The crossbar clock was observed, never set, so a domain that moves with it could be the cause.
mVolt+ (`b00nz/mVolt`, v0.47.3) documents an XBAR clock offset (`--xbar-offset`). The search
(GPT Job 37, `docs/gpt-findings/2026-09-30-xbar-direct-control-search.md`) found no one who has set
XBAR and measured memory bandwidth in GB/s, on any NVIDIA card.

**The basis, from data already committed (§12, `5060ti-memmatched-20260926/`), stated before any
new collection.** Across both arms of that session, `membw` follows the crossbar clock and barely
the core clock:

| arm | core target | XBAR (reported) | GB/s |
|---|---|---|---|
| stock | 1402 | 1335 | 309.0 |
| curve 3 | 1867 | 1342 | 311.2 |
| curve 3 | 1942 | 1395 | 322.6 |
| stock | 1477 | 1410 | 322.1 |
| curve 3 | 2025 | 1470 | 332.9 |
| stock | 1560 | 1485 | 333.8 |

At nearly equal XBAR the two arms agree within 1% although their core clocks differ by up to
465 MHz. That is still an association: both arms ran a shipped or edited curve, never XBAR alone.
**This registration turns it into three interventions.**

**Hardware and configuration.** RTX 5060 Ti (Zotac Twin Edge OC), the card of §12. Stock is
Profile 3 (180 W, memory +0); curve 3 is Profile 1 (P4's curve, memory +0, 200 W), as in §12. Snapshot
the profile store before the session, per the safety envelope. Memory must read exactly 13801 MHz
at every point. **The only new variable is mVolt+'s XBAR clock offset.** No mVolt+ voltage, ratio,
SYS, video, core, memory or power control is used, and none is changed from its default.

**Instruments.** HWiNFO at 0.50 s, joined by time. **The manipulation check uses HWiNFO's "GPU
Crossbar Clock (measured)" column.** `join_hwinfo_voltage.py` reads only "GPU Crossbar Clock [MHz]"
today, so it must also report the measured column before collection. §12's values above are the
reported column. `mVolt+ --status` JSON is saved before and after every arm. ⚠️ **HWiNFO shows no
SYS clock on this card.** If `--status` reports SYS, it is logged; if not, every result below is
"the XBAR offset request", with SYS unmeasured, and is written that way.

### Step 0: calibration, before collection, clocks only

Install, start read-only (`--version`, `--list-gpus`, `--status`), and save the output into the
repository. Then, with a load running and the core locked by `nvidia-smi -lgc`, set XBAR offsets
and read HWiNFO's measured XBAR. **Calibration may look at clocks, voltage and the mVolt+ status
only. Never `membw` or `gemm` throughput**, because seeing an outcome before collection would void
this registration. The load is any steady workload (`gemm` is fine), with its throughput not read.

- **C0a, the gate.** At offset 0, on stock at 1560 MHz, the reported and measured crossbar columns
  must agree within 15 MHz. If they do not, §12's numbers cannot be compared, and this registration
  is amended before collection.
- **C0b, transfer under a lock.** A −100 MHz offset at a locked 1560 MHz must move the loaded,
  measured XBAR by at least 50 MHz, then read back to within 15 MHz of the offset-0 value after a
  reset. **If it does not move under `-lgc`** (LACT PR 1158 reports exactly that for its RM path),
  the tests below are not run. Any other way of holding the core needs an amendment first.
- **C0c, choosing each offset.** For each arm below, choose the offset that puts the loaded, measured
  XBAR inside the arm's window at that target, in 25 MHz steps. Positive offsets go up by +50 MHz
  at a time and stop at the first driver reset. Record every offset tried.
- **C0d, side effects.** At each chosen offset, record the reported VID, core achieved and memory
  clock. If VID differs from offset 0 by more than one 5 mV code, that target is flagged
  **XBAR+VOLTAGE**: on this card the fabric reportedly shares the core rail (UNIKO, 2026-08-20).

### Collection: one session

Every arm is a single-target `membw` sweep (default iterations); `gemm` is single-target at 120
iterations. Between arms, reset the XBAR offset to 0, read it back in `--status`, and confirm that
HWiNFO's measured XBAR has returned. Order:

1. stock bracket A: `membw` at 1402, 1560, 1710, 1867; `gemm` at 1867
2. **S** arms (stock + offset), at 1560, 1710, 1867; then **S-gemm** at 1867 with the 1867 offset
3. **C** arm (stock + offset) at 1402
4. stock bracket B: as 1
5. curve 3 baseline: `membw` at 1710, 1867
6. **N** arms (curve 3 + offset), at 1710, 1867
7. curve 3 baseline again: as 5
8. stock bracket C: `membw` at 1402, 1560, 1710, 1867

**Interpretable only if** stock bracket C's `membw` mean over its four targets lies within **1.5%**
of bracket A's, and each curve 3 baseline pair agrees within 1.5%. Every comparison below is against
**the mean of the same-session brackets at that target**: A and B for S and C, and the two baselines
for N.

**A target is scoreable only if**, against its bracket:
- measured XBAR lies inside the arm's window;
- core achieved is within ±10 MHz;
- memory is exactly 13801 MHz;
- no driver reset occurs between the arm's set and its readback.

A target that fails these is **NOT SCOREABLE**: a failed manipulation, not a null.

### S: sufficiency (primary)

**Treatment:** stock curve, XBAR lowered to curve 3's §12 level. **Window:** measured XBAR
1312–1372 MHz.

**Prediction:** `membw` falls toward curve 3's §12 values. As a ratio of arm to bracket, §12's curve
3 gave 0.924, 0.886 and 0.863 at 1560, 1710 and 1867.

| verdict | condition, at every scoreable target |
|---|---|
| **SUFFICIENT, FULL** | ratio within ±0.03 of §12's: XBAR alone reproduces the plateau |
| **SUFFICIENT, PARTIAL** | ratio at most 0.962 / 0.943 / 0.931 (at least half §12's deficit), but not FULL |
| **NOT SUFFICIENT** | ratio at least 0.985 at all three |
| **MIXED** | anything else, reported per target |

**Control, S-gemm:** `gemm` throughput at 1867 within **±2%** of its bracket. If it moves more, the
offset is doing more than the bandwidth path. That is reported beside the S verdict, and S cannot be
read as XBAR-specific.

### C: the low-clock bandwidth limit (secondary)

**Treatment:** stock at a 1402 MHz core, XBAR **raised** to stock's 1560-MHz level. **Window:**
1455–1515 MHz.

**Prediction:** `membw` rises. §12 at the same XBAR gives 333.8 against 309.0 GB/s, +8.0%.

| verdict | ratio, arm to bracket |
|---|---|
| **LIFTS** | at least 1.04 |
| **PARTIAL** | 1.015 up to 1.04 |
| **NULL** | 0.985 up to 1.015: the limit at this core clock is not XBAR |
| **reported as unexpected** | below 0.985 |

⚠️ This tests this session's limit at a 1402 MHz core (about 309 GB/s at 13801 MHz memory). It does
**not** test the ~281 GB/s ceiling of long draft §3.3.1, which came from other sessions at a
different memory clock. Do not write it as resolving that ceiling.

### N: necessity (exploratory; riskier, so last)

**Treatment:** curve 3, XBAR raised back to stock's level. **Windows:** 1605–1665 MHz at 1710, and
1770–1830 MHz at 1867.

**Prediction:** the plateau lifts. Recovery means the arm's rise over the curve 3 baseline,
divided by the gap between the stock bracket and that baseline.

| verdict | condition, at both targets |
|---|---|
| **LIFTS** | ratio to the stock bracket of at least 0.97 |
| **PARTIAL** | recovery of at least one half, but not LIFTS |
| **NULL** | recovery of under one quarter |
| **MIXED** | anything else |

**Stop rule:** any driver reset, `membw` validation failure or visible artefact ends N, which is
then NOT SCOREABLE. **Never raise voltage to make it stable.** Curve 3 holds 0.720 V by design, and
a faster fabric at that voltage may simply not run, which is itself recorded.

### What each answer means, decided now

- **S FULL or PARTIAL with S-gemm inside ±2%:** lowering XBAR alone, at a matched core lock and memory
  clock, lowers `membw` on this card. Sufficiency, N = 1. Submission §5.4 may then say "an
  intervention on the crossbar clock reproduces the plateau" (or "part of it"), with SYS stated as
  unmeasured if it was.
- **S NOT SUFFICIENT with the manipulation verified:** evidence against XBAR as the mediator, and §5.4
  says so as a null. Something that moves with the curve, not with XBAR, would carry the plateau.
- **C and N** are reported with their verdicts whatever S gives. **N LIFTS** plus S sufficient
  would make XBAR both sufficient and necessary on this card for this kernel, at these targets.
- **Any XBAR+VOLTAGE flag:** that target's result is "the XBAR offset and its voltage demand", not
  XBAR alone.

**Limits, stated now.** One card, one session, one arm per target, three to four targets per
test. The offset is a request through an undocumented tool; only the measured clock is evidence that
it happened. SYS may be unobservable. §12's ratios come from a session four days earlier. The memory
path tested is `membw`'s copy kernel at 13801 MHz, not every bandwidth-bound workload. Nothing here
tests another card.

**Safety.** XBAR clock offsets only. No voltage, ratio or memory writes. The power limit stays at
each profile's §12 value. Close Afterburner after it applies a profile and before mVolt+ writes, and
never run two mVolt+ versions (mVolt #12). Read back after a driver reset, and treat it as clearing
everything. **After the session:** reset every mVolt+ control, verify stock as in the safety envelope
(power limit, memory under load, peak core, measured XBAR at offset 0), then uninstall mVolt+.

### ⛔ Amendment, 2026-09-30 21:39 (commit 837eb56), after calibration (step 0) and BEFORE collection

**No prediction, window, threshold or verdict changes.** This records what calibration found about
the method. Calibration read clocks only: `data/frequency-sweeps/5060ti-xbar14-calibration-20260930/`.

1. **The gates passed under load.** C0a: reported and measured XBAR are 4.2 MHz apart. C0b: −100 MHz
   under an `nvidia-smi -lgc` lock moved the measured XBAR by −92.0 MHz, back within 9.3 MHz. C0d:
   VID unchanged at every chosen offset. ⚠️ The first C0b attempt "passed" on an IDLE card (the load
   never started), so it is not used; the gate was repeated under a 61 W load.
2. **The offsets, fixed now:** S −125 / −300 / −475 at 1560 / 1710 / 1867; C +150 at 1402; N +300 /
   +450 at 1710 / 1867. Each put the loaded, measured XBAR inside its window
   (`xbar14-calibration.json`). Curve 3 ran +450 and +500 at 0.720 V with no driver event.
3. **How N is applied.** mVolt+ refuses EVERY write while curve 3 is live (*"The profile contains an
   invalid V/F point offset"*). So each N offset is written on stock, then Afterburner applies curve 3
   over it, and the measured XBAR follows (calibration run `211301`). Every reset to 0 from curve 3
   goes through stock first. The collection order and every comparison are unchanged.
4. **SYS is observable after all**, as mVolt+'s `sys_mhz`. Calibration read it under load at every
   offset: it stays within about 30 MHz of its offset-0 value. **So the offset moves XBAR without
   moving SYS on this card**, and S is read as "the XBAR offset", not "XBAR and SYS". During
   collection `--status` is saved after every write but is NOT polled during sweeps, so as not to add
   a process to a throughput measurement. SYS evidence for §14 is the calibration's, and is stated
   as such.
5. **The manipulation is still scored on the clock measured during collection.** The `membw` load can
   read differently from calibration's `layernorm`: §12 shows 1485 at a 1560 core under `membw`,
   against 1466–1475 here.

### Provenance note, 2026-10-01 09:06 (commit 292a712), after the dry run and BEFORE any treatment data

**Nothing in the design, the offsets or the predictions changes.** The dry run (offsets forced to 0,
`xbar14dry-` labels) completed at 09:04 with no driver event. The real session then stopped at its
store-hash gate: during the dry run Afterburner appended `[Defaults]` (its capture of stock values)
and `[Settings] CaptureDefaults=0` to the 5060 Ti's store. **With those two sections removed the
store is byte-identical to the committed curve 3 snapshot, `8EC197F30E21D116`**; `[Startup]` and
`[Profile1]`–`[Profile5]` are untouched. The gate now hashes only those six sections, in file order,
and still expects `8EC197F30E21D116`; a one-byte change inside `[Profile4]` gives `19E0ACAD…` and is
refused. This is the same rewrite that stopped Session D on 2026-09-24 (§4b's provenance note).

**Second stop, 09:10, also before any treatment sweep.** The stock check read memory under load as
**14001 MHz** (the card's P0 maximum) against the expected 13801, and refused. The check took the
MAXIMUM of its readings. Three repeats at 09:13, stock, ChatGPT closed, read **13801 at every loaded
sample** (P-state P1), so it was one transient sample. The check now takes the **median** of 5 s of
loaded readings and logs every value; a sustained 14001 or 16301 still refuses. The memory clock
during every sweep is in its HWiNFO log and is checked when the session is scored.
⛔ *Corrected the same evening: 14001 is not a transient. §13's amendment (2026-09-27) had already
recorded it as this card's other loaded stock state; this note should have cited it.*

### Result — collected 2026-10-01 09:17–09:46: NOT SCOREABLE as registered; under §13's memory rule, a post hoc sensitivity analysis, the S FULL, C LIFTS and N LIFTS thresholds hold

⛔ **Rewritten 2026-10-01 evening after GPT Job 40** (`docs/gpt-findings/2026-10-01-xbar14-result-adversarial-audit.md`),
which recomputed every number and found three false or overbroad statements in the first version and
three scorer defects; each was verified here before the text changed. The first version's
headline, *"lowering the crossbar clock alone reproduces the plateau, and raising it alone removes
it"*, is withdrawn: it overstates what one post hoc-qualified session can show.

Scored by `analysis/score_xbar14.py`, written **after** collection from this section's text; no
threshold in it is its own; `analysis/test_score_xbar14.py` pins the cases Job 40 found. Data, logs
and both refused launches: `data/frequency-sweeps/5060ti-xbar14-20261001/`. Every arm ran, in the
registered order, with **0 display-driver events**.

```
python analysis/score_xbar14.py data/frequency-sweeps/5060ti-xbar14-20261001 --memory-rule literal
python analysis/score_xbar14.py data/frequency-sweeps/5060ti-xbar14-20261001 --memory-rule section13
```

**As registered ("memory is exactly 13801", read per sample): S, C and N are all NOT SCOREABLE.**
13 of 25 points fail it, and the failures include references: stock bracket C at all four targets,
both curve 3 baselines at 1710 and 1867, A at 1710 and B at 1402. So no N target has a valid pair of
baselines either. A memory-qualified session, in §14's own terms, was not obtained.

**Interpretable on throughput.** Bracket C's four-target `membw` mean is **+0.08%** from bracket A's
(limit 1.5%); the curve 3 baseline pairs agree within **+0.04%** and **−0.07%**.

**Post hoc sensitivity analysis, under §13's memory rule** (each instrument's maximum within
13801–14001, stock's two loaded states; all 25 points pass, references included):

| test | target | arm / reference | registered reference | measured XBAR, arm (reference) | threshold met |
|---|---|---|---|---|---|
| **S** | 1560 | **0.952** | §12 0.924 (±0.03) | 1368 (1478) | |
| | 1710 | **0.890** | §12 0.886 | 1329 (1634) | |
| | 1867 | **0.875** | §12 0.863 | 1333 (1807) | **FULL** |
| S-gemm | 1867 | **+0.59%** | within ±2% | 1342 | inside |
| **C** | 1402 | **1.068** | ≥ 1.04 | 1495 (1343) | **LIFTS** |
| **N** | 1710 | **1.001** of stock; recovery **1.014** | ≥ 0.97 at both | 1636 (curve 3: 1335) | |
| | 1867 | **0.999** of stock; recovery **0.995** | | 1785 (curve 3: 1335) | **LIFTS** |

Every arm's measured crossbar clock is inside its window, and every core clock is within ±10 MHz of
its references (averages; curve 3's instantaneous clocks spread wider). **What this supports, and no
more:** *on one RTX 5060 Ti, in one session, XBAR-offset requests in both directions changed the
measured crossbar clock and `membw` throughput at nearly matched core clocks, and the numerical
intervention and rescue thresholds hold under a memory rule chosen after the data were seen.* It does
**not** reverse the 2026-09-18 retraction of XBAR as a demonstrated mediator. Do not write "XBAR
alone", "necessary and sufficient" or "registered success".

⛔ **Why §13's rule, and the case against it.** §13's amendment of 2026-09-27 had already rewritten
this same condition, because 14001 is this card's other loaded stock state (CLAUDE.md, hardware
table); §14, written three days later, copied the old wording. But importing it here was done after
the outcomes were visible, and a maximum ignores idle minima: a legitimate second loaded state does
not show that idle samples are harmless for this kernel. Job 40's checks, verified here:
- ~~"never in both instruments at the same point"~~ **is false**: curve 3 baseline 1 at 1710 and
  1867, and stock C at 1402, have an exceptional sample in both. Simultaneity is not established
  either way.
- ~~"with no throughput effect"~~ is **narrowed** to: no consistent loss in the repeated stock and
  curve 3 references (a larger change occurs between two clean stock-1560 readings, −0.89%). The S
  arms, C and N-1710 carry an exception and have no clean same-setting repeat, so their effect cannot
  be tested.
- In local raw logs every HWiNFO exception is the **first** sample of its window, 0.03–0.26 s in.

**Read beside it:**
1. **Voltage readings moved in two places.** S at 1560 reads VID 0.735 V, two 5 mV codes above its
   bracket mean, and **the S-gemm control reads 0.805 V against 0.795 V for both brackets**, also two
   codes, so the control is not voltage-matched and its +0.59% does not exclude a compensated compute
   effect. S at 1710 and 1867 read the same VID as their brackets and alone meet FULL. S-1560 meets
   FULL by 0.0016 ratio units against the A/B mean (registered); against A alone it is 0.948, against
   B alone 0.957.
2. ⛔ **Protocol deviation: no reset or return check between consecutive arms.** −125 → −300 → −475
   across S, **−475 → +150 into C**, and +300 → +450 across N; the registration asks for a reset,
   readback and return check between arms. Realised clocks sit at the requested levels, not sums, and
   the closing references return, but history effects inside treatments are not excluded.
3. **SYS was not measured during collection.** Calibration's loaded `sys_mhz` (layernorm, previous
   evening) moved −4.0, −1.5, −15.0, −3.5, +2.0 and +2.0 MHz at the six chosen offsets, at most 28 MHz
   in any subrun. N's rescue goes through an offset write on stock and a profile re-application, with
   no zero-offset sham of that path.
4. 🔑 **This session was quiet and the dry run before it was not.** Per-window medians from HWiNFO
   (raw logs gitignored, kept locally): this session **4–7 fps presented, 1–7% GPU bus load** in all
   25 windows; the dry run (08:41–09:04) **156–233 fps, 17–49%** (42–49% on `membw`), and its stock
   `membw` at 1402 reads **308.2 GB/s against 339.6** here. §12's raw logs (2026-09-26) show the same
   kind of load, **147–240 fps and 41–51% bus load on its `membw` windows**, so §12's absolute GB/s are
   depressed and its ratios are measurements under that load, not established clean ratios. A ratio
   cancels a shared multiplicative penalty, not necessarily a frequency-dependent one. This session's
   own curve 3 / stock ratios are 0.893 and 0.877 at 1710 and 1867, against §12's 0.886 and 0.863.
5. One card, one session, one arm per target, one kernel at 13801 MHz. The offset is a request
   through an undocumented tool; the measured clock is the evidence it happened.

**What a prospective re-run needs** (Job 40 §8, adopted as the design notes for any §14 repeat): the
memory statistic, each instrument's rule, the allowed states and first-sample handling registered
before throughput is seen and applied to every reference; resets with return checks between all arms;
counterbalanced order; a zero-offset sham of N's write-and-reapply path; SYS read during kernels; and
a scorer tested on bad references, subsets and unequal achieved clocks before collection.

## 15. RTX 5060 Ti: clean re-runs of the results measured beside a desktop load. Registered 2026-10-03, before collection

✅ **Approved by Raymond and committed as registered 2026-10-03, before any §15 sweep.** The text below is as drafted and amended the same day (the amendments after GPT Job 41 are marked). **R1 and R3 run first, in one session; R2 is deferred** to a later session or dropped, which changes no R1 or R3 prediction. The scorer (`analysis/score_rerun15.py`) and its fixtures are committed (`718d41f`).

**Why.** On 2026-10-03 a visible desktop window (the Claude app's) was shown to cost 6.3–9.2% of
`membw` on this card, largest at low clocks, and to pass every earlier guard
(`data/frequency-sweeps/5060ti-deskload-20261003/`). Its HWiNFO signature sits on 91 of the 585
dataset-grade RTX 5060 Ti sweeps (`docs/DESKTOP-LOAD-AUDIT-20261003.md`), including three results the
papers lean on: **§12's memory-matched pair** (submission §5.4), **the 2026-08-20 voltage pair** behind
the plateau table (long draft §5.7), and **both ladder rungs of §1** (submission §5.3). This
re-collects each under conditions that exclude that load, with the original predictions unchanged,
plus one prediction about the load itself.

**What does not change.** Every prediction in §1 and §12 is restated below **as originally
registered**; nothing is re-tuned after seeing which results were contaminated. Grids, workloads,
iteration counts and runners are the originals' (`runner-run-4j.ps1.txt`, `runner-run-4f.ps1.txt`
beside their data). The original results stand as recorded; these are new collections reported
beside them, never pooled with them.

### Conditions that apply to every sweep

1. **Desktop load excluded and checked.** `Invoke-LoggedSweep.ps1` minimizes every Claude window
   before its preflight and fails the sweep (exit 8) if its own HWiNFO log shows a benchmark window
   above **30 fps presented or 10% GPU bus load**. A failed sweep is re-run once; a second failure
   makes that arm **NOT SCOREABLE**. Opera, Discord, ChatGPT, Codex, games and Obsidian closed;
   operator away.
   🆕 *Amended 2026-10-03, before any §15 sweep, after the runner's dry run
   (`C:/headroom-bench/rerun15/20261003-144635-r15dry`, single-target sweeps, not §15 data):*
   **a window is flagged on framerate alone (above 30 fps); bus load is reported, not gated**, except
   in a log with no framerate column. The dry run flagged a `copy` sweep at 5.3 fps and 17% bus load
   with nothing rendering, and quiet historical suites (4–13 fps presented) reach 13–36% NVIDIA bus
   load at some points from the kernels themselves (`copy`, `reduce`, `layernorm`, `bgemm`). Framerate
   alone separates the 2026-10-03 ABA states (4–7 fps against 201–239). The same change is made in
   `check_desktop_load.py`, the bench app's copy of it, and `score_rerun15.py`.
2. **Memory rule, defined now, before throughput is seen** (the gap Job 40 found in §14). For each
   point and each instrument (nvidia-smi samples in the sweep CSV, HWiNFO's NVIDIA "GPU Memory Clock"
   ×8 in the window), the **median** of in-window readings must equal the configuration's loaded
   state (13801 for memory +0, 16301 for +2500), and the **maximum** must lie in that state or the
   one above it (14001 / 16501). A single low reading is allowed and counted. Anything else makes
   that point NOT SCOREABLE. The rule applies to every sweep collected under §15, stock reference
   arms as well as treatments. 🆕 *Amended 2026-10-03, before collection, after GPT Job 41 built the
   scorer:* the nvidia-smi readings are the per-point in-window sample array
   (`memory_clock_samples_mhz`) that `Invoke-FrequencySweep.ps1` writes from this date; earlier CSVs
   kept only the mean, minimum and maximum, from which a median and a low count cannot be recovered.
   **The two named historical comparators** of the load predictions predate that record, and the
   2026-08-20 one has no benchmark windows, so they are **used as recorded**: each point's recorded
   maximum must be 13801 or 14001, and their minimum and mean are reported, not gated (both carry
   single idle readings: 810 and 7001 MHz minima).
3. **Configuration witnessed.** Before each arm: the profile store's `[Startup]` and
   `[Profile1]`–`[Profile5]` sections hash-match the committed snapshot named for that arm; power
   limit and memory under load are read live. mVolt+ reads every offset 0. Driver 616.92.
4. **Restoring a profile.** Where an arm needs a stored curve that is no longer in a slot, the
   profile store is restored byte-for-byte from its committed snapshot with Afterburner closed, then
   section-hash verified. P2–P5 are byte-identical across the 09-22 rung B, 09-26 rung C and 09-26
   curve 3 snapshots (section hashes compared 2026-10-03), so only Profile 1 changes between arms.

### R1 — §12 again: curve 3 against stock, memory matched (~30 min)

Design exactly as §12: stock `membw` → stock `gemm` → curve 3 `membw` → curve 3 `gemm` → stock
`membw`; `membw` 1400–2100 in 10 points (default iterations), `gemm` 1237–3090 in 13 points at 120
iterations. Profile 1 = curve 3 (snapshot `5060ti-profiles-20260926-curve3`), Profile 3 = stock.

- **Gate:** closing stock `membw` band mean within **1.5%** of the opening one.
- **Primary (§12's):** curve 3's `membw` below the opening stock sweep's at every target 1560–1867.
- **Telemetry (§12's, as worded):** curve 3's crossbar within 1300–1360 MHz from 1402 to 1867 while
  stock's rises, read as: the opening stock sweep's in-window median crossbar clock **strictly
  increases at each successive target** from 1402 to 1867 (§12's stock did, 1335 → 1800, in both of
  its stock sweeps). (§12's 0.720 V clause is not restated: it failed by one code on stock too, and the
  VID is not the state variable.)
- **Secondary (§12's):** curve 3 `gemm` board power below stock at every matched target 1545–2475
  (2625 dropped: stock reached its 180 W limit there).
- 🆕 **The load prediction:** the clean opening stock `membw` band mean (1400–2100) exceeds §12's
  opening stock band mean by **at least 3%**. If it does not, the desktop load did not depress §12
  materially and the audit overstates it for this session.
- **Reported, not scored:** curve 3 / stock ratios at 1560, 1710, 1867 beside §12's 0.924 / 0.886 /
  0.863.

### R2 — the 2026-08-20 pair, and the repair, clean (~45 min)

Stock `membw` → P4 `membw` → P2 `membw` → stock `membw`, all on the 08-20 grid (1402–2100, the same
10 targets), default iterations. P4 = full tune (memory +2500), P2 = repair (+2500), P3 = stock (+0).
⚠️ P4 vs stock is **not memory-matched**, exactly as the 08-20 pair was; R1 is the matched version.
The 08-20 "oc" profile is not proved identical to today's P4 (§12), so these predictions are about
today's profiles, and the 08-20 numbers are compared descriptively only.

- **Gate:** closing stock band mean within 1.5% of the opening one.
- **Plateau:** P4 below the opening stock at every target 1560–1867 (long draft §5.7.2's claim).
- **Crossbar:** P4's within 1300–1360 MHz from 1402 to 1867; stock's rising, read as in R1.
- **Repair (long draft §5.7.4's, memory-matched against P4):** P2 above P4 at every target 1560–1867,
  and by at least **+8%** at 1867.
- 🆕 **The load prediction:** the clean stock band mean exceeds the 2026-08-20 stock sweep's
  (`20260820-211630_5060ti-stock-volt-membw`) by at least 3%.

### R3 — both ladder rungs, in one session, between stock suites (~4.5 h)

Stock suite → **rung B** suite → **rung C** suite → stock suite. Twelve workloads × 13 targets
1237–3090, iteration counts as the original rung suites. Rung B = store restored from
`5060ti-profiles-20260922-rungB`, rung C = `5060ti-profiles-20260926-rungC`, each into Profile 1 and
witnessed (+2500 memory live, as in the originals).

- **Gate (as §10's):** the worst workload's median absolute matched-target change between the two
  stock suites is within **1.5%**. Otherwise R3 is NOT SCOREABLE.
- **Primary (§1's):** median efficiency optimum **1702 MHz** on rung B and **1852 MHz** on rung C.
- **Secondary (§1's):** at least **7 of 12** workloads on the predicted point on each rung.
- **Tertiary (§1's):** with this session's stock median as rung A, the optima rise monotonically, and
  B and C land on different points. Since there are two stock suites, **each** stock suite's median
  must be at or below rung B's, and rung B's strictly below rung C's; the two are not averaged.
- **Reported, not scored:** per-workload agreement with the original rung suites (09-23, 09-26) and
  with the stock suites; the original runs' 9 of 12 is the comparison.

### What each outcome means, decided now

- **R1, R2 and R3 all hold:** the load did not create any of these results; the papers say so and
  cite these collections as the clean ones.
- **A primary fails clean:** that result was produced or materially shaped by the load. The paper
  sentence resting on it is withdrawn or narrowed in the same commit as the result, and the original
  stays recorded with its failure beside it.
- **A load prediction fails** (clean not ≥3% above the old): the audit's absolute-throughput caution
  is narrowed for that session, in writing.
- **NOT SCOREABLE** anywhere is reported as such, with no third collection registered here.

### Limits and safety

One card, one collection per arm, the ~155 MHz suite grid. The profiles are the ones already run for
hours (§1's envelope; curve 3 and P4 at 0.720 V). Power limits stay at each profile's value. No mVolt+
writes. Every exit path resets clocks and applies Profile 3; the profile store is restored to the
current committed state (`5060ti-profiles-20260926-curve3`) at the end.

**Scorer:** `python analysis/score_rerun15.py r1|r2|r3 <dir>`, written by GPT Job 41 and tested on
fixtures **before** collection (`analysis/test_score_rerun15.py`; record
`docs/gpt-findings/2026-10-03-score-rerun15.md`). The collection directory carries
`rerun15-inputs.json`, mapping each arm to its sweep, HWiNFO log, wrapper result and pre-arm witness.
Its fixtures include unequal achieved clocks, failed and boundary gates, a desktop-load exit and its
sole retry, an idle first sample (allowed) and an idle median (refused), a NOT SCOREABLE reference,
both rungs on one point, and a median between grid points. The scoring choices it made where this
text was silent are listed in its record and adopted above.

### Result, 2026-10-03: R3 HOLDS; R1's primary, telemetry and load predictions hold, its gemm-power secondary FAILS

Collected unattended 15:13–19:44 (`data/frequency-sweeps/5060ti-rerun15-20261003/`, scored with
`python analysis/score_rerun15.py r1|r3 <dir>`). 53 sweeps; **0 driver events, 0 desktop-load exits,
0 retries**; every evidence gate passed (memory rule at all 1,360 point-instrument checks, desktop
4–8.8 fps, every profile witness).

| part | prediction | result | verdict |
|---|---|---|---|
| R1 | drift gate, 1.5% | +0.014% | passes |
| R1 | **primary:** curve 3 below stock 1560–1867 | 0.936 to 0.885 of stock | ✅ HOLDS |
| R1 | crossbar telemetry | curve 3 1312–1342; stock 1335 → 1807, rising at each target | ✅ HOLDS |
| R1 | secondary: curve 3 `gemm` power below stock 1545–2475 | **1.001 at 1545**; 0.913 to 0.760 at 1702–2475 | ⛔ **FAILS** |
| R1 | load: clean stock ≥3% above §12's | **+8.16%** | ✅ HOLDS |
| R3 | drift gate, 1.5% (worst workload) | 0.063% | passes |
| R3 | **primary:** medians 1702 / 1852 | **1702 / 1852** | ✅ HOLDS |
| R3 | secondary: ≥7 of 12 on the point | 7 of 12 / 9 of 12 | ✅ HOLDS |
| R3 | tertiary: stock ≤ B < C, both stock suites | 1545 / 1702 / 1852 / 1545 | ✅ HOLDS |

**What follows, as decided in advance.**
- **The primaries held clean.** The memory-matched plateau (§12, submission §5.4) and both ladder
  rungs (§1, submission §5.3) were not created by the desktop load. The papers cite this
  collection as the clean one. Reported, not scored: curve 3/stock 0.936 / 0.901 / 0.885 at 1560 /
  1710 / 1867 against §12's 0.924 / 0.886 / 0.863 under load, so the load slightly exaggerated the gap.
- **The load prediction held:** §12's absolute stock bandwidth was depressed by about 8%, as the
  ABA test predicted. The audit's caution on absolute throughput from LOAD sweeps stands.
- **The secondary failed at its first target only.** At 1545 MHz both arms reach 1537 MHz and
  report 0.720 V, and draw 75.37 against 75.27 W. §12's −3.5% there was measured under the load.
  The statement it rests on is narrowed: curve 3 draws less `gemm` power than stock **from 1702 to
  2475 MHz** (8.7–24.0% less), not from 1545. No paper sentence states the 1545 point.
- Rung B lands exactly on its 7-of-12 threshold and its per-workload optima match the 09-23 original
  at only 5 of 12; rung C matches its original at 9 of 12. The medians reproduce; individual
  workload points move, as Table 4's baseline already says they do between identical suites.
- **A quiet desktop makes this card very reproducible:** the two stock suites, four hours apart,
  agree to a median 0.01–0.06% per workload.
- N=1 chip, one session, one collection per arm.
- **R2 will run in its own session** (decided 2026-10-03 evening): submission §5.4 cites the repair,
  whose August `membw` sweeps carry the load signature, so R2's repair prediction is its clean check.
  `Invoke-Rerun15Session.ps1 -Parts r2` runs it, predictions unchanged from the text above.

### Result, 2026-10-04: R2 HOLDS on every prediction

Collected unattended 19:15–19:38 in its own session (`data/frequency-sweeps/5060ti-rerun15r2-20261004/`,
scored with `python analysis/score_rerun15.py r2 <dir>`), after a passing dry run. 4 sweeps; **0
driver events, 0 desktop-load exits, 0 retries**; every evidence gate passed (memory rule at all 80
point-instrument checks, desktop 4–6 fps, every profile witness).

| part | prediction | result | verdict |
|---|---|---|---|
| R2 | drift gate, 1.5% | −0.02% | passes |
| R2 | **plateau:** P4 below stock 1560–1867 | 0.960 to 0.908 of stock | ✅ HOLDS |
| R2 | crossbar telemetry | P4 1312–1350; stock 1335 → 1807, rising at each target | ✅ HOLDS |
| R2 | **repair:** P2 above P4 1560–1867, ≥ +8% at 1867 | 1.101 to **1.245** | ✅ HOLDS |
| R2 | load: clean stock ≥3% above the 08-20 stock sweep | **+15.65%** | ✅ HOLDS |

**What follows, as decided in advance.** With R1 and R3, **R1, R2 and R3 all hold on their primary
predictions: the load did not create any of these results.** The repair the submission cites
(§5.4) now has a clean, registered measurement: 10.1–24.5% above the full tune at 1560–1867 MHz,
memory-matched to it. The P4-against-stock contrast is still not memory-matched (R1 is), and
today's P4 is not proved identical to the 08-20 profile. The 08-20 stock sweep read about 16% low in
band mean, twice §12's 8%; that session also predates the Instant Replay finding, so the 16% is not
attributed to the window alone. N=1 chip, one session, one sweep per arm.

## 16. RTX 5060 Ti: the upper-curve control clean, and the floor manipulation registered. Registered 2026-10-06, before collection

**Approved by Raymond 2026-10-06 08:55 and committed before any §16 sweep.**

**Why.** Two headline 5060 Ti results still lack a clean, registered measurement:
- **The upper-curve control** (§10) passed on 2026-10-01 only under a desktop load present in all
  468 windows. §15 re-ran everything else that load touched; not this.
- **The floor manipulation** (`abba-20260908`, P5 against P4) was found in a run registered for a
  different prediction. It has never been a registered prediction.

GPT Job 50 (2026-10-04) adds the baseline both need: identical-configuration suites on this card
change 2–6 of 12 target-grid optima, so changed-workload counts are reported beside a same-session
repeat count, never alone.

**Design.** One session, operator absent, driven by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s16` (§15's runner, this part added and dry-run
first): **P5 → P4 → P2 → P5**, four twelve-workload suites, grid 1237–3090 MHz in 13 points
ascending, §10's iteration counts (identical to §15's R3).
- **§15's conditions 1–4 carry over unchanged:** the HWiNFO framerate screen with one retry after a
  desktop-load exit (a second makes that role NOT SCOREABLE); Claude minimized; ChatGPT, Codex,
  Opera, Discord, Obsidian, games and `llama-server` closed; driver 616.92; mVolt+ offsets and
  voltage demands all 0; the profile store restored byte for byte from
  `data/afterburner-profiles/5060ti-profiles-20260926-curve3/` (slots 2, 4 and 5 identical to the
  §10 store) and section-hash verified after Afterburner restarts.
- **Slot witness per arm:** memory under load 16301 MHz and power limit 200 W for all three slots,
  plus §10's amended witness, `gemm` power at a locked 2475 MHz: **P5 ≤ 163 W, P2 ≥ 165 W**. P4's
  value is recorded, not gated; no threshold was ever measured for it.
- P5 and P4 differ below the floor (+465 MHz below 840 mV) and also −98 MHz at 875–925 mV, as in
  the ABBA run; the contrast is not region-isolated. Today's P4 has the 3030 MHz plateau
  (edited 2026-09-08 after the ABBA run), so it is not the ABBA-era P4.
- Scored by `analysis/score_session16.py` (committed with this registration, tested on synthetic
  sweeps, never on §16 data). Its P5/P2/P5 legs carry §10's labels, so
  `analysis/score_control10.py` scores the control unchanged as a cross-check.

**Scoreable only if (§10's rule):** the two P5 suites have the same median, and no workload's
median absolute matched-target throughput change between them exceeds 1.5%. Otherwise every
prediction below is NOT SCOREABLE, which is not a failure. A suite with a role lost to a second
desktop load is NOT SCOREABLE; a lost P5 role voids everything.

**Predictions**, optimum = `analyze_sweep.efficiencyPeak` per workload on the target grid:
- **C (control, §10's):** the P2 median equals the P5 median.
- **M1 (manipulation, primary):** the P4 median is **2010 MHz**, the grid point nearest the floor
  end its decoded curve gives (2002 MHz; `predict_from_curve.py`).
- **M2 (manipulation, secondary):** at least **9 of 12** P4 optima lie strictly above the opening
  P5 optimum of the same workload.

**Reported, always:** P2 optima differing from both P5 optima; the P5a/P5b changed count (the
same-session repeat baseline); P4 optima above, equal to and below P5a; each slot's 2475 MHz power.

**What each outcome means, decided now.**
- **C HOLDS:** the control holds clean, in a same-session bracket, with its moved count beside the
  repeat count. **C FAILS:** the 5060 Ti's control moved too, and with the 3070 Ti's §4b the
  floor-region attribution is established on neither chip.
- **M1 and M2 HOLD:** the manipulation is a registered result on this card, not only a post hoc one.
  It is still not region-isolated (the −98 MHz above), and N=1 chip. **M1 FAILS:** the post hoc
  ABBA result does not reproduce as registered, and the papers say so.
- N=1 chip, one session, one suite per arm; the twelve workloads are repeated outcomes on it.
- Afterwards, if the session ends before 14:25: worklist 4g, a 90-minute soak of P5 under
  `Invoke-StabilityProtocol.ps1` (descriptive; not part of §16).

### ⛔ Amendment, 2026-10-06 09:10, after the dry run and before collection: when the witness is taken

The dry run (09:00–09:08, single-target sweeps, not data) took the 2475 MHz witness after the memory
check's own `gemm` load and read **P5 at 144.1 W opening but 156.1 W closing**, 7 W from the 163 W
limit, with P2 at 178.5 W and P4 at 153.0 W. Board power at a fixed clock rises as the card warms,
and §10's runner took the witness as the first load after applying the slot. **The runner now does
the same, after 90 s idle, and records the temperature after it.** The thresholds, predictions, gate
and scorer are unchanged. No §16 data existed when this was written.

### ⛔ Amendment 2, 2026-10-06 11:30: the first collection was killed by the agent's tool, and is collected again

The collection started at 09:24 (`C:\headroom-bench\rerun15\20261006-092420-s16`) was killed at
11:22 by the agent harness's two-hour limit on a background command, during P4's twelfth sweep
(`gemm`). The runner's `finally` block did not run: HWiNFO was left logging and P4 left applied;
both were reset by hand at 11:25 (Log Stop, `nvidia-smi -rgc`, Profile 3, 180 W read back). The
opening P5 suite and 11 P4 sweeps had completed with exit 0 and no driver events. **None of their
sweep data has been read or scored;** only the runner log's exit codes and slot witnesses were seen
(P5 150.8 W, P4 150.4 W at 2475 MHz). The registered design is one session, so it is **collected
again from the start, unchanged**, launched as a detached process. The killed attempt stays on the
bench PC as a record of the abort and is not §16 data. Nothing else changes.

### Result, 2026-10-06: C, M1 and M2 all HOLD

Collected unattended 11:25–15:31 (`data/frequency-sweeps/5060ti-session16-20261006/`, scored with
`python analysis/score_session16.py <dir>`). 48 sweeps; **0 driver events, 0 desktop-load exits, 0
retries**; desktop screen 0 of 624 windows flagged (4.0–8.1 fps); memory 16301 MHz under load at
every arm; 2475 MHz witnesses P5 148.9, P4 149.5, P2 172.2, P5 149.1 W.

| prediction | result | verdict |
|---|---|---|
| gate: equal P5 medians, every P5 return ≤ 1.5% | 1545 / 1545 MHz; worst 0.725% | passes |
| **C:** P2 median equals P5 median | 1545 = 1545 | ✅ HOLDS |
| **M1:** P4 median 2010 MHz | **2010** | ✅ HOLDS |
| **M2:** ≥ 9 of 12 P4 optima above P5a's | **10 of 12** (1 equal, 1 below) | ✅ HOLDS |

Reported, always: **P2 differs from both P5 suites at 2 of 12** (`bgemm32`, `gemm`), and from the
opening P5 suite alone at 4 of 12; **the P5 suites differ from each other at 5 of 12**; P4 against P5a is 10 above, `bgemm64` equal, `copy` below
(1545 against 1702). `score_control10.py` on the P5/P2/P5 sweeps alone agrees: PASS.

**What follows, as decided in advance.** The 5060 Ti's upper-curve control holds clean, changing no
more workloads against the opening P5 suite (4) than the same-session repeat did (5). ⛔ *Corrected the same evening: this first compared P2's 2 of 12 (different from BOTH P5 suites) against the P5 pair's 5 of 12, two different statistics. Like for like, P2 against the opening P5 suite changes 4 of 12.* The floor manipulation is a registered result on this
card, no longer only a post hoc one; its median moved to the predicted 2010 MHz. ⚠️ ABBA's "all 12
moved upward" did not repeat (10 of 12), the contrast is still not region-isolated (−98 MHz at
875–925 mV), today's P4 is not the ABBA-era P4, and N=1 chip, one session, one suite per arm.

**4g ran afterwards although the session ended at 15:31, after the 14:25 condition above:** Raymond
approved it during the collection. It is descriptive and not part of §16; CLEAN, 90 minutes
(`data/stability-runs/`).

## 17. RTX 5060 Ti: sampled board power against NVML's integrated energy counter. Registered 2026-10-06, before collection

**Approved by Raymond 2026-10-06 (evening) and committed before any §17 sweep.**

**Why.** Every power figure in this project is `nvidia-smi`'s power reading sampled at 2 Hz and
averaged over the benchmark's timed window, a smoothed device-side estimate (Yang et al. 2024,
paper [26]). Nothing here has checked it. NVML's cumulative energy counter
(`nvmlDeviceGetTotalEnergyConsumption`) is supported on this card (checked 2026-10-06: return code
0, millijoules, ticking about every 100 ms), and energy over the timed window divided by its
length is a second average power that is integrated rather than sampled.

**Design.** `gpu_workload.py` reads the counter at the two edges of its timed region; the sweep
(schema 0.3.4) writes `energy_avg_power_w` beside `power_avg_w`. Stock (Afterburner Profile 3,
180 W), driver 616.92, Claude minimized, unattended. First a two-point `gemm` test sweep (1545 and
2475 MHz), which is not data: it must show both power figures at both points and memory 13801–14001
MHz under load, or nothing else runs. Then one twelve-workload stock suite, the replicate grid
(13 points, 40% of the top lockable clock upward) and `Invoke-SuiteReplicate.ps1`'s iteration
counts, ascending intensity. Scored by `python analysis/compare_energy_power.py <dir>`, committed
and tested with this registration and never run on §17 data before it.

**Scoreable only if** at least 11 of the 12 sweeps complete with at least 12 of 13 points carrying
both figures.

**Predictions:**
- **A (agreement):** the median absolute per-point difference between the two power figures, over
  every usable point, is at most **2%**.
- **B (optimum):** each sweep's efficiency optimum on the target grid is the same under both power
  figures in at least **10 of 12** workloads, and the suite median optimum is the same.

**What each outcome means, decided now.** Both hold: the paper may say the sampled power agrees with
the integrated counter on this card at stock. ⚠️ Both are the card's own telemetry, so agreement is
consistency, not accuracy against a shunt; it says nothing about other cards or configurations.
A fails: report the size and sign of the gap, and the counter becomes the preferred figure for new
sweeps. B fails: optimum locations depend on the power figure, reported as such, and the key 5060 Ti
optima are re-checked with the counter. N=1 chip, one suite, one session.

### Result, 2026-10-06: A and B both FAIL

Collected unattended 18:53–19:46 (`data/frequency-sweeps/5060ti-energy17-20261006/`), after the
two-point test passed (both figures recorded, memory 13801 MHz). 12 sweeps, all exit 0, 13 of 13
points each, so scoreable.

| prediction | result | verdict |
|---|---|---|
| **A:** median absolute per-point difference ≤ 2% | **7.83%**, every one of 156 points positive (energy higher); worst 15.35% | ⛔ FAILS |
| **B:** optimum unchanged in ≥ 10 of 12, suite median unchanged | **8 of 12**; median 1545 MHz both ways | ⛔ FAILS |

By workload the median gap is about +3% on `gemm`, `conv` and `attention` and +7 to +10% on the
other nine, and it scatters by several percent from point to point within a sweep. The four optima
that move (`copy`, `layernorm`, `bgemm64`, `bgemm128`) each move one grid step, to 1545 MHz.

**What follows, as decided in advance.** The paper may NOT say the sampled power agrees with the
integrated counter. It reports the gap and its size, and that the median optimum is unaffected
while per-workload optima are sensitive to the power figure at the grid's resolution. The counter
becomes the preferred figure for new sweeps. Re-checking the key 5060 Ti optima with the counter is
owed. ⚠️ Both are the card's own telemetry: this shows they disagree, not which is right. N=1 chip,
stock, one suite.

⛔ **Audited 2026-10-07 by GPT Job 57 (`docs/gpt-findings/2026-10-07-section17-audit.md`), rechecked
here; A and B still FAIL.** In 52 of 156 points the first 2 Hz sample in the window is an idle-memory
reading, and dropping one minimum reading per point (an influence check, not a correction) moves the
median gap from +7.83% to +2.59%. One point (`reduce`, 2625 MHz) has a 2.18 s window mismatch;
excluding it leaves both verdicts unchanged. The two windows bracket the same timed work but are not
literally identical. The scorer was descriptive only; it now refuses non-finite values.

## 18 and 19. RTX 5060 Ti: which power reading the energy counter matches, and the key optima by energy. Registered 2026-10-06, before collection — COLLECTED 2026-10-07: §18 H1 and H2 FAIL; §19 HOLDS at every arm

**Requested by Raymond 2026-10-06 (night) for the 2026-10-07 school day; committed before any §18 or
§19 sweep.** One session serves both: `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s19`, dry-run
first the same morning (its output is not data).

**Why.** §17 found NVML's integrated energy counter a median 7.83% above the sampled `nvidia-smi`
power, at every point of a stock suite, and moving 4 of 12 per-workload optima. That leaves two
questions: why the readings differ (§18), and whether the project's registered optima still stand
when efficiency is computed from the counter (§19).

**Design.** One session, operator absent, twelve-workload suites on the 13-point replicate grid with
§10's iteration counts: **stock → P5 → P4 → rung B → rung C → stock**. §15's conditions 1–4 carry
over unchanged (desktop-load screen with one retry, Claude minimized, ChatGPT/Codex closed by the
runner, driver 616.92, mVolt+ offsets 0, profile stores restored byte for byte from `curve3`, `rungB`
and `rungC` and section-hash verified). Each arm's witness adds `gemm` power at a locked 2475 MHz
after 90 s idle, gated as in §16 (P5 ≤ 163 W), recorded for the others. Every sweep is schema 0.3.4
or later, so every point carries both `power_avg_w` and `energy_avg_power_w`.
`tools/power-probe/sample_power.py` logs NVML's `power.draw` value, its average and instant fields
and the energy counter at 20 Hz for the whole session; its load (~1.4% of one core) is the same
beside every arm. Checked on 2026-10-06 before registering: all three power fields and the counter
are supported on this card and update about every 100 ms, and `power.draw` equalled the average
field in every reading taken.

### §18: which reading matches the counter

Scored by `python analysis/score_power_fields.py <dir>`, committed and tested with this registration.
For every point of every accepted sweep, over the benchmark's timed window:
- **H1:** the median absolute difference between the 20 Hz mean of the **instant** field and the
  energy counter's average power is **at most 2%**.
- **H2:** the median absolute difference between the 20 Hz mean of `power.draw` and the sweep's own
  2 Hz `power_avg_w` is **at most 1%**.
Reported, always: every reading's median signed difference from the counter, overall and per
configuration (which also repeats §17 on six configurations).

**What each outcome means, decided now.** H1 holds: the counter agrees with the instant reading and
the gap is in what `power.draw` reports, an averaged value, not a scope difference; the counter is the
better figure for timed windows. H1 fails: the counter and the instant reading differ too, and the
gap stays unexplained. H2 holds: sampling at 2 Hz is not the cause; H2 fails: it is part of it.
Neither is a shunt; this tests consistency between the card's readings, not accuracy.

### ⛔ Amendment to §18, 2026-10-07 ~13:30, during collection and before any §18 data was read

GPT Job 54 (`docs/gpt-findings/2026-10-07-nvml-power-semantics.md`, reviewed by Claude) found the
"what each outcome means" paragraph above stronger than a pooled median test can carry. **H1, H2,
their thresholds and the scorer are unchanged.** The meanings are narrowed to:
- **H1 holds:** pooled agreement within 2% between the counter and the instant reading. That supports
  the §17 gap being specific to the averaged path that `power.draw` reports (NVIDIA documents it as a
  one-second average of board power on Ampere and newer, except GA100). It does **not** establish
  identical electrical scope, the absence of a bias common to both, the counter's accuracy, or
  agreement for every workload. **H1 fails:** averaging alone does not explain the gap; nothing is
  concluded about which reading is right.
- **H2 holds:** for the median window, the 2 Hz and 20 Hz means of the same field do not differ
  materially; this does not rule out a sampling effect for individual workloads. **H2 fails:** host
  sampling contributes, and its signed direction is reported, because a failure that does not run in
  the direction of §17's positive gap does not explain it.
- The per-workload and per-configuration signed differences are reported beside both, always.

**Recorded now, before the data, as an exploratory reading, not a prediction:** if `power.draw` is a
one-second rolling average, the window's opening second partly averages pre-load power, so the
sampled figure should read lowest where the work before the window is shortest. Each benchmark's
warm-up is 5 iterations: about 0.3 s for `gemm` and a few milliseconds for the memory-bound kernels,
which matches the direction of §17's workload split (+3% against +7 to +10%). The 20 Hz log can show
this directly by comparing the average field against the instant field in each window's first
second. It is reported as exploratory whatever it shows.

### ⛔ §19 scorer hardened, 2026-10-07 ~14:20, during collection and before any §19 data was read

GPT Job 56 (`docs/gpt-findings/2026-10-07-section16-audit.md`) found four ways the §16 scorer could
mis-score synthetic inputs; `analysis/score_session19.py` shared three of them and is fixed the same
way: a return of exactly 1.5% now passes (the registration fails only what *exceeds* it; float
rounding had put it at 1.5000000000000013%); a repeated target, a target off the registered grid, or
a non-finite or non-positive value is refused; a lock that overshot its target is excluded, as
`analyze_sweep` does; and an incomplete suite already marked NOT SCOREABLE no longer stops the other
suites being scored. **Predictions, thresholds and the gate are unchanged.** None of these cases
occurs in the real §16 data, whose verdicts the audit reproduced.

### §19: the key optima, by the energy counter

Scored by `python analysis/score_session19.py <dir>`, committed and tested with this registration.
Optimum per workload is the target with the highest throughput per watt, computed from
`energy_avg_power_w`.

**Scoreable only if (§15 R3's rule):** the two stock suites have the same energy median and no
workload's median absolute matched-target throughput change between them exceeds 1.5%. A lost stock
role voids everything; a lost treatment role voids its own suite.

**Predictions, energy figure:** the median optimum is **1545 MHz** for both stock suites and P5,
**2010** for P4, **1702** for rung B and **1852** for rung C, the values registered for the sampled
figure in §15 R3, §16 and the ladder.

**Reported, always:** the same medians from the sampled figure, and per arm the workloads whose
optimum differs between the two figures.

**What each outcome means, decided now.** All hold: the registered optima do not depend on which
power reading is used. Any fails: that arm's optimum depends on the power reading, and the paper says
so beside that result. N=1 chip, one session, one suite per arm; the twelve workloads are repeated
outcomes on it.

### Result, 2026-10-07: §18 H1 and H2 both FAIL; §19 HOLDS at every arm

Collected unattended 08:57–15:08 (`data/frequency-sweeps/5060ti-session19-20261007/`), after the
dry run the same morning. **72 sweeps, all exit 0, 0 display-driver events, 0 desktop-load exits,
0 retries, 0 of 936 windows flagged (5.8–11.2 fps).** Every witness passed: memory 13801 MHz on
stock and 16301 on the tuned arms, power limits 180 / 200 W, stores restored byte for byte,
mVolt+ offsets 0. `gemm` at a locked 2475 MHz: stock 180.1 / P5 150.7 / P4 151.3 / rung B 149.9 /
rung C 151.8 / stock 179.8 W. The 20 Hz logger ran the whole session, 445,145 rows over 6.18 h.

```
python analysis/score_power_fields.py data/frequency-sweeps/5060ti-session19-20261007
python analysis/score_session19.py data/frequency-sweeps/5060ti-session19-20261007
```

**§18, 936 points joined, 0 skipped:**

| prediction | result | verdict |
|---|---|---|
| **H1:** instant at 20 Hz within 2% of the energy counter (median absolute) | **8.05%** | ⛔ FAILS |
| **H2:** `power.draw` at 20 Hz within 1% of the sweep's 2 Hz sample (median absolute) | **1.17%** | ⛔ FAILS |

Median signed difference against the energy counter; every **median** is above it, though per window the sampled figure is below the counter in 275 of 936 (GPT Job 61):

| configuration | sampled 2 Hz | `power.draw` 20 Hz | average 20 Hz | instant 20 Hz |
|---|---:|---:|---:|---:|
| all | +2.86% | +3.24% | +3.24% | +8.04% |
| stock (opening) | +4.81% | +5.02% | +5.02% | +9.61% |
| P5 | +2.29% | +2.29% | +2.29% | +8.02% |
| P4 | +2.16% | +2.50% | +2.50% | +7.44% |
| rung B | +3.21% | +3.75% | +3.75% | +8.83% |
| rung C | +0.20% | +0.30% | +0.30% | +5.75% |
| stock (closing) | +3.92% | +4.74% | +4.74% | +8.81% |

`power.draw` equals the average field in all but 25 of 445,145 logger rows, and in every joined
window mean but one (by 0.0008 W). **H2's signed direction**, which the amendment requires: the
median signed difference of `power.draw` at 20 Hz from the 2 Hz sample is **+0.14%**, 497 windows
positive and 439 negative (`analysis/explore_power_fields.py`). ⛔ *This first said "scatter in both
directions, not a bias". A pooled median near zero does not show that: by workload it runs from
−1.11% (`conv`) to +1.37% (`bgemm1024`); GPT Job 61.* Pooled, it is far smaller than the
several-percent gaps here.

**Per workload, which the amendment also requires and the first filing omitted** (median signed,
78 windows each; added 2026-10-08 after GPT Job 61):

| workload | sampled vs counter | `power.draw` vs counter | instant vs counter | H2: `power.draw` vs sample |
|---|---:|---:|---:|---:|
| `attention` | +1.66% | +1.49% | +5.00% | −0.39% |
| `bgemm1024` | +3.26% | +4.55% | +9.35% | +1.37% |
| `bgemm128` | +7.38% | +9.00% | +14.65% | +0.50% |
| `bgemm256` | +6.28% | +7.11% | +11.09% | +0.44% |
| `bgemm32` | +2.47% | +3.34% | +9.88% | +0.95% |
| `bgemm64` | +4.71% | +6.50% | +12.58% | +1.15% |
| `conv` | +6.94% | +4.67% | +9.70% | −1.11% |
| `copy` | −1.26% | −1.11% | +4.26% | −0.10% |
| `gemm` | +10.93% | +9.28% | +13.62% | −0.53% |
| `layernorm` | −0.61% | −0.47% | +4.96% | −0.00% |
| `reduce` | −1.85% | −1.76% | +3.30% | +0.47% |
| `softmax` | +0.65% | +0.68% | +6.67% | +0.10% |

**What follows, as amended before the data.** H1 fails: averaging alone does not explain the gap
between the readings, and nothing is concluded about which reading is right. H2 fails: host
sampling contributes, with a pooled signed median of +0.14% and workload medians of both signs, so
it is too small to account for the pooled gaps. ⛔ *This first said it "does not run in the direction
of any gap here", which is false of the positive workloads (Job 61).*

⛔ **And §17 did not repeat in sign.** §17 found the counter a median 7.83% **above** the sampled
figure at every one of 156 points (stock, one suite, 2026-10-06). Here the sampled figure is above
the counter in every configuration; on the opening stock suite, the closest match to §17, the
per-window counter figure is a median **4.59% below** it. The counter's per-window figure is
therefore not stable across sessions on this card. See the exploratory section below for the
difference between the two sessions; **the reason is not established.**

**§19, energy figure:**

| arm | predicted | energy median | sampled median | optima differing between figures | verdict |
|---|---:|---:|---:|---:|---|
| stock (opening) | 1545 | 1545 | 1545 | 4 of 12 | ✅ HOLDS |
| P5 | 1545 | 1545 | 1545 | 3 of 12 | ✅ HOLDS |
| P4 | 2010 | 2010 | 2010 | 6 of 12 | ✅ HOLDS |
| rung B | 1702 | 1702 | 1702 | 3 of 12 | ✅ HOLDS |
| rung C | 1852 | 1852 | 1852 | 3 of 12 | ✅ HOLDS |
| stock (closing) | 1545 | 1545 | 1545 | 5 of 12 | ✅ HOLDS |

Gate: stock energy medians equal (1545, 1545); worst stock return **0.048%** (limit 1.5%).

**What follows, as decided in advance.** All hold: the registered medians do not depend on which
power reading is used. ⚠️ **Per-workload optima do:** 3 to 6 of 12 differ between the two figures
in every arm, as in §17 (4 of 12). Of the 24 that differ, **21 move one grid step, two move two and
one moves three** (P4 `softmax`, 1545 → 2010; P4 `bgemm64` and rung C `reduce` move two). ⛔ *This
first said "resolved only to about one grid step"; GPT Job 61 found the three larger moves.* So the
power reading can move a per-workload optimum by more than a step, and the paper must not quote one
as if it were fixed.

⚠️ **And the median test is coarse (Job 61, rechecked here).** In every arm 8 to 11 workloads share
the median grid point, so no single workload's one-step change could have moved any arm's median;
it takes 2 to 6 simultaneous shifts. HOLDS shows the registered medians survive the change of power
reading. It could not have detected a change in one workload, and does not say none occurred.

#### Exploratory, not registered: what the 20 Hz log shows

`python analysis/explore_power_fields.py data/frequency-sweeps/5060ti-session19-20261007`, written
after scoring. No threshold is applied and none of this is a test.

- **Over the whole session the readings agree.** The counter totals **1104.4 kJ** over 6.18 h,
  against **1113.2 kJ** integrated from the instant field (counter −0.79%) and **1111.6 kJ** from the
  average field (−0.64%). The per-window disagreement is not a disagreement about total energy.
- **The averaged field lags at a load step.** Over the first second of each timed window the
  instant field reads a median **+82.8%** above the average field; over the rest of the window,
  **+0.9%** (936 windows). That is what a trailing one-second average does when load starts at the
  window's edge, as the amendment's pre-recorded reading expected. ⚠️ The exact figures belong to the
  one-second split: at 0.95 s and 1.05 s the first part reads +88.6% and +77.0% (Job 61). The
  contrast between the opening and the rest holds at every split from 0.25 to 2 s, and rejoining
  each field on NVML's own timestamps leaves it unchanged.
- **The workload pattern reproduces §17's.** Instant at 20 Hz over the 2 Hz sample, median by
  workload: `attention` +1.79, `conv` +2.00, `gemm` +3.07, `bgemm256` +4.63, `reduce` +4.89,
  `bgemm128` +5.01, `copy` +5.33, `bgemm1024` +5.65, `layernorm` +5.73, `softmax` +5.89, `bgemm64`
  +6.68, `bgemm32` +6.70%. The three kernels with the longest warm-up have the smallest gap, as in
  §17 (+3% against +7 to +10%). **That fits the warm-up reading**: the sampled figure reads 2–7%
  below the instant one, least where the load ran longest before the window. It is an association
  across twelve workloads on one card. ⛔ *This first said the sampled figure "under-reads a short
  window by 2–7% depending on how long the load ran before it". The design does not isolate warm-up
  from the workloads' other differences (duration, load shape, launch pattern), and the instant
  reading is not known to be right either (Job 61).*
- **The counter's per-window figure moved between sessions.** Per window, the counter over the 2 Hz
  sample has median −2.78% here (range −18.7 to +10.5%; by configuration −4.59 stock opening, −2.24
  P5, −2.12 P4, −3.11 rung B, −0.20 rung C, −3.77 stock closing), against +7.83% in §17. One
  difference between the sessions is that this one was polled: HWiNFO read the card every 0.5 s
  and the logger read the counter 20 times a second. §17 ran with neither. Dauner et al. (HotCarbon
  2026, `docs/RELATED-WORK.md` §15; read by GPT, not here) report energy-counter under-reading at short polling intervals,
  including on an RTX 5060 Ti. ⚠️ **That is a candidate, not a finding:** the sessions also differ
  in date, configuration order and length, and no session here varied polling alone.
- **Added after GPT Job 57 audited §17, same evening.** Here too the 2 Hz figure often opens on an
  idle reading: **250 of 936** windows begin with an idle-memory sample (§17: 52 of 156), and the
  median window's lowest sample is 0.21 of its mean (§17: 0.20). And §17's per-workload counter gap
  ranks the twelve workloads much as this session's instant-over-sampled gap does (Spearman
  **0.62**; `attention`, `conv` and `gemm` lowest in both). Read together, the sampled figure
  under-reads short windows in both sessions, and what changed between them is the counter's
  per-window figure. ⚠️ That reading is post hoc, across two sessions on one card, and not tested.

**What this supports, and no more:** on one RTX 5060 Ti, the medians registered for the floor
ladder and its controls are the same whichever power reading is used. The readings disagree per
window by several percent, in a direction that changed between two sessions, while agreeing within
0.8% on total energy over six hours. **Neither reading is a shunt, and nothing here says which is
right.** N=1 chip, one session, one suite per arm.

## 20. RTX 5060 Ti: where efficiency peaks relative to the floor's end, on a fine grid. Registered 2026-10-07, before collection — COLLECTED 2026-10-08: F1, F2 and F3 HOLD on both configurations

**Chosen by Raymond 2026-10-07 (night) for the 2026-10-08 school day; committed before any §20
sweep.** One session: `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20`, launched by
`C:\headroom-bench\Run-S20Morning.ps1`, which runs a dry run first (not data) and starts the real
session only if the dry run exits 0, records all four arms and sweeps the descending suite
descending.

**Why.** The paper says the floor's end is "an upper bound rather than the exact peak" (submission
§5.2, marker R06). That rests on **one** clean fine-grid `gemm` sweep (`5060ti-finefloor-20260918`
r2: argmax 1402 MHz achieved, 1.975% lost at the last floor point 1560, 0.622% at the decoded-curve
pick 1530; GPT Job 59). The seven fine `gemm` sweeps of 2026-09-22 peak between 1377 and 1552 MHz
achieved (two are early runs with transient degraded points), and no other workload has ever been
swept finely. Every suite optimum in the project sits on a 150–158 MHz
grid, where the floor end and the peak are the nearest point to both. This tests the statement on
twelve workloads and two configurations, one of them the edited curve.

**Design.** Stock (Afterburner Profile 3, 180 W, memory +0) and the full tune (Profile 4, P4, 200 W,
memory +2500), in the order **stock ascending → P4 ascending → P4 descending → stock descending**,
twelve workloads each with §10's iteration counts, every point a locked target. Each configuration
gets an **18-point grid at 37.5 MHz** (every fifth supported clock), nine targets below its
registered floor end and eight above:
- stock: 1237, 1275, …, 1537, **1575**, 1612, …, 1875 MHz;
- P4: 1672, 1710, …, 1972, **2010**, 2047, …, 2310 MHz.

The registered floor-end targets come from earlier data, fixed now: **stock 1575 MHz** (worklist 4h,
2026-09-22: 0.720 V held through 1567 MHz achieved, at target 1575) and **P4 2010 MHz** (§16's
voltage extracts, the last target at 0.720 V; P4's decoded floor ends at 2002). §15's conditions
1–4 carry over unchanged (desktop-load screen with one retry, Claude minimized, ChatGPT/Codex closed
by the runner, driver 616.92, mVolt+ offsets 0, profile store restored byte for byte from `curve3`
and section-hash verified, the 2475 MHz `gemm` witness recorded per arm). HWiNFO logs at 0.50 s for
the voltage join. **No 20 Hz NVML logger**: §18 left open whether polling the counter disturbs it.
Estimated 5.6 h from §19's per-point times.

Scored by `python analysis/score_session20.py <dir>`, committed and tested with this registration
(`analysis/test_score_session20.py`, 19 synthetic cases). Per workload, efficiency at each target is
throughput / `power_avg_w`, the 2 Hz figure every earlier result uses, **averaged over the ascending
and descending sweeps**. The energy-counter figure is reported beside it and not scored.

**Scoreable only if:** every usable stock workload's median absolute matched-target throughput change
between the ascending and descending stock suites is at most 1.5% (§15 R3's rule; a failure voids
everything); and a configuration has at least 11 usable workloads (both sweeps complete on all 18
targets, no role NOT SCOREABLE), or that configuration is NOT SCOREABLE.

**Predictions, each per configuration (stock and P4), each allowing two misses among the usable
workloads (10 of 12):**
- **F1 (upper bound):** the efficiency argmax is at or below the floor-end target plus one grid step
  (stock ≤ 1612, P4 ≤ 2047 MHz).
- **F2 (near-optimal at the floor end):** the median over workloads of the efficiency lost at the
  floor-end target, against that workload's maximum, is **at most 3%**.
- **F3 (falls above):** efficiency 300 MHz above the floor end (stock 1875, P4 2310 MHz) is lower
  than at the floor end.

**Reported, always:** each workload's argmax and its distance from the floor end in grid steps; how
many sit within one step of the floor end on either side (the struck reading "the optimum IS the
floor end"); how many sit at the grid's lower edge, where the peak is not bracketed; the per-direction
argmaxes; F1–F3 on the energy figure; and the floor end measured in this session's voltage extracts
(last target at the lowest code before the first rise), reported and never substituted for the
registered one.

**What each outcome means, decided now.**
- All three hold in both configurations: on this card, at 37.5 MHz resolution, the floor's end is an
  upper bound on where efficiency peaks for most workloads, and running there costs a median of 3% or
  less, on the stock curve and on an edited one. That supports the paper's upper-bound wording on
  twelve workloads instead of one.
- F1 fails: the efficiency peak sits above the floor's end for more than two workloads; the
  upper-bound statement must be withdrawn or restricted to the workloads where it held.
- F2 fails: the floor end is not near-optimal on this grid; "where to run" must not be written.
- F3 fails: efficiency does not reliably fall above the floor end, and the ridge-point reading itself
  is in doubt on this card.
- Holding on one configuration and failing on the other is reported as exactly that.
- Whatever happens, the "within one step" count says whether "the optimum IS the floor end" (struck
  2026-09-20) has any support on a fine grid, without being a test of it.

N=1 chip, one session, one sweep per direction per workload; the twelve workloads are repeated
outcomes on one card, and a 37.5 MHz grid still bounds where a peak can be read.

### Result, 2026-10-08: all three HOLD on both configurations

Collected unattended 08:38–14:20 after a clean dry run, **48 sweeps, 0 display-driver events, 0
desktop-load exits, 0 retries, no role NOT SCOREABLE**; filed in
`data/frequency-sweeps/5060ti-session20-20261008/`. Scored by
`python analysis/score_session20.py data/frequency-sweeps/5060ti-session20-20261008`.

| gate or prediction | stock (floor end 1575) | P4 (floor end 2010) |
|---|---|---|
| usable workloads | 12 | 12 |
| gate: stock ascending-to-descending, worst workload | 0.300% (limit 1.5%) | - |
| **F1** argmax ≤ floor end + 1 step | 11 of 12, ✅ HOLDS | 11 of 12, ✅ HOLDS |
| **F2** median loss at the floor end | 2.38%, ✅ HOLDS | 0.12%, ✅ HOLDS |
| **F3** lower 300 MHz above than at the floor end | 11 of 12, ✅ HOLDS | 11 of 12, ✅ HOLDS |
| within one step of the floor end (reported) | 5 | 9 |
| at the grid's lower edge (reported) | 0 | 0 |
| energy figure (reported): F1 / F2 / F3 | 11 / 0.69% / 11 | 11 / 0.04% / 11 |
| floor end in this session's voltage extracts (reported, not substituted) | median 1575, range 1537–1575, 24 sweeps | **median 2047**, range 1972–2047, 24 sweeps |

**The one miss in each configuration is `reduce`**, on F1 and F3 alike: argmax 1800 MHz on stock
(+6 steps, 4.75% lost at the floor end) and 2310 MHz on P4 (+8 steps, 4.86%), the top of P4's grid, so
its P4 peak is not bracketed. The other eleven stock peaks run from 1350 (`bgemm1024`, −6 steps,
0.81% lost at the floor end) to 1575; six of the twelve are two or more steps BELOW the end. On P4 nine sit
within one step and the losses at the floor end are all under 2.1% bar `reduce`.

⚠️ **Per-direction argmaxes disagree where the curve is flat.** P4 `bgemm32` peaks at 2010 ascending
and 2047 descending but at 1785 averaged, with 0.04% lost at the floor end; P4 `copy` 2010 / 2272;
P4 `conv` 1785 / 2010; P4 `gemm` 2010 / 1860. Where the loss at the floor end is a fraction of a
percent, the argmax's location is an uncertain estimate, so the steps column must be read beside
the loss column. ⛔ *This said "is not a measurement of anything" until GPT Job 69 (2026-10-08): the
direction gap exceeds the top-three spread for 7 of 12 P4 and 6 of 12 stock workloads, but not for
all (P4 `gemm`: 0.45% spread against a 0.19% gap). Uncertain, not noise.*

**What it means, as decided before collection:** on this card, at 37.5 MHz resolution, the floor's
end is an upper bound on where efficiency peaks for 11 of 12 workloads and running there costs a
median 2.4% or less, on the stock curve and on an edited one. That supports the paper's upper-bound
wording on twelve workloads instead of one `gemm` sweep. **Only 5 of 12 stock peaks sit within one
step of the end**, so "the optimum IS the floor end" (struck 2026-09-20) gets no support on stock; on
P4 its 9 of 12 coincide with a curve flat enough that the argmax hardly matters.

⚠️ **P4's floor ended one step later than registered** in this session (2047 against 2010). The
registered value was scored, as the design requires. ⛔ *This said "it changes no verdict" until GPT
Job 69:* as a labelled sensitivity analysis with 2047 substituted, F1 holds (11 of 12) and F2 holds
(median loss 1.98%, against 0.12% at 2010), but F3 cannot be evaluated, because 2047 + 300 = 2347 MHz
was never collected.

**GPT Job 69's audit, 2026-10-08** (`docs/gpt-findings/2026-10-09-section20-audit.md`): all six
verdicts reproduce from independent code. Qualifications, all recomputed there:
- **Pooled is not per-direction.** On the ascending stock sweep alone F2's median loss is **3.14%**,
  above the limit; descending alone 1.90%. The registered direction mean holds by 0.62 points, and one
  workload's floor loss rising past 3.27% (for example `gemm`) would flip stock F2. P4 F2 cannot be
  flipped by one workload. F1 and F3 need two more misses to fail on either configuration.
- **"Upper bound" means floor end + one step** on sampled targets: P4 `copy`, `softmax` and
  `attention` peak at 2047, one step above the registered 2010.
- **Scorer defects, none affecting this session** (no exact ties, no zero energy, no retry lists):
  exactly 3% could fail on float rounding; exact ties went to whichever target the CSV listed first;
  a zero energy figure crashed scoring; an empty retry list crashed it. **Fixed after scoring,
  2026-10-08**, with four tests; re-scoring gives identical output. The docstring's "cancels a linear
  drift" was too broad and is narrowed.

**Deviations, stated:**
- **GPT Job 65, the pre-scoring audit of the registration and scorer, had not landed when this was
  scored.** The scorer, its 19 tests and the registration were committed before collection
  (`3129fa0`, `c1b5b09`); Job 65 now audits a scored session, which is weaker than intended.
- Claude ran a few seconds of file reads (census and CSV headers, no tests, no git) around
  09:50–10:10 beside the sweep. Every window in the session passed the desktop-load screen
  (864 of 864 quiet, 4.0–8.0 fps) and the stock drift gate is 0.300%.

N=1 chip, one session, one sweep per direction per workload; the twelve workloads are repeated
outcomes on one card.

## 21. RTX 5060 Ti: does the floor's end bound the efficiency peak for application workloads? Registered 2026-10-08, before collection

**Chosen by Raymond 2026-10-08 (evening) for the 2026-10-09 school day; committed before any §21
sweep.** §20 tested the floor-end upper bound on the twelve synthetic kernels; every workload this
project has swept is a kernel. This repeats §20's tests on four **application workloads** designed by
GPT Job 60 (`docs/gpt-findings/2026-10-07-real-workload-scoping.md`) and implemented in
`tools/frequency-sweep/app_workloads.py`, plus a coarse stock sweep to compare their optima with the
suite's.

**The workloads, and what they are not.** One iteration is one complete task:
- `alexnet`, `resnet50`: a full forward pass of the torchvision architecture (ResNet-50 v1.5) over a
  batch of 16 images, FP32, TF32 off, cuDNN benchmarking off. **Seeded random weights**
  (torchvision's initialisation) **and a seeded synthetic input batch**, not pretrained checkpoints
  or photographs: the arithmetic is the network's, the values are not, and switching activity, and so
  power, may differ from a trained network's by an amount nobody has measured. No download.
- `kmeans`: a complete fixed-iteration Lloyd run (20 updates, then a final assignment and inertia) on
  Job 60's generated mixture, 1,048,576 points × 32 features, 16 clusters.
- `hotspot`: Rodinia's HotSpot thermal simulation with its physical constants, 100 explicit steps over
  16 chips of 1024 × 1024 cells, Job 60's analytic temperature and power maps.
k-means and HotSpot are this project's eager PyTorch ports, not the Rodinia binaries. Sizes are larger
than Job 60's pilot suggestions so that GPU work, not kernel launches, dominates.

**Validated before registration** (2026-10-08): `tools/frequency-sweep/test_app_workloads.py`, 15
CPU checks (the CNNs have torchvision's exact parameter counts; k-means memberships equal a float64
reference exactly; HotSpot within 1e-3 °C of a float64 clamped-edge reference; Rodinia's timestep is
stable at 1024 cells); GPU against CPU: CNN arg-maxes agree (relative logit difference 2.1e-4 and
1.3e-6), k-means memberships identical, HotSpot within 7.6e-6 °C.

**Timing pilot, 2026-10-08, stock, recorded here because it informed nothing but iteration counts.**
Calibrated at unlocked boost for about 9 s: `alexnet` 3484, `resnet50` 424, `kmeans` 85, `hotspot` 14
iterations. Locked at 1237 and at 3090 (achieved about 2707–2745) MHz, the runs took 11–17 s and
9.1–9.3 s, and throughput rose 1.91×, 1.77×, 1.75× and 1.17× for a 2.19× clock rise, so all four are
GPU-bound, HotSpot mostly memory-bound. **Power was not looked at**; no efficiency was computed. A
two-point HotSpot sweep through `Invoke-LoggedSweep.ps1` (1237, 3090; `C:\headroom-bench\results\
20261008-145842_apppilot-hotspot`, not data) verified the plumbing: exit 0, desktop load quiet,
unit `task/s`, `bench_ok` at both points. Its power columns were not read.

**Design.** One session, `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s21`, launched by
`C:\headroom-bench\Run-S21Morning.ps1` after a dry run that must pass. Order: **stock coarse ascending
→ stock fine ascending → P4 fine ascending → P4 fine descending → stock fine descending → stock coarse
descending**, all four workloads per step. Fine grids, registered floor-end targets (stock 1575, P4
2010 MHz) and everything about efficiency are §20's exactly. P4's floor end stays registered at 2010
for comparability with §20, although §20's own extracts put it at 2047; the one-step allowance covers
the difference, and the measured end is reported. The coarse grid is §10's 13 points, 1237–3090 MHz.
§15's conditions 1–4 carry over, with the 2475 MHz `gemm` witness per arm. No 20 Hz logger. Estimated
about 3.5 h.

Scored by `python analysis/score_session21.py <dir>` (`analysis/test_score_session21.py`, 15 synthetic
cases), committed with this registration. It imports §20's grids, reader, estimator and tests.

**Amendment, 2026-10-08, before any §21 data exists.** GPT Job 69 found four boundary defects in
§20's scorer, which §21's imports; they were fixed the same evening, before collection. **An exact
tie in efficiency goes to the lowest target**, in A1–A4 and the per-direction argmaxes; a loss of
exactly 3% holds A2; zero optional energy figures and empty retry histories no longer crash scoring.

**Scoreable only if:** the stock fine ascending and descending sweeps agree within 1.5% per usable
workload (median absolute matched-target throughput change), or A1–A3 are NOT SCOREABLE; the stock
coarse pair meets the same rule, or A4 is NOT SCOREABLE; and a configuration has at least three usable
workloads. With four usable workloads each test allows **one** miss; with three, none.

**Predictions:**
- **A1, per configuration (stock, P4):** the fine-grid efficiency argmax is at or below the floor end
  plus one step (stock ≤ 1612, P4 ≤ 2047 MHz).
- **A2, per configuration:** the median efficiency lost at the floor-end target is at most 3%.
- **A3, per configuration:** efficiency 300 MHz above the floor end is lower than at it.
- **A4, stock coarse grid:** the efficiency argmax is at or below 1702 MHz, the first coarse target
  above the stock floor end.

**Reported, always:** per-workload argmaxes, distances in steps and losses; per-direction argmaxes;
the energy-counter figure; the floor end measured in this session; how many coarse argmaxes sit at
the twelve-workload suite's 1545 MHz.

**What each outcome means, decided now.**
- All hold: on this card the floor-end upper bound, measured on kernels in §20, also holds for these
  four application workloads, on the stock curve and an edited one.
- A1 or A4 fails: at least two of the four peak above the floor end; the paper may not extend the
  upper-bound statement beyond kernels, and says so.
- A2 fails: running at the floor end costs these applications more than 3%; "where to run" must not be
  written for them.
- A3 fails: efficiency does not fall above the floor end for them.
- Either way, four workloads, two of them CNNs with random weights, are a pilot extension, not
  application coverage. N=1 chip, one session.

### Result, 2026-10-09: A1–A4 all HOLD

Collected unattended 08:46–11:55 after a clean dry run, **24 sweeps, 0 display-driver events, 0
desktop-load exits, 0 retries, no role NOT SCOREABLE**; filed in
`data/frequency-sweeps/5060ti-session21-20261009/`. Scored by
`python analysis/score_session21.py data/frequency-sweeps/5060ti-session21-20261009`.

| gate or prediction | stock (floor end 1575) | P4 (floor end 2010) |
|---|---|---|
| usable workloads | 4 | 4 |
| gate: stock fine ascending-to-descending, worst workload | 0.104% (limit 1.5%) | - |
| gate: stock coarse ascending-to-descending, worst workload | 0.083% (limit 1.5%) | - |
| **A1** argmax ≤ floor end + 1 step | 4 of 4, ✅ HOLDS | 4 of 4, ✅ HOLDS |
| **A2** median loss at the floor end | 0.40%, ✅ HOLDS | 0.55%, ✅ HOLDS |
| **A3** lower 300 MHz above than at the floor end | 4 of 4, ✅ HOLDS | 4 of 4, ✅ HOLDS |
| **A4** coarse argmax ≤ 1702 MHz | 4 of 4, ✅ HOLDS; all four at 1545 | - |
| within one step of the floor end (reported) | 3 | 4 |
| at the grid's lower edge (reported) | 0 | 0 |
| energy figure (reported): A1 / A2 / A3 | 4 / 0.57% / 4 | 4 / 0.00% / 4 |
| energy figure (reported): coarse argmax | all four at 1545 | - |
| floor end in this session's voltage extracts (reported, not substituted) | median 1575, range 1537–1575, 8 sweeps | **median 2047**, range 2010–2047, 8 sweeps |

| workload | stock argmax (steps, loss at 1575) | P4 argmax (steps, loss at 2010) | coarse |
|---|---|---|---|
| `alexnet` | 1537 (−1, 1.51%) | 2047 (+1, 0.21%) | 1545 |
| `resnet50` | 1575 (0, 0.00%) | 2047 (+1, 0.89%) | 1545 |
| `kmeans` | 1575 (0, 0.00%) | 2047 (+1, 0.93%) | 1545 |
| `hotspot` | 1500 (−2, 0.81%) | 2010 (0, 0.00%) | 1545 |

Per-direction argmaxes differ for stock `hotspot` (1500 ascending / 1537 descending), P4 `alexnet`
(2010 / 2047) and P4 `kmeans` (1972 / 2047). As in §20, where the loss at the floor end is under 1%
the argmax's location is an uncertain estimate.

**What it means, as decided before collection:** on this card the floor-end upper bound measured on
kernels in §20 also holds for these four application workloads, on the stock curve and an edited one,
and all four coarse stock optima sit at the twelve-workload suite's 1545 MHz. ⚠️ **Four workloads,
two of them CNNs with random weights and two of them PyTorch ports: a pilot extension, not
application coverage.** N=1 chip, one session, one sweep per direction per workload.

⚠️ **P4's floor again ended at 2047**, one step above the registered 2010, as in §20; three of the four
P4 peaks sit at 2047, inside the one-step allowance. The registered value was scored. As in §20, an
A3 at 2047 + 300 = 2347 MHz cannot be evaluated because that target was not collected.

**Deviations, stated:**
- Claude ran one `nvidia-smi` query and a few log reads at about 09:08–09:09, during the start of
  `s21-stock-coarse-asc-hotspot`. Every window in the session passed the desktop-load screen (392 of
  392 quiet, 4.0–8.1 fps), and the coarse return gate, which includes that sweep, is 0.083%.
- No pre-scoring outside audit was requested for §21's scorer beyond GPT Job 69's audit of §20's,
  which §21's imports.

## 20b. RTX 5060 Ti: does field-83 energy polling, or the power-query bundle, change the counter's reported power? Registered 2026-10-11, before any pilot session under this design — STOPPED 2026-10-20 after four pilots: insufficient precision, no verdict

**Adopted by Raymond 2026-10-11 (evening).** Text from GPT Job 77
(`docs/gpt-findings/2026-10-11-section20b-registration-text.md`), on GPT Job 71's design
(`docs/submission/drafts/section20b-registration-draft.md`), reviewed by Claude against the code.
Core sessions only: Job 71's logger-plus-HWiNFO exploratory panel is not part of this registration.
**N=1 chip; sessions are repeated observations of it.**

**Why, and what was already seen.** §17 and §18 gave opposite signs for the counter-versus-sampled
gap, and polling was the untested candidate (Jobs 61/62). The supervised tool qualification of
2026-10-09 (`docs/section20b/qualification-20261009/`) ran one window per arm in three cells: with
field 83 polled, **E and EP read 9.5–20.6% below A**, wall throughput within 0.21% of A. **That was
seen before this text was written, motivates it, and is not data or a verdict.** The ±2 pp band and
the sizing formula below are Job 71's, written before that qualification, and unchanged.

**History before registration, all excluded from inference:**
- **Pilot index 1, attempt 1, 2026-10-11, under the superseded 2475 MHz design** (`56e29ba`,
  `docs/section20b/pilot1-attempt1-20261011/`). It stopped correctly at `w020-P`, gemm at 2475 MHz,
  whose clock fell to 2437 at 178.5 W against stock's 180 W cap. Its 20 earlier windows' energies were
  not compared across arms. **It is retained, listed and counts for nothing**: the design changed
  because of it, the old schedule cannot be scored under the new one, and pilot indices 1–4 start
  afresh under this design.
- **Qualification at 2317 MHz, 2026-10-11 19:34–20:04** (`52e6a4f`,
  `docs/section20b/qualification-20261011/`): 36 of 36 windows clean, operator away by Raymond's choice.
- **Qualification on the registered code, 2026-10-11 from 21:46** (`96c683f`), repeated because
  `051dd7a` changed the watcher's filter and the cleanup paths after the one above: 36 of 36 clean,
  the watcher stopped and reaped with exit 0 (`docs/section20b/qualification-20261011b/`). Neither
  qualification's arms were compared.

**Conditions.** Stock Afterburner Profile 3 from the hash-checked `curve3` store, 180 W, memory offset
0, mVolt+ offsets and voltage demands 0, driver 616.92. The runner witnesses stock (gemm at a locked
2475 MHz, outside the core windows, recorded only), closes HWiNFO, Afterburner and RTSS, re-checks
stock, and minimizes Claude. The controller's preflight requires one NVIDIA device, driver 616.92, the
limit within 0.5 W of 180, idle utilization under 10% and video engines at 0%. A command-line process
inventory before and after every row visit must succeed and show no forbidden process (the frozen list
in `run_core_session.py`, including ChatGPT and Codex), no GPU poller and no visible Claude window. CPU
load is recorded, not gated. There is no continuous power sampler, HWiNFO screen or achieved-clock
trace in the core windows; boundary witnesses can miss a transient. A watcher subscribed to the System
log stops a window at the first display-driver event (ID 4101, or a provider like `*nvlddmkm*`).

**Cells and fixed work.** Nine equally weighted cells: gemm, softmax and copy, each at **1545, 2010 and
2317 MHz** (supported clocks 1537, 2002 and 2310). fp32, frozen in `design.WORKLOAD_SPEC`:

| Kernel | Iterations/window | Size | Work/iteration | Unit |
|---|---:|---|---:|---|
| gemm | 120 | 8192 × 8192 | 1,099,511,627,776 FLOP | FLOP/s |
| softmax | 2600 | 8192 × 18310 | 1,199,964,160 bytes | byte/s |
| copy | 2660 | 150,000,000 elements | 1,200,000,000 bytes | byte/s |

Counts are §19's stock ones and never change by arm, target, pilot result or deadline. Byte work is
the benchmark's declared work, not measured DRAM traffic. **Why 2317, not 2475:** at 2475 stock gemm
averaged 173.6 W and peaked at 183.5 W across §19's opening and closing sweeps, over the 180 W cap; at
2317 it averaged 145.8 W and peaked at 156.1 W (Job 77, recomputed from the six §19 stock CSVs). A
common top target keeps one frequency set for all three kernels.

**Arms.** One reader process in every arm, on the same nominal 20 Hz schedule and writer:

| Arm | Reader calls per poll, in order |
|---|---|
| A | none: timing and status rows only |
| E | one `nvmlDeviceGetFieldValues` batch: field 83 |
| P | `nvmlDeviceGetPowerUsage`, then one batch: fields 185, 186 |
| EP | `nvmlDeviceGetPowerUsage`, then one batch: fields 185, 186, 83 |

Every arm keeps the benchmark's common queries: one energy-counter support read and two
`nvmlDeviceGetTotalEnergyConsumption` endpoints, temperature-only safety reads, and NVML SM and memory
reads just outside the timed region. Added API cost is part of the treatment. P is a bundle of power
paths, not one path.

**Timing and order.** Per window: stop the previous reader; lock the target; record an idle witness
(not gated: an idle card keeps its previous state); wait 30 s with no power or energy monitoring
(measured washout must be at least 29.99 s); start the arm's reader; five warm-up iterations; at least
1.0 s of synchronized same-kernel preload (actual duration recorded, no upper cutoff); energy endpoint;
the fixed work; energy endpoint; stop the reader. **T** is the difference between the two endpoint
calls' midpoints. Each cell's four arms run contiguously in its Williams row's order:

| Row | 1st | 2nd | 3rd | 4th |
|---|---|---|---|---|
| 1 | A | E | EP | P |
| 2 | E | P | A | EP |
| 3 | P | EP | E | A |
| 4 | EP | A | P | E |

`random.Random(71020 + index)` shuffles the four rows, then the nine cells within each row; 144
windows, 36 per arm, saved with seed, date and commit before the first window. **Pilot indices 1–4
(seeds 71021–71024); confirmation indices from 101 (seeds from 71121), the first S of them.**

**Window validity** (`tools/section20b/validate.py`, shared by controller and scorer). Every window
must have: lock, benchmark and reader exit 0, no failure, `ok`, no abort, all iterations, and the frozen
workload, dtype, size, unit and work; warm-up 5 and preload at least 1.0 s; integer energy endpoints
with `E_end > E_start ≥ 0`, finite ordered call brackets, the synchronized work inside them, T within
1e-6 s and work within 1e-9 relative of the cached values; exactly one successful support read; every
temperature finite and strictly below 88 °C; **SM within 15 MHz of target and memory 13801–14001 MHz
at both boundaries**; the reader's mode, columns, row count, contiguous sequence and call count exact,
with zero failed calls, every return 0, field types 83 → 3 and 185/186 → 1, finite non-negative values,
integer timestamps and latencies, ordered brackets and strictly increasing poll starts covering both
endpoint midpoints. In E, P and EP, over the poll starts inside T: at least 20 intervals, median 45–55
ms and nearest-rank 99th percentile at most 100 ms. Stale field timestamps are reported, never gated.

**Session validity.** The canonical schedule, seed and constants; every window once and in order; a
recorded commit and date; no preflight problem; controller complete with exit 0 and a clean reset with a
finite readback; the watcher stopped cleanly; all eight row-visit inventories clean; a readable event
log with zero driver events; and the runner's restoration record showing reset exit 0, the store
restored, 13801–14001 MHz under load and 180 W. **Any invalid window invalidates the whole session.** A
valid session is **scoreable** only if, in every cell, the last A visit's wall throughput is within
1.5% of the first (equality passes); otherwise VALID but NOT SCOREABLE. No energy or effect screen.

**Attempts and replacements.** Every attempt is recorded and kept, failures included; no window is
retried or deleted. One whole-session replacement per planned index, at most two per stage, only after a
recorded operational failure (a return-gate failure or a large effect is not one), on a later day, with
the same index, schedule and seed. After a driver reset or thermal abort, inspect before restarting.
**Sessions and attempts fall on distinct days across both stages**, and confirmation begins only after
the pilot is complete and S is committed. If a planned stage cannot be completed within these limits it
is NOT SCOREABLE; S is never reduced and no cell is dropped. **The attempt log:** before each pilot
launch Claude commits and pushes a line to `docs/section20b/ATTEMPTS.md` (index, date, commit), and
afterwards its outcome. Before confirmation that becomes a check the runner and scorer enforce (Raymond's
choice over Job 78's heavier design, `docs/gpt-findings/2026-10-11-section20b-attempt-ledger.md`); the
runner's confirmation launch path is also still to be built. Until then the scorer's stage checks apply
only to the directories it is given, and nothing here claims more.

**Estimands and pilot sizing.** Per window `J = (E_end − E_start)/1000`, `p = J/T`, `e = J/work`,
throughput `work/T`. Within each cell and row, against that row's A:
`d_E = 100(p_E/p_A − 1)`, `d_P = 100(p_P/p_A − 1)`, `d_EP = 100(p_EP/p_A − 1)`,
`d_I = 100(p_EP − p_E − p_P + p_A)/p_A`. Average the four rows within a cell, then the nine cells
equally: four contrasts per session, which are the units. **Pilot: four scoreable sessions.** Take each
contrast's sample SD over them (3 df) and `s_max`, the largest. Freeze the smallest integer **S in
8–32** with `t(1 − 0.05/8, S − 1) · 1.5 · s_max / √S ≤ 1 pp`, committed before any confirmation
session; if none qualifies, stop and report insufficient precision. The 1.5 is a chosen allowance, not
a bound. Pilot sessions never enter confirmation.

**Predictions: the interval rule, decided now.** For each confirmation contrast report the mean and
`mean ± t(1 − 0.05/8, S − 1) · SD/√S` (four 98.75% intervals, at least 95% family coverage under
independent, roughly normal session means). Against **±2 pp**: the whole interval above +2 is a
MATERIAL INCREASE, below −2 a MATERIAL DECREASE, strictly inside (−2, +2) PRACTICALLY EQUIVALENT for
the aggregate over these nine cells and days; anything else, touching a boundary included, is
INCONCLUSIVE.

**Reported, always:** every session's contrasts, the nine cell contrasts, energy per work and
throughput contrasts, raw endpoints, joules, T and work, boundary state, temperatures, cadence and
latency, staleness, the position summaries (descriptive; FLOP/s and byte/s are not one unit), and every
invalid or superseded attempt.

**What each outcome means, decided now.** Material E: adding field-83 polling changes the counter's
reported power on this baseline. Material P: the specified power-query bundle does. Material d_I: the
two are not additive on this scale; an EP effect with inconclusive singles does not show that by
itself. Four equivalent intervals: within 2 pp in aggregate over these cells and days only. Inconclusive
is never "no effect". A validity, return, stage or precision failure gives no verdict. A power change
cannot by itself be called counter corruption: monitoring can cost real energy, and no external meter
says which reading is right. It does not settle §17/§18's sign reversal, other polling rates, HWiNFO or
other cells. Thirty seconds is a chosen washout, not a measured carryover bound. N=1 chip.

**Scored by** `python analysis/score_section20b.py <session dirs> [--frozen-plan plan.json]`, with
`analysis/test_score_section20b.py`; collected by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts
s20b -Session N -ManageChatGpt`, which runs `tools/section20b/run_core_session.py`. About 2 h per
session (Job 77's forecast: 101 min before overhead); four pilots about 8 h, confirmation 16–64 h.

### Result — four pilots, 2026-10-12 to 2026-10-20: insufficient precision, no verdict

Pilots 1–4 ran on 2026-10-12, 13, 14 and 20, each SCOREABLE (`data/section20b/pilot1-20261012/` to
`pilot4-20261020/`; attempts 5–8 in `docs/section20b/ATTEMPTS.md`). Return gates 0.255%, 0.211%, 0.353% and
0.334%. `python analysis/score_section20b.py data/section20b/pilot*/core`:

| pilot | d_E | d_P | d_EP | d_I |
|---|---:|---:|---:|---:|
| 1 | −15.129 | −0.076 | −15.633 | −0.428 |
| 2 | −10.286 | −0.098 | −12.891 | −2.507 |
| 3 | −12.781 | +0.090 | −13.218 | −0.526 |
| 4 | −10.498 | −0.046 | −11.092 | −0.547 |

**The largest contrast SD is d_E's, 2.271 pp. No S from 8 to 32 meets the sizing rule:** at the cap,
S = 32, it allows an SD of at most 1.422 pp, and 2.271 gives a half-width of 1.597 pp against 1 pp. So,
as registered, §20b **stops and reports insufficient precision**. A precision failure gives no verdict, no
confirmation session is run, and nothing in the pilots may be cited as a §20b result. GPT Job 90 had
proved this outcome from pilots 1–2 alone (`docs/gpt-findings/2026-10-14-section20b-sizing-outlook.md`);
pilots 3 and 4 were run knowing it, for the day-to-day record and so the registration ends at its own
rule rather than by an amendment.

**Descriptive only.** On all four days, field-83 polling lowered the counter's reported power in every
cell, and the power-query bundle moved it by under a point in every cell. Throughput was unchanged within
0.1 pp at session level; single cells stayed within 0.16%, except pilot 3's `copy` at 2010 MHz under
field-83 polling, at −1.26%. ⛔ *This said "at unchanged throughput (within 0.1 pp), in every cell" until
the same evening: the bound holds for sessions, not cells (GPT Job 110, recomputed here with the scorer's
own functions).*
The size of the drop moved by about 5 pp between days, which is why the confirmation stage could not be
sized. Four days are four repeated observations of one chip. Neither reading is shown to be the right one:
the counter is the card's own telemetry and no external meter was used. This does not settle §17/§18's
sign reversal.

## 22. RTX 5060 Ti: day-to-day stock repeatability. Registered 2026-10-14 (approved by Raymond that evening), before any day — COMPLETE 2026-10-19: gemm and resnet50 WITHIN 3%, copy and reduce INCONCLUSIVE

**Why.** Every result here is one chip measured on one or a few days, and the §20b pilots showed a
counter effect moving ~5 pp between days. This asks how much stock efficiency curves, observed peaks and
the regret at the floor-end reference move from day to day on this card. Days are the units; **N=1 chip
throughout: five days are five repeated observations of one card, never five cards.**

**Source.** GPT Job 87's draft (`docs/gpt-findings/2026-10-13-repeatability-registration-draft.md`) is
adopted as written except for the changes listed at the end of this section; where the two differ, this
section rules. Implemented and tested before any day: runner part `-Parts rep -Session N`, scorer
`analysis/score_repeatability.py` (38 checks in `analysis/test_score_repeatability.py`, expected values
derived by hand), filing `tools/rerun15/file_repeatability_day.py`, and `gpu_workload.py --input-seed`.

**Conditions.** Stock Profile 3 restored from the `curve3` snapshot, section hash verified; 180 W
enforced; driver 616.92; mVolt+ offsets and voltage demands 0; arm witness memory 13801 MHz under load.
§15/§20 hygiene: ChatGPT/Codex closed, Claude minimized, Instant Replay off, no game or browser, HWiNFO at
0.50 s. No §20b reader and no 20 Hz sampler.

**Panel, fixed on every day.** `gemm` 120, `copy` 2660, `reduce` 2870 (§10/§20 counts; inputs drawn with
`--input-seed 20261013`), `resnet50` 424 (§21; seeds itself, 20261008). FP32, TF32 off, never
recalibrated. Grid, 20 requested targets: §20's 18-point stock grid 1237–1875 MHz plus 2010 and 2317.
`reduce` is kept on purpose: it is the known exception whose peak sits above the floor.

**One day.** Stock witnessed (90 s idle, the 2475 MHz `gemm` witness recorded only, memory and limit
checked, 90 s settle); the first pass, all four workloads in the day's order and direction; stock
re-witnessed; the second pass, order reversed and direction flipped:

| day | first pass | direction | second pass |
|---|---|---|---|
| 1 | gemm, copy, reduce, resnet50 | ascending | reverse, descending |
| 2 | copy, reduce, resnet50, gemm | descending | reverse, ascending |
| 3 | reduce, resnet50, gemm, copy | ascending | reverse, descending |
| 4 | resnet50, gemm, copy, reduce | descending | reverse, ascending |
| 5 | gemm, copy, reduce, resnet50 | ascending | reverse, descending |

Day 5 repeats day 1 deliberately. Days run in index order. Forecast 80–100 min a day (Job 87, from §20/§21
wrapper times), not yet measured in this mode.

**Validity, per day.** Exactly eight roles, each the registered grid in its declared order; every point
`bench_ok`, windowed power, finite positive throughput and power, achieved clock minimum and maximum within
±15 MHz of the target, loaded memory maximum 13801–14001 MHz, no thermal or hardware-slowdown reason, under
88 °C; every role's desktop-load verdict exactly `quiet`; the stock witness for every role; runner exit 0,
no display-driver event, cleanup verified (reset 0, store restored, 13801–14001 MHz, 180 W). **No role
retry and no replacement day**: a desktop-load role is kept and marked NOT SCOREABLE, the day continues for
the record, and the day is INVALID. Distinct local dates; **no date shared with any §20b attempt**
(`docs/section20b/ATTEMPTS.md`). Before each launch Claude pushes the day's line to
`docs/repeatability/ATTEMPTS.md`.

**Return gate**, per workload: median over the 20 targets of |pass-2 / pass-1 throughput − 1| at most 1.5%.
A valid day failing it is VALID, NOT SCOREABLE and reported separately. Only SCOREABLE days enter intervals.

**Estimands**, per workload, per day: efficiency = throughput / sampled power, the mean of the two
directions' ratios (§20's estimator); the curve, its shape anchored at 1575 MHz, the observed peak target
(ties to the lowest), the set within 1% of the peak, and the observed grid regret at the 1575 MHz reference.
Day-level means with pointwise 95% t intervals, SD with chi-square 95% intervals, the raw range always beside
them. The energy-counter figure and the measured VID floor are secondary and descriptive.

**Prediction, decided now.** For each workload, the 98.75% t interval for mean regret at 1575 MHz (four
workloads, Bonferroni) against 3%, §20's practical-loss reference: upper bound ≤ 3% is **WITHIN 3%**; lower
bound > 3% is **ABOVE 3%**; anything else is **INCONCLUSIVE**, never "no day effect". Five scoreable days
complete it; three or four are an explicitly PARTIAL result; fewer than three are descriptive only, with no
outcome. §20's pairs already put `copy` and `reduce` near or above 3% at 1575 MHz, so ABOVE 3% is a live
possibility and is reported as a result, not a failure. A moving peak label with small regret means a flat
curve, not an unstable optimum. No prior-art claim rides on this: repeatability is a property of this
dataset, and nothing here is novel.

**Changes from Job 87's draft, and why.**
- **No ambient instrument.** None is owned or calibrated (confirmed by Raymond at approval), so days are not
  conditioned on ambient. On-card and motherboard temperatures are recorded as what they are, never called
  ambient. Raymond noted 2026-10-14 was noticeably hotter than 2026-10-13, so room temperature is a known,
  unmeasured candidate source of day-to-day variation. If an instrument is added later, it is added as a
  disclosed amendment, secondary and descriptive only, and every earlier day stays "ambient unmeasured".
- **No raw per-point sidecars.** Validity uses the sweep CSV's window aggregates (achieved minimum and
  maximum, memory maximum, throttle masks, maximum temperature) and the wrapper result, as §20 and §21 did;
  raw HWiNFO logs are kept, gitignored, with their hashes.
- **Memory rule on the window maximum.** The window minimum reads 810 MHz in clean §20 stock sweeps, so the
  loaded state is tested on the maximum.
- **Distinct dates, not a 24 h gap.** Unattended launches follow Raymond's school days; start times are
  recorded and the gap reported, but only distinct dates (and none shared with §20b) are required.

**Scored by** `python analysis/score_repeatability.py data/repeatability/day*`; collected by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts rep -Session N -ManageChatGpt`; filed by
`python tools/rerun15/file_repeatability_day.py <session dir> --write`.

### Implementation hardened 2026-10-14, before any day (GPT Job 94)

**No rule above changed, and no day existed.** GPT Job 94 (`docs/gpt-findings/2026-10-15-section22-implementation-audit.md`)
found that the scorer trusted declarations for several of these rules. It now checks them from the evidence:
- **Dates and attempts:** both attempt ledgers are required; the first attempt at a day index in
  `docs/repeatability/ATTEMPTS.md` is the only eligible one, whatever order folders are given in; days follow
  index order; every local date a day occupies (its recorded date, both witnesses, every sweep's start and end)
  is checked against §20b and against every other day.
- **Display-driver events:** the runner reads the event log with the checked reader after every role and after
  cleanup, and the scorer requires each read to have succeeded with no events.
- **What ran:** exactly eight roles; each sweep's label, driver, direction and exact workload command (counts,
  and the input seed for `gemm`, `copy` and `reduce` only); roles in the registered order without overlap, each
  pass after its own stock witness; the witness's complete mVolt+ record, byte-for-byte restore, 2475 MHz reading,
  and a profile store whose sections hash to the curve3 snapshot.
- **Telemetry:** non-finite clock, temperature or power-limit readings, an inconsistent clock minimum/mean/maximum,
  and an empty throttle record make a point invalid rather than passing every threshold.
- **Provenance:** the runner copies itself into the session at launch and records the hashes of what it calls;
  the filer files that copy, never the current checkout.
- **Reporting only:** a zero energy figure no longer crashes the secondary result; every target's pointwise,
  log-SD and shape intervals and ranges, the near-optimal sets and direction peaks are printed (`--json` too);
  a VID curve that re-enters its floor is flagged ambiguous.

`analysis/test_score_repeatability.py` grows from 38 to 87 checks, each finding with its own.

**Further hardening, 2026-10-16, after day 1 (GPT Jobs 99 and 100); no rule changed and day 1's verdict is
unchanged.** The filed runner now also matches its launch hash by an exact CRLF reconstruction, reported as
such: the runner hashes its own Windows CRLF bytes and git stores the copy as LF, so a Linux checkout had
scored day 1 INVALID. The full mVolt+ status record beside each witness (NVVDD offsets included) must read
zero and agree with the manifest's summary, and the final event read must cover the day from before the
first witness to after the last sweep. Day 1 passes all three; 94 checks.

**Desktop screen hardened 2026-10-18, between days 3 and 4 (GPT Job 107); no rule changed.** The screen the
runner uses (`tools/hwinfo-logging/check_desktop_load.py`), the voltage joiner and the bench checker now refuse
a log whose repeated HWiNFO header moves an opening column name, because then every column read by position
may be another sensor; the screen also no longer crashes on a truncated row. A column HWiNFO appends at the
end keeps the named columns in place and is read as before. Checked before committing: the screen's output on days 1–3 is byte-identical
before and after, and none of the 528 raw HWiNFO logs on the bench PC has a conflicting header.

### Result — five days collected 2026-10-15 to 2026-10-19, all SCOREABLE: COMPLETE

Days 1–5 ran on 2026-10-15, 16, 17, 18 and 19, each the first attempt at its index in
`docs/repeatability/ATTEMPTS.md` (attempts 2–6; attempt 1 was the 10-15 dry run), from the same runner
(launch hash `A0753C59…`), none on a §20b date. Every day is valid and passes the return gate (largest
median 0.674%, day 3 `reduce`). Filed in `data/repeatability/day1-20261015/` to `day5-20261019/`. Scored
by `python analysis/score_repeatability.py data/repeatability/day*`, which prints `5 of 5 -> COMPLETE`:

| workload | regret at 1575 MHz, days 1–5 | mean | 98.75% interval | day SD (95%) | outcome |
|---|---|---|---|---|---|
| `gemm` | 1.263 / 2.835 / 1.632 / 1.218 / 1.407% | 1.671% | 0.377 to 2.965 | 0.671 pp (0.402–1.927) | **WITHIN 3%** |
| `copy` | 1.113 / 2.051 / 2.666 / 0.000 / 0.856% | 1.337% | −0.674 to 3.348 | 1.042 pp (0.624–2.995) | INCONCLUSIVE |
| `reduce` | 4.115 / 2.638 / 5.913 / 2.176 / 5.289% | 4.026% | 0.898 to 7.155 | 1.621 pp (0.971–4.659) | INCONCLUSIVE |
| `resnet50` | 0.485 / 1.270 / 0.000 / 1.423 / 1.978% | 1.031% | −0.485 to 2.547 | 0.786 pp (0.471–2.258) | **WITHIN 3%** |

- **`gemm` is WITHIN 3% by 0.035 pp** (upper bound 2.965%); after four days it was INCONCLUSIVE at 3.773%.
  A margin that small should be quoted with its interval, never as a comfortable pass.
- **`reduce` is not ABOVE 3%.** Its mean is the largest, 4.026%, but the lower bound is 0.898%. It remains
  the known exception whose peak sits above the floor (observed peaks 1725–1800 MHz on every day).
- Observed peak targets moved between neighbouring grid points from day to day (`gemm` 1425–1537, `copy`
  1500–1575, `resnet50` 1500–1575 MHz), none at a grid edge. With regret this small that is a flat curve,
  not an unstable optimum.
- Secondary, descriptive: a one-code 0.725 V VID step inside the floor appeared on every day, in one or two of its eight roles, always in
  windows reading about 36–43 °C and never in a warmer one, but not at every cool window; the day READMEs
  record each against the raw logs. Not interpreted, and temperature-dependent V/F behaviour is known GPU
  Boost practice (GPT Job 106).

**Limits.** N=1 chip: five days are five observations of one card, and the intervals assume independent,
roughly normal day values. Five consecutive dates in one week of October, no ambient instrument; room
temperature is an unmeasured candidate source of the variation. The regret is observed grid regret within
this 20-target panel, not a physical optimum.

## Safety envelope — these cards are going to be sold

**The hardware risk of a floor manipulation is low and should be stated plainly rather than
gestured at: undervolting reduces electrical and thermal stress, and the failure mode is a driver
reset, which self-recovers and clears the offsets.** The one crash this project has induced —
875 mV pinned at 3000 MHz, deliberately past the edge — did no damage. What follows is about
leaving a card in a known-good state for a buyer, not about protecting silicon from a curve edit.

1. ⛔ **Power limit stays at stock. Never raised.** Not needed for any prediction above.
2. ⛔ **Memory clocks are not touched.** Memory is the genuinely risky axis — GDDR6X thermals on the
   3070 Ti, and silent error-correction retries that make a "stable" overclock net *slower*. No
   prediction here needs it.
3. ⛔ **Peak voltage never exceeds the stock curve's maximum.** Reshaping means moving clocks at a
   given voltage, not raising voltage.
4. ✅ **Snapshot the profile store verbatim before the first change**, into
   `data/afterburner-profiles/`, per the convention that exists because a slot number is not an
   identity.
5. ✅ **Stability protocol after the manipulation**, and **verify return to stock before shipping** —
   read back the power limit, memory clock under load, and peak core, as was done for Profile 3 on
   2026-09-09. A driver reset silently clears offsets, so a card can look tuned in its settings
   string and be running stock.
6. ⚠️ **Uninstall what was installed.** The collection kit deliberately leaves nothing behind; a
   manipulation needs Afterburner present, which does not. Remove it and its profile store.

## Order of operations, given both cards leave soon

1. **2060 Super fine floor sweep** — 10 minutes, no elevation, no manipulation. Needed for 4c and
   valuable alone as the first measured Turing V/F curve in this literature.
2. **3070 Ti: 4a then 4b.** The replication is the point; the control is what makes it mean
   something.
3. **2060 Super manipulation (4c)** only if time remains after 1 and 2.

🔑 **If only one thing gets done, do the 3070 Ti pair.** It is what converts "one chip" into
"two chips, two architectures", and that is the sentence the paper currently cannot write.
