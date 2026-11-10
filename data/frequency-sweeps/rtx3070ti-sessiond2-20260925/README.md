# RTX 3070 Ti — Session D2, the negative control repeated (§8d), 2026-09-25

Three twelve-workload suites, **stock-7 (P1) → edit2-8 (P3, Edit 2) → stock-9 (P1)**, collected
08:22–11:43 by Headroom Bench from `bench/bench-plan-20260925-082202.json`. The plan's SHA-256 is
`004B1F8A…` and equals the session record's `planHash`.

**It ran untouched.** The window opened the only active run list for this card, asked no resume
question, and every step passed on the first attempt. There is no window-error log. It is the first
bench session with no interruption.

Registered: `docs/REGISTERED-PREDICTIONS.md` §8d, in `01623d3`, before collection. Its scorer,
`score_session_d.py --control-replicate`, was committed in `8305cfb`, also before collection.

## Registered verdict: NOT SCOREABLE — the grid was not Session D's

```
python analysis/score_session_d.py data/frequency-sweeps/rtx3070ti-sessiond2-20260925 --control-replicate
8d cannot be scored: ...stock-7-copy_sweep.csv: usable sweep rows do not match the 13-point grid
```

§8d registered **"the same grid ... as Session D"**, and the pre-committed scorer enforces that. The
grid moved **above 1485 MHz**:

| | 855–1485 MHz (7 points) | the top six |
|---|---|---|
| Session D, 2026-09-24 | 855 … 1485 | **1590, 1695, 1800, 1905, 2010, 2115** |
| Session D2, 2026-09-25 | 855 … 1485, identical | **1605, 1710, 1815, 1920, 2025, 2130** |

**Why:** `Collect.ps1` builds its grid from the card's supported-clock table. That table had **116**
entries on Friday against **115** on Thursday, and its top entry rose from 2115 to 2130 MHz. The
card, driver (617.14) and BIOS (290/290/320 W) were the same. It has happened before:
`rtx3070ti-suite-20260904` also swept 852–2130. **The cause of the table's change is not known.**
The registration assumed the grid was fixed by the design, and nothing in the collection could
pin it. Future registrations on this card should name the target list, and the tool should refuse
another.

**The scorer was not loosened after the data was seen, and 8d stays NOT SCOREABLE.** 4b stays FAIL.

## Descriptive only: on the collected grid, the control held

Computed with the registered rules, except the grid: per-workload `efficiencyPeak` on the target
grid, and Edit 2's six clipped targets as one median-efficiency bin at 1500 MHz. The clipped points
achieved 1485–1515 MHz, as Edit 2 should.

| suite | median optimum | per-workload optima |
|---|---|---|
| stock-7 | **1485** | copy 1065, reduce 1065, layernorm 1380, conv 1380, gemm 1380; the other seven 1485 |
| **edit2-8** | **1485** | copy 855, reduce 855, layernorm 1275, conv 1380, gemm 1380; bgemm32/128/1024 and attention 1485; softmax, bgemm64 and bgemm256 1500 (the clipped bin) |
| stock-9 | **1485** | copy 1170, reduce 855, layernorm 1065, conv 1380; the other eight 1485 |

- **Stock return:** the worst workload is 0.563% (`reduce`), against a limit of 1.5%.
- **Floors:** the control floor check passes on all 12 `edit2-8` extracts (1485 and the six clipped
  targets ≤0.825 V), and 1485 reads on the floor in both stock suites.
- **If the grid had matched, this would read as a PASS: 1485 is inside 1485–1500.** Session D's
  control gave 1432.5, a six-six split. So on this chip the control moved once and held once, on
  consecutive days. **That is a description of two runs, not a verdict.**

## The files

- Each suite folder holds the 12 sweeps, their JSONs, `machine-info.txt`, and a time-windowed
  `_sweep_voltage.csv` for every sweep: 13 of 13 points, at least **15** samples per point.
- The raw HWiNFO logs are in `data/HWiNFO-Data/rtx3070ti-sessiond2-20260925/` (gitignored).
- `bench/` holds the plan, the session record and the engine's output log.
