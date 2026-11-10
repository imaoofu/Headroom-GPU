"""GPU-free tests of the pinned llama-bench JSON contract and timed-window arithmetic."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm_workload as llm  # noqa: E402


CHECKS = []
HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "llama_bench_qwen3_8b_tg256.json"
ROW = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
PREFILL_ROW = json.loads((HERE / "fixtures" / "llama_bench_qwen3_8b_pp512.json").read_text(encoding="utf-8"))[0]


def check(label, condition):
    result = bool(condition)
    CHECKS.append(result)
    print(f"  {'[PASS]' if result else '[FAIL]'} {label}")


def captured(row=None, second_gap=0.012, kind="generation"):
    item = ROW if row is None else row
    reference = item["samples_ns"] if len(item["samples_ns"]) == 2 else ROW["samples_ns"]
    first = 1_700_000_000.0
    second = first + reference[0] / 1e9 + second_gap
    end = second + reference[1] / 1e9
    lines = [(kind, 1, 2, first), (kind, 2, 2, second)]
    return llm.CapturedRun(0, json.dumps([item]), "", lines, first - 3, end + 1)


def error_name(call):
    try:
        call()
    except llm.WorkloadError as error:
        return error.name
    return None


model = Path(ROW["model_filename"])
parsed = llm.parse_result(captured(), "llm-decode", 2, model=model, lead_in=0)
durations = ROW["samples_ns"]
expected_window = sum(durations) / 1e9 + 0.012
check("real pinned-build JSON fixture parses as two 256-token repetitions",
      parsed["total_tokens"] == 512 and parsed["iterations_completed"] == 2)
check("reported token/s uses the marker-bounded window, including the inter-run gap",
      abs(parsed["throughput"] - 512 / expected_window) < 0.0001)
check("timed-window end extends the last progress marker by its measured duration",
      abs(parsed["timed_region_end_unix"] -
          (captured().progress[-1][3] + durations[-1] / 1e9)) < 0.000002)
check("timed region excludes process load and teardown",
      parsed["timed_region_start_unix"] > captured().process_start_unix and
      parsed["timed_region_end_unix"] < captured().process_end_unix)
check("sample rates and sample standard deviation are retained",
      len(parsed["per_repetition_tokens_per_second"]) == 2 and
      parsed["stddev_repetition_tokens_per_second"] >= 0)
prefill_parsed = llm.parse_result(captured(PREFILL_ROW, kind="prompt"), "llm-prefill", 2, model=model, lead_in=0)
check("real prompt JSON fixture parses as 512 tokens per repetition",
      prefill_parsed["total_tokens"] == 1024 and
      prefill_parsed["prompt_tokens_per_repetition"] == 512 and
      prefill_parsed["generated_tokens_per_repetition"] == 0)

with tempfile.TemporaryDirectory() as temp:
    tmp = Path(temp)
    exe = tmp / "llama-bench.exe"
    fake_model = tmp / "model.gguf"
    fake_model.write_bytes(b"test model bytes")
    check("missing executable refuses before model use",
          error_name(lambda: llm.check_inputs(exe, fake_model)) == "missing_executable")
    exe.write_bytes(b"test exe bytes")
    check("missing model refuses by name",
          error_name(lambda: llm.check_inputs(exe, tmp / "absent.gguf")) == "missing_model")
    check("model hash mismatch refuses by name",
          error_name(lambda: llm.check_inputs(exe, fake_model)) == "model_hash_mismatch")
    check("matching SHA-256 permits fixture model bytes",
          llm.check_inputs(exe, fake_model, llm.sha256_file(fake_model)) == llm.sha256_file(fake_model))

failed = captured()
failed.returncode = 7
failed.stderr = "GPU allocation failed"
check("nonzero llama-bench exit refuses before parsing success-shaped JSON",
      error_name(lambda: llm.parse_result(failed, "llm-decode", 2, model, lead_in=0)) == "benchmark_exit_nonzero")

changed = dict(ROW, n_gen=255)
check("changed generated token count refuses",
      error_name(lambda: llm.parse_result(captured(changed), "llm-decode", 2, model, lead_in=0)) == "token_count_mismatch")
changed = dict(ROW, samples_ns=[ROW["samples_ns"][0]])
check("missing repetition duration refuses",
      error_name(lambda: llm.parse_result(captured(changed), "llm-decode", 2, model, lead_in=0)) == "repetition_count_mismatch")
changed = dict(ROW, n_batch=256)
check("uncontrolled batch-size drift refuses",
      error_name(lambda: llm.parse_result(captured(changed), "llm-decode", 2, model, lead_in=0)) == "benchmark_setting_mismatch")
changed = dict(ROW, build_commit="later-build")
check("new llama.cpp build requires timing revalidation",
      error_name(lambda: llm.parse_result(captured(changed), "llm-decode", 2, model, lead_in=0)) == "unvalidated_benchmark_build")
missing_marker = captured()
missing_marker.progress = missing_marker.progress[:1]
check("missing timed-repetition progress marker refuses",
      error_name(lambda: llm.parse_result(missing_marker, "llm-decode", 2, model, lead_in=0)) == "progress_count_mismatch")

# Lead-in (Claude's review): the window, token count and rate start AFTER the lead-in repetitions.
lead = llm.parse_result(captured(), "llm-decode", 1, model=model, lead_in=1)
check("lead-in: the timed window starts at the first counted repetition's marker",
      abs(lead["timed_region_start_unix"] - captured().progress[1][3]) < 0.000002)
check("lead-in: only counted repetitions enter tokens, active time and rate",
      lead["total_tokens"] == 256 and lead["iterations_completed"] == 1 and
      abs(lead["duration_seconds"] - durations[1] / 1e9) < 0.000002 and
      abs(lead["throughput"] - 256 / (durations[1] / 1e9)) < 0.0001)
check("lead-in: its duration is recorded, not discarded silently",
      lead["lead_in_repetitions"] == 1 and abs(lead["lead_in_seconds"] - durations[0] / 1e9) < 0.000002)
check("lead-in: a missing lead-in repetition refuses",
      error_name(lambda: llm.parse_result(captured(), "llm-decode", 2, model, lead_in=1)) == "repetition_count_mismatch")
check("default lead-in covers the measured ~1 s power lag (1 decode rep ~3.4 s, 15 prefill reps ~2.3 s)",
      llm.WORK["llm-decode"][3] == 1 and llm.WORK["llm-prefill"][3] == 15)
check("the command runs counted plus lead-in repetitions",
      llm.build_command("llm-decode", 5)[llm.build_command("llm-decode", 5).index("-r") + 1] == "6" and
      llm.build_command("llm-prefill", 200)[llm.build_command("llm-prefill", 200).index("-r") + 1] == "215")

prefill = llm.build_command("llm-prefill", 20)
decode = llm.build_command("llm-decode", 5)
check("default prefill window is long enough to dilute telemetry response lag",
      llm.WORK["llm-prefill"][2] == 200 and llm.WORK["llm-decode"][2] == 5)
check("prefill and decode commands pin requested fixed work and offline JSON mode",
      prefill[prefill.index("-p") + 1:prefill.index("-p") + 2] == ["512"] and
      prefill[prefill.index("-n") + 1] == "0" and decode[decode.index("-n") + 1] == "256" and
      all(flag in prefill and flag in decode for flag in ("--offline", "--progress", "json")))

wrapper = (HERE.parent / "hwinfo-logging" / "Invoke-LoggedSweep.ps1").read_text(encoding="utf-8-sig")
check("elevated wrapper routes allowlisted LLM names to llm_workload.py",
      '"llm-prefill", "llm-decode"' in wrapper and
      '$workload = if ($work -in @("llm-prefill", "llm-decode")) { $llmWorkload }' in wrapper)
check("wrapper names idle llama-server in its preflight refusal",
      'Name = \'llama-server.exe\'' in wrapper and
      'Preflight failed: llama-server is running' in wrapper)
# os.name is patched too, so this runs on CI's Ubuntu leg; the guard itself is Windows-only.
with mock.patch.object(llm.os, "name", "nt"), mock.patch.object(llm.subprocess, "run", return_value=subprocess.CompletedProcess(
        [], 0, '"llama-server.exe","1234","Console","1","12,000 K"\n', "")):
    check("standalone process guard detects an idle llama-server by name",
          llm.llama_server_running())

# WhatIfOnly validates the actual wrapper allowlist and exits before HWiNFO/GPU work. The wrapper is a
# Windows PowerShell 5.1 tool with Windows paths, so this runs only on Windows; CI's Ubuntu leg skips it.
if os.name != "nt":
    print("  [SKIP] WhatIfOnly routing checks: Windows only")
else:
    with tempfile.TemporaryDirectory() as temp:
        job = Path(temp) / "job.json"
        base = {"label": "llm-route-check", "minMhz": 1000, "maxMhz": 2000,
                "frequencyCount": 3, "appliedSettings": "stock GPU with no modified clocks", "expectedMinutes": 10}
        for name, expected in (("llm-prefill", True), ("llm-decode", True), ("shell-command", False)):
            base["workload"] = name
            job.write_text(json.dumps(base), encoding="utf-8")
            result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(HERE.parent / "hwinfo-logging" / "Invoke-LoggedSweep.ps1"),
                                     "-JobPath", str(job), "-WhatIfOnly"],
                                    capture_output=True, text=True, timeout=15)
            check(f"WhatIfOnly {'accepts' if expected else 'rejects'} {name}",
                  (result.returncode == 0) == expected and
                  ("WhatIfOnly - validated" in result.stdout and
                   "llm_workload.py" in result.stdout if expected else "not in the allowed list" in result.stdout))

print(f"{sum(CHECKS)}/{len(CHECKS)} llm workload checks passed")
sys.exit(0 if all(CHECKS) else 1)
