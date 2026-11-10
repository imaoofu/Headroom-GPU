"""Release selection and trust-boundary checks, using temporary synthetic repositories only.

Never invokes a collection runner or writes into the real data tree. Achieved clocks deliberately
differ from targets, sessions use a BOM, samples use CRLF, and excluded neighbours share a folder.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_builder", REPO_ROOT / "tools/release/build_release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
passed = 0


def check(description, condition):
    global passed
    if not condition:
        print("  [FAIL] " + description)
        raise AssertionError(description)
    passed += 1
    print("  [PASS] " + description)


def write(repo, name, data):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def session(repo, name, label="dataset-gemm"):
    stem = "data/frequency-sweeps/" + name + "_sweep"
    write(repo, stem + ".json", b"\xef\xbb\xbf" + json.dumps({
        "session_label": label, "gpu_name": "Synthetic GPU", "frequencies_measured": 3,
        "workload_command": r"python C:\Users\Alice\bench.py", "username": "operator42",
    }).encode("utf-8"))
    write(repo, stem + ".csv", b"target_frequency_mhz,achieved_frequency_avg,bench_throughput,power_avg_w,bench_ok,bench_throughput_unit\r\n1545,1537,100,10,True,GB/s\r\n2010,2002,120,20,True,GB/s\r\n2350,2340,130,30,True,GB/s\r\n")
    return repo / (stem + ".json")


def snapshot(repo):
    return {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}


def refuses(description, action):
    try:
        action()
    except (ValueError, OSError):
        check(description, True)
    else:
        check(description, False)


with tempfile.TemporaryDirectory(prefix="headroom-release-test-") as temporary:
    base = Path(temporary)
    repo = base / "source"
    repo.mkdir()
    for relative in builder.ROOT_FILES:
        write(repo, relative, "Raymond owns this test fixture.\n")
    census_path = write(repo, "analysis/build_data_manifest.py", (REPO_ROOT / "analysis/build_data_manifest.py").read_bytes())
    # Ensure the canonical classification source itself is distributed, without editing its rules.
    write(repo, "analysis/analyze_sweep.py", (REPO_ROOT / "analysis/analyze_sweep.py").read_bytes())
    write(repo, "data/frequency-sweeps/README.md", "Synthetic sweep root.\n")
    write(repo, "data/frequency-sweeps/mixed/README.md", "Dataset and kit verification share this folder.\n")
    good = session(repo, "mixed/good")
    kittest = session(repo, "mixed/kit", "5060ti-kittest-stock-gemm-stock")
    excluded = session(repo, "mixed/no", "kitverify-idle")
    verification = session(repo, "verify/early", "verify-3pt")
    nested = session(repo, "mixed/nested/suite")
    write(repo, "data/frequency-sweeps/verify/README.md", "Verification only.\n")
    write(repo, "data/frequency-sweeps/mixed/good_sweep_voltage.csv", "voltage_v\r\n0.720\r\n")
    write(repo, "data/frequency-sweeps/mixed/no_sweep_voltage.csv", "Do not copy.\n")
    write(repo, "data/frequency-sweeps/mixed/orphan_sweep.csv", "No session exists.\n")
    write(repo, "data/frequency-sweeps/mixed/machine-info.txt", "hostname: DESKTOP-PRIVATE\n")
    write(repo, "data/frequency-sweeps/mixed/runner-console.log", "username: operator42\n")
    write(repo, "data/frequency-sweeps/excluded-only/x.txt", "Excluded support folder without README.\n")
    raw_path = write(repo, "data/HWiNFO-Data/raw.CSV", "GPU Crossbar Clock,username\n1342,operator42\n")
    third_party = write(repo, "data/raw/upstream.csv", "Uncleared third-party data.\n")
    write(repo, "data/afterburner-profiles/numeric.json", '{"clock": 1530}')
    write(repo, "data/afterburner-profiles/VEN_10DE&DEV_1234.cfg", "Do not redistribute.\n")
    write(repo, "tools/frequency-sweep/helper.ps1", "# collection helper, never executed\n")
    write(repo, "tools/frequency-sweep/fixtures/example.json", "fixture excluded\n")
    write(repo, "tools/collection-kit/private.ini", "username=operator42\n")
    write(repo, "tools/collection-kit/HWiNFO64.INI", "SensorInterval=500\n")
    write(repo, ".obsidian/app.json", "private UI\n")
    write(repo, ".gitignore", "data/HWiNFO-Data/*\ndata/raw/*.csv\ntools/collection-kit/private.ini\n")
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    before = snapshot(repo)
    # Inventory already happened in the fixture setup; suppress only import cache writes.
    old_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        out = base / "release"
        report = builder.build_release(out, repo, identifiers=("Alice", "Raymond"))
        check("all and only census dataset-grade sessions are selected, including kittest", report["release_sweeps"] == 3)
        check("the excluded and verification neighbours remain in the source census", report["source_counts"] == {"dataset-grade": 3, "excluded": 1, "verification": 1})
        check("excluded session and its voltage extract are not copied", not (out / excluded.relative_to(repo)).exists() and not (out / "data/frequency-sweeps/mixed/no_sweep_voltage.csv").exists())
        check("verification measurements are not counted or copied", not (out / verification.relative_to(repo)).exists())
        check("source and release censuses have distinct row counts", len(json.loads((out / "manifest/SOURCE-CENSUS.json").read_text())) == 5 and len(json.loads((out / "data/MANIFEST.json").read_text())) == 3)
        check("session BOM and CRLF samples are preserved exactly", (out / good.relative_to(repo)).read_bytes() == good.read_bytes() and (out / good.with_suffix(".csv").relative_to(repo)).read_bytes() == good.with_suffix(".csv").read_bytes())
        check("the rule source is copied unchanged", (out / census_path.relative_to(repo)).read_bytes() == census_path.read_bytes())
        check("matching distilled voltage telemetry is included", (out / "data/frequency-sweeps/mixed/good_sweep_voltage.csv").exists())
        check("nested missing READMEs and excluded-only missing READMEs are reported", set(report["missing_readmes"]) == {"data/frequency-sweeps/mixed/nested", "data/frequency-sweeps/excluded-only"})
        check("ancestor READMEs are present", (out / "data/frequency-sweeps/README.md").exists() and (out / "data/frequency-sweeps/mixed/README.md").exists())
        omissions = {x["path"]: x["reason"] for x in report["omitted_files"]}
        check("census-excluded files carry their named rule", omissions[excluded.relative_to(repo).as_posix()] == "census-kit-verification")
        check("orphan samples are reported rather than silently selected", "data/frequency-sweeps/mixed/orphan_sweep.csv" in omissions and any("NO SESSION" in x for x in report["structural_problems"]))
        check("raw HWiNFO and third-party inputs are omitted and inventoried", not (out / raw_path.relative_to(repo)).exists() and not (out / third_party.relative_to(repo)).exists() and raw_path.relative_to(repo).as_posix() in report["gitignored_inputs"])
        check("ignored collection configuration is never distributed", not (out / "tools/collection-kit/private.ini").exists())
        check("ordinary HWiNFO configuration required by the kit is copied", (out / "tools/collection-kit/HWiNFO64.INI").is_file())
        check("raw profiles, transcripts and machine-info are excluded", not (out / "data/afterburner-profiles/VEN_10DE&DEV_1234.cfg").exists() and not (out / "data/frequency-sweeps/mixed/machine-info.txt").exists() and not (out / "data/frequency-sweeps/mixed/runner-console.log").exists())
        check("numeric curve JSON is retained for the predictor", (out / "data/afterburner-profiles/numeric.json").exists())
        check("source history and Obsidian state are not copied", not (out / ".git").exists() and not (out / ".obsidian").exists())
        check("MIT/data licenses, citation and checksum convention are present", all((out / x).exists() for x in ("LICENSE", "LICENSE-DATA", "CITATION.cff", "CHECKSUMS.md")))
        check("citation does not invent a DOI or source-as-release URL", "doi:" not in (out / "CITATION.cff").read_text() and "repository-code:" not in (out / "CITATION.cff").read_text())
        kinds = {x["kind"] for x in report["identifier_findings"]}
        check("known names, user paths and explicit account fields are flagged", {"windows-path", "account-or-host-field", "known-identifier-1"} <= kinds)
        check("identifier report gives locations and token hashes, without copying the sensitive match", all("match" not in x for x in report["identifier_findings"]))
        check("generated README/citation and the report are scanned too", {"README.md", "CITATION.cff", "RELEASE-REPORT.json"} <= set(report["identifier_scanned_files"]) and {"CITATION.cff", "RELEASE-REPORT.json"} <= {x["path"] for x in report["identifier_findings"]})
        check("source bytes and file inventory are unchanged after assembly", snapshot(repo) == before)
        expected = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
        hashed = {}
        for line in (out / "SHA256SUMS").read_text().splitlines():
            digest, relative = line.split("  ", 1)
            hashed[relative] = digest
        check("checksums cover the report and every payload file exactly once", set(hashed) == expected and len(hashed) == len(expected))
        check("every published checksum hashes the distributed bytes", all(hashlib.sha256((out / name).read_bytes()).hexdigest() == digest for name, digest in hashed.items()))
        check("the source-independent verifier checks the complete artifact", builder.verify_release(out) == {"files": len(expected), "sweeps": 3})
        # Rehash an altered CSV to test semantic census agreement, independently of byte integrity.
        original_manifest_csv = (out / "data/MANIFEST.csv").read_bytes()
        (out / "data/MANIFEST.csv").write_bytes(original_manifest_csv.replace(b"Synthetic GPU", b"Changed GPU"))
        original_sums = (out / "SHA256SUMS").read_bytes()
        altered_digest = hashlib.sha256((out / "data/MANIFEST.csv").read_bytes()).hexdigest()
        (out / "SHA256SUMS").write_bytes(original_sums.replace(hashed["data/MANIFEST.csv"].encode(), altered_digest.encode()))
        refuses("a deliberately rehashed CSV census mismatch is caught", lambda: builder.verify_release(out))
        (out / "data/MANIFEST.csv").write_bytes(original_manifest_csv)
        (out / "SHA256SUMS").write_bytes(original_sums)
        original_samples = (out / good.with_suffix(".csv").relative_to(repo)).read_bytes()
        (out / good.with_suffix(".csv").relative_to(repo)).write_bytes(original_samples.replace(b"100,10", b"900,10"))
        refuses("a deliberate throughput mutation is caught by byte verification", lambda: builder.verify_release(out))
        (out / good.with_suffix(".csv").relative_to(repo)).write_bytes(original_samples)
        write(out, "unlisted.txt", "extra\n")
        refuses("a deliberately injected unlisted file is caught", lambda: builder.verify_release(out))
        (out / "unlisted.txt").unlink()
        check("sample clocks unequal to targets survive and are usable by the shipped analysis", b"1545,1537" in (out / good.with_suffix(".csv").relative_to(repo)).read_bytes())
        analysis_run = subprocess.run([sys.executable, str(out / "analysis/analyze_sweep.py"), "--pattern", "**/*good_sweep.csv"], capture_output=True, text=True)
        check("a copied read-only analysis runs in the trimmed tree", analysis_run.returncode == 0 and "optimum" in analysis_run.stdout)
        check("LF/CRLF normalization would change the release checksum", hashlib.sha256(good.with_suffix(".csv").read_bytes()).hexdigest() != hashlib.sha256(good.with_suffix(".csv").read_bytes().replace(b"\r\n", b"\n")).hexdigest())
        refuses("existing output is refused without overwriting", lambda: builder.build_release(out, repo))
        refuses("output under data is refused before any mutation", lambda: builder.build_release(repo / "data/release", repo))
        refuses("the source repository itself is refused", lambda: builder.build_release(repo, repo))
        refuses("an ancestor directory is refused", lambda: builder.build_release(base, repo))
        refuses("a plain file cannot be an output directory", lambda: builder.build_release(raw_path, repo))
        empty = base / "empty"
        empty.mkdir()
        # Compare RESOLVED paths: GitHub's Windows runner puts temp under the 8.3 short name
        # RUNNER~1, which resolve() expands, so the raw path never matched there (CI,
        # 2026-10-03; local temp paths are already long, so it passed here).
        check("an existing empty external directory is allowed", builder.validate_output(repo, empty) == empty.resolve())
        hidden = base / "hidden"
        hidden.mkdir()
        write(hidden, ".keep", "keep\n")
        refuses("hidden files also prevent overwriting", lambda: builder.build_release(hidden, repo))
        docs = base / "owner-docs"
        write(docs, "README.md", "# Public README\n")
        write(docs, "CITATION.cff", "cff-version: 1.2.0\ntitle: Synthetic\n")
        write(docs, "DATASHEET.md", "# Datasheet\n")
        census_rows_source = [good, kittest, nested]

        def census(rows):
            write(repo, builder.DESKTOP_CENSUS, "sweep,verdict\r\n" + "".join(
                p.relative_to(repo).as_posix() + ",quiet\r\n" for p in rows))
        builder.DESKTOP_CENSUS_GPU = "Synthetic GPU"  # the fixture's sweeps stand in for the screened card
        census(census_rows_source[:2])
        refuses("a desktop census missing a distributed sweep is refused", lambda: builder.build_release(base / "census-short", repo, release_docs=docs))
        check("a refused census build creates no output", not (base / "census-short").exists())
        census(census_rows_source + [good])
        refuses("a desktop census naming a sweep twice is refused", lambda: builder.build_release(base / "census-twice", repo, release_docs=docs))
        census(census_rows_source + [excluded])
        docs_report = builder.build_release(base / "docs-review", repo, release_docs=docs)
        published = base / "docs-review"
        check("owner README, citation and datasheet replace the generated stubs byte for byte",
              all((published / n).read_bytes() == (docs / n).read_bytes() for n in builder.RELEASE_DOCS)
              and set(docs_report["release_docs"]) == set(builder.RELEASE_DOCS))
        census_rows = (published / "manifest/DESKTOP-LOAD-CENSUS.csv").read_bytes()
        check("the desktop-load census ships restricted to distributed sweeps, CRLF",
              good.relative_to(repo).as_posix().encode() in census_rows and b"mixed/no_sweep" not in census_rows
              and census_rows.startswith(b"sweep,verdict\r\n"))
        check("a release with owner documents still verifies", builder.verify_release(published)["sweeps"] == 3)
        for hidden_name in ("fixtures/unlisted.txt", "__pycache__/unlisted.bin", "nested/venv/private.txt"):
            write(published, hidden_name, "extra\n")
            refuses("an unlisted file under a skipped folder name is caught: " + hidden_name, lambda: builder.verify_release(published))
            (published / hidden_name).unlink()
        report_path = published / "RELEASE-REPORT.json"
        original_report = report_path.read_bytes()
        sums_path = published / "SHA256SUMS"
        original_sums = sums_path.read_bytes()
        bad = json.loads(original_report)
        bad["release_sweeps"] = 999
        report_path.write_bytes(builder.json_bytes(bad))
        sums_path.write_bytes(original_sums.replace(hashlib.sha256(original_report).hexdigest().encode(),
                                                    hashlib.sha256(report_path.read_bytes()).hexdigest().encode()))
        refuses("a rehashed report claiming the wrong sweep count is caught", lambda: builder.verify_release(published))
        report_path.write_bytes(original_report)
        sums_path.write_bytes(original_sums)
        self_findings = [x for x in docs_report["identifier_findings"] if x["path"] == "RELEASE-REPORT.json"]
        report_lines = report_path.read_text(encoding="utf-8").splitlines()
        fresh = builder.scan_bytes(report_path.read_bytes(), "RELEASE-REPORT.json", builder.DEFAULT_IDENTIFIERS)
        key = lambda x: (x["line"], x["kind"], x.get("match_sha256"))
        check("report self-findings match a fresh scan of the final report, line for line",
              sorted(map(key, self_findings)) == sorted(map(key, fresh)) and len(report_lines) > 0)
        citation = (docs / "CITATION.cff").read_bytes()
        (docs / "CITATION.cff").write_bytes(citation + b"doi: ZENODO-DOI-PENDING\n")
        refuses("owner documents still carrying a PENDING placeholder are refused",
                lambda: builder.build_release(base / "docs-pending", repo, release_docs=docs))
        (docs / "CITATION.cff").unlink()
        refuses("owner documents without a citation are refused", lambda: builder.build_release(base / "docs-missing", repo, release_docs=docs))
        (repo / builder.DESKTOP_CENSUS).unlink()
        builder.DESKTOP_CENSUS_GPU = "NVIDIA GeForce RTX 5060 Ti"
        strip = builder.strip_emoji_bytes
        check("a check alone in a table cell becomes yes", strip("| rises | \u2705 |".encode()) == b"| rises | yes |")
        check("a check after a value becomes (yes), a cross (no)",
              strip("| 1545 \u2705 | 1065 \u2717 |".encode()) == b"| 1545 (yes) | 1065 (no) |")
        check("a leading marker emoji and its space are removed",
              strip("\u26a0\ufe0f **Note** and \U0001f511 key".encode()) == b"**Note** and key")
        check("a BOM, CRLF and arrows survive", strip("\ufeffa \u2192 b\r\n".encode()) == "\ufeffa \u2192 b\r\n".encode())
        readme = repo / "data/frequency-sweeps/mixed/README.md"
        original_readme = readme.read_bytes()
        readme.write_bytes("\u2705 Dataset and kit verification share this folder.\n".encode())
        emoji_report = builder.build_release(base / "emoji-review", repo, strip_emoji=True)
        edited = {r["path"]: r for r in emoji_report["copied_files"] if r.get("edit")}
        check("--strip-emoji edits documentation, records both hashes, and leaves code alone",
              set(edited) == {"data/frequency-sweeps/mixed/README.md"}
              and edited["data/frequency-sweeps/mixed/README.md"]["source_sha256"] == hashlib.sha256(readme.read_bytes()).hexdigest()
              and (base / "emoji-review/data/frequency-sweeps/mixed/README.md").read_bytes() == b"Dataset and kit verification share this folder.\n")
        check("an emoji-stripped release verifies", builder.verify_release(base / "emoji-review")["sweeps"] == 3)
        readme.write_bytes(original_readme)
        raw_report = builder.build_release(base / "raw-review", repo, include_raw=True)
        check("raw HWiNFO inclusion requires the explicit option and retains exact bytes", raw_report["raw_hwinfo_included"] and (base / "raw-review" / raw_path.relative_to(repo)).read_bytes() == raw_path.read_bytes())
        check("raw inclusion still does not copy third-party tables", not (base / "raw-review" / third_party.relative_to(repo)).exists())
        sample = builder.scan_bytes(b"email: alice@example.test\npath: /home/alice/bench\n", "Alice/record.json", ("Alice",))
        check("filenames, emails and Unix account paths are scanned", {"email", "unix-account-path", "known-identifier-1"} <= {x["kind"] for x in sample} and any(x["line"] == 0 for x in sample))
        utf16 = builder.scan_bytes("username: Alice\n".encode("utf-16"), "record.txt", ("Alice",))
        check("UTF-16 identifiers are not skipped", any(x["kind"] == "known-identifier-1" for x in utf16))
        check("binary content gets an explicit manual-review finding", builder.scan_bytes(b"binary\x00content", "file.bin", ()) == [{"path": "file.bin", "line": 0, "kind": "binary-needs-manual-review"}])
        with patch.object(builder, "REPO_ROOT", repo), patch.object(builder, "build_release", return_value=report):
            check("CLI reports review-required with exit 2", builder.main([str(base / "cli")]) == 2)
        # Broken required measurements fail before creating the destination.
        good.with_suffix(".csv").unlink()
        failed_output = base / "failed"
        refuses("missing required samples prevent an incomplete release", lambda: builder.build_release(failed_output, repo))
        check("missing samples fail before output creation", not failed_output.exists())
        write(repo, good.with_suffix(".csv").relative_to(repo).as_posix(), "restored\n")
        good.write_text("{bad JSON}", encoding="utf-8")
        refuses("unreadable sessions cannot disappear from the release", lambda: builder.build_release(base / "bad-json", repo))
        good.write_text("[]", encoding="utf-8")
        refuses("valid non-object JSON is refused explicitly", lambda: builder.build_release(base / "wrong-shape", repo))
        # Symlink privileges are optional on Windows; record an unavailable check without claiming it passed.
        link = base / "source-alias"
        try:
            link.symlink_to(repo, target_is_directory=True)
        except OSError:
            print("  [NOTE] Symlink creation is unavailable on this host; alias test was not run.")
        else:
            refuses("an output alias resolving inside the repository is refused", lambda: builder.validate_output(repo, link / "out"))
        if sys.platform == "win32":
            junction = base / "source-junction"
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(repo)], capture_output=True)
            if result.returncode == 0:
                refuses("a Windows junction output alias is refused after resolving", lambda: builder.validate_output(repo, junction / "out"))
                refuses("source directory junctions are rejected by the file walker", lambda: builder.files_under(junction))
            else:
                print("  [NOTE] Junction creation is unavailable on this host; junction tests were not run.")
    finally:
        sys.dont_write_bytecode = old_bytecode

print(f"\n{passed} checks passed.")
