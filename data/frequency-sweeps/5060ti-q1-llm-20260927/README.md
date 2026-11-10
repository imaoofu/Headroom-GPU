# Q1 — does the load-floor rule hold for LLM decode? RTX 5060 Ti, 2026-09-27

<!-- dataset-grade: yes -->

**Registered before collection:** `docs/REGISTERED-PREDICTIONS.md` §13 (commit `90c1c21`), plus an
amendment at 15:10 (`34a0fdb`) made after a refused first launch and before any sweep. **Primary
(decode): HOLDS. Secondary (prefill): HOLDS.** Scorer: `python analysis/score_q1_llm.py`.

**One chip, one session, one model.** Qwen3-8B Q4_K_M at batch 1 on llama-bench `d222767c7`
(`tools/frequency-sweep/llm_workload.py`, commit `0d8ced7`). Energy is board-level only.

## Configuration

- Stock Profile 3: 180 W, memory +0, every curve offset 0. NVML offset 0. Driver 616.92.
- **Verified live** by memory under load (13801 MHz) and the 180 W power limit before the first
  sweep. Reverted and re-verified afterwards.
- HWiNFO at 0.50 s. Each sweep is time-joined to its own log
  (`join_hwinfo_voltage.py --join-by time`); the minimum is **33 samples per point**.
- ChatGPT, Codex and `llama-server` were closed, the operator was away, and the driving agent only
  polled the console log once a minute.
- Order: decode ascending (15:11) → decode descending → prefill ascending → prefill descending
  (ended 16:03). 13 targets, 465–3090 MHz.

## Result

Efficiency is tokens per joule: throughput over windowed board power, the mean of both directions.

| target | decode tok/s | decode tok/J, % of max | prefill tok/J, % of max | reported V |
|---:|---:|---:|---:|---|
| 465 | 22.1 | 62.3% | 57.2% | 0.720 |
| 1125 | 48.7 | 92.4% | 90.7% | 0.720 |
| 1342 | 52.4 | 95.2% | 96.6% | 0.720 |
| **1560** | **60.3** | **100.0%** | **100.0%** | **0.720** |
| 1777 | 69.9 | 94.8% | 91.3% | 0.770–0.780 |
| 2212 | 73.9 | 84.1% | 81.2% | 0.855 |
| 3090 (reaches ~2730) | 76.4 | 61.3% | 57.2% | 1.020 |

- **Decode:** efficiency peaks at **1560 in both directions**. Repeat noise d = **2.14%**.
- **Prefill:** efficiency peaks at 1560 in both directions too. d = **13.42%**, but that comes
  entirely from one point (see below), and the verdict does not depend on d, since the argmax is
  1560 itself.
- **Memory max read 13801 MHz at every point of all four sweeps**, and the enforced limit was 180 W
  throughout. The amendment's 14001 allowance was never needed by the data.

### Descriptive, not scored

- **Decode is NOT flat in core clock on this card.** It gives 22.1 tok/s at 465 against 60.3 at
  1560 (37%), and 76.4 at the top. Maliakel et al. report decode latency within ~1% across 180–2842
  MHz on an RTX PRO 6000 Blackwell. Here, performance falls with f below the floor, which is the
  premise the rule needs, so the rule holds. **That is a difference between two setups, not a
  refutation:**
  - different card, model, framework and batch;
  - this smoke test also showed decode scaling with the memory clock (×1.19 for ×1.18), so decode on
    this card is bound by both clocks, not memory alone.
- **0.720 V at every target from 465 to 1560, in all four sweeps.** This card's data had never shown
  the floor below 1378 MHz before (§13's own descriptive item). The first rise is at 1777.
- The top two targets are unreachable at stock (achieved ~2696–2736), as in every stock sweep. They
  are scored as targets, like the rest.
- **One unexplained point: prefill ascending at 465 MHz.** It is the first point of the first
  prefill sweep, at **585 tok/s against 709** descending: throughput, not power (29.1 W against
  30.8). Temperature was the same (42.3 °C against 42.2). **Cause not identified.** It sets prefill's
  d; without it the largest asc/desc gap is about 4%.

## Refused first launch, kept

`runner-console-attempt1-refused.log`: at 15:06 the stock witness read 14001 MHz, outside the runner's
13801 ± 100, so it refused before any sweep and reverted. 14001 is stock's documented second loaded
memory state. The tolerance was widened to ±400 (`Collect.ps1`'s value), §13's "memory max 13801"
condition was amended to 13801–14001, and the run relaunched at 15:09. The runner as run is
`runner-run-q1.ps1.txt`, and its console is `runner-console-attempt2.log`.

## Limits

- One chip, one session, one 8B model at batch 1, synthetic tokens, one llama.cpp build.
- Board energy only.
- A ~218 MHz grid, so "at 1560" means within half a step of the floor end, 1567–1575 achieved.
- **This extends the rule to one decode workload on one card.** It is not an LLM-wide optimum.
  Since Maliakel et al. found the opposite behaviour on a different setup, the result depends on
  the setup, and it should be written that way.
