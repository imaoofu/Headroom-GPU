"""Generate the Session E catalog for the RTX 2060 Super: E1 (REGISTERED-PREDICTIONS 4d) and E2 (4c).

Written 2026-09-24 from docs/GPU-WORKLIST-2060S.md and SESSION-E-RUNSHEET.md, with every card
figure taken from this card's committed sweeps (data/frequency-sweeps/rtx2060s-*), not from the
3070 Ti catalog.

Slot convention: P1 = STOCK, P2 = STOCK WITH A -165 MHz CORE OFFSET. ⛔ Until 2026-09-27 P2 was the
Part 2 edit (every point below 0.669 V capped at 810 MHz). Afterburner would not move any point below
700 mV on this card, so that edit could not be built; REGISTERED-PREDICTIONS §4d, Amendment 2,
replaces it with the offset before any Session E data exists. The store snapshotted that day
(data/afterburner-profiles/rtx2060s-profiles-20260927) held stock in both slots, and P2 is saved
again after it, so there is still no profile hash to pin: the voltage witnesses carry identity. They
check what each slot DOES to the curve, which a slot number cannot.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKLOADS = 'copy reduce softmax layernorm bgemm32 bgemm64 bgemm128 bgemm256 bgemm1024 attention conv gemm'.split()
# From 20260912-124138_rtx2060super-suite, the run that produced the registered 1065 MHz baseline.
# Reused, never re-derived: new counts change the work per point (worklist E2, correction 2).
ITERATIONS = [2936, 3180, 2377, 1628, 1163, 2986, 1935, 1076, 297, 88, 223, 120]
# Collect.ps1's membw probe read 7000 MHz under load on 2026-09-12 (machine-info.txt); gemm sweeps
# log 6801. Collect's own tolerance is +/-400.
EXPECTED_MEMORY = 7000
MEMORY = (6700, 7100)
# Unlocked stock peak is set by the 175 W power cap, not the curve: the 09-12 suite's per-workload
# peaks ran 1576-1908 MHz, so an unlocked witness CANNOT tell stock from the offset. It only proves
# an alive, unlocked card.
UNLOCKED = (1450, 2115)
# Locked 1065 MHz: stock reads 0.644 V (20260915 fine floor; 0.650 is one warm code up), the
# stored curve's 643.8 mV point. Under -165 MHz a locked f reads stock's f + 165 (the reported
# voltage follows the stored curve, 6.25 mV / 30 MHz steps): 1230's 681.2 mV point. An offset that
# failed to reach the points below 700 mV, which the editor will not expose, leaves 0.644 and fails.
LOCK_EDIT_TEST = 1065
STOCK_AT_1065 = (0.630, 0.657)
OFFSET_AT_1065 = (0.672, 0.700)
# Locked 1275 MHz reads 0.694 V at stock; under the offset it reads stock's 1440, the 743.8 mV point.
# Both ranges accept roughly -135 to -195 MHz: they prove an offset of about that size is live on
# the whole curve, not that it is exactly -165 (the re-snapshotted store's CoreClkBoost records that).
LOCK_ABOVE = 1275
OFFSET_AT_1275 = (0.731, 0.757)
POWER = dict(limit=175, default=175, max=185)   # enforced / default / max, every committed sweep


def step(identifier, kind, name, minutes=None, **fields):
    estimates = {'gate-power': 0.1, 'gate-quiet': 0.3, 'gate-drift': 0.2, 'apply-profile': 0.2,
                 'witness': 1.0, 'hwinfo-start': 0.3, 'hwinfo-stop': 0.2, 'suite': 58,
                 'sweep': 14, 'human': 0.5}
    return dict(id=identifier, type=kind, name=name,
                estimatedMinutes=minutes if minutes is not None else estimates[kind], **fields)


def run(identifier, name, why, minutes, priority, steps, requires=(), group=None):
    return dict(id=identifier, name=name, why=why, minutes=minutes, priority=priority,
                preselected=True, locked=True, requires=list(requires), group=group,
                finalRun=(identifier == 'cleanup'), steps=steps)


def witness(identifier, name, lock, core, voltage):
    # 200 gemm iterations is ~45 s at 1065 MHz on this card (120 took 29 s on 09-12).
    return step(identifier, 'witness', name, workload='gemm', iterations=200,
                coreMin=core[0], coreMax=core[1], memoryMin=MEMORY[0], memoryMax=MEMORY[1],
                lockMhz=lock, voltageMin=voltage[0], voltageMax=voltage[1])


def verified(slot, label, checks):
    """Apply a slot and prove what it does, inside a short log of its own (never the data log)."""
    steps = [step('profile', 'apply-profile', 'Apply profile P%d' % slot, slot=slot),
             step('witness-log-start', 'hwinfo-start', 'Start short witness voltage log',
                  path='kit:/results/hwinfo-' + label + '-witness.csv')]
    steps += checks
    steps += [step('witness-log-stop', 'hwinfo-stop', 'Stop witness voltage log')]
    return steps


def stock_checks():
    return [witness('witness', 'Stock at locked 1065 MHz reads the stock floor voltage',
                    LOCK_EDIT_TEST, (1050, 1080), STOCK_AT_1065)]


def offset_checks():
    return [witness('witness', 'Offset at locked 1065 MHz reads stock 1230 MHz voltage',
                    LOCK_EDIT_TEST, (1050, 1080), OFFSET_AT_1065),
            witness('witness-above', 'Offset at locked 1275 MHz reads stock 1440 MHz voltage',
                    LOCK_ABOVE, (1260, 1290), OFFSET_AT_1275)]


def full_suite(identifier, title, why, slot, checks, settings, requires):
    label = 'rtx2060s-sessione-' + identifier
    steps = verified(slot, label, checks)
    steps += [step('log-start', 'hwinfo-start', 'Start HWiNFO log', path='kit:/results/hwinfo-' + label + '.csv'),
              step('collect', 'suite', 'Collect 12-workload suite', label=label, settings=settings,
                   workloads=WORKLOADS, iterations=ITERATIONS, expectedMemoryClockMhz=EXPECTED_MEMORY),
              step('log-stop', 'hwinfo-stop', 'Stop HWiNFO log')]
    return run(identifier, title, why, 62, 1, steps, requires=requires, group='sessione-e2')


BASE = 'PL default 175 W, memory +0, IR off, baseline under 5 pct'
E1 = ('STOCK P1, verified at locked 1065 MHz by voltage; ' + BASE + ' - fine floor probe 900-1140 '
      'DESCENDING order, same grid as 20260915 rtx2060s-finefloor-gemm, thermal control for '
      'REGISTERED-PREDICTIONS 4d; gemm 120 iterations, the default that run used')
STOCK1 = ('STOCK P1, verified at locked 1065 MHz by voltage; ' + BASE + '; iterations matched to '
          '20260912-124138_rtx2060super-suite; REGISTERED-PREDICTIONS 4c, opening stock bracket')
OFFSET2 = ('P2 = STOCK CURVE WITH A -165 MHz CORE OFFSET (Afterburner core slider, curve untouched); '
           'verified at locked 1065 MHz (0.672-0.700 V) and locked 1275 MHz (0.731-0.757 V); ' + BASE +
           '; REGISTERED-PREDICTIONS 4c-offset, Amendment 2 2026-09-27 (the 4c curve edit could not '
           'be built)')
STOCK3 = ('STOCK P1 reverted after the offset, verified at locked 1065 MHz by voltage; ' + BASE +
          '; REGISTERED-PREDICTIONS 4c, closing stock bracket')

plan = dict(
    schemaVersion=1, title='RTX 2060 Super Session E', volumeLabel='ESD-USB',
    # Collected 2026-09-27 (PASS, untouched). Retired: its 4c-offset re-run is Session E2
    # (build_sessione2.py), which reuses every step defined here.
    retired=True,
    # Supported table: 122 clocks, 2115 MHz at the top; the 09-12 lowrange sweep locked 405.
    # suiteTopClockMhz: the registered 855-2115 grid (4c) is Collect's 40%-to-top of a table whose
    # top was 2115 on 09-12 and 09-15 (122 entries both days). The 3070 Ti's table top moved
    # 2115 -> 2130 between two days and cost Session D2 its registered verdict (2026-09-25).
    card=dict(name='NVIDIA GeForce RTX 2060 SUPER', minClockMhz=405, maxClockMhz=2115, suiteTopClockMhz=2115,
              legacyDerivedGrids='Session E, collected 2026-09-27, before the explicit-target rule '
                                 'of 2026-09-30. The offset moved the table top 2115 -> 2100, '
                                 'shifted the derived grid and made 4c-offset NOT SCOREABLE: the '
                                 'second failure that rule exists for.'),
    revert=dict(slot=1, witness=dict(workload='gemm', iterations=400, coreMin=UNLOCKED[0],
                                     coreMax=UNLOCKED[1], memoryMin=MEMORY[0], memoryMax=MEMORY[1])),
    runs=[
        run('preflight', 'Preflight: quiet card, HWiNFO, power, alive',
            'Reject a busy card, a changed power limit or a dead workload before measuring.', 3, 0, [
                step('quiet', 'gate-quiet', 'Quiet pmon baseline and video engines', maxUtil=5),
                step('sensors', 'human', 'Confirm HWiNFO Sensors window',
                     instruction='HWiNFO has launched from the kit (if it was not already running). Open Sensors only and close any update popup. The run continues by itself once the Sensors window is detected; Continue also works.',
                     launchHwinfo=True),
                step('profile', 'apply-profile', 'Apply profile P1 (stock)', slot=1),
                step('power', 'gate-power', 'Power 175 / 175 / 185 W', **POWER),
                step('witness', 'witness', 'Unlocked gemm: card alive, memory stock', workload='gemm',
                     iterations=400, coreMin=UNLOCKED[0], coreMax=UNLOCKED[1],
                     memoryMin=MEMORY[0], memoryMax=MEMORY[1]),
            ]),
        # E1 first: it is the thermal-order test, so it should not follow three hours of suites.
        run('e1-desc', 'E1: descending fine floor 1140 to 900 MHz (4d)',
            'Is the non-monotonic Turing floor a property of the curve or of a cold card?', 16, 0,
            verified(1, 'rtx2060s-sessione-e1-desc', stock_checks()) + [
                step('log-start', 'hwinfo-start', 'Start HWiNFO log',
                     path='kit:/results/hwinfo-rtx2060s-sessione-e1-desc.csv'),
                step('sweep', 'sweep', 'Descending 900-1140 MHz gemm sweep, 13 points',
                     label='rtx2060s-sessione-e1-desc', workload='gemm', iterations=120,
                     minMhz=900, maxMhz=1140, points=13, direction='descending',
                     output='kit:/results/e1-desc', settings=E1),
                step('log-stop', 'hwinfo-stop', 'Stop HWiNFO log')],
            requires=['preflight']),
        full_suite('stock-1', 'E2: stock suite (opening bracket)', 'Baseline for 4c, same work as 09-12.',
                   1, stock_checks(), STOCK1, ['preflight']),
        full_suite('offset-2', 'E2: -165 MHz offset suite (4c-offset)',
                   'The whole curve shifted -165 MHz: floor end 1005 to 840 MHz.',
                   2, offset_checks(), OFFSET2, ['stock-1']),
        full_suite('stock-3', 'E2: stock suite (closing bracket)', 'If stock does not return, 4c is not interpretable.',
                   1, stock_checks(), STOCK3, ['offset-2']),
        run('cleanup', 'Verify stock and bring the kit back',
            'Verify stock before the card ships; retain the USB.', 3, 2,
            verified(1, 'rtx2060s-sessione-cleanup', stock_checks()) + [
                step('power', 'gate-power', 'Verify stock power limits', **POWER)],
            requires=['preflight']),
    ],
    # No afterRevertHuman: the session ends by itself. Afterburner and its store stay until the
    # results are reviewed, then are removed by hand before the card ships (worklist).
)
[stock3] = [r for r in plan['runs'] if r['id'] == 'stock-3']
stock3['steps'].append(step('stock-return', 'gate-drift', 'Check stock return across 12 workloads',
                            firstRun='stock-1', lastRun='stock-3', workloads=WORKLOADS,
                            maxMedianAbsPct=1.5, blocking=False))

if __name__ == '__main__':
    (HERE / 'sessione-2060s.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
