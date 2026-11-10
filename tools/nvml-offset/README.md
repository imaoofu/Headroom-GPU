# `nvml-offset` — the NVML P0 graphics clock offset, negative only

**Added 2026-09-22, for worklist items 4c and 4d.** `Set-NvmlClockOffset.ps1 -Status | -SetMhz <n> | -Reset`.

**It CHANGES GPU STATE** when not `-Status`, so it follows the sweep tool's rules:
- **Negative offsets only, down to −500 MHz.** Positive values are refused. A negative offset lowers
  the clock at every voltage, so a given clock takes more voltage and instability is not reachable.
- **Every write is verified by reading it back** (exit 4 if the driver disagrees).
- **Writes need an elevated shell.** Without it NVML returns `NO_PERMISSION` (exit 5), not `NOT_SUPPORTED`.

**What a read-back proves:** that the driver accepted the value. It does **not** show what the
value does to clocks or voltage; the 4c sweep measures that. As of 2026-09-22 the effect of a
driver reset, and of an Afterburner profile applied *after* the offset, are unverified. **Apply any
profile before the offset, and `-Reset` plus read back at the end of every session.**

Verified 2026-09-22 before any write: `-Status` reads 0 MHz, allowed range −1000 to +1000, and
`-SetMhz 100` is refused with exit 2.
