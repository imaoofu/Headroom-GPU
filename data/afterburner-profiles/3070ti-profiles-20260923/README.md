# RTX 3070 Ti profile store — Session D curves, 2026-09-23

**Verbatim copy** of `C:\Program Files (x86)\MSI Afterburner\Profiles\` from the shop machine
(GA104, `DEV_2482`, Gigabyte `SUBSYS_408F1458`), made by Raymond at 15:05 and carried here on the
USB kit. Built **before** any Session D sweep, for `docs/REGISTERED-PREDICTIONS.md` §4a–4b.

| file | SHA-256 (as written by Afterburner, **CRLF line endings**) |
|---|---|
| `VEN_10DE&DEV_2482&…cfg` (the curves) | `1b08c2d0854460ff548861fe1534d90073cd6ffd5f85c2310e147044cdb187f9` |

Git stores this file with LF endings, so a checkout's hash can differ. Compare against the CRLF
form, which is what `Get-FileHash` reads on the live store. At the machine the store must still
begin `1B08C2D0854460FF` before any sweep; if it does not, a slot changed and this snapshot no
longer describes it.

| slot | contents | PowerLimit | MemClkBoost | CoreClkBoost |
|---|---|---|---|---|
| P1 | **stock**, every offset 0 | 100 | 0 | 0 |
| P2 | **Edit 1**, the manipulation | 100 | 0 | −502296 |
| P3 | **Edit 2**, the negative control | 100 | 0 | −502296 |

Power limit default and memory +0 in every slot: the safety envelope holds. `CoreClkBoost −502296`
is the same unexplained field the 5060 Ti's tuned profiles carry (CLAUDE.md).

## Decoded curves

**Read with each point's base paired with the NEXT record's stored offset.** Read the naive way
(base + its own offset), P2 is nonsense: 1866 MHz at 825 mV, 635 at 831. Paired with the next offset
it is a clean flat cap and a ramp of exactly +60 MHz per point, **and it matches the curve editor's
own tooltip for 831 mV: 1215 MHz, offset −410** (Raymond's screenshot). That is the same one-record
lag the 5060 Ti's rung B showed at 845 mV, seen here across a whole edited region on a second card.
**Two files, one tooltip.** Treat it as well supported, not as a format rule. By default, the committed
decoder (`tools/afterburner/decode_profiles.py`) still pairs the naive way and **refuses this
file**: it requires five slots and a zero-filled tail, and this store has three slots and
extra nonzero data from float 406 of the tail onward (values 1785 and 83 repeating).
**Since 2026-09-24 it reads the file on request:** `--lenient --pairing next` reproduces the table
below at every listed voltage, pinned by `analysis/test_decode_profiles.py`. The tail values are
still not decoded. This was drafted by the local model and reviewed
(`docs/local-model-findings/2026-09-24-queue-L1-L3.md`).

| mV | P1 stock | **P2 Edit 1** | **P3 Edit 2** |
|---|---|---|---|
| 700.00 / 706.25 / 712.50 | 1125 / 1155 / 1170 | same | same |
| 718.75 | 1185 | **1200** +15 over stock | 1185 |
| 725.00 → 812.50 | 1215 → 1485 | **1200 flat** | stock |
| 818.75 | 1500 | **1200** | 1500 |
| 825.00 | 1515 | **1200** | **1500** (−15) |
| 831.25 | 1530 | 1215 | 1500 |
| 837.50 → 868.75 | 1545 → 1620 | 1275 / 1335 / 1395 / 1455 / 1515 / 1575 | 1500 |
| 875.00 | 1635 | 1635 (stock again) | 1500 |
| 900 / 1000 / 1100 / 1200 | 1695 / 1875 / 1965 / 1995 | stock | 1500 |

- **P2 caps the whole floor band (0.812–0.825 V) at 1200**, as the runsheet specifies. The driver
  would not accept one step from 1200 to stock at 831 mV, so it ramps back at +60 MHz per point
  through 868.75 mV. Every point is at or below stock **except 718.75 mV, which is 15 MHz above**. That
  is a light-load point, below the 0.812 V floor, which the card does not use under load.
- **P3 leaves the curve at stock through 818.75 mV**, then holds **1500 from 825 mV upward**. 825 mV
  sits 15 MHz under stock, inside the floor band.

## How the edit was found to need a ramp

Raymond, at the machine: 825 mV could not be set to 1200 with 831 mV at stock, and the editor
**forced a ramp**: first below 825, then, after rebuilding, above it. The rule the driver enforces is
inferred from these files, not documented: **no point can sit more than ~60 MHz below its right-hand
neighbour.** The 5060 Ti accepted a 205 MHz step on rung B, so this may be specific to Ampere or to
this board.
