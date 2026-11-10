# Profile store snapshot, 2026-09-26 15:16 — curve 3 (P4, memory +0) in P1

**Verbatim copy of `C:\Program Files (x86)\MSI Afterburner\Profiles\`**, taken after Raymond built
curve 3 into Profile 1, over rung C (worklist 4j, `REGISTERED-PREDICTIONS.md` §12). It was taken
before any curve 3 sweep. Curve file SHA-256 begins `8ec197f30e21d116`.

**How it was built:** apply P4, set the memory slider to +0, touch nothing else, save to Profile 1.

## Verified by decoding

| check | result |
|---|---|
| P1's 127 stored (voltage, base, offset) triples against P4's | **identical, 0 differences** |
| memory offset | **+0** on P1, against +2500 on P4 |
| power limit, `CoreClkBoost` | identical to P4 (111, i.e. 200 W; −502296 kHz) |
| P2–P5 | decode identical to `../5060ti-profiles-20260926-rungC/` |
| `MSIAfterburner.cfg` | byte-identical to the rung C snapshot's |

Rung C, which P1 held before, is preserved in `../5060ti-profiles-20260926-rungC/`.

**Memory under load cannot tell curve 3 from stock**: both read 13801. The live witness for
curve 3 is the **200 W** power limit (stock is 180 W), together with this store hash. Every other slot
carries +2500 memory, so 13801 plus 200 W identifies curve 3.
