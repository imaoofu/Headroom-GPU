"""
Known-answer checks for analyze_constrained.py.

Written BEFORE trusting any number the analysis prints, for the reason the fine-sweep
analysis needed the same treatment: a plausible-looking optimiser that is quietly wrong
produces plausible-looking results, and there is no way to tell from the output. Every
case here has an answer derivable by hand.

Run: python analysis/test_analyze_constrained.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_constrained import (  # noqa: E402
    analyseCurves,
    bestFixedFrequency,
    bindingCurve,
    buildPoints,
    loadSweepCurves,
    constrainedOptimum,
    flatTopCurves,
    monotonicPerformanceViolations,
    nearDuplicateFrequencies,
    singlePeakViolations,
    structuralPrediction,
)

failures = []


def check(description, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {description}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(description)


def synthetic():
    """
    A hand-built curve with an obvious answer.

    Frequencies 1000-1500. Performance rises monotonically. Power rises faster, so
    efficiency peaks in the middle. Reference is 1500 (perf 1.00 by construction).

      MHz   perf   power   eff = perf/power   eff relative to 1500
     1000   0.70    50     0.01400            1.400
     1100   0.80    55     0.01455            1.455
     1200   0.88    62     0.01419            1.419
     1300   0.94    72     0.01306            1.306
     1400   0.98    85     0.01153            1.153
     1500   1.00   100     0.01000            1.000

    Unconstrained optimum: 1100 MHz, +45.5% efficiency, 20% performance given up.
    """
    return buildPoints(
        [1000, 1100, 1200, 1300, 1400, 1500],
        [0.70, 0.80, 0.88, 0.94, 0.98, 1.00],
        [50, 55, 62, 72, 85, 100],
    )


print("Reference normalisation:")
points = synthetic()
reference = points[-1]
check("reference point has perf exactly 1.0", abs(reference["perf"] - 1.0) < 1e-12)
check("reference point has eff exactly 1.0", abs(reference["eff"] - 1.0) < 1e-12)
check("efficiency peaks at 1100 MHz",
      max(points, key=lambda p: p["eff"])["mhz"] == 1100)
check("peak efficiency is +45.5%",
      abs(max(points, key=lambda p: p["eff"])["eff"] - 1.4545) < 1e-3)

print("\nFloor not binding - constraint is slack, so the unconstrained optimum stands:")
best = constrainedOptimum(points, 0.70)
check("floor 70% returns 1100 MHz", best["mhz"] == 1100, f"got {best['mhz']}")

print("\nFloor binding - constraint pushes the answer up to the lowest feasible point:")
best = constrainedOptimum(points, 0.90)
check("floor 90% returns 1300 MHz (0.94 is the lowest perf >= 0.90)",
      best["mhz"] == 1300, f"got {best['mhz']}")
check("realised performance OVERSHOOTS the floor (0.94, not 0.90)",
      abs(best["perf"] - 0.94) < 1e-9, f"got {best['perf']}")
best = constrainedOptimum(points, 0.95)
check("floor 95% returns 1400 MHz", best["mhz"] == 1400, f"got {best['mhz']}")

print("\nDegenerate floors:")
best = constrainedOptimum(points, 1.00)
check("floor 100% returns the reference frequency", best["mhz"] == 1500, f"got {best['mhz']}")
check("floor 100% yields exactly 0% gain", abs(best["eff"] - 1.0) < 1e-12)
best = constrainedOptimum(points, 0.0)
check("floor 0% equals the unconstrained optimum", best["mhz"] == 1100, f"got {best['mhz']}")
check("floor above 1.0 is infeasible and returns None",
      constrainedOptimum(points, 1.01) is None)

print("\nFloating-point boundary - a floor exactly equal to a measured value must be feasible:")
exact = buildPoints([1000, 1500], [0.95, 1.00], [50, 100])
best = constrainedOptimum(exact, 0.95)
check("perf exactly 0.95 satisfies a 0.95 floor", best["mhz"] == 1000, f"got {best['mhz']}")

print("\nClosed form agrees with brute force on a well-behaved curve:")
for floor in (0.0, 0.70, 0.90, 0.95, 1.00):
    a = constrainedOptimum(points, floor)
    b = structuralPrediction(points, floor)
    check(f"floor {floor:.2f}: closed form matches", a["mhz"] == b["mhz"],
          f"brute {a['mhz']} vs closed {b['mhz']}")

print("\nAssumption detectors must FIRE on curves that violate them:")
dip = buildPoints([1000, 1100, 1200], [0.90, 0.85, 1.00], [50, 55, 100])
check("non-monotonic performance is detected", len(monotonicPerformanceViolations(dip)) == 1,
      f"got {monotonicPerformanceViolations(dip)}")
check("monotonic curve reports no violations", monotonicPerformanceViolations(points) == [])

# Two separated efficiency peaks: eff = perf/power relative to the last point.
#   1000: 0.50/40 = 0.01250   1100: 0.60/40 = 0.01500  <- peak
#   1200: 0.70/60 = 0.01167   1300: 0.90/60 = 0.01500  <- second peak
#   1400: 0.95/90 = 0.01056   1500: 1.00/90 = 0.01111
twoPeak = buildPoints([1000, 1100, 1200, 1300, 1400, 1500],
                      [0.50, 0.60, 0.70, 0.90, 0.95, 1.00],
                      [40, 40, 60, 60, 90, 90])
check("second efficiency peak is detected at exactly 1300 and 1500 MHz",
      singlePeakViolations(twoPeak) == [1300.0, 1500.0],
      f"got {singlePeakViolations(twoPeak)}")
check("single-peaked curve reports no extra peaks", singlePeakViolations(points) == [])

print("\nBrute force must WIN where the closed form is wrong:")
# On the two-peak curve the closed form can pick the wrong peak once the floor bites.
mismatches = 0
for floor in (0.0, 0.55, 0.65, 0.80, 0.92, 0.96, 1.00):
    a = constrainedOptimum(twoPeak, floor)
    b = structuralPrediction(twoPeak, floor)
    if a is None or b is None:
        continue
    if a["mhz"] != b["mhz"]:
        mismatches += 1
    check(f"floor {floor:.2f}: brute force efficiency >= closed form",
          a["eff"] >= b["eff"] - 1e-12, f"{a['eff']:.5f} vs {b['eff']:.5f}")
print(f"  (closed form disagreed on {mismatches} of 7 floors for the two-peak curve - "
      f"which is exactly why the analysis brute-forces and only CHECKS the shortcut)")

print("\nPower saving is measured against the reference, not the neighbour:")
best = constrainedOptimum(points, 0.90)
check("1300 MHz saves 28% power against 1500 MHz",
      abs((1.0 - best["power_rel"]) * 100.0 - 28.0) < 1e-9,
      f"got {(1.0 - best['power_rel']) * 100.0:.2f}%")

print("\nUnsorted input must not change the answer:")
shuffled = buildPoints([1500, 1000, 1300, 1100, 1400, 1200],
                       [1.00, 0.70, 0.94, 0.80, 0.98, 0.88],
                       [100, 50, 72, 55, 85, 62])
check("shuffled input gives the same optimum",
      constrainedOptimum(shuffled, 0.90)["mhz"] == 1300)
check("shuffled input normalises to the highest frequency",
      abs(shuffled[-1]["perf"] - 1.0) < 1e-12 and shuffled[-1]["mhz"] == 1500)

print("\nAggregate statistics - the function that produces every reported number:")
# Hand-derived from synthetic(), reference = 1500 MHz (perf 1.00, power 100, eff 0.01).
#   floor 0.90 -> 1300 MHz: perf 0.94, power 72, eff 0.94/72 = 0.0130556
#       gain   = 0.0130556/0.01 - 1 = +30.56%
#       loss   = 1 - 0.94           =   6.00%
#       saved  = 1 - 72/100         =  28.00%
#   floor 0.70 -> 1100 MHz: perf 0.80, power 55, eff 0.80/55 = 0.0145455
#       gain   = +45.45%,  loss = 20.00%,  saved = 45.00%
rows, disagreements = analyseCurves({"synthetic": points}, [0.90, 0.70])
byFloor = {round(r["floor"], 2): r for r in rows}

check("both floors produce a row", set(byFloor) == {0.9, 0.7}, f"got {sorted(byFloor)}")
check("floor 0.90 gain is +30.56%", abs(byFloor[0.9]["gain_mean"] - 30.5556) < 1e-3,
      f"got {byFloor[0.9]['gain_mean']:.4f}")
check("floor 0.90 loss is 6.00%", abs(byFloor[0.9]["loss_mean"] - 6.0) < 1e-9,
      f"got {byFloor[0.9]['loss_mean']:.4f}")
check("floor 0.90 power saved is 28.00%", abs(byFloor[0.9]["power_saved_mean"] - 28.0) < 1e-9,
      f"got {byFloor[0.9]['power_saved_mean']:.4f}")
check("floor 0.70 gain is +45.45%", abs(byFloor[0.7]["gain_mean"] - 45.4545) < 1e-3,
      f"got {byFloor[0.7]['gain_mean']:.4f}")
check("floor 0.70 loss is 20.00%", abs(byFloor[0.7]["loss_mean"] - 20.0) < 1e-9,
      f"got {byFloor[0.7]['loss_mean']:.4f}")
check("floor 0.70 power saved is 45.00%", abs(byFloor[0.7]["power_saved_mean"] - 45.0) < 1e-9,
      f"got {byFloor[0.7]['power_saved_mean']:.4f}")
check("well-behaved curve produces no closed-form disagreements", disagreements == [],
      f"got {disagreements}")
check("gains are positive when efficiency beats the reference",
      byFloor[0.9]["gain_min"] > 0 and byFloor[0.7]["gain_min"] > 0)

# 'moved' must count curves that actually left the reference frequency.
check("floor 0.90 counts the curve as moved", byFloor[0.9]["moved"] == 1)
atCeiling, _ = analyseCurves({"synthetic": points}, [1.00])
check("floor 1.00 counts the curve as NOT moved", atCeiling[0]["moved"] == 0,
      f"got {atCeiling[0]['moved']}")
check("floor 1.00 is flagged noise-sensitive", atCeiling[0]["noise_sensitive"] is True)
check("floor 0.90 is NOT flagged noise-sensitive", byFloor[0.9]["noise_sensitive"] is False)

# A curve peaking below its reference is the V100 flat-top case, and must be caught.
flatTop = buildPoints([1000, 1500], [1.02, 1.00], [60, 100])
check("flat-top curve is detected", "f" in flatTopCurves({"f": flatTop}))
check("monotonic curve is not flagged flat-top", flatTopCurves({"s": points}) == {})

# Near-duplicate grid points: the consumer sweeps clamp several targets to one clock.
clamped = buildPoints([1000, 1495, 1500], [0.70, 0.999, 1.00], [50, 99, 100])
check("near-duplicate frequencies are detected",
      nearDuplicateFrequencies(clamped) == [(1495.0, 1500.0)],
      f"got {nearDuplicateFrequencies(clamped)}")
check("well-separated frequencies are not flagged", nearDuplicateFrequencies(points) == [])

print("\nOne fixed frequency vs per-workload selection:")
# Two curves sharing a grid, reference 1500 MHz for both.
#
#   sensitive : perf 0.50 @1000, 1.00 @1500 | power 40, 100
#               eff 0.0125, 0.0100  ->  relative 1.25, 1.00
#   flat      : perf 0.98 @1000, 1.00 @1500 | power 40, 100
#               eff 0.0245, 0.0100  ->  relative 2.45, 1.00
#
# At floor 0.95: 'sensitive' cannot use 1000 (0.50 < 0.95) so it is stuck at 1500 (+0%).
#                'flat' can (0.98 >= 0.95) so it takes 1000 (+145%).
#                per-workload mean gain = (0 + 145)/2 = 72.5%
#                a FIXED frequency must serve both, so 1000 is out; only 1500 works, +0%.
#                gap = 72.5 pp, i.e. 100% of all available gain needs the workload identity.
sensitive = buildPoints([1000, 1500], [0.50, 1.00], [40, 100])
flat = buildPoints([1000, 1500], [0.98, 1.00], [40, 100])
pair = {"sensitive": sensitive, "flat": flat}

fixed = bestFixedFrequency(pair, 0.95)
check("floor 0.95 pins the fixed policy at 1500 MHz", fixed[0] == 1500.0, f"got {fixed}")
check("fixed policy gains 0% at 1500 MHz", abs((fixed[1] - 1.0) * 100.0) < 1e-9,
      f"got {(fixed[1] - 1.0) * 100.0:.4f}%")

perMean = sum(constrainedOptimum(p, 0.95)["eff"] for p in pair.values()) / 2
check("per-workload mean gain is +72.5%", abs((perMean - 1.0) * 100.0 - 72.5) < 1e-9,
      f"got {(perMean - 1.0) * 100.0:.4f}%")

# When the constraint is slack both curves prefer the SAME frequency, so the gap vanishes.
# At floor 0.40: both feasible at 1000. Fixed picks 1000, mean eff (1.25+2.45)/2 = 1.85.
# Per-workload also picks 1000 for both. Gap must be exactly zero.
fixedSlack = bestFixedFrequency(pair, 0.40)
perSlack = sum(constrainedOptimum(p, 0.40)["eff"] for p in pair.values()) / 2
check("slack floor puts the fixed policy at 1000 MHz", fixedSlack[0] == 1000.0, f"got {fixedSlack}")
check("slack floor gain is +85%", abs((fixedSlack[1] - 1.0) * 100.0 - 85.0) < 1e-9,
      f"got {(fixedSlack[1] - 1.0) * 100.0:.4f}%")
check("slack floor gap is EXACTLY zero - the workloads agree",
      abs(perSlack - fixedSlack[1]) < 1e-12, f"got {(perSlack - fixedSlack[1]) * 100:.6f} pp")

# Identical curves can never produce a gap, whatever the floor.
twin = {"a": buildPoints([1000, 1500], [0.96, 1.00], [40, 100]),
        "b": buildPoints([1000, 1500], [0.96, 1.00], [40, 100])}
for floor in (0.95, 0.90, 0.50):
    f = bestFixedFrequency(twin, floor)
    p = sum(constrainedOptimum(pts, floor)["eff"] for pts in twin.values()) / 2
    check(f"identical curves have zero gap at floor {floor:.2f}", abs(p - f[1]) < 1e-12,
          f"got {(p - f[1]) * 100:.6f} pp")

print("\nThe binding workload is the one with the highest floor of its own:")
name, mhz, lowest = bindingCurve(pair, 0.95)
check("'sensitive' is identified as binding", name == "sensitive", f"got {name}")
check("binding frequency is 1500 MHz", mhz == 1500.0, f"got {mhz}")
check("'flat' is recorded as needing only 1000 MHz", lowest["flat"] == 1000.0,
      f"got {lowest['flat']}")

print("\nCurves on different grids cannot share a policy frequency, and must say so:")
mismatched = {"a": buildPoints([1000, 1500], [0.9, 1.0], [40, 100]),
              "b": buildPoints([1100, 1600], [0.9, 1.0], [40, 100])}
check("no shared grid returns None rather than inventing a comparison",
      bestFixedFrequency(mismatched, 0.90) is None,
      f"got {bestFixedFrequency(mismatched, 0.90)}")
check("empty curve set returns None", bestFixedFrequency({}, 0.90) is None)
check("a floor nothing can satisfy returns None",
      bestFixedFrequency(pair, 1.01) is None, f"got {bestFixedFrequency(pair, 1.01)}")

print()


# ---------------------------------------------------------------------------------------------
# The COMMANDED frequency basis, added 2026-08-29.
#
# WHY IT EXISTS: on consumer sweeps a workload clamps to whatever clock its own power draw
# allows, so twelve sweeps sharing thirteen commanded targets shared only five achieved clocks
# and reportFixedVersusPerWorkload could not run at all. A fixed-frequency POLICY sets a target
# and accepts what each workload sustains, so the target is the right key for that question.
#
# The V100 has one frequency per point and no clamping, so this must not change it.

sameFrequencies = [1000.0, 1100.0, 1200.0]
heldLower = [990.0, 1080.0, 1150.0]
perfCurve = [0.80, 0.92, 1.00]
powerCurve = [100.0, 130.0, 200.0]

withoutHeld = buildPoints(sameFrequencies, perfCurve, powerCurve)
withHeld = buildPoints(sameFrequencies, perfCurve, powerCurve,
                                          achieved=heldLower)

check("buildPoints without achieved carries no achieved_mhz key",
      all("achieved_mhz" not in point for point in withoutHeld))
check("buildPoints with achieved carries one per point",
      [point["achieved_mhz"] for point in withHeld] == heldLower)
check("passing achieved does not change perf",
      [p["perf"] for p in withHeld] == [p["perf"] for p in withoutHeld])
check("passing achieved does not change eff",
      [p["eff"] for p in withHeld] == [p["eff"] for p in withoutHeld])
check("passing achieved does not change mhz - it is carried, not substituted",
      [p["mhz"] for p in withHeld] == sameFrequencies)

# achieved must be reordered with the rest when frequencies arrive unsorted, or a point would
# be labelled with another point's achieved clock - a silent mislabelling, not an error.
shuffled = buildPoints([1200.0, 1000.0, 1100.0],
                                          [1.00, 0.80, 0.92], [200.0, 100.0, 130.0],
                                          achieved=[1150.0, 990.0, 1080.0])
check("achieved is sorted alongside frequencies, not left in input order",
      [p["achieved_mhz"] for p in shuffled] == heldLower,
      f"got {[p['achieved_mhz'] for p in shuffled]}")
check("and the sorted mhz still line up with it",
      [p["mhz"] for p in shuffled] == sameFrequencies)

try:
    loadSweepCurves("nothing*.csv", basis="nonsense")
    check("an unknown basis is rejected", False)
except ValueError:
    check("an unknown basis is rejected", True)


if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for item in failures:
        print(f"  - {item}")
    raise SystemExit(1)
print("ALL CHECKS PASSED")
