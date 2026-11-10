<!-- dataset-grade: yes -->

# `rtx2060s-sessione-20260927` — Session E: 4d PARTIAL, 4c-offset NOT SCOREABLE (its grid shifted)

**RTX 2060 Super (MSI Ventus 2X, TU106), 37 sweeps, one unattended Headroom Bench session,
2026-09-27 14:26–18:12**, on the shop machine through the USB kit. Driver **617.14** (the 09-15
reference ran on 616.92). Enforced power limit 175 W (175 default, 185 max). HWiNFO at 0.50 s,
every sweep time-joined to its own suite log (`join_hwinfo_voltage.py --join-by time`), with a
minimum of 17 samples per point.

**Registered before collection:** `docs/REGISTERED-PREDICTIONS.md` §4c, §4d and the §4d amendments
of 2026-09-25 and 2026-09-27. Scorer: `python analysis/score_session_e.py <this dir>` (4c) and
`… --4d`. Profiles: `data/afterburner-profiles/rtx2060s-profiles-20260927b-offset/` (P1 stock,
P2 = stock + −165 MHz core offset).

## What ran

| run | what | sweeps | witness (locked-clock voltage) |
|---|---|---:|---|
| `e1-desc` | descending fine floor, 1140 → 900 MHz, `gemm` | 1 | P1 at 1065: **0.644 V** |
| `stock-1` | 12-workload suite, P1 | 12 | P1 at 1065: **0.644 V** |
| `offset-2` | 12-workload suite, P2 | 12 | P2 at 1065: **0.681 V**, at 1275: **0.744 V** (both as predicted from the stored curve) |
| `stock-3` | 12-workload suite, P1 | 12 | P1 at 1065: **0.644 V**; stock return, worst workload **0.21%** (limit 1.5%) |

The first launch (14:25) was refused by the quiet gate at 28% SM, and Raymond relaunched at 14:26.
Both session records are in `bench-records/`. The raw HWiNFO logs are in
`data/HWiNFO-Data/rtx2060s-sessione-20260927/` (gitignored).

## 4d — PARTIAL (scored as registered)

| target | 900 | 915 | 945 | 960 | 975 | 1005 | 1020 | 1065 | 1140 |
|---|---|---|---|---|---|---|---|---|---|
| ascending, 09-15 (V / °C) | 0.644 / 42.0 | 0.644 / 46.4 | 0.637 / 49.5 | 0.637 / 51.9 | 0.631 / 54.0 | 0.631 / 55.5 | 0.637 / 56.2 | 0.644 / 57.6 | 0.662 / 58.7 |
| **descending, today** | **0.637** / 54.7 | **0.637** / 54.8 | **0.631** / 55.5 | **0.631** / 55.7 | 0.631 / 56.1 | 0.631 / 56.6 | 0.637 / 56.8 | 0.644 / 57.4 | 0.662 / 55.5 |

The minimum set widens from {975, 1005} to **{945, 960, 975, 1005}**, and 900–915 read one code
lower on the warm card. Under the registration that means **both temperature and the curve
contribute**. That is the registered reading of PARTIAL, not an isolated causal finding: sweep
direction, thermal history and driver all differ between the two sweeps, one each way (GPT Job 31).
Report the split, and never quote a floor extent on this card without its sweep
direction beside it. The driver differs from the reference (617.14 against 616.92), reported
beside the verdict as registered. One sweep in each direction.

## 4c-offset — NOT SCOREABLE: the offset moved the clock table, so offset-2's grid shifted by −15 MHz

The registration requires every suite on the 855–2115 grid. **offset-2 ran on 840, 945, 1050 …
2100.**
- Under the −165 MHz offset the supported-clock table became **121 clocks, 300–2100** (122 clocks,
  300–2115 at stock).
- The suite derives its grid from the table top, so every target moved down by 15 MHz.
- The kit's engine checks the table top only at session start, so nothing stopped the run.
- **This was a design miss:** nobody checked beforehand whether an offset changes the table.

**Descriptive only, not a verdict:**

| suite | median optimum | per-workload |
|---|---:|---|
| stock-1 | **1065** | 960 ×4, 1065 ×6, 1170 ×2 |
| offset-2 (shifted grid) | **1050** | 945 ×3, 1050 ×5, 1155 ×4 |
| stock-3 | **1065** | 855, 960 ×2, 1065 ×5, 1170 ×2, 1275, 1380 |

- **The offset median sits at the same grid position as stock's, 15 MHz lower.** The prediction was
  855–960 (about 840–945 on the shifted grid), so descriptively the optimum **did not follow** the
  −165 MHz shift.
- **Per-workload optima are noisy.** Only 5 of 12 match between the two stock suites, although both
  medians are 1065.
- **Offset voltages follow the stored curve at 945, 1050 and 1260.** At 840 the reading is **0.644**,
  not the 0.631 floor, so the offset grid never reached a floor point.

**A re-run on a fixed explicit grid is registered as Amendment 3 (§4d)** and is the scored test.
This session's 4c-offset stays NOT SCOREABLE whatever the re-run shows.

## Limits

One chip, one session, one sweep each way for 4d. The reported voltage is a VID lookup on a
6.25 mV grid, not rail voltage. Board energy only.
