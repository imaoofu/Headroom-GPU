# Section 20b pilot session 4, 2026-10-20: SCOREABLE; with it, §20b stops at insufficient precision

`docs/REGISTERED-PREDICTIONS.md` §20b, registered 2026-10-11 (`d8e6019`), pilot index 4, seed 71024.
Run by `tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s20b -Session 4 -ManageChatGpt` at 08:34–10:23
local, launched after the attempt-line commit `248d983` (logged as `0b8e8d4`, its parent; the runner is the
same in both). Since pilot 3 the runner has gained only §22 additions (the `rep` part, a self-copy and
source hashes); the §20b path is unchanged, and the §20b scorer hardened after GPT Job 91 still scores
pilots 1–3 SCOREABLE. Launched minimized and unattended. Attempt 8 in `docs/section20b/ATTEMPTS.md`.
`core/` is the controller's output as written (the 144 per-window stop-signal files removed);
`session.log` and `rerun15-inputs.json` are the runner's. `witnesses/` is new relative to pilots 1–3: the
hardened runner's stock witness, mVolt+ status and the profile store it restored. **N=1 chip.**

Before launch, a Claude desktop update (3.1623) that had downloaded and was waiting to install was applied
first, so the app would not restart itself mid-session. Phone Link was stopped.

**Pilot sessions size the confirmation stage; they give no verdict.** These figures never enter
confirmation intervals, and with this session no confirmation stage follows (below).

## Validity

Scored with `python analysis/score_section20b.py data/section20b/pilot4-20261020/core`: **SCOREABLE**,
no problems. 144 of 144 windows, controller and runner exit 0, zero display-driver events, the watcher
stopped cleanly (exit 0, reaped), all eight row-visit background checks clean (no forbidden processes, no
pollers, no visible Claude window), runner cleanup ok (reset 0, store restored, 13801 MHz, 180 W).
Preflight: driver 616.92, power limit 180 W, utilisation 5%, encoder and decoder 0. Return gate: worst
cell 0.334% against the 1.5% limit.

## The scorer's session contrasts (percentage points against A)

| | d_E | d_P | d_EP | d_I |
|---|---:|---:|---:|---:|
| counter-average power | −10.498 | −0.046 | −11.092 | −0.547 |
| energy per work unit | −10.507 | −0.088 | −11.129 | −0.535 |
| wall throughput | +0.007 | +0.042 | +0.042 | −0.007 |

Per-cell values, from the same scorer run: d_E ranges −5.97 (copy 1545) to −15.55 (gemm 2010); d_P
−0.98 (copy 2010) to +0.50 (softmax 2317); d_EP −6.28 (copy 1545) to −19.34 (gemm 2010); d_I −4.02
(gemm 2010) to +2.90 (softmax 1545).

## Sizing, with four pilots: no confirmation size qualifies

`python analysis/score_section20b.py data/section20b/pilot*/core` prints: *"Pilot: four sessions,
largest contrast SD 2.2710 pp; no S from 8 to 32 meets the 1 pp rule, so the approved cap cannot deliver
the planned precision."* The largest SD is d_E's, over −15.13, −10.29, −12.78 and −10.50 pp (recomputed
by hand: 2.271). At the cap, S = 32, the rule allows an SD of at most 1.422 pp; with 2.271 it gives a
half-width of 1.597 pp against the 1 pp limit. GPT Job 90 had already proved from pilots 1–2 alone that no
pilots 3–4 could get below 1.98 pp.

**So §20b stops here, as registered: insufficient precision, and no verdict.** No confirmation session is
run. Nothing in the four pilots may be cited as a §20b result.

**Across the four pilot days, descriptively:** session d_E was −15.13, −10.29, −12.78 and −10.50 pp; d_EP
−15.63, −12.89, −13.22 and −11.09; d_P −0.08, −0.10, +0.09 and −0.05; d_I −0.43, −2.51, −0.53 and −0.55.
Every day, field-83 polling lowered the counter's reported power at unchanged throughput (within 0.1 pp),
and the power-query bundle moved it by under a point. The size of the drop moved by about 5 pp between
days. Four days are four repeated observations of one chip. **It does not say which reading is right**:
the counter is the card's own telemetry and no external meter was used.
