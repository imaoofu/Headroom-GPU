"""
Tests for the guards inside the 3070 Ti cross-chip claims.

WHY THIS FILE EXISTS, AND WHAT IT IS FOR
    Four of the claims in claims_crosschip.py carry a check that raises when the DATA stops
    supporting the sentence around it, rather than merely changing a number: the OC BIOS drawing
    more power at every matched point, the silent run being the hotter one, neither BIOS reaching
    its clock ceiling, and the two membw sweeps sharing all thirteen targets.

    A mutation run showed all four surviving deletion, because against today's data the guard
    condition is false and removing it changes nothing observable. That is the same trap recorded
    three times in test_audit_claims.py: a check that cannot be observed to fail is not a check.

    So each test below feeds one guard the data it exists to reject, and then feeds it data it
    should accept - because a guard that raises unconditionally is no better than one that never
    raises.

RUN
    python analysis/test_claims_crosschip.py
"""

import csv
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_claims                                     # noqa: E402
import claims_crosschip as cc                           # noqa: E402

failures = []


def check(name, ok, detail=""):
    if ok:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name}" + (f"\n       {detail}" if detail else ""))
        failures.append(name)


# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------

COLUMNS = [
    "target_frequency_mhz", "achieved_frequency_avg", "achieved_frequency_min",
    "achieved_frequency_max", "memory_clock_avg_mhz", "memory_clock_min_mhz",
    "memory_clock_max_mhz", "lock_held", "lock_miss_mhz", "lock_miss_direction",
    "power_avg_w", "power_min_w", "power_max_w", "temperature_avg_c", "temperature_max_c",
    "utilization_avg_pct", "power_avg_process_w", "power_window_applied", "workload_seconds",
    "bench_seconds", "bench_wall_seconds", "bench_monitoring_s", "bench_throughput",
    "bench_throughput_unit", "bench_ok", "samples", "samples_process", "throttle_masks_seen",
]


def writeSweep(path, points, unit="FLOP/s", masks=None):
    """Write a sweep CSV the real loader will accept.

    `points` is a list of (target, achievedMhz, watts, throughput, tempAvg).
    `masks` optionally maps a target to its throttle_masks_seen string; anything absent gets
    "0x1", the idle mask, which is what a healthy point actually records.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for target, mhz, watts, throughput, temp in points:
            writer.writerow([
                target, mhz, mhz, mhz, 9251, 9251, 9251, "True", 0, "",
                watts, watts, watts, temp, temp + 2,
                98.0, watts, "True", 20, 20, 20, 20, throughput, unit, "True", 20, 20,
                (masks or {}).get(target, "0x0000000000000001"),
            ])


def withFixture(build, call):
    """Run `call` against a throwaway repository laid out the way the claims expect."""
    saved = audit_claims.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        build(root / "data" / "frequency-sweeps")
        try:
            audit_claims.REPO_ROOT = root
            audit_claims._sweepCache.clear()
            return call()
        finally:
            audit_claims.REPO_ROOT = saved
            audit_claims._sweepCache.clear()


GRID = [855, 960, 1065, 1170, 1275, 1380, 1485]


def buildPair(silentWatts, ocWatts, silentTemp, ocTemp, ocThroughput=None):
    """A silent and a matched-grid OC sweep that differ only in the ways a test cares about."""
    def build(root):
        writeSweep(root / cc.SILENT_GEMM,
                   [(t, float(t), silentWatts(t), 1e10 * t, silentTemp(t)) for t in GRID])
        writeSweep(root / cc.OC_GEMM_MATCHED,
                   [(t, float(t), ocWatts(t),
                     (ocThroughput(t) if ocThroughput else 1e10 * t), ocTemp(t)) for t in GRID])
    return build


# --------------------------------------------------------------------------------------
# The four guards
# --------------------------------------------------------------------------------------

def testMatchedPowerGuardRejectsALostDirection():
    """The paragraph calls this the clearest evidence that shipped voltage is not required voltage.

    That reading needs the OC BIOS to draw more power at EVERY matched point. If one point ever
    inverts, a mean is still computable and would render happily under prose that has stopped
    being true.
    """
    # One point where the OC BIOS draws less: the claim must refuse the whole comparison.
    inverted = buildPair(lambda t: 100.0, lambda t: 130.0 if t != 1275 else 90.0,
                         lambda t: 50.0, lambda t: 50.0)
    raised = False
    try:
        withFixture(inverted, cc.matchedPower)
    except ValueError:
        raised = True
    check("an inverted power point is refused", raised, "it rendered a mean anyway")

    higher = buildPair(lambda t: 100.0, lambda t: 130.0, lambda t: 50.0, lambda t: 50.0)
    text = withFixture(higher, cc.matchedPower)
    check("a uniformly higher OC power still renders", "+30.00%" in text, f"got {text!r}")


def testThermalGuardRejectsAReversedTemperature():
    """The thermal argument only works while the SILENT run is the hotter one.

    Reverse the temperatures and the paragraph's reasoning is gone - but the numbers would still
    format. The guard is what makes the argument, not the formatting.
    """
    # TWO hotter points, not zero. A fixture with none makes `hotter` empty, and min() over an
    # empty sequence raises ValueError all by itself - so the test passed whether the guard was
    # there or not, and a mutation run caught it doing exactly that. Two points leaves the
    # rendering path working, so the only thing that can raise is the guard.
    reversed_ = buildPair(lambda t: 100.0, lambda t: 130.0,
                          silentTemp=lambda t: 60.0 if t in (855, 960) else 45.0,
                          ocTemp=lambda t: 52.0)
    message = ""
    try:
        withFixture(reversed_, cc.thermalRunsBackwards)
    except ValueError as error:
        message = str(error)
    check("too few hotter points is refused", "no longer the hotter one" in message,
          f"got {message!r}" if message else "it rendered a range anyway")

    asMeasured = buildPair(lambda t: 100.0, lambda t: 130.0,
                           silentTemp=lambda t: 58.0, ocTemp=lambda t: 52.0)
    text = withFixture(asMeasured, cc.thermalRunsBackwards)
    check("the measured ordering still renders", "C against" in text, f"got {text!r}")


def testPeakClockGuardRejectsABiosThatReachesItsCeiling():
    """5.5 says the card is power-limited rather than clock-limited. That is a claim about the
    data, not a description of it, and it has to be able to fail."""
    def build(root):
        # Throughput rising all the way to the top target: the card reaches its ceiling.
        writeSweep(root / cc.SILENT_GEMM,
                   [(t, float(t), 100.0 + t / 20, 1e10 * t, 50.0) for t in GRID])
        writeSweep(root / cc.OC_GEMM,
                   [(t, float(t), 100.0 + t / 20, 1e10 * t, 50.0) for t in GRID])
    raised = False
    try:
        withFixture(build, cc.peakClocksAgainstCeilings)
    except ValueError:
        raised = True
    check("a BIOS that reaches its ceiling is refused", raised, "it rendered a comparison anyway")

    def buildShort(root):
        # Peak in the middle, top targets undershooting - the measured behaviour.
        points = [(t, float(t) if t < 1380 else 1300.0, 100.0, 1e10 * min(t, 1380), 50.0)
                  for t in GRID]
        writeSweep(root / cc.SILENT_GEMM, points)
        writeSweep(root / cc.OC_GEMM, points)
    text = withFixture(buildShort, cc.peakClocksAgainstCeilings)
    check("a card short of its ceiling still renders", "against ceilings of" in text, f"got {text!r}")


def testReplicateGuardRejectsAChangedTargetCount():
    """"all thirteen shared targets" is a sentence, and thirteen is checkable."""
    def build(root):
        for path in cc.OC_MEMBW_RUNS:
            writeSweep(root / path,
                       [(t, float(t), 100.0, 1e11 * t, 50.0) for t in GRID], unit="B/s")
    raised = False
    try:
        withFixture(build, cc.membwReplicates)
    except ValueError:
        raised = True
    check("a grid that is not thirteen targets is refused", raised, "it rendered a mean anyway")


testMatchedPowerGuardRejectsALostDirection()
testThermalGuardRejectsAReversedTemperature()
testPeakClockGuardRejectsABiosThatReachesItsCeiling()
testReplicateGuardRejectsAChangedTargetCount()


# --------------------------------------------------------------------------------------
# The 5.5.3 guards - voltage floor, flat bandwidth band, power-capped ceiling
# --------------------------------------------------------------------------------------

VOLT_COLUMNS = ["target", "achieved", "throughputGbs", "powerW", "sampleCount", "voltage",
                "crossbar", "memoryMhz"]


def writeVoltage(path, points):
    """Write a *_voltage.csv the real voltageJoin() will accept.

    `points` is a list of (target, achievedMhz, volts, crossbarMhz).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(VOLT_COLUMNS)
        for target, mhz, volts, crossbar in points:
            writer.writerow([target, mhz, 500.0, 200.0, 6, volts, crossbar, 9251])


def testVoltageFloorGuardRejectsANonFlatFloor():
    """The sentence says the OC BIOS holds ONE voltage across the band.

    A floor that drifts by a millivolt still formats as a range and would render under prose that
    has stopped being true, so flatness is asserted rather than described.
    """
    def drifting(root):
        writeVoltage(root / cc.VOLTS(cc.OC_GEMM_FINE),
                     [(t, float(t), 0.819 if t < 1500 else 0.822, 1410.0)
                      for t in (1200, 1290, 1380, 1500, 1590)])
    raised = False
    try:
        withFixture(drifting, cc.voltageFloor)
    except ValueError:
        raised = True
    check("a floor that drifts by 3 mV is refused", raised, "it rendered a range anyway")

    def flat(root):
        writeVoltage(root / cc.VOLTS(cc.OC_GEMM_FINE),
                     [(t, float(t), 0.819, 1410.0) for t in (1200, 1290, 1380, 1500, 1590)])
    text = withFixture(flat, cc.voltageFloor)
    check("a genuinely flat floor still renders", "0.819 V" in text and "5 points" in text,
          f"got {text!r}")


def testMembwFlatGuardRejectsARespondingWorkload():
    """The claim's whole point is that core clock buys no bandwidth on this chip.

    If a future card's membw DOES scale, the span still computes and the sentence would be false
    rather than merely differently-numbered.
    """
    grid = [855, 1275, 1710, 2130]

    def responding(root):
        # 10% across the band: a workload that is not memory-bound.
        writeSweep(root / cc.OC_MEMBW_V,
                   [(t, float(t), 200.0, 500e9 * (1 + 0.10 * i / 3), 50.0)
                    for i, t in enumerate(grid)], unit="B/s")
        writeVoltage(root / cc.VOLTS(cc.OC_MEMBW_V),
                     [(t, float(t), 0.819, 1410.0) for t in grid])
    raised = False
    try:
        withFixture(responding, cc.membwFlat)
    except ValueError:
        raised = True
    check("a bandwidth band that spans 10% is refused", raised, "it rendered a span anyway")

    def flat(root):
        writeSweep(root / cc.OC_MEMBW_V,
                   [(t, float(t), 200.0, 500e9 * (1 + 0.001 * i / 3), 50.0)
                    for i, t in enumerate(grid)], unit="B/s")
        writeVoltage(root / cc.VOLTS(cc.OC_MEMBW_V),
                     [(t, float(t), 0.819, 1410.0) for t in grid])
    text = withFixture(flat, cc.membwFlat)
    check("a genuinely flat band still renders", "0.10%" in text, f"got {text!r}")


def testPowerCapGuardRejectsACapAwayFromTheCollapse():
    """The section argues the cap and the collapse coincide EXACTLY.

    One capped point that held its lock, or one collapsed point with no cap, and the causal
    reading is gone while the counts would still format.
    """
    held = [(t, float(t)) for t in (855, 1275, 1710)]
    collapsed = [(t, 1775.0) for t in (1815, 2130)]

    def misaligned(root):
        # SwPowerCap on a point that held its lock: cap and collapse no longer coincide.
        masks = {1275: "0x0000000000000004", 1815: "0x0000000000000004",
                 2130: "0x0000000000000004"}
        writeSweep(root / cc.OC_GEMM_V,
                   [(t, mhz, 250.0, 1e10 * t, 50.0) for t, mhz in held + collapsed], masks=masks)
    raised = False
    try:
        withFixture(misaligned, cc.gemmPowerCap)
    except ValueError:
        raised = True
    check("a power cap on a point that held its lock is refused", raised,
          "it rendered counts anyway")

    def thermal(root):
        masks = {1815: "0x0000000000000044", 2130: "0x0000000000000004"}
        writeSweep(root / cc.OC_GEMM_V,
                   [(t, mhz, 250.0, 1e10 * t, 50.0) for t, mhz in held + collapsed], masks=masks)
    raised = False
    try:
        withFixture(thermal, cc.gemmPowerCap)
    except ValueError:
        raised = True
    check("a hardware thermal slowdown anywhere in the run is refused", raised,
          "the section says the ceiling is power, not heat")

    def aligned(root):
        masks = {1815: "0x0000000000000004", 2130: "0x0000000000000004"}
        writeSweep(root / cc.OC_GEMM_V,
                   [(t, mhz, 250.0, 1e10 * t, 50.0) for t, mhz in held + collapsed], masks=masks)
    text = withFixture(aligned, cc.gemmPowerCap)
    check("a cap that coincides with the collapse still renders",
          "2 targets" in text and "3 below" in text, f"got {text!r}")


testVoltageFloorGuardRejectsANonFlatFloor()
testMembwFlatGuardRejectsARespondingWorkload()
testPowerCapGuardRejectsACapAwayFromTheCollapse()


# --------------------------------------------------------------------------------------
# The Session B guards - the additive model, and the offset description
# --------------------------------------------------------------------------------------
#
# These two claims do not report a measurement, they report a COMPARISON between two descriptions
# of the same data. That makes their guards load-bearing in a way the others' are not: if the
# comparison ever inverts, both claims can still render a perfectly well-formed number under prose
# that has become false.


def buildHwinfoPair(silentWatts, ocWatts):
    """A SILENT and an OC matched sweep on the shared grid, differing only in power."""
    def build(root):
        writeSweep(root / cc.SILENT_GEMM_V,
                   [(t, float(t), silentWatts(t), 1e10 * t, 50.0) for t in GRID])
        writeSweep(root / cc.OC_GEMM_V,
                   [(t, float(t), ocWatts(t), 1e10 * t, 50.0) for t in GRID])
    return build


def testAdditiveGuardRejectsAMultiplicativeWorld():
    """The claim exists to say the additive form predicts better. It must refuse to say it if not.

    A world where the gap really IS a constant ratio is the honest counter-case: there the ratio
    model wins on leave-one-out and the sentence "the additive model reduces error by N%" is
    simply wrong. The guard has to fire on exactly that.
    """
    # Purely multiplicative: OC is always 1.25x SILENT, and SILENT varies a lot across the band
    # so the two models genuinely diverge. The ratio model should win outright.
    multiplicative = buildHwinfoPair(lambda t: 50.0 + t / 10.0,
                                     lambda t: (50.0 + t / 10.0) * 1.25)
    raised = False
    try:
        withFixture(multiplicative, cc.additiveBeatsRatio)
    except ValueError:
        raised = True
    check("a genuinely multiplicative gap is refused by the additive claim", raised,
          "it rendered a reduction anyway")

    # Purely additive: a fixed 40 W offset. The claim should render.
    additive = buildHwinfoPair(lambda t: 50.0 + t / 10.0,
                               lambda t: 50.0 + t / 10.0 + 40.0)
    text = withFixture(additive, cc.additiveBeatsRatio)
    check("a genuinely additive gap still renders", "reduction" in text, f"got {text!r}")


def testOffsetSpreadGuardRejectsAWorseDescription():
    """Same test from the other direction, on the spread rather than the prediction error."""
    multiplicative = buildHwinfoPair(lambda t: 50.0 + t / 10.0,
                                     lambda t: (50.0 + t / 10.0) * 1.25)
    raised = False
    try:
        withFixture(multiplicative, cc.gapIsAnOffset)
    except ValueError:
        raised = True
    check("an offset description that is NOT the tighter one is refused", raised,
          "it rendered a spread anyway")

    additive = buildHwinfoPair(lambda t: 50.0 + t / 10.0,
                               lambda t: 50.0 + t / 10.0 + 40.0)
    text = withFixture(additive, cc.gapIsAnOffset)
    check("an offset description that IS tighter renders", "relative spread" in text,
          f"got {text!r}")


testAdditiveGuardRejectsAMultiplicativeWorld()
testOffsetSpreadGuardRejectsAWorseDescription()


if failures:
    print(f"{len(failures)} check(s) failed.")
    raise SystemExit(1)
print("ALL CHECKS PASSED")
