# RTX 5060 Ti — §10, the negative control repeated in one session, 2026-09-25: NOT SCOREABLE

`docs/REGISTERED-PREDICTIONS.md` §10 was registered in `1c4e10d` and its slot witness amended in
`a7bcd44`, both before collection. The scorer `analysis/score_control10.py` was committed in
`b2d83b9` before its data was read. Three twelve-workload suites, **P5 → P2 → P5**, ran 11:52–14:45
with the operator away, driven by
`tools/hwinfo-logging/experiments/Run-ControlRepeat-20260925.ps1`.

## Registered verdict: NOT SCOREABLE — the P5 bracket did not return

```
python analysis/score_control10.py data/frequency-sweeps/5060ti-control10-20260925
```

| leg | median optimum | per-workload optima |
|---|---|---|
| P5, opening (`p5a`) | **1545 MHz** | copy 1852, reduce 1852, bgemm32 1702, bgemm128 1702, gemm 1395; the other seven 1545 |
| P2, the control (`p2`) | **1545 MHz** | copy 1702, reduce 2010, layernorm 1702, gemm 1395; the other eight 1545 |
| P5, closing (`p5b`) | **1545 MHz** | copy 1545, reduce 1852, bgemm128 1702; the other nine 1545 |

**The P5 return fails:** 11 of 12 workloads exceed the registered 1.5%, the worst by **7.57%**. So
the control cannot be scored, whatever its median shows. **That is not a failure of the control**
(§10: *"Otherwise NOT SCOREABLE, which is not a failure"*). Reported beside it, as §10 requires:
**P2's optimum differs from both P5 optima in 4 of 12 workloads** (`bgemm128`, `copy`,
`layernorm`, `reduce`).

## Why the bracket failed: the closing suite ran uniformly slower

| | p5b against p5a, mean over 12 workloads |
|---|---|
| 1237 MHz | **−8.5%** |
| 1545 MHz | −7.0% |
| 2010 MHz | −6.2% |
| 2475 MHz | −6.8% |
| 3090 MHz | **−4.5%** |

- **11 of 12 workloads lost 5.5–7.4%.** `copy`, the first sweep of the closing suite, lost 1.5%.
- **The loss is largest at low clocks.** This is the desktop-contamination signature CLAUDE.md
  records (5.4.4, and the 9.4% level shift of 2026-09-18).
- **The idle baseline before each p5b sweep rose to 2.6–6.0%**, against about 0–3% before p5a and
  P2 sweeps.
- **P2 does not show it.** Against p5a, P2 is within ±0.1% at every target from 1237 to 2010 MHz.
  Its differences above 2010 (−2.5% to +2.0%) are the curves genuinely differing there.
- The closing slot witness read **152.7 W** at locked 2475 MHz, against **149.4 W** for the opening
  one. It is the same slot (P2 reads ~176 W), and the witness passed.

**Cause: not established.** Process start times show two batches of Codex (ChatGPT desktop) tool
processes starting at **13:43 and 13:47**: `node_repl`, `node`, and an app-tools MCP server, all
children of `codex.exe`. The closing suite's first sweep started at 13:47:32. Codex shares this
working tree. **Its only files written today predate the run** (10:34 and 11:48), so what it did
after 13:43 is not recorded, and nothing here shows it used the GPU. The coincidence is recorded,
**not** attributed. The Claude desktop app was also open.

**2026-10-03:** HWiNFO's "Framerate Presented" / "GPU Bus Load" signature is in **142 of 156**
closing-P5 windows, against 35 (opening P5) and 29 (P2). On 2026-10-03 an ABA test showed the
**Claude app's visible window** produces that signature and a 6–9% `membw` loss, gone when the
window is minimized (`../5060ti-deskload-20261003/`). The Claude window is therefore the likeliest
cause here; the screen was not recorded, so it is not shown.

## What the data can and cannot support

- **No registered verdict on the 5060 Ti control.** 4b (3070 Ti) stays FAIL. The original 5060 Ti
  control (`repair-suite-p2-20260909`) stands as it was, single and unbracketed.
- **Descriptive only:** in this session P2's median equals both P5 medians. Against the opening
  suite, which the contamination did not reach, P2 holds the median, and 4 of 12 workloads move.
  That is the same shape as 2026-09-09. It is n = 1 chip, with one uncontaminated comparator, and
  it is not a verdict.
- **The p5b suite's throughput is not usable** for anything that compares its level with other
  runs. Its voltage extracts are: contamination moves throughput, not voltage (CLAUDE.md).

## The run

- **36 of 36 sweeps**, 13 of 13 points each, 1236–3090 MHz ascending, driver **616.92**.
- The iteration counts are `repair-suite-p2-20260909`'s.
- The Afterburner store was checked section for section against
  `data/afterburner-profiles/5060ti-profiles-20260922-rungB/` before collection: all five slots are
  identical.
- Every slot was witnessed before its suite: power limit **200 W** and memory **16301 MHz**; locked
  2475 MHz `gemm` medians of **149.4 W** (P5), **175.9 W** (P2) and **152.7 W** (P5).
- **One busy-GPU preflight refusal**, at the first P2 sweep (12:49:56), right after the witness's
  own `gemm` run. It was retried a minute later. The refused attempt's output folder is empty and not
  imported.
- HWiNFO was started unattended by `Start-HwinfoSensors.ps1`, its first live use.
- Voltage extracts are joined by timed window, 13 of 13 points, at least **14** samples per point.
  The raw logs are in `data/HWiNFO-Data/5060ti-control10-20260925/` (gitignored).
- `queue-runner.log` is the runner's console capture. Its repeated `Add-Content` errors are from a
  Git Bash `tail -f` that locked the log file for the first 30 minutes. The run itself was
  unaffected, and every line was also written to this console capture.
