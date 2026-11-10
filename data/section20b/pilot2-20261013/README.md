# Section 20b pilot session 2, 2026-10-13: SCOREABLE (pilot data, for sizing only)

`docs/REGISTERED-PREDICTIONS.md` §20b, registered 2026-10-11 (`d8e6019`), pilot index 2, seed 71022.
Run by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20b -Session 2 -ManageChatGpt` at 08:41–10:29
local from `c72630b` (the §20b code is identical to `3bbdfca`, which the attempt log names; `c72630b`
only adds that log line), launched minimized and unattended. Attempt 6 in
`docs/section20b/ATTEMPTS.md`. `core/` is the controller's output as written (the 144 per-window
stop-signal files removed); `session.log` and `rerun15-inputs.json` are the runner's. **N=1 chip.**

**Pilot sessions size the confirmation stage; they give no verdict.** Nothing here may be cited as a
§20b result before confirmation, and these figures never enter confirmation intervals.

## Validity

Scored with `python analysis/score_section20b.py data/section20b/pilot2-20261013/core`: **SCOREABLE**,
no problems. 144 of 144 windows, controller and runner exit 0, zero display-driver events, the
watcher stopped cleanly (exit 0, reaped), all eight row-visit background checks clean (no forbidden
processes, no pollers, no visible Claude window), runner cleanup ok (reset 0, store restored,
13801 MHz, 180 W). Preflight: driver 616.92, power limit 180 W, utilisation 0. Return gate: worst cell
0.211% against the 1.5% limit.

## The scorer's session contrasts (percentage points against A)

| | d_E | d_P | d_EP | d_I |
|---|---:|---:|---:|---:|
| counter-average power | −10.286 | −0.098 | −12.891 | −2.507 |
| energy per work unit | −10.286 | −0.092 | −12.895 | −2.517 |
| wall throughput | −0.001 | −0.006 | +0.004 | +0.011 |

Per-cell values, from the same scorer run: d_E ranges −6.32 (gemm 2010) to −12.30 (copy 1545);
d_P −0.77 (softmax 1545) to +0.82 (gemm 1545); d_EP −8.92 (copy 1545) to −18.91 (gemm 2010); d_I
−12.33 (gemm 2010) to +3.18 (copy 1545). As in pilot 1, cell-level d_I is far noisier than its
session average.

**Against pilot 1, descriptively:** the direction repeats (field 83 polling lowers the counter's
reported energy at unchanged throughput, in every cell; the power-query bundle moves it by under a
point), but the size does not: session d_E was −15.13 pp on 2026-10-12 and −10.29 pp here, and d_I
−0.43 against −2.51. That between-session spread is what the pilot exists to measure; two sessions
cannot estimate it, so no sizing is drawn until all four pilots are in. **It still does not say which
reading is right**: the counter is the card's own telemetry and no external meter was used.
