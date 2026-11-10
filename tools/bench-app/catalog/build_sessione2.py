"""Generate Session E2 for the RTX 2060 Super: the 4c-offset re-run on a fixed grid.

REGISTERED-PREDICTIONS §4d, Amendment 3, 2026-09-27, written before this collection and AFTER
Session E's descriptive result was seen. Session E's offset suite could not be scored: the -165 MHz
offset moved the supported-clock table's top 2115 -> 2100, so its grid (derived from the table top)
shifted to 840..2100. Here every suite sweeps the SAME explicit list, 855..2010 MHz (12 targets),
which exists in both tables. 2115 is dropped: stock reached only ~1916 there, and nothing above
~1740 is reachable under the offset.

Every step definition is imported from build_sessione.py, so E2 is Session E's configuration by
construction: the same slots, witnesses, iteration counts, memory clock and power gate. Runs are
numbered on from Session E (stock-4 -> offset-5 -> stock-6), as Session D2 did.
"""
import json
from pathlib import Path

import build_sessione as e

HERE = Path(__file__).resolve().parent
# 855..2010 in 105 MHz steps: Session E's registered grid without 2115. All twelve are 15 MHz
# multiples inside both the stock (300-2115) and the offset (300-2100) clock tables.
TARGETS = list(range(855, 2011, 105))
assert TARGETS[0] == 855 and TARGETS[-1] == 2010 and len(TARGETS) == 12


def full_suite(identifier, title, why, slot, checks, settings, requires):
    label = 'rtx2060s-sessione2-' + identifier
    steps = e.verified(slot, label, checks)
    steps += [e.step('log-start', 'hwinfo-start', 'Start HWiNFO log', path='kit:/results/hwinfo-' + label + '.csv'),
              e.step('collect', 'suite', 'Collect 12-workload suite on the fixed 12-target list', label=label,
                     settings=settings, workloads=e.WORKLOADS, iterations=e.ITERATIONS,
                     expectedMemoryClockMhz=e.EXPECTED_MEMORY, targetsMhz=TARGETS),
              e.step('log-stop', 'hwinfo-stop', 'Stop HWiNFO log')]
    return e.run(identifier, title, why, 58, 1, steps, requires=requires, group='sessione2-e2')


GRID = 'fixed target list 855-2010 MHz, 12 points, 105 MHz apart (not derived from the clock table)'
STOCK4 = ('STOCK P1, verified at locked 1065 MHz by voltage; ' + e.BASE + '; ' + GRID +
          '; iterations matched to 20260912-124138_rtx2060super-suite; REGISTERED-PREDICTIONS 4c-offset '
          're-run (4d Amendment 3), opening stock bracket')
OFFSET5 = ('P2 = STOCK CURVE WITH A -165 MHz CORE OFFSET (Afterburner core slider, curve untouched; store '
           'data/afterburner-profiles/rtx2060s-profiles-20260927b-offset); verified at locked 1065 MHz '
           '(0.672-0.700 V) and locked 1275 MHz (0.731-0.757 V); ' + e.BASE + '; ' + GRID +
           '; REGISTERED-PREDICTIONS 4c-offset re-run (4d Amendment 3)')
STOCK6 = ('STOCK P1 reverted after the offset, verified at locked 1065 MHz by voltage; ' + e.BASE + '; ' +
          GRID + '; REGISTERED-PREDICTIONS 4c-offset re-run (4d Amendment 3), closing stock bracket')

[preflight] = [r for r in e.plan['runs'] if r['id'] == 'preflight']
[cleanup] = [r for r in e.plan['runs'] if r['id'] == 'cleanup']

plan = dict(
    schemaVersion=1, title='RTX 2060 Super Session E2 (4c-offset re-run, fixed grid)', volumeLabel='ESD-USB',
    # E2 states every suite's targets, so it takes Session E's card without E's legacy exemption;
    # the validator refuses an exemption a run list does not need.
    card={k: v for k, v in e.plan['card'].items() if k != 'legacyDerivedGrids'}, revert=e.plan['revert'],
    runs=[
        preflight,
        full_suite('stock-4', 'E2: stock suite (opening bracket)', 'Baseline for the offset re-run, fixed grid.',
                   1, e.stock_checks(), STOCK4, ['preflight']),
        full_suite('offset-5', 'E2: -165 MHz offset suite (4c-offset re-run)',
                   'The whole curve shifted -165 MHz, on the same 12 targets as stock.',
                   2, e.offset_checks(), OFFSET5, ['stock-4']),
        full_suite('stock-6', 'E2: stock suite (closing bracket)', 'If stock does not return, the re-run is not interpretable.',
                   1, e.stock_checks(), STOCK6, ['offset-5']),
        dict(cleanup, requires=['preflight']),
    ],
)
[stock6] = [r for r in plan['runs'] if r['id'] == 'stock-6']
stock6['steps'].append(e.step('stock-return', 'gate-drift', 'Check stock return across 12 workloads',
                              firstRun='stock-4', lastRun='stock-6', workloads=e.WORKLOADS,
                              maxMedianAbsPct=1.5, blocking=False))

if __name__ == '__main__':
    (HERE / 'sessione2-2060s.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
