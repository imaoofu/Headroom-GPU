<!-- dataset-grade: yes -->

# `rtx2060s-sessione2-20260927` — Session E2: 4c-offset FAIL_NO_MOVEMENT

**RTX 2060 Super (MSI Ventus 2X, TU106), 36 sweeps, one unattended Headroom Bench session,
2026-09-27 20:05–23:24**, on the shop machine through the USB kit. Driver **617.14**, the same as
Session E. Enforced power limit 175 W (175 default, 185 max). HWiNFO at 0.50 s, every sweep
time-joined to its own suite log (`join_hwinfo_voltage.py --join-by time`), with a minimum of 17
samples per point.

**Registered before collection:** `docs/REGISTERED-PREDICTIONS.md` §4d, Amendment 3 (written
**after** Session E's descriptive result was seen; the prediction was not changed). Scorer:
`python analysis/score_session_e.py <this dir> --e2`. Profiles:
`data/afterburner-profiles/rtx2060s-profiles-20260927b-offset/` (P1 stock, P2 = stock + −165 MHz
core offset). **Never quote this result without Session E's** (`rtx2060s-sessione-20260927/`,
NOT SCOREABLE, descriptively no movement), as Amendment 3 requires.

## What ran

Every suite swept the same explicit list, **855, 960 … 2010 MHz (12 targets)**
(`sweep_targets_explicit: true` in every JSON), so the offset could not move the grid as it did in
Session E.

| run | what | sweeps | witness (locked-clock voltage) |
|---|---|---:|---|
| `stock-4` | 12-workload suite, P1 | 12 | P1 at 1065: **0.644 V** |
| `offset-5` | 12-workload suite, P2 | 12 | P2 at 1065: **0.681 V**, at 1275: **0.744 V**, as in Session E and as predicted from the stored curve |
| `stock-6` | 12-workload suite, P1 | 12 | P1 at 1065: **0.644 V** |

- The first launch (20:04) was refused by the quiet gate at 5% SM; Raymond relaunched at 20:05.
  Both session records are in `bench-records/`.
- **The bench reports the session as FAIL, and that is a tool defect, not a data problem.** All
  three suites collected; the closing stock-return gate then threw *"needs 13 points on each side"*,
  because `Stock-Drift.ps1` hard-coded Session E's 13-point grid. Fixed in `8263896`. The scorer
  computes the same statistic itself: **worst workload 0.524%** (limit 1.5%). The cleanup step
  (verify stock) never ran.
- The raw HWiNFO logs are in `data/HWiNFO-Data/rtx2060s-sessione2-20260927/` (gitignored).

## 4c-offset — FAIL_NO_MOVEMENT (scored as registered)

Every scoreability condition holds: one driver, the 12 targets in all 36 suites, stock medians
equal (1065 / 1065), stock return 0.524%, every witness in range.

| run | median optimum | per workload |
|---|---|---|
| `stock-4` | **1065** | copy 1065, reduce 960, softmax 1170, layernorm 1065, bgemm32 1275, bgemm64 1065, bgemm128 1170, bgemm256 1065, bgemm1024 960, attention 1275, conv 1170, gemm 960 |
| `offset-5` | **1065** | copy 960, reduce 1170, softmax 1065, layernorm 1065, bgemm32 1170, bgemm64 1170, bgemm128 1065, bgemm256 1065, bgemm1024 855, attention 1170, conv 1065, gemm 855 |
| `stock-6` | **1065** | copy 1065, reduce 960, softmax 1170, layernorm 1065, bgemm32 1065, bgemm64 1170, bgemm128 1065, bgemm256 1170, bgemm1024 960, attention 1065, conv 1065, gemm 960 |

**The prediction was the median moving into 855–960 MHz. It stayed at 1065.**

### Descriptive, not scored

Median across the 12 workloads of efficiency relative to each workload's own peak, with the median
reported voltage:

| target | stock-4 | offset-5 | stock-6 |
|---:|---|---|---|
| 855 | 92.7% · 0.637 V | **97.3%** · 0.644 V | 92.4% · 0.637 V |
| 960 | 97.8% · 0.637 V | 98.7% · 0.656 V | 98.5% · 0.637 V |
| 1065 | 99.2% · 0.644 V | 99.9% · 0.681 V | 99.8% · 0.644 V |
| 1170 | 98.4% · 0.669 V | 98.3% · 0.706 V | 97.8% · 0.669 V |
| 1275 | 96.6% · 0.694 V | 94.2% · 0.744 V | 97.5% · 0.694 V |
| 1380 | 92.7% · 0.725 V | **88.2%** · 0.794 V | 95.4% · 0.725 V |
| 1485 | 88.1% · 0.762 V | 81.4% · 0.844 V | 88.1% · 0.762 V |

- **The offset changed the measured efficiency profile, but did not move the registered median
  optimum on this 105 MHz grid; the displacement of any continuous optimum is unresolved.** The
  low end rose *relative to each workload's own peak* (855 MHz: 92.4–92.7% on stock against 97.3%;
  the stock-to-stock span there is 0.35 points) and the region above the peak fell faster. Mean
  regret at 960 MHz is 1.51% under the offset against 1.77–2.45% on stock; at 1065 it is 1.05%
  against 1.07–1.45%.
- **That rise is relative, not an absolute gain.** At 855 MHz the offset's median per-workload
  absolute efficiency is **2.1–2.6% below** stock's, with board power up 2.0–2.6%; at 1380 it is
  12.2–12.6% below, with power up 13.1–14.0% (GPT Job 31, recomputed). Normalising each workload to
  its own, now lower, peak is part of why 855 looks better.
- **Per-workload movement is larger than the one stock pair, but does not change the registered
  statistic.** Stock-to-stock, 6 of 12 workloads change their optimum (4 down, 2 up). The offset
  moves 10 against `stock-4` (8 down, 2 up) and 8 against `stock-6` (5 down, 3 up). Both exceed the
  stock pair's 6 and lean downward. **This said "the count is inside what two identical stock
  suites produce" until 2026-09-28, which is numerically false** (GPT Job 31). One stock pair is
  not a null distribution, and the registered verdict rests on the median, which did not move.
- **Under the offset no grid point reaches the stock floor voltage:** 855 MHz already reads
  0.644 V, stock's 1020 MHz reading. That is the whole-curve shift working as the witnesses said.
- The registration reads a fail as *"the optimum is tied to frequency, not to the curve"*. The
  changed profile above makes that reading too strong, but the data do **not** show the optimum
  moving by less than one step either: `gemm` and `bgemm1024` peak at the lowest sampled target
  under the offset, and a three-point sub-grid fit on the other ten (GPT Job 31, exploratory) moves
  them 73.6–83.1 MHz median against 49.7 MHz stock-to-stock. This said *"the curve did matter,
  just not by a full 105 MHz grid step"* until 2026-09-28; that bound is unsupported. All of this
  is written **after** seeing the data.
- **Contrast, not replication:** on the 5060 Ti, §7's **registered verdict was INVALID**; a
  post hoc revised scoring then gave a falling 1545 / 1395 / 1237 MHz ladder under NVML offsets. The two cards differ in architecture, in the offset method (Afterburner
  against NVML) and in grid step, so this does not show which of them is responsible.

**Limits:** one chip, one session, one offset size. A whole-curve offset, not region-targeted, so
it says nothing about 4c's disjunction. The grid is coarse against the shift: 165 MHz is about
1.6 steps of 105 MHz, so a movement of less than a full step cannot register in the median.
