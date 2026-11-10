"""Score REGISTERED-PREDICTIONS section 22: day-to-day stock repeatability on the RTX 5060 Ti.

Usage: python analysis/score_repeatability.py DAY_DIRECTORY [DAY_DIRECTORY ...]

Written 2026-10-14 with section 22's registration and before any of its days existed. Each day is one
session of tools/rerun15/Invoke-Rerun15Session.ps1 -Parts rep -Session N, filed under data/repeatability/
by tools/rerun15/file_repeatability_day.py: its rerun15-inputs.json maps eight roles,
"pass{1,2}-{workload}", to sweeps on one fixed 20-target grid, one pass ascending and one descending.

Days are the units. A day is VALID when every check below holds, and SCOREABLE when it also passes the
return gate; only scoreable days enter the intervals. N=1 chip throughout: five days are five repeated
observations of one card, never five cards.

Design: GPT Job 87's draft (docs/gpt-findings/2026-10-13-repeatability-registration-draft.md), adopted
with the changes the registration lists (no ambient instrument; no raw per-point sidecars; distinct
local dates rather than a 24 h start gap as the hard rule).

Hardened 2026-10-14, before any day, after GPT Job 94's audit
(docs/gpt-findings/2026-10-15-section22-implementation-audit.md). No registered rule changed; the
scorer now enforces rules it had trusted the runner's declarations for: the attempt ledgers are
required and the first attempt at a day index is the only eligible one; every date the day occupies
is checked; exactly eight roles, each the registered command, in order, after its own stock witness,
whose profile store must hash to the curve3 snapshot; a clean display-driver event read after every
role and after cleanup; the runner as run is filed and matches its launch hash; non-finite telemetry
and absent throttle evidence are refused. It also reports every registered curve output (--json).
"""

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from score_section20b import t_quantile


def _gamma_p(a, x):
    """Regularized lower incomplete gamma P(a, x), by series (x < a + 1) or continued fraction."""
    if x <= 0:
        return 0.0
    if x < a + 1:
        term = total = 1.0 / a
        n = a
        for _ in range(500):
            n += 1
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b, c, d = x + 1 - a, 1e300, 1.0 / (x + 1 - a)
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return 1.0 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_quantile(p, df):
    """Chi-square quantile by bisection on the CDF (SciPy is not a declared dependency here)."""
    lo, hi = 0.0, max(1.0, 4.0 * df)
    while _gamma_p(df / 2.0, hi / 2.0) < p:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _gamma_p(df / 2.0, mid / 2.0) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0

WORKLOADS = ("gemm", "copy", "reduce", "resnet50")
ITERATIONS = {"gemm": 120, "copy": 2660, "reduce": 2870, "resnet50": 424}
GRID = (1237, 1275, 1312, 1350, 1387, 1425, 1462, 1500, 1537, 1575,
        1612, 1650, 1687, 1725, 1762, 1800, 1837, 1875, 2010, 2317)
FINE = GRID[:18]
REFERENCE = 1575          # the registered floor-end reference (section 20 / worklist 4h)
INPUT_SEED = 20261013
SCHEDULE = {               # day -> (first-pass order, first pass descending); pass 2 reverses both
    1: (("gemm", "copy", "reduce", "resnet50"), False),
    2: (("copy", "reduce", "resnet50", "gemm"), True),
    3: (("reduce", "resnet50", "gemm", "copy"), False),
    4: (("resnet50", "gemm", "copy", "reduce"), True),
    5: (("gemm", "copy", "reduce", "resnet50"), False),
}
RETURN_LIMIT_PCT = 1.5
REGRET_REFERENCE_PCT = 3.0
NEAR_OPTIMAL_PCT = 1.0
LOCK_TOLERANCE_MHZ = 15.0
MEMORY_LOADED = (13801, 14001)
CONCERNING_BITS = 0x8 | 0x20 | 0x40 | 0x80     # HwSlowdown, SwThermal, HwThermal, HwPowerBrake
SW_POWER_CAP = 0x4

MAX_TEMP_C = 88.0
POWER = {"sampled": "power_avg_w", "energy": "energy_avg_power_w"}
DRIVER = "616.92"
OFFSET_KEYS = {"xbar_offset_mhz", "sys_offset_mhz", "video_offset_mhz", "demand_core_mv", "demand_xbar_mv",
               "demand_sys_mv", "demand_video_mv"}
SOURCES = ("Invoke-Rerun15Session.ps1", "Invoke-LoggedSweep.ps1", "gpu_workload.py", "app_workloads.py")
STORE_NAME = "VEN_10DE&DEV_2D04&SUBSYS_177219DA&REV_A1&BUS_1&DEV_0&FN_0.cfg"
SNAPSHOT = Path("data") / "afterburner-profiles" / "5060ti-profiles-20260926-curve3" / STORE_NAME
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def passes(day):
    order, descending = SCHEDULE[day]
    return ((1, tuple(order), descending), (2, tuple(reversed(order)), not descending))


def roles_in_order(day):
    return [f"pass{n}-{w}" for n, order, _ in passes(day) for w in order]


def resolve(directory, value):
    path = Path(str(value))
    return path if path.is_absolute() else directory / path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def masks(text):
    out = []
    for part in re.split(r"[;,\s]+", str(text or "").strip()):
        if part:
            out.append(int(part, 16))
    return out


def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def section_hash(path):
    """Get-SectionHash in Invoke-Rerun15Session.ps1: [Startup] and [Profile1]-[Profile5] only, byte for
    byte in file order, SHA-256 in upper-case hex. Afterburner appends other sections by itself."""
    text = Path(path).read_bytes().decode("latin-1")
    sections = re.split(r"(?m)^(?=\[)", text)
    kept = "".join(s for s in sections if re.match(r"^\[(Startup|Profile[1-5])\]", s))
    return hashlib.sha256(kept.encode("latin-1")).hexdigest().upper()


def parse_time(text):
    """An ISO timestamp with offset, as the sweep JSON writes it (seven fractional digits allowed)."""
    text = re.sub(r"(\.\d{6})\d+", r"\1", str(text))
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError(f"timestamp {text!r} has no UTC offset")
    return value


def read_sweep(path, descending):
    """{target: point} in the declared order; raises ValueError naming the first broken rule."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    targets = []
    points = {}
    for raw in rows:
        where = f"{path.name}: target {raw.get('target_frequency_mhz')}"
        try:
            target = float(raw["target_frequency_mhz"])
            point = {
                "throughput": float(raw["bench_throughput"]),
                "sampled": float(raw["power_avg_w"]),
                "energy": float(raw.get("energy_avg_power_w") or "nan"),
                "achieved_min": float(raw["achieved_frequency_min"]),
                "achieved_max": float(raw["achieved_frequency_max"]),
                "achieved": float(raw["achieved_frequency_avg"]),
                "memory_max": float(raw["memory_clock_max_mhz"]),
                "temp_max": float(raw["temperature_max_c"]),
                "masks": masks(raw.get("throttle_masks_seen")),
            }
        except (KeyError, ValueError, TypeError):
            raise ValueError(f"{where}: a required column is missing or unreadable")
        if not (math.isfinite(target) and target.is_integer()):
            raise ValueError(f"{where}: not a whole-MHz target")
        target = int(target)
        if str(raw.get("bench_ok")).strip().lower() != "true":
            raise ValueError(f"{where}: the benchmark did not report ok")
        if str(raw.get("power_window_applied")).strip().lower() != "true":
            raise ValueError(f"{where}: power was not windowed to the timed work")
        if not all(math.isfinite(point[k]) and point[k] > 0 for k in ("throughput", "sampled")):
            raise ValueError(f"{where}: throughput and sampled power must be finite and positive")
        # GPT Job 94, F4: a NaN compares false against every threshold, so missing or corrupt telemetry
        # must be refused before the thresholds, and an empty mask list is absent evidence, not a clean one.
        if not all(math.isfinite(point[k]) for k in ("achieved_min", "achieved", "achieved_max", "temp_max")):
            raise ValueError(f"{where}: an achieved-clock or temperature reading is not finite")
        if not point["achieved_min"] <= point["achieved"] <= point["achieved_max"]:
            raise ValueError(f"{where}: the achieved-clock minimum, mean and maximum are inconsistent")
        if not point["masks"]:
            raise ValueError(f"{where}: no throttle-reason evidence was recorded")
        if (abs(point["achieved_min"] - target) > LOCK_TOLERANCE_MHZ
                or abs(point["achieved_max"] - target) > LOCK_TOLERANCE_MHZ):
            raise ValueError(f"{where}: the achieved clock left target +/- {LOCK_TOLERANCE_MHZ:g} MHz "
                             f"({point['achieved_min']:g}-{point['achieved_max']:g})")
        if not MEMORY_LOADED[0] <= point["memory_max"] <= MEMORY_LOADED[1]:
            raise ValueError(f"{where}: loaded memory {point['memory_max']:g} MHz is outside 13801-14001")
        if any(m & CONCERNING_BITS for m in point["masks"]):
            raise ValueError(f"{where}: a thermal or hardware slowdown reason was seen")
        if point["temp_max"] >= MAX_TEMP_C:
            raise ValueError(f"{where}: temperature reached {point['temp_max']:g} C")
        targets.append(target)
        points[target] = point
    expected = list(sorted(GRID, reverse=descending))
    if targets != expected:
        raise ValueError(f"{path.name}: targets are not the registered grid in the declared "
                         f"{'descending' if descending else 'ascending'} order")
    return points


def expected_command(workload):
    """The arguments Invoke-LoggedSweep.ps1 gives gpu_workload.py for a section 22 role, in its order."""
    args = ["--workload", workload, "--json", "--iterations", str(ITERATIONS[workload])]
    if workload != "resnet50":
        args += ["--input-seed", str(INPUT_SEED)]
    return args


def command_problem(command, workload):
    """None when the recorded workload command is exactly the registered one for this workload."""
    tokens = str(command or "").split()
    script = next((i for i, tok in enumerate(tokens) if tok.replace("\\", "/").endswith("/gpu_workload.py")), None)
    if script is None:
        return "the workload command does not run gpu_workload.py"
    if tokens[script + 1:] != expected_command(workload):
        return f"the workload command's arguments are {' '.join(tokens[script + 1:])!r}, not the registered ones"
    return None


def events_ok(record):
    return isinstance(record, dict) and record.get("ok") is True and record.get("count") == 0


def launch_hash_form(data, recorded):
    """How the filed runner matches the hash the runner took of itself at launch, or None.

    GPT Jobs 99 (F4) and 100 (F1), 2026-10-16: the runner hashes its own CRLF bytes on Windows, and git
    stores the filed copy as LF, so an LF checkout failed the raw comparison. The CRLF reconstruction is
    exact (every LF becomes CRLF, nothing else changes) and is reported as such, never silently."""
    recorded = str(recorded).upper()
    if hashlib.sha256(data).hexdigest().upper() == recorded:
        return "bytes as filed"
    crlf = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if hashlib.sha256(crlf).hexdigest().upper() == recorded:
        return "CRLF reconstruction of the filed copy"
    return None


def mvolt_status_problem(store_path, offsets):
    """GPT Job 100, F2: the full mVolt+ status record the runner wrote beside the witnessed store, not
    only its seven-value summary. Every offset and voltage demand, the NVVDD offsets included, must
    read 0, the enforced limit 180 W, and the summary must agree with it."""
    status = Path(str(store_path).replace("-store.cfg", "-mvolt-status.json"))
    try:
        record = read_json(status)
    except (OSError, ValueError) as exc:
        return f"the full mVolt+ status record is missing or unreadable ({exc})"
    demands = record.get("voltage_demand_mv")
    nvvdd = record.get("nvvdd_offsets_uv")
    full = {"xbar_offset_mhz": record.get("xbar_offset_mhz"), "sys_offset_mhz": record.get("sys_offset_mhz"),
            "video_offset_mhz": record.get("video_offset_mhz")}
    if not (isinstance(demands, dict) and set(demands) == {"Core", "Xbar", "SYS", "Video"}
            and isinstance(nvvdd, dict) and nvvdd):
        return "the full mVolt+ status record lacks its voltage demands or NVVDD offsets"
    full.update({"demand_core_mv": demands["Core"], "demand_xbar_mv": demands["Xbar"],
                 "demand_sys_mv": demands["SYS"], "demand_video_mv": demands["Video"]})
    if any(v != 0 for v in full.values()) or any(v != 0 for v in nvvdd.values()):
        return "the full mVolt+ status record shows a non-zero offset or voltage demand"
    if full != offsets:
        return "the mVolt+ summary in the manifest does not match the full status record"
    if (record.get("power_limits") or {}).get("enforced_mw") != 180000:
        return "the full mVolt+ status record does not show 180 W enforced"
    return None


def witness_problem(witness, directory, snapshot_hash):
    if not (witness.get("profile_slot") == 3 and witness.get("snapshot") == "curve3"
            and witness.get("memory_loaded_mhz") == 13801 and witness.get("power_limit_w") == 180
            and witness.get("driver") == DRIVER):
        return "the stock witness is not the registered one"
    offsets = witness.get("offsets_mhz")
    if not isinstance(offsets, dict) or set(offsets) != OFFSET_KEYS or any(v != 0 for v in offsets.values()):
        return "the mVolt+ witness is not the complete set of seven zero offsets and demands"
    if witness.get("restored_byte_for_byte") is not True or witness.get("afterburner_closed") is not True:
        return "the witness does not record the store restored byte for byte with Afterburner closed"
    if not (finite(witness.get("gemm_2475_power_w")) and float(witness["gemm_2475_power_w"]) > 0):
        return "the 2475 MHz gemm witness was not recorded"
    if not finite(witness.get("witnessed_at_unix")):
        return "the witness has no time"
    store = witness.get("profile_store")
    if not store or not resolve(directory, store).is_file():
        return "the witnessed profile store was not filed with the day"
    if section_hash(resolve(directory, store)) != snapshot_hash:
        return "the witnessed profile store's sections are not the curve3 snapshot's"
    wrong = mvolt_status_problem(resolve(directory, store), offsets)
    if wrong:
        return wrong
    return None


def section20b_dates(repo):
    """Local dates of every section 20b attempt in its ledger, which section 22 days must avoid. The
    ledger is required: without it the rule cannot be checked (GPT Job 94, F1)."""
    ledger = repo / "docs" / "section20b" / "ATTEMPTS.md"
    if not ledger.is_file():
        raise ValueError(f"cannot check section 22's date rule: {ledger} is missing")
    return set(re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|", ledger.read_text(encoding="utf-8")))


def day_attempts(repo):
    """{day index: [local dates of its attempts, in ledger order]} from docs/repeatability/ATTEMPTS.md.
    Qualifications are not days. The ledger is required (GPT Job 94, F1)."""
    ledger = repo / "docs" / "repeatability" / "ATTEMPTS.md"
    if not ledger.is_file():
        raise ValueError(f"cannot check section 22's attempt history: {ledger} is missing")
    attempts = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        kind = cells[1].lower()
        if "day" not in kind or "qualification" in kind:
            continue
        if not cells[2].isdigit() or not DATE.match(cells[3]):
            raise ValueError(f"attempt ledger row {cells[0]}: day index or local date unreadable")
        attempts.setdefault(int(cells[2]), []).append(cells[3])
    return attempts


def load_day(directory, repo=Path(__file__).resolve().parents[1]):
    """Read and check one day. Returns a dict with 'status' VALID/INVALID, 'problems' and the data."""
    directory = Path(directory)
    problems = []
    out = {"directory": str(directory), "problems": problems, "status": "INVALID", "occupied": set()}
    try:
        manifest = read_json(directory / "rerun15-inputs.json")
    except (OSError, ValueError) as exc:
        problems.append(f"rerun15-inputs.json unreadable: {exc}")
        return out
    rep = manifest.get("repeatability") or {}
    day = rep.get("day")
    out["day"] = day
    out["date"] = rep.get("localDate")
    if "section 22" not in str(manifest.get("section", "")):
        problems.append("not a section 22 session")
    if manifest.get("dryRun") is not False:
        problems.append("a dry run is a qualification, not a day")
    if manifest.get("exitCode") != 0:
        problems.append(f"the runner exited {manifest.get('exitCode')!r}, not 0")
    if manifest.get("notScoreable"):
        problems.append("roles were recorded NOT SCOREABLE (desktop load): " + ", ".join(manifest["notScoreable"]))
    if not (isinstance(out["date"], str) and DATE.match(out["date"])):
        problems.append(f"the local date {out['date']!r} is not a yyyy-mm-dd date")
    else:
        out["occupied"].add(out["date"])          # the day began on it, before its first sweep
    if day not in SCHEDULE:
        problems.append(f"day index {day!r} is not 1-5")
        return out
    order, descending = SCHEDULE[day]
    second = (rep.get("pass2") or {})
    if (list(rep.get("grid") or []) != list(GRID) or rep.get("inputSeed") != INPUT_SEED
            or {k: int(v) for k, v in (rep.get("iterations") or {}).items()} != ITERATIONS
            or list((rep.get("pass1") or {}).get("order") or []) != list(order)
            or (rep.get("pass1") or {}).get("descending") is not descending
            or list(second.get("order") or []) != list(reversed(order))
            or second.get("descending") is not (not descending)):
        problems.append("the recorded grid, seed, iterations or day schedule is not the registered one")
    # GPT Job 94, F2: the event log must have been READ, and read clean, after every role and after cleanup.
    if not events_ok(manifest.get("driverEventsFinal")):
        problems.append("no clean display-driver event read after cleanup (unread, or events found)")
    # GPT Job 94, F7: the runner as run is filed, and it is the file the runner hashed at launch.
    sources = manifest.get("sources") or {}
    if set(sources) != set(SOURCES):
        problems.append("the manifest does not record the hashes of the runner and what it called")
    else:
        try:
            form = launch_hash_form((directory / "runner-Invoke-Rerun15Session.ps1.txt").read_bytes(),
                                    sources["Invoke-Rerun15Session.ps1"])
            out["runner_hash_match"] = form
            if form is None:
                problems.append("the filed runner is not the file the runner hashed at launch")
        except OSError as exc:
            problems.append(f"the filed runner is unreadable: {exc}")
    try:
        cleanup = read_json(directory / "runner-cleanup.json")
        if not (cleanup.get("ok") is True and cleanup.get("reset_exit") == 0 and cleanup.get("store_restored") is True
                and finite(cleanup.get("memory_loaded_mhz")) and finite(cleanup.get("power_limit_w"))
                and MEMORY_LOADED[0] <= float(cleanup["memory_loaded_mhz"]) <= MEMORY_LOADED[1]
                and abs(float(cleanup["power_limit_w"]) - 180) <= 0.5 and not cleanup.get("errors")):
            problems.append("the runner's cleanup did not verify stock")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        problems.append(f"runner-cleanup.json unreadable: {exc}")
    try:
        snapshot_hash = section_hash(repo / SNAPSHOT)
    except OSError as exc:
        raise ValueError(f"cannot check the stock witness: the curve3 snapshot is unreadable ({exc})")
    sweeps = manifest.get("sweeps") or {}
    # GPT Job 94, F3: exactly the eight registered roles, no more.
    if set(sweeps) != set(roles_in_order(day)):
        extra = sorted(set(sweeps) - set(roles_in_order(day)))
        if extra:
            problems.append("roles other than the registered eight: " + ", ".join(extra))
    offset = rep.get("utcOffsetMinutes")
    data = {}
    caps = 0
    spans = {}
    witnesses = {1: set(), 2: set()}
    for number, pass_order, pass_desc in passes(day):
        for workload in pass_order:
            role = f"pass{number}-{workload}"
            desc = sweeps.get(role)
            if not isinstance(desc, dict):
                problems.append(f"{role}: missing, or retried (section 22 allows no retry)")
                continue
            witness = desc.get("witness") or {}
            wrong = witness_problem(witness, directory, snapshot_hash)
            if wrong:
                problems.append(f"{role}: {wrong}")
            elif finite(witness.get("witnessed_at_unix")):
                witnesses[number].add(float(witness["witnessed_at_unix"]))
            if not events_ok(desc.get("driver_events")):
                problems.append(f"{role}: no clean display-driver event read after the role")
            try:
                wrapper = read_json(resolve(directory, desc["wrapper"]))
                if wrapper.get("desktopLoad") != "quiet":
                    problems.append(f"{role}: desktop-load verdict {wrapper.get('desktopLoad')!r}, not 'quiet'")
                if wrapper.get("sweepExitCode") != 0 or wrapper.get("logStopExitCode") != 0:
                    problems.append(f"{role}: the sweep or log stop did not exit 0")
                metadata = read_json(resolve(directory, desc["sweep"]).with_suffix(".json"))
                limit = float(metadata.get("power_limit_enforced_w", "nan"))
                if not math.isfinite(limit) or abs(limit - 180) > 0.5:
                    problems.append(f"{role}: the enforced power limit is not 180 W")
                if metadata.get("session_label") != f"rep-{role}":
                    problems.append(f"{role}: the sweep's label is {metadata.get('session_label')!r}, not 'rep-{role}'")
                if metadata.get("driver_version") != DRIVER:
                    problems.append(f"{role}: driver {metadata.get('driver_version')!r}, not {DRIVER}")
                if metadata.get("sweep_order") != ("descending" if pass_desc else "ascending"):
                    problems.append(f"{role}: the sweep ran {metadata.get('sweep_order')!r}, not the declared direction")
                wrong = command_problem(metadata.get("workload_command"), workload)
                if wrong:
                    problems.append(f"{role}: {wrong}")
                start, end = parse_time(metadata["started_at"]), parse_time(metadata["ended_at"])
                if not start < end:
                    problems.append(f"{role}: the sweep ends before it starts")
                spans[role] = (start, end)
                out["occupied"].update({metadata["started_at"][:10], metadata["ended_at"][:10]})
                points = read_sweep(resolve(directory, desc["sweep"]), pass_desc)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                problems.append(f"{role}: {exc}")
                continue
            caps += sum(1 for p in points.values() if any(m & SW_POWER_CAP for m in p["masks"]))
            data[(number, workload)] = {"points": points, "descending": pass_desc,
                                        "sweep": str(resolve(directory, desc["sweep"]))}
    # GPT Job 94, F3: the roles ran in the registered order, one after another, each pass after its own
    # stock witness, and the second pass after a fresh one.
    ordered = [spans.get(r) for r in roles_in_order(day)]
    if all(ordered):
        if any(later[0] < earlier[1] for earlier, later in zip(ordered, ordered[1:])):
            problems.append("the roles did not run one after another in the registered order")
        if len(witnesses[1]) == 1 and len(witnesses[2]) == 1:
            w1, w2 = next(iter(witnesses[1])), next(iter(witnesses[2]))
            if not (w1 < ordered[0][0].timestamp() and ordered[3][1].timestamp() <= w2 < ordered[4][0].timestamp()):
                problems.append("a pass was not preceded by its own stock witness")
            if offset is not None and finite(offset):
                for t in (w1, w2):
                    local = datetime.fromtimestamp(t, tz=timezone(timedelta(minutes=int(offset))))
                    out["occupied"].add(local.strftime("%Y-%m-%d"))
        else:
            problems.append("each pass must carry exactly one stock witness")
    # GPT Job 100, F3: the final event read must cover the whole day: read after the last sweep ended,
    # over a window that began before the first witness. A clean read taken earlier proves nothing.
    final = manifest.get("driverEventsFinal") or {}
    if all(ordered) and witnesses[1]:
        if not (finite(final.get("read_at_unix")) and finite(final.get("session_start_unix"))
                and float(final["read_at_unix"]) > max(e.timestamp() for _, e in ordered)
                and float(final["session_start_unix"]) <= min(witnesses[1])):
            problems.append("the final event read does not cover the whole day (from before the first "
                            "witness to after the last sweep)")
    if out["occupied"] and out["date"] != min(out["occupied"]):
        problems.append(f"the recorded local date {out['date']!r} is not the day's first date, {min(out['occupied'])}")
    out["data"] = data
    out["power_cap_points"] = caps
    if not problems and len(data) == 8:
        out["status"] = "VALID"
    return out


def return_gate(day):
    """Per workload, median absolute matched-target throughput change, second pass against first."""
    gate = {}
    for w in WORKLOADS:
        first, second = day["data"][(1, w)]["points"], day["data"][(2, w)]["points"]
        changes = [100 * (second[t]["throughput"] / first[t]["throughput"] - 1) for t in GRID]
        gate[w] = {"median_abs_pct": statistics.median(abs(c) for c in changes),
                   "max_abs_pct": max(abs(c) for c in changes), "changes": changes}
    return gate


def day_efficiency(day, figure):
    """{workload: {target: direction-averaged efficiency}}, the mean of the two directions' ratios
    (section 20's estimator), or None for a workload whose figure is missing anywhere."""
    out = {}
    for w in WORKLOADS:
        a, b = day["data"][(1, w)]["points"], day["data"][(2, w)]["points"]
        values = {}
        for t in GRID:
            # GPT Job 94, F5: a zero or missing secondary figure is refused before dividing by it.
            if not all(math.isfinite(d[t][figure]) and d[t][figure] > 0 for d in (a, b)):
                values = None
                break
            ratios = [d[t]["throughput"] / d[t][figure] for d in (a, b)]
            if not all(math.isfinite(r) and r > 0 for r in ratios):
                values = None
                break
            values[t] = statistics.fmean(ratios)
        out[w] = values
    return out


def direction_argmax(day, w):
    found = {}
    for number in (1, 2):
        cell = day["data"][(number, w)]
        eff = {t: p["throughput"] / p["sampled"] for t, p in cell["points"].items()}
        found["desc" if cell["descending"] else "asc"] = max(sorted(eff), key=eff.get)
    return found


def sd_interval(sd, D):
    """95% chi-square interval for a standard deviation from D values."""
    return (sd * math.sqrt((D - 1) / chi2_quantile(0.975, D - 1)),
            sd * math.sqrt((D - 1) / chi2_quantile(0.025, D - 1)))


def summarize(eff_days):
    """Day-level statistics for one workload: eff_days is a list of {target: efficiency}."""
    D = len(eff_days)
    result = {"D": D}
    argmax = [max(sorted(e), key=e.get) for e in eff_days]          # ties go to the LOWEST target
    regret = [100 * (1 - e[REFERENCE] / max(e.values())) for e in eff_days]
    near = [sorted(t for t in GRID if 100 * (1 - e[t] / max(e.values())) <= NEAR_OPTIMAL_PCT + 1e-9) for e in eff_days]
    result.update(argmax=argmax, regret=regret, near_optimal=near,
                  edge_peaks=sum(1 for t in argmax if t in (GRID[0], GRID[-1])))
    curve = {}
    for t in GRID:
        x = [math.log(e[t]) for e in eff_days]
        z = [100 * math.log(e[t] / e[REFERENCE]) for e in eff_days]
        curve[t] = {"geomean": math.exp(statistics.fmean(x)), "min": min(e[t] for e in eff_days),
                    "max": max(e[t] for e in eff_days),
                    "log_sd": statistics.stdev(x) if D >= 2 else None,
                    "shape_mean": statistics.fmean(z), "shape_min": min(z), "shape_max": max(z),
                    "shape_sd": statistics.stdev(z) if D >= 2 else None}
        if D >= 2:
            t95 = t_quantile(0.975, D - 1)
            half = t95 * curve[t]["log_sd"] / math.sqrt(D)
            mean = statistics.fmean(x)
            curve[t]["ci95"] = (math.exp(mean - half), math.exp(mean + half))
            curve[t]["log_sd_ci95"] = sd_interval(curve[t]["log_sd"], D)
            shalf = t95 * curve[t]["shape_sd"] / math.sqrt(D)
            curve[t]["shape_ci95"] = (curve[t]["shape_mean"] - shalf, curve[t]["shape_mean"] + shalf)
    result["curve"] = curve
    if D >= 2:
        sd = statistics.stdev(regret)
        mean = statistics.fmean(regret)
        half = t_quantile(1 - 0.05 / 8, D - 1) * sd / math.sqrt(D)
        result.update(regret_mean=mean, regret_sd=sd, regret_ci9875=(mean - half, mean + half),
                      regret_sd_ci95=sd_interval(sd, D))
        low, high = result["regret_ci9875"]
        if high <= REGRET_REFERENCE_PCT + 1e-9:
            result["outcome"] = "WITHIN 3%"
        elif low > REGRET_REFERENCE_PCT + 1e-9:
            result["outcome"] = "ABOVE 3%"
        else:
            result["outcome"] = "INCONCLUSIVE"
    return result


def measured_floor(sweep_csv):
    """The measured VID floor from the joined voltage extract, in target order: the lowest reading, the
    last target of the first run at it and the first target above it. Secondary and descriptive only.
    None when there is no extract, a grid target has no voltage, or a point has fewer than five samples.
    'reenters' is True when the curve returns to the lowest reading after leaving it (GPT Job 94, F8),
    and then the floor end is ambiguous, not a clean single exit."""
    extract = Path(str(sweep_csv).replace("_sweep.csv", "_sweep_voltage.csv"))
    if not extract.exists():
        return None
    with open(extract, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    try:
        points = sorted((int(float(r["target"])), float(r["voltage"]), int(float(r.get("sampleCount") or 0)))
                        for r in rows if r.get("voltage") not in (None, ""))
    except (KeyError, ValueError):
        return None
    if ([t for t, _, _ in points] != sorted(GRID) or any(n < 5 for _, _, n in points)
            or not all(math.isfinite(v) for _, v, _ in points)):
        return None
    low = min(v for _, v, _ in points)
    at_low = [abs(v - low) < 1e-9 for _, v, _ in points]
    first = at_low.index(True)
    end = first
    while end + 1 < len(points) and at_low[end + 1]:
        end += 1
    return {"floor_v": low, "last_floor_target": points[end][0],
            "first_rise_target": points[end + 1][0] if end + 1 < len(points) else None,
            "reenters": any(at_low[end + 1:]), "starts_at_floor": first == 0}


def score(directories, repo=Path(__file__).resolve().parents[1]):
    repo = Path(repo)
    blocked = section20b_dates(repo)
    attempts = day_attempts(repo)
    days = [load_day(d, repo) for d in directories]
    # GPT Job 94, F1: the eligible observation for day k is the FIRST attempt at day k in the ledger
    # pushed before launch; a later attempt never replaces it, whatever order the folders are given in.
    first = {k: v[0] for k, v in attempts.items()}
    for day in days:
        k, date = day.get("day"), day.get("date")
        if k not in SCHEDULE:
            continue
        if k not in first:
            day["problems"].append(f"no attempt line for day {k} in docs/repeatability/ATTEMPTS.md")
        elif first[k] != date:
            day["problems"].append(f"not the first attempt at day {k} (that was {first[k]}); "
                                   "section 22 allows no replacement day")
        if k > 1 and not (k - 1 in first and first[k - 1] < first.get(k, date)):
            day["problems"].append(f"day {k} did not follow a day {k - 1} attempt on an earlier date "
                                   "(days run in index order)")
        clash = sorted(day["occupied"] & blocked)
        if clash:
            day["problems"].append(f"{', '.join(clash)} is also a section 20b date")
        if day["problems"]:
            day["status"] = "INVALID"
    ranked = sorted(days, key=lambda d: (d.get("day") if isinstance(d.get("day"), int) else 99, str(d.get("date"))))
    claimed_days, claimed_dates = set(), set()
    for day in ranked:
        clash = sorted(day["occupied"] & claimed_dates)
        if day.get("day") in claimed_days or clash:
            day["problems"].append("a day index or local date repeats an earlier day's")
            day["status"] = "INVALID"
        claimed_days.add(day.get("day"))
        claimed_dates |= day["occupied"]
    for day in days:
        if day["status"] == "VALID":
            day["gate"] = return_gate(day)
            day["status"] = ("SCOREABLE" if all(g["median_abs_pct"] <= RETURN_LIMIT_PCT + 1e-9 for g in day["gate"].values())
                             else "VALID, NOT SCOREABLE")
    scoreable = sorted((d for d in days if d["status"] == "SCOREABLE"), key=lambda d: d["day"])
    D = len(scoreable)
    stage = "COMPLETE" if D == 5 else ("PARTIAL" if D >= 3 else "DESCRIPTIVE ONLY")
    results = {"days": days, "D": D, "stage": stage, "workloads": {}, "energy": {}, "floors": {}}
    for figure, target in (("sampled", results["workloads"]), ("energy", results["energy"])):
        effs = [day_efficiency(d, figure) for d in scoreable]
        for w in WORKLOADS:
            series = [e[w] for e in effs]
            if not series or any(s is None for s in series):
                target[w] = None
                continue
            target[w] = summarize(series)
            if figure == "sampled":
                target[w]["direction_argmax"] = [direction_argmax(d, w) for d in scoreable]
    for d in scoreable:
        for w in WORKLOADS:
            for number in (1, 2):
                cell = d["data"][(number, w)]
                results["floors"][(d["day"], w, "desc" if cell["descending"] else "asc")] = measured_floor(cell["sweep"])
    if D < 3:
        for block in (results["workloads"], results["energy"]):
            for item in block.values():
                if item:
                    item.pop("outcome", None)
    return results


def report(r):
    print("Section 22, day-to-day stock repeatability | RTX 5060 Ti, N=1 chip")
    for d in r["days"]:
        print(f"Day {d.get('day')} ({d.get('date')}): {d['status']}")
        for p in d["problems"]:
            print(f"  - {p}")
        if d.get("runner_hash_match"):
            print(f"  filed runner matches its launch hash: {d['runner_hash_match']}")
        if "gate" in d:
            print("  return gate (median |pass 2 / pass 1 - 1| throughput): " + ", ".join(
                f"{w} {g['median_abs_pct']:.3f}% (max {g['max_abs_pct']:.3f}%)" for w, g in d["gate"].items()))
            print(f"  software power-cap reason seen at {d['power_cap_points']} of 160 points (reported, not a failure)")
    print(f"Scoreable days: {r['D']} of 5 -> {r['stage']}")
    for w in WORKLOADS:
        s = r["workloads"].get(w)
        if not s:
            print(f"{w}: no scoreable days")
            continue
        print(f"{w}: observed peak targets by day {s['argmax']}; peaks at a grid edge {s['edge_peaks']}; "
              f"regret at {REFERENCE} MHz by day " + ", ".join(f"{x:.3f}%" for x in s["regret"]))
        print(f"  peaks by direction, by day: {s['direction_argmax']}")
        print(f"  targets within {NEAR_OPTIMAL_PCT:g}% of the peak, by day: {s['near_optimal']}")
        if "regret_ci9875" in s:
            low, high = s["regret_ci9875"]
            sdl, sdh = s["regret_sd_ci95"]
            print(f"  mean regret {s['regret_mean']:.3f}% (98.75% interval {low:.3f} to {high:.3f}; "
                  f"range {min(s['regret']):.3f} to {max(s['regret']):.3f}), "
                  f"day SD {s['regret_sd']:.3f} pp (95% {sdl:.3f}-{sdh:.3f})"
                  + (f" -> {s['outcome']}" if "outcome" in s else " (descriptive: fewer than three days)"))
        print("  target  geomean eff  95% pointwise    range              log SD (95%)          "
              f"shape vs {REFERENCE}, % (95%; range)")
        for t in GRID:
            c = s["curve"][t]
            ci = f"{c['ci95'][0]:.5g}-{c['ci95'][1]:.5g}" if "ci95" in c else "-"
            lsd = (f"{c['log_sd']:.4f} ({c['log_sd_ci95'][0]:.4f}-{c['log_sd_ci95'][1]:.4f})"
                   if c.get("log_sd") is not None else "-")
            shape = (f"{c['shape_mean']:+.2f} ({c['shape_ci95'][0]:+.2f} to {c['shape_ci95'][1]:+.2f}; "
                     f"{c['shape_min']:+.2f} to {c['shape_max']:+.2f})" if "shape_ci95" in c
                     else f"{c['shape_mean']:+.2f}")
            print(f"  {t:6d}  {c['geomean']:.5g}  {ci:16s} {c['min']:.5g}-{c['max']:.5g}  {lsd:22s}  {shape}")
        if r["energy"].get(w) and "regret_mean" in r["energy"][w]:
            print(f"  energy-counter figure, secondary: mean regret {r['energy'][w]['regret_mean']:.3f}%, "
                  f"peaks {r['energy'][w]['argmax']}")
    floors = [(k, v) for k, v in sorted(r["floors"].items())]
    if floors:
        print("Measured VID floor, secondary and descriptive (day, workload, direction):")
        for (day, w, direction), f in floors:
            if f is None:
                print(f"  day {day} {w} {direction}: no complete voltage extract")
            else:
                print(f"  day {day} {w} {direction}: {f['floor_v']:.3f} V, last floor target {f['last_floor_target']}, "
                      f"first rise {f['first_rise_target']}"
                      + ("; RE-ENTERS the floor later: ambiguous" if f["reenters"] else "")
                      + ("" if f["starts_at_floor"] else "; the lowest target is not on the floor"))
    print("Days are repeated observations of one chip, not chips. Observed grid regret within this 20-target "
          "panel, not a physical optimum; a peak at a panel edge is unbracketed. Intervals are pointwise and "
          "assume independent, roughly normal day values. No ambient instrument was used.")


def to_json(r):
    """The results as plain JSON (keys stringified), for --json."""
    def plain(value):
        if isinstance(value, dict):
            return {(", ".join(map(str, k)) if isinstance(k, tuple) else str(k)): plain(v) for k, v in value.items()
                    if k != "data"}
        if isinstance(value, (list, tuple, set)):
            return [plain(v) for v in (sorted(value) if isinstance(value, set) else value)]
        return value
    return plain(r)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("days", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, help="also write every result, all 20 targets, as JSON here")
    args = parser.parse_args(argv)
    try:
        r = score(args.days)
    except (ValueError, OSError) as exc:
        print(f"Cannot score: {exc}", file=sys.stderr)
        return 2
    report(r)
    if args.json:
        args.json.write_text(json.dumps(to_json(r), indent=1) + "\n", encoding="utf-8")
        print(f"Wrote {args.json}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
