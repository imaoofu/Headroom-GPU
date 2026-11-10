"""Desktop-load census of every committed RTX 5060 Ti sweep, from whatever raw HWiNFO logs survive.

    python tools/hwinfo-logging/scan_desktop_load_corpus.py [--out docs/desktop-load-census-20261003.csv]

Written 2026-10-03, after the Claude desktop app's visible window was shown to cost 6-9% of `membw`
(data/frequency-sweeps/5060ti-deskload-20261003/). Its signature is HWiNFO's "Framerate Presented
(avg) [FPS]": quiet windows read 4-7 fps, loaded ones 150-240. For each sweep JSON on the 5060 Ti it
finds every raw HWiNFO log (data/HWiNFO-Data, C:/headroom-bench, the USB kit's results) whose samples
fall inside the sweep, and takes the median framerate over the benchmark windows when the sweep CSV
records them, else over the sweep's start-to-end span.

Verdicts: LOAD (median above 30 fps), quiet, no-log (no surviving raw log covers it), no-column (a log
covers it without the framerate column). Thresholds come from one day's two clusters; this is a
screen. HWiNFO stamps local time; every log here is from August-October 2026, PDT (UTC-7).
"""
import argparse
import csv
import datetime
import glob
import json
import os
import statistics
from bisect import bisect_left, bisect_right
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TZ = datetime.timezone(datetime.timedelta(hours=-7))
FPS = "Framerate Presented (avg) [FPS]"
BUS = "GPU Bus Load [%]"
FPS_LIMIT = 30.0


def rawLogs():
    roots = [REPO / "data" / "HWiNFO-Data", Path("C:/headroom-bench"), Path("F:/headroom-kit/results")]
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for path in glob.glob(str(root / "**" / "*.csv"), recursive=True) + glob.glob(str(root / "**" / "*.CSV"), recursive=True):
            name = os.path.basename(path).lower()
            if "hwinfo" not in name and "HWiNFO-Data" not in path:
                continue
            key = (name, os.path.getsize(path))
            if key in seen:
                continue
            seen.add(key)
            yield path


def loadLog(path):
    """Sorted sample times, framerates and bus loads; None columns when absent."""
    with open(path, newline="", encoding="latin-1") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return None
        if len(header) < 3 or header[0] != "Date":
            return None
        fi = header.index(FPS) if FPS in header else None
        # The NVIDIA block's bus load; the PC's AMD iGPU has no such column.
        bi = header.index(BUS) if BUS in header else None
        times, fps, bus = [], [], []
        for row in reader:
            try:
                t = datetime.datetime.strptime(row[0] + " " + row[1], "%d.%m.%Y %H:%M:%S.%f").replace(tzinfo=TZ).timestamp()
            except (ValueError, IndexError):
                continue
            times.append(t)
            fps.append(float(row[fi]) if fi is not None and row[fi] not in ("", "No") else None)
            bus.append(float(row[bi]) if bi is not None and row[bi] not in ("", "No") else None)
    if not times:
        return None
    order = sorted(range(len(times)), key=times.__getitem__)
    return {"path": path, "t": [times[i] for i in order], "fps": [fps[i] for i in order],
            "bus": [bus[i] for i in order], "hasFps": fi is not None}


def iso(text):
    return datetime.datetime.fromisoformat(text[:26] + text[-6:] if len(text) > 32 else text).timestamp()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO / "docs" / "desktop-load-census-20261003.csv"))
    args = parser.parse_args()
    logs = [l for l in (loadLog(p) for p in rawLogs()) if l]
    print(f"{len(logs)} raw HWiNFO logs indexed, {sum(l['hasFps'] for l in logs)} with the framerate column.")

    rows = []
    for jpath in sorted(glob.glob(str(REPO / "data" / "frequency-sweeps" / "**" / "*_sweep.json"), recursive=True)):
        try:
            meta = json.load(open(jpath, encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if "5060" not in str(meta.get("gpu_name", "")) or not meta.get("started_at") or not meta.get("ended_at"):
            continue
        start, end = iso(meta["started_at"]), iso(meta["ended_at"])
        spans = []
        cpath = jpath[: -len(".json")] + ".csv"
        if os.path.exists(cpath):
            for point in csv.DictReader(open(cpath, encoding="utf-8-sig")):
                try:
                    spans.append((float(point["window_start_unix"]), float(point["window_end_unix"])))
                except (KeyError, TypeError, ValueError):
                    pass
        basis = "benchmark windows" if spans else "sweep span"
        spans = spans or [(start, end)]
        fps, bus, covered, noColumn = [], [], False, False
        for log in logs:
            if log["t"][0] > end or log["t"][-1] < start:
                continue
            for a, b in spans:
                lo, hi = bisect_left(log["t"], a), bisect_right(log["t"], b)
                if hi <= lo:
                    continue
                covered = True
                if not log["hasFps"]:
                    noColumn = True
                    continue
                fps += [v for v in log["fps"][lo:hi] if v is not None]
                bus += [v for v in log["bus"][lo:hi] if v is not None]
        rel = os.path.relpath(jpath, REPO).replace("\\", "/")
        if fps:
            med = statistics.median(fps)
            verdict = "LOAD" if med > FPS_LIMIT else "quiet"
        else:
            med, verdict = None, ("no-column" if covered and noColumn else "no-log")
        rows.append({"sweep": rel, "directory": rel.split("/")[2] if rel.count("/") >= 3 else "(top level)",
                     "label": meta.get("session_label", ""), "startedAt": meta["started_at"], "basis": basis,
                     "samples": len(fps), "fpsMedian": "" if med is None else round(med, 1),
                     "busMedian": round(statistics.median(bus), 1) if bus else "", "verdict": verdict})
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    byDir = {}
    for r in rows:
        byDir.setdefault(r["directory"], []).append(r["verdict"])
    print(f"\n{len(rows)} RTX 5060 Ti sweeps. Verdict counts: " +
          ", ".join(f"{v} {sum(r['verdict'] == v for r in rows)}" for v in ("LOAD", "quiet", "no-column", "no-log")))
    print("\nBy directory (LOAD / quiet / unknown):")
    for d, vs in sorted(byDir.items()):
        unknown = sum(v in ("no-log", "no-column") for v in vs)
        print(f"  {d:45s} {vs.count('LOAD'):3d} / {vs.count('quiet'):3d} / {unknown:3d}")
    print(f"\nWrote {args.out}. A screen: a 'quiet' sweep is not proven clean, and 'unknown' is not quiet.")


if __name__ == "__main__":
    main()
