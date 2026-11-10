"""Log NVML's power readings and energy counter at a fixed rate until told to stop. Observes only.

Usage: python tools/power-probe/sample_power.py --out FILE.csv [--hz 20] [--stop-file PATH] [--seconds N]

Written 2026-10-06 for REGISTERED-PREDICTIONS section 18, after section 17 found NVML's integrated
energy counter reading a median 7.83% above the sampled `nvidia-smi` power. NVML exposes three power
figures on the RTX 5060 Ti, checked that evening: `nvmlDeviceGetPowerUsage` (what `nvidia-smi
power.draw` reports; it equalled the average field in every reading taken), field 185
(NVML_FI_DEV_POWER_AVERAGE) and field 186 (NVML_FI_DEV_POWER_INSTANT), all in milliwatts, plus field
83, the cumulative energy counter in millijoules. All of them updated about every 100 ms, so 20 Hz
catches every update. One poll of all four cost about 0.7 ms, about 1.4% of one CPU core at 20 Hz.

Each row: wall-clock Unix time, the three power figures in W, the energy counter in mJ, and each
field's own NVML timestamp. Rows are flushed as written, so a killed run keeps what it logged. It
stops when the stop file appears, after --seconds, or on Ctrl+C. It never changes clocks, power
limits or anything else on the card, and it reads device index 0 only, so on a machine with more
than one NVIDIA device it refuses rather than guess.
"""
import argparse
import csv
import ctypes
import sys
import time
from pathlib import Path

FIELDS = {"average": 185, "instant": 186, "energy": 83}


class _Value(ctypes.Union):
    _fields_ = [("d", ctypes.c_double), ("ui", ctypes.c_uint), ("ul", ctypes.c_ulong),
                ("ull", ctypes.c_ulonglong), ("sll", ctypes.c_longlong)]


class _FieldValue(ctypes.Structure):
    _fields_ = [("fieldId", ctypes.c_uint), ("scopeId", ctypes.c_uint), ("timestamp", ctypes.c_longlong),
                ("latencyUsec", ctypes.c_longlong), ("valueType", ctypes.c_uint),
                ("nvmlReturn", ctypes.c_uint), ("value", _Value)]


def open_device():
    nvml = ctypes.WinDLL("nvml.dll") if sys.platform == "win32" else ctypes.CDLL("libnvidia-ml.so.1")
    if nvml.nvmlInit_v2() != 0:
        raise RuntimeError("nvmlInit failed")
    count = ctypes.c_uint()
    if nvml.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0 or count.value != 1:
        raise RuntimeError(f"expected exactly one NVIDIA device, found {count.value}")
    handle = ctypes.c_void_p()
    if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
        raise RuntimeError("no handle for device 0")
    return nvml, handle


def make_reader(nvml, handle):
    names = list(FIELDS)
    array = (_FieldValue * len(names))()
    for i, name in enumerate(names):
        array[i].fieldId = FIELDS[name]
    usage = ctypes.c_uint()

    def read():
        row = {"unix": time.time()}
        row["usage_w"] = usage.value / 1000.0 if nvml.nvmlDeviceGetPowerUsage(handle, ctypes.byref(usage)) == 0 else None
        ok = nvml.nvmlDeviceGetFieldValues(handle, len(names), array) == 0
        for i, name in enumerate(names):
            good = ok and array[i].nvmlReturn == 0
            raw = (array[i].value.ull if name == "energy" else array[i].value.ui) if good else None
            row[f"{name}_ts_us"] = array[i].timestamp if good else None
            if name == "energy":
                row["energy_mj"] = raw
            else:
                row[f"{name}_w"] = raw / 1000.0 if raw is not None else None
        return row

    return read


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--hz", type=float, default=20.0)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--seconds", type=float)
    args = parser.parse_args(argv)
    try:
        nvml, handle = open_device()
    except (OSError, RuntimeError) as exc:
        print(f"[POWER] Cannot open NVML: {exc}. Nothing logged.", file=sys.stderr)
        return 2
    read = make_reader(nvml, handle)
    first = read()
    missing = [k for k in ("usage_w", "average_w", "instant_w", "energy_mj") if first[k] is None]
    if missing:
        print(f"[POWER] This card or driver does not report: {', '.join(missing)}. Nothing logged.", file=sys.stderr)
        return 3
    period = 1.0 / args.hz
    started = time.perf_counter()
    rows = 0
    columns = ["unix", "usage_w", "average_w", "instant_w", "energy_mj",
               "average_ts_us", "instant_ts_us", "energy_ts_us"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[POWER] Logging NVML power at {args.hz:g} Hz to {args.out}. It observes only.")
    try:
        with args.out.open("w", encoding="utf-8", newline="") as handle_out:
            writer = csv.DictWriter(handle_out, fieldnames=columns)
            writer.writeheader()
            next_tick = time.perf_counter()
            while True:
                writer.writerow(read())
                handle_out.flush()
                rows += 1
                if args.stop_file and args.stop_file.exists():
                    break
                if args.seconds and time.perf_counter() - started >= args.seconds:
                    break
                next_tick += period
                delay = next_tick - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.perf_counter()
    except KeyboardInterrupt:
        pass
    finally:
        nvml.nvmlShutdown()
    elapsed = time.perf_counter() - started
    print(f"[POWER] Stopped after {elapsed:.0f} s and {rows} rows ({rows / elapsed if elapsed else 0:.1f} per second).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
