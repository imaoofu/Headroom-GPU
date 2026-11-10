# Rung B suite — worklist item 4e, 2026-09-23

**Twelve workloads × 13 frequencies (1237–3090 MHz), Afterburner Profile 1 = rung B, driver
616.92.** Collected **unattended**, operator absent, by `tools/hwinfo-logging/Invoke-LoggedSweep.ps1`,
same session as the activity A/B test (`../5060ti-activity-ab-20260923/`). HWiNFO at 0.50 s; every
sweep has its own time-joined voltage extract.

This collects `docs/REGISTERED-PREDICTIONS.md` §1, **registered 2026-09-11**.

---

## THE REGISTERED PREDICTION HOLDS

> **Registered:** *"The median efficiency optimum across the twelve-workload suite equals the grid
> point nearest the frequency the applied curve reaches at 0.720 V — 1702 MHz on rung B."*
> **Refuted by:** the median on any other grid point.

**Measured median: 1702 MHz. Nine of twelve workloads land individually on it**, above the
registered secondary threshold of 7 of 12.

| workload | optimum target | achieved |
|---|---|---|
| softmax, layernorm, bgemm64, bgemm128, bgemm256, bgemm1024, attention, conv, gemm | **1702** | 1695.0 |
| copy | 1852 | 1845.0 |
| bgemm32 | 1852 | 1843.5 |
| reduce | 2167 | 2160.0 |

With stock (1545, measured) and P4 (2010, measured), the ladder reads **1545 → 1702 → 2010**, each
on its predicted grid point. **One chip, one suite per rung, a ~155 MHz grid.** A prediction
needs only to land within half a step, so "on the grid point" is coarse. Twelve workloads are
repeated outcomes on one card, not twelve chips.

## Provenance: the profile was verified live, not assumed

- **Before applying:** the live Afterburner profile store was **byte-identical** to the committed
  snapshot `data/afterburner-profiles/5060ti-profiles-20260922-rungB/` (SHA-256 begins
  `110aa774d5fc4123`). The runner refused to continue otherwise.
- **After applying:** memory under load read **16301 MHz** (stock 13801, so +2500 live) and the
  power limit **200 W**. `memory_clock_max_mhz` is **at least 16301 at every one of the 156
  points**, so the +2500 stayed live throughout. (Use the maximum: the average and minimum catch
  idle memory between iterations.)
- **After the suite:** reverted to stock Profile 3 and verified at 13801 MHz, 180 W.
- NVML offset 0 throughout.

Runner: `runner-run-4e.ps1.txt` (saved as text; it ran from the session scratchpad). Console logs:
`runner-console-attempt2.log` is the run. **`runner-console-attempt1-refused.log` is a first launch
that took no data:** the first sweep's own preflight refused at 26% SM, drawn by **the Claude desktop
app rendering the driving agent's message** during the preflight window. The 10% guard worked as
designed. The relaunch adds a 90 s settle before the first sweep.

## Voltage: the lift is where it was built, and the region above matches P5

`gemm`, rung B today against P5 (`../voltage-curve-20260908/`, **a different session**), by target:

| target | B achieved | B V | P5 achieved | P5 V |
|---|---|---|---|---|
| 1545 | 1542.8 | 0.720 | 1537.0 | 0.720 |
| **1702** | 1695.0 | **0.720** | 1695.0 | **0.755** |
| 1852 | 1845.0 | 0.745 | 1845.0 | 0.795 |
| 2010 | 2002.0 | 0.795 | 2002.0 | 0.840 |
| 2167 | 2160.0 | 0.835 | 2153.7 | 0.840 |
| 2317–2782 | | 0.840 / 0.845 / 0.845 / 0.865 | | **identical** |
| 2932 | 2902.8 | 0.905 | 2925.0 | 0.910 |
| 3090 | 2909.8 | 0.910 | 2979.2 | 0.920 |

- **The floor extends one grid step further than P5's**: 0.720 V through 1695 achieved, where P5 had
  already risen to 0.755. That is the +170 lift, measured.
- **2317–2782: the same VID codes as P5**, which is the above-floor equivalence the rung B snapshot
  README said had to be checked by measurement, not decoded. At **2167** B reads 0.835 against
  0.840, one 5 mV code apart.
- **At the top, rung B reaches lower clocks** (2909.8 against 2979.2 at the 3090 target, and
  2578 against 2602 at 2625). This compares **two sessions 15 days apart**, so it is recorded, not
  interpreted. It does not touch the verdict: the optimum is at 1702.

## Missed locks — all BELOW target, all at 2317 MHz and above

Every sweep has at least one point that missed its lock target, **always below it and always at
2317 MHz or higher**. No benchmark failed.

| target | 2317 | 2475 | 2625 | 2782 | 2932 | 3090 |
|---|---|---|---|---|---|---|
| rung B, sweeps missing (of 12) | 3 | 4 | 10 | 2 | 1 | 12 |
| P1, 2026-09-22 (of 12) | 0 | 0 | 3 | 1 | 3 | 12 |

**Rung B misses lower down the curve than P1 did**, at 2317 and 2475, and far more often at
2625. P1 is a **different curve** (+478 below the floor, no P5 split) **and a different session**, so
this is not a like-for-like comparison. The misses sit around the 845→850 mV step in the stored curve
(2362 → 2180), the region the snapshot README says cannot be read from the file. **Observation only.**
No missed point is any workload's efficiency optimum, so the verdict does not depend on them.

## What is dataset-grade

All twelve sweeps are complete, verified-live rung B measurements with voltage. The console logs and
runner text are provenance, not data.
