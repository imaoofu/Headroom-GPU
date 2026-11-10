"""Job 45: claims must track changed evidence and reject invalid pairings.

All altered inputs live in memory or a temporary directory. No GPU APIs run,
and no repository measurement is rewritten. Known-answer strings here are test
expectations; production claims contain no stored measured outcomes.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import audit_claims as audit
import claims_consumer as consumer
import claims_crosschip as crosschip
import claims_reference as reference


def test_band_is_selected_by_target_but_ratios_use_achieved():
    rows = {
        1395: {"achieved": 1394.0, "crossbar": 900.0, "voltage": 0.72},
        1402: {"achieved": 1400.6, "crossbar": 1000.0, "voltage": 0.72},
        1867: {"achieved": 1800.0, "crossbar": 1020.0, "voltage": 0.72},
        1942: {"achieved": 1940.0, "crossbar": 1700.0, "voltage": 0.80},
    }
    with patch.object(consumer, "_voltageExtract", return_value=rows):
        rendered = consumer.crossbarTracksVoltageNotClock()
        assert "28.5% higher" in rendered and "crossbar 2.0%" in rendered, rendered
        rendered = consumer.stockRatioAcrossSameRange()
        assert "0.64 ratio" in rendered, rendered
    # A changed endpoint voltage invalidates the sentence, even if the clocks match.
    rows[1867]["voltage"] = 0.725
    with patch.object(consumer, "_voltageExtract", return_value=rows):
        try:
            consumer.crossbarTracksVoltageNotClock()
        except ValueError as error:
            assert "voltage is not held constant" in str(error)
        else:
            raise AssertionError("a voltage change must invalidate the fixed-voltage claim")


def test_equal_voltage_gap_uses_each_actual_crossbar():
    stock = {1477: {"voltage": 0.72, "crossbar": 1402.5},
             1560: {"voltage": 0.72, "crossbar": 1470.0}}
    tuned = {1477: {"voltage": 0.72, "crossbar": 1320.0},
             1560: {"voltage": 0.72, "crossbar": 1342.5}}
    mapping = {consumer.VOLT_STOCK: stock, consumer.VOLT_TUNED: tuned}
    with patch.object(consumer, "_voltageExtract", side_effect=mapping.__getitem__):
        before = consumer.regimeEqualVoltageCrossbarGaps()
        assert "82 and 128 MHz" in before, before
        tuned[1477]["crossbar"] = 1300.0
        assert "102 and 128 MHz" in consumer.regimeEqualVoltageCrossbarGaps()
        tuned[1560]["voltage"] = 0.725
        try:
            consumer.regimeEqualVoltageCrossbarGaps()
        except ValueError as error:
            assert "equal reported voltage" in str(error)
        else:
            raise AssertionError("unequal voltage must not render the equality sentence")


def test_rated_denominator_is_not_loaded_memory():
    with patch.object(consumer, "sweep", return_value={2932: {"throughput": 352.2e9}}):
        assert "79% of the rated peak" in consumer.regimeRatedBandwidth()
    with patch.object(consumer, "sweep", return_value={2932: {"throughput": 336e9}}):
        assert "75% of the rated peak" in consumer.regimeRatedBandwidth()


def test_documented_neighbours_must_be_adjacent_and_recover():
    first = {1665: {"throughput": 90}, 1725: {"throughput": 80},
             1785: {"throughput": 85}, 1837: {"throughput": 95}}
    second = {t: {"throughput": 100} for t in first}
    mapping = {consumer.QUICKEDIT_GEMM_P1: first, consumer.QUICKEDIT_GEMM_P2: second}
    with patch.object(consumer, "sweep", side_effect=mapping.__getitem__):
        assert "two neighbouring" in consumer.quickEditAffectedNeighbours()
        first[1750] = {"throughput": 99}
        try:
            consumer.quickEditAffectedNeighbours()
        except ValueError as error:
            assert "neighbouring" in str(error)
        else:
            raise AssertionError("an intervening point must invalidate adjacency")
        del first[1750]
        second[1785]["throughput"] = 84
        try:
            consumer.quickEditAffectedNeighbours()
        except ValueError as error:
            assert "does not recover" in str(error)
        else:
            raise AssertionError("lack of recovery must invalidate the claim")


def test_pass_label_comes_from_the_source_name():
    with patch.object(consumer, "sweep", return_value={1200: {}}):
        assert consumer.quickEditPassLabel() == "`gemm` pass 1 froze"
        with patch.object(consumer, "QUICKEDIT_GEMM_P1", "fixture-gemm-p2_sweep.csv"):
            assert consumer.quickEditPassLabel() == "`gemm` pass 2 froze"


def test_original_grid_guard_and_matched_grid_size():
    paths = tuple(consumer.CAVEAT_MEMBW.values())
    mapping = {p: {1402: {}, 1477: {}, 1560: {}} for p in paths}
    mapping[consumer.STOCK_MEMBW_VOLT] = mapping[paths[0]]
    mapping[consumer.MEMONLY_MEMBW] = mapping[paths[2]]
    with patch.object(consumer, "sweep", side_effect=mapping.__getitem__):
        # Corrected 2026-10-03: the claim now renders how many targets the original stock run
        # shares with the tuned and memory-only runs, rather than asserting one grid.
        assert "shares 3 of its 3 locked targets" in consumer.originalSummaryGridAgreement()
        assert "same 3-point grid" in consumer.summaryMatchedStockGridSize()
        mapping[paths[0]] = {1395: {}, 1545: {}, 1702: {}}
        assert "shares none of its 3 locked targets with the 3-point" in consumer.originalSummaryGridAgreement()
        mapping[paths[1]] = {1402: {}, 1477: {}}
        try:
            consumer.originalSummaryGridAgreement()
        except ValueError:
            pass
        else:
            raise AssertionError("tuned and memory-only runs on different grids must not render")


def test_reciprocal_loss_and_actual_worst_target():
    targets = consumer.SUMMARY_PLATEAU_TARGETS
    tuned = {t: {"throughput": 100} for t in targets}
    memonly = {t: {"throughput": 110} for t in targets}
    memonly[1710]["throughput"] = 125  # Worst point differs from today's 1867.
    mapping = {consumer.TUNED_MEMBW: tuned, consumer.MEMONLY_MEMBW: memonly}
    with patch.object(consumer, "sweep", side_effect=mapping.__getitem__):
        text = consumer.summaryCorrectedLossBase()
        assert "25.0% more than tuned at 1710 MHz" in text, text
        assert "that is -20.0%" in text, text
        assert "25.0%" in consumer.caveatEffectSize()


def test_cross_session_comparison_means_previous_sweeps_before_ratio():
    # The mean of denominators is 150. Averaging the two ratios instead
    # gives 50%, a different statistic from the intended 33.33%.
    target = 1545
    mapping = {consumer.MEMONLY_GEMM_SAMESESSION: {target: {"throughput": 200}},
               consumer.MEMONLY_GEMM_CLEAN[0]: {target: {"throughput": 100}},
               consumer.MEMONLY_GEMM_CLEAN[1]: {target: {"throughput": 200}}}
    with patch.object(consumer, "sweep", side_effect=mapping.__getitem__):
        assert "33.33% on throughput" in consumer.caveatCrossSessionDrift()


def test_bios_grid_overlap_cannot_pass_disjoint_claim():
    mapping = {crosschip.SILENT_GEMM: {855: {}, 960: {}},
               crosschip.OC_GEMM: {885: {}, 990: {}}}
    with patch.object(crosschip, "sweep", side_effect=mapping.__getitem__):
        assert "share no targets" in crosschip.biosOriginalGridsDisjoint()
        mapping[crosschip.OC_GEMM][960] = {}
        try:
            crosschip.biosOriginalGridsDisjoint()
        except ValueError as error:
            assert "960" in str(error)
        else:
            raise AssertionError("a shared target must invalidate the disjoint statement")


def test_profile_plateau_does_not_use_transition_artifact():
    points = [{"applied_mhz": 6096}, {"applied_mhz": 3015}, {"applied_mhz": 3015}]
    snapshot = {"profiles": {"Profile4": {"curve_points": points}}}
    with patch.object(consumer, "_probe", return_value=snapshot):
        assert "near 3000 MHz" in consumer.summaryUpperCurveClock()
        points[1]["applied_mhz"] = points[2]["applied_mhz"] = 2800
        assert "near 2800 MHz" in consumer.summaryUpperCurveClock()


def test_fleet_precision_and_fractions():
    assert reference.fleetRow(0, 0) == (100, 100, 1, 100)
    perf, power, units, fleet = reference.fleetRow(13.6845454545, 40.1074648772)
    assert abs(units - 1.1585410808) < 1e-9
    assert abs(fleet - 69.3879623739) < 1e-8
    assert reference._fractionWords(0.4) == "two-fifths"
    assert reference._fractionWords(0.3577230459) == "one-third"
    assert reference._fractionWords(2 / 3) == "two-thirds"
    assert reference._fractionWords(0.7819881195) == "four-fifths"
    # The text must follow a changed input, rather than always rendering today's words.
    fakeSummary = {"headroom_gap_pct": type("Mean", (), {"mean": lambda self: 50})()}
    fakeData = {"floorRow": {"gain_mean": 30}}
    with patch.object(reference, "SUMMARY", fakeSummary), patch.object(reference, "DATA", fakeData), \
         patch.object(reference, "_fleetComparison", return_value=((80, 50, 1.25, 62.5),
                                                                   (95, 75, 1.05, 78.75))):
        text = reference.fleetHeadroomCapitalFractions()
        assert text == "Giving up two-fifths of the headroom removes four-fifths of the extra capital.", text


def test_illustrative_ratio_tracks_assumed_inputs():
    text = reference._illustrativeEnergyPrice(("example", 400, 180, 900, 3))
    assert "| $400 | 180 W | ~$900 (3 yr) | 2.25 |" in text, text
    assert "4.50" in reference._illustrativeEnergyPrice(("example", 200, 180, 900, 3))


def test_same_number_in_another_sentence_does_not_hide_drift():
    # Coverage counts numeric tokens, but matching must still check the
    # specific sentence. A second 79% elsewhere cannot rescue the bad 78%.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "paper.md").write_text("DRAM bandwidth, at roughly 78% of the rated peak.\n"
                                      "Another paragraph says 79%.\n", encoding="utf-8")
        entry = {"claimId": "fixture", "document": "paper.md", "section": "3.3.2",
                 "render": lambda: "DRAM bandwidth, at roughly 79% of the rated peak",
                 "mixedProvenance": None}
        with patch.object(audit, "REPO_ROOT", root), patch.object(audit, "_documentCache", {}):
            assert audit.audit([entry])[0]["status"] == "FAIL"
            (root / "paper.md").write_text((entry["render"]() + "\n") * 2, encoding="utf-8")
            audit._documentCache.clear()
            assert audit.audit([entry])[0]["status"] == "AMBIGUOUS"


def main():
    failures = 0
    for name, function in list(globals().items()):
        if not name.startswith("test_"):
            continue
        if name.startswith(("test_fleet_", "test_illustrative_")) and reference.DATA is None:
            print(f"[SKIP] {name}: fetched V100 data is absent; these claims do not register.")
            continue
        try:
            function()
            print(f"[PASS] {name}")
        except Exception as error:
            failures += 1
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
