# RTX 3070 Ti - first non-Blackwell chip, and a vendor BIOS A/B - 2026-08-25

Gigabyte RTX 3070 Ti GAMING OC rev2.0, a machine built to sell and owned outright at the time of collection — this README said "a customer's machine" until 2026-09-13, which is what recorded a non-existent blocker on tuning it — collected with the kit and returned
to the state it was found in. **This is the first chip in the project that is not the RTX 5060 Ti**,
and the first controlled comparison of two configurations on identical silicon.

## The card

Ampere, 8 GB GDDR6X, 116-120 discrete clock bins from 405 MHz. For contrast the 5060 Ti is
Blackwell, 16 GB GDDR7, 389 bins from 180 MHz - a much finer ladder over a much wider range.

The card carries a dual-BIOS switch and was **found in the SILENT position**, which is not the
factory default. Both positions were measured, then it was returned to SILENT.

| | SILENT (as found) | OC |
|---|---|---|
| VBIOS | `94.04.5a.00.91` | `94.05.5a.00.bd` |
| `clocks.max.graphics` | 2115 MHz | 2190 MHz |
| top supported bin | 2130 MHz | 2190 MHz |
| power limit / default / max | 290 / 290 / 320 W | 310 / 310 / 350 W |

The OC BIOS raises the clock ceiling **and** the power envelope together. Vendor spec claims
1830 MHz boost against ~1785 silent and 1770 reference; not verified here.

## What is in this directory

    silent-asfound/       gemm + membw, 13-point grid 855-2130 MHz
    oc-bios/              gemm + membw, 13-point grid 885-2190 MHz
    oc-bios-membw-r2/     a second OC membw sweep - see "the run labelled FAILED" below
    matched-grid/         OC gemm forced onto the silent band, to share targets
    logs/                 full console transcripts of every run

All five sweeps are **verified-quiet**: encoder and decoder read 0% at preflight, baseline GPU
utilisation 0-1.2%.

## The run labelled FAILED is not a failed run

`oc-bios-membw-r2` was collected in a folder the operator marked `--FAILED RUN--`. What actually
happened is in `logs/run-20260825-132407.log`: the `gemm` sweep **refused to start** because
Microsoft Edge was using 11% of the GPU, and the guard named the process. By the time the `membw`
sweep began the browser had gone idle and it ran at 0% baseline, completing all 13 points.

So the folder contains one valid `membw` sweep, and it is a useful one - it makes the OC BIOS
`membw` measurement n=2. The two agree to **+0.30% mean, +0.24% to +0.39%** across all 13 shared
targets, which is far tighter than the 5060 Ti manages on the same workload.

**The guard did exactly what it exists for.** Nothing here needed diagnosing.

## The grids do not line up, and the matched-grid run only half fixes it

Each sweep builds its grid from 40% of that BIOS's own maximum, so:

    silent   855  960 1065 1170 1275 1380 1485 1605 1710 1815 1920 2025 2130
    oc       885  990 1095 1215 1320 1425 1545 1650 1755 1860 1965 2085 2190

**Zero shared targets.** The `matched-grid` run was added to fix that by forcing the OC BIOS onto
the silent band, but it was given a ceiling of 2115 MHz - the `clocks.max.graphics` reading -
rather than 2130, the silent sweep's actual top target. It therefore produced:

    matched  855  960 1065 1170 1275 1380 1485 1590 1695 1800 1905 2010 2115

**Seven of thirteen targets match** (855-1485 MHz), and the upper half does not. Every
matched-frequency figure below is over those seven points. A ceiling of 2130 would have matched
all thirteen.

## Findings

### At matched clocks the OC BIOS is almost pure voltage

Over the seven shared `gemm` targets, with achieved clocks identical to 0.0 MHz at every point and
memory clock identical:

| | throughput | power |
|---|---|---|
| OC vs silent, mean | **-0.00%** | **+23.1%** |
| range | -0.15% to +0.07% | +19.4% to +27.5% |

Identical work, a quarter more power. **The temperature difference runs against this reading, not
with it:** the silent run was the *hotter* of the two at five of the seven points (55.8-58.8 C
against 51.8-54.0 C), and hotter silicon leaks more, so a thermal account would predict silent
drawing more power. It draws less.

No voltage telemetry was available on that machine, so the mechanism is inferred rather than
measured. Power at fixed frequency and fixed work scales with V^2, and +23% implies roughly 11%
more voltage.

### What the OC BIOS buys

| | silent | OC | difference |
|---|---|---|---|
| peak `gemm` | 16.96 TFLOP/s @ 273.1 W | 17.05 TFLOP/s @ 289.1 W | **+0.56%** throughput, **+5.9%** power |
| peak `membw` | 550.9 GB/s | 551.1 GB/s | **+0.0%** |
| band-mean `membw` power | 149.7 W | 201-203 W | **+35%** |
| best `gemm` efficiency | 77.51 GFLOP/J @ 1380 MHz | 64.47 GFLOP/J @ 1425 MHz | **-16.8%** |

A factory "OC" BIOS on this card costs 23% more power at matched frequency and 35% more on a
bandwidth-bound workload, and returns half a percent of peak compute and nothing at all on
bandwidth.

### Neither BIOS reaches its clock ceiling

Both peak at about **1765 MHz achieved** - silent 1765.0, OC 1772.0 - against ceilings of 2130 and
2190 MHz. Above roughly 1710 MHz the commanded clock stops being reached and throughput flattens.
The card is power-limited, not clock-limited, at the top of its range, which is the same pattern
the 5060 Ti shows and an independent instance of it on a different architecture.

### The efficiency headroom is larger on the quieter BIOS

    silent   optimum 1380 MHz: 21.7% slower than peak for 37.3% less power
    oc       optimum 1425 MHz: 19.6% slower than peak for 26.4% less power

Both are the project's central claim reproduced on a second chip. The silent BIOS is the better
starting point for it, which is the opposite of what a buyer would assume from the product name.

## Limits

  - **n=1 per BIOS on `gemm`.** The `membw` side is n=2 for the OC BIOS and n=1 for silent. Today
    established on the 5060 Ti that a single sweep can misreport a band mean by a full percentage
    point; the +23% matched-clock power gap is far outside that, the +0.56% peak difference is not.
  - **Seven matched points, 855-1485 MHz**, the lower half of the band.
  - Voltage inferred from power, not measured. No HWiNFO on that machine, by choice - it was a
    customer's PC and the kit installs nothing.
  - One chip, one cooler, one case, one session, one ambient.
