"""Read one bench step's explicit sweep files and HWiNFO log; emit JSON only.

Uses the logged-sweep screen's thresholds. No measurement files are written.
"""
import argparse
import csv
import datetime
import importlib.util
import json
import math
import statistics
from pathlib import Path

SCREEN_PATH = Path(__file__).resolve().parents[1] / 'hwinfo-logging' / 'check_desktop_load.py'
SPEC = importlib.util.spec_from_file_location('headroom_desktop_screen', SCREEN_PATH)
SCREEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCREEN)


def finite_number(value):
    value = SCREEN.number(value)
    return value if value is not None and math.isfinite(value) else None


def columns(header):
    """Use the clock block carrying XBAR, not the first GPU (which may be an iGPU)."""
    fps = [i for i, name in enumerate(header) if name == SCREEN.FPS_COLUMN]
    bus = [i for i, name in enumerate(header) if name == SCREEN.BUS_COLUMN]
    xbar = [i for i, name in enumerate(header) if name == 'GPU Crossbar Clock [MHz]']
    if len(xbar) == 1:
        clocks = [i for i, name in enumerate(header) if name == 'GPU Clock [MHz]']
        before = [i for i in clocks if i < xbar[0]]
        after = [i for i in clocks if i > xbar[0]]
        if before:
            bus = [i for i in bus if max(before) < i < min(after, default=len(header))]
        else:
            bus = []  # The NVIDIA block cannot be bounded safely.
    elif len(xbar) > 1 or len(bus) > 1:
        bus = []  # Ambiguous multi-GPU log, never silently select the first.
    return (fps[0] if len(fps) == 1 else None,
            bus[0] if len(bus) == 1 else None)


def readable_lengths(rows, header):
    """The row lengths the screen may read, and the names of any columns HWiNFO appended.

    A row as long as the opening header is always readable. HWiNFO adds a sensor that appears mid-log
    as a new column at the END of each row, and writes the whole header again when the log closes. A
    longer row is read only when that closing header keeps every opening name at its own position, so
    the named columns provably did not move. Found 2026-10-17 in the new-card practice run: the CPU's
    integrated GPU began reporting an effective clock at 13:45, every later row gained one trailing
    column, and the old exact-length rule left 31 of 156 suite windows unchecked although the frame-rate
    and bus-load columns had stayed in place. Without a closing header, or with one whose names moved,
    longer rows are still refused."""
    names = list(header)
    while names and names[-1] == '':
        names.pop()
    closing = [r for r in rows[1:] if len(r) > 2 and r[0] == 'Date' and r[1] == 'Time']
    # Every repeated header must keep the opening names in place, not just the last one (GPT Job 107,
    # F2-F3); check_step refuses the whole log when one does not, before this is called.
    if closing and len(closing[-1]) > len(header) and closing[-1][:len(names)] == names:
        return set(range(len(header), len(closing[-1]) + 1)), [n for n in closing[-1][len(names):] if n]
    return {len(header)}, []


def check_step(sweep_files, log_path, utc_offset):
    result = dict(status='unchecked', log=str(log_path), utcOffset=utc_offset,
                  fpsLimit=SCREEN.FPS_LIMIT, busLimit=SCREEN.BUS_LIMIT,
                  windows=[], checked=0, flagged=0, unchecked=0,
                  limitation='This screen is not a validated gate; quiet does not prove a clean run.')
    try:
        with open(log_path, encoding='latin-1', newline='') as handle:
            rows = list(csv.reader(handle))
        header = rows[0] if rows else []
        fps_index, bus_index = columns(header)
        result['fpsColumnIndex'], result['busColumnIndex'] = fps_index, bus_index
        if fps_index is None and bus_index is None:
            result['reason'] = 'This log has no unambiguous desktop-load columns.'
            return result
        tz = SCREEN.parseOffset(utc_offset)
        conflict = SCREEN.headerConflict(rows)
        if conflict:
            result['reason'] = f'{conflict}, so no position in this log can be trusted.'
            return result
        allowed, appended = readable_lengths(rows, header)
        if appended:
            result['appendedColumns'] = appended
        refused_long = 0
        samples = []
        for row in rows[1:]:
            # Ignore repeated headers and an incomplete trailing row from the live writer; read a
            # longer row only when the closing header proves its extra columns were appended.
            if len(row) not in allowed:
                # Count only dated sample rows: headers and HWiNFO's sensor-group label line are not
                # samples (GPT Job 107, F6).
                dated = len(row) > 1 and row[0][:1].isdigit()
                refused_long += len(row) > len(header) and dated
                continue
            try:
                stamp = datetime.datetime.strptime(row[0] + ' ' + row[1],
                                                   '%d.%m.%Y %H:%M:%S.%f').replace(tzinfo=tz).timestamp()
            except (ValueError, IndexError):
                continue
            samples.append((stamp, finite_number(row[fps_index]) if fps_index is not None else None,
                            finite_number(row[bus_index]) if bus_index is not None else None))
        for path in sweep_files:
            with open(path, encoding='utf-8-sig', newline='') as handle:
                points = list(csv.DictReader(handle))
            for point in points:
                window = dict(sweep=str(path), targetMhz=point.get('target_frequency_mhz'),
                              status='unchecked', fpsMedian=None, busMedian=None, fpsSamples=0, busSamples=0)
                start = finite_number(point.get('window_start_unix'))
                end = finite_number(point.get('window_end_unix'))
                if start is None or end is None or end < start:
                    window['reason'] = 'No valid benchmark window.'
                else:
                    inside = [s for s in samples if start <= s[0] <= end]
                    fps = [s[1] for s in inside if s[1] is not None]
                    bus = [s[2] for s in inside if s[2] is not None]
                    window.update(fpsMedian=statistics.median(fps) if fps else None,
                                  busMedian=statistics.median(bus) if bus else None,
                                  fpsSamples=len(fps), busSamples=len(bus))
                    # Framerate alone when it is logged; bus load only as a fallback (changed
                    # 2026-10-03: kernels reach 13-36% bus load by themselves on a quiet desktop).
                    bad = ((window['fpsMedian'] > SCREEN.FPS_LIMIT) if fps else
                           bool(bus and window['busMedian'] > SCREEN.BUS_LIMIT))
                    if bad:
                        window['status'] = 'DESKTOP LOAD'
                    elif (fps_index is None or fps) and (bus_index is None or bus) and (fps or bus):
                        window['status'] = 'quiet'
                    else:
                        window['reason'] = 'No valid samples for an available column in the benchmark window.'
                result['windows'].append(window)
        result['flagged'] = sum(w['status'] == 'DESKTOP LOAD' for w in result['windows'])
        result['unchecked'] = sum(w['status'] == 'unchecked' for w in result['windows'])
        result['checked'] = len(result['windows']) - result['unchecked']
        if result['flagged']:
            result['status'] = 'DESKTOP LOAD'
        elif result['checked'] and not result['unchecked']:
            result['status'] = 'quiet'
        else:
            result['reason'] = 'One or more benchmark windows could not be checked, or no windows were found.'
        if refused_long:
            result['refusedLongerRows'] = refused_long
            result['reason'] = (result.get('reason', '') + f' {refused_long} log rows are longer than the header and '
                                'no closing header proves the extra columns were appended, so they were not read.').strip()
    except (OSError, ValueError, csv.Error) as error:
        # Missing telemetry is unchecked; preserve any flags already computed.
        result['status'] = 'DESKTOP LOAD' if any(w['status'] == 'DESKTOP LOAD' for w in result['windows']) else 'unchecked'
        result['reason'] = str(error)
        result['flagged'] = sum(w['status'] == 'DESKTOP LOAD' for w in result['windows'])
        result['unchecked'] = sum(w['status'] == 'unchecked' for w in result['windows'])
        result['checked'] = len(result['windows']) - result['unchecked']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--hwinfo-log', required=True)
    parser.add_argument('--utc-offset', required=True)
    parser.add_argument('--sweep', action='append', required=True)
    args = parser.parse_args()
    print(json.dumps(check_step(args.sweep, args.hwinfo_log, args.utc_offset), allow_nan=False))


if __name__ == '__main__':
    main()
