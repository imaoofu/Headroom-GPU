"""Checks for build_data_manifest.py.

The classification rules are the part worth testing. They are the kind of logic that fails
silently - a rule that stops matching drops real sweeps out of the count and the total still
looks plausible, which is precisely the failure this repository keeps finding elsewhere.

Every check here runs against SYNTHETIC sessions rather than the real tree, so a check cannot
start passing because the data changed. The two that do touch the real tree are marked, and they
assert invariants rather than totals - a totals assertion would go stale every collection run.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_data_manifest as manifest

passed = 0


def check(description, condition):
    global passed
    if condition:
        passed += 1
        print(f"  [PASS] {description}")
    else:
        print(f"  [FAIL] {description}")
        raise AssertionError(description)


def session(**overrides):
    base = {"session_label": "5060ti-suite-gemm", "gpu_name": "NVIDIA GeForce RTX 5060 Ti",
            "schema_version": "0.3.3", "driver_version": "616.56", "frequencies_planned": 13,
            "frequencies_measured": 13, "encoder_util_pct": 0, "decoder_util_pct": 0,
            "baseline_util_pct": 2, "video_engines_allowed": False}
    base.update(overrides)
    return base


print("classification - every exclusion names itself")

category, rule, why = manifest.classify(Path("data/frequency-sweeps/x/y_sweep.json"), session())
check("an ordinary suite sweep is dataset-grade", category == "dataset-grade")
check("a dataset-grade sweep carries no rule", rule == "")

category, rule, _ = manifest.classify(
    Path("data/frequency-sweeps/rtx2060s-20260912/failed-invocations/a_sweep.json"), session())
check("a failed invocation is excluded", category == "excluded")
check("...and names the rule that excluded it", rule == "failed-invocation")

category, rule, _ = manifest.classify(Path("x/y_sweep.json"),
                                      session(session_label="5060ti-kitverify-idle-gemm"))
check("a kit-verification run is excluded", category == "excluded" and rule == "kit-verification")

# ⛔ REGRESSION GUARD. A "kit-test" rule here excluded these two on the substring "kittest",
# and it was wrong: they are the STOCK ARM of the stock-versus-tuned comparison, bound to
# STOCK_GEMM and STOCK_MEMBW_13PT in claims_consumer.py where live claims read them. Excluding
# them put the manifest two sweeps below the paper and made a correct abstract look wrong.
for label in ("5060ti-kittest-stock-gemm-stock", "5060ti-kittest-stock-membw-stock"):
    category, rule, _ = manifest.classify(
        Path("data/frequency-sweeps/oc-comparison-20260819/x_sweep.json"),
        session(session_label=label))
    check(f"{label} is DATASET-GRADE - a label substring is not a classifier",
          category == "dataset-grade" and rule == "")

category, rule, _ = manifest.classify(Path("x/y_sweep.json"), session(session_label="verify-3pt"))
check("a three-point verification run is its OWN category, not 'excluded' - the paper counts "
      "these separately", category == "verification" and rule == "tool-verification-3pt")

for directory in manifest.DECLARED_NOT_DATASET_DIRS:
    category, rule, _ = manifest.classify(Path("data/" + directory + "a_sweep.json"), session())
    check(f"a sweep in {directory.split('/')[-2]} is excluded by its README's declaration",
          category == "excluded" and rule == "declared-not-dataset-grade")

print()
print("classification - rules must not fire on things that merely resemble them")

category, _, _ = manifest.classify(Path("x/y_sweep.json"),
                                   session(session_label="5060ti-suite-verify-later"))
check("'verify' alone does not trigger the three-point rule - it needs 'verify-3pt'",
      category == "dataset-grade")

category, _, _ = manifest.classify(Path("data/frequency-sweeps/suite-r7/a_sweep.json"), session())
check("a directory NOT in the declared list is not excluded by proximity",
      category == "dataset-grade")

print()
print("provenance flags - a flag records a condition, it never excludes")

check("a clean modern session carries no flags", manifest.provenanceFlags(session()) == [])
check("a pre-0.3.2 schema is flagged as having no VRAM record",
      "no-vram-record" in manifest.provenanceFlags(session(schema_version="0.3.1")))
check("0.3.2 itself is NOT flagged - it is the version that added the record",
      "no-vram-record" not in manifest.provenanceFlags(session(schema_version="0.3.2")))
check("an active encoder is flagged",
      "encoder-active" in manifest.provenanceFlags(session(encoder_util_pct=21)))
check("an active decoder is flagged too",
      "encoder-active" in manifest.provenanceFlags(session(decoder_util_pct=4)))
check("absent encoder telemetry is flagged differently from a measured zero",
      "no-encoder-telemetry" in manifest.provenanceFlags(
          session(encoder_util_pct=None, decoder_util_pct=None)))
check("a baseline above 5% is flagged with its value",
      "baseline-18.8pct" in manifest.provenanceFlags(session(baseline_util_pct=18.8)))
check("a baseline at or under 5% is not flagged",
      manifest.provenanceFlags(session(baseline_util_pct=4.3)) == [])
check("video engines permitted is flagged",
      "video-engines-allowed" in manifest.provenanceFlags(session(video_engines_allowed=True)))
check("a short sweep records how short",
      "measured-11-of-13" in manifest.provenanceFlags(session(frequencies_measured=11)))

print()
print("the BOM - PowerShell writes some session JSONs with one, and it killed the first version")

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "bom_sweep.json"
    path.write_text(json.dumps(session()), encoding="utf-8-sig")
    loaded = json.load(open(path, encoding="utf-8-sig"))
    check("a BOM-prefixed session parses with utf-8-sig", loaded["schema_version"] == "0.3.3")
    try:
        json.load(open(path, encoding="utf-8"))
        parsedPlain = True
    except json.JSONDecodeError:
        parsedPlain = False
    check("...and genuinely fails on plain utf-8, so the encoding choice is load-bearing "
          "rather than defensive", not parsedPlain)

print()
print("the real tree - invariants only, never totals")

rows = manifest.loadSessions()
check("the real tree has sweep sessions to inventory", len(rows) > 0)
check("every session in the real tree parses", all(row["error"] is None for row in rows))

built = manifest.buildManifest(rows)
check("every manifest row is classified", all(entry["category"] for entry in built))
check("every excluded row names its rule",
      all(entry["rule"] for entry in built if entry["category"] != "dataset-grade"))
check("no dataset-grade row carries an exclusion rule",
      all(not entry["rule"] for entry in built if entry["category"] == "dataset-grade"))
check("every row records which card it came from",
      all(entry["gpu"] for entry in built if entry["category"] != "unreadable"))

print()
print("the saved census against the live one - synthetic files, never the real ones")

# Added 2026-09-29 (GPT Job 35): the first version of this comparison read only the JSON, so a
# changed or deleted CSV passed, and a BOM or malformed JSON raised a traceback.
fixture = [{"path": "data/frequency-sweeps/x/a_sweep.json", "category": "dataset-grade",
            "rule": "", "gpu": "NVIDIA GeForce RTX 5060 Ti", "label": "a", "schema": "0.3.3",
            "driver": "616.56", "frequenciesMeasured": 13, "flags": "", "hasSamplesCsv": True,
            "why": ""}]
realPaths = (manifest.REPO_ROOT, manifest.MANIFEST_JSON, manifest.MANIFEST_CSV)
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    manifest.REPO_ROOT = root
    manifest.MANIFEST_JSON = root / "MANIFEST.json"
    manifest.MANIFEST_CSV = root / "MANIFEST.csv"
    try:
        def save(jsonText=None, csvText=None):
            manifest.MANIFEST_JSON.write_text(
                json.dumps(fixture, indent=2) + "\n" if jsonText is None else jsonText,
                encoding="utf-8")
            manifest.MANIFEST_CSV.write_text(
                manifest.manifestCsvText(fixture) if csvText is None else csvText,
                encoding="utf-8", newline="")

        save()
        check("identical saved files match the live census",
              manifest.savedManifestProblems(fixture) == [])
        save(jsonText=json.dumps(list(reversed([dict(reversed(list(fixture[0].items())))])),
                                 indent=4))
        check("key order and indentation in the saved JSON do not matter",
              manifest.savedManifestProblems(fixture) == [])
        save(csvText=manifest.manifestCsvText(fixture).replace("\r\n", "\n"))
        check("CSV line endings do not matter", manifest.savedManifestProblems(fixture) == [])
        save(csvText="unrelated text\n")
        check("a changed CSV is caught", any("MANIFEST.csv" in p
                                             for p in manifest.savedManifestProblems(fixture)))
        save()
        manifest.MANIFEST_CSV.unlink()
        check("a missing CSV is caught", any("MANIFEST.csv is missing" in p
                                             for p in manifest.savedManifestProblems(fixture)))
        save(jsonText="﻿" + json.dumps(fixture))
        check("a BOM on otherwise identical JSON is accepted, not a traceback",
              manifest.savedManifestProblems(fixture) == [])
        save(jsonText="{not json")
        check("malformed JSON is reported, not raised",
              any("not valid JSON" in p for p in manifest.savedManifestProblems(fixture)))
        save(jsonText=json.dumps([dict(fixture[0], category="excluded")]))
        check("a changed JSON field is caught", any("does not match" in p
                                                    for p in manifest.savedManifestProblems(fixture)))
    finally:
        manifest.REPO_ROOT, manifest.MANIFEST_JSON, manifest.MANIFEST_CSV = realPaths
# Whether the REAL saved census matches the tree is --check's job, not this suite's: a test would
# fail every run between a new sweep landing and the census being regenerated.

print()
print(f"{passed} checks passed.")
print("These check the RULES, not the counts. The reconciliation itself is asserted by "
      "`paper-dataset-grade-total` in claims_repo.py and enforced by --check, which is the right "
      "place for it - a claim recomputes from the tree at audit time, where a test would freeze "
      "a number that grows every collection run.")
