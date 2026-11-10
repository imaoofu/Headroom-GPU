# Rung C suite — worklist item 4f, 2026-09-26

**Twelve workloads × 13 frequencies (1237–3090 MHz), Afterburner Profile 1 = rung C, driver
616.92.** Collected **unattended**, operator absent, driving agent silent, by
`tools/hwinfo-logging/Invoke-LoggedSweep.ps1`. HWiNFO at 0.50 s; every sweep has its own time-joined
voltage extract (156 points, **minimum 14 samples per point**). ChatGPT and Codex were closed; every
sweep's own preflight read 2.4–4.8% baseline utilisation with the video engines idle.

This collects `docs/REGISTERED-PREDICTIONS.md` §1, **registered 2026-09-11**, and completes its
four-rung ladder. Same grid and iteration counts as the rung B suite (`../5060ti-rungB-suite-20260923/`).

---

## THE REGISTERED PREDICTION HOLDS, ON ALL THREE LEVELS

> **Registered:** *"The median efficiency optimum across the twelve-workload suite equals the grid
> point nearest the frequency the applied curve reaches at 0.720 V — … 1852 MHz on rung C."*
> **Refuted by:** the median on any other grid point; optima not increasing monotonically A → B → C →
> D; both new rungs on the same grid point.

**Measured median: 1852 MHz. Nine of twelve workloads land individually on it**, above the
registered secondary threshold of 7 of 12. Optimum = argmax of throughput / average board power over
the 13 targets, the same rule that reproduces rung B's committed result (1702, nine of twelve).

| workload | rung B | **rung C** | achieved on C |
|---|---|---|---|
| softmax, bgemm64, bgemm128, bgemm256, bgemm1024, attention, conv, gemm | 1702 | **1852** | 1845.0 |
| bgemm32 | 1852 | **1852** | 1845.0 |
| copy | 1852 | 2010 | 2002.0 |
| layernorm | 1702 | 2010 | 2002.0 |
| reduce | 2167 | 2317 | 2310.0 |

**The ladder, all four rungs on their predicted grid points, in order:**

| rung | offset below 850 mV | clock at 0.720 V | predicted | measured median |
|---|---|---|---|---|
| A (stock / P5 / P2) | +0 | 1530 | 1545 | 1545 (earlier sessions) |
| B | +165 to +172 | 1702 | 1702 | **1702** (2026-09-23) |
| **C** | **+315** | **1845** | **1852** | **1852** (this directory) |
| D (P4) | +472 | 2002 | 2010 | 2010 (earlier sessions) |

- **Primary:** median 1852.
- **Secondary:** 9 of 12 (threshold 7). `reduce` is included and misses, as registered it would.
- **Tertiary:** 1545 / 1702 / 1852 / 2010, monotone and one grid step apart.
- **Refutations:** none occurred. B and C land on different grid points.

**Limits, stated with the result.**
- **One chip.** Twelve workloads are repeated outcomes on one card, not twelve chips.
- **One suite per rung,** and the four rungs come from **different sessions** (A and D earlier; B on
  09-23; C today).
- **A ~155 MHz grid,** so "on the predicted point" means within half a step.
- **Per-workload optima reproduce only about 9 of 12 between identical runs** (2026-09-22), so weight
  the median over the per-workload counts.
- **The rule is the ridge point, published prior art** (CLAUDE.md, the load-floor section). What
  this adds is a relocation predicted in advance from the floor voltage, tracked across four levels
  of a knob.

## Provenance: the profile was verified live, not assumed

- **Before applying:** the live Afterburner profile store was **byte-identical** to the committed
  snapshot `data/afterburner-profiles/5060ti-profiles-20260926-rungC/` (SHA-256 begins
  `4fdfbf241c1dae7a`). The runner refuses otherwise.
- **After applying:** memory under load read **16501 MHz** and the power limit **200 W**. The +2500
  offset should give 16301; the 16501 reading was a single maximum over a short sampling window,
  inside the runner's acceptance band (16101–16601). **`memory_clock_max_mhz` is at least 16301 at
  all 156 points**, so the memory offset stayed live throughout.
- **After the suite:** reverted to stock Profile 3 and verified at **13801 MHz, 180 W**.
- NVML offset 0 throughout.

**`runner-console-attempt1-refused.log` is a first launch that took no data.** Its live-profile check
read **810 MHz**, idle memory, because its six reads came 3–5 s after starting a load that had not
reached the GPU yet. The power limit had already gone to 200 W, so the profile was live and the
check was wrong. It refused as designed and reverted to stock. The runner (`runner-run-4f.ps1.txt`,
otherwise rung B's runner with the rung swapped) now samples for up to 30 s and takes the maximum
from 3 s after the load starts. **The acceptance band was not changed.** `runner-console-attempt2.log`
is the run.

## Voltage: the floor is one grid step longer than rung B's, and the region above is unchanged

`gemm`, rung C against rung B, by target:

| target | B achieved | B V | C achieved | C V |
|---|---|---|---|---|
| 1545 | 1542.8 | 0.720 | 1543.8 | 0.720 |
| 1702 | 1695.0 | 0.720 | 1695.0 | 0.720 |
| **1852** | 1845.0 | **0.745** | 1845.0 | **0.720** |
| 2010 | 2002.0 | 0.795 | 2002.0 | 0.755 |
| 2167 | 2160.0 | 0.835 | 2160.0 | 0.795 |
| 2317–2932 | | 0.840 / 0.845 / 0.845 / 0.865 / 0.905 | | **identical** |
| 3090 | 2909.8 | 0.910 | 2913.2 | 0.9075 |

- **0.720 V holds through 1845 MHz achieved**, where rung B had already risen to 0.745. That is the
  +315 lift, measured.
- **2317–2932 carry the same VID codes as rung B** (and therefore P5), which is the above-floor
  equivalence the snapshot README said had to be settled by measurement.
- 3090's 0.9075 is the median of an even sample count straddling two 5 mV codes.

## Missed locks — all BELOW target, all at 2475 MHz and above

| target | 2317 | 2475 | 2625 | 2782 | 2932 | 3090 |
|---|---|---|---|---|---|---|
| rung C, sweeps missing (of 12) | **0** | 2 | 10 | 2 | 1 | 12 |
| rung B, 2026-09-23 (of 12) | 3 | 4 | 10 | 2 | 1 | 12 |

Almost the same pattern as rung B, which shares everything above 850 mV with it. **Observation
only.** No missed point is any workload's efficiency optimum, so the verdict does not depend on them.

## What is dataset-grade

All twelve sweeps are complete, verified-live rung C measurements with voltage. The console logs and
runner text are provenance, not data. Raw HWiNFO logs are in `data/HWiNFO-Data/5060ti-rungC-suite-20260926/`
(gitignored).
