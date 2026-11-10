"""Synthetic section 18 decisions; no measurement files are read or written."""

import csv
import gzip
import json
import shutil
import tempfile
from pathlib import Path

from score_power_fields import score


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def fixture(root, instant=108.0, usage=100.0, sampled2=100.0, energy=108.0, short=False, section="REGISTERED-PREDICTIONS sections 18 and 19 (2026-10-07)"):
    """One sweep of three 10 s windows; the logger runs 20 Hz across all of them."""
    windows = [(1000.0, 1010.0), (1020.0, 1030.0), (1040.0, 1041.0 if short else 1050.0)]
    with (root / "power-samples.csv").open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=("unix", "usage_w", "average_w", "instant_w", "energy_mj"))
        w.writeheader()
        t = 995.0
        while t < 1055.0:
            w.writerow({"unix": round(t, 3), "usage_w": usage, "average_w": usage, "instant_w": instant, "energy_mj": 0})
            t += 0.05
    with (root / "x_sweep.csv").open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=("target_frequency_mhz", "window_start_unix", "window_end_unix",
                                               "power_avg_w", "energy_avg_power_w", "bench_ok"))
        w.writeheader()
        for i, (s, e) in enumerate(windows):
            w.writerow({"target_frequency_mhz": 1237 + i, "window_start_unix": s, "window_end_unix": e,
                        "power_avg_w": sampled2, "energy_avg_power_w": energy, "bench_ok": "True"})
    manifest = {"section": section, "sweeps": {"p4-gemm": {"sweep": "x_sweep.csv"}}, "powerSamples": "power-samples.csv"}
    (root / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")


def evaluate(gz=False, **kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixture(root, **kwargs)
        if gz:
            # The committed session stores its logger output gzipped.
            with (root / "power-samples.csv").open("rb") as src, gzip.open(root / "power-samples.csv.gz", "wb") as dst:
                shutil.copyfileobj(src, dst)
            (root / "power-samples.csv").unlink()
            manifest = json.loads((root / "rerun15-inputs.json").read_text(encoding="utf-8"))
            manifest["powerSamples"] = "power-samples.csv.gz"
            (root / "rerun15-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
        return score(tmp)


def main():
    r = evaluate()
    check(r["h1"] == "HOLDS" and r["h2"] == "HOLDS" and r["points"] == 3, "instant matching energy and usage matching the 2 Hz sample both hold")
    check(abs(r["against_energy"]["sampled2"] - 100 * (100 / 108 - 1)) < 1e-9, "the sampled figure's gap to energy is reported signed")
    g = evaluate(gz=True)
    check(g["points"] == 3 and g["against_energy"] == r["against_energy"], "a gzipped logger file scores identically")
    r = evaluate(instant=100.0)
    check(r["h1"] == "FAILS", "an instant reading 7% below the counter fails H1")
    r = evaluate(sampled2=97.0)
    check(r["h2"] == "FAILS", "a 2 Hz sample 3% off the 20 Hz mean of the same field fails H2")
    r = evaluate(short=True)
    check(r["points"] == 2 and r["skipped"] == 1, "a 1 s window, under 40 logger rows, is skipped and counted")
    check(r["by_leg"].keys() == {"p4"}, "the configuration is read from the role name")
    try:
        evaluate(section="REGISTERED-PREDICTIONS section 16 (2026-10-06)")
        check(False, "a section 16 manifest is refused")
    except ValueError:
        check(True, "a section 16 manifest is refused")


if __name__ == "__main__":
    main()
