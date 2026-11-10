def testResolutionClaimRefusesConfigurationsThatSeparate():
    """The subsection says no ranking among the three configurations is supported.

    That sentence is only true while the between-configuration spread stays below the
    within-configuration spread. Fed data where the configurations genuinely separate, the claim
    must refuse rather than render a tidy pair of percentages under prose that has become false.
    """
    import claims_consumer as cc

    grid = FINE_GRID
    mapping = {cc.CLEAN_CEILING_MEMBW: _fakeSweepRows(grid, [300.0] * 10)}
    # Repair tight around 300, split tight around 260: configurations far apart, replicates close.
    for path in cc.REPAIR_MEMBW_RUNS:
        mapping[path] = _fakeSweepRows(grid, [300.0] * 10)
    for path in cc.SPLIT_MEMBW_RUNS:
        mapping[path] = _fakeSweepRows(grid, [260.0] * 10)

    raised = False
    try:
        _withFakeSweep(mapping, cc.resolution)
    except ValueError:
        raised = True
    check("configurations that separate are refused", raised,
          "it rendered a no-ranking-supported sentence over data that ranks them")

    # And overlapping configurations still render, so the guard discriminates.
    for i, path in enumerate(cc.REPAIR_MEMBW_RUNS):
        mapping[path] = _fakeSweepRows(grid, [300.0 + 8 * (1 if i else -1)] * 10)
    for i, path in enumerate(cc.SPLIT_MEMBW_RUNS):
        mapping[path] = _fakeSweepRows(grid, [300.0 + 6 * (i - 1)] * 10)
    text = _withFakeSweep(mapping, cc.resolution)
    check("overlapping configurations still render", "sweeps together span" in text, f"got {text!r}")


"""
Known-answer checks for the claim auditor.

WHY THESE
    audit_claims.py exists to catch documents drifting away from data. A checker that cannot
    fail is worse than no checker, because it converts "nobody verified this" into "this is
    verified" without changing anything. So the checks below are mostly about making it FAIL,
    in each of the ways it is supposed to.

    Two properties matter more than the rest and are easy to lose in a refactor:

      - A claim matching TWICE must not pass. The engine's whole guarantee is that a claim
        pins one specific line; if the rendered string appears in two places, editing the
        intended line still leaves the claim green against the other copy. AMBIGUOUS exists
        for that and is asserted here.
      - Coverage must credit only PASSING claims. Crediting a failing claim would report a
        number as pinned in the same run that just proved it is not in the document at all.

    Section extraction and the noise filter are checked because the coverage report is the
    only signal for what ISN'T audited, and a filter that silently eats real numbers makes
    the gap invisible - which is the failure this whole module exists to prevent.

PROVENANCE
    Written directly, not delegated. Eleven deliberate mutations were introduced into
    audit_claims.py. TWO SURVIVED the first pass, and both were weaknesses in the checks
    rather than in the code:

      - "coverage does NOT credit a failing claim" used a failing claim whose number was not
        in the section at all, so the number stayed unpinned whether or not failing claims
        were credited. Rewritten to use a claim that renders a number the section DOES
        contain, inside a sentence the document does not.
      - "a sweep CSV with no target column raises" asserted only that the claim came back
        ERROR. Without the guard the claim still errors, on a KeyError from the lookup rather
        than the ValueError from the loader, so the guard could be deleted with the suite
        green. Rewritten to call sweep() directly and name the exception.

    Both of those are the same mistake: asserting an outcome that the mutation also produces.
    After the rewrite all eleven are caught:

      - occurrences == 1 relaxed to >= 1                    (ambiguity check)
      - AMBIGUOUS reported as PASS                          (ambiguity check)
      - normalise() made an identity function               (bold checks)
      - normalise() applied to the document only            (bold checks)
      - normalise() also stripping single '*'               (over-normalisation check)
      - readDocument dropping newline=""                    (CRLF check)
      - coverage crediting every claim, not just PASSes     (coverage check)
      - extractSection stopping at any later heading        (nesting check)
      - extractSection including its own heading line       (heading-excluded check)
      - the NOISE date pattern removed                      (noise check)
      - sweep() no longer raising on a missing target column (schema check)

    Delete analysis/__pycache__ between mutations; a same-length edit can leave stale bytecode
    running while the source on disk reads correct.
"""

import shutil
import sys
import tempfile
from pathlib import Path

import audit_claims

failures = []


def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"       {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")


# --------------------------------------------------------------------------------------
# A throwaway repository, so no check can touch the real documents or data
# --------------------------------------------------------------------------------------

SWEEP_HEADER = ("target_frequency_mhz,achieved_frequency_avg,lock_held,lock_miss_mhz,"
                "lock_miss_direction,power_avg_w,bench_throughput,bench_throughput_unit,"
                "bench_ok\r\n")

SWEEP_ROWS = (
    "1000,999.0,True,1.0,below,100.0,1000000000000,FLOP/s,True\r\n"
    "2000,1998.0,True,2.0,below,200.0,1800000000000,FLOP/s,True\r\n"
    # Overshoots its lock, so loadSweep must drop it and sweepRaw must keep it. This is the
    # run-7 shape: the cap was never applied and the card ran far above its target.
    "3000,4500.0,False,1500.0,above,300.0,2500000000000,FLOP/s,True\r\n"
)

DOCUMENT = (
    "# Title\r\n"
    "\r\n"
    "## 1 First section\r\n"
    "\r\n"
    "Power at the top point is 200.0 W, taken on 2026-08-21 and described in 5.7.3.\r\n"
    "The file is `run-3000.csv` and the gain is **+80.0%** over the low point.\r\n"
    "\r\n"
    "### 1.1 A nested subsection\r\n"
    "\r\n"
    "Nested text mentioning 42 belongs to section 1 as well as to 1.1.\r\n"
    "\r\n"
    "## 2 Second section\r\n"
    "\r\n"
    "This paragraph is outside section 1 and mentions 999 which must not be counted.\r\n"
    "\r\n"
    "Repeated line for the ambiguity check.\r\n"
    "Repeated line for the ambiguity check.\r\n"
)


def buildRepository():
    root = Path(tempfile.mkdtemp(prefix="audit-claims-test-"))
    sweeps = root / "data" / "frequency-sweeps" / "fake"
    sweeps.mkdir(parents=True)
    with open(sweeps / "run_sweep.csv", "w", newline="") as handle:
        handle.write(SWEEP_HEADER + SWEEP_ROWS)
    docs = root / "docs"
    docs.mkdir()
    with open(docs / "DOC.md", "w", newline="") as handle:
        handle.write(DOCUMENT)
    return root


def useRepository(root):
    """Point the engine at the throwaway repo and drop every cache.

    The caches are keyed by relative path, so without this a second case would read the first
    case's file contents from memory and pass for the wrong reason.
    """
    audit_claims.REPO_ROOT = root
    audit_claims._documentCache.clear()
    audit_claims._sweepCache.clear()


def makeClaim(render, claimId="test", document="docs/DOC.md", section=None):
    return {"claimId": claimId, "document": document, "section": section, "render": render}


def statusOf(render, **kwargs):
    return audit_claims.audit([makeClaim(render, **kwargs)])[0]["status"]


repository = buildRepository()
useRepository(repository)

SWEEP = "fake/run_sweep.csv"

# --------------------------------------------------------------------------------------
# The three outcomes
# --------------------------------------------------------------------------------------

check(
    "a rendering that appears exactly once passes",
    statusOf(lambda: "Power at the top point is 200.0 W") == "PASS",
)

check(
    "a rendering absent from the document fails",
    statusOf(lambda: "Power at the top point is 999.9 W") == "FAIL",
)

check(
    "a rendering that appears twice is AMBIGUOUS, not PASS",
    statusOf(lambda: "Repeated line for the ambiguity check.") == "AMBIGUOUS",
    "two matches mean the claim does not pin the line anyone thinks it pins",
)

check(
    "a render function that raises is reported as ERROR, not propagated",
    statusOf(lambda: 1 / 0) == "ERROR",
    "one broken claim must not abort the other 29",
)

check(
    "a missing document is an ERROR naming the file",
    audit_claims.audit([makeClaim(lambda: "x", document="docs/NOPE.md")])[0]["status"] == "ERROR",
)

# --------------------------------------------------------------------------------------
# Drift in each direction - the property the whole module is for
# --------------------------------------------------------------------------------------

def powerRender():
    return f"Power at the top point is {audit_claims.sweep(SWEEP)[2000]['power']:.1f} W"


check(
    "a claim rendered from the CSV matches the prose while they agree",
    statusOf(powerRender) == "PASS",
)

mutatedData = buildRepository()
with open(mutatedData / "data" / "frequency-sweeps" / "fake" / "run_sweep.csv",
          "w", newline="") as handle:
    handle.write(SWEEP_HEADER + SWEEP_ROWS.replace("2000,1998.0,True,2.0,below,200.0",
                                                   "2000,1998.0,True,2.0,below,222.0"))
useRepository(mutatedData)
check(
    "changing the DATA under unchanged prose fails the claim",
    statusOf(powerRender) == "FAIL",
    "the CSV now says 222.0 W and the document still says 200.0",
)

mutatedProse = buildRepository()
docPath = mutatedProse / "docs" / "DOC.md"
with open(docPath, "w", newline="") as handle:
    handle.write(DOCUMENT.replace("is 200.0 W", "is about 200 W"))
useRepository(mutatedProse)
check(
    "rewording the PROSE around an unchanged number fails the claim",
    statusOf(powerRender) == "FAIL",
    "an unpinnable number is the thing this module refuses to call verified",
)

useRepository(repository)

# --------------------------------------------------------------------------------------
# Normalisation: emphasis is presentation, everything else is content
# --------------------------------------------------------------------------------------

check(
    "a render without bold matches a document line that has it",
    statusOf(lambda: "the gain is +80.0% over the low point") == "PASS",
)

check(
    "a render WITH bold also matches, so claims may write it either way",
    statusOf(lambda: "the gain is **+80.0%** over the low point") == "PASS",
)

check(
    "normalisation does not strip single asterisks",
    audit_claims.normalise("*emphasis* and **strong**") == "*emphasis* and strong",
    "stripping single '*' would silently match italic text against plain",
)

# Whitespace is presentation for the same reason bold is: the documents are hard-wrapped, so a
# sentence breaks wherever the wrap falls. Without collapsing it a claim can only pin what fits
# on one line, and re-wrapping a paragraph - which changes nothing factual - would break every
# claim in it.
check(
    "a claim may span a line break in the document",
    statusOf(lambda: "described in 5.7.3. The file is `run-3000.csv`") == "PASS",
    "this text is split across two lines in the fixture; pinning it must still work",
)

check(
    "a claim may itself contain a newline where the document has a space, and vice versa",
    statusOf(lambda: "taken on 2026-08-21\nand described in 5.7.3.") == "PASS",
)

check(
    "a doubled space is tolerated",
    statusOf(lambda: "the  gain is +80.0% over the low point") == "PASS",
)

# The limit of the tolerance. Collapsing whitespace must not start matching text that differs
# in any character that is not whitespace, which is where every number lives.
check(
    "a changed digit still fails",
    statusOf(lambda: "the gain is +80.1% over the low point") == "FAIL",
)

check(
    "a missing word still fails",
    statusOf(lambda: "the gain is +80.0% over low point") == "FAIL",
    "collapsing whitespace must not collapse the words either",
)

check(
    "CRLF line endings survive the read, so multi-line renderings can match",
    "\r\n" in audit_claims.readDocument("docs/DOC.md"),
    "universal-newline translation would make every multi-line claim fail on Windows",
)

# --------------------------------------------------------------------------------------
# The loaders, and the excluded row in particular
# --------------------------------------------------------------------------------------

check(
    "sweep() drops the row whose lock overshot, reusing analyze_sweep's filter",
    sorted(audit_claims.sweep(SWEEP)) == [1000, 2000],
    f"got {sorted(audit_claims.sweep(SWEEP))}; the 3000 MHz row missed ABOVE",
)

check(
    "sweepRaw() keeps that row, so a claim can quote the failure",
    sorted(audit_claims.sweepRaw(SWEEP)) == [1000, 2000, 3000],
)

check(
    "sweepRaw() reports the miss direction and magnitude it was kept for",
    audit_claims.sweepRaw(SWEEP)[3000]["missDirection"] == "above"
    and audit_claims.sweepRaw(SWEEP)[3000]["missMhz"] == 1500.0,
)

noTargets = buildRepository()
with open(noTargets / "data" / "frequency-sweeps" / "fake" / "run_sweep.csv",
          "w", newline="") as handle:
    handle.write(SWEEP_HEADER.replace("target_frequency_mhz,", "")
                 + "".join(row.split(",", 1)[1] for row in SWEEP_ROWS.splitlines(True)))
useRepository(noTargets)

# Asserting only that the CLAIM errors is not enough: without the guard, sweep() returns
# {None: row} and the claim still errors, on a KeyError from the lookup instead. The check has
# to name the failure, or the guard can be deleted with the suite still green.
try:
    audit_claims.sweep(SWEEP)
    schemaFailure = "no exception"
except ValueError as error:
    schemaFailure = "ValueError" if "target_frequency_mhz" in str(error) else str(error)
except Exception as error:                            # noqa: BLE001 - reported below
    schemaFailure = type(error).__name__

check(
    "a sweep CSV with no target column raises ValueError rather than keying rows on None",
    schemaFailure == "ValueError",
    f"got {schemaFailure}; collapsing every row onto a single None key would corrupt "
    f"every claim built on that file",
)
useRepository(repository)

# --------------------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------------------

check(
    "signedPct renders a gain with an explicit plus",
    audit_claims.signedPct(1.017) == "+1.7%",
    f"got {audit_claims.signedPct(1.017)!r}",
)

check(
    "signedPct renders a loss with ASCII minus by default",
    audit_claims.signedPct(0.819) == "-18.1%",
    f"got {audit_claims.signedPct(0.819)!r}",
)

check(
    "signedPct can render U+2212 for the documents that use it",
    audit_claims.signedPct(0.819, minus=chr(0x2212)) == chr(0x2212) + "18.1%",
    f"got {audit_claims.signedPct(0.819, minus=chr(0x2212))!r}",
)

check(
    "a positive value is untouched by the minus substitution",
    audit_claims.signedPct(1.017, minus=chr(0x2212)) == "+1.7%",
    "replacing '-' on a string with no '-' must not corrupt it",
)

# --------------------------------------------------------------------------------------
# Section extraction and the coverage report
# --------------------------------------------------------------------------------------

body = audit_claims.extractSection(audit_claims.readDocument("docs/DOC.md"), "1")

check(
    "extractSection excludes its own heading line",
    "First section" not in body,
)

check(
    "extractSection runs THROUGH a deeper nested heading",
    "42 belongs to section 1" in body,
    "stopping at any later heading would silently halve the audited region",
)

check(
    "extractSection stops at the next heading of the same level",
    "999 which must not be counted" not in body,
)

check(
    "an unknown section id returns None rather than the whole document",
    audit_claims.extractSection(audit_claims.readDocument("docs/DOC.md"), "9.9") is None,
)

numbers = audit_claims.numbersIn(body)

check(
    "the noise filter removes dates",
    "2026" not in numbers,
    f"got {numbers}",
)

check(
    "the noise filter removes section cross-references",
    "5" not in numbers and "7" not in numbers,
    f"got {numbers}; '5.7.3' must not become three unpinned numbers",
)

check(
    "the noise filter removes numbers inside code spans",
    "3000" not in numbers,
    f"got {numbers}; `run-3000.csv` is a filename, not a measurement",
)

check(
    "real measurements survive the noise filter",
    "200.0" in numbers and "+80.0%" in numbers,
    f"got {numbers}",
)

passing = audit_claims.audit([makeClaim(
    lambda: "Power at the top point is 200.0 W", section="1")])

# The rendering CONTAINS 200.0, which is genuinely in the section, but does not match the
# document because of the wrong unit. That combination is what makes the check bite: if
# coverage credited failing claims it would mark 200.0 as pinned on the strength of a claim
# the same run reported as FAIL. A failing claim whose numbers are absent from the section
# would leave 200.0 unpinned either way and prove nothing.
failing = audit_claims.audit([makeClaim(
    lambda: "Power at the top point is 200.0 kW", section="1")])

check(
    "coverage counts a passing claim's numbers as pinned",
    "200.0" not in audit_claims.coverage(passing)[0]["unpinned"],
)

check(
    "coverage does NOT credit a failing claim",
    failing[0]["status"] == "FAIL"
    and "200.0" in audit_claims.coverage(failing)[0]["unpinned"],
    "a claim that just failed has not pinned anything, by definition",
)

check(
    "coverage flags a claim pointing at a section that does not exist",
    audit_claims.coverage(audit_claims.audit([makeClaim(
        lambda: "Power at the top point is 200.0 W", section="9.9")]))[0]["missing"],
)

check(
    "unauditedSections lists a numbered heading no claim references",
    ("docs/DOC.md", "2 Second section") in audit_claims.unauditedSections(
        {"docs/DOC.md"}, passing),
)

check(
    "unauditedSections does not list a section that has a claim",
    ("docs/DOC.md", "1 First section") not in audit_claims.unauditedSections(
        {"docs/DOC.md"}, passing),
)

# --------------------------------------------------------------------------------------
# Non-ASCII claims must survive being reported
# --------------------------------------------------------------------------------------

# Section 5.4's table uses U+2212 MINUS SIGN and U+2014 EM DASH, so claims covering it MUST
# render them - matching the document byte for byte is the entire mechanism. Printing them raw
# raises UnicodeEncodeError on a cp1252 console, which is what a plain `python` gets on Windows,
# and that killed the whole report rather than the one line that could not be shown.
audit_claims.makeConsoleSafe()

check(
    "makeConsoleSafe leaves stdout able to encode a minus sign without raising",
    (lambda: (chr(0x2212).encode(sys.stdout.encoding or "utf-8", errors=sys.stdout.errors),
              True)[1])(),
    "a console that cannot show U+2212 must degrade to an escape, not take the run down",
)

nonAscii = audit_claims.audit([makeClaim(lambda: "value is " + chr(0x2212) + "18.1%")])[0]
check(
    "a claim rendering non-ASCII is compared, not rejected",
    nonAscii["status"] == "FAIL" and chr(0x2212) in nonAscii["expected"],
    f"got {nonAscii['status']}; the character must reach the comparison intact",
)

# --------------------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------------------

registered = len(audit_claims.CLAIMS)


@audit_claims.claim("test-registration", "docs/DOC.md", "1")
def registeredClaim():
    return "Power at the top point is 200.0 W"


check(
    "the claim decorator registers exactly one claim and returns the function",
    len(audit_claims.CLAIMS) == registered + 1 and registeredClaim() is not None,
)

check(
    "the decorator records the id, document and section it was given",
    audit_claims.CLAIMS[-1]["claimId"] == "test-registration"
    and audit_claims.CLAIMS[-1]["section"] == "1",
)

for directory in (repository, mutatedData, mutatedProse, noTargets):
    shutil.rmtree(directory, ignore_errors=True)

# The summary and exit live at the very END of this file, deliberately.
#
# They used to sit here, in the middle, and a block of tests appended after them on 2026-08-23
# could report [PASS] lines while being unable to fail the suite: on success execution fell
# through and ran them, and on failure nothing re-read `failures`, so the process still exited 0.
# Six deliberate mutations of the code under test all survived. Anything added to this file must
# come BEFORE the summary; that is why the summary is last.


# ---------------------------------------------------------------------------------------------
# Provenance tracking, added 2026-08-23.
#
# The engine verified arithmetic and never provenance, so a claim comparing a clean sweep against
# a contaminated one passed green forever. Two such comparisons reached the paper and both were
# found by accident on the same day, not by any check.
#
# NOTE A REAL LIMITATION, because these tests would otherwise imply more than the feature does:
# the tiers describe RECORDED EVIDENCE, not actual conditions. A run taken with Instant Replay on
# but written by a schema that had no encoder field reads as `declared-unverified`, exactly like a
# clean run of the same vintage. That is why 5.4.4 - whose entire subject is contaminated versus
# clean - does NOT trip the mixed-provenance flag. The feature narrows the blind spot; it does not
# close it, and only a re-measurement can.
# ---------------------------------------------------------------------------------------------

REAL_REPO_ROOT = Path(__file__).resolve().parent.parent


def testProvenanceTiers():
    """Call provenanceOf for real, against a temp tree laid out the way it expects.

    The first version of this test reimplemented the classification inline and compared the copy
    against the expectation, which passes no matter what provenanceOf does. That is the mutation
    -survives-because-the-check-asserts-the-mutation's-own-outcome failure this file already
    records twice. Do not reintroduce it.
    """
    import tempfile, json as _json
    import audit_claims as ac

    cases = [
        ("quiet", {"encoder_util_pct": 0, "decoder_util_pct": 0}, ac.QUIET),
        ("busyenc", {"encoder_util_pct": 21, "decoder_util_pct": 0}, ac.BUSY),
        ("busydec", {"encoder_util_pct": 0, "decoder_util_pct": 2}, ac.BUSY),
        ("declared", {"applied_settings": "stock", "applied_settings_declared": True}, ac.DECLARED),
        ("bare", {"schema_version": "0.1.0"}, ac.UNKNOWN),
    ]
    saved = ac.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        sweeps = root / "data" / "frequency-sweeps"
        sweeps.mkdir(parents=True)
        try:
            ac.REPO_ROOT = root
            for name, payload, expected in cases:
                (sweeps / f"{name}_sweep.json").write_text(_json.dumps(payload), encoding="utf-8")
                ac._provenanceCache.clear()
                tier, why = ac.provenanceOf(f"{name}_sweep.csv")
                check(f"{name} classifies as {expected}", tier == expected, f"got {tier} ({why})")

            # A voltage join carries its parent sweep's conditions; it has no session of its own.
            ac._provenanceCache.clear()
            tier, _ = ac.provenanceOf("quiet_sweep_voltage.csv")
            check("a voltage join inherits its parent sweep's tier", tier == ac.QUIET, f"got {tier}")

            # No session JSON at all must not silently read as clean.
            ac._provenanceCache.clear()
            tier, _ = ac.provenanceOf("nothing_sweep.csv")
            check("a sweep with no session JSON is unknown, not quiet", tier == ac.UNKNOWN, f"got {tier}")
        finally:
            ac.REPO_ROOT = saved
            ac._provenanceCache.clear()


def testProvenanceReportSeparatesDeclaredFromSilent():
    import audit_claims as ac
    silent = {"claimId": "a", "provenanceTiers": [ac.QUIET, ac.UNKNOWN], "mixedProvenance": None}
    stated = {"claimId": "b", "provenanceTiers": [ac.QUIET, ac.UNKNOWN],
              "mixedProvenance": "deliberate: the contaminated-versus-clean comparison"}
    uniform = {"claimId": "c", "provenanceTiers": [ac.QUIET], "mixedProvenance": None}
    flagged, declared = ac.provenanceReport([silent, stated, uniform])
    check("a silent mix is flagged", [r["claimId"] for r in flagged] == ["a"],
          f"got {[r['claimId'] for r in flagged]}")
    check("a declared mix is not flagged", [r["claimId"] for r in declared] == ["b"],
          f"got {[r['claimId'] for r in declared]}")
    check("a uniform claim is neither", "c" not in [r["claimId"] for r in flagged + declared],
          "uniform claim was reported")


def testAuditRecordsEverySourceAClaimTouches():
    """The flag is only as good as the access log; an unrecorded read is an invisible source.

    REPO_ROOT is restored explicitly because an earlier test in this file repoints it at a
    fixture and never puts it back. Without that, this test errors on a claim that passes
    perfectly well on its own - which is how it failed the first time it was written.
    """
    import audit_claims as ac
    saved = ac.REPO_ROOT
    try:
        ac.REPO_ROOT = REAL_REPO_ROOT
        ac._documentCache.clear()
        ac._sweepCache.clear()
        import claims_consumer                          # noqa: F401 - registers claims
        results = ac.audit([c for c in ac.CLAIMS if c["claimId"] == "5.7.4-plateau-comparison"])
        check("the claim ran", len(results) == 1 and results[0]["status"] == "PASS",
              f"got {results[0]['detail'] if results else 'nothing'}")
        sources = results[0].get("sources") or []
        check("both sweeps it compares were recorded", len(sources) == 2, f"recorded {sources}")
        check("it recorded the repaired-curve sweep",
              any("curvefixed-membw" in s for s in sources), f"got {sources}")
        check("it recorded the tuned sweep",
              any("oc-membw-stock" in s for s in sources), f"got {sources}")
    finally:
        ac.REPO_ROOT = saved
        ac._documentCache.clear()
        ac._sweepCache.clear()




# ---------------------------------------------------------------------------------------------
# Stability-run readers, added 2026-08-24.
#
# WHY THEY EXIST. Section 5.7.6 quoted two sustained-load comparisons whose numbers came from
# three different aggregation windows inside one sentence - the split curve's gemm mean over all
# sixteen iterations, its membw mean over the five SOAK iterations alone, and the original tune's
# means over its eleven post-soak iterations - beneath prose declaring all of them post-soak.
# Every figure was a real measurement. The pairing was not, and nothing could see it, because the
# whole paragraph was unpinned prose.
#
# So `iterationsIn` takes the window as a required argument. These tests exist to keep it that
# way: if the window ever acquires a default, several of them stop being able to fail.
# ---------------------------------------------------------------------------------------------


def _writeStabilityRun(root, label, iterationRows, samples=None, session=None, protocol=None):
    """Lay out the four artifacts a protocol run leaves, under a temp REPO_ROOT."""
    import json as _json

    base = root / "data" / "stability-runs"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{label}_stability_protocol.json").write_text(
        _json.dumps(protocol if protocol is not None else {"protocol_version": "1.0.0"}),
        encoding="utf-8")
    (base / f"{label}_session.json").write_text(
        _json.dumps(session if session is not None else {"loaded_threshold_pct": 50}),
        encoding="utf-8")

    header = ("iteration,workload,phase_elapsed_s,throughput,unit,duration_s,temp_start_c,"
              "temp_peak_c,aborted,in_soak")
    lines = [header]
    for i, (workload, value, aborted, inSoak) in enumerate(iterationRows, start=1):
        lines.append(f'"{i}","{workload}","0","{value}","FLOP/s","1","40","50","{aborted}","{inSoak}"')
    (base / f"{label}_stability_iterations.csv").write_text("\n".join(lines) + "\n",
                                                            encoding="utf-8")

    sampleHeader = ("timestamp_iso,elapsed_seconds,sm_clock_mhz,memory_clock_mhz,power_draw_w,"
                    "temperature_c,gpu_utilization_pct,memory_utilization_pct,fan_speed_pct,"
                    "memory_used_mb,throttle_bitmask,throttle_reasons")
    rows = [sampleHeader]
    for clock, util, reasons in (samples if samples is not None else [(3000, 99, "None")]):
        rows.append(f"2026-08-24T00:00:00,1,{clock},14001,150,60,{util},50,40,1000,0x0,{reasons}")
    (base / f"{label}_samples.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return base


def testIterationWindowsPartitionTheRun():
    """soak and post-soak must be disjoint, cover the run, and give DIFFERENT answers.

    The last part is what makes the rest meaningful. A window argument that is accepted and then
    ignored would satisfy "disjoint" and "covers" trivially - both windows would return the same
    list - so the test asserts the three windows disagree on data built to make them disagree.
    """
    import audit_claims as ac

    saved = ac.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _writeStabilityRun(root, "windowtest", [
            ("gemm", 100.0, "False", "True"),        # soak
            ("gemm", 100.0, "False", "True"),        # soak
            ("gemm", 200.0, "False", "False"),       # post-soak
            ("gemm", 200.0, "False", "False"),       # post-soak
        ])
        try:
            ac.REPO_ROOT = root
            ac._sweepCache.clear()
            run = ac.stabilityRun("windowtest")
            soak = ac.iterationsIn(run, "gemm", ac.SOAK)
            post = ac.iterationsIn(run, "gemm", ac.POST_SOAK)
            whole = ac.iterationsIn(run, "gemm", ac.WHOLE_RUN)
            check("soak selects only the soak iterations", soak == [100.0, 100.0], f"got {soak}")
            check("post-soak selects only the rest", post == [200.0, 200.0], f"got {post}")
            check("whole-run is both", sorted(whole) == [100.0, 100.0, 200.0, 200.0], f"got {whole}")
            check("the windows do not agree with each other",
                  len({tuple(soak), tuple(post), tuple(whole)}) == 3,
                  "two windows returned the same selection")
        finally:
            ac.REPO_ROOT = saved
            ac._sweepCache.clear()


def testIterationWindowMustBeNamed():
    """A misspelt window has to raise, not return nothing.

    An unknown window that quietly selected zero rows would surface as a mean() of an empty
    sequence somewhere far from the mistake, which is the shape of bug this whole file is about.
    """
    import audit_claims as ac

    saved = ac.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _writeStabilityRun(root, "guardtest", [("gemm", 1.0, "False", "False")])
        try:
            ac.REPO_ROOT = root
            ac._sweepCache.clear()
            run = ac.stabilityRun("guardtest")
            raised = False
            try:
                ac.iterationsIn(run, "gemm", "postsoak")
            except ValueError:
                raised = True
            check("an unrecognised window raises", raised, "it was accepted silently")

            # And a window that is valid but empty for this workload must also raise rather than
            # hand back [] for someone to average.
            emptyRaised = False
            try:
                ac.iterationsIn(run, "gemm", ac.SOAK)
            except ValueError:
                emptyRaised = True
            check("a valid but empty window raises", emptyRaised, "an empty list was returned")
        finally:
            ac.REPO_ROOT = saved
            ac._sweepCache.clear()


def testAbortedIterationsAreExcluded():
    import audit_claims as ac

    saved = ac.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _writeStabilityRun(root, "abortedtest", [
            ("gemm", 100.0, "False", "False"),
            ("gemm", 0.5, "True", "False"),          # a failed iteration, not a slow one
        ])
        try:
            ac.REPO_ROOT = root
            ac._sweepCache.clear()
            values = ac.iterationsIn(ac.stabilityRun("abortedtest"), "gemm", ac.POST_SOAK)
            check("an aborted iteration is not a data point", values == [100.0], f"got {values}")
        finally:
            ac.REPO_ROOT = saved
            ac._sweepCache.clear()


def testLoadedSamplesUsesTheRunsOwnThreshold():
    """Read the threshold the logger recorded rather than assuming its default.

    The logger's threshold is configurable and its value is the difference between "the card was
    busy for 96.9% of the run" and a number that means nothing. Hardcoding 50 here would agree
    with every run taken so far and silently disagree with the first one that changed it.
    """
    import audit_claims as ac

    saved = ac.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _writeStabilityRun(root, "threshtest", [("gemm", 1.0, "False", "False")],
                           samples=[(3000, 95, "None"), (3000, 70, "None"), (800, 5, "GpuIdle")],
                           session={"loaded_threshold_pct": 80})
        try:
            ac.REPO_ROOT = root
            ac._sweepCache.clear()
            loaded = ac.loadedSamples(ac.stabilityRun("threshtest"))
            check("only samples above the recorded threshold count", len(loaded) == 1,
                  f"got {len(loaded)} at a threshold of 80")
        finally:
            ac.REPO_ROOT = saved
            ac._sweepCache.clear()


def testStabilityRunRefusesAnIncompleteRun():
    """All four artifacts are checked BEFORE any of them is parsed.

    Asserting only "it raises FileNotFoundError" would not test anything: open() raises that by
    itself when it reaches the missing file, so the check could be deleted and the test would
    still pass. That is the assert-an-outcome-the-mutation-also-produces failure recorded twice
    above, and a mutation run caught this test committing it.

    So the fixture makes the iterations CSV unparseable AND removes the telemetry. With the
    upfront check the reader reports the missing file; without it, it parses its way into a
    KeyError on the malformed CSV first and never mentions what is actually absent.
    """
    import audit_claims as ac

    saved = ac.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        base = _writeStabilityRun(root, "partialtest", [("gemm", 1.0, "False", "False")])
        (base / "partialtest_samples.csv").unlink()
        (base / "partialtest_stability_iterations.csv").write_text(
            'iteration,workload,aborted,in_soak\n"1","gemm","False","False"\n',
            encoding="utf-8")
        try:
            ac.REPO_ROOT = root
            ac._sweepCache.clear()
            error = None
            try:
                ac.stabilityRun("partialtest")
            except Exception as caught:                 # noqa: BLE001 - the type is the assertion
                error = caught
            check("a run missing an artifact is refused", error is not None, "it loaded anyway")
            check("it names the missing artifact rather than failing on a later one",
                  isinstance(error, FileNotFoundError) and "partialtest_samples.csv" in str(error),
                  f"got {type(error).__name__}: {error}")
        finally:
            ac.REPO_ROOT = saved
            ac._sweepCache.clear()


def testStabilityProvenanceTiers():
    """A protocol run that refuses to start on a busy encoder still has to WRITE DOWN what it saw.

    Protocol 1.0.0 did not, so its runs are declared-unverified rather than verified-quiet even
    though the guard demonstrably ran. That is the honest tier: the guarantee exists but the
    evidence does not, and this project has already recorded what happens when a tool cannot tell
    "verified fine" from "not verified at all".
    """
    import json as _json
    import audit_claims as ac

    cases = [
        ("quiet", {"encoder_util_pct": 0, "decoder_util_pct": 0, "applied_settings": "x"}, ac.QUIET),
        ("busy", {"encoder_util_pct": 14, "decoder_util_pct": 0, "applied_settings": "x"}, ac.BUSY),
        ("v100", {"protocol_version": "1.0.0", "applied_settings": "x"}, ac.DECLARED),
        ("bare", {"protocol_version": "1.0.0"}, ac.UNKNOWN),
    ]
    saved = ac.REPO_ROOT
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        base = root / "data" / "stability-runs"
        base.mkdir(parents=True)
        try:
            ac.REPO_ROOT = root
            for label, payload, expected in cases:
                (base / f"{label}_stability_protocol.json").write_text(_json.dumps(payload),
                                                                       encoding="utf-8")
                ac._provenanceCache.clear()
                tier, why = ac.provenanceOf(ac.STABILITY_PREFIX + label)
                check(f"a {label} protocol run classifies as {expected}", tier == expected,
                      f"got {tier} ({why})")

            ac._provenanceCache.clear()
            tier, _ = ac.provenanceOf(ac.STABILITY_PREFIX + "missing")
            check("a run with no protocol JSON is unknown, not quiet", tier == ac.UNKNOWN,
                  f"got {tier}")
        finally:
            ac.REPO_ROOT = saved
            ac._provenanceCache.clear()


def testSustainedComparisonRefusesMismatchedWindows():
    """The regression guard for the actual 5.7.6 defect.

    5.7.6-sustained-gemm compares two runs' post-soak means and raises if the two windows hold
    different numbers of iterations. That check is what would have caught the original sentence,
    where one side had eleven iterations and the other sixteen.
    """
    import audit_claims as ac

    saved = ac.REPO_ROOT
    try:
        ac.REPO_ROOT = REAL_REPO_ROOT
        ac._documentCache.clear()
        ac._sweepCache.clear()
        import claims_consumer as cc

        run = ac.stabilityRun(cc.SPLIT_RUN)
        post = len(ac.iterationsIn(run, "gemm", ac.POST_SOAK))
        whole = len(ac.iterationsIn(run, "gemm", ac.WHOLE_RUN))
        check("the two windows really do differ on the run 5.7.6 quotes", post != whole,
              f"both windows hold {post} iterations, so the mismatch guard cannot fire")

        # Force the mismatch the prose used to contain - one side short by an iteration - and
        # require the claim to refuse rather than average across unequal windows.
        original = list(run["iterations"])
        raised = False
        try:
            dropped = False
            trimmed = []
            for row in original:
                if not dropped and row["workload"] == "gemm" and not row["inSoak"]:
                    dropped = True
                    continue
                trimmed.append(row)
            run["iterations"] = trimmed
            check("the mutation actually shortened the window",
                  len(ac.iterationsIn(run, "gemm", ac.POST_SOAK)) == post - 1,
                  "the row was not removed, so the next check cannot fail")
            try:
                cc.sustainedGemm()
            except ValueError:
                raised = True
        finally:
            run["iterations"] = original
        check("comparing unequal post-soak counts raises", raised,
              "the claim rendered a number from mismatched windows")
    finally:
        ac.REPO_ROOT = saved
        ac._documentCache.clear()
        ac._sweepCache.clear()


# EVERY TEST BELOW THIS LINE MAY READ REAL REPOSITORY DATA.
#
# The fixture-based tests above call useRepository() to point the engine at a throwaway tree and
# do not put it back, so by this point REPO_ROOT is a temp directory that no longer exists. Three
# separate tests have been written since, each of which failed on its first run with a confusing
# "sweep CSV missing" against a file that is plainly present, and each of which was fixed by
# adding its own save/restore. Restoring once, here, is the fix for the class.
useRepository(REAL_REPO_ROOT)

testProvenanceTiers()
testProvenanceReportSeparatesDeclaredFromSilent()
testAuditRecordsEverySourceAClaimTouches()
testIterationWindowsPartitionTheRun()
testIterationWindowMustBeNamed()
testAbortedIterationsAreExcluded()
testLoadedSamplesUsesTheRunsOwnThreshold()
testStabilityRunRefusesAnIncompleteRun()
testStabilityProvenanceTiers()


# ---------------------------------------------------------------------------------------------
# Guards inside the 5.7.6 bandwidth claims, added 2026-08-24.
#
# Three of those claims carry a check that raises when the DATA stops supporting the sentence
# rather than merely changing its numbers - the split curve leading at a different number of
# points, the contamination signature inverting, the grid changing shape. A mutation run showed
# all three surviving deletion, because against today's data the guard condition is false and
# removing it changes nothing observable.
#
# That is the same trap this file records three times already: a check that cannot be observed to
# fail is not a check. These tests feed each guard the data it exists to reject, by substituting
# claims_consumer's `sweep` for the duration of the call.
# ---------------------------------------------------------------------------------------------

FINE_GRID = [1402, 1477, 1560, 1635, 1710, 1792, 1867, 1942, 2025, 2100]


def _fakeSweepRows(targets, throughputs, clocks=None, power=60.0):
    """A minimal sweep()-shaped dict: keyed by commanded target, one row each."""
    return {t: {"target": t,
                "mhz": float(t if clocks is None else clocks[i]),
                "power": power,
                "throughput": float(throughputs[i])}
            for i, t in enumerate(targets)}


def _withFakeSweep(mapping, call):
    """Run `call` with claims_consumer.sweep replaced by a lookup into `mapping`."""
    import claims_consumer as cc

    real = cc.sweep

    def stub(path):
        if path not in mapping:
            raise AssertionError(f"the claim read an unexpected file: {path}")
        return mapping[path]

    cc.sweep = stub
    try:
        return call()
    finally:
        cc.sweep = real


def testConfigurationRowAveragesEveryRun():
    """A configuration's reported mean must read EVERY sweep it has, not the first.

    This is the regression guard for the actual defect. Read individually the split-curve sweeps
    give -0.11%, -0.73% and -0.57% against the memory-only reference and the repair sweeps give
    -0.39% and +0.58%; the paper quoted a single one of them twice, on two different days.
    """
    import claims_consumer as cc

    for name, runs in (("split", cc.SPLIT_MEMBW_RUNS), ("repair", cc.REPAIR_MEMBW_RUNS)):
        check(f"the {name} curve is measured more than once", len(runs) >= 2,
              f"only {len(runs)} sweep(s)")

    # Runs that disagree by a wide margin but average to exactly 300 GB/s. Built for however many
    # sweeps the configuration currently has, so adding a fourth does not silently skip it - which
    # is what happened when the third was added and this fixture named only two.
    runs = cc.SPLIT_MEMBW_RUNS
    offsets = [(i - (len(runs) - 1) / 2) * 0.1 for i in range(len(runs))]
    mapping = {}
    for path, offset in zip(runs, offsets):
        # Bytes per second, because _r576bandMean renders GB/s - a fixture in bare units
        # renders 0.0 and the check would compare two zeroes and pass.
        mapping[path] = _fakeSweepRows(FINE_GRID, [300.0e9 * (1 + offset)] * 10)

    row = _withFakeSweep(mapping, lambda: cc._r576configRow("split curve", runs))
    # The mean column is bolded when a configuration has more than one sweep, so match that form.
    # Reading only the first run would render 270.0 here, which is what makes this discriminating.
    check("every run is averaged, not one picked", "**300.0**" in row,
          f"got {row!r}, which is one run rather than the mean of {len(runs)}")
    check("the sweep count is the real count", f"| {len(runs)} |" in row, f"got {row!r}")

    # And the fixture has to be capable of failing: each run alone is far from the mean.
    check("the fixture would expose a single-run read", abs(offsets[0]) > 0.05,
          "the runs planted were too similar for this check to mean anything")


def testCeilingComparisonRefusesASingleSweepPassedAsAString():
    """A configuration measured once has to say so, because the count is printed in the table.

    Passing a bare path would work by accident - a string is iterable - and would silently read
    one character as a filename. Refusing it is what keeps the "sweeps" column honest.
    """
    import claims_consumer as cc

    raised = False
    try:
        cc._r576configRow("repaired curve", cc.REPAIR_MEMBW_FINE)
    except TypeError:
        raised = True
    check("a bare path is refused", raised, "a single sweep was accepted as a sequence")

    # And a one-element LIST is fine - the guard rejects the wrong type, not a small sample.
    # Against a fabricated sweep rather than the real one, so this does not depend on REPO_ROOT.
    mapping = {cc.CLEAN_CEILING_MEMBW: _fakeSweepRows(FINE_GRID, [300.0e9] * 10)}
    row = _withFakeSweep(
        mapping, lambda: cc._r576configRow("memory-only (stock curve)", [cc.CLEAN_CEILING_MEMBW]))
    check("a single sweep passed as a list still renders", row.count("|") == 6, f"got {row!r}")
    check("a single sweep reports no spread", row.rstrip().endswith("| - |"), f"got {row!r}")


def testContaminationSignatureExcludesTheDipPoints():
    """The withdrawn signature figures must exclude the two known dips, or they mean nothing.

    This test used to assert that the claim REFUSED an inverted signature. That guard is gone
    along with the argument it protected: with the dips removed the two bands differ by 0.31
    points, which is flat, and 5.4.4's boundary is not inside this grid anyway. What is left worth
    testing is that the exclusion happens at all.
    """
    import claims_consumer as cc

    # new/old rising with frequency: the opposite of what capture software does.
    old = _fakeSweepRows(FINE_GRID, [100.0] * 10)
    new = _fakeSweepRows(FINE_GRID, [101.0, 101.0, 101.0, 101.0, 101.0,
                                     104.0, 104.0, 104.0, 104.0, 104.0])
    mapping = {cc.SPLIT_MEMBW_OLD: old}
    for path in cc.SPLIT_MEMBW_RUNS:
        mapping[path] = new
    text = _withFakeSweep(mapping, cc.contaminationSignature)
    check("the withdrawn signature still renders both bands", "against" in text,
          f"got {text!r}")

    # The dip points are EXCLUDED, so a value planted at 1867 must not reach the output.
    planted = dict(new)
    planted[1867] = {"target": 1867, "mhz": 1867.0, "power": 60.0, "throughput": 1.0}
    for path in cc.SPLIT_MEMBW_RUNS:
        mapping[path] = planted
    check("excluding the dip points changes nothing",
          _withFakeSweep(mapping, cc.contaminationSignature) == text,
          "a planted value at 1867 MHz reached the rendered figure")


def testClockMatchGuardRejectsAChangedGrid():
    """Two configurations on a ten-point grid is twenty comparisons. Anything else is a different
    measurement, and the sentence's "eighteen of the twenty points" would be wrong rather than
    merely stale."""
    import claims_consumer as cc

    short = [1402, 1477, 1560, 1635, 1710]
    mapping = {cc.CLEAN_CEILING_MEMBW: _fakeSweepRows(short, [300.0] * 5)}
    for path in cc.REPAIR_MEMBW_RUNS + cc.SPLIT_MEMBW_RUNS:
        mapping[path] = _fakeSweepRows(short, [300.0] * 5)
    raised = False
    try:
        _withFakeSweep(mapping, cc.clockMatch)
    except ValueError:
        raised = True
    check("a grid that is no longer ten points is refused", raised, "it rendered a number anyway")


testSustainedComparisonRefusesMismatchedWindows()


def testPerSweepReadingsRefusesAChangedRunCount():
    """The prose names three split and two repair readings. Any other count makes it false.

    Without the guard the claim would render four or five figures into a sentence introduced as
    three and two, and the audit would still pass on the fragment it pins.
    """
    import audit_claims as ac
    import claims_consumer as cc

    saved = cc.SPLIT_MEMBW_RUNS
    try:
        cc.SPLIT_MEMBW_RUNS = list(saved[:2])
        raised = False
        try:
            cc.perSweepReadings()
        except ValueError:
            raised = True
        check("a changed run count is refused", raised, "it rendered two readings as three")
    finally:
        cc.SPLIT_MEMBW_RUNS = saved

    # The guard must not refuse everything. REPO_ROOT is pinned because an earlier test in this
    # file repoints it at a fixture and leaves it there.
    savedRoot = ac.REPO_ROOT
    try:
        ac.REPO_ROOT = REAL_REPO_ROOT
        ac._sweepCache.clear()
        text = cc.perSweepReadings()
    finally:
        ac.REPO_ROOT = savedRoot
        ac._sweepCache.clear()
    check("the real run lists still render", "the two repair" in text, f"got {text!r}")


def testPointSpreadRefusesAChangedNumberOfUnreliablePoints():
    """The sentence names exactly two points that do not replicate. If a third appears it is false.

    Fed three noisy points, the claim must raise rather than print two of them and drop the rest,
    which is the shape of the "seven of ten" error this section already made once.
    """
    import claims_consumer as cc

    grid = FINE_GRID
    ceiling = _fakeSweepRows(grid, [300.0] * 10)
    # Three runs that agree everywhere except at three grid points.
    values = [[300.0] * 10 for _ in cc.SPLIT_MEMBW_RUNS]
    for column in (1, 5, 8):
        values[0][column] = 260.0
    mapping = {cc.CLEAN_CEILING_MEMBW: ceiling}
    for path, series in zip(cc.SPLIT_MEMBW_RUNS, values):
        mapping[path] = _fakeSweepRows(grid, series)

    raised = False
    try:
        _withFakeSweep(mapping, cc.pointSpread)
    except ValueError:
        raised = True
    check("three unreliable points are refused", raised, "it rendered a sentence naming two")

    # Two noisy points render, so the guard is discriminating rather than always raising.
    values = [[300.0] * 10 for _ in cc.SPLIT_MEMBW_RUNS]
    for column in (1, 5):
        values[0][column] = 260.0
    for path, series in zip(cc.SPLIT_MEMBW_RUNS, values):
        mapping[path] = _fakeSweepRows(grid, series)
    text = _withFakeSweep(mapping, cc.pointSpread)
    check("two unreliable points still render", "The two that do not are" in text, f"got {text!r}")



testConfigurationRowAveragesEveryRun()
testPerSweepReadingsRefusesAChangedRunCount()
testResolutionClaimRefusesConfigurationsThatSeparate()
testCeilingComparisonRefusesASingleSweepPassedAsAString()
testContaminationSignatureExcludesTheDipPoints()
testClockMatchGuardRejectsAChangedGrid()



print("\nthe not-dataset-grade marker must stand alone on a line")
# Regression test for 2026-09-11. The marker is what removes a directory from the published sweep
# count, and it has now been defeated TWICE by READMEs that discuss the convention instead of
# invoking it: once by matching "NOT DATASET-GRADE" as prose, and once by matching the exact HTML
# comment ANYWHERE in the file, so a README quoting the marker inside a code span - while
# explaining that it must NOT be applied - excluded its own four sweeps from a published number.
from claims_consumer import hasNotDatasetGradeMarker as _marker  # noqa: E402

check("a marker alone on its line is detected",
      _marker("# Title\n\n<!-- dataset-grade: no -->\n"))
check("leading and trailing whitespace around it still counts",
      _marker("   <!-- dataset-grade: no -->   "))
check("it is detected on the very first line",
      _marker("<!-- dataset-grade: no -->\nrest of the file"))
check("a README that merely QUOTES the marker is NOT excluded",
      not _marker("the `<!-- dataset-grade: no -->` marker is read in exactly one place"))
check("prose discussing the concept is not a marker",
      not _marker("## Why they are not dataset-grade\n\nn = 1 per workload."))
check("the marker with text after it on the same line does not count",
      not _marker("<!-- dataset-grade: no --> but see the correction above"))
check("a file with no marker at all is not excluded",
      not _marker("# An ordinary README\n\nTwelve sweeps, 13 of 13 frequencies."))

if failures:
    print(f"{len(failures)} check(s) failed.")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
