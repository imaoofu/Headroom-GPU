"""
Tests for select_probes.py.

WHAT THESE ARE FOR
    The module exists to correct a leak in curve_model.py - probes selected with every unit
    visible, then scored on those same units. A test suite for it has to do more than check that
    functions return numbers: it has to prove the fold isolation actually holds, because a leak is
    exactly the kind of defect that produces a plausible answer and no error.

    So the central case here is adversarial. It builds a dataset where one unit is an outlier that
    WOULD change which probes get selected, and asserts that the fold holding that unit out picks
    the set chosen in its absence. If nestedEvaluation ever regresses to selecting once up front,
    that check fails and nothing else needs to.

    The rest assert VALUES on synthetic data small enough to work out by hand.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from select_probes import (  # noqa: E402
    MEASUREMENT_NOISE_FLOOR,
    evenlySpacedProbes,
    exhaustiveBestProbes,
    greedyBestProbes,
    informativeIndices,
    nestedEvaluation,
    regretPercent,
    scoreProbeSet,
    selectionStability,
)

failures = []


def check(description, condition, detail=""):
    # The [PASS] / [FAIL] markers are load-bearing: run_tests.py counts literal occurrences to get
    # a suite's assertion count and treats a suite reporting ZERO as a silent failure.
    if condition:
        print(f"[PASS] {description}")
    else:
        print(f"[FAIL] {description}" + (f" - {detail}" if detail else ""))
        failures.append(description)


print("informativeIndices - the dead-column filter")
constantTop = np.array([[0.5, 0.8, 1.0],
                        [0.6, 0.9, 1.0],
                        [0.7, 0.7, 1.0]])
check("a zero-variance column is excluded", informativeIndices(constantTop) == [0, 1],
      f"got {informativeIndices(constantTop)}")
check("a column that varies is kept even if barely",
      informativeIndices(np.array([[1.0, 1.0], [1.0, 1.000001]])) == [1])
check("all-constant input yields no candidates",
      informativeIndices(np.ones((4, 3))) == [])

print("\nevenlySpacedProbes - the no-thought baseline")
check("one probe from a 12-wide range takes the first",
      evenlySpacedProbes(list(range(12)), 1) == [0],
      f"got {evenlySpacedProbes(list(range(12)), 1)}")
check("two probes take both ends", evenlySpacedProbes(list(range(12)), 2) == [0, 11],
      f"got {evenlySpacedProbes(list(range(12)), 2)}")
# np.linspace(0, 11, 3) gives 5.5 in the middle and Python rounds half to EVEN, so this is 6
# rather than 5. Pinned at the value the code actually produces; either is a fine midpoint, but a
# test that asserts the wrong one would fail on a correct implementation.
check("three probes take both ends and the middle",
      evenlySpacedProbes(list(range(12)), 3) == [0, 6, 11],
      f"got {evenlySpacedProbes(list(range(12)), 3)}")
check("asking for more probes than candidates returns all of them",
      evenlySpacedProbes([2, 4, 6], 9) == [2, 4, 6])
check("it draws from the candidate list, not from range(n)",
      evenlySpacedProbes([3, 7, 11, 15], 2) == [3, 15],
      f"got {evenlySpacedProbes([3, 7, 11, 15], 2)}")

print("\nregretPercent - efficiency given up, in points")
curve = np.array([0.80, 1.00, 0.95])
check("picking the true peak costs nothing", regretPercent(curve, 1) == 0.0)
check("picking a point 20 points below costs 20",
      abs(regretPercent(curve, 0) - 20.0) < 1e-9, f"got {regretPercent(curve, 0)}")
check("regret is measured against the curve's own peak, not against 1.0",
      abs(regretPercent(np.array([0.5, 0.6]), 0) - 10.0) < 1e-9,
      f"got {regretPercent(np.array([0.5, 0.6]), 0)}")

print("\nexhaustive vs greedy selection")
# A dataset where column 1 alone reconstructs everything: columns 0 and 2 are noise-ish constants
# per unit while column 1 varies with the unit's identity and the rest are functions of it.
rng = np.random.default_rng(20260911)
signal = rng.uniform(0.2, 0.9, size=12)
crafted = np.column_stack([np.full(12, 0.5), signal, signal * 0.5 + 0.25, np.full(12, 1.0)])
bestSingle, bestSingleError = exhaustiveBestProbes(crafted, [0, 1, 2], 1)
check("exhaustive search finds the one informative column", bestSingle == [1],
      f"got {bestSingle}")
# NOT an absolute threshold. Ridge(alpha=1.0) shrinks a single-feature fit noticeably, so even a
# perfectly informative probe lands well above zero - an earlier version of this check asserted
# <0.01 and failed against correct code. The meaningful claim is COMPARATIVE.
constantOnlyError = exhaustiveBestProbes(crafted, [0], 1)[1]
# The margin is deliberately modest: two of this fixture's four columns are constants that BOTH
# probes reconstruct perfectly, which dilutes the advantage into the column mean. A factor-of-two
# expectation failed here against correct code for exactly that reason.
check("the informative column reconstructs better than the constant one",
      bestSingleError < constantOnlyError * 0.9,
      f"informative {bestSingleError:.5f} vs constant {constantOnlyError:.5f}")
greedySingle, _ = greedyBestProbes(crafted, [0, 1, 2], 1)
check("greedy agrees with exhaustive when only one probe is taken",
      greedySingle == bestSingle, f"greedy {greedySingle} vs exhaustive {bestSingle}")
check("exhaustive never scores worse than greedy at the same probe count",
      exhaustiveBestProbes(crafted, [0, 1, 2], 2)[1]
      <= greedyBestProbes(crafted, [0, 1, 2], 2)[1] + 1e-12)
check("selection draws only from the candidate list it was given",
      exhaustiveBestProbes(crafted, [0, 2], 1)[0][0] in (0, 2))

print("\nscoreProbeSet - reconstruction and the choice it implies")
mae, regret, pick = scoreProbeSet(crafted, [1], 0)
check("a held-out unit's curve reconstructs with a finite error", np.isfinite(mae))
check("regret from a reconstruction is never negative", regret >= 0.0, f"got {regret}")
check("the index the reconstruction chose is returned and is in range",
      isinstance(pick, int) and 0 <= pick < crafted.shape[1], f"got {pick}")
check("the chosen index is the argmax of the reconstruction, so its regret is consistent",
      abs(regret - regretPercent(crafted[0], pick)) < 1e-9)
check("perfect information about a flat curve costs no regret",
      scoreProbeSet(np.tile(np.array([0.5, 0.7, 1.0, 0.9]), (8, 1)), [0, 1], 0)[1] == 0.0)

print("\nnestedEvaluation - THE fold-isolation check")
# Build 11 near-identical units for which column 0 is the best single probe, plus ONE outlier
# whose shape makes column 2 look best. Selecting over all 12 is pulled toward column 2; selecting
# on the 11 training units is not. The fold that holds the outlier out must pick column 0.
base = np.linspace(0.3, 0.9, 11)
ordinary = np.column_stack([base, base * 0.4 + 0.3, np.full(11, 0.5), np.full(11, 1.0)])
outlier = np.array([[0.5, 0.5, 0.95, 1.0]])
mixed = np.vstack([ordinary, outlier])

# ⛔ AN EARLIER VERSION OF THIS SECTION WAS DECORATIVE AND MUTATION TESTING CAUGHT IT.
# It built the outlier below, selected probes with and without it, and asserted the two agreed -
# reasoning that a leak would pull the selection toward the outlier. Reintroducing the exact leak
# (selecting from `curves` instead of `curves[trainMask]`) did NOT fail it: one outlier in twelve
# is not enough to change which single column wins, so the check passed either way. A test whose
# premise is "the defect would change the answer" is only as good as that premise.
#
# The replacement does not reason about consequences at all. It SPIES on what the selector is
# handed and asserts the held-out unit is not in it, which is the property the module claims.
seenBySelector = []


def spySelector(trainCurves, candidates, probeCount):
    seenBySelector.append(np.array(trainCurves, copy=True))
    return exhaustiveBestProbes(trainCurves, candidates, probeCount)


_, _, chosenPerFold, mixedPicks = nestedEvaluation(mixed, [0, 1, 2], 1, spySelector)
check("nested selection returns one probe set per unit", len(chosenPerFold) == 12,
      f"got {len(chosenPerFold)}")
check("the selector is called exactly once per fold", len(seenBySelector) == 12,
      f"got {len(seenBySelector)}")
check("the selector is handed exactly n-1 units every time, never all of them",
      all(seen.shape[0] == 11 for seen in seenBySelector),
      f"got {[seen.shape[0] for seen in seenBySelector]}")
leakedFolds = [fold for fold, seen in enumerate(seenBySelector)
               if any(np.array_equal(row, mixed[fold]) for row in seen)]
check("NO fold's selector sees the unit that fold will be scored on",
      leakedFolds == [], f"leaked on folds {leakedFolds}")

check("nested evaluation reports one decision per fold as well as one probe set",
      len(mixedPicks) == 12, f"got {len(mixedPicks)}")

honestMae, honestRegret, _, picks = nestedEvaluation(crafted, [0, 1, 2], 1, greedyBestProbes)
check("nested evaluation returns a finite mean MAE", np.isfinite(honestMae))
check("nested evaluation returns a non-negative mean regret", honestRegret >= 0.0,
      f"got {honestRegret}")
check("every per-fold decision is a valid column index",
      all(isinstance(i, int) and 0 <= i < crafted.shape[1] for i in picks), f"got {picks}")

print("\nselectionStability - whether the leak would have mattered")
modal, modalCount, distinct = selectionStability([(1,), (1,), (1,), (2,)])
check("the modal probe set is the most common one", modal == (1,), f"got {modal}")
check("its count is right", modalCount == 3, f"got {modalCount}")
check("the number of distinct sets is right", distinct == 2, f"got {distinct}")
allSame = selectionStability([(0, 3)] * 33)
check("a selection that never changes reports one distinct set", allSame[2] == 1)
check("...and a modal count equal to the fold count", allSame[1] == 33)

print("\nthe noise floor the verdict is judged against")
check("the measurement noise floor is the 0.76% within-session spread CLAUDE.md records",
      abs(MEASUREMENT_NOISE_FLOOR - 0.0076) < 1e-12, f"got {MEASUREMENT_NOISE_FLOOR}")

if failures:
    print(f"\n{len(failures)} CHECK(S) FAILED")
    raise SystemExit(1)
print("\nALL CHECKS PASSED")
