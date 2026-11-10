"""Score REGISTERED-PREDICTIONS section 14 (the crossbar-clock interventions on the RTX 5060 Ti).

Written 2026-10-01 after collection, from the registration's text (ba59500, amended 837eb56 and
292a712/d765902): no threshold here is chosen by this file. Every comparison is against the mean of
the same-session brackets at that target - A and B for S and C, the two curve 3 baselines for N.

    python analysis/score_xbar14.py data/frequency-sweeps/5060ti-xbar14-20261001 [--memory-rule literal|section13]

THE MEMORY RULE HAS TWO READINGS, AND BOTH ARE PRINTED. Section 14 says "memory is exactly 13801 MHz".
Read per sample, almost no point meets it: in about half the points one sample in ~20 reads idle (810,
nvidia-smi; 101.2 x 8, HWiNFO) or 14001, stock's other loaded state, never in both instruments at once
and with no throughput effect. Section 13's amendment of 2026-09-27 (before its data) had already
rewritten the same rule as "memory max within 13801-14001 at every point" for exactly this reason;
section 14 copied the old wording. `literal` (the default) applies section 14 as written, per sample,
both instruments; `section13` applies section 13's amended rule. Report both; the choice was made
after the data were seen, and says so.

Limits: one card, one session, one arm per target. The offset is a request through mVolt+, an
undocumented tool; only HWiNFO's measured crossbar clock is evidence it happened. SYS is not
measured during collection (the calibration's sys_mhz readings are the only SYS evidence).
"""
import csv
import re
import sys
from pathlib import Path

S_WINDOW = (1312, 1372)
S_SECTION12 = {1560: 0.924, 1710: 0.886, 1867: 0.863}
S_PARTIAL_MAX = {1560: 0.962, 1710: 0.943, 1867: 0.931}
C_WINDOW = (1455, 1515)
N_WINDOWS = {1710: (1605, 1665), 1867: (1770, 1830)}


def hwinfoMemory(directory):
    """HWiNFO's NVIDIA memory clock inside each window (hwinfo-memory-in-window.csv), as effective MHz."""
    table = {}
    with open(directory / "hwinfo-memory-in-window.csv", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            table[(row["label"], int(float(row["target"])))] = (round(float(row["hwinfoGpuMemoryClockMin"]) * 8),
                                                                 round(float(row["hwinfoGpuMemoryClockMax"]) * 8))
    return table


def load(directory, label, hw):
    """One label's joined rows, keyed by target, with the sweep CSV's memory min/max attached."""
    joined = list(directory.glob(f"*_xbar14-{label}_sweep_voltage.csv"))
    raw = list(directory.glob(f"*_xbar14-{label}_sweep.csv"))
    if len(joined) != 1 or len(raw) != 1:
        sys.exit(f"expected one sweep and one join for {label}, found {len(raw)} and {len(joined)}")
    memory = {}
    with open(raw[0], newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            memory[int(float(row["target_frequency_mhz"]))] = (float(row["memory_clock_min_mhz"]), float(row["memory_clock_max_mhz"]))
    rows = {}
    with open(joined[0], newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            target = int(float(row["target"]))
            rows[target] = {"achieved": float(row["achieved"]), "throughput": float(row["throughputGbs"]),
                            "xbar": float(row["crossbarMeasured"]), "xbarReported": float(row["crossbar"]),
                            "vid": float(row["voltage"]), "memJoin": float(row["memoryMhz"]),
                            "memMin": memory[target][0], "memMax": memory[target][1],
                            "hwMin": hw[("xbar14-" + label, target)][0], "hwMax": hw[("xbar14-" + label, target)][1]}
    return rows


def mean(values):
    return sum(values) / len(values)


def driverEvents(directory):
    log = directory / "session-logs" / "session.log"
    counts = [int(n) for n in re.findall(r"display-driver events since session start: (\d+)", log.read_text(encoding="utf-8"))]
    return max(counts) if counts else None


MEMORY_RULE = "literal"


def memoryFailure(arm):
    readings = (arm["memMin"], arm["memMax"], arm["hwMin"], arm["hwMax"])
    if MEMORY_RULE == "literal":
        if all(abs(v - 13801) <= 1 for v in readings):
            return None
        return f"memory not 13801 at every sample (nvidia-smi {arm['memMin']:.0f}-{arm['memMax']:.0f}, HWiNFO {arm['hwMin']}-{arm['hwMax']})"
    # Section 13's rule is a BOUNDED maximum: each instrument's maximum must be one of stock's two
    # loaded states. Until GPT Job 40 (2026-10-01) this tested only the upper bound, so an all-idle
    # point (810 throughout) passed.
    bad = [(name, v) for name, v in (("nvidia-smi", arm["memMax"]), ("HWiNFO", arm["hwMax"])) if not 13801 - 1 <= v <= 14001 + 1]
    if not bad:
        return None
    return "memory max outside stock's 13801-14001 (" + ", ".join(f"{n} {v:.0f}" for n, v in bad) + ")"


def scoreable(arm, bracketRows, window, events):
    """The registration's four conditions. Returns a list of failures (empty = scoreable)."""
    failures = []
    if not window[0] <= arm["xbar"] <= window[1]:
        failures.append(f"measured XBAR {arm['xbar']:.1f} outside {window[0]}-{window[1]}")
    bracketAchieved = mean([r["achieved"] for r in bracketRows])
    if abs(arm["achieved"] - bracketAchieved) > 10:
        failures.append(f"core achieved {arm['achieved']:.0f} vs bracket {bracketAchieved:.1f}")
    memory = memoryFailure(arm)
    if memory:
        failures.append(memory)
    # The memory condition applies to the references as well (Job 40): a clean arm against a bracket
    # at 16301 is not a matched-memory comparison.
    for i, ref in enumerate(bracketRows):
        refMemory = memoryFailure(ref)
        if refMemory:
            failures.append(f"reference {i + 1}: {refMemory}")
    if events != 0:
        failures.append(f"display-driver events: {events}")
    return failures


def sVerdictOf(sRatios, interpretable):
    """S's table. FULL and PARTIAL hold "at every scoreable target"; NOT SUFFICIENT is registered
    "at all three", so a null on a subset is not a registered null (Job 40, 2026-10-01)."""
    if not interpretable or not sRatios:
        return "NOT SCOREABLE"
    if all(abs(r - S_SECTION12[t]) <= 0.03 for t, r in sRatios.items()):
        return "SUFFICIENT, FULL"
    if all(r <= S_PARTIAL_MAX[t] for t, r in sRatios.items()):
        return "SUFFICIENT, PARTIAL"
    if all(r >= 0.985 for r in sRatios.values()):
        if len(sRatios) == 3:
            return "NOT SUFFICIENT"
        return f"no registered verdict: null at the {len(sRatios)} scoreable target(s) only; NOT SUFFICIENT needs all three"
    return "MIXED"


def describe(name, target, arm, bracketRows, ratio):
    b = mean([r["throughput"] for r in bracketRows])
    bx = mean([r["xbar"] for r in bracketRows])
    bv = mean([r["vid"] for r in bracketRows])
    return (f"  {name} {target}: {arm['throughput']:.1f} against bracket {b:.1f} -> ratio {ratio:.3f}; "
            f"measured XBAR {arm['xbar']:.1f} (bracket {bx:.1f}); VID {arm['vid']:.3f} (bracket {bv:.3f}); "
            f"core {arm['achieved']:.0f}")


def main():
    global MEMORY_RULE
    directory = Path(sys.argv[1])
    if "--memory-rule" in sys.argv:
        MEMORY_RULE = sys.argv[sys.argv.index("--memory-rule") + 1]
    if MEMORY_RULE not in ("literal", "section13"):
        sys.exit("--memory-rule is literal or section13")
    hw = hwinfoMemory(directory)
    L = {name: load(directory, name, hw) for name in
         ["a-membw", "a-gemm", "s1560-membw", "s1710-membw", "s1867-membw", "s1867-gemm", "c1402-membw",
          "b-membw", "b-gemm", "c3base1-membw", "n1710-membw", "n1867-membw", "c3base2-membw", "cbr-membw"]}
    events = driverEvents(directory)
    print("Section 14 scorer | RTX 5060 Ti | one session | membw GB/s, measured XBAR from HWiNFO")
    print(f"Display-driver events during the session: {events}")
    print(f"Memory rule: {MEMORY_RULE} ({'section 14 as written: exactly 13801 at every sample, both instruments' if MEMORY_RULE == 'literal' else 'section 13 amendment: max within 13801-14001, stock states'})")
    allPoints = [(n, t, r) for n, rows in L.items() for t, r in rows.items()]
    failing = [f"{n}@{t}" for n, t, r in allPoints if memoryFailure(r)]
    print(f"Points failing the memory rule, arms and brackets alike: {len(failing)} of {len(allPoints)}" + (f" ({', '.join(failing)})" if failing else ""))

    # Interpretability.
    targets = [1402, 1560, 1710, 1867]
    aMean = mean([L["a-membw"][t]["throughput"] for t in targets])
    cMean = mean([L["cbr-membw"][t]["throughput"] for t in targets])
    drift = cMean / aMean - 1
    print(f"\nBracket C against A, mean over four targets: {cMean:.2f} vs {aMean:.2f} GB/s, {drift * 100:+.2f}% (limit 1.5%)")
    baseDrift = {t: L["c3base2-membw"][t]["throughput"] / L["c3base1-membw"][t]["throughput"] - 1 for t in (1710, 1867)}
    for t, d in baseDrift.items():
        print(f"Curve 3 baseline pair at {t}: {L['c3base1-membw'][t]['throughput']:.2f} then {L['c3base2-membw'][t]['throughput']:.2f}, {d * 100:+.2f}% (limit 1.5%)")
    interpretable = abs(drift) <= 0.015 and all(abs(d) <= 0.015 for d in baseDrift.values())
    print(f"Interpretable: {'YES' if interpretable else 'NO - every verdict below is NOT SCOREABLE as registered'}")
    for t in targets:
        rows = [L[k][t] for k in ("a-membw", "b-membw", "cbr-membw")]
        print(f"  stock {t}: A {rows[0]['throughput']:.1f} B {rows[1]['throughput']:.1f} C {rows[2]['throughput']:.1f} GB/s; "
              f"measured XBAR {rows[0]['xbar']:.0f} / {rows[1]['xbar']:.0f} / {rows[2]['xbar']:.0f}; VID {rows[0]['vid']:.3f} / {rows[1]['vid']:.3f} / {rows[2]['vid']:.3f}")
    for t in (1710, 1867):
        rows = [L[k][t] for k in ("c3base1-membw", "c3base2-membw")]
        print(f"  curve 3 {t}: {rows[0]['throughput']:.1f} / {rows[1]['throughput']:.1f} GB/s; measured XBAR {rows[0]['xbar']:.0f} / {rows[1]['xbar']:.0f}; VID {rows[0]['vid']:.3f} / {rows[1]['vid']:.3f}")

    # S.
    print("\nS, sufficiency (primary). Window 1312-1372 MHz measured.")
    sRatios = {}
    for t in (1560, 1710, 1867):
        arm = L[f"s{t}-membw"][t]
        bracket = [L["a-membw"][t], L["b-membw"][t]]
        ratio = arm["throughput"] / mean([r["throughput"] for r in bracket])
        failures = scoreable(arm, bracket, S_WINDOW, events)
        vidCodes = (arm["vid"] - mean([r["vid"] for r in bracket])) / 0.005
        print(describe("S", t, arm, bracket, ratio) + (f"  NOT SCOREABLE: {'; '.join(failures)}" if failures else f"  (section 12: {S_SECTION12[t]})")
              + (f"  VID {vidCodes:+.1f} codes from the bracket mean" if abs(vidCodes) > 1 else ""))
        if not failures:
            sRatios[t] = ratio
    sVerdict = sVerdictOf(sRatios, interpretable)
    print(f"S verdict over {len(sRatios)} scoreable target(s): {sVerdict}")

    armG = L["s1867-gemm"][1867]
    bracketG = [L["a-gemm"][1867], L["b-gemm"][1867]]
    gRatio = armG["throughput"] / mean([r["throughput"] for r in bracketG])
    gFail = scoreable(armG, bracketG, S_WINDOW, events)
    print(f"S-gemm control at 1867: {armG['throughput']:.0f} against {mean([r['throughput'] for r in bracketG]):.0f} GFLOP/s, "
          f"{(gRatio - 1) * 100:+.2f}% (limit 2%): {'inside' if abs(gRatio - 1) <= 0.02 else 'OUTSIDE - S cannot be read as XBAR-specific'}"
          f"; measured XBAR {armG['xbar']:.1f}; VID {armG['vid']:.3f} against {mean([r['vid'] for r in bracketG]):.3f}"
          f" ({(armG['vid'] - mean([r['vid'] for r in bracketG])) / 0.005:+.1f} codes)"
          + (f"; NOT SCOREABLE: {'; '.join(gFail)}" if gFail else ""))

    # C.
    print("\nC, the low-clock limit (secondary). Window 1455-1515 MHz measured.")
    arm = L["c1402-membw"][1402]
    bracket = [L["a-membw"][1402], L["b-membw"][1402]]
    ratio = arm["throughput"] / mean([r["throughput"] for r in bracket])
    failures = scoreable(arm, bracket, C_WINDOW, events)
    print(describe("C", 1402, arm, bracket, ratio) + (f"  NOT SCOREABLE: {'; '.join(failures)}" if failures else ""))
    if not interpretable or failures:
        cVerdict = "NOT SCOREABLE"
    elif ratio >= 1.04:
        cVerdict = "LIFTS"
    elif ratio >= 1.015:
        cVerdict = "PARTIAL"
    elif ratio >= 0.985:
        cVerdict = "NULL"
    else:
        cVerdict = "reported as unexpected (below 0.985)"
    print(f"C verdict: {cVerdict}")

    # N.
    print("\nN, necessity (exploratory). Windows 1605-1665 at 1710, 1770-1830 at 1867, measured.")
    nRows = {}
    for t in (1710, 1867):
        arm = L[f"n{t}-membw"][t]
        base = [L["c3base1-membw"][t], L["c3base2-membw"][t]]
        stock = mean([L["a-membw"][t]["throughput"], L["b-membw"][t]["throughput"]])
        baseMean = mean([r["throughput"] for r in base])
        toStock = arm["throughput"] / stock
        # Recovery needs a positive gap between stock and the curve 3 baseline.
        recovery = (arm["throughput"] - baseMean) / (stock - baseMean) if stock - baseMean > 0 else float("nan")
        failures = scoreable(arm, base, N_WINDOWS[t], events)
        if not stock - baseMean > 0:
            failures.append("no positive stock-minus-baseline gap, recovery undefined")
        # N's stock denominator (A and B) is a reference too.
        for name in ("a-membw", "b-membw"):
            refMemory = memoryFailure(L[name][t])
            if refMemory:
                failures.append(f"stock reference {name[0].upper()}: {refMemory}")
        print(f"  N {t}: {arm['throughput']:.1f} GB/s; curve 3 baseline {baseMean:.1f}; stock bracket (A,B) {stock:.1f}; "
              f"ratio to stock {toStock:.3f}; recovery {recovery:.3f}; measured XBAR {arm['xbar']:.1f}; VID {arm['vid']:.3f}; core {arm['achieved']:.0f}"
              + (f"  NOT SCOREABLE: {'; '.join(failures)}" if failures else ""))
        if not failures:
            nRows[t] = (toStock, recovery)
    if not interpretable or len(nRows) < 2:
        nVerdict = "NOT SCOREABLE" if len(nRows) == 0 or not interpretable else "reported per target (one target not scoreable)"
    elif all(r[0] >= 0.97 for r in nRows.values()):
        nVerdict = "LIFTS"
    elif all(r[1] >= 0.5 for r in nRows.values()):
        nVerdict = "PARTIAL"
    elif all(r[1] < 0.25 for r in nRows.values()):
        nVerdict = "NULL"
    else:
        nVerdict = "MIXED"
    print(f"N verdict: {nVerdict}")
    print("\nn = 1 card, one session, one arm per target. SYS was not measured during collection.")


if __name__ == "__main__":
    main()
