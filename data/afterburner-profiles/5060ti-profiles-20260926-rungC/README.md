# Profile store snapshot, 2026-09-26 13:26 — floor-ladder rung C in P1

**Verbatim copy of `C:\Program Files (x86)\MSI Afterburner\Profiles\`**, taken after Raymond built rung
C (`REGISTERED-PREDICTIONS.md` §1, worklist 4f) into Profile 1, over rung B.
It was taken before any rung C sweep, as the registration's pre-run check 5 requires; the profile
had been saved, not yet applied for a run. Curve file SHA-256 begins `4fdfbf241c1dae7a`.

**P2–P5 decode identical to `../5060ti-profiles-20260922-rungB/`**, and so do P1's power limit (111,
200 W), `CoreClkBoost` and memory offset (+2500). Rung B's store is preserved in that snapshot.

## Rung C, as decoded and as Afterburner shows it

| check (registration §1) | result |
|---|---|
| 1. 720 mV inside 1778–1931 | **1845**, nearest grid point 1852, the predicted one |
| 2. 850 mV and above identical to P5 | 0 differences in stored triples from 860 mV up |
| 3. below 850 mV between stock and P4 | **fails at 670–690 mV, as it did for rung B**: P4 is stock there, so any raised rung exceeds it. A defect in the registration, recorded in §1 |
| 4. rises across 850 → 860 mV | (raw 2180 → 2775) |
| 5. snapshot before collection | this directory. The decoder's check 5 reads this README; chronology is as reported, not provable from the bytes |

**The floor region, 670–840 mV, is lifted exactly +315 MHz at every decodable point** against stock
(P3). The target was +320; Afterburner's grid offered 2302 or 2317 at 840 mV, and 2302 is nearer.
This is cleaner than rung B, which landed +165 to +172.

## The boundary points, same pattern as rung B

- **845 mV stores (base 2362, offset +319)**: the offset of the 840 mV point, carried one record,
  which is exactly the lag rung B showed (+176 there). On rung B the editor showed **2362, +0** and a
  re-save was byte-identical. Expect the same here. Never read this point as 2681.
- **Below 700 mV**, which the editor cannot reach: 670–695 mV moved with the edit (+315), 650 and
  660 mV still store rung B's +186, and 665 mV stores +319 on rung B's base, another boundary. The
  card never runs below 0.720 V under load, so these apply at light load only.
- 850 and 860 mV are unchanged from rung B (and P5).

As with rung B, **how the driver treats 845–860 mV is not readable from the stored points.**
Whether rung C matches P5 above the floor is settled by the suite's voltage extracts, not by decode.
