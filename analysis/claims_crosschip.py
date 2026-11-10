"""
Claims about the RTX 3070 Ti measurements of paper 5.5 and 2.6, checked against their source CSVs.

READ audit_claims.py FIRST. Each function below returns the exact string its document must
contain, computed from the data. Nothing here stores an expected number.

WHY THIS IS A SEPARATE MODULE FROM claims_consumer.py
    ⛔ THE REASON RECORDED HERE WAS OVERTAKEN AND IS CORRECTED, 2026-09-12. It argued that
    claims_consumer.py "opens 'Claims about the RTX 5060 Ti consumer measurements'" and is
    therefore one card's file, so "a second chip does not belong inside it". By the time that
    was written the 3070 Ti suite was ALREADY being read from claims_consumer.py through
    SUITE_3070_SWEEPS, and the 3060 followed. The premise was false when it was relied on.

    THE SPLIT THAT ACTUALLY EXISTS IS BY STUDY. This module is the self-contained two-BIOS
    comparison on one 3070 Ti, sections 2.6 and 5.5-5.5.3. claims_consumer.py holds the sweeps
    this project ran on its own card plus every claim that sets cards SIDE BY SIDE - 5.5.4's
    rank correlation and 5.5.7's knee table compare four chips inside one claim and could never
    have lived in a per-card module.

    ⚠️ SO THE 3070 Ti IS REACHED FROM TWO MODULES, through two independent sets of constants
    into the same rtx3070ti-20260825/ tree. The original worry - that a shared constant lets a
    claim silently read the wrong hardware - is not addressed by the arrangement that exists.
    What does address it is that every path in both files is a literal, so a wrong card shows up
    in the diff. Do not add a helper that resolves a card name to a directory.

WHAT THESE RUNS ARE
    Five sweeps on one Gigabyte RTX 3070 Ti GAMING OC rev2.0, collected 2026-08-25 on a third
    party's machine and all verified quiet - encoder and decoder 0% at preflight.

      silent-asfound/   gemm + membw   BIOS switch as found, VBIOS 94.04.5a.00.91
      oc-bios/          gemm + membw   BIOS switch moved to OC, VBIOS 94.05.5a.00.bd
      oc-bios-membw-r2/ membw          a second OC membw sweep; its gemm half was REFUSED
                                       because a browser held 11% of the GPU, which is the
                                       guard working, not a failure
      matched-grid/     gemm           OC BIOS forced onto the silent band so the two share
                                       targets

    THE TWO COLLECTIONS SHARE NO GRID POINTS. Each builds its grid from 40% of its own BIOS's
    maximum, so silent runs 855-2130 and OC runs 885-2190 with nothing in common. Every
    matched-frequency claim below reads matched-grid, and only seven of its thirteen targets line
    up with the silent sweep because it was given a 2115 MHz ceiling - the clocks.max.graphics
    reading - rather than 2130, the silent sweep's actual top target. The claims compute that
    overlap rather than assuming it.
"""

from statistics import fmean as mean

from audit_claims import claim, sweep, throttleReasons, voltageJoin

PAPER = "docs/PAPER_DRAFT.md"

ROOT = "rtx3070ti-20260825/"
SILENT_GEMM = ROOT + "silent-asfound/20260825-130824_rtx3070ti-gaming-oc-bios-silent-asfound-gemm_sweep.csv"
SILENT_MEMBW = ROOT + "silent-asfound/20260825-131304_rtx3070ti-gaming-oc-bios-silent-asfound-membw_sweep.csv"
OC_GEMM = ROOT + "oc-bios/20260825-133241_rtx3070ti-gaming-oc-bios-oc-gemm_sweep.csv"
OC_MEMBW_RUNS = [
    ROOT + "oc-bios-membw-r2/20260825-132601_rtx3070ti-gaming-oc-bios-oc-membw_sweep.csv",
    ROOT + "oc-bios/20260825-133716_rtx3070ti-gaming-oc-bios-oc-membw_sweep.csv",
]
OC_GEMM_MATCHED = ROOT + "matched-grid/20260825-134916_rtx3070ti-bios-oc-matchedgrid-gemm_sweep.csv"


def _peak(path):
    return max(sweep(path).values(), key=lambda row: row["throughput"])


def _optimum(path):
    return max(sweep(path).values(), key=lambda row: row["throughput"] / row["power"])


def _matchedTargets():
    """The grid points the silent sweep and the matched-grid OC sweep have in common.

    Computed, never hardcoded. The overlap is an accident of the ceiling the matched run was given
    and the number would silently change if either sweep were replaced.
    """
    return sorted(set(sweep(SILENT_GEMM)) & set(sweep(OC_GEMM_MATCHED)))


def _matched(field):
    silent, oc = sweep(SILENT_GEMM), sweep(OC_GEMM_MATCHED)
    return [(oc[t][field] / silent[t][field] - 1) * 100 for t in _matchedTargets()]


# --------------------------------------------------------------------------------------
# 5.5 - the second chip
# --------------------------------------------------------------------------------------

@claim("5.5-headroom", PAPER, "5.5")
def headroomReproduces():
    """The project's central claim, on a second architecture.

    Read off the SILENT position, which is how the card was found. Both figures come from the same
    two rows so they cannot drift apart.
    """
    peak, optimum = _peak(SILENT_GEMM), _optimum(SILENT_GEMM)
    lost = 100 * (1 - optimum["throughput"] / peak["throughput"])
    saved = 100 * (1 - optimum["power"] / peak["power"])
    return f"costs\n**{lost:.1f}%** of throughput and saves **{saved:.1f}%** of power"


@claim("5.5-peak-clocks", PAPER, "5.5")
def peakClocksAgainstCeilings():
    """Both BIOSes stop short of their own ceiling, which is the claim the sentence makes.

    RAISES if either one ever reaches its ceiling, because the surrounding prose says the card is
    power-limited rather than clock-limited and that would no longer be the reading.
    """
    silentPeak, ocPeak = _peak(SILENT_GEMM), _peak(OC_GEMM)
    silentTop, ocTop = max(sweep(SILENT_GEMM)), max(sweep(OC_GEMM))
    if silentPeak["mhz"] >= silentTop or ocPeak["mhz"] >= ocTop:
        raise ValueError(f"a BIOS now reaches its ceiling: silent {silentPeak['mhz']:.1f} of "
                         f"{silentTop}, oc {ocPeak['mhz']:.1f} of {ocTop}")
    return (f"{silentPeak['mhz']:.1f} in\none position and {ocPeak['mhz']:.1f} in the other - "
            f"against ceilings of {silentTop} and {ocTop} MHz")


@claim("5.5-clock-ladder", PAPER, "5.5")
def clockLadder():
    """The ladder the two BIOSes expose, which is what makes this a different measurement problem.

    The bin COUNT is not in the CSVs - it is in the run logs - so only the range is computed here
    and the count is left to the prose. Rendering half a fact is better than pretending the whole
    of it was checked.
    """
    lo = min(min(sweep(p)) for p in (SILENT_GEMM, OC_GEMM))
    hi = max(max(sweep(p)) for p in (SILENT_GEMM, OC_GEMM))
    if lo <= 405 or hi != 2190:
        raise ValueError(f"the swept range moved: {lo}-{hi}")
    return f"116-120 bins, 405-{hi} MHz"


# --------------------------------------------------------------------------------------
# 5.5.1 - the two BIOSes
# --------------------------------------------------------------------------------------

@claim("5.5.1-matched-band", PAPER, "5.5.1")
def matchedBand():
    targets = _matchedTargets()
    return (f"Seven grid points from {targets[0]} to {targets[-1]} MHz" if len(targets) == 7
            else f"{len(targets)} grid points from {targets[0]} to {targets[-1]} MHz")


@claim("5.5.1-matched-clocks", PAPER, "5.5.1")
def matchedClocks():
    """The comparison is only a matched-frequency one if the clocks actually matched."""
    silent, oc = sweep(SILENT_GEMM), sweep(OC_GEMM_MATCHED)
    worst = max(abs(oc[t]["mhz"] - silent[t]["mhz"]) for t in _matchedTargets())
    return f"achieved clocks equal to {worst:.1f} MHz at every"


@claim("5.5.1-matched-throughput", PAPER, "5.5.1")
def matchedThroughput():
    d = _matched("throughput")
    return f"| throughput, OC against SILENT | **{mean(d):.2f}%** | {min(d):.2f}% to {max(d):+.2f}% |"


@claim("5.5.1-matched-power", PAPER, "5.5.1")
def matchedPower():
    """The headline of the subsection.

    RAISES if the two ever stop being separable, because the prose calls this the clearest
    evidence in the paper that shipped voltage is not required voltage.
    """
    d = _matched("power")
    if min(d) <= 0:
        raise ValueError(f"the OC BIOS no longer draws more power at every matched point: {d}")
    return f"| power, OC against SILENT | **+{mean(d):.2f}%** | +{min(d):.2f}% to +{max(d):.2f}% |"


@claim("5.5.1-thermal-runs-backwards", PAPER, "5.5.1")
def thermalRunsBackwards():
    """The temperature check that rules out the obvious alternative explanation.

    Asserts the DIRECTION as well as rendering the numbers: if the silent run ever stops being the
    hotter one, the argument in the surrounding paragraph is gone and a number would not say so.
    """
    import csv
    import io

    from audit_claims import REPO_ROOT

    def temps(relative):
        path = REPO_ROOT / "data" / "frequency-sweeps" / relative
        with open(path, encoding="utf-8-sig") as handle:
            return {int(float(r["target_frequency_mhz"])): float(r["temperature_avg_c"])
                    for r in csv.DictReader(handle)}

    silent, oc = temps(SILENT_GEMM), temps(OC_GEMM_MATCHED)
    hotter = [t for t in _matchedTargets() if silent[t] > oc[t]]
    if len(hotter) < 4:
        raise ValueError(f"the silent run is no longer the hotter one - only {len(hotter)} of "
                         f"{len(_matchedTargets())} points. The paragraph's argument depends on it.")
    return (f"at five of the seven points, {min(silent[t] for t in hotter):.1f}-"
            f"{max(silent[t] for t in hotter):.1f} C against {min(oc[t] for t in hotter):.1f}-"
            f"{max(oc[t] for t in hotter):.1f} C")


@claim("5.5.1-peak-gemm", PAPER, "5.5.1")
def peakGemmRow():
    s, o = _peak(SILENT_GEMM), _peak(OC_GEMM)
    return (f"| peak `gemm` | {s['throughput'] / 1e12:.2f} TFLOP/s at {s['power']:.1f} W | "
            f"{o['throughput'] / 1e12:.2f} TFLOP/s at {o['power']:.1f} W | "
            f"**+{100 * (o['throughput'] / s['throughput'] - 1):.2f}%** |")


@claim("5.5.1-peak-membw", PAPER, "5.5.1")
def peakMembwRow():
    s = _peak(SILENT_MEMBW)
    o = max((_peak(p) for p in OC_MEMBW_RUNS), key=lambda row: row["throughput"])
    return (f"| peak `membw` | {s['throughput'] / 1e9:.1f} GB/s | {o['throughput'] / 1e9:.1f} GB/s "
            f"| **+{100 * (o['throughput'] / s['throughput'] - 1):.2f}%** |")


@claim("5.5.1-membw-power", PAPER, "5.5.1")
def membwPowerRow():
    """Band means, and the OC side averages both of its sweeps rather than picking one."""
    def band(path):
        return mean(row["power"] for row in sweep(path).values())

    s = band(SILENT_MEMBW)
    o = mean(band(p) for p in OC_MEMBW_RUNS)
    return (f"| band-mean `membw` power | {s:.1f} W | {o:.1f} W | "
            f"**+{100 * (o / s - 1):.1f}%** |")


@claim("5.5.1-efficiency", PAPER, "5.5.1")
def efficiencyRow():
    s, o = _optimum(SILENT_GEMM), _optimum(OC_GEMM)
    se = s["throughput"] / s["power"] / 1e9
    oe = o["throughput"] / o["power"] / 1e9
    return (f"| best `gemm` efficiency | {se:.2f} GFLOP/J at {s['target']} MHz | "
            f"{oe:.2f} GFLOP/J at {o['target']} MHz | **{100 * (oe / se - 1):.2f}%** |")


# --------------------------------------------------------------------------------------
# 5.5.2 - reproducibility on this card
# --------------------------------------------------------------------------------------

@claim("5.5.2-replicates", PAPER, "5.5.2")
def membwReplicates():
    """Two sweeps of one configuration, and the reason 5.7.6's resolution floor may not transfer."""
    first, second = (sweep(p) for p in OC_MEMBW_RUNS)
    shared = sorted(set(first) & set(second))
    d = [(second[t]["throughput"] / first[t]["throughput"] - 1) * 100 for t in shared]
    if len(shared) != 13:
        raise ValueError(f"the two OC membw sweeps now share {len(shared)} targets, not thirteen")
    return (f"agree to **+{mean(d):.2f}%** on average across all thirteen\nshared targets, from "
            f"+{min(d):.2f}% to +{max(d):.2f}%")


# --------------------------------------------------------------------------------------
# 5.5.3 - the voltage session: what the OC BIOS actually spends its extra power on
# --------------------------------------------------------------------------------------

HW = ROOT + "hwinfo-oc/"
OC_GEMM_FINE = HW + "20260825-160418_rtx3070ti-oc-gemm-fine_sweep.csv"

# Session B, 2026-08-27: the SILENT position with voltage telemetry. Two gemm matched runs were
# collected; this is the SECOND, and it is the one with usable voltage data - the first ran while
# HWiNFO was not logging. See hwinfo-silent/README.md for how that was established.
HWS = ROOT + "hwinfo-silent/"
SILENT_README = "data/frequency-sweeps/rtx3070ti-20260825/hwinfo-silent/README.md"
SILENT_GEMM_V = HWS + "20260827-170331_rtx3070ti-silent-gemm-matched2130-hwinfo_sweep.csv"
OC_GEMM_V = HW + "20260825-154606_rtx3070ti-oc-gemm-matched2130-hwinfo_sweep.csv"
OC_MEMBW_V = HW + "20260825-155312_rtx3070ti-oc-membw-matched2130-hwinfo_sweep.csv"
VOLTS = lambda path: path.replace("_sweep.csv", "_sweep_voltage.csv")

# 256-bit GDDR6X at 19 Gbps. A published specification, not a measurement, and named as a constant
# so a claim reading it cannot be mistaken for one that measured it.
BUS_GBS_3070TI = 19.0 * 256 / 8


@claim("5.5.3-voltage-floor", PAPER, "5.5.3")
def voltageFloor():
    """The floor is flat to the resolution HWiNFO reports, not merely low.

    RAISES if it ever stops being flat, because the sentence around it says the OC BIOS holds one
    voltage across the band. A spread of even a millivolt would need different prose.
    """
    rows = voltageJoin(VOLTS(OC_GEMM_FINE))
    volts = sorted(r["voltage"] for r in rows.values())
    if volts[0] != volts[-1]:
        raise ValueError(f"the fine-sweep floor is no longer flat: {volts[0]:.3f}-{volts[-1]:.3f} V")
    clocks = sorted(r["mhz"] for r in rows.values())
    return (f"**{volts[0]:.3f} V** at all {len(rows)} points from {clocks[0]:.0f} to "
            f"{clocks[-1]:.0f} MHz")


@claim("5.5.3-voltage-floor-power", PAPER, "5.5.3")
def voltageFloorPower():
    rows = sweep(OC_GEMM_FINE)
    power = sorted(r["power"] for r in rows.values())
    return f"power rises {power[0]:.1f} to {power[-1]:.1f} W ({100 * (power[-1] / power[0] - 1):+.1f}%)"


@claim("5.5.3-crossbar-floor", PAPER, "5.5.3")
def crossbarFloor():
    """The crossbar has a floor of its own, and the RATIO is the quantity 5.7.4 cares about."""
    rows = voltageJoin(VOLTS(OC_GEMM_V))
    ratios = [r["crossbar"] / r["mhz"] for r in rows.values()]
    floor = min(r["crossbar"] for r in rows.values())
    pinned = [t for t, r in rows.items() if r["crossbar"] == floor]
    return (f"pinned at **{floor:.0f} MHz** across {len(pinned)} of {len(rows)} targets, so the "
            f"crossbar-to-core ratio\nfalls from {max(ratios):.3f} to {min(ratios):.3f}")


@claim("5.5.3-membw-flat", PAPER, "5.5.3")
def membwFlat():
    """The load-bearing claim: core clock does nothing for bandwidth on this chip.

    RAISES if the band ever spreads past 1%, because the sentence says the workload is
    memory-bound at every core frequency tested and would no longer be supported.
    """
    rows = voltageJoin(VOLTS(OC_MEMBW_V))
    tp = sweep(OC_MEMBW_V)
    values = [tp[t]["throughput"] / 1e9 for t in sorted(tp)]
    clocks = [rows[t]["mhz"] for t in sorted(rows)]
    span = 100 * (max(values) - min(values)) / mean(values)
    if span > 1.0:
        raise ValueError(f"membw now spans {span:.2f}% across the band; it is no longer flat")
    return (f"span **{max(values) - min(values):.1f} GB/s ({span:.2f}%)** while core clock rises "
            f"{clocks[0]:.0f} to {clocks[-1]:.0f} MHz\n({100 * (clocks[-1] / clocks[0] - 1):+.1f}%)")


@claim("5.5.3-membw-cost", PAPER, "5.5.3")
def membwCost():
    tp, volts = sweep(OC_MEMBW_V), voltageJoin(VOLTS(OC_MEMBW_V))
    targets = sorted(tp)
    lo, hi = tp[targets[0]], tp[targets[-1]]
    return (f"**{100 * (hi['power'] / lo['power'] - 1):+.1f}% power** for "
            f"**{100 * (hi['throughput'] / lo['throughput'] - 1):+.2f}% bandwidth**, with core "
            f"voltage rising\n{volts[targets[0]]['voltage']:.3f} to "
            f"{volts[targets[-1]]['voltage']:.3f} V")


@claim("5.5.3-membw-saturated", PAPER, "5.5.3")
def membwSaturated():
    """Why the flatness is a control for 5.7.3 rather than an oddity of this card."""
    peak = max(r["throughput"] for r in sweep(OC_MEMBW_V).values()) / 1e9
    return f"**{100 * peak / BUS_GBS_3070TI:.1f}%** of its {BUS_GBS_3070TI:.0f} GB/s bus"


@claim("5.5.3-gemm-ceiling", PAPER, "5.5.3")
def gemmCeiling():
    rows = sweep(OC_GEMM_V)
    held = {t: r for t, r in rows.items() if abs(r["mhz"] - t) < 5}
    missed = {t: r for t, r in rows.items() if abs(r["mhz"] - t) >= 5}
    clocks = sorted(r["mhz"] for r in missed.values())
    return (f"the top {len(missed)} targets, {min(missed)} to {max(missed)} MHz, all collapse to "
            f"{clocks[0]:.0f}-{clocks[-1]:.0f} MHz,\nwhile the {len(held)} below them hold their "
            f"lock exactly")


@claim("5.5.3-gemm-powercap", PAPER, "5.5.3")
def gemmPowerCap():
    """The mask decides between silicon ceiling and board limit, so it is read, not inferred.

    RAISES if SwPowerCap ever appears at a target that held its lock: the section's whole argument
    is that the cap and the collapse coincide exactly, and a single counterexample breaks it.
    """
    reasons = throttleReasons(OC_GEMM_V)
    rows = sweep(OC_GEMM_V)
    capped = sorted(t for t, names in reasons.items() if "SwPowerCap" in names)
    missed = sorted(t for t, r in rows.items() if abs(r["mhz"] - t) >= 5)
    if capped != missed:
        raise ValueError(f"SwPowerCap no longer coincides with the collapse: capped {capped}, "
                         f"collapsed {missed}")
    thermal = {n for names in reasons.values() for n in names if "Thermal" in n or "HwSlowdown" in n}
    if thermal:
        raise ValueError(f"a thermal or hardware slowdown appears in this run: {sorted(thermal)}")
    peak = max(r["power"] for r in rows.values())
    return (f"**SwPowerCap** at exactly those {len(capped)} targets and at none of the "
            f"{len(rows) - len(capped)} below,\nwith power peaking at {peak:.1f} W")


# --------------------------------------------------------------------------------------
# 2.6 - the same measurement, quoted in the related-work section
# --------------------------------------------------------------------------------------

@claim("2.6-vendor-cost", PAPER, "2.6")
def vendorCost():
    """Rendered from the same data as 5.5.1 rather than copied from it.

    A figure quoted in two sections is a figure that can disagree with itself, which is how 5.7.1's
    "+12.3% sustainable ceiling" survived being measured against the wrong denominator.
    """
    power = mean(_matched("power"))
    s, o = _peak(SILENT_GEMM), _peak(OC_GEMM)
    gain = 100 * (o["throughput"] / s["throughput"] - 1)
    return (f"for **{power:.2f}%** more power, and returned\n**{gain:.2f}%** of peak compute and "
            f"nothing measurable on bandwidth")


# --------------------------------------------------------------------------------------
# Session B - the refutation, and what replaced the refuted model
# --------------------------------------------------------------------------------------
# 5.5.3 predicted a SILENT voltage floor of 0.738 V on the assumption that the whole matched-
# frequency power gap was core dynamic power. It is not: the gap is a roughly constant offset that
# does not scale with core clock, so there was no core-voltage ratio inside it to recover.
#
# These claims are pinned against the session README rather than the paper because the paper still
# carries the refuted account. When 5.5.1 is rewritten they move.


def _hwinfoMatchedTargets():
    """Grid points shared by the two HWiNFO-paired matched sweeps, computed rather than assumed."""
    return sorted(set(sweep(SILENT_GEMM_V)) & set(sweep(OC_GEMM_V)))


def _looPredictionErrors():
    """Leave-one-out mean absolute error of two models for OC power given SILENT power.

    Multiplicative: OC = SILENT x r, r fitted on the other points. This is what 5.5.1 assumed when
    it read a voltage ratio out of a power ratio.
    Additive: OC = SILENT + d, d fitted the same way.

    Leave-one-out rather than in-sample because both models have one free parameter and an
    in-sample comparison of two one-parameter fits on seven points would mostly measure which
    functional form can absorb the spread, not which one predicts.
    """
    targets = _hwinfoMatchedTargets()
    silent, oc = sweep(SILENT_GEMM_V), sweep(OC_GEMM_V)
    ratioErrors, offsetErrors = [], []
    for held in targets:
        rest = [t for t in targets if t != held]
        ratio = mean(oc[t]["power"] / silent[t]["power"] for t in rest)
        offset = mean(oc[t]["power"] - silent[t]["power"] for t in rest)
        ratioErrors.append(abs(oc[held]["power"] - silent[held]["power"] * ratio))
        offsetErrors.append(abs(oc[held]["power"] - (silent[held]["power"] + offset)))
    return mean(ratioErrors), mean(offsetErrors)


@claim("5.5.1-additive-beats-ratio", SILENT_README)
def additiveBeatsRatio():
    """The number that makes "the model improved" a measurement rather than an impression.

    RAISES if the ratio model ever predicts as well or better, because the surrounding text is an
    argument that the functional form was wrong. A number alone would not report that collapse.
    """
    ratioError, offsetError = _looPredictionErrors()
    if offsetError >= ratioError:
        raise ValueError(
            f"the additive model no longer predicts better: {offsetError:.2f} W against "
            f"{ratioError:.2f} W for the ratio model"
        )
    reduction = 100 * (1 - offsetError / ratioError)
    return (f"**{offsetError:.2f} W** against **{ratioError:.2f} W** for the ratio model, a "
            f"**{reduction:.0f}%** reduction")


@claim("5.5.1-gap-is-an-offset", SILENT_README)
def gapIsAnOffset():
    """The offset description is tighter than the percentage one - stated as both spreads.

    This is the claim that actually carries the finding: 5.5.1 reported the gap as a percentage,
    and a percentage with a 19% relative spread reads as noise around a constant rather than as
    the wrong functional form.
    """
    # SAMPLE standard deviation, matching the "34.1 +/- 3.4 W" already written beside it in the
    # README. Population sd would give 9.2% and 17.6% instead of 9.9% and 17.6%-> the conclusion
    # is the same either way, but two spreads computed differently in one paragraph is how a
    # reader loses trust in both.
    from statistics import stdev

    targets = _hwinfoMatchedTargets()
    silent, oc = sweep(SILENT_GEMM_V), sweep(OC_GEMM_V)
    offsets = [oc[t]["power"] - silent[t]["power"] for t in targets]
    percents = [100 * (oc[t]["power"] / silent[t]["power"] - 1) for t in targets]
    offsetSpread = 100 * stdev(offsets) / mean(offsets)
    percentSpread = 100 * stdev(percents) / mean(percents)
    if offsetSpread >= percentSpread:
        raise ValueError(
            f"the offset description is no longer the tighter one: {offsetSpread:.1f}% against "
            f"{percentSpread:.1f}%"
        )
    return (f"**{mean(offsets):.1f} W**, relative spread **{offsetSpread:.1f}%**, against "
            f"**{mean(percents):.1f}%** at **{percentSpread:.1f}%**")


# The two claims above pin the finding in hwinfo-silent/README.md, where it was written the day it
# was measured. As of 2026-08-28 the paper carries it too, in 5.5.1.1, so it needs pinning in BOTH
# documents - a claim asserts its string appears once in ONE document, so the paper's copy was
# unprotected until these existed. The render functions are reused rather than reimplemented: two
# formulas for one number is how the two documents would drift apart while both looked audited.

@claim("5.5.1-paper-gap-is-an-offset", PAPER, "5.5.1.1")
def paperGapIsAnOffset():
    return gapIsAnOffset()


@claim("5.5.1-paper-additive-beats-ratio", PAPER, "5.5.1.1")
def paperAdditiveBeatsRatio():
    return additiveBeatsRatio()


# ---------------------------------------------------------------------------------------------
# The fan candidate, refuted 2026-08-29 from data collected on 2026-08-25 and 2026-08-27. Fan RPM
# was in the raw HWiNFO logs all along and was dropped during distillation, so the measurement
# needed no further access to the card. Extracts committed beside the voltage ones.

FAN_SILENT = HWS + "fan-silent-gemm-matched.csv"
FAN_OC = HW + "fan-oc-gemm-matched.csv"


def _fanRows(relativePath):
    """Loaded samples from a distilled fan extract, binned into 15 MHz clock bins.

    15 MHz because that is the card's own clock step; finer bins split one operating point across
    two keys and coarser ones merge neighbouring sweep targets.
    """
    import csv
    from audit_claims import REPO_ROOT
    binned = {}
    path = REPO_ROOT / "data" / "frequency-sweeps" / relativePath
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = round(float(row["clock_mhz"]) / 15) * 15
            binned.setdefault(key, []).append({
                "power": float(row["power_w"]),
                "fan": (float(row["fan1_rpm"]) + float(row["fan2_rpm"])) / 2.0,
            })
    return {k: v for k, v in binned.items() if len(v) >= 5}


@claim("5.5.1-fans-stopped-gap-remains", SILENT_README)
def fansStoppedGapRemains():
    """RAISES if the fans were not actually stopped at those two points.

    The whole refutation rests on the fans reading zero on BOTH sides while the offset persists.
    If a future re-extraction shows them spinning, the sentence around this number is wrong and
    must fail rather than render a new pair of watts.
    """
    silent, oc = _fanRows(FAN_SILENT), _fanRows(FAN_OC)
    quiet = sorted(k for k in set(silent) & set(oc)
                   if all(r["fan"] == 0 for r in silent[k]) and all(r["fan"] == 0 for r in oc[k]))
    if len(quiet) < 2:
        raise ValueError(f"expected at least two bins with both fans stopped, found {quiet}")
    gaps = [mean(r["power"] for r in oc[k]) - mean(r["power"] for r in silent[k]) for k in quiet[:2]]
    return (f"+{gaps[0]:.1f} W** and **+{gaps[1]:.1f} W")


@claim("5.5.1-fan-binned-offset", SILENT_README)
def fanBinnedOffset():
    """The offset re-derived from HWiNFO board power rather than from the sweep CSVs.

    Independent corroboration of 34.1 W by a different instrument, which is worth more than the
    third decimal place of either.
    """
    silent, oc = _fanRows(FAN_SILENT), _fanRows(FAN_OC)
    shared = sorted(set(silent) & set(oc))
    gaps = [mean(r["power"] for r in oc[k]) - mean(r["power"] for r in silent[k]) for k in shared]
    return f"**+{mean(gaps):.1f} W**, against the **34.1 W**"


# ---------------------------------------------------------------------------------------------
# Session C, 2026-08-29: the SILENT membw matched-2130 sweep Session B planned and never
# collected. It breaks the "roughly constant 34 W" description - the offset is 67% larger on the
# bandwidth-bound workload, on the same band and the same points.

# NOT SILENT_MEMBW - that name is taken at the top of this file by Session A's as-found run.
# Reusing it redefined the module-level constant and silently redirected 5.5.1-peak-membw and
# 5.5.1-membw-power to this file instead, which is the shared-constant failure this module's
# docstring exists to warn about. The audit caught it; the suffix keeps it caught.
SILENT_MEMBW_C = (ROOT + "hwinfo-silent-membw-20260829/"
                "20260829-145431_rtx3070ti-silent-membw-matched2130-membw_sweep.csv")

@claim("5.5.1.2-membw-trade", PAPER, "5.5.1.2")
def membwTrade():
    """What the OC position costs on the bandwidth-bound workload, across its whole band."""
    silent, oc = sweep(SILENT_MEMBW_C), sweep(OC_MEMBW_V)
    shared = sorted(set(silent) & set(oc))
    power = mean(oc[t]["power"] - silent[t]["power"] for t in shared)
    throughput = mean(100 * (oc[t]["throughput"] / silent[t]["throughput"] - 1) for t in shared)
    return f"**+{power:.1f} W** for **+{throughput:.2f}%**"


@claim("5.5.1.2-offset-scales-with-traffic", PAPER, "5.5.1.2")
def offsetScalesWithTraffic():
    """RAISES if the membw offset stops exceeding the gemm one on the shared band.

    The sentence around this is that a constant board-level draw cannot produce a
    workload-dependent offset. If the two ever come out equal, that argument is gone and the
    paragraph needs rewriting rather than the number updating.
    """
    band = lambda a, b: [t for t in sorted(set(a) & set(b)) if 855 <= t <= 1485]
    silentM, ocM = sweep(SILENT_MEMBW_C), sweep(OC_MEMBW_V)
    silentG, ocG = sweep(SILENT_GEMM_V), sweep(OC_GEMM_V)
    membwOffset = mean(ocM[t]["power"] - silentM[t]["power"] for t in band(silentM, ocM))
    gemmOffset = mean(ocG[t]["power"] - silentG[t]["power"] for t in band(silentG, ocG))
    if membwOffset <= gemmOffset:
        raise ValueError(
            f"the membw offset ({membwOffset:.1f} W) no longer exceeds the gemm one "
            f"({gemmOffset:.1f} W) - 5.5.1.2's argument does not hold")
    return f"**+{gemmOffset:.1f} W** |\n| `membw` | ~545 GB/s | **+{membwOffset:.1f} W**"


@claim("5.5.5-power-gap-is-large", PAPER, "5.5.5")
def powerGapIsLarge():
    """A wrong zero-decimal power gap would silently pass a two-decimal 5.5.1 match."""
    # 5.5.1 pins the gap at two decimals; this zero-decimal rendering is the only one that matches 5.5.5.
    return f"The +{mean(_matched('power')):.0f}% matched-frequency power gap"


@claim("5.5.5-peak-difference-is-not", PAPER, "5.5.5")
def peakDifferenceIsNot():
    """A non-positive OC peak would make the 'not' prose false; fail loudly instead of rendering a negative."""
    ocPeak = _peak(OC_GEMM)
    silentPeak = _peak(SILENT_GEMM)
    diff = (ocPeak["throughput"] - silentPeak["throughput"]) / silentPeak["throughput"] * 100.0
    if diff <= 0:
        raise ValueError("OC peak throughput is not ahead of silent peak throughput")
    # The same figure appears in the abstract, 2.6, 5.5.1's table, and 5.7.6; only this exact wording is unique to 5.5.5.
    return f"the +{diff:.2f}% peak difference is not"


@claim("5.5.5-matched-coverage", PAPER, "5.5.5")
def matchedCoverage():
    """Wrong English count words (seven/thirteen) would pass a digit-only match; fail loudly on mismatch."""
    targets = _matchedTargets()
    lo = int(targets[0])
    hi = int(targets[-1])
    matchedCount = len(targets)
    totalCount = len(sweep(SILENT_GEMM))
    matchedWord = "seven" if matchedCount == 7 else str(matchedCount)
    totalWord = "thirteen" if totalCount == 13 else str(totalCount)
    # The band endpoints also appear in 5.5.3; the 'covers ... grid points' wording is unique to 5.5.5.
    return f"covers {matchedWord} of {totalWord} grid points, {lo}-{hi} MHz"


@claim("5.5.5-collection-counts", PAPER, "5.5.5")
def biosCollectionCounts():
    """Count the Session A inputs, not later fine sweeps of the same BIOS.

    The named paths define the study selection; loading them checks that every
    counted sweep exists and has usable data. They are not independent chips.
    """
    groups = ((SILENT_GEMM,), (OC_GEMM,), (SILENT_MEMBW,), tuple(OC_MEMBW_RUNS))
    counts = []
    for group in groups:
        counts.append(sum(bool(sweep(path)) for path in group))
    word = lambda n: {1: "one", 2: "two"}.get(n, str(n))
    if counts[0] != counts[1]:
        raise ValueError(f"the compute conditions have different sweep counts: {counts[:2]}")
    return (f"The BIOS comparison is {word(counts[0])} sweep per position on the compute workload "
            f"and {word(counts[2])} against {word(counts[3])} on the bandwidth workload")


@claim("5.5.5-original-grids-disjoint", PAPER, "5.5.5")
def biosOriginalGridsDisjoint():
    common = sorted(set(sweep(SILENT_GEMM)) & set(sweep(OC_GEMM)))
    if common:
        raise ValueError(f"the original BIOS sweeps now share targets: {common}")
    # 'two' refers to the two named BIOS conditions, not two physical units.
    count = len((SILENT_GEMM, OC_GEMM))
    word = "two" if count == 2 else str(count)
    return f"The {word} BIOSes build their sweep grids from their own maxima and therefore share no targets at all"
