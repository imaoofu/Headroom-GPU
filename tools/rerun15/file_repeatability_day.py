"""File one section 22 (repeatability) day from C:\\headroom-bench into data/repeatability/.

Usage: python tools/rerun15/file_repeatability_day.py SESSION_DIR [--write]

SESSION_DIR is the runner's own folder (C:\\headroom-bench\\rerun15\\<stamp>-rep). Without --write it
prints what it would do. With --write it builds data/repeatability/day<N>-<yyyymmdd>/: every role's
sweep CSV and JSON, its wrapper result, the stock witnesses, session.log, runner-cleanup.json, the copy of
the runner the runner made of itself at launch, and a rerun15-inputs.json whose paths are rewritten relative to the day folder. Each
sweep is joined to its own HWiNFO log by time at the UTC offset the runner recorded, and the raw logs go
to data/HWiNFO-Data/<day folder>/, which git ignores. The day is built in a staging folder and renamed
into place only when every join succeeds. It refuses a dry run and an existing destination.

Written 2026-10-14 with section 22 so a day is filed the same way every time, rather than by hand.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JOIN = REPO / "tools" / "frequency-sweep" / "join_hwinfo_voltage.py"


def offset_text(minutes):
    sign = "-" if minutes < 0 else "+"
    minutes = abs(int(minutes))
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def plan(session):
    session = Path(session)
    manifest = json.loads((session / "rerun15-inputs.json").read_text(encoding="utf-8-sig"))
    if "section 22" not in str(manifest.get("section", "")):
        raise ValueError("not a section 22 session")
    if manifest.get("dryRun") is not False:
        raise ValueError("a dry run is a qualification; it is not filed as a day")
    rep = manifest.get("repeatability") or {}
    day, date = rep.get("day"), str(rep.get("localDate", ""))
    if day not in range(1, 6) or len(date) != 10:
        raise ValueError("the manifest records no day index or local date")
    for role, desc in (manifest.get("sweeps") or {}).items():
        label = Path(str((desc or {}).get("sweep", "") if isinstance(desc, dict) else "")).stem
        if "_rep-" not in label:
            raise ValueError(f"{role}: sweep {label!r} is not a section 22 day's label (a dry run's are repdry-)")
    if not (session / "runner-as-run.ps1.txt").is_file():
        raise ValueError("the session has no runner-as-run.ps1.txt (the runner copies itself at launch)")
    name = f"day{day}-{date.replace('-', '')}"
    return manifest, name


def file_day(session, write=False, data_root=REPO / "data", out=print):
    session = Path(session)
    manifest, name = plan(session)
    dest = data_root / "repeatability" / name
    raw = data_root / "HWiNFO-Data" / name
    out(f"{session.name} -> {dest} ({len(manifest['sweeps'])} roles); raw logs -> {raw}")
    if not write:
        out("Dry run: nothing written. Add --write.")
        return None
    stage = dest.with_name(dest.name + ".filing")
    stage_raw = raw.with_name(raw.name + ".filing")
    for path in (dest, raw, stage, stage_raw):
        if path.exists():
            raise ValueError(f"refusing to write over {path}")
    (stage / "wrapper").mkdir(parents=True)
    stage_raw.mkdir(parents=True)
    try:
        for role, desc in manifest["sweeps"].items():
            if not isinstance(desc, dict):
                raise ValueError(f"{role}: a retried role cannot be filed as a section 22 day")
            sweep = Path(desc["sweep"])
            shutil.copy2(sweep, stage / sweep.name)
            shutil.copy2(sweep.with_suffix(".json"), stage / sweep.with_suffix(".json").name)
            wrapper_name = f"{sweep.parent.name.split('_', 1)[-1]}-wrapper-result.json"
            shutil.copy2(desc["wrapper"], stage / "wrapper" / wrapper_name)
            log = Path(desc["hwinfo"])
            shutil.copy2(log, stage_raw / log.name)
            run = subprocess.run([sys.executable, str(JOIN), str(stage / sweep.name), str(stage_raw / log.name),
                                  "--join-by", "time", f"--hwinfo-utc-offset={offset_text(desc['utc_offset_minutes'])}"],
                                 capture_output=True, text=True)
            if run.returncode != 0:
                raise ValueError(f"{role}: voltage join failed: {(run.stdout + run.stderr).strip()[-300:]}")
            desc["sweep"] = sweep.name
            desc["wrapper"] = f"wrapper/{wrapper_name}"
            desc["hwinfo"] = f"../../HWiNFO-Data/{name}/{log.name}"
            store = (desc.get("witness") or {}).get("profile_store")
            if store:
                desc["witness"]["profile_store"] = f"witnesses/{Path(store).name}"
        shutil.copytree(session / "witnesses", stage / "witnesses")
        for extra in ("session.log", "runner-cleanup.json"):
            shutil.copy2(session / extra, stage / extra)
        # GPT Job 94, F7: the runner AS RUN, which it copied into its own session folder at launch.
        # The checkout this filer runs from may have changed since, so it is never used instead.
        shutil.copy2(session / "runner-as-run.ps1.txt", stage / "runner-Invoke-Rerun15Session.ps1.txt")
        (stage / "rerun15-inputs.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(stage_raw, ignore_errors=True)
        raise
    stage_raw.rename(raw)
    stage.rename(dest)
    out(f"Filed {dest}. Write its README, run check_data_hashes --write (additions only), then score.")
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("session", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        file_day(args.session, args.write)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"Not filed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
