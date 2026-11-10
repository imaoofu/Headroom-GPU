# power-probe

`sample_power.py` logs NVML's three power readings (`nvmlDeviceGetPowerUsage`, which is what
`nvidia-smi power.draw` reports, and fields 185 average and 186 instant) and the cumulative energy
counter (field 83), at 20 Hz by default, to a CSV that is flushed row by row.

**It observes only.** It never changes clocks, power limits or anything else, and it refuses on a
machine with more than one NVIDIA device rather than guess which one to read.

Written for `docs/REGISTERED-PREDICTIONS.md` §18, after §17 found the energy counter reading a median
7.83% above the sampled power on the RTX 5060 Ti. Checked on that card on 2026-10-06: all four
values update about every 100 ms, the usage value equalled the average field, and one poll of all
four costs about 0.7 ms, about 1.4% of one CPU core at 20 Hz. That load runs beside every sweep of a
session that uses it, the same in every arm.

**§18 (2026-10-07) did not repeat §17's sign:** with this logger running, the sampled power
read a median 2.86% *above* the counter. Polling the counter at 20 Hz is one candidate for the
change, alongside the other differences between the sessions; it is untested. Do not assume this
logger leaves the counter's per-window readings undisturbed.

```
python tools/power-probe/sample_power.py --out power-samples.csv --stop-file stop-sampler
```

`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s19` starts it after preflight and stops it in its
`finally` block. `analysis/score_power_fields.py` joins it to each sweep's timed window.
