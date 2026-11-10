<!-- dataset-grade: no -->

# Verbatim Afterburner profile store, RTX 5060 Ti, 2026-09-18

**Raw `.cfg` files copied byte-for-byte before applying Profile 3 for the fine-floor sweep.**
Not a decoded snapshot — the two JSON files beside this directory are those. This is the fallback
the run sheets prescribe when no decoder is run: **copy the raw files and record each SHA-256.**

| file | SHA-256 (first 16) | bytes |
|---|---|---|
| `MSIAfterburner.cfg` | `95E4BD5D28365639` | 2931 |
| `Profile1.cfg` … `Profile5.cfg` | `CADE1B0DA7D80656` (all five identical) | 31 each |
| `VEN_10DE&DEV_2D04&…cfg` | `E5CBE0ECD89D899C` | 32897 |
| `VEN_1002&DEV_13C0&…cfg` | `62CDA03FAC784488` | 131 |
| `VEN_0000&DEV_0000&…cfg` | `B0D8CB40FA778F0E` | 94 |

**The five `ProfileN.cfg` files are 31-byte stubs and all hash identically** — they hold no curve
data. Everything is in the per-device `VEN_10DE&DEV_2D04&…cfg`, which carries `[Startup]` plus
`[Profile1]`–`[Profile5]` sections.

## What Profile 3 contained, checked rather than assumed

`CLAUDE.md`'s rule is that **a slot number is not an identity** — P3 held an aggressive curve one
day and stock the next. So it was read before being applied:

| slot | PowerLimit | CoreClkBoost | MemClkBoost |
|---|---|---|---|
| Profile1 | 100 | −502296 | 2000000 |
| Profile2 | 111 | −502296 | 2500000 |
| **Profile3** | **100** | **0** | **0** stock |
| Profile4 | 111 | −502296 | 2500000 |
| Profile5 | 111 | −502296 | 2500000 |

**Matches the 2026-09-09 record exactly** — every offset zero, `PowerLimit 100` = the 180 W
factory default. The `−502296` on the other four is the `CoreClkBoost = −502 MHz` this project has
recorded and not explained.

## Verified in application, three ways

1. Power limit **200 → 180 W** after applying P3.
2. Memory clock under load **13801 MHz**, not the 16301 of a memory-overclocked profile.
3. Peak core under free boost **~2557 MHz**, against Profile 4's ~2976.

**Driver was 616.92** at snapshot time — the reboot that preceded this session picked up an
update from 616.64. Read it off the sweep JSON, never off a document.

## Re-verified against the live store 2026-09-22, before P1 is overwritten

Every file was compared by SHA-256 with `C:\Program Files (x86)\MSI Afterburner\Profiles\` on the
evening of 2026-09-22, immediately before Profile 1 was to be overwritten with ladder rung B (4e).
**All five `ProfileN.cfg` stubs and all three `VEN_*.cfg` device files are byte-identical**, including the
curve file (`e5cbe0ecd89d899c…`). The only difference is `MSIAfterburner.cfg`, Afterburner's
own window settings: `WindowY` 48 → 49. **So this directory is the pre-edit snapshot for the
2026-09-22 rung build; no second copy was taken, because it would be identical.**

## How to restore these curves exactly

Afterburner holds its profiles in memory and can write them back to disk when it exits. **Copying
files in while it is running can therefore be silently undone.**

1. **Exit Afterburner completely**: right-click its tray icon, then Exit. Closing the window only
   minimises it.
2. From an **elevated** PowerShell in the repository root:

   ```powershell
   Copy-Item "data\afterburner-profiles\5060ti-profiles-20260918\VEN_10DE*.cfg" "C:\Program Files (x86)\MSI Afterburner\Profiles\" -Force
   Copy-Item "data\afterburner-profiles\5060ti-profiles-20260918\Profile?.cfg" "C:\Program Files (x86)\MSI Afterburner\Profiles\" -Force
   ```

   Leave `MSIAfterburner.cfg` alone. It holds no curves.
3. Start Afterburner, then check that the live file hashes back to `e5cbe0ecd89d899c…`:
   `(Get-FileHash "C:\Program Files (x86)\MSI Afterburner\Profiles\VEN_10DE*.cfg").Hash`
4. **Apply the profile you want and verify it by memory clock under load**: stock reads 13801,
   the +2500 profiles 16301. A slot number is not an identity.

**Restoring the VEN file restores ALL FIVE slots at once**, because every profile's curve lives
in that one file. It also undoes any rung saved into P1 since, so snapshot that first if it
matters. **This procedure has not been exercised.** It is the documented file layout, not a
tested restore.
