"""Section 20b's monitoring reader: one process per window, in every arm, on a fixed 50 ms schedule.

Usage: python tools/section20b/reader.py --mode {A,E,P,EP} --out F.csv --ready-file R --stop-file S --done-file D

The arm decides which NVML power and energy calls each poll makes (design.MODE_CALLS). Unwanted
calls are skipped at the source, never made and then dropped:
  A   no NVML call of any kind; NVML is not even initialised. Rows carry timing only.
  E   one field batch: 83 (the cumulative energy counter, as sample_power.py reads it).
  P   nvmlDeviceGetPowerUsage, then a field batch 185/186 (average and instant power).
  EP  nvmlDeviceGetPowerUsage, then a field batch 185/186/83: sample_power.py's order exactly.
Every arm has the same schedule, the same CSV writer and the same flush after every row, so the host
work differs only by the calls themselves. That difference is part of the treatment and is recorded.

Lifecycle: the ready file is written once the reader can poll (and before the first poll); polling
stops at the first check after the stop file appears; the done file then reports rows, calls and
failures. Each row records perf_counter before and after each API call and around the whole poll (one clock across processes on
Windows, so the controller and the benchmark can be aligned to it), Unix time, and for every call its
return code, and for every field its own return code, value type, NVML timestamp, latency and value.
It observes only: it never changes clocks, limits or anything else on the card.
"""
import argparse
import csv
import ctypes
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "power-probe"))
from design import MODE_CALLS, READER_HZ  # noqa: E402
from sample_power import _FieldValue, open_device  # noqa: E402

TIMING_COLUMNS = ["seq", "mono_before", "mono_after", "unix"]
FIELD_PARTS = ["ret", "type", "ts_us", "latency_us", "value"]


def columns_for(mode):
    columns = list(TIMING_COLUMNS)
    for kind, fields in MODE_CALLS[mode]:
        if kind == "usage":
            columns += ["usage_mono_before", "usage_mono_after", "usage_ret", "usage_mw"]
        else:
            columns += ["batch_mono_before", "batch_mono_after", "batch_ret"]
            columns += [f"f{fid}_{part}" for fid in fields for part in FIELD_PARTS]
    return columns


def decode(field):
    """A field's value by its declared NVML value type (0 double, 1 uint, 2 ulong, 3 ulonglong,
    4 signed long long, 5 signed int). None for an unknown type rather than a guess."""
    kind = field.valueType
    if kind == 0:
        return field.value.d
    if kind == 1:
        return field.value.ui
    if kind == 2:
        return field.value.ul
    if kind == 3:
        return field.value.ull
    if kind == 4:
        return field.value.sll
    if kind == 5:
        return ctypes.c_int(field.value.ui).value
    return None


def make_poll(mode, nvml=None, handle=None):
    """A zero-argument poll returning (row, calls_made, calls_failed). A makes no call at all."""
    prepared = []
    for kind, fields in MODE_CALLS[mode]:
        if kind == "usage":
            prepared.append(("usage", ctypes.c_uint()))
        else:
            array = (_FieldValue * len(fields))()
            for i, fid in enumerate(fields):
                array[i].fieldId = fid
            prepared.append(("fields", (fields, array)))

    def poll():
        row = {"unix": time.time()}
        made = failed = 0
        row["mono_before"] = time.perf_counter()
        for kind, item in prepared:
            made += 1
            if kind == "usage":
                row["usage_mono_before"] = time.perf_counter()
                ret = nvml.nvmlDeviceGetPowerUsage(handle, ctypes.byref(item))
                row["usage_mono_after"] = time.perf_counter()
                row["usage_ret"] = ret
                row["usage_mw"] = item.value if ret == 0 else None
                failed += ret != 0
            else:
                fields, array = item
                row["batch_mono_before"] = time.perf_counter()
                ret = nvml.nvmlDeviceGetFieldValues(handle, len(fields), array)
                row["batch_mono_after"] = time.perf_counter()
                row["batch_ret"] = ret
                bad = ret != 0
                for i, fid in enumerate(fields):
                    good = ret == 0 and array[i].nvmlReturn == 0
                    value = decode(array[i]) if good else None
                    # A successful return with a type this reader cannot decode, or a non-finite or
                    # negative value, is a failed read (GPT Job 73, F10), with its metadata kept.
                    usable = (good and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0)
                    bad = bad or not usable
                    row[f"f{fid}_ret"] = array[i].nvmlReturn if ret == 0 else None
                    row[f"f{fid}_type"] = array[i].valueType if good else None
                    row[f"f{fid}_ts_us"] = array[i].timestamp if good else None
                    row[f"f{fid}_latency_us"] = array[i].latencyUsec if good else None
                    row[f"f{fid}_value"] = value if usable else None
                failed += bad
        row["mono_after"] = time.perf_counter()
        return row, made, failed

    return poll


def write_json(path, payload):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def run(mode, out, ready_file, stop_file, done_file, hz=READER_HZ, nvml=None, handle=None, max_rows=None):
    """The reader's loop. nvml/handle are injectable for tests; A never touches them."""
    opened = False
    if MODE_CALLS[mode] and nvml is None:
        nvml, handle = open_device()
        opened = True
    poll = make_poll(mode, nvml, handle)
    columns = columns_for(mode)
    period = 1.0 / hz
    rows = made = failed = 0
    reason = "stop file"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("w", encoding="utf-8", newline="") as handle_out:
            writer = csv.DictWriter(handle_out, fieldnames=columns)
            writer.writeheader()
            handle_out.flush()
            write_json(ready_file, {"mode": mode, "pid": os.getpid(), "ready_mono": time.perf_counter(),
                                    "calls_per_poll": len(MODE_CALLS[mode]), "hz": hz})
            next_tick = time.perf_counter()
            while True:
                row, m, f = poll()
                row["seq"] = rows
                writer.writerow(row)
                handle_out.flush()
                rows += 1
                made += m
                failed += f
                if stop_file.exists():
                    break
                if max_rows is not None and rows >= max_rows:
                    reason = "max rows"
                    break
                next_tick += period
                delay = next_tick - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.perf_counter()
    except KeyboardInterrupt:
        reason = "interrupted"
    finally:
        if opened:
            nvml.nvmlShutdown()
    summary = {"mode": mode, "rows": rows, "nvml_power_energy_calls": made, "failed_calls": failed,
               "stop_reason": reason, "done_mono": time.perf_counter()}
    write_json(done_file, summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", required=True, choices=list(MODE_CALLS))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--ready-file", required=True, type=Path)
    parser.add_argument("--stop-file", required=True, type=Path)
    parser.add_argument("--done-file", required=True, type=Path)
    parser.add_argument("--hz", type=float, default=READER_HZ)
    args = parser.parse_args(argv)
    try:
        summary = run(args.mode, args.out, args.ready_file, args.stop_file, args.done_file, args.hz)
    except (OSError, RuntimeError) as exc:
        print(f"[READER] Cannot run mode {args.mode}: {exc}", file=sys.stderr)
        return 2
    return 0 if summary["failed_calls"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
