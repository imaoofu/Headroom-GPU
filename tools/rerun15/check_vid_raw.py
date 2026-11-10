"""Section 22: read the RAW HWiNFO samples inside each voltage-extract window of one filed role.

Usage: python tools/rerun15/check_vid_raw.py DAY_FOLDER_NAME ROLE      e.g. day1-20261015 pass1-copy

GPT Job 100 (2026-10-16) could not tell whether a 0.725 V stretch in a filed extract was a real reading or
a join artifact, because the raw logs under data/HWiNFO-Data/ are gitignored. This prints, per target, the
extract's median and sample count beside the raw samples' count, median, every VID code seen and the GPU
temperature range, so the two can be compared on the machine that holds the logs. Read-only; descriptive.
The reported voltage is a VID lookup, not a rail measurement.
"""

import csv
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main(day, role):
    extract = next((REPO / "data" / "repeatability" / day).glob(f"*_rep-{role}_sweep_voltage.csv"))
    raw = REPO / "data" / "HWiNFO-Data" / day / f"rep-{role}-hwinfo.csv"
    windows = list(csv.DictReader(open(extract, encoding="utf-8-sig")))
    tz = timezone(timedelta(minutes=int(float(windows[0]["hwinfoUtcOffsetMinutes"]))))
    with open(raw, encoding="latin-1", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    vcol = [i for i, h in enumerate(header) if h == "GPU Core Voltage [V]"]
    tcol = [i for i, h in enumerate(header) if h.startswith("GPU Temperature")]
    if len(vcol) != 1:
        raise SystemExit(f"expected one 'GPU Core Voltage [V]' column, found {len(vcol)}")
    samples = []
    for r in rows[1:]:
        try:
            stamp = datetime.strptime(r[0] + " " + r[1], "%d.%m.%Y %H:%M:%S.%f").replace(tzinfo=tz).timestamp()
            samples.append((stamp, float(r[vcol[0]]), float(r[tcol[-1]]) if tcol else float("nan")))
        except (ValueError, IndexError):
            continue
    print(f"{role} {day}: {len(samples)} raw samples, voltage column {header[vcol[0]]!r}")
    for w in sorted(windows, key=lambda x: float(x["target"])):
        a, b = float(w["windowStart"]), float(w["windowEnd"])
        inside = [s for s in samples if a <= s[0] <= b]
        if not inside:
            print(f"  {w['target']}: no raw samples in the window")
            continue
        codes = dict(sorted(Counter(round(s[1] * 1000) for s in inside).items()))
        temps = [s[2] for s in inside]
        print(f"  {int(float(w['target'])):5d} extract {float(w['voltage']) * 1000:.0f} mV n={w['sampleCount']:>3} | "
              f"raw n={len(inside):3d} median {statistics.median(s[1] for s in inside) * 1000:.1f} mV "
              f"codes {codes}  GPU temp {min(temps):.0f}-{max(temps):.0f} C")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
