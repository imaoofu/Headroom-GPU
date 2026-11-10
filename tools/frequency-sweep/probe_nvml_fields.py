"""Scan NVML field IDs for one that reports GPU core voltage.

HWiNFO reads core voltage on this card, so the hardware exposes it. The question is whether
NVML does too - if so the whole thing is scriptable with no GUI in the loop. nvidia-smi has no
voltage field, but nvmlDeviceGetFieldValues exposes many fields nvidia-smi never surfaces.

Rather than guess the constant, query every field id in a range and look for a plausible
millivolt reading.
"""

import ctypes
import ctypes.util

NVML = ctypes.CDLL(r"C:\Windows\System32\nvml.dll")


class NvmlValue(ctypes.Union):
    _fields_ = [
        ("dVal", ctypes.c_double),
        ("uiVal", ctypes.c_uint),
        ("ulVal", ctypes.c_ulong),
        ("ullVal", ctypes.c_ulonglong),
        ("sllVal", ctypes.c_longlong),
    ]


class NvmlFieldValue(ctypes.Structure):
    _fields_ = [
        ("fieldId", ctypes.c_uint),
        ("scopeId", ctypes.c_uint),
        ("timestamp", ctypes.c_longlong),
        ("latencyUsec", ctypes.c_longlong),
        ("valueType", ctypes.c_int),
        ("nvmlReturn", ctypes.c_int),
        ("value", NvmlValue),
    ]


TYPE_NAMES = {0: "double", 1: "uint", 2: "ulong", 3: "ulonglong", 4: "slonglong"}


def extract(fv):
    t = fv.valueType
    if t == 0:
        return fv.value.dVal
    if t == 1:
        return fv.value.uiVal
    if t == 2:
        return fv.value.ulVal
    if t == 3:
        return fv.value.ullVal
    if t == 4:
        return fv.value.sllVal
    return None


def main():
    if NVML.nvmlInit_v2() != 0:
        print("nvmlInit failed")
        return 1
    handle = ctypes.c_void_p()
    if NVML.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
        print("could not get device handle")
        return 1

    found = []
    for fieldId in range(1, 260):
        fv = NvmlFieldValue()
        fv.fieldId = fieldId
        fv.scopeId = 0
        rc = NVML.nvmlDeviceGetFieldValues(handle, 1, ctypes.byref(fv))
        if rc != 0 or fv.nvmlReturn != 0:
            continue
        value = extract(fv)
        if value is None:
            continue
        found.append((fieldId, TYPE_NAMES.get(fv.valueType, "?"), value))

    print(f"{len(found)} field ids returned a value\n")
    print("candidates in a plausible core-voltage range:")
    hits = [f for f in found if isinstance(f[2], (int, float))
            and (500 <= f[2] <= 1300 or 0.5 <= f[2] <= 1.3)]
    for fieldId, typeName, value in hits:
        print(f"  fieldId={fieldId:<4} type={typeName:<10} value={value}")
    if not hits:
        print("  (none)")

    print("\nall readable fields:")
    for fieldId, typeName, value in found:
        print(f"  {fieldId:<4} {typeName:<10} {value}")

    NVML.nvmlShutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
