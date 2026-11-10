"""Section 20b's --endpoint-detail path in gpu_workload.py, without a GPU or PyTorch.

GPT Job 73 (F3) found that a failed temperature read silently disabled the thermal ceiling. In the
detail path it must now refuse instead; on the historical path it must behave exactly as before.
A stand-in torch module lets main() run as far as the first temperature read on any machine."""
import io
import json
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gpu_workload  # noqa: E402


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def fake_torch():
    torch = types.ModuleType("torch")
    torch.float32, torch.float16 = "fp32", "fp16"
    torch.cuda = types.SimpleNamespace(is_available=lambda: True, get_device_name=lambda i: "fake",
                                       get_device_properties=lambda i: types.SimpleNamespace(),
                                       synchronize=lambda: None, empty_cache=lambda: None)
    torch.device = lambda name: name

    def stop(*a, **k):
        raise RuntimeError("stand-in torch: no tensors")
    torch.randn = torch.empty = stop
    torch.backends = types.SimpleNamespace(cudnn=types.SimpleNamespace(allow_tf32=True),
                                           cuda=types.SimpleNamespace(matmul=types.SimpleNamespace(allow_tf32=False)))
    return torch


def run(argv, temperature):
    sys.modules["torch"] = fake_torch()
    original_read, original_argv = gpu_workload.readGpuTemperature, sys.argv
    original_energy, original_clocks = gpu_workload.openEnergyCounter, gpu_workload.openClockReader
    gpu_workload.readGpuTemperature = lambda: temperature
    gpu_workload.openEnergyCounter = lambda pci=None, log=None: None
    gpu_workload.openClockReader = lambda pci=None: None
    sys.argv = ["gpu_workload.py"] + argv
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            code = gpu_workload.main()
    finally:
        gpu_workload.readGpuTemperature, sys.argv = original_read, original_argv
        gpu_workload.openEnergyCounter, gpu_workload.openClockReader = original_energy, original_clocks
        del sys.modules["torch"]
    return code, out.getvalue()


def main():
    code, out = run(["--workload", "gemm", "--iterations", "1", "--json", "--endpoint-detail"], None)
    payload = json.loads(out.strip().splitlines()[-1])
    check(code == 9 and payload["ok"] is False and payload["error"] == "section20b_temperature_read_failed"
          and len(payload["temperature_reads"]) == 1,
          "with --endpoint-detail a failed first temperature read refuses, with the read recorded")
    code, out = run(["--workload", "gemm", "--iterations", "1", "--json", "--endpoint-detail"], float("nan"))
    check(code == 9, "a non-finite temperature is treated as a failed read")
    code, out = run(["--workload", "gemm", "--iterations", "1", "--json"], None)
    check(code == 7 and "section20b_temperature_read_failed" not in out and "stand-in torch" in out,
          "without the flag a failed temperature read keeps the historical behaviour (it carries on to set-up)")
    code, out = run(["--workload", "gemm", "--iterations", "1", "--json", "--endpoint-detail"], 95.0)
    payload = json.loads(out.strip().splitlines()[-1])
    check(code == 6 and payload["error"] == "already_too_hot", "the thermal refusal still applies in detail mode")
    print("All endpoint-detail checks passed.")


if __name__ == "__main__":
    main()
