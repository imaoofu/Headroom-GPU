"""Synthetic section 19 decisions; no measurement files are read or written."""

import csv
import json
import tempfile
from pathlib import Path

from score_session19 import LEGS, PREDICTED, score
from score_control10 import WORKLOADS

TARGETS = [1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090]


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def write_sweep(path, peak_energy, peak_sampled, scale=1.0, drop=None):
    """Throughput is flat; each power figure dips at its own peak so the two optima can differ."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("target_frequency_mhz", "bench_throughput", "power_avg_w",
                                                    "energy_avg_power_w", "bench_ok"))
        writer.writeheader()
        for t in TARGETS:
            row = {"target_frequency_mhz": t, "bench_throughput": 100 * scale,
                   "power_avg_w": 50 if t == peak_sampled else 100,
                   "energy_avg_power_w": 50 if t == peak_energy else 100, "bench_ok": "True"}
            if drop == t:
                row["energy_avg_power_w"] = ""
            writer.writerow(row)


def fixture(root, energy=None, sampled=None, scale=None, lost=(), section="REGISTERED-PREDICTIONS sections 18 and 19 (2026-10-07)", drop=None,
            mutate=None, clip=None):
    manifest = {"section": section, "sweeps": {}, "notScoreable": list(lost)}
    for leg in LEGS:
        for w in WORKLOADS:
            pe = ((energy or {}).get(leg) or {}).get(w, PREDICTED[leg])
            ps = ((sampled or {}).get(leg) or {}).get(w, pe)
            name = f"x_s19-{leg}-{w}_sweep.csv"
            write_sweep(root / name, pe, ps, (scale or {}).get(leg, 1.0), drop if (leg, w) == ("p4", "gemm") else None)
            manifest["sweeps"][f"{leg}-{w}"] = {"sweep": name}
    for path in sorted(root.glob("*_sweep.csv")):
        if mutate is None and clip is None:
            break
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        fields = list(rows[0])
        if mutate is not None and "-stock-close-" in path.name:
            mutate(rows)
        if clip is not None and f"s19-{clip[0]}-{clip[1]}_" in path.name:
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
    check(all(v == "HOLDS" for v in r["verdicts"].values()), "every leg on its predicted point holds")

    # The energy figure decides; the sampled figure is reported beside it.
    r = evaluate(sampled={"p4": {w: 1852 for w in WORKLOADS}})
    check(r["verdicts"]["p4"] == "HOLDS" and r["medians"]["sampled"]["p4"] == 1852
          and len(r["figures_differ"]["p4"]) == 12, "a sampled-only disagreement is reported, not scored")
    r = evaluate(energy={"rungB": {w: 1545 for w in WORKLOADS}})
    check(r["verdicts"]["rungB"] == "FAILS" and r["verdicts"]["rungC"] == "HOLDS", "an energy median off its point fails that leg only")

    # Stock bracket: unequal energy medians, or a slow return, void everything.
    r = evaluate(energy={"stock-close": {w: 1702 for w in WORKLOADS}})
    check(all(v == "NOT_SCOREABLE" for v in r["verdicts"].values()), "unequal stock energy medians void every prediction")
    r = evaluate(scale={"stock-close": 0.97})
    check(all(v == "NOT_SCOREABLE" for v in r["verdicts"].values()), "a 3% slow stock return voids every prediction")
    r = evaluate(scale={"stock-close": 0.99})
    check(r["verdicts"]["p4"] == "HOLDS", "a 1% stock return is inside the 1.5% gate")

    # A lost treatment role voids its own leg; a lost stock role voids everything.
    r = evaluate(lost=("p4-gemm",))
    check(r["verdicts"]["p4"] == "NOT_SCOREABLE" and r["verdicts"]["p5"] == "HOLDS", "a lost P4 role voids P4 only")
    r = evaluate(lost=("stock-open-copy",))
    check(all(v == "NOT_SCOREABLE" for v in r["verdicts"].values()), "a lost stock role voids everything")

    # GPT Job 56's failure cases, applied to this scorer before section 19 was scored.
    r = evaluate(scale={"stock-close": 0.985})
    check(r["verdicts"]["p4"] == "HOLDS", "a stock return of exactly 1.5% passes: only what exceeds it fails")
    for name, fn in (("a repeated target", lambda rows: rows[0].update(target_frequency_mhz="1395")),
                     ("a target off the registered grid", lambda rows: rows[0].update(target_frequency_mhz="1245")),
                     ("a non-finite throughput", lambda rows: rows[8].update(bench_throughput="nan")),
                     ("a fractional target (GPT Job 61)", lambda rows: rows[0].update(target_frequency_mhz="1237.9"))):
        try:
            evaluate(mutate=fn)
            check(False, f"{name} is refused")
        except ValueError:
            check(True, f"{name} is refused")
    r = evaluate(lost=("p4-gemm",), clip=("p4", "gemm"))
    check(r["verdicts"]["p4"] == "NOT_SCOREABLE" and r["verdicts"]["rungC"] == "HOLDS",
          "an incomplete suite already marked lost voids only itself")

    # A point missing the energy figure is refused, not silently scored on the other figure.
    try:
        evaluate(drop=2010)
        check(False, "a missing energy figure is refused")
    except ValueError:
        check(True, "a missing energy figure is refused")
    try:
        evaluate(section="REGISTERED-PREDICTIONS section 16 (2026-10-06)")
        check(False, "a section 16 manifest is refused")
    except ValueError:
        check(True, "a section 16 manifest is refused")


if __name__ == "__main__":
    main()
