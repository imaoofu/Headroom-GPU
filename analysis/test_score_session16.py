"""Synthetic section 16 decisions (P5 -> P4 -> P2 -> P5); no measurement files are written or edited."""

import csv
import json
import tempfile
from pathlib import Path

from score_session16 import LEGS, score
from score_control10 import WORKLOADS

TARGETS = [1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090]


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def write_sweep(path, peak, scale=1.0, achieved_offset=-0.4):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "target_frequency_mhz", "achieved_frequency_avg", "bench_throughput",
            "power_avg_w", "bench_ok", "lock_miss_direction", "power_window_applied"))
        writer.writeheader()
        for target in TARGETS:
            writer.writerow({"target_frequency_mhz": target,
                             "achieved_frequency_avg": target + achieved_offset,
                             "bench_throughput": (2.0 if target == peak else 1.0) * 100 * scale,
                             "power_avg_w": 100, "bench_ok": "True",
                             "lock_miss_direction": "none", "power_window_applied": "True"})


def fixture(root, peaks=None, factor=None, retry=None, lost=(), section="REGISTERED-PREDICTIONS section 16 (2026-10-06)",
            mutate=None, clip=None):
    """peaks[leg][workload] -> best-efficiency target (P5/P2 default 1545, P4 default 2010).
    Achieved clocks sit 0.4 MHz below target (P4: 37 MHz below) so a target/achieved mix-up shows."""
    manifest = {"section": section, "sweeps": {}, "notScoreable": list(lost)}
    for leg, label in LEGS.items():
        for workload in WORKLOADS:
            default = 2010 if leg == "p4" else 1545
            peak = ((peaks or {}).get(leg) or {}).get(workload, default)
            name = f"20261006-000000_s16-{label}-{workload}_sweep.csv"
            write_sweep(root / name, peak, (factor or {}).get(leg, 1.0), -37.0 if leg == "p4" else -0.4)
            entry = {"sweep": name}
            if retry and (leg, workload) in retry:
                first = f"20261006-000000_s16-{label}-{workload}-first_sweep.csv"
                write_sweep(root / first, 3090)
                entry = [{"sweep": first}, entry]
            manifest["sweeps"][f"{label}-{workload}"] = entry
    for path in sorted(root.glob("*_sweep.csv")):
        if mutate is None and clip is None:
            break
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        fields = list(rows[0])
        if mutate is not None and "-p5b-" in path.name:
            mutate(rows)
        if clip is not None and f"{LEGS[clip[0]]}-{clip[1]}_" in path.name:
            rows = rows[:-1]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    (root / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")


def evaluate(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        fixture(Path(tmp), **kwargs)
        return score(tmp)


def main():
    r = evaluate()
    check(r["control"] == "HOLDS" and r["p4_primary"] == "HOLDS" and r["p4_secondary"] == "HOLDS",
          "the pictured outcome holds on all three predictions")
    check(r["medians"]["p4"] == 2010, "the P4 median is read on the target grid, not the achieved clock")

    # Five of twelve P4 workloads stay at 1545: the median still lands on 2010 (7 of 12 there), but
    # only 7 lie above P5, so the secondary fails while the primary holds.
    stay = {w: 1545 for w in WORKLOADS[:5]}
    r = evaluate(peaks={"p4": stay})
    check(r["p4_primary"] == "HOLDS" and r["p4_secondary"] == "FAILS" and len(r["p4_above"]) == 7,
          "a median on 2010 with only 7 of 12 above P5 fails the secondary")

    # Exactly nine above passes; eight fails.
    r = evaluate(peaks={"p4": {w: 1545 for w in WORKLOADS[:3]}})
    check(r["p4_secondary"] == "HOLDS" and len(r["p4_above"]) == 9, "nine of twelve above is enough")
    r = evaluate(peaks={"p4": {w: 1545 for w in WORKLOADS[:4]}})
    check(r["p4_secondary"] == "FAILS" and len(r["p4_above"]) == 8, "eight of twelve above is not")

    # A six-six split puts the P4 median between grid points: not 2010.
    split = {w: (1852 if i < 6 else 2167) for i, w in enumerate(WORKLOADS)}
    r = evaluate(peaks={"p4": split})
    check(r["medians"]["p4"] == 2009.5 and r["p4_primary"] == "FAILS", "a median between grid points fails the primary")

    # Control: four P2 workloads move, median unmoved -> HOLDS, with the count reported.
    r = evaluate(peaks={"p2": {w: 1702 for w in WORKLOADS[:4]}})
    check(r["control"] == "HOLDS" and len(r["p2_moved"]) == 4, "a moved minority leaves the control holding, counted")
    r = evaluate(peaks={"p2": {w: 1702 for w in WORKLOADS[:7]}})
    check(r["control"] == "FAILS", "a moved majority fails the control")

    # P5 bracket: unequal medians or a slow return voids every prediction.
    r = evaluate(peaks={"p5b": {w: 1702 for w in WORKLOADS[:7]}})
    check(all(r[k] == "NOT_SCOREABLE" for k in ("control", "p4_primary", "p4_secondary")),
          "unequal P5 medians void every prediction")
    r = evaluate(factor={"p5b": 0.97})
    check(r["control"] == "NOT_SCOREABLE" and r["p4_primary"] == "NOT_SCOREABLE", "a 3% slow P5 return voids every prediction")
    r = evaluate(factor={"p5b": 0.99})
    check(r["control"] == "HOLDS", "a 1% P5 return is inside the 1.5% gate")

    # Desktop-load retries: the last descriptor is the accepted sweep.
    r = evaluate(retry={("p4", "gemm")})
    check(r["optima"]["p4"]["gemm"] == 2010, "a retried role is scored on its accepted (last) sweep")
    # A role NOT SCOREABLE after a second load voids only its own suite, unless it is a P5 suite.
    r = evaluate(lost=("5060ti-s16-p4-gemm",))
    check(r["p4_primary"] == "NOT_SCOREABLE" and r["control"] == "HOLDS", "a lost P4 role voids P4 only")
    r = evaluate(lost=("5060ti-ctrl10-p5b-copy",))
    check(r["control"] == "NOT_SCOREABLE" and r["p4_primary"] == "NOT_SCOREABLE", "a lost P5 role voids everything")

    # GPT Job 56's failure cases (F10-F13), each now handled.
    r = evaluate(factor={"p5b": 0.985})
    check(r["control"] == "HOLDS", "a return of exactly 1.5% passes: the registration fails only what exceeds it")
    for name, fn in (("a repeated target", lambda rows: rows[0].update(target_frequency_mhz="1395")),
                     ("a target off the registered grid", lambda rows: rows[0].update(target_frequency_mhz="1245")),
                     ("a non-finite throughput", lambda rows: rows[8].update(bench_throughput="nan"))):
        try:
            evaluate(mutate=fn)
            check(False, f"{name} is refused")
        except ValueError:
            check(True, f"{name} is refused")
    r = evaluate(lost=("5060ti-s16-p4-gemm",), clip=("p4", "gemm"))
    check(r["p4_primary"] == "NOT_SCOREABLE" and r["control"] == "HOLDS",
          "an incomplete suite already marked lost voids only itself; the control is still scored")

    try:
        evaluate(section="REGISTERED-PREDICTIONS section 15 (377e1be)")
        check(False, "a section 15 manifest is refused")
    except ValueError:
        check(True, "a section 15 manifest is refused")


if __name__ == "__main__":
    main()
