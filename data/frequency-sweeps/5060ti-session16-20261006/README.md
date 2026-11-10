# RTX 5060 Ti: section 16, the upper-curve control clean and the floor manipulation registered, 2026-10-06

`docs/REGISTERED-PREDICTIONS.md` §16, registered `6e91bcb` and amended before collection (`bb33f84`,
witness timing; `afae3dc`/`60a2e59`, the killed first attempt). Collected unattended 11:25–15:31 by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts s16` (copy here as
`runner-Invoke-Rerun15Session.ps1.txt`), launched as a detached process. Driver 616.92. **48 sweeps,
every one dataset-grade: 0 display-driver events, 0 desktop-load exits, 0 retries.** Operator away;
Claude minimized; ChatGPT, Codex, Opera, Discord and Obsidian closed.

**This is the second collection.** The first (`C:\headroom-bench\rerun15\20261006-092420-s16`,
09:24) was killed at 11:22 by the agent's two-hour limit on a background command, during P4's last
sweep. None of its sweep data was read or scored, and none of it is here (Amendment 2).

Order: **split (P5) → full tune (P4) → repair (P2) → split (P5)**, four twelve-workload suites, grid
1237–3090 MHz in 13 points ascending, §10's iteration counts. All three slots carry memory +2500 and
200 W, so every contrast here is memory-matched.

## Verdicts

```
python analysis/score_session16.py data/frequency-sweeps/5060ti-session16-20261006
```

| prediction | result | verdict |
|---|---|---|
| gate: equal P5 medians; every workload's P5 return ≤ 1.5% | 1545 and 1545 MHz; worst workload **0.725%** | passes |
| **C** (control): P2 median equals the P5 median | 1545 = 1545 MHz | **HOLDS** |
| **M1** (manipulation, primary): P4 median is 2010 MHz | **2010 MHz** | **HOLDS** |
| **M2** (manipulation, secondary): ≥ 9 of 12 P4 optima strictly above P5a's | **10 of 12** | **HOLDS** |

Cross-check: `analysis/score_control10.py`, run on the 36 P5/P2/P5 sweeps alone, gives the same
optima and **PASS**.

**Reported, always:**
- **P2 optima differing from both P5 optima: 2 of 12** (`bgemm32` 1395, `gemm` 1545), the
  registered statistic. **P2 against the opening P5 suite alone: 4 of 12** (`reduce`, `layernorm`,
  `bgemm32`, `gemm`).
- **The two P5 suites themselves differ at 5 of 12** (`bgemm128`, `copy`, `layernorm`, `reduce`,
  `softmax`). That is the same-session repeat baseline. The like-for-like comparison is P2's 4
  against the opening suite with this 5: **no more than the repeat, not clearly fewer.**
  *Corrected the same evening: this first compared P2's 2 of 12 (different from BOTH P5 suites) against the P5 pair's 5 of 12, two different statistics. Like for like, P2 against the opening P5 suite changes 4 of 12.*
- **P4 against P5a: 10 above, 1 equal (`bgemm64`, 1545), 1 below (`copy`, 1545 against 1702).**
  Per-workload shifts: +465 at seven workloads, +458 `reduce`, +457 `gemm`, +307 `bgemm32`, 0
  `bgemm64`, −157 `copy`.
- `gemm` at a locked 2475 MHz, first load after 90 s idle: **P5 148.9 / P4 149.5 / P2 172.2 /
  P5 149.1 W** (P5 ≤ 163 and P2 ≥ 165 gated; P4 recorded only).

Evidence gates: memory under load 16301 MHz at every arm's witness, back to 13801 on stock at the
end; desktop-load screen **0 of 624 windows flagged, 4.0–8.1 fps** (48 sweeps × 13; corrected from 576 after GPT Job 56: a byte-order mark hid each file's first line from the count); every profile store restored
byte for byte from `curve3` with Afterburner closed and mVolt+ offsets and voltage demands all 0.

## What it shows, and what it does not

- **The upper-curve control holds clean.** §10's pass on 2026-10-01 ran under a desktop load in
  all 468 windows; this one ran quiet, inside a same-session P5 bracket, and P2 changed no more
  workloads against the opening P5 suite (4) than the P5 repeat did (5).
- **The floor manipulation is now a registered result on this card.** The ABBA run that found it
  (2026-09-08) had been registered for a different prediction. The median moved +465 MHz to the
  predicted 2010, as in ABBA. **Not "all twelve moved up" this time:** ABBA had 12 of 12 upward;
  here `bgemm64` stayed and `copy` moved down.
- **The floor ends where the decoded curves say.** In the voltage extracts the last target at
  exactly 0.720 V is 1545 MHz for P5 and P2 and 2010 MHz for P4, in **10 / 11 / 11 / 12 of 12**
  workloads (opening P5 / P4 / P2 / closing P5). Requiring also that no earlier target read above
  0.720 V gives **10 / 10 / 10 / 11** (`copy` starts at 0.725 V on P4 and P2, then returns to
  0.720). P4's decoded floor end is 2002 MHz. *Corrected after GPT Job 56: this said "each in 10 of
  12" without naming the rule or the suite.*
- **Not region-isolated.** P4 differs from P5 by about +465 MHz below 840 mV (465 or 472 MHz at
  the decoded points that are not offset boundaries; +472 at 720 mV) and by about −98 MHz at
  875–925 mV (−98 at 875 mV, up to −105 between). *The flat "+465" was a simplification, found by
  GPT Job 56.* The control (P2, edited above the floor by up to 570 MHz) is what bounds that.
- Today's P4 carries the 3030 MHz plateau, so it is not the ABBA-era P4.
- One chip, one session, one suite per arm; the twelve workloads are repeated outcomes on it.
  Desktop framerate is a screen, not proof of an idle machine.

## Files

| file | what |
|---|---|
| `*_sweep.csv`, `*_sweep.json` | the 48 sweeps; each point carries `memory_clock_samples_mhz` |
| `*_sweep_voltage.csv` | `tools/frequency-sweep/join_hwinfo_voltage.py`, joined by time; 624 points, none empty, at least 13 samples each |
| `rerun15-inputs.json` | the scorer's evidence map, paths relative to here |
| `wrapper/` | each sweep's wrapper result, desktop-load check and GPU-users-at-start record |
| `witnesses/` | per arm: the live profile store copied before the arm, mVolt+ status, witness record |
| `session.log` | the runner's log |
| raw HWiNFO logs | gitignored, `data/HWiNFO-Data/5060ti-session16-20261006/` |

The 90-minute P5 soak that followed (worklist 4g) is in `data/stability-runs/`; it is not part of §16.
