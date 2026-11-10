"""
Check that the numbers written in the prose still match the numbers in the CSVs.

WHY THIS EXISTS
    docs/PAPER_DRAFT.md is ~11,000 words citing eight frequency sweeps, and the data READMEs
    and ROADMAP.md restate many of the same figures. Nothing connected a sentence to the file
    it came from, so the failure mode was silent: a number could be mis-derived once and then
    copied forward, or a re-run could replace the data under a paragraph that still described
    the old result. Both happened.

      - "173% of theoretical peak" survived into a README because a probe sampled the memory
        clock at its idle P-state. Caught by noticing, not by any check.
      - A sweep was labelled `memonly` while the tuned profile was applied. Caught because the
        operator remembered, mid-run.
      - The gemm re-run under the repaired curve landed in a commit message and the roadmap,
        and the paper went on saying "the expected cost has not been measured" for a day.
      - The roadmap's "5-18% across 2317-2782 MHz" was computed from a run whose 1852 MHz row
        had overshot its lock by +1002.6 MHz. The real figure is up to 33.1% across
        1545-2782 MHz - a wider band and roughly double the effect.

    Every one of those is a claim that disagreed with the committed data. That is a mechanical
    property, so it should be checked mechanically.

HOW A CLAIM WORKS, AND WHY IT IS SHAPED THIS WAY
    A claim does NOT store an expected number. It stores a function that RENDERS the exact
    string the document should contain, computed from the CSVs at audit time, and the engine
    asserts that string appears in the document verbatim and exactly once.

    That single mechanism closes both directions of drift:

      - change the data (or fix a loader bug) and the rendered string no longer matches the
        prose, so the claim fails;
      - edit the prose and the prose no longer contains the rendered string, so the claim
        fails.

    Storing an expected value instead would only catch the first, and would need the value
    maintained in two places - which is the bookkeeping problem one level down.

    The consequence to understand before adding claims: THE RENDERED STRING IS THE
    SPECIFICATION. If a claim renders "+1.7%" the document must say "+1.7%", not "+1.70%" or
    "about 1.7%". That is deliberate. Prose that cannot be pinned to an exact rendering is
    prose whose number nobody can check.

WHAT THIS DOES NOT DO
    It does not verify anything no claim covers, and a green run is not a statement that the
    document is correct. The coverage report exists so that gap is visible rather than
    assumed: for every section that has at least one claim, it lists the numeric tokens NO
    claim pins. Sections with no claims at all are listed as unaudited.

USAGE
    python analysis/audit_claims.py
    python analysis/audit_claims.py --coverage      # also list unpinned numbers
    python analysis/audit_claims.py --filter 5.7.5
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from analyze_sweep import loadSweep

REPO_ROOT = Path(__file__).resolve().parent.parent

# Claims register themselves here at import time. Kept module-level rather than passed around
# so a claims module is a flat list of decorated functions with no wiring.
CLAIMS = []

_documentCache = {}
_sweepCache = {}
_provenanceCache = {}

# Files a claim touched while rendering. Populated by the loaders below, read and cleared by
# audit(). A claim never sees this; it exists so the engine can answer a question the claim
# itself cannot: were these numbers all measured under the same conditions?
_accessLog = set()

# What the run recorded about its own measurement conditions, in descending order of evidence.
# Deliberately NOT derived from the filename date. A date cutoff encodes an assumption about
# when the protocol changed; these tiers encode what each session actually wrote down.
QUIET = "verified-quiet"          # session JSON reports encoder AND decoder at 0%
BUSY = "video-engines-active"     # session JSON reports encoder or decoder above 0%
DECLARED = "declared-unverified"  # settings were declared, but no video-engine telemetry exists
UNKNOWN = "unknown"               # neither: predates schema 0.2.0, conditions unrecoverable

PROVENANCE_ORDER = [QUIET, DECLARED, BUSY, UNKNOWN]


def provenanceOf(relativePath):
    """Classify a sweep CSV by what its sibling session JSON recorded about conditions.

    WHY THIS EXISTS. On 2026-08-22 this project found that always-on capture software depressed
    measured throughput by 4.22% across 1237-2010 MHz and inflated run-to-run spread fivefold
    (paper 5.4.4). Half the repository's sweeps predate that finding. The claims engine verifies
    that a rendered number matches the document, and it will do that perfectly for a number
    computed by comparing a clean sweep against a contaminated one - which is exactly how two
    such comparisons survived into the paper and were both found by accident on 2026-08-23.

    Arithmetic was never the weak point. Provenance was, and nothing checked it.
    """
    if relativePath not in _provenanceCache:
        if relativePath.startswith(STABILITY_PREFIX):
            _provenanceCache[relativePath] = _stabilityProvenance(
                relativePath[len(STABILITY_PREFIX):])
            return _provenanceCache[relativePath]
        csvPath = REPO_ROOT / "data" / "frequency-sweeps" / relativePath
        # Voltage joins are derived artifacts; their conditions are the parent sweep's.
        stem = str(csvPath).replace("_sweep_voltage.csv", "_sweep.csv")
        jsonPath = Path(stem.replace("_sweep.csv", "_sweep.json"))
        tier, evidence = UNKNOWN, "no session JSON alongside the CSV"
        if jsonPath.exists():
            try:
                with open(jsonPath, encoding="utf-8-sig") as handle:
                    session = json.load(handle)
            except Exception as error:               # noqa: BLE001 - reported, not raised
                session = None
                evidence = f"session JSON unreadable: {type(error).__name__}"
            if session is not None:
                enc = session.get("encoder_util_pct")
                dec = session.get("decoder_util_pct")
                if enc is not None and dec is not None:
                    if enc == 0 and dec == 0:
                        tier, evidence = QUIET, "encoder 0%, decoder 0% at preflight"
                    else:
                        tier, evidence = BUSY, f"encoder {enc}%, decoder {dec}% at preflight"
                elif session.get("applied_settings_declared") or session.get("applied_settings"):
                    tier = DECLARED
                    evidence = "settings declared, but this schema records no video-engine telemetry"
                else:
                    tier = UNKNOWN
                    evidence = f"schema {session.get('schema_version', '?')} records neither"
        _provenanceCache[relativePath] = (tier, evidence)
    return _provenanceCache[relativePath]


def claim(claimId, document, section=None, mixedProvenance=None):
    """Register a function whose return value is the exact text the document must contain.

    mixedProvenance: a REASON string, when the claim deliberately compares runs measured under
    different conditions. Section 5.4.4 is the honest case - its entire subject is the difference
    between contaminated and clean runs, so a claim there that did NOT mix would be the broken
    one. Anything left unannotated is reported, not failed, because the engine cannot tell a
    deliberate comparison from an accidental one and should not pretend to.
    """
    def register(render):
        CLAIMS.append({
            "claimId": claimId,
            "document": document,
            "section": section,
            "render": render,
            "mixedProvenance": mixedProvenance,
        })
        return render
    return register


def readDocument(relativePath):
    if relativePath not in _documentCache:
        path = REPO_ROOT / relativePath
        if not path.exists():
            raise FileNotFoundError(f"audited document missing: {relativePath}")
        # newline="" so the file's own line endings survive. Every document here is CRLF, and
        # universal-newline translation would rewrite them to LF on read, so a claim rendering
        # a multi-line table would match text that is not what is on disk.
        # open(..., newline="") rather than Path.read_text(newline=""): read_text only grew a
        # newline argument in 3.13, and this repo runs 3.12.
        with open(path, encoding="utf-8", newline="") as handle:
            _documentCache[relativePath] = handle.read()
    return _documentCache[relativePath]


def sweep(relativePath):
    """Load a sweep CSV keyed by COMMANDED frequency, reusing analyze_sweep's row filter.

    Rows whose lock missed in the ABOVE direction are dropped by loadSweep, which is the
    behaviour this audit wants and the reason it is imported rather than reimplemented: the
    curvefixed gemm run has a row that overshot 1852 MHz by +1002.6 MHz, and an audit that
    silently included it would reproduce the exact class of error it exists to catch.
    """
    _accessLog.add(relativePath)
    if relativePath not in _sweepCache:
        path = REPO_ROOT / "data" / "frequency-sweeps" / relativePath
        if not path.exists():
            raise FileNotFoundError(f"sweep CSV missing: {relativePath}")
        byTarget = {}
        for row in loadSweep(path):
            if row["target"] is None:
                raise ValueError(f"{relativePath} has no target_frequency_mhz column")
            byTarget[row["target"]] = row
        if not byTarget:
            raise ValueError(f"{relativePath} yielded no usable rows")
        _sweepCache[relativePath] = byTarget
    return _sweepCache[relativePath]


def sweepRaw(relativePath):
    """Every row of a sweep CSV, including ones loadSweep drops.

    Needed because some claims are ABOUT the excluded rows - the paper documents a run whose
    1852 MHz point overshot its lock by +1002.6 MHz, and that number cannot be checked against
    a loader whose whole job is to remove it. Use sweep() for anything analytical; this is for
    quoting a failure.
    """
    _accessLog.add(relativePath)
    key = ("raw", relativePath)
    if key not in _sweepCache:
        path = REPO_ROOT / "data" / "frequency-sweeps" / relativePath
        if not path.exists():
            raise FileNotFoundError(f"sweep CSV missing: {relativePath}")
        rows = {}
        with open(path, encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                rows[int(float(raw["target_frequency_mhz"]))] = {
                    "target": int(float(raw["target_frequency_mhz"])),
                    "mhz": float(raw["achieved_frequency_avg"]),
                    "power": float(raw["power_avg_w"]),
                    "throughput": float(raw["bench_throughput"]),
                    "lockHeld": raw.get("lock_held") in ("True", "true"),
                    "missMhz": float(raw["lock_miss_mhz"]) if raw.get("lock_miss_mhz") else 0.0,
                    "missDirection": raw.get("lock_miss_direction", ""),
                }
        _sweepCache[key] = rows
    return _sweepCache[key]


# NVML clocks_throttle_reasons bits. Only the ones this project has actually observed or would
# need to recognise are named; an unknown bit is reported as its hex value rather than dropped,
# because a mask nobody has seen before is information, not noise.
THROTTLE_REASONS = {
    0x0001: "GpuIdle",
    0x0002: "ApplicationsClocksSetting",
    0x0004: "SwPowerCap",
    0x0008: "HwSlowdown",
    0x0010: "SyncBoost",
    0x0020: "SwThermalSlowdown",
    0x0040: "HwThermalSlowdown",
    0x0080: "HwPowerBrakeSlowdown",
    0x0100: "DisplayClockSetting",
}


def throttleReasons(relativePath):
    """Per-target set of decoded NVML throttle reasons, from a sweep CSV's throttle_masks_seen.

    Separate from sweep() because the column is not a per-point aggregate like the others: it is
    the SET of distinct masks seen while that point ran, semicolon-joined, so it does not reduce
    to one number and cannot share sweep()'s row shape.

    GpuIdle is kept rather than filtered. It appears at almost every point because the sampler
    catches the gap between the lock being set and the workload starting, so its presence means
    nothing - but its ABSENCE at the top targets of a power-limited run is a real observation,
    and a reader that silently dropped it would hide that.
    """
    _accessLog.add(relativePath)
    key = ("throttle", relativePath)
    if key not in _sweepCache:
        path = REPO_ROOT / "data" / "frequency-sweeps" / relativePath
        if not path.exists():
            raise FileNotFoundError(f"sweep missing: {relativePath}")
        rows = {}
        with open(path, encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                masks = [m for m in (raw.get("throttle_masks_seen") or "").split(";") if m.strip()]
                names = set()
                for mask in masks:
                    value = int(mask, 16)
                    if value == 0:
                        continue
                    for bit, name in THROTTLE_REASONS.items():
                        if value & bit:
                            names.add(name)
                    unknown = value & ~sum(THROTTLE_REASONS)
                    if unknown:
                        names.add(hex(unknown))
                rows[int(float(raw["target_frequency_mhz"]))] = names
        if not rows:
            raise ValueError(f"{relativePath} yielded no rows")
        _sweepCache[key] = rows
    return _sweepCache[key]


def voltageJoin(relativePath):
    """Load a *_voltage.csv produced by tools/frequency-sweep/join_hwinfo_voltage.py.

    Separate from sweep() because these are a different artifact with a different schema: they
    carry HWiNFO's core voltage and crossbar clock, which NVML does not expose at all, and they
    exist only for the runs where HWiNFO happened to be logging.
    """
    _accessLog.add(relativePath)
    key = ("voltage", relativePath)
    if key not in _sweepCache:
        path = REPO_ROOT / "data" / "frequency-sweeps" / relativePath
        if not path.exists():
            raise FileNotFoundError(f"voltage join missing: {relativePath}")
        rows = {}
        with open(path, encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                rows[int(float(raw["target"]))] = {
                    "target": int(float(raw["target"])),
                    "mhz": float(raw["achieved"]),
                    "voltage": float(raw["voltage"]),
                    "crossbar": float(raw["crossbar"]),
                }
        if not rows:
            raise ValueError(f"{relativePath} yielded no rows")
        _sweepCache[key] = rows
    return _sweepCache[key]


# --------------------------------------------------------------------------------------
# Stability protocol runs
# --------------------------------------------------------------------------------------
#
# A protocol run leaves four artifacts sharing one file stem: the harness verdict
# (_stability_protocol.json), the logger session summary (_session.json), the per-iteration
# throughputs (_stability_iterations.csv) and the one-second telemetry (_samples.csv). They are
# read together because no single one of them answers a question about the run on its own.

STABILITY_PREFIX = "stability-runs/"

# The three windows a run divides into. Named constants rather than bare strings so a typo is an
# AttributeError at import rather than an empty selection at audit time.
SOAK = "soak"                 # the thermal-soak iterations, EXCLUDED from the degradation test
POST_SOAK = "post-soak"       # everything after the soak: what the run actually certifies
WHOLE_RUN = "whole-run"       # both, for claims about the run rather than about the verdict

_WINDOWS = (SOAK, POST_SOAK, WHOLE_RUN)


def stabilityRun(label):
    """Load one stability-protocol run by the file stem its four artifacts share.

    e.g. stabilityRun("20260823-183256_splitcurve")
    """
    _accessLog.add(STABILITY_PREFIX + label)
    key = ("stability", label)
    if key not in _sweepCache:
        base = REPO_ROOT / "data" / "stability-runs"
        protocolPath = base / (label + "_stability_protocol.json")
        sessionPath = base / (label + "_session.json")
        iterationsPath = base / (label + "_stability_iterations.csv")
        samplesPath = base / (label + "_samples.csv")
        for path in (protocolPath, sessionPath, iterationsPath, samplesPath):
            if not path.exists():
                raise FileNotFoundError(f"stability run {label} is missing {path.name}")

        # utf-8-sig throughout: these files predate the BOM fix and every one of them carries a
        # byte-order mark that json.load and csv.DictReader both mis-read.
        with open(protocolPath, encoding="utf-8-sig") as handle:
            protocol = json.load(handle)
        with open(sessionPath, encoding="utf-8-sig") as handle:
            session = json.load(handle)

        rows = []
        with open(iterationsPath, encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                rows.append({
                    "iteration": int(raw["iteration"]),
                    "workload": raw["workload"],
                    "throughput": float(raw["throughput"]),
                    "unit": raw["unit"],
                    "aborted": raw["aborted"] in ("True", "true"),
                    "inSoak": raw["in_soak"] in ("True", "true"),
                })
        if not rows:
            raise ValueError(f"stability run {label} recorded no iterations")

        samples = []
        with open(samplesPath, encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                if not raw.get("sm_clock_mhz"):
                    continue                          # QUERY_FAILED rows carry no telemetry
                samples.append({
                    "smClock": float(raw["sm_clock_mhz"]),
                    "power": float(raw["power_draw_w"]),
                    "temperature": float(raw["temperature_c"]),
                    "utilisation": float(raw["gpu_utilization_pct"]),
                    "throttleReasons": raw.get("throttle_reasons", ""),
                })
        if not samples:
            raise ValueError(f"stability run {label} recorded no telemetry samples")

        _sweepCache[key] = {"label": label, "protocol": protocol, "session": session,
                            "iterations": rows, "samples": samples}
    return _sweepCache[key]


def iterationsIn(run, workload, window):
    """Throughputs from one workload phase of a run, restricted to `window`.

    THE WINDOW ARGUMENT HAS NO DEFAULT, ON PURPOSE. Paper 5.7.6 compared the split curve against
    the original tune under sustained load and drew three numbers from three different windows
    inside one sentence - the split curve's `gemm` mean over all sixteen iterations, its `membw`
    mean over the five SOAK iterations only, and the original tune's mean over its eleven
    post-soak iterations - beneath prose declaring all of them "post-soak means over eleven
    unlocked iterations each". Every individual figure was a real measurement of something. The
    pairing was still wrong, and it read as three tidy numbers.

    Requiring the window at the call site is the structural fix. The corrected numbers are the
    symptom; an aggregate whose window is implicit is the defect.
    """
    if window not in _WINDOWS:
        raise ValueError(f"window must be one of {_WINDOWS}, got {window!r}")
    values = []
    for row in run["iterations"]:
        if row["workload"] != workload or row["aborted"]:
            continue
        if window == SOAK and not row["inSoak"]:
            continue
        if window == POST_SOAK and row["inSoak"]:
            continue
        values.append(row["throughput"])
    if not values:
        raise ValueError(f"{run['label']} has no {workload} iterations in the {window} window")
    return values


def loadedSamples(run):
    """Telemetry samples the logger counted as loaded, by its own recorded threshold.

    The threshold is read from the session rather than assumed, and the GpuIdle throttle bit is
    deliberately not used for this: the driver reports it on every sample of a compute-only
    workload running at 98% utilisation. The logger documents that at length; this only has to
    avoid re-deriving it differently.
    """
    threshold = float(run["session"].get("loaded_threshold_pct", 50))
    return [s for s in run["samples"] if s["utilisation"] > threshold]


def _stabilityProvenance(label):
    """What a stability run recorded about its own measurement conditions.

    The protocol REFUSES TO START when the encoder or decoder reads above zero, so a completed
    run was quiet at preflight by construction - but until protocol 1.1.0 it did not write the
    readings down, and a guarantee that leaves no evidence behind cannot be audited. Runs
    predating that field are DECLARED, not QUIET, and that is the honest tier for them.
    """
    base = REPO_ROOT / "data" / "stability-runs"
    protocolPath = base / (label + "_stability_protocol.json")
    if not protocolPath.exists():
        return UNKNOWN, "no protocol JSON for this run"
    try:
        with open(protocolPath, encoding="utf-8-sig") as handle:
            protocol = json.load(handle)
    except Exception as error:                        # noqa: BLE001 - reported, not raised
        return UNKNOWN, f"protocol JSON unreadable: {type(error).__name__}"
    enc = protocol.get("encoder_util_pct")
    dec = protocol.get("decoder_util_pct")
    if enc is not None and dec is not None:
        if enc == 0 and dec == 0:
            return QUIET, "encoder 0%, decoder 0% at protocol preflight"
        return BUSY, f"encoder {enc}%, decoder {dec}% at protocol preflight"
    if protocol.get("applied_settings"):
        version = protocol.get("protocol_version", "?")
        return DECLARED, ("protocol " + str(version) + " refused to start on a busy video engine "
                          "but recorded no reading")
    return UNKNOWN, "protocol JSON records neither settings nor video-engine telemetry"


def signedPct(ratio, minus="-"):
    """Format a ratio-minus-one as a signed percentage, e.g. 1.017 -> '+1.7%'.

    `minus` exists because the documents disagree: code and the paper's 5.7 tables use ASCII
    '-', while the data READMEs and ROADMAP use U+2212. A claim renders whatever its own
    document actually uses; it is not this function's job to decide which is right.
    """
    value = (ratio - 1.0) * 100.0
    text = f"{value:+.1f}%"
    return text.replace("-", minus) if minus != "-" else text


def deltaPct(new, old, minus="-"):
    return signedPct(new / old, minus=minus)


BOLD = re.compile(r"\*\*")
WHITESPACE = re.compile(r"\s+")


def normalise(text):
    """Strip bold markers and collapse whitespace before matching.

    BOLD, because which numbers a section puts in bold is an editorial decision that changes as
    the prose is edited, and it is not a factual claim about the data. Without this, moving
    emphasis from one row of a table to another breaks a claim that is still perfectly true -
    and the fix would be to teach the claim WHICH rows deserve bold, putting an editorial
    judgement inside the checker.

    WHITESPACE, because the documents are hard-wrapped at ~100 characters and a sentence
    therefore breaks wherever the wrap happens to fall. Without this a claim can only pin text
    that fits on one line, so covering a sentence like "utilisation of 99.0% and 92.7% - and
    throughput of 342.3 and 342.3 GB/s" means splitting it into fragments chosen by where the
    line ends rather than by what the claim is about. Worse, re-wrapping a paragraph - which
    changes nothing factual - would break every claim in it.

    Both sides are normalised, so a claim may render the markers or not and may wrap or not.

    The cost: a claim cannot pin emphasis, and cannot distinguish one space from two. Both are
    the intended trade. What a claim still pins exactly is every character that is not
    whitespace or an asterisk pair, which is where the numbers live.
    """
    return WHITESPACE.sub(" ", BOLD.sub("", text)).strip()


def audit(claims):
    results = []
    for entry in claims:
        _accessLog.clear()
        try:
            expected = normalise(entry["render"]())
            text = normalise(readDocument(entry["document"]))
            occurrences = text.count(expected)
        except Exception as error:                    # noqa: BLE001 - reported, not raised
            results.append({**entry, "status": "ERROR", "expected": None,
                            "sources": sorted(_accessLog),
                            "detail": f"{type(error).__name__}: {error}"})
            continue
        sources = sorted(_accessLog)

        if occurrences == 1:
            status, detail = "PASS", expected
        elif occurrences == 0:
            status = "FAIL"
            detail = f"document does not contain: {expected!r}"
        else:
            # More than one match means the claim is not pinning the line anyone thinks it is,
            # so a change to the intended line would still pass against the other copy.
            status = "AMBIGUOUS"
            detail = f"{occurrences} occurrences of {expected!r}; anchor is not unique"
        tiers = {provenanceOf(s)[0] for s in sources}
        results.append({**entry, "status": status, "expected": expected, "detail": detail,
                        "sources": sources, "provenanceTiers": sorted(tiers)})
    return results


def provenanceReport(results):
    """Claims whose numbers were computed across runs measured under different conditions."""
    flagged, declared = [], []
    for r in results:
        tiers = r.get("provenanceTiers") or []
        if len(tiers) < 2:
            continue
        (declared if r.get("mixedProvenance") else flagged).append(r)
    return flagged, declared


# --------------------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------------------

HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)

# Stripped before numbers are extracted, because these are not measurements and counting them
# as unpinned would bury the real gaps in noise.
NOISE = [
    re.compile(r"`[^`]*`"),                        # inline code, including file names
    re.compile(r"\[[^\]]*\]\([^)]*\)"),            # markdown links
    re.compile(r"\d{4}-\d{2}-\d{2}"),              # dates
    re.compile(r"\b\d+\.\d+(?:\.\d+)+\b"),         # section cross-references, e.g. 5.7.3
    re.compile(r"\(\d+\.\d+\)"),                   # parenthesised section refs, e.g. "(5.6)"
]

NUMBER = re.compile("[+\\-\u2212]?\\d+(?:\\.\\d+)?%?")


def headingId(sectionId):
    """The heading a claim's section id names. Submission claims use a "sub-" namespace (sub-5.2,
    sub-abstract) so their ids never collide with the long draft's; the heading itself is "5.2 ..."
    or "Abstract". Without this the coverage report said SECTION NOT FOUND for every submission
    section (GPT Job 92)."""
    if sectionId.startswith("sub-"):
        sectionId = sectionId[len("sub-"):]
        return "Abstract" if sectionId == "abstract" else sectionId
    return sectionId


def extractSection(text, sectionId):
    """Return the body under the heading whose title starts with sectionId, heading excluded."""
    sectionId = headingId(sectionId)
    matches = list(HEADING.finditer(text))
    for index, match in enumerate(matches):
        title = match.group(2).strip()
        if not title.startswith(sectionId):
            continue
        level = len(match.group(1))
        start = match.end()
        for later in matches[index + 1:]:
            if len(later.group(1)) <= level:
                return text[start:later.start()]
        return text[start:]
    return None


def numbersIn(text):
    stripped = text
    for pattern in NOISE:
        stripped = pattern.sub(" ", stripped)
    return NUMBER.findall(stripped)


def coverage(results):
    """For each audited section, the numeric tokens no passing claim pins."""
    bySection = {}
    for entry in results:
        if not entry["section"]:
            continue
        bySection.setdefault((entry["document"], entry["section"]), []).append(entry)

    report = []
    for (document, sectionId), entries in sorted(bySection.items()):
        body = extractSection(readDocument(document), sectionId)
        if body is None:
            report.append({"document": document, "section": sectionId,
                           "missing": True, "unpinned": [], "total": 0})
            continue
        # Only PASSING claims count as pinning anything. A failing claim's rendered string is
        # by definition not in the document, so crediting it would report coverage the audit
        # has just finished disproving.
        pinned = " ".join(e["expected"] for e in entries
                          if e["status"] == "PASS" and e["expected"])
        pinnedNumbers = set(numbersIn(pinned))
        found = numbersIn(body)
        unpinned = [n for n in found if n not in pinnedNumbers]
        report.append({"document": document, "section": sectionId, "missing": False,
                       "unpinned": unpinned, "total": len(found)})
    return report


def unauditedSections(documents, results):
    """Numbered headings in the audited documents that no claim references at all."""
    audited = {(e["document"], headingId(e["section"])) for e in results if e["section"]}
    out = []
    for document in sorted(documents):
        for match in HEADING.finditer(readDocument(document)):
            title = match.group(2).strip()
            sectionId = title.split()[0] if title else ""
            if not re.match(r"^\d+(\.\d+)*$", sectionId):
                continue
            if (document, sectionId) not in audited:
                out.append((document, title))
    return out


def makeConsoleSafe():
    """Stop a non-ASCII claim from killing the whole report.

    Claims render whatever the document contains, and the document contains U+2212 MINUS SIGN
    and U+2014 EM DASH - section 5.4's table uses both. Printing those raw raises
    UnicodeEncodeError on a cp1252 console, which is what a plain `python` on Windows gets
    unless the code page has been changed, and the failure takes out every remaining claim
    rather than the one that could not be shown.

    CLAUDE.md's rule is that printed output stays ASCII. That cannot apply to a rendered claim,
    whose whole purpose is to be byte-identical to the document, so the next best thing is to
    degrade rather than crash: a console that cannot show U+2212 gets the escape instead.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(errors="backslashreplace")


def main():
    makeConsoleSafe()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--filter", default="",
                        help="Only run claims whose id contains this substring.")
    parser.add_argument("--coverage", action="store_true",
                        help="Also list numbers in audited sections that no claim pins.")
    parser.add_argument("--provenance", action="store_true",
                        help="Report what each claim's source runs recorded about measurement "
                             "conditions, and every audited section's mix of them.")
    args = parser.parse_args()

    import claims_consumer                             # noqa: F401 - registers claims
    import claims_crosschip                            # noqa: F401 - registers claims
    import claims_datasets                             # noqa: F401 - registers claims
    import claims_reference                            # noqa: F401 - registers claims
    import claims_repo                                 # noqa: F401 - registers claims
    import claims_submission                           # noqa: F401 - registers claims (after claims_consumer)

    selected = [c for c in CLAIMS if args.filter in c["claimId"]]
    if not selected:
        print(f"No claims match --filter {args.filter!r}. {len(CLAIMS)} registered.")
        return 1

    results = audit(selected)
    width = max(len(r["claimId"]) for r in results)
    for result in results:
        print(f"[{result['status']:>9}] {result['claimId']:<{width}}  {result['detail']}")

    bad = [r for r in results if r["status"] != "PASS"]
    print(f"\n{len(results) - len(bad)} of {len(results)} claims verified against the CSVs.")

    # Reported unconditionally. A cross-condition comparison is invisible in a green run - that
    # is exactly why two of them went unnoticed until 2026-08-23 - so it does not hide behind a flag.
    flagged, declaredMix = provenanceReport(results)
    if flagged:
        print("")
        print(f"  ! {len(flagged)} claim(s) compute across runs measured under DIFFERENT conditions, without saying so:")
        for r in flagged:
            print(f"      {r['claimId']}  [{', '.join(r['provenanceTiers'])}]")
            for s in r["sources"]:
                tier, why = provenanceOf(s)
                print(f"          {tier:<20s} {s.split('/')[-1]}  ({why})")
        print('      Pass mixedProvenance="reason" to claim() if the comparison is deliberate.')
    if declaredMix:
        print("")
        print(f"  {len(declaredMix)} claim(s) mix conditions deliberately and say why:")
        for r in declaredMix:
            print(f"      {r['claimId']}: {r['mixedProvenance']}")

    if args.provenance:
        print("")
        print("--- provenance: what each audited section's sources recorded ---")
        bySection = {}
        for r in results:
            key = f"{r['document']} {r['section']}"
            bySection.setdefault(key, set()).update(r.get("sources") or [])
        for key in sorted(bySection):
            tiers = {}
            for s in bySection[key]:
                tiers.setdefault(provenanceOf(s)[0], []).append(s.split("/")[-1])
            summary = "  ".join(f"{k}:{len(tiers[k])}" for k in PROVENANCE_ORDER if k in tiers)
            print(f"  {key}: {summary or 'no sweep sources'}")
            for tier in PROVENANCE_ORDER:
                for name in sorted(tiers.get(tier, [])):
                    print(f"      {tier:<20s} {name}")

    if args.coverage:
        print("\n--- coverage: numbers in audited sections that NO claim pins ---")
        for entry in coverage(results):
            where = f"{entry['document']} {entry['section']}"
            if entry["missing"]:
                print(f"  {where}: SECTION NOT FOUND")
                continue
            pinned = entry["total"] - len(entry["unpinned"])
            print(f"  {where}: {pinned}/{entry['total']} pinned")
            if entry["unpinned"]:
                print(f"      unpinned: {' '.join(entry['unpinned'])}")
        stray = unauditedSections({c["document"] for c in selected}, results)
        if stray:
            print(f"\n  {len(stray)} numbered section(s) in audited documents have NO claims:")
            for document, title in stray:
                print(f"      {document}: {title}")

    if bad:
        print(f"\n{len(bad)} claim(s) did not verify.")
        return 1
    return 0


if __name__ == "__main__":
    # Running this file directly binds it as `__main__`. A claims module then does
    # `from audit_claims import claim`, which imports a SECOND copy of this file under its real
    # name, and every claim registers into THAT copy's CLAIMS list - leaving the one `main()`
    # can see permanently empty. The symptom is "0 registered" with the claims file plainly
    # sitting next to it.
    #
    # Re-dispatching through the named module makes the two copies agree on which registry is
    # real. Do not "simplify" this back to sys.exit(main()).
    from audit_claims import main as entryPoint

    sys.exit(entryPoint())
