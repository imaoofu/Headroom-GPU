"""Synthetic checks for the registered activity A/B scorer. No measurement file is read or written.

Added 2026-09-22 after the preflight review. The fixtures include the awkward cases on purpose -
achieved clocks that do not equal their targets, an exact 2 pct tie, a generator that failed -
because the Session D scorer's bug hid behind fixtures where everything was exact.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_activity_ab as S

TARGETS = [1380, 1410, 1440, 1470, 1507, 1537, 1567, 1597, 1627, 1665, 1695, 1725, 1755]
passed = 0


def check(message, condition):
    global passed
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    passed += 1
    print(f"[PASS] {message}")


def build(root, losses=None, warmupLoss=0.0, dropRun=None, noEvents=None, failedAction=None,
          wrongGrid=None, late=None):
    """losses: {tag: (fraction lost at one point, target)}; every run otherwise identical."""
    losses = losses or {}
    records, t0 = [], 1_800_000_000.0
    for order, cond in enumerate(S.REGISTERED_ORDER):
        tag = f"w{order}" if cond == "warmup" else f"{order - 1:02d}-{cond}"
        label = f"5060ti-actab-{tag}"
        d = os.path.join(root, f"run_{label}")
        os.makedirs(d)
        grid = TARGETS[:-1] if tag == wrongGrid else TARGETS
        rows, start = [], t0 + order * 400
        for i, target in enumerate(grid):
            tp = 1e13 * (1 + i * 0.03)
            frac, at = losses.get(tag, (0.0, None))
            if at == target:
                tp *= (1 - frac)
            if cond == "warmup" and i == 3:
                tp *= (1 - warmupLoss)
            rows.append(f"{target},{target - 7.5},{tp!r},{start + i * 20},{start + i * 20 + 12},45.0")
        csv = os.path.join(d, f"20260923-000000_{label}_sweep.csv")
        with open(csv, "w", encoding="utf-8") as f:
            f.write("target_frequency_mhz,achieved_frequency_avg,bench_throughput,window_start_unix,"
                    "window_end_unix,temperature_avg_c\n" + "\n".join(rows) + "\n")
        events = None
        if cond == "active" and tag != noEvents:
            events = os.path.join(root, f"{tag}-events.csv")
            genStart = start + (60 if tag == late else -2)
            lines = ["event,start_unix,end_unix,ok", f"generator_start,{genStart},{genStart},1"]
            t = genStart
            while t < start + len(grid) * 20 + 5:
                ok = 0 if (tag == failedAction and t > start + 100) else 1
                lines.append(f"pmon,{t},{t + 0.1},{ok}")
                t += 5
            lines.append(f"generator_stop_stop_file,{t},{t},1")
            with open(events, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        records.append({"order": order, "tag": tag, "label": label, "condition": cond,
                        "uptime_min_at_start": 40 + order * 7, "wrapper_exit": 1 if tag == dropRun else 0,
                        "load_seen": True, "event_log": events, "generator_exit": 0 if events else None,
                        "generator_killed": False, "sweep_csv": csv})
    with open(os.path.join(root, "experiment.json"), "w", encoding="utf-8") as f:
        json.dump(records, f)


def run(**kwargs):
    with tempfile.TemporaryDirectory() as root:
        build(root, **kwargs)
        return S.evaluate(root)


ACTIVE_TAGS = ["02-active", "03-active", "06-active", "07-active"]

code, _ = run()
check("identical runs with no losses give NOT_SUPPORTED", code == "NOT_SUPPORTED")

code, lines = run(losses={t: (0.09, 1597) for t in ACTIVE_TAGS})
check("four 9 pct losses in four active runs, none silent, give SUPPORTED", code == "SUPPORTED")

code, _ = run(losses={t: (0.02, 1597) for t in ACTIVE_TAGS})
check("an EXACT 2 pct loss is not degraded, so four ties give NOT_SUPPORTED", code == "NOT_SUPPORTED")

code, _ = run(losses={t: (0.0201, 1597) for t in ACTIVE_TAGS})
check("2.01 pct losses are degraded and give SUPPORTED", code == "SUPPORTED")

code, lines = run(losses={t: (0.09, 1597) for t in ACTIVE_TAGS}, dropRun="02-active")
check("a failed active run gives INCOMPLETE and no VERDICT line",
      code == "INCOMPLETE" and not any(l.startswith("VERDICT") for l in lines))

code, lines = run(losses={t: (0.09, 1597) for t in ACTIVE_TAGS}, noEvents="03-active")
check("an active run without an event log gives INCOMPLETE",
      code == "INCOMPLETE" and any("no generator event log" in l for l in lines))

code, lines = run(failedAction="06-active")
check("failed generator actions make the run invalid",
      code == "INCOMPLETE" and any("action(s) failed" in l for l in lines))

code, lines = run(late="07-active")
check("a generator that started after the first window makes the run invalid",
      code == "INCOMPLETE" and any("started after" in l for l in lines))

code, lines = run(wrongGrid="01-silent")
check("a run without the registered 13-point grid gives INCOMPLETE",
      code == "INCOMPLETE" and any("not 13" in l for l in lines))

code, _ = run(warmupLoss=0.10)
check("losses in the excluded warm-ups do not count", code == "NOT_SUPPORTED")

code, lines = run(losses={"01-silent": (0.09, 1597), "04-silent": (0.09, 1627), "05-silent": (0.09, 1440)})
check("three silent losses report the other-cause line",
      any(l.startswith("ALSO: 3 losses in SILENT") for l in lines))

code, lines = run(losses={"09-silent": (0.09, 1597)})
blockLine = [l for l in lines if l.startswith("Degraded points by block")][0]
check("blocks follow recorded order: a loss in silent run 09 (order 10) lands in block 3", "3: 1" in blockLine)

print(f"{passed} checks passed.")
