"""Score REGISTERED-PREDICTIONS section 20b: does energy or power polling change the counter's reported power?

Usage: python analysis/score_section20b.py SESSION_DIR [SESSION_DIR ...]

Each SESSION_DIR is a core session written by tools/section20b/run_core_session.py (schedule.json,
windows.jsonl, status.json, the readers' CSVs, and driver-events.json from the session runner). The
design is GPT Job 71's (docs/submission/drafts/section20b-registration-draft.md); its constants live
in tools/section20b/design.py, shared with the controller.

Per window: p = (E_end - E_start) / 1000 / T in W, e = joules per work unit, and wall throughput W/T,
where T is the difference of the two energy-call midpoints. Within each cell and row, against that
row's own A: d_E, d_P, d_EP as percentage changes of p, and the interaction d_I = 100 (p_EP - p_E - p_P
+ p_A) / p_A. Rows are averaged within a cell, cells equally across the nine. Those four SESSION
contrasts are the analysis units; windows are not independent replicates.

A session is VALID only if every scheduled window ran in order, completely, with valid endpoints,
its arm's reader running through both endpoints, every requested call succeeding, A making no power
or energy call, the E/P/EP cadence within its tolerance, both boundary clock witnesses within
tolerance, no forbidden process before or after any row, no display-driver event, and a clean finish.
A valid session is NOT SCOREABLE if, in any cell, A's last visit differs from its first by more than
1.5% in wall throughput. Pilot sessions size the confirmation (smallest S in 8-32 meeting the 1 pp
rule, or none); confirmation sessions get Bonferroni 98.75% intervals against the +/-2 pp band.

N=1 RTX 5060 Ti. Repeated sessions are repeated observations of one chip.
"""
import datetime
import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "section20b"))
import design  # noqa: E402
import validate  # noqa: E402
from validate import window_metrics  # noqa: E402

# ---- statistics, without scipy (CI does not install it) ---------------------------------------

def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def _betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    tail = 0.5 * _betainc(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t >= 0 else tail


def t_quantile(p, df):
    """Student t quantile by bisection on the CDF; p in (0.5, 1)."""
    lo, hi = 0.0, 1.0
    while t_cdf(hi, df) < p:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def critical_t(sessions):
    return t_quantile(1.0 - design.FAMILY_ALPHA / (2 * len(design.CONTRASTS)), sessions - 1)


def confirmation_size(s_max, bounds=design.SIZING_RANGE):
    """Smallest S in the approved range with t(1-0.05/8, S-1) * 1.5 s_max / sqrt(S) <= 1 pp, or None."""
    for s in range(bounds[0], bounds[1] + 1):
        if critical_t(s) * design.SIZING_ALLOWANCE * s_max / math.sqrt(s) <= design.SIZING_HALF_WIDTH_PP:
            return s
    return None


def classify(low, high, band=design.BAND_PP):
    """The registered interval rule. Touching a boundary is inconclusive."""
    if low > band:
        return "MATERIAL INCREASE"
    if high < -band:
        return "MATERIAL DECREASE"
    if low > -band and high < band:
        return "PRACTICALLY EQUIVALENT"
    return "INCONCLUSIVE"


def interval(values):
    n = len(values)
    mean = statistics.fmean(values)
    half = critical_t(n) * statistics.stdev(values) / math.sqrt(n)
    return mean, mean - half, mean + half


def nearest_rank(sorted_values, q):
    return sorted_values[max(0, math.ceil(q * len(sorted_values)) - 1)]


# ---- one session -----------------------------------------------------------------------------

def contrasts(by_key, value="p"):
    """Per cell/row contrasts against that row's A, averaged over rows then over the nine cells."""
    per_cell = {}
    for cell in range(len(design.CELLS)):
        rows = []
        for row in design.WILLIAMS_ROWS:
            arms = {arm: by_key.get((row, cell, arm), {}).get(value) for arm in design.ARMS}
            if any(v is None for v in arms.values()):
                return None, None
            a = arms["A"]
            rows.append({"d_E": 100 * (arms["E"] / a - 1), "d_P": 100 * (arms["P"] / a - 1),
                         "d_EP": 100 * (arms["EP"] / a - 1),
                         "d_I": 100 * (arms["EP"] - arms["E"] - arms["P"] + a) / a})
        per_cell[cell] = {c: statistics.fmean(r[c] for r in rows) for c in design.CONTRASTS}
    session = {c: statistics.fmean(per_cell[cell][c] for cell in per_cell) for c in design.CONTRASTS}
    return session, per_cell


def return_gate(metrics):
    """A's last versus first chronological visit in each cell, wall throughput. Over 1.5% fails."""
    worst, changes = 0.0, {}
    for cell in range(len(design.CELLS)):
        visits = sorted((m for m in metrics if m["arm"] == "A" and m["cell"] == cell), key=lambda m: m["index"])
        if len(visits) < 2 or "throughput" not in visits[0] or "throughput" not in visits[-1]:
            return None, changes
        change = 100.0 * (visits[-1]["throughput"] / visits[0]["throughput"] - 1.0)
        changes[cell] = change
        worst = max(worst, abs(change))
    return worst, changes


def read_json(path):
    """Session JSON from Python or PowerShell 5.1, which writes a byte-order mark (GPT Job 73, F9)."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def session_problems(session_dir, plan, status, records):
    """Everything about the session as a whole that must hold before any window is scored."""
    problems = []
    index = plan.get("session_index")
    if plan.get("section") != "20b" or plan.get("kind") != "core":
        problems.append(f"not a section 20b core session ({plan.get('section')}, {plan.get('kind')})")
        return problems
    stage = plan.get("stage")
    allowed = design.PILOT_INDICES if stage == "pilot" else design.CONFIRMATION_INDICES if stage == "confirmation" else ()
    if index not in allowed:
        problems.append(f"session index {index} is not a {stage} index")
    elif plan.get("windows") != design.schedule(index):
        problems.append(f"the saved schedule is not design.schedule({index})")
    if plan.get("seed") != design.SEED_BASE + (index or 0):
        problems.append(f"seed {plan.get('seed')}")
    for key, want in (("washout_seconds", design.WASHOUT_SECONDS), ("preload_seconds", design.PRELOAD_SECONDS),
                      ("warmup_iterations", design.WARMUP_ITERATIONS)):
        if plan.get(key) != want:
            problems.append(f"{key} {plan.get(key)}, not {want}")
    if not (plan.get("provenance") or {}).get("commit") or not plan.get("started_local_date"):
        problems.append("no recorded commit or start date")
    keys = ("index", "row", "cell", "arm", "position", "workload", "target_mhz", "iterations")
    expected = plan.get("windows") or []
    if len(records) != len(expected):
        problems.append(f"{len(records)} of {len(expected)} windows recorded")
    for rec, want in zip(records, expected):
        if any(rec.get(k) != want.get(k) for k in keys):
            problems.append(f"window {rec.get('index')} does not match the schedule (expected {want['index']} "
                            f"{want['arm']} cell {want['cell']} row {want['row']})")
            break
    seen = [(r.get("row"), r.get("cell"), r.get("arm")) for r in records]
    if len(seen) != len(set(seen)):
        problems.append("a row/cell/arm window appears more than once")
    if status.get("preflight_problems") != []:
        problems.append(f"preflight: {status.get('preflight_problems')}")
    # The raw evidence, not only the controller's cached verdicts on it (GPT Job 91, F4): the preflight
    # readings against the controller's own rules, the watcher's stop record, and exactly one background
    # check before and after each row visit, so a failed record cannot be overwritten by a clean one.
    preflight = status.get("preflight") if isinstance(status.get("preflight"), dict) else {}
    gpu = preflight.get("gpu") if isinstance(preflight.get("gpu"), dict) else {}
    try:
        if (gpu.get("driver_version") != "616.92"
                or abs(float(gpu.get("power.limit")) - validate.STOCK_POWER_LIMIT_W) > 0.5
                or float(gpu.get("utilization.gpu")) >= 10
                or float(gpu.get("utilization.encoder")) != 0 or float(gpu.get("utilization.decoder")) != 0):
            problems.append(f"the recorded preflight readings fail the controller's rules: {gpu}"[:300])
    except (TypeError, ValueError):
        problems.append("the recorded preflight readings are missing or unreadable")
    pre_bg = preflight.get("background") if isinstance(preflight.get("background"), dict) else {}
    if (pre_bg.get("inventory_ok") is not True or pre_bg.get("forbidden") or pre_bg.get("pollers")
            or pre_bg.get("claude_visible_windows") != 0):
        problems.append("the recorded preflight background check did not pass")
    watcher = status.get("watcher_cleanup")
    if not isinstance(watcher, dict) or watcher.get("exit_code") != 0 or watcher.get("reaped") is not True \
            or watcher.get("errors"):
        problems.append(f"the driver-event watcher was not stopped cleanly: {watcher!r}"[:300])
    keys = [(b.get("when"), b.get("row_visit")) for b in status.get("background", []) if isinstance(b, dict)]
    wanted = {(when, visit) for visit in range(len(design.WILLIAMS_ROWS)) for when in ("before", "after")}
    if len(keys) != len(set(keys)) or set(keys) != wanted:
        problems.append("the background checks are not exactly one before and one after each row visit")
    if not status.get("complete") or status.get("exit_code") != 0:
        problems.append(f"the controller did not finish cleanly: {status.get('failure')}")
    if status.get("reset_exit") != 0 or status.get("cleanup_failure"):
        problems.append(f"the clock reset did not succeed: {status.get('cleanup_failure') or status.get('reset_exit')}")
    # The readback itself, not only the controller's verdict on it (GPT Job 76, R1).
    if not validate.reset_witness_complete(status.get("after_reset")):
        problems.append(f"no complete numeric readback after the reset: {status.get('after_reset')!r}"[:300])
    ledger = {(b.get("when"), b.get("row_visit")): b for b in status.get("background", [])}
    for visit in range(len(design.WILLIAMS_ROWS)):
        for when in ("before", "after"):
            bg = ledger.get((when, visit))
            if bg is None:
                problems.append(f"no background check {when} row visit {visit}")
            elif not isinstance(bg.get("forbidden"), list) or not isinstance(bg.get("pollers"), list) \
                    or not isinstance(bg.get("claude_visible_windows"), int) or isinstance(bg.get("claude_visible_windows"), bool):
                problems.append(f"background {when} row visit {visit} lacks a forbidden, poller or Claude-window decision")
            elif not bg.get("inventory_ok") or bg.get("forbidden") or bg.get("pollers") or bg.get("claude_visible_windows"):
                problems.append(f"background {when} row visit {visit}: inventory_ok {bg.get('inventory_ok')}, "
                                f"forbidden {bg.get('forbidden')}, pollers {bg.get('pollers')}, "
                                f"Claude windows {bg.get('claude_visible_windows')}")
    for name in ("driver-events.json", "runner-cleanup.json"):
        try:
            content = read_json(session_dir / name)
        except (OSError, ValueError) as exc:
            problems.append(f"{name} missing or unreadable ({type(exc).__name__})")
            continue
        if name == "driver-events.json":
            if not isinstance(content, dict) or content.get("query_ok") is not True or content.get("count") != 0 \
                    or isinstance(content.get("count"), bool):
                problems.append(f"{name} does not show a clean session: {content!r}"[:300])
        else:
            # Every restoration field, not the cached ok alone (GPT Job 76, R1).
            bad = validate.runner_cleanup_problems(content)
            if bad:
                problems.append(f"{name} does not show the card back on stock: {'; '.join(bad)}")
    return problems


def score_session(session_dir):
    session_dir = Path(session_dir)
    try:
        plan = read_json(session_dir / "schedule.json")
        status = read_json(session_dir / "status.json") if (session_dir / "status.json").exists() else {}
        lines = (session_dir / "windows.jsonl").read_text(encoding="utf-8-sig").splitlines() \
            if (session_dir / "windows.jsonl").exists() else []
        records = [json.loads(l) for l in lines if l.strip()]
    except (OSError, ValueError) as exc:
        return {"dir": str(session_dir.resolve()), "session_index": None, "stage": None, "date": None,
                "valid": False, "scoreable": False,
                "problems": [f"unreadable session files ({type(exc).__name__}: {exc})"],
                "contrasts": None, "per_cell": None, "energy_per_work": None, "throughput": None,
                "return_worst_pct": None, "return_changes": {}, "stale_max_s": 0.0, "positions": {}, "windows": 0}
    if not isinstance(plan, dict) or not isinstance(status, dict) or not all(isinstance(r, dict) for r in records) \
            or not isinstance(plan.get("provenance", {}), dict) or not isinstance(status.get("background", []), list) \
            or not all(isinstance(b, dict) for b in status.get("background", [])):
        return {"dir": str(session_dir.resolve()), "session_index": None, "stage": None, "date": None,
                "valid": False, "scoreable": False, "problems": ["session files are not the expected objects"],
                "contrasts": None, "per_cell": None, "energy_per_work": None, "throughput": None,
                "return_worst_pct": None, "return_changes": {}, "stale_max_s": 0.0, "positions": {}, "windows": 0}
    try:
        return _score_parsed(session_dir, plan, status, records)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError, ZeroDivisionError) as exc:
        # Malformed fields anywhere are reported as an invalid session, never a traceback that stops
        # every other session being scored (GPT Job 76, R6).
        return {"dir": str(session_dir.resolve()), "session_index": None, "stage": None, "date": None,
                "valid": False, "scoreable": False,
                "problems": [f"malformed session files ({type(exc).__name__}: {exc})"[:300]],
                "contrasts": None, "per_cell": None, "energy_per_work": None, "throughput": None,
                "return_worst_pct": None, "return_changes": {}, "stale_max_s": 0.0, "positions": {}, "windows": 0}


def _identity(value, kind):
    """A session index, stage or date usable as a key, else None (so it can be counted, never crash)."""
    if kind == "index":
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    return value if isinstance(value, str) else None


def _score_parsed(session_dir, plan, status, records):
    problems = session_problems(session_dir, plan, status, records)
    metrics = []
    for rec in records:
        m, p = window_metrics(rec, session_dir)
        metrics.append(m)
        problems += p
    by_key = {(m.get("row"), m.get("cell"), m.get("arm")): m for m in metrics}
    session, per_cell = contrasts(by_key, "p")
    energy, _ = contrasts(by_key, "e")
    throughput, _ = contrasts(by_key, "throughput")
    worst, changes = return_gate(metrics)
    valid = not problems and session is not None
    # Equality passes; the epsilon keeps an exact 1.5% from failing on float rounding (Job 69's lesson).
    scoreable = valid and worst is not None and worst <= design.RETURN_GATE_PCT + 1e-9
    stale = max((m.get("stale_max_s", 0.0) for m in metrics), default=0.0)
    # The draft's row-position summaries: each Williams position, all arms pooled, descriptive only.
    positions = {}
    for position in range(len(design.ARMS)):
        powers = [m["p"] for m in metrics if m.get("position") == position and "p" in m]
        rates = [m["throughput"] for m in metrics if m.get("position") == position and "throughput" in m]
        if powers:
            positions[position] = {"windows": len(powers), "mean_p_w": statistics.fmean(powers),
                                   "mean_throughput": statistics.fmean(rates)}
    return {"dir": str(session_dir.resolve()), "session_index": _identity(plan.get("session_index"), "index"),
            "stage": _identity(plan.get("stage"), "str"), "date": _identity(plan.get("started_local_date"), "str"),
            "valid": valid, "scoreable": scoreable, "problems": problems,
            "contrasts": session, "per_cell": per_cell, "energy_per_work": energy, "throughput": throughput,
            "return_worst_pct": worst, "return_changes": changes, "stale_max_s": stale, "positions": positions,
            "windows": len(records)}


def select_stage(results, stage, indices):
    """One scoreable session per planned index, under the draft's whole-session replacement limits:
    at most one replacement per planned session and two per stage, sessions on distinct days, and no
    directory counted twice. Returns (chosen, errors)."""
    errors = []
    submitted = [r for r in results if r["stage"] == stage]
    dirs = [r["dir"] for r in submitted]
    if len(dirs) != len(set(dirs)):
        errors.append("the same session directory was submitted twice")
    for r in submitted:
        try:
            r["_day"] = datetime.date.fromisoformat(r["date"])
        except (TypeError, ValueError):
            errors.append(f"session {r['session_index']} has no valid start date ({r['date']!r})")
            r["_day"] = None
    chosen, replacements = [], 0
    for index in indices:
        attempts = [r for r in submitted if r["session_index"] == index]
        replacements += max(0, len(attempts) - 1)
        if len(attempts) > 2:
            errors.append(f"session {index} has {len(attempts)} attempts; one replacement is allowed")
        good = [r for r in attempts if r["scoreable"]]
        if len(good) > 1:
            errors.append(f"session {index} has {len(good)} scoreable attempts")
        elif good:
            chosen.append(good[0])
            # A replacement follows a failed attempt and runs on a later day (GPT Job 75, R7).
            earlier = [r for r in attempts if r is not good[0]]
            if earlier and (good[0]["_day"] is None or any(r["_day"] is None or r["_day"] >= good[0]["_day"] for r in earlier)):
                errors.append(f"session {index}'s scoreable attempt is not on a later day than the attempt it replaces")
    if replacements > 2:
        errors.append(f"{replacements} replacement sessions in the {stage}; two are allowed")
    dates = [r["_day"] for r in chosen]
    if len(dates) != len(set(dates)):
        errors.append(f"{stage} sessions share a day: {sorted(map(str, dates))}")
    strays = sorted({r["session_index"] for r in submitted if r["session_index"] not in indices}, key=str)
    if strays:
        errors.append(f"{stage} sessions outside the plan: {strays}")
    return chosen, errors


def summarise(results, frozen_plan=None):
    """Pilot sizing from exactly four scoreable pilot sessions; confirmation intervals only from the full
    frozen set of S confirmation sessions (GPT Job 73, F8). Pilot sessions never enter confirmation."""
    out = {}
    pilot, errors = select_stage(results, "pilot", design.PILOT_INDICES)
    if errors:
        out["pilot"] = {"state": "NOT SCOREABLE", "errors": errors, "sessions": len(pilot)}
    elif len(pilot) == len(design.PILOT_INDICES):
        sds = {c: statistics.stdev([r["contrasts"][c] for r in pilot]) for c in design.CONTRASTS}
        s_max = max(sds.values())
        out["pilot"] = {"sessions": len(pilot), "sd": sds, "s_max": s_max, "S": confirmation_size(s_max)}
    else:
        out["pilot"] = {"sessions": len(pilot), "note": "four scoreable pilot sessions are needed to size confirmation"}
    if any(r["stage"] == "confirmation" for r in results):
        if frozen_plan is not None and not isinstance(frozen_plan, dict):
            out["confirmation"] = {"state": "NOT SCOREABLE", "errors": ["the frozen plan is not a JSON object"]}
            return out
        s = (frozen_plan or {}).get("S")
        if not isinstance(s, int) or not design.SIZING_RANGE[0] <= s <= design.SIZING_RANGE[1]:
            out["confirmation"] = {"state": "NOT SCOREABLE", "errors": [f"no frozen S in 8-32 ({s})"]}
            return out
        indices = design.CONFIRMATION_INDICES[:s]
        confirm, errors = select_stage(results, "confirmation", indices)
        pilot_dirs = {r["dir"] for r in results if r["stage"] == "pilot"}
        if pilot_dirs & {r["dir"] for r in confirm}:
            errors.append("a pilot session was submitted as confirmation")
        if errors or len(confirm) != s:
            out["confirmation"] = {"state": "NOT SCOREABLE" if errors else "INCOMPLETE", "errors": errors,
                                   "sessions": len(confirm), "planned": s}
            return out
        verdicts = {}
        for c in design.CONTRASTS:
            mean, low, high = interval([r["contrasts"][c] for r in confirm])
            verdicts[c] = {"mean": mean, "low": low, "high": high, "verdict": classify(low, high)}
        out["confirmation"] = {"sessions": s, "intervals": verdicts}
    return out


def report(results, summary):
    for r in results:
        state = "SCOREABLE" if r["scoreable"] else ("VALID but NOT SCOREABLE" if r["valid"] else "INVALID")
        print(f"== section 20b {r['stage']} session {r['session_index']} ({r['windows']} windows): {state} ==")
        for p in r["problems"][:20]:
            print(f"  problem: {p}")
        if len(r["problems"]) > 20:
            print(f"  ... and {len(r['problems']) - 20} more problems.")
        if r["return_worst_pct"] is not None:
            print(f"  Return gate: A's last against first visit, worst cell {r['return_worst_pct']:.3f}% "
                  f"(limit {design.RETURN_GATE_PCT}%).")
        if r["contrasts"]:
            print("  Session contrasts of counter-average power against A (pp): " +
                  ", ".join(f"{c} {r['contrasts'][c]:+.3f}" for c in design.CONTRASTS))
            print("  Energy per work unit (pp): " + ", ".join(f"{c} {r['energy_per_work'][c]:+.3f}" for c in design.CONTRASTS))
            print("  Wall throughput (pp): " + ", ".join(f"{c} {r['throughput'][c]:+.3f}" for c in design.CONTRASTS))
            for cell, values in r["per_cell"].items():
                w, t = design.CELLS[cell]
                print(f"    {w} {t} MHz: " + ", ".join(f"{c} {values[c]:+.2f}" for c in design.CONTRASTS))
        print(f"  Longest unchanged field timestamp inside a window: {r['stale_max_s']:.2f} s (reported, not gated).")
    pilot = summary.get("pilot", {})
    if "S" in pilot:
        s = pilot["S"]
        print(f"Pilot: four sessions, largest contrast SD {pilot['s_max']:.4f} pp; "
              + (f"confirmation needs S = {s} sessions." if s else
                 "no S from 8 to 32 meets the 1 pp rule, so the approved cap cannot deliver the planned precision."))
    elif pilot:
        print(f"Pilot: {pilot.get('sessions', 0)} scoreable sessions. "
              + (pilot.get("note") or f"{pilot.get('state')}: " + "; ".join(pilot.get("errors", []))))
    conf = summary.get("confirmation", {})
    if conf.get("state"):
        print(f"Confirmation: {conf['state']}. " + "; ".join(conf.get("errors", [])))
    for c, v in conf.get("intervals", {}).items():
        print(f"Confirmation {c}: mean {v['mean']:+.3f} pp, 98.75% interval {v['low']:+.3f} to {v['high']:+.3f}: {v['verdict']}.")
    print("Counter power is the card's own telemetry, not a shunt; nothing here says which reading is accurate. "
          "N=1 chip; sessions are repeated observations of it.")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sessions", nargs="+", type=Path)
    parser.add_argument("--frozen-plan", type=Path,
                        help="JSON holding the confirmation stage's frozen S, committed before confirmation began")
    args = parser.parse_args(argv)
    try:
        frozen_plan = read_json(args.frozen_plan) if args.frozen_plan else None
    except (OSError, ValueError) as exc:
        print(f"The frozen plan {args.frozen_plan} could not be read ({type(exc).__name__}: {exc}). Nothing scored.")
        return 1
    results = [score_session(d) for d in args.sessions]
    summary = summarise(results, frozen_plan)
    report(results, summary)
    # 0 when every session given is scoreable and no stage is refused; 1 otherwise. Reported, not hidden.
    refused = any(isinstance(v, dict) and v.get("state") for v in summary.values())
    return 0 if all(r["scoreable"] for r in results) and not refused else 1


if __name__ == "__main__":
    sys.exit(main())
