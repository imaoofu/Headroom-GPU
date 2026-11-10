# Activity A/B test — 2026-09-23

**Stock Profile 3, `gemm`, ascending 1380–1760 MHz, 13 points, 14 sweeps: two warm-ups, then
S A A S × 3.** Driver 616.92, HWiNFO at 0.50 s, operator absent, driving agent silent. Collected by
`tools/hwinfo-logging/experiments/Run-ActivityAB.ps1`, registered in advance in
`docs/REGISTERED-PREDICTIONS.md` §5 and revised before collection. Stock was verified at 13801 MHz
memory under load and 180 W before the first sweep. The runner waited until the machine had been up
30 minutes (boot 08:12:30, first sweep 08:43).

**Question:** on 2026-09-22 three stock replicates lost 8–11% at isolated points. Was it agent
activity, warm-up, or run order? This design separates them.

---

## REGISTERED VERDICT: INCOMPLETE — none is printed, and none is claimed here

```
python analysis/score_activity_ab.py data/frequency-sweeps/5060ti-activity-ab-20260923/experiment data/frequency-sweeps/5060ti-activity-ab-20260923
```

The registered scorer requires every ACTIVE run to prove its generator was running **before the
first measured window**. **Three of six fail that check: 03, 06 and 11.** Every other check passes
in all twelve runs: wrapper exit 0, the full 13-point grid, generator actions all succeeded, no gap
in activity, clean stop on the stop file.

**By how much they fail:** the generator started **0.1–0.2 s after** the first window opened, so one
of 13 windows began before the activity did. In the three runs that pass, it started ~22.5 s early.

**Why:** a design flaw in the runner, not a fault in the card. The generator waits for GPU
utilisation ≥ 50% and then starts. In three runs (02, 07, 10) a reading ≥ 50% arrived ~4 s after
launch, before the sweep's first window; **what produced it is not known.** In the other three the
first ≥ 50% reading was **the sweep's own first measured point**, so the trigger raced the thing it
was meant to precede. There is no pattern by preceding condition: late run 06 follows a SILENT run
and early run 07 follows an ACTIVE one. **The fix for any re-run: start the generator
before launching the sweep, not on a load trigger.**

**The registered rule is not relaxed after the fact.** 0.1 s is small, but deciding after seeing the
data that it "doesn't count" is exactly what registration exists to prevent.

## Descriptive only — NOT the registered verdict: there were no losses at all

Loss is measured against the per-target best of all twelve scored runs, including the three late ones:

| run | condition | worst point | mean |
|---|---|---|---|
| warmup-1 | (warm-up, unscored) | 0.14% | 0.11% |
| warmup-2 | (warm-up, unscored) | 0.13% | 0.11% |
| 01 | silent | 0.13% | 0.11% |
| 02–12 | 5 active, 6 silent | **≤ 0.08%** | ≤ 0.04% |

**Zero degraded points (> 2%) in all twelve runs, active or silent, and none in the warm-ups.** The
worst single point anywhere is 0.14%, against the 8–11% losses of 2026-09-22.

**The descriptive outcome does not depend on how the three late runs are treated.** Excluding them
leaves 3 active runs with 0 losses against 6 silent with 0; including them gives 6 and 6, also 0 and
0. Had the collection been complete, the registered rules would have printed *NOT SUPPORTED FOR
THIS PROXY* plus *no losses at all*. **That sentence is a counterfactual, not a result.**

**What it suggests, and no more:** yesterday's losses did not reappear on a card up for 30+ minutes,
with or without the scripted activity. That points toward the **cold start**, or toward some part of
**real agent activity the script does not imitate**, and away from this proxy. It does not separate
those two, and the registration said in advance that a null here "does not rule out the parts of
real agent activity the proxy does not imitate". One chip, one session.

## Files

- 14 sweeps, each with its own time-joined `_sweep_voltage.csv`.
- `experiment/experiment.json`: the runner's record of order, condition, uptime and exit codes.
  Its `sweep_csv` and `event_log` paths are absolute paths on the collection machine
  (`C:\headroom-bench\...`). The scorer falls back to searching its roots for a **sweep CSV**, but
  **not for an event log**, so on another machine it reports every ACTIVE run as "no generator event
  log". The copies here are byte-identical; point `event_log` at `experiment/` to rescore elsewhere.
- `experiment/*-events.csv`: the activity generator's event logs, one per ACTIVE run.
- `experiment/runner-console.log`: the runner's console output.

All fourteen sweeps are complete stock `gemm` measurements and dataset-grade as such. For
activity-condition comparisons, use the registered verdict above: INCOMPLETE.
