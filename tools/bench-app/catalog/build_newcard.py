"""Generate the generic new-card run list: REGISTERED-PREDICTIONS 11, written before any card is known.

Written 2026-09-25, when Raymond said one or two more cards would come through the shop before
publication, most likely RTX 40- or 50-series. The protocol is fixed now, so what the data will be
asked cannot be tuned to the card that turns up.

STOCK ONLY, by construction: the engine's validator refuses profiles, witnesses, hash gates and a
revert slot in a generic run list. It matches any card whose name fits NAME_PATTERN, and a run list
written for a specific card always wins over it in the window.

Order: calibrate (11 suite workloads; gemm keeps its default 120), then the dense floor sweep
ascending, then descending, then the 12-workload suite. Each measurement has its own HWiNFO log,
and every path carries {session}, so a second card on the same USB never collides with the first.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKLOADS = 'copy reduce softmax layernorm bgemm32 bgemm64 bgemm128 bgemm256 bgemm1024 attention conv gemm'.split()
CALIBRATED = [name for name in WORKLOADS if name != 'gemm']
# RTX 40 and 50 series desktop cards. Turing and Ampere cards all have committed data already.
NAME_PATTERN = r'^NVIDIA GeForce RTX (40|50)[0-9]0( Ti)?( SUPER)?$'
# The dense floor sweep: 40-80% of the clock table's top, 25 points. Every floor end measured so far
# sits inside it: 2060 Super 975-1005 of 2115 (46-48%), 5060 Ti 1567-1575 of 3090 (51%), 3060 1260,
# 3070 Ti ~1485-1500 of 2115-2130 (70%). 25 points is ~52 MHz on a 3090 MHz table, a third of the
# suite grid's ~154 MHz step, which is what locating the floor end for the rule needs.
DENSE = dict(minPctOfTop=0.40, maxPctOfTop=0.80, points=25)
GEMM_ITERATIONS = 120  # the default every committed gemm sweep on every card used

SETTINGS = ('STOCK as found on a shop build, nothing applied by the bench; power limit verified at '
            'the card default; no Afterburner profile applied; IR off; baseline under 5 pct; '
            'REGISTERED-PREDICTIONS 11 (new-card protocol)')


def step(identifier, kind, name, minutes=None, **fields):
    estimates = {'gate-power': 0.1, 'gate-quiet': 0.3, 'calibrate': 6, 'hwinfo-start': 0.3,
                 'hwinfo-stop': 0.2, 'suite': 62, 'sweep': 18, 'human': 0.5}
    return dict(id=identifier, type=kind, name=name,
                estimatedMinutes=minutes if minutes is not None else estimates[kind], **fields)


def run(identifier, name, why, minutes, steps, requires=(), group=None):
    return dict(id=identifier, name=name, why=why, minutes=minutes, priority=0,
                preselected=True, locked=True, requires=list(requires), group=group,
                finalRun=(identifier == 'cleanup'), steps=steps)


def logged(label, measurement):
    return ([step('log-start', 'hwinfo-start', 'Start HWiNFO log',
                  path='kit:/results/hwinfo-{session}-' + label + '.csv'),
             measurement,
             step('log-stop', 'hwinfo-stop', 'Stop HWiNFO log')])


def dense(identifier, direction):
    label = 'newcard-dense-' + direction[:3]
    measurement = step('sweep', 'sweep', 'Dense gemm floor sweep, 40-80 pct of table top, ' + direction,
                       label=label, workload='gemm', iterations=GEMM_ITERATIONS,
                       direction=direction, output='kit:/results/{session}-' + label,
                       settings=SETTINGS + '; dense floor sweep ' + direction, **DENSE)
    return run(identifier, 'Dense floor sweep, ' + direction + ' (11)',
               'Locates the load floor end on this card; up then down, so warm-up is visible.',
               18, logged(label, measurement), requires=['calibrate'], group='newcard')


plan = dict(
    schemaVersion=1, title='New card: stock protocol (REGISTERED-PREDICTIONS 11)',
    volumeLabel='ESD-USB',
    card=dict(generic=True, name='Any NVIDIA GeForce RTX 40 or 50 series card, stock only',
              namePattern=NAME_PATTERN),
    revert=None,
    runs=[
        run('preflight', 'Preflight: quiet card, HWiNFO, stock power',
            'Reject a busy card or a changed power limit before measuring.', 2, [
                step('quiet', 'gate-quiet', 'Quiet pmon baseline and video engines', maxUtil=5),
                step('sensors', 'human', 'Confirm HWiNFO Sensors window',
                     instruction='HWiNFO has launched from the kit (if it was not already running). Open Sensors only and close any update popup. The run continues by itself once the Sensors window is detected; Continue also works.',
                     launchHwinfo=True),
                step('power', 'gate-power', 'Power limit is the card default (stock)', stockOnly=True),
            ]),
        run('calibrate', 'Calibrate the suite for this card',
            'Iteration counts are a property of the card; taken once, kept on resume.', 6, [
                step('calibrate', 'calibrate', 'Calibrate 11 suite workloads (gemm stays 120)',
                     workloads=CALIBRATED, targetSeconds=9),
            ], requires=['preflight']),
        dense('dense-asc', 'ascending'),
        dense('dense-desc', 'descending'),
        run('suite', 'Twelve-workload suite (11)', 'The stock efficiency optimum the rule predicts.',
            62, logged('newcard-suite', step('collect', 'suite', 'Collect 12-workload suite',
                                             label='newcard-suite', settings=SETTINGS,
                                             workloads=WORKLOADS, iterations='calibrated')),
            requires=['calibrate'], group='newcard'),
        run('cleanup', 'Verify stock power and bring the kit back',
            'Nothing was applied; confirm the power limit is still the default.', 1, [
                step('power', 'gate-power', 'Power limit is still the card default', stockOnly=True),
            ], requires=['preflight']),
    ],
)

if __name__ == '__main__':
    (HERE / 'newcard-rtx40-50.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
