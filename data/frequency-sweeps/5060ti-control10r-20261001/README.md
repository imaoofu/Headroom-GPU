# RTX 5060 Ti — §10 re-collected, 2026-10-01: PASS, under desktop load

`docs/REGISTERED-PREDICTIONS.md` §10 (registered `1c4e10d`, witness `a7bcd44`), collected again under
its Amendment 2 of 2026-09-30. Three twelve-workload suites, **P5 → P2 → P5**, 09:46–12:41, unattended,
by `tools/hwinfo-logging/experiments/Run-ControlRepeat-20261001.ps1` as step 3 of the 2026-10-01
chain, after §14. Driver 616.92, ChatGPT/Codex closed, mVolt+ offsets all read 0 before the first
suite, 0 display-driver events, every wrapper exit 0. `queue-runner.log` is the runner's log.

```
python analysis/score_control10.py data/frequency-sweeps/5060ti-control10r-20261001
```

| | |
|---|---|
| P5 return, `p5a` → `p5b`, worst workload | **0.635%** (limit 1.5%; the 09-25 collection failed by 7.57%) |
| median optimum, P5 / P2 / P5 | **1545 / 1545 / 1545 MHz** |
| P2 optima differing from both P5 optima | **4 of 12** (`bgemm32`, `copy`, `gemm`, `softmax`) |
| registered verdict | **PASS** |

**Not a quiet run.** HWiNFO records an unidentified desktop load in all 468 benchmark windows:
**148–240 frames per second presented, 16–64% GPU bus load** (per-window medians). It started at
09:46, with this queue, and ended at 14:03; the §14 session immediately before it was quiet (4–7 fps,
1–7%). The P5 bracket returned under it, but equal P5 endpoints do not exclude a load present only
during P2 (GPT Job 40), and desktop load depresses the low and mid band more than the top
(CLAUDE.md, §5.4.4).
**Absolute throughput and efficiency values here are not clean**, and the PASS is a within-session
comparison under that load.

Raw HWiNFO logs (0.50 s) are gitignored, in `data/HWiNFO-Data/5060ti-control10r-20261001/`.

**Dataset grade:** usable for the registered within-session comparison, n = 1 chip, twelve workloads
as repeated outcomes. Not for absolute throughput.
