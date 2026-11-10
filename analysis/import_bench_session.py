"""Import one Headroom Bench session from the USB kit into data/, accepted attempts only.

Usage:
  python analysis/import_bench_session.py --session <kit>/results/bench-session-<stamp>.json
      --plan <kit>/results/bench-plan-<stamp>.json --dest data/frequency-sweeps/<card>-newcard-<date>
      [--results-root <kit>/results] [--write]

Without --write it prints what it would do and changes nothing.

WHY THIS EXISTS (GPT Job 88, R4, 2026-10-12). The only import instruction was "copy the results
into data/ and join the voltage", so the operator chose files by name and date. A failed attempt and
its resumed replacement can sit side by side on the USB, a scorer PASS checked GPU name and driver
but not the physical card, and nothing carried the bench session's desktop-load verdicts or the UTC
offset the HWiNFO join needs. This reads the bench session itself and decides from it:

- the session must be live (not a dry run), finished PASS, on a recorded GPU UUID, with its plan's
  SHA-256 equal to the one the session recorded;
- for each step key, the LAST attempt is the accepted one (the bench app's own rule when it
  decides PASS); earlier attempts are listed in IMPORT.json as rejected and never copied;
- every accepted sweep or suite step must have passed and been checked QUIET by the desktop-load
  check. A step left "unchecked" is refused too: the import is for data that was checked;
- each sweep or suite CSV is joined to ITS OWN step's HWiNFO log, by time, with the UTC offset
  recorded when that log started (join_hwinfo_voltage.py otherwise uses this computer's zone).

It writes IMPORT.json into the destination with the SHA-256 of every file it copied or made, and
score_new_card.py refuses a directory without one (verify_import below). Raw HWiNFO logs go to
data/HWiNFO-Data/<destination name>/, which git ignores; their hashes are in IMPORT.json.

GPT Job 89 (2026-10-13) audited the first version; fixed here: paths are kept relative to results
instead of flattened to basenames (I1), the results folder is found above a nested session file
(I2), nothing is parsed before it is hash-checked (I3), the copied plan is verified (I4), and a
failed import is built in staging folders so it leaves nothing behind.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

REPO = Path(__file__).resolve().parents[1]
JOIN = REPO / "tools" / "frequency-sweep" / "join_hwinfo_voltage.py"
SCHEMA = 1
MEASURED = ("sweep", "suite")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_json(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def kit_relative(recorded):
    """The part of a recorded kit path after its 'results' folder, e.g. ('x', 'y.csv')."""
    parts = PureWindowsPath(str(recorded)).parts
    lowered = [p.lower() for p in parts]
    if "results" not in lowered:
        raise ValueError(f"recorded path is not under the kit's results folder: {recorded}")
    index = len(lowered) - 1 - lowered[::-1].index("results")
    rest = parts[index + 1:]
    if not rest:
        raise ValueError(f"recorded path is the results folder itself: {recorded}")
    return rest


def find_results_root(session_path, results_root=None):
    """The kit's results folder: given, or the nearest parent of the session named 'results'.

    A live session may sit in a subfolder of results (Run-Plan.ps1 allows any path under it), while
    its outputs are recorded relative to results itself (GPT Job 89, I2)."""
    if results_root is not None:
        return Path(results_root)
    for parent in Path(session_path).parents:
        if parent.name.casefold() == "results":
            return parent
    raise ValueError("the session file is not inside a folder named 'results'; pass --results-root")


def inside(root, path):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def plan_import(session_path, plan_path, results_root=None):
    """Read the session and decide what to import. Raises ValueError on anything not importable."""
    session_path, plan_path = Path(session_path), Path(plan_path)
    session = load_json(session_path)
    results = find_results_root(session_path, results_root)
    problems = []
    if session.get("dryRun"):
        problems.append("the session is a dry run")
    if session.get("status") != "PASS":
        problems.append(f"the session finished {session.get('status')!r}, not 'PASS'")
    if not session.get("gpuUuid"):
        problems.append("the session recorded no GPU UUID")
    if not session.get("gpuName"):
        problems.append("the session recorded no GPU name")
    recorded_hash = str(session.get("planHash", "")).upper()
    if not recorded_hash or sha256(plan_path) != recorded_hash:
        problems.append("the plan file's SHA-256 is not the one the session recorded")
    final = session.get("finalState") or {}
    if not (final.get("clocks") or {}).get("verified"):
        problems.append("the session's final clock reset was not verified")
    if not (final.get("logging") or {}).get("stoppedVerified"):
        problems.append("the session's HWiNFO logging was not verified stopped")
    if problems:
        raise ValueError("; ".join(problems))

    attempts = {}
    for step in session.get("steps") or []:
        attempts.setdefault(step["key"], []).append(step)
    accepted, rejected = [], []
    for key, tries in attempts.items():
        for number, step in enumerate(tries[:-1], 1):
            rejected.append({"key": key, "attempt": number, "type": step.get("type"),
                             "verdict": step.get("verdict"), "start": step.get("start"),
                             "error": step.get("error"),
                             "desktopLoad": (step.get("desktopLoad") or {}).get("status")})
        last = tries[-1]
        if last.get("type") not in MEASURED:
            continue
        load = last.get("desktopLoad") or {}
        if last.get("verdict") != "PASS":
            raise ValueError(f"{key}: the accepted attempt's verdict is {last.get('verdict')!r}")
        if load.get("status") != "quiet":
            raise ValueError(f"{key}: the desktop-load check says {load.get('status')!r}, not 'quiet'")
        if not load.get("log") or not load.get("utcOffset"):
            raise ValueError(f"{key}: no HWiNFO log or UTC offset recorded with the step")
        witness = last.get("witness") or {}
        folder = witness.get("directory") if last["type"] == "suite" else witness.get("output")
        if not folder:
            raise ValueError(f"{key}: the step recorded no output folder")
        # Kept relative to results, never flattened to a basename: two logs called same.csv in
        # different folders are two logs (GPT Job 89, I1).
        folder_relative = Path(*kit_relative(folder))
        log_relative = Path(*kit_relative(load["log"]))
        source = results / folder_relative
        log = results / log_relative
        if not (inside(results, source) and inside(results, log)):
            raise ValueError(f"{key}: a recorded path leaves the results folder")
        if not source.is_dir():
            raise ValueError(f"{key}: output folder missing: {source}")
        if not log.is_file():
            raise ValueError(f"{key}: HWiNFO log missing: {log}")
        csvs = sorted(source.glob("*_sweep.csv"))
        checked = {PureWindowsPath(w["sweep"]).name for w in load.get("windows") or []}
        if not csvs or {c.name for c in csvs} != checked:
            raise ValueError(f"{key}: the sweep CSVs in {source.name} are not the ones the "
                             f"desktop-load check read")
        accepted.append({"key": key, "type": last["type"], "start": last.get("start"),
                         "end": last.get("end"), "folder": source, "folderRelative": folder_relative,
                         "log": log, "logRelative": log_relative,
                         "utcOffset": load["utcOffset"], "csvs": csvs,
                         "desktopLoad": {k: load.get(k) for k in ("status", "flagged", "unchecked")}})
    if not accepted:
        raise ValueError("the session has no accepted sweep or suite step")
    folders = [a["folderRelative"].as_posix().casefold() for a in accepted]
    if len(set(folders)) != len(folders):
        raise ValueError("two accepted steps write the same output folder")
    return session, accepted, rejected


def do_import(session_path, plan_path, dest, write=False, out=print, raw_root=REPO / "data" / "HWiNFO-Data",
              results_root=None):
    session_path, plan_path, dest = Path(session_path), Path(plan_path), Path(dest)
    session, accepted, rejected = plan_import(session_path, plan_path, results_root)
    raw = Path(raw_root) / dest.name
    out(f"Session {session_path.name}: {session.get('gpuName')} ({session.get('gpuUuid')}), "
        f"driver {session.get('driver')}, status {session.get('status')}.")
    for item in accepted:
        out(f"  accept {item['key']}: {item['folderRelative'].as_posix()} ({len(item['csvs'])} CSV), "
            f"log {item['logRelative'].as_posix()}, UTC offset {item['utcOffset']}, desktop load quiet")
    for item in rejected:
        out(f"  reject {item['key']} attempt {item['attempt']}: {item['verdict']} (kept out, listed)")
    if not write:
        out(f"Dry run: nothing written. Add --write to import into {dest}.")
        return None
    # Built in staging folders and renamed into place only once every join has succeeded, so a
    # failed import leaves nothing that blocks a retry (GPT Job 89). The staging folders hold only
    # copies this run made, so removing them on failure deletes no original.
    stage_dest = dest.with_name(dest.name + ".importing")
    stage_raw = raw.with_name(raw.name + ".importing")
    for path in (dest, raw, stage_dest, stage_raw):
        if path.exists():
            raise ValueError(f"refusing to write over an existing folder: {path}")
    created = []
    try:
        # Created inside the cleanup, so a failure making the second folder still removes the first
        # (GPT Job 93, R3). Only folders this call created are ever removed.
        for folder in (stage_dest, stage_raw):
            folder.mkdir(parents=True)
            created.append(folder)
        manifest = {"schema": SCHEMA, "tool": "analysis/import_bench_session.py",
                    "session": {"file": session_path.name, "sha256": sha256(session_path),
                                "plan": plan_path.name, "planSha256": sha256(plan_path),
                                "status": session.get("status"), "gpuName": session.get("gpuName"),
                                "gpuUuid": session.get("gpuUuid"), "driver": session.get("driver"),
                                "start": session.get("start"), "end": session.get("end")},
                    "accepted": [], "rejected": rejected}
        shutil.copy2(session_path, stage_dest / session_path.name)
        shutil.copy2(plan_path, stage_dest / plan_path.name)
        for item in accepted:
            target = stage_dest / item["folderRelative"]
            shutil.copytree(item["folder"], target)
            log_copy = stage_raw / item["logRelative"]
            log_copy.parent.mkdir(parents=True, exist_ok=True)
            if not log_copy.exists():
                shutil.copy2(item["log"], log_copy)
            elif sha256(log_copy) != sha256(item["log"]):
                raise ValueError(f"{item['key']}: two different logs map to {item['logRelative'].as_posix()}")
            joins = []
            for csv_path in item["csvs"]:
                copied = target / csv_path.name
                run = subprocess.run([sys.executable, str(JOIN), str(copied), str(log_copy), "--join-by", "time",
                                      f"--hwinfo-utc-offset={item['utcOffset']}"],
                                     capture_output=True, text=True)
                if run.returncode != 0:
                    raise ValueError(f"{item['key']}: the voltage join failed for {csv_path.name}: "
                                     f"{(run.stdout + run.stderr).strip()[-400:]}")
                voltage = copied.with_name(copied.stem + "_voltage.csv")
                joins.append({"csv": copied.relative_to(stage_dest).as_posix(),
                              "voltage": voltage.relative_to(stage_dest).as_posix(),
                              "voltageSha256": sha256(voltage)})
            files = sorted(p for p in target.rglob("*") if p.is_file())
            manifest["accepted"].append({
                "key": item["key"], "type": item["type"], "start": item["start"], "end": item["end"],
                "desktopLoad": item["desktopLoad"], "utcOffset": item["utcOffset"],
                "log": {"name": item["logRelative"].as_posix(), "sha256": sha256(log_copy)},
                "joins": joins,
                "files": {p.relative_to(stage_dest).as_posix(): sha256(p) for p in files}})
        (stage_dest / "IMPORT.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    except BaseException:
        for folder in created:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    stage_raw.rename(raw)
    stage_dest.rename(dest)
    out(f"Imported into {dest}; raw HWiNFO logs in {raw} (gitignored). Write the README, then score.")
    return manifest


def verify_import(directory, csv_paths, gpu_names=None):
    """Check the scored files against IMPORT.json. Returns a summary; raises ValueError otherwise.

    Every file is hash-checked BEFORE any of it is parsed (GPT Job 89, I3), and the GPU name is then
    read from the verified metadata, so a caller never has to read an unverified file to call this."""
    directory = Path(directory)
    csv_paths = [Path(p) for p in csv_paths]
    path = directory / "IMPORT.json"
    if not path.is_file():
        raise ValueError("no IMPORT.json: import with analysis/import_bench_session.py, which keeps "
                         "only the bench session's accepted, quiet attempts")
    manifest = load_json(path)
    session = manifest.get("session") or {}
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"IMPORT.json schema {manifest.get('schema')!r} is not {SCHEMA}")
    if session.get("status") != "PASS" or not session.get("gpuUuid"):
        raise ValueError("IMPORT.json does not describe a PASS session on a recorded GPU UUID")
    copied = directory / str(session.get("file"))
    if not copied.is_file() or sha256(copied) != session.get("sha256"):
        raise ValueError("the bench session file beside IMPORT.json is missing or changed")
    # The copied plan is part of the archive too (GPT Job 89, I4).
    copied_plan = directory / str(session.get("plan"))
    if not session.get("plan") or not copied_plan.is_file() or sha256(copied_plan) != session.get("planSha256"):
        raise ValueError("the bench plan file beside IMPORT.json is missing or changed")
    owners = {}
    for step in manifest.get("accepted") or []:
        if (step.get("desktopLoad") or {}).get("status") != "quiet":
            raise ValueError(f"{step.get('key')}: not quiet in IMPORT.json")
        for name in step.get("files") or {}:
            owners[name] = step
    metadata_paths = []
    for csv_path in csv_paths:
        relative = csv_path.resolve().relative_to(directory.resolve()).as_posix()
        if relative not in owners:
            raise ValueError(f"{relative} is not an accepted file in IMPORT.json")
        step = owners[relative]
        voltage = relative[:-4] + "_voltage.csv"
        if [j["voltage"] for j in step.get("joins") or [] if j["csv"] == relative] != [voltage]:
            raise ValueError(f"{relative}: its voltage join is not recorded in IMPORT.json")
        for companion in (relative, relative[:-4] + ".json", voltage):
            expected = (step.get("files") or {}).get(companion)
            target = directory / companion
            if expected is None or not target.is_file() or sha256(target) != expected:
                raise ValueError(f"{companion} is missing or differs from IMPORT.json")
        metadata_paths.append(directory / (relative[:-4] + ".json"))
    # Only now, with every byte verified, is anything parsed.
    recorded = load_json(copied)
    for field in ("status", "gpuUuid", "gpuName"):
        if recorded.get(field) != session.get(field):
            raise ValueError(f"IMPORT.json's {field} is not the copied bench session's")
    if str(recorded.get("planHash", "")).upper() != str(session.get("planSha256", "")).upper():
        raise ValueError("the copied plan is not the plan the bench session recorded")
    names = {load_json(p).get("gpu_name", "") for p in metadata_paths}
    if names != {session.get("gpuName")} or (gpu_names is not None and set(gpu_names) != names):
        raise ValueError(f"sweep metadata names {sorted(names)}, the bench session {session.get('gpuName')!r}")
    return {"uuid": session["gpuUuid"], "session": session.get("file"),
            "accepted": len(manifest.get("accepted") or []), "rejected": len(manifest.get("rejected") or [])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, default=None,
                        help="the kit's results folder, when the session file is not inside one")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        do_import(args.session, args.plan, args.dest, args.write, results_root=args.results_root)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"Not imported: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
