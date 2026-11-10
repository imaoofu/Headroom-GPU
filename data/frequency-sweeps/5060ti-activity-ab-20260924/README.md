# RTX 5060 Ti — activity A/B, re-collected 2026-09-24

**The re-run of `docs/REGISTERED-PREDICTIONS.md` §5, under its 2026-09-24 amendment.** The only change
from 2026-09-23 is the generator trigger: an active run's generator now starts when the sweep
wrapper's HWiNFO log appears, instead of at GPU load ≥ 50%. The amendment was committed in `69ea460`
at 09:06:56, before the first sweep of the day. The design, scorer and thresholds are unchanged.

**Stock Profile 3, `gemm`, 1380–1760 MHz, 13 points ascending. Two warm-ups, then S A A S × 3.
Driver 616.92.** Run by `tools/hwinfo-logging/experiments/Run-Queue-20260924.ps1` with the operator
away. HWiNFO was started by `tools/hwinfo-logging/Start-HwinfoSensors.ps1` with nobody at the PC. The
Claude app's window was minimized for the whole queue: at 09:09 its redraws reached 21% SM and a
preflight refused to start. Stock was verified by memory under load (13801 MHz) and the power limit
(180 W) before the first sweep. All 14 wrapper runs exited 0.

## Registered verdict: NOT SUPPORTED FOR THIS PROXY

```
python analysis/score_activity_ab.py data/frequency-sweeps/5060ti-activity-ab-20260924/experiment data/frequency-sweeps/5060ti-activity-ab-20260924
```

> **Degraded points (> 2.0 pct below the per-target envelope): ACTIVE 0 across 6 runs (0 runs hit),
> SILENT 0 across 6 runs.** VERDICT: NOT SUPPORTED FOR THIS PROXY — the scripted activity does not
> add losses. ALSO: no losses at all.

- **Every active run is valid this time.** Each generator started **22.0–22.4 s before** its first
  measured window, against 0.1–0.2 s *after* it in 3 of 6 runs on 2026-09-23.
- **There were zero degraded points in all 12 scored runs**, active and silent.
- Uptime was 145.9–206.3 min at the scored runs' starts, and temperature 45.4–51.4 °C.

## What it does and does not say

- **The scripted activity does not reproduce the 2026-09-22 losses** on a warm card. The proxy is
  pmon polling, a CPU burst and a screen capture every 5–15 s.
- **It does not rule out the parts of real agent activity the proxy does not imitate.** It gives
  no reason to think the proxy was faithful, either.
- **Not blind.** The 2026-09-23 collection had shown zero losses before this ran, and the
  amendment says so.
- **One chip, one session, one proxy.** 2026-09-22's losses happened on a cold card, under real
  agent activity. This run removed the first and imitated the second, so those two are **still not
  separated**.
- **One practical point from the same morning:** the one process that tripped the idle guard today
  was the Claude desktop app drawing text, at 21% SM for one sample. The wrapper's preflight caught
  it, and nothing was measured under it. It is the same kind of activity as the "real agent
  activity" that the proxy does not imitate.

## Files

- `*_sweep.csv`, `*_sweep.json`, `*_sweep_voltage.csv`: 14 sweeps (2 warm-ups, 12 scored), voltage
  joined by timed window from HWiNFO logs at 0.50 s.
- `experiment/experiment.json`: the runner's record of order, condition, uptime and exit codes.
  Its `event_log` paths point at the collection machine; the copies in `experiment/` are
  byte-identical.
- `experiment/*-events.csv`: the generator's event logs, one per active run.
- `experiment/runner-console.log`: `Run-ActivityAB.ps1`'s console output.
