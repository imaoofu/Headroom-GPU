# 5060 Ti fine floor at 0.50 s sampling — worklist item 4i, 2026-09-22

**Three ascending replicates, 1380–1760 MHz, 13 points (~31 MHz), stock Profile 3, driver 616.92.**
The first sweeps in this project **driven end to end with no human present** —
`tools/hwinfo-logging/Invoke-LoggedSweep.ps1` did preflight, HWiNFO log start, sweep and log stop.

Raw HWiNFO logs are in the gitignored `data/HWiNFO-Data/5060ti-finefloor-20260922/`; the distilled
`_voltage.csv` extracts beside each sweep are the dataset-grade files.

---

## Why it was run: the 2026-09-18 pair sampled too slowly to answer its own question

`5060ti-finefloor-20260918/` logged at the main machine's **2.00 s**, giving **5–9 samples per
frequency point** — enough for a constant median, not enough to see whether the voltage *dithers*
between adjacent codes. The RTX 2060 Super dithers **23–26%**. Whether this card does was unknown.

At `SensorInterval=500` these runs carry **22–28 samples per point**.

## The floor reproduces exactly

`..._asc-r3_sweep_voltage.csv`, the clean replicate:

| MHz | 1377 | 1402 | 1432 | 1462 | 1500 | 1530 | **1560** | **1590** | 1620 | 1657 | 1687 | 1717 | 1747 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | **0.720** | **0.730** | 0.740 | 0.745 | 0.755 | 0.760 | 0.770 |

**0.720 V holds through 1560 and first rises at 1590**, matching 2026-09-18 at four times the
sampling rate. Throughput agrees with the committed quiet reference at all thirteen points within
±1.9%, mean ≈ 0.

## 4i's answer: the 5 mV grid DOES dither — but only ABOVE the floor

Distinct voltage values inside each point's benchmark window, r3:

| region | behaviour |
|---|---|
| floor, 1378–1560 | **one code**, with at most a single stray sample (4% of ~25) |
| 1590, 1657 | one code plus one stray |
| **1620** | **0.735 × 9, 0.740 × 15 — 38% minority** |
| **1717** | **17% minority** |
| **1747** | **0.765 × 7, 0.770 × 14, 0.775 × 1 — 36%, across THREE codes** |

**A 4% minority is one sample of ~25 and is not dither** — most likely a window-edge sample
catching the ramp. The claim rests on 1620, 1717 and 1747, where the minority is 17–38%.

**So the floor is genuinely single-code and the rising region is not.** That is a structural
difference the 2.00 s logs could not have shown, and it is consistent with the floor being a
clamp rather than a regulation target.

---

## THE METHODOLOGICAL RESULT, WHICH MATTERS MORE THAN THE DITHER

**Three replicates of one configuration, 15 minutes apart, differ by up to 11% at isolated points —
and the number of bad points tracks how busy the driving agent was.**

**NARROWED 2026-09-22 by an outside audit (`docs/gpt-findings/2026-09-22-5060ti-session-results-audit.md`), recomputed here.** Two
corrections:

1. **`asc-r2` has TWO degraded points, not one:** −8.78% at 1597 and **−3.27% at 1627** against
   `asc-r3`. It was counted as one because only one fell in the 8–11% class. **The sequence is
   4 → 2 → 0.**
2. **"Tracks how busy the driving agent was" is an ASSOCIATION, not a cause.** Agent activity,
   run order and **time since the card was switched on** all changed together (r1, r2, r3 started
   08:59, 09:07, 09:14; the operator reports a cold start that morning). The argument below that
   "warm-up is monotonic" rules out a *smooth* drift, not an intermittent cold-session effect.
   **What would separate them:** alternate active and silent runs on a card already warm.

| run | what the agent was doing | degraded points |
|---|---|---|
| `asc` | running `nvidia-smi pmon` checks and composing replies | **4** — 1560, 1590, 1620, 1747 |
| `asc-r2` | silent during the run, composing replies around it | **1** — 1590 |
| `asc-r3` | silent | **0** |

`bench_seconds` is the readable column, because at fixed work it must fall monotonically as clock
rises:

```
asc     14.05 13.75 13.45 13.18 12.85 12.60 13.86 13.59 13.05 11.66 11.41 11.22 12.01
asc-r2  14.05 13.75 13.44 13.18 12.84 12.62 12.42 13.30 12.35 11.66 11.41 11.22 11.03
asc-r3  14.06 13.76 13.46 13.19 12.85 12.64 12.43 12.14 11.94 11.67 11.42 11.24 11.05
```

Only r3 is monotonic. **A point that departs the trend and then returns to it is not warm-up** —
warm-up is monotonic and does not recover.

**This is NOT the 2026-09-18 contamination.** That was the test suite imposing a **uniform
−9.38% at every point**. This removes **8–11% from isolated points while their neighbours are
untouched**, and lands on different frequencies each time. **A point-to-point residual cannot
find either**, which is why three replicates were needed.

**It is almost certainly the same unexplained defect CLAUDE.md has carried since August** —
*"every verified-quiet `membw` sweep on the 10-point grid has a worst point"*, *"a defect that
lands on a different frequency each time is transient"*. ~~**This is the first time it has been
caught on `gemm` with a controlled A/B/C, and the first evidence that it is driven by machine
activity rather than being intrinsic.**~~ **Struck 2026-09-22:** it was not controlled. Activity,
run order and warm-up changed together. It is the first time the signature was **caught on `gemm`
in replicate**, and activity is the leading hypothesis.

### The protocol that follows

**Replicate and take the maximum.** *This assumes the losses are one-sided, which holds in every
run so far and is not proven in general.* The defect only ever removes throughput, so the max across
replicates is the uncontended value — and r3 achieves it at all thirteen points. **A single
fine-grid sweep is not trustworthy at the ~1% level no matter how quiet the machine looks**, and
the preflight cannot help: every one of these runs passed preflight at 2–3% SM baseline.

### What was eliminated

| hypothesis | why not |
|---|---|
| thermal throttling | temperature **fell** at the slow points while the clock rose; throttling raises it |
| warm-up from a cold card | real and visible (44 → 52 °C over the first six points) but monotonic, and the bad points recover |
| power cap | `throttle_masks_seen` shows `0x4` SwPowerCap at 1500, 1530 and 1657 — **all of which were fine** — and 72–82 W against a 180 W limit |
| clock not held | `lock_held=True` and achieved = target at every point, including the slow ones |
| the 0.5 s sampling itself | r3 is clean at 0.5 s and matches the 2.00 s reference |

`0x400` appears on every point and is **not** decoded here — `tools/stability-logger/ThrottleReasons.ps1`
records it as an unknown bit that arrived with the 610.88 → 616.56 driver and appears in 589 of 603
samples of a healthy run.

---

## Provenance

**The operator was absent and two AI agents were resident on the machine** (Claude Code driving
the runs, OpenAI Codex working in the repository). Each run's `applied_settings` says so. The
degradation above is the measured cost of that arrangement; **r3 is the run to cite**, and the
other two are kept because the comparison between them *is* the methodological finding.

**Files:** `_sweep.csv` / `_sweep.json` per run, `_sweep_voltage.csv` the HWiNFO join.
These are the first sweeps carrying `window_start_unix` / `window_end_unix`, so the voltage join
ran in **time mode** rather than binning by clock — its first use on hardware-collected data.

---

# 4b — the descending twin. **The floor is a curve property, not a thermal one.**

Two descending replicates (`*-desc-r1`, `*-desc-r2`), same band, same config, same session. The
sweep counts DOWN from 1760, which *is* the experiment: the card arrives at each low frequency
having just been hot, instead of warming into it.

**Run TWICE deliberately.** 4i above showed isolated points losing 8-11% transiently on a
different frequency each time. 4b asks whether the floor differs by direction — **one descending
run with a transient bad point would look exactly like a direction effect**, which is the thing
being tested. Replication was a precondition, not a nicety.

## The answer

| | |
|---|---|
| descending vs ascending, 13 points | **mean +0.00%**, range ~~−0.04% to +0.08%~~ **−0.08% to +0.08%** *corrected 2026-09-22: `bench_throughput` by matched target against `asc-r3`. desc-r1 −0.0025% mean, −0.082 to +0.080; desc-r2 −0.0115%, −0.061 to +0.067. The old range matched neither.* |
| descending r1 vs r2 | max spread **0.06%** |
| floor end, both directions | **0.720 V through 1560, first rise at 1590** |

**And the thermal histories really are different**, which is what makes the null meaningful
rather than vacuous:

| | at 1378 MHz | at 1747 MHz |
|---|---|---|
| ascending (warming in) | **43.8 °C** | 51.1 °C |
| descending (cooling down) | **46.5 °C** | 48.2 °C |

**Up to ~4 °C apart at the extremes, and the floor and the throughput do not move at all.**

**So the floor extent belongs to the applied V/F curve, not to the card's thermal state** — the
branch of the worklist's reading table. **This is one chip.** `SESSION-E-RUNSHEET.md` §4d asks
the same question of the RTX 2060 Super, whose floor is the ambiguous one, and this does not answer
it there.

## A precision note worth keeping

Across `asc-r3`, `desc-r1` and `desc-r2` — three runs, two directions — **every one of the thirteen
points agrees to better than 0.1%.** That is roughly eight times tighter than the ~0.76%
within-session spread this project cites elsewhere, and it is what the fine grid plus 0.50 s
sampling plus a silent machine buys. It also means the 8-11% excursions documented above are
~~**four orders of magnitude**~~ **about two orders of magnitude outside the noise floor of this
measurement** *(corrected 2026-09-22: 8–11% against 0.1% is ~100x, not 10,000x)*, which is why they are
attributable at all.

**Corroboration of the dither finding, unlooked for:** `desc-r1` reports **0.738 V** at 1620 where
r3 reports 0.740. That is the 0.735/0.740 mixture showing up in the median — the same point 4i
independently flags at a 38% minority.

---

# 4h — the floor end, pinned. **1567–1575 MHz.**

Two ascending replicates, **1530–1620 MHz in 13 points (~7.5 MHz)**, stock Profile 3, 0.50 s
sampling. Closes the 30 MHz gap the coarser grids left.

| achieved MHz | 1545 | 1552 | 1560 | **1567** | **1575** | 1582 | 1590 |
|---|---|---|---|---|---|---|---|
| r1 | 0.720 | 0.720 | 0.720 | **0.720** | **0.730** | 0.730 | 0.730 |
| r2 | 0.720 | 0.720 | 0.720 | **0.720** | **0.730** | 0.730 | 0.730 |

**The floor ends between 1567 and 1575 MHz.** Both replicates agree at every one of the thirteen
points, and throughput agrees between them to within 0.2%.

**The sequence this number has been through is the useful part:**

| when | floor end | how |
|---|---|---|
| until 2026-09-18 | "1537" | **inferred**, never measured — nearest coarse points were 1545 and 1702 |
| 2026-09-18 | 1560–1590 | measured at ~31 MHz |
| **2026-09-22** | **1567–1575** | measured at ~7.5 MHz, replicated |

**It changes no verdict.** The suite grid is 158 MHz wide and the rule only needs a prediction
to land within half a step, so every conclusion built on the floor end stands unaltered. This
replaces a bracket with a measurement — which matters because this project carried an inferred
figure as though it were measured for weeks.

**No claim module had to change.** Checked by grepping `analysis/claims_*.py` for the
superseded extract, per CLAUDE.md's rule that a finer measurement means grepping the claims for the
file it replaces. The 1560/1590 hits in `claims_consumer.py` are `PLATEAU_TARGETS`, a band list and
a bootstrap interval — unrelated. CLAUDE.md's own prose did carry it, in two places, and both were
corrected.

**Dither shows up here too, independently.** At 1605 MHz achieved, r1 medians **0.735** and r2
medians **0.740** — the two runs straddle a code boundary at the same frequency, which is what a
genuinely dithering point looks like when you only keep the median.
