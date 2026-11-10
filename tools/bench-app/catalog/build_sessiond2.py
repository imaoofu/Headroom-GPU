"""Generate the Session D2 catalog: REGISTERED-PREDICTIONS 8d, the 3070 Ti negative control repeated.

Registered 2026-09-25 00:40, before collection and after 4b failed (commit 01623d3). Three suites,
stock-7 -> edit2-8 -> stock-9, on the same card, BIOS, store and grid as Session D. Every step
definition is imported from build_sessiond.py, so D2 is the same configuration by construction:
the same witnesses, iteration counts, memory clock and profile-store section hash.

Built to run with nobody at the machine (Raymond's instruction, 2026-09-25): no step waits for a
person once the HWiNFO Sensors window is detected, both drift gates are non-blocking, and there is
no end-of-session prompt.
"""
import json
from pathlib import Path

import build_sessiond as d

HERE = Path(__file__).resolve().parent


def run(identifier, name, why, minutes, priority, steps, requires, group=None):
    return dict(id=identifier, name=name, why=why, minutes=minutes, priority=priority,
                preselected=True, locked=True, requires=requires, group=group,
                finalRun=(identifier == 'cleanup'), steps=steps)


def full_suite(identifier, title, why, slot, core_range, settings, requires):
    label = 'rtx3070ti-sessiond-' + identifier
    steps = [d.profile(slot), d.witness('Verify profile under load', *core_range),
             d.log(label), d.suite(label, settings),
             d.step('log-stop', 'hwinfo-stop', 'Stop HWiNFO log')]
    return run(identifier, title, why, 62, 0, steps, requires, group='sessiond2-suites')


BASE = ('P1-P3 section hash a1159941da541eb9 (the curves decoded from store 1b08c2d0854460ff), '
        'SILENT BIOS, PL default, memory +0, IR off, baseline under 5 pct, iterations matched to '
        'rtx3070ti-suite-20260904')
STOCK7 = 'STOCK P1, Session D2 opening bracket, REGISTERED-PREDICTIONS 8d; ' + BASE
EDIT2_8 = ('EDIT 2 NEGATIVE CONTROL P3 as built, unchanged from Session D: stock through 818.75 mV, '
           'flat 1500 MHz from 825 mV up (825 mV is 15 under stock); REPEAT of edit2-3, '
           'REGISTERED-PREDICTIONS 8d; ' + BASE)
STOCK9 = 'STOCK P1, Session D2 closing bracket, REGISTERED-PREDICTIONS 8d; ' + BASE

[preflight] = [r for r in d.plan['runs'] if r['id'] == 'preflight']
[cleanup] = [r for r in d.plan['runs'] if r['id'] == 'cleanup']
preflight = dict(preflight, name='Preflight: BIOS, quiet card, profile store, stock, HWiNFO')

plan = dict(
    schemaVersion=1, title='RTX 3070 Ti Session D2 (8d control repeat)', volumeLabel='ESD-USB',
    # Collected 2026-09-25 (PASS, untouched). Retired: nothing more runs on this card.
    retired=True,
    card=dict(d.plan['card'],
              legacyDerivedGrids='Session D2, collected 2026-09-25, before the explicit-target rule '
                                 'of 2026-09-30. Its derived grid moved with the clock table (116 '
                                 'entries against 115) and made 8d NOT SCOREABLE: one of the two '
                                 'failures that rule exists for.'),
    revert=d.plan['revert'],
    runs=[
        preflight,
        full_suite('stock-7', '8d: stock suite (opening bracket)', 'Baseline for the control repeat.',
                   1, d.STOCK, STOCK7, ['preflight']),
        full_suite('edit2-8', '8d: Edit 2 control suite (the repeat)', 'Does 4b\'s move repeat?',
                   3, (1450, 1550), EDIT2_8, ['stock-7']),
        full_suite('stock-9', '8d: stock suite (closing bracket)', 'Stock return for 8d.',
                   1, d.STOCK, STOCK9, ['edit2-8']),
        dict(cleanup, requires=['preflight']),
    ],
)
[stock9] = [r for r in plan['runs'] if r['id'] == 'stock-9']
stock9['steps'] = stock9['steps'] + [d.step('stock-return', 'gate-drift',
    'Check stock return stock-7 to stock-9 (8d scoreability)', firstRun='stock-7',
    lastRun='stock-9', workloads=d.WORKLOADS, maxMedianAbsPct=1.5, blocking=False)]

if __name__ == '__main__':
    (HERE / 'sessiond2-3070ti.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
