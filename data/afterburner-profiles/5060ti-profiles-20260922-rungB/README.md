# Profile store snapshot, 2026-09-22 21:21 — floor-ladder rung B in P1

**Verbatim copy of `C:\Program Files (x86)\MSI Afterburner\Profiles\`**, taken after Raymond built rung
B (`REGISTERED-PREDICTIONS.md` §1, worklist 4e) into Profile 1. It was taken before any rung B sweep,
as the registration's pre-run check 5 requires. Curve file SHA-256 begins `110aa774d5fc4123`.

**P2–P5 are byte-identical to `../5060ti-profiles-20260918/`.** Only P1 changed: it held the Profile 1
configuration, whose suite was collected on 2026-09-22 and is preserved in the 09-18 snapshot.

## Rung B, as decoded and as Afterburner shows it

| check (registration §1) | result |
|---|---|
| 1. 720 mV inside 1624–1777 | **1702**, the predicted grid point |
| 2. 850 mV and above identical to P5 | all points, plus memory +2500 and PL 111 (200 W), as on P5 |
| 3. below 850 mV between stock and P4 | **fails at 650–690 mV; the registration's claim was impossible there** (see the note in §1) |
| 4. rises across 850 → 860 mV | yes |
| 5. snapshot before collection | this directory |

The floor region, 695–840 mV, is lifted **+165 to +172 MHz**, not exactly +170. Afterburner stores
clocks on a grid (…1687, 1702, 1717…) that has no value at 1530 + 170 = 1700.

## What tonight showed about DECODING this file — read before trusting a decoded point

**1. At 845 mV the decoder and the editor disagree, and the editor is right.** The file stores
(offset **+176**, base **2362**), which `applied = base + offset` reads as **2538**. The curve editor
shows **2362, +0**. **Raymond re-saved P1 at 21:21:29, and the file came out byte-identical**, so the
editor's view and the stored bytes are the SAME state. **+176 is exactly the offset of the previous
point (840 mV)**: the offset field lags by one record where the offset changes. It is the same class
of pairing artifact CLAUDE.md documents at 935 mV on the tuned profiles, **at a new location**. That
file had said "exactly one record per tuned profile… always at 935 mV", which is not the whole story.

**2. Below 700 mV the editor cannot reach the points at all.** Its axis starts at 700 mV, and Raymond
reports he could not manipulate anything below it. Yet the decode shows 650–690 mV lifted +175 to
+180. **Raymond did not make that edit.** Afterburner moved those points itself, or they decode wrongly
for the same reason as 845, and nothing here can tell which. The card never runs below 0.720 V under
load, so they apply only at light load.

**3. Even P5's decoded 845 point does not predict the card's behaviour.** P5 decodes 2362 at 845 mV,
yet the committed `voltage-curve-20260908` P5 sweep ran **2462 and 2602 MHz at 0.845 V**. So how the
driver treats the 845 → 850 → 860 region is not readable from the stored points.

**So the question "does rung B match P5 above the floor?" is settled by MEASUREMENT, not decode:**
compare the rung B suite's voltage extracts against P5's at the same targets. And do not use
`applied = base + offset` at any point where the offset field changes value.
