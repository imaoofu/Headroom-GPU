# OC BIOS voltage telemetry - 2026-08-25 evening

Three HWiNFO sensor logs taken alongside three sweeps on the Gigabyte RTX 3070 Ti GAMING OC, with
the dual-BIOS switch in the **OC** position (VBIOS `94.05.5a.00.bd`, 310 W).

**The paired sweep CSVs arrived 2026-08-26** and sit alongside these logs, with the joins
produced by `tools/frequency-sweep/join_hwinfo_voltage.py --min-power 120` as `*_voltage.csv`.
The findings below are now pinned as claims in `analysis/claims_crosschip.py` and written up in
paper 5.5.3.

**Use `--min-power 120`, not the 30 W default.** The gaps between sweep points sit at boost
voltage, and on a 310 W card the default threshold is permissive enough to let one through: it
reports the fine sweep's floor as 0.819-0.822 V. Every loaded reading here is above 164 W, so 120
excludes the idle samples without discarding a single real one.

| log | sweep it accompanies |
|---|---|
| `hwinfo-oc-gemm-matched2130.csv` | `gemm`, 13 points forced to the silent band 852-2130 MHz |
| `hwinfo-oc-membw-matched2130.csv` | `membw`, same band |
| `hwinfo-oc-gemm-fine.csv` | `gemm`, 10 points 1200-1600 MHz |

HWiNFO 8.52-6060 portable, run from the kit folder, nothing installed. All four columns the join
needs are present on this machine - `GPU Core Voltage [V]`, `GPU Clock [MHz]`,
`GPU Crossbar Clock [MHz]`, `GPU Power [W]` - including the crossbar clock, which was the one at
risk of being absent on Ampere.

## What they already show

**The OC BIOS holds a hard voltage floor of 0.819 V.** From the fine sweep, ten consecutive points
with the load running:

    1200 MHz  0.819 V  1410 MHz crossbar  195.3 W
    1245      0.819    1410              200.9
    1290      0.819    1410              202.3
    1335      0.819    1410              208.8
    1380      0.819    1410              211.5
    1410      0.819    1410              218.6
    1455      0.819    1410              224.1
    1500      0.819    1440              229.0
    1545      0.819    1470              238.5
    1590      0.819    1515              225.8

Voltage does not move at all across the whole band - spread 0.000 V - while power rises 16.4%.
An earlier version of this file reported 0.822 V and 197.3 W at 1590 MHz, both from samples the
30 W threshold admitted; the joined figures above supersede them. The coarse sweep extends the
same floor down to 855 MHz and up to 1605, after which voltage climbs - 0.869 V at 1710, 0.925 at
1815, 0.988 at 1920, 1.075 at 2025.

**The crossbar clock has its own floor at 1410 MHz**, flat from 855 to about 1485 and tracking the
core clock above that. The crossbar-to-core ratio therefore falls from 1.649 at 855 MHz to 0.949 at
1485, which is the same shape 5.7.4 measured on the 5060 Ti from the opposite direction.

The floor covers the entire 855-1485 MHz band that 5.5.1 uses for its matched-frequency
comparison, which is what makes the next measurement a clean test.

## A PREDICTION, RECORDED BEFORE THE MEASUREMENT THAT TESTS IT

Section 5.5.1 reports the OC BIOS drawing **+23.11%** more power than SILENT at matched frequency,
and attributes it to voltage on the strength of an inference rather than a measurement.

At fixed frequency and fixed work, dynamic power scales with the square of voltage. If the whole
gap is voltage, the SILENT floor should sit at:

    0.819 V / sqrt(1.2311) = 0.738 V

**So: if tomorrow's SILENT session reads a floor near 0.738 V, the mechanism is confirmed and
5.5.1 stops being an inference. If it reads 0.819 V - the same floor - then voltage does not
explain the power gap and that section needs rewriting.**

This is written down now, before the SILENT session, deliberately. A prediction recorded after
seeing the answer is not a prediction, and this project has spent two days learning what happens
when a number is chosen after the fact.

## Two flaws in these logs, for whoever processes them

**Polling was 2000 ms, not the 500 ms intended.** That yields 5-10 loaded samples per grid point.
Enough for a median, thin for anything else. The SILENT session should use 500 ms, and the two will
therefore differ in sample density - which does not affect a median but should be stated.

**Samples above roughly 1605 MHz are contaminated by the settle window.** The coarse log shows
107 W at 1815 MHz and 88 W at 1920, against 227 W at 1485 - impossible under load. Those are
samples taken after the clock was locked but before the workload started. `join_hwinfo_voltage.py`
filters idle samples at `IDLE_POWER_WATTS = 30.0`, which is far too permissive on a card whose
loaded draw is 165-290 W. **Pass `--min-power 120` or higher when joining these**, and treat the
top of the band as unmeasured rather than as measured-and-low.
