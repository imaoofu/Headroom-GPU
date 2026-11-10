"""Build a deterministic manifest of every sweep under data/, and reconcile it against the paper.

WHY THIS EXISTS
    The paper's abstract states "374 dataset-grade sweeps across four chips and three
    architectures". Nothing computed that number, no claim pinned it, and the only inventory in
    the repository was `tools/local-model/specs/sweep-root-inventory.md` - a PROMPT asking a local
    LLM to describe the tree. An inference step has no business in a file census: walking a
    directory is deterministic, reviewable in a diff, and cannot hallucinate a sweep that is not
    there.

    So this script answers three questions that were previously answered by hand, or not at all:

      1. What is actually on disk, per card, per configuration?
      2. Which files are dataset-grade, and BY WHAT RULE - stated, not implied?
      3. Does that agree with what the paper claims? If not, by how much?

WHAT IT DELIBERATELY DOES NOT DO
    It does not decide that the paper is right. The reconciliation prints the delta and leaves it
    to a human, because the honest failure mode here runs both ways: the classification below may
    be wrong, or the abstract may be. A script that adjusted its own rules until the total matched
    would be the exact thing `audit_claims.py` warns against - "a claim's job is to state what the
    data says, not to make the audit green".

USAGE
    python analysis/build_data_manifest.py                 # summary + reconciliation
    python analysis/build_data_manifest.py --write         # also write the manifest files
    python analysis/build_data_manifest.py --check         # exit 1 if the paper disagrees

⚠️ THE BOM. PowerShell writes some session JSONs as UTF-8 *with* a byte-order mark, and json.load
   on a plain utf-8 handle raises on them. Read every one with utf-8-sig. This is not hypothetical;
   it is how the first version of this script died.
"""

# Console output in this file is deliberately ASCII-only. A Windows console under the cp1252
# codepage raises UnicodeEncodeError on the emoji used freely elsewhere in this repository, and
# these tools are supposed to run on a shop machine with zero setup. The first run of this script
# crashed on its own warning marker.
import argparse
import collections
import csv
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SWEEPS = REPO_ROOT / "data" / "frequency-sweeps"
MANIFEST_JSON = REPO_ROOT / "data" / "MANIFEST.json"
MANIFEST_CSV = REPO_ROOT / "data" / "MANIFEST.csv"

# What the paper's abstract asserts. Kept here so the reconciliation compares against a stated
# figure rather than a remembered one; if the abstract changes, this must change with it and the
# mismatch is the point.
PAPER_CLAIMS = {
    "NVIDIA GeForce RTX 5060 Ti": 846,
    "NVIDIA GeForce RTX 3070 Ti": 137,
    "NVIDIA GeForce RTX 2060 SUPER": 91,
    "NVIDIA GeForce RTX 3060": 14,
}
PAPER_VERIFICATION_RUNS = 3
PAPER_TOTAL = 1091

# ---------------------------------------------------------------------------------------------
# CLASSIFICATION. Every exclusion names itself. A sweep is never dropped silently, and the reason
# travels into the manifest so a reader can disagree with a specific rule rather than with a
# total.
# ---------------------------------------------------------------------------------------------

# Directories whose README declares the WHOLE directory not dataset-grade, in those words.
# Listed explicitly rather than grepped, because a grep cannot tell "this directory is not
# dataset-grade" from "run 7 is discarded at one point" or from a cross-reference to another
# directory - and three directories contain exactly that kind of sentence. Prose is not a
# classifier; the review section of the report surfaces the ones a human still has to judge.
DECLARED_NOT_DATASET_DIRS = (
    "frequency-sweeps/driver-61664-probe-20260905/",
    "frequency-sweeps/identity-probes-20260908/",
    "frequency-sweeps/5060ti-xbar14-20261001/dryrun/",
    "frequency-sweeps/5060ti-deskload-20261003/",
)

# ⛔ THERE WAS A "kit-test" RULE HERE AND IT WAS WRONG. It excluded any session whose label
# contained "kittest", on the assumption that the substring meant the same thing as "kitverify".
# It does not. The two sweeps it caught -
#     oc-comparison-20260819/20260819-142844_5060ti-kittest-stock-gemm-stock
#     oc-comparison-20260819/20260819-143337_5060ti-kittest-stock-membw-stock
# - are the STOCK ARM of the stock-versus-tuned comparison that ROADMAP.md calls "the project's
# whole thesis in one comparison", and they are bound to STOCK_GEMM and STOCK_MEMBW_13PT in
# claims_consumer.py, where live claims read them. The label records that the run happened while
# the collection kit was being exercised; the DATA is the stock baseline.
#
# 🔑 Removing that rule is what made the abstract's 359 reconcile exactly. The paper was right and
# this file was wrong, which is the direction the reconciliation was built to allow - see the
# module docstring. **A label substring is not a classifier.** Check what reads a file before
# deciding it is not data.

EXCLUSION_RULES = [
    ("failed-invocation",
     lambda path, session: "failed-invocations" in path.as_posix(),
     "The workload never ran. Kept as evidence of the failure mode, never as data."),

    ("kit-verification",
     lambda path, session: "kitverify" in (session.get("session_label") or "").lower(),
     "A collection-kit shakedown on known hardware, run to test the KIT rather than the card."),

    ("declared-not-dataset-grade",
     lambda path, session: any(part in path.as_posix() for part in DECLARED_NOT_DATASET_DIRS),
     "The directory's own README declares the whole directory NOT DATASET-GRADE and says not to "
     "pool it with any suite or replicate."),

    ("tool-verification-3pt",
     lambda path, session: "verify-3pt" in (session.get("session_label") or "").lower(),
     "The three early three-point runs. The paper counts these SEPARATELY from the per-card "
     "totals, and data/frequency-sweeps/README.md says they must not be pooled with real sweeps."),
]


def classify(path, session):
    """Return (category, ruleName, why). Categories: dataset-grade, verification, excluded."""
    for name, predicate, why in EXCLUSION_RULES:
        if predicate(path, session):
            category = "verification" if name == "tool-verification-3pt" else "excluded"
            return category, name, why
    return "dataset-grade", "", ""


# ---------------------------------------------------------------------------------------------
# PROVENANCE. Not exclusions - warnings that travel with a row, because several of this project's
# retractions came from comparing runs whose collection conditions differed silently.
# ---------------------------------------------------------------------------------------------

def provenanceFlags(session):
    flags = []
    schema = session.get("schema_version") or "0.0.0"
    if schema < "0.3.2":
        flags.append("no-vram-record")
    if session.get("video_engines_allowed"):
        flags.append("video-engines-allowed")
    encoder = session.get("encoder_util_pct")
    decoder = session.get("decoder_util_pct")
    if encoder is None and decoder is None:
        flags.append("no-encoder-telemetry")
    elif (encoder or 0) > 0 or (decoder or 0) > 0:
        flags.append("encoder-active")
    baseline = session.get("baseline_util_pct")
    if baseline is not None and baseline > 5:
        flags.append(f"baseline-{baseline}pct")
    if session.get("applied_settings_declared") and schema < "0.3.0":
        flags.append("settings-declared-unverified")
    planned = session.get("frequencies_planned")
    measured = session.get("frequencies_measured")
    if planned and measured and measured < planned:
        flags.append(f"measured-{measured}-of-{planned}")
    return flags


def loadSessions():
    """Every sweep session JSON under data/frequency-sweeps, read BOM-tolerantly."""
    rows = []
    for path in sorted(SWEEPS.glob("**/*_sweep.json")):
        try:
            session = json.load(open(path, encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as error:
            rows.append({"path": path, "session": None, "error": str(error)})
            continue
        rows.append({"path": path, "session": session, "error": None})
    return rows


def buildManifest(rows):
    manifest = []
    for row in rows:
        path, session = row["path"], row["session"]
        relative = path.relative_to(REPO_ROOT).as_posix()
        if session is None:
            manifest.append({"path": relative, "category": "unreadable", "rule": "parse-error",
                             "why": row["error"], "gpu": "", "label": "", "schema": "",
                             "driver": "", "frequenciesMeasured": "", "flags": "",
                             "hasSamplesCsv": path.with_suffix(".csv").exists()})
            continue
        category, rule, why = classify(path, session)
        manifest.append({
            "path": relative,
            "category": category,
            "rule": rule,
            "why": why,
            "gpu": session.get("gpu_name", ""),
            "label": session.get("session_label", ""),
            "schema": session.get("schema_version", ""),
            "driver": session.get("driver_version", ""),
            "frequenciesMeasured": session.get("frequencies_measured", ""),
            "flags": ";".join(provenanceFlags(session)),
            "hasSamplesCsv": path.with_suffix(".csv").exists(),
        })
    return manifest


def integrityProblems(manifest):
    """Structural faults that are not about counting: orphans, missing READMEs, parse failures."""
    problems = []

    for entry in manifest:
        if entry["category"] == "unreadable":
            problems.append(f"UNREADABLE  {entry['path']}: {entry['why']}")
        elif not entry["hasSamplesCsv"]:
            problems.append(f"NO SAMPLES  {entry['path']} has no matching _sweep.csv")

    known = {entry["path"] for entry in manifest}
    for csvPath in sorted(SWEEPS.glob("**/*_sweep.csv")):
        jsonPath = csvPath.with_suffix(".json").relative_to(REPO_ROOT).as_posix()
        if jsonPath not in known:
            relative = csvPath.relative_to(REPO_ROOT).as_posix()
            problems.append(f"NO SESSION  {relative} has no matching _sweep.json, so its "
                            f"collection conditions are unrecorded")

    # Every investigation directory carries its own README - a convention that had already
    # drifted once, in two directories read by live claims.
    for directory in sorted(d for d in SWEEPS.iterdir() if d.is_dir()):
        if not (directory / "README.md").exists():
            problems.append(f"NO README   data/frequency-sweeps/{directory.name}/ has no README.md")

    return problems


def directoriesNeedingJudgement(manifest):
    """Directories whose README says 'not dataset-grade' yet whose sweeps are still counted.

    Deliberately reported rather than acted on. The phrase appears in three directories where it
    qualifies a single run or points at a different directory entirely, so acting on it would
    silently drop real data - the opposite of this script's purpose.
    """
    counted = collections.Counter(
        entry["path"].split("/")[2] for entry in manifest
        if entry["category"] == "dataset-grade" and entry["path"].count("/") > 2)
    flagged = []
    for directory in sorted(d for d in SWEEPS.iterdir() if d.is_dir()):
        readme = directory / "README.md"
        if not readme.exists():
            continue
        text = readme.read_text(encoding="utf-8", errors="replace").lower()
        if "not dataset-grade" not in text:
            continue
        if any(directory.name in part for part in DECLARED_NOT_DATASET_DIRS):
            continue
        if counted.get(directory.name):
            flagged.append((directory.name, counted[directory.name]))
    return flagged


def report(manifest, checkMode):
    byCategory = collections.Counter(entry["category"] for entry in manifest)
    datasetGrade = [e for e in manifest if e["category"] == "dataset-grade"]
    verification = [e for e in manifest if e["category"] == "verification"]
    byCard = collections.Counter(e["gpu"] for e in datasetGrade)

    print(f"[MANIFEST] {len(manifest)} sweep session files under data/frequency-sweeps.")
    print()
    for category, count in byCategory.most_common():
        print(f"[MANIFEST]   {category:<16} {count:>4}")
    print()

    print("[MANIFEST] Excluded sweeps, by the rule that excluded them. No sweep is dropped")
    print("[MANIFEST] silently; disagree with a rule rather than with a total.")
    byRule = collections.Counter(e["rule"] for e in manifest if e["category"] != "dataset-grade")
    for rule, count in byRule.most_common():
        why = next(e["why"] for e in manifest if e["rule"] == rule)
        print(f"[MANIFEST]   {rule:<24} {count:>3}  {why}")
    print()

    print("[MANIFEST] Dataset-grade sweeps by card:")
    for card, count in byCard.most_common():
        claimed = PAPER_CLAIMS.get(card)
        mark = "" if claimed is None else ("  == paper" if claimed == count
                                          else f"  != paper, which says {claimed}")
        print(f"[MANIFEST]   {card:<32} {count:>4}{mark}")
    print()

    measured = len(datasetGrade) + len(verification)
    print(f"[MANIFEST] RECONCILIATION against the abstract's stated figures:")
    print(f"[MANIFEST]   on disk : {len(datasetGrade)} dataset-grade + {len(verification)} "
          f"verification = {measured}")
    print(f"[MANIFEST]   paper   : {sum(PAPER_CLAIMS.values())} dataset-grade + "
          f"{PAPER_VERIFICATION_RUNS} verification = {PAPER_TOTAL}")
    delta = measured - PAPER_TOTAL
    if delta == 0:
        print("[MANIFEST]   They agree. The abstract's figure is reproducible from the tree.")
    else:
        print(f"[MANIFEST]   ** THEY DISAGREE BY {delta:+d}. **")
        print("[MANIFEST]   This script does NOT decide which is wrong, and must not be tuned")
        print("[MANIFEST]   until it matches. Either an exclusion rule above is wrong, or the")
        print("[MANIFEST]   abstract is. Resolve it by reading the rows, not by editing the rule.")
    print()

    ambiguous = directoriesNeedingJudgement(manifest)
    if ambiguous:
        print("[MANIFEST] Directories whose README mentions 'not dataset-grade' but which are NOT")
        print("[MANIFEST] excluded by any rule above. A human has to read these; the phrase may")
        print("[MANIFEST] apply to one run, or be a cross-reference to somewhere else.")
        for name, count in ambiguous:
            print(f"[MANIFEST]   {name:<34} {count:>3} sweep(s) currently counted as dataset-grade")
        print()

    problems = integrityProblems(manifest)
    if problems:
        print(f"[MANIFEST] {len(problems)} structural problem(s):")
        for problem in problems:
            print(f"[MANIFEST]   {problem}")
    else:
        print("[MANIFEST] No structural problems: every session has its samples file, every")
        print("[MANIFEST] samples file has its session, and every directory has a README.")
    print()

    flagged = [e for e in datasetGrade if e["flags"]]
    print(f"[MANIFEST] {len(flagged)} of {len(datasetGrade)} dataset-grade sweeps carry a "
          f"provenance flag.")
    flagCounts = collections.Counter(
        flag for entry in datasetGrade for flag in entry["flags"].split(";") if flag)
    for flag, count in flagCounts.most_common():
        print(f"[MANIFEST]   {flag:<28} {count:>4}")
    print()
    print("[MANIFEST] A flag is NOT a disqualification. It records a condition that differed, so")
    print("[MANIFEST] that a comparison drawn across it is made knowingly - several of this")
    print("[MANIFEST] project's corrections came from pairs whose conditions differed silently.")

    if checkMode:
        return 1 if (delta != 0 or problems) else 0
    return 0


CSV_FIELDS = ["path", "category", "rule", "gpu", "label", "schema", "driver",
              "frequenciesMeasured", "flags", "hasSamplesCsv", "why"]


def manifestCsvText(manifest):
    """The CSV exactly as --write saves it, so --check can compare the saved file with it."""
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for entry in manifest:
        writer.writerow({field: entry.get(field, "") for field in CSV_FIELDS})
    return buffer.getvalue()


def writeManifest(manifest):
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with open(MANIFEST_CSV, "w", newline="", encoding="utf-8") as handle:
        handle.write(manifestCsvText(manifest))
    print(f"[MANIFEST] Wrote {MANIFEST_JSON.relative_to(REPO_ROOT).as_posix()} and "
          f"{MANIFEST_CSV.relative_to(REPO_ROOT).as_posix()}.")


def savedManifestProblems(manifest):
    """Why the saved census files differ from the live one; an empty list means they match.

    Added 2026-09-29 (GPT Job 34): --check compared the live census with the paper but never with
    the SAVED files, which sat at 367 rows while the tree grew to 788. Extended the same day (GPT
    Job 35): the first version read only the JSON, so a changed or deleted CSV passed, and a BOM or
    malformed JSON crashed with a traceback instead of saying what was wrong.
    """
    problems = []
    jsonName = MANIFEST_JSON.relative_to(REPO_ROOT).as_posix()
    csvName = MANIFEST_CSV.relative_to(REPO_ROOT).as_posix()
    if not MANIFEST_JSON.exists():
        problems.append(f"{jsonName} is missing.")
    else:
        try:
            saved = json.loads(MANIFEST_JSON.read_text(encoding="utf-8-sig"))
        except ValueError as error:
            problems.append(f"{jsonName} is not valid JSON ({error}).")
        else:
            if saved != json.loads(json.dumps(manifest)):
                problems.append(f"{jsonName} ({len(saved)} rows) does not match the live census "
                                f"({len(manifest)} rows).")
    if not MANIFEST_CSV.exists():
        problems.append(f"{csvName} is missing.")
    else:
        savedCsv = MANIFEST_CSV.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        if savedCsv != manifestCsvText(manifest).replace("\r\n", "\n"):
            problems.append(f"{csvName} does not match the live census.")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true",
                        help="Write data/MANIFEST.json and data/MANIFEST.csv.")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if the tree disagrees with the paper or is structurally "
                             "inconsistent. For CI, once the two are reconciled.")
    args = parser.parse_args()

    if not SWEEPS.exists():
        print(f"[MANIFEST] {SWEEPS} does not exist. Nothing to inventory.")
        return 1

    manifest = buildManifest(loadSessions())
    status = report(manifest, args.check)
    if args.check and not args.write:
        problems = savedManifestProblems(manifest)
        if problems:
            print()
            for problem in problems:
                print(f"[MANIFEST] {problem}")
            print("[MANIFEST] Regenerate the saved census with --write.")
            status = 1
    if args.write:
        print()
        writeManifest(manifest)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
