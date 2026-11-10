# Profile store snapshot, 2026-09-27 ~13:58 — RTX 2060 Super, before any Session E run

**Verbatim copy of the RTX 2060 Super's `MSI Afterburner\Profiles\`**, carried back on the USB kit
by Raymond. No bench run had happened: the kit's `results/` holds nothing from this day. Curve file
SHA-256 begins `e477b20d38c69df4`.

**Not the untouched store the worklist asked for.** Its timestamp (13:58) is after Profile 2 was
saved (13:57), so it is the store *after* slots 1 and 2 were saved. Both slots decode as stock (below),
so nothing was lost, but the file itself is not a pre-save copy.

## Verified by decoding

| check | result |
|---|---|
| slots present | `Profile1`, `Profile2`, `Startup` (empty) |
| P1 and P2 `VFCurve` | **byte-identical** |
| `CoreClkBoost`, `MemClkBoost`, `PowerLimit` | **0, 0, 100** in both slots — stock |
| per-point offsets | **0 at all 128 records**, both slots |

**So Profile 2 does NOT hold the −165 MHz offset.** Both slots are stock. Nothing had been
registered for the offset yet; the offset is set on the next visit, after the amendment in
`docs/REGISTERED-PREDICTIONS.md` (§4c, "Amendment 2, 2026-09-27").

## The format differs from the 5060 Ti's

The blob is the same 3224 bytes, but the header reads `00000200 80000000`: **128 records**, not the
5060 Ti's 127 (`…7f000000`). `tools/afterburner/decode_profiles.py` pins 127 and will refuse this
file; decode it with a count read from the header.

## The stored stock curve, and why the planned edit could not be built

The curve stores points from **450 mV**, 6.25 mV apart. Below ~1300 MHz each code is **30 MHz**:

| mV | 612.5 | 618.8 | 625.0 | **631.2** | 637.5 | **643.8** | 650.0 | 656.2 | 662.5 | 668.8 | 700.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base MHz | 915 | 945 | 975 | **1005** | 1035 | **1065** | 1095 | 1125 | 1140 | 1170 | 1305 |

These agree with what the sweeps measured on this card: 0.637 V at 1035 MHz, **0.644 at 1065**,
0.669 at 1170, 0.694 at 1275 (the next point up, 1290 at 693.8 mV). Below 1005 MHz the stored curve
keeps falling (to 420 MHz at 450–506 mV) but the card **reads 0.631 V from 630 to 1005 MHz**, so
the 0.631 V load floor is where this curve crosses a minimum that the curve itself does not set.

**The "6 mV creep" that makes this card undecidable is the stock curve's own staircase**, one
6.25 mV code per 30 MHz, a much shallower slope than the 5060 Ti's. That is a decode of the stored
file plus a comparison with existing sweeps, not a new measurement.

**Part 2's edit was not buildable.** Raymond reported that Afterburner's curve editor on this card
would not move any point below **700 mV**. The registered edit caps every point below 0.669 V, so none
of its points could be reached. The points are in the file; the editor does not expose them for
editing. **Why** the editor refuses them was not investigated. Writing the capped points into the
file by hand was not attempted: that would build a curve the tool itself declines to build, with
unknown driver behaviour.
