"""Synthetic section 20 decisions; no measurement files are read or written."""

import csv
import json
import tempfile
from pathlib import Path

from score_control10 import WORKLOADS
from score_session20 import GRIDS, score

FLOOR_INDEX = 9  # both registered grids put the floor end tenth


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def curve(peak=7, floor_loss=None, rises_above=False):
    """Efficiency per grid index: a gentle peak below the floor end, then a fall above it."""
    eff = [100 - 0.5 * abs(i - peak) for i in range(18)]
    if peak <= FLOOR_INDEX:
        for i in range(FLOOR_INDEX + 1, 18):
            eff[i] = eff[FLOOR_INDEX] - 3 * (i - FLOOR_INDEX)
    if floor_loss is not None:
        eff[FLOOR_INDEX] = max(eff) * (1 - floor_loss / 100)
    if rises_above:
        eff[17] = eff[FLOOR_INDEX] + 1
    return eff


def write_sweep(path, grid, eff, scale=1.0, mutate=None, volts=None):
    rows = [{"target_frequency_mhz": t, "bench_throughput": 100 * scale, "power_avg_w": 100 / e,
             "energy_avg_power_w": 105 / e, "bench_ok": "True", "lock_miss_direction": ""}
            for t, e in zip(grid, eff)]
    if mutate:
        mutate(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    if volts:
        with Path(str(path).replace("_sweep.csv", "_sweep_voltage.csv")).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("target", "voltage"))
            writer.writeheader()
            writer.writerows({"target": t, "voltage": v} for t, v in zip(grid, volts))


def fixture(root, shapes=None, scale_stock_desc=1.0, lost=(), mutate=None, section="REGISTERED-PREDICTIONS section 20 (2026-10-08)",
            volts=None):
    manifest = {"section": section, "sweeps": {}, "notScoreable": list(lost)}
    for config, grid in GRIDS.items():
        for d in ("asc", "desc"):
            for w in WORKLOADS:
                eff = ((shapes or {}).get(config) or {}).get(w) or curve()
                name = f"x_s20-{config}-{d}-{w}_sweep.csv"
                scale = scale_stock_desc if (config, d) == ("stock", "desc") else 1.0
                write_sweep(root / name, grid, eff, scale, mutate if (config, d, w) == ("stock", "asc", "copy") else None, volts)
                manifest["sweeps"][f"{config}-{d}-{w}"] = {"sweep": name}
    (root / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")


def evaluate(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        fixture(Path(tmp), **kwargs)
        return score(tmp)


def refused(name, **kwargs):
    try:
        evaluate(**kwargs)
        check(False, f"{name} is refused")
    except ValueError:
        check(True, f"{name} is refused")


def main():
    r = evaluate()
    check(all(v == "HOLDS" for v in r["verdicts"].values()), "a peak below the floor end, near-flat to it and falling above, holds F1-F3")
    check(r["results"]["stock"]["sampled"]["steps"]["gemm"] == -2, "the argmax distance is counted in grid steps from the floor end")

    # F1: three workloads peaking three steps above the floor end fail it; two are allowed.
    above = {w: curve(peak=12) for w in WORKLOADS[:3]}
    r = evaluate(shapes={"p4": above})
    check(r["verdicts"]["p4-f1"] == "FAILS" and r["verdicts"]["stock-f1"] == "HOLDS", "three peaks above the floor end fail F1 for that configuration only")
    r = evaluate(shapes={"p4": {w: curve(peak=12) for w in WORKLOADS[:2]}})
    check(r["verdicts"]["p4-f1"] == "HOLDS", "two peaks above the floor end are allowed")
    r = evaluate(shapes={"stock": {w: curve(peak=10) for w in WORKLOADS}})
    check(r["verdicts"]["stock-f1"] == "HOLDS", "a peak one step above the floor end still counts as at or below it")

    # F2: the median loss at the floor end decides, at 3%.
    r = evaluate(shapes={"stock": {w: curve(floor_loss=4.0) for w in WORKLOADS}})
    check(r["verdicts"]["stock-f2"] == "FAILS", "a 4% median loss at the floor end fails F2")
    r = evaluate(shapes={"stock": {w: curve(floor_loss=2.9) for w in WORKLOADS}})
    check(r["verdicts"]["stock-f2"] == "HOLDS", "a 2.9% median loss holds F2")

    # F3: efficiency 300 MHz above the floor end must be lower, in all but two.
    r = evaluate(shapes={"stock": {w: curve(rises_above=True) for w in WORKLOADS[:3]}})
    check(r["verdicts"]["stock-f3"] == "FAILS", "three workloads more efficient 300 MHz above the floor end fail F3")

    # Gate: a 3% slower descending stock suite voids every prediction.
    r = evaluate(scale_stock_desc=0.97)
    check(all(v == "NOT_SCOREABLE" for v in r["verdicts"].values()), "a 3% stock change between directions voids everything")
    r = evaluate(scale_stock_desc=0.99)
    check(r["verdicts"]["stock-f1"] == "HOLDS", "a 1% stock change is inside the 1.5% gate")

    # Lost roles: fewer than 11 usable workloads voids that configuration only.
    r = evaluate(lost=("p4-asc-gemm", "p4-desc-conv"))
    check(r["verdicts"]["p4-f1"] == "NOT_SCOREABLE" and r["verdicts"]["stock-f1"] == "HOLDS", "two lost P4 workloads void P4 only")
    r = evaluate(lost=("p4-asc-gemm",))
    check(r["verdicts"]["p4-f1"] == "HOLDS" and r["results"]["p4"]["sampled"]["usable"] == 11, "one lost workload leaves 11 usable")

    # The energy figure is reported beside the registered one, not scored.
    r = evaluate()
    check(r["results"]["stock"]["energy"]["argmax"] == r["results"]["stock"]["sampled"]["argmax"], "a uniform energy offset gives the same argmaxes")

    # Measured floor end: last target at the lowest code before the first rise.
    volts = [0.720] * 10 + [0.725 + 0.005 * i for i in range(8)]
    r = evaluate(volts=volts)
    check(r["results"]["stock"]["measured_floor_end"]["median"] == 1575, "the measured floor end is read from the voltage extract")

    # Malformed input is refused.
    refused("a fractional target", mutate=lambda rows: rows[0].update(target_frequency_mhz="1237.9"))
    refused("a target off the registered grid", mutate=lambda rows: rows[0].update(target_frequency_mhz="1245"))
    refused("a repeated target", mutate=lambda rows: rows[1].update(target_frequency_mhz="1237"))
    refused("a non-finite throughput", mutate=lambda rows: rows[3].update(bench_throughput="nan"))
    refused("a section 19 manifest", section="REGISTERED-PREDICTIONS sections 18 and 19 (2026-10-07)")

    # GPT Job 69's boundary defects, fixed 2026-10-08 after section 20 was scored (no verdict moved).
    from score_session20 import efficiency, sweep_path, tests
    grid = GRIDS["stock"]
    exact = {t: 90.0 for t in grid}
    exact[1500], exact[1575] = 100.0, 97.0
    check(tests({"w": exact}, grid, 1575)["f2"], "a loss of exactly 3% holds F2 despite float rounding")
    tied = {t: 90.0 for t in reversed(grid)}
    tied[1687] = tied[1575] = 100.0
    check(tests({"w": tied}, grid, 1575)["argmax"]["w"] == 1575, "an exact tie goes to the lowest target, whatever the row order")
    point = {"throughput": 100.0, "sampled": 50.0, "energy": 0.0}
    check(efficiency({1575: point}, {1575: point}, "energy") is None and efficiency({1575: point}, {1575: point}, "sampled") == {1575: 2.0},
          "a zero optional energy figure is unavailable, not a crash")
    check(sweep_path(Path("."), {"sweeps": {"x": []}}, "x") is None, "an empty retry history reads as a missing role")


if __name__ == "__main__":
    main()
