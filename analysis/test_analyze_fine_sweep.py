"""Does analyze_fine_sweep.py find differences that exist, and refuse ones that don't?

WHY THIS FILE EXISTS
    analyze_fine_sweep.py answers a question no measurement in this repo can check by eye: are
    two efficiency optima at different frequencies? Its output is a confident-looking sentence
    either way, so "it ran and printed something plausible" is not evidence it works. The only
    way to know is to feed it curves whose optima are known by construction.

    That is not hypothetical caution. The first version of the script fitted a parabola, passed
    every test with symmetric curves, and produced "+37 MHz, 95% CI +29 to +45, the optima do
    differ" on two curves with the SAME optimum at 1550 MHz and different skew - a false positive
    of exactly the size and direction the real effect was expected to have. It was caught here,
    by this test, and not by reading the code. Hence the cubic fit, and hence this file.

RUN
    python analysis/test_analyze_fine_sweep.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_fine_sweep import bootstrapVertices, fitVertex  # noqa: E402

# The real grid: 13 points, 1200-1900 MHz, as swept by Invoke-FrequencySweep.ps1.
GRID = np.array([1200, 1260, 1320, 1372, 1432, 1492, 1545, 1605, 1665, 1725, 1785, 1837, 1897],
                dtype=float)

# 0.6% per-point scatter, taken from the coarse sweep's unexplained 0.6% non-monotonicity
# between 1987 and 2205 MHz - i.e. measured on this hardware, not assumed.
NOISE = 0.006


def makeCurve(vertex, skew, rng, passes=2, noise=NOISE):
    """Efficiency curve peaking exactly at `vertex`, skewed by `skew`, sampled `passes` times."""
    freqs = np.tile(GRID, passes)
    u = (freqs - vertex) / 900.0
    effs = (1.0 - u ** 2 + skew * u ** 3) * (1.0 + rng.normal(0, noise, size=freqs.size))
    return list(zip(freqs, effs))


def difference(pooledA, pooledB, rng, draws=3000):
    """Same comparison analyze_fine_sweep.py makes: bootstrap CI on the vertex difference."""
    left, _ = bootstrapVertices(pooledA, draws, rng)
    right, _ = bootstrapVertices(pooledB, draws, rng)
    size = min(len(left), len(right))
    diff = rng.choice(left, size, replace=True) - rng.choice(right, size, replace=True)
    return np.percentile(diff, [2.5, 97.5])


def check(label, expectation, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}: {expectation}")
    return condition


def main():
    rng = np.random.default_rng(20260816)
    ok = True

    print("Vertex recovery (400 trials each) - is the estimator unbiased under curve skew?")
    print(f"  {'skew':>5} {'parabola':>18} {'cubic':>18}   true = 1550 MHz")
    for skew in (0.0, 0.3, 0.6, 0.8):
        quad, cubic = [], []
        for trial in range(400):
            trialRng = np.random.default_rng(trial)
            pooled = makeCurve(1550.0, skew, trialRng)
            freqs = [p[0] for p in pooled]
            effs = [p[1] for p in pooled]
            for degree, bucket in ((2, quad), (3, cubic)):
                found = fitVertex(freqs, effs, degree=degree)
                if found is not None:
                    bucket.append(found)
        quad, cubic = np.array(quad), np.array(cubic)
        print(f"  {skew:>5} {quad.mean():>8.0f} +/-{quad.std():<6.0f} "
              f"{cubic.mean():>8.0f} +/-{cubic.std():<6.0f}")
        # The cubic must stay unbiased; the parabola is expected to fail here and is only
        # measured so the size of the bias it would have introduced stays on the record.
        ok &= check(f"skew {skew}", "cubic bias < 8 MHz", abs(cubic.mean() - 1550.0) < 8)

    print("\nDifference test - detects real differences, refuses fake ones:")

    cases = [
        # label,                        gemm vertex, membw vertex, gemm skew, membw skew, expect
        ("large real difference",       1600, 1450, 0.0, 0.0, True),
        ("small real difference",       1585, 1520, 0.0, 0.0, True),
        ("no difference",               1550, 1550, 0.0, 0.0, False),
        ("equal vertices, equal skew",  1550, 1550, 0.5, 0.5, False),
        # The case that broke the parabola version. Different curve SHAPES, same optimum.
        ("equal vertices, DIFFERENT skew", 1550, 1550, 0.8, 0.0, False),
    ]

    for label, vertexA, vertexB, skewA, skewB, shouldDiffer in cases:
        caseRng = np.random.default_rng(11)
        pooledA = makeCurve(float(vertexA), skewA, caseRng)
        pooledB = makeCurve(float(vertexB), skewB, caseRng)
        low, high = difference(pooledA, pooledB, caseRng)
        declared = not (low <= 0 <= high)
        truth = vertexA - vertexB
        verdict = "differ" if declared else "not distinguishable"
        print(f"  {label:<32} true {truth:+4d} MHz -> CI [{low:+6.0f}, {high:+6.0f}] {verdict}")
        ok &= check(label, f"should say {'differ' if shouldDiffer else 'not distinguishable'}",
                    declared == shouldDiffer)

    print("\nExtrapolation guard - a peak outside the swept band is not a measurement:")
    guardRng = np.random.default_rng(3)
    # True optimum 700 MHz below the band. The band lies entirely on one flank, so there is no
    # interior maximum and the honest answer is None, not the edge of the grid.
    offBand = makeCurve(500.0, 0.0, guardRng)
    found = fitVertex([p[0] for p in offBand], [p[1] for p in offBand], degree=3)
    ok &= check("optimum far below band", "returns None rather than a made-up vertex", found is None)

    print("\n" + ("ALL CHECKS PASSED" if ok else "*** SOME CHECKS FAILED ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
