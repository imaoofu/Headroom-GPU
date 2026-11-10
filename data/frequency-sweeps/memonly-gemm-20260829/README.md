# Memory-only `gemm`, same session — and the retraction it forces, 2026-08-29

One sweep, 13 of 13 points, on the 1237–3090 grid. **Memory +2500 only, core V/F curve at default**,
both verified by measurement minutes before the run: memory 16301 MHz under load against stock's
13801, peak SM 2655 MHz where a flat core curve reaches ~2977.

Collected roughly ninety minutes after `../stock-suite-20260829/20260829-145752_5060ti-stock-gemm-1237grid`,
in the same session on the same machine, with one knob changed between them.

## It retracts this morning's result

`CLAUDE.md` carried a standing open item: *"`gemm` gets nothing measurable from the memory
overclock, ±1%" cannot be checked clean.* This morning's stock sweep made it checkable for the first
time, against the clean memory-only runs of 2026-08-22, and gave **−1.50%, negative at all 13
targets**. That was written up as the ±1% claim failing.

**It does not fail. Measured in one session the effect is −0.05%.**

| comparison | mean | sign |
|---|---|---|
| stock vs memory-only, **same session** | **−0.05%** | 7 of 13 negative — random |
| stock vs memory-only, **7 days apart** | −1.50% | 13 of 13 negative |

And the direct measurement of what caused the difference:

| | |
|---|---|
| **today's memory-only vs 2026-08-22 memory-only** — *identical configuration* | **+1.47%** |

**That is cross-session drift, and it accounts for the whole of the −1.50%.** The same card in the
same configuration reads 1.47% faster today than it did seven days ago, so a stock run from today
compared against a memory-only run from last week inherits that offset entire. Subtract it and
−1.50% becomes approximately −0.05%, which is what the same-session comparison measures directly.

**The original claim stands: `gemm` gets nothing measurable from the memory overclock, ±1%.** It is
now tested rather than assumed, and the open item is closed in the direction it was originally
written.

## What the failed version got right, and what it did not

The mechanism checks were sound and survive: achieved clocks differ by −2.1 MHz and power by
+0.3 W, so nothing about this is a power-budget or clock effect. Those were the right things to
check. They were checked on a difference that was not real.

The error was structural rather than arithmetic. A seven-day gap was noted as a caveat and then
reasoned around — the argument being that a consistent sign across all 13 points looked systematic
rather than noisy. **A consistent sign is exactly what a constant session offset produces.** Sign
consistency distinguishes a real effect from *random* noise and says nothing about a *systematic*
one, which is the kind of noise a session gap creates.

## The number worth keeping: same-config cross-session drift is ~1.47% on `gemm`

This project has cited ~0.76% as run-to-run spread on `gemm`. That figure is *within* a session.
**Across sessions, on an identical configuration, this measures 1.47%** — roughly double.

Any comparison in this repository drawn from runs on different days carries an offset of that order.
That is a limitation worth stating in §6 and a bar that several existing comparisons sit close to.
