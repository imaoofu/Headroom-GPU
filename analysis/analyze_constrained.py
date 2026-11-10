"""
Performance-constrained efficiency optima: the question users actually have.

WHY THIS IS A DIFFERENT QUESTION
    `characterize.py` reports the UNCONSTRAINED optimum - the frequency with the best
    performance-per-watt, whatever it costs. On the V100 dataset that is a 44.4% mean
    efficiency gain, and it costs a mean 13.7% performance. Almost nobody wants that
    trade. The question people actually ask is "how much power can I save while keeping
    essentially all of my performance", which is a constrained optimisation:

        maximise   efficiency(f)
        subject to performance(f) >= floor x performance(stock)

    This script answers it across a range of floors, so the shape of the trade-off is
    visible rather than one arbitrary threshold being picked.

WHY THE COMPARISON MATTERS
    GEEPAFS [6] - the EuroSys '24 paper the V100 dataset was published with - reports
    26.7% mean efficiency gain for 5.8% mean performance loss on this same chip. That is
    the correct benchmark for a constrained result, and it is a much harder bar than the
    unconstrained 44.4%.

    It is NOT an apples-to-apples race, and the output says so. GEEPAFS is an ONLINE
    policy: it picks frequencies live, without profiling the application first. This
    script is an offline ORACLE - it sees the whole measured curve for every workload and
    picks the best point with hindsight. An oracle SHOULD beat an online policy. If it
    only ties, that is a poor result for the oracle, not a tie.

STRUCTURE, AND WHY IT IS CHECKED RATHER THAN ASSUMED
    Efficiency curves are single-peaked and performance rises monotonically with clock.
    If both hold, the constrained optimum has a closed form: max(unconstrained optimum,
    lowest feasible frequency). That shortcut is NOT used to compute the answer - the
    answer is brute-forced over the feasible set - but it IS computed alongside and
    compared, because a disagreement means one of those two assumptions fails in the real
    data, and that is worth knowing rather than silently averaging over.

GRID COARSENESS
    The V100 dataset has 13 frequencies; the sweeps have 13 points. The constrained
    optimum is therefore a grid point, and realised performance usually OVERSHOOTS the
    floor rather than landing on it. Realised performance is reported next to every floor
    for that reason. All savings here are a LOWER BOUND on what a continuous knob would
    reach.

THE 100% FLOOR IS A SOFT BOUNDARY, NOT A HARD ONE
    A floor of 100% ought to return the reference frequency and a 0% gain. It does not,
    and the reason is real rather than a coding error: 4 of the 33 V100 workloads record
    performance ABOVE their own 1530 MHz value at some lower frequency - FDTD, CNN_1.5M,
    CNN_1.8M and RL-PPO, by +0.62 to +1.44 percentage points. Those are memory-bound
    workloads whose performance curve is FLAT across the top of the range, which is
    exactly why they are the ones with the most efficiency headroom.

    Both readings are defensible and the output does not pick one. Either the flat top is
    genuine, in which case those workloads really do give up nothing by downclocking, or a
    1% excess is measurement noise in a dataset that averaged 5 repeats. Under the second
    reading a 100% floor is unresolvable, because the constraint is being applied at finer
    resolution than the data can support. The 100% and 99% rows are therefore annotated,
    and no headline number should be quoted from them. The 95% and 90% rows are clear of
    the noise band and are the ones to cite.

USAGE
    python analysis/analyze_constrained.py
    python analysis/analyze_constrained.py --floors 0.99 0.95 0.90
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
SWEEPS = REPO_ROOT / "data" / "frequency-sweeps"

sys.path.insert(0, str(REPO_ROOT / "analysis"))

# Floors to report. 1.00 means "give up nothing", which must return the reference
# frequency and a 0% gain - a built-in sanity check visible in every run.
DEFAULT_FLOORS = [1.00, 0.99, 0.95, 0.90, 0.85, 0.80]

# GEEPAFS [6], EuroSys '24, on the same V100: mean efficiency gain and mean performance
# loss of their online policy. Used only for context, never as a target to beat.
GEEPAFS_EFFICIENCY_GAIN_PCT = 26.7
GEEPAFS_PERFORMANCE_LOSS_PCT = 5.8

# Sweep rows locked ABOVE their target are excluded, matching analyze_sweep.py.
EXCLUDE_DIRECTIONS = {"above"}

# Performance differences below this are not resolvable in either dataset: the V100 CSVs
# are published to 4 decimals from 5 averaged repeats, and the sweeps repeat to ~1.7-2.6%
# between passes. A floor whose slack is thinner than this is being applied at finer
# resolution than the measurement supports.
NOISE_BAND_PCT = 1.0

# Sweep points closer together than this are the same operating condition measured twice,
# not distinct grid points - the card clamps every target above its ceiling to one clock.
DUPLICATE_FREQUENCY_MHZ = 10.0


def buildPoints(frequencies, performance, power, achieved=None):
    """
    Normalise one workload's curve against its highest frequency.

    The reference is the fastest point measured, not a nameplate clock: for the V100 that
    is 1530 MHz (its stock boost, and the dataset's own normalisation reference), and for
    a sweep it is the sustained maximum the card actually held. A nameplate denominator
    would compare against a frequency the hardware never ran.
    """
    order = np.argsort(frequencies)
    frequencies = np.asarray(frequencies, dtype=float)[order]
    performance = np.asarray(performance, dtype=float)[order]
    power = np.asarray(power, dtype=float)[order]
    # Carried, not used in any calculation. On a COMMANDED-basis curve `mhz` is the target that
    # was set and this is what the card actually held, which differs per workload and is the
    # whole reason the commanded basis exists. Reported so a reader can see the spread rather
    # than assume the policy delivered its number.
    achieved = np.asarray(achieved, dtype=float)[order] if achieved is not None else None

    referenceIndex = len(frequencies) - 1
    referencePerformance = performance[referenceIndex]
    referencePower = power[referenceIndex]
    referenceEfficiency = referencePerformance / referencePower

    points = []
    for index in range(len(frequencies)):
        efficiency = performance[index] / power[index]
        point = {
            "mhz": float(frequencies[index]),
            "perf": float(performance[index] / referencePerformance),
            "power": float(power[index]),
            "power_rel": float(power[index] / referencePower),
            "eff": float(efficiency / referenceEfficiency),
        }
        if achieved is not None:
            point["achieved_mhz"] = float(achieved[index])
        points.append(point)
    return points


def constrainedOptimum(points, floor):
    """
    Best efficiency among points meeting the performance floor. Brute force, on purpose.

    Returns None only if nothing is feasible, which cannot happen for floor <= 1.0 since
    the reference point has perf == 1.0 exactly.
    """
    feasible = [p for p in points if p["perf"] >= floor - 1e-9]
    if not feasible:
        return None
    return max(feasible, key=lambda p: p["eff"])


def structuralPrediction(points, floor):
    """
    What the closed form predicts: max(unconstrained optimum, lowest feasible frequency).

    Valid only if efficiency is single-peaked AND performance is monotonic in frequency.
    Computed to be COMPARED against the brute-force answer, never to replace it.
    """
    feasible = [p for p in points if p["perf"] >= floor - 1e-9]
    if not feasible:
        return None
    unconstrained = max(points, key=lambda p: p["eff"])
    lowestFeasible = min(feasible, key=lambda p: p["mhz"])
    return unconstrained if unconstrained["mhz"] >= lowestFeasible["mhz"] else lowestFeasible


def monotonicPerformanceViolations(points):
    """Frequencies where performance FALLS as clock rises. Measurement noise, usually."""
    violations = []
    for earlier, later in zip(points, points[1:]):
        if later["perf"] < earlier["perf"] - 1e-9:
            violations.append((earlier["mhz"], later["mhz"],
                               (later["perf"] - earlier["perf"]) * 100.0))
    return violations


def singlePeakViolations(points):
    """Local maxima in efficiency beyond the first. A second bump breaks the closed form."""
    efficiencies = [p["eff"] for p in points]
    peaks = []
    for index in range(len(efficiencies)):
        leftLower = index == 0 or efficiencies[index - 1] < efficiencies[index]
        rightLower = index == len(efficiencies) - 1 or efficiencies[index + 1] < efficiencies[index]
        if leftLower and rightLower:
            peaks.append(points[index]["mhz"])
    return peaks[1:] if len(peaks) > 1 else []


def analyseCurves(curves, floors):
    """curves: {name: points}. Returns per-floor aggregate rows plus assumption diagnostics."""
    rows = []
    disagreements = []
    for floor in floors:
        gains, losses, saved, chosen = [], [], [], []
        moved = 0
        for name, points in curves.items():
            best = constrainedOptimum(points, floor)
            if best is None:
                continue
            predicted = structuralPrediction(points, floor)
            if predicted is not None and abs(predicted["mhz"] - best["mhz"]) > 1e-6:
                disagreements.append((name, floor, best["mhz"], predicted["mhz"]))
            referenceMhz = max(p["mhz"] for p in points)
            if best["mhz"] < referenceMhz - DUPLICATE_FREQUENCY_MHZ:
                moved += 1
            gains.append((best["eff"] - 1.0) * 100.0)
            losses.append((1.0 - best["perf"]) * 100.0)
            saved.append((1.0 - best["power_rel"]) * 100.0)
            chosen.append(best["mhz"])
        if not gains:
            continue
        rows.append({
            "floor": floor,
            "n": len(gains),
            "moved": moved,
            "noise_sensitive": floor >= 1.0 - NOISE_BAND_PCT / 100.0,
            "gain_mean": float(np.mean(gains)),
            "gain_median": float(np.median(gains)),
            "gain_min": float(np.min(gains)),
            "gain_max": float(np.max(gains)),
            "loss_mean": float(np.mean(losses)),
            "loss_max": float(np.max(losses)),
            "power_saved_mean": float(np.mean(saved)),
            "freq_median": float(np.median(chosen)),
        })
    return rows, disagreements


def bestFixedFrequency(curves, floor):
    """
    Best SINGLE frequency that satisfies the floor for every curve. Returns (mhz, meanEff).

    This is the baseline §5.2's null was measured against, and applying it under a constraint
    is what makes the constrained result meaningful. A policy that promises "you keep 95% of
    your performance" must keep that promise on every workload it might meet, so it cannot
    pick a frequency that is fine on average - it is pinned by the most frequency-sensitive
    workload in the set. That is the entire mechanism.

    Returns None when the curves share no common frequency grid, which is not a failure but a
    real limitation: two sweeps whose achieved clocks differ cannot be served by one policy
    frequency in any meaningful sense, and pretending otherwise would invent a comparison.
    """
    if not curves:
        return None
    grids = [set(round(p["mhz"], 3) for p in points) for points in curves.values()]
    shared = set.intersection(*grids)
    if not shared:
        return None

    best = None
    for frequency in sorted(shared):
        efficiencies = []
        for points in curves.values():
            point = next(p for p in points if round(p["mhz"], 3) == frequency)
            if point["perf"] < floor - 1e-9:
                efficiencies = None
                break
            efficiencies.append(point["eff"])
        if efficiencies is None:
            continue
        mean = sum(efficiencies) / len(efficiencies)
        if best is None or mean > best[1]:
            best = (frequency, mean)
    return best


def bindingCurve(curves, floor):
    """Which curve forces the fixed policy upward: the one with the highest floor of its own."""
    lowest = {}
    for name, points in curves.items():
        feasible = [p["mhz"] for p in points if p["perf"] >= floor - 1e-9]
        if feasible:
            lowest[name] = min(feasible)
    if not lowest:
        return None
    name = max(lowest, key=lambda k: lowest[k])
    return name, lowest[name], lowest


def reportFixedVersusPerWorkload(curves, floors):
    """The comparison that decides whether knowing the workload is worth anything."""
    print("=== per-workload selection vs one fixed frequency ===")
    print("  A fixed-frequency policy must hold its guarantee on EVERY workload, so it is")
    # ASCII only in printed output: the Windows console is cp1252 and mangles anything else.
    print("  pinned by the most frequency-sensitive one. This is the 5.2 baseline, applied")
    print("  under a constraint.")
    print()
    probe = bestFixedFrequency(curves, 0.0)
    if probe is None:
        print("  The curves share no common frequency grid, so no single policy frequency")
        print("  exists to evaluate. This is a property of the data, not a missing feature:")
        print("  each sweep achieved its own clocks. Aligning targets across workloads in a")
        print("  future sweep would make this comparison available on consumer hardware.")
        print()
        return []

    print(f"{'floor':>7}{'per-workload':>14}{'best fixed':>12}{'at':>9}{'gap':>10}{'share':>9}")
    rows = []
    for floor in floors:
        perWorkload = []
        for points in curves.values():
            best = constrainedOptimum(points, floor)
            if best is not None:
                perWorkload.append(best["eff"])
        fixed = bestFixedFrequency(curves, floor)
        if not perWorkload or fixed is None:
            print(f"{floor * 100:6.0f}%   no frequency is feasible for every workload")
            continue
        perMean = sum(perWorkload) / len(perWorkload)
        gainPer = (perMean - 1.0) * 100.0
        gainFixed = (fixed[1] - 1.0) * 100.0
        gap = gainPer - gainFixed
        share = (gap / gainPer * 100.0) if gainPer > 1e-9 else 0.0
        rows.append({"floor": floor, "per_workload_pct": gainPer, "fixed_pct": gainFixed,
                     "fixed_mhz": fixed[0], "gap_pp": gap, "share_pct": share})
        print(f"{floor * 100:6.0f}%{gainPer:>13.1f}%{gainFixed:>11.1f}%{fixed[0]:>9.0f}"
              f"{gap:>9.1f}pp{share:>8.0f}%")

    print("  'gap' = what knowing the workload is worth. 'share' = that gap as a fraction of")
    print("  all gain available at that floor.")

    # Tightest floor = HIGHEST fraction. 0.95 constrains harder than 0.80, so this is max().
    tightest = max((f for f in floors if f < 1.0 - NOISE_BAND_PCT / 100.0), default=None)
    if tightest is not None:
        binding = bindingCurve(curves, tightest)
        if binding:
            name, mhz, lowest = binding
            relaxed = sorted(lowest.items(), key=lambda kv: kv[1])[:3]
            print()
            print(f"  At a {tightest * 100:.0f}% floor the policy is pinned at {mhz:.0f} MHz by "
                  f"{name}.")
            print(f"  Least demanding: " +
                  ", ".join(f"{n} ({f:.0f} MHz)" for n, f in relaxed))
    print()
    return rows


def printFloorTable(title, rows):
    print(f"=== {title} ===")
    print(f"{'floor':>7}{'moved':>8}{'eff gain':>10}{'median':>9}{'range':>16}"
          f"{'perf lost':>11}{'worst':>8}{'power saved':>13}{'median MHz':>12}")
    flagged = False
    for row in rows:
        rangeText = f"{row['gain_min']:.1f} to {row['gain_max']:.1f}"
        marker = " (*)" if row["noise_sensitive"] else ""
        movedText = f"{row['moved']}/{row['n']}"
        print(f"{row['floor'] * 100:6.0f}%{movedText:>8}{row['gain_mean']:>9.1f}%"
              f"{row['gain_median']:>8.1f}%{rangeText:>16}"
              f"{row['loss_mean']:>10.1f}%{row['loss_max']:>7.1f}%"
              f"{row['power_saved_mean']:>12.1f}%{row['freq_median']:>12.0f}{marker}")
        flagged = flagged or row["noise_sensitive"]
    if flagged:
        print(f"  (*) floor sits within the {NOISE_BAND_PCT:.0f}% noise band - the constraint is")
        print("      finer than the data resolves. Do not quote a headline number from these rows.")
    print("  'moved' = curves that chose a frequency below the reference at all.")
    print()


def nearDuplicateFrequencies(points):
    """Grid points close enough to be the same operating condition measured twice."""
    pairs = []
    for earlier, later in zip(points, points[1:]):
        if later["mhz"] - earlier["mhz"] < DUPLICATE_FREQUENCY_MHZ:
            pairs.append((earlier["mhz"], later["mhz"]))
    return pairs


def flatTopCurves(curves):
    """Curves whose best performance beats the reference - a flat or noisy top of range."""
    found = {}
    for name, points in curves.items():
        best = max(points, key=lambda p: p["perf"])
        if best["perf"] > 1.0 + 1e-9:
            found[name] = ((best["perf"] - 1.0) * 100.0, best["mhz"])
    return found


def reportAssumptions(curves, disagreements):
    print("=== assumption checks ===")

    flatTop = flatTopCurves(curves)
    if flatTop:
        worst = max(v[0] for v in flatTop.values())
        print(f"  performance peaks AT the reference: NO - {len(flatTop)}/{len(curves)} curves "
              f"beat it below max clock, by up to {worst:.2f} pp")
        for name, (excess, mhz) in sorted(flatTop.items(), key=lambda kv: -kv[1][0])[:4]:
            print(f"      {name}: +{excess:.2f} pp at {mhz:.0f} MHz")
        print("      These drive the 100% floor. Either their curve is genuinely flat across")
        print("      the top - the most interesting reading - or the excess is noise. The data")
        print("      cannot separate those, so neither is asserted.")

    duplicates = {n: nearDuplicateFrequencies(p) for n, p in curves.items()}
    duplicates = {n: v for n, v in duplicates.items() if v}
    if duplicates:
        total = sum(len(v) for v in duplicates.values())
        print(f"  distinct grid points              : NO - {total} pair(s) within "
              f"{DUPLICATE_FREQUENCY_MHZ:.0f} MHz")
        for name, pairs in list(duplicates.items())[:3]:
            shown = ", ".join(f"{a:.0f}/{b:.0f}" for a, b in pairs[:3])
            print(f"      {name}: {shown} MHz - the card clamped several targets to one clock")
        print("      Repeat measurements of one condition, not independent points. Any closed-form")
        print("      disagreement of a few MHz between them is bookkeeping, not a real difference.")

    monotonic = {name: monotonicPerformanceViolations(points) for name, points in curves.items()}
    multiPeak = {name: singlePeakViolations(points) for name, points in curves.items()}
    brokenMonotonic = {k: v for k, v in monotonic.items() if v}
    brokenPeak = {k: v for k, v in multiPeak.items() if v}

    if brokenMonotonic:
        worst = min(min(v[2] for v in violations) for violations in brokenMonotonic.values())
        print(f"  performance monotonic in clock : NO - {len(brokenMonotonic)}/{len(curves)} "
              f"curves dip, worst {worst:.2f} percentage points")
    else:
        print(f"  performance monotonic in clock : yes, all {len(curves)} curves")

    if brokenPeak:
        print(f"  efficiency single-peaked       : NO - {len(brokenPeak)}/{len(curves)} curves "
              f"have a second local maximum")
        for name, peaks in list(brokenPeak.items())[:4]:
            print(f"      {name}: extra peak(s) at {', '.join(f'{p:.0f}' for p in peaks)} MHz")
    else:
        print(f"  efficiency single-peaked       : yes, all {len(curves)} curves")

    if disagreements:
        print(f"  closed form matches brute force: NO - {len(disagreements)} disagreements")
        for name, floor, actual, predicted in disagreements[:5]:
            print(f"      {name} at {floor * 100:.0f}%: brute force {actual:.0f} MHz, "
                  f"closed form {predicted:.0f} MHz")
        print("      The BRUTE FORCE answer is the one reported. The closed form is only a check.")
    else:
        print("  closed form matches brute force: yes, everywhere - the curves behave as assumed")
    print()


def compareToGeepafs(rows):
    """Place the oracle beside the published online policy WITHOUT declaring a winner."""
    print("=== against GEEPAFS (EuroSys '24, same V100) ===")
    print(f"  GEEPAFS, online policy : {GEEPAFS_EFFICIENCY_GAIN_PCT}% efficiency gain "
          f"for {GEEPAFS_PERFORMANCE_LOSS_PCT}% performance loss")

    # Find the floor whose realised mean loss is closest to what GEEPAFS actually spent.
    usable = [r for r in rows if not r["noise_sensitive"]]
    if not usable:
        print("  no floor outside the noise band - nothing comparable to report")
        print()
        return
    comparable = min(usable, key=lambda r: abs(r["loss_mean"] - GEEPAFS_PERFORMANCE_LOSS_PCT))
    print(f"  this oracle, nearest    : {comparable['gain_mean']:.1f}% efficiency gain "
          f"for {comparable['loss_mean']:.1f}% performance loss "
          f"(floor {comparable['floor'] * 100:.0f}%)")

    # A floor beating them on BOTH axes is the cleanest statement of the oracle's advantage.
    dominating = [r for r in usable
                  if r["gain_mean"] > GEEPAFS_EFFICIENCY_GAIN_PCT
                  and r["loss_mean"] < GEEPAFS_PERFORMANCE_LOSS_PCT]
    if dominating:
        best = max(dominating, key=lambda r: r["gain_mean"])
        print(f"  oracle dominates at     : floor {best['floor'] * 100:.0f}% - "
              f"{best['gain_mean']:.1f}% gain for only {best['loss_mean']:.1f}% loss, "
              f"better on BOTH axes")
    print()
    print("  These are NOT the same problem and the numbers must not be presented as a race.")
    print("  GEEPAFS chooses frequencies online with no prior knowledge of the application.")
    print("  This picks the best point with the entire measured curve already in hand. An")
    print("  oracle is SUPPOSED to win; the gap is the price of not knowing the future, not")
    print("  evidence of a better method. Reported only to size that price.")
    print()


def loadV100Curves():
    from load_data import loadDataset  # noqa: E402  (path set up above)

    dataset = loadDataset(validate=False)
    curves = {}
    for workload, group in dataset.groupby("workload"):
        curves[str(workload)] = buildPoints(
            group["frequency_mhz"].to_numpy(),
            group["performance_normalised"].to_numpy(),
            group["power_watts"].to_numpy(),
        )
    return curves


def loadSweepCurves(pattern, basis="achieved"):
    """
    Load sweeps as curves keyed by either the ACHIEVED or the COMMANDED frequency.

    WHY THE CHOICE EXISTS
        The V100 dataset has one frequency per point and no clamping, so the distinction is
        empty there. On consumer sweeps it is not. At a commanded 2625 MHz one workload holds
        2579 and another 2751, because they draw different power and the card clamps each
        independently - so twelve sweeps that share thirteen TARGETS share only five achieved
        clocks, and a fixed-frequency policy cannot be evaluated across them at all.

        A deployment sets `nvidia-smi -lgc 2625` and accepts whatever each workload sustains.
        The policy variable is therefore the COMMANDED frequency, and that is the basis a
        fixed-versus-per-workload comparison on consumer hardware has to use.

        "achieved" stays the default so every existing caller and every published number is
        unchanged. Pass basis="commanded" for policy questions.
    """
    if basis not in ("achieved", "commanded"):
        raise ValueError(f"basis must be 'achieved' or 'commanded', got {basis!r}")
    column = "achieved_frequency_avg" if basis == "achieved" else "target_frequency_mhz"
    curves = {}
    for path in sorted(SWEEPS.glob(pattern)):
        frequencies, throughput, power, achieved = [], [], [], []
        with open(path, encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                if not raw.get("bench_throughput"):
                    continue
                if raw.get("bench_ok") not in ("True", "true", None):
                    continue
                if raw.get("lock_miss_direction") in EXCLUDE_DIRECTIONS:
                    continue
                frequencies.append(float(raw[column]))
                throughput.append(float(raw["bench_throughput"]))
                power.append(float(raw["power_avg_w"]))
                achieved.append(float(raw["achieved_frequency_avg"]))
        if len(frequencies) >= 3:
            curves[path.stem.replace("_sweep", "")] = buildPoints(
                frequencies, throughput, power,
                achieved=achieved if basis == "commanded" else None)
    return curves


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--floors", type=float, nargs="+", default=DEFAULT_FLOORS,
                        help="Performance floors as fractions of the reference frequency.")
    parser.add_argument("--pattern", default="*floor15*_sweep.csv",
                        help="Sweep glob. Defaults to the wide sweeps, which reach stock; the "
                             "fine sweeps stop at 1900 MHz and never measure the reference.")
    parser.add_argument("--basis", choices=["achieved", "commanded"], default="achieved",
                        help="Which frequency keys a consumer curve. 'achieved' is what the card "
                             "held and is the default. 'commanded' is what was SET, and is the "
                             "basis a fixed-frequency POLICY has to be evaluated on: workloads "
                             "clamp to different achieved clocks at one target, so twelve sweeps "
                             "sharing thirteen targets share only five achieved clocks and the "
                             "fixed-versus-per-workload comparison cannot be computed at all. "
                             "Does not affect the V100, which has no clamping.")
    args = parser.parse_args()
    floors = sorted(args.floors, reverse=True)

    v100 = loadV100Curves()
    print(f"[DATA] V100: {len(v100)} workloads x "
          f"{len(next(iter(v100.values())))} frequencies\n")
    v100Rows, v100Disagreements = analyseCurves(v100, floors)
    printFloorTable("V100 (33 workloads, 757-1530 MHz)", v100Rows)
    reportAssumptions(v100, v100Disagreements)
    reportFixedVersusPerWorkload(v100, [f for f in floors if f < 1.0 - NOISE_BAND_PCT / 100.0])
    compareToGeepafs(v100Rows)

    consumer = loadSweepCurves(args.pattern, basis=args.basis)
    if consumer:
        print(f"[DATA] RTX 5060 Ti: {len(consumer)} sweeps matching "
              f"{args.pattern}, keyed by {args.basis.upper()} frequency\n")
        if args.basis == "commanded":
            shared = set.intersection(
                *[{round(q["mhz"]) for q in v} for v in consumer.values()])
            heldShared = set.intersection(
                *[{round(q["achieved_mhz"]) for q in v} for v in consumer.values()])
            print(f"[BASIS] {len(shared)} shared commanded targets against "
                  f"{len(heldShared)} shared achieved clocks. The gap between "
                  f"those two numbers is why this basis exists.")
            print("[BASIS] A fixed-frequency policy sets a TARGET and accepts what each")
            print("[BASIS] workload sustains, so the policy is defined on the target. A wide")
            print("[BASIS] achieved spread means the policy did NOT deliver one frequency.\n")
        for name, points in consumer.items():
            rows, disagreements = analyseCurves({name: points}, floors)
            printFloorTable(f"{name} ({len(points)} points, "
                            f"{points[0]['mhz']:.0f}-{points[-1]['mhz']:.0f} MHz)", rows)
            if disagreements:
                reportAssumptions({name: points}, disagreements)
        if len(consumer) > 1:
            reportFixedVersusPerWorkload(
                consumer, [f for f in floors if f < 1.0 - NOISE_BAND_PCT / 100.0])
        print("  NOTE: the consumer reference is the card's SUSTAINED maximum in that sweep,")
        print("  not a stock clock - these sweeps ran on an overclocked card, and the applied")
        print("  offsets were never recorded. Treat the consumer half as shape, not magnitude,")
        print("  until an interleaved stock-vs-tuned run exists.")
    else:
        print(f"[DATA] No sweeps matched {args.pattern} - skipping the consumer half.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
