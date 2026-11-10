"""Clocks-only report for one Invoke-XbarCalibration.ps1 run (REGISTERED-PREDICTIONS section 14, step 0).

Joins the run's HWiNFO log to its load windows by time and prints, per XBAR offset step, the core
clock, the reported core voltage (VID), and the reported and MEASURED crossbar clocks. Then it
scores the calibration gates that can be scored from one run:

  C0a  at offset 0, reported and measured crossbar agree within 15 MHz
  C0b  a negative offset moves the measured crossbar by at least 50 MHz, and the following
       offset-0 step returns to within 15 MHz of the first
  C0d  VID at each offset differs from the first offset-0 step by at most one 5 mV code

It never reads throughput: section 14 forbids looking at an outcome before collection.

Usage: python tools/xbar/calibration_report.py <calibration-hwinfo.csv> <windows.json>
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "frequency-sweep"))
from join_hwinfo_voltage import loadHwinfo  # noqa: E402

AGREE_MHZ = 15.0
MOVE_MHZ = 50.0
VID_CODE_V = 0.005


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else float("nan")


def summarise(samples, window):
    inside = [s for s in samples if window["windowStart"] <= s["timestamp"] <= window["windowEnd"]]
    return {
        "offset": window["offsetMhz"],
        "n": len(inside),
        "core": median(s["clock"] for s in inside),
        "vid": median(s["voltage"] for s in inside),
        "reported": median(s["crossbar"] for s in inside),
        "measured": median(s.get("crossbarMeasured") for s in inside),
        "memory": window.get("smiMemMedian"),
        "power": window.get("smiPowerMedian"),
        "sys": window.get("mvoltSysMhz"),
    }


def main(hwinfoPath, windowsPath):
    windows = json.loads(Path(windowsPath).read_text(encoding="utf-8-sig"))
    if isinstance(windows, dict):
        windows = [windows]
    samples, indices = loadHwinfo(hwinfoPath, includeTime=True)
    if indices.get("crossbarMeasured") is None:
        print("The HWiNFO log has no 'GPU Crossbar Clock (measured) [MHz]' column. "
              "Section 14 scores only on that column, so nothing below can be scored.")
        return 2
    rows = [summarise(samples, w) for w in windows]

    print(f"{'step':>4} {'offset':>7} {'n':>4} {'core':>7} {'VID':>7} {'XBAR rep':>9} "
          f"{'XBAR meas':>10} {'memory':>7} {'W':>6} {'SYS':>6}")
    for i, r in enumerate(rows, 1):
        print(f"{i:>4} {r['offset']:>7} {r['n']:>4} {r['core']:>7.0f} {r['vid']:>7.4f} "
              f"{r['reported']:>9.1f} {r['measured']:>10.1f} {r['memory'] or float('nan'):>7.0f} "
              f"{r['power'] if r['power'] is not None else float('nan'):>6.1f} "
              f"{r['sys'] if r['sys'] is not None else float('nan'):>6.0f}")
    empty = [i for i, r in enumerate(rows, 1) if r["n"] == 0]
    if empty:
        print(f"\nSteps {empty} have no HWiNFO samples in their window. Check logging and the clock.")
        return 2

    zeros = [r for r in rows if r["offset"] == 0]
    print()
    if zeros:
        gap = abs(zeros[0]["reported"] - zeros[0]["measured"])
        print(f"C0a  offset 0: reported {zeros[0]['reported']:.1f}, measured {zeros[0]['measured']:.1f}, "
              f"gap {gap:.1f} MHz -> {'PASS' if gap <= AGREE_MHZ else 'FAIL'} (limit {AGREE_MHZ:.0f})")
    for i, r in enumerate(rows):
        if r["offset"] >= 0 or not zeros:
            continue
        moved = zeros[0]["measured"] - r["measured"]
        after = next((z for z in rows[i + 1:] if z["offset"] == 0), None)
        back = abs(after["measured"] - zeros[0]["measured"]) if after else float("nan")
        verdict = "PASS" if moved >= MOVE_MHZ and after is not None and back <= AGREE_MHZ else "FAIL"
        print(f"C0b  offset {r['offset']}: measured XBAR moved {moved:+.1f} MHz down "
              f"(need >= {MOVE_MHZ:.0f}); return to offset 0 within {back:.1f} MHz "
              f"(need <= {AGREE_MHZ:.0f}) -> {verdict}")
    if zeros:
        for r in rows:
            step = abs(r["vid"] - zeros[0]["vid"])
            flag = "ok" if step <= VID_CODE_V + 1e-9 else "XBAR+VOLTAGE flag"
            print(f"C0d  offset {r['offset']:>5}: VID {r['vid']:.4f} V, {step * 1000:.1f} mV from offset 0 -> {flag}")
    print("\nClocks only. No throughput was read, by design (REGISTERED-PREDICTIONS section 14).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
