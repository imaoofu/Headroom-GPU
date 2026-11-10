"""Synthetic section 21 decisions; no measurement files are read or written."""

import json
import tempfile
from pathlib import Path

from score_session20 import GRIDS
from score_session21 import COARSE, WORKLOADS, score
from test_score_session20 import curve, write_sweep

COARSE_PEAK = 2  # 1545 MHz


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def coarse_curve(peak=COARSE_PEAK):
    return [100 - 2.0 * abs(i - peak) for i in range(len(COARSE))]


def fixture(root, fine=None, coarse=None, scale=None, lost=(), skip=(),
            section="REGISTERED-PREDICTIONS section 21 (2026-10-09)"):
    """fine[config][workload] and coarse[workload] are efficiency lists; scale[(config, grid, dir)]
    multiplies throughput; skip lists roles left out of the manifest."""
    manifest = {"section": section, "sweeps": {}, "notScoreable": list(lost)}
    grids = {("stock", "fine"): GRIDS["stock"], ("p4", "fine"): GRIDS["p4"], ("stock", "coarse"): COARSE}
    for (config, grid_name), grid in grids.items():
        for d in ("asc", "desc"):
            for w in WORKLOADS:
                role = f"{config}-{grid_name}-{d}-{w}"
                if role in skip:
                    continue
                if grid_name == "coarse":
                    eff = (coarse or {}).get(w) or coarse_curve()
                else:
                    eff = ((fine or {}).get(config) or {}).get(w) or curve()
                name = f"x_s21-{role}_sweep.csv"
                write_sweep(root / name, grid, eff, (scale or {}).get((config, grid_name, d), 1.0))
                manifest["sweeps"][role] = {"sweep": name}
    (root / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")


def evaluate(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        fixture(Path(tmp), **kwargs)
        return score(tmp)


def main():
    r = evaluate()
    check(set(r["verdicts"].values()) == {"HOLDS"}, "peaks below the floor end and at 1545 hold A1-A4")
    check(r["results"]["stock-coarse"]["sampled"]["at_suite_optimum"] == 4, "coarse argmaxes are reported against 1545")

    one = evaluate(fine={"stock": {"hotspot": curve(peak=14)}})
    check(one["verdicts"]["stock-A1"] == "HOLDS" and one["results"]["stock"]["sampled"]["f1_count"] == 3,
          "one fine peak above the floor end is the one allowed miss")
    two = evaluate(fine={"stock": {"hotspot": curve(peak=14), "kmeans": curve(peak=14)}})
    check(two["verdicts"]["stock-A1"] == "FAILS", "two of four above the floor end fail A1")

    lost = evaluate(lost=["p4-fine-desc-alexnet"], fine={"p4": {"hotspot": curve(peak=14)}})
    check(lost["unusable"]["p4"] == ["alexnet"], "a NOT SCOREABLE role makes its workload unusable")
    check(lost["verdicts"]["p4-A1"] == "FAILS", "with three usable, no miss is allowed")
    gone = evaluate(skip=("p4-fine-asc-alexnet", "p4-fine-asc-resnet50"))
    check(gone["verdicts"]["p4-A1"] == "NOT_SCOREABLE", "fewer than three usable workloads is NOT SCOREABLE")
    check(gone["verdicts"]["stock-A1"] == "HOLDS", "one configuration's loss does not void the other")

    loss = evaluate(fine={"stock": {w: curve(floor_loss=3.5) for w in WORKLOADS}})
    check(loss["verdicts"]["stock-A2"] == "FAILS", "a 3.5% median loss at the floor end fails A2")
    rises = evaluate(fine={"p4": {"kmeans": curve(rises_above=True), "hotspot": curve(rises_above=True)}})
    check(rises["verdicts"]["p4-A3"] == "FAILS", "efficiency rising above the floor end in two of four fails A3")

    drift = evaluate(scale={("stock", "fine", "desc"): 1.02})
    check(all(drift["verdicts"][f"{c}-{t}"] == "NOT_SCOREABLE" for c in ("stock", "p4") for t in ("A1", "A2", "A3"))
          and drift["verdicts"]["stock-A4"] == "HOLDS", "a 2% stock fine drift voids A1-A3 but not A4")
    cdrift = evaluate(scale={("stock", "coarse", "desc"): 1.02})
    check(cdrift["verdicts"]["stock-A4"] == "NOT_SCOREABLE" and cdrift["verdicts"]["stock-A1"] == "HOLDS",
          "a 2% stock coarse drift voids A4 only")

    high = evaluate(coarse={"alexnet": coarse_curve(4), "resnet50": coarse_curve(4)})
    check(high["verdicts"]["stock-A4"] == "FAILS", "two coarse peaks at 1852 MHz fail A4")
    edge = evaluate(coarse={"alexnet": coarse_curve(3)})
    check(edge["verdicts"]["stock-A4"] == "HOLDS" and edge["results"]["stock-coarse"]["sampled"]["within"] == 4,
          "a coarse peak at exactly 1702 MHz counts as within the bound")

    try:
        evaluate(section="REGISTERED-PREDICTIONS section 20 (2026-10-08)")
        check(False, "a section 20 manifest is refused")
    except ValueError:
        check(True, "a section 20 manifest is refused")
    print("All section 21 scorer checks passed.")


if __name__ == "__main__":
    main()
