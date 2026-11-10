# RTX 3070 Ti — Session D, the registered causal test on a second chip, 2026-09-24

Six twelve-workload suites and three fine sweeps, collected unattended by Headroom Bench
(`tools/bench-app/`) from the plan `bench/bench-plan-20260924-160923.json`, plus **C8**
(`fine/finefloor-desc`), the 2026-09-23 shakedown's descending sweep from its own session and
plan. So the 76 sweeps are **75 from Session D and one from the day before**. *This sentence
said all four fine sweeps came from the Session D plan until 2026-09-25 (GPT Job 19).* Its SHA-256 is
`5DBBECDD…` and equals the `planHash` in `bench/bench-session-20260924-160923.json`. The
predictions are `docs/REGISTERED-PREDICTIONS.md` §4a, §4b and §8, all registered before
collection.

## Results, scored by the scripts committed before collection

| | test | result |
|---|---|---|
| **4a** | Edit 1 moves the median optimum from 1485 into 1170–1275 MHz | **PASS**, `edit1-2` median **1222.5 MHz** |
| **4b** | Edit 2, the negative control, leaves it at 1485–1500 MHz | **FAIL**, `edit2-3` median **1432.5 MHz** |
| joint | | **CONTROL_ALSO_MOVES_ATTRIBUTION_FAILS** |
| **8a** | the Edit 1 replicate lands in 1170–1275 MHz | **PASS**, `edit1-5` median **1170 MHz** |
| **8b** | Edit 1's floor ends at ≤1200 MHz (≥0.831 V above 1215) | **FAIL**: **1230 MHz reads 0.819 V**; the floor ends between 1230 and 1275 |
| 8c | ascending against descending, stock, one session | exploratory: **+0.00% mean**, −0.06% to +0.10% |

Stock medians are **1485 MHz in all three stock suites**. The worst workload's stock return is
**0.619%** from stock-1 to stock-4 and **1.192%** from stock-4 to stock-6 (limit 1.5%).

```
python analysis/score_session_d.py data/frequency-sweeps/rtx3070ti-sessiond-20260924
python analysis/score_session_d.py data/frequency-sweeps/rtx3070ti-sessiond-20260924 --replicate
```

**The headline is the failed control, not the passing manipulation.** On this chip the optimum
moved with Edit 1 twice, as predicted, **and it moved with Edit 2 as well**, so the move cannot be
attributed to the floor region here. The full reading is in `REGISTERED-PREDICTIONS.md` under 4b
and §8. It includes three points that do not change the verdict:
- the control's median is a 6/6 split;
- identical stock suites disagree on 3–4 of 12 per-workload argmaxes;
- Edit 2 lowered the 825 mV point, which is inside the floor band.

**n = 1 chip, one session.** The twelve workloads are repeated outcomes on it.

## The runs

| folder | profile | collected | notes |
|---|---|---|---|
| `20260924-161512_…-stock-1` | P1 stock | 16:15–17:16 | |
| `20260924-173607_…-edit1-2` | P2, Edit 1 | 17:36–18:37 | second attempt; see below |
| `20260924-183848_…-edit2-3` | P3, Edit 2 | 18:38–19:41 | peak 234 W: the curve clips at ~1500 MHz |
| `20260924-202902_…-stock-4` | P1 stock | 20:29–21:30 | second attempt; see below |
| `20260924-214751_…-edit1-5` | P2, Edit 1 | 21:47–22:49 | §8a |
| `20260924-225042_…-stock-6` | P1 stock | 22:50–23:52 | §8a closing bracket |
| `fine/finefloor-asc2-…`, `fine/finefloor-desc2-…` | P1 stock | 21:31–21:39 | §8c, 1200–1590 MHz, 10 points |
| `fine/edit1-finefloor-…` | P2, Edit 1 | 21:40–21:46 | §8b, descending 1050–1590 MHz, 13 points |
| `fine/finefloor-desc` | P1 stock | **2026-09-23** 22:09 | C8, the shakedown session's descending sweep (`bench/bench-session-20260923-215615.json`) |

Every suite sweep reached **13 of 13** points; the fine sweeps reached 10 of 10 or 13 of 13.
Across all 76 sweeps:
- encoder and decoder at **0%**;
- driver **617.14**;
- SILENT BIOS **290 / 290 / 320 W**, checked by the preflight gate and by the scorer;
- iteration counts from `rtx3070ti-suite-20260904`;
- Afterburner store pinned by its `[Profile1]`–`[Profile3]` section hash `A1159941DA541EB9`;
- every profile checked under load before measuring, and P2 at locked 1395 MHz each time
  (0.850 V).

Idle baseline was ≤3.4% on every suite sweep. **The §8b sweep started at 7.0%**, over the ~5%
the protocol prefers. 8b is a voltage result, and CLAUDE.md records that contamination moves
throughput, not voltage.

**Voltage.** Each `*_sweep_voltage.csv` was joined by the benchmark's own timed windows
(`tools/frequency-sweep/join_hwinfo_voltage.py --hwinfo-utc-offset=-07:00`). Every extract covers
every point, with at least **16** HWiNFO samples each at 0.5 s. The raw logs are in
`data/HWiNFO-Data/rtx3070ti-sessiond-20260924/` (gitignored, kept locally).

## Two interruptions, and what was left out

The session was resumed twice. A resume restarts the interrupted run from its start, with fresh
paths.
- **Step 17, 17:17:** `Collect.ps1`'s early busy check read 12% from one sample, at the start of
  `edit1-2`. Fixed to a median of five (commit 493ab6a). No sweep of that attempt was written.
- **Step 27, 19:59:** the session record's save failed, *"Cannot create a file when that file
  already exists"*, 16 minutes into `stock-4`. The window was reading the file while the engine
  replaced it, on a FAT32 USB. Fixed with `Write-Atomic.ps1` (commit b881273).
  **That attempt's partial folder (`20260924-194221_…-stock-4`, 3 of 12 sweeps) and its HWiNFO
  log are NOT imported.** The scorer refuses two `stock-4` suites, and a partial suite is not a
  measurement of anything registered.

`bench/` holds the session record, its output log, the window's error log, and both plans.

## What this data does not support

- **Any claim that the floor region causes the optimum on this chip.** The registered control
  failed.
- **Edit 1's floor end at 1200 MHz.** §8b measured it between 1230 and 1275.
- Comparing these suites with `rtx3070ti-suite-20260904` without noting the driver (610.88 then,
  617.14 now) and the cross-session drift this project measures (~1.5% on `gemm`).
