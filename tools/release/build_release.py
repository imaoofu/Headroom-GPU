"""Stage the census-selected release outside the source repository, without editing inputs.

Usage: python tools/release/build_release.py <empty-output-directory>
The result is a review copy, not a publication. Exit 2 means it was built but needs review;
exit 1 means assembly failed. No GPU tools are executed and no Git history is copied.
"""

import argparse
import collections
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_ROOTS = (
    "analysis", "scripts", "tools/frequency-sweep", "tools/stability-logger",
    "tools/hwinfo-logging", "tools/collection-kit", "tools/bench-app",
    "tools/afterburner", "tools/nvml-offset", "tools/xbar", "tools/release",
    "tools/section20b", "tools/power-probe", "tools/rerun15",
)
CODE_SUFFIXES = {".py", ".ps1", ".bat", ".md", ".txt", ".json", ".ini"}
SKIP_PARTS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "fixtures"}
ROOT_FILES = ("LICENSE", "LICENSE-DATA", "requirements.txt", "tools/Disable-QuickEdit.ps1")
DEFAULT_IDENTIFIERS = ("Raymond", "imaoofu")
LINE_ENDINGS = (
    "Copied files are byte-for-byte filesystem reads from the recorded working tree. "
    "No BOM, encoding, CRLF, LF or lone-CR normalization is applied. SHA-256 hashes the "
    "exact distributed bytes, not Git blobs or a line-ending-neutral representation. "
    "Generated text is UTF-8 without BOM; JSON/Markdown/CFF use LF and manifest CSV uses CRLF. "
    "SHA256SUMS covers every distributed file except itself, including the review report."
)


def within(path, parent):
    return path == parent or parent in path.parents


def validate_output(repo, output):
    repo, output = repo.resolve(), output.resolve()
    if within(output, repo) or within(repo, output):
        raise ValueError("The output must be outside the repository and cannot be its ancestor.")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("The output must be a new or empty directory; existing files are never overwritten.")
    return output


def files_under(root, skip_parts=SKIP_PARTS):
    """Reject links, including directory junctions, rather than follow them out of the tree."""
    if not root.exists():
        return []
    if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
        raise ValueError("A source root is a link or junction: " + root.name)
    found = []
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(current) / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("A source directory is a link or junction: " + path.name)
            if name in skip_parts:
                dirs.remove(name)
        for name in names:
            path = Path(current) / name
            if path.is_symlink():
                raise ValueError("A source file is a link: " + path.name)
            found.append(path)
    return sorted(found)


def census_module(repo):
    path = repo / "analysis/build_data_manifest.py"
    spec = importlib.util.spec_from_file_location("release_source_census", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Configure this private module instance, never the source file or another importer's module.
    module.REPO_ROOT = repo
    module.SWEEPS = repo / "data/frequency-sweeps"
    module.MANIFEST_JSON = repo / "data/MANIFEST.json"
    module.MANIFEST_CSV = repo / "data/MANIFEST.csv"
    return module


def git_info(repo):
    def run(*args):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
        if result.returncode:
            raise ValueError("Git could not inventory source provenance.")
        return result.stdout
    return {
        "commit": run("rev-parse", "HEAD").decode("ascii").strip(),
        "status": run("status", "--porcelain", "-z").decode("utf-8", errors="replace").split("\0"),
        "ignored": set(run("ls-files", "--others", "--ignored", "--exclude-standard", "-z",
                           "--", "data", *CODE_ROOTS).decode("utf-8", errors="replace").split("\0")),
    }


def supplement_module():
    spec = importlib.util.spec_from_file_location("release_supplements", Path(__file__).with_name("v120_supplements.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_files(repo, census, include_raw=False, ignored=(), v120_supplements=False):
    selected, omissions, missing_readmes = {}, [], set()
    sweep_root = repo / "data/frequency-sweeps"
    all_sweep_files = files_under(sweep_root)
    rows = census.loadSessions()
    if any(row["session"] is not None and not isinstance(row["session"], dict) for row in rows):
        raise ValueError("A sweep session is valid JSON but is not an object; it cannot be classified.")
    entries = census.buildManifest(rows)
    if not entries:
        raise ValueError("The census contains no sweep sessions.")
    faults = [e["path"] for e in entries if e["category"] == "unreadable" or not e["hasSamplesCsv"]]
    if faults:
        raise ValueError("Unreadable sessions or missing samples prevent a complete release: " + "; ".join(faults))
    accepted = [e for e in entries if e["category"] == "dataset-grade"]
    if not accepted:
        raise ValueError("The census contains no dataset-grade sweeps.")

    def add(path, reason):
        relative = path.relative_to(repo).as_posix()
        if not within(path.resolve(), repo) or path.is_symlink():
            raise ValueError("A selected source escapes the repository: " + relative)
        if not path.is_file():
            raise ValueError("A required source file is missing: " + relative)
        selected[relative] = reason

    # The matching session, samples and optional distilled telemetry are one release unit.
    for entry in accepted:
        session = repo / entry["path"]
        add(session, "dataset-grade-session")
        add(session.with_suffix(".csv"), "dataset-grade-samples")
        voltage = session.with_name(session.stem + "_voltage.csv")
        if voltage.exists():
            add(voltage, "distilled-voltage-crossbar")
        # Include READMEs at every level, including nested run folders and sweep-root rules.
        directory = session.parent
        while within(directory, sweep_root):
            readme = directory / "README.md"
            if readme.exists():
                add(readme, "run-provenance-readme")
            else:
                missing_readmes.add(directory.relative_to(repo).as_posix())
            directory = directory.parent

    excluded_files = {}
    for entry in entries:
        if entry["category"] != "dataset-grade":
            path = Path(entry["path"])
            for relative in (path, path.with_suffix(".csv"), path.with_name(path.stem + "_voltage.csv")):
                excluded_files[relative.as_posix()] = "census-" + (entry["rule"] or entry["category"])

    for path in all_sweep_files:
        relative = path.relative_to(repo).as_posix()
        if relative not in selected:
            omissions.append({"path": relative, "reason": excluded_files.get(relative, "unselected-sweep-support-file")})

    for root in CODE_ROOTS:
        for path in files_under(repo / root):
            relative = path.relative_to(repo).as_posix()
            if path.suffix.lower() in CODE_SUFFIXES and relative not in ignored:
                add(path, "collection-analysis-source")
            else:
                omissions.append({"path": relative, "reason": "ignored-or-non-source-code-file"})
    for relative in ROOT_FILES:
        add(repo / relative, "license-or-code-dependency")

    # Numeric curve JSON is project-created; raw device-tuple CFG stores are deliberately omitted.
    # These JSONs keep the paths expected by predict_from_curve.py.
    for path in files_under(repo / "data/afterburner-profiles"):
        relative = path.relative_to(repo).as_posix()
        if path.suffix.lower() == ".json" or path.name == "README.md":
            add(path, "numeric-curve-provenance")

    if v120_supplements:
        if include_raw:
            raise ValueError("The v1.2 proposal excludes raw HWiNFO logs, including opt-in logs.")
        for relative in supplement_module().selection(repo, ignored, files_under):
            add(repo / relative, "v120-registered-evidence")

    # Inventory every uncopied data input, including tracked raw logs and ignored downloads.
    # Never treat tracked status alone as redistribution permission or dataset quality.
    for path in files_under(repo / "data"):
        relative = path.relative_to(repo).as_posix()
        if relative in selected or within(path, sweep_root):
            continue
        if relative.startswith("data/HWiNFO-Data/") and path.suffix.lower() == ".csv":
            if include_raw:
                add(path, "operator-selected-raw-hwinfo")
                continue
            reason = "raw-hwinfo-not-included"
        elif relative.startswith(("data/raw/", "data/external/")):
            reason = "third-party-input-not-redistributed"
        elif relative.startswith("data/afterburner-profiles/"):
            reason = "raw-profile-not-redistributed"
        elif relative in {"data/MANIFEST.csv", "data/MANIFEST.json"}:
            reason = "replaced-by-live-release-census"
        else:
            reason = "outside-sweep-release-scope"
        omissions.append({"path": relative, "reason": reason, "gitignored": relative in ignored})
    # All top-level investigation directories must be reported, even excluded-only directories.
    for directory in sorted(sweep_root.iterdir()):
        if directory.is_dir() and not (directory / "README.md").is_file():
            missing_readmes.add(directory.relative_to(repo).as_posix())
    return selected, entries, sorted(omissions, key=lambda x: x["path"]), sorted(missing_readmes)


PATTERNS = {
    "email": re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I),
    "windows-path": re.compile(r"[A-Z]:[\\/][^\s\"'<>|,;]+", re.I),
    "unix-account-path": re.compile(r"/(?:Users|home)/[^/\s\"']+", re.I),
    "account-or-host-field": re.compile(r"\b(?:username|user_name|runas user|machine|hostname|computer_name|full_name)\b[\"']?\s*[:=]\s*[^,}\r\n]+", re.I),
    "windows-account": re.compile(r"\b(?:DESKTOP|LAPTOP)-[A-Z0-9]+(?:\\[^\s,\"']+)?", re.I),
    "github-username": re.compile(r"github\.com/([A-Z0-9_-]+)", re.I),
    "device-identifier": re.compile(r"\b(?:GPU-[0-9a-f-]{8,}|VEN_[0-9a-f]{4}&DEV_[^\s\"'`]+)", re.I),
}


def scan_bytes(data, path, identifiers):
    findings = []
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16", errors="replace")
    elif b"\x00" in data:
        return [{"path": path, "line": 0, "kind": "binary-needs-manual-review"}]
    else:
        text = data.decode("utf-8-sig", errors="replace")
    patterns = dict(PATTERNS)
    for index, value in enumerate(identifiers):
        if value:
            patterns["known-identifier-" + str(index + 1)] = re.compile(re.escape(value), re.I)
    # Scan file names as well as content. Matches carry locations and token hashes, never raw values.
    for line_number, line in [(0, path), *enumerate(text.splitlines(), 1)]:
        for kind, pattern in patterns.items():
            match = pattern.search(line)
            if match:
                findings.append({"path": path, "line": line_number, "kind": kind,
                                 "match_sha256": hashlib.sha256(match.group().encode("utf-8")).hexdigest()})
    return findings


def text_bytes(value):
    return value.encode("utf-8")


def json_bytes(value):
    return text_bytes(json.dumps(value, indent=2, ensure_ascii=True) + "\n")


# Emoji used as markers in the project's notes. Stripped from distributed documentation only when
# --strip-emoji is given (2026-10-08, the owner's choice for the public upload). Code is never edited:
# some of its strings must match the private paper exactly, and data files carry none.
STRIP_SUFFIXES = {".md", ".txt"}
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]\uFE0F?")
# A check or cross that ends a table cell carries the verdict, so it becomes a word.
VERDICT = re.compile(r"(\|[^|\r\n]*?)[ ]*([\u2705\u2717\u274C])\uFE0F?[ ]*(?=\|)")
VERDICT_WORDS = {"\u2705": "yes", "\u2717": "no", "\u274C": "no"}


def strip_emoji_bytes(data):
    """Remove emoji markers from UTF-8 text, keeping a BOM and the line endings. A check or cross at
    the end of a table cell becomes "yes"/"no" when alone in the cell and "(yes)"/"(no)" after a value;
    every other emoji is dropped, with the space that followed it."""
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    text = data[len(bom):].decode("utf-8")

    def verdict(match):
        before, word = match.group(1), VERDICT_WORDS[match.group(2)]
        return (before + " " + word + " ") if before.strip("| ") == "" else (before.rstrip() + " (" + word + ") ")
    text = VERDICT.sub(verdict, text)
    text = re.sub("[ ]?" + EMOJI.pattern + "[ ]?", lambda m: " " if m.group(0).startswith(" ") and m.group(0).endswith(" ") else "", text)
    text = re.sub(r"\|[ ]{2,}", "| ", text)
    return bom + text.encode("utf-8")


RELEASE_DOCS = ("README.md", "DATASHEET.md", "CITATION.cff")  # owner-written, replace the generated stubs
DESKTOP_CENSUS = "docs/desktop-load-census-20261003.csv"
DESKTOP_CENSUS_GPU = "NVIDIA GeForce RTX 5060 Ti"  # the screen covers this card's sweeps only


def release_doc_bytes(release_docs):
    """Owner-approved public documents; README.md and CITATION.cff are required, DATASHEET.md optional."""
    folder = Path(release_docs)
    if not folder.is_dir():
        raise ValueError("The release-docs path is not a directory.")
    found = {name: (folder / name).read_bytes() for name in RELEASE_DOCS if (folder / name).is_file()}
    if not {"README.md", "CITATION.cff"} <= set(found):
        raise ValueError("The release-docs directory needs README.md and CITATION.cff.")
    # A version is prepared before Zenodo reserves its DOI; the placeholders must never ship.
    pending = sorted(name for name, data in found.items() if b"PENDING" in data)
    if pending:
        raise ValueError(f"Release documents still carry a PENDING placeholder: {', '.join(pending)}.")
    return found


def census_problem(rows, expected):
    """None when the census rows name every expected sweep exactly once and nothing else."""
    found = collections.Counter(r["sweep"] for r in rows)
    if found != collections.Counter(expected):
        missing = sorted(set(expected) - set(found))
        extra = sorted(set(found) - set(expected))
        repeated = sorted(k for k, v in found.items() if v > 1)
        return (f"the desktop-load census does not match the distributed {DESKTOP_CENSUS_GPU} sweeps: "
                f"{len(missing)} missing, {len(extra)} extra, {len(repeated)} repeated")
    return None


def desktop_census_bytes(repo, accepted):
    """The desktop-load screen's per-sweep verdicts for the distributed sweeps of the screened card.
    Required whenever that card has distributed sweeps, and refused unless it covers each of them
    exactly once (GPT Job 68: a partial or duplicated census used to build and verify)."""
    expected = [e["path"] for e in accepted if e["gpu"] == DESKTOP_CENSUS_GPU]
    path = repo / DESKTOP_CENSUS
    if not path.is_file():
        if expected:
            raise ValueError(f"{DESKTOP_CENSUS} is missing, so the distributed {DESKTOP_CENSUS_GPU} sweeps have no desktop-load screen.")
        return None
    accepted_paths = {e["path"] for e in accepted}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = [r for r in reader if r["sweep"] in accepted_paths]
    problem = census_problem(rows, expected)
    if problem:
        raise ValueError(problem[0].upper() + problem[1:] + ".")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build_release(output, repo=REPO_ROOT, identifiers=DEFAULT_IDENTIFIERS, include_raw=False, release_docs=None,
                  strip_emoji=False, v120_supplements=False):
    repo = Path(repo).resolve()
    output = validate_output(repo, Path(output))
    owner_docs = release_doc_bytes(release_docs) if release_docs is not None else {}
    provenance = git_info(repo)
    rule_hash = hashlib.sha256((repo / "analysis/build_data_manifest.py").read_bytes()).hexdigest()
    census = census_module(repo)
    selected, entries, omissions, missing_readmes = select_files(repo, census, include_raw, provenance["ignored"], v120_supplements)
    initial_hashes = {relative: hashlib.sha256((repo / relative).read_bytes()).hexdigest()
                      for relative in selected}
    if initial_hashes["analysis/build_data_manifest.py"] != rule_hash:
        raise ValueError("The classification source changed while the census was loaded.")
    accepted = [e for e in entries if e["category"] == "dataset-grade"]
    counts = dict(sorted(collections.Counter(e["category"] for e in entries).items()))
    by_card = dict(sorted(collections.Counter(e["gpu"] for e in accepted).items()))
    # The source script itself is copied; this describes the additional release selection.
    generated = {
        "data/MANIFEST.json": json_bytes(accepted),
        "data/MANIFEST.csv": text_bytes(census.manifestCsvText(accepted)),
        "manifest/SOURCE-CENSUS.json": json_bytes(entries),
        "manifest/SOURCE-CENSUS.csv": text_bytes(census.manifestCsvText(entries)),
        "manifest/SELECTION.md": text_bytes(
            "# Release selection\n\nUse the classification in analysis/build_data_manifest.py. "
            "Select only category `dataset-grade`; retain every provenance flag. Include each "
            "session JSON, matching samples CSV, existing `_sweep_voltage.csv`, and ancestor "
            "README through data/frequency-sweeps/. Missing READMEs are reported, never invented.\n\n"
            "SOURCE-CENSUS retains excluded and verification rows as an inventory, not measurements. "
            "data/MANIFEST describes the copied dataset-grade sweeps. The original census script's "
            "--check compares the complete private source tree to its paper and is not a release gate.\n\n"
            "Include numeric curve JSON/README, collection and analysis source in the builder's "
            "CODE_ROOTS, and LICENSE files. Omit fixtures, caches, raw profile stores, transcripts, "
            "machine-info, third-party tables and unrelated source history. Raw HWiNFO is opt-in; "
            "the default release cannot independently regenerate joins from omitted logs. "
            "RELEASE-REPORT.json lists file-level omissions and ignored inputs.\n"),
        "CHECKSUMS.md": text_bytes("# Byte checksums\n\n" + LINE_ENDINGS + "\n"),
        "CITATION.cff": text_bytes(
            'cff-version: 1.2.0\nmessage: "Cite this dataset when using the measurements."\n'
            'title: "Headroom: measured GPU frequency-efficiency data on consumer hardware"\n'
            'type: dataset\nauthors:\n  - name: "Raymond"\nlicense: CC-BY-4.0\n'
            '# Stage only: release version, publication date, public repository URL and DOI await owner decision.\n'),
        "README.md": text_bytes(
            "# Headroom release review copy\n\n"
            f"This copy contains {len(accepted)} dataset-grade sweeps selected from a live census of "
            f"{len(entries)} source sessions. It is unpublished and requires identifier and dependency review.\n\n"
            "Measurements and their run READMEs use CC BY 4.0 (LICENSE-DATA); software uses MIT "
            "(LICENSE). Third-party inputs and proprietary executables are not redistributed. "
            "Numeric curve JSONs are derived project records, with decoding limits in their READMEs.\n\n"
            "data/MANIFEST.json and .csv describe the distributed sweeps. manifest/SOURCE-CENSUS "
            "records the complete source inventory; manifest/SELECTION.md and the copied census "
            "script state the rules. RELEASE-REPORT.json records the source commit, working-tree "
            "status, exact per-file source hashes, omissions, missing READMEs, identifier locations, "
            "and inputs a reader may need. It is part of the review copy and needs privacy review too.\n\n"
            "The collection samples one physical chip per GPU model (N=1 per model); sweeps and "
            "workloads are repeated outcomes, not independent chips. Dataset-grade is the census "
            "category, not a certification of quiet collection, stability or scoreability. Read "
            "each run README and flags before comparing results; failed predictions and known "
            "contamination remain as recorded. Reported voltage is telemetry, not a measured rail.\n\n"
            "## Inspect existing measurements\n\n"
            "Install requirements.txt in your own environment, then run "
            "`python analysis/analyze_sweep.py --pattern \"**/*floor15*_sweep.csv\"` from this folder. "
            "This only reads measurements. For figures, matplotlib is an additional dependency. "
            "Collection requires Windows, an NVIDIA driver, appropriate PyTorch/CUDA, and separately "
            "installed HWiNFO; LLM workloads also need the pinned external runner and model in their "
            "tool README. Some collection tools change GPU state and require administrator rights. "
            "Read their safety and reset instructions before running them.\n\n"
            "Paper audits, some scorers and full-source tests require omitted documents, raw logs, "
            "fixtures, stability/probe supplements or third-party datasets. Their presence as source "
            "code does not mean those analyses are self-contained. RELEASE-REPORT.json inventories "
            "the omissions; scripts/Get-Dataset.ps1 fetches external inputs under upstream terms. "
            "No collection or GPU-state command was executed to assemble this release.\n\n"
            "## Checksums and citation\n\n"
            "SHA256SUMS uses exact distributed bytes, as described in CHECKSUMS.md. No source file "
            "was redacted, re-encoded or re-saved. CITATION.cff has provisional author attribution; "
            "publication metadata and DOI have not been assigned. Identifiers are reported without "
            "automatic redaction. Pattern scans cannot certify anonymity or detect every secret.\n"),
    }
    supplement_summary = None
    if v120_supplements:
        supplement_files, supplement_summary = supplement_module().generated(repo)
        generated.update(supplement_files)
        generated["manifest/SELECTION.md"] += text_bytes(
            "\n## Section 20b and 22 supplements\n\n"
            "The explicit tools/release/v120-cohorts.json policy selects separate pilot/day cohorts. "
            "manifest/SUPPLEMENTS.json and family/per-cohort manifests record exact evidence hashes, "
            "README excerpts and separate counts; these never change the legacy sweep census. "
            "Pilots are sizing data, never results; stopped at insufficient precision. Five repeatability days are COMPLETE, N=1 chip. "
            "Explicit exceptions ship both attempt ledgers, registered rules, eleven witnessed profile "
            "stores and the curve3 reference CFG; they need identifier/redistribution review. "
            "Process transcripts, controller logs, workload stdout/stderr and watcher signals stay out; "
            "parsed workload result records stay in windows.jsonl. All other filed cohort evidence, four probe JSONs and both probe READMEs are retained. Raw HWiNFO always stays out in this mode. "
            "Registered evidence is byte-preserved even with --strip-emoji: the filed runner TXT "
            "is hashed at launch. Its CRLF launch-hash reconstruction is the scorer's responsibility.\n")
        supplement_pointer = text_bytes(
            "\n## Section 20b and 22 supplements\n\n"
            "See manifest/section20b/README.md (sizing data, never results) and "
            "manifest/repeatability/README.md (five-day COMPLETE outcome), and manifest/probes/README.md (diagnostics, not sweep rows). The desktop-load screen is in manifest/DESKTOP-LOAD-CENSUS.csv. Counts and per-cohort "
            "README excerpts are separate from the legacy sweep manifest.\n")
    # Owner-written public documents replace the review stubs; the census screen ships beside them.
    generated.update({name: data for name, data in owner_docs.items()})
    if v120_supplements:
        generated["README.md"] += supplement_pointer
    if strip_emoji:
        generated = {name: strip_emoji_bytes(data) if Path(name).suffix.lower() in STRIP_SUFFIXES else data
                     for name, data in generated.items()}
        owner_docs = {name: generated[name] for name in owner_docs}
    if owner_docs or v120_supplements:
        census_csv = desktop_census_bytes(repo, accepted)
        if census_csv is not None:
            generated["manifest/DESKTOP-LOAD-CENSUS.csv"] = census_csv
    report = {
        "schema_version": 1, "status": "REVIEW REQUIRED", "published": False,
        "release_docs": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(owner_docs.items())},
        "emoji_stripped_from_documentation": bool(strip_emoji),
        "source_commit": provenance["commit"],
        "working_tree_status": [x for x in provenance["status"] if x],
        "supplements": supplement_summary,
        "source_counts": counts, "release_sweeps": len(accepted), "release_by_card": by_card,
        "line_ending_convention": LINE_ENDINGS, "raw_hwinfo_included": include_raw,
        "missing_readmes": missing_readmes, "omitted_files": omissions,
        "gitignored_inputs": sorted(x for x in provenance["ignored"] if x and x.startswith("data/")),
        "source_manifest_problems": census.savedManifestProblems(entries),
        "structural_problems": census.integrityProblems(entries),
        "identifier_scan_limits": "Known names/handles, email, local paths, account/host fields and device IDs; no semantic name recognition, OCR, secret clearance or blind-review certification.",
        "identifiers_searched": list(identifiers), "identifier_findings": [], "copied_files": [],
        "identifier_scanned_files": sorted([*selected, *generated, "RELEASE-REPORT.json"]),
        "unverified": ["Public upload, DOI and blind-venue policy.",
                       "Hardware execution and installed third-party binaries/models.",
                       "Full paper audits and all analyses in this trimmed tree.",
                       "Raw-log join reproduction when raw logs are omitted.",
                       "Code provenance and third-party redistribution clearance."],
    }
    output.mkdir(parents=True, exist_ok=True)
    # Only new files, even if an unrelated process starts writing into the output after preflight.
    def write(relative, data):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not within(destination.resolve(), output):
            raise ValueError("An output path escapes the release directory.")
        with destination.open("xb") as handle:
            handle.write(data)

    for relative, reason in sorted(selected.items()):
        data = (repo / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != initial_hashes[relative]:
            raise ValueError("A selected source changed before copying: " + relative)
        record = {"path": relative, "reason": reason}
        if strip_emoji and reason != "v120-registered-evidence" and Path(relative).suffix.lower() in STRIP_SUFFIXES:
            edited = strip_emoji_bytes(data)
            if edited != data:
                # The distributed bytes differ from the source; both hashes are recorded.
                record.update({"edit": "emoji-removed", "source_sha256": hashlib.sha256(data).hexdigest()})
                data = edited
        write(relative, data)
        record.update({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        report["copied_files"].append(record)
        report["identifier_findings"].extend(scan_bytes(data, relative, identifiers))
    for relative, data in sorted(generated.items()):
        write(relative, data)
        report["identifier_findings"].extend(scan_bytes(data, relative, identifiers))
    # A changing shared working tree cannot produce a review copy with coherent provenance.
    if census.buildManifest(census.loadSessions()) != entries:
        raise ValueError("The sweep census changed during assembly; discard this partial copy and retry.")
    for record in report["copied_files"]:
        if hashlib.sha256((repo / record["path"]).read_bytes()).hexdigest() != record.get("source_sha256", record["sha256"]):
            raise ValueError("A copied source changed during assembly: " + record["path"])
    # Scan the report once before adding its findings; avoid an endless self-scan of findings.
    # Findings last, so the self-findings appended below cannot shift any line a finding points to
    # (GPT Job 68: three stored report locations were off by 1,518 lines).
    report["identifier_findings"] = report.pop("identifier_findings")
    report["identifier_findings"].extend(scan_bytes(json_bytes(report), "RELEASE-REPORT.json", identifiers))
    write("RELEASE-REPORT.json", json_bytes(report))
    sums = []
    for path in files_under(output, skip_parts=()):
        sums.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(output).as_posix())
    write("SHA256SUMS", text_bytes("\n".join(sums) + "\n"))
    return report


def verify_release(output):
    """Verify the distributed byte inventory and sweep pair/manifest membership without a source tree."""
    output = Path(output).resolve()
    sums = output / "SHA256SUMS"
    expected = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("A checksum line is malformed.")
        path = output / relative
        if relative in expected or not within(path.resolve(), output) or path.is_symlink():
            raise ValueError("A checksum path is repeated, linked or outside the release.")
        expected[relative] = digest
    # No skipped names here: a file in a folder called fixtures or __pycache__ is still distributed.
    actual = {p.relative_to(output).as_posix() for p in files_under(output, skip_parts=()) if p != sums}
    if set(expected) != actual:
        raise ValueError("The checksum inventory does not match the distributed file set.")
    for relative, digest in expected.items():
        if hashlib.sha256((output / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("A distributed file fails its checksum: " + relative)
    manifest = json.loads((output / "data/MANIFEST.json").read_text(encoding="utf-8-sig"))
    source = json.loads((output / "manifest/SOURCE-CENSUS.json").read_text(encoding="utf-8-sig"))
    selected = [e for e in source if e["category"] == "dataset-grade"]
    if manifest != selected:
        raise ValueError("The release census differs from the source census's dataset-grade rows.")
    for name, rows in (("data/MANIFEST.csv", manifest), ("manifest/SOURCE-CENSUS.csv", source)):
        with (output / name).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            csv_rows = list(reader)
        if not fields or not rows or set(fields) != set(rows[0]):
            raise ValueError("A census CSV header differs from its JSON fields: " + name)
        if csv_rows != [{field: str(row.get(field, "")) for field in fields} for row in rows]:
            raise ValueError("A census CSV differs from its JSON rows: " + name)
    named = [e["path"] for e in manifest]
    present = sorted(p.relative_to(output).as_posix() for p in (output / "data/frequency-sweeps").rglob("*_sweep.json"))
    if sorted(named) != present or len(named) != len(set(named)):
        raise ValueError("The release's sweep sessions do not match its census.")
    present_samples = sorted(p.relative_to(output).as_posix() for p in (output / "data/frequency-sweeps").rglob("*_sweep.csv"))
    if sorted(str(Path(relative).with_suffix(".csv")).replace("\\", "/") for relative in named) != present_samples:
        raise ValueError("The release's sweep samples do not match its census.")
    for relative in named:
        if not (output / relative).with_suffix(".csv").is_file():
            raise ValueError("A released sweep has no samples CSV: " + relative)
    for path in (output / "data/frequency-sweeps").rglob("*_sweep_voltage.csv"):
        if path.with_name(path.name.replace("_voltage.csv", ".json")).relative_to(output).as_posix() not in named:
            raise ValueError("A voltage extract has no selected sweep: " + path.name)
    report = json.loads((output / "RELEASE-REPORT.json").read_text(encoding="utf-8"))
    for record in report["copied_files"]:
        if expected.get(record["path"]) != record["sha256"]:
            raise ValueError("The distributed copy differs from its recorded source hash: " + record["path"])
    # The report's own claims, reconciled against the payload rather than trusted (GPT Job 68).
    if report.get("release_sweeps") != len(manifest):
        raise ValueError("The report's sweep count differs from the distributed census.")
    if report.get("release_by_card") != dict(sorted(collections.Counter(e["gpu"] for e in manifest).items())):
        raise ValueError("The report's per-card counts differ from the distributed census.")
    for name, digest in (report.get("release_docs") or {}).items():
        if expected.get(name) != digest:
            raise ValueError("A public document differs from the digest the report records: " + name)
    copied = {r["path"] for r in report["copied_files"]}
    data_files = {r for r in expected if r.startswith("data/frequency-sweeps/")}
    if not data_files <= copied:
        raise ValueError("A distributed sweep file has no copied-file record in the report.")
    census_path = output / "manifest/DESKTOP-LOAD-CENSUS.csv"
    if census_path.is_file():
        with census_path.open(encoding="utf-8-sig", newline="") as handle:
            problem = census_problem(list(csv.DictReader(handle)),
                                     [e["path"] for e in manifest if e["gpu"] == DESKTOP_CENSUS_GPU])
        if problem:
            raise ValueError("The release's " + problem + ".")
    if report.get("supplements") is not None:
        supplement_module().verify(output, expected, report)
    elif (output / "manifest/SUPPLEMENTS.json").exists():
        raise ValueError("A supplement inventory exists but is absent from the report.")
    return {"files": len(expected), "sweeps": len(named)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="A new or empty directory outside this repository.")
    parser.add_argument("--identifier", action="append", default=[], help="An additional personal name or handle to flag.")
    parser.add_argument("--include-raw-hwinfo", action="store_true", help="Include ignored raw HWiNFO CSVs for review; never anonymizes them.")
    parser.add_argument("--release-docs", type=Path, default=None, help="A folder of owner-written README.md, CITATION.cff and optional DATASHEET.md that replace the generated stubs, and add the desktop-load census.")
    parser.add_argument("--strip-emoji", action="store_true", help="Remove emoji markers from distributed .md/.txt documentation (never code or data), recording both hashes for every edited file.")
    parser.add_argument("--v120-supplements", action="store_true", help="Include the frozen, separately counted section 20b/22 and diagnostic-probe evidence proposal; raw HWiNFO stays out.")
    parser.add_argument("--verify", action="store_true", help="Read an existing release and verify all checksums and sweep membership; write nothing.")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            verified = verify_release(args.output)
            print(f"The release verifies {verified['files']} distributed byte hashes and {verified['sweeps']} dataset-grade sweep pairs.")
            print("This checks integrity and selection, not anonymity, scientific validity or publication readiness.")
            return 0
        result = build_release(args.output, identifiers=(*DEFAULT_IDENTIFIERS, *args.identifier),
                               include_raw=args.include_raw_hwinfo, release_docs=args.release_docs, strip_emoji=args.strip_emoji,
                               v120_supplements=args.v120_supplements)
    except (ValueError, OSError, KeyError, TypeError) as error:
        message = "The release did not verify. " if args.verify else "The release could not be assembled. "
        print((message + str(error)).encode("ascii", errors="backslashreplace").decode("ascii"))
        if not args.verify:
            print("Any partially assembled output is a failed review copy; use a new empty directory after resolving the error.")
        return 1
    print(f"The review copy contains {result['release_sweeps']} dataset-grade sweeps.")
    print(f"The source census contains {result['source_counts']}.")
    print(f"The builder reports {len(result['missing_readmes'])} directories without READMEs, "
          f"{len(result['omitted_files'])} omitted files, and {len(result['gitignored_inputs'])} ignored data inputs.")
    print(f"The identifier scan reports {len(result['identifier_findings'])} locations needing review.")
    print("Read RELEASE-REPORT.json, CHECKSUMS.md and SHA256SUMS in the output directory.")
    print("The copy needs human review and has not been anonymized or published. A pattern scan is not privacy clearance.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
