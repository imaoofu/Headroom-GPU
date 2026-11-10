"""Claims for the submission paper, docs/submission/paper.md.

Two kinds, both deliberately tied to the long draft so the two documents cannot disagree:
- REUSED: a long-draft claim's render function registered a second time against the submission.
  The submission must then contain the identical string, so a number changes in both or neither.
- NEW: tables the long draft does not have, computed from the same scorers and helpers.

Added 2026-09-28 with the submission's results section.
"""
import statistics
from pathlib import Path

from audit_claims import CLAIMS, claim

SUBMISSION = "docs/submission/paper.md"
PAPER = "docs/PAPER_DRAFT.md"

import claims_consumer as cc  # noqa: E402 - registers the long draft's claims first

# Long-draft claims whose exact rendered text the submission reuses, and the submission section.
REUSED = {
    "5.5.4-mean-gain-5060": "5.1",
    "5.5.4-mean-gain-3070": "5.1",
    "5.5.4-rank-correlation": "5.1",
    "5.5.4-within-card-control": "5.1",
    "5.5.7-2060s-4d-minimum": "5.2",
    "5.5.7-2060s-agreement": "5.2",
    "5.5.8-abba-shift-range": "5.3",
    "5.5.8-abba-exact-count": "5.3",
    "5.5.8-control-agreement": "5.3",
    "5.5.8-ladder-prospective": "5.3",
    "5.5.9-edit1-at-1590": "5.3",
    "5.5.7-2060s-e2-verdict": "5.3",
    "5.5.7-2060s-e2-return": "5.3",
    "5.5.7-2060s-e2-directions": "5.3",
    "5.7.3-4j-plateau": "5.4",
    "5.7.3-4j-crossbar": "5.4",
    "5.7.3-4j-gate": "5.4",
    "5.5.10-floor-voltage": "5.5",
    "5.5.10-elasticity": "5.5",
}


def _reuse():
    byId = {c["claimId"]: c for c in CLAIMS if c["document"] == PAPER}
    for claimId, section in REUSED.items():
        if claimId not in byId:
            raise KeyError(f"submission reuses {claimId}, which the long draft no longer registers")
        source = byId[claimId]
        claim(f"sub-{claimId}", SUBMISSION, f"sub-{section}",
              mixedProvenance=source["mixedProvenance"])(source["render"])


_reuse()


@claim("sub-floor-table", SUBMISSION, "sub-5.2")
def subFloorTable():
    """The four-card floor table, from the same suites and extracts as the long draft's 5.5.7."""
    rows = []
    specs = [
        ("RTX 5060 Ti (Blackwell)", cc.REPLICATES_5060[1:], cc._VOLT_5060_STOCK, None),
        ("RTX 3070 Ti (Ampere)", cc.SUITE_3070_SWEEPS, cc._VOLT_3070_SILENT, cc.SUITE_3070_SWEEPS),
        ("RTX 3060 (Ampere)", cc.SUITE_3060, cc._VOLT_3060_SUITE, cc.SUITE_3060),
    ]
    for name, suites, volt, agreementSuite in specs:
        # The 5060 Ti's median pools its replicates, so it has no single count; give the range of
        # the per-replicate counts instead of a dash (GPT Job 34, 2026-09-29).
        if agreementSuite is None:
            counts = [cc._suiteAgreement(t)[0] for t in suites]
            agreement = f"{min(counts)}–{max(counts)} of 12 per replicate"
        else:
            agree, total = cc._suiteAgreement(agreementSuite)
            agreement = f"{agree} of {total}"
        rows.append(f"| {name} | {cc._medianSuiteOptimum(suites):.0f} MHz | "
                    f"{cc._voltageFloorTop(volt):.0f} MHz | {cc._voltageFloorValue(volt):.3f} V | "
                    f"{agreement} |")
    strict = cc._voltageFloorTop(cc._VOLT_2060S_LOWRANGE)
    lenient = cc._voltageFloorTopWithin(cc._VOLT_2060S_LOWRANGE, 0.006)
    agree, total = cc._suiteAgreement(cc.SUITE_2060S)
    rows.append(f"| RTX 2060 Super (Turing) | {cc._medianSuiteOptimum(cc.SUITE_2060S):.0f} MHz | "
                f"{strict:.0f} or {lenient:.0f} MHz, one 6 mV step apart | "
                f"{cc._voltageFloorValue(cc._VOLT_2060S_LOWRANGE):.3f} V | {agree} of {total} |")
    return "\n".join(rows)


def _changed(before, after):
    return sum(after[n] != before[n] for n in before)


@claim("sub-3070-baseline", SUBMISSION, "sub-5.3")
def sub3070Baseline():
    main, rep = cc.sessionD("main"), cc.sessionD("replicate")
    stockPairs = sorted([_changed(main["optima"]["stock-1"], main["optima"]["stock-4"]),
                         _changed(rep["optima"]["stock-4"], rep["optima"]["stock-6"])])
    edits = [_changed(main["optima"]["stock-1"], main["optima"]["edit1-2"]),
             _changed(rep["optima"]["stock-4"], rep["optima"]["edit1-5"])]
    return (f"the edit changed {edits[0]} and then {edits[1]} of the twelve per-workload optima, "
            f"where two identical stock suites change {stockPairs[0]}–{stockPairs[1]}")


# Session D2's grid moved above 1485 MHz (the clock table's top rose 2115 -> 2130), so its six
# clipped targets are these rather than the registered 1590..2115.
D2_CLIPPED = (1605, 1710, 1815, 1920, 2025, 2130)


def _d2ControlMedian():
    """Session D2's control repeat, scored DESCRIPTIVELY with the registered rules except the grid.

    The committed scorer refuses D2's shifted grid, so 8d is NOT SCOREABLE. This applies that
    scorer's own collapse_control - Edit 2's six clipped targets become one median-efficiency bin
    at 1500 MHz - to D2's six. A raw argmax over the clipped targets would instead pick among six
    repeated ~1500 MHz points labelled 1605..2130, which is how a first version of this claim read
    1920 MHz (2026-09-28) against the data README's 1485.
    """
    import dataclasses
    import score_session_d
    from analyze_sweep import efficiencyPeak, loadSweep
    base = cc._REPO_ROOT / "data" / "frequency-sweeps" / "rtx3070ti-sessiond2-20260925"
    saved = score_session_d.REGISTRATION
    score_session_d.REGISTRATION = dataclasses.replace(saved, clipped_targets=D2_CLIPPED)
    try:
        optima = []
        for name in saved.workloads:
            [path] = sorted(base.rglob(f"*_rtx3070ti-sessiond-edit2-8-{name}_sweep.csv"))
            options, clippedBin = score_session_d.collapse_control(loadSweep(path))
            best = efficiencyPeak(options)
            optima.append(saved.clipped_achieved_mhz if best is clippedBin else best["target"])
    finally:
        score_session_d.REGISTRATION = saved
    return statistics.median(optima)


@claim("sub-registered-tests", SUBMISSION, "sub-5.3")
def subRegisteredTests():
    """Table 3: every curve test, its registration, prediction, measured median and verdict."""
    main, rep = cc.sessionD("main"), cc.sessionD("replicate")
    e2 = cc.sessionE("e2")
    b, c = cc._rung("rungB"), cc._rung("rungC")
    decode = cc.q1("decode")
    split = cc._medianSuiteOptimum(cc.REPLICATES_5060[1:])
    s16 = _session16()[0]
    rows = [
        ("floor region +465 MHz", "5060 Ti", "no (post hoc)", "—",
         "+465 MHz shift", "the median moved with the floor"),
        ("edit above the floor (control)", "5060 Ti", "yes", "unchanged",
         "unchanged", "held; some workloads moved"),
        ("both arms again, one session", "5060 Ti", "yes", "2010 MHz; control unchanged",
         f"{s16['medians']['p4']:g} MHz; control {s16['medians']['p2']:g} MHz", "held, held"),
        ("ladder rung B", "5060 Ti", "yes", f"{b['pick']} MHz", f"{b['median']:g} MHz", "held"),
        ("ladder rung C", "5060 Ti", "yes", f"{c['pick']} MHz", f"{c['median']:g} MHz", "held"),
        ("floor shortened", "3070 Ti", "yes", "1170–1275 MHz",
         f"{main['medians']['edit1-2']:g}, then {rep['medians']['edit1-5']:g} MHz",
         f"{main['4a']}, {rep['8a']}"),
        ("edit above the floor (control)", "3070 Ti", "yes", "1485–1500 MHz",
         f"{main['medians']['edit2-3']:g} MHz", main["4b"]),
        ("the control, repeated", "3070 Ti", "yes", "1485–1500 MHz",
         f"{_d2ControlMedian():g} MHz, descriptive", "NOT SCOREABLE"),
        ("whole-curve offset −165 MHz", "2060 Super", "yes, repeat after the first result",
         "855–960 MHz", f"{e2['medians']['offset-5']:g} MHz", e2["4c"].replace("_", " ")),
        ("LLM decode at stock", "5060 Ti", "yes", "1560 MHz", f"{decode['best']} MHz",
         decode["verdict"]),
    ]
    if split != 1537:
        return f"the 5060 Ti split median is now {split:g}"
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


# --------------------------------------------------------------------------------------------------
# Section 3, Methods (2026-09-28).

REUSED_METHODS = {"3.3.4-intensity-span": "3", "3.3.5-llm-work": "3"}


def _reuseMethods():
    byId = {c["claimId"]: c for c in CLAIMS if c["document"] == PAPER}
    for claimId, section in REUSED_METHODS.items():
        source = byId[claimId]
        claim(f"sub-{claimId}", SUBMISSION, f"sub-{section}")(source["render"])


_reuseMethods()

# Board, chip and memory are stated facts (TR 3.1); drivers and power limits are read from every
# committed sweep JSON, so the table cannot drift from the data.
CARD_FACTS = [
    ("NVIDIA GeForce RTX 5060 Ti", "RTX 5060 Ti", "Zotac Twin Edge OC", "GB206, Blackwell",
     "16 GB GDDR7, 128-bit"),
    ("NVIDIA GeForce RTX 3070 Ti", "RTX 3070 Ti", "Gigabyte GAMING OC rev2.0, two BIOS positions",
     "GA104, Ampere", "8 GB GDDR6X, 256-bit"),
    ("NVIDIA GeForce RTX 3060", "RTX 3060", "ASUS Phoenix", "GA106, Ampere", "12 GB GDDR6"),
    ("NVIDIA GeForce RTX 2060 SUPER", "RTX 2060 Super", "MSI Ventus 2X", "TU106, Turing",
     "8 GB GDDR6, 256-bit"),
]


@claim("sub-card-table", SUBMISSION, "sub-3")
def subCardTable():
    import collections
    import json
    seen = collections.defaultdict(lambda: collections.defaultdict(set))
    for path in (cc._REPO_ROOT / "data" / "frequency-sweeps").rglob("*_sweep.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        for key in ("driver_version", "power_limit_default_w", "power_limit_w"):
            if meta.get(key):
                seen[meta.get("gpu_name", "")][key].add(meta[key])

    def watts(values):
        return " or ".join(f"{float(v):g}" for v in sorted(values, key=float))

    rows = []
    for gpu, short, board, chip, memory in CARD_FACTS:
        s = seen[gpu]
        power = f"{watts(s['power_limit_default_w'])} / {watts(s['power_limit_w'])} W"
        if short == "RTX 3070 Ti":
            power = _power3070(s)
        rows.append(f"| {short} | {board} | {chip} | {memory} | {power} | "
                    f"{', '.join(sorted(s['driver_version']))} |")
    return "\n".join(rows)


def _power3070(fields):
    """The 3070 Ti's two BIOS positions have different envelopes (GPT Job 34, 2026-09-29).

    The OC-position sweep JSONs record the 350 W maximum but leave the default empty, so a union
    of JSON fields printed "290 / 320 or 350 W" and implied a 290 W default for both. The OC
    default is read from that position's machine-info record, and its maximum must agree with the
    JSONs'.

    Only the operator's "MEASURED in this position:" sentence is read, and it must hold exactly one
    default/max pair (GPT Job 35): a spec quoted elsewhere in the file must never be picked up.
    """
    import re
    silentDefault = {float(v) for v in fields["power_limit_default_w"]}
    limits = {float(v) for v in fields["power_limit_w"]}
    info = (cc._REPO_ROOT / "data" / "frequency-sweeps" / "rtx3070ti-20260825" / "oc-bios" /
            "machine-info.txt").read_text(encoding="utf-8-sig")
    measured = re.findall(r"MEASURED in this position:(.*?)\.(?:\s|$)", info)
    pairs = [p for m in measured for p in re.findall(r"default (\d+) W and max (\d+) W", m)]
    if len(measured) != 1 or len(pairs) != 1:
        return (f"3070 Ti OC machine-info: expected one measured default/max pair, found "
                f"{len(pairs)} in {len(measured)} measured sentence(s)")
    ocDefault, ocMax = map(float, pairs[0])
    silentMax = limits - {ocMax}
    if len(silentDefault) != 1 or len(silentMax) != 1 or ocMax not in limits:
        return f"3070 Ti power fields no longer split by BIOS: {sorted(silentDefault)}, {sorted(limits)}"
    return (f"{silentDefault.pop():g} / {silentMax.pop():g} W (Silent BIOS); "
            f"{ocDefault:g} / {ocMax:g} W (OC)")


# --------------------------------------------------------------------------------------------------
# Section 4, Dataset (2026-09-28).

# Reused only where the long draft registers them: 2.7's claims need the fetched data/external sets,
# which CI's bare leg does not have, so there the submission sentence simply goes unpinned.
OPTIONAL_REUSE = {"2.7-declared-floor-pct": "4", "6-flagged-sweeps": "4"}


def _reuseOptional():
    byId = {c["claimId"]: c for c in CLAIMS if c["document"] == PAPER}
    for claimId, section in OPTIONAL_REUSE.items():
        if claimId in byId:
            claim(f"sub-{claimId}", SUBMISSION, f"sub-{section}")(byId[claimId]["render"])


_reuseOptional()


@claim("sub-census", SUBMISSION, "sub-4")
def subCensus():
    import collections
    import build_data_manifest
    manifest = build_data_manifest.buildManifest(build_data_manifest.loadSessions())
    grade = [e for e in manifest if e["category"] == "dataset-grade"]
    verification = sum(1 for e in manifest if e["category"] == "verification")
    cards = collections.Counter(e["gpu"] for e in grade)
    return (f"{len(grade)} dataset-grade sweeps and {verification} early verification runs: "
            f"{cards['NVIDIA GeForce RTX 5060 Ti']} on the RTX 5060 Ti, "
            f"{cards['NVIDIA GeForce RTX 3070 Ti']} on the RTX 3070 Ti, "
            f"{cards['NVIDIA GeForce RTX 2060 SUPER']} on the RTX 2060 Super and "
            f"{cards['NVIDIA GeForce RTX 3060']} on the RTX 3060")


def _datasetGrade():
    import build_data_manifest
    manifest = build_data_manifest.buildManifest(build_data_manifest.loadSessions())
    return [e for e in manifest if e["category"] == "dataset-grade"]


@claim("sub-voltage-extracts", SUBMISSION, "sub-4")
def subVoltageExtracts():
    """The dataset-grade population, as the sentence in the dataset paragraph names it. It counted EVERY
    paired extract under data/ (746) until 2026-10-20, when GPT Job 112 (F3) found the sentence's
    denominator changed silently; the formula and the sentence changed in the same commit."""
    grade = _datasetGrade()
    with_extract = sum(1 for e in grade
                       if (cc._REPO_ROOT / e["path"]).with_name(
                           Path(e["path"]).stem + "_voltage.csv").is_file())
    return f"{with_extract} of the {len(grade)} dataset-grade sweeps carry a joined voltage and crossbar-clock extract"


@claim("sub-schema-gaps", SUBMISSION, "sub-4")
def subSchemaGaps():
    """Which per-row fields older schemas lack, read from every dataset-grade CSV header (GPT Job 112, F4:
    the field list read as universal). Video-engine telemetry is the census's no-encoder-telemetry flag."""
    import csv
    grade = _datasetGrade()
    noWindow = noMemory = 0
    for e in grade:
        with (cc._REPO_ROOT / e["path"]).with_suffix(".csv").open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
        noWindow += "window_start_unix" not in header or "window_end_unix" not in header
        noMemory += "memory_clock_avg_mhz" not in header
    noEngines = sum(1 for e in grade if "no-encoder-telemetry" in (e.get("flags") or []))
    return (f"the absolute window bounds are absent from {noWindow} of the {len(grade)} dataset-grade "
            f"sweeps, the mean memory clock from {noMemory}, and video-engine telemetry from {noEngines}")


def desktopLoadCounts():
    """The desktop-load census of 2026-10-03 (docs/desktop-load-census-20261003.csv, written by
    tools/hwinfo-logging/scan_desktop_load_corpus.py from raw logs that only exist on the bench PC),
    restricted to the sweeps the live manifest calls dataset-grade. Rerun 2026-10-04 to add section 15
    R2 (4 rows added, none changed) and 2026-10-06 to add section 16 (48 rows added, none changed) and section 17 (12 rows, no HWiNFO log, so unknown); a later sweep is not in it until the census is rerun again."""
    import csv
    import build_data_manifest
    manifest = build_data_manifest.buildManifest(build_data_manifest.loadSessions())
    grade = {e["path"] for e in manifest if e["category"] == "dataset-grade"}
    counts = {"LOAD": 0, "quiet": 0, "unknown": 0}
    with open(cc._REPO_ROOT / "docs" / "desktop-load-census-20261003.csv", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["sweep"] in grade:
                counts[row["verdict"] if row["verdict"] in ("LOAD", "quiet") else "unknown"] += 1
    return counts, sum(counts.values())


@claim("sub-desktop-load-census", SUBMISSION, "sub-6")
def subDesktopLoadCensus():
    c, total = desktopLoadCounts()
    return (f"{c['LOAD']} of the {total} dataset-grade 5060 Ti sweeps carry its signature, "
            f"{c['quiet']} were checked quiet and {c['unknown']} cannot be checked")


@claim("desktop-load-census", PAPER, "5.4.4")
def desktopLoadCensus():
    c, total = desktopLoadCounts()
    return (f"{c['LOAD']} of the {total} dataset-grade RTX 5060 Ti sweeps carry that signature, "
            f"{c['quiet']} were checked quiet and {c['unknown']} cannot be checked")


# --------------------------------------------------------------------------------------------------
# Section 6, Uncertainty and limitations (2026-09-29).

@claim("sub-noise-table", SUBMISSION, "sub-6")
def subNoiseTable():
    """Table 4, the long draft's noise table cut to five rows, every figure recomputed.

    The long draft's copy of this table is prose; here the replicate spreads come from 5.4.5's own
    helpers, the within-configuration range from 5.7.6's five clean tuned peaks, the cross-session
    offset from the 2026-08-29 memory-only run against both 2026-08-22 clean runs, and the grid
    steps from each card's commanded targets.
    """
    from statistics import mean

    def optimum(path):
        return max(cc.sweep(path).values(), key=lambda r: r["efficiency"])["mhz"]

    def agree(a, b):
        return sum(abs(optimum(a[n]) - optimum(b[n])) < 5 for n in a)

    peaks = [cc._peakTf(p) for p in cc.TUNED_CLEAN_5]
    later = cc.sweep(cc.MEMONLY_GEMM_SAMESESSION)
    earlier = [cc.sweep(p) for p in cc.MEMONLY_GEMM_CLEAN]
    shared = sorted(set(later).intersection(*earlier))
    offset = 100 * mean(later[t]["throughput"] / mean(e[t]["throughput"] for e in earlier) - 1
                        for t in shared)
    main, rep = cc.sessionD("main"), cc.sessionD("replicate")
    stock3070 = sorted([_changed(main["optima"]["stock-1"], main["optima"]["stock-4"]),
                        _changed(rep["optima"]["stock-4"], rep["optima"]["stock-6"])])
    e2 = cc.sessionE("e2")["optima"]

    def steps(table):
        found = set()
        for path in table.values():
            targets = sorted(cc.sweep(path))
            found.update(round(b - a) for a, b in zip(targets, targets[1:]))
        return found

    step5060 = steps(cc.REPLICATES_5060[1])
    others = steps(cc.SUITE_3070_SWEEPS) | steps(cc.SUITE_3060) | steps(cc.SUITE_2060S)
    if len(others) != 1:
        return f"the other three cards' grid steps are now {sorted(others)}"
    rows = [
        ("throughput, power and efficiency, one stock configuration",
         f"{cc._spreadsFor('throughput'):.2f}%, {cc._spreadsFor('power'):.2f}% and "
         f"{cc._spreadsFor('efficiency'):.2f}%, mean per-point spread",
         "three stock suite replicates, RTX 5060 Ti"),
        ("efficiency gain, optimum over the highest clock reached",
         f"{mean(cc._gainSpreads().values()):.2f} points, mean over twelve workloads",
         "the same replicates"),
        ("`gemm` throughput, unchanged configuration",
         f"{100 * (max(peaks) - min(peaks)) / mean(peaks):.2f}% range over five clean peak runs; "
         f"{offset:.2f}% mean offset between two sessions a week apart", "RTX 5060 Ti"),
        ("per-workload optimum between identical suites",
         f"agree on {agree(cc.ABBA_A1, cc.ABBA_A2)} and {agree(cc.ABBA_B1, cc.ABBA_B2)} of 12 "
         f"(5060 Ti ABBA pairs); change {stock3070[0]}–{stock3070[1]} of 12 (3070 Ti) and "
         f"{_changed(e2['stock-4'], e2['stock-6'])} of 12 (2060 Super)", "pairs of one configuration in one session"),
        ("optimum location",
         f"one grid step: {min(step5060)}–{max(step5060)} MHz on the 5060 Ti, "
         f"{others.pop()} MHz on the other three", "the suites of §5.2"),
    ]
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


@claim("sub-drift-sign", SUBMISSION, "sub-6")
def subDriftSign():
    """Why sign consistency does not rule drift out: the unchanged configuration moved one way at
    every shared point, against each of the two earlier runs separately."""
    later = cc.sweep(cc.MEMONLY_GEMM_SAMESESSION)
    earlier = [cc.sweep(p) for p in cc.MEMONLY_GEMM_CLEAN]
    shared = sorted(set(later).intersection(*earlier))
    higher = [sum(later[t]["throughput"] > e[t]["throughput"] for t in shared) for e in earlier]
    if min(higher) != len(shared):
        return f"read faster a week later at only {min(higher)} of {len(shared)} grid points"
    return f"read faster a week later at all {len(shared)} grid points"


# --------------------------------------------------------------------------------------------------
# Section 15's clean re-runs (REGISTERED-PREDICTIONS section 15, collected 2026-10-03) and the
# abstract. Read straight from the committed sweep CSVs, never through score_rerun15.py, whose
# evidence gates need raw HWiNFO logs that only exist on the bench PC.

RERUN15 = "data/frequency-sweeps/5060ti-rerun15-20261003"
MEMMATCHED_STOCK = "data/frequency-sweeps/5060ti-memmatched-20260926/20260926-155100_5060ti-4j-stock-membw_sweep.csv"


def _rerun15Path(role):
    import json
    with open(cc._REPO_ROOT / RERUN15 / "rerun15-inputs.json", encoding="utf-8") as handle:
        desc = json.load(handle)["sweeps"][role]
    if isinstance(desc, list):
        desc = desc[-1]
    return cc._REPO_ROOT / RERUN15 / desc["sweep"]


def _rerun15Rows(role):
    from analyze_sweep import loadSweep
    return {r["target"]: r for r in loadSweep(_rerun15Path(role))}


def _rerun15Rungs():
    """Each rung's median target-grid optimum and its count of workloads on that point."""
    from score_control10 import WORKLOADS, read_suite
    result = {}
    for arm, predicted in (("rungB", 1702), ("rungC", 1852)):
        suite, _ = read_suite({w: _rerun15Path(f"{arm}-{w}") for w in WORKLOADS})
        optima = [suite[w]["optimum"] for w in WORKLOADS]
        result[arm] = (statistics.median(optima), sum(o == predicted for o in optima), len(optima))
    return result


def _rerun15Gap():
    stock, curve = _rerun15Rows("stock-open-membw"), _rerun15Rows("curve3-membw")
    band = [t for t in sorted(stock) if 1560 <= t <= 1867]
    gaps = [100 * (1 - curve[t]["throughput"] / stock[t]["throughput"]) for t in band]
    return min(gaps), max(gaps)


def _rerun15LoadUplift():
    from analyze_sweep import loadSweep
    clean = statistics.mean(r["throughput"] for r in _rerun15Rows("stock-open-membw").values())
    loaded = statistics.mean(r["throughput"] for r in loadSweep(cc._REPO_ROOT / MEMMATCHED_STOCK))
    return 100 * (clean / loaded - 1)


def _rerun15Drift():
    """Worst workload's median absolute matched-target change between the two stock suites, as
    section 10's gate, rounded UP to two decimals so "within" stays true."""
    import math
    from score_control10 import WORKLOADS, read_suite, stock_return
    a, targets = read_suite({w: _rerun15Path(f"stock-open-{w}") for w in WORKLOADS})
    b, _ = read_suite({w: _rerun15Path(f"stock-close-{w}") for w in WORKLOADS})
    return math.ceil(max(stock_return(a, b, targets).values()) * 100) / 100


def _rungText():
    r = _rerun15Rungs()
    return r["rungB"], r["rungC"]


@claim("sub-rerun15-rungs", SUBMISSION, "sub-5.3")
def subRerun15Rungs():
    (mb, nb, t), (mc, nc, _) = _rungText()
    return (f"Both medians landed on {mb:.0f} and {mc:.0f} MHz again, with {nb} and {nc} of {t} "
            f"workloads on the predicted point.")


@claim("rerun15-rungs", PAPER, "5.4.4")
def rerun15Rungs():
    (mb, nb, t), (mc, nc, _) = _rungText()
    return (f"Both ladder rungs landed on their predicted medians again, {mb:.0f} and {mc:.0f} MHz, "
            f"with {nb} and {nc} of {t} workloads on the point.")


@claim("sub-rerun15-gap", SUBMISSION, "sub-5.4")
def subRerun15Gap():
    lo, hi = _rerun15Gap()
    return (f"reproduced the gap, {lo:.1f}–{hi:.1f}% below stock across the same targets, and put "
            f"stock's absolute bandwidth {_rerun15LoadUplift():.1f}% above the loaded session's")


@claim("rerun15-gap", PAPER, "5.4.4")
def rerun15Gap():
    lo, hi = _rerun15Gap()
    stock, curve = cc._memmatchedRows("stock-membw"), cc._memmatchedRows("curve3-membw")
    band = [t for t in sorted(stock) if 1560 <= t <= 1867]
    old = [100 * (1 - curve[t]["throughput"] / stock[t]["throughput"]) for t in band]
    return (f"curve 3 {lo:.1f}–{hi:.1f}% below stock at {band[0]}–{band[-1]} MHz against "
            f"{min(old):.1f}–{max(old):.1f}% under the load, and stock's absolute bandwidth came out "
            f"{_rerun15LoadUplift():.1f}% above the loaded session's")


@claim("sub-rerun15-understated", SUBMISSION, "sub-6")
def subRerun15Understated():
    # Clean over loaded, minus one: an uplift, so the sentence says the clean sweep read higher (GPT Job
    # 112, F5: "understated by 8.2%" reads as loaded = clean - 8.2%, which is 7.5%).
    return f"in the one case re-measured, the clean sweep read {_rerun15LoadUplift():.1f}% higher"


@claim("sub-rerun15-drift", SUBMISSION, "sub-6")
def subRerun15Drift():
    return f"agreed to within {_rerun15Drift():.2f}% per workload"


@claim("rerun15-drift", PAPER, "5.4.4")
def rerun15Drift():
    return f"agreed to within {_rerun15Drift():.2f}% per workload"


@claim("rerun15-gemm-power-1545", PAPER, "5.4.4")
def rerun15GemmPower():
    stock, curve = _rerun15Rows("stock-gemm"), _rerun15Rows("curve3-gemm")
    change = 100 * (curve[1545]["power"] / stock[1545]["power"] - 1)
    if abs(change) >= 0.5:
        return f"curve 3's `gemm` power differs from stock's at 1545 MHz by {change:+.2f}%"
    return f"equal to stock's at 1545 MHz ({change:+.2f}%)"


# Section 15 R2 (collected 2026-10-04 in its own session): the 08-20 pair and the repair, clean.
RERUN15R2 = "data/frequency-sweeps/5060ti-rerun15r2-20261004"


def _rerun15r2Rows(role):
    import json
    from analyze_sweep import loadSweep
    with open(cc._REPO_ROOT / RERUN15R2 / "rerun15-inputs.json", encoding="utf-8") as handle:
        desc = json.load(handle)["sweeps"][role]
    return {r["target"]: r for r in loadSweep(cc._REPO_ROOT / RERUN15R2 / desc["sweep"])}


def _rerun15r2Band():
    """P4 below opening stock, and P2 above P4, in percent, over R2's registered 1560-1867 band."""
    stock, p4, p2 = (_rerun15r2Rows(r) for r in ("stock-open-membw", "p4-membw", "p2-membw"))
    band = [t for t in sorted(stock) if 1560 <= t <= 1867]
    below = [100 * (1 - p4[t]["throughput"] / stock[t]["throughput"]) for t in band]
    above = [100 * (p2[t]["throughput"] / p4[t]["throughput"] - 1) for t in band]
    return band, (min(below), max(below)), (min(above), max(above))


@claim("rerun15r2-repair", PAPER, "5.4.4")
def rerun15r2Repair():
    band, (blo, bhi), (alo, ahi) = _rerun15r2Band()
    return (f"the full tune {blo:.1f}–{bhi:.1f}% below stock at {band[0]}–{band[-1]} MHz and the "
            f"repair {alo:.1f}–{ahi:.1f}% above the full tune there")


@claim("sub-rerun15r2-repair", SUBMISSION, "sub-5.4")
def subRerun15r2Repair():
    _, _, (alo, ahi) = _rerun15r2Band()
    return f"the repair measured {alo:.1f}–{ahi:.1f}% above the flattened curve"


# Section 16 (collected 2026-10-06): the control clean and the floor manipulation registered, one session.
SESSION16 = "data/frequency-sweeps/5060ti-session16-20261006"


def _session16():
    """score_session16's verdicts and counts on the committed sweeps; refuses unless all three hold."""
    from score_session16 import score
    r = score(cc._REPO_ROOT / SESSION16)
    assert (r["control"], r["p4_primary"], r["p4_secondary"]) == ("HOLDS",) * 3, r
    p4, p5 = r["optima"]["p4"], r["optima"]["p5a"]
    equal = sum(1 for w in p4 if p4[w] == p5[w])
    below = sum(1 for w in p4 if p4[w] < p5[w])
    changed = sum(1 for w in p5 if r["optima"]["p2"][w] != p5[w])
    return r, len(r["p4_above"]), equal, below, changed


@claim("session16-both-arms", PAPER, "5.5.8")
def session16BothArms():
    r, above, equal, below, changed = _session16()
    return (f"Profile 4's median landed on its predicted {r['medians']['p4']:g} MHz with {above} of 12 "
            f"workloads above Profile 5's optima ({equal} equal, {below} below); the control's median "
            f"stayed at {r['medians']['p2']:g} MHz, with {changed} of 12 optima changed against the opening "
            f"Profile 5 suite ({len(r['p2_moved'])} against both) and {len(r['p5_repeat_changed'])} of 12 "
            f"between the two Profile 5 suites")


@claim("sub-session16-both-arms", SUBMISSION, "sub-5.3")
def subSession16BothArms():
    r, above, equal, below, changed = _session16()
    return (f"The lifted-floor median landed on its predicted {r['medians']['p4']:g} MHz, with {above} of 12 "
            f"workloads above their factory-floor optima ({equal} equal, {below} below); the upper-curve "
            f"edit left the median at {r['medians']['p2']:g} MHz and changed {changed} of 12 optima "
            f"against the opening factory-floor suite, while the two factory-floor suites differed at "
            f"{len(r['p5_repeat_changed'])} of 12")


# Section 17 (collected 2026-10-06): sampled power against NVML's integrated energy counter, stock.
ENERGY17 = "data/frequency-sweeps/5060ti-energy17-20261006"


@claim("sub-energy-counter", SUBMISSION, "sub-3")
def subEnergyCounter():
    """The registered comparison (both predictions FAILED), rendered from compare_energy_power."""
    import statistics
    from compare_energy_power import compare, expand
    sweeps = [s for s in compare(expand([str(cc._REPO_ROOT / ENERGY17)])) if s["points"]]
    diffs = [d for s in sweeps for d in s["diffs_pct"]]
    moved = [s for s in sweeps if s["optimum_sampled"] != s["optimum_energy"]]
    steps = set()
    for s in moved:
        grid = sorted(p["target"] for p in s["points"])
        steps.add(abs(grid.index(s["optimum_sampled"]) - grid.index(s["optimum_energy"])))
    if steps != {1}:
        return f"optimum moves of {sorted(steps)} grid steps"
    medians = {statistics.median(s[k] for s in sweeps) for k in ("optimum_sampled", "optimum_energy")}
    if len(medians) != 1:
        return f"the median optima differ: {sorted(medians)}"
    higher = "every point higher" if min(diffs) > 0 else f"{sum(d > 0 for d in diffs)} of {len(diffs)} points higher"
    return (f"NVML's integrated energy counter read a median {statistics.median(diffs):.2f}% higher for "
            f"the same timed work, {higher}; the median optimum was {medians.pop():g} MHz either way, but "
            f"{len(moved)} of {len(sweeps)} per-workload optima moved by one grid step")


# Sections 18 and 19 (collected 2026-10-07): six configurations, both power figures, a 20 Hz log.
SESSION19 = "data/frequency-sweeps/5060ti-session19-20261007"


@claim("sub-energy-counter-s19", SUBMISSION, "sub-3")
def subEnergyCounterS19():
    """Section 18's signed gap and section 19's verdicts; refuses unless every section 19 arm holds."""
    from score_power_fields import score as score18
    from score_session19 import GRID, LEGS, score as score19
    r18, r19 = score18(cc._REPO_ROOT / SESSION19), score19(cc._REPO_ROOT / SESSION19)
    if set(r19["verdicts"].values()) != {"HOLDS"}:
        return f"section 19 verdicts {r19['verdicts']}"
    gap = r18["against_energy"]["sampled2"]
    direction = "above" if gap > 0 else "below"
    counts = [len(r19["figures_differ"][leg]) for leg in LEGS]
    # How far each differing optimum moves (GPT Job 61: not always one grid step).
    steps = [abs(GRID.index(r19["optima"]["energy"][leg][w]) - GRID.index(r19["optima"]["sampled"][leg][w]))
             for leg in LEGS for w in r19["figures_differ"][leg]]
    one, most = sum(1 for s in steps if s == 1), max(steps)
    medians = ", ".join(f"{r19['medians']['energy'][leg]:g}" for leg in LEGS[:-1])
    return (f"the sampled figure read a median {abs(gap):.2f}% {direction} the counter, and recomputing "
            f"efficiency from the counter left every registered median optimum in place ({medians} and "
            f"{r19['medians']['energy'][LEGS[-1]]:g} MHz), while {min(counts)} to {max(counts)} of 12 "
            f"per-workload optima differed between the two figures, {one} of the {len(steps)} by one grid step "
            f"and the rest by up to {most}")


@claim("sub-energy-counter-total", SUBMISSION, "sub-3")
def subEnergyCounterTotal():
    """Exploratory, and the paper must say so: whole-session counter against integrated instant power."""
    from explore_power_fields import explore
    r = explore(cc._REPO_ROOT / SESSION19)
    gap = 100 * (r["counter_kj"] / r["instant_kj"] - 1)
    return (f"Over the whole {r['hours']:.0f}-hour session the counter's total was within "
            f"{abs(gap):.1f}% of the integrated instant reading")


SESSION20 = "data/frequency-sweeps/5060ti-session20-20261008"


@claim("sub-finegrid-s20", SUBMISSION, "sub-5.2")
def subFineGridS20():
    """Section 20's registered fine-grid test, both configurations; refuses unless all six hold."""
    from score_session20 import score as score20
    r = score20(cc._REPO_ROOT / SESSION20)
    if set(r["verdicts"].values()) != {"HOLDS"}:
        return f"section 20 verdicts {r['verdicts']}"
    s, p = r["results"]["stock"]["sampled"], r["results"]["p4"]["sampled"]
    return (f"the efficiency peak sat no more than one step above the floor's end for {s['f1_count']} of "
            f"{s['usable']} workloads on the stock curve and {p['f1_count']} of {p['usable']} on the edited one, "
            f"running at the floor's end cost a median {s['f2_median_loss_pct']:.2f}% and "
            f"{p['f2_median_loss_pct']:.2f}% of each workload's best efficiency, and efficiency 300 MHz higher "
            f"was lower for {s['f3_count']} and {p['f3_count']} of them. Only {s['within_one_step']} stock and "
            f"{p['within_one_step']} edited-curve peaks sat within one step of the floor's end")


SESSION21 = "data/frequency-sweeps/5060ti-session21-20261009"


@claim("sub-appworkloads-s21", SUBMISSION, "sub-5.2")
def subAppWorkloadsS21():
    """Section 21's registered repeat on four application workloads; refuses unless all seven hold."""
    from score_session21 import score as score21
    r = score21(cc._REPO_ROOT / SESSION21)
    if set(r["verdicts"].values()) != {"HOLDS"}:
        return f"section 21 verdicts {r['verdicts']}"
    s, p = r["results"]["stock"]["sampled"], r["results"]["p4"]["sampled"]
    c = r["results"]["stock-coarse"]["sampled"]
    coarse = sorted(set(c["argmax"].values()))
    where = f"all {c['usable']} peaked at {coarse[0]} MHz" if len(coarse) == 1 else \
        f"{c['within']} of {c['usable']} peaked at or below 1702 MHz"
    return (f"the peak sat no more than one step above the floor's end for {s['f1_count']} of {s['usable']} "
            f"on the stock curve and {p['f1_count']} of {p['usable']} on the edited one, running at the floor's "
            f"end cost a median {s['f2_median_loss_pct']:.2f}% and {p['f2_median_loss_pct']:.2f}%, and "
            f"efficiency 300 MHz higher was lower for {s['f3_count']} and {p['f3_count']} of them. On the "
            f"13-point stock grid {where}")


@claim("sub-abstract-census", SUBMISSION, "sub-abstract")
def subAbstractCensus():
    import build_data_manifest
    manifest = build_data_manifest.buildManifest(build_data_manifest.loadSessions())
    grade = [e for e in manifest if e["category"] == "dataset-grade"]
    verification = sum(1 for e in manifest if e["category"] == "verification")
    words = {3: "three", 4: "four", 5: "five"}
    cards = len({e["gpu"] for e in grade})
    return (f"We present {len(grade)} dataset-grade sweeps and {verification} early verification runs "
            f"on {words.get(cards, cards)} consumer NVIDIA cards")


def _abstractRange():
    import re
    byId = {c["claimId"]: c for c in CLAIMS if c["document"] == PAPER}
    if "2.7-declared-floor-pct" in byId:
        @claim("sub-abstract-public-range", SUBMISSION, "sub-abstract")
        def subAbstractPublicRange():
            pct = re.search(r"(\d+)%", byId["2.7-declared-floor-pct"]["render"]()).group(1)
            return f"reach only {pct}% of their declared default clocks"


_abstractRange()


# --------------------------------------------------------------------------------------------------
# 5.1's later 3070 Ti stock suites (GPT Job 98 F1, recomputed by Claude 2026-10-19 with the project's
# own gain function before the paper used them). The historical comparison bank above is ONE selected
# suite (2026-09-04, driver 610.88); these five are Session D (stock-1/4/6, one session, 617.14) and
# D2 (stock-7/9, a day later, upper targets shifted 15 MHz). Every path is a literal, as the module
# rules require: no helper resolves a card to a directory.

LATER_3070_STOCK = {
    "stock-1": {
        "copy": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-161519_rtx3070ti-sessiond-stock-1-copy_sweep.csv",
        "reduce": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-161959_rtx3070ti-sessiond-stock-1-reduce_sweep.csv",
        "softmax": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-162439_rtx3070ti-sessiond-stock-1-softmax_sweep.csv",
        "layernorm": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-162928_rtx3070ti-sessiond-stock-1-layernorm_sweep.csv",
        "bgemm32": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-163412_rtx3070ti-sessiond-stock-1-bgemm32_sweep.csv",
        "bgemm64": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-163931_rtx3070ti-sessiond-stock-1-bgemm64_sweep.csv",
        "bgemm128": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-164448_rtx3070ti-sessiond-stock-1-bgemm128_sweep.csv",
        "bgemm256": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-164942_rtx3070ti-sessiond-stock-1-bgemm256_sweep.csv",
        "bgemm1024": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-165501_rtx3070ti-sessiond-stock-1-bgemm1024_sweep.csv",
        "attention": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-170020_rtx3070ti-sessiond-stock-1-attention_sweep.csv",
        "conv": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-170555_rtx3070ti-sessiond-stock-1-conv_sweep.csv",
        "gemm": "rtx3070ti-sessiond-20260924/20260924-161512_rtx3070ti-sessiond-stock-1/20260924-171109_rtx3070ti-sessiond-stock-1-gemm_sweep.csv",
    },
    "stock-4": {
        "copy": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-202909_rtx3070ti-sessiond-stock-4-copy_sweep.csv",
        "reduce": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-203350_rtx3070ti-sessiond-stock-4-reduce_sweep.csv",
        "softmax": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-203830_rtx3070ti-sessiond-stock-4-softmax_sweep.csv",
        "layernorm": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-204321_rtx3070ti-sessiond-stock-4-layernorm_sweep.csv",
        "bgemm32": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-204807_rtx3070ti-sessiond-stock-4-bgemm32_sweep.csv",
        "bgemm64": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-205329_rtx3070ti-sessiond-stock-4-bgemm64_sweep.csv",
        "bgemm128": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-205850_rtx3070ti-sessiond-stock-4-bgemm128_sweep.csv",
        "bgemm256": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-210348_rtx3070ti-sessiond-stock-4-bgemm256_sweep.csv",
        "bgemm1024": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-210909_rtx3070ti-sessiond-stock-4-bgemm1024_sweep.csv",
        "attention": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-211432_rtx3070ti-sessiond-stock-4-attention_sweep.csv",
        "conv": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-212008_rtx3070ti-sessiond-stock-4-conv_sweep.csv",
        "gemm": "rtx3070ti-sessiond-20260924/20260924-202902_rtx3070ti-sessiond-stock-4/20260924-212526_rtx3070ti-sessiond-stock-4-gemm_sweep.csv",
    },
    "stock-6": {
        "copy": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-225049_rtx3070ti-sessiond-stock-6-copy_sweep.csv",
        "reduce": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-225531_rtx3070ti-sessiond-stock-6-reduce_sweep.csv",
        "softmax": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-230013_rtx3070ti-sessiond-stock-6-softmax_sweep.csv",
        "layernorm": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-230506_rtx3070ti-sessiond-stock-6-layernorm_sweep.csv",
        "bgemm32": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-230954_rtx3070ti-sessiond-stock-6-bgemm32_sweep.csv",
        "bgemm64": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-231519_rtx3070ti-sessiond-stock-6-bgemm64_sweep.csv",
        "bgemm128": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-232042_rtx3070ti-sessiond-stock-6-bgemm128_sweep.csv",
        "bgemm256": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-232543_rtx3070ti-sessiond-stock-6-bgemm256_sweep.csv",
        "bgemm1024": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-233105_rtx3070ti-sessiond-stock-6-bgemm1024_sweep.csv",
        "attention": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-233630_rtx3070ti-sessiond-stock-6-attention_sweep.csv",
        "conv": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-234207_rtx3070ti-sessiond-stock-6-conv_sweep.csv",
        "gemm": "rtx3070ti-sessiond-20260924/20260924-225042_rtx3070ti-sessiond-stock-6/20260924-234727_rtx3070ti-sessiond-stock-6-gemm_sweep.csv",
    },
    "stock-7": {
        "copy": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-083403_rtx3070ti-sessiond-stock-7-copy_sweep.csv",
        "reduce": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-083847_rtx3070ti-sessiond-stock-7-reduce_sweep.csv",
        "softmax": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-084329_rtx3070ti-sessiond-stock-7-softmax_sweep.csv",
        "layernorm": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-084822_rtx3070ti-sessiond-stock-7-layernorm_sweep.csv",
        "bgemm32": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-085309_rtx3070ti-sessiond-stock-7-bgemm32_sweep.csv",
        "bgemm64": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-085830_rtx3070ti-sessiond-stock-7-bgemm64_sweep.csv",
        "bgemm128": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-090352_rtx3070ti-sessiond-stock-7-bgemm128_sweep.csv",
        "bgemm256": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-090851_rtx3070ti-sessiond-stock-7-bgemm256_sweep.csv",
        "bgemm1024": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-091412_rtx3070ti-sessiond-stock-7-bgemm1024_sweep.csv",
        "attention": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-091934_rtx3070ti-sessiond-stock-7-attention_sweep.csv",
        "conv": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-092511_rtx3070ti-sessiond-stock-7-conv_sweep.csv",
        "gemm": "rtx3070ti-sessiond2-20260925/20260925-083357_rtx3070ti-sessiond-stock-7/20260925-093028_rtx3070ti-sessiond-stock-7-gemm_sweep.csv",
    },
    "stock-9": {
        "copy": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-104044_rtx3070ti-sessiond-stock-9-copy_sweep.csv",
        "reduce": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-104525_rtx3070ti-sessiond-stock-9-reduce_sweep.csv",
        "softmax": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-105005_rtx3070ti-sessiond-stock-9-softmax_sweep.csv",
        "layernorm": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-105456_rtx3070ti-sessiond-stock-9-layernorm_sweep.csv",
        "bgemm32": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-105942_rtx3070ti-sessiond-stock-9-bgemm32_sweep.csv",
        "bgemm64": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-110503_rtx3070ti-sessiond-stock-9-bgemm64_sweep.csv",
        "bgemm128": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-111024_rtx3070ti-sessiond-stock-9-bgemm128_sweep.csv",
        "bgemm256": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-111521_rtx3070ti-sessiond-stock-9-bgemm256_sweep.csv",
        "bgemm1024": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-112042_rtx3070ti-sessiond-stock-9-bgemm1024_sweep.csv",
        "attention": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-112605_rtx3070ti-sessiond-stock-9-attention_sweep.csv",
        "conv": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-113141_rtx3070ti-sessiond-stock-9-conv_sweep.csv",
        "gemm": "rtx3070ti-sessiond2-20260925/20260925-104037_rtx3070ti-sessiond-stock-9/20260925-113658_rtx3070ti-sessiond-stock-9-gemm_sweep.csv",
    },
}


def _laterGains():
    return {tag: cc._gainsOf(table) for tag, table in LATER_3070_STOCK.items()}


@claim("sub-5.1-later-3070-spread", SUBMISSION, "sub-5.1")
def subLater3070Spread():
    """Session D's three suites only: same session, driver and grid, so a within-session spread.
    D2 is left out of this figure because its grid moved (Job 98 calls the five-suite figure a
    sensitivity result, not a repeatability estimate)."""
    gains = _laterGains()
    session = ("stock-1", "stock-4", "stock-6")
    means = ", ".join(f"{statistics.mean(gains[t].values()):.1f}%" for t in session[:-1])
    last = f"{statistics.mean(gains[session[-1]].values()):.1f}%"
    names = list(gains[session[0]])
    spread = statistics.mean(max(gains[t][n] for t in session) - min(gains[t][n] for t in session)
                             for n in names)
    return (f"give means of {means} and {last}, and each workload's gain spans {spread:.1f} percentage "
            "points across them on average")


@claim("sub-5.1-later-3070-rank", SUBMISSION, "sub-5.1")
def subLater3070Rank():
    """All five later suites against the same pooled 5060 Ti ranking that gives -0.273, and their
    agreement with one another. U+2212 minus, as the paper sets negative correlations."""
    import itertools
    ref = cc._rankOf({n: statistics.mean(cc._gainsOf(t)[n] for t in cc.REPLICATES_5060)
                      for n in cc.SUITE_R1_SWEEPS})
    ranks = [cc._rankOf(g) for g in _laterGains().values()]
    cross = [cc._spearman(ref, r) for r in ranks]
    within = [cc._spearman(a, b) for a, b in itertools.combinations(ranks, 2)]
    sign = lambda v: f"{v:+.3f}".replace("-", "−")
    return (f"the card's five later stock suites give {sign(min(cross))} to {sign(max(cross))} against "
            f"the same 5060 Ti ranking, while agreeing with one another at {sign(min(within))} to "
            f"{sign(max(within))}")
