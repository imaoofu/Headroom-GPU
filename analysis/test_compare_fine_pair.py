"""compare_fine_pair.py: arithmetic, cleanliness and refusals, on synthetic and committed sweeps."""

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from compare_fine_pair import compare, load_sweep  # noqa: E402

COMMITTED = ROOT / "data/frequency-sweeps/rtx3070ti-20260825/hwinfo-silent/20260827-172904_rtx3070ti-silent-gemm-fine_sweep.csv"
HEADER = ["target_frequency_mhz", "achieved_frequency_avg", "lock_held", "power_avg_w",
          "temperature_avg_c", "bench_throughput", "bench_ok"]


def write(folder, name, rows, header=HEADER):
    path = Path(folder) / name
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        writer.writerows(rows)
    return path


class CompareFinePair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_committed_sweep_against_itself_is_all_zero(self):
        sweep = load_sweep(COMMITTED)
        result = compare(sweep, sweep)
        self.assertEqual(len(result["points"]), 10)
        self.assertTrue(all(p["delta_pct"] == 0 and p["clean"] for p in result["points"]))
        self.assertEqual(result["argmax_eff_a"], result["argmax_eff_b"])

    def test_arithmetic_unmatched_targets_and_dirty_points(self):
        a = write(self.tmp.name, "a.csv", [
            [1500, 1500, "True", 100, 50, 1.0e13, "True"],
            [1400, 1400, "True", 80, 50, 1.0e13, "True"],
            [1300, 1300, "True", 70, 50, 9.0e12, "True"]])
        b = write(self.tmp.name, "b.csv", [
            [1400, 1400, "True", 80, 55, 9.9e12, "True"],
            [1500, 1488, "False", 100, 55, 1.2e13, "True"],
            [1600, 1600, "True", 110, 55, 1.1e13, "True"]])
        result = compare(load_sweep(a), load_sweep(b))
        self.assertEqual([p["target"] for p in result["points"]], [1400, 1500])
        self.assertEqual((result["only_a"], result["only_b"]), ([1300], [1600]))
        self.assertAlmostEqual(result["points"][0]["delta_pct"], -1.0)
        self.assertFalse(result["points"][1]["clean"])  # a missed lock in either sweep is not clean
        # Statistics use clean points only: the +20% at the dirty 1500 is excluded.
        self.assertAlmostEqual(result["mean_delta_pct"], -1.0)
        self.assertEqual((result["argmax_eff_a"], result["argmax_eff_b"]), (1400, 1400))

    def test_refusals(self):
        dup = write(self.tmp.name, "dup.csv", [[1500, 1500, "True", 100, 50, 1e13, "True"]] * 2)
        empty = write(self.tmp.name, "empty.csv", [[1500, 1500, "True", 100, 50, "", "True"]])
        nokey = write(self.tmp.name, "nokey.csv", [[1500, "True", 100, 50, 1e13, "True"]], HEADER[1:])
        for path in (dup, empty, nokey):
            with self.subTest(path=path.name):
                with self.assertRaises(ValueError):
                    load_sweep(path)
        run = subprocess.run([sys.executable, str(ROOT / "analysis/compare_fine_pair.py"), str(dup), str(COMMITTED)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    # run_tests.py counts [PASS] lines, so report each passing test the way test_bench_app.py does.
    class ReportingResult(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            print("[PASS] " + test.id())

    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    outcome = unittest.TextTestRunner(resultclass=ReportingResult).run(suite)
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
