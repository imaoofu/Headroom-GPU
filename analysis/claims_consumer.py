"""
Claims about the sweeps THIS PROJECT collected, checked against their source CSVs.

READ audit_claims.py FIRST. The short version: each function below returns the exact string
its document must contain, computed from the data. The engine asserts that string appears
verbatim and exactly once. Nothing here stores an expected number.

THIS MODULE IS NOT ONE CARD, AND ITS OPENING LINE SAID IT WAS UNTIL 2026-09-12
    It read "Claims about the RTX 5060 Ti consumer measurements" while already reading the
    RTX 3060 through SUITE_3060 and the RTX 3070 Ti through SUITE_3070_SWEEPS and
    _VOLT_3070_SILENT. The 2060 Super belongs here too when it is pinned.

    CLAUDE.md described the three claims modules as "split by which hardware the data came
    from", and that was the intent, but it is not what the files do and it cannot be. The
    cross-chip claims - 5.5.4's rank correlation, 5.5.7's knee table - compare cards to each
    other INSIDE ONE CLAIM. A claim spanning four chips has no per-card module to live in.

    THE HONEST SPLIT IS BY STUDY, NOT BY CARD:

      claims_consumer.py    the sweeps this project ran: the 5060 Ti configuration work of
                            5.4, 5.7 and 5.8, plus every claim that sets cards side by side
                            (5.5.4, 5.5.6, 5.5.7, 5.5.8)
      claims_crosschip.py   the 3070 Ti two-BIOS study of 2.6 and 5.5-5.5.3, self-contained
      claims_reference.py   the public V100 dataset, published by others and never pooled
                            with the above

    ⚠️ SO THE 3070 Ti IS REACHED FROM TWO MODULES, through two independent sets of constants
    into the same rtx3070ti-20260825/ tree. The stated reason for keeping the modules apart
    was that "a shared constant is how a claim silently reads the wrong hardware" - and the
    arrangement that actually exists is the one that reasoning warns about. Nothing is known
    to be wrong today; the guard is that every path here is a literal, so a wrong card is
    visible in the diff rather than inherited. Do not add a helper that resolves a card name
    to a directory.

WHICH RUNS THE 5060 Ti CONFIGURATION CLAIMS REFER TO
    Eight sweeps, in the order they were taken, all on the same card:

      1  stock         gemm    2026-08-19 14:28   no memory OC, stock V/F curve
      2  tuned         gemm    2026-08-19 16:20   memory OC + flattened core curve
      3  tuned         membw   2026-08-19 20:42   the run that found the plateau
      4  memory-only   membw   2026-08-20 18:13   memory OC, core curve reverted
      5  memory-only   gemm    2026-08-20 18:32
      6  curve-fixed   membw   2026-08-20 21:53   stock slope restored below ~925 mV
      7  curve-fixed   gemm    2026-08-20 22:02   DISCARDED at 1852 MHz, see below
      8  curve-fixed2  gemm    2026-08-20 22:14   the clean gemm run under the repair

    Run 7's 1852 MHz row overshot its lock by +1002.6 MHz - the cap was never applied and the
    card ran at full boost. analyze_sweep.loadSweep drops rows that miss ABOVE, so sweep()
    excludes it automatically and every analytical claim below uses run 8. The one claim that
    quotes the failure itself reads it through sweepRaw().

    This matters more than it looks. An earlier version of the ROADMAP computed the tuned-vs-
    repaired efficiency gap from run 7 and reported "5-18% across 2317-2782 MHz". Including
    that one bad row understated both the band and the effect: the real answer from run 8 is
    up to 33.1% across 1545-2782 MHz.

WHY SOME CLAIMS PIN A SENTENCE FRAGMENT
    The documents are hard-wrapped at ~100 characters, so a sentence usually spans a line
    break and its exact text depends on where the wrap happens to fall. Claims therefore pin
    the longest fragment that stays on ONE line. Re-wrapping a paragraph will not break a
    claim; changing a number will.
"""

from statistics import fmean as mean, median, stdev
from audit_claims import (CLAIMS, POST_SOAK, SOAK, WHOLE_RUN, claim, deltaPct, iterationsIn,
                          loadedSamples, signedPct, stabilityRun, sweep, sweepRaw,
                          voltageJoin)

PAPER = "docs/PAPER_DRAFT.md"
ANOMALY_README = "data/frequency-sweeps/membw-anomaly-20260819/README.md"

STOCK_GEMM = "oc-comparison-20260819/20260819-142844_5060ti-kittest-stock-gemm-stock_sweep.csv"
TUNED_GEMM = "oc-comparison-20260819/20260819-162025_5060ti-oc-gemm-stock_sweep.csv"
MEMONLY_GEMM = "membw-anomaly-20260819/20260820-183206_5060ti-memonly-gemm_sweep.csv"
FIXED1_GEMM = "membw-anomaly-20260819/20260820-220226_5060ti-curvefixed-gemm_sweep.csv"
FIXED2_GEMM = "membw-anomaly-20260819/20260820-221451_5060ti-curvefixed2-gemm_sweep.csv"

FIXED1_MEMBW_VOLTS = "membw-anomaly-20260819/20260820-215336_5060ti-curvefixed-membw_sweep_voltage.csv"
FIXED2_GEMM_VOLTS = "membw-anomaly-20260819/20260820-221451_5060ti-curvefixed2-gemm_sweep_voltage.csv"

# The four targets at which stock, tuned and the repaired curve all held their lock at the same
# achieved clock. 5.7.1 and 5.7.5 both tabulate these, which is the point - the repair is
# measured against the same rows the original saving was measured against.
MATCHED_TARGETS = [1852, 2010, 2167, 2317]

GRID = [1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090]


def efficiency(row):
    return row["throughput"] / row["power"]


def peak(sweepRows):
    """Highest-throughput row. Not the highest TARGET row - the card does not reach its top
    targets, so the fastest point and the last point are different rows."""
    return max(sweepRows.values(), key=lambda r: r["throughput"])


# --------------------------------------------------------------------------------------
# 5.7.1 - the matched-frequency power reduction is entirely the core curve
# --------------------------------------------------------------------------------------

# Section 5.7.1 uses the 2026-08-22 clean-protocol runs, two per configuration, averaged.
#
# NEW CONSTANTS RATHER THAN REPOINTING STOCK_GEMM AND TUNED_GEMM IN PLACE. Those two are read by
# nine claims, including 5.7.5's voltage-shortfall refutation, which compares the tuned card
# against the curvefixed925 run of 2026-08-21. That is a dirty-vs-dirty comparison and valid on
# its own terms; repointing the shared constant would silently make it clean-vs-dirty, corrupting
# a sound refutation while breaking no test and looking like a tidy refactor.
#
# Averaged over two runs because a single sweep is what this project spent 2026-08-22 learning not
# to trust. Stock run-to-run spread on power at these four targets is 1.54% mean, 3.05% worst.
STOCK_GEMM_CLEAN = ["20260822-201101_5060ti-stock-gemm-clean-r1_sweep.csv", "20260822-201554_5060ti-stock-gemm-clean-r2_sweep.csv"]
TUNED_GEMM_CLEAN = ["20260822-182129_5060ti-tuned-gemm-clean-r1_sweep.csv", "20260822-182619_5060ti-tuned-gemm-clean-r2_sweep.csv"]
MEMONLY_GEMM_CLEAN = ["20260822-211705_5060ti-memonly-gemm-clean-r1_sweep.csv", "20260822-212156_5060ti-memonly-gemm-clean-r2_sweep.csv"]


def _meanPower(paths, target):
    return mean(sweep(p)[target]["power"] for p in paths)


def _powerRow171(target):
    stockW = _meanPower(STOCK_GEMM_CLEAN, target)
    tunedW = _meanPower(TUNED_GEMM_CLEAN, target)
    memonlyW = _meanPower(MEMONLY_GEMM_CLEAN, target)
    # No ** around the tuned column even though the document bolds it: audit_claims.normalise
    # strips emphasis from both sides, so rendering it here would be decoration only.
    return (f"| {target} MHz | {deltaPct(tunedW, stockW)} "
            f"| {deltaPct(memonlyW, stockW)} |")


for _target in MATCHED_TARGETS:
    claim(f"5.7.1-power-{_target}", PAPER, "5.7.1")(
        lambda target=_target: _powerRow171(target))


@claim("5.7.1-memonly-within-3pct", PAPER, "5.7.1")
def memonlyReproducesStockPower():
    """The claim is a bound, so the rendering has to be a bound too: the sentence says "within
    3%" and what is checked is that 3 is the smallest whole percent that still contains every
    matched point."""
    worst = max(abs(_meanPower(MEMONLY_GEMM_CLEAN, t) / _meanPower(STOCK_GEMM_CLEAN, t) - 1.0) * 100.0
                for t in MATCHED_TARGETS)
    import math
    return f"Memory-only reproduces stock power to within {math.ceil(worst)}%."


# --------------------------------------------------------------------------------------
# 5.7.5 - the repair is a trade, not a win
# --------------------------------------------------------------------------------------

def _powerRow175(target):
    stock, tuned, fixed = sweep(STOCK_GEMM), sweep(TUNED_GEMM), sweep(FIXED2_GEMM)
    return (f"| {target} MHz | {deltaPct(tuned[target]['power'], stock[target]['power'])} "
            f"| {deltaPct(fixed[target]['power'], stock[target]['power'])} |")


for _target in MATCHED_TARGETS:
    claim(f"5.7.5-power-{_target}", PAPER, "5.7.5")(
        lambda target=_target: _powerRow175(target))


def _efficiencyRow(target):
    tuned, fixed = sweep(TUNED_GEMM), sweep(FIXED2_GEMM)
    tunedEff, fixedEff = efficiency(tuned[target]), efficiency(fixed[target])
    # Throughput is in FLOP/s in the CSV; the table is in TFLOP/W, so scale before rounding.
    # Rounding a ratio of unscaled numbers would agree to four decimals by accident.
    return (f"| {target} MHz | {tunedEff / 1e12:.4f} | {fixedEff / 1e12:.4f} "
            f"| {signedPct(tunedEff / fixedEff)} |")


for _target in GRID:
    claim(f"5.7.5-efficiency-{_target}", PAPER, "5.7.5")(
        lambda target=_target: _efficiencyRow(target))


@claim("5.7.5-peak-repaired", PAPER, "5.7.5")
def peakOfRepairedCurve():
    best = peak(sweep(FIXED2_GEMM))
    return (f"repaired curve reaches {best['throughput'] / 1e12:.2f} TFLOP/s "
            f"at {best['mhz']:.0f} MHz drawing {best['power']:.1f} W")


@claim("5.7.5-peak-tuned", PAPER, "5.7.5")
def peakOfTunedCurve():
    best = peak(sweep(TUNED_GEMM))
    return (f"{best['mhz']:.0f} MHz drawing {best['power']:.1f} W - "
            f"{deltaPct(peak(sweep(FIXED2_GEMM))['throughput'], best['throughput'])[1:]} "
            f"less throughput for "
            f"{deltaPct(peak(sweep(FIXED2_GEMM))['power'], best['power'])[1:]} less power")


@claim("5.7.5-peak-efficiency-inversion", PAPER, "5.7.5")
def repairedIsMoreEfficientAtItsPeak():
    """The one point where the repaired curve wins on gemm. Pinned deliberately: reporting it
    without the thirteen-row table above was the cherry-pick this section exists to avoid."""
    fixedBest, tunedBest = peak(sweep(FIXED2_GEMM)), peak(sweep(TUNED_GEMM))
    gain = signedPct(efficiency(fixedBest) / efficiency(tunedBest))
    return f"so {gain[1:]} better efficiency"


@claim("5.7.5-stock-peak", PAPER, "5.7.5")
def stockPeak():
    return f"peaks at {peak(sweep(STOCK_GEMM))['throughput'] / 1e12:.2f}."


@claim("5.7.5-run7-overshoot", PAPER, "5.7.5")
def run7Overshoot():
    """Read through sweepRaw because sweep() exists to remove exactly this row."""
    bad = sweepRaw(FIXED1_GEMM)[1852]
    if bad["missDirection"] != "above":
        raise ValueError("run 7's 1852 MHz row no longer misses ABOVE; the claim is stale")
    return (f"{bad['mhz']:.1f} MHz and {bad['power']:.1f} W, "
            f"an overshoot of +{bad['missMhz']:.1f} MHz")


@claim("5.7.5-top-voltage-identical", PAPER, "5.7.5")
def bothCurveVariantsTopOutAtTheSameVoltage():
    """Two different runs on two different workloads, hence the odd pairing: run 7 was not
    voltage-logged, so variant 1's top voltage is only available from its membw sweep."""
    tops = []
    for path in (FIXED1_MEMBW_VOLTS, FIXED2_GEMM_VOLTS):
        rows = voltageJoin(path)
        volts = {rows[t]["voltage"] for t in rows if t >= 2625}
        if len(volts) != 1:
            raise ValueError(f"{path} is not flat above 2625 MHz: {sorted(volts)}")
        tops.append(volts.pop())
    if tops[0] != tops[1]:
        raise ValueError(f"the two variants differ at the top: {tops}")
    return f"Both curve variants measure {tops[0]:.3f} V at every target"


@claim("5.7.1-ceiling", PAPER, "5.7.1")
def theCurveRaisesTheSustainableCeiling():
    """The +12.3% here needs a stated denominator, and the sentence around it does not give
    one. Stock's PEAK is 15.71 TFLOP/s at 2598 MHz; stock's LAST GRID POINT is 15.68 at
    2588 MHz. Against the peak the gain is +12.1%, against the last point +12.3%. This claim
    renders the peak comparison, because "the highest throughput this configuration reached"
    is the only denominator the surrounding sentence can be read as meaning once it has
    already said stock collapses to ~2590 MHz."""
    tunedBest, stockBest = peak(sweep(TUNED_GEMM)), peak(sweep(STOCK_GEMM))
    return (f"holds {tunedBest['mhz']:.0f} MHz and reaches "
            f"{tunedBest['throughput'] / 1e12:.2f} TFLOP/s "
            f"({deltaPct(tunedBest['throughput'], stockBest['throughput'])}).")


@claim("5.7.5-widest-gap", PAPER, "5.7.5")
def theWidestEfficiencyGap():
    """The prose bound. Rendering it from the data is what stops it drifting out of step with
    the table above it, which is precisely how the ROADMAP came to say 5-18%."""
    tuned, fixed = sweep(TUNED_GEMM), sweep(FIXED2_GEMM)
    band = [t for t in GRID if efficiency(tuned[t]) > efficiency(fixed[t])]
    widest = max(efficiency(tuned[t]) / efficiency(fixed[t]) for t in band)
    return (f"ahead at every point from {min(band)} through {max(band)} MHz, "
            f"by up to {signedPct(widest)[1:]}")


TUNED_MEMBW = "membw-anomaly-20260819/20260819-204233_5060ti-oc-membw-anomaly_sweep.csv"
MEMONLY_MEMBW = "membw-anomaly-20260819/20260820-181307_5060ti-memonly-membw-anomaly_sweep.csv"
STOCK_MEMBW_13PT = "oc-comparison-20260819/20260819-143337_5060ti-kittest-stock-membw-stock_sweep.csv"
# The only stock membw sweep on the 10-point grid the memory-only runs use. The 13-point
# file above shares NO targets with them, so it cannot serve a matched comparison.
STOCK_MEMBW_VOLT = "membw-anomaly-20260819/20260820-211630_5060ti-stock-volt-membw_sweep.csv"

# --------------------------------------------------------------------------------------
# 5.7.2 - the core curve costs a bandwidth-bound workload up to 29.6%
# --------------------------------------------------------------------------------------

PLATEAU_TARGETS = [1560, 1710, 1867, 2025]


def _plateauRow(target):
    memonly, tuned = sweep(MEMONLY_MEMBW), sweep(TUNED_MEMBW)
    m, t = memonly[target], tuned[target]
    return (f"| ~{target} MHz | {m['throughput'] / 1e9:.1f} | {t['throughput'] / 1e9:.1f} "
            f"| {deltaPct(m['throughput'], t['throughput'])} "
            f"| {deltaPct(efficiency(m), efficiency(t))} |")


for _target in PLATEAU_TARGETS:
    claim(f"5.7.2-plateau-{_target}", PAPER, "5.7.2")(
        lambda target=_target: _plateauRow(target))


@claim("5.7.2-monotone-range", PAPER, "5.7.2")
def monotoneRange():
    rows = sweep(MEMONLY_MEMBW)
    targets = sorted(rows)
    lo, hi = targets[0], targets[-1]
    return f"at {lo} MHz to {rows[hi]['throughput'] / 1e9:.1f} at {hi}:"


@claim("5.7.2-plateau-band", PAPER, "5.7.2")
def plateauBand():
    rows = sweep(TUNED_MEMBW)
    bandTargets = [1560, 1635, 1710, 1792, 1867]
    throughputs = [rows[t]["throughput"] for t in bandTargets]
    smallest = min(throughputs)
    band = (max(throughputs) - smallest) / smallest * 100
    # rise is over achieved clock, not commanded target
    rise = (rows[bandTargets[-1]]["mhz"] / rows[bandTargets[0]]["mhz"] - 1) * 100
    return f"Five consecutive points sit inside a {band:.1f}% band while core clock rises {rise:.0f}%."


@claim("5.7.2-stock-rises", PAPER, "5.7.2")
def stockRises():
    rows = sweep(STOCK_MEMBW_13PT)
    vals = [rows[t]["throughput"] / 1e9 for t in (1545, 1702, 1852)]
    return f"{vals[0]:.0f} to {vals[1]:.0f} to {vals[2]:.0f}."


# --------------------------------------------------------------------------------------
# 5.7 - the section introduction and its two-knob summary table (GPT Job 14, done by Claude
# 2026-09-24). The section carried 17 numbers and no claim. Each cell is rendered from the same
# comparison its subsection uses, so the summary cannot drift from the evidence under it.
#
# Two cells did not match when first rendered, and both were findings about the PAPER:
# - membw, memory overclock: the paper said "+3.6% to +16.1% over stock", taken from the membw
#   README's table, which pairs stock at 1545/1702/1852/2010 MHz with memory-only at
#   1560/1710/1867/2025 - different targets, a day apart. STOCK_MEMBW_13PT's own comment above says
#   it "cannot serve a matched comparison", and the paragraph promises "identical locked targets".
# - membw, core curve: the paper said "up to -29.6% throughput". 29.6% is memory-only OVER tuned;
#   as a signed change from memory-only to tuned it is -22.9%. Both are now stated.
# Left unpinned: "14001 rating" (clocks.max.memory, which reads 14001 with or without an offset -
# not a measurement in any CSV), "3000 MHz" and "~925 mV" (the decoded profile, not a sweep).
# --------------------------------------------------------------------------------------

MEMONLY_GEMM_SAMESESSION = "memonly-gemm-20260829/20260829-163134_5060ti-memonly-gemm-1237grid-samesession_sweep.csv"
STOCK_GEMM_SAMESESSION = "stock-suite-20260829/20260829-145752_5060ti-stock-gemm-1237grid_sweep.csv"
# Named apart from PLATEAU_BAND further down, a (1402, 1867) range read by other claims: a shared
# name here silently replaced this list on first render, 2026-09-24.
SUMMARY_PLATEAU_TARGETS = [1560, 1635, 1710, 1792, 1867]


def _maxLoadedMemory(paths):
    import csv as _csv
    values = []
    for relativePath in paths:
        with open(_REPO_ROOT / "data" / "frequency-sweeps" / relativePath, encoding="utf-8-sig") as handle:
            values += [float(row["memory_clock_max_mhz"]) for row in _csv.DictReader(handle)]
    return max(values)


@claim("5.7-memory-offset", PAPER, "5.7")
def memoryOffsetFromTheSweeps():
    """The offset and the tuned clock, both read off the clean 5.7.1 runs rather than restated
    from the profile: tuned loads memory at 16301 MHz, stock at 13801."""
    tuned = _maxLoadedMemory(TUNED_GEMM_CLEAN)
    stock = _maxLoadedMemory(STOCK_GEMM_CLEAN)
    return f"(+{tuned - stock:.0f} MHz offset, {tuned:.0f} against"


@claim("5.7-power-reproduces", PAPER, "5.7")
def powerReproducesWithin():
    """The header's reference to 5.4.5, rendered by the same function as 5.4.5's own table row."""
    return f"inside the {_spreadsFor('power'):.2f}% at which power reproduces (5.4.5)"


@claim("5.7-table-gemm", PAPER, "5.7",
       mixedProvenance="the row joins three comparisons, each on its own pair of runs. The memory-overclock bound uses the verified-quiet 2026-08-29 same-session pair, and the matched-clock power range the verified-quiet 2026-08-22 clean pairs. Only the sustainable-ceiling figure uses the 2026-08-19 peak sweeps, both schema 0.1.0 with no video-engine telemetry, taken the same day. A later top-band A/B found about a 1.5% capture effect (5.4.4), but that does not bound the bias in this pair; 'and no more' stood here until 2026-09-28 (GPT Job 33). Stated in 6 of the paper.")
def gemmRowOfTheSummaryTable():
    """Memory overclock: the 2026-08-29 same-session pair, whose MEAN change is the claim (-0.05%).
    Single points range -2.16% to +1.16%, so the bound is on the mean, not on every point.
    Core curve: the clean 5.7.1 power pairs at the matched targets, and 5.7.1's peak ceiling."""
    import math
    stock, memonly = sweep(STOCK_GEMM_SAMESESSION), sweep(MEMONLY_GEMM_SAMESESSION)
    shared = sorted(set(stock) & set(memonly))
    meanChange = mean(memonly[t]["throughput"] / stock[t]["throughput"] - 1.0 for t in shared) * 100.0
    bound = max(1, math.ceil(abs(meanChange)))
    power = [(_meanPower(TUNED_GEMM_CLEAN, t) / _meanPower(STOCK_GEMM_CLEAN, t) - 1.0) * 100.0
             for t in MATCHED_TARGETS]
    tunedBest, stockBest = peak(sweep(TUNED_GEMM)), peak(sweep(STOCK_GEMM))
    ceiling = deltaPct(tunedBest["throughput"], stockBest["throughput"])
    return (f"| `gemm` (compute-bound) | nothing measurable, plus or minus {bound}% "
            f"| the entire benefit: {max(power):.0f}% to {min(power):.0f}% power at matched clock, "
            f"{ceiling} sustainable ceiling |")


@claim("5.7-table-membw", PAPER, "5.7")
def membwRowOfTheSummaryTable():
    """Memory overclock: memory-only against the one stock membw sweep on the SAME 10-point grid
    (STOCK_MEMBW_VOLT). Core curve: tuned against memory-only across the 5.7.2 plateau band,
    stated both ways because "29.6%" had been written as a signed loss."""
    memonly, stock, tuned = sweep(MEMONLY_MEMBW), sweep(STOCK_MEMBW_VOLT), sweep(TUNED_MEMBW)
    shared = sorted(set(memonly) & set(stock))
    gains = [memonly[t]["throughput"] / stock[t]["throughput"] for t in shared]
    over = max(memonly[t]["throughput"] / tuned[t]["throughput"] for t in SUMMARY_PLATEAU_TARGETS)
    return (f"| `membw` (bandwidth-bound) | the entire benefit: {signedPct(min(gains))} to "
            f"{signedPct(max(gains))} over stock at identical targets | actively harmful: memory-only "
            f"delivers up to {signedPct(over)[1:]} more, so the curve costs up to "
            f"{signedPct(1.0 / over)[1:]} of throughput across {SUMMARY_PLATEAU_TARGETS[0]}-{SUMMARY_PLATEAU_TARGETS[-1]} MHz |")


# --------------------------------------------------------------------------------------
# 5.4 - consumer hardware measurements
# --------------------------------------------------------------------------------------

GEMM_FLOOR15 ="20260822-173451_5060ti-gemm-floor15-rerun_sweep.csv"
MEMBW_FLOOR15 = "20260822-174118_5060ti-membw-floor15-rerun_sweep.csv"


def _optimum(rows):
    return max(rows.values(), key=efficiency)


def _sustainedMax(rows):
    return max(rows.values(), key=lambda r: r["mhz"])


def _gemmMembw():
    g, m = sweep(GEMM_FLOOR15), sweep(MEMBW_FLOOR15)
    return (_optimum(g), _sustainedMax(g), _optimum(m), _sustainedMax(m))


@claim("5.4-optimum", PAPER, "5.4")
def optimumRow():
    gOpt, _, mOpt, _ = _gemmMembw()
    return (f"| Efficiency optimum | {gOpt['mhz']:.0f} MHz "
            f"| {mOpt['mhz']:.0f} MHz |")


@claim("5.4-pct-of-max", PAPER, "5.4")
def pctOfMaxRow():
    gOpt, gMax, mOpt, mMax = _gemmMembw()
    gPct = gOpt["mhz"] / gMax["mhz"] * 100
    mPct = mOpt["mhz"] / mMax["mhz"] * 100
    return (f"| {chr(0x2014)} as % of sustained max "
            f"| {gPct:.0f}% (of {gMax['mhz']:.0f} MHz) "
            f"| {mPct:.0f}% (of {mMax['mhz']:.0f} MHz) |")


@claim("5.4-efficiency-gain", PAPER, "5.4")
def efficiencyGainRow():
    gOpt, gMax, mOpt, mMax = _gemmMembw()
    g = signedPct(efficiency(gOpt) / efficiency(gMax))
    m = signedPct(efficiency(mOpt) / efficiency(mMax))
    return f"| Efficiency gain vs sustained max | {g} | {m} |"


@claim("5.4-performance-cost", PAPER, "5.4")
def performanceCostRow():
    gOpt, gMax, mOpt, mMax = _gemmMembw()
    g = deltaPct(gOpt["throughput"], gMax["throughput"], minus=chr(0x2212))
    m = deltaPct(mOpt["throughput"], mMax["throughput"], minus=chr(0x2212))
    return f"| Performance cost at optimum | {g} | {m} |"


@claim("5.4-power-saved", PAPER, "5.4")
def powerSavedRow():
    gOpt, gMax, mOpt, mMax = _gemmMembw()
    g = deltaPct(gOpt["power"], gMax["power"], minus=chr(0x2212))
    m = deltaPct(mOpt["power"], mMax["power"], minus=chr(0x2212))
    return f"| Power saved at optimum | {g} | {m} |"


@claim("5.4-monotonicity-break", PAPER, "5.4")
def monotonicityBreak():
    rows = sweep(GEMM_FLOOR15)
    lower = min(rows.values(), key=lambda r: abs(r["mhz"] - 1987))
    higher = min(rows.values(), key=lambda r: abs(r["mhz"] - 2205))
    if lower["mhz"] >= higher["mhz"]:
        lower, higher = higher, lower
    lowerEff = efficiency(lower) / 1e9
    higherEff = efficiency(higher) / 1e9
    gap = (higherEff / lowerEff - 1) * 100
    # The unit is on the FIRST figure only, which is how the paper writes it.
    return (f"at {lower['mhz']:.0f} MHz ({lowerEff:.2f} GFLOP/J) sits marginally below "
            f"{higher['mhz']:.0f} MHz ({higherEff:.2f}), "
            f"breaking monotonicity by {gap:.1f}%")


# --------------------------------------------------------------------------------------
# 5.4.1 - Resolving the two optima
# 5.4.3 - The sub-100% utilisation is a telemetry artifact, not lost work
# --------------------------------------------------------------------------------------

GEMM_FINE_P1 = "20260822-174624_5060ti-gemm-fine-p1-rerun_sweep.csv"
MEMBW_FINE_P1 = "20260822-175205_5060ti-membw-fine-p1-rerun_sweep.csv"
MEMBW_FINE_P2 = "20260822-175706_5060ti-membw-fine-p2-rerun_sweep.csv"
GEMM_FINE_P2 = "20260822-180206_5060ti-gemm-fine-p2-rerun_sweep.csv"


@claim("5.4.1-point-count", PAPER, "5.4.1")
def pointCount():
    # sweepRaw keeps every row (so the total is right even if a lock overshot); sweep() has
    # the windowed flag, which sweepRaw rows do not carry.
    paths = (GEMM_FINE_P1, MEMBW_FINE_P1, MEMBW_FINE_P2, GEMM_FINE_P2)
    rawRows = [r for p in paths for r in sweepRaw(p).values()]
    total = len(rawRows)
    held = sum(1 for r in rawRows if r["lockHeld"])
    windowed = sum(1 for p in paths for r in sweep(p).values() if r["windowed"])
    if not (total == held == windowed):
        raise ValueError(
            f"point counts disagree: total={total}, lockHeld={held}, windowed={windowed}")
    return (f"All {total} points held their locked clock exactly, none overshot, "
            f"and all {total} had power windowed to the benchmark's timed region.")


def _membwDecoupled(target):
    p1, p2 = sweep(MEMBW_FINE_P1)[target], sweep(MEMBW_FINE_P2)[target]
    return p1, p2


@claim("5.4.3-decoupled-1897", PAPER, "5.4.3")
def decoupled1897():
    p1, p2 = _membwDecoupled(1897)
    return (f"At 1897 MHz the two passes recorded utilisation of {p1['utilisation']:.1f}% "
            f"and {p2['utilisation']:.1f}% {chr(0x2014)} and throughput of "
            f"{p1['throughput'] / 1e9:.1f} and {p2['throughput'] / 1e9:.1f} GB/s.")


@claim("5.4.3-decoupled-1605", PAPER, "5.4.3")
def decoupled1605():
    p1, p2 = _membwDecoupled(1605)
    return (f"At 1605 MHz, {p1['utilisation']:.1f}% and {p2['utilisation']:.1f}% "
            f"utilisation gave {p1['throughput'] / 1e9:.1f} and "
            f"{p2['throughput'] / 1e9:.1f} GB/s")


# ---------------------------------------------------------------------------------------------
# 5.7.5 The voltage-shortfall hypothesis, refuted
#
# These pin a REFUTATION. The paragraph they cover previously proposed the test as future work,
# and disagreed with every other project document for a day after the test was run. Pinning the
# numbers is what stops that paragraph drifting back out of step with the sweeps.
# ---------------------------------------------------------------------------------------------

CURVEFIXED2_GEMM = "membw-anomaly-20260819/20260820-221451_5060ti-curvefixed2-gemm_sweep.csv"
CURVEFIXED925_GEMM = "membw-anomaly-20260819/20260821-215215_5060ti-curvefixed925-gemm_sweep.csv"


def _peakPoint(path):
    return max(sweep(path).values(), key=lambda r: r["throughput"])


@claim("5.7.5-ceiling-fell", PAPER, "5.7.5")
def ceilingFell():
    before, after = _peakPoint(CURVEFIXED2_GEMM), _peakPoint(CURVEFIXED925_GEMM)
    drop = before["mhz"] - after["mhz"]
    if drop <= 0:
        raise ValueError(
            f"the ceiling did not fall: {before['mhz']:.1f} -> {after['mhz']:.1f} MHz. "
            "The paragraph this pins argues the prediction failed; if the data now says "
            "otherwise the prose is wrong, not this claim.")
    return (f"it fell, from {before['mhz']:.1f} MHz to {after['mhz']:.1f} MHz, "
            f"{drop:.1f} MHz in the wrong direction")


@claim("5.7.5-peak-improved", PAPER, "5.7.5")
def peakImproved():
    before, after = _peakPoint(CURVEFIXED2_GEMM), _peakPoint(CURVEFIXED925_GEMM)
    return (f"to {after['throughput'] / 1e12:.2f} TFLOP/s from "
            f"{before['throughput'] / 1e12:.2f}")


@claim("5.7.5-deficit-narrowed", PAPER, "5.7.5")
def deficitNarrowed():
    tuned = _peakPoint(TUNED_GEMM)
    before, after = _peakPoint(CURVEFIXED2_GEMM), _peakPoint(CURVEFIXED925_GEMM)
    return (f"against the tuned card's {tuned['throughput'] / 1e12:.2f} TFLOP/s from "
            f"{100 * (before['throughput'] / tuned['throughput'] - 1):.1f}% to "
            f"{100 * (after['throughput'] / tuned['throughput'] - 1):.1f}%")


@claim("5.7.5-frequency-gap", PAPER, "5.7.5")
def frequencyGap():
    tuned, after = _peakPoint(TUNED_GEMM), _peakPoint(CURVEFIXED925_GEMM)
    return (f"{after['mhz']:.1f} MHz against {tuned['mhz']:.1f} MHz, a shortfall of "
            f"{tuned['mhz'] - after['mhz']:.1f} MHz")


# ---------------------------------------------------------------------------------------------
# 5.4.4 Default-enabled capture software shifts the measured optimum
#
# Five sweeps on one configuration in one session: three with NVIDIA Instant Replay enabled, two
# with it disabled. These pin the section that reports a contaminant which biased this project's
# own measurements, so they matter more than most - a drifted number here would undermine the
# section's whole argument about measurement discipline.
# ---------------------------------------------------------------------------------------------

IR_ON = ["20260822-160740_5060ti-splitcurve-gemm-r1_sweep.csv",
         "20260822-161322_5060ti-splitcurve-gemm-r2_sweep.csv",
         "20260822-165213_5060ti-splitcurve-gemm-r4-instantreplay-on_sweep.csv"]
IR_OFF = ["20260822-163705_5060ti-splitcurve-gemm-r3-quiet_sweep.csv",
          "20260822-165944_5060ti-splitcurve-gemm-r5-instantreplay-off_sweep.csv"]


def _irCondition(paths):
    """Per-target mean throughput and mean power across the runs in one condition."""
    runs = [sweep(p) for p in paths]
    shared = set(runs[0])
    for r in runs[1:]:
        shared &= set(r)
    return {t: (mean(r[t]["throughput"] for r in runs),
                mean(r[t]["power"] for r in runs)) for t in shared}


def _irPeaks(paths):
    return [max(sweep(p).values(), key=lambda r: r["throughput"])["throughput"] / 1e12
            for p in paths]


def _irBandMeanGap(low, high):
    on, off = _irCondition(IR_ON), _irCondition(IR_OFF)
    targets = [t for t in sorted(on) if low <= t <= high]
    return mean(100 * (off[t][0] / on[t][0] - 1) for t in targets)


@claim("5.4.4-peaks-on", PAPER, "5.4.4")
def peaksOn():
    return "| Instant Replay enabled | " + " / ".join(f"{v:.2f}" for v in _irPeaks(IR_ON)) + " TFLOP/s |"


@claim("5.4.4-peaks-off", PAPER, "5.4.4")
def peaksOff():
    return "| Instant Replay disabled | " + " / ".join(f"{v:.2f}" for v in _irPeaks(IR_OFF)) + " TFLOP/s |"


@claim("5.4.4-band-penalty", PAPER, "5.4.4")
def bandPenalty():
    return (f"{_irBandMeanGap(1237, 2010):.2f}% mean across 1237-2010 MHz against "
            f"{_irBandMeanGap(2167, 3090):.2f}% across 2167-3090 MHz")


@claim("5.4.4-clock-unchanged", PAPER, "5.4.4")
def clockUnchanged():
    def peakMhz(p):
        return max(sweep(p).values(), key=lambda r: r["throughput"])["mhz"]
    on = [peakMhz(p) for p in IR_ON]
    off = [peakMhz(p) for p in IR_OFF]
    # The sentence gives ONE figure for the disabled condition, which is only honest if both of
    # its runs peaked at the same clock. Raise rather than quietly picking one of two.
    if len(set(round(v, 1) for v in off)) != 1:
        raise ValueError(f"disabled runs peaked at different clocks: {off}; the prose states a "
                         "single value and would be misdescribing the data")
    listed = ", ".join(f"{v:.1f}" for v in on[:-1]) + f" and {on[-1]:.1f}"
    return f"{listed} MHz enabled against {off[0]:.1f} MHz disabled"


def _irSpread(paths, target):
    values = [sweep(p)[target]["throughput"] for p in paths]
    return 100 * (max(values) - min(values)) / mean(values)


@claim("5.4.4-spread-1545", PAPER, "5.4.4")
def spread1545():
    return (f"At 1545 MHz the spread is\n{_irSpread(IR_ON, 1545):.2f}% enabled against "
            f"{_irSpread(IR_OFF, 1545):.2f}% disabled.")


def _irOptimum(paths):
    cond = _irCondition(paths)
    best = max(cond, key=lambda t: cond[t][0] / cond[t][1])
    top = max(cond)
    gain = 100 * ((cond[best][0] / cond[best][1]) / (cond[top][0] / cond[top][1]) - 1)
    return best, gain


@claim("5.4.4-optimum-on", PAPER, "5.4.4")
def optimumOn():
    best, gain = _irOptimum(IR_ON)
    return f"| Instant Replay enabled | {best} MHz | +{gain:.1f}% |"


@claim("5.4.4-optimum-off", PAPER, "5.4.4")
def optimumOff():
    best, gain = _irOptimum(IR_OFF)
    return f"| Instant Replay disabled | {best} MHz | +{gain:.1f}% |"


# ---------------------------------------------------------------------------------------------
# 5.7.6 A split-region curve, derived from the mechanism, recovers both
#
# Eight clean-protocol sweeps, five tuned and three split. The non-overlap claim is the load-
# bearing one here because it does not depend on averaging, so it is pinned separately from the
# means and RAISES rather than rendering if the ranges ever start to overlap.
# ---------------------------------------------------------------------------------------------

# The three split-curve gemm runs are not all verified-quiet, and four claims below
# compare them against five runs that are. Written once here rather than repeated at
# each call site, because a reason pasted four times is a reason nobody re-reads.
SPLIT_GEMM_MIX = ("two of the three split-curve runs (r3-quiet, r5-instantreplay-off) predate the encoder guard: their settings declare Instant Replay off but nothing verified it. The five tuned runs are all verified-quiet. The risk runs TOWARD the finding, not against it - undetected contamination would depress the split runs and understate the gap - and the one verified-quiet split run agrees at 18.22. Stated rather than silently mixed.")

TUNED_CLEAN_5 = [f"20260822-{s}_5060ti-tuned-gemm-clean-r{i}_sweep.csv" for i, s in
                 zip((1, 2, 3, 4, 5), ("182129", "182619", "213750", "215317", "215811"))]
SPLIT_CLEAN_3 = ["20260822-163705_5060ti-splitcurve-gemm-r3-quiet_sweep.csv",
                 "20260822-165944_5060ti-splitcurve-gemm-r5-instantreplay-off_sweep.csv",
                 "20260822-220443_5060ti-splitcurve-gemm-clean-r3_sweep.csv"]


def _peakTf(path):
    return max(sweep(path).values(), key=lambda r: r["throughput"])["throughput"] / 1e12


@claim("5.7.6-tuned-runs", PAPER, "5.7.6")
def tunedRuns():
    v = [_peakTf(p) for p in TUNED_CLEAN_5]
    return ("| original tune, n=5 | " + " / ".join(f"{x:.2f}" for x in v)
            + f" | {mean(v):.2f} TFLOP/s |")


@claim("5.7.6-split-runs", PAPER, "5.7.6",
       mixedProvenance=SPLIT_GEMM_MIX)
def splitRuns():
    v = [_peakTf(p) for p in SPLIT_CLEAN_3]
    return ("| split curve, n=3 | " + " / ".join(f"{x:.2f}" for x in v)
            + f" | {mean(v):.2f} TFLOP/s |")


@claim("5.7.6-no-overlap", PAPER, "5.7.6",
       mixedProvenance=SPLIT_GEMM_MIX)
def noOverlap():
    """The section's central claim, and the one that survives a small sample. If the ranges ever
    overlap the sentence is false, so this raises rather than quietly rendering numbers that no
    longer support the surrounding prose."""
    t = [_peakTf(p) for p in TUNED_CLEAN_5]
    s = [_peakTf(p) for p in SPLIT_CLEAN_3]
    if min(s) <= max(t):
        raise ValueError(f"the ranges now OVERLAP: lowest split {min(s):.2f} is not above highest "
                         f"tuned {max(t):.2f}. The prose claims they do not overlap.")
    return f"{min(s):.2f} against\n{max(t):.2f}"


@claim("5.7.6-gap", PAPER, "5.7.6",
       mixedProvenance=SPLIT_GEMM_MIX)
def splitGap():
    t = mean(_peakTf(p) for p in TUNED_CLEAN_5)
    s = mean(_peakTf(p) for p in SPLIT_CLEAN_3)
    return f"The gap is **+{100 * (s / t - 1):.2f}%**"


# ---------------------------------------------------------------------------------------------
# 5.7.4 - the repair REMOVES the membw plateau, and the cost lands on gemm in 5.7.5.
# Three source files, two grids, and one of them is an overclocked run with the word
# "stock" in its filename. See specs/paper-5.7.4-claims.md before editing any of this.
# ---------------------------------------------------------------------------------------------

FIXED_MEMBW = "membw-anomaly-20260819/20260820-215336_5060ti-curvefixed-membw_sweep.csv"
FIXED_MEMBW_VOLTS = "membw-anomaly-20260819/20260820-215336_5060ti-curvefixed-membw_sweep_voltage.csv"
TUNED_MEMBW_13PT = "oc-comparison-20260819/20260819-162516_5060ti-oc-membw-stock_sweep.csv"
TUNED_MEMBW_VOLTS = "membw-anomaly-20260819/20260820-210822_5060ti-oc-volt-membw_sweep_voltage.csv"


def _r574ratioRange(path, targets):
    rows = voltageJoin(path)
    vals = [rows[t]["crossbar"] / rows[t]["mhz"] for t in targets]
    return min(vals), max(vals)


@claim("5.7.4-voltage-rises", PAPER, "5.7.4")
def voltageRises():
    rows = voltageJoin(FIXED_MEMBW_VOLTS)
    return (f"{rows[1545]['voltage']:.3f} V at 1545 MHz through "
            f"{rows[2010]['voltage']:.3f} V at 2010, against a")


@claim("5.7.4-crossbar-restored", PAPER, "5.7.4")
def crossbarRestored():
    tunedRows = voltageJoin(TUNED_MEMBW_VOLTS)
    tunedVolt = tunedRows[1867]["voltage"]
    tunedRatio = tunedRows[1867]["crossbar"] / tunedRows[1867]["mhz"]
    lo, hi = _r574ratioRange(FIXED_MEMBW_VOLTS, [1545, 1852, 2010])
    return (f"flat {tunedVolt:.3f} V on the tuned card - and the crossbar-to-core ratio "
            f"returns to {lo:.3f}-{hi:.3f} from {tunedRatio:.3f}.")


@claim("5.7.4-plateau-gone", PAPER, "5.7.4")
def plateauGone():
    return f"{sweep(FIXED_MEMBW)[1852]['throughput'] / 1e9:.1f} GB/s at 1852 MHz"


@claim("5.7.4-plateau-comparison", PAPER, "5.7.4")
def plateauComparison():
    fixed = sweep(FIXED_MEMBW)[1852]["throughput"]
    tuned = sweep(TUNED_MEMBW_13PT)[1852]["throughput"]
    return (f"against the tuned profile's {tuned / 1e9:.1f}, "
            f"{deltaPct(fixed, tuned)}.")


@claim("5.7.4-peak-throughput", PAPER, "5.7.4")
def peakThroughput():
    best = max(sweep(FIXED_MEMBW).values(), key=lambda r: r["throughput"])
    return f"{best['throughput'] / 1e9:.1f} GB/s peak against"


@claim("5.7.4-peak-comparison", PAPER, "5.7.4")
def peakComparison():
    fixedPeak = max(sweep(FIXED_MEMBW).values(), key=lambda r: r["throughput"])["throughput"]
    tunedPeak = max(sweep(TUNED_MEMBW_13PT).values(), key=lambda r: r["throughput"])["throughput"]
    gap = abs(1 - fixedPeak / tunedPeak) * 100
    return f"the tuned {tunedPeak / 1e9:.1f}, a {gap:.1f}% difference"


@claim("5.7.4-peak-power", PAPER, "5.7.4")
def peakPower():
    fixedW = sweep(FIXED_MEMBW)[2932]["power"]
    tunedW = sweep(TUNED_MEMBW_13PT)[2932]["power"]
    return f"{fixedW:.1f} W against {tunedW:.1f} W at 2932 MHz"


# ---------------------------------------------------------------------------------------------
# 5.7.6 continued - the clean bandwidth ceiling, and the two sustained-load runs
#
# This block exists because of what 2026-08-24 found in the prose above it. Section 5.7.6 was
# rewritten twice on 2026-08-23 and both rewrites landed as UNPINNED prose, which the audit
# cannot see. Re-deriving every number in it by hand turned up two sentences that quoted three
# different aggregation windows as though they were one, and one unqualified "no throttled
# sample" that was true only of the logger's narrower definition.
#
# Nothing here was wrong arithmetic. Every figure was a real measurement of something. What was
# missing was a machine that would have noticed the pairing, which is what these claims are.
# ---------------------------------------------------------------------------------------------

# The three membw sweeps that share the 10-point 1402-2100 fine grid, all measured under the
# clean protocol of 5.4.4. Do not substitute the 2026-08-21 split-curve membw sweep or the
# 2026-08-20 memory-only one: both predate the encoder guard, and the second of them is the
# contaminated reference this section was rewritten to remove.
CLEAN_CEILING_MEMBW = "memonly-clean-20260823/20260823-205231_5060ti-memonly-clean-membw-fine_sweep.csv"
DIRTY_CEILING_MEMBW = "membw-anomaly-20260819/20260820-181307_5060ti-memonly-membw-anomaly_sweep.csv"
# Two sweeps, for the same reason the split curve has three: read individually they give
# -0.39% and +0.58% against the memory-only reference, so a single one of them is not a
# measurement of anything. REPAIR_MEMBW_FINE is kept as a name for the first because the
# 2026-08-23 write-up quotes it specifically as the run that caught the contaminated
# reference; analytical claims use the list.
REPAIR_MEMBW_FINE = "curve-rebuild-20260823/20260823-202324_5060ti-curverebuilt-membw-fine_sweep.csv"
REPAIR_MEMBW_RUNS = [
    REPAIR_MEMBW_FINE,
    "repair-clean-20260824/20260824-214928_5060ti-repair-clean-membw-fine-r2_sweep.csv",
]
TUNED_MEMBW_CLEAN = "20260822-183112_5060ti-tuned-membw-clean_sweep.csv"
# TWO sweeps, averaged. n=1 was not enough: the two runs land at -0.11% and -0.73% against
# the ceiling, because one of them carries a 6.91% single-point dip and the other does not.
# Every claim that reads the split curve reads the mean of both, and none of them reports
# a per-point statistic any more - see 5.7.6-within-instability for why.
SPLIT_MEMBW_RUNS = [
    "splitcurve-clean-20260824/20260824-203810_5060ti-splitcurve-clean-membw-fine_sweep.csv",
    "splitcurve-clean-20260824/20260824-210054_5060ti-splitcurve-clean-membw-fine-r2_sweep.csv",
    "splitcurve-clean-20260824/20260824-211535_5060ti-splitcurve-clean-membw-fine-r3_sweep.csv",
]

# RESOLVED 2026-08-24. This constant used to carry a mixed-provenance caveat saying that the
# split curve's -3.18% deficit was an upper bound rather than a measurement, because its membw
# sweep predated the encoder guard while both references were verified-quiet. The clean
# re-measurement below settled it: the split curve rose 3.19% and the deficit was almost entirely
# the contaminant. The caveat is gone because the run it described is no longer used.
#
# Keep the old sweep in the repository and do NOT delete it - it is the evidence for the
# withdrawal, and two claims below quote the difference between the two runs.
SPLIT_MEMBW_OLD = "20260822-161921_5060ti-splitcurve-membw-r2_sweep.csv"

SPLIT_RUN = "20260823-183256_splitcurve"
OGTUNE_RUN = "20260823-192719_ogtune"


def _r576throughput(paths, target):
    """Mean throughput at one target across however many sweeps a configuration has."""
    return mean(sweep(p)[target]["throughput"] for p in paths)


@claim("5.7.6-tuned-spread", PAPER, "5.7.6")
def tunedSpread():
    """The table's spread column is the RANGE over the mean, not a standard deviation. The
    sentence below the table quotes a standard deviation ratio instead, and the two are pinned
    separately because they are different statistics that happen to sit two lines apart."""
    v = [_peakTf(p) for p in TUNED_CLEAN_5]
    return f"| {mean(v):.2f} TFLOP/s | {100 * (max(v) - min(v)) / mean(v):.2f}% |"


@claim("5.7.6-split-spread", PAPER, "5.7.6", mixedProvenance=SPLIT_GEMM_MIX)
def splitSpread():
    v = [_peakTf(p) for p in SPLIT_CLEAN_3]
    return f"| {mean(v):.2f} TFLOP/s | {100 * (max(v) - min(v)) / mean(v):.2f}% |"


@claim("5.7.6-spread-factor", PAPER, "5.7.6", mixedProvenance=SPLIT_GEMM_MIX)
def spreadFactor():
    """Raw standard deviations, not coefficients of variation. The two differ here - 4.5 against
    4.6 - and the sentence says "on standard deviation", so the raw ratio is what it means."""
    t = [_peakTf(p) for p in TUNED_CLEAN_5]
    s = [_peakTf(p) for p in SPLIT_CLEAN_3]
    tSpread = 100 * (max(t) - min(t)) / mean(t)
    sSpread = 100 * (max(s) - min(s)) / mean(s)
    return (f"{sSpread:.2f}% spread against {tSpread:.2f}%, "
            f"a factor of {stdev(t) / stdev(s):.1f} on")


@claim("5.7.6-peak-clocks", PAPER, "5.7.6",
       mixedProvenance="the split runs are mixed provenance, but this claim is about achieved CLOCK, and 5.4.4 measured that capture software does not move it - 2975.9 / 2976.5 / 2977.1 MHz with it enabled against 2977.0 disabled. The contaminant depresses throughput at a given clock; it does not change the clock reached.")
def peakClocks():
    def clockAtPeak(path):
        return max(sweep(path).values(), key=lambda r: r["throughput"])["mhz"]
    s = [clockAtPeak(p) for p in SPLIT_CLEAN_3]
    t = [clockAtPeak(p) for p in TUNED_CLEAN_5]
    if len({round(x, 1) for x in s}) != 1:
        raise ValueError(f"the three split runs no longer share one peak clock: {s}")
    return (f"All three split runs peaked at {s[0]:.1f} MHz achieved, against the tuned card's "
            f"{min(t):.1f}-{max(t):.1f} MHz.")


@claim("5.7.6-ceiling-rose", PAPER, "5.7.6",
       mixedProvenance="deliberately clean against contaminated - that difference is the quantity being measured. The 2026-08-20 memory-only sweep is schema 0.1.0 and recorded no video-engine telemetry at all, which is why it reads as unknown rather than merely unverified.")
def ceilingRose():
    """The correction that prompted the rewrite: the memory-only reference was contaminated, and
    re-measuring it clean moved it by roughly the amount 5.4.4 attributes to capture software."""
    clean = sweep(CLEAN_CEILING_MEMBW)
    dirty = sweep(DIRTY_CEILING_MEMBW)
    shared = sorted(set(clean) & set(dirty))
    if len(shared) != len(clean):
        raise ValueError(f"grids no longer match: {len(shared)} shared of {len(clean)}")
    d = [(clean[t]["throughput"] / dirty[t]["throughput"] - 1) * 100 for t in shared]
    return f"+{mean(d):.2f}%\non average, from +{min(d):.2f}% to +{max(d):.2f}%"


def _r576join(items):
    """"a, b and c" - the prose reads as English, so the rendering has to as well."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _r576word(n):
    small = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten", 20: "twenty", 30: "thirty",
             40: "forty", 50: "fifty", 60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}
    if n in small:
        return small[n]
    if 20 < n < 100:
        return small[n // 10 * 10] + "-" + small[n % 10]
    raise ValueError(f"no spelling for {n}; the prose that needs it should be rewritten")


@claim("5.7.6-clock-match", PAPER, "5.7.6")
def clockMatch():
    """The comparison is only meaningful if the three configurations reached the same clocks.

    Both halves are computed: the worst mismatch, and the tolerance that covers all but the two
    top-of-band points. Pinning only the worst case would let the typical case drift silently,
    and the typical case is what makes the -0.11% and -0.39% readable as real."""
    ceiling = sweep(CLEAN_CEILING_MEMBW)
    deltas = []
    for path in REPAIR_MEMBW_RUNS + SPLIT_MEMBW_RUNS:
        rows = sweep(path)
        deltas.extend(abs(rows[t]["mhz"] - ceiling[t]["mhz"]) for t in ceiling)
    deltas.sort(reverse=True)
    # One point per sweep misses by the same amount at the top of the band, so "above the
    # third largest" counts zero. Split on the worst VALUE, not on a rank.
    outliers = sum(1 for d in deltas if d >= deltas[0])
    sweeps = len(REPAIR_MEMBW_RUNS) + len(SPLIT_MEMBW_RUNS)
    if len(deltas) != 10 * sweeps:
        raise ValueError(f"expected ten points across {sweeps} sweeps, got {len(deltas)}")
    return (f"achieved clocks matched to {deltas[0]:.1f} MHz in the worst case\n"
            f"and to {deltas[outliers]:.1f} MHz at the other {_r576word(len(deltas) - outliers)}")


def _r576bandMean(path):
    """Mean throughput across the whole 10-point band, in GB/s.

    The band mean rather than a per-point comparison, because 2026-08-24 established that
    per-point statistics on this measurement move by up to a full percentage point between
    replicates of one untouched profile. Six sweeps of three configurations span 1.32%; the
    configurations themselves span 0.56%. Nothing finer than a band mean is supportable.
    """
    return mean(r["throughput"] for r in sweep(path).values()) / 1e9


def _r576configRow(label, paths):
    # A bare path is iterable, so without this a single sweep would be read one character at a
    # time and the "sweeps" column would print its filename length. The count is a number the
    # reader relies on, so it has to be a real count.
    if isinstance(paths, str):
        raise TypeError("pass a list of sweeps; a configuration measured once must say so")
    values = [_r576bandMean(p) for p in paths]
    spread = ("-" if len(values) == 1
              else f"**{100 * (max(values) - min(values)) / mean(values):.2f}%**")
    each = " / ".join(f"{v:.1f}" for v in values)
    bold = "" if len(values) == 1 else "**"
    return f"| {label} | {len(values)} | {each} | {bold}{mean(values):.1f}{bold} | {spread} |"


@claim("5.7.6-ceiling-row", PAPER, "5.7.6")
def ceilingRow():
    return _r576configRow("memory-only (stock curve)", [CLEAN_CEILING_MEMBW])


@claim("5.7.6-repair-row", PAPER, "5.7.6")
def repairRow():
    return _r576configRow("repaired curve", REPAIR_MEMBW_RUNS)


@claim("5.7.6-split-row", PAPER, "5.7.6")
def splitRow():
    return _r576configRow("split curve", SPLIT_MEMBW_RUNS)


@claim("5.7.6-resolution", PAPER, "5.7.6")
def resolution():
    """The load-bearing claim of the subsection: the configurations are closer than the noise.

    RAISES if that ever stops being true, because the sentence around it says no ranking is
    supported. A future measurement that separates them would need different prose, not a
    different number."""
    groups = [[CLEAN_CEILING_MEMBW], REPAIR_MEMBW_RUNS, SPLIT_MEMBW_RUNS]
    configMeans = [mean(_r576bandMean(p) for p in g) for g in groups]
    between = 100 * (max(configMeans) - min(configMeans)) / mean(configMeans)
    withinEach = [100 * (max(v) - min(v)) / mean(v) for v in
                  ([_r576bandMean(p) for p in g] for g in groups) if len(v) > 1]
    everySweep = [_r576bandMean(p) for g in groups for p in g]
    across = 100 * (max(everySweep) - min(everySweep)) / mean(everySweep)
    if between >= max(withinEach):
        raise ValueError(f"the configurations now separate: between {between:.2f}% against a "
                         f"within-configuration maximum of {max(withinEach):.2f}%. The prose says "
                         "no ranking is supported and would no longer be true.")
    return (f"span {between:.2f}%. A single configuration re-measured spans up to "
            f"{max(withinEach):.2f}%, and the six\nsweeps together span {across:.2f}%")


@claim("5.7.6-repair-above-ceiling", PAPER, "5.7.6")
def repairAboveCeiling():
    """The reference is exceeded, and the paragraph says why that is noise and not a finding."""
    ceiling = sweep(CLEAN_CEILING_MEMBW)
    rows = sweep(REPAIR_MEMBW_RUNS[1])
    d = [(rows[t]["throughput"] / ceiling[t]["throughput"] - 1) * 100 for t in sorted(ceiling)]
    return f"also sits **{mean(d):.2f}%** above it"


@claim("5.7.6-per-sweep-readings", PAPER, "5.7.6")
def perSweepReadings():
    """Every individual reading, on one line, so no future edit can quote one of them alone."""
    # Counts checked before any file is read, so a changed run list fails saying so rather than
    # surfacing as a missing CSV. Third time this pattern has been needed in one file - a guard
    # placed after the I/O reports the wrong problem.
    if len(SPLIT_MEMBW_RUNS) != 3 or len(REPAIR_MEMBW_RUNS) != 2:
        raise ValueError("the prose names three split and two repair sweeps; there are "
                         f"{len(SPLIT_MEMBW_RUNS)} and {len(REPAIR_MEMBW_RUNS)}")
    ceiling = sweep(CLEAN_CEILING_MEMBW)

    def against(path):
        rows = sweep(path)
        return mean((rows[t]["throughput"] / ceiling[t]["throughput"] - 1) * 100
                    for t in sorted(ceiling))

    split = [against(p) for p in SPLIT_MEMBW_RUNS]
    repair = [against(p) for p in REPAIR_MEMBW_RUNS]
    return ("give " + _r576join(f"**{v:.2f}%**" for v in split)
            + " against the memory-only reference, and the two repair\nsweeps give "
            + _r576join(f"**{v:+.2f}%**" for v in repair))


def _r576loadedFraction(label):
    run = stabilityRun(label)
    return 100 * run["session"]["loaded_fraction"]


def _r576powerCapped(label):
    run = stabilityRun(label)
    return sum(1 for s in run["samples"] if "SwPowerCap" in s["throttleReasons"])


@claim("5.7.6-split-loaded", PAPER, "5.7.6")
def splitLoaded():
    run = stabilityRun(SPLIT_RUN)
    return (f"{_r576loadedFraction(SPLIT_RUN):.1f}% of one-second samples above "
            f"{run['session']['loaded_threshold_pct']:.0f}% utilisation")


@claim("5.7.6-split-powercap", PAPER, "5.7.6")
def splitPowerCap():
    """The logger reports zero throttled samples because it counts only hardware slowdown and
    thermal events - the software power cap is normal operation and it says so at length. The
    paper used to repeat the zero without the qualification, which reads as a stronger claim
    than the telemetry supports."""
    run = stabilityRun(SPLIT_RUN)
    return f"{_r576powerCapped(SPLIT_RUN)} of\n{len(run['samples'])} samples reported the software power cap"


@claim("5.7.6-split-power-temp", PAPER, "5.7.6")
def splitPowerTemp():
    run = stabilityRun(SPLIT_RUN)
    loaded = loadedSamples(run)
    return (f"Power averaged {mean(s['power'] for s in loaded):.1f} W and peaked\n"
            f"at {max(s['power'] for s in run['samples']):.1f} W against a "
            f"{float(run['session']['power_limit_w']):.0f} W limit; temperature peaked at "
            f"{max(s['temperature'] for s in run['samples']):.0f} C.")


def _r576drift(label, workload):
    """The harness's own post-soak degradation figure, positive meaning a fall."""
    for entry in stabilityRun(label)["protocol"]["degradation"]:
        if entry["Workload"] == workload:
            return entry["DropPct"]
    raise ValueError(f"{label} has no {workload} degradation entry")


@claim("5.7.6-split-drift", PAPER, "5.7.6")
def splitDrift():
    return (f"`gemm` drifted\n{_r576drift(SPLIT_RUN, 'gemm'):.2f}% and `membw` "
            f"+{_r576drift(SPLIT_RUN, 'membw'):.2f}%")


@claim("5.7.6-ogtune-summary", PAPER, "5.7.6")
def ogtuneSummary():
    run = stabilityRun(OGTUNE_RUN)
    return (f"{run['protocol']['iterations']} iterations, zero aborted, zero driver resets, zero "
            f"thermal or hardware-slowdown\nsamples, {_r576powerCapped(OGTUNE_RUN)} of "
            f"{len(run['samples'])} at the software power cap, "
            f"{_r576loadedFraction(OGTUNE_RUN):.1f}%\nloaded, drift `gemm` "
            f"+{_r576drift(OGTUNE_RUN, 'gemm'):.2f}% and `membw`\n"
            f"{_r576drift(OGTUNE_RUN, 'membw'):.2f}%.")


@claim("5.7.6-sustained-gemm", PAPER, "5.7.6")
def sustainedGemm():
    """POST-SOAK, on both sides. The earlier version of this sentence took the split curve's
    figure from all sixteen iterations and the original tune's from its eleven post-soak ones,
    under prose declaring both post-soak."""
    s = iterationsIn(stabilityRun(SPLIT_RUN), "gemm", POST_SOAK)
    o = iterationsIn(stabilityRun(OGTUNE_RUN), "gemm", POST_SOAK)
    if len(s) != len(o):
        raise ValueError(f"the two runs no longer have matching post-soak counts: {len(s)}, {len(o)}")
    return (f"`gemm` {mean(s) / 1e12:.2f} TFLOP/s on the split curve against {mean(o) / 1e12:.2f} on the\n"
            f"original tune, a gap of +{100 * (mean(s) / mean(o) - 1):.2f}%.")


@claim("5.7.6-sustained-corroboration", PAPER, "5.7.6", mixedProvenance=SPLIT_GEMM_MIX)
def sustainedCorroboration():
    """The whole point of the paragraph: two designs sharing no methodology land in the same
    place. Both halves are computed, so neither can drift away from the other unnoticed."""
    lockedGap = 100 * (mean(_peakTf(p) for p in SPLIT_CLEAN_3)
                       / mean(_peakTf(p) for p in TUNED_CLEAN_5) - 1)
    sustainedGap = 100 * (mean(iterationsIn(stabilityRun(SPLIT_RUN), "gemm", POST_SOAK))
                          / mean(iterationsIn(stabilityRun(OGTUNE_RUN), "gemm", POST_SOAK)) - 1)
    return f"agree to within {abs(lockedGap - sustainedGap):.2f}\npercentage points"


def _r576membwGap(window):
    s = iterationsIn(stabilityRun(SPLIT_RUN), "membw", window)
    o = iterationsIn(stabilityRun(OGTUNE_RUN), "membw", window)
    return mean(s), mean(o), 100 * (mean(s) / mean(o) - 1)


@claim("5.7.6-sustained-membw", PAPER, "5.7.6")
def sustainedMembw():
    s, o, gap = _r576membwGap(POST_SOAK)
    return f"{s / 1e9:.1f} GB/s against {o / 1e9:.1f}, a difference of {gap:.2f}%"


@claim("5.7.6-membw-windows", PAPER, "5.7.6")
def membwWindows():
    """Reading the same comparison on all three windows is what makes "indistinguishable"
    a measurement rather than a hope: it is small and negative on each of them."""
    soakGap = _r576membwGap(SOAK)[2]
    wholeGap = _r576membwGap(WHOLE_RUN)[2]
    whole = iterationsIn(stabilityRun(SPLIT_RUN), "membw", WHOLE_RUN)
    if len(whole) != 17:
        raise ValueError(f"the whole-run window is no longer seventeen iterations: {len(whole)}")
    return f"{soakGap:.2f}% across the soak\niterations, {wholeGap:.2f}% across all seventeen"


@claim("5.7.6-boost-band", PAPER, "5.7.6")
def boostBand():
    """Where an unlocked card actually sits, which is what makes 5.7.2's locked-frequency
    plateau a laboratory result rather than a cost paid in ordinary use. Mean loaded clock of
    each run, so the range is across configurations rather than within one."""
    means = sorted(mean(s["smClock"] for s in loadedSamples(stabilityRun(label)))
                   for label in (SPLIT_RUN, OGTUNE_RUN))
    return f"at {means[0]:.0f}-{means[1]:.0f} MHz, above the flattened region entirely"


# --- the withdrawal, and the evidence that identifies it as contamination ---------------------
#
# These pin the numbers that make the second correction of this paragraph auditable. Without them
# the withdrawal is an assertion, which is precisely the shape the two withdrawn versions had.

# The two grid points known to carry a single-point dip: 1792 MHz in the withdrawn 2026-08-22
# sweep, 1867 MHz in the second 2026-08-24 sweep. Excluding both is what "the one known dip in
# each run excluded" means in the prose, and it is stated rather than trimmed silently.
DIP_POINTS = (1792, 1867)


def _r576oldVsNew(excludeDips=False):
    old = sweep(SPLIT_MEMBW_OLD)
    targets = [t for t in sorted(old) if not (excludeDips and t in DIP_POINTS)]
    return {t: (_r576throughput(SPLIT_MEMBW_RUNS, t) / old[t]["throughput"] - 1) * 100
            for t in targets}


@claim("5.7.6-split-rose", PAPER, "5.7.6",
       mixedProvenance="deliberately verified-quiet against declared-unverified - that difference "
                       "is the quantity being measured, and it is what withdrew the -3.18%.")
def splitRose():
    """Both figures, because the second is what makes the first not depend on the dips."""
    return (f"reads **+{mean(_r576oldVsNew().values()):.2f}%** above\n"
            f"its 2026-08-22 predecessor, or **+{mean(_r576oldVsNew(True).values()):.2f}%** "
            f"with the one known dip in each run excluded")


@claim("5.7.6-contamination-signature", PAPER, "5.7.6",
       mixedProvenance="deliberately verified-quiet against declared-unverified, for the same "
                       "reason as 5.7.6-split-rose.")
def contaminationSignature():
    """WITHDRAWN AS EVIDENCE, and pinned anyway so the withdrawal itself stays honest.

    This used to render a within-band decline as confirmation that the rise carried 5.4.4's
    frequency signature, and it asserted the direction so it would fail if that inverted. Two
    things were wrong with it. With both known dips removed the difference is 0.31 points, which
    is flat. And the test was never available on this grid: 5.4.4's boundary is near 2010 MHz and
    nine of these ten points sit below it, where 5.4.4 predicts a UNIFORM offset. The paragraph
    now cites these numbers as the reason the argument does not hold, so the guard is gone with
    it - there is no direction left to assert."""
    d = _r576oldVsNew(excludeDips=True)
    low = [v for t, v in d.items() if t <= 1710]
    high = [v for t, v in d.items() if t >= 1942]
    return f"flat: **+{mean(low):.2f}%** against **+{mean(high):.2f}%**"


@claim("5.7.6-dip-replicate", PAPER, "5.7.6")
def dipInReplicate():
    """The verified-quiet dip that withdrew the isolated-point argument."""
    return f"**{_r576dip(SPLIT_MEMBW_RUNS[1])[1]:.2f}%** hole of its own at {_r576dip(SPLIT_MEMBW_RUNS[1])[0]} MHz"


@claim("5.7.6-vs-tuned-band", PAPER, "5.7.6")
def splitVsTunedBand():
    """The claim that survived every rewrite: against the fully tuned profile the plateau is gone.

    Both sweeps are verified-quiet, so unlike the ceiling comparison this one has never rested on
    mixed evidence."""
    tuned = sweep(TUNED_MEMBW_CLEAN)
    d = [(_r576throughput(SPLIT_MEMBW_RUNS, t) / tuned[t]["throughput"] - 1) * 100
         for t in sorted(tuned)]
    return f"+{mean(d):.1f}% on average across the\nband, +{min(d):.1f}% to +{max(d):.1f}%"


# --- single-point membw dips in verified-quiet runs -------------------------------------------
#
# Added 2026-08-24, and it retires an explanation rather than adding one. The "wandering membw
# dip" had been attributed to the capture software of 5.4.4 since 2026-08-22 on the strength of
# both being transient and both moving between runs. Two of the five verified-quiet sweeps on this
# grid carry one, so whatever produces it, that is not what it is.

CLEAN_MEMBW_FINE = ([CLEAN_CEILING_MEMBW, TUNED_MEMBW_CLEAN]
                    + REPAIR_MEMBW_RUNS + SPLIT_MEMBW_RUNS)


def _r576dip(path):
    """The deepest single-point departure from the local trend, as (target, percent).

    Measured against the mean of a point's two neighbours rather than against another sweep,
    because the question is whether a run is internally consistent - a dip that appears in one
    sweep of a pair is not a property of the configuration and must not be read as one.
    """
    rows = sweep(path)
    targets = sorted(rows)
    residuals = []
    for i in range(1, len(targets) - 1):
        neighbours = (rows[targets[i - 1]]["throughput"] + rows[targets[i + 1]]["throughput"]) / 2
        residuals.append((targets[i], (rows[targets[i]]["throughput"] / neighbours - 1) * 100))
    return min(residuals, key=lambda entry: entry[1])


@claim("5.7.6-dip-spread", PAPER, "5.7.6")
def dipSpread():
    """The worst-point departure of every verified-quiet sweep, as a CONTINUUM.

    This replaces a claim that counted "two of five runs with a 6-7% dip". That count was a 3%
    threshold laid across a continuous distribution of five samples, and the sixth sweep landed
    at -2.17%, between the two groups it had invented. A spread cannot be discretised into a
    finding the way a count invites."""
    worst = sorted((_r576dip(p)[1] for p in CLEAN_MEMBW_FINE), reverse=True)
    return (f"runs from **{worst[0]:.2f}%** to **{worst[-1]:.2f}%**, with the others at "
            + _r576join(f"{v:.2f}%" for v in worst[1:-1]))


@claim("5.7.6-dip-pair", PAPER, "5.7.6")
def dipPair():
    """The same point in two sweeps of one untouched profile, twenty minutes apart.

    This is the claim that makes the dip a measurement property rather than a configuration
    property, so it is pinned separately from the depth figures."""
    target = _r576dip(SPLIT_MEMBW_RUNS[1])[0]
    # The pair the prose names: the run WITHOUT the bad point and the run with it. Indexing two
    # specific runs rather than unpacking the list, which silently broke when a third was added.
    a = sweep(SPLIT_MEMBW_RUNS[0])[target]["throughput"] / 1e9
    b = sweep(SPLIT_MEMBW_RUNS[1])[target]["throughput"] / 1e9
    return f"reads {a:.1f} GB/s in one sweep\nand {b:.1f} in another"


# --------------------------------------------------------------------------------------
# 5.5.3 - the 5060 Ti half of the cross-chip bus-saturation comparison
# --------------------------------------------------------------------------------------
# This claim renders into 5.5.3, which is otherwise served by claims_crosschip.py. It lives here
# because it reads 5060 Ti sweeps and that module is forbidden from doing so. Splitting on data
# ownership rather than section number is what keeps a cross-chip claim from quietly reaching a
# 5060 Ti file through a shared constant.

# 128-bit bus, double-pumped, at the memory clock each configuration actually ran. Computed per
# configuration rather than from one nominal figure: the memory overclock changes the denominator,
# and dividing an overclocked throughput by the stock bus is how "173% of theoretical peak" got
# into a README once already.
def _r553bus(memoryClockMhz):
    return memoryClockMhz * 2 * 16 / 1000


@claim("5.5.3-5060ti-bus", PAPER, "5.5.3",
       mixedProvenance="two of the three runs are schema 0.1.0 and record no video-engine telemetry. Capture contamination DEPRESSES throughput, so a contaminated run understates bus efficiency and would exaggerate the shortfall this claim reports. The direction therefore runs toward the finding - and the single verified-quiet run gives 78.3%, the HIGHEST of the three, so the best-provenance number is still 12 points below the 3070 Ti's 90.4%.")
def bus5060ti():
    stock = max(r["throughput"] for r in sweep(STOCK_MEMBW_VOLT).values()) / 1e9
    ocPeaks = [max(r["throughput"] for r in sweep(p).values()) / 1e9
               for p in (MEMONLY_MEMBW, CLEAN_CEILING_MEMBW)]
    fractions = ([100 * stock / _r553bus(13801)]
                 + [100 * p / _r553bus(16301) for p in ocPeaks])
    return f"**{min(fractions):.1f}-{max(fractions):.1f}%** of its own bus"


# ---------------------------------------------------------------------------------------------
# 5.6.1.1, added 2026-08-29: the twelve-workload consumer constrained result, computed on the
# COMMANDED frequency basis. Keyed by achieved clock these sweeps share only five frequencies and
# the comparison cannot run at all - see analyze_constrained.py's loadSweepCurves docstring.
#
# These claims RUN THE ANALYSIS rather than reading a stored table, so the audit fails if the
# analyser's behaviour changes under them. That costs about a second per run.

SUITE_PATTERNS = ("stock-suite-20260829/*_sweep.csv", "suite-pilot-20260829/*_sweep.csv")


def _suiteCurves():
    """The twelve stock suite workloads, keyed by commanded target."""
    import contextlib
    import io
    import sys
    from audit_claims import REPO_ROOT
    analysisDir = str(REPO_ROOT / "analysis")
    if analysisDir not in sys.path:
        sys.path.insert(0, analysisDir)
    import analyze_constrained as constrained
    curves = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for pattern in SUITE_PATTERNS:
            curves.update(constrained.loadSweepCurves(pattern, basis="commanded"))
    if len(curves) != 12:
        raise ValueError(f"expected 12 suite workloads, loaded {len(curves)}")
    return curves


def _fixedRow(floor):
    import contextlib
    import io
    import sys
    from audit_claims import REPO_ROOT
    analysisDir = str(REPO_ROOT / "analysis")
    if analysisDir not in sys.path:
        sys.path.insert(0, analysisDir)
    import analyze_constrained as constrained
    with contextlib.redirect_stdout(io.StringIO()):
        rows = constrained.reportFixedVersusPerWorkload(_suiteCurves(), [floor])
    if not rows:
        raise ValueError(f"no fixed frequency is feasible at a {floor:.0%} floor on the "
                         f"commanded basis - 5.6.1.1's table cannot be rendered")
    return rows[0]


@claim("5.6.1.1-shared-frequencies", PAPER, "5.6.1.1")
def suiteSharedFrequencies():
    """RAISES if the achieved basis ever stops being the smaller number.

    The whole argument for the commanded basis is that clamping collapses the shared grid. If the
    two counts ever match, the section's premise is gone and the prose needs rewriting rather than
    the number updating.
    """
    import contextlib
    import io
    import sys
    from audit_claims import REPO_ROOT
    analysisDir = str(REPO_ROOT / "analysis")
    if analysisDir not in sys.path:
        sys.path.insert(0, analysisDir)
    import analyze_constrained as constrained
    counts = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for basis in ("achieved", "commanded"):
            curves = {}
            for pattern in SUITE_PATTERNS:
                curves.update(constrained.loadSweepCurves(pattern, basis=basis))
            counts[basis] = len(set.intersection(
                *[{round(p["mhz"]) for p in v} for v in curves.values()]))
    if counts["achieved"] >= counts["commanded"]:
        raise ValueError(f"the achieved basis no longer shares fewer frequencies "
                         f"({counts['achieved']}) than the commanded one ({counts['commanded']})")
    return f"share only **{counts['achieved']}** achieved clocks"


@claim("5.6.1.1-floor-row-95", PAPER, "5.6.1.1")
def suiteFloorRow95():
    row = _fixedRow(0.95)
    return (f"| **{row['floor']:.0%}** | **{row['per_workload_pct']:.1f}%** | "
            f"**{row['fixed_pct']:.1f}%** | **{row['fixed_mhz']:.0f} MHz** | "
            f"**{row['gap_pp']:.1f} pp** | **{row['share_pct']:.0f}%** |")


@claim("5.6.1.1-share-beats-v100", PAPER, "5.6.1.1")
def suiteShareBeatsV100():
    """RAISES if the consumer share ever falls below the V100's 83%.

    The sentence says the consumer case is the stronger one. If it stops being so, that is a
    finding about the suite and not a number to quietly update.
    """
    share = _fixedRow(0.95)["share_pct"]
    if share <= 83:
        raise ValueError(f"consumer share {share:.0f}% no longer exceeds the V100's 83%")
    return f"**{share:.0f}% of the available efficiency gain requires knowing which workload is\nrunning** — against 83% on the V100"


@claim("5.6.1.1-achieved-spread", PAPER, "5.6.1.1")
def suiteAchievedSpread():
    """What the twelve workloads actually held at the fixed policy's chosen target.

    The point of the commanded basis is that this spread exists and an achieved-keyed analysis
    cannot see it, so it is pinned rather than described.
    """
    row = _fixedRow(0.95)
    target = round(row["fixed_mhz"])
    held = []
    for points in _suiteCurves().values():
        held += [p["achieved_mhz"] for p in points if round(p["mhz"]) == target]
    return (f"**{min(held):.0f} to {max(held):.0f} MHz, a spread of "
            f"{max(held) - min(held):.0f} MHz**")


# ---------------------------------------------------------------------------------------------
# 5.6.2.1: the constrained MODEL comparison retested on consumer silicon. These run the
# leave-one-workload-out evaluation, which is why the audit costs a few seconds - the alternative
# is a stored table that cannot notice the model changing underneath it.

def _consumerLoo(floor=0.95):
    import contextlib
    import io
    import sys
    from audit_claims import REPO_ROOT
    for directory in (REPO_ROOT / "analysis", REPO_ROOT / "analysis" / "models"):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    import predict_constrained_frequency as predictor
    with contextlib.redirect_stdout(io.StringIO()):
        dataset = predictor.loadConsumerDataset()
        result = predictor.runLeaveOneWorkloadOut(
            dataset, floor, probeFrequencies=predictor.CONSUMER_PROBE_FREQUENCIES_MHZ)
    return result["scores"]


@claim("5.6.2.1-interpolation-row", PAPER, "5.6.2.1")
def consumerInterpolationRow():
    s = _consumerLoo()
    return (f"| **interpolation between the four probes, no fit** | "
            f"**{s.loc['interpolation (no fit)', 'mean_gain_pct']:.1f}%** | "
            f"**{s.loc['interpolation (no fit)', 'floor_violations']:.0f}** |")


@claim("5.6.2.1-fitting-earns-nothing", PAPER, "5.6.2.1")
def consumerFittingEarnsNothing():
    """RAISES if a fitted variant ever beats plain interpolation on the consumer suite.

    This is the half of the result that says the FITTING earns nothing. If a calibrated fit
    overtakes interpolation, 5.6.2.1's conclusion is inverted and the prose must be rewritten
    rather than the numbers refreshed.
    """
    s = _consumerLoo()
    calibrated = s.loc["probe model (calibrated)", "mean_gain_pct"]
    interpolation = s.loc["interpolation (no fit)", "mean_gain_pct"]
    if calibrated >= interpolation:
        raise ValueError(f"the calibrated fit now beats interpolation on the consumer suite, "
                         f"{calibrated:.1f}% against {interpolation:.1f}%")
    return f"falls to {calibrated:.1f}%, below the {interpolation:.1f}%"


@claim("5.6.2.1-ridge-breaks-floor", PAPER, "5.6.2.1")
def consumerRidgeBreaksFloor():
    """RAISES if Ridge ever keeps the floor here - the sentence says it only leads by breaking it."""
    violations = _consumerLoo().loc["probe model (ridge)", "floor_violations"]
    if violations <= 0:
        raise ValueError("Ridge no longer breaks the floor on the consumer suite")
    return f"breaking the floor on {violations:.0f} of 12"


@claim("5.6.2.1-fixed-breaks-floor", PAPER, "5.6.2.1")
def consumerFixedBreaksFloor():
    """The fixed baseline breaking the floor is the consumer-specific part of this result.

    RAISES if it stops, because the paragraph's claim is that a single frequency is infeasible at
    a 95% floor across this spread of workloads - not that it merely scores badly.
    """
    violations = _consumerLoo().loc["best fixed frequency", "floor_violations"]
    if violations <= 0:
        raise ValueError("the fixed baseline no longer breaks the floor on the consumer suite - "
                         "5.6.2.1 says it does, and that is the consumer-specific finding")
    return f"**One workload of twelve.**" if violations == 1 else f"{violations:.0f} of twelve"


# --------------------------------------------------------------------------------------
# 3.3 / 5.5 - the declared arithmetic intensity column
#
# WHY THIS IS PINNED, AND WHY A TEST WAS NOT ENOUGH
#     The FLOP/byte column is the axis 5.5's central result is plotted against: the performance
#     cost of the optimum tracks arithmetic intensity, with the transition between bgemm64 and
#     bgemm128 landing where the roofline knee was measured independently. Nothing checked it.
#
#     test_gpu_workload.py appears to. It compares suiteDeclaredIntensity() against a longhand
#     builderIntensity() written out in the test file, deliberately not importing from the
#     builder so the two derivations stay independent. But buildSuiteWorkload() - the code that
#     actually runs on the card - is in NEITHER side of that comparison. Mutation testing on
#     2026-08-30 changed six of its coefficients one at a time (softmax 5.0 to 4.0, layernorm
#     8.0 to 6.0, conv's 2.0 to 1.0, attention's 4.0 to 2.0, and two byte counts) and all six
#     survived the full suite. The check compares two copies of the formula; the third copy is
#     the one that ships.
#
#     Fixing that properly means extracting the builder's arithmetic so the runtime path is the
#     tested path. That is a change to the collection tool, and the 3070 Ti runs are still to be
#     taken with it, so it waits until after collection. THIS claim is the interim guard: it is
#     additive, touches no collection code, and if a coefficient ever drifts the README table
#     stops matching the formula and the audit fails.
#
#     It pins suiteDeclaredIntensity, not the builder, so it does not close the gap above - it
#     bounds the damage. A drift in the builder alone still goes unnoticed.
# --------------------------------------------------------------------------------------

import sys as _sys
from audit_claims import REPO_ROOT as _REPO_ROOT

# gpu_workload defers `import torch` into the function that needs it, so importing the module
# here costs nothing and works on a machine with no CUDA - which is what lets CI run this.
_sys.path.insert(0, str(_REPO_ROOT / "tools" / "frequency-sweep"))
from gpu_workload import LADDER_SIZES, suiteDeclaredIntensity  # noqa: E402

SUITE_README = "data/frequency-sweeps/stock-suite-20260829/README.md"

# `gemm` appears in the same table at 1365 but is the legacy workload, not a suite one -
# suiteDeclaredIntensity raises on it - so it is not pinned here.
SUITE_INTENSITY_NAMES = (["copy", "reduce", "softmax", "layernorm"]
                         + [f"bgemm{n}" for n in LADDER_SIZES]
                         + ["attention", "conv"])


def formatIntensity(value):
    """Render one cell exactly as the table writes it.

    Three shapes, and they are the table's, not a preference: an exact zero is written `0`
    rather than `0.00`; a whole number at or above 100 drops its decimals (`256`, `288`);
    everything else takes two places. Changing this changes what the document must say.
    """
    if value == 0:
        return "0"
    if float(value).is_integer() and value >= 100:
        return str(int(value))
    return f"{value:.2f}"


def _registerIntensityClaim(name):
    def render():
        return f"| `{name}` | {formatIntensity(suiteDeclaredIntensity(name))} |"
    render.__name__ = f"intensity_{name}"
    render.__doc__ = (f"{name}'s FLOP/byte cell, computed from operation counts rather than "
                      f"read back from the table it is checking.")
    claim(f"5.5-intensity-{name}", SUITE_README)(render)


for _name in SUITE_INTENSITY_NAMES:
    _registerIntensityClaim(_name)


# --------------------------------------------------------------------------------------
# 5.5 - the suite table's measured columns
#
# WHY THESE EXIST, AND WHAT THEY COST BY NOT EXISTING SOONER
#     The FLOP/byte column was pinned earlier on 2026-08-30. The three MEASURED columns beside
#     it - efficiency gain, performance cost, power saved - were not, and one of them was wrong.
#     `attention` read 55.6% / 46.3% / 65.5% against its own CSV's 53.7% / 45.9% / 64.8%. The
#     other eleven rows agreed to within rounding, so it was a transcription error rather than a
#     computation one, and it survived from 2026-08-29 until a replicate was collected and the
#     recomputed r1 value disagreed with the table.
#
#     That is the failure audit_claims.py was built for, appearing in the one part of the table
#     nothing rendered. Each claim below pins a row through its gain column, computed from the
#     CSV, so the same error fails the audit rather than waiting for someone to recompute it.
# --------------------------------------------------------------------------------------

SUITE_R1_SWEEPS = {
    "copy": "suite-pilot-20260829/20260829-142703_5060ti-stock-suitepilot-copy_sweep.csv",
    "reduce": "stock-suite-20260829/20260829-151627_5060ti-stock-suite-reduce_sweep.csv",
    "softmax": "stock-suite-20260829/20260829-152055_5060ti-stock-suite-softmax_sweep.csv",
    "layernorm": "stock-suite-20260829/20260829-152513_5060ti-stock-suite-layernorm_sweep.csv",
    "bgemm32": "stock-suite-20260829/20260829-150242_5060ti-stock-suite-bgemm32_sweep.csv",
    "bgemm64": "stock-suite-20260829/20260829-150701_5060ti-stock-suite-bgemm64_sweep.csv",
    "bgemm128": "suite-pilot-20260829/20260829-143124_5060ti-stock-suitepilot-bgemm128_sweep.csv",
    "bgemm256": "stock-suite-20260829/20260829-151122_5060ti-stock-suite-bgemm256_sweep.csv",
    "bgemm1024": "suite-pilot-20260829/20260829-143601_5060ti-stock-suitepilot-bgemm1024_sweep.csv",
    "attention": "stock-suite-20260829/20260829-152936_5060ti-stock-suite-attention_sweep.csv",
    "conv": "suite-pilot-20260829/20260829-144105_5060ti-stock-suitepilot-conv_sweep.csv",
    "gemm": "stock-suite-20260829/20260829-145752_5060ti-stock-gemm-1237grid_sweep.csv",
}


def suiteRowFigures(relativePath):
    """(optimum MHz, efficiency gain %, performance cost %) for one sweep.

    The reference point is the highest ACHIEVED clock in the sweep, not the highest commanded
    one: above ~2310 MHz each workload clamps to a different sustained clock, so the top target
    is not a frequency any of them actually ran at. This mirrors analyze_sweep.describe().
    """
    rows = list(sweep(relativePath).values())
    peak = max(rows, key=lambda row: row["efficiency"])
    fastest = max(rows, key=lambda row: row["mhz"])
    return (peak["mhz"],
            100.0 * (peak["efficiency"] / fastest["efficiency"] - 1.0),
            100.0 * (1.0 - peak["throughput"] / fastest["throughput"]))


def _registerSuiteRowClaim(name):
    def render():
        optimum, gain, _ = suiteRowFigures(SUITE_R1_SWEEPS[name])
        return (f"| `{name}` | {formatIntensity(suiteDeclaredIntensity(name)) if name != 'gemm' else '1365'} "
                f"| {optimum:.0f} MHz | {gain:.1f}% |")
    render.__name__ = f"suiteRow_{name}"
    render.__doc__ = (f"{name}'s row through the efficiency-gain column, recomputed from its "
                      f"sweep CSV rather than read back from the table it checks.")
    claim(f"5.5-suite-row-{name}", SUITE_README)(render)


for _name in SUITE_R1_SWEEPS:
    _registerSuiteRowClaim(_name)


# --------------------------------------------------------------------------------------
# 3.3.1 - the saturation probes
#
# These sat unpinned while 3.3.1 carried a DRAFT marker, and the marker was doing the work a
# claim should: signalling "not checked" rather than making checking unnecessary. The section's
# argument rests on two independent methods landing at the same ceiling, so the two numbers that
# have to agree are exactly the two worth rendering from the data.
#
# The 2800 MHz band of the unrolled-kernel probe is deliberately NOT pinned: it sampled the
# memory clock at an idle P-state and its derived peak is wrong by a factor of two, which shows
# up as unroll-1 reading 173% of "peak". See data/probes/README-saturation.md. Pinning a number
# from it would give a wrong figure the appearance of an audited one.
# --------------------------------------------------------------------------------------

import json as _json

PROBE_ISSUE_CEILING = "data/probes/probe_issue_ceiling_result.json"
PROBE_UNROLLED = "data/probes/probe_unrolled_kernel_result.json"


def _probe(relativePath):
    with open(_REPO_ROOT / relativePath, encoding="utf-8-sig") as handle:
        return _json.load(handle)


@claim("3.3.1-concurrency-ceiling", PAPER, "3.3.1")
def concurrencyCeiling():
    """Four streams against one, at 1395 MHz. The sentence pins both numbers because the CLAIM is
    that concurrency lifts throughput and then stops, which one number cannot express."""
    data = _probe(PROBE_ISSUE_CEILING)["aggregate_gbs"]
    return (f"four independent copies on separate streams at 1395 MHz reach "
            f"{data['4']:.1f} GB/s\naggregate, against {data['1']:.1f} for one")


@claim("3.3.1-unroll-spread", PAPER, "3.3.1")
def unrollSpread():
    """Unroll 1 against unroll 16 at 1395 MHz - a 16x change in memory-level parallelism."""
    unrolled = _probe(PROBE_UNROLLED)["results"]["1400"]["unrolled"]
    return (f"At 1395 MHz it delivers {unrolled['1']:.1f} GB/s at unroll 1 and "
            f"{unrolled['16']:.1f} at unroll 16")


@claim("3.3.1-methods-agree", PAPER, "3.3.1")
def methodsAgree():
    """The load-bearing sentence of 3.3.1: two unrelated mechanisms for raising memory-level
    parallelism land on the same ceiling. Rendered as a BOUND, because the sentence states one -
    and the bound is what makes the agreement an argument rather than a coincidence."""
    concurrency = _probe(PROBE_ISSUE_CEILING)["aggregate_gbs"]["4"]
    unrolled = _probe(PROBE_UNROLLED)["results"]["1400"]["unrolled"]["16"]
    spread = abs(unrolled / concurrency - 1.0) * 100.0
    import math
    bound = math.ceil(spread * 100) / 100
    return f"agree to within {bound:.2f}% ({concurrency:.1f} against {unrolled:.1f} GB/s)"


# --------------------------------------------------------------------------------------
# 5.4.5 - what reproduces between sessions
#
# Three complete stock collections of the twelve-workload suite: r1 (2026-08-29), r2 (08-30),
# r3 (09-02). These claims recompute the spread from all 36 CSVs rather than storing it, so a
# re-measured replicate or an edited paper both fail the audit.
#
# THE FILES CANNOT BE GLOBBED, which is why all three maps are written out. r1's gemm sweep is
# named `stock-gemm-1237grid` rather than `stock-suite-gemm`, so a `*gemm*` pattern matches
# `bgemm1024` instead and yields a plausible wrong number - that happened once during analysis.
# And `bgemm64-r3` exists in TWO directories: this replicate, and the third of four bgemm64
# repeats collected during the r2 session. Resolve by directory, never by tag.
# --------------------------------------------------------------------------------------

SUITE_R2_DIR = "suite-replicate-r2-20260830"
SUITE_R3_DIR = "suite-replicate-r3-20260902"

SUITE_R2_SWEEPS = {
    "copy": f"{SUITE_R2_DIR}/20260830-131414_5060ti-stock-suite-copy-r2_sweep.csv",
    "reduce": f"{SUITE_R2_DIR}/20260830-131835_5060ti-stock-suite-reduce-r2_sweep.csv",
    "softmax": f"{SUITE_R2_DIR}/20260830-132304_5060ti-stock-suite-softmax-r2_sweep.csv",
    "layernorm": f"{SUITE_R2_DIR}/20260830-132723_5060ti-stock-suite-layernorm-r2_sweep.csv",
    "bgemm32": f"{SUITE_R2_DIR}/20260830-133147_5060ti-stock-suite-bgemm32-r2_sweep.csv",
    "bgemm64": f"{SUITE_R2_DIR}/20260830-133608_5060ti-stock-suite-bgemm64-r2_sweep.csv",
    "bgemm128": f"{SUITE_R2_DIR}/20260830-134028_5060ti-stock-suite-bgemm128-r2_sweep.csv",
    "bgemm256": f"{SUITE_R2_DIR}/20260830-134503_5060ti-stock-suite-bgemm256-r2_sweep.csv",
    "bgemm1024": f"{SUITE_R2_DIR}/20260830-135007_5060ti-stock-suite-bgemm1024-r2_sweep.csv",
    "attention": f"{SUITE_R2_DIR}/20260830-135511_5060ti-stock-suite-attention-r2_sweep.csv",
    "conv": f"{SUITE_R2_DIR}/20260830-140020_5060ti-stock-suite-conv-r2_sweep.csv",
    "gemm": f"{SUITE_R2_DIR}/20260830-140529_5060ti-stock-suite-gemm-r2_sweep.csv",
}

SUITE_R3_SWEEPS = {
    "copy": f"{SUITE_R3_DIR}/20260902-190250_5060ti-stock-suite-copy-r3_sweep.csv",
    "reduce": f"{SUITE_R3_DIR}/20260902-190713_5060ti-stock-suite-reduce-r3_sweep.csv",
    "softmax": f"{SUITE_R3_DIR}/20260902-191142_5060ti-stock-suite-softmax-r3_sweep.csv",
    "layernorm": f"{SUITE_R3_DIR}/20260902-191602_5060ti-stock-suite-layernorm-r3_sweep.csv",
    "bgemm32": f"{SUITE_R3_DIR}/20260902-192026_5060ti-stock-suite-bgemm32-r3_sweep.csv",
    "bgemm64": f"{SUITE_R3_DIR}/20260902-192446_5060ti-stock-suite-bgemm64-r3_sweep.csv",
    "bgemm128": f"{SUITE_R3_DIR}/20260902-192906_5060ti-stock-suite-bgemm128-r3_sweep.csv",
    "bgemm256": f"{SUITE_R3_DIR}/20260902-193343_5060ti-stock-suite-bgemm256-r3_sweep.csv",
    "bgemm1024": f"{SUITE_R3_DIR}/20260902-193847_5060ti-stock-suite-bgemm1024-r3_sweep.csv",
    "attention": f"{SUITE_R3_DIR}/20260902-194351_5060ti-stock-suite-attention-r3_sweep.csv",
    "conv": f"{SUITE_R3_DIR}/20260902-194901_5060ti-stock-suite-conv-r3_sweep.csv",
    "gemm": f"{SUITE_R3_DIR}/20260902-195410_5060ti-stock-suite-gemm-r3_sweep.csv",
}

REPLICATES = (SUITE_R1_SWEEPS, SUITE_R2_SWEEPS, SUITE_R3_SWEEPS)


def _relativeSpread(values):
    """Range as a percentage of the mean - the statistic 5.4.5's table reports."""
    return 100.0 * (max(values) - min(values)) / mean(values)


def _sharedTargets(name):
    """Commanded frequencies present in all three replicates of one workload."""
    keyed = [sweep(table[name]) for table in REPLICATES]
    shared = set(keyed[0])
    for one in keyed[1:]:
        shared &= set(one)
    return keyed, sorted(shared)


def _spreadsFor(field):
    """Mean per-point spread of one measured field, averaged over the twelve workloads."""
    perWorkload = []
    for name in SUITE_R1_SWEEPS:
        keyed, targets = _sharedTargets(name)
        perWorkload.append(mean(_relativeSpread([k[t][field] for k in keyed]) for t in targets))
    return mean(perWorkload)


def _gainSpreads():
    """Per-workload range of the reported efficiency gain, in percentage POINTS not percent."""
    out = {}
    for name, relativePath in SUITE_R1_SWEEPS.items():
        gains = [suiteRowFigures(table[name])[1] for table in REPLICATES]
        out[name] = max(gains) - min(gains)
    return out


@claim("5.4.5-throughput-spread", PAPER, "5.4.5")
def replicateThroughputSpread():
    """Throughput is the quantity the project's existing ~0.76% figure describes."""
    return f"| throughput | **{_spreadsFor('throughput'):.2f}%** |"


@claim("5.4.5-power-spread", PAPER, "5.4.5")
def replicatePowerSpread():
    """Power, the term every efficiency figure divides by, and the dominant noise source."""
    return f"| power | **{_spreadsFor('power'):.2f}%** |"


@claim("5.4.5-efficiency-spread", PAPER, "5.4.5")
def replicateEfficiencySpread():
    """Efficiency tracks power rather than throughput - that is the section's whole point."""
    return f"| efficiency (throughput per watt) | **{_spreadsFor('efficiency'):.2f}%** |"


@claim("5.4.5-gain-spread", PAPER, "5.4.5")
def replicateGainSpread():
    """The derived gain, in percentage POINTS. Rendered to match the table's own wording."""
    return (f"| reported efficiency gain | **{mean(_gainSpreads().values()):.2f} percentage "
            f"points** |")


@claim("5.4.5-power-versus-throughput", PAPER, "5.4.5")
def powerIsTheDominantTerm():
    """The ratio the section leads with. Rendered as a bound so it states the direction."""
    factor = _spreadsFor("power") / _spreadsFor("throughput")
    return f"It reproduces {factor:.1f} times worse"


@claim("5.4.5-gain-range", PAPER, "5.4.5")
def gainSpreadRange():
    """Best and worst reproducing workloads. Both are named because the RANGE is the claim -
    a mean alone would hide that one workload moves eleven times as much as another."""
    spreads = _gainSpreads()
    best = min(spreads, key=spreads.get)
    worst = max(spreads, key=spreads.get)
    return (f"from {spreads[best]:.1f} points (`{best}`) to {spreads[worst]:.1f} points "
            f"(`{worst}`)")


@claim("5.4.5-anchor-refutation", PAPER, "5.4.5")
def topPointIsNotTheNoisiest():
    """The refuted hypothesis. Pinned because a claim that only recorded the conclusion would
    not fail if the underlying numbers moved enough to reverse it."""
    byTarget = {}
    for name in SUITE_R1_SWEEPS:
        keyed, targets = _sharedTargets(name)
        for target in targets:
            byTarget.setdefault(target, []).append(
                _relativeSpread([k[target]["throughput"] for k in keyed]))
    ordered = sorted(byTarget)
    top = mean(byTarget[ordered[-1]])
    rest = mean(mean(byTarget[t]) for t in ordered[:-1])
    worst = max(ordered, key=lambda t: mean(byTarget[t]))
    return (f"{ordered[-1]:.0f} MHz reproduces to {top:.2f}% against {rest:.2f}% averaged over "
            f"every other point, and the worst point is {worst:.0f} MHz at "
            f"{mean(byTarget[worst]):.2f}%")


# --------------------------------------------------------------------------------------
# The status header - the one place the auditor could not previously audit
#
# A council review of the paper found the header advertising "143 numbers are pinned" while the
# real count was 192. That is the failure this whole file exists to prevent, sitting in the
# paragraph that ADVERTISES the mechanism, and nothing caught it because nothing pinned it.
#
# The claim below is deliberately SELF-REFERENTIAL: it counts itself, so adding any future claim
# forces the header to be updated or the audit fails. That is the intended friction. It is also
# why the number in the paper is one higher than the count before this claim existed.
#
# IT IS ALSO GUARDED, and the first version of it broke CI for exactly the reason the guard now
# exists. claims_reference.py registers 24 claims ONLY when data/raw/ is present, and that
# dataset is gitignored and fetched rather than committed - so the registry totals 193 on a
# machine that has it and 169 on one that does not. An unguarded count renders whichever number
# the environment produces and fails wherever the paper disagrees, which is both CI legs of the
# "checks" job. The guard is the same condition claims_reference.py itself uses, so this claim
# registers exactly where the count it reports is the complete one: locally, and in the CI job
# named "V100 reference claims" that fetches the dataset before auditing.
#
# THE SKIP IS NOT A PASS, for the same reason that module says so: a green audit without the
# dataset has not checked this number either.
# --------------------------------------------------------------------------------------

def _referenceDataPresent():
    """Whether the V100 set is fetched, and therefore whether CLAIMS is the complete registry."""
    return (_REPO_ROOT / "data" / "raw" / "dataset_performance.csv").exists()


if _referenceDataPresent():
    @claim("header-pinned-count", PAPER)
    def headerPinnedCount():
        """The header's own advertised claim count, rendered from the live registry.

        ⚠️ THE WHOLE REGISTRY, NOT ONLY THE PAPER'S SHARE, AND THAT WAS CHECKED RATHER THAN
        ASSUMED. When claims_repo.py began pinning numbers in CLAUDE.md on 2026-09-05 this was
        briefly narrowed to document == PAPER, on the reasoning that a count in the paper's header
        describes the paper. Reading the sentence settled it the other way: it says "numbers are
        pinned by analysis/audit_claims.py", which is a statement about the TOOL's coverage, and
        the registry had already included 27 claims on two data READMEs long before CLAUDE.md
        joined it. Narrowing it would have reported 177 and silently redefined a published figure.
        """
        return f"**{len(CLAIMS)} numbers are pinned by `analysis/audit_claims.py`**"


# --------------------------------------------------------------------------------------
# 3.5 - the real driver crash of 2026-08-30
#
# WHY THIS DOES NOT USE stabilityRun(). That loader requires all four artifacts a completed run
# writes - protocol, session, iterations and samples - and this run has only the samples. The
# operator stopped it on seeing the crash, so neither JSON was ever written. That is not an
# inconvenience to work around; it is the fact 3.5 reports when it says the UNSTABLE verdict was
# reconstructed rather than emitted. A claim that quietly reached for the missing files would be
# asserting the run completed.
#
# The samples exist at all because the logger flushes each row as it writes it, which is what
# lets the record cover the four-second gap where sampling itself stopped.
# --------------------------------------------------------------------------------------

CRASH_SAMPLES = "data/stability-runs/20260830-123609_uv-875mv-3ghz_samples.csv"


def _crashSamples():
    """Every telemetry row of the crashed run, in order."""
    rows = []
    with open(_REPO_ROOT / CRASH_SAMPLES, encoding="utf-8-sig") as handle:
        import csv as _csv
        for raw in _csv.DictReader(handle):
            rows.append({
                "mhz": float(raw["sm_clock_mhz"]),
                "memory": float(raw["memory_clock_mhz"]),
                "watts": float(raw["power_draw_w"]),
                "util": float(raw["gpu_utilization_pct"]),
            })
    return rows


def _largestPowerDrop():
    """The consecutive pair with the steepest fall in power. Found rather than indexed, so the
    claim keeps pointing at the event and not at a row number that a re-export could shift."""
    rows = _crashSamples()
    pairs = zip(rows, rows[1:])
    return max(pairs, key=lambda pair: pair[0]["watts"] - pair[1]["watts"])


@claim("3.5-crash-signature", PAPER, "3.5")
def crashSignature():
    """The failure signature: power collapses while utilisation still reads 100%. Both samples are
    rendered because the CLAIM is that the counter did not move while the power did, which one
    number cannot express."""
    before, after = _largestPowerDrop()
    return (f"{before['watts']:.2f} W to {after['watts']:.2f} W in one second while the card still "
            f"reported {before['mhz']:.0f} MHz and {before['util']:.0f}% utilisation")


@claim("3.5-offsets-cleared", PAPER, "3.5")
def offsetsCleared():
    """The memory clock either side of the reset. 16301 is the +2500 offset, 13801 is stock, and
    the difference is the whole reason a run continued past this point would have been measuring
    something other than what its settings string claimed."""
    before, _ = _largestPowerDrop()
    final = _crashSamples()[-1]
    return f"read {before['memory']:.0f} MHz before the event and {final['memory']:.0f}"


# --------------------------------------------------------------------------------------
# 5.7.3 - the crossbar mechanism
#
# This is the largest original finding in the paper and it carried NO claims until 2026-09-04:
# its table was checked by eye when written and never again. The two extracts below are the
# distilled HWiNFO joins committed beside the sweeps they came from, and every figure 5.7.3
# quotes is recomputed from them here.
#
# The ratio is crossbar / ACHIEVED core clock, not crossbar / target. The card undershoots its
# lock at several of these points, and dividing by a clock it did not reach would understate the
# stock ratio at exactly the points where the argument needs it to be near unity.
# --------------------------------------------------------------------------------------

VOLT_DIR = "data/frequency-sweeps/membw-anomaly-20260819/"
VOLT_STOCK = VOLT_DIR + "20260820-211630_5060ti-stock-volt-membw_sweep_voltage.csv"
VOLT_TUNED = VOLT_DIR + "20260820-210822_5060ti-oc-volt-membw_sweep_voltage.csv"


def _voltageExtract(relativePath):
    """One distilled HWiNFO join, keyed by commanded target."""
    import csv as _csv
    out = {}
    with open(_REPO_ROOT / relativePath, encoding="utf-8-sig") as handle:
        for raw in _csv.DictReader(handle):
            out[int(raw["target"])] = {
                "achieved": float(raw["achieved"]),
                "throughput": float(raw["throughputGbs"]),
                "voltage": float(raw["voltage"]),
                "crossbar": float(raw["crossbar"]),
            }
    return out


def _ratios(relativePath):
    """Crossbar-to-core ratio at every point, ordered by target."""
    rows = _voltageExtract(relativePath)
    return [rows[t]["crossbar"] / rows[t]["achieved"] for t in sorted(rows)]


@claim("5.7.3-stock-ratio-band", PAPER, "5.7.3")
def stockRatioBand():
    """At stock the interconnect tracks the core. The BAND is the claim, not a midpoint."""
    values = _ratios(VOLT_STOCK)
    return f"its ratio to core clock holds between {min(values):.3f} and {max(values):.3f}"


@claim("5.7.3-ratio-collapse", PAPER, "5.7.3")
def ratioCollapse():
    """The headline: under the flattened curve the ratio falls away instead of holding. Rendered
    as first-to-lowest rather than max-to-min, because the CLAIM is a collapse with frequency and
    an unordered range would also match a curve that merely wobbled."""
    values = _ratios(VOLT_TUNED)
    return f"that ratio collapses from {values[0]:.3f} to {min(values):.3f}"


@claim("5.7.3-voltage-rise", PAPER, "5.7.3")
def voltageRise():
    """What the flattened curve actually does, in volts. Both numbers, because the contrast is
    the point - one configuration responds to frequency and the other does not."""
    stock = _voltageExtract(VOLT_STOCK)
    tuned = _voltageExtract(VOLT_TUNED)
    stockRise = max(r["voltage"] for r in stock.values()) - min(r["voltage"] for r in stock.values())
    tunedRise = max(r["voltage"] for r in tuned.values()) - min(r["voltage"] for r in tuned.values())
    return (f"stock core voltage rises {stockRise:.3f} V while the tuned card's rises "
            f"{tunedRise:.3f} V")


# ⛔ RETIRED 2026-09-24: "5.7.3-agree-where-voltages-agree". It rendered "at 1402 MHz both sit at
# 0.720 V and both deliver ~282 GB/s", which is true, and so stayed green on a sentence whose
# other half ("diverge from 1635 MHz") was false. A claim that pins only the true half of a
# sentence certifies the sentence. It is replaced by the table that retracted it.
@claim("5.7.3-divergence-at-equal-voltage", PAPER, "5.7.3")
def divergenceAtEqualVoltage():
    """The retraction's evidence: the configurations diverge at 1477 and 1560 MHz while both still
    report the same voltage, so reported voltage is not the state variable. All four rows, so the
    table cannot be edited back to a clean agreement without failing here."""
    stock = _voltageExtract(VOLT_STOCK)
    tuned = _voltageExtract(VOLT_TUNED)
    rows = []
    for target in (1402, 1477, 1560, 1635):
        s, t = stock[target], tuned[target]
        gap = 100.0 * (t["throughput"] / s["throughput"] - 1.0)
        rows.append(f"| {target} | {s['voltage']:.3f} | {t['voltage']:.3f} | {s['crossbar']:.0f} | "
                    f"{t['crossbar']:.0f} | {gap:+.1f}% |")
    return "\n".join(rows)


@claim("5.7.3-memory-not-matched", PAPER, "5.7.3")
def memoryNotMatched():
    """The stock telemetry run is at stock memory; the tuned run carries +2500. Found by an outside
    audit, after the paper had said both ran at 16301 MHz throughout. Per-point logged means."""
    import csv as _csv

    def span(relativePath):
        with open(_REPO_ROOT / relativePath, encoding="utf-8-sig") as handle:
            values = [float(raw["memoryMhz"]) for raw in _csv.DictReader(handle)]
        return f"{min(values):.0f}–{max(values):.0f} MHz"
    return f"The stock sweep in the table logs {span(VOLT_STOCK)}"


@claim("5.7.3-tuned-memory-applied", PAPER, "5.7.3")
def tunedMemoryApplied():
    """The other half: the memory overclock WAS applied on the plateaued card, which is what places
    the plateau upstream of DRAM. Pinned separately so neither half can pass for the other."""
    import csv as _csv
    with open(_REPO_ROOT / VOLT_TUNED, encoding="utf-8-sig") as handle:
        values = [float(raw["memoryMhz"]) for raw in _csv.DictReader(handle)]
    return f"its DRAM logs {min(values):.0f}–{max(values):.0f} MHz across the sweep"


# --------------------------------------------------------------------------------------
# The header's OTHER count
#
# The status header advertised "67 committed sweeps" while the repository held 112. Same defect
# as the claim count it sits beside, found the same way - by measuring instead of reading - and
# 24 of the missing 45 were added by suite replicates r2 and r3 alone.
#
# Counted from the filesystem rather than from git, because the audit has no git dependency and
# does not want one. That is only equivalent while nothing untracked lives under
# data/frequency-sweeps; it was verified equal (112 both ways, working tree clean) when this
# claim was written. Voltage extracts end _sweep_voltage.csv and are joins rather than sweeps,
# so the glob excludes them - there are 11, and counting them would inflate this by a tenth.
#
# NOT guarded on the reference dataset, unlike header-pinned-count: these CSVs are committed, so
# the number is the same with or without data/raw.
# --------------------------------------------------------------------------------------

NOT_DATASET_GRADE_MARKER = "<!-- dataset-grade: no -->"


def hasNotDatasetGradeMarker(readmeText):
    """True only when the marker stands ALONE on a line.

    Separated from headerSweepCount so it can be tested without a filesystem, because both ways
    this has been got wrong are about text rather than about counting.
    """
    return any(line.strip() == NOT_DATASET_GRADE_MARKER for line in readmeText.splitlines())


@claim("header-sweep-count", PAPER)
def headerSweepCount():
    """The header's advertised sweep count, recomputed from the committed CSVs.

    ⚠️ EXCLUDES DIRECTORIES WHOSE README DECLARES THEM NOT DATASET-GRADE, because the sentence
    this renders says results REST ON these sweeps. On 2026-09-05 a deliberately-overridden
    one-workload probe was committed to settle whether a driver's raised utilisation reading was
    real contamination; its own README says do not pool it with the replicate suite. Counting it
    would have made the paper claim its results rest on a run the repository explicitly says not
    to use - a true count producing a false sentence.

    The marker is read from the directory README rather than kept as a list here, so a new probe
    is excluded by documenting it honestly rather than by remembering to edit this function. That
    is the same reason every data directory carries a README in the first place.
    """
    root = _REPO_ROOT / "data" / "frequency-sweeps"
    excluded = set()
    for readme in root.rglob("README.md"):
        # An HTML comment ON ITS OWN LINE, not prose and not a mention. Two earlier versions of
        # this test were both defeated by READMEs discussing the convention rather than invoking
        # it. The first matched "NOT DATASET-GRADE" anywhere in the file and excluded 36 sweeps,
        # because "what is dataset-grade and what is not" is the convention's own wording. The
        # second required the exact HTML comment but still matched it ANYWHERE, so on 2026-09-11 a
        # README that quoted the marker inside a code span while explaining why it must NOT be
        # applied excluded itself - four sweeps, silently, from a published count.
        #
        # A marker that fires when it is merely named is not a marker. Every genuine one in this
        # repository sits alone on a line, so that is what is required.
        if hasNotDatasetGradeMarker(readme.read_text(encoding="utf-8", errors="replace")):
            excluded.add(readme.parent)
    # ⚠️ ANY ANCESTOR, NOT JUST THE IMMEDIATE PARENT. This read `p.parent not in excluded` until
    # 2026-09-10, which silently counted four sweeps from `kitverify-20260823/` - a directory whose
    # README carries the marker, but whose sweeps sit one level down in per-run subfolders. Every
    # excluded directory until that day happened to be flat, so the bug could not fire and the
    # claim looked correct for as long as the convention stayed accidentally uniform.
    #
    # A marker that only works at one nesting depth is not a marker. The fix is four characters of
    # logic and it moved the published count by four sweeps.
    sweeps = [p for p in root.rglob("*_sweep.csv")
              if not p.name.endswith("_sweep_voltage.csv")
              and not any(ancestor in excluded for ancestor in p.parents)]
    return f"**{len(sweeps)} committed"


# --------------------------------------------------------------------------------------
# 5.5.4 - does the per-workload ordering transfer between architectures?
#
# WHY A CROSS-CHIP CLAIM LIVES IN THE CONSUMER MODULE. The three claims modules are split by
# which hardware the data came from, and this one reads BOTH cards, so neither module is its
# natural home. It sits here because the machinery does: the r1-r5 suite maps and
# suiteRowFigures() are already here, and duplicating them into claims_crosschip.py is precisely
# the shared-constant drift the split exists to prevent - two copies of a path map diverge
# silently, whereas one map read by a claim that NAMES both cards does not.
#
# THE CONTROL IS PINNED ALONGSIDE THE RESULT, DELIBERATELY. A rank correlation of -0.273 means
# nothing on its own: a ranking of noisy quantities scrambles against anything, including itself.
# It is a finding only beside the within-card figure. An edit that dropped the control would
# leave the result reading as though it needed no baseline, which is the same failure mode
# claims_reference.py guards against for 5.6.2.
# --------------------------------------------------------------------------------------

SUITE_R4_SWEEPS = {name: f"suite-replicate-r4-20260904/{stamp}_5060ti-stock-suite-{name}-r4_sweep.csv"
                   for name, stamp in {
                       "copy": "20260904-192751", "reduce": "20260904-193212",
                       "softmax": "20260904-193641", "layernorm": "20260904-194100",
                       "bgemm32": "20260904-194523", "bgemm64": "20260904-194944",
                       "bgemm128": "20260904-195403", "bgemm256": "20260904-195839",
                       "bgemm1024": "20260904-200343", "attention": "20260904-200848",
                       "conv": "20260904-201356", "gemm": "20260904-201904"}.items()}

SUITE_R5_SWEEPS = {name: f"suite-replicate-r5-20260904/{stamp}_5060ti-stock-suite-{name}-r5_sweep.csv"
                   for name, stamp in {
                       "copy": "20260904-202626", "reduce": "20260904-203048",
                       "softmax": "20260904-203517", "layernorm": "20260904-203935",
                       "bgemm32": "20260904-204358", "bgemm64": "20260904-204818",
                       "bgemm128": "20260904-205238", "bgemm256": "20260904-205712",
                       "bgemm1024": "20260904-210215", "attention": "20260904-210719",
                       "conv": "20260904-211226", "gemm": "20260904-211735"}.items()}

SUITE_3070_SWEEPS = {name: f"rtx3070ti-suite-20260904/{stamp}_rtx3070ti-suite-{name}_sweep.csv"
                     for name, stamp in {
                         "copy": "20260904-194702", "reduce": "20260904-195142",
                         "softmax": "20260904-195620", "layernorm": "20260904-200107",
                         "bgemm32": "20260904-200548", "bgemm64": "20260904-201106",
                         "bgemm128": "20260904-201622", "bgemm256": "20260904-202116",
                         "bgemm1024": "20260904-202634", "attention": "20260904-203205",
                         "conv": "20260904-203735", "gemm": "20260904-204245"}.items()}

SUITE_R6_SWEEPS = {name: f"suite-replicate-r6-20260905/{stamp}_5060ti-stock-suite-{name}-r6_sweep.csv"
                   for name, stamp in {
                       "copy": "20260905-133312", "reduce": "20260905-133733",
                       "softmax": "20260905-134201", "layernorm": "20260905-134618",
                       "bgemm32": "20260905-135041", "bgemm64": "20260905-135501",
                       "bgemm128": "20260905-135921", "bgemm256": "20260905-140356",
                       "bgemm1024": "20260905-140859", "attention": "20260905-141403",
                       "conv": "20260905-141911", "gemm": "20260905-142420"}.items()}

# SIX STOCK REPLICATES, and the count is load-bearing for what the control below can say.
# r4 and r5 are the only WITHIN-session pair; r1, r2, r3, r4 and r6 span five separate days. So
# this is not six independent sessions and 5.5.4 must not be read as though it were.
#
# ⚠️ SCHEMA MIXED. r6 is 0.3.2 and carries free_vram_mb_at_start; r1-r5 are 0.3.1 and record no
# VRAM occupancy at all, so they cannot be audited retrospectively for a resident model. Nothing
# read here is affected - the added fields are preflight provenance, not measurement - but any
# code that reads the whole set must tolerate the field's absence rather than assume it.
#
# ⚠️ DRIVER MIXED, AND DELIBERATELY SO. r1 is 610.88; r2-r6 are 616.56. r6 was collected before a
# pending update specifically to stay in the larger group rather than straddle the change.
REPLICATES_5060 = (SUITE_R1_SWEEPS, SUITE_R2_SWEEPS, SUITE_R3_SWEEPS,
                   SUITE_R4_SWEEPS, SUITE_R5_SWEEPS, SUITE_R6_SWEEPS)


def _englishCount(n):
    """Small counts as words, because the paper writes them that way and a claim must match the
    document rather than ask the document to match it."""
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 10: "ten",
             15: "fifteen", 21: "twenty-one", 28: "twenty-eight"}
    return words.get(n, str(n))


def _rankOf(gains):
    ordered = sorted(gains, key=lambda name: -gains[name])
    return {name: index + 1 for index, name in enumerate(ordered)}


def _spearman(first, second):
    names = list(first)
    count = len(names)
    squared = sum((first[n] - second[n]) ** 2 for n in names)
    return 1.0 - 6.0 * squared / (count * (count * count - 1))


def _gainsOf(table):
    """Gain per workload for one complete suite, via the canonical highest-achieved reference."""
    return {name: suiteRowFigures(path)[1] for name, path in table.items()}


@claim("5.5.4-rank-correlation", PAPER, "5.5.4")
def crossArchitectureRank():
    """The result: the ordering carries no information across these two architectures."""
    perWorkload = {name: mean(_gainsOf(t)[name] for t in REPLICATES_5060)
                   for name in SUITE_R1_SWEEPS}
    rho = _spearman(_rankOf(perWorkload), _rankOf(_gainsOf(SUITE_3070_SWEEPS)))
    # U+2212 MINUS SIGN, not a hyphen: the paper sets negative correlations that way and so does
    # 5.2-sensitivity-correlation, and a claim that rendered ASCII would never match.
    return ("Spearman rank correlation between the two cards: "
            + f"{rho:+.3f}".replace("-", "−"))


@claim("5.5.4-within-card-control", PAPER, "5.5.4")
def withinCardRankControl():
    """The control, without which the result above is uninterpretable. Rendered as the band across
    all ten replicate pairs AND the mean: a midpoint alone would not show that every single pair
    clears the cross-card figure by a wide margin, which is the part that carries the argument."""
    import itertools
    ranks = [_rankOf(_gainsOf(table)) for table in REPLICATES_5060]
    values = [_spearman(a, b) for a, b in itertools.combinations(ranks, 2)]
    # ⚠️ THE PAIR COUNT IS RENDERED, NOT WRITTEN. It said "all ten pairs" as literal text while
    # computing however many the replicate set implies - correct at five replicates and silently
    # wrong the moment a sixth was added, which is exactly what happened on 2026-09-05. A claim
    # that hardcodes any part of its own sentence is only pinning the rest of it.
    return (f"all {_englishCount(len(values))} pairs, gives **{min(values):+.3f} to "
            f"{max(values):+.3f}, mean {mean(values):+.3f}**")


@claim("5.5.4-mean-gain-5060", PAPER, "5.5.4")
def crossArchitectureMeanGain5060():
    """What DOES transfer is the size of the effect, so both cards' means are pinned - this one
    and the 3070 Ti's below - rather than only their difference."""
    perWorkload = {name: mean(_gainsOf(t)[name] for t in REPLICATES_5060)
                   for name in SUITE_R1_SWEEPS}
    return f"**{mean(perWorkload.values()):.1f}%** on the 5060 Ti"


@claim("5.5.4-mean-gain-3070", PAPER, "5.5.4")
def crossArchitectureMeanGain3070():
    """The other half of the pair."""
    return f"against **{mean(_gainsOf(SUITE_3070_SWEEPS).values()):.1f}%** on the 3070 Ti"


# --------------------------------------------------------------------------------------
# 5.5.4, second pass - the figures the sixth replicate forced into the open (2026-09-05).
#
# The optimum-as-a-fraction-of-range numbers were in the paper UNPINNED, and folding r6 in meant
# checking whether they moved. They did not - but establishing that took reverse-engineering which
# denominator produced them, because the method had never been written down. 49.7% is against the
# highest COMMANDED clock; against the highest ACHIEVED clock, which is what suiteRowFigures uses
# three paragraphs earlier, the same data gives 56.3%. Two defensible conventions, a 6.6-point
# gap, and nothing in the document saying which was in force. Pinned with the method in the
# docstring so the next person does not have to derive it from the answer.
# --------------------------------------------------------------------------------------


def _medianOptimumFraction(tables, denominator):
    values = []
    for table in (tables if isinstance(tables, tuple) else (tables,)):
        for path in table.values():
            rows = sweep(path)
            peak = max(rows.values(), key=lambda row: row["efficiency"])
            values.append(100.0 * peak["mhz"] / denominator(rows))
    return median(values)


def _maxCommanded(rows):
    return max(row["target"] for row in rows.values())


def _maxAchieved(rows):
    return max(row["mhz"] for row in rows.values())


@claim("5.5.4-optimum-fraction-5060", PAPER, "5.5.4")
def optimumFraction5060():
    """Against the highest COMMANDED clock - the convention this sentence uses."""
    value = _medianOptimumFraction(REPLICATES_5060, _maxCommanded)
    return f"median **{value:.1f}%** of maximum"


@claim("5.5.4-optimum-fraction-3070", PAPER, "5.5.4")
def optimumFraction3070():
    """The other half of the pair, same convention."""
    value = _medianOptimumFraction(SUITE_3070_SWEEPS, _maxCommanded)
    return f"against **{value:.1f}%** on the 3070 Ti"


@claim("5.5.4-two-conventions", PAPER, "5.5.4")
def optimumFractionBothConventions():
    """Pins BOTH numbers in one string, deliberately.

    The point of the sentence is that two conventions disagree by six points on one card. A claim
    that pinned only the commanded figure would let the achieved one drift and leave the sentence
    asserting a gap it no longer measured - which is the same shape as the paired-comparison
    failure of 5.7.6, where correcting one half of a pair produced a confident wrong answer.
    """
    commanded = _medianOptimumFraction(REPLICATES_5060, _maxCommanded)
    achieved = _medianOptimumFraction(REPLICATES_5060, _maxAchieved)
    return f"give {commanded:.1f}% and {achieved:.1f}% for the same card"


@claim("5.5.4-ranks-unmoved", PAPER, "5.5.4")
def ranksUnmovedBySixthReplicate():
    """The sixth replicate changed no rank, and the largest percentage shift was under a point.

    ⚠️ THIS CLAIM WILL FAIL IF A SEVENTH REPLICATE MOVES A RANK, AND THAT IS THE POINT. The
    sentence it pins is an observation about stability, not a permanent property. If r7 reorders
    anything the sentence becomes false and the audit says so, rather than the paper continuing to
    assert it. Computed by comparing the six-replicate ordering against the five-replicate one.
    """
    six = {name: mean(_gainsOf(t)[name] for t in REPLICATES_5060) for name in SUITE_R1_SWEEPS}
    five = {name: mean(_gainsOf(t)[name] for t in REPLICATES_5060[:5]) for name in SUITE_R1_SWEEPS}
    if _rankOf(six) != _rankOf(five):
        raise AssertionError("a rank MOVED between five and six replicates - the sentence this "
                             "claim pins is no longer true and must be rewritten, not renumbered")
    shift = max(abs(six[n] - five[n]) for n in six)
    return f"by at most {shift:.1f} points"


# --------------------------------------------------------------------------------------
# 5.4.1 - the fine-sweep vertex fits. Least-covered section in the paper at 2 of 122 numbers
# pinned before 2026-09-05, and the blocker CLAUDE.md recorded for it had already been removed:
# analyseWorkload() is importable, returns its summary, and the seed defaults to 20260816.
#
# 🔑 THE RNG IS CONSUMED SEQUENTIALLY AND THE ORDER IS PART OF THE ANSWER. One generator is
# created and then passed to gemm's bootstrap, membw's, and the comparison, in that order. Fitting
# a workload on its own, or in the other order, draws different resamples and moves the interval by
# a megahertz or two. So this runs the WHOLE analysis once, in main()'s order, and caches it -
# every claim below reads that one run rather than recomputing its own.
#
# ⛔ THE PER-PASS CONFIDENCE INTERVALS ARE DELIBERATELY NOT PINNED. The paper's table gives
# 1446-1491, 1492-1536, 1552-1636 and 1582-1633 for the four passes. Re-running the bootstrap
# reproduces the four VERTICES exactly (1467, 1513, 1598, 1611) but lands one megahertz off on one
# bound of all four intervals, whichever way the generator is seeded. One megahertz is not a
# disagreement worth correcting the paper over, and it is also not a match - so writing a claim
# that rendered the paper's numbers would mean fitting the formula to the document, which is the
# one thing a claim must never do. Recorded here instead: those four intervals were produced by an
# invocation this code path does not reproduce, and their provenance is unknown.
# --------------------------------------------------------------------------------------

_fineSweepCache = {}


def _fineSweepAnalysis():
    """The full 5.4.1 analysis, run once in main()'s order, with stdout suppressed."""
    if _fineSweepCache:
        return _fineSweepCache

    import collections
    import contextlib
    import glob
    import io as _io
    import os
    import sys as _sys
    import numpy as np

    _sys.path.insert(0, str(_REPO_ROOT / "analysis"))
    import analyze_fine_sweep as fine

    grouped = collections.defaultdict(dict)
    for path in sorted(glob.glob(str(_REPO_ROOT / "data" / "frequency-sweeps"
                                     / "*fine-p*-rerun_sweep.csv"))):
        workload, passNo = fine.parseName(os.path.basename(path).replace("_sweep.csv", ""))
        grouped[workload][passNo] = fine.loadSweep(path)

    rng = np.random.default_rng(20260816)
    summaries = {}
    with contextlib.redirect_stdout(_io.StringIO()):
        for workload in ("gemm", "membw"):
            summaries[workload] = fine.analyseWorkload(workload, grouped[workload], 5000, rng)
        # compare() draws from the SAME generator, after both workloads. Its output is parsed
        # rather than recomputed, so the number pinned is the one the tool actually prints.
        captured = _io.StringIO()
        with contextlib.redirect_stdout(captured):
            fine.compare(summaries["gemm"], summaries["membw"], rng)

    perPass = {}
    for workload in ("gemm", "membw"):
        for passNo, rows in sorted(grouped[workload].items()):
            pooled = fine.normalisePerPass({passNo: rows})
            perPass[(workload, passNo)] = fine.fitVertex([p[0] for p in pooled],
                                                         [p[1] for p in pooled], degree=3)

    _fineSweepCache.update({"summaries": summaries, "perPass": perPass,
                            "compareText": captured.getvalue(), "grouped": grouped})
    return _fineSweepCache


@claim("5.4.1-pooled-optima", PAPER, "5.4.1")
def fineSweepPooledOptima():
    """The section's headline: two workloads, two optima, and an interval excluding zero.

    The difference and its interval are read from compare()'s own printed line rather than
    recomputed, so this pins what the tool reports rather than a second implementation of it.
    """
    import re as _re
    data = _fineSweepAnalysis()
    line = [l for l in data["compareText"].splitlines() if "95% CI" in l][0].strip()
    difference, interval = _re.match(r"(-?\d+) MHz\s+\(95% CI (-?\d+ to -?\d+) MHz\)", line).groups()
    # U+2212 MINUS SIGN, not a hyphen: 5.4's tables set negatives that way and so does
    # 5.5.4-rank-correlation. The tool prints ASCII, the document uses the typographic form, and
    # an unconverted hyphen would never match - the same trap 5.5.4 hit on its first run.
    toMinus = lambda s: s.replace("-", chr(0x2212))
    return (f"`gemm` **{data['summaries']['gemm']['vertex']:.0f} MHz**, "
            f"`membw` **{data['summaries']['membw']['vertex']:.0f} MHz**, difference "
            f"**{toMinus(difference)} MHz (95% CI {toMinus(interval)})**")


def _perPassVertexClaim(workload, passNo):
    """One claim per table row. Four separate claims rather than one combined string, because the
    rows are on separate lines of a markdown table and each must be pinned where it sits - a
    combined render would depend on how the table happens to wrap."""

    @claim(f"5.4.1-vertex-{workload}-p{passNo}", PAPER, "5.4.1")
    def perPassVertex():
        vertex = _fineSweepAnalysis()["perPass"][(workload, passNo)]
        return f"`{workload}` pass {passNo} | {vertex:.0f} MHz"

    return perPassVertex


for _workload in ("gemm", "membw"):
    for _passNo in (1, 2):
        _perPassVertexClaim(_workload, _passNo)


@claim("5.4.1-pass-agreement", PAPER, "5.4.1")
def fineSweepPassAgreement():
    """The spread between repeats of one measurement, which is what makes the 112 MHz meaningful."""
    # ⚠️ DIFFERENCE THE ROUNDED VERTICES, NOT THE RAW FLOATS. The sentence refers to the table
    # three lines above it, which shows whole megahertz, and 1611.4 - 1598.6 rounds to 12 while
    # 1611 - 1598 is 13. The paper says 13, and it is right: it is describing the numbers a reader
    # can see. Differencing the floats would have silently contradicted the table it points at.
    v = {k: round(x) for k, x in _fineSweepAnalysis()["perPass"].items()}
    gemmGap = abs(v[("gemm", 2)] - v[("gemm", 1)])
    membwGap = abs(v[("membw", 2)] - v[("membw", 1)])
    return f"agree within {gemmGap:.0f} MHz and the two `membw` fits within {membwGap:.0f} MHz"


@claim("5.4.1-repeatability", PAPER, "5.4.1")
def fineSweepRepeatability():
    """Median and worst point-to-point disagreement between the two passes of each workload."""
    import re as _re
    data = _fineSweepAnalysis()
    import analyze_fine_sweep as fine
    import contextlib, io as _io
    worst = {}
    for workload in ("gemm", "membw"):
        with contextlib.redirect_stdout(_io.StringIO()) as buf:
            fine.reportRepeatability(workload, data["grouped"][workload])
        worst[workload] = _re.search(r"worst ([\d.]+)%", buf.getvalue()).group(1)
    return (f"median {data['summaries']['gemm']['noise']:.2f}% for `gemm` "
            f"(worst {worst['gemm']}%) and {data['summaries']['membw']['noise']:.2f}% for `membw` "
            f"(worst {worst['membw']}%)")


# --------------------------------------------------------------------------------------
# 5.5.6 - the same sweeps read through energy-delay product.
#
# WHY THIS EXISTS. Every headline in 5.5 is perf-per-watt, which weights a watt saved and a second
# lost equally. EDP and ED2P weight delay once and twice more, and a reviewer is entitled to ask
# what the answer looks like under them. The sweeps already contain everything needed: the workload
# is FIXED-WORK, so time is proportional to 1/throughput and no new measurement is required.
#
#     energy  = power / throughput          EDP = power / throughput^2   ED2P = power / throughput^3
#
# 🔑 ENERGY AND PERF-PER-WATT ARE THE SAME STATISTIC HERE, not two agreeing ones. For fixed work
# they are exact reciprocals, so their optima coincide by construction and the agreement is not
# evidence of anything. Reporting them as though it were would be a mistake; the claims below pin
# the coincidence so nobody later reads it as corroboration.
# --------------------------------------------------------------------------------------


def _metricOptimum(path, exponent):
    """Frequency minimising power/throughput**exponent, and the improvement over the top clock.

    exponent 1 = energy, 2 = EDP, 3 = ED2P. Lower is better for all three, so the improvement is
    how much LOWER the metric sits at its optimum than at the highest achieved clock.
    """
    rows = list(sweep(path).values())
    reference = max(rows, key=lambda row: row["mhz"])
    best = min(rows, key=lambda row: row["power"] / (row["throughput"] ** exponent))
    atBest = best["power"] / (best["throughput"] ** exponent)
    atRef = reference["power"] / (reference["throughput"] ** exponent)
    return {"mhz": best["mhz"],
            "improvement": 100.0 * (atRef / atBest - 1.0),
            "cost": 100.0 * (1.0 - best["throughput"] / reference["throughput"])}


def _acrossStock(exponent, field):
    return mean(mean(_metricOptimum(table[name], exponent)[field]
                     for table in REPLICATES_5060[1:])
                for name in SUITE_R1_SWEEPS)


@claim("5.5.6-edp-optimum", PAPER, "5.5.6")
def edpOptimum():
    """Median EDP optimum against the perf-per-watt one. The gap is the point of the section."""
    perWatt = median([mean(_metricOptimum(t[n], 1)["mhz"] for t in REPLICATES_5060[1:])
                      for n in SUITE_R1_SWEEPS])
    edp = median([mean(_metricOptimum(t[n], 2)["mhz"] for t in REPLICATES_5060[1:])
                  for n in SUITE_R1_SWEEPS])
    return f"median optimum moves from **{perWatt:.0f} MHz** to **{edp:.0f} MHz**"


@claim("5.5.6-edp-gain", PAPER, "5.5.6")
def edpGain():
    """What EDP recovers at its own optimum, and what it costs."""
    return (f"**{_acrossStock(2, 'improvement'):.1f}%** better EDP for a "
            f"**{_acrossStock(2, 'cost'):.1f}%** performance cost")


@claim("5.5.6-ed2p-gain", PAPER, "5.5.6")
def ed2pGain():
    """ED2P, which weights delay harder still."""
    return (f"**{_acrossStock(3, 'improvement'):.1f}%** better ED2P for "
            f"**{_acrossStock(3, 'cost'):.1f}%**")


# --------------------------------------------------------------------------------------
# 5.5.7 - the efficiency optimum sits at the knee of the stock V/F curve, on BOTH chips.
#
# WHAT THIS IS. The textbook account of why an efficiency valley exists invokes leakage: a fixed
# per-second drain that eventually cancels the dynamic saving. That mechanism is real and is not
# disputed here, but it is BORROWED - nvidia-smi reports one board-level power number and cannot
# separate static from dynamic, so this study cannot observe leakage at all.
#
# What it CAN observe is the vendor's own voltage/frequency curve, through HWiNFO. Below some
# frequency the curve stops lowering voltage and holds a floor. Below that floor, P = Pfixed + C*V^2*f
# has a CONSTANT V, so power falls only linearly with frequency while runtime grows as 1/f - the two
# cancel, Pfixed does not shrink at all, and efficiency stops improving. The prediction is therefore
# that the efficiency optimum should sit at the LAST frequency at which voltage is still falling.
#
# 🔑 IT HOLDS ON BOTH CHIPS, at different absolute frequencies, which is what makes it a mechanism
# rather than a coincidence. One card could be luck; two architectures with different vendor curves
# landing on their own respective knees is a testable regularity - and it predicts where a third
# card's optimum will be, which is the cheapest possible check on the 3060 and 2060 Super.
#
# ⚠️ THE VOLTAGE AND THE OPTIMUM COME FROM DIFFERENT RUNS ON THE FIRST TWO CARDS. Voltage needs
# HWiNFO binned onto the sweep by CORE CLOCK - NOT joined on timestamp, which join_hwinfo_voltage.py
# rejects because the sweep CSV records durations rather than absolute timestamps - and it was
# collected on gemm/membw sweeps; the optima come from the 12-workload suites. The 3060 is the
# exception: its HWiNFO log covers the suite itself, so its floor and optimum share one session.
# Same card and same stock configuration in each case, but not the same session. The claims below
# render both numbers so the gap between them is visible rather than asserted, and 5.5.7 says plainly
# that a careful version measures voltage during the suite itself.
# --------------------------------------------------------------------------------------

# The fine floor-end sweep (worklist 4h, ~7.5 MHz steps), not the coarse 2026-08-20 membw extract this
# read until 2026-09-28: that one put the floor end at 1552 MHz because its next point was 1702. GPT
# Job 32 found the paper contradicting itself (1552 here, 1567-1575 in 5.5.10). Replicate r2 must agree.
_VOLT_5060_STOCK = "5060ti-finefloor-20260922/20260922-093857_5060ti-4h-floorend-r1_sweep_voltage.csv"
_VOLT_5060_STOCK_R2 = "5060ti-finefloor-20260922/20260922-094425_5060ti-4h-floorend-r2_sweep_voltage.csv"
_VOLT_3070_SILENT = ("rtx3070ti-20260825/hwinfo-silent/"
                     "20260827-172904_rtx3070ti-silent-gemm-fine_sweep_voltage.csv")


def _voltageFloorTop(relativePath):
    """Highest achieved clock at which stock voltage is still sitting at its floor.

    The floor is the minimum voltage the row set contains; the answer is the last row still at it.
    Reading the file directly rather than through sweep() because these are the HWiNFO-joined
    extracts, which carry voltage and crossbar columns the ordinary sweep CSVs do not.
    """
    import csv
    import io as _io
    with _io.open(_REPO_ROOT / "data" / "frequency-sweeps" / relativePath,
                  encoding="utf-8-sig", newline="") as handle:
        rows = [(float(r["achieved"]), float(r["voltage"])) for r in csv.DictReader(handle)]
    floor = min(v for _, v in rows)
    return max(mhz for mhz, v in rows if v <= floor + 1e-9)


def _medianSuiteOptimum(tables):
    """Median per-workload efficiency optimum. Accepts one table or a tuple of replicates."""
    tables = tables if isinstance(tables, tuple) else (tables,)
    perWorkload = []
    for name in tables[0]:
        perWorkload.append(mean(max(sweep(t[name]).values(),
                                    key=lambda row: row["efficiency"])["mhz"] for t in tables))
    return median(perWorkload)


@claim("5.5.7-knee-5060", PAPER, "5.5.7")
def kneeFiveThousandSixty():
    """5060 Ti: suite optimum against the top of its stock voltage floor."""
    if _voltageFloorTop(_VOLT_5060_STOCK) != _voltageFloorTop(_VOLT_5060_STOCK_R2):
        return "the two fine floor-end replicates no longer agree"
    return (f"**{_medianSuiteOptimum(REPLICATES_5060[1:]):.0f} MHz** against a voltage floor holding "
            f"to **{_voltageFloorTop(_VOLT_5060_STOCK):.0f} MHz**")


@claim("5.5.7-knee-3070", PAPER, "5.5.7")
def kneeThirtySeventy():
    """3070 Ti: the same pair, on a different architecture and at a different absolute frequency."""
    return (f"**{_medianSuiteOptimum(SUITE_3070_SWEEPS):.0f} MHz** against a floor holding to "
            f"**{_voltageFloorTop(_VOLT_3070_SILENT):.0f} MHz**")


@claim("5.5.7-knee-modal", PAPER, "5.5.7")
def kneeModalAgreement():
    """How many of the twelve 3070 Ti workloads independently pick the modal optimum.

    Pinned because "the median is 1485" is much weaker than "seven workloads chose it separately" -
    a median can be produced by a scatter with nothing at its centre.
    """
    optima = [max(sweep(p).values(), key=lambda row: row["efficiency"])["mhz"]
              for p in SUITE_3070_SWEEPS.values()]
    modal = median(optima)
    return f"**{sum(1 for m in optima if abs(m - modal) < 5)} of the twelve**"


# --------------------------------------------------------------------------------------
# 5.8 - the stock bracket, 2026-09-09
#
# The first same-session stock-versus-tuned comparison in the project. Written from a spec by
# the local model (tools/local-model/specs/stock-bracket-claims.md) and verified by this audit.
# --------------------------------------------------------------------------------------

BRACKET_README = "data/frequency-sweeps/stock-bracket-20260909/README.md"

BRACKET_TUNE_1 = {
    "copy": "stock-bracket-20260909/20260909-103757_5060ti-fulltune3030-suite-copy-p4t1_sweep.csv",
    "reduce": "stock-bracket-20260909/20260909-104157_5060ti-fulltune3030-suite-reduce-p4t1_sweep.csv",
    "softmax": "stock-bracket-20260909/20260909-104610_5060ti-fulltune3030-suite-softmax-p4t1_sweep.csv",
    "layernorm": "stock-bracket-20260909/20260909-105006_5060ti-fulltune3030-suite-layernorm-p4t1_sweep.csv",
    "bgemm32": "stock-bracket-20260909/20260909-105408_5060ti-fulltune3030-suite-bgemm32-p4t1_sweep.csv",
    "bgemm64": "stock-bracket-20260909/20260909-105805_5060ti-fulltune3030-suite-bgemm64-p4t1_sweep.csv",
    "bgemm128": "stock-bracket-20260909/20260909-110202_5060ti-fulltune3030-suite-bgemm128-p4t1_sweep.csv",
    "bgemm256": "stock-bracket-20260909/20260909-110624_5060ti-fulltune3030-suite-bgemm256-p4t1_sweep.csv",
    "bgemm1024": "stock-bracket-20260909/20260909-111109_5060ti-fulltune3030-suite-bgemm1024-p4t1_sweep.csv",
    "attention": "stock-bracket-20260909/20260909-111555_5060ti-fulltune3030-suite-attention-p4t1_sweep.csv",
    "conv": "stock-bracket-20260909/20260909-112047_5060ti-fulltune3030-suite-conv-p4t1_sweep.csv",
    "gemm": "stock-bracket-20260909/20260909-112537_5060ti-fulltune3030-suite-gemm-p4t1_sweep.csv",
}

BRACKET_STOCK = {
    "copy": "stock-bracket-20260909/20260909-114339_5060ti-stock-suite-copy-r9_sweep.csv",
    "reduce": "stock-bracket-20260909/20260909-114746_5060ti-stock-suite-reduce-r9_sweep.csv",
    "softmax": "stock-bracket-20260909/20260909-115159_5060ti-stock-suite-softmax-r9_sweep.csv",
    "layernorm": "stock-bracket-20260909/20260909-115605_5060ti-stock-suite-layernorm-r9_sweep.csv",
    "bgemm32": "stock-bracket-20260909/20260909-120014_5060ti-stock-suite-bgemm32-r9_sweep.csv",
    "bgemm64": "stock-bracket-20260909/20260909-120420_5060ti-stock-suite-bgemm64-r9_sweep.csv",
    "bgemm128": "stock-bracket-20260909/20260909-120826_5060ti-stock-suite-bgemm128-r9_sweep.csv",
    "bgemm256": "stock-bracket-20260909/20260909-121250_5060ti-stock-suite-bgemm256-r9_sweep.csv",
    "bgemm1024": "stock-bracket-20260909/20260909-121737_5060ti-stock-suite-bgemm1024-r9_sweep.csv",
    "attention": "stock-bracket-20260909/20260909-122227_5060ti-stock-suite-attention-r9_sweep.csv",
    "conv": "stock-bracket-20260909/20260909-122719_5060ti-stock-suite-conv-r9_sweep.csv",
    "gemm": "stock-bracket-20260909/20260909-123211_5060ti-stock-suite-gemm-r9_sweep.csv",
}

BRACKET_TUNE_2 = {
    "copy": "stock-bracket-20260909/20260909-124707_5060ti-fulltune3030-suite-copy-p4t2_sweep.csv",
    "reduce": "stock-bracket-20260909/20260909-125108_5060ti-fulltune3030-suite-reduce-p4t2_sweep.csv",
    "softmax": "stock-bracket-20260909/20260909-125521_5060ti-fulltune3030-suite-softmax-p4t2_sweep.csv",
    "layernorm": "stock-bracket-20260909/20260909-125916_5060ti-fulltune3030-suite-layernorm-p4t2_sweep.csv",
    "bgemm32": "stock-bracket-20260909/20260909-130318_5060ti-fulltune3030-suite-bgemm32-p4t2_sweep.csv",
    "bgemm64": "stock-bracket-20260909/20260909-130714_5060ti-fulltune3030-suite-bgemm64-p4t2_sweep.csv",
    "bgemm128": "stock-bracket-20260909/20260909-131111_5060ti-fulltune3030-suite-bgemm128-p4t2_sweep.csv",
    "bgemm256": "stock-bracket-20260909/20260909-131531_5060ti-fulltune3030-suite-bgemm256-p4t2_sweep.csv",
    "bgemm1024": "stock-bracket-20260909/20260909-132016_5060ti-fulltune3030-suite-bgemm1024-p4t2_sweep.csv",
    "attention": "stock-bracket-20260909/20260909-132502_5060ti-fulltune3030-suite-attention-p4t2_sweep.csv",
    "conv": "stock-bracket-20260909/20260909-132955_5060ti-fulltune3030-suite-conv-p4t2_sweep.csv",
    "gemm": "stock-bracket-20260909/20260909-133444_5060ti-fulltune3030-suite-gemm-p4t2_sweep.csv",
}


def _bracketMeanGain(table):
    return sum(suiteRowFigures(path)[1] for path in table.values()) / len(table)


def _bracketTuneGain():
    return (_bracketMeanGain(BRACKET_TUNE_1) + _bracketMeanGain(BRACKET_TUNE_2)) / 2.0


@claim("5.8-bracket-stock-mean", BRACKET_README)
def bracketStockMean():
    """the stock leg's mean efficiency gain, recomputed from its twelve sweep CSVs rather than read back from the table it checks."""
    return f"| stock (`r9`) | {_bracketMeanGain(BRACKET_STOCK):.2f}% |"


@claim("5.8-bracket-tune-mean", BRACKET_README)
def bracketTuneMean():
    """the full-tune mean of the two tuned legs' mean efficiency gains, recomputed from their sweep CSVs rather than read back from the table it checks."""
    return f"| full tune (mean of `p4t1`, `p4t2`) | {_bracketTuneGain():.2f}% |"


@claim("5.8-bracket-gap", BRACKET_README)
def bracketGap():
    """the gap between the stock and full-tune mean efficiency gains, recomputed from the sweep CSVs rather than read back from the table it checks."""
    return f"| GAP | {_bracketMeanGain(BRACKET_STOCK) - _bracketTuneGain():.2f} points |"


@claim("5.8-bracket-drift", BRACKET_README)
def bracketDrift():
    """the drift between the two tuned legs' mean efficiency gains, recomputed from their sweep CSVs rather than read back from the table it checks."""
    return f"| this run, full tune `p4t1` \u2192 `p4t2`, ~2 h | \u2212{abs(_bracketMeanGain(BRACKET_TUNE_2) - _bracketMeanGain(BRACKET_TUNE_1)):.2f} points |"


@claim("5.8-bracket-power-2010", BRACKET_README)
def bracketPower2010():
    """the 2010 MHz power and achieved-clock figures for stock and full tune, recomputed from the sweep CSVs rather than read back from the table it checks."""
    stockPower = sum(sweep(path)[2010]["power"] for path in BRACKET_STOCK.values()) / len(BRACKET_STOCK)
    tunePower = (sum(sweep(path)[2010]["power"] for path in BRACKET_TUNE_1.values()) / len(BRACKET_TUNE_1)
                 + sum(sweep(path)[2010]["power"] for path in BRACKET_TUNE_2.values()) / len(BRACKET_TUNE_2)) / 2.0
    stockClock = sum(sweep(path)[2010]["mhz"] for path in BRACKET_STOCK.values()) / len(BRACKET_STOCK)
    tuneClock = (sum(sweep(path)[2010]["mhz"] for path in BRACKET_TUNE_1.values()) / len(BRACKET_TUNE_1)
                 + sum(sweep(path)[2010]["mhz"] for path in BRACKET_TUNE_2.values()) / len(BRACKET_TUNE_2)) / 2.0
    # NOT signedPct: that renders a RATIO minus one, so the saving-as-a-fraction 0.187 would
    # come out as -81.3%. The table's quantity is the power saved relative to STOCK, and its
    # negative rows use U+2212 rather than an ASCII hyphen.
    saving = (1.0 - tunePower / stockPower) * 100.0
    savingText = f"{saving:+.1f}%".replace("-", "−")
    return f"| 2010 | {stockPower:.2f} | {tunePower:.2f} | {savingText} | {round(stockClock)} / {round(tuneClock)} |"


@claim("5.8-bracket-r9-row", BRACKET_README)
def bracketR9Row():
    """the stock leg's mean efficiency gain, recomputed from its twelve sweep CSVs rather than read back from the table it checks."""
    return f"| r9 (this run) | {_bracketMeanGain(BRACKET_STOCK):.2f}% |"

# --------------------------------------------------------------------------------------
# 5.5.7 third chip and 5.5.8 - the intervention arms, 2026-09-08 .. 09-10
#
# Paths are listed explicitly rather than globbed. That is the convention in this file and it
# exists because of a real collision: suite-replicate-r2-20260830/ holds bgemm64 sweeps tagged
# -r3 and -r4 from a separate early set, so a glob can silently resolve to the wrong file. A
# model may fail loudly on ambiguity; a claim may not take the risk at all.
# --------------------------------------------------------------------------------------

# abba-20260908 a1 -> 12 files
ABBA_A1 = {
    "copy":      "abba-20260908/20260908-115201_5060ti-fulltune-suite-copy-a1_sweep.csv",
    "reduce":    "abba-20260908/20260908-115601_5060ti-fulltune-suite-reduce-a1_sweep.csv",
    "softmax":   "abba-20260908/20260908-120014_5060ti-fulltune-suite-softmax-a1_sweep.csv",
    "layernorm": "abba-20260908/20260908-120410_5060ti-fulltune-suite-layernorm-a1_sweep.csv",
    "bgemm32":   "abba-20260908/20260908-120811_5060ti-fulltune-suite-bgemm32-a1_sweep.csv",
    "bgemm64":   "abba-20260908/20260908-121207_5060ti-fulltune-suite-bgemm64-a1_sweep.csv",
    "bgemm128":  "abba-20260908/20260908-121603_5060ti-fulltune-suite-bgemm128-a1_sweep.csv",
    "bgemm256":  "abba-20260908/20260908-122024_5060ti-fulltune-suite-bgemm256-a1_sweep.csv",
    "bgemm1024": "abba-20260908/20260908-122509_5060ti-fulltune-suite-bgemm1024-a1_sweep.csv",
    "attention": "abba-20260908/20260908-122955_5060ti-fulltune-suite-attention-a1_sweep.csv",
    "conv":      "abba-20260908/20260908-123446_5060ti-fulltune-suite-conv-a1_sweep.csv",
    "gemm":      "abba-20260908/20260908-123934_5060ti-fulltune-suite-gemm-a1_sweep.csv",
}

# abba-20260908 b1 -> 12 files
ABBA_B1 = {
    "copy":      "abba-20260908/20260908-125526_5060ti-splitcurve-suite-copy-b1_sweep.csv",
    "reduce":    "abba-20260908/20260908-125922_5060ti-splitcurve-suite-reduce-b1_sweep.csv",
    "softmax":   "abba-20260908/20260908-130325_5060ti-splitcurve-suite-softmax-b1_sweep.csv",
    "layernorm": "abba-20260908/20260908-130718_5060ti-splitcurve-suite-layernorm-b1_sweep.csv",
    "bgemm32":   "abba-20260908/20260908-131114_5060ti-splitcurve-suite-bgemm32-b1_sweep.csv",
    "bgemm64":   "abba-20260908/20260908-131508_5060ti-splitcurve-suite-bgemm64-b1_sweep.csv",
    "bgemm128":  "abba-20260908/20260908-131901_5060ti-splitcurve-suite-bgemm128-b1_sweep.csv",
    "bgemm256":  "abba-20260908/20260908-132322_5060ti-splitcurve-suite-bgemm256-b1_sweep.csv",
    "bgemm1024": "abba-20260908/20260908-132807_5060ti-splitcurve-suite-bgemm1024-b1_sweep.csv",
    "attention": "abba-20260908/20260908-133253_5060ti-splitcurve-suite-attention-b1_sweep.csv",
    "conv":      "abba-20260908/20260908-133745_5060ti-splitcurve-suite-conv-b1_sweep.csv",
    "gemm":      "abba-20260908/20260908-134234_5060ti-splitcurve-suite-gemm-b1_sweep.csv",
}

# abba-20260908 b2 -> 12 files
ABBA_B2 = {
    "copy":      "abba-20260908/20260908-135801_5060ti-splitcurve-suite-copy-b2_sweep.csv",
    "reduce":    "abba-20260908/20260908-140157_5060ti-splitcurve-suite-reduce-b2_sweep.csv",
    "softmax":   "abba-20260908/20260908-140600_5060ti-splitcurve-suite-softmax-b2_sweep.csv",
    "layernorm": "abba-20260908/20260908-140952_5060ti-splitcurve-suite-layernorm-b2_sweep.csv",
    "bgemm32":   "abba-20260908/20260908-141349_5060ti-splitcurve-suite-bgemm32-b2_sweep.csv",
    "bgemm64":   "abba-20260908/20260908-141743_5060ti-splitcurve-suite-bgemm64-b2_sweep.csv",
    "bgemm128":  "abba-20260908/20260908-142136_5060ti-splitcurve-suite-bgemm128-b2_sweep.csv",
    "bgemm256":  "abba-20260908/20260908-142557_5060ti-splitcurve-suite-bgemm256-b2_sweep.csv",
    "bgemm1024": "abba-20260908/20260908-143042_5060ti-splitcurve-suite-bgemm1024-b2_sweep.csv",
    "attention": "abba-20260908/20260908-143529_5060ti-splitcurve-suite-attention-b2_sweep.csv",
    "conv":      "abba-20260908/20260908-144020_5060ti-splitcurve-suite-conv-b2_sweep.csv",
    "gemm":      "abba-20260908/20260908-144510_5060ti-splitcurve-suite-gemm-b2_sweep.csv",
}

# abba-20260908 a2 -> 12 files
ABBA_A2 = {
    "copy":      "abba-20260908/20260908-150036_5060ti-fulltune-suite-copy-a2_sweep.csv",
    "reduce":    "abba-20260908/20260908-150437_5060ti-fulltune-suite-reduce-a2_sweep.csv",
    "softmax":   "abba-20260908/20260908-150849_5060ti-fulltune-suite-softmax-a2_sweep.csv",
    "layernorm": "abba-20260908/20260908-151249_5060ti-fulltune-suite-layernorm-a2_sweep.csv",
    "bgemm32":   "abba-20260908/20260908-151702_5060ti-fulltune-suite-bgemm32-a2_sweep.csv",
    "bgemm64":   "abba-20260908/20260908-152111_5060ti-fulltune-suite-bgemm64-a2_sweep.csv",
    "bgemm128":  "abba-20260908/20260908-152519_5060ti-fulltune-suite-bgemm128-a2_sweep.csv",
    "bgemm256":  "abba-20260908/20260908-152953_5060ti-fulltune-suite-bgemm256-a2_sweep.csv",
    "bgemm1024": "abba-20260908/20260908-153454_5060ti-fulltune-suite-bgemm1024-a2_sweep.csv",
    "attention": "abba-20260908/20260908-153957_5060ti-fulltune-suite-attention-a2_sweep.csv",
    "conv":      "abba-20260908/20260908-154506_5060ti-fulltune-suite-conv-a2_sweep.csv",
    "gemm":      "abba-20260908/20260908-155014_5060ti-fulltune-suite-gemm-a2_sweep.csv",
}

# repair-suite-p2-20260909 p2t1 -> 12 files
REPAIR_P2T1 = {
    "copy":      "repair-suite-p2-20260909/20260909-202923_5060ti-repair3022-suite-copy-p2t1_sweep.csv",
    "reduce":    "repair-suite-p2-20260909/20260909-193955_5060ti-repair3022-suite-reduce-p2t1_sweep.csv",
    "softmax":   "repair-suite-p2-20260909/20260909-194400_5060ti-repair3022-suite-softmax-p2t1_sweep.csv",
    "layernorm": "repair-suite-p2-20260909/20260909-194753_5060ti-repair3022-suite-layernorm-p2t1_sweep.csv",
    "bgemm32":   "repair-suite-p2-20260909/20260909-195150_5060ti-repair3022-suite-bgemm32-p2t1_sweep.csv",
    "bgemm64":   "repair-suite-p2-20260909/20260909-195543_5060ti-repair3022-suite-bgemm64-p2t1_sweep.csv",
    "bgemm128":  "repair-suite-p2-20260909/20260909-195937_5060ti-repair3022-suite-bgemm128-p2t1_sweep.csv",
    "bgemm256":  "repair-suite-p2-20260909/20260909-200359_5060ti-repair3022-suite-bgemm256-p2t1_sweep.csv",
    "bgemm1024": "repair-suite-p2-20260909/20260909-200845_5060ti-repair3022-suite-bgemm1024-p2t1_sweep.csv",
    "attention": "repair-suite-p2-20260909/20260909-201331_5060ti-repair3022-suite-attention-p2t1_sweep.csv",
    "conv":      "repair-suite-p2-20260909/20260909-201820_5060ti-repair3022-suite-conv-p2t1_sweep.csv",
    "gemm":      "repair-suite-p2-20260909/20260909-202310_5060ti-repair3022-suite-gemm-p2t1_sweep.csv",
}

SPLIT_S2 = {
    "copy":      "splitcurve-suite-s2-20260908/20260908-101152_5060ti-splitcurve-suite-copy-s2_sweep.csv",
    "reduce":    "splitcurve-suite-s2-20260908/20260908-101557_5060ti-splitcurve-suite-reduce-s2_sweep.csv",
    "softmax":   "splitcurve-suite-s2-20260908/20260908-102018_5060ti-splitcurve-suite-softmax-s2_sweep.csv",
    "layernorm": "splitcurve-suite-s2-20260908/20260908-102416_5060ti-splitcurve-suite-layernorm-s2_sweep.csv",
    "bgemm32":   "splitcurve-suite-s2-20260908/20260908-102812_5060ti-splitcurve-suite-bgemm32-s2_sweep.csv",
    "bgemm64":   "splitcurve-suite-s2-20260908/20260908-103206_5060ti-splitcurve-suite-bgemm64-s2_sweep.csv",
    "bgemm128":  "splitcurve-suite-s2-20260908/20260908-103559_5060ti-splitcurve-suite-bgemm128-s2_sweep.csv",
    "bgemm256":  "splitcurve-suite-s2-20260908/20260908-104020_5060ti-splitcurve-suite-bgemm256-s2_sweep.csv",
    "bgemm1024": "splitcurve-suite-s2-20260908/20260908-104504_5060ti-splitcurve-suite-bgemm1024-s2_sweep.csv",
    "attention": "splitcurve-suite-s2-20260908/20260908-104951_5060ti-splitcurve-suite-attention-s2_sweep.csv",
    "conv":      "splitcurve-suite-s2-20260908/20260908-105441_5060ti-splitcurve-suite-conv-s2_sweep.csv",
    "gemm":      "splitcurve-suite-s2-20260908/20260908-105931_5060ti-splitcurve-suite-gemm-s2_sweep.csv",
}

SUITE_3060 = {
    "copy":      "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-191442_rtx3060-suite-copy_sweep.csv",
    "reduce":    "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-191911_rtx3060-suite-reduce_sweep.csv",
    "softmax":   "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-192343_rtx3060-suite-softmax_sweep.csv",
    "layernorm": "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-192823_rtx3060-suite-layernorm_sweep.csv",
    "bgemm32":   "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-193259_rtx3060-suite-bgemm32_sweep.csv",
    "bgemm64":   "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-193815_rtx3060-suite-bgemm64_sweep.csv",
    "bgemm128":  "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-194321_rtx3060-suite-bgemm128_sweep.csv",
    "bgemm256":  "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-194812_rtx3060-suite-bgemm256_sweep.csv",
    "bgemm1024": "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-195309_rtx3060-suite-bgemm1024_sweep.csv",
    "attention": "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-195811_rtx3060-suite-attention_sweep.csv",
    "conv":      "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-200310_rtx3060-suite-conv_sweep.csv",
    "gemm":      "rtx3060-20260910/20260910-191436_rtx3060-suite/20260910-200806_rtx3060-suite-gemm_sweep.csv",
}



def _voltageFloorValue(relativePath):
    """The floor voltage itself - the minimum core voltage the joined extract contains."""
    import csv
    import io as _io
    with _io.open(_REPO_ROOT / "data" / "frequency-sweeps" / relativePath,
                  encoding="utf-8-sig", newline="") as handle:
        return min(float(r["voltage"]) for r in csv.DictReader(handle))


def _suiteAgreement(table):
    """(how many of the twelve workloads pick the suite median, how many there are).

    "The median is 1260" is a much weaker statement than "ten workloads chose it separately" - a
    median can be produced by a scatter with nothing at its centre. Pinned for that reason.
    """
    perWorkload = [max(sweep(path).values(), key=lambda row: row["efficiency"])["mhz"]
                   for path in table.values()]
    middle = median(perWorkload)
    return sum(1 for m in perWorkload if abs(m - middle) < 5), len(perWorkload)


def _perWorkloadShifts():
    """Per-workload optimum shift, full tune minus split, averaged over each ABBA pair."""
    shifts = []
    for name in ABBA_A1:
        tune = mean(max(sweep(t[name]).values(), key=lambda r: r["efficiency"])["mhz"]
                    for t in (ABBA_A1, ABBA_A2))
        split = mean(max(sweep(t[name]).values(), key=lambda r: r["efficiency"])["mhz"]
                     for t in (ABBA_B1, ABBA_B2))
        shifts.append(tune - split)
    return shifts


_VOLT_3060_SUITE = ("rtx3060-20260910/20260910-191436_rtx3060-suite/"
                    "20260910-200806_rtx3060-suite-gemm_sweep_voltage.csv")


@claim("5.5.7-knee-3060", PAPER, "5.5.7")
def kneeThirtySixty():
    """Third chip, third architecture: the row that tests the rule out of sample.

    Voltage and optimum come from the SAME session here, unlike the other two cards - the HWiNFO
    log covers the twelve-workload suite itself.
    """
    agree, total = _suiteAgreement(SUITE_3060)
    return (f"| RTX 3060 (Ampere GA106) | {_medianSuiteOptimum(SUITE_3060):.0f} MHz | "
            f"{_voltageFloorTop(_VOLT_3060_SUITE):.0f} MHz | "
            f"{_voltageFloorValue(_VOLT_3060_SUITE):.3f} V | {agree} of {total} |")


@claim("5.5.8-abba-split", PAPER, "5.5.8")
def abbaSplitMedian():
    """The unmodified low-voltage region's median optimum, over both ABBA split legs."""
    return (f"| Profile 5 (factory low-voltage region) | "
            f"{_medianSuiteOptimum((ABBA_B1, ABBA_B2)):.0f} MHz |")


@claim("5.5.8-abba-tune", PAPER, "5.5.8")
def abbaTuneMedian():
    """The lifted low-voltage region's median optimum, over both ABBA full-tune legs."""
    shift = _medianSuiteOptimum((ABBA_A1, ABBA_A2)) - _medianSuiteOptimum((ABBA_B1, ABBA_B2))
    return (f"| Profile 4 (low-voltage region +{shift:.0f} MHz) | "
            f"{_medianSuiteOptimum((ABBA_A1, ABBA_A2)):.0f} MHz |")


@claim("5.5.8-abba-shift", PAPER, "5.5.8")
def abbaShift():
    """The measured shift. The prediction was that it equals the curve's own +465 MHz offset."""
    shift = _medianSuiteOptimum((ABBA_A1, ABBA_A2)) - _medianSuiteOptimum((ABBA_B1, ABBA_B2))
    return f"| shift | +{shift:.0f} MHz |"


@claim("5.5.8-abba-exact-count", PAPER, "5.5.8")
def abbaExactCount():
    """How many workloads moved by EXACTLY the predicted amount - not the same as how many moved.

    Pinned because an earlier draft of this section, and the run's own README, both said
    "+465 MHz in 12 of 12 workloads". Twelve of twelve moved UP; six moved by exactly 465.
    """
    shifts = _perWorkloadShifts()
    median_ = median(shifts)
    return (f"{sum(1 for s in shifts if abs(s - median_) < 1e-9)} of the {len(shifts)} moved by "
            f"exactly {median_:.0f} MHz")


@claim("5.5.8-abba-shift-range", PAPER, "5.5.8")
def abbaShiftRange():
    """The spread of per-workload shifts, which is what makes the median the honest statistic."""
    shifts = _perWorkloadShifts()
    return f"range from {min(shifts):.0f} to {max(shifts):.0f} MHz"


@claim("5.5.8-control-measured", PAPER, "5.5.8")
def controlMeasured():
    """The negative control's outcome: a 570 MHz change above the floor moved the optimum by 0."""
    return f"| measured | {_medianSuiteOptimum(REPAIR_P2T1):.0f} MHz |"


@claim("5.5.8-control-agreement", PAPER, "5.5.8")
def controlAgreement():
    """How many of the twelve independently pick the control's unmoved median."""
    agree, total = _suiteAgreement(REPAIR_P2T1)
    return (f"{agree} of {total} workloads land on {_medianSuiteOptimum(REPAIR_P2T1):.0f} MHz "
            f"individually")


@claim("5.5.8-agreement-range", PAPER, "5.5.8")
def agreementRange():
    """Per-workload agreement across every single twelve-workload suite in the study.

    This exists to stop the control's 9 of 12 being called exceptional, which an earlier draft did.
    """
    counts = [_suiteAgreement(t)[0] for t in
              (BRACKET_STOCK, BRACKET_TUNE_1, BRACKET_TUNE_2,
               ABBA_A1, ABBA_A2, ABBA_B1, ABBA_B2, SPLIT_S2, REPAIR_P2T1)]
    return f"from {min(counts)} to {max(counts)} of 12"


@claim("5.5.8-config-stock", PAPER, "5.5.8")
def configStock():
    """Stock: floor at 1530, optimum 1537, and the largest headroom of any configuration."""
    return (f"| stock (Profile 3) | 1530 | {_medianSuiteOptimum(BRACKET_STOCK):.0f} | "
            f"{_bracketMeanGain(BRACKET_STOCK):.2f}% |")


@claim("5.5.8-config-split-b1", PAPER, "5.5.8")
def configSplitB1():
    """Split curve, ABBA leg b1."""
    return (f"| split (Profile 5, run `b1`) | 1530 | {_medianSuiteOptimum(ABBA_B1):.0f} | "
            f"{_bracketMeanGain(ABBA_B1):.2f}% |")


@claim("5.5.8-config-split-s2", PAPER, "5.5.8")
def configSplitS2():
    """Split curve, the separate s2 suite - a different session, same applied curve."""
    return (f"| split (Profile 5, run `s2`) | 1530 | {_medianSuiteOptimum(SPLIT_S2):.0f} | "
            f"{_bracketMeanGain(SPLIT_S2):.2f}% |")


@claim("5.5.8-config-repair", PAPER, "5.5.8")
def configRepair():
    """The negative control's own row."""
    return (f"| repair (Profile 2) | 1530 | {_medianSuiteOptimum(REPAIR_P2T1):.0f} | "
            f"{_bracketMeanGain(REPAIR_P2T1):.2f}% |")


@claim("5.5.8-config-fulltune", PAPER, "5.5.8")
def configFullTune():
    """The one configuration whose floor ends elsewhere - and whose optimum is there instead."""
    return (f"| full tune (Profile 4) | {_medianSuiteOptimum(BRACKET_TUNE_1):.0f} | "
            f"{_medianSuiteOptimum(BRACKET_TUNE_1):.0f} | "
            f"{_bracketMeanGain(BRACKET_TUNE_1):.2f}% |")


# --------------------------------------------------------------------------------------
# 5.8 in the PAPER - the same-session stock bracket, 2026-09-11
#
# The 5.8-bracket-* claims above pin the run's own README. These pin the paper's account of it,
# which is a separate document and can drift from the README independently.
# --------------------------------------------------------------------------------------


def _bracketTuneMean():
    return (_bracketMeanGain(BRACKET_TUNE_1) + _bracketMeanGain(BRACKET_TUNE_2)) / 2.0


def _bracketPerWorkloadGaps():
    """Stock minus tuned, per workload, with the tuned side averaged over both bracket legs."""
    gaps = []
    for name in BRACKET_STOCK:
        tuned = (suiteRowFigures(BRACKET_TUNE_1[name])[1]
                 + suiteRowFigures(BRACKET_TUNE_2[name])[1]) / 2.0
        gaps.append(suiteRowFigures(BRACKET_STOCK[name])[1] - tuned)
    return gaps


@claim("5.8-paper-gap", PAPER, "5.8")
def paperBracketGap():
    """The headline: stock gives up more efficiency than the tuned card, measured in one session."""
    return f"| **gap** | **{_bracketMeanGain(BRACKET_STOCK) - _bracketTuneMean():.2f} points** |"


@claim("5.8-paper-unanimous", PAPER, "5.8")
def paperBracketUnanimous():
    """Unanimity of DIRECTION. Checked per workload rather than asserted from the means."""
    gaps = _bracketPerWorkloadGaps()
    return (f"more headroom than the tuned card in {sum(1 for g in gaps if g > 0)} of {len(gaps)} "
            f"workloads")


@claim("5.8-paper-gap-range", PAPER, "5.8")
def paperBracketGapRange():
    """The spread behind that unanimity - the narrowest margin is close to session noise."""
    gaps = _bracketPerWorkloadGaps()
    return f"span **{min(gaps):.2f} to {max(gaps):.2f} points**"


@claim("5.8.1-cross-session-gap", PAPER, "5.8.1")
def paperCrossSessionGap():
    """The same comparison assembled across days, which is how every earlier one was built."""
    crossStock = mean(_bracketMeanGain(t) for t in REPLICATES_5060[1:])
    crossTune = mean(_bracketMeanGain(t) for t in (ABBA_A1, ABBA_A2))
    return (f"gives **{crossStock - crossTune:.2f} points** against this run's "
            f"**{_bracketMeanGain(BRACKET_STOCK) - _bracketTuneMean():.2f}**")


@claim("5.8.1-cross-session-error", PAPER, "5.8.1")
def paperCrossSessionError():
    """How much the cross-session construction understated the gap - the bound this run supplies."""
    crossStock = mean(_bracketMeanGain(t) for t in REPLICATES_5060[1:])
    crossTune = mean(_bracketMeanGain(t) for t in (ABBA_A1, ABBA_A2))
    inSession = _bracketMeanGain(BRACKET_STOCK) - _bracketTuneMean()
    return f"low by {inSession - (crossStock - crossTune):.2f} points"


@claim("5.8.2-drift-abba", PAPER, "5.8.2")
def paperDriftAbba():
    """The fortunate sample: same configuration twice, 2.5 h apart, agreeing to 0.04 points."""
    return (f"| §5.5.8's ABBA run, legs `a1` → `a2`, ~2.5 h | "
            f"**{_bracketMeanGain(ABBA_A2) - _bracketMeanGain(ABBA_A1):+.2f} points** |")


@claim("5.8.2-drift-bracket", PAPER, "5.8.2")
def paperDriftBracket():
    """The one that retracts it. Thirty times larger, same card, same profile, similar interval."""
    drift = _bracketMeanGain(BRACKET_TUNE_2) - _bracketMeanGain(BRACKET_TUNE_1)
    # The paper sets negatives with a typographic minus (U+2212), not a hyphen. Rendering the sign
    # explicitly rather than via {:+.2f} keeps the claim matching the document it audits, and unlike
    # the abs() in 5.8-bracket-drift above it does not assume which way the drift went.
    sign = "−" if drift < 0 else "+"
    return f"| this run, legs `p4t1` → `p4t2`, ~2 h | **{sign}{abs(drift):.2f} points** |"


SUITE_2060S = {
    name: (
        "rtx2060s-20260912/20260912-124138_rtx2060super-suite/"
        f"{stamp}_rtx2060super-suite-{name}_sweep.csv"
    )
    for name, stamp in {
        "copy": "20260912-124145",
        "reduce": "20260912-124640",
        "softmax": "20260912-125127",
        "layernorm": "20260912-125620",
        "bgemm32": "20260912-130111",
        "bgemm64": "20260912-130628",
        "bgemm128": "20260912-131127",
        "bgemm256": "20260912-131626",
        "bgemm1024": "20260912-132131",
        "attention": "20260912-132644",
        "conv": "20260912-133217",
        "gemm": "20260912-133734",
    }.items()
}

# The suite grid starts above the load floor and cannot see it, so the low-range sweep is the
# only extract that reaches the floor; the voltage floor claims must read it, not the suite.
_VOLT_2060S_LOWRANGE = (
    "rtx2060s-20260912/20260912-142900_rtx2060s-lowrange/"
    "20260912-142900_rtx2060s-lowrange-gemm_sweep_voltage.csv"
)


def _voltageFloorTopWithin(relativePath, toleranceV):
    """Like _voltageFloorTop but the highest clock within toleranceV of the floor.

    The TU106 sensor steps about six millivolts, so "still at the floor" and "one step off"
    give different answers and the paper reports both.
    """
    import csv
    with open(_REPO_ROOT / "data" / "frequency-sweeps" / relativePath,
              encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    floor = min(float(row["voltage"]) for row in rows)
    eps = 1e-9
    candidates = [
        float(row["achieved"])
        for row in rows
        if abs(float(row["voltage"]) - floor) <= toleranceV + eps
    ]
    return max(candidates)


@claim("5.5.7-knee-2060s", PAPER, "5.5.7")
def kneeTwentySixty():
    """Section 5.5.7 table row: the TU106 floor exit is too gradual for the rule to decide."""
    median = _medianSuiteOptimum(SUITE_2060S)
    strict = _voltageFloorTop(_VOLT_2060S_LOWRANGE)
    lenient = _voltageFloorTopWithin(_VOLT_2060S_LOWRANGE, 0.006)
    floorV = _voltageFloorValue(_VOLT_2060S_LOWRANGE)
    agree, total = _suiteAgreement(SUITE_2060S)
    emdash = chr(0x2014)
    return (
        "| RTX 2060 Super (Turing TU106) | "
        f"{median:.0f} MHz | {strict:.0f} or {lenient:.0f} MHz {emdash} see below | "
        f"{floorV:.3f} V | {agree} of {total} |"
    )


@claim("5.5.7-2060s-strict-reading", PAPER, "5.5.7")
def strictReadingTwentySixty():
    """Strict reading: the floor ends at the strict clock, one grid step below the median."""
    median = _medianSuiteOptimum(SUITE_2060S)
    strict = _voltageFloorTop(_VOLT_2060S_LOWRANGE)
    grid = sorted(sweep(SUITE_2060S["gemm"]))
    nearest = min(grid, key=lambda g: abs(g - strict))
    return (
        f"the floor ends at {strict:.0f} MHz and the nearest grid point is "
        f"{nearest:.0f}, one step below the measured {median:.0f}"
    )


@claim("5.5.7-2060s-lenient-reading", PAPER, "5.5.7")
def lenientReadingTwentySixty():
    """Lenient reading: one sensor step of slack lands the floor exactly on the median grid point."""
    median = _medianSuiteOptimum(SUITE_2060S)
    lenient = _voltageFloorTopWithin(_VOLT_2060S_LOWRANGE, 0.006)
    grid = sorted(sweep(SUITE_2060S["gemm"]))
    nearest = min(grid, key=lambda g: abs(g - lenient))
    if nearest != median:
        raise ValueError(
            f"lenient reading {nearest} does not equal the median optimum {median}"
        )
    return f"it ends at {lenient:.0f}, whose nearest grid point is {nearest:.0f} exactly"


@claim("5.5.7-2060s-flat-band", PAPER, "5.5.7")
def flatBandTwentySixty():
    """Honest width of the region actually at the floor; expected to fail against the paper's span."""
    floorV = _voltageFloorValue(_VOLT_2060S_LOWRANGE)
    import csv
    with open(_REPO_ROOT / "data" / "frequency-sweeps" / _VOLT_2060S_LOWRANGE,
              encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    eps = 1e-9
    atFloor = [
        float(row["achieved"])
        for row in rows
        if abs(float(row["voltage"]) - floorV) <= eps
    ]
    span = max(atFloor) - min(atFloor)
    return f"{floorV:.3f} V held across {span:.0f} MHz"


@claim("5.5.7-2060s-near-flat-band", PAPER, "5.5.7")
def nearFlatBandTwentySixty():
    """The 570 MHz the paper had attached to the floor value. Pinned apart so they cannot re-merge."""
    import csv
    with open(_REPO_ROOT / "data" / "frequency-sweeps" / _VOLT_2060S_LOWRANGE,
              encoding="utf-8-sig") as handle:
        rows = [(float(r["achieved"]), float(r["voltage"])) for r in csv.DictReader(handle)]
    floorV = min(v for _, v in rows)
    floorTop = max(m for m, v in rows if abs(v - floorV) <= 1e-9)
    below = [(m, v) for m, v in rows if m <= floorTop]
    millivolts = 1000 * (max(v for _, v in below) - floorV)
    return (f"voltage moves {millivolts:.0f} mV across the "
            f"{floorTop - min(m for m, _ in below):.0f} MHz from "
            f"{min(m for m, _ in below):.0f} to {floorTop:.0f} MHz")


@claim("5.5.7-2060s-agreement", PAPER, "5.5.7")
def agreementTwentySixty():
    """How many workloads pick the median on the TU106, against the other cards' range.

    The range was a literal "6 to 10" until 2026-09-29 (GPT Job 34): nothing computed it, and the
    current suites give 7 to 11. It is now computed over the suites the floor table uses: each
    5060 Ti stock replicate separately, the 3070 Ti suite and the 3060 suite.
    """
    agree, _total = _suiteAgreement(SUITE_2060S)
    others = [_suiteAgreement(t)[0] for t in REPLICATES_5060[1:]]
    others += [_suiteAgreement(SUITE_3070_SWEEPS)[0], _suiteAgreement(SUITE_3060)[0]]
    return f"{agree} of 12, against {min(others)} to {max(others)} on the other three cards"


# --------------------------------------------------------------------------------------------------
# 5.5.7 - Sessions E and E2 on the RTX 2060 Super (REGISTERED-PREDICTIONS 4c/4d, Amendments 2-3).
# Added 2026-09-28, after GPT Job 31 recomputed both sessions independently. Registered numbers come
# from analysis/score_session_e.py, the scorer committed before collection. Session E's offset suite
# is NOT SCOREABLE there (its grid shifted), so its descriptive median is computed here with the
# same efficiency peak the scorer uses, and says so.

SESSION_E_DIR = "rtx2060s-sessione-20260927"
SESSION_E2_DIR = "rtx2060s-sessione2-20260927"
_sessionE = {}


def sessionE(kind):
    """Score Session E ('4d') or E2 ('e2') with the committed scorer, restoring its registration."""
    if kind not in _sessionE:
        import score_session_e
        directory = _REPO_ROOT / "data" / "frequency-sweeps"
        saved = score_session_e.REGISTRATION
        try:
            if kind == "4d":
                score_session_e.REGISTRATION = score_session_e.SessionERegistration()
                _sessionE[kind] = score_session_e.score_4d(directory / SESSION_E_DIR)
            else:
                score_session_e.REGISTRATION = score_session_e.E2_REGISTRATION
                _sessionE[kind] = score_session_e.score_4c(directory / SESSION_E2_DIR)
        finally:
            score_session_e.REGISTRATION = saved
    return _sessionE[kind]


def _sessionESuite(directory, run):
    """{workload: rows} for one Session E/E2 suite, read with the scorer's own loader."""
    from analyze_sweep import loadSweep
    import score_session_e
    base = _REPO_ROOT / "data" / "frequency-sweeps" / directory
    suite = {}
    for name in score_session_e.SessionERegistration().workloads:
        found = sorted(base.glob(f"*-{run}-{name}_sweep.csv"))
        if len(found) != 1:
            raise ValueError(f"{directory}: expected one {run}-{name} sweep, found {len(found)}")
        suite[name] = loadSweep(found[0])
    return suite


def _efficiencyAt(rows, target):
    return next(r["efficiency"] for r in rows if r["target"] == target)


@claim("5.5.7-2060s-4d-minimum", PAPER, "5.5.7")
def sessionE4dMinimum():
    result = sessionE("4d")
    if result["4d"] != "PARTIAL":
        return f"4d is now {result['4d']}"
    asc, desc = sorted(result["reference_minimum"]), sorted(result["minimum"])
    return (f"its minimum set widened from {asc[0]:g}–{asc[-1]:g} to {desc[0]:g}–{desc[-1]:g} MHz, "
            f"with drivers {result['reference_driver']} and {result['driver']}")


@claim("5.5.7-2060s-e-offset-descriptive", PAPER, "5.5.7")
def sessionEOffsetDescriptive():
    from analyze_sweep import efficiencyPeak
    offset = [efficiencyPeak(rows)["target"]
              for rows in _sessionESuite(SESSION_E_DIR, "sessione-offset-2").values()]
    stock = [efficiencyPeak(rows)["target"]
             for rows in _sessionESuite(SESSION_E_DIR, "sessione-stock-1").values()]
    return (f"its offset median was {median(offset):g} MHz on the shifted grid, the same grid "
            f"position as stock's {median(stock):g}")


@claim("5.5.7-2060s-e2-verdict", PAPER, "5.5.7")
def sessionE2Verdict():
    result = sessionE("e2")
    m = result["medians"]
    return (f"The stock, offset and stock medians were {m['stock-4']:g} / {m['offset-5']:g} / "
            f"{m['stock-6']:g} MHz: {result['4c'].replace('_', ' ')}")


@claim("5.5.7-2060s-e2-return", PAPER, "5.5.7")
def sessionE2Return():
    result = sessionE("e2")
    if result["not_scoreable_reasons"]:
        return "E2 is no longer scoreable"
    return (f"stock returned to within {max(result['drift_per_workload_pct'].values()):.2f}% at "
            f"the worst workload")


@claim("5.5.7-2060s-e2-directions", PAPER, "5.5.7")
def sessionE2Directions():
    optima = sessionE("e2")["optima"]
    def moved(a, b):
        return sum(optima[a][n] != optima[b][n] for n in optima[a])
    return (f"individual optima moved at {moved('stock-4', 'offset-5')} and "
            f"{moved('stock-6', 'offset-5')} of 12 workloads against the two stock suites, which "
            f"themselves differ at {moved('stock-4', 'stock-6')}")


@claim("5.5.7-2060s-e2-relative-855", PAPER, "5.5.7")
def sessionE2Relative855():
    suites = {run: _sessionESuite(SESSION_E2_DIR, f"sessione2-{run}")
              for run in ("stock-4", "offset-5", "stock-6")}
    def relative(run):
        return 100 * median(_efficiencyAt(rows, 855) / max(r["efficiency"] for r in rows)
                            for rows in suites[run].values())
    def absolute(run):
        return 100 * median(1 - _efficiencyAt(suites["offset-5"][n], 855) / _efficiencyAt(rows, 855)
                            for n, rows in suites[run].items())
    low, high = sorted((relative("stock-4"), relative("stock-6")))
    fall = sorted((absolute("stock-4"), absolute("stock-6")))
    return (f"efficiency at 855 MHz rose from {low:.1f}–{high:.1f}% on stock to "
            f"{relative('offset-5'):.1f}% under the offset, while the median per-workload "
            f"absolute efficiency there fell "
            f"{fall[0]:.1f}–{fall[1]:.1f}%")


PLATEAU_BAND = (1402, 1867)   # the membw plateau: where the tuned card's crossbar is pinned
FULL_VOLT_BAND = (1402, 2100)  # every target in the tuned voltage extract


def _bandEnds(relativePath, band):
    """The lowest and highest rows whose COMMANDED target lies inside an inclusive band.

    Selecting on the commanded target rather than the achieved clock is not a detail: target
    1402 lands at 1400.6 MHz, so an achieved-clock filter silently drops the band's own floor.
    """
    rows = _voltageExtract(relativePath)
    targets = sorted(t for t in rows if band[0] <= t <= band[1])
    return rows[targets[0]], rows[targets[-1]]


@claim("3.3.2-crossbar-tracks-voltage-not-clock", PAPER, "3.3.2")
def crossbarTracksVoltageNotClock():
    """The evidence that the crossbar follows voltage, not the locked graphics clock."""
    low, high = _bandEnds(VOLT_TUNED, PLATEAU_BAND)
    if low["voltage"] != high["voltage"]:
        raise ValueError("voltage is not held constant across the plateau band")
    c = (high["achieved"] - low["achieved"]) / low["achieved"] * 100
    x = (high["crossbar"] - low["crossbar"]) / low["crossbar"] * 100
    return f"locking the graphics clock {c:.1f}% higher while voltage is held constant moves the crossbar {x:.1f}%"


@claim("3.3.2-stock-ratio-across-same-range", PAPER, "3.3.2")
def stockRatioAcrossSameRange():
    # "across the same range" fixes the window to PLATEAU_BAND, matching claim 1
    rows = _voltageExtract(VOLT_STOCK)
    targets = [t for t in sorted(rows) if PLATEAU_BAND[0] <= t <= PLATEAU_BAND[1]]
    r = sum(rows[t]["crossbar"] / rows[t]["achieved"] for t in targets) / len(targets)
    return f"the crossbar holds a near-constant {r:.2f} ratio to the graphics clock across the same range"


@claim("3.3.3-crossbar-elasticity", PAPER, "3.3.3")
def crossbarElasticity():
    """Which clock actually predicts membw throughput - the whole point of 3.3.3."""
    import math
    low, high = _bandEnds(VOLT_TUNED, FULL_VOLT_BAND)
    # log elasticity, not a percentage-change ratio; the two differ on this band
    gain = math.log(high["throughput"] / low["throughput"])
    a = gain / math.log(high["crossbar"] / low["crossbar"])
    b = gain / math.log(high["achieved"] / low["achieved"])
    return f"elasticity {a:.2f}, against {b:.2f} for the graphics clock"


# --------------------------------------------------------------------------------------
# 5.7.7 Caveats. Pinned 2026-09-24 from the local model's L3 inventory, which showed the section's
# other "numbers" are clock times, labels, range hyphens or restatements of 5.4.5 and 5.7.2.
# --------------------------------------------------------------------------------------

CAVEAT_MEMBW = {"stock": "oc-comparison-20260819/20260819-143337_5060ti-kittest-stock-membw-stock_sweep.csv",
                "full tuned": "membw-anomaly-20260819/20260819-204233_5060ti-oc-membw-anomaly_sweep.csv",
                "memory-only": "membw-anomaly-20260819/20260820-181307_5060ti-memonly-membw-anomaly_sweep.csv"}


@claim("5.7.7-collection-times", PAPER, "5.7.7")
def caveatCollectionTimes():
    """The three start times are read from the sweeps' own filenames (YYYYMMDD-HHMMSS), and the
    sweep() calls record them as this claim's provenance."""
    stamps = {}
    for name, path in CAVEAT_MEMBW.items():
        sweep(path)
        stamp = path.split("/")[-1][:15]
        stamps[name] = (f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}", f"{stamp[9:11]}:{stamp[11:13]}")
    stock, tuned, memonly = stamps["stock"], stamps["full tuned"], stamps["memory-only"]
    same = "the same day" if tuned[0] == stock[0] else tuned[0]
    return (f"stock at {stock[1]} on {stock[0]}, full tuned at {tuned[1]} {same}, "
            f"memory-only at {memonly[1]} the next")


@claim("5.7.7-memonly-out-of-band-power", PAPER, "5.7.7")
def caveatOutOfBandPower():
    """Power from sweep(), as every other 5.7 claim. Temperature is not in the loader, so it is read
    from the same two CSVs' temperature_avg_c column; sweep() has already logged both files."""
    import csv
    from audit_claims import REPO_ROOT
    stock = "oc-comparison-20260819/20260819-142844_5060ti-kittest-stock-gemm-stock_sweep.csv"
    memonly = "membw-anomaly-20260819/20260820-183206_5060ti-memonly-gemm_sweep.csv"

    def temperature(path, target):
        with (REPO_ROOT / "data" / "frequency-sweeps" / path).open(encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if int(row["target_frequency_mhz"]) == target]
        if len(rows) != 1:
            raise ValueError(f"{path}: expected one {target} MHz row, found {len(rows)}")
        return float(rows[0]["temperature_avg_c"])

    power, heat = [], []
    for target in (2475, 2625):
        power.append(abs(sweep(memonly)[target]["power"] / sweep(stock)[target]["power"] - 1) * 100)
        heat.append(temperature(memonly, target) - temperature(stock, target))
    return (f"memory-only drawing {power[0]:.1f}% and {power[1]:.1f}% more power than stock "
            f"with only {heat[0]:.1f} and {heat[1]:.1f} C to account for it")


# Job 45, 2026-10-03: remaining measured quantities in the named sections.
# Editorial dates, section numbers, and quantities without a primary numerical
# record are inventoried in docs/gpt-findings/2026-10-03-claims-coverage.md.
# They must not become claims that merely repeat the paper's own assertion.

@claim("3.3.2-issue-ceiling", PAPER, "3.3.2")
def regimeIssueCeiling():
    value = max(_probe(PROBE_ISSUE_CEILING)["aggregate_gbs"].values())
    return f"a ceiling near {value:.0f} GB/s that neither concurrency nor per-thread unrolling lifts"


@claim("3.3.2-rated-bandwidth", PAPER, "3.3.2")
def regimeRatedBandwidth():
    # This section refers back to 3.3.1's STOCK sweep and rated bandwidth.
    # 448 GB/s is the declared specification (28 Gb/s x 128 bits / 8),
    # not a measurement of the loaded memory clock. Using 13801 instead
    # would test a different denominator and could conceal the disagreement.
    ratedGbs = 28 * 128 / 8
    maximum = peak(sweep(STOCK_MEMBW_13PT))["throughput"] / 1e9
    return f"DRAM bandwidth, at roughly {100 * maximum / ratedGbs:.0f}% of the rated peak"


@claim("3.3.2-equal-voltage-crossbar-gaps", PAPER, "3.3.2")
def regimeEqualVoltageCrossbarGaps():
    stock, tuned = _voltageExtract(VOLT_STOCK), _voltageExtract(VOLT_TUNED)
    targets = (1477, 1560)  # The two points the sentence names, not a fitted band.
    if any(stock[t]["voltage"] != tuned[t]["voltage"] for t in targets):
        raise ValueError("the named points no longer have equal reported voltage")
    voltages = {stock[t]["voltage"] for t in targets}
    if len(voltages) != 1:
        raise ValueError("the two points no longer share one reported voltage")
    gaps = [stock[t]["crossbar"] - tuned[t]["crossbar"] for t in targets]
    return (f"At {targets[0]} and {targets[1]} MHz the two configurations both report "
            f"{voltages.pop():.3f} V, yet their crossbar clocks differ by "
            f"{gaps[0]:.0f} and {gaps[1]:.0f} MHz (5.7.3).")


QUICKEDIT_GEMM_P1 = "20260816-124651_5060ti-gemm-fine-p1_sweep.csv"
QUICKEDIT_GEMM_P2 = "20260816-131140_5060ti-gemm-fine-p2_sweep.csv"
QUICKEDIT_EXCLUDED_TARGETS = (1725, 1785)


@claim("5.4.2-pass-label", PAPER, "5.4.2")
def quickEditPassLabel():
    # Pin only the pass label carried by the source filename. The literal
    # 'froze' anchors it uniquely; this does not time or diagnose the stall.
    import re
    sweep(QUICKEDIT_GEMM_P1)
    match = re.search(r"-p(\d+)_sweep[.]csv$", QUICKEDIT_GEMM_P1)
    if match is None:
        raise ValueError("the interrupted run's source lacks a pass label")
    return f"`gemm` pass {int(match.group(1))} froze"


@claim("5.4.2-affected-neighbours", PAPER, "5.4.2")
def quickEditAffectedNeighbours():
    # These are the historically documented exclusions, not an automatically
    # discovered corruption threshold. Verify their adjacency and recovery;
    # the CSVs cannot establish QuickEdit as the cause or time its selection.
    first, second = sweep(QUICKEDIT_GEMM_P1), sweep(QUICKEDIT_GEMM_P2)
    targets = sorted(first)
    positions = [targets.index(t) for t in QUICKEDIT_EXCLUDED_TARGETS]
    if positions != list(range(positions[0], positions[0] + len(positions))):
        raise ValueError("the documented affected points are no longer neighbouring targets")
    if any(first[t]["throughput"] >= second[t]["throughput"]
           for t in QUICKEDIT_EXCLUDED_TARGETS):
        raise ValueError("a documented affected point does not recover in pass 2")
    count = len(positions)
    word = "two" if count == 2 else str(count)
    return f"while the {word} neighbouring points were measurably corrupted"


@claim("5.7-upper-curve-clock", PAPER, "5.7")
def summaryUpperCurveClock():
    # Snapshot input, not a voltage measurement. Use the repeated top block;
    # summing an offset-transition record would repeat the decoder's old bug.
    snapshot = _probe("data/afterburner-profiles/5060ti-profiles-20260908.json")
    points = snapshot["profiles"]["Profile4"]["curve_points"]
    last = points[-1]["applied_mhz"]
    repeated = [p for p in points if p["applied_mhz"] == last]
    if len(repeated) < 2:
        raise ValueError("the archived tuned profile no longer has a repeated plateau")
    approximate = round(last / 100) * 100  # 'near 3000', to the stated hundred MHz precision.
    return f"a core V/F curve pinned flat near {approximate:.0f} MHz"


@claim("5.7-original-three-grid-agreement", PAPER, "5.7")
def originalSummaryGridAgreement():
    # The introduction and 5.7.7 name the original three runs. Do not silently
    # replace the stock run with the later 21:16 voltage run to make this pass.
    # Corrected 2026-10-03 (GPT Job 45): the three are NOT on one grid, so the paper now says so
    # and this renders the count of targets the original stock run shares with the other two.
    stock = set(sweep(CAVEAT_MEMBW["stock"]))
    tuned, memonly = set(sweep(CAVEAT_MEMBW["full tuned"])), set(sweep(CAVEAT_MEMBW["memory-only"]))
    if tuned != memonly:
        raise ValueError("the original tuned and memory-only runs no longer share one grid")
    shared = len(stock & tuned)
    word = "none" if shared == 0 else str(shared)
    return (f"the original stock run shares {word} of its {len(stock)} locked targets with the "
            f"{len(tuned)}-point tuned and memory-only runs")


@claim("5.7-historical-mismatched-targets", PAPER, "5.7")
def summaryHistoricalMismatchedTargets():
    # Reproduce the old pairing to pin the correction's account of how it erred.
    # Never use this pair as the current matched-memory-overclock result.
    stock, memonly = sweep(STOCK_MEMBW_13PT), sweep(MEMONLY_MEMBW)
    stockTargets = (1545, 1702, 1852, 2010)
    memoryTargets = (1560, 1710, 1867, 2025)
    for left, right in zip(stockTargets, memoryTargets):
        if left == right or left not in stock or right not in memonly:
            raise ValueError("the historical mismatched pair changed")
    return (f"It paired stock at {'/'.join(map(str, stockTargets))} MHz with memory-only "
            f"at {'/'.join(map(str, memoryTargets))}")


@claim("5.7-historical-wrong-memory-range", PAPER, "5.7")
def summaryHistoricalWrongMemoryRange():
    stock, memonly = sweep(STOCK_MEMBW_13PT), sweep(MEMONLY_MEMBW)
    pairs = ((1545, 1560), (1702, 1710), (1852, 1867), (2010, 2025))
    ratios = [memonly[right]["throughput"] / stock[left]["throughput"] for left, right in pairs]
    return (f'The `membw` row read *"{signedPct(min(ratios))} to '
            f'{signedPct(max(ratios))} over stock"*')


@claim("5.7-matched-stock-grid-size", PAPER, "5.7")
def summaryMatchedStockGridSize():
    stock, memonly = sweep(STOCK_MEMBW_VOLT), sweep(MEMONLY_MEMBW)
    if set(stock) != set(memonly):
        raise ValueError("the correction's stock and memory-only grids no longer match")
    return f"Against the one stock `membw` sweep on the same {len(stock)}-point grid"


@claim("5.7-corrected-memory-range", PAPER, "5.7")
def summaryCorrectedMemoryRange():
    stock, memonly = sweep(STOCK_MEMBW_VOLT), sweep(MEMONLY_MEMBW)
    ratios = [memonly[t]["throughput"] / stock[t]["throughput"]
              for t in sorted(set(stock) & set(memonly))]
    return f"the range is {signedPct(min(ratios))} to {signedPct(max(ratios))}."


def _summaryPlateauLead():
    memonly, tuned = sweep(MEMONLY_MEMBW), sweep(TUNED_MEMBW)
    ratios = {t: memonly[t]["throughput"] / tuned[t]["throughput"]
              for t in SUMMARY_PLATEAU_TARGETS}
    target = max(ratios, key=ratios.get)
    return target, ratios[target]


@claim("5.7-corrected-loss-base", PAPER, "5.7")
def summaryCorrectedLossBase():
    target, ratio = _summaryPlateauLead()
    return (f"Memory-only delivers {100 * (ratio - 1):.1f}% more than tuned at {target} MHz; "
            f"as a change from memory-only to tuned that is {signedPct(1 / ratio)}.")


@claim("5.7.7-effect-size", PAPER, "5.7.7")
def caveatEffectSize():
    _, ratio = _summaryPlateauLead()
    return f"Effect sizes up to {100 * (ratio - 1):.1f}%"


@claim("5.7.7-replicate-resolution", PAPER, "5.7.7")
def caveatReplicateResolution():
    count = len(REPLICATES)
    word = "three" if count == 3 else str(count)
    return (f"power reproducing at {_spreadsFor('power'):.2f}% and efficiency at "
            f"{_spreadsFor('efficiency'):.2f}% across {word} replicates")


@claim("5.7.7-cross-session-drift", PAPER, "5.7.7")
def caveatCrossSessionDrift():
    today = sweep(MEMONLY_GEMM_SAMESESSION)
    previous = [sweep(p) for p in MEMONLY_GEMM_CLEAN]
    shared = sorted(set(today).intersection(*(set(p) for p in previous)))
    drift = mean(100 * (today[t]["throughput"] / mean(p[t]["throughput"] for p in previous) - 1)
                 for t in shared)
    return f"cross-session drift at {drift:.2f}% on throughput"


@claim("5.7.7-out-of-band-targets", PAPER, "5.7.7")
def caveatOutOfBandTargets():
    targets = (2475, 2625)  # The two points tested by caveatOutOfBandPower.
    stock, memonly = sweep(STOCK_GEMM), sweep(MEMONLY_GEMM)
    for target in targets:
        if target not in stock or target not in memonly:
            raise ValueError(f"the out-of-band comparison lacks target {target}")
    word = "Two" if len(targets) == 2 else str(len(targets))
    return (f"{word} `gemm` points outside the comparison band "
            f"({targets[0]} and {targets[1]} MHz)")


# --------------------------------------------------------------------------------------------------
# 5.5.9 - the causal test repeated on the RTX 3070 Ti (Session D, REGISTERED-PREDICTIONS 4a/4b/8a).
# Added 2026-09-26. Every number comes from analysis/score_session_d.py, the scorer committed before
# collection, run on the committed directory - not from a second implementation that could disagree
# with it. Session D2 (8d) is NOT SCOREABLE by that scorer and its descriptive medians are not pinned
# here yet (local-model job L8).

SESSION_D_DIR = "rtx3070ti-sessiond-20260924"
_sessionD = {}


def sessionD(kind):
    if kind not in _sessionD:
        import score_session_d
        from audit_claims import REPO_ROOT
        directory = REPO_ROOT / "data" / "frequency-sweeps" / SESSION_D_DIR
        scorer = score_session_d.score if kind == "main" else score_session_d.score_replicate
        _sessionD[kind] = scorer(directory)
    return _sessionD[kind]


def _mhz(value):
    return f"{value:g} MHz"


@claim("5.5.9-results-edit-rows", PAPER, "5.5.9")
def sessionDEditRows():
    main, rep = sessionD("main"), sessionD("replicate")
    if (main["4a"], main["4b"], rep["8a"]) != ("PASS", "FAIL", "PASS"):
        return f"verdicts changed: 4a {main['4a']}, 4b {main['4b']}, 8a {rep['8a']}"
    return (f"| `edit1-2` | D | Edit 1 | {_mhz(main['medians']['edit1-2'])} | 1170–1275 | ✅ 4a PASS |\n"
            f"| `edit2-3` | D | Edit 2 | {_mhz(main['medians']['edit2-3'])} | 1485–1500 | ⛔ 4b FAIL |\n"
            f"| `stock-4` | D | stock | {_mhz(main['medians']['stock-4'])} | — | returned; worst workload "
            f"{max(main['drift_per_workload_pct'].values()):.3f}% |\n"
            f"| `edit1-5` | D | Edit 1 | {_mhz(rep['medians']['edit1-5'])} | 1170–1275 | ✅ 8a PASS |\n"
            f"| `stock-6` | D | stock | {_mhz(rep['medians']['stock-6'])} | — | returned; worst workload "
            f"{max(rep['drift_per_workload_pct'].values()):.3f}% |")


@claim("5.5.9-stock-baseline", PAPER, "5.5.9")
def sessionDBaseline():
    main = sessionD("main")
    return f"| `stock-1` | D | stock | {_mhz(main['medians']['stock-1'])} | — | baseline, as registered |"


def _directions(before, after):
    down = sum(after[n] < before[n] for n in before)
    up = sum(after[n] > before[n] for n in before)
    return down, up, len(before) - down - up


@claim("5.5.9-edit1-directions", PAPER, "5.5.9")
def sessionDDirections():
    main, rep = sessionD("main"), sessionD("replicate")
    # The stock-against-stock rows are the baseline GPT Job 23 found missing (2026-09-26).
    s1 = _directions(main["optima"]["stock-1"], main["optima"]["stock-4"])
    s2 = _directions(rep["optima"]["stock-4"], rep["optima"]["stock-6"])
    a = _directions(main["optima"]["stock-1"], main["optima"]["edit1-2"])
    b = _directions(rep["optima"]["stock-4"], rep["optima"]["edit1-5"])
    return (f"| `stock-1` against `stock-4`, identical curves | {s1[0]} | {s1[1]} | {s1[2]} |\n"
            f"| `stock-4` against `stock-6`, identical curves | {s2[0]} | {s2[1]} | {s2[2]} |\n"
            f"| `edit1-2` against `stock-1` | {a[0]} | {a[1]} | {a[2]} |\n"
            f"| `edit1-5` against `stock-4` | {b[0]} | {b[1]} | {b[2]} |")


@claim("5.5.9-edit1-at-1590", PAPER, "5.5.9")
def sessionDAt1590():
    main, rep = sessionD("main"), sessionD("replicate")
    words = {2: "Two", 5: "five"}
    first = sum(v == 1590 for v in main["optima"]["edit1-2"].values())
    second = sum(v == 1590 for v in rep["optima"]["edit1-5"].values())
    stock = [main["optima"]["stock-1"], main["optima"]["stock-4"], rep["optima"]["stock-6"]]
    if any(v == 1590 for suite in stock for v in suite.values()):
        return "a Session D stock suite now peaks at 1590 MHz"
    return (f"{words.get(first, first)} workloads in `edit1-2` and {words.get(second, second)} in "
            f"`edit1-5` moved to 1590 MHz, above the stock optimum; no Session D stock suite has a "
            f"workload peaking there.")


@claim("5.5.9-control-split", PAPER, "5.5.9")
def sessionDControlSplit():
    values = sorted(sessionD("main")["optima"]["edit2-3"].values())
    low, high = values[:6], values[6:]
    return (f"The twelve optima fall at {', '.join(f'{v:g}' for v in low)} | "
            f"{', '.join(f'{v:g}' for v in high[:-1])} and {high[-1]:g} MHz")


# --------------------------------------------------------------------------------------------------
# 5.5.10 - LLM decode against the load floor on the RTX 5060 Ti (REGISTERED-PREDICTIONS 13). Added
# 2026-09-28. Verdicts and efficiencies come from analysis/score_q1_llm.py, the scorer committed with
# the data; nothing here re-implements its criteria.

_q1 = {}


def q1(workload):
    if workload not in _q1:
        import score_q1_llm
        _q1[workload] = score_q1_llm.score(score_q1_llm.DEFAULT_DIR, workload)
    return _q1[workload]


@claim("5.5.10-verdicts", PAPER, "5.5.10")
def q1Verdicts():
    decode, prefill = q1("decode"), q1("prefill")
    if decode["problems"] or prefill["problems"]:
        return "section 13 is no longer interpretable"
    def peak(r):
        a = max(r["e_asc"], key=r["e_asc"].get)
        b = max(r["e_desc"], key=r["e_desc"].get)
        return f"{a:g} and {b:g}"
    return (f"decode {decode['verdict']}, peaking at {peak(decode)} MHz ascending and descending "
            f"with repeat noise d = {100 * decode['d']:.2f}%; prefill {prefill['verdict']}, peaking "
            f"at {peak(prefill)} MHz with d = {100 * prefill['d']:.2f}%")


@claim("5.5.10-neighbours", PAPER, "5.5.10")
def q1Neighbours():
    r = q1("decode")
    rel = {t: 100 * r["e"][t] / r["max_e"] for t in r["e"]}
    return f"{rel[1342]:.1f}% of the peak at 1342 MHz and {rel[1777]:.1f}% at 1777 MHz"


@claim("5.5.10-elasticity", PAPER, "5.5.10")
def q1Elasticity():
    import math
    r = q1("decode")
    clock = 1560 / 465
    speed = r["throughput"][1560] / r["throughput"][465]
    power = r["power"][1560] / r["power"][465]
    return (f"{r['throughput'][465]:.1f} tok/s at 465 MHz against {r['throughput'][1560]:.1f} at "
            f"1560 and {r['throughput'][3090]:.1f} at the top of the grid. Over that 3.35-fold clock "
            f"rise, throughput grows {speed:.2f}-fold and power {power:.2f}-fold, elasticities of "
            f"{math.log(speed) / math.log(clock):.2f} and {math.log(power) / math.log(clock):.2f}")


@claim("5.5.10-floor-voltage", PAPER, "5.5.10")
def q1FloorVoltage():
    readings = [v for w in ("decode", "prefill") for t, pair in q1(w)["voltage"].items()
                if t <= 1560 for v in pair]
    rise = sorted({v for w in ("decode", "prefill") for v in q1(w)["voltage"][1777]})
    if None in readings or any(abs(v - 0.720) > 1e-9 for v in readings):
        return "the floor is no longer 0.720 V throughout 465-1560"
    return (f"0.720 V at every target from 465 to 1560 MHz in all four sweeps, first rising at "
            f"1777 MHz ({rise[0]:.3f}–{rise[-1]:.3f} V)")


@claim("5.5.10-prefill-outlier", PAPER, "5.5.10")
def q1PrefillOutlier():
    import score_q1_llm
    _, asc, _ = score_q1_llm.read_sweep(score_q1_llm.DEFAULT_DIR, "5060ti-q1-prefill-asc")
    _, desc, _ = score_q1_llm.read_sweep(score_q1_llm.DEFAULT_DIR, "5060ti-q1-prefill-desc")
    return (f"{float(asc[465]['bench_throughput']):.0f} tok/s ascending against "
            f"{float(desc[465]['bench_throughput']):.0f} descending")


# --------------------------------------------------------------------------------------------------
# 5.5.8 - the floor ladder (REGISTERED-PREDICTIONS 1): rungs B and C, predicted 2026-09-11 and
# collected 2026-09-23 / 09-26. Picks, regrets and baselines come from
# analysis/models/predict_from_curve.py, the module whose rung picks were registered; nothing here
# re-derives its criteria. Medians are on the TARGET grid, as the registration scored them.

_ladder = {}


def _ladderModule():
    if "module" not in _ladder:
        _sys.path.insert(0, str(_REPO_ROOT / "analysis" / "models"))
        import predict_from_curve
        _ladder["module"] = predict_from_curve
        _ladder["curves"] = predict_from_curve.loadLadderCurves()
    return _ladder["module"], _ladder["curves"]


def _rung(configuration):
    module, curves = _ladderModule()
    subset = [entry for entry in curves if entry[0] == configuration]
    pick = module.nearestTarget(subset[0][2], module.floorExtentMhz(configuration))
    optima = [max(curve, key=curve.get) for _, _, curve in subset]
    return {"extent": module.floorExtentMhz(configuration), "pick": pick,
            "median": median(optima), "on_pick": sum(o == pick for o in optima),
            "mechanism": module.evaluateStrategy(subset, lambda c, w, curve: pick),
            "fixed": module.evaluateStrategy(subset, lambda c, w, curve: 1545)}


@claim("5.5.8-ladder-rows", PAPER, "5.5.8")
def ladderRows():
    rows = []
    for label, configuration in (("B", "rungB"), ("C", "rungC")):
        r = _rung(configuration)
        verdict = "✅" if r["median"] == r["pick"] else "⛔"
        rows.append(f"| {label} | {r['extent']:.0f} MHz | {r['pick']} | {r['median']:g} {verdict} | "
                    f"{r['on_pick']} of 12 |")
    return chr(10).join(rows)


@claim("5.5.8-ladder-prospective", PAPER, "5.5.8")
def ladderProspective():
    b, c = _rung("rungB"), _rung("rungC")
    return (f"{b['mechanism']['mean_regret_pct']:.3f}% and {c['mechanism']['mean_regret_pct']:.3f}% "
            f"mean regret, with {b['mechanism']['exact_match_rate'] * 12:.0f} and "
            f"{c['mechanism']['exact_match_rate'] * 12:.0f} of 12 workloads exact, against "
            f"{b['fixed']['mean_regret_pct']:.3f}% and {c['fixed']['mean_regret_pct']:.3f}% with "
            f"{b['fixed']['exact_match_rate'] * 12:.0f} exact for the 1545 MHz constant")


@claim("5.5.8-ladder-extended", PAPER, "5.5.8")
def ladderExtended():
    module, ladder = _ladderModule()
    curves = module.loadEfficiencyCurves() + ladder
    mechanism, _ = module.chooseByMechanism(curves)
    fixed, best = module.chooseByBestFixedFrequency(curves)
    return (f"{module.evaluateStrategy(curves, mechanism)['mean_regret_pct']:.3f}% against "
            f"{module.evaluateStrategy(curves, fixed)['mean_regret_pct']:.3f}% for the best "
            f"hindsight constant, {best} MHz, over {len(curves)} sweeps")


# --------------------------------------------------------------------------------------------------
# 5.7.3 - the memory-matched plateau repeat (REGISTERED-PREDICTIONS 12, worklist 4j), 2026-09-26.
# Pinned 2026-09-28; the section described it in prose, unpinned, since collection.

MEMMATCHED_DIR = "5060ti-memmatched-20260926"


def _memmatched(tag):
    base = _REPO_ROOT / "data" / "frequency-sweeps" / MEMMATCHED_DIR
    [path] = sorted(base.glob(f"*_5060ti-4j-{tag}_sweep.csv"))
    return path


def _memmatchedRows(tag):
    from analyze_sweep import loadSweep
    return {row["target"]: row for row in loadSweep(_memmatched(tag))}


def _memmatchedCrossbar(tag):
    import csv
    path = _memmatched(tag).with_name(_memmatched(tag).stem + "_voltage.csv")
    with open(path, encoding="utf-8-sig") as handle:
        return {int(float(r["target"])): float(r["crossbar"]) for r in csv.DictReader(handle)}


@claim("5.7.3-4j-plateau", PAPER, "5.7.3")
def memmatchedPlateau():
    stock, curve = _memmatchedRows("stock-membw"), _memmatchedRows("curve3-membw")
    band = [t for t in sorted(stock) if 1560 <= t <= 1867]
    gaps = [100 * (1 - curve[t]["throughput"] / stock[t]["throughput"]) for t in band]
    if min(gaps) <= 0:
        return "curve 3 is no longer below stock at every target 1560-1867"
    return (f"curve is {min(gaps):.1f}–{max(gaps):.1f}% below stock at every target from "
            f"{band[0]} to {band[-1]} MHz")


@claim("5.7.3-4j-crossbar", PAPER, "5.7.3")
def memmatchedCrossbar():
    curve, stock = _memmatchedCrossbar("curve3-membw"), _memmatchedCrossbar("stock-membw")
    band = [t for t in sorted(curve) if 1402 <= t <= 1867]
    held = [curve[t] for t in band]
    return (f"crossbar held at {min(held):.0f}–{max(held):.0f} MHz while stock's rises from "
            f"{stock[band[0]]:.0f} to {stock[band[-1]]:.0f}")


@claim("5.7.3-4j-gate", PAPER, "5.7.3")
def memmatchedGate():
    opening, closing = _memmatchedRows("stock-membw"), _memmatchedRows("stock-membw-r2")
    change = 100 * (mean(closing[t]["throughput"] for t in opening)
                    / mean(opening[t]["throughput"] for t in opening) - 1)
    return f"the closing stock sweep's band mean landed {change:+.2f}% from the opening one"


# --------------------------------------------------------------------------------------------------
# Abstract - the ladder, E2 and the LLM check, added to the contribution sentence and after it on
# 2026-09-28. Each reuses the section's own scorer path, so the abstract cannot drift from 5.5.x.


@claim("abstract-ladder", PAPER, "Abstract")
def abstractLadder():
    b, c = _rung("rungB"), _rung("rungC")
    if b["median"] != b["pick"] or c["median"] != c["pick"]:
        return "a ladder rung no longer lands on its pick"
    return (f"put\n> the median on their predicted grid points, {b['pick']} and {c['pick']} MHz, "
            f"giving four floor positions in\n> order")


@claim("abstract-e2", PAPER, "Abstract")
def abstractE2():
    result = sessionE("e2")
    if result["4c"] != "FAIL_NO_MOVEMENT":
        return f"E2 is now {result['4c']}"
    return (f"a registered whole-curve offset left the median\n> optimum at "
            f"{result['medians']['offset-5']:g} MHz")


@claim("abstract-llm-decode", PAPER, "Abstract")
def abstractLlmDecode():
    r = q1("decode")
    if r["verdict"] != "HOLDS":
        return f"decode is now {r['verdict']}"
    return f"peaked in tokens per joule at {r['best']} MHz, the grid point at the floor's end"


# --------------------------------------------------------------------------------------------------
# 3.3.4 / 3.3.5 - the suite and the LLM workload, described in Methods on 2026-09-28. Rendered from
# the workload code itself, so the description cannot drift from what runs.


@claim("3.3.4-intensity-span", PAPER, "3.3.4")
def suiteIntensitySpan():
    values = [suiteDeclaredIntensity(name) for name in SUITE_INTENSITY_NAMES]
    gemm = 8192 / 6   # 2 n^3 FLOP over 3 n^2 fp32 elements of 4 bytes, n = 8192
    return (f"Declared intensity runs from {formatIntensity(min(values))} to "
            f"{int(max(max(values), gemm))} FLOP/byte")


@claim("3.3.5-llm-work", PAPER, "3.3.5")
def llmWork():
    import llm_workload
    prompt, _, prefillReps, prefillLead = llm_workload.WORK["llm-prefill"]
    _, generated, decodeReps, decodeLead = llm_workload.WORK["llm-decode"]
    return (f"`llm-decode` generates {generated} tokens and `llm-prefill` processes {prompt} prompt "
            f"tokens")
