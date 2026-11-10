"""Flag sweep points measured beside a desktop load, from the HWiNFO log of each sweep.

    python tools/hwinfo-logging/check_desktop_load.py <sweep dir> <raw HWiNFO dir> [--utc-offset=-07:00]

For every benchmark window (the sweep CSV's window_start_unix / window_end_unix), it prints the
median of HWiNFO's "Framerate Presented (avg) [FPS]" and "GPU Bus Load [%]" and flags the window if
either is above a quiet desktop. Written 2026-10-01: an unidentified load presenting 148-240 fps
with 16-64% bus load sat under section 12, the section 14 dry run and section 10's re-collection,
about 10% on membw, while the section 14 session between them read 4-7 fps and 1-7%.

The thresholds (30 fps, 10% bus load) sit between those two clusters. They are a screen, not a
validated gate: one day's two clusters, on one card and one PC.

Changed 2026-10-03, before any section 15 sweep: a window is flagged on FRAMERATE alone, and bus
load is reported, not gated. The section 15 dry run flagged a `copy` sweep at 5.3 fps and 17% bus
load, and quiet historical suites (4-13 fps) show 13-36% NVIDIA bus load at some points from the
kernels themselves (copy, reduce, layernorm, bgemm), so the bus limit fails quiet runs. Framerate
separates the 2026-10-03 ABA states on its own (4-7 fps against 201-239). Bus load is used only
when a log has no framerate column.

Matching: each HWiNFO log is named <label>-hwinfo.csv and its sweep *_<label>_sweep.csv, as
tools/hwinfo-logging/Invoke-LoggedSweep.ps1 writes them. HWiNFO stamps local time; give the UTC
offset that applied at collection (default: this computer's current offset). Exit 1 if any window
is flagged, 2 if nothing could be checked.
"""
import argparse
import csv
import datetime
import statistics
import sys
from pathlib import Path

FPS_COLUMN = "Framerate Presented (avg) [FPS]"
BUS_COLUMN = "GPU Bus Load [%]"
FPS_LIMIT = 30.0
BUS_LIMIT = 10.0


def parseOffset(text):
    if text is None:
        return datetime.datetime.now().astimezone().tzinfo
    sign = -1 if text.startswith("-") else 1
    hours, minutes = text.lstrip("+-").split(":")
    return datetime.timezone(sign * datetime.timedelta(hours=int(hours), minutes=int(minutes)))


def number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def headerConflict(rows):
    """None, or why a repeated HWiNFO header contradicts the opening one.

    HWiNFO repeats its header (always when a log closes). A sensor that appears mid-log is appended at the
    END, so every later header keeps the opening names at their positions; then every column this file
    indexes is still the sensor it names. A later header that drops, renames or reorders an opening name
    means the positions moved, and nothing read by position can be trusted. GPT Job 107 (2026-10-18)
    showed such a log making this screen read bus load as framerate and still print `quiet`; a census the
    same day found no such header in any of the 528 raw logs on the bench PC, so this changes nothing
    collected so far."""
    if not rows:
        return None
    names = list(rows[0])
    while names and names[-1] == "":
        names.pop()
    for number, row in enumerate(rows[1:], start=2):
        if len(row) > 2 and row[0] == "Date" and row[1] == "Time" and row[:len(names)] != names:
            return f"the header repeated at row {number} does not keep the opening column names in place"
    return None


def windowMedians(rows, fpsIndex, busIndex, tz, start, end):
    fps, bus = [], []
    needed = max(i for i in (fpsIndex, busIndex, 1) if i is not None)
    for row in rows:
        if len(row) <= needed:
            continue  # a truncated row (GPT Job 107, F5): it used to raise IndexError after the time parsed
        try:
            t = datetime.datetime.strptime(row[0] + " " + row[1], "%d.%m.%Y %H:%M:%S.%f").replace(tzinfo=tz).timestamp()
        except (ValueError, IndexError):
            continue
        if start <= t <= end:
            f, b = number(row[fpsIndex]) if fpsIndex is not None else None, number(row[busIndex]) if busIndex is not None else None
            if f is not None:
                fps.append(f)
            if b is not None:
                bus.append(b)
    return (statistics.median(fps) if fps else None, statistics.median(bus) if bus else None, max(len(fps), len(bus)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sweepDir")
    parser.add_argument("hwinfoDir")
    parser.add_argument("--utc-offset", default=None)
    args = parser.parse_args()
    tz = parseOffset(args.utc_offset)
    sweepDir, hwinfoDir = Path(args.sweepDir), Path(args.hwinfoDir)

    checked = flagged = 0
    for log in sorted(hwinfoDir.glob("*-hwinfo.csv")):
        label = log.name[: -len("-hwinfo.csv")]
        sweeps = list(sweepDir.glob(f"*_{label}_sweep.csv"))
        if len(sweeps) != 1:
            print(f"{label}: {len(sweeps)} matching sweeps, skipped")
            continue
        with open(log, newline="", encoding="latin-1") as handle:
            rows = list(csv.reader(handle))
        header = rows[0]
        conflict = headerConflict(rows)
        if conflict:
            print(f"{label}: {conflict}, so this log cannot be checked")
            continue
        fpsIndex = header.index(FPS_COLUMN) if FPS_COLUMN in header else None
        busIndex = header.index(BUS_COLUMN) if BUS_COLUMN in header else None
        if fpsIndex is None and busIndex is None:
            print(f"{label}: this HWiNFO log has neither column, so it cannot be checked")
            continue
        with open(sweeps[0], newline="", encoding="utf-8-sig") as handle:
            points = list(csv.DictReader(handle))
        for point in points:
            start, end = number(point.get("window_start_unix")), number(point.get("window_end_unix"))
            if start is None or end is None:
                print(f"{label} @ {point.get('target_frequency_mhz')}: no benchmark window, skipped")
                continue
            fps, bus, n = windowMedians(rows[1:], fpsIndex, busIndex, tz, start, end)
            if n == 0:
                print(f"{label} @ {point['target_frequency_mhz']}: no HWiNFO samples in the window (check --utc-offset)")
                continue
            checked += 1
            bad = (fps > FPS_LIMIT) if fps is not None else (bus is not None and bus > BUS_LIMIT)
            flagged += bad
            print(f"{'LOAD ' if bad else 'quiet'} {label} @ {point['target_frequency_mhz']}: "
                  f"{'-' if fps is None else f'{fps:.1f}'} fps, {'-' if bus is None else f'{bus:.0f}'}% bus load, {n} samples")
    if checked == 0:
        print("Nothing could be checked.")
        sys.exit(2)
    print(f"\n{flagged} of {checked} windows flagged (above {FPS_LIMIT:.0f} fps; {BUS_LIMIT:.0f}% bus load only where no framerate is logged). "
          "A screen from one day's evidence, not a validated gate; a quiet result does not prove a clean run.")
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
