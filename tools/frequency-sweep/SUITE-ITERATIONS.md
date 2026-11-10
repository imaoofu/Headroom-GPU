# Suite iteration counts — RTX 5060 Ti, stock

Iteration counts for the extended workload suite. **A count is per card and per configuration**,
so this file is a record of one measurement session and not a set of constants for the project.
The 3070 Ti needs its own; so does this card if its curves change.

Counts target roughly **9 seconds of GPU work** at full boost, which is long enough that the card
reaches a steady clock and launch overhead stops being visible in the throughput figure.

---

## Conditions, recorded because the last set was not

| | |
|---|---|
| Date | 2026-08-28 |
| Card | RTX 5060 Ti 16 GB, driver 610.88 |
| Configuration | **STOCK** — verified by memory reading **13801 MHz under load**, which is §5.7.6's stock reference against the tuned profile's 16301 |
| Power limit | 180 W (default), peak draw 181.7 W |
| SM clock under load | 2655 MHz |
| Precision | fp32, **TF32 off** — the suite's default since it was found that PyTorch enables it for convolution and not for matmul |
| Baseline load | **7%**, encoder 0%, decoder 2% |
| Running | Wallpaper Engine was **not** closed |

**The baseline was 7%, above the protocol's ~5%.** That is acceptable *here* and not in a sweep:
an iteration count is a setup constant, and a few percent of contention moves a 9-second target by
a fraction of a second. It is not acceptable for anything that produces a datapoint. Close
Wallpaper Engine, browsers and media players before collecting.

`nvidia-smi` cannot see an Afterburner offset — `clocks.max.memory` reports the 14001 MHz rating in
either configuration — so the memory clock **under load** is the only check that distinguishes
stock from tuned. Do not skip it.

---

## Counts

| workload | ms/iteration | `--iterations` |
|---|---|---|
| bgemm32 | 3.367 | 2673 |
| bgemm64 | 3.383 | 2661 |
| bgemm128 | 3.649 | 2467 |
| bgemm256 | 5.700 | 1579 |
| bgemm1024 | 21.745 | 414 |
| copy | 3.384 | 2660 |
| reduce | 3.136 | 2870 |
| softmax | 3.461 | 2600 |
| layernorm | 5.634 | 1597 |
| conv | 59.608 | 151 |
| attention | 61.199 | 147 |

`gemm` and `membw` keep their existing defaults — 120 and 1200 — and are not re-set here. Changing
them would break comparability with the 67 sweeps already committed.

---

## Two things this session established about the existing two

**gemm's default is correct and still is.** 120 iterations gives **8.2 s**, against the 7.5–8.4 s
its own docstring records. The harness behaves as documented.

**membw's default was calibrated on the overclocked card.** 1200 iterations gives **11.8 s** at
stock, against the "~9.3 s" the docstring states. The ratio, 1.27, is close to the tuned/stock
memory ratio of 16301/13801 = 1.18, which is what a memory overclock would do to a
bandwidth-bound workload.

Nothing is wrong with the data this produced — a longer run is a safer run, and the count was held
constant within each sweep, which is what the fixed-work property actually requires. But the
docstring states a duration without stating the configuration it was measured in, and that is the
same omission that made 448 GB/s look like a defect in `reduce`. **A duration without its applied
settings is a number nobody can check.**

---

## Retired: `bgemm8` and `bgemm16`

Both were calibrated in this session and then removed from `LADDER_SIZES` the same day. They ran
correctly and are not broken — they measure the wrong thing. At stock they reached **6% and 19% of
the memory bus** with negligible FLOP/s, so both are bound by batched-matmul launch and occupancy
overhead rather than by bandwidth or by arithmetic, and their declared intensities of 1.3 and 2.7
predict nothing about them.

Kept out because collecting them costs sweep time on two points that sit off the axis and then
costs a paragraph in the paper explaining why they are there. The low end is already covered by
workloads that are genuinely on the axis: `copy` at 0, `membw` at 0.167, `reduce` at 0.25 and
`softmax` at 0.625.

**To restore them:** put `8` and `16` back into `LADDER_SIZES` in `gpu_workload.py`. Nothing else
changes — `buildSuiteWorkload` parses the size out of the name, so any `bgemmN` works. Their stock
counts, should they be wanted:

| workload | ms/iteration | `--iterations` |
|---|---|---|
| bgemm8 | 37.884 | 238 |
| bgemm16 | 13.557 | 664 |

## Still open

`layernorm` sits at 47% of the bus, between the bandwidth-bound and compute-bound groups, and has
not been diagnosed either way. It is kept because it is a real operator at a real intensity, not
because anyone knows what bounds it.
