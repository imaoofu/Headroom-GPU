# RTX 5060 Ti — is the `reduce` residual a workload property or a run-order artifact? (worklist 4m)

**Registered before collection:** `docs/REGISTERED-PREDICTIONS.md` §9, commit `69ea460` at 09:06:56,
2026-09-24. The first sweep here started at 09:32.

**The design:**
- stock Profile 3, verified by memory under load (13801 MHz) and power limit (180 W);
- the suite grid, 1237–3090 MHz, 13 points, ascending;
- `reduce` at 2870 iterations and `copy` at 2660, from `5060ti-stock-repro-20260922`;
- driver 616.92;
- eight sweeps in the fixed order **R C C R R C C R**, operator away, the Claude app minimized.

Run by `tools/hwinfo-logging/experiments/Run-Queue-20260924.ps1` straight after 4n; its log is
`queue-runner.log`. Every wrapper exit was 0.

## Registered outcome: WORKLOAD PROPERTY

The optimum is the grid target with the highest throughput per watt among rows whose lock held.
The rule was 1545 MHz.

| sweep | position | optimum | runner-up, efficiency relative to the optimum |
|---|---|---|---|
| 01 `reduce` | not after `copy` (after the stock check) | **1702** | 1852, −1.73% |
| 04 `reduce` | right after `copy` | **1702** | 1545, −2.34% |
| 05 `reduce` | not after `copy` (after `reduce`) | **1852** | 1702, −2.62% |
| 08 `reduce` | right after `copy` | **1702** | 1545, −1.20% |
| 02 `copy` | | 1545 | 1395, −1.60% |
| 03 `copy` | | 1545 | 1395, −1.62% |
| 06 `copy` | | 1702 | 1395, −1.10% |
| 07 `copy` | | 1545 | 1395, −0.91% |

**All four `reduce` optima are above 1545, in both positions.** That is the registered "workload
property" outcome. `reduce`'s offset does not follow its place after `copy`, so it is not evidence
that the per-workload residuals are run-order artifacts.

**The limits registered in advance:**
- n = 2 per position, one chip, one session;
- "not after `copy`" mixes two histories;
- `copy` is the only neighbour tested.

**And one this data shows.** The efficiency curves are flat near the top: every runner-up is within
0.9–2.6% of its optimum, so an optimum's grid point is decided by small differences. `copy`'s one move
to 1702 (sweep 06, 1.10% ahead of 1395) is that kind of case. "`reduce` sits above 1545" held in 4 of
4; the exact bin, 1702 or 1852, is less stable.

**Missed locks:** 2932 and 3090 MHz in every sweep (stock cannot reach them), plus 2782 in sweeps 02,
06 and 08. All missed below target, and none is near an optimum.

## Files

`*_sweep.csv`, `*_sweep.json`, `*_sweep_voltage.csv` (joined by timed window, HWiNFO at 0.50 s) for
the eight sweeps; `queue-runner.log`, the runner's log for the whole morning queue (4n, 4m and the A/B).
