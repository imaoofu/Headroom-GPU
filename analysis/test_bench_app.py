"""No-GPU checks for Headroom Bench under Windows PowerShell 5.1 or PS 7."""
import copy
import csv
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'tools' / 'bench-app'
CATALOG = APP / 'catalog' / 'sessiond-3070ti.json'
SESSIONE = APP / 'catalog' / 'sessione-2060s.json'
SESSIOND2 = APP / 'catalog' / 'sessiond2-3070ti.json'
SESSIONE2 = APP / 'catalog' / 'sessione2-2060s.json'
NEWCARD = APP / 'catalog' / 'newcard-rtx40-50.json'
PS = (shutil.which(os.environ['HEADROOM_TEST_PS']) if os.environ.get('HEADROOM_TEST_PS')
      else (shutil.which('powershell.exe') or shutil.which('pwsh')))


@unittest.skipUnless(PS, 'PowerShell is unavailable')
class BenchAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        self.mock = {
            'telemetry': [290, 290, 320, '610.88'],
            'quietUtil': 0, 'profileHash': 'A1159941DA541EB90123',
            'witnesses': {
                '1': {'core': 1763, 'memory': 9501},
                '2': {'core': 1395, 'memory': 9501},
                '3': {'core': 1500, 'memory': 9501},
            },
            'voltage': 0.850,
        }

    def write(self, name, value):
        path = self.dir / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def ps(self, script, *args):
        cmd = [PS, '-NoProfile']
        if os.name == 'nt':
            cmd += ['-ExecutionPolicy', 'Bypass']
        cmd += ['-File', str(APP / script), *map(str, args)]
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=40)

    def ps_command(self, command):
        cmd = [PS, '-NoProfile']
        if os.name == 'nt':
            cmd += ['-ExecutionPolicy', 'Bypass']
        return subprocess.run(cmd + ['-Command', command], cwd=ROOT,
                              capture_output=True, text=True, timeout=40)

    def display(self, expression, plan=None, record=None):
        helper = str(APP / 'Bench-Display.ps1').replace("'", "''")
        prefix = f". '{helper}'; "
        if plan is not None:
            path = str(self.write('display-plan.json', plan)).replace("'", "''")
            prefix += f"$plan=Get-Content '{path}' -Raw | ConvertFrom-Json; "
        if record is not None:
            path = str(self.write('display-record.json', record)).replace("'", "''")
            prefix += f"$record=Get-Content '{path}' -Raw | ConvertFrom-Json; "
        proc = self.ps_command(prefix + expression + ' | ConvertTo-Json -Depth 12 -Compress')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def engine(self, plan=None, session=None, resume=False):
        plan = plan or self.catalog
        session = session or self.dir / 'session.json'
        plan_path = self.write('plan.json', plan)
        mock_path = self.write('mock.json', self.mock)
        args = ['-PlanPath', plan_path, '-SessionPath', session,
                '-MockPath', mock_path, '-DryRun']
        if resume:
            args.append('-Resume')
        proc = self.ps('Run-Plan.ps1', *args)
        record = json.loads(session.read_text(encoding='utf-8')) if session.exists() else None
        return proc, record

    def validate(self, plan):
        path = self.write('invalid.json', plan)
        return self.ps('Test-Plan.ps1', '-PlanPath', path)

    def test_full_passing_preselected_catalog(self):
        proc, record = self.engine()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['status'], 'PASS')
        self.assertEqual(len(record['steps']), 63)
        self.assertEqual(record['selectedRuns'], [r['id'] for r in self.catalog['runs']])
        self.assertEqual(record['revert']['coreMhz'], 1763)
        # Unattended (2026-09-24): no end-of-session prompt, so nothing waits for a person.
        self.assertIsNone(self.catalog.get('afterRevertHuman'))
        self.assertFalse(record['afterRevertHumanCompleted'])
        self.assertTrue(record['finalState']['logging']['stoppedVerified'])
        self.assertTrue(record['finalState']['clocks']['verified'])
        self.assertEqual(record['finalState']['clocks']['readbackSmClockMhz'], 1763)
        self.assertTrue(record['finalState']['processes']['verified'])

    def test_sensors_step_passes_itself_when_sensors_window_detected(self):
        # Suggested by Raymond 2026-09-23: with HWiNFO's Sensors window up, run start to finish
        # untouched. Default (not detected) records the operator; detected records auto.
        proc, record = self.engine()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        sensors = [s for s in record['steps'] if s['key'] == 'preflight/sensors'][0]
        self.assertEqual(sensors['witness'], {'acknowledged': True, 'confirmedBy': 'operator'})
        self.mock['sensorsReady'] = True
        proc, record = self.engine(session=self.dir / 'auto.json')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        sensors = [s for s in record['steps'] if s['key'] == 'preflight/sensors'][0]
        self.assertEqual(sensors['witness'], {'acknowledged': True, 'confirmedBy': 'auto'})
        # Wait-Human now returns a value; no other step may pick it up as stray output.
        for step in record['steps']:
            self.assertNotIn('operator', json.dumps(step['witness']) if step['key'] != 'preflight/sensors' else '')

    def test_section8_runs_follow_the_registered_bracket(self):
        # REGISTERED-PREDICTIONS section 8 (2026-09-23): the extras must run only after stock-4
        # closes 4a/4b, so they cannot change how the registered suites are scored.
        ids = [r['id'] for r in self.catalog['runs']]
        extras = ['finefloor-pair', 'edit1-finefloor', 'edit1-5', 'stock-6']
        self.assertEqual(ids[:5], ['preflight', 'stock-1', 'edit1-2', 'edit2-3', 'stock-4'])
        self.assertEqual([i for i in ids if i in extras], extras)
        self.assertTrue(all(ids.index(e) > ids.index('stock-4') for e in extras))
        self.assertEqual(ids[-1], 'cleanup')
        runs = {r['id']: r for r in self.catalog['runs']}
        self.assertEqual(runs['finefloor-pair']['requires'], ['stock-4'])
        gate = [s for s in runs['stock-6']['steps'] if s['type'] == 'gate-drift'][0]
        self.assertEqual((gate['firstRun'], gate['lastRun']), ('stock-4', 'stock-6'))
        labels = [s.get('label') for r in self.catalog['runs'] for s in r['steps'] if s.get('label')]
        self.assertEqual(len(labels), len(set(labels)))

    @unittest.skipUnless(os.name == 'nt', 'Windows file-sharing semantics')
    def test_session_save_survives_a_reader_holding_the_file(self):
        # Session D stopped at step 27 on 2026-09-24: "Cannot create a file when that file already
        # exists". Move-Item -Force over a file another process holds open fails with exactly that;
        # Write-FileAtomic retries until the reader lets go.
        target = self.dir / 'session.json'
        target.write_text('{"old":1}', encoding='utf-8')
        path = str(target).replace("'", "''")
        hold = (f"$f=[IO.File]::Open('{path}','Open','Read','ReadWrite'); "
                "Start-Sleep -Milliseconds 1500; $f.Close()")
        args = [PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command']
        reader = subprocess.Popen(args + [hold])
        self.addCleanup(reader.wait)
        time.sleep(0.8)
        helper = str(APP / 'Write-Atomic.ps1').replace("'", "''")
        old = self.ps_command(f"Set-Content -LiteralPath '{path}.tmp' -Value 'x'; "
                              f"try {{ Move-Item -LiteralPath '{path}.tmp' -Destination '{path}' -Force -ErrorAction Stop; 'ok' }} "
                              "catch { 'FAILED: ' + $_.Exception.Message }")
        self.assertIn('already exists', old.stdout)
        reader.wait()
        (self.dir / 'session.json.tmp').unlink(missing_ok=True)
        reader = subprocess.Popen(args + [hold])
        self.addCleanup(reader.wait)
        time.sleep(0.8)
        new = self.ps_command(f". '{helper}'; $n=Write-FileAtomic '{path}' '{{\"new\":2}}'; "
                              f"'attempts=' + $n + ' tmp=' + (Test-Path '{path}.tmp')")
        self.assertEqual(new.returncode, 0, new.stdout + new.stderr)
        self.assertIn('tmp=False', new.stdout)
        self.assertGreater(int(new.stdout.split('attempts=')[1].split()[0]), 1)
        reader.wait()
        self.assertEqual(target.read_text(encoding='utf-8'), '{"new":2}')

    def test_suite_top_guard_refuses_a_moved_clock_table(self):
        # Session D2 (2026-09-25): the 3070 Ti's table top moved 2115 -> 2130 overnight, the grid
        # moved with it, and 8d became NOT SCOREABLE. A catalog that states its table top refuses.
        helper = str(APP / 'Card-Checks.ps1').replace("'", "''")
        def problem(top, card_json):
            proc = self.ps_command(f". '{helper}'; $card='{card_json}' | ConvertFrom-Json; "
                                   f"$r=Get-SuiteTopProblem {top} $card; if ($null -eq $r) {{ 'NONE' }} else {{ $r }}")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.strip()
        self.assertEqual(problem(2115, '{"suiteTopClockMhz":2115}'), 'NONE')
        moved = problem(2130, '{"suiteTopClockMhz":2115}')
        self.assertIn('tops out at 2130 MHz, not the 2115 MHz', moved)
        self.assertEqual(problem(2130, '{"name":"no pin"}'), 'NONE')
        plan = json.loads(SESSIONE.read_text(encoding='utf-8'))
        self.assertEqual(plan['card']['suiteTopClockMhz'], 2115)
        bad = copy.deepcopy(plan)
        bad['card']['suiteTopClockMhz'] = 5
        self.assertNotEqual(self.validate(bad).returncode, 0)

    # ---- Session D2, RTX 3070 Ti, REGISTERED-PREDICTIONS 8d (2026-09-25) --------------------

    def test_sessiond2_is_current_and_runs_through_unattended(self):
        spec = importlib.util.spec_from_file_location('build_sessiond2', APP / 'catalog' / 'build_sessiond2.py')
        builder = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(APP / 'catalog'))
        try:
            spec.loader.exec_module(builder)
        finally:
            sys.path.remove(str(APP / 'catalog'))
        plan = json.loads(SESSIOND2.read_text(encoding='utf-8'))
        self.assertEqual(json.loads(json.dumps(builder.plan)), plan, 'rerun build_sessiond2.py')
        self.assertEqual([r['id'] for r in plan['runs']], ['preflight', 'stock-7', 'edit2-8', 'stock-9', 'cleanup'])
        runs = {r['id']: r for r in plan['runs']}
        # The same preflight as Session D, so the same store hash, BIOS gate and stock witness.
        self.assertEqual(runs['preflight']['steps'], self.catalog['runs'][0]['steps'])
        self.assertEqual([s['slot'] for s in runs['edit2-8']['steps'] if s['type'] == 'apply-profile'], [3])
        for identifier in ('stock-7', 'edit2-8', 'stock-9'):
            collect = [s for s in runs[identifier]['steps'] if s['type'] == 'suite'][0]
            self.assertEqual(collect['label'], 'rtx3070ti-sessiond-' + identifier)
            self.assertEqual(collect['iterations'], self.catalog['runs'][1]['steps'][3]['iterations'])
        gate = [s for s in runs['stock-9']['steps'] if s['type'] == 'gate-drift'][0]
        self.assertEqual((gate['firstRun'], gate['lastRun'], gate['blocking']), ('stock-7', 'stock-9', False))
        self.assertIsNone(plan.get('afterRevertHuman'))
        self.assertTrue(all(r['preselected'] for r in plan['runs']))
        # Unattended: with the Sensors window already open, nothing waits for a person.
        self.mock['sensorsReady'] = True
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['status'], 'PASS')
        sensors = [s for s in record['steps'] if s['key'] == 'preflight/sensors'][0]
        self.assertEqual(sensors['witness']['confirmedBy'], 'auto')

    def test_one_active_catalog_per_card(self):
        # The window opens the only active run list for its card with no picker. Two active lists
        # for one card would open a picker whose first entry may be the wrong session.
        active = {}
        for path in sorted((APP / 'catalog').glob('*.json')):
            plan = json.loads(path.read_text(encoding='utf-8'))
            if not plan.get('retired'):
                active.setdefault(plan['card']['name'], []).append(path.name)
        # The 3070 Ti's sessions are all collected (D2 retired 2026-09-25), so it has none.
        self.assertNotIn('NVIDIA GeForce RTX 3070 Ti', active)
        # Session E is collected (retired 2026-09-27); its re-run E2 is the one active list.
        self.assertEqual(active['NVIDIA GeForce RTX 2060 SUPER'], ['sessione2-2060s.json'])
        # Exactly one generic run list, offered only where no card-specific one exists.
        generic = [path.name for path in (APP / 'catalog').glob('*.json')
                   if json.loads(path.read_text(encoding='utf-8'))['card'].get('generic')]
        self.assertEqual(generic, ['newcard-rtx40-50.json'])
        self.assertTrue(all(len(names) == 1 for names in active.values()), active)

    # ---- Session E, RTX 2060 Super (2026-09-24; P2 changed 2026-09-27) ----------------------
    # P2 was a curve edit below 0.669 V, which Afterburner would not build; it is now a -165 MHz
    # whole-curve offset (REGISTERED-PREDICTIONS §4d, Amendment 2). An unlocked witness cannot see
    # either, so the witnesses are locked-clock voltage checks. The mock keys them "slot@lock".

    def sessione(self):
        plan = json.loads(SESSIONE.read_text(encoding='utf-8'))
        mock = {
            'telemetry': [175, 175, 185, '616.92'], 'quietUtil': 0, 'voltage': 0.644,
            'witnesses': {
                '1': {'core': 1618, 'memory': 6801},
                '1@1065': {'core': 1065, 'memory': 6801, 'voltage': 0.644},
                '2@1065': {'core': 1065, 'memory': 6801, 'voltage': 0.681},
                '2@1275': {'core': 1275, 'memory': 6801, 'voltage': 0.744},
            },
        }
        return plan, mock

    def test_sessione_catalog_is_current_and_runs_through(self):
        spec = importlib.util.spec_from_file_location('build_sessione', APP / 'catalog' / 'build_sessione.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        plan, self.mock = self.sessione()
        self.assertEqual(json.loads(json.dumps(builder.plan)), plan, 'rerun build_sessione.py')
        self.assertEqual(plan['card']['name'], 'NVIDIA GeForce RTX 2060 SUPER')
        self.assertEqual([r['id'] for r in plan['runs']],
                         ['preflight', 'e1-desc', 'stock-1', 'offset-2', 'stock-3', 'cleanup'])
        runs = {r['id']: r for r in plan['runs']}
        sweep = [s for s in runs['e1-desc']['steps'] if s['type'] == 'sweep'][0]
        self.assertEqual((sweep['minMhz'], sweep['maxMhz'], sweep['points'], sweep['direction'],
                          sweep['iterations']), (900, 1140, 13, 'descending', 120))
        for identifier in ('stock-1', 'offset-2', 'stock-3'):
            collect = [s for s in runs[identifier]['steps'] if s['type'] == 'suite'][0]
            # 4c's baseline came from the 09-12 suite; its counts are reused, never re-derived.
            self.assertEqual(collect['iterations'], [2936, 3180, 2377, 1628, 1163, 2986, 1935, 1076, 297, 88, 223, 120])
            self.assertEqual(collect['expectedMemoryClockMhz'], 7000)
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['status'], 'PASS')
        self.assertEqual(record['revert']['coreMhz'], 1618)

    def test_sessione_offset_missing_below_700_mv_stops_before_its_suite(self):
        # An offset that moved only the points the editor exposes leaves 1065 on stock's 0.644 V.
        plan, self.mock = self.sessione()
        self.mock['witnesses']['2@1065']['voltage'] = 0.644
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        failed = [s['key'] for s in record['steps'] if s['verdict'] == 'FAIL']
        self.assertEqual(failed, ['offset-2/witness'])
        self.assertNotIn('offset-2/collect', [s['key'] for s in record['steps']])

    def test_sessione_offset_live_in_the_stock_slot_stops_e1(self):
        # E1 measures the stock floor, so it must not run with the offset live.
        plan, self.mock = self.sessione()
        self.mock['witnesses']['1@1065']['voltage'] = 0.681
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('e1-desc/witness', [s['key'] for s in record['steps'] if s['verdict'] == 'FAIL'])
        self.assertNotIn('e1-desc/sweep', [s['key'] for s in record['steps']])

    def test_sessione_offset_missing_on_the_upper_curve_stops(self):
        # Stock's 0.694 V at 1275: the offset did not shift the upper curve.
        plan, self.mock = self.sessione()
        self.mock['witnesses']['2@1275']['voltage'] = 0.694
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('offset-2/witness-above', [s['key'] for s in record['steps'] if s['verdict'] == 'FAIL'])

    # ---- Session E2, the 4c-offset re-run on a fixed target list (2026-09-27) -----------------
    # Session E's offset suite shifted its grid because the offset moved the clock table's top
    # (2115 -> 2100). E2 gives every suite the same explicit 12-target list, so the table may move.

    def sessione2(self):
        plan = json.loads(SESSIONE2.read_text(encoding='utf-8'))
        _, mock = self.sessione()
        mock['witnesses']['2@1065']['voltage'] = 0.681
        mock['witnesses']['2@1275']['voltage'] = 0.744
        return plan, mock

    def test_sessione2_is_current_and_runs_with_a_moving_table(self):
        spec = importlib.util.spec_from_file_location('build_sessione2', APP / 'catalog' / 'build_sessione2.py')
        builder = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(APP / 'catalog'))
        try:
            spec.loader.exec_module(builder)
        finally:
            sys.path.pop(0)
        plan, self.mock = self.sessione2()
        self.assertEqual(json.loads(json.dumps(builder.plan)), plan, 'rerun build_sessione2.py')
        self.assertEqual([r['id'] for r in plan['runs']],
                         ['preflight', 'stock-4', 'offset-5', 'stock-6', 'cleanup'])
        runs = {r['id']: r for r in plan['runs']}
        for identifier in ('stock-4', 'offset-5', 'stock-6'):
            collect = [s for s in runs[identifier]['steps'] if s['type'] == 'suite'][0]
            self.assertEqual(collect['targetsMhz'], list(range(855, 2011, 105)))
            self.assertEqual(collect['iterations'], [2936, 3180, 2377, 1628, 1163, 2986, 1935, 1076, 297, 88, 223, 120])
        # The table top moves under the offset, as it did in Session E; explicit targets run anyway.
        self.mock['tableTopSequence'] = [2115, 2100, 2115]
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['status'], 'PASS')

    def test_sessione2_without_its_list_would_stop_at_the_offset_suite(self):
        # The same plan with the offset suite's list removed is Session E's design: a derived grid,
        # and the newer engine's mid-session check refuses when the table top moves.
        plan, self.mock = self.sessione2()
        for step in [r for r in plan['runs'] if r['id'] == 'offset-5'][0]['steps']:
            step.pop('targetsMhz', None)
        # Since 2026-09-30 the validator refuses this plan outright (see the explicit-target test
        # below). The exemption a pre-rule run list carries lets this test still reach the engine's
        # own mid-session check, which is the second line of defence.
        plan['card']['legacyDerivedGrids'] = 'test: a derived grid, as Session E had'
        self.mock['tableTopSequence'] = [2115, 2100]
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        failed = [s for s in record['steps'] if s['verdict'] == 'FAIL']
        self.assertEqual([s['key'] for s in failed], ['offset-5/collect'])
        self.assertIn('moved from 2115 MHz to 2100 MHz', failed[0]['error'])

    def test_validator_requires_explicit_targets_with_a_profile(self):
        # Rule of 2026-09-30: a derived grid moved under two registered tests (3070 Ti D2 overnight,
        # 2060 Super Session E under an offset), so a known-card run list that applies a profile must
        # give every suite targetsMhz, or carry card.legacyDerivedGrids with a stated reason.
        plan, _ = self.sessione2()
        proc = self.validate(plan)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)   # every suite explicit

        derived = copy.deepcopy(plan)
        for step in [r for r in derived['runs'] if r['id'] == 'offset-5'][0]['steps']:
            step.pop('targetsMhz', None)
        proc = self.validate(derived)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('every suite must state its targets', proc.stdout)
        self.assertIn('Suites without them:', proc.stdout)

        blank = copy.deepcopy(derived)
        blank['card']['legacyDerivedGrids'] = '   '
        self.assertNotEqual(self.validate(blank).returncode, 0, 'a blank reason is not an exemption')

        unneeded = copy.deepcopy(plan)
        unneeded['card']['legacyDerivedGrids'] = 'not needed'
        proc = self.validate(unneeded)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('has none that need it', proc.stdout)

        # Session D carries the exemption, and loses validity without it.
        self.assertEqual(self.validate(self.catalog).returncode, 0)
        stripped = copy.deepcopy(self.catalog)
        stripped['card'].pop('legacyDerivedGrids')
        self.assertNotEqual(self.validate(stripped).returncode, 0)

        # The generic stock-only list has no profile, so it needs no exemption and may not carry one.
        generic = json.loads(NEWCARD.read_text(encoding='utf-8'))
        self.assertEqual(self.validate(generic).returncode, 0)
        generic['card']['legacyDerivedGrids'] = 'not needed'
        self.assertNotEqual(self.validate(generic).returncode, 0)

    def test_generic_list_needs_its_stock_only_power_gate(self):
        # GPT Job 88, R2: ordinary gates with any three positive values used to validate.
        def gates(plan):
            return [s for run in plan['runs'] for s in run['steps'] if s['type'] == 'gate-power']
        plan = json.loads(NEWCARD.read_text(encoding='utf-8'))
        self.assertTrue(gates(plan) and all(s.get('stockOnly') for s in gates(plan)))
        for step in gates(plan):
            step.pop('stockOnly'); step.update(limit=200, default=180, max=200)
        proc = self.validate(plan)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('only stockOnly power gates', proc.stdout + proc.stderr)
        plan = json.loads(NEWCARD.read_text(encoding='utf-8'))
        for step in gates(plan):
            keep = step['id']
            step.clear(); step.update(id=keep, type='gate-quiet', name='Quiet', estimatedMinutes=0.3, maxUtil=10)
        proc = self.validate(plan)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('stockOnly power gate before any measurement', proc.stdout + proc.stderr)

    def test_sessione2_offset_missing_below_700_mv_stops(self):
        plan, self.mock = self.sessione2()
        self.mock['witnesses']['2@1065']['voltage'] = 0.644
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual([s['key'] for s in record['steps'] if s['verdict'] == 'FAIL'], ['offset-5/witness'])

    # ---- The generic new-card protocol, REGISTERED-PREDICTIONS 11 (2026-09-25) ---------------
    # Written before any card is known; stock only by construction.

    def newcard(self):
        plan = json.loads(NEWCARD.read_text(encoding='utf-8'))
        mock = {'telemetry': [165, 165, 180, '617.14'], 'quietUtil': 0, 'tableTop': 3090,
                'uuid': 'GPU-aaaa', 'witnesses': {'1': {'core': 2600, 'memory': 14001}}}
        return plan, mock

    def test_newcard_catalog_is_current_and_runs_through(self):
        spec = importlib.util.spec_from_file_location('build_newcard', APP / 'catalog' / 'build_newcard.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        plan, self.mock = self.newcard()
        self.assertEqual(json.loads(json.dumps(builder.plan)), plan, 'rerun build_newcard.py')
        self.assertTrue(plan['card']['generic'])
        self.assertIsNone(plan['revert'])
        self.assertEqual([r['id'] for r in plan['runs']],
                         ['preflight', 'calibrate', 'dense-asc', 'dense-desc', 'suite', 'cleanup'])
        self.mock['calibration'] = 250
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['status'], 'PASS')
        self.assertIsNone(record['revert'])
        self.assertEqual(record['supportedClockRange'][1], 3090)
        self.assertEqual(record['calibration']['iterations'], [250] * 11)
        steps = {s['key']: s for s in record['steps']}
        # 40-80% of a 3090 MHz table top, resolved at run time.
        for key in ('dense-asc/sweep', 'dense-desc/sweep'):
            self.assertEqual((steps[key]['witness']['minMhz'], steps[key]['witness']['maxMhz']), (1236, 2472))
        # Calibrated counts for eleven workloads, gemm at its default 120, in suite order.
        self.assertEqual(steps['suite/collect']['witness']['iterations'], [250] * 11 + [120])
        # {session} makes every log path this session's own.
        logs = [s['witness']['path'] for s in record['steps'] if s['type'] == 'hwinfo-start']
        self.assertEqual(len(logs), 3)
        self.assertTrue(all('hwinfo-session-newcard-' in p for p in logs), logs)

    def test_newcard_card_pattern_takes_40_and_50_series_only(self):
        plan, _ = self.newcard()
        pattern = plan['card']['namePattern'].replace("'", "''")
        helper = str(APP / 'Card-Checks.ps1').replace("'", "''")
        names = {'NVIDIA GeForce RTX 5060 Ti': True, 'NVIDIA GeForce RTX 4060': True,
                 'NVIDIA GeForce RTX 4070 Ti SUPER': True, 'NVIDIA GeForce RTX 5060': True,
                 'NVIDIA GeForce RTX 3070 Ti': False, 'NVIDIA GeForce RTX 2060 SUPER': False,
                 'NVIDIA GeForce RTX 4060 Laptop GPU': False}
        for name, expected in names.items():
            proc = self.ps_command(f". '{helper}'; $card=[pscustomobject]@{{generic=$true; namePattern='{pattern}'}}; "
                                   f"if (Test-CardMatches '{name}' $card) {{ 'yes' }} else {{ 'no' }}")
            self.assertEqual(proc.stdout.strip(), 'yes' if expected else 'no', name)

    def test_newcard_validator_keeps_it_stock_only(self):
        plan, _ = self.newcard()
        mutations = []
        def altered(change):
            p = copy.deepcopy(plan)
            change(p)
            mutations.append(p)
        altered(lambda p: p['runs'][0]['steps'].append({'id': 'profile', 'type': 'apply-profile', 'name': 'x', 'slot': 1}))
        altered(lambda p: p['runs'][0]['steps'].append({'id': 'w', 'type': 'witness', 'name': 'x', 'workload': 'gemm', 'iterations': 10,
                                                        'coreMin': 100, 'coreMax': 200, 'memoryMin': 1, 'memoryMax': 2}))
        # Well formed in every other respect, so only the stock-only rule can refuse it.
        altered(lambda p: p['runs'][0]['steps'].append({'id': 'hash', 'type': 'gate-hash', 'name': 'x',
                                                        'path': 'C:/Program Files (x86)/MSI Afterburner/Profiles/VEN.cfg', 'prefix': 'A1159941'}))
        altered(lambda p: p.update(revert={'slot': 1, 'witness': {'workload': 'gemm', 'iterations': 10, 'coreMin': 1, 'coreMax': 2, 'memoryMin': 1, 'memoryMax': 2}}))
        altered(lambda p: p['card'].update(namePattern='NVIDIA'))              # unanchored
        altered(lambda p: p['card'].update(suiteTopClockMhz=3090))
        altered(lambda p: p['runs'][2]['steps'][1].update(minMhz=1200))         # fixed MHz on a generic sweep
        altered(lambda p: p['runs'][2]['steps'][1].update(maxPctOfTop=1.2))
        altered(lambda p: p['runs'][1]['steps'][0]['workloads'].append('gemm'))  # gemm keeps 120
        altered(lambda p: p['runs'].pop(1))                                      # calibrated suite, no calibrate
        altered(lambda p: p['runs'][0]['steps'][2].update(limit=165))            # stockOnly with a limit
        for i, mutated in enumerate(mutations):
            with self.subTest(mutation=i):
                proc = self.validate(mutated)
                self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_newcard_refuses_a_power_limit_off_default(self):
        plan, self.mock = self.newcard()
        self.mock['telemetry'] = [180, 165, 180, '617.14']
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual([s['key'] for s in record['steps'] if s['verdict'] == 'FAIL'], ['preflight/power'])

    def test_table_top_moving_mid_session_stops_before_the_next_grid(self):
        plan, self.mock = self.newcard()
        # Read 1 is preflight, read 2 the ascending sweep; read 3, the descending sweep, sees 3105.
        self.mock['tableTopSequence'] = [3090, 3090, 3105]
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        failed = [s for s in record['steps'] if s['verdict'] == 'FAIL']
        self.assertEqual([s['key'] for s in failed], ['dense-desc/sweep'])
        self.assertIn('moved from 3090 MHz to 3105 MHz', failed[0]['error'])

    def test_newcard_resume_reuses_calibration(self):
        plan, self.mock = self.newcard()
        self.mock['calibration'] = 250
        self.mock['failSuite'] = True
        first, _ = self.engine(plan)
        self.assertNotEqual(first.returncode, 0)
        # Same card: the counts are kept, not re-derived, even if calibration would now differ. A
        # resume skips the finished calibrate run entirely; the engine's reuse guard is a second
        # layer this test does not isolate (mutation-tested 2026-09-25).
        self.mock['failSuite'] = False
        self.mock['calibration'] = 999
        second, record = self.engine(plan, resume=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(record['calibration']['iterations'], [250] * 11)
        suite = [s for s in record['steps'] if s['key'] == 'suite/collect' and s['verdict'] == 'PASS'][0]
        self.assertEqual(suite['witness']['iterations'], [250] * 11 + [120])

    def test_resume_on_another_physical_card_is_refused(self):
        plan, self.mock = self.newcard()
        self.mock['failSuite'] = True
        first, _ = self.engine(plan)
        self.assertNotEqual(first.returncode, 0)
        self.mock['failSuite'] = False
        self.mock['uuid'] = 'GPU-bbbb'
        second, record = self.engine(plan, resume=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('started on another card', second.stdout)

    def test_resume_after_the_table_moved_is_refused(self):
        plan, self.mock = self.newcard()
        self.mock['failSuite'] = True
        first, _ = self.engine(plan)
        self.assertNotEqual(first.returncode, 0)
        self.mock['failSuite'] = False
        self.mock['tableTop'] = 3105
        second, _ = self.engine(plan, resume=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('moved from 3090 MHz to 3105 MHz', second.stdout)

    def section_hash(self, path, sections):
        helper = str(APP / 'Profile-Hash.ps1').replace("'", "''")
        names = ','.join("'%s'" % name for name in sections)
        command = f". '{helper}'; Get-ProfileSectionHash '{str(path)}' @({names})"
        args = [PS, '-NoProfile'] + (['-ExecutionPolicy', 'Bypass'] if os.name == 'nt' else [])
        return subprocess.run(args + ['-Command', command], capture_output=True, text=True, timeout=30)

    def test_profile_section_hash_pins_the_slots_not_the_file(self):
        # 2026-09-24: Afterburner added [Defaults] and [Settings] to the 3070 Ti store by itself and
        # the whole-file hash stopped Session D, with Profile1-3 unchanged. The gate now hashes the
        # slots the runs apply; both real snapshots must give the catalog's prefix.
        slots = ['Profile1', 'Profile2', 'Profile3']
        prefix = [s for s in self.catalog['runs'][0]['steps'] if s['type'] == 'gate-hash'][0]['prefix']
        stores = {}
        for folder in ('3070ti-profiles-20260923', '3070ti-profiles-20260924-afterburner-rewrite'):
            store = next((ROOT / 'data' / 'afterburner-profiles' / folder).glob('VEN_10DE*.cfg'))
            stores[folder] = store
            proc = self.section_hash(store, slots)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.strip().startswith(prefix), (folder, proc.stdout))
        # A changed curve in a pinned slot changes the hash; an added unpinned section does not.
        text = stores['3070ti-profiles-20260923'].read_text(encoding='utf-8-sig')
        marker = text.index('VFCurve=', text.index('[Profile2]')) + len('VFCurve=') + 40
        changed = self.dir / 'changed.cfg'
        changed.write_text(text[:marker] + ('0' if text[marker] != '0' else '1') + text[marker + 1:], encoding='utf-8')
        self.assertFalse(self.section_hash(changed, slots).stdout.strip().startswith(prefix))
        extra = self.dir / 'extra.cfg'
        extra.write_text(text + '\n[Defaults]\nPowerLimit=100\n[Settings]\nCaptureDefaults=0\n', encoding='utf-8')
        self.assertTrue(self.section_hash(extra, slots).stdout.strip().startswith(prefix))
        missing = self.section_hash(stores['3070ti-profiles-20260923'], slots + ['Profile4'])
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('no [Profile4] section', missing.stdout + missing.stderr)
        # The validator accepts only ProfileN slots.
        bad = copy.deepcopy(self.catalog)
        [s for s in bad['runs'][0]['steps'] if s['type'] == 'gate-hash'][0]['sections'] = ['Defaults']
        self.assertNotEqual(self.validate(bad).returncode, 0)

    def test_edited_preselected_run_is_flagged_and_recorded(self):
        queue = copy.deepcopy(self.catalog['runs'])
        queue[1]['steps'][3]['settings'] += ' operator edit'
        queue_path = self.write('queue.json', {'runs': queue})
        plan_path = self.dir / 'edited-plan.json'
        made = self.ps('New-Plan.ps1', '-CatalogPath', CATALOG,
                       '-QueuePath', queue_path, '-OutputPath', plan_path)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        self.assertEqual(plan['customizations'][0]['kind'], 'edited')
        self.assertEqual(plan['customizations'][0]['run'], 'stock-1')
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['customizations'][0]['actual']['steps'][3]['settings'],
                         queue[1]['steps'][3]['settings'])

    def test_unselected_cleanup_does_not_request_uninstall(self):
        queue = {'runs': self.catalog['runs'][:-1]}
        queue_path = self.write('queue.json', queue)
        plan_path = self.dir / 'subset-plan.json'
        made = self.ps('New-Plan.ps1', '-CatalogPath', CATALOG,
                       '-QueuePath', queue_path, '-OutputPath', plan_path)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        self.assertIsNone(plan['afterRevertHuman'])
        self.assertEqual(plan['customizations'][0]['kind'], 'selection-or-order')

    def test_failed_gate_stops_and_reverts(self):
        self.mock['telemetry'][0] = 310
        proc, record = self.engine()
        self.assertNotEqual(proc.returncode, 0)
        # Preflight checks the store, applies stock, then gates power, so a tuned
        # profile left live is replaced before the gate rather than failing it.
        self.assertEqual([s['type'] for s in record['steps']],
                         ['gate-hash', 'apply-profile', 'gate-power'])
        self.assertEqual(record['steps'][2]['verdict'], 'FAIL')
        self.assertEqual(record['revert']['coreMhz'], 1763)
        self.assertTrue(record['finalState']['logging']['stoppedVerified'])

    def test_final_check_stops_mocked_running_hwinfo_log(self):
        self.mock['finalLoggingStillRunning'] = True
        proc, record = self.engine()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['status'], 'PASS')
        self.assertEqual(record['finalState']['logging']['status'], 'stopped')
        self.assertTrue(record['finalState']['logging']['stopAttempted'])
        self.assertTrue(record['finalState']['logging']['stoppedVerified'])

    def test_final_check_fails_if_mocked_log_cannot_stop(self):
        self.mock['finalLoggingStillRunning'] = True
        self.mock['finalLoggingStopFails'] = True
        proc, record = self.engine()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(record['status'], 'FAIL')
        self.assertEqual(record['finalState']['logging']['status'], 'running')
        self.assertFalse(record['finalState']['logging']['stoppedVerified'])

    def test_estimate_fresh_mid_resume_overrun_and_skipped_steps(self):
        plan = {'runs': [
            {'id': 'a', 'minutes': 2, 'steps': [{'id': 'one', 'estimatedMinutes': 2}]},
            {'id': 'b', 'minutes': 7, 'steps': [
                {'id': 'one', 'estimatedMinutes': 3}, {'id': 'two', 'estimatedMinutes': 4}]},
        ]}
        now = '2026-09-23T19:00:00'
        old = '2026-09-23T18:00:00'
        passed_a = {'key': 'a/one', 'verdict': 'PASS', 'start': '2026-09-23T18:40:00'}
        passed_b = {'key': 'b/one', 'verdict': 'PASS', 'start': '2026-09-23T18:45:00'}
        running = {'key': 'b/one', 'verdict': 'RUNNING', 'start': '2026-09-23T18:59:00'}
        cases = [
            ({'start': now, 'attemptStart': now, 'resumeRunId': '', 'steps': []}, 9, False),
            ({'start': '2026-09-23T18:40:00', 'attemptStart': '2026-09-23T18:40:00', 'resumeRunId': '',
              'steps': [passed_a, running]}, 6, False),
            ({'start': old, 'attemptStart': '2026-09-23T18:59:00', 'resumeRunId': 'b',
              'steps': [passed_a, passed_b,
                        {'key': 'b/one', 'verdict': 'RUNNING', 'start': '2026-09-23T18:30:00'},
                        running]}, 6, False),
            ({'start': old, 'attemptStart': '2026-09-23T18:45:00', 'resumeRunId': 'b',
              'steps': [passed_a, {**running, 'start': '2026-09-23T18:50:00'}]}, 4, True),
            ({'start': now, 'attemptStart': now, 'resumeRunId': '',
              'steps': [passed_a, passed_b]}, 4, False),
        ]
        for record, expected, overrun in cases:
            with self.subTest(record=record):
                value = self.display(f"Get-BenchEstimate $plan $record ([datetime]'{now}')",
                                     plan=plan, record=record)
                self.assertAlmostEqual(value['remainingMinutes'], expected)
                self.assertEqual(value['stepOverrun'], overrun)
                self.assertEqual(value['stepFinish'] is None, overrun or not any(
                    step['verdict'] == 'RUNNING' for step in record['steps']))

    def test_reading_formatter_labels_units_and_missing_fields(self):
        full = self.display("Format-BenchReadings '2572, 13801, 176.86, 62, 99' '0.720' $true")
        self.assertEqual(full, 'Core 2572 MHz   Memory 13801 MHz   Power 176.9 W   Temp 62 C   Util 99%   Voltage 0.720 V')
        missing = self.display("Format-BenchReadings '2572,,bad,62' '0.720' $false")
        self.assertEqual(missing, 'Core 2572 MHz   Memory -- MHz   Power -- W   Temp 62 C   Util --%')
        self.assertNotIn('Voltage', missing)

    def test_status_caption_value_and_color_for_each_state(self):
        names = ['Ready', 'Running', 'Pause requested', 'Paused', 'Stop requested',
                 'Stopping and reverting', 'PASS', 'FAIL']
        expression = "@('Ready','Running','Pause requested','Paused','Stop requested','Stopping and reverting','PASS','FAIL') | ForEach-Object { Get-BenchStatus $_ }"
        values = self.display(expression)
        self.assertEqual([item['value'] for item in values], names)
        self.assertTrue(all(item['caption'] == 'Status:' for item in values))
        self.assertEqual(values[-2]['color'], 'Green')
        self.assertEqual(values[-1]['color'], 'Red')

    def test_stock_drift_gate_fails_and_reverts(self):
        # A blocking gate (the default) stops the session and reverts.
        plan = copy.deepcopy(self.catalog)
        for run in plan['runs']:
            for step in run['steps']:
                step.pop('blocking', None)
        self.mock['driftPct'] = 1.6
        proc, record = self.engine(plan)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('stock-4/stock-return', [s['key'] for s in record['steps'] if s['verdict'] == 'FAIL'])
        self.assertEqual(record['revert']['coreMhz'], 1763)

    def test_nonblocking_drift_gate_records_and_continues(self):
        # Session D's gates are non-blocking so an unattended session runs to the end; the breach
        # is recorded, and the scorer applies the same 1.5% rule afterwards.
        self.mock['driftPct'] = 1.6
        proc, record = self.engine()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(record['status'], 'PASS')
        gates = [s for s in record['steps'] if s['key'].endswith('/stock-return')]
        self.assertEqual([g['key'] for g in gates], ['stock-4/stock-return', 'stock-6/stock-return'])
        self.assertTrue(all(g['witness']['exceeded'] for g in gates))
        self.assertIn('Recorded; not stopping.', proc.stdout)

    def test_stock_clocks_after_applied_profile_fail_witness(self):
        self.mock['witnesses']['3']['core'] = 1763
        proc, record = self.engine()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('edit2-3/witness', [s['key'] for s in record['steps'] if s['verdict'] == 'FAIL'])
        failed = [s for s in record['steps'] if s['key'] == 'edit2-3/witness'][0]
        self.assertEqual(failed['witness']['coreMhz'], 1763)
        self.assertEqual(record['revert']['coreMhz'], 1763)

    def test_hwinfo_fallback_records_manual_path(self):
        self.mock['hwinfoStartFail'] = True
        proc, record = self.engine()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        starts = [s for s in record['steps'] if s['type'] == 'hwinfo-start']
        self.assertTrue(starts)
        self.assertTrue(all(s['witness']['mode'] == 'manual' for s in starts))
        self.assertIn('hwinfo-rtx3070ti-sessiond-stock-1', starts[0]['witness']['path'])

    def test_resume_after_interrupted_suite_keeps_old_attempt(self):
        self.mock['failSuite'] = True
        first, old = self.engine()
        self.assertNotEqual(first.returncode, 0)
        self.assertEqual(old['status'], 'FAIL')
        self.mock['failSuite'] = False
        second, record = self.engine(resume=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(record['status'], 'PASS')
        self.assertTrue(any(s['verdict'] == 'FAIL' for s in record['steps']))
        paths = [s['witness']['path'] for s in record['steps']
                 if s['type'] == 'hwinfo-start' and s['verdict'] == 'PASS']
        self.assertTrue(any('-resume-' in p for p in paths))
        self.assertEqual(len(paths), len(set(paths)))

    def test_second_resume_reruns_a_run_whose_latest_attempt_failed(self):
        # GPT Job 93, R2: a run's log-stop fails, then on resume its suite fails. Its historical
        # PASS entries now number as many as its steps, so counting them called the run complete
        # and a second resume skipped it, leaving a failed suite as its latest attempt.
        self.mock['failHwinfoStop'] = True
        first, _ = self.engine()
        self.assertNotEqual(first.returncode, 0)
        self.mock['failHwinfoStop'] = False
        self.mock['failSuite'] = True
        second, _ = self.engine(resume=True)
        self.assertNotEqual(second.returncode, 0)
        self.mock['failSuite'] = False
        third, record = self.engine(resume=True)
        self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
        latest = {}
        for step in record['steps']:
            latest[step['key']] = step['verdict']
        self.assertEqual({k: v for k, v in latest.items() if v != 'PASS'}, {})
        self.assertEqual(record['status'], 'PASS')

    def test_refuses_session_overwrite(self):
        first, _ = self.engine()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second, record = self.engine()
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('Refusing to overwrite session', second.stdout)
        self.assertEqual(record['status'], 'PASS')

    def test_validator_rejects_malformed_plans(self):
        mutations = []
        def altered(change):
            p = copy.deepcopy(self.catalog)
            change(p)
            mutations.append(p)
        altered(lambda p: p['runs'][0]['steps'][0].update(type='unknown'))
        altered(lambda p: p.pop('volumeLabel'))
        altered(lambda p: p['revert']['witness'].pop('memoryMax'))
        altered(lambda p: p['runs'][0]['steps'][2].pop('limit'))
        altered(lambda p: p['runs'][0]['steps'][0].update(path='Profiles/VEN.cfg'))
        altered(lambda p: p['runs'][1]['steps'].pop(2))  # suite with no start
        altered(lambda p: p['runs'][2]['steps'][1].update(path=p['runs'][1]['steps'][2]['path']))
        altered(lambda p: p['runs'][5]['steps'][1].update(minMhz=50))
        altered(lambda p: p['runs'][5]['steps'][1].update(maxMhz=3000))
        altered(lambda p: p['runs'][5]['steps'][1].update(iterations=[120, 200]))
        altered(lambda p: p['runs'][5]['steps'][1].update(workload='gemm;calc'))
        altered(lambda p: p['runs'][2]['steps'][0].update(type='hwinfo-start', path='relative.csv'))
        altered(lambda p: p['runs'][0]['steps'][3].update(maxUtil=0))
        altered(lambda p: p['runs'][1]['steps'][0].update(slot=0))
        altered(lambda p: p['runs'][1]['steps'][1].pop('memoryMax'))
        altered(lambda p: p['runs'][1]['steps'][1].update(coreMax=3000))
        altered(lambda p: p['runs'][1]['steps'].pop(1))  # applied profile without a witness
        altered(lambda p: p['runs'][1]['steps'][2].update(path='relative.csv'))
        altered(lambda p: p['runs'][1]['steps'][2].update(path='C:/Temp/hwinfo.csv'))
        altered(lambda p: p['runs'][1]['steps'][4].update(type='hwinfo-start', path='kit:/results/extra.csv'))
        altered(lambda p: p['runs'][1]['steps'][3].pop('settings'))
        altered(lambda p: p['runs'][5]['steps'][1].pop('output'))
        altered(lambda p: p['runs'][5]['steps'][1].update(output='C:/Temp/sweep'))
        altered(lambda p: p['runs'][0]['steps'][5].update(instruction=''))
        altered(lambda p: p['runs'][1]['steps'].insert(3, {'id':'bad-profile','type':'apply-profile','name':'Bad','slot':1}))
        altered(lambda p: p['runs'].insert(2, p['runs'].pop(5)))
        altered(lambda p: p['runs'].insert(1, p['runs'].pop(-1)))
        altered(lambda p: p['runs'].pop(0))
        for i, plan in enumerate(mutations):
            with self.subTest(mutation=i):
                proc = self.validate(plan)
                self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_all_scripts_parse_and_are_ascii(self):
        scripts = sorted(APP.glob('*.ps1'))
        for script in scripts:
            with self.subTest(script=script.name):
                self.assertTrue(script.read_bytes().isascii())
                quoted = str(script).replace("'", "''")
                command = f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{quoted}',[ref]$null,[ref]$e); if($e.Count){{exit 1}}"
                # 60 s, not 10: a cold pwsh start on the Ubuntu runner took over 10 s twice on 2026-10-06
                # (runs 37492019240, 37511221835) while the parse itself is instant.
                proc = subprocess.run([PS, '-NoProfile', '-Command', command], capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_hwinfo_voltage_reader_handles_duplicate_headers_and_footer(self):
        source = ROOT / 'data' / 'frequency-sweeps' / 'rtx3070ti-20260825' / 'hwinfo-oc' / 'hwinfo-oc-membw-matched2130.csv'
        if not source.exists():
            self.skipTest('HWiNFO fixture is unavailable')
        with source.open(encoding='cp1252', newline='') as f:
            rows = list(csv.reader(f))
        column = [i for i, name in enumerate(rows[0]) if name.startswith('GPU Core Voltage')]
        self.assertEqual(len(column), 1)
        actual_rows = [r for r in rows[1:] if len(r) == len(rows[0]) and r[0] != 'Date' and r[0]]
        expected = float(actual_rows[-1][column[0]])
        helper = str(APP / 'Hwinfo-Csv.ps1').replace("'", "''")
        data = str(source).replace("'", "''")
        command = f". '{helper}'; Get-HwinfoCoreVoltage '{data}'"
        args = [PS, '-NoProfile']
        if os.name == 'nt':
            args += ['-ExecutionPolicy', 'Bypass']
        proc = subprocess.run(args + ['-Command', command], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertAlmostEqual(float(proc.stdout.strip()), expected)

    def read_voltage(self, header, rows):
        path = self.dir / 'igpu.csv'
        with path.open('w', encoding='cp1252', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        helper = str(APP / 'Hwinfo-Csv.ps1').replace("'", "''")
        data = str(path).replace("'", "''")
        args = [PS, '-NoProfile']
        if os.name == 'nt':
            args += ['-ExecutionPolicy', 'Bypass']
        return subprocess.run(args + ['-Command', f". '{helper}'; Get-HwinfoCoreVoltage '{data}'"],
                              capture_output=True, text=True, timeout=20)

    def test_hwinfo_voltage_reader_ignores_integrated_gpu_column(self):
        # The first live run, 2026-09-23, on a Ryzen 9700X: its Radeon iGPU adds
        # "GPU Core Voltage (VDDCR_GFX) [V]" beside the NVIDIA "GPU Core Voltage [V]". The reader
        # demanded exactly one prefix match and failed every sample. Worse, the iGPU read 0.725 V,
        # inside the 5060 Ti witness window, so picking it would have passed on the wrong GPU.
        header = ['Date', 'Time', 'GPU Core Voltage (VDDCR_GFX) [V]', 'GPU Clock [MHz]',
                  'GPU Core Voltage [V]', 'GPU Clock [MHz]']
        rows = [['23.9.2026', '18:51:0%d' % i, '0.725', '600.0', '0.720', '1537.0'] for i in range(5)]
        proc = self.read_voltage(header, rows)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertAlmostEqual(float(proc.stdout.strip()), 0.720)

    def test_hwinfo_voltage_reader_picks_the_loaded_gpu_among_same_named_columns(self):
        header = ['Date', 'Time', 'GPU Core Voltage [V]', 'GPU Clock [MHz]',
                  'GPU Core Voltage [V]', 'GPU Clock [MHz]']
        rows = [['23.9.2026', '18:51:0%d' % i, '0.900', '350.0', '0.720', '1537.0'] for i in range(5)]
        proc = self.read_voltage(header, rows)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertAlmostEqual(float(proc.stdout.strip()), 0.720)

    def test_hwinfo_manual_fallback_requires_file_growth(self):
        path = self.dir / 'log.csv'
        path.write_text('Date,Voltage\n', encoding='ascii')
        helper = str(APP / 'Hwinfo-Csv.ps1').replace("'", "''")
        data = str(path).replace("'", "''")
        command = f". '{helper}'; Assert-HwinfoLogGrowth '{data}' -FirstDelayMs 150 -SecondDelayMs 150"
        args = [PS, '-NoProfile']
        if os.name == 'nt':
            args += ['-ExecutionPolicy', 'Bypass']
        frozen = subprocess.run(args + ['-Command', command], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(frozen.returncode, 0)
        self.assertIn('not growing', frozen.stderr + frozen.stdout)
        # A real HWiNFO log grows continuously. A single append at a fixed delay raced PowerShell 7's
        # slower start on Linux CI (the append landed before the first size read), so append
        # every 100 ms for as long as the check runs.
        done = threading.Event()
        def append():
            while not done.is_set():
                with path.open('a', encoding='ascii') as f:
                    f.write('2026-09-23,0.85\n')
                time.sleep(0.1)
        thread = threading.Thread(target=append)
        thread.start()
        try:
            growing_command = f". '{helper}'; Assert-HwinfoLogGrowth '{data}' -FirstDelayMs 200 -SecondDelayMs 1200"
            growing = subprocess.run(args + ['-Command', growing_command], capture_output=True, text=True, timeout=10)
        finally:
            done.set()
            thread.join()
        self.assertEqual(growing.returncode, 0, growing.stdout + growing.stderr)

    def test_stock_drift_uses_median_absolute_matched_target_change(self):
        first = self.dir / 'first'
        last = self.dir / 'last'
        first.mkdir(); last.mkdir()
        names = ['target_frequency_mhz', 'achieved_frequency_avg', 'bench_throughput']
        for directory, factor in [(first, lambda i: 1.0),
                                  (last, lambda i: 1.01 if i < 6 else 1.016)]:
            with (directory / 'run-gemm_sweep.csv').open('w', newline='', encoding='ascii') as file:
                writer = csv.DictWriter(file, fieldnames=names)
                writer.writeheader()
                for i in range(13):
                    target = 855 + i * 105
                    writer.writerow({'target_frequency_mhz': target,
                                     'achieved_frequency_avg': target + (3 if directory == first else -3),
                                     'bench_throughput': 100 * factor(i)})
        helper = str(APP / 'Stock-Drift.ps1').replace("'", "''")
        a = str(first).replace("'", "''")
        b = str(last).replace("'", "''")
        command = f". '{helper}'; Measure-StockDrift '{a}' '{b}' @('gemm') | ConvertTo-Json -Compress"
        args = [PS, '-NoProfile']
        if os.name == 'nt':
            args += ['-ExecutionPolicy', 'Bypass']
        proc = subprocess.run(args + ['-Command', command], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        measured = json.loads(proc.stdout)
        self.assertAlmostEqual(measured['worstMedianAbsPct'], 1.6, places=6)
        self.assertAlmostEqual(measured['perWorkload']['gemm'], 1.6, places=6)

    def test_stock_drift_takes_its_point_count_from_the_sweep(self):
        # Session E2 (2026-09-27) sweeps a fixed 12-target list. A hard-coded 13 failed its gate
        # after all three suites had collected; the mock engine never wrote a 12-point CSV.
        def drift(count_first, count_last, changes):
            first = self.dir / f'f{count_first}{count_last}'
            last = self.dir / f'l{count_first}{count_last}'
            first.mkdir(); last.mkdir()
            names = ['target_frequency_mhz', 'achieved_frequency_avg', 'bench_throughput']
            for directory, count, factor in [(first, count_first, lambda i: 1.0),
                                             (last, count_last, lambda i: 1 + changes[i] / 100)]:
                with (directory / 'run-copy_sweep.csv').open('w', newline='', encoding='ascii') as file:
                    writer = csv.DictWriter(file, fieldnames=names)
                    writer.writeheader()
                    for i in range(count):
                        target = 855 + i * 105
                        writer.writerow({'target_frequency_mhz': target, 'achieved_frequency_avg': target,
                                         'bench_throughput': 100 * factor(i)})
            helper = str(APP / 'Stock-Drift.ps1').replace("'", "''")
            command = (f". '{helper}'; Measure-StockDrift '{str(first)}' '{str(last)}' @('copy') "
                       "| ConvertTo-Json -Compress")
            args = [PS, '-NoProfile']
            if os.name == 'nt':
                args += ['-ExecutionPolicy', 'Bypass']
            return subprocess.run(args + ['-Command', command], capture_output=True, text=True, timeout=10)
        # Twelve points: the median is the mean of the 6th and 7th, as statistics.median gives.
        changes = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
        proc = drift(12, 12, changes)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertAlmostEqual(json.loads(proc.stdout)['worstMedianAbsPct'], 0.7, places=6)
        proc = drift(12, 11, changes)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('same number of points', proc.stdout + proc.stderr)

    def test_pmon_gate_sums_processes_and_checks_video_engines(self):
        helper = str(APP / 'Pmon-Gate.ps1').replace("'", "''")
        command = (f". '{helper}'; "
                   "$rows=@('0 101 C 3 0 0 0 - - a','0 202 C 3 0 0 0 - - b',"
                   "'0 101 C 2 0 1 0 - - a','0 202 C 1 0 0 0 - - b'); "
                   "Measure-PmonQuiet $rows | ConvertTo-Json -Compress")
        args = [PS, '-NoProfile']
        if os.name == 'nt':
            args += ['-ExecutionPolicy', 'Bypass']
        proc = subprocess.run(args + ['-Command', command], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        measured = json.loads(proc.stdout)
        self.assertEqual(measured['maxSm'], 6)
        self.assertEqual(measured['maxEncoder'], 1)
        self.assertEqual(measured['maxDecoder'], 0)
        self.assertEqual(measured['samples'], 2)

    def test_sync_kit_lists_every_runtime_file(self):
        kit = self.dir / 'headroom-kit'
        (kit / 'python').mkdir(parents=True)
        (kit / 'python' / 'python.exe').write_bytes(b'fixture')
        cmd = [PS, '-NoProfile']
        if os.name == 'nt':
            cmd += ['-ExecutionPolicy', 'Bypass']
        cmd += ['-File', str(ROOT / 'tools' / 'collection-kit' / 'Sync-Kit.ps1'),
                '-KitPath', str(kit), '-WhatIfOnly']
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for file in ['RUN-BENCH.bat', 'Run-Plan.ps1', 'Bench-Window.ps1', 'Bench-Display.ps1',
                     'Run-Child.ps1', 'Test-Plan.ps1', 'New-Plan.ps1',
                     'Hwinfo-Csv.ps1', 'Stock-Drift.ps1', 'Pmon-Gate.ps1', 'sessiond-3070ti.json', 'sessione-2060s.json', 'sessiond2-3070ti.json', 'sessione2-2060s.json', 'build_sessione2.py',
                     'Invoke-HwinfoLogging.ps1', 'Write-Atomic.ps1', 'Profile-Hash.ps1', 'Card-Checks.ps1',
                     'newcard-rtx40-50.json', 'build_newcard.py', 'Desktop-Load.ps1',
                     'check_desktop_load.py']:
            self.assertIn(file, proc.stdout)

    def desktop_fixture(self, fps=31, bus=0, header=None, sample_values=None):
        directory = self.dir / 'desktop fixtures with spaces'
        directory.mkdir(exist_ok=True)
        header = header or ['Date', 'Time', 'GPU Clock [MHz]', 'GPU Bus Load [%]',
                            'GPU Clock [MHz]', 'GPU Crossbar Clock [MHz]', 'GPU Bus Load [%]',
                            'Framerate Presented (avg) [FPS]']
        # The iGPU is deliberately busier than NVIDIA. Only NVIDIA bus load counts.
        values = sample_values or [[10, bus, fps], [90, bus, fps]]
        stamp = datetime.datetime(2026, 10, 3, 12, tzinfo=datetime.timezone(datetime.timedelta(hours=-7)))
        log = directory / 'suite-log.csv'
        with log.open('w', newline='', encoding='latin-1') as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            # Outside-window load must not contaminate the screen.
            for second, igpu, nvidia, presented in [(-2, 95, 99, 200), (1, *values[0]), (2, *values[1]), (5, 95, 99, 200)]:
                local = stamp + datetime.timedelta(seconds=second)
                readings = ['100', str(igpu), '1500', '1400', str(nvidia), str(presented)]
                writer.writerow([local.strftime('%d.%m.%Y'), local.strftime('%H:%M:%S.%f'), *readings])
            writer.writerow(header)  # HWiNFO repeats its header.
            writer.writerow(['03.10.2026', '12:00:01.500', 'partial'])
        files = []
        for name in ('gemm', 'membw'):
            path = directory / f'run_{name}_sweep.csv'
            with path.open('w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.DictWriter(handle, fieldnames=['target_frequency_mhz', 'achieved_clock_mhz',
                                                           'window_start_unix', 'window_end_unix'])
                writer.writeheader()
                writer.writerow(dict(target_frequency_mhz=1545, achieved_clock_mhz=1537.2,
                                     window_start_unix=stamp.timestamp(), window_end_unix=stamp.timestamp()+3))
            files.append(str(path))
        return dict(sweepFiles=files, log=str(log), utcOffset='-07:00')

    def desktop_check(self, fixture):
        proc = self.ps_command(
            f". '{str(APP / 'Desktop-Load.ps1').replace(chr(39), chr(39)*2)}'; "
            f"$f=Get-Content '{str(self.write('desktop-input.json', fixture)).replace(chr(39), chr(39)*2)}' -Raw | ConvertFrom-Json; "
            f"Invoke-BenchDesktopCheck '{str(Path(sys.executable)).replace(chr(39), chr(39)*2)}' "
            f"'{str(APP / 'check_desktop_load.py').replace(chr(39), chr(39)*2)}' "
            "$f.sweepFiles $f.log $f.utcOffset | ConvertTo-Json -Depth 12 -Compress")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def desktop_plan(self, fixture):
        plan = copy.deepcopy(self.catalog)
        plan['card'].pop('legacyDerivedGrids', None)
        source = plan['runs'][1]
        source['requires'] = []
        source['steps'] = [s for s in source['steps'] if s['type'] in ('hwinfo-start', 'suite', 'hwinfo-stop')]
        source['steps'].append(dict(id='after-check', name='Following step', type='human', instruction='Later work.'))
        plan['runs'] = [source]
        label = next(s['label'] for s in source['steps'] if s['type'] == 'suite')
        self.mock['desktopLoadFixtures'] = {label: fixture}
        self.mock['desktopCheckPython'] = sys.executable
        return plan

    def test_desktop_screen_uses_nvidia_window_medians_and_all_suite_files(self):
        result = self.desktop_check(self.desktop_fixture(fps=30, bus=10))
        self.assertEqual(result['status'], 'quiet')  # Equality is not above either threshold.
        self.assertEqual(result['checked'], 2)
        self.assertEqual(result['busColumnIndex'], 6)
        self.assertTrue(all(w['busMedian'] == 10 and w['fpsMedian'] == 30 for w in result['windows']))
        self.assertTrue(all(w['fpsSamples'] == 2 for w in result['windows']))
        result = self.desktop_check(self.desktop_fixture(fps=31, bus=0))
        self.assertEqual(result['status'], 'DESKTOP LOAD')
        self.assertEqual(result['flagged'], 2)
        # Framerate alone flags when it is logged (2026-10-03): kernels reach 13-36% bus load by
        # themselves on a quiet desktop, so 11% at a quiet framerate is reported, not flagged.
        result = self.desktop_check(self.desktop_fixture(fps=0, bus=11))
        self.assertEqual(result['status'], 'quiet')
        self.assertEqual(result['flagged'], 0)
        result = self.desktop_check(self.desktop_fixture(sample_values=[[90, 0, 0], [90, 22, 62]]))
        self.assertEqual(result['windows'][0]['fpsMedian'], 31)  # Even-sample median, not either sample.
        self.assertEqual(result['windows'][0]['busMedian'], 11)

    def test_desktop_missing_columns_windows_and_nonfinite_samples_are_unchecked(self):
        fixture = self.desktop_fixture()
        Path(fixture['log']).write_text('Date,Time,Temperature\n03.10.2026,12:00:01.000,55\n', encoding='ascii')
        self.assertEqual(self.desktop_check(fixture)['status'], 'unchecked')
        # Partial coverage remains unchecked even when the other workload is quiet.
        fixture = self.desktop_fixture(fps=0, bus=0)
        Path(fixture['sweepFiles'][0]).write_text('target_frequency_mhz,window_start_unix,window_end_unix\n1545,,\n', encoding='ascii')
        result = self.desktop_check(fixture)
        self.assertEqual(result['status'], 'unchecked')
        self.assertEqual((result['checked'], result['unchecked']), (1, 1))
        fixture = self.desktop_fixture(fps='NaN', bus='inf')
        self.assertEqual(self.desktop_check(fixture)['status'], 'unchecked')
        fixture['utcOffset'] = '+00:00'  # No matching local-time samples.
        self.assertEqual(self.desktop_check(fixture)['status'], 'unchecked')
        Path(fixture['log']).unlink()
        self.assertEqual(self.desktop_check(fixture)['status'], 'unchecked')

    def appended_column_log(self, fixture, closing):
        """Rewrite the fixture's log the way HWiNFO wrote the 2026-10-17 practice run's: the opening
        header ends in an empty cell, rows from second 2 on carry one extra trailing value, and the
        log may close with a repeated header (`closing`, or none when None)."""
        header = ['Date', 'Time', 'GPU Clock [MHz]', 'GPU Bus Load [%]', 'GPU Clock [MHz]',
                  'GPU Crossbar Clock [MHz]', 'GPU Bus Load [%]', 'Framerate Presented (avg) [FPS]', '']
        stamp = datetime.datetime(2026, 10, 3, 12, tzinfo=datetime.timezone(datetime.timedelta(hours=-7)))
        with Path(fixture['log']).open('w', newline='', encoding='latin-1') as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for second in (1, 2):
                local = stamp + datetime.timedelta(seconds=second)
                row = [local.strftime('%d.%m.%Y'), local.strftime('%H:%M:%S.%f'), '100', '10', '1500', '1400',
                       '0', '20', '']
                if second == 2:
                    row[-1:] = ['2100', '']   # the new sensor's value, then the trailing empty cell
                writer.writerow(row)
            if closing is not None:
                writer.writerow(closing)

    def test_desktop_screen_reads_rows_with_columns_appended_mid_log_only_when_proven(self):
        names = ['Date', 'Time', 'GPU Clock [MHz]', 'GPU Bus Load [%]', 'GPU Clock [MHz]',
                 'GPU Crossbar Clock [MHz]', 'GPU Bus Load [%]', 'Framerate Presented (avg) [FPS]']
        fixture = self.desktop_fixture()
        # Proven: the closing header keeps every opening name in place and adds one at the end.
        self.appended_column_log(fixture, names + ['GPU Clock (Effective) [MHz]', ''])
        result = self.desktop_check(fixture)
        self.assertEqual(result['status'], 'quiet')
        self.assertEqual(result['appendedColumns'], ['GPU Clock (Effective) [MHz]'])
        self.assertTrue(all(w['fpsSamples'] == 2 for w in result['windows']))
        # Not proven: no closing header, so the longer row is refused and the refusal is reported.
        self.appended_column_log(fixture, None)
        result = self.desktop_check(fixture)
        self.assertEqual(result['refusedLongerRows'], 1)
        self.assertTrue(all(w['fpsSamples'] == 1 for w in result['windows']))
        self.assertIn('no closing header proves', result['reason'])
        # A repeated header whose names moved (a column inserted mid-row) makes every position in the
        # log untrustworthy, so the whole log is refused (GPT Job 107, F2-F3), not just the longer rows.
        self.appended_column_log(fixture, names[:4] + ['Inserted [MHz]'] + names[4:] + [''])
        result = self.desktop_check(fixture)
        self.assertEqual(result['status'], 'unchecked')
        self.assertIn('does not keep the opening column names in place', result['reason'])
        self.assertEqual(result['windows'], [])
        self.assertNotIn('appendedColumns', result)
        # A sensor-group label line after the closing header is not a refused sample (Job 107, F6).
        self.appended_column_log(fixture, None)
        with Path(fixture['log']).open('a', newline='', encoding='latin-1') as handle:
            csv.writer(handle).writerow(['', '', 'Memory', 'GPU [#0]: NVIDIA', '', '', '', '', '', 'extra'])
        self.assertEqual(self.desktop_check(fixture)['refusedLongerRows'], 1)

    def test_desktop_snapshot_preserves_foreground_and_distinct_pids(self):
        self.mock['desktopSnapshot'] = dict(foreground=dict(pid=42, process='renderer', title='Window title'), samples=[
            dict(InstanceName=f'pid_{pid}_luid_0_phys_0_eng_0_engtype_{engine}', CookedValue=value)
            for pid, engine, value in [(42, '3D', .8), (42, '3D', .4), (43, '3D', .6),
                                       (43, '3D', .2), (44, 'Copy', .1), (44, 'Copy', .1)]])
        proc, record = self.engine()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        snapshot = record['desktopPreflights'][0]['snapshot']
        self.assertEqual(snapshot['foreground']['title'], 'Window title')
        self.assertEqual([u['pid'] for u in snapshot['gpuUsers']], [42, 43])
        self.assertAlmostEqual(snapshot['gpuUsers'][0]['percent'], .6)
        self.mock['desktopSnapshot']['counterError'] = 'Counters unavailable.'
        proc, record = self.engine(session=self.dir / 'counter-missing.json')
        snapshot = record['desktopPreflights'][0]['snapshot']
        self.assertEqual(snapshot['foreground']['pid'], 42)
        self.assertIn('Counters unavailable.', snapshot['errors'][0])

    def test_renderer_list_defaults_and_plan_generation_and_exact_window_selection(self):
        catalog = json.loads((APP / 'catalog/localtest-5060ti.json').read_text(encoding='utf-8'))
        self.assertEqual(catalog['minimizeKnownRenderers'], ['claude'])
        plan = copy.deepcopy(self.catalog)
        plan['minimizeKnownRenderers'] = ['claude']
        self.mock['rendererWindows'] = [dict(pid=1, process='claude', handle=100, alreadyMinimized=False),
                                        dict(pid=2, process='claude', handle=200, alreadyMinimized=True),
                                        dict(pid=3, process='other', handle=300, alreadyMinimized=False)]
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        minimized = record['desktopPreflights'][0]['minimizeKnownRenderers']
        self.assertEqual([w['handle'] for w in minimized['windows']], [100, 200])
        self.assertTrue(all(w['minimizedVerified'] for w in minimized['windows']))
        proc, record = self.engine(session=self.dir / 'no-renderers.json')
        self.assertEqual(record['desktopPreflights'][0]['minimizeKnownRenderers']['names'], [])
        self.assertEqual(record['desktopPreflights'][0]['minimizeKnownRenderers']['windows'], [])
        queue = self.write('renderer-queue.json', dict(runs=plan['runs']))
        catalog_path = self.write('renderer-catalog.json', plan)
        output = self.dir / 'renderer-plan.json'
        made = self.ps('New-Plan.ps1', '-CatalogPath', catalog_path, '-QueuePath', queue, '-OutputPath', output)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['minimizeKnownRenderers'], ['claude'])
        for invalid in ('claude', ['*'], ['claude.exe'], ['HWiNFO64'], [42]):
            bad = copy.deepcopy(plan)
            bad['minimizeKnownRenderers'] = invalid
            self.assertNotEqual(self.validate(bad).returncode, 0)
        plan['runs'][0]['steps'].insert(0, dict(id='minimize', name='Minimize known renderers', type='minimize-known-renderers'))
        self.assertEqual(self.validate(plan).returncode, 0)
        self.mock['rendererWindows'][0]['fail'] = True
        proc, record = self.engine(plan, session=self.dir / 'minimize-failure.json')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('Could not verify minimized window', record['desktopPreflights'][0]['minimizeKnownRenderers']['errors'][0])
        explicit = next(s for s in record['steps'] if s['type'] == 'minimize-known-renderers')
        self.assertFalse(explicit['witness']['windows'][0]['minimizedVerified'])

    def test_desktop_native_declarations_compile_without_calling_windows(self):
        helper = str(APP / 'Desktop-Load.ps1').replace("'", "''")
        proc = self.ps_command(f". '{helper}'; Initialize-BenchWindows; 'HeadroomBench.Desktop' -as [type] | ForEach-Object FullName")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.strip(), 'HeadroomBench.Desktop')

    def test_desktop_screen_checks_a_single_available_column_and_reports_partial_errors(self):
        fixture = self.desktop_fixture()
        log = Path(fixture['log'])
        for column, value, status in [('Framerate Presented (avg) [FPS]', 30, 'quiet'),
                                      ('Framerate Presented (avg) [FPS]', 31, 'DESKTOP LOAD'),
                                      ('GPU Bus Load [%]', 11, 'DESKTOP LOAD')]:
            log.write_text(f'Date,Time,{column}\n03.10.2026,12:00:01.000,{value}\n', encoding='ascii')
            self.assertEqual(self.desktop_check(fixture)['status'], status)
        fixture['sweepFiles'][1] = str(self.dir / 'missing_sweep.csv')
        result = self.desktop_check(fixture)
        self.assertEqual(result['status'], 'DESKTOP LOAD')
        self.assertEqual(result['flagged'], 1)
        self.assertIn('reason', result)

    def test_custom_sweep_receives_the_same_desktop_check(self):
        # Framerate flags since 2026-10-03; bus load alone no longer does.
        fixture = self.desktop_fixture(fps=31, bus=0)
        fixture['sweepFiles'] = fixture['sweepFiles'][:1]
        plan = self.desktop_plan(fixture)
        source = next(s for s in self.catalog['runs'][5]['steps'] if s['type'] == 'sweep')
        source = copy.deepcopy(source)
        source['label'] = next(s['label'] for s in plan['runs'][0]['steps'] if s['type'] == 'suite')
        plan['runs'][0]['steps'][1] = source
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        measured = next(s for s in record['steps'] if s['type'] == 'sweep')
        self.assertEqual(measured['desktopLoad']['status'], 'DESKTOP LOAD')
        self.assertEqual(measured['desktopLoad']['flagged'], 1)

    def test_desktop_result_is_recorded_per_step_and_survives_continue(self):
        fixture = self.desktop_fixture()
        plan = self.desktop_plan(fixture)
        proc, record = self.engine(plan)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIsNotNone(record, proc.stdout + proc.stderr)
        measured = next(s for s in record['steps'] if s['type'] == 'suite')
        self.assertEqual(measured['verdict'], 'DESKTOP LOAD')
        self.assertEqual(measured['desktopLoad']['flagged'], 2)
        self.assertEqual(measured['desktopLoad']['acknowledgedBy'], 'operator')
        self.assertEqual(record['steps'][-1]['verdict'], 'PASS')
        self.assertEqual(record['status'], 'FAIL')
        self.assertIn('ACTION NEEDED: DESKTOP LOAD', proc.stdout)
        self.assertTrue(record['finalState']['clocks']['verified'])
        fixture = self.desktop_fixture(fps=0, bus=0)
        plan = self.desktop_plan(fixture)
        proc, record = self.engine(plan, resume=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        replacements = [s for s in record['steps'] if s['type'] == 'suite']
        self.assertEqual([s['desktopLoad']['status'] for s in replacements], ['DESKTOP LOAD', 'quiet'])
        self.assertEqual(record['operatorState'], 'Stopping and reverting')
        self.assertIsNone(record['operatorMessage'])
        self.assertEqual(record['desktopPreflights'][-2]['key'], 'session-start')
        proc, record = self.engine(plan, session=self.dir / 'quiet-desktop.json')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(next(s for s in record['steps'] if s['type'] == 'suite')['desktopLoad']['status'], 'quiet')
        Path(fixture['log']).write_text('Date,Time\n', encoding='ascii')
        proc, record = self.engine(plan, session=self.dir / 'unchecked-desktop.json')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(next(s for s in record['steps'] if s['type'] == 'suite')['desktopLoad']['status'], 'unchecked')

    def test_desktop_pause_waits_for_fresh_continue_or_stop(self):
        for action in ('continue', 'stop'):
            with self.subTest(action=action):
                plan = self.desktop_plan(self.desktop_fixture())
                self.mock['desktopPauseWait'] = True
                session = self.dir / f'wait-{action}.json'
                control = Path(str(session) + '.control.json')
                control.write_text(json.dumps(dict(pause=False, stop=False, **{'continue': True})), encoding='utf-8')
                plan_path = self.write('wait-plan.json', plan)
                mock_path = self.write('wait-mock.json', self.mock)
                cmd = [PS, '-NoProfile'] + (['-ExecutionPolicy', 'Bypass'] if os.name == 'nt' else [])
                cmd += ['-File', str(APP / 'Run-Plan.ps1'), '-PlanPath', str(plan_path), '-SessionPath', str(session),
                        '-DryRun', '-MockPath', str(mock_path), '-ParentPid', str(os.getpid())]
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                def cleanup(p=process):
                    if p.poll() is None:
                        p.kill()
                    p.communicate()
                self.addCleanup(cleanup)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        record = json.loads(session.read_text(encoding='utf-8'))
                        if record['operatorState'] == 'Paused':
                            break
                    except (OSError, ValueError):
                        pass
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        self.fail('Engine exited before pause: ' + stdout + stderr)
                    time.sleep(.05)
                else:
                    self.fail('Desktop pause was never published.')
                time.sleep(.8)
                self.assertIsNone(process.poll(), 'A stale Continue bypassed the desktop warning.')
                self.assertIn('DESKTOP LOAD', record['operatorMessage'])
                self.assertFalse(any(s['key'].endswith('/after-check') for s in record['steps']))
                control.write_text(json.dumps(dict(pause=False, stop=action == 'stop', **{'continue': action == 'continue'})), encoding='utf-8')
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 1, stdout + stderr)
                record = json.loads(session.read_text(encoding='utf-8'))
                self.assertEqual(any(s['key'].endswith('/after-check') for s in record['steps']), action == 'continue')
                self.assertTrue(record['finalState']['clocks']['verified'])

    def test_new_desktop_runtime_files_are_copied_and_verified_on_temporary_kit(self):
        kit = self.dir / 'headroom-kit'
        (kit / 'python').mkdir(parents=True)
        (kit / 'python/python.exe').write_bytes(b'fixture')
        cmd = [PS, '-NoProfile'] + (['-ExecutionPolicy', 'Bypass'] if os.name == 'nt' else [])
        # PS 5.1 launched beneath PS 7 can inherit PS 7's Utility module first; that module lacks
        # the PS 5.1 script function Get-FileHash. Import the current host's own bundled module.
        script = str(ROOT / 'tools/collection-kit/Sync-Kit.ps1').replace("'", "''")
        destination = str(kit).replace("'", "''")
        cmd += ['-Command', "Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility') -Force; "
                f"& '{script}' -KitPath '{destination}'"]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('files match the repository', proc.stdout)
        for relative in ('tools/bench-app/Desktop-Load.ps1', 'tools/bench-app/check_desktop_load.py',
                         'tools/hwinfo-logging/check_desktop_load.py'):
            self.assertEqual((kit / relative).read_bytes(), (ROOT / relative).read_bytes())
        fixture = self.desktop_fixture(fps=0, bus=0)
        command = [sys.executable, str(kit / 'tools/bench-app/check_desktop_load.py'), '--hwinfo-log', fixture['log'],
                   '--utc-offset=-07:00']
        for path in fixture['sweepFiles']:
            command += ['--sweep', path]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['status'], 'quiet')

    @unittest.skipUnless(os.name == 'nt', 'WinForms needs Windows desktop')
    def test_window_opens_in_dry_run(self):
        mock = self.write('mock.json', self.mock)
        # -Hidden keeps the full ShowDialog path (timer, FormClosing) but off-screen and invisible,
        # so the suite stops flashing the bench window on the desktop (2026-09-29).
        proc = self.ps('Bench-Window.ps1', '-DryRun', '-MockPath', mock, '-AutoCloseSeconds', '1',
                       '-Hidden')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # 6 of 7 since 2026-09-23: C8 runs the evening before in shakedown-3070ti.json, so the
        # Session D catalog no longer preselects it.
        self.assertIn('CATALOG LOADED: 11 runs, 10 preselected.', proc.stdout)

    def test_hidden_refused_outside_dry_run(self):
        """A real bench window must never be hidden: -Hidden without -DryRun throws before any
        GPU query, catalog load or window."""
        proc = self.ps('Bench-Window.ps1', '-Hidden', '-AutoCloseSeconds', '1')
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('-Hidden is allowed only with -DryRun', proc.stdout + proc.stderr)
        self.assertNotIn('CATALOG LOADED', proc.stdout)


if __name__ == '__main__':
    class ReportingResult(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            print('[PASS] ' + test.id())

        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            print('[SKIP] ' + test.id() + ': ' + reason)

    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    outcome = unittest.TextTestRunner(resultclass=ReportingResult).run(suite)
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
