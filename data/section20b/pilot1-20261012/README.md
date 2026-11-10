# Section 20b pilot session 1, 2026-10-12: SCOREABLE (pilot data, for sizing only)

`docs/REGISTERED-PREDICTIONS.md` §20b, registered 2026-10-11 (`d8e6019`), pilot index 1, seed 71021.
Run by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20b -Session 1 -ManageChatGpt` at 17:20–19:09
local from `72fb0cf` (the §20b code is identical to `025588e`, which the attempt log names; the commits
between are website-only), launched minimized and unattended. Attempt 5 in
`docs/section20b/ATTEMPTS.md`. `core/` is the controller's output as written (stop-signal files
removed); `session.log` and `rerun15-inputs.json` are the runner's. **N=1 chip.**

**Pilot sessions size the confirmation stage; they give no verdict.** Nothing here may be cited as a
§20b result before confirmation, and these figures never enter confirmation intervals.

## Validity

Scored with `python analysis/score_section20b.py data/section20b/pilot1-20261012/core`: **SCOREABLE**,
no problems. 144 of 144 windows, controller and runner exit 0, zero display-driver events, the
watcher stopped cleanly, all eight row-visit background checks clean, runner cleanup ok (reset 0,
store restored, 13801 MHz, 180 W). Return gate: worst cell 0.255% against the 1.5% limit. Preceded the
same day by a 10-minute stock full-load check after the GPU power cable was reseated (0 driver events,
8500 of 8500 iterations; `C:\headroom-bench\cable-check-20261012`, not data).

## The scorer's session contrasts (percentage points against A)

| | d_E | d_P | d_EP | d_I |
|---|---:|---:|---:|---:|
| counter-average power | −15.129 | −0.076 | −15.633 | −0.428 |
| energy per work unit | −15.135 | −0.068 | −15.642 | −0.439 |
| wall throughput | +0.006 | −0.008 | +0.009 | +0.011 |

Per-cell values, from the same scorer run: d_E ranges −7.20 (softmax 2010) to −19.76 (gemm 1545);
d_P −0.53 to +0.61; d_EP −8.98 (copy 1545) to −18.77 (gemm 1545); d_I −7.85 (softmax 2010) to +6.93
(copy 1545). Cell-level d_I is far noisier than its session average; one session cannot say how much.

**What one session shows, descriptively:** with field 83 polled (E, EP), the energy counter reported
about 15% less energy for the same work at unchanged throughput, in every cell; the power-query bundle
(P) moved it by less than a percentage point. That repeats the qualification pattern of 2026-10-09 at
full scale. **It does not say which reading is right**: the counter is the card's own telemetry and no
external meter was used. It is also one day: the pilot's purpose is the between-session spread, which
needs all four sessions.
