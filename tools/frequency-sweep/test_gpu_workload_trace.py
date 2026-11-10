"""The historical (no new flags) path of gpu_workload.py must make exactly the calls it made before
section 20b's changes (GPT Job 75, R8 found one extra timer call). Deterministic fakes stand in for
PyTorch, NVML, nvidia-smi and the clock; EXPECTED was recorded from the file at a88c52f^ (the last
version before section 20b) by running this same trace against it. If this fails, a change reached
the path every historical sweep used: gate it behind a flag instead of updating EXPECTED."""
import io
import json
import sys
import types
from contextlib import redirect_stdout

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_workload as gw  # noqa: E402

counts = {"perf_counter": 0, "time": 0, "temperature": 0, "energy": 0, "matmul": 0, "synchronize": 0,
          "energy_open": 0, "clock_open": 0}


class FakeTime:
    def __init__(self):
        self.t = 1000.0

    def perf_counter(self):
        counts["perf_counter"] += 1
        self.t += 0.1
        return self.t

    def time(self):
        counts["time"] += 1
        return 1.79e9 + self.t

    def sleep(self, s):
        pass


def fake_torch():
    torch = types.ModuleType("torch")
    torch.float32, torch.float16 = "fp32", "fp16"

    def sync():
        counts["synchronize"] += 1
    torch.cuda = types.SimpleNamespace(is_available=lambda: True, get_device_name=lambda i: "fake",
                                       get_device_properties=lambda i: types.SimpleNamespace(),
                                       synchronize=sync, empty_cache=lambda: None)
    torch.device = lambda name: name
    torch.randn = lambda *a, **k: object()
    torch.empty = lambda *a, **k: object()

    def matmul(a, b):
        counts["matmul"] += 1
    torch.matmul = matmul
    torch.backends = types.SimpleNamespace(cudnn=types.SimpleNamespace(allow_tf32=True),
                                           cuda=types.SimpleNamespace(matmul=types.SimpleNamespace(allow_tf32=False)))
    return torch


def run():
    sys.modules["torch"] = fake_torch()
    gw.time = FakeTime()
    energy = iter(range(10_000_000, 20_000_000, 7919))

    def read_energy():
        counts["energy"] += 1
        return next(energy)

    def open_energy(*args):
        counts["energy_open"] += 1
        return read_energy

    def temperature():
        counts["temperature"] += 1
        return 45.0

    gw.openEnergyCounter = open_energy
    if hasattr(gw, "openClockReader"):
        def open_clock(*args):
            counts["clock_open"] += 1
            return None
        gw.openClockReader = open_clock
    gw.readGpuTemperature = temperature
    sys.argv = ["gpu_workload.py", "--workload", "gemm", "--iterations", "40", "--json", "--temp-check-seconds", "0.5"]
    out = io.StringIO()
    with redirect_stdout(out):
        code = gw.main()
    payload = json.loads(out.getvalue().strip().splitlines()[-1])
    return {"code": code, "counts": counts, "keys": sorted(payload),
            "payload": {k: payload[k] for k in ("duration_seconds", "wall_seconds", "monitoring_overhead_seconds",
                                                 "energy_window_seconds", "energy_avg_power_w", "throughput")}}


EXPECTED = json.loads('{"code": 0, "counts": {"clock_open": 0, "energy": 2, "energy_open": 1, "matmul": 45, "perf_counter": 15, "synchronize": 11, "temperature": 3, "time": 2}, "keys": ["abort_reason", "aborted", "arithmetic_intensity_flop_per_byte", "arithmetic_intensity_is_declared", "bytes_per_iteration", "device", "dtype", "duration_seconds", "energy_avg_power_w", "energy_counter_end_mj", "energy_counter_start_mj", "energy_joules", "energy_window_seconds", "flops_per_iteration", "iterations_completed", "iterations_requested", "monitoring_overhead_seconds", "ok", "seconds_per_iteration", "size", "temperature_peak_c", "temperature_start_c", "tf32_allowed", "throughput", "throughput_unit", "timed_region_end_unix", "timed_region_start_unix", "wall_seconds", "workload"], "payload": {"duration_seconds": 1.2, "energy_avg_power_w": 6.092, "energy_window_seconds": 1.3, "monitoring_overhead_seconds": 0.1, "throughput": 36650387592525.0, "wall_seconds": 1.3}}')


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


if __name__ == "__main__":
    got = run()
    del sys.modules["torch"]
    check(got["code"] == EXPECTED["code"], "the historical gemm path exits as before")
    check(got["counts"] == EXPECTED["counts"], f"it makes exactly the old timer, energy, temperature and kernel calls {got['counts']}")
    check(got["keys"] == EXPECTED["keys"], "it emits exactly the old payload fields")
    check(got["payload"] == EXPECTED["payload"], "its timing, energy and throughput figures are identical under the same fakes")
    print("Historical-path trace matches the pre-section-20b benchmark.")
