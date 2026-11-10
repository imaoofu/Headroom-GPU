# Profile store snapshot, 2026-09-27 14:13 — RTX 2060 Super, slot 2 = −165 MHz offset

**Verbatim copy of the RTX 2060 Super's `MSI Afterburner\Profiles\`**, taken after Raymond saved
Profile 2 for Session E's `offset-2` run (`REGISTERED-PREDICTIONS.md` §4d, Amendment 2). It was taken
before any Session E sweep. Curve file SHA-256 begins `1db73d729ef72ed6`.

## Verified by decoding, slot by slot, against `../rtx2060s-profiles-20260927/`

| slot | what changed |
|---|---|
| `Profile1` | **nothing**: every key identical, still stock (CoreClkBoost 0, all offsets 0) |
| `Profile2` | **`CoreClkBoost` 0 → −165000** (kHz) and `VFCurve`; PowerLimit 100 and MemClkBoost 0 unchanged |
| `Startup` | nothing, still empty |
| `Profile1.cfg`, `MSIAfterburner.cfg` | byte-identical |

**Profile 2's curve:** 128 records with the same 128 voltages as stock. The per-point offset is
**−165 at 127 of them**, including every point below 700 mV that the editor would not let Raymond
move, and 0 at the first record (450 mV). So the core slider did write an offset into the region
the curve editor locks. **Whether the driver applies it there is what the `offset-2` witness at
locked 1065 MHz checks**; the file cannot show it.

**The stored BASE clocks differ from Profile 1's at 38 of 128 points, always by exactly one
15 MHz bin**, in both directions (for example 1140 → 1155 at 662.5 mV and 2010 → 1995 at the top).
Nothing was edited there: the base is the driver's curve as read at save time, and Profile 1 was
saved at 13:52, Profile 2 at 14:13. A one-bin shift is consistent with GPU Boost's temperature
bins, but **that is an inference, not checked.** The two points the witnesses depend on are
unchanged: 1230 MHz at 681.25 mV, which locked 1065 should read under −165, and 1440 MHz at
743.75 mV, which locked 1275 should read.

Decode with a record count read from the header (`00000200 80000000`, 128 records).
`tools/afterburner/decode_profiles.py` pins the 5060 Ti's 127 and will refuse this file.
