"""Fixed-work llama.cpp prefill/decode for the frequency-sweep harness.

The payload's token/s divided by the harness's average board watts is tokens per
joule of *board* energy. It is not system energy or a serving-quality metric.

Timing requires llama-bench build d222767c7: its --progress messages are printed
inside each timed repetition, immediately after its timer starts, and its JSON
samples_ns contain each repetition's measured duration. We timestamp the first
and last progress messages and extend the last timestamp by its samples_ns. The
boundary error is measured against a power trace in the Job 28 finding, rather
than assumed to be zero. A changed build is refused until this is revalidated.

LEAD-IN REPETITIONS (added at Claude's review, 2026-09-27). llama-bench's warm-up
for generation is a single token, so the timed work starts from a nearly idle GPU,
and NVML's power reading lags the load by about a second. The stock smoke test
measured the first second of the window at 53 W against ~136 W steady for decode
(66 against ~150 for prefill), pulling the window's mean power ~4% (decode) and ~2%
(prefill) low. Because that lag is fixed in seconds while the window's length
changes with clock, the bias would vary across a sweep. So each workload runs
extra LEAD-IN repetitions first, and the timed window, the token count and the
throughput all start at the first repetition AFTER them: about 3.4 s of decode
(1 repetition) and about 2.3 s of prefill (15 repetitions) at stock.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass


BENCH_EXE = Path(r"C:\Users\Raymond\llamacpp\llama-bench.exe")
MODEL = Path(r"C:\Users\Raymond\models\Qwen3-8B-Q4_K_M.gguf")
MODEL_SHA256 = "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
BENCH_COMMIT = "d222767c7"
# Short prefill windows lose a large fraction of their power samples to NVML's
# delayed telemetry response. 200 repetitions give about 28 seconds on this card.
WORK = {"llm-prefill": (512, 0, 200, 15), "llm-decode": (0, 256, 5, 1)}  # prompt, gen, counted reps, lead-in reps
PROGRESS = re.compile(r"^llama-bench: benchmark 1/1: (prompt|generation) run (\d+)/(\d+)$")


@dataclass
class CapturedRun:
    returncode: int
    stdout: str
    stderr: str
    progress: list[tuple[str, int, int, float]]
    process_start_unix: float
    process_end_unix: float


class WorkloadError(Exception):
    def __init__(self, name: str, detail: str):
        super().__init__(detail)
        self.name = name


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_inputs(exe: Path = BENCH_EXE, model: Path = MODEL,
                 expected_hash: str = MODEL_SHA256) -> str:
    if not exe.is_file():
        raise WorkloadError("missing_executable", f"llama-bench is missing: {exe}")
    if not model.is_file():
        raise WorkloadError("missing_model", f"model is missing: {model}")
    actual = sha256_file(model)
    if actual.lower() != expected_hash.lower():
        raise WorkloadError("model_hash_mismatch", f"model SHA-256 {actual} differs from pinned {expected_hash}")
    return actual


def llama_server_running() -> bool:
    """Check an idle resident server too; GPU utilization alone misses its VRAM."""
    if os.name != "nt":
        raise WorkloadError("process_check_unavailable", "llama-server process check requires Windows")
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WorkloadError("process_check_unavailable", str(error)) from error
    if result.returncode:
        raise WorkloadError("process_check_unavailable", result.stderr.strip()[:300])
    return any(row and row[0].casefold() == "llama-server.exe"
               for row in csv.reader(result.stdout.splitlines()))


def build_command(workload: str, iterations: int, exe: Path = BENCH_EXE,
                  model: Path = MODEL) -> list[str]:
    if workload not in WORK:
        raise WorkloadError("unknown_workload", workload)
    if iterations < 1 or iterations > 1000:
        raise WorkloadError("invalid_iterations", "iterations must be 1..1000")
    prompt, generated, _, lead_in = WORK[workload]
    return [str(exe), "-m", str(model), "-p", str(prompt), "-n", str(generated),
            "-r", str(iterations + lead_in), "-b", "512", "-ub", "512", "-t", "8",
            "-ngl", "99", "-sm", "none", "-mg", "0", "-nkvo", "0",
            "-fa", "on", "-ctk", "f16", "-ctv", "f16", "--offline",
            "-o", "json", "--progress"]


def run_command(command: list[str], timeout: int = 1800) -> CapturedRun:
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace",
                                   bufsize=1,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as error:
        raise WorkloadError("launch_failed", str(error)) from error
    start = time.time()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    progress: list[tuple[str, int, int, float]] = []

    def collect_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_lines.append(line)

    def collect_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stamp = time.time()
            stderr_lines.append(line)
            match = PROGRESS.match(line.strip())
            if match:
                progress.append((match.group(1), int(match.group(2)),
                                 int(match.group(3)), stamp))

    readers = [threading.Thread(target=collect_stdout, daemon=True),
               threading.Thread(target=collect_stderr, daemon=True)]
    for reader in readers:
        reader.start()
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        raise WorkloadError("benchmark_timeout", f"llama-bench exceeded {timeout} seconds") from error
    finally:
        for reader in readers:
            reader.join(timeout=5)
    return CapturedRun(returncode, "".join(stdout_lines), "".join(stderr_lines),
                       progress, start, time.time())


def parse_result(captured: CapturedRun, workload: str, iterations: int,
                 model: Path = MODEL, lead_in: int | None = None) -> dict:
    if captured.returncode != 0:
        raise WorkloadError("benchmark_exit_nonzero",
                            f"llama-bench exited {captured.returncode}: {captured.stderr[-300:]}")
    try:
        rows = json.loads(captured.stdout)
    except json.JSONDecodeError as error:
        raise WorkloadError("invalid_benchmark_json", str(error)) from error
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise WorkloadError("invalid_benchmark_json", "expected exactly one JSON test row")
    row = rows[0]
    prompt, generated, _, default_lead_in = WORK[workload]
    lead_in = default_lead_in if lead_in is None else lead_in
    total_reps = iterations + lead_in
    if row.get("build_commit") != BENCH_COMMIT:
        raise WorkloadError("unvalidated_benchmark_build", f"expected {BENCH_COMMIT}, got {row.get('build_commit')}")
    if row.get("n_prompt") != prompt or row.get("n_gen") != generated:
        raise WorkloadError("token_count_mismatch",
                            f"expected prompt/gen {prompt}/{generated}, got {row.get('n_prompt')}/{row.get('n_gen')}")
    reported_model = row.get("model_filename")
    if not isinstance(reported_model, str) or Path(reported_model).resolve() != model.resolve():
        raise WorkloadError("model_path_mismatch", str(reported_model))
    expected_settings = {"n_batch": 512, "n_ubatch": 512, "n_threads": 8,
                         "n_gpu_layers": 99, "split_mode": "none", "main_gpu": 0,
                         "type_k": "f16", "type_v": "f16", "flash_attn": 1,
                         "no_kv_offload": False}
    for key, expected in expected_settings.items():
        if row.get(key) != expected:
            raise WorkloadError("benchmark_setting_mismatch", f"{key}: expected {expected}, got {row.get(key)}")
    if not isinstance(row.get("backends"), str) or "CUDA" not in row["backends"] or not row.get("gpu_info"):
        raise WorkloadError("gpu_offload_unverified", "CUDA GPU backend missing from benchmark JSON")
    durations = row.get("samples_ns")
    if (not isinstance(durations, list) or len(durations) != total_reps or
            any(not isinstance(ns, int) or isinstance(ns, bool) or ns <= 0 for ns in durations)):
        raise WorkloadError("repetition_count_mismatch", "samples_ns must contain one positive duration per repetition")
    kind = "prompt" if prompt else "generation"
    expected_events = [(kind, i, total_reps) for i in range(1, total_reps + 1)]
    if [item[:3] for item in captured.progress] != expected_events:
        raise WorkloadError("progress_count_mismatch", f"expected {expected_events}, got {captured.progress}")
    first = captured.progress[lead_in][3]  # the first COUNTED repetition, after the lead-in
    last = captured.progress[-1][3]
    counted = durations[lead_in:]
    end = last + durations[-1] / 1e9
    if not (captured.process_start_unix <= first < end <= captured.process_end_unix + 0.25):
        raise WorkloadError("invalid_timed_window", "progress-derived interval falls outside benchmark process")
    active_seconds = sum(counted) / 1e9
    wall_seconds = end - first
    if wall_seconds < active_seconds - 0.05:
        raise WorkloadError("invalid_timed_window", "repetition durations exceed progress-derived window")
    tokens = prompt or generated
    rates = [tokens * 1e9 / ns for ns in counted]
    total_tokens = tokens * iterations
    return {
        "ok": True,
        "workload": workload,
        "device": row["gpu_info"],
        "throughput": total_tokens / wall_seconds,
        "throughput_unit": "token/s",
        "timed_region_start_unix": round(first, 6),
        "timed_region_end_unix": round(end, 6),
        "duration_seconds": round(active_seconds, 6),
        "wall_seconds": round(wall_seconds, 6),
        "inter_repetition_seconds": round(wall_seconds - active_seconds, 6),
        "iterations_requested": iterations,
        "iterations_completed": len(counted),
        "lead_in_repetitions": lead_in,
        "lead_in_seconds": round(sum(durations[:lead_in]) / 1e9, 6),
        "tokens_per_repetition": tokens,
        "prompt_tokens_per_repetition": prompt,
        "generated_tokens_per_repetition": generated,
        "total_tokens": total_tokens,
        "per_repetition_tokens_per_second": [round(value, 4) for value in rates],
        "mean_repetition_tokens_per_second": statistics.mean(rates),
        "stddev_repetition_tokens_per_second": statistics.stdev(rates) if len(rates) > 1 else 0.0,
        "samples_ns": durations,
        "llama_bench_args": build_command(workload, iterations, model=model)[1:],
        "llama_bench_executable": str(BENCH_EXE),
        "llama_cpp_build_commit": row["build_commit"],
        "llama_cpp_build_number": row.get("build_number"),
        "model_file": model.name,
        "model_sha256": MODEL_SHA256,
        "model_bytes_gguf": row.get("model_size"),
        "timing_method": "progress marker of the first counted repetition (after lead-in) to the last marker plus its samples_ns; power-trace validation in Job 28's review",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", choices=sorted(WORK), required=True)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    iterations = args.iterations if args.iterations is not None else WORK[args.workload][2]
    try:
        command = build_command(args.workload, iterations)
        if llama_server_running():
            raise WorkloadError("llama_server_running", "Stop llama-server before any LLM sweep; an idle server holds VRAM")
        actual_hash = check_inputs()
        captured = run_command(command)
        payload = parse_result(captured, args.workload, iterations)
        payload["model_sha256"] = actual_hash
    except WorkloadError as error:
        payload = {"ok": False, "workload": args.workload, "error": error.name,
                   "detail": str(error)[:500]}
    if not args.json:
        if payload["ok"]:
            print(f"[LLM] {args.workload}: {payload['throughput']:.2f} token/s; "
                  f"{iterations} repetitions; build {payload['llama_cpp_build_commit']}")
        else:
            print(f"[LLM] REFUSED: {payload['error']}: {payload['detail']}")
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
