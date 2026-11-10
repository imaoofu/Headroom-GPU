# `afterburner-profiles` — verbatim snapshots of the tuning profiles the sweeps were taken under

<!-- dataset-grade: no -->

Not sweeps and not measurements. These are **snapshots of machine configuration**, kept so that a
configuration referenced by a sweep can still be reconstructed after the operator changes it.

## Why this exists

`docs/AFTERBURNER-PROFILES.md` tabulates the five profiles at five sampled voltages. That is enough
to tell them apart and **not** enough to rebuild one. Each curve has **127 points**, and the
operator edits these profiles by hand between sessions.

The specific risk this guards against was raised on 2026-09-08: the plan to **raise Profile 4's
plateau from 3015 to 3030 MHz** so it matches Profile 5's, which is a good experimental control —
it removes the top-clock difference and leaves the low-band voltage shape as the only variable
between them. But it also means **"Profile 4" would refer to two different configurations either
side of that edit**, and the `a1`/`a2` legs of the 2026-09-08 ABBA run measured the earlier one.

A slot number is not an identity. This file is what makes the identity recoverable.

## Contents

Two snapshots so far. **The Profile 4 edit they bracket is exactly the event this directory exists
for**, and it happened the same day the directory was created.

| file | sha256 (head) | Profile 4 plateau |
|---|---|---|
| `5060ti-profiles-20260908.json` | `7f98d342` | **3015 MHz** |
| `5060ti-profiles-20260908b-p4-plateau-3030.json` | `e5cbe0ec` | **3030 MHz** |

**`abba-20260908`'s `a1` and `a2` legs measured the 3015 version.** Any later run on "Profile 4"
measures the 3030 one. Same slot, two configurations, and only the date tells them apart.

**What changed in Profile 4:** 49 of 127 curve points, all at **940 mV and above**, raising the
plateau from 3015 to 3030 to match Profile 5. The low-voltage region is byte-identical — 1912 MHz at
700 mV, 2317 at 800, 2752 at 875, 2932 at 925 — and power limit (111) and memory offset (+2500) are
unchanged.

**AND PROFILE 3 CHANGED IN THE SAME EDIT, WHICH THIS FILE MISSED UNTIL 2026-09-09.** The paragraph
above was the entire description of the diff and it covered one slot of two. **Profile 3 was wiped to
stock** in the same sitting: its curve replaced with 122 all-zero-offset points, its memory offset
taken from **+2500 to +0**, leaving PL 100 — the card's 180 W factory default.

**The snapshot itself is complete and always was.** `…20260908b…` holds the stock Profile 3 verbatim,
which is exactly what snapshotting the whole store is for. What failed was the *description*: the
diff was run against the slot the edit was expected in, and the answer was written up as though that
were the whole answer. **Diff every slot. An edit you were told about is not evidence that it was the
only edit.** The cost was real — `docs/AFTERBURNER-PROFILES.md` carried "None of these is stock" and
"there is no stock profile to apply" for a day after a stock profile existed, and a run design was
built on that constraint.

**Consequence: stock is applicable programmatically for the first time.** Every ABBA and
cross-configuration comparison in this repository has been tuned-versus-tuned because stock could not
be reached from the command line. It can now. **Verified in application too, 2026-09-09 at 11:38**, before the stock-bracket run: power limit fell 200 → 180 W, peak memory clock under load read 13801 rather than 16301, and peak core clock 2640 against Profile 4's ~2976. This line said "verified on disk only" until 2026-09-11; the check had already been done and recorded in `data/frequency-sweeps/stock-bracket-20260909/README.md` the same day. See the application
check flagged in `docs/AFTERBURNER-PROFILES.md`.

**Re-decoded 2026-09-09 10:47:** the live store is sha256 `e5cbe0ec`, **byte-identical to the
`…20260908b…` snapshot**, so that snapshot is current and no new one is due. The file's mtime
(09-09 08:23:35) is Afterburner rewriting it unchanged at launch, not an edit — **compare the hash,
never the timestamp.**

**Why the operator made it:** to match Profile 5's plateau, so that the two profiles differ only in
the low/mid-band voltage shape. That isolates the variable behind the +465 MHz optimum shift instead
of leaving the top clock confounded with it. Note one residual difference — P4 reaches its plateau at
940 mV where P5 reaches it at 925.

Each snapshot holds, for all five slots plus `[Startup]`:

- `power_limit_pct`, `core_clk_boost_khz`, `mem_clk_boost_khz` as stored
- `vf_curve_hex` — the raw blob, so a profile can be restored exactly
- `curve_points` — all 127 decoded points per profile as
  `{voltage_mv, base_mhz, offset_mhz, applied_mhz}`
- `source_sha256` of the whole cfg, so a later snapshot can be compared without diffing curves

`[Startup]` holds empty values — no settings, i.e. stock. **It is not reachable from the command
line**, which is why applying stock programmatically is currently impossible and why a slot has to
be sacrificed to get one.

## How to use it

- **To identify what a sweep ran under:** match the sweep's date against a snapshot, then the
  snapshot's curve against the `applied_settings` string.
- **To restore a profile after an edit:** the `vf_curve_hex`, power limit and memory boost are
  everything the cfg stores for that slot.
- **To check whether anything changed:** compare `source_sha256` between snapshots. Cheaper and
  stricter than comparing curves.

**Take a new snapshot whenever a profile is edited**, named by date. Do not overwrite an existing
one — the whole point is the history.

## Known decoder caveat

A naive stride-3 read of the curve blob mispairs at one record — the boundary between the
zero-offset and non-zero-offset regions — and produces an impossible ~6000 MHz point near 937 mV.
The `curve_points` here are written as decoded, including that artifact, because filtering during
capture would make the snapshot lossy. **Filter on read** to the card's supported range
(≤3090 MHz, the top of its supported-clock table).
