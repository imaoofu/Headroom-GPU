"""Generate the reviewed Session D catalog from the C0-C10 shop worklist."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKLOADS = 'copy reduce softmax layernorm bgemm32 bgemm64 bgemm128 bgemm256 bgemm1024 attention conv gemm'.split()
ITERATIONS = [4099, 4291, 3230, 2462, 843, 2113, 3511, 2327, 616, 135, 432, 120]
# Hash of the Profile1-3 SECTIONS only (tools/bench-app/Profile-Hash.ps1), not the whole file. The
# whole-file hash was 1B08C2D0854460FF when the curves were decoded (2026-09-23); by 2026-09-24
# Afterburner had added [Defaults] and [Settings] by itself (CaptureDefaults) and Session D's first
# launch stopped at the gate, with Profile1-3 identical key for key. The runs apply only P1-P3, so
# those are what is pinned. This value is identical for the 09-23 and 09-24 snapshots.
HASH = 'A1159941DA541EB9'
HASH_SECTIONS = ['Profile1', 'Profile2', 'Profile3']
STOCK = (1700, 2115)   # unlocked stock witness core range; see witness()


def step(identifier, kind, name, minutes=None, **fields):
    estimates = {'gate-power':0.1, 'gate-quiet':0.3, 'gate-hash':0.1,
                 'gate-drift':0.2, 'apply-profile':0.2, 'witness':0.7,
                 'hwinfo-start':0.3, 'hwinfo-stop':0.2, 'suite':62,
                 'sweep':12, 'human':0.5}
    return dict(id=identifier, type=kind, name=name,
                estimatedMinutes=minutes if minutes is not None else estimates[kind], **fields)


def run(identifier, name, why, minutes, priority, steps, locked=True):
    requirements = {'stock-1':['preflight'], 'edit1-2':['stock-1'],
                    'edit2-3':['edit1-2'], 'stock-4':['edit2-3'],
                    'finefloor-desc':['stock-4'], 'cleanup':['preflight'],
                    # REGISTERED-PREDICTIONS section 8, added 2026-09-23 before collection. They run
                    # after stock-4 closes the registered bracket, so 4a/4b are scored as before.
                    'finefloor-pair':['stock-4'], 'edit1-finefloor':['finefloor-pair'],
                    'edit1-5':['edit1-finefloor'], 'stock-6':['edit1-5']}
    if identifier in ('stock-1','edit1-2','edit2-3','stock-4'):
        group = 'sessiond-suites'
    elif identifier in ('finefloor-pair','edit1-finefloor','edit1-5','stock-6'):
        group = 'sessiond-section8'
    else:
        group = None
    return dict(id=identifier, name=name, why=why, minutes=minutes,
                # C8 runs the evening before, in shakedown-3070ti.json (2026-09-23), so it is not
                # ticked here: a second run would hit the app's refuse-to-overwrite and end the session.
                priority=priority, preselected=(identifier != 'finefloor-desc'), locked=locked,
                requires=requirements.get(identifier, []), group=group,
                finalRun=(identifier == 'cleanup'), steps=steps)


def suite(label, settings):
    return step('collect', 'suite', 'Collect 12-workload suite', label=label,
                settings=settings, workloads=WORKLOADS, iterations=ITERATIONS,
                expectedMemoryClockMhz=9501)


def log(label):
    return step('log-start', 'hwinfo-start', 'Start HWiNFO log',
                path='kit:/results/hwinfo-' + label + '.csv')


def witness(name, core_min, core_max, lock=0, voltage=None):
    # Reviewed 2026-09-23: loaded memory on this card reads 9251 MHz at 186 of 192 committed
    # points (9501 at 6), so the floor is 9200, not 9450. Stock peak core reached 1785 at a
    # 2115 MHz target. STOCK ceiling raised 1900 -> 2115 on 2026-09-23: the witness keeps the
    # MAXIMUM sample, and the shakedown's revert witness read 1890 with a 1935 clock read-back
    # just after, so a cool-card boost sample could fail an unattended session. No slot in the
    # hash-verified store raises the top; the floor (1700, against Edit 2's ~1515) and the
    # memory ceiling (9550) carry the discrimination.
    data = dict(workload='gemm', iterations=400, coreMin=core_min, coreMax=core_max,
                memoryMin=9200, memoryMax=9550)
    if lock:
        data['lockMhz'] = lock
    if voltage:
        data['voltageMin'], data['voltageMax'] = voltage
    return step('witness', 'witness', name, **data)


def profile(slot):
    return step('profile', 'apply-profile', 'Apply profile P' + str(slot), slot=slot)


def full_suite(identifier, title, why, priority, slot, core_range, settings, lock=0, voltage=None):
    label = 'rtx3070ti-sessiond-' + identifier
    # The brief requires a short voltage log for the locked P2 witness. This is an
    # extra log, explicitly separate from the suite log, and is recorded as such.
    steps = [profile(slot)]
    if voltage:
        steps += [step('witness-log-start', 'hwinfo-start', 'Start short witness voltage log',
                       path='kit:/results/hwinfo-' + label + '-witness.csv')]
    steps += [witness('Verify profile under load', *core_range, lock=lock, voltage=voltage)]
    if voltage:
        steps += [step('witness-log-stop', 'hwinfo-stop', 'Stop witness voltage log')]
    steps += [log(label), suite(label, settings), step('log-stop', 'hwinfo-stop', 'Stop HWiNFO log')]
    return run(identifier, title, why, 62, priority, steps)


stock1 = 'STOCK P1, profile P1-P3 section hash a1159941da541eb9 (the curves decoded from store 1b08c2d0854460ff), SILENT BIOS verified at 290 W, memory +0, IR off, baseline under 5 pct, iterations matched to rtx3070ti-suite-20260904'
edit1 = 'EDIT 1 P2 as built: 725-825 mV capped at 1200 MHz, forced ramp +60 MHz per point 831-869 mV, stock from 875 mV, 718.75 mV at 1200 (+15 over stock); P1-P3 section hash a1159941da541eb9 (the curves decoded from store 1b08c2d0854460ff); SILENT BIOS, PL default, memory +0'
edit2 = 'EDIT 2 NEGATIVE CONTROL P3 as built: stock through 818.75 mV, flat 1500 MHz from 825 mV up (825 mV is 15 under stock); P1-P3 section hash a1159941da541eb9 (the curves decoded from store 1b08c2d0854460ff); SILENT BIOS, PL default, memory +0'
stock4 = 'STOCK P1 reverted after both edits, witnessed by peak core, P1-P3 section hash a1159941da541eb9 (the curves decoded from store 1b08c2d0854460ff), SILENT BIOS, PL default, memory +0'
edit1rep = edit1 + ' - REPLICATE of edit1-2, REGISTERED-PREDICTIONS 8a, run after stock-4 closed the registered bracket'
stock6 = 'STOCK P1 closing bracket for the edit1-5 replicate, REGISTERED-PREDICTIONS 8a; P1-P3 section hash a1159941da541eb9 (the curves decoded from store 1b08c2d0854460ff), SILENT BIOS, PL default, memory +0'


def fine(label, direction, lo, hi, points, settings, minutes):
    return [step('log-start-' + label, 'hwinfo-start', 'Start HWiNFO log',
                 path='kit:/results/hwinfo-rtx3070ti-sessiond-' + label + '.csv'),
            step('sweep-' + label, 'sweep', '%s %d-%d MHz gemm sweep, %d points' % (direction.capitalize(), lo, hi, points),
                 minutes=minutes, label='rtx3070ti-sessiond-' + label, workload='gemm', iterations=120,
                 minMhz=lo, maxMhz=hi, points=points, direction=direction,
                 output='kit:/results/' + label, settings=settings),
            step('log-stop-' + label, 'hwinfo-stop', 'Stop HWiNFO log')]

plan = dict(
    schemaVersion=1, title='RTX 3070 Ti Session D', volumeLabel='ESD-USB',
    # Collected and scored 2026-09-24. Retired so the window opens Session D2 on this card without
    # a picker whose first entry is this finished session.
    retired=True,
    # SILENT BIOS worklist spans supported bins from 405 through 2115 MHz.
    card=dict(name='NVIDIA GeForce RTX 3070 Ti', minClockMhz=405, maxClockMhz=2115,
              legacyDerivedGrids='Session D, collected 2026-09-24, before the explicit-target rule '
                                 'of 2026-09-30. Kept as the record of what ran; never run again.'),
    revert=dict(slot=1, witness=dict(workload='gemm', iterations=400,
                                    coreMin=STOCK[0], coreMax=STOCK[1],
                                    memoryMin=9200, memoryMax=9550)),
    runs=[
        run('preflight', 'C0-C3: preflight and profile store',
            'Reject a wrong BIOS, busy GPU, or changed profile store before measuring.',
            4, 0, [
                # Hash first, so slot 1 is known to be stock before it is applied. Applying it
                # before the power gate means a tuned profile left live is not a false stop:
                # the BIOS sets default and max, and stock returns the limit to default.
                step('profile-hash', 'gate-hash', 'Verify Afterburner P1-P3 are the decoded curves',
                     path='C:/Program Files (x86)/MSI Afterburner/Profiles/VEN_10DE*.cfg', prefix=HASH,
                     sections=HASH_SECTIONS),
                step('profile', 'apply-profile', 'Apply profile P1 (stock)', slot=1),
                step('power', 'gate-power', 'SILENT BIOS: 290 / 290 / 320 W', limit=290, default=290, max=320),
                step('quiet', 'gate-quiet', 'Quiet pmon baseline and video engines', maxUtil=5),
                witness('Stock under load', *STOCK),
                step('sensors', 'human', 'Confirm HWiNFO Sensors window',
                     instruction='HWiNFO has launched from the kit (if it was not already running). Open Sensors only and close any update popup. The run continues by itself once the Sensors window is detected; Continue also works.',
                     launchHwinfo=True)
            ]),
        full_suite('stock-1', 'C4: stock baseline', 'Baseline before any edits.', 0, 1, STOCK, stock1),
        full_suite('edit1-2', 'C5: edit 1 manipulation', 'Test the floor-shortening edit.', 0, 2,
                   (1370, 1420), edit1, lock=1395, voltage=(0.835, 0.870)),
        full_suite('edit2-3', 'C6: edit 2 negative control', 'The control is essential to the causal test.', 0, 3,
                   (1450, 1550), edit2),
        full_suite('stock-4', 'C7: stock drift bracket', 'Check stock returns after both edits.', 2, 1,
                   STOCK, stock4),
        run('finefloor-desc', 'C8: descending stock fine sweep',
            'Thermal-order control on the stock floor.', 3, 12, [
                log('rtx3070ti-sessiond-finefloor-desc'),
                step('fine-sweep', 'sweep', 'Descending 1200-1590 MHz gemm sweep',
                     label='rtx3070ti-sessiond-finefloor-desc', workload='gemm', iterations=120,
                     minMhz=1200, maxMhz=1590, points=10, direction='descending',
                     output='kit:/results/finefloor-desc',
                     settings='STOCK P1, SILENT BIOS, PL default, memory +0 - fine floor 1200-1590 DESCENDING, same grid as rtx3070ti-silent-gemm-fine 2026-08-27, thermal control as in 4d'),
                step('log-stop', 'hwinfo-stop', 'Stop HWiNFO log')
            ]),
        run('finefloor-pair', '8c: stock fine pair, ascending then descending (exploratory)',
            'Separates sweep direction from day-to-day drift, which C8 against 2026-08-27 confounds.', 12, 5,
            [profile(1), witness('Verify stock under load', *STOCK)]
            + fine('finefloor-asc2', 'ascending', 1200, 1590, 10,
                   'STOCK P1, SILENT BIOS, PL default, memory +0 - fine floor 1200-1590 ASCENDING, same grid as C8; REGISTERED-PREDICTIONS 8c (exploratory, no prediction), after stock-4', 5)
            + fine('finefloor-desc2', 'descending', 1200, 1590, 10,
                   'STOCK P1, SILENT BIOS, PL default, memory +0 - fine floor 1200-1590 DESCENDING, same grid as C8; REGISTERED-PREDICTIONS 8c (exploratory, no prediction), after stock-4', 5)),
        run('edit1-finefloor', '8b: where Edit 1 floor ends, fine sweep with voltage',
            'Measures the edited floor end directly; the suites infer it from a 105 MHz grid.', 8, 6,
            [profile(2),
             step('witness-log-start', 'hwinfo-start', 'Start short witness voltage log',
                  path='kit:/results/hwinfo-rtx3070ti-sessiond-edit1-finefloor-witness.csv'),
             witness('Locked 1395 MHz on Edit 1', 1370, 1420, lock=1395, voltage=(0.835, 0.870)),
             step('witness-log-stop', 'hwinfo-stop', 'Stop witness voltage log')]
            + fine('edit1-finefloor', 'descending', 1050, 1590, 13,
                   'EDIT 1 P2 as built, P1-P3 section hash a1159941da541eb9 (the curves decoded from store 1b08c2d0854460ff), SILENT BIOS, PL default, memory +0 - fine floor 1050-1590 DESCENDING, 13 points; REGISTERED-PREDICTIONS 8b', 6)),
        full_suite('edit1-5', '8a: Edit 1 replicate suite (registered)', 'n=2 on the manipulation; scored like edit1-2.', 7, 2,
                   (1370, 1420), edit1rep, lock=1395, voltage=(0.835, 0.870)),
        full_suite('stock-6', '8a: closing stock suite for the replicate', 'Stock bracket after edit1-5.', 8, 1,
                   STOCK, stock6),
        run('cleanup', 'C9-C10: verify stock and bring kit back',
            'Verify stock three ways before the card ships and retain the USB.', 0, 4, [
                profile(1),
                step('power', 'gate-power', 'Verify stock power limits', limit=290, default=290, max=320),
                witness('Verify stock core and memory under load', *STOCK)
            ])
    ],
    # No afterRevertHuman: the session must end by itself (unattended, 2026-09-24), and Afterburner
    # stays installed until the results are checked, in case anything needs re-running.
)
plan['runs'][4]['steps'].append(step('stock-return', 'gate-drift',
    'Check stock return across 12 workloads', firstRun='stock-1',
    lastRun='stock-4', workloads=WORKLOADS, maxMedianAbsPct=1.5, blocking=False))
[stock6_run] = [r for r in plan['runs'] if r['id'] == 'stock-6']
stock6_run['steps'].append(step('stock-return', 'gate-drift',
    'Check stock return stock-4 to stock-6 (8a scoreability)', firstRun='stock-4',
    lastRun='stock-6', workloads=WORKLOADS, maxMedianAbsPct=1.5, blocking=False))

if __name__ == '__main__':
    (HERE / 'sessiond-3070ti.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
