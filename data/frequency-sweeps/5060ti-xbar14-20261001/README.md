# RTX 5060 Ti — §14, setting the crossbar clock directly, 2026-10-01

`docs/REGISTERED-PREDICTIONS.md` §14, registered `ba59500`, amended after clocks-only calibration in
`837eb56`, with provenance notes `292a712` / `d765902` written before any treatment sweep. The XBAR
clock offset was set through mVolt+ v0.47.3 (SHA-256 `2ab951d9…abd6a25`); no other mVolt+ control was
used. Collected unattended 09:17–09:46 by `tools/xbar/Invoke-Xbar14Session.ps1`, step 2 of
`tools/hwinfo-logging/experiments/Run-Chain-20261001.ps1`. Driver 616.92. **0 display-driver events.**

## Verdicts: NOT SCOREABLE as registered; thresholds met only in a post hoc sensitivity analysis

```
python analysis/score_xbar14.py data/frequency-sweeps/5060ti-xbar14-20261001 --memory-rule section13
python analysis/score_xbar14.py data/frequency-sweeps/5060ti-xbar14-20261001 --memory-rule literal
```

Under §13's memory rule, chosen after the data were seen:

| test | result |
|---|---|
| **S**, XBAR lowered on stock to curve 3's level | ratios 0.952 / 0.890 / 0.875 at 1560 / 1710 / 1867 against §12's 0.924 / 0.886 / 0.863: **SUFFICIENT, FULL** |
| S-gemm control | +0.59% (limit ±2%) |
| **C**, XBAR raised at a 1402 MHz core | 1.068: **LIFTS** |
| **N**, XBAR raised on curve 3 | 1.001 and 0.999 of stock, recovery 1.014 and 0.995: **LIFTS** |

**As registered, S, C and N are all NOT SCOREABLE**: §14's "exactly 13801" fails at 13 of 25
points, references included, each on a single first-in-window sample. The table above uses §13's
rule (each instrument's maximum within 13801–14001) and is a **post hoc sensitivity analysis**. GPT
Job 40 audited it (`docs/gpt-findings/2026-10-01-xbar14-result-adversarial-audit.md`): every number
reproduces; it does **not** support "XBAR alone" or reverse the 2026-09-18 retraction. Also in §14's
result: VID +2 codes at S-1560 **and at the S-gemm control**, no reset between consecutive arms
(including −475 → +150 into C), SYS unmeasured during collection.

## Files

| path | what |
|---|---|
| `*_xbar14-<arm>_sweep.csv / .json` | 14 sweeps, 25 points, as the sweep tool wrote them |
| `*_sweep_voltage.csv` | `tools/frequency-sweep/join_hwinfo_voltage.py`, joined by time; `crossbarMeasured` is the manipulation check |
| `hwinfo-memory-in-window.csv` | HWiNFO's NVIDIA memory clock (raw MHz; ×8 = effective) and nvidia-smi's, min and max inside each benchmark window. The PC also has an AMD iGPU; its columns share names, and the NVIDIA block is the one carrying "GPU Crossbar Clock" |
| `session-logs/` | the session log, every mVolt+ `--status` and set output, the calibration file used, the end-of-session reset |
| `refused-launches/` | the two launches that refused before any treatment sweep (09:04, store hash; 09:10, memory check) |
| `chain-logs/` | the chain's own logs: the first run (dry run passed, step 2 refused), the second (refused), the third (completed) |
| `dryrun/` | §14 with every offset forced to 0, quick (first target per bracket), 08:39–09:04. Pipeline check only, not scored |

Raw HWiNFO logs (0.50 s) are gitignored, in `data/HWiNFO-Data/5060ti-xbar14-20261001/`.

## The dry run was contaminated and this session was not

Per-window medians from HWiNFO: this session presented **4–7 frames per second with 1–7% GPU bus
load**; the dry run, 35 minutes earlier, **156–233 fps with 17–49% bus load**, from a desktop source
nothing here identifies. The dry run's stock `membw` at 1402 MHz is **308.2 GB/s against 339.6**
here, with the same core, memory and crossbar clocks. §12's raw logs (2026-09-26, gitignored) carry the
same load, so its absolute GB/s are depressed as well.

**Dataset grade:** the 25 points of this session, n = 1 card, one arm per target. The dry run is a
pipeline check under contamination and must not be pooled with it.
