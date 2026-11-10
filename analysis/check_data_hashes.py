"""Check committed measurement files against a reviewed, line-ending-neutral hash list.

USAGE
    python analysis/check_data_hashes.py --check
    python analysis/check_data_hashes.py --write

The first --write on the real repository must be reviewed before it is run. --check
fails closed while docs/data-measurement-hashes.json is absent.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = Path("docs/data-measurement-hashes.json")
ALGORITHM = "sha256"
NORMALIZATION = "CRLF and lone CR bytes become LF; all other bytes are unchanged"
SCOPE = ("Git-tracked and nonignored new files under data/, excluding Markdown, .gitkeep, "
         "data/MANIFEST.csv and data/MANIFEST.json")
EXCLUDED = {"data/MANIFEST.csv", "data/MANIFEST.json"}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


def eligible(name):
    """Git's repository-relative paths use forward slashes on all platforms.

    Every record type, not only CSV/JSON: widened 2026-09-22 at review, because the first scope
    left 76 tracked provenance files unguarded - the Afterburner profile snapshots (.cfg) that are
    the only backup of the tuned curves, the collection-kit run logs and the stability-run logs.
    Markdown stays out because READMEs are legitimately edited.
    """
    return (name.startswith("data/") and name not in EXCLUDED
            and Path(name).suffix.lower() != ".md" and Path(name).name != ".gitkeep")


def discover(repo_root):
    """Include deleted tracked files and new nonignored files, but not fetched datasets."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "data"],
        cwd=repo_root, capture_output=True, check=True,
    )
    names = {os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw}
    return sorted(name for name in names if eligible(name))


def digest(path):
    """Hash bytes after normalizing platform line endings without decoding the file."""
    raw = path.read_bytes()
    canonical = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(canonical).hexdigest()


def collect(repo_root):
    hashes = {}
    missing = []
    for name in discover(repo_root):
        path = repo_root / name
        if path.is_symlink() or not path.is_file():
            missing.append(name)
        else:
            hashes[name] = digest(path)
    return hashes, missing


def document(hashes):
    return {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "normalization": NORMALIZATION,
        "scope": SCOPE,
        "files": hashes,
    }


def write(repo_root, manifest_path):
    hashes, missing = collect(repo_root)
    if missing:
        print(f"FAIL: {len(missing)} tracked measurement file(s) missing or symlinked:")
        for name in missing:
            print(f"  {name}")
        return 1
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(document(hashes), indent=2, ensure_ascii=True) + "\n"
    manifest_path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {len(hashes)} hashes to {manifest_path}")
    print("Review the entire hash-list diff before treating it as the new baseline.")
    return 0


def read_manifest(path):
    # PowerShell 5.1 can add a UTF-8 BOM when someone edits JSON by hand.
    with path.open(encoding="utf-8-sig") as handle:
        saved = json.load(handle)
    if not isinstance(saved, dict):
        raise ValueError("hash list must be a JSON object")
    for key, expected in (("schema_version", 1), ("algorithm", ALGORITHM),
                          ("normalization", NORMALIZATION), ("scope", SCOPE)):
        if saved.get(key) != expected:
            raise ValueError(f"hash-list {key} is missing or has an unsupported value")
    hashes = saved.get("files")
    if not isinstance(hashes, dict):
        raise ValueError("hash-list files must be a JSON object")
    for name, value in hashes.items():
        if not isinstance(name, str) or not eligible(name):
            raise ValueError(f"ineligible path in hash list: {name!r}")
        if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
            raise ValueError(f"invalid SHA-256 digest for {name!r}")
    return hashes


def check(repo_root, manifest_path):
    if not manifest_path.is_file():
        print(f"FAIL: hash list missing: {manifest_path}")
        print("The first baseline must be generated and reviewed before this gate can pass.")
        return 1
    try:
        expected = read_manifest(manifest_path)
        actual, missing_on_disk = collect(repo_root)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: cannot check measurement hashes: {exc}")
        return 1
    missing = sorted(set(expected) - set(actual))
    unhashed = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual)
                     if expected[name] != actual[name])
    # A deleted tracked file that was absent even from the saved list is still an error.
    unlisted_missing = sorted(set(missing_on_disk) - set(expected))
    for label, names in (("missing or symlinked", missing),
                         ("unhashed new", unhashed),
                         ("changed", changed),
                         ("tracked but absent and unhashed", unlisted_missing)):
        for name in names:
            print(f"FAIL [{label}] {name}")
    if missing or unhashed or changed or unlisted_missing:
        print(f"FAILED: {len(missing)} missing, {len(unhashed)} unhashed, "
              f"{len(changed)} changed, {len(unlisted_missing)} unlisted missing.")
        return 1
    print(f"PASS: {len(actual)} measurement hashes match {manifest_path}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true", help="Write a baseline for review.")
    modes.add_argument("--check", action="store_true", help="Fail on missing, new or changed data.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT,
                        help="Repository root; useful for testing with a temporary copy.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="Hash-list path, relative to repository root unless absolute.")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
    if args.write:
        return write(root, manifest)
    return check(root, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
