# NVML offset ladder — worklist item 4o, 2026-09-23

**Four twelve-workload suites, 48 sweeps, stock Profile 3, NVML P0 graphics offset 0 / −150 / −300 / 0
MHz, 13 points 1237–3090 MHz, driver 616.92.** Collected unattended, operator absent, by
`tools/hwinfo-logging/experiments/Run-OffsetLadder.ps1`, registered before collection in
`docs/REGISTERED-PREDICTIONS.md` §7. HWiNFO at 0.50 s; every sweep has its own time-joined voltage
extract. 13:08–16:58.

**Offset writes, from `runner-console.log`, each verified by read-back:** 0 (13:08), −150 (14:05),
−300 (15:02), 0 (16:00), and the final reset to 0 (16:57). A read-back shows the driver accepted the
value; the sweeps measure what it did.

---

## REGISTERED VERDICT: INVALID — its own validity rule could never be met

Two defects in the registered scorer and one in the registration, all found after collection and
**before any median was computed**:

1. **The registration requires "no missed lock" in every sweep.** On stock, 2932 and 3090 MHz are
   unreachable: the committed stock suites this design was built from (`../5060ti-stock-repro-20260922/`)
   miss them in **24 of 24 sweeps**. So the rule was unsatisfiable for any stock suite on this grid.
   Every sweep here misses at the top, always **below** target.
2. **The scorer checked stock memory with the AVERAGE column**, which takes in idle memory (810 MHz)
   between iterations. `../5060ti-p1-suite-20260922/README.md` documented that trap the day before.
   The **maximum** is the witness: it reads **13801–14001 MHz at all 624 points**, stock's two loaded
   states, so no memory offset was ever live.
3. **The scorer required achieved clocks within 15 MHz**, while the sweep tool calls a lock held
   within **30 MHz** (`Invoke-FrequencySweep.ps1`, `lock_held`). Stock reaches the 2782 target only
   as 2752.5.

Fixing 2 changes nothing about validity: it corrects a wrong witness. Fixing 1 and 3 relaxes the
registered rule, so **the registered verdict stays INVALID** and the result below is reported beside
it, never instead of it.

## Revised scoring — POST HOC, defined before any median was seen

```
python analysis/score_offset_ladder.py data/frequency-sweeps/5060ti-offset-ladder-20260923 --revised
```

The revised rule keeps rows that missed their lock **below** target, uses the sweep tool's own 30 MHz
lock definition, and **invalidates a sweep if its efficiency optimum is a missed-lock row**. That is
the standard the rung B and P1 suites were scored by. No sweep was invalidated.

| suite | registered prediction | median | workloads on it |
|---|---|---|---|
| opening 0 MHz | 1545 | **1545** (yes) | 10 of 12 |
| **−150 MHz** | **1395** | **1395** (yes) | 9 of 12 |
| −300 MHz | 1237 | **1237** (yes) | 10 of 12 |
| closing 0 MHz (drift bracket) | = opening | **1545** (yes) | 11 of 12 |

Drift bracket agrees; the trend is non-increasing and strictly drops at each step.

**What each pass shows.** **−150 is the one interior test**: 1395 lies between two other grid
points, so its pass locates the move. **−300 is edge-limited**: 1237 is the lowest target, so its pass
fits any optimum at or below ~1316 MHz, and shows a move of at least two steps, not a move to ~1270.
**One chip, one session, one suite per offset, a ~155 MHz grid.** Twelve workloads are repeated
outcomes on one card, not twelve chips. The curve-shift mechanism is prior art (170tune,
`docs/RELATED-WORK.md` §10); this tests a predictive rule on this card.

## Voltage: each −150 moves the whole column one grid step

`gemm`, reported VID by target (achieved clock / voltage):

| target | 0 | −150 | −300 | closing 0 |
|---|---|---|---|---|
| 1237 | 0.720 | 0.720 | 0.720 | 0.720 |
| 1395 | 0.720 | 0.720 | **0.755** | 0.720 |
| 1545 | 0.720 | **0.755** | 0.795 | 0.720 |
| 1702 | **0.755** | 0.795 | 0.840 | **0.755** |
| 1852 | 0.795 | 0.840 | 0.840 | 0.795 |
| 2010 | 0.840 | 0.840 | 0.885 | 0.840 |

The last 0.720 V point moves **1537 → 1387 → 1230 MHz achieved**, and the opening and closing stock
columns are identical. The reported value is a VID lookup, not rail voltage.

## Missed locks — all below target

Per suite, sweeps missing each target (of 12): opening 0: 2625 ×3, 2782 ×9, 2932 ×12, 3090 ×12.
−150: 2010 ×2, 2475 ×3, 2625 ×5, 2782–3090 ×12. −300: 2317 ×2, 2475 ×6, 2625–3090 ×12. Closing 0:
2475 ×1, 2625 ×4, 2782 ×9, 2932–3090 ×12. The negative offsets lower the whole curve, so the top of
the grid becomes unreachable sooner. None of these rows is any workload's optimum. No benchmark
failed, and every power window was applied.

## What is dataset-grade

All 48 sweeps are complete stock-Profile-3 measurements with the stated offset live, each with its
own voltage extract. `runner-console.log` is provenance, and the only record of the read-backs.
