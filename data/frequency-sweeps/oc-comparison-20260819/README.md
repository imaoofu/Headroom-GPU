# Stock vs tuned, one chip, one session — 2026-08-19

The controlled version of the comparison `ROADMAP.md` calls *"the project's whole thesis in
one comparison."* The previous stock-versus-tuned figures came from runs on different days
with different background load (6.2% against 3.6%) and unmatched thermal state, and were
explicitly recorded as worth nothing. These two runs are the same RTX 5060 Ti, the same tool,
the same 13 target frequencies, roughly 90 minutes apart in one session.

**Applied settings are recorded for the first time** — see `APPLIED-SETTINGS.txt` and
`afterburner-gpu-profile.cfg`. Memory +2500 MHz, core on a V/F curve pinned flat near
3000 MHz at every voltage at and above ~925 mV, power limit 111%. That is the field nothing
can reconstruct after the fact, and its absence is why the earlier tuned data is unusable.

## Headline

At each configuration's own sustained maximum:

| workload | throughput | power | efficiency |
|---|---|---|---|
| `gemm` | **+12.1%** | **−2.9%** | **+15.4%** |
| `membw` | **+17.6%** | **−3.7%** | **+22.1%** |

This closely reproduces the earlier uncontrolled +13.1% / −2.5%, so that figure is
corroborated rather than overturned — it simply now has a controlled measurement behind it.

`membw`'s gain has a coherent mechanism: memory runs at 16301 MHz tuned against a 14001 MHz
rating, a ratio of 1.164 against a measured throughput ratio of 1.176. A bandwidth-limited
workload tracking memory clock is what theory predicts.

## The more interesting result: power at matched frequency

With the core clock **locked to the same value** in both runs, `gemm` does the same work for
far less power. Achieved clocks matched to within 0 MHz and temperatures to within 1 °C, so
this is neither a clock difference nor thermal drift:

| locked clock | throughput Δ | power Δ | efficiency Δ |
|---|---|---|---|
| 1852 MHz | −2.0% | **−18.1%** | +19.8% |
| 2010 MHz | −2.3% | **−26.4%** | +32.7% |
| 2167 MHz | +0.8% | **−19.9%** | +25.8% |
| 2317 MHz | −1.2% | **−18.1%** | +20.7% |

Throughput differences sit inside this workload's measured run-to-run spread (median 2.56%
between identical passes). **The efficiency gain is mostly power reduction at matched
frequency, not the higher peak clock.** That is the voltage guardband, visible in the only
terms this project can measure.

**This has since been separated into its two knobs and the attribution is confirmed.** A third
`gemm` sweep with the memory overclock retained and the core V/F curve reverted to stock
reproduces stock power to within ±3% at all four of these frequencies (−0.6%, −2.9%, +0.9%,
−2.5%), against the tuned profile's −18% to −26%. Temperatures matched to within 0.6 °C. So the
power reduction is entirely the core V/F curve, not the memory overclock, and memory speed does
nothing measurable for this compute-bound workload. The curve additionally lifts the sustainable
ceiling: stock and memory-only both collapse to ~2590 MHz and ~15.7 TFLOP/s at the top three
grid points, while the curve holds 2948 MHz and reaches 17.61 TFLOP/s, +12.1% against stock's
own peak of 15.71 TFLOP/s at 2598 MHz. An earlier version of this line said +12.3%, measured
against stock's last grid point rather than its best. See
`../membw-anomaly-20260819/`.

Below ~1545 MHz the sign flips — the tuned configuration draws *more* power (+4.4% at
1237 MHz). Plausibly the custom curve sets a higher voltage floor at low clocks than stock
would. **Voltage readback was later obtained via HWiNFO** (see `../membw-anomaly-20260819/`,
Part 1b), and the voltage-logged runs cover 1402–2100 MHz, so the region below 1402 MHz is still
unmeasured and this remains a hypothesis — for want of coverage now, not for want of a sensor.

## An anomaly that is REAL, REPRODUCIBLE, and now traced to the core V/F curve

Across 1545–1852 MHz the tuned `membw` run is flat at ~295 GB/s while stock rises
312 → 332 → 342. That is 11–14% **slower** with more memory bandwidth available, at identical
core clock and temperature.

This was originally recorded here as probably an artifact, because a stability logger ran
concurrently during the tuned sweep and not the stock one, spawning `nvidia-smi` once per
second. **That explanation is now ruled out.** A second tuned `membw` sweep was run the same
evening with no logger and nothing else touching the GPU — see
`../membw-anomaly-20260819/` — and the plateau reproduced to within 1%:

| SM MHz | stock | tuned run 1 (logger) | tuned run 2 (clean) | run 1 vs run 2 |
|---|---|---|---|---|
| ~1560 | 311.8 | 296.6 | 294.1 | −0.8% |
| ~1710 | 331.8 | 295.3 | 297.8 | +0.8% |
| ~1867 | 341.6 | 294.5 | 297.5 | +1.0% |
| ~2025 | 344.4 | 324.4 | 326.7 | +0.7% |

Three mechanisms are now eliminated:

- **Not the logger.** Two independent runs, one with it and one without, agree within 1%.
- **Not memory clock.** The re-run added memory-clock telemetry to the sweep tool, which had
  only ever recorded the SM clock — the wrong clock for a bandwidth-bound workload. Memory
  held at exactly 16301 MHz at every frequency, with `min` equal to `max` equal to `avg`. There
  is no downclock.
- **Not throttling.** `clocks_throttle_reasons.active` was decoded for all three runs. No power
  cap, no thermal slowdown, no hardware slowdown anywhere. The `GpuIdle` bit appears in the
  tuned runs at *every* frequency including the ones performing at +17.6%, so it reflects a
  telemetry sample landing between benchmark iterations, not a stall.

Temperature in the band was 44–48 °C, far below any throttle point.

**So the 1545–1852 MHz data is not unusable — it is corroborated.** What is missing is a
mechanism, not a measurement. The plateau is genuine behaviour of this card under this tuned
profile, and it is the one result here that contradicts the simple story the rest of the data
tells.

### RESOLVED: it is the core V/F curve, not the memory overclock

The separation test was run the following evening (2026-08-20 18:13, against run 1 at
2026-08-19 20:42 — a 21.5 hour gap, since switching configurations needs a manual Afterburner
change): memory left at +2500, core V/F curve reverted to stock. **The plateau disappears completely.** Throughput rises monotonically across the whole
band, 291.8 GB/s at 1402 MHz to 400.4 GB/s at 2100 MHz, with memory still reading 16301 MHz
under load.

| SM MHz | mem-OC only | full tuned | throughput | efficiency |
|---|---|---|---|---|
| ~1560 | 323.0 | 294.1 | +9.8% | +8.8% |
| ~1710 | 360.1 | 297.8 | +20.9% | +9.3% |
| ~1867 | 385.7 | 297.5 | **+29.6%** | **+12.1%** |
| ~2025 | 399.9 | 326.7 | +22.4% | +1.7% |

**Memory-only leads the flattened curve by up to 29.6% in throughput and 12.1% in efficiency on
this workload across this band** (the curve costs up to 22.9% of memory-only's throughput; this said
"costs up to 29.6% of throughput" until 2026-09-24). **It costs more throughput than it saves power.**
Memory-overclock-only also beats stock on both axes (+3.6% to +16.1% throughput, +2.1% to +8.4%
efficiency, at stock targets 15 MHz below the memory-only ones; +2.4% to +17.1% against a stock sweep
on identical targets, `membw-anomaly-20260819/…stock-volt-membw`).

This does not overturn the headline `membw` +17.6% figure above, which was measured at each
configuration's own sustained maximum near 2900-3000 MHz — outside this band. Both hold: the
flattened curve helps at the top of the range and hurts badly in the middle.

It does mean the profile recorded in `APPLIED-SETTINGS.txt` is **not** the right configuration
for bandwidth-bound work below ~2100 MHz, which is precisely where a DVFS efficiency optimum
would be looked for.

What is pinned down here is *which knob* is responsible, not *how*. The working hypothesis was
that locking the SM clock into this band forces a voltage selection below the curve's flattened
region.

**That hypothesis has since been confirmed by measurement, and this paragraph is left as the
record of what was known at the time.** HWiNFO turned out to read core voltage on this hardware
even though NVML does not, and the follow-up runs show core voltage pinned at 0.720 V across a
49% rise in core clock, with the crossbar clock pinned alongside it. The mechanism is no longer a
hypothesis. See `../membw-anomaly-20260819/`, Part 1b.

Full data, method and caveats: `../membw-anomaly-20260819/`.

### What this still does not establish

The stock leg of the comparison is unchanged and was measured at 14:33 the same day, while the
clean tuned re-run was at 20:42 — roughly six hours and an unknown ambient shift apart. The
tuned-versus-tuned reproduction is solid; the tuned-versus-stock gap in this band rests on the
original same-session pair, not on the re-run.

That gap in the `gemm` evidence is now closed — see the note added to the matched-frequency
section above. The short version is that the two knobs do opposite things to the two workloads:
the core V/F curve is the entire benefit for `gemm` and a large penalty for `membw` in the
1560–1867 MHz band, while the memory overclock is the entire benefit for `membw` and does
nothing measurable for `gemm`. **There is no single tuned profile that is right for both.**

## Other caveats that stay attached

- **Sequential, not interleaved.** All of stock, then all of tuned. Thermal drift remains
  confounded with condition. Proper interleaving alternates them.
- **n = 1 chip.** Nothing here speaks to chip-to-chip variation.
- **Frequency versus power, not voltage.** No documented API on this hardware reads voltage
  back. The curve was *set* at these voltage points, not verified at them. This must not be
  described as a measured undervolt.
- **No stability verdict.** The concurrent logger was killed before it wrote its session JSON,
  so only the raw 584-sample telemetry (`oc-stability-samples.csv`) exists. No crash occurred
  — the card held 2948–2985 MHz across 26 locked frequencies — but that is an observation, not
  the tool's judgement.
- **Filenames are misleading on the tuned run.** They read `...-oc-gemm-stock_sweep.csv`
  because the collection kit hardcoded a `-stock` suffix. Fixed in the kit afterwards; these
  files keep their original names. `machine-info-OC.txt` records
  `peak_sm_clock_mhz[gemm] : 2948`, against stock's 2598 in the CSVs, which is the
  authoritative discriminator.
