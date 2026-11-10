"""The kit's loaded memory-clock witness (tools/collection-kit/MemoryWitness.ps1).

Runs the real PowerShell function against a fake nvidia-smi (a .cmd passed by absolute path, not on
PATH) and a CPU-only fake probe that prints a gpu_workload-style JSON result with a timed region. No
GPU is touched. The fake probe switches what the fake nvidia-smi reports between its start-up, timed
work and wind-down, which is how the GPT Job 89 cases are built: busy start-up must not stand in for
the probe's work, a start-up clock must not decide the result, and a hung query must not defeat the
deadline. Live checks on the RTX 5060 Ti are recorded in tools/collection-kit/README.md.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WITNESS = ROOT / 'tools' / 'collection-kit' / 'MemoryWitness.ps1'
PS = shutil.which('powershell.exe') or shutil.which('pwsh')

PROBE = r'''
import json, os, sys, time
pre, work, post, code, ok = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), sys.argv[5] == '1'
lines = sys.argv[6:9]
smi = os.environ['FAKE_SMI_FILE']
def report(line):
    with open(smi, 'w') as handle:
        handle.write(line.replace('|', '\n') + '\n')
report(lines[0]); time.sleep(pre)
report(lines[1]); start = time.time(); time.sleep(work); end = time.time()
report(lines[2]); time.sleep(post)
print(json.dumps({"ok": ok, "iterations_requested": 10, "iterations_completed": 10 if ok else 3,
                  "timed_region_start_unix": round(start, 4), "timed_region_end_unix": round(end, 4)}))
sys.exit(code)
'''

CALL = r"""
$ErrorActionPreference = 'Stop'
. $env:HW_WITNESS
$r = Measure-LoadedMemoryClock -PythonExe $env:HW_PYTHON -WorkingDirectory $env:HW_DIR -SmiExe $env:HW_SMI `
    -ProbeArguments ($env:HW_ARGS -split ' ') -DeadlineSeconds ([int]$env:HW_DEADLINE) `
    -QueryTimeoutSeconds ([int]$env:HW_QUERY_TIMEOUT) -PollMilliseconds 100
$r | ConvertTo-Json -Compress
"""

IDLE, BUSY, BUSY_HIGH = '405, 0', '13801, 99', '14001, 99'


@unittest.skipUnless(PS and os.name == 'nt', 'Windows PowerShell unavailable: witness not verified')
class MemoryWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        (self.dir / 'fake-smi.cmd').write_text('@type "%FAKE_SMI_FILE%"\r\n', encoding='ascii')
        (self.dir / 'hung-smi.cmd').write_text('@ping -n 30 127.0.0.1 >nul\r\n', encoding='ascii')
        (self.dir / 'probe.py').write_text(PROBE, encoding='utf-8')

    def measure(self, pre, work, post, lines, exit_code=0, ok=True, smi='fake-smi.cmd', deadline=120, query_timeout=10):
        env = {**os.environ, 'FAKE_SMI_FILE': str(self.dir / 'smi.txt'), 'HW_WITNESS': str(WITNESS),
               'HW_PYTHON': sys.executable, 'HW_DIR': str(self.dir), 'HW_SMI': str(self.dir / smi),
               'HW_ARGS': ' '.join([str(self.dir / 'probe.py'), str(pre), str(work), str(post), str(exit_code),
                                    '1' if ok else '0'] + [line.replace(' ', '') for line in lines]),
               'HW_DEADLINE': str(deadline), 'HW_QUERY_TIMEOUT': str(query_timeout)}
        (self.dir / 'smi.txt').write_text(lines[0].replace('|', '\n') + '\n', encoding='ascii')
        started = time.monotonic()
        run = subprocess.run([PS, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', CALL],
                             capture_output=True, text=True, env=env, timeout=180)
        self.elapsed = time.monotonic() - started
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout.strip().splitlines()[-1])

    def test_busy_timed_work_gives_a_loaded_reading(self):
        r = self.measure(0.5, 2.0, 0.3, (IDLE, BUSY, IDLE))
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mhz'], 13801)
        self.assertGreaterEqual(r['loadedSamples'], 3)
        self.assertGreaterEqual(r['timedRegionStartSeconds'], 0.4)

    def test_busy_startup_then_idle_work_is_refused(self):
        # Job 89 W1: three busy start-up samples were enough before; now only the timed work counts.
        r = self.measure(2.0, 2.0, 0.2, (BUSY, IDLE, IDLE))
        self.assertFalse(r['ok'], r)
        self.assertGreaterEqual(r['busyAnywhere'], 3)
        self.assertEqual(r['loadedSamples'], 0)

    def test_a_higher_startup_clock_does_not_decide_the_result(self):
        r = self.measure(1.5, 2.0, 0.2, (BUSY_HIGH, BUSY, IDLE))
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mhz'], 13801)

    def test_busy_samples_after_the_timed_work_do_not_count(self):
        r = self.measure(0.2, 2.0, 1.5, (IDLE, BUSY, BUSY_HIGH))
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mhz'], 13801)

    def test_failed_probe_is_refused_even_with_busy_work(self):
        r = self.measure(0.2, 1.0, 0.2, (BUSY, BUSY, BUSY), exit_code=3)
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['exitCode'], 3)
        self.assertIn('code 3', r['reason'])

    def test_probe_that_reports_an_incomplete_run_is_refused(self):
        r = self.measure(0.2, 1.0, 0.2, (BUSY, BUSY, BUSY), ok=False)
        self.assertFalse(r['ok'], r)
        self.assertIn('ok = true', r['reason'])

    def test_deadline_stops_a_probe_and_verifies_it(self):
        r = self.measure(0.2, 60, 0.2, (BUSY, BUSY, BUSY), deadline=2)
        self.assertFalse(r['ok'], r)
        self.assertIn('still running', r['reason'])
        self.assertIn('was stopped', r['reason'])
        self.assertTrue(r['probeStopped'])
        self.assertLess(self.elapsed, 40)

    def test_a_hung_nvidia_smi_cannot_hold_the_witness(self):
        # Job 89 W3: each query is bounded, so a hang costs one timeout per poll, not the whole run.
        r = self.measure(0.2, 1.5, 0.2, (BUSY, BUSY, BUSY), smi='hung-smi.cmd', query_timeout=1)
        self.assertFalse(r['ok'], r)
        self.assertGreater(r['queryFailures'], 0)
        self.assertLess(self.elapsed, 40)

    def test_two_gpus_are_refused_not_guessed(self):
        r = self.measure(0.2, 1.5, 0.2, (BUSY + '|' + BUSY_HIGH,) * 3)
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['loadedSamples'], 0)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MemoryWitnessTests)
    names = [test.id() for test in suite]  # the runner empties the suite as it goes
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    for test, reason in result.skipped: print('[SKIP] ' + test.id() + ': ' + reason)
    bad = {test.id() for test, _ in result.failures + result.errors + result.skipped}
    for name in names:
        if name not in bad:
            print('[PASS] ' + name.rsplit('.', 1)[-1].replace('_', ' '))
    raise SystemExit(0 if result.wasSuccessful() else 1)
