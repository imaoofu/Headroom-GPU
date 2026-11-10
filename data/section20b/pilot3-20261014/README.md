# Section 20b pilot session 3, 2026-10-14: SCOREABLE (pilot data, for sizing only)

`docs/REGISTERED-PREDICTIONS.md` §20b, registered 2026-10-11 (`d8e6019`), pilot index 3, seed 71023.
Run by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20b -Session 3 -ManageChatGpt` at 10:59–12:48
local from `317b5ea`. The attempt log names `3d23a1b`; the §20b code is identical, and the commits
between only add that log line and a fix to the collection kit's memory witness, which §20b does not
use. Launched minimized and unattended. Attempt 7 in `docs/section20b/ATTEMPTS.md`. `core/` is the
controller's output as written (the 144 per-window stop-signal files removed); `session.log` and
`rerun15-inputs.json` are the runner's. **N=1 chip.**

**Pilot sessions size the confirmation stage; they give no verdict.** Nothing here may be cited as a
§20b result before confirmation, and these figures never enter confirmation intervals.

⚠️ **Run knowing confirmation is already unattainable.** GPT Job 90
(`docs/gpt-findings/2026-10-14-section20b-sizing-outlook.md`, recomputed by Claude) showed from pilots 1–2
alone that no pilots 3–4 can bring the four-pilot d_E SD below 1.98 pp, while the registered rule needs
1.42 pp or less for any S up to 32. This session was run for the day-to-day record and so that the
registration can end at its own registered "insufficient precision" outcome after pilot 4.

## Validity

Scored with `python analysis/score_section20b.py data/section20b/pilot3-20261014/core`: **SCOREABLE**,
no problems. 144 of 144 windows, controller and runner exit 0, zero display-driver events, the
watcher stopped cleanly (exit 0, reaped), all eight row-visit background checks clean (no forbidden
processes, no pollers, no visible Claude window), runner cleanup ok (reset 0, store restored,
13801 MHz, 180 W). Preflight: driver 616.92, power limit 180 W, utilisation 0. Return gate: worst cell
0.353% against the 1.5% limit.

## The scorer's session contrasts (percentage points against A)

| | d_E | d_P | d_EP | d_I |
|---|---:|---:|---:|---:|
| counter-average power | −12.781 | +0.090 | −13.218 | −0.526 |
| energy per work unit | −12.710 | +0.039 | −13.249 | −0.578 |
| wall throughput | −0.085 | +0.050 | +0.037 | +0.071 |

Per-cell values, from the same scorer run: d_E ranges −8.05 (copy 1545) to −15.89 (gemm 2010); d_P
−0.56 (gemm 1545) to +0.84 (copy 2317); d_EP −10.16 (copy 1545) to −16.95 (gemm 1545); d_I −4.43
(gemm 1545) to +2.54 (softmax 1545). Cell-level d_I is again far noisier than its session average.

**Across the three pilot days, descriptively:** session d_E was −15.13, −10.29 and −12.78 pp; d_EP
−15.63, −12.89 and −13.22; d_P −0.08, −0.10 and +0.09; d_I −0.43, −2.51 and −0.53. Every day,
field-83 polling lowered the counter's reported power in every cell, with session throughput unchanged
within 0.1 pp. ⛔ *Corrected 2026-10-20: this said "at unchanged throughput (within 0.1 pp), in every cell".
One cell of this session moved more: `copy` at 2010 MHz under field-83 polling, −1.26% (GPT Job 110).* The size of that drop moved by about 5 pp between days, and the power-query bundle moved it by
under a point each time. Three days are three repeated observations of one chip. **It still does not
say which reading is right**: the counter is the card's own telemetry and no external meter was used.
