# RTX 3070 Ti profile store, as found 2026-09-24: rewritten by Afterburner, curves unchanged

**Verbatim copy** of `C:\Program Files (x86)\MSI Afterburner\Profiles\` from the shop machine, made
by Raymond after Session D's first launch that morning (`bench-session-20260924-081957`) stopped at
its first check: *Profile hash mismatch*. Nothing had been measured.

| file | SHA-256 (as written by Afterburner, CRLF) |
|---|---|
| `VEN_10DE&DEV_2482&…cfg` | `cce75e81fe322380…`, where 2026-09-23's snapshot is `1b08c2d0854460ff…` |

## What changed: two sections Afterburner added itself; the curves did not change

Compared key for key against `../3070ti-profiles-20260923/`:
- **`Startup`, `Profile1`, `Profile2` and `Profile3` are identical in every key, including every
  `VFCurve`.** So Session D's stock, Edit 1 and Edit 2 are exactly the decoded curves.
- **Two sections were added.**
  - `[Defaults]`: power limit 100, core +0, memory +0, fan 30, and a curve.
  - `[Settings]`: `CaptureDefaults=0`.
- **No other key was changed or removed.**

The `[Defaults]` curve is **not** Profile 1. It differs at three points, each by one 15 MHz step at
zero offset: 950 mV reads 1800 against 1785, 987.5 mV 1860 against 1845, and 1100 mV 1980 against
1965. It reads like the driver's default curve captured at a different moment, but that is an
inference, not established. **Session D never applies it**: the runs apply P1, P2 and P3 by
command line.

**Why the gate tripped:** the bench app hashes the whole file, so an added section fails it just as a
changed curve would. The gate did its job; the whole-file hash is simply stricter than "the curves
are the ones decoded". ~~The Session D catalog now expects `CCE75E81FE322380`~~ **Superseded the
same day (commit 90bb9a8):** the gate now hashes only the `[Profile1]`–`[Profile3]` sections, and
the catalog expects **`A1159941DA541EB9`**, identical for this snapshot and the 09-23 one
(`tools/bench-app/Profile-Hash.ps1`, `build_sessiond.py`). The whole-file `CCE75E81FE322380` would
have tripped again on the next section Afterburner added; this line was not updated when that
changed, found 2026-09-24. **The load witnesses are unchanged,** and they still check each
profile's effect directly.

**Not known:** what made Afterburner write these sections, or when between the shakedown's end
(2026-09-23 22:15) and 08:19 the next morning. If it happens again before Session D runs, the gate
stops the run the same way. That is safe, and this comparison can be repeated in a minute.
