"""Claims over the public V100 set - sections 5.1, 5.2, 5.3, 5.6, 5.6.1 and 5.6.2.

This module is separate from claims_consumer.py and claims_crosschip.py on purpose: those hold
claims over the consumer sweep CSVs this project collected, whereas these sections are about the
public V100 dataset (33 workloads by 13 frequencies) published by others and never pooled with the
consumer data. A shared constant is how a claim silently reads the wrong hardware, so each dataset
keeps its own module.

WHAT IS PINNED HERE, AND WHAT IS NOT
    5.1        the headroom gap, in full.
    5.2        the two numbers in its prose that come from the workload summary. NOT its regret
               table - those come from a leave-one-out Ridge fit and are 5.6.2's business.
    5.3        the probe-count table: selected frequencies, curve MAE, measurement reduction.
    5.6/5.6.1  the 95% floor rows. These are ORACLE numbers - measurements of an upper bound with
               the whole curve in hand, computed by analyze_constrained.py.
    5.6.2      the leave-one-workload-out strategy comparison, which is a PREDICTION and comes
               from analysis/models/. Both halves are pinned deliberately: the one saying probing
               wins, and the one saying the fitting is not what wins. A future edit that quietly
               dropped the second half would leave the first reading as a model success.

    Sections 5.4, 5.5 and 5.7 are consumer measurements and belong to the other two modules.

COST
    Importing this module runs the constrained leave-one-out fit and the greedy probe selection,
    which together add a couple of seconds to the audit. That is the price of pinning results that
    are computed rather than read, and it is paid once per run rather than once per claim.

WHY THIS MODULE CAN REGISTER NOTHING
    Every claim here needs data/raw/, which is gitignored and fetched by scripts/Get-Dataset.ps1.
    An unguarded load raises FileNotFoundError at import and takes the WHOLE audit down with it -
    every claim, not just these - because the audit imports its claims modules eagerly. So a
    missing dataset registers nothing and says so, matching what
    models/test_predict_constrained_frequency.py already does for the same data.

    THE SKIP IS NOT A PASS. A green audit on a machine that never fetched the dataset has not
    checked any of these sections. The CI job named "V100 reference claims" exists to be the
    machine that does fetch it; the other job is the one that skips.
"""

import contextlib
import io
import sys

from audit_claims import claim, REPO_ROOT
from load_data import loadDataset, REFERENCE_FREQUENCY_MHZ
from characterize import buildWorkloadSummary

# analysis/models is not on the path just because analysis/ is. The model files each add it for
# themselves when run as scripts; this module is imported, so it has to do the same.
sys.path.insert(0, str(REPO_ROOT / "analysis" / "models"))

PAPER = "docs/PAPER_DRAFT.md"

FLOOR = 0.95


def _load():
    """Everything the claims below read, computed once. Returns None if the dataset is absent."""
    try:
        dataset = loadDataset(validate=False)
    except FileNotFoundError:
        return None

    import numpy as np

    import analyze_constrained as constrained
    import curve_model
    import predict_constrained_frequency as predictor

    curves = constrained.loadV100Curves()

    # reportFixedVersusPerWorkload prints its table as a side effect. The audit's output is a list
    # of claim verdicts and nothing else, so the print is swallowed rather than allowed to
    # interleave with them.
    with contextlib.redirect_stdout(io.StringIO()):
        floorRows, _ = constrained.analyseCurves(curves, [FLOOR])
        fixedRows = constrained.reportFixedVersusPerWorkload(curves, [FLOOR])

    probeFrequencies, probeCurves, _ = curve_model.loadUnitsFromPublicDataset()
    topIndex = int(np.argmax(probeFrequencies))
    probeTable = {}
    for count in (3, 4, 5):
        with contextlib.redirect_stdout(io.StringIO()):
            indices, error = curve_model.selectProbeFrequencies(
                probeFrequencies, probeCurves, count, alwaysInclude=[topIndex])
        probeTable[count] = {
            "mhz": sorted(int(probeFrequencies[i]) for i in indices),
            "mae": error,
            "reduction": round(100 * (len(probeFrequencies) - count) / len(probeFrequencies)),
        }

    performance = dataset.pivot(index="workload", columns="frequency_mhz",
                                values="performance_normalised")
    frequencies = np.array(sorted(performance.columns))
    with contextlib.redirect_stdout(io.StringIO()):
        looScores = predictor.runLeaveOneWorkloadOut(dataset, FLOOR)["scores"]
        bias = predictor.measureInterpolationBias(
            performance, frequencies, predictor.DEFAULT_PROBE_FREQUENCIES_MHZ)

    return {
        "summary": buildWorkloadSummary(dataset),
        "floorRow": floorRows[0],
        "fixedRow": fixedRows[0],
        "probes": probeTable,
        "scores": looScores,
        "bias": bias,
    }


DATA = _load()

if DATA is None:
    print("  [SKIP] claims_reference: the public V100 dataset is not downloaded - run "
          "scripts/Get-Dataset.ps1. The Abstract and sections 5.1, 5.2, 5.3, 5.3.1, 5.6, "
          "5.6.1 and 5.6.2 are NOT audited in this run.")
else:
    SUMMARY = DATA["summary"]

    # ------------------------------------------------------------ Abstract
    # The abstract restates figures the body already pins, in different words. Pinning it
    # separately is not redundant: the two are separate strings, and an edit to one does not
    # touch the other, so an unpinned abstract can drift away from a body that is still green.
    # It is also the part most likely to be read on its own.

    @claim("abstract-headroom-gap", PAPER, "Abstract")
    def abstractHeadroomGap():
        return f"recovers {SUMMARY['headroom_gap_pct'].mean():.1f}% efficiency on average"

    @claim("abstract-constrained-inversion", PAPER, "Abstract")
    def abstractConstrainedInversion():
        scores = DATA["scores"]
        return (f"probe-based selection reaches "
                f"{scores.loc['interpolation (no fit)', 'mean_gain_pct']:.1f}% mean efficiency "
                f"gain where the best fixed frequency reaches "
                f"{scores.loc['best fixed frequency', 'mean_gain_pct']:.1f}%")

    # ------------------------------------------------------------ Section 1
    # The introduction gained a motivation passage on 2026-08-29, arguing that perf-per-watt is
    # the throughput function wherever power is the binding constraint. It restates figures from
    # 5.1 and 5.6 to make that case, and a motivating number that drifts from the result it
    # motivates is worse than no number, so both are pinned here as well.

    @claim("1-unconstrained-cost", PAPER, "1")
    def introUnconstrainedCost():
        return f"a mean {SUMMARY['performance_given_up_pct'].mean():.1f}% of performance"

    @claim("1-constrained-trade", PAPER, "1")
    def introConstrainedTrade():
        row = DATA["floorRow"]
        return (f"{row['loss_mean']:.1f}%** on average for **{row['power_saved_mean']:.1f}%** "
                f"less power")

    # ---------------------------------------------------------------- 5.1

    @claim("5.1-workload-count", PAPER, "5.1")
    def workloadCount():
        return f"{len(SUMMARY)} workloads at stock ({REFERENCE_FREQUENCY_MHZ} MHz)"

    @claim("5.1-mean-gap", PAPER, "5.1")
    def meanGap():
        # The number alone is not an anchor: bold markers are normalised away on both sides, so
        # "44.4%" matches eight places in the paper. The surrounding words are what pin the line.
        return f"a mean of {SUMMARY['headroom_gap_pct'].mean():.1f}% efficiency"

    @claim("5.1-median-gap", PAPER, "5.1")
    def medianGap():
        return f"median {SUMMARY['headroom_gap_pct'].median():.1f}%"

    @claim("5.1-gap-range", PAPER, "5.1")
    def gapRange():
        # The paper uses an EN DASH between the two endpoints, not a hyphen.
        return (f"range {SUMMARY['headroom_gap_pct'].min():.1f}"
                f"–{SUMMARY['headroom_gap_pct'].max():.1f}%")

    @claim("5.1-performance-cost", PAPER, "5.1")
    def performanceCost():
        return f"costing a mean {SUMMARY['performance_given_up_pct'].mean():.1f}% performance"

    @claim("5.1-power-saved", PAPER, "5.1")
    def powerSaved():
        return f"saving a mean {SUMMARY['power_saved_pct'].mean():.1f}% power"

    # ---------------------------------------------------------------- 5.2

    @claim("5.2-modal-frequency", PAPER, "5.2")
    def modalFrequency():
        counts = SUMMARY["optimal_frequency_mhz"].value_counts()
        modalMhz = int(counts.idxmax())
        modalCount = int(counts.max())
        percent = round(100.0 * modalCount / len(SUMMARY))
        return f"{modalMhz} MHz is optimal for {modalCount} of {len(SUMMARY)} workloads ({percent}%)"

    @claim("5.2-sensitivity-correlation", PAPER, "5.2")
    def sensitivityCorrelation():
        correlation = SUMMARY["performance_at_lowest_frequency"].corr(
            SUMMARY["optimal_frequency_mhz"])
        # The paper writes the sign with U+2212 MINUS SIGN, not an ASCII hyphen.
        sign = "−" if correlation < 0 else ""
        # The bare figure appears twice - here and again in 5.4.1's discussion - so the anchor
        # carries the words that distinguish this occurrence from that one.
        return f"correlation {sign}{abs(correlation):.3f} between performance retained"

    # ---------------------------------------------------------------- 5.3

    def _probeRow(count):
        row = DATA["probes"][count]
        return (f"| {count} | {', '.join(str(m) for m in row['mhz'])} | "
                f"{row['mae']:.4f} | {row['reduction']}% |")

    @claim("5.3-three-probes", PAPER, "5.3")
    def threeProbes():
        return _probeRow(3)

    @claim("5.3-four-probes", PAPER, "5.3")
    def fourProbes():
        return _probeRow(4)

    @claim("5.3-five-probes", PAPER, "5.3")
    def fiveProbes():
        # The paper writes this row's frequencies as "+ 952" rather than listing them again, so
        # only the two computed columns are pinned.
        row = DATA["probes"][5]
        return f"{row['mae']:.4f} | {row['reduction']}%"

    # ---------------------------------------------------------------- 5.6

    @claim("5.6-floor-row", PAPER, "5.6")
    def floorRow():
        row = DATA["floorRow"]
        return (f"| {row['floor']:.0%} | {row['moved']}/{row['n']} | "
                f"**{row['gain_mean']:.1f}% / {row['gain_median']:.1f}%** | "
                f"{row['loss_mean']:.1f}% / {row['loss_max']:.1f}% | "
                f"{row['power_saved_mean']:.1f}% | {row['freq_median']:.0f} MHz |")

    # ---------------------------------------------------------------- 5.6.1

    @claim("5.6.1-fixed-versus-per-workload", PAPER, "5.6.1")
    def fixedVersusPerWorkload():
        row = DATA["fixedRow"]
        return (f"| {row['floor']:.0%} | {row['per_workload_pct']:.1f}% | "
                f"**{row['fixed_pct']:.1f}%** | {row['fixed_mhz']:.0f} MHz | "
                f"**{row['gap_pp']:.1f} pp** | **{row['share_pct']:.0f}%** |")

    # ---------------------------------------------------------------- 5.6.2

    def _score(strategy, column):
        return DATA["scores"].loc[strategy, column]

    @claim("5.6.2-interpolation-row", PAPER, "5.6.2")
    def interpolationRow():
        return (f"| **interpolation between the four probes, no fit** | "
                f"**{_score('interpolation (no fit)', 'mean_gain_pct'):.1f}%** | "
                f"**{_score('interpolation (no fit)', 'floor_violations'):.0f}** | "
                f"{100 * _score('interpolation (no fit)', 'exact_match_rate'):.1f}% |")

    @claim("5.6.2-probing-beats-fixed", PAPER, "5.6.2")
    def probingBeatsFixed():
        return (f"{_score('interpolation (no fit)', 'mean_gain_pct'):.1f}% against the fixed "
                f"policy's {_score('best fixed frequency', 'mean_gain_pct'):.1f}%")

    @claim("5.6.2-share-of-gap", PAPER, "5.6.2")
    def shareOfGap():
        interpolation = _score("interpolation (no fit)", "mean_gain_pct")
        fixed = _score("best fixed frequency", "mean_gain_pct")
        oracle = _score("oracle (upper bound)", "mean_gain_pct")
        return f"{100 * (interpolation - fixed) / (oracle - fixed):.0f}% of the gap"

    @claim("5.6.2-ridge-breaks-the-floor", PAPER, "5.6.2")
    def ridgeBreaksTheFloor():
        """RAISES if Ridge ever stops violating the floor.

        The sentence around this number says Ridge only appears to win by breaking the floor. If
        it ever keeps the floor, that sentence is wrong regardless of what the number renders to,
        and the paper needs rewriting rather than the claim updating.
        """
        violations = _score("probe model (ridge)", "floor_violations")
        if violations <= 0:
            raise ValueError("Ridge no longer breaks the floor - 5.6.2's argument does not hold")
        return (f"violating the floor on {violations:.0f} of {len(SUMMARY)} workloads, worst by "
                f"{_score('probe model (ridge)', 'worst_violation_pp'):.2f} points")

    @claim("5.6.2-calibrated-loses-to-interpolation", PAPER, "5.6.2")
    def calibratedLosesToInterpolation():
        """RAISES if the calibrated fit ever beats plain interpolation.

        This is the half of 5.6.2 that says the FITTING earns nothing. A fitted variant that
        overtakes interpolation would invert the section's conclusion, so it must fail loudly
        rather than quietly render a new pair of numbers.
        """
        calibrated = _score("probe model (calibrated)", "mean_gain_pct")
        interpolation = _score("interpolation (no fit)", "mean_gain_pct")
        if calibrated >= interpolation:
            raise ValueError(
                f"the calibrated fit now beats interpolation, {calibrated:.1f}% against "
                f"{interpolation:.1f}% - 5.6.2 says the opposite")
        return f"{calibrated:.1f}% - below the {interpolation:.1f}%"

    @claim("5.6.2-concavity", PAPER, "5.6.2")
    def concavity():
        return f"{100 * DATA['bias']['concave_share']:.1f}% of second differences curve downward"

    @claim("5.6.2-underestimate", PAPER, "5.6.2")
    def underestimate():
        # mean_error_pp is already expressed in percentage points by the diagnostic, so it is NOT
        # scaled again here. The share beside it is a fraction and is.
        return (f"under-estimate {100 * DATA['bias']['under_estimate_share']:.0f}% of the time, "
                f"by a mean of {abs(DATA['bias']['mean_error_pp']):.2f} points")


    # --------------------------------------------------------------------------------------
    # 5.3.1 - probe selection, 2026-09-11
    #
    # Fixed probe sets, not a re-run of the selection search. select_probes.py does the searching and
    # reports which frequencies win; these claims pin what those frequencies ACHIEVE, which is 33 Ridge
    # fits per set and cheap enough to run inside the auditor.
    # --------------------------------------------------------------------------------------

    _PROBE_SETS_MHZ = {
        1: (757,),
        2: (757, 825),
        3: (757, 825, 885),
        4: (757, 825, 885, 952),
        5: (757, 825, 885, 952, 1012),
    }


    def _probeContext():
        """(frequencies, curves, index-by-MHz) for the public V100 matrix."""
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent / "models"))
        from curve_model import loadUnitsFromPublicDataset  # noqa: E402
        frequencies, curves, _ = loadUnitsFromPublicDataset()
        return frequencies, curves, {int(f): i for i, f in enumerate(frequencies)}


    def _probeIndices(probeCount):
        _, _, byMhz = _probeContext()
        return [byMhz[m] for m in _PROBE_SETS_MHZ[probeCount]]


    def _probeScores(probeIndices):
        """(mean curve MAE, mean regret, modal picked frequency, how many folds picked it)."""
        import numpy as np
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent / "models"))
        from select_probes import scoreProbeSet  # noqa: E402
        frequencies, curves, _ = _probeContext()
        scored = [scoreProbeSet(curves, probeIndices, held) for held in range(curves.shape[0])]
        picks = [row[2] for row in scored]
        modal = max(set(picks), key=picks.count)
        return (float(np.mean([row[0] for row in scored])),
                float(np.mean([row[1] for row in scored])),
                int(frequencies[modal]), picks.count(modal), len(picks))


    @claim("5.3.1-selected-vs-even-3", PAPER, "5.3.1")
    def probeSelectedVsEvenThree():
        """Three informative probes: chosen by search against spread evenly across the range."""
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent / "models"))
        from select_probes import evenlySpacedProbes, informativeIndices, reconstructionErrorForProbes
        _, curves, byMhz = _probeContext()
        chosen = reconstructionErrorForProbes(curves, _probeIndices(3))
        even = reconstructionErrorForProbes(curves, evenlySpacedProbes(informativeIndices(curves), 3))
        return f"| 3 | {chosen:.4f} | {even:.4f} | 757, 825, 885 |"


    @claim("5.3.1-regret-is-flat", PAPER, "5.3.1")
    def probeRegretIsFlat():
        """The whole point of the section: five probe counts, one regret, to four decimal places."""
        regrets = [_probeScores(_probeIndices(k))[1] for k in sorted(_PROBE_SETS_MHZ)]
        return "| **mean regret, %** | " + " | ".join(f"**{r:.3f}**" for r in regrets) + " |"


    @claim("5.3.1-argmax-unchanging", PAPER, "5.3.1")
    def probeArgmaxUnchanging():
        """The decision does not move because the reconstruction's peak does not move."""
        scores = [_probeScores(_probeIndices(k)) for k in sorted(_PROBE_SETS_MHZ)]
        assert len({s[2] for s in scores}) == 1, "probe counts disagree on the picked frequency"
        return f"**{scores[0][2]} MHz in {scores[0][3]} of {scores[0][4]} folds at every probe count**"


    @claim("5.3.1-dead-column", PAPER, "5.3.1")
    def probeDeadColumn():
        """Why selection favours the low end, and why the top probe carries no information."""
        _, curves, byMhz = _probeContext()
        return (f"from {curves[:, byMhz[757]].std():.3f} at 757 MHz to **exactly zero** at "
                f"{max(byMhz):.0f} MHz")


    def fleetRow(performanceGivenUp, powerSaved):
        # Rounding only at render so derived claims (trade, breakeven) use full-precision intermediates.
        perfRetained = 100 - performanceGivenUp
        powerPerUnit = 100 - powerSaved
        units = 100 / perfRetained
        fleetPower = units * powerPerUnit
        return perfRetained, powerPerUnit, units, fleetPower

    @claim("5.6.3-unconstrained-row", PAPER, "5.6.3")
    def unconstrainedRow():
        perfRetained, powerPerUnit, units, fleetPower = fleetRow(
            SUMMARY["performance_given_up_pct"].mean(),
            SUMMARY["power_saved_pct"].mean(),
        )
        return (
            f"| unconstrained optimum (5.1) | {perfRetained:.1f}% | "
            f"{powerPerUnit:.1f}% | {units:.3f} | {fleetPower:.1f}% |"
        )

    @claim("5.6.3-floor-row", PAPER, "5.6.3")
    def fleetFloorRow():
        perfRetained, powerPerUnit, units, fleetPower = fleetRow(
            DATA["floorRow"]["loss_mean"],
            DATA["floorRow"]["power_saved_mean"],
        )
        return (
            f"| 95% floor (5.6) | {perfRetained:.1f}% | "
            f"{powerPerUnit:.1f}% | {units:.3f} | {fleetPower:.1f}% |"
        )

    @claim("5.6.3-unconstrained-trade", PAPER, "5.6.3")
    def unconstrainedTrade():
        # The bare numbers recur in the "buying" sentence; the word "trades" is what makes this match exactly once.
        _, _, units, fleetPower = fleetRow(
            SUMMARY["performance_given_up_pct"].mean(),
            SUMMARY["power_saved_pct"].mean(),
        )
        extraUnits = units * 100 - 100
        fleetSaving = 100 - fleetPower
        return f"trades {extraUnits:.1f}% more units for {fleetSaving:.1f}% less fleet power"

    @claim("5.6.3-floor-trade", PAPER, "5.6.3")
    def floorTrade():
        # Ends at "less" with no "fleet power" suffix, which is what separates this match from the unconstrained trade.
        _, _, units, fleetPower = fleetRow(
            DATA["floorRow"]["loss_mean"],
            DATA["floorRow"]["power_saved_mean"],
        )
        extraUnits = units * 100 - 100
        fleetSaving = 100 - fleetPower
        return f"trades {extraUnits:.1f}% more units for {fleetSaving:.1f}% less"

    @claim("5.6.3-unconstrained-breakeven", PAPER, "5.6.3")
    def unconstrainedBreakeven():
        # Catches a paper that quotes a breakeven fraction or ratio that does not follow from the fleet math.
        _, _, units, fleetPower = fleetRow(
            SUMMARY["performance_given_up_pct"].mean(),
            SUMMARY["power_saved_pct"].mean(),
        )
        extraUnits = units * 100 - 100
        fleetSaving = 100 - fleetPower
        a = extraUnits / 100
        b = fleetSaving / 100
        pct = 100 * a / b
        return f"unconstrained {a:.3f} / {b:.3f} = lifetime energy must exceed {pct:.0f}% of unit price"

    @claim("5.6.3-floor-breakeven", PAPER, "5.6.3")
    def floorBreakeven():
        # Catches a paper that quotes a floor breakeven fraction or ratio that does not follow from the fleet math.
        _, _, units, fleetPower = fleetRow(
            DATA["floorRow"]["loss_mean"],
            DATA["floorRow"]["power_saved_mean"],
        )
        extraUnits = units * 100 - 100
        fleetSaving = 100 - fleetPower
        a = extraUnits / 100
        b = fleetSaving / 100
        pct = 100 * a / b
        return f"95% floor {a:.3f} / {b:.3f} = lifetime energy must exceed {pct:.0f}% of unit price"


    # Job 45: repeated fleet figures, identity baseline, and the English fractions.
    # Keep every new V100 claim inside this fetched-data guard. Assumed prices
    # and lifetime energy in the examples are not V100 measurements.

    @claim("5.6.3-stock-identity", PAPER, "5.6.3")
    def fleetStockIdentity():
        perf, power, units, fleet = fleetRow(0, 0)
        return f"| stock | {perf:.0f}% | {power:.0f}% | {units:.3f} | {fleet:.0f}% |"


    def _fleetComparison():
        unconstrained = fleetRow(SUMMARY["performance_given_up_pct"].mean(),
                                 SUMMARY["power_saved_pct"].mean())
        floor = fleetRow(DATA["floorRow"]["loss_mean"], DATA["floorRow"]["power_saved_mean"])
        return unconstrained, floor


    @claim("5.6.3-breakeven-ratio", PAPER, "5.6.3")
    def fleetBreakevenRatio():
        unconstrained, floor = _fleetComparison()
        ratios = [(row[2] - 1) / (1 - row[3] / 100) for row in (unconstrained, floor)]
        count = round(ratios[0] / ratios[1])
        word = "three" if count == 3 else str(count)
        return f"The constrained point is roughly {word} times easier to justify than the unconstrained one"


    def _fractionWords(value):
        """Nearest simple fraction with denominator at most five, for approximate prose.

        This is a declared rendering precision, not an empirical threshold or a
        mechanism for preserving the current words. 0.40 must render two-fifths,
        and cannot be relabelled two-thirds to match the paper.
        """
        from fractions import Fraction
        fraction = Fraction(float(value)).limit_denominator(5)
        numerators = {1: "one", 2: "two", 3: "three", 4: "four"}
        denominators = {2: "half", 3: "third", 4: "fourth", 5: "fifth"}
        if fraction.numerator not in numerators or fraction.denominator not in denominators:
            return f"{100 * value:.1f}%"
        suffix = "s" if fraction.numerator != 1 else ""
        return f"{numerators[fraction.numerator]}-{denominators[fraction.denominator]}{suffix}"


    @claim("5.6.3-headroom-capital-fractions", PAPER, "5.6.3")
    def fleetHeadroomCapitalFractions():
        unconstrained, floor = _fleetComparison()
        available = SUMMARY["headroom_gap_pct"].mean()
        retained = DATA["floorRow"]["gain_mean"]
        lostHeadroom = 1 - retained / available
        removedCapital = 1 - (floor[2] - 1) / (unconstrained[2] - 1)
        return (f"Giving up {_fractionWords(lostHeadroom)} of the headroom removes "
                f"{_fractionWords(removedCapital)} of the extra capital.")


    @claim("5.6.3-buying-restatement", PAPER, "5.6.3")
    def fleetBuyingRestatement():
        unconstrained, _ = _fleetComparison()
        return (f"buying {100 * (unconstrained[2] - 1):.1f}% more units to save "
                f"{100 - unconstrained[3]:.1f}% of the power loses money")


    @claim("5.6.3-headroom-restatement", PAPER, "5.6.3")
    def fleetHeadroomRestatement():
        return f"rather than 5.1's {SUMMARY['headroom_gap_pct'].mean():.1f}%"


    # Explicit illustrative INPUTS from 5.6.3, not stored expected results and
    # not prices verified from a market source. The claims below recompute only
    # energy/price and compare that result with the paper. Power, years, duty,
    # tariff and PUE cannot be validated by these amounts; see the findings.
    FLEET_ILLUSTRATIVE_CASES = (("consumer card, high duty", 450, 180, 850, 3),
                                ("datacenter accelerator", 30000, 700, 5200, 5))

    def _illustrativeEnergyPrice(case):
        name, price, watts, lifetimeEnergy, years = case
        return (f"| {name} | ${price:,} | {watts} W | ~${lifetimeEnergy:,} ({years} yr) "
                f"| {lifetimeEnergy / price:.2f} |")


    for _index, _case in enumerate(FLEET_ILLUSTRATIVE_CASES):
        claim(f"5.6.3-illustrative-energy-price-{_index + 1}", PAPER, "5.6.3")(
            lambda case=_case: _illustrativeEnergyPrice(case))
