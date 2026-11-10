# Dense grid — resolving the 1537 MHz clustering, 2026-08-29

Five sweeps at **13 points across 1237–1852 MHz, ~51 MHz spacing** — three times finer than the
standard grid's ~155 MHz. All five 13 of 13, locks held, clocks reset.

## Why it was run

The standard-grid suite put **nine of twelve** workload optima at exactly 1537 MHz. At 155 MHz
spacing that reading is ambiguous: it is equally consistent with *every workload wanting 1537* and
with *workloads wanting anything between 1460 and 1620*. The two support opposite claims, and the
data could not distinguish them.

Five workloads spanning declared arithmetic intensity 0 to 1365, chosen to include both coarse-grid
outliers — `reduce` (optimum 1845) and `gemm` (1389).

## Configuration, verified rather than declared

| | |
|---|---|
| Card | Zotac RTX 5060 Ti Twin Edge OC, driver 610.88 |
| Configuration | **STOCK**, checked immediately before the run |
| Memory clock under load | **13801 MHz** — stock, against 16301 with the +2500 offset |
| Peak SM under load | **2632 MHz** — no core curve, against ~2977 with the flat curve |
| Power limit | 180 W default |
| Baseline | encoder 0%, decoder 0% |

Both knobs were checked because a run earlier the same day was killed after the memory offset was
applied to the machine while a sweep labelled "stock" was in flight. Nothing was written and no data
was lost, but the label would have been wrong, and a declared configuration that nothing verifies is
the failure this project keeps meeting.

## Result 1 — the argmax positions WERE a grid artifact

| workload | coarse-grid optimum | dense optimum |
|---|---|---|
| `gemm` | 1389 MHz | **1485 MHz** |
| `bgemm1024` | 1537 | 1537 |
| `copy` | 1537 | **1590** |
| `bgemm64` | 1537 | **1642** |
| `reduce` | 1845 | 1845 |

Five workloads, five distinct optima, where the coarse grid read three of them as identical. The
optima are not clustered on one point.

## Result 2 — and it does not matter, which is the finding

The five sweeps share **nine** achieved frequencies, so a fixed-versus-per-workload comparison is
computable here (unlike the standard-grid suite, where clamping above 2310 MHz left only five shared
points — see `../stock-suite-20260829/README.md`).

Efficiency given up by running every workload at one frequency, against each workload's own optimum:

| fixed frequency | mean regret | worst |
|---|---|---|
| **1537 MHz** | **1.94%** | **3.99%** |
| 1485 | 2.23% | 4.67% |
| 1590 | 2.42% | 3.75% |
| 1642 | 2.82% | 7.13% |
| 1695 | 3.75% | 6.82% |

Per workload at 1537 MHz: `bgemm1024` 0.00%, `bgemm64` 0.25%, `copy` 2.35%, `reduce` 3.10%,
`gemm` 3.99%.

**The optima differ and the difference is worth under 2% on average.** The efficiency curves are
flat near their peaks, so the argmax wanders with resolution while the quantity anyone cares about
barely moves. Both readings of the coarse data were half right: the *positions* were an artifact,
the *practical* clustering was not.

**This is §5.2's null reproduced on consumer hardware.** On the V100, a fixed 952 MHz costs 0.837%
mean regret across 33 workloads and a probe model cannot beat it. Here a fixed 1537 MHz costs 1.94%
across five workloads on a card this project measured itself, at a resolution fine enough that the
result is not a grid artifact. Unconstrained, one frequency serves nearly everything on consumer
silicon too.

**This says nothing about the constrained case**, which is where §5.6.1 and §5.6.2 found workload
identity worth 83% of the available gain. Unconstrained flatness is exactly the condition under
which a performance floor makes the difference matter — the floor cuts off the flat region from
below, and which workload you have decides where the cut lands.

## Caveats

- **Five workloads, n = 1 each.** Between-run spread on `gemm` in this project is ~0.76%, so the
  0.25% and 0.00% entries are inside noise and the 3.99% is not.
- **The grid spans 1237–1852 MHz only.** Every optimum found lies inside it, so no optimum is
  clipped, but the regret figures are computed over that window rather than the full range.
- Standard-grid and dense-grid runs are separated by about an hour, same session, same verified
  configuration.
