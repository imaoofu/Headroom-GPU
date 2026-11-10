"""Checks for score_new_card.py (REGISTERED-PREDICTIONS 11); no measurement files are written.

The floor classifier is first run on committed sweeps from three cards whose floors are already
known, so its definitions are checked against real readings, not only against fixtures.
"""

import csv
import json
import tempfile
from pathlib import Path

from import_bench_session import sha256
from score_new_card import WORKLOADS, classify_floor, grid_position, grid_value, main as score_main, rule_11a, score
from score_session_d import read_voltage

ROOT = Path(__file__).resolve().parents[1] / "data" / "frequency-sweeps"


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def real(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as handle:
        targets = [int(float(row["target"])) for row in csv.DictReader(handle)]
    return {t: r["voltage"] for t, r in read_voltage(ROOT / path, targets).items()}


DENSE = list(range(1236, 2500, 52))[:25]   # 25 points, like 40-80% of a 3090 MHz table
SUITE = [round(1236 + i * 154.5) for i in range(13)]


def dense_volts(floor_end, floor_v=0.720, dip_at=None):
    volts = {t: floor_v if t <= floor_end else round(floor_v + 0.005 * (1 + (t - floor_end) // 52), 3)
             for t in DENSE}
    if dip_at is not None:
        volts[DENSE[0]] = floor_v + 0.013   # voltage falls INTO the floor, as on the 2060 Super
    return volts


def write(root, label, targets, peak, volts=None, order=None, gpu="NVIDIA GeForce RTX 4060",
          power=("115.00", "115.00")):
    csv_path = root / f"20990101-000000_{label}_sweep.csv"
    meta = {"session_label": label, "gpu_name": gpu, "driver_version": "synthetic",
            "power_limit_enforced_w": power[0], "power_limit_default_w": power[1]}
    if order:
        meta["sweep_order"] = order
    csv_path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "target_frequency_mhz", "achieved_frequency_avg", "bench_throughput", "power_avg_w",
            "temperature_avg_c", "bench_ok", "lock_miss_direction", "power_window_applied"))
        writer.writeheader()
        for t in (sorted(targets, reverse=True) if order == "descending" else targets):
            writer.writerow({"target_frequency_mhz": t, "achieved_frequency_avg": t,
                             "bench_throughput": 200 if t == peak else 100, "power_avg_w": 100,
                             "temperature_avg_c": 60, "bench_ok": "True",
                             "lock_miss_direction": "none", "power_window_applied": "True"})
    with csv_path.with_name(csv_path.stem + "_voltage.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("target", "achieved", "voltage", "sampleCount"))
        writer.writeheader()
        for t in targets:
            writer.writerow({"target": t, "achieved": t, "voltage": (volts or {}).get(t, 0.8),
                             "sampleCount": 40})


def evaluate(asc_end=1652, desc_end=1652, peak=1700, peaks=None, dip=False, gpu="NVIDIA GeForce RTX 4060",
             power=("115.00", "115.00"), suite=SUITE):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        write(root, "newcard-dense-asc", DENSE, 0, dense_volts(asc_end, dip_at=dip or None), "ascending", gpu, power)
        write(root, "newcard-dense-des", DENSE, 0, dense_volts(desc_end), "descending", gpu, power)
        for name in WORKLOADS:
            write(root, f"newcard-suite-{name}", suite, (peaks or {}).get(name, peak), gpu=gpu, power=power)
        return score(root, require_import=False)


def mutated(change):
    """Score a valid fixture after change(root) edits its files; True when the scorer refuses it."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        write(root, "newcard-dense-asc", DENSE, 0, dense_volts(1652), "ascending")
        write(root, "newcard-dense-des", DENSE, 0, dense_volts(1652), "descending")
        for name in WORKLOADS:
            write(root, f"newcard-suite-{name}", SUITE, 1700)
        change(root)
        try:
            score(root, require_import=False)
        except ValueError:
            return True
        return False


def edit_rows(root, label, edit):
    path = next(root.glob(f"*_{label}_sweep.csv"))
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    rows = edit(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fixture(root, gpu="NVIDIA GeForce RTX 4060"):
    write(root, "newcard-dense-asc", DENSE, 0, dense_volts(1652), "ascending", gpu)
    write(root, "newcard-dense-des", DENSE, 0, dense_volts(1652), "descending", gpu)
    for name in WORKLOADS:
        write(root, f"newcard-suite-{name}", SUITE, 1700, gpu=gpu)


def manifest(root, status="PASS", uuid="GPU-test", gpu="NVIDIA GeForce RTX 4060", quiet="quiet"):
    """IMPORT.json as import_bench_session.py writes it, built by hand over a fixture."""
    plan = root / "bench-plan-test.json"
    plan.write_text('{"runs": []}', encoding="utf-8")
    session = root / "bench-session-test.json"
    session.write_text(json.dumps({"status": status, "gpuUuid": uuid, "gpuName": gpu,
                                   "planHash": sha256(plan)}), encoding="utf-8")
    files = {p.name: sha256(p) for p in root.iterdir() if p.name.endswith((".csv", ".json"))
             and not p.name.startswith("bench-")}
    joins = [{"csv": n, "voltage": n[:-4] + "_voltage.csv", "voltageSha256": files[n[:-4] + "_voltage.csv"]}
             for n in files if n.endswith("_sweep.csv")]
    data = {"schema": 1, "session": {"file": session.name, "sha256": sha256(session), "status": status,
                                     "gpuName": gpu, "gpuUuid": uuid,
                                     "plan": plan.name, "planSha256": sha256(plan)},
            "accepted": [{"key": "all/steps", "desktopLoad": {"status": quiet}, "joins": joins, "files": files}],
            "rejected": [{"key": "all/steps", "attempt": 1, "verdict": "FAIL"}]}
    (root / "IMPORT.json").write_text(json.dumps(data), encoding="utf-8")


def imported(change=lambda root: None, **kwargs):
    """Score a fixture through the import check; returns the result, or the refusal text."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture(root)
        manifest(root, **kwargs)
        change(root)
        try:
            return score(root)
        except ValueError as exc:
            return str(exc)


def raises(**kwargs):
    try:
        evaluate(**kwargs)
    except ValueError:
        return True
    return False


def main():
    # ------------------------------------------------ the classifier on committed real sweeps
    ti = classify_floor(real("5060ti-finefloor-20260918/20260918-202543_5060ti-finefloor-gemm-r2_sweep_voltage.csv"))
    check(ti[0] == "FLAT_FLOOR" and ti[1] == 1567 and ti[2] == 0.720,
          "the 5060 Ti's quiet fine sweep is a flat 0.720 V floor ending at 1567 MHz")
    s = classify_floor(real("rtx2060s-finefloor-20260915/20260915-160921_rtx2060s-finefloor-gemm_sweep_voltage.csv"))
    check(s[0] == "NON_MONOTONIC", "the 2060 Super's fine sweep is non-monotonic: the rule is undecidable")
    asc = classify_floor(real("rtx3070ti-sessiond-20260924/fine/finefloor-asc2-resume-20260924-202335/20260924-213132_rtx3070ti-sessiond-finefloor-asc2_sweep_voltage.csv"))
    desc = classify_floor(real("rtx3070ti-sessiond-20260924/fine/finefloor-desc2-resume-20260924-202335/20260924-213543_rtx3070ti-sessiond-finefloor-desc2_sweep_voltage.csv"))
    check(asc[:2] == ("FLAT_FLOOR", 1500) and desc[:2] == ("FLAT_FLOOR", 1500),
          "the 3070 Ti's up and down fine sweeps both end the floor at 1500 MHz")
    check((asc[2], desc[2]) == (0.812, 0.819), "... one voltage code apart, which 11b reports but does not score")

    # Edge cases the first mutation pass showed were unpinned (2026-09-25).
    check(classify_floor({1: 0.720, 2: 0.720, 3: 0.730, 4: 0.720, 5: 0.740})[0] == "NON_MONOTONIC",
          "a floor with a bump in the middle is not one floor")
    check(classify_floor({1: 0.720, 2: 0.730, 3: 0.740})[0] == "NOT_LOCATED",
          "a floor touching only the lowest point ends at or below the range and is not located")
    check(classify_floor({1: 0.720, 2: 0.722, 3: 0.720, 4: 0.730})[:2] == ("FLAT_FLOOR", 3),
          "a 0.722 V median between two codes still sits on the 0.720 V floor")

    # ------------------------------------------------ 11a and 11b on synthetic cards
    passed = evaluate()
    check(passed["rule"] == "PASS" and passed["direction"] == "AGREE",
          "optimum one grid point above a 1652 MHz floor end, inside half a step, passes")
    check(passed["regrets"] is not None and max(passed["regrets"].values()) == 0,
          "regret at the nearest grid point is reported and is zero when every optimum is there")
    below = evaluate(peak=1390)
    check(below["rule"] == "FAIL_BELOW" and max(below["regrets"].values()) == 50,
          "an optimum two steps below fails BELOW, with its regret reported beside it")
    check(evaluate(peak=2008)["rule"] == "FAIL_ABOVE", "an optimum well above fails ABOVE")
    check(evaluate(peak=1545)["rule"] == "FAIL_BELOW",
          "107 MHz below the floor end is more than half a 154.5 MHz step, and fails")
    split = evaluate(peaks={n: (1545 if i < 6 else 1700) for i, n in enumerate(WORKLOADS)})
    check(split["median"] == 1622.5 and split["rule"] == "PASS",
          "a 1545/1700 split has median 1622.5, 29.5 MHz from the floor end, and passes")
    check(evaluate(dip=True)["rule"] == "UNDECIDABLE",
          "voltage falling into the floor, as on the 2060 Super, is undecidable, not a failure")
    far = evaluate(asc_end=1652, desc_end=1860)
    check(far["direction"] == "DIFFER" and far["rule"] == "NOT_SCOREABLE",
          "floor ends four dense steps apart differ, and the rule is not scored")
    check(evaluate(asc_end=1652, desc_end=1704)["direction"] == "AGREE",
          "floor ends one dense step apart agree")
    check(evaluate(asc_end=2600, desc_end=2600)["rule"] == "NOT_SCOREABLE",
          "a floor running past 80% of the table top is not located")
    check(raises(power=("125.00", "115.00")), "a power limit above the card default is refused as not stock")
    # GPT Job 88, R1: invalid or incomplete observations are refused, never scored.
    check(not mutated(lambda root: None), "the unmutated fixture still scores")
    for label in ("newcard-dense-asc", "newcard-dense-des"):
        check(mutated(lambda root, l=label: edit_rows(root, l, lambda rows: [rows[0], rows[8], rows[9]])),
              f"{label}: three of 25 dense points is refused, not classified on a 234 MHz grid")
    check(mutated(lambda root: edit_rows(root, "newcard-dense-asc", lambda rows: rows[::-1])),
          "an 'ascending' sweep whose rows ran descending is refused")
    for column, value, what in (("bench_ok", "False", "a failed benchmark"),
                                ("power_window_applied", "False", "unwindowed telemetry"),
                                ("lock_miss_direction", "above", "a clock above its lock"),
                                ("power_avg_w", "0", "zero power"),
                                ("bench_throughput", "nan", "non-finite throughput")):
        check(mutated(lambda root, c=column, v=value: edit_rows(
                  root, "newcard-dense-des", lambda rows: [dict(r, **{c: v}) if i == 3 else r for i, r in enumerate(rows)])),
              f"one dense point with {what} is refused")
    check(mutated(lambda root: edit_rows(root, "newcard-suite-gemm",
                                         lambda rows: [dict(r, power_avg_w="0") if i == 2 else r for i, r in enumerate(rows)])),
          "a suite point with zero power is refused, not a ZeroDivisionError")
    # GPT Job 93, R1: a NaN suite power scored PASS with NaN regret. Every bad value, first row included.
    for column, value in (("power_avg_w", "nan"), ("power_avg_w", "inf"), ("power_avg_w", "-5"),
                          ("bench_throughput", "nan"), ("achieved_frequency_avg", "nan")):
        for index in (0, 6):
            check(mutated(lambda root, c=column, v=value, i=index: edit_rows(
                      root, "newcard-suite-copy", lambda rows: [dict(r, **{c: v}) if j == i else r for j, r in enumerate(rows)])),
                  f"a suite {column} of {value} at row {index} is refused, never scored")
    ti_card = evaluate(gpu="NVIDIA GeForce RTX 5060 Ti")
    check(ti_card["comparison"] is not None and ti_card["comparison"]["borrowed_grid_point"] == 1545,
          "an 8 GB 5060 Ti gets the 11c comparison, borrowing the 16 GB unit's 1571 MHz floor end")
    check(evaluate()["comparison"] is None, "any other card gets no 5060 Ti comparison")
    # Amendment of 2026-09-28: 11c covers any desktop GB206 card, the RTX 5060 included.
    plain = evaluate(gpu="NVIDIA GeForce RTX 5060")
    check(plain["comparison"] is not None and "cut-down" in plain["comparison"]["variant"]
          and plain["comparison"]["borrowed_grid_point"] == 1545,
          "an RTX 5060 gets the 11c comparison, labelled as a cut-down GB206")
    check("same GB206" in ti_card["comparison"]["variant"], "a 5060 Ti is labelled as the same configuration")
    for other in ("NVIDIA GeForce RTX 5060 Laptop GPU", "NVIDIA GeForce RTX 5070", "NVIDIA GeForce RTX 4060 Ti"):
        check(evaluate(gpu=other)["comparison"] is None, f"{other} gets no GB206 comparison")

    # ------------------------------------------------ GPT Job 88, R4: only an imported session scores
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture(root)
        check(score_main([str(root)]) == 2, "the command line refuses a directory with no IMPORT.json")
    good = imported()
    check(isinstance(good, dict) and good["import"]["uuid"] == "GPU-test" and good["import"]["rejected"] == 1,
          "a directory whose files match IMPORT.json scores, reporting the UUID and rejected attempts")
    check("differs" in imported(lambda root: edit_rows(root, "newcard-suite-gemm",
                                                       lambda rows: [dict(rows[0], bench_throughput="101")] + rows[1:])),
          "a suite CSV edited after import is refused by its hash")
    check("differs" in imported(lambda root: next(root.glob("*newcard-dense-des_sweep_voltage.csv")).write_text("target" + chr(10))),
          "a voltage extract replaced after import is refused by its hash")
    check("not an accepted file" in imported(lambda root: (root / "IMPORT.json").write_text(
              (root / "IMPORT.json").read_text().replace("newcard-dense-asc_sweep.csv", "renamed.csv"))),
          "a scored CSV that IMPORT.json does not list is refused")
    check("plan" in imported(lambda root: (root / "bench-plan-test.json").write_text("{}")),
          "a copied plan changed after import is refused (GPT Job 89, I4)")
    import score_new_card as scorer_module
    calls = []
    real_read, real_verify = scorer_module.read_metadata, scorer_module.verify_import
    scorer_module.read_metadata = lambda path: (calls.append("read"), real_read(path))[1]
    scorer_module.verify_import = lambda *a, **k: (calls.append("verify"), real_verify(*a, **k))[1]
    try:
        ordered = imported()
    finally:
        scorer_module.read_metadata, scorer_module.verify_import = real_read, real_verify
    check(isinstance(ordered, dict) and calls and calls[0] == "verify",
          "no metadata is read before the import is verified (GPT Job 89, I3)")
    check("not quiet" in imported(quiet="DESKTOP LOAD"), "a step not checked quiet is refused")
    check("PASS session" in imported(status="FAIL"), "a session that did not finish PASS is refused")
    check("PASS session" in imported(uuid=""), "a session with no GPU UUID is refused")
    check("the bench session" in imported(gpu="NVIDIA GeForce RTX 4060 Ti"),
          "sweep metadata naming another GPU than the bench session is refused")

    # ------------------------------------------------ amendment of 2026-09-29: uneven suite grids
    # The sweep tool spaces its grid by INDEX into the clock table, so the grid can be uneven in
    # MHz. 11a's half step is now measured in grid steps (GPT Job 31 found the single median
    # spacing could misjudge it).
    uneven = [1000, 1100, 1300, 1600]
    check(grid_position(uneven, 1000) == 0 and grid_position(uneven, 1600) == 3
          and grid_position(uneven, 1200) == 1.5 and grid_position(uneven, 1450) == 2.5,
          "a grid position is the fractional index, linear between neighbouring points")
    check(all(abs(grid_value(uneven, grid_position(uneven, f)) - f) < 1e-9 for f in range(1000, 1601, 7)),
          "grid_value inverts grid_position across the grid")
    check(grid_value(uneven, -1) == 1000 and grid_value(uneven, 9) == 1600, "grid_value clamps to the ends")
    try:
        grid_position(uneven, 1700)
        outside = False
    except ValueError:
        outside = True
    check(outside, "a frequency outside the suite grid is refused rather than extrapolated")

    even = [1236 + 150 * i for i in range(13)]
    mismatches = 0
    medians = even + [a + 75 for a in even[:-1]]
    for f in range(even[0], even[-1] + 1, 7):
        for m in medians:
            old = "PASS" if abs(m - f) <= 75 else ("FAIL_BELOW" if m < f else "FAIL_ABOVE")
            if rule_11a(even, m, f)[0] != old:
                mismatches += 1
    check(mismatches == 0, "on an evenly spaced grid the grid-step rule equals |M - F| <= G/2 exactly")

    # A wide gap: 1500 -> 1800 in a grid whose median spacing is 100 MHz.
    wide = [1236, 1300, 1400, 1500, 1800, 1900, 2000, 2100, 2200, 2300, 2400, 2500, 2600]
    gap = evaluate(peak=1800, suite=wide)
    check(gap["rule"] == "PASS" and gap["median_spacing_reading"] == "FAIL_ABOVE",
          "an optimum 148 MHz above F, inside a 300 MHz grid interval, passes (a median spacing said FAIL)")
    check(evaluate(peak=1500, suite=wide)["rule"] == "FAIL_BELOW",
          "... while 152 MHz below, across the same interval, is just over half a step and fails")
    # A dense run: 20 MHz steps around F in a grid whose median spacing is 182 MHz.
    dense = [1236, 1400, 1600, 1620, 1640, 1660, 1680, 1800, 2000, 2200, 2400, 2600, 2800]
    run = evaluate(peak=1600, suite=dense)
    check(run["rule"] == "FAIL_BELOW" and run["median_spacing_reading"] == "PASS",
          "an optimum 2.6 grid steps below F fails although it is within half a median spacing")
    check(tuple(round(v, 6) for v in run["window"]) == (1642.0, 1662.0),
          "the pass window is reported in MHz, from the local steps")


if __name__ == "__main__":
    main()
