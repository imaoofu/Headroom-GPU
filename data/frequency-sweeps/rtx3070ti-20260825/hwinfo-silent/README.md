# Session B — SILENT BIOS with voltage telemetry, 2026-08-27

Collected on the Gigabyte RTX 3070 Ti GAMING OC, dual-BIOS switch in the **SILENT** position
(VBIOS `94.04.5a.00.91`), to test the prediction §5.5.3 recorded before the measurement existed.

## THE PREDICTION FAILED

> §5.5.3 predicted: if the OC BIOS's +23.11% matched-frequency power draw is voltage and nothing
> else, the SILENT floor should sit at **0.819 / √1.2311 = 0.738 V**.

**Measured floor: 0.812–0.819 V.** The OC floor is 0.819–0.825 V. Within this sensor's ~6–7 mV
quantisation the two BIOSes hold **the same voltage floor**. The predicted separation was 81 mV,
about twelve sensor steps; the measured separation is zero to one step.

This is the second branch of the outcome table written into `SESSION-B-PLAN.md` before collection:
*"if it reads near 0.819 V, voltage does not explain the power gap and §5.5.1 needs rewriting."*
That is what happened. **§5.5.1's "the overclock is almost entirely voltage" is wrong**, and
§5.5.3's account of what the OC BIOS spends its extra power on has to be rebuilt.

## The gap is real, reproduces, and is not voltage

Matched frequency, `gemm`, SILENT (today) against OC (2026-08-25). Both verified-quiet.

| MHz | SILENT V | OC V | ΔV | SILENT W | OC W | ΔW | SILENT xbar | OC xbar |
|---|---|---|---|---|---|---|---|---|
| 855 | 0.819 | 0.825 | +0.006 | 130.3 | 164.3 | **+26.1%** | 1335 | 1410 |
| 960 | 0.819 | 0.819 | **0.000** | 138.6 | 173.0 | +24.8% | 1335 | 1410 |
| 1065 | 0.812 | 0.819 | +0.007 | 145.7 | 184.0 | +26.3% | 1335 | 1410 |
| 1170 | 0.819 | 0.819 | **0.000** | 156.6 | 194.0 | +23.9% | 1335 | 1410 |
| 1275 | 0.819 | 0.819 | **0.000** | 161.4 | 196.6 | +21.8% | 1335 | 1410 |
| 1380 | 0.819 | 0.819 | **0.000** | 172.6 | 201.6 | +16.8% | 1335 | 1410 |
| 1485 | 0.812 | 0.819 | +0.007 | 188.3 | 218.7 | +16.2% | 1410 | 1410 |

- **Power gap: +22.27% mean**, against the +23.11% §5.5.1 measured on a different day from a
  different run. The effect reproduces.
- **Throughput gap: +0.42% mean.** The extra power buys essentially nothing, as §5.5.1 said.
- **Voltage gap: +0.003 V mean, exactly 0.000 at four of seven points.**
- **Memory clock is identical at 9251 MHz** in every position.

### Why the prediction failed: the gap is ADDITIVE, not multiplicative

The prediction needed the whole gap to be core dynamic power, which scales as V²·f. Then a
+23.11% power ratio at matched f gives a voltage ratio of √1.2311 and the SILENT floor follows.

**The gap does not behave that way.** A constant +23.11% predicts the absolute difference *grows*
across the band as total power grows. It does not:

| MHz | SILENT W | OC W | actual offset | offset a +23.11% model predicts |
|---|---|---|---|---|
| 855 | 130.3 | 164.3 | 34.0 W | 30.1 W |
| 1065 | 145.7 | 184.0 | 38.2 W | 33.7 W |
| 1275 | 161.4 | 196.6 | 35.2 W | 37.3 W |
| 1380 | 172.6 | 201.6 | 29.0 W | 39.9 W |
| 1485 | 188.3 | 218.7 | 30.4 W | **43.5 W** |

As an offset the gap is **34.1 W**, relative spread **9.9%**, against **22.3%** at **19.0%**
as a percentage. The additive description fits twice as tightly, and the multiplicative one
overshoots by 43% at the top of the band.

*Pinned as `5.5.1-gap-is-an-offset`, which raises if the offset ever stops being the tighter
description.*

**A fixed offset cannot be core dynamic power**, because core dynamic power scales with frequency.
The core clock rises 74% across this band and the extra draw does not grow at all. Whatever is
consuming those ~34 W is not the core switching harder — so there was never a core-voltage ratio
to recover from it, and √1.2311 was being applied to a quantity that does not contain one.

### The specific error, in one decomposition

Fit each BIOS's matched-band power as `P(f) = intercept + slope·f`. The slope is the part that
scales with core frequency — the term `P = C·V²·f` actually governs. The intercept is everything
that does not scale with core clock.

| | SILENT | OC | difference |
|---|---|---|---|
| slope (frequency-scaling) | 87.7 ± 5.4 W/GHz | 79.3 ± 6.4 W/GHz | **−8.4 ± 8.4 — consistent with zero** |
| intercept (constant) | 53.6 ± 6.4 W | 97.5 ± 7.6 W | **+43.9 ± 9.9 W — 4.4σ** |

R² = 0.981 and 0.968.

**The frequency-scaling term is the same in both BIOSes within error. All of the resolvable
difference is in the constant.**

That is the whole failure, stated exactly. §5.5.1 wrote:

> *"At fixed frequency and fixed work, dynamic power scales with the square of voltage, and +23%
> implies roughly 11% more of it."*

`V²·f` is a statement about the **slope**. The +23.11% was measured on **total board power**, and
it lives entirely in the **intercept**. The inference fed a whole-quantity ratio into a law that
governs only one term of it, and that term had not changed.

**43.9 W is not the same number as 34.1 W, and neither one changed between sessions.**
34.1 W is the *measured* mean offset across the seven matched points. 43.9 W is the difference
between the two fits' *intercepts* — an extrapolation to zero frequency, which no measurement
reaches. They differ because the slopes differ slightly, so the two lines converge as frequency
rises. **The number that describes the card is 34.1 W**; 43.9 W only ever appears inside the
decomposition.

### Does the replacement model actually predict better?

Yes, and by how much is pinned rather than asserted. Leave-one-out across the seven matched
points — fit each model's single parameter on six, predict the seventh:

| | mean absolute error |
|---|---|
| multiplicative, `OC = SILENT × r` | 6.43 W |
| additive, `OC = SILENT + d` | **2.95 W** |

The additive model predicts to **2.95 W** against **6.43 W** for the ratio model, a **54%**
reduction. Leave-one-out rather than in-sample because both models have exactly one free
parameter, and comparing two one-parameter fits in-sample on seven points would mostly measure
which functional form absorbs the spread.

The ratio model's errors are also *structured* — it overshoots at the bottom of the band (+5.8 W
at 855 MHz) and undershoots at the top (−13.4 W at 1485), which is the signature of a wrong
functional form rather than noise. The additive model's residuals show no such trend.

*Pinned as `5.5.1-additive-beats-ratio`, which raises if the ratio model ever predicts as well or
better — the sentence around it is an argument about functional form, and a number alone would not
report that collapse.*

**This is an improvement in description, not in explanation.** It predicts the OC position's power
from the SILENT position's on this card. It still does not say what draws the 34 W.

Applied correctly — V² to the slope alone — the same data gives a voltage ratio of √0.904 = 0.951,
which would put the SILENT floor at 0.819 / 0.951 = **0.861 V**, *above* the OC floor rather than
below it. The measured 0.812–0.819 V says the slope difference is noise, as its error bar already
says. Either way the sign of the original inference came entirely from the misattributed constant.

### It is not even all die power

**SILENT draws 34 W less and runs 5 °C hotter**, at every matched point, in both sessions
independently (SILENT 51.6–58.7 °C against OC 46.6–53.6 °C today; §5.5.1's
`thermal-runs-backwards` claim asserts the same direction from Session A).

Same die, same heatsink, same clock, same work — and the card drawing *more* power is the *cooler*
one. That means the cooling system is doing more work in the OC position, which is precisely what
distinguishes a "SILENT" BIOS from an "OC" one, and fan power sits inside the board power figure
`nvidia-smi` reports.

It also **rules out leakage** as the driver, in the useful direction: leakage rises with
temperature, so it would make the hotter card draw more. The hotter card draws less.

### The crossbar candidate is withdrawn

An earlier version of this file called the crossbar floor — 1335 MHz on SILENT against 1410 on OC —
"the one systematic difference this session can see". **The data does not support it.**

At **1485 MHz both BIOSes hold the same crossbar clock, 1410 MHz, and the offset there is 30.4 W** —
larger than the 29.0 W at 1380 MHz where the crossbar clocks differ by 75 MHz. The offset does not
collapse when the crossbar converges, so the crossbar is not what is drawing the power.

### What is actually established

A roughly constant **~34 W** that is:

- **not core voltage** — the floors are identical within one sensor step
- **not core dynamic power** — it does not scale with core clock at all
- **not memory clock** — identical at 9251 MHz in both positions
- **not crossbar clock** — survives unchanged where the crossbar clocks converge
- **not leakage** — the card drawing it is the cooler one
- **partly board-level rather than die-level** — the thermal inversion requires more cooling work
  in the OC position, and fan power is inside this measurement

That is a much sharper constraint than §5.5.1 had, and it is a set of exclusions rather than a
mechanism. **No mechanism is claimed here.** Separating a fan-curve contribution from the rest
needs fan RPM logged alongside power, which HWiNFO can report and this session did not capture.

## Fine sweep — where the floor was read

`gemm`, 1200–1600 MHz, 10 points, n = 19–24 samples per point.

    1200  0.825 V  1335 xbar  158.7 W
    1245  0.819    1335       155.2
    1290  0.812    1335       163.3
    1335  0.812    1335       166.6
    1380  0.812    1335       170.3
    1410  0.812    1335       173.2
    1455  0.812    1380       177.6
    1500  0.812    1425       180.8
    1545  0.831    1470       194.3
    1590  0.850    1515       205.1

Six consecutive points at 0.812 V. The two lowest points read 0.819 and 0.825 — *higher* than the
middle of the band, which is the opposite of a voltage-frequency curve and is not explained here.
It does not affect the conclusion: every candidate reading is far above 0.738 V.

## What was collected, and what was not

| planned | outcome |
|---|---|
| `gemm` matched 852–2130, 13 pts | **two runs**, 16:53 and 17:03. Both 13/13, `aborted_by_user: false`. |
| `membw` matched 852–2130, 13 pts | **never collected.** No sweep output exists and no HWiNFO log covers a `membw` run. |
| `gemm` fine 1200–1600, 10 pts | 10/10 |

**The HWiNFO log filenames do not match their contents.** Established from the logs' own internal
timestamps and confirmed by the join:

| file as named | actually covers |
|---|---|
| `hwinfo-silent-gemm-matched.csv` | 16:36:39–16:49:42 — **nothing.** It was stopped 4 minutes before the first sweep started. Max power 74 W; no loaded samples at all. |
| `hwinfo-silent-membw-matched-ORPHAN.csv` | 17:03:23–~17:28 — the **second `gemm` matched run**. All 13 points bin cleanly, n = 19–58, power range 130.3–274.9 W matching that sweep exactly. |
| `hwinfo-silent-gemm-fine.csv` | 17:28:50–~17:32 — the **fine sweep**. Correct as named. |

The ORPHAN file keeps its misleading original name with a suffix rather than being renamed,
because the name is evidence about how the session ran.

**So the first matched run has no voltage data** and stands only as a throughput replicate. It is
a good one: run 1 against run 2 agrees to **−0.21% mean (−0.30 to −0.13%)**, and today against
Session A's SILENT sweep agrees to **−0.57% (−0.61 to −0.46%)** across seven shared targets.

## Provenance

All three sweeps `verified-quiet` — `encoder_util_pct` 0, `decoder_util_pct` 0,
`video_engines_allowed` false. Driver 610.88, schema 0.3.1.

**First sweeps in the project to record the enforced power limit.** Every session JSON here
reports `power_limit_enforced_w` 290.00, `power_limit_default_w` 290.00, `power_limit_w` 320.00 —
confirming the SILENT position and closing the gap §5.5.3 had to acknowledge for the OC session,
where the 310 W figure existed only in a hand-read note.

## Join parameters

`--min-power 120`, fixed **before** any voltage was inspected. Justification, in order:

1. The sweeps' own `power_avg_w` puts loaded draw at **130.3–275.3 W** (matched) and
   **155.2–205.1 W** (fine), independent of HWiNFO. Session A's SILENT sweep gave 129.9–277.1 W.
2. A power histogram of each HWiNFO log shows the idle population below 80 W and the loaded
   population above 155 W, with the gap straddling 120.
3. Anything above ~125 W would begin discarding the real 855 MHz point.

Every point retained n ≥ 19. The threshold was not revisited after the voltages were read.

---

## The fan candidate is refuted, from data already collected (2026-08-29)

The exclusion list above left one live candidate: *"partly board-level rather than die-level — the
thermal inversion requires more cooling work in the OC position, and fan power sits inside this
measurement."* It also said separating it "needs fan RPM logged alongside power, which HWiNFO can
report and this session did not capture."

**That was wrong. This session did capture it.** The raw HWiNFO logs carry 327 columns including
`GPU Fan1 [RPM]` and `GPU Fan2 [RPM]`. Fan RPM was dropped during distillation, not during
collection, so the measurement existed on the USB the whole time and no further access to the card
was needed. Distilled extracts are now committed beside the voltage ones as
`fan-silent-gemm-matched.csv` and `fan-oc-gemm-matched.csv`.

Binned by GPU core clock into 15 MHz bins, loaded samples only, eight bins shared by both
positions:

| MHz | SILENT fan | OC fan | Δfan | SILENT W | OC W | ΔW | SILENT °C | OC °C |
|---|---|---|---|---|---|---|---|---|
| 855 | **0** | **0** | +0 | 131.9 | 164.6 | **+32.7** | 51.7 | 46.1 |
| 960 | **0** | **0** | +0 | 139.1 | 175.4 | **+36.3** | 55.8 | 51.0 |
| 1065 | 750 | 646 | −105 | 148.1 | 178.7 | +30.5 | 58.6 | 52.2 |
| 1170 | 1133 | 1347 | +215 | 157.9 | 188.5 | +30.6 | 57.0 | 50.9 |
| 1275 | 511 | 727 | +216 | 164.8 | 203.7 | +38.9 | 57.4 | 53.5 |
| 1380 | 1082 | 1354 | +272 | 173.6 | 209.1 | +35.5 | 57.5 | 52.7 |
| 1485 | 643 | 714 | +71 | 185.1 | 228.9 | +43.8 | 58.3 | 54.0 |
| 1785 | 1142 | 1453 | +311 | 235.7 | 271.8 | +36.1 | 63.4 | 58.8 |

**The decisive rows are the first two. At 855 and 960 MHz both fans read exactly zero in both BIOS
positions — 62 of 62 samples on the SILENT side and 16 of 16 on the OC side, literal `0`, the
card's zero-RPM idle mode holding through 130–175 W of load — and the offset there is still
+32.7 W and +36.3 W.** Fan power contributes exactly nothing at those points and the gap is
undiminished.

The rest of the band agrees. Fan speed ranges from 0 to 1453 rpm across these bins while the offset
stays between 30.5 and 43.8 W with no relationship to it: the smallest fan difference (855 MHz,
zero on both sides) carries a 32.7 W gap, and the largest (1785 MHz, +311 rpm) carries 36.1 W. If
fans drove the offset it would grow with them. **It bounds the fan contribution at roughly 3 W of a
~35 W gap**, and two axial fans at 1400 rpm cannot draw more than a couple of watts anyway.

**So the offset is not fan power.** Adding to the exclusion list above: not core voltage, not core
dynamic power, not memory clock, not crossbar clock, not leakage, **and not cooling**. No mechanism
is claimed and the list is now longer rather than shorter.

**This does not explain the thermal inversion**, which is a separate open question. The OC
position is 5–7 °C cooler at every matched point while drawing ~35 W more, and at the two lowest
points it is cooler with both fans stopped. Something is moving heat differently, or the extra
power is being dissipated somewhere that is not the die. Neither is established here.

**Provenance.** Mean power delta over these eight bins is **+35.5 W**, against the **34.1 W**
measured from the sweep CSVs. Two different instruments — HWiNFO board power binned by clock
against `nvidia-smi` per sweep point — agreeing to 1.4 W on a different derivation. The per-point
figures match too: 855 MHz gives 131.9 / 164.6 W here against 130.3 / 164.3 W in the table above.
