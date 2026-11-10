"""Is the `membw` stall at ~1627 MHz achieved in the historical 5060 Ti data too? (GPT Job 12)

Chord residual, exactly as `data/frequency-sweeps/5060ti-membw-silent-20260922/README.md` computes
it: at each interior point, throughput against the straight line between its two neighbours, linear
in ACHIEVED clock, in percent. A negative residual is a point below that line: a flatter rise, not
necessarily a fall.

Where a sweep has a committed `_voltage.csv` extract, the crossbar clock at the same point is
compared with its neighbours' midpoint too, since worklist 4n (2026-09-24) found the 09-22 stall to be
the last clock before a crossbar step.

Only committed CSVs are read. Run: python analysis/membw_chord_history.py [--all]
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWEEPS = ROOT / 'data' / 'frequency-sweeps'
NEAR = 15   # MHz either side of 1627 achieved counts as "a point near 1627"
CENTRE = 1627


def is_5060ti_membw(json_path):
    try:
        meta = json.loads(json_path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None
    if '5060 Ti' not in str(meta.get('gpu_name', '')):
        return None
    if '--workload membw' not in str(meta.get('workload_command', '')):
        return None
    return meta


def load_points(csv_path):
    points = []
    with open(csv_path, encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            try:
                achieved = float(row['achieved_frequency_avg'])
                throughput = float(row['bench_throughput'])
            except (KeyError, ValueError):
                continue
            if throughput > 0 and row.get('bench_ok', 'True') == 'True':
                points.append((achieved, throughput, int(float(row['target_frequency_mhz']))))
    points.sort()
    return points


def chord_residuals(points):
    """[(achieved, target, residual %)] for every interior point."""
    out = []
    for i in range(1, len(points) - 1):
        (x0, y0, _), (x1, y1, target), (x2, y2, _) = points[i - 1], points[i], points[i + 1]
        if x2 == x0:
            continue
        line = y0 + (y2 - y0) * (x1 - x0) / (x2 - x0)
        out.append((x1, target, 100.0 * (y1 / line - 1.0)))
    return out


def crossbar_offsets(voltage_path):
    """{target: crossbar minus its neighbours' midpoint, MHz} from a committed extract."""
    rows = []
    with open(voltage_path, encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append((float(row['achieved']), int(float(row['target'])), float(row['crossbar'])))
            except (KeyError, ValueError):
                continue
    rows.sort()
    return {rows[i][1]: rows[i][2] - (rows[i - 1][2] + rows[i + 1][2]) / 2.0
            for i in range(1, len(rows) - 1)}


def main():
    show_all = '--all' in sys.argv
    results = []
    for json_path in sorted(SWEEPS.rglob('*_sweep.json')):
        meta = is_5060ti_membw(json_path)
        if meta is None:
            continue
        csv_path = json_path.with_suffix('.csv')
        if not csv_path.exists():
            continue
        residuals = chord_residuals(load_points(csv_path))
        near = [r for r in residuals if abs(r[0] - CENTRE) <= NEAR]
        if not near and not show_all:
            continue
        voltage_path = json_path.with_name(json_path.stem + '_voltage.csv')
        xbar = crossbar_offsets(voltage_path) if voltage_path.exists() else None
        results.append((json_path, meta, residuals, near, xbar))

    print(f'5060 Ti membw sweeps with an interior point within {NEAR} MHz of {CENTRE} achieved: '
          f'{sum(1 for r in results if r[3])}')
    below = lowest = 0
    for json_path, meta, residuals, near, xbar in results:
        rel = json_path.relative_to(SWEEPS).as_posix()
        if not near:
            print(f'  (no point near {CENTRE}) {rel}')
            continue
        achieved, target, value = near[0]
        rank_lowest = min(residuals, key=lambda r: r[2])[0] == achieved
        below += value < 0
        lowest += rank_lowest
        others = [r[2] for r in residuals if r[0] != achieved]
        xbar_text = ''
        if xbar is not None and target in xbar:
            xbar_text = f'  crossbar {xbar[target]:+.1f} MHz vs neighbours'
        print(f'  {value:+6.2f}% at {achieved:.0f} (target {target})  '
              f'{"LOWEST" if rank_lowest else "      "}  others {min(others):+.2f}..{max(others):+.2f}'
              f'{xbar_text}  {rel}')
        print(f'         settings: {str(meta.get("applied_settings", ""))[:110]}')
    total = sum(1 for r in results if r[3])
    print(f'\nBelow its chord: {below} of {total}. Lowest interior residual in its sweep: {lowest} of {total}.')


if __name__ == '__main__':
    main()
