"""
Locate each workload's efficiency optimum precisely enough to ask whether the two DIFFER.

THE QUESTION
    The V100 analysis found a -0.666 correlation between a workload's frequency sensitivity and
    its optimal clock: bandwidth-bound work should prefer a LOWER optimum than compute-bound
    work. The coarse 13-point sweep put both gemm and membw at 1552 MHz, but with a 217 MHz grid
    step that means "indistinguishable", not "equal". This script exists to separate them, or to
    establish honestly that they cannot be separated on this hardware.

WHY NOT JUST TAKE THE ARGMAX, LIKE analyze_sweep.py DOES
    Because near its optimum an efficiency curve is flat by construction - that is what being an
    optimum means - and the argmax of a flat noisy curve is mostly noise.

    The numbers from the coarse run: gemm's peak stood 1.8% above the points +/-218 MHz on either
    side, while the SAME run contained a 0.6% non-monotonicity between 1987 and 2205 MHz that has
    no physical explanation and is simply run-to-run variation. At this fine sweep's ~58 MHz
    spacing, the true efficiency difference between adjacent points near the peak is smaller than
    that 0.6%. So the argmax of a single fine sweep would be close to a coin flip between several
    frequencies, and the difference between two coin flips is not a measurement.

    argmax also throws away almost all the data - 12 of 13 points contribute nothing to it.

WHAT THIS DOES INSTEAD
    1. Fits a smooth curve to the whole efficiency-vs-frequency relationship and takes its
       interior maximum. Every point constrains the fit, so independent per-point noise averages
       down instead of deciding the answer. This is why the band was widened to 1200-1900 MHz:
       a polynomial fit needs curvature to bite on, and across a tight band around the peak
       there is barely any.
    2. Uses TWO passes per workload. Replicates are what convert "these two numbers differ" into
       "these two optima differ" - without a measured noise floor there is no scale to judge a
       difference against. They also let the script report the argmax's own instability, which is
       the empirical justification for not using it.
    3. Bootstraps the vertex to get a confidence interval, then bootstraps the DIFFERENCE between
       the two workloads' vertices. If that interval contains zero, the honest answer is that
       this hardware and this method cannot separate them, and that is reported as the result
       rather than as a failure.

WHY A CUBIC AND NOT A PARABOLA
    An efficiency curve is not symmetric. It rises steeply from low clocks and falls gently past
    the peak, and a symmetric parabola fitted to a skewed curve puts its vertex on the shallow
    side of the true peak.

    That was measured, on synthetic curves with a known peak at 1550 MHz, this exact 13-point
    grid, two passes, and realistic 0.6% noise:

        skew    parabola vertex     cubic vertex
        0.0     1550 +/- 2          1550 +/- 5
        0.3     1564 +/- 2          1550 +/- 5
        0.6     1578 +/- 2          1550 +/- 5
        0.8     1587 +/- 2          1550 +/- 5

    The parabola is precise and wrong: up to +37 MHz of bias, with a confidence interval far too
    narrow to cover it. The cubic is unbiased at every skew level and pays 2.5x in random error,
    which is a trade worth making when the bias is an order of magnitude larger than the noise.

    It matters more than it looks, because a bias shared by both workloads would cancel in the
    difference and be harmless. This one does not: gemm and membw have differently-shaped curves,
    so they are skewed by different amounts. Feeding two curves with the SAME true optimum at
    1550 MHz and different skew (0.8 vs 0.0) into the parabola version of this script produced
    "+37 MHz, 95% CI +29 to +45, the optima do differ" - a false positive of exactly the size and
    direction the real effect is expected to have, stated with confidence. The cubic reports no
    difference on the same data, correctly.

    So: cubic is the estimator, the parabola is kept as a cross-check, and the gap between them
    is reported, because that gap IS the curve's asymmetry.

WHAT WOULD STILL MAKE THIS WRONG
    A cubic is also not the true functional form - it is just flexible enough to absorb the skew
    that mattered. If the real curve has structure a cubic cannot represent, the fit will be
    driven by shape rather than by peak location. The window-sensitivity check exists to show
    that: it refits over progressively narrower bands, and a vertex that wanders as the window
    changes is a vertex that should not be trusted.

USAGE
    python analysis/analyze_fine_sweep.py
    python analysis/analyze_fine_sweep.py --pattern "*fine-p*_sweep.csv" --bootstrap 5000
"""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
SWEEPS = REPO_ROOT / "data" / "frequency-sweeps"

# Same rule as analyze_sweep.py: a row whose clock cap was never applied cannot be attributed to
# a frequency. Honest undershoot is kept, because the card really did run there.
EXCLUDE_DIRECTIONS = {"above"}

# Frequencies are divided by this before fitting. A raw quadratic in MHz has terms spanning ~6
# orders of magnitude and the normal equations lose precision; centring and scaling costs nothing
# and the vertex is converted back to MHz afterwards.
FREQ_SCALE = 1000.0


def parseName(stem):
    """Pull workload and pass number out of e.g. '20260816-...._5060ti-gemm-fine-p2_sweep'."""
    match = re.search(r"-(gemm|membw)-fine-p(\d+)", stem)
    if not match:
        return None, None
    return match.group(1), int(match.group(2))


def loadSweep(path):
    rows = []
    with open(path, encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            if not raw.get("bench_throughput"):
                continue
            if raw.get("bench_ok") not in ("True", "true", None):
                continue
            if raw.get("lock_miss_direction") in EXCLUDE_DIRECTIONS:
                continue
            throughput = float(raw["bench_throughput"])
            power = float(raw["power_avg_w"])
            rows.append({
                "target": int(raw["target_frequency_mhz"]),
                "mhz": float(raw["achieved_frequency_avg"]),
                "throughput": throughput,
                "power": power,
                "efficiency": throughput / power,
                "windowed": raw.get("power_window_applied") in ("True", "true"),
                "temperature": float(raw.get("temperature_avg_c") or "nan"),
            })
    return sorted(rows, key=lambda r: r["mhz"])


def fitVertex(freqs, effs, degree=3):
    """Interior maximum of the least-squares polynomial, in MHz. None if there isn't one.

    degree=3 is the estimator (unbiased under curve skew); degree=2 is kept as a cross-check.
    """
    freqs = np.asarray(freqs, dtype=float)
    centre = float(np.mean(freqs))
    x = (freqs - centre) / FREQ_SCALE
    y = np.asarray(effs, dtype=float)
    coeffs = np.polyfit(x, y, degree)

    if degree == 2:
        a, b, _ = coeffs
        # Convex: the data has no interior maximum for a parabola to find. Reporting -b/2a here
        # would return the location of a MINIMUM and call it an optimum.
        if a >= 0:
            return None
        return float(centre + FREQ_SCALE * (-b / (2 * a)))

    a, b, c, _ = coeffs
    # Stationary points of the cubic: 3a.x^2 + 2b.x + c = 0.
    discriminant = 4 * b * b - 12 * a * c
    if discriminant < 0 or a == 0:
        return None
    root = np.sqrt(discriminant)
    stationary = [(-2 * b + root) / (6 * a), (-2 * b - root) / (6 * a)]
    # Keep maxima only (second derivative 6a.x + 2b < 0), and prefer one inside the measured
    # band. A cubic always has a maximum somewhere; one outside the swept range is an
    # extrapolation artefact, not a measurement, and must not be reported as an optimum.
    maxima = [r for r in stationary if 6 * a * r + 2 * b < 0]
    inBand = [r for r in maxima if x.min() <= r <= x.max()]
    if not inBand:
        return None
    return float(centre + FREQ_SCALE * inBand[0])


def normalisePerPass(rowsByPass):
    """Divide each pass by its own mean efficiency before pooling the passes together.

    Two passes of the same workload can sit at slightly different absolute efficiency - the card
    is warmer on the later one, background load differs. That is a LEVEL difference and it says
    nothing about where the peak is, but pooling unnormalised passes into one fit lets it tilt
    the fit and move the vertex. Dividing each pass by its own mean removes the level while
    leaving the shape, which is the only part being measured.
    """
    pooled = []
    for rows in rowsByPass.values():
        mean = float(np.mean([r["efficiency"] for r in rows]))
        for row in rows:
            pooled.append((row["mhz"], row["efficiency"] / mean))
    return pooled


def bootstrapVertices(pooled, draws, rng, degree=3):
    """Residual bootstrap of the vertex position.

    Resampling residuals rather than points keeps the frequency grid fixed, which is right here:
    the frequencies were chosen by design and are not a random sample of anything. What IS random
    is the measurement error at each one, and that is what gets resampled.

    Returns (vertices, failureRate). Draws that produce no interior maximum are dropped, and the
    rate is returned rather than swallowed: if a large share of resamples cannot find a peak at
    all, the interval computed from the rest is conditional on succeeding and overstates how well
    the optimum is pinned down.
    """
    freqs = np.array([p[0] for p in pooled])
    effs = np.array([p[1] for p in pooled])
    x = (freqs - freqs.mean()) / FREQ_SCALE
    fitted = np.polyval(np.polyfit(x, effs, degree), x)
    residuals = effs - fitted

    vertices = []
    for _ in range(draws):
        resampled = fitted + rng.choice(residuals, size=len(residuals), replace=True)
        vertex = fitVertex(freqs, resampled, degree=degree)
        if vertex is not None:
            vertices.append(vertex)
    return np.array(vertices), 1.0 - (len(vertices) / draws if draws else 0.0)


def reportRepeatability(name, rowsByPass):
    """How much does the same measurement move between passes? This sets the scale for everything."""
    byTarget = defaultdict(dict)
    for passNo, rows in rowsByPass.items():
        for row in rows:
            byTarget[row["target"]][passNo] = row

    diffs, argmaxes = [], []
    for passNo, rows in sorted(rowsByPass.items()):
        best = max(rows, key=lambda r: r["efficiency"])
        argmaxes.append((passNo, best["mhz"]))

    for target, passes in sorted(byTarget.items()):
        if len(passes) < 2:
            continue
        values = [p["efficiency"] for p in passes.values()]
        diffs.append(200.0 * abs(values[0] - values[1]) / (values[0] + values[1]))

    if diffs:
        print(f"  repeatability    : {len(diffs)} frequencies measured twice; "
              f"median |pass1-pass2| = {np.median(diffs):.2f}%, worst {max(diffs):.2f}%")
    else:
        print("  repeatability    : no frequency measured twice - cannot estimate noise.")
    shown = ", ".join(f"pass {p}: {m:.0f} MHz" for p, m in argmaxes)
    print(f"  raw argmax       : {shown}")
    if len({round(m) for _, m in argmaxes}) > 1:
        spread = max(m for _, m in argmaxes) - min(m for _, m in argmaxes)
        print(f"                     the argmax moved {spread:.0f} MHz between identical passes, "
              f"which is why the fit is used instead.")
    return np.median(diffs) if diffs else None


def windowSensitivity(pooled):
    """Refit after dropping the outermost frequencies. A vertex that moves is a vertex driven by
    curve shape rather than by peak location, and the printout should say so."""
    ordered = sorted(pooled)
    freqs = sorted({p[0] for p in ordered})
    results = []
    for trim in (0, 1, 2):
        if len(freqs) - 2 * trim < 5:
            break
        low, high = freqs[trim], freqs[len(freqs) - 1 - trim]
        subset = [p for p in ordered if low <= p[0] <= high]
        vertex = fitVertex([p[0] for p in subset], [p[1] for p in subset])
        results.append((trim, low, high, vertex))
    return results


def analyseWorkload(name, rowsByPass, draws, rng):
    print(f"=== {name} ===")
    total = sum(len(r) for r in rowsByPass.values())
    print(f"  passes           : {len(rowsByPass)} ({total} points total)")

    noise = reportRepeatability(name, rowsByPass)
    pooled = normalisePerPass(rowsByPass)

    freqs = [p[0] for p in pooled]
    effs = [p[1] for p in pooled]

    vertex = fitVertex(freqs, effs, degree=3)
    if vertex is None:
        print("  FIT FAILED: no interior maximum inside the swept band.")
        print("  The band is probably on one flank of the peak rather than spanning it.\n")
        return None

    samples, failureRate = bootstrapVertices(pooled, draws, rng, degree=3)
    low, high = np.percentile(samples, [2.5, 97.5])
    print(f"  fitted optimum   : {vertex:.0f} MHz   (95% CI {low:.0f} - {high:.0f} MHz)   [cubic]")
    if failureRate > 0.02:
        print(f"  NOTE: {100*failureRate:.0f}% of bootstrap resamples found no interior peak, so the")
        print("  interval above is conditional on finding one and is narrower than the truth.")

    # The parabola is biased by curve skew (see the header). The gap between the two fits is a
    # direct read on how asymmetric this workload's curve is - not a disagreement to resolve.
    quadratic = fitVertex(freqs, effs, degree=2)
    if quadratic is not None:
        print(f"  parabola says    : {quadratic:.0f} MHz  ({quadratic - vertex:+.0f} MHz) "
              f"- skew indicator, biased; the cubic is the estimate")

    for trim, lowF, highF, alt in windowSensitivity(pooled):
        if alt is None:
            print(f"  window {lowF:.0f}-{highF:.0f} MHz: no interior peak")
        else:
            note = "" if trim == 0 else f"  ({alt - vertex:+.0f} MHz vs full band)"
            print(f"  window {lowF:.0f}-{highF:.0f} MHz: vertex {alt:.0f} MHz{note}")

    if not all(r["windowed"] for rows in rowsByPass.values() for r in rows):
        print("  WARNING: some points lack power windowing - their power is diluted by CUDA init.")
    print()
    return {"name": name, "vertex": vertex, "samples": samples, "noise": noise}


def compare(first, second, rng):
    """Bootstrap the difference between two vertices.

    The two workloads were measured in separate sweeps, so their errors are independent and the
    bootstrap draws are combined independently. The counterbalanced run order (gemm, membw,
    membw, gemm) is what makes that defensible - it keeps thermal drift from loading onto one
    workload and appearing here as a real difference.
    """
    print("=== does the optimum differ between workloads? ===")
    size = min(len(first["samples"]), len(second["samples"]))
    if size == 0:
        print("  Not enough successful bootstrap fits to compare.")
        return

    left = rng.choice(first["samples"], size=size, replace=True)
    right = rng.choice(second["samples"], size=size, replace=True)
    diff = left - right
    low, high = np.percentile(diff, [2.5, 97.5])
    point = first["vertex"] - second["vertex"]

    print(f"  {first['name']} optimum minus {second['name']} optimum:")
    print(f"    {point:+.0f} MHz   (95% CI {low:+.0f} to {high:+.0f} MHz)")

    if low <= 0 <= high:
        print("  The interval contains zero. These two optima are NOT distinguishable by this")
        print("  measurement. That is a result, not a failure: it bounds how large any real")
        print(f"  difference can be at roughly +/-{max(abs(low), abs(high)):.0f} MHz.")
        print("  The V100's -0.666 correlation predicts a nonzero difference, so this neither")
        print("  confirms nor refutes it - it says this hardware cannot resolve it at this scale.")
    else:
        # Work out which side is the bandwidth-bound workload rather than assuming an order.
        # Getting this backwards would report the V100's prediction as confirmed when the data
        # contradicts it, which is the one error here that could not be caught by reading the
        # number alone.
        if "membw" in first["name"]:
            membwLower = point < 0
        elif "membw" in second["name"]:
            membwLower = point > 0
        else:
            membwLower = None

        if membwLower is None:
            print("  The interval excludes zero: the two optima do differ.")
        else:
            direction = "LOWER" if membwLower else "HIGHER"
            print("  The interval excludes zero: the optima do differ, with the bandwidth-bound")
            print(f"  workload preferring a {direction} clock.")

        # The V100 predicts bandwidth-bound work optimises at a lower clock. Name the prediction
        # and whether it held, rather than reporting a bare sign.
        if membwLower is True:
            print("  This matches the direction the V100 dataset predicts (-0.666 correlation")
            print("  between frequency sensitivity and optimal clock).")
        elif membwLower is False:
            print("  This is the OPPOSITE of the direction the V100 dataset predicts. Report it")
            print("  as measured; a contradicted prediction is worth more than a quiet one.")
            print()
            print("  BEFORE CALLING THE CORRELATION REFUTED, check the premise. That correlation is")
            print("  computed over performance RETAINED at the lowest frequency swept, and its")
            print("  memory-bound class means >=90% retained. A kernel that is issue-limited rather")
            print("  than bandwidth-saturated does not belong to that class, and a prediction tested")
            print("  outside its domain has not been tested. Check retention at the same RELATIVE")
            print("  floor before concluding anything about the correlation itself:")
            print("      python analysis/characterize.py     # how the V100 side classifies workloads")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--pattern", default="*fine-p*_sweep.csv")
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument(
        "--exclude", default="", metavar="workload:pass:targetMhz,...",
        help="Drop specific measured points, e.g. 'gemm:1:1725,gemm:1:1785'. Excluding points "
             "AFTER seeing the result is how a finding gets manufactured, so every exclusion is "
             "echoed to stdout and each one needs a reason recorded in "
             "data/frequency-sweeps/README.md that does not depend on the conclusion.")
    args = parser.parse_args()

    excluded = set()
    for item in filter(None, (piece.strip() for piece in args.exclude.split(","))):
        try:
            workload, passNo, target = item.split(":")
            excluded.add((workload, int(passNo), int(target)))
        except ValueError:
            print(f"Could not parse --exclude entry {item!r}; expected workload:pass:targetMhz")
            return 1

    paths = sorted(SWEEPS.glob(args.pattern))
    if not paths:
        print(f"No sweeps matching {args.pattern} under {SWEEPS}")
        return 1

    grouped = defaultdict(dict)
    for path in paths:
        workload, passNo = parseName(path.stem)
        if workload is None:
            print(f"  skipping {path.name}: not a recognised fine-sweep filename")
            continue
        rows = loadSweep(path)
        if excluded:
            kept = [r for r in rows if (workload, passNo, r["target"]) not in excluded]
            for row in rows:
                if row not in kept:
                    print(f"  EXCLUDED {workload} pass {passNo} at {row['target']} MHz "
                          f"(by --exclude; reason must be recorded in the data README)")
            rows = kept
        grouped[workload][passNo] = rows

    rng = np.random.default_rng(args.seed)
    summaries = []
    for workload in ("gemm", "membw"):
        if workload not in grouped:
            continue
        # An unbalanced set breaks the counterbalancing the comparison depends on. Say so rather
        # than analysing it as though the design had been met.
        if len(grouped[workload]) < 2:
            print(f"=== {workload} ===")
            print(f"  Only {len(grouped[workload])} pass present. Without a replicate there is no")
            print("  noise estimate, and no basis for calling any difference real.\n")
        summary = analyseWorkload(workload, grouped[workload], args.bootstrap, rng)
        if summary:
            summaries.append(summary)

    if len(summaries) == 2:
        compare(summaries[0], summaries[1], rng)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
