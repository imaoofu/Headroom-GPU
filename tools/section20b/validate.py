"""Section 20b's per-window validity rules, shared by the controller (which stops on the first invalid
window) and the scorer (which re-checks every window), so the two cannot apply different rules.

A window is valid only if all of the following hold, each recomputed from raw evidence rather than
taken from a cached field (GPT Job 73, F7):
- the clock lock, benchmark and reader processes all exited 0, and the fixed work completed;
- warm-up 5, preload requested 1 s and measured at least 1 s, washout measured at least 30 s;
- both energy endpoints are integers bracketed by finite, ordered perf_counter calls; T is the
  difference of the call midpoints and agrees with the benchmark's cached T; work is
  work_per_iteration x completed iterations and agrees with its cached work; energy rose;
- the benchmark ran the scheduled workload in fp32 at its frozen size, work per iteration and unit
  (design.WORKLOAD_SPEC), and its synchronized fixed-work bounds sit between the two endpoints;
- the one support read succeeded; every temperature read is finite and below the 88 C ceiling;
- both NVML boundary witnesses: SM clock finite and within 15 MHz of target, memory 13801-14001 MHz;
- the reader ran the window's arm, wrote exactly its arm's columns, as many rows as it reported, made
  exactly its arm's calls, every call and field returned 0 with its permitted type and a finite value,
  every timing bracket is finite and ordered (poll, then usage, then batch, inside the poll), poll
  starts strictly increase, field timestamps and latencies are non-negative integers, it ran through
  both endpoints, and (E/P/EP) kept a 45-55 ms median and <=100 ms p99 cadence inside T.
Stale field timestamps are reported, not gated.
"""
import csv
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design  # noqa: E402
from reader import columns_for  # noqa: E402

CLOCK_TOLERANCE_MHZ = 15
MEMORY_LOADED_MHZ = (13801, 14001)
THERMAL_CEILING_C = 88.0
MIN_CADENCE_INTERVALS = 20
# NVML value types each field must report (seen in the 2026-10-09 qualification): 83 is the
# cumulative energy counter, unsigned long long; 185 and 186 are powers in mW, unsigned int.
FIELD_TYPES = {83: 3, 185: 1, 186: 1}


def finite(*values):
    try:
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
    except OverflowError:  # an integer too large for a float is not a reading (GPT Job 76, R6)
        return False


# The readback after the controller's clock reset, and the runner's restoration record. Shared by the
# controller and the scorer, so both apply one rule (GPT Job 76, R1).
RESET_WITNESS_FIELDS = ("clocks.sm", "clocks.mem", "pstate", "temperature.gpu")
STOCK_POWER_LIMIT_W = 180.0


def reset_witness_complete(record):
    """Every field present, and the clocks and temperature finite non-negative numbers. An idle clock
    does not prove a lock was released; this proves only that the card answered."""
    try:
        return isinstance(record, dict) and all(record.get(f) not in (None, "") for f in RESET_WITNESS_FIELDS) and \
            all(math.isfinite(float(record[f])) and float(record[f]) >= 0
                for f in ("clocks.sm", "clocks.mem", "temperature.gpu"))
    except (TypeError, ValueError, OverflowError, AttributeError):
        return False


def runner_cleanup_problems(cleanup):
    """Why the runner's restoration record does not show the card back on stock; empty when it does.
    Memory uses the windows' 13801-14001 rule; the runner itself demands 13801 before writing ok."""
    if not isinstance(cleanup, dict):
        return ["runner-cleanup.json is not an object"]
    problems = []
    if cleanup.get("ok") is not True:
        problems.append("ok is not true")
    if cleanup.get("reset_exit") != 0 or isinstance(cleanup.get("reset_exit"), bool):
        problems.append(f"reset_exit {cleanup.get('reset_exit')!r}")
    if cleanup.get("store_restored") is not True:
        problems.append(f"store_restored {cleanup.get('store_restored')!r}")
    memory, power = cleanup.get("memory_loaded_mhz"), cleanup.get("power_limit_w")
    if not finite(memory) or not MEMORY_LOADED_MHZ[0] <= memory <= MEMORY_LOADED_MHZ[1]:
        problems.append(f"memory under load {memory!r}, not {MEMORY_LOADED_MHZ[0]}-{MEMORY_LOADED_MHZ[1]} MHz")
    if not finite(power) or abs(power - STOCK_POWER_LIMIT_W) > 0.5:
        problems.append(f"power limit {power!r}, not {STOCK_POWER_LIMIT_W:g} W")
    return problems


def nearest_rank(sorted_values, q):
    return sorted_values[max(0, math.ceil(q * len(sorted_values)) - 1)]


def read_reader(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def _number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _integral(text):
    value = _number(text)
    return value is not None and value >= 0 and value == int(value)


def _midpoint(call):
    return (call["mono_before"] + call["mono_after"]) / 2.0


def _bracket_ok(call):
    return finite(call.get("mono_before"), call.get("mono_after")) and call["mono_before"] <= call["mono_after"]


def window_metrics(rec, session_dir):
    """(metrics, problems) for one window record. Malformed evidence is a problem, never an exception."""
    try:
        return _window_metrics(rec, Path(session_dir))
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, ZeroDivisionError, OSError,
            OverflowError) as exc:
        tag = rec.get("tag", f"window {rec.get('index')}") if isinstance(rec, dict) else "window"
        return {"tag": tag, "arm": rec.get("arm") if isinstance(rec, dict) else None}, \
            [f"{tag}: malformed evidence ({type(exc).__name__}: {exc})"]


def _window_metrics(rec, session_dir):
    problems = []
    tag = rec.get("tag", f"window {rec.get('index')}")
    arm, target = rec.get("arm"), rec.get("target_mhz")
    metrics = {"tag": tag, "arm": arm, "row": rec.get("row"), "cell": rec.get("cell"),
               "index": rec.get("index"), "position": rec.get("position")}

    def bad(text):
        problems.append(f"{tag}: {text}")

    if rec.get("failure"):
        bad(rec["failure"])
    for key in ("lock_exit", "workload_exit_code", "reader_exit_code"):
        if rec.get(key) != 0:
            bad(f"{key} {rec.get(key)}")
    payload = rec.get("result") or {}
    detail = payload.get("endpoint_detail") or {}
    spec = design.WORKLOAD_SPEC.get(rec.get("workload"))
    if spec is None or payload.get("workload") != rec.get("workload") or payload.get("dtype") != "fp32" \
            or payload.get("iterations_requested") != rec.get("iterations") or payload.get("size") != spec[0] \
            or payload.get("throughput_unit") != spec[2] \
            or not finite(detail.get("work_per_iteration")) or abs(detail["work_per_iteration"] - spec[1]) > 1e-9 * spec[1]:
        bad(f"the benchmark did not run the scheduled work ({payload.get('workload')}, {payload.get('dtype')}, "
            f"size {payload.get('size')}, {detail.get('work_per_iteration')} per iteration)")
    if payload.get("ok") is not True or payload.get("aborted"):
        bad("the fixed work did not complete")
    if payload.get("iterations_completed") != rec.get("iterations"):
        bad(f"{payload.get('iterations_completed')} of {rec.get('iterations')} iterations")
    if detail.get("warmup_iterations") != design.WARMUP_ITERATIONS:
        bad(f"warm-up {detail.get('warmup_iterations')}")
    if detail.get("preload_seconds_requested") != design.PRELOAD_SECONDS or not \
            (finite(detail.get("preload_seconds")) and detail["preload_seconds"] >= design.PRELOAD_SECONDS):
        bad(f"preload {detail.get('preload_seconds_requested')} requested, {detail.get('preload_seconds')} s run")
    events = rec.get("events") or {}
    if not (finite(events.get("washout_start"), events.get("washout_end"))
            and events["washout_end"] - events["washout_start"] >= design.WASHOUT_SECONDS - 0.01):
        bad("washout shorter than 30 s or unrecorded")

    start, end = detail.get("energy_start") or {}, detail.get("energy_end") or {}
    e0, e1 = start.get("value_mj"), end.get("value_mj")
    if not (_bracket_ok(start) and _bracket_ok(end) and start["mono_after"] <= end["mono_before"]):
        bad("energy endpoint brackets missing, non-finite or out of order")
        return metrics, problems
    t = _midpoint(end) - _midpoint(start)
    w0, w1 = detail.get("work_mono_start"), detail.get("work_mono_end")
    if not (finite(w0, w1) and start["mono_after"] <= w0 < w1 <= end["mono_before"]):
        bad(f"fixed-work bounds {w0} to {w1} are missing or not between the endpoints")
    cached_t = detail.get("duration_t_seconds")
    if not finite(cached_t) or abs(cached_t - t) > 1e-6:
        bad(f"cached T {cached_t} disagrees with the brackets' {t:.6f} s")
    per_iteration, completed = detail.get("work_per_iteration"), payload.get("iterations_completed")
    work = per_iteration * completed if finite(per_iteration) and isinstance(completed, int) else None
    cached_work = detail.get("work_units")
    if work is None or work <= 0 or not finite(cached_work) or abs(cached_work - work) > 1e-9 * work:
        bad(f"work {cached_work} disagrees with {per_iteration} x {completed}")
    if not (isinstance(e0, int) and isinstance(e1, int) and e1 > e0 >= 0 and t > 0 and work):
        bad(f"invalid endpoints (E {e0} -> {e1}, T {t})")
    else:
        joules = (e1 - e0) / 1000.0
        metrics.update(p=joules / t, e=joules / work, throughput=work / t, joules=joules, t=t)

    support = detail.get("energy_support_reads")
    if not (isinstance(support, list) and len(support) == 1 and support[0].get("ok") is True):
        bad("the energy support read is missing or failed")
    temps = detail.get("temperature_reads")
    if not temps or not all(finite(r.get("value_c")) and r["value_c"] < THERMAL_CEILING_C for r in temps):
        bad("temperature evidence missing, non-finite or at the ceiling")
    for key in ("clocks_before_start", "clocks_after_end"):
        clocks = detail.get(key) or {}
        sm, mem = clocks.get("sm_mhz"), clocks.get("mem_mhz")
        if not finite(sm, target) or abs(sm - target) > CLOCK_TOLERANCE_MHZ:
            bad(f"{key} SM clock {sm} MHz against target {target}")
        if not finite(mem) or not MEMORY_LOADED_MHZ[0] <= mem <= MEMORY_LOADED_MHZ[1]:
            bad(f"{key} memory clock {mem} MHz")

    ready, done = rec.get("reader_ready") or {}, rec.get("reader_done") or {}
    if ready.get("mode") != arm or done.get("mode") != arm:
        bad(f"reader mode {ready.get('mode')}/{done.get('mode')} for arm {arm}")
    csv_path = session_dir / rec.get("reader_csv", "missing.csv")
    if not csv_path.exists():
        bad("reader CSV missing")
        return metrics, problems
    columns, rows = read_reader(csv_path)
    if columns != columns_for(arm):
        bad(f"reader columns {columns} are not arm {arm}'s")
        return metrics, problems
    if len(rows) != done.get("rows") or [int(r["seq"]) for r in rows] != list(range(len(rows))):
        bad(f"{len(rows)} reader rows against {done.get('rows')} reported, or a broken sequence")
    calls = len(design.MODE_CALLS[arm]) * len(rows)
    if done.get("nvml_power_energy_calls") != calls or done.get("failed_calls") != 0:
        bad(f"reader made {done.get('nvml_power_energy_calls')} calls ({done.get('failed_calls')} failed), "
            f"expected {calls} and 0")
    previous = None
    for r in rows:
        stamps = [_number(r["mono_before"])] + [_number(r[c]) for c in columns if c.endswith(("_mono_before", "_mono_after"))] \
            + [_number(r["mono_after"])]
        if None in stamps or stamps != sorted(stamps) or _number(r["unix"]) is None:
            bad(f"reader row {r['seq']} has missing, non-finite or out-of-order timing brackets")
            return metrics, problems
        if previous is not None and stamps[0] <= previous:
            bad(f"reader poll starts do not increase at row {r['seq']}")
            return metrics, problems
        previous = stamps[0]
        for column in columns:
            value = r[column]
            if column.endswith(("_ts_us", "_latency_us")) and not _integral(value):
                bad(f"reader {column} holds {value!r}")
                return metrics, problems
            if column.endswith("_ret") and value != "0":
                bad(f"reader {column} returned {value!r}")
                return metrics, problems
            if column.endswith("_type"):
                fid = int(column[1:].split("_")[0])
                if value != str(FIELD_TYPES[fid]):
                    bad(f"reader {column} is {value!r}, not {FIELD_TYPES[fid]}")
                    return metrics, problems
            if (column.endswith("_value") or column == "usage_mw") and \
                    (value == "" or not math.isfinite(float(value)) or float(value) < 0):
                bad(f"reader {column} holds {value!r}")
                return metrics, problems

    t_start, t_end = _midpoint(start), _midpoint(end)
    monos = [float(r["mono_before"]) for r in rows]
    if not monos or not (monos[0] <= t_start and monos[-1] >= t_end):
        bad("the reader did not run through both endpoints")
    inside = [m for m in monos if t_start <= m <= t_end]
    gaps = sorted((b - a) * 1000.0 for a, b in zip(inside, inside[1:]))
    if gaps:
        metrics["cadence_median_ms"] = statistics.median(gaps)
        metrics["cadence_p99_ms"] = nearest_rank(gaps, 0.99)
    if arm != "A":
        if len(gaps) < MIN_CADENCE_INTERVALS:
            bad(f"only {len(gaps)} reader intervals inside the window")
        else:
            low, high = design.CADENCE_MEDIAN_MS
            if not low <= metrics["cadence_median_ms"] <= high or metrics["cadence_p99_ms"] > design.CADENCE_P99_MAX_MS:
                bad(f"cadence median {metrics['cadence_median_ms']:.1f} ms, p99 {metrics['cadence_p99_ms']:.1f} ms")
        stale = 0.0
        for column in [c for c in columns if c.endswith("_ts_us")]:
            last_ts, since = None, None
            for r in rows:
                m = float(r["mono_before"])
                if not t_start <= m <= t_end:
                    continue
                if r[column] != last_ts:
                    last_ts, since = r[column], m
                else:
                    stale = max(stale, m - since)
        metrics["stale_max_s"] = stale
    return metrics, problems
