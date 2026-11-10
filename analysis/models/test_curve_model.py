"""
Known-answer checks for the probe-selection and curve-prediction machinery in curve_model.py.

WHY THIS MODULE
    It carries the project's cheap-characterisation claim: that a chip measured at three
    well-chosen frequencies can have its remaining ten predicted. If that machinery is wrong,
    the claim is wrong, and nothing else in the repo would notice - the outputs are plausible
    curves either way.

WHY THESE CHECKS LOOK INDIRECT
    predict() returns whatever a fitted Ridge regression produces. Asserting specific predicted
    efficiencies would either bake in sklearn's current numerics or require reimplementing
    Ridge here, and a test that reimplements the thing it tests proves nothing. So every check
    asserts a property that holds regardless of what the regression outputs: a boundary
    (fewer than 3 units cannot do leave-one-out), an invariant (identical units reconstruct
    exactly), a structural guarantee (indices sorted, alwaysInclude honoured), or an exact
    relationship against a value obtained by calling the code itself (the prior blend).

    The prior blend is checked at weight 0.25 rather than 0.5 deliberately. A symmetric weight
    cannot distinguish the correct blend from one with the two weights swapped.

PROVENANCE
    Drafted by a local model (qwen3-coder:30b via Ollama), then verified rather than trusted.
    Four defects, all of which crashed rather than failed quietly:

      - No `import numpy as np`, so the file died on its first fixture.
      - probeValues had 5 elements while the predictor was constructed with 3 probe indices.
        Ridge was fitted on 3 features and raised on a 5-feature input, taking out every
        predict() check. The model built the probe vector from the frequency axis rather than
        the probe axis.
      - `0.25 * prior` with `prior` as a Python list raises TypeError - list repetition needs
        an int. Only the ndarray form does elementwise scaling.
      - The populationMean equality check called np.allclose on possibly mismatched shapes,
        which raises. That is precisely the state the wrong-axis mutation produces, so the
        check would have crashed instead of reporting a clean failure. Shape is now asserted
        before values are compared.

    Eight deliberate mutations were then introduced into curve_model.py - swapping the prior
    blend weights, taking the minimum instead of the maximum optimal frequency, dropping the
    x100 on regret, letting the leave-one-out guard accept 2 units, dropping alwaysInclude,
    returning probe indices unsorted, taking the population mean along the wrong axis, and
    dropping the abs in the reconstruction error.

    Seven were caught on the first pass. The eighth was not, and the miss was the useful part:
    with abs removed the error is a mean of SIGNED residuals, and on the original fixture those
    happened to average positive, so every check still passed. Nothing in the test file was
    wrong - it simply had no fixture that could tell the two apart. The two fixtures added
    above were built specifically to separate them, and all eight are now caught. A test file
    that passes is not evidence; this is what the mutation step is for.

    Delete analysis/__pycache__ between mutations; a same-length edit can leave stale bytecode
    running while the source on disk reads correct.

Run: python analysis/test_curve_model.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
# analysis/ too, for load_data. The module under test bootstraps this itself, but relying on that
# would make these imports order-dependent for no reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curve_model import (
    reconstructionErrorForProbes, selectProbeFrequencies, CurvePredictor, regretPercent,
)

import numpy as np

failures = []


def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"       {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")


# 4 units by 5 frequencies. The counts differ on purpose: a mean along the wrong axis would
# have length 4 instead of 5, which a square fixture could not reveal.
curves = np.array(
    [
        [0.10, 0.30, 0.50, 0.70, 0.90],
        [0.20, 0.55, 0.62, 0.81, 1.00],
        [0.35, 0.50, 0.78, 0.90, 1.10],
        [0.40, 0.62, 0.80, 1.05, 1.15],
    ]
)
frequencies = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
PROBE_INDICES = [0, 1, 2]

check(
    "fewer than 3 units returns infinity, since leave-one-out needs a held-out unit",
    reconstructionErrorForProbes(curves[:2], PROBE_INDICES) == float("inf"),
    f"got {reconstructionErrorForProbes(curves[:2], PROBE_INDICES)}",
)

error = reconstructionErrorForProbes(curves, PROBE_INDICES)
check(
    "with 4 units the error is a finite, non-negative float",
    isinstance(error, float) and np.isfinite(error) and error >= 0.0,
    f"got {error!r}",
)

identical = np.array([[0.1, 0.3, 0.5, 0.7, 0.9]] * 3)
identicalError = reconstructionErrorForProbes(identical, PROBE_INDICES)
check(
    "identical units reconstruct exactly, giving an error of 0.0",
    identicalError < 1e-6,
    f"got {identicalError}",
)

check(
    "units that differ give a strictly positive error",
    error > 0.0,
    f"got {error}",
)

check(
    "the error is deterministic across repeated calls",
    reconstructionErrorForProbes(curves, PROBE_INDICES)
    == reconstructionErrorForProbes(curves, PROBE_INDICES),
)

# The next two exist because the error is a mean of ABSOLUTE residuals, and a mean of signed
# residuals passes every check above. Both fixtures are built so the signed version gives the
# wrong answer: an outlier unit is badly under-predicted when it is the held-out one, and two
# symmetric clusters produce residuals that cancel to nothing.
outlierUnit = np.array(
    [
        [0.10, 0.20, 0.30, 0.40, 0.50],
        [0.12, 0.22, 0.31, 0.41, 0.51],
        [0.11, 0.21, 0.32, 0.42, 0.52],
        [3.00, 3.10, 3.20, 3.30, 3.40],
    ]
)
outlierError = reconstructionErrorForProbes(outlierUnit, PROBE_INDICES)
check(
    "an outlier unit gives a positive error, not a negative one",
    outlierError > 0.0,
    f"got {outlierError}; a mean of signed residuals is negative here",
)

symmetricClusters = np.array(
    [
        [0.10, 0.20, 0.30, 0.40, 0.50],
        [0.11, 0.21, 0.31, 0.41, 0.51],
        [2.00, 2.10, 2.20, 2.30, 2.40],
        [2.01, 2.11, 2.21, 2.31, 2.41],
    ]
)
clusterError = reconstructionErrorForProbes(symmetricClusters, PROBE_INDICES)
check(
    "residuals that cancel in sign still register as error",
    clusterError > 1e-3,
    f"got {clusterError}; a mean of signed residuals cancels to about zero here",
)

chosen, _ = selectProbeFrequencies(frequencies, curves, 3)
check(
    "it returns exactly probeCount indices",
    len(chosen) == 3,
    f"got {chosen}",
)

# alwaysInclude is the HIGHEST index, so the greedily added probes must be sorted in front of
# it. With a mandatory low index the sort would be invisible.
withTopProbe, _ = selectProbeFrequencies(frequencies, curves, 3, alwaysInclude=[4])
check(
    "returned indices are sorted ascending with no duplicates",
    withTopProbe == sorted(withTopProbe) and len(withTopProbe) == len(set(withTopProbe)),
    f"got {withTopProbe}",
)
check(
    "every alwaysInclude index survives into the result",
    4 in withTopProbe,
    f"got {withTopProbe}",
)

noSelectionNeeded, _ = selectProbeFrequencies(frequencies, curves, 2, alwaysInclude=[2, 0])
check(
    "probeCount equal to len(alwaysInclude) does no selection and returns them sorted",
    noSelectionNeeded == [0, 2],
    f"got {noSelectionNeeded}",
)

allProbes, _ = selectProbeFrequencies(frequencies, curves, 10)
check(
    "probeCount above the frequency count stops early and returns all columns",
    allProbes == [0, 1, 2, 3, 4],
    f"got {allProbes}",
)

reportedIndices, reportedError = selectProbeFrequencies(frequencies, curves, 3)
check(
    "the reported error is the error of the indices it reported",
    abs(reportedError - reconstructionErrorForProbes(curves, reportedIndices)) < 1e-12,
    f"reported {reportedError} for {reportedIndices}",
)

predictor = CurvePredictor(frequencies, PROBE_INDICES)
returned = predictor.fit(curves)

check(
    "fit returns self so it can be chained",
    returned is predictor,
)
check(
    "populationMean is one value per frequency, not one per unit",
    np.shape(predictor.populationMean) == (len(frequencies),),
    f"got shape {np.shape(predictor.populationMean)}, expected ({len(frequencies)},)",
)
check(
    "populationMean equals the mean across units",
    np.shape(predictor.populationMean) == (len(frequencies),)
    and np.allclose(predictor.populationMean, curves.mean(axis=0)),
    f"got {predictor.populationMean}",
)

# One value per PROBE index, not per frequency. Ridge was fitted on len(PROBE_INDICES)
# features and raises on anything else.
probeValues = [0.10, 0.30, 0.50]
prediction = predictor.predict(probeValues)
check(
    "predict returns one value per frequency",
    np.shape(prediction) == (len(frequencies),),
    f"got shape {np.shape(prediction)}",
)

unblended = predictor.predict(probeValues, prior=None)
prior = np.array([2.00, 1.00, 0.50, 0.25, 0.125])

check(
    "priorWeight of 0.0 ignores the prior entirely",
    np.allclose(predictor.predict(probeValues, prior=prior, priorWeight=0.0), unblended),
)
check(
    "priorWeight of 1.0 returns the prior exactly",
    np.allclose(predictor.predict(probeValues, prior=prior, priorWeight=1.0), prior),
)
check(
    "priorWeight of 0.25 gives 0.75 * prediction + 0.25 * prior",
    np.allclose(
        predictor.predict(probeValues, prior=prior, priorWeight=0.25),
        0.75 * unblended + 0.25 * prior,
    ),
    f"got {predictor.predict(probeValues, prior=prior, priorWeight=0.25)}",
)

risingCurve = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
optimal = predictor.optimalFrequency(risingCurve)
check(
    "optimalFrequency returns the frequency at the curve's maximum, as a float",
    isinstance(optimal, float) and abs(optimal - 500.0) < 1e-9,
    f"got {optimal!r}",
)

regretCurve = np.array([1.5, 1.25, 1.0])
check(
    "choosing the curve's own maximum gives exactly zero regret",
    abs(regretPercent(regretCurve, 0) - 0.0) < 1e-12,
    f"got {regretPercent(regretCurve, 0)}",
)
check(
    "regret is in percentage points: 25.0 and 50.0, not 0.25 and 0.50",
    abs(regretPercent(regretCurve, 1) - 25.0) < 1e-9
    and abs(regretPercent(regretCurve, 2) - 50.0) < 1e-9,
    f"got {regretPercent(regretCurve, 1)} and {regretPercent(regretCurve, 2)}",
)

if failures:
    print(f"{len(failures)} check(s) failed.")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
