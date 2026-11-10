# Section 22 day 5, 2026-10-19: SCOREABLE (five days of five: the section is COMPLETE)

`docs/REGISTERED-PREDICTIONS.md` §22, day index 5. Run by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts rep -Session 5 -ManageChatGpt` from `e903149` (the
attempt-line commit; runner byte-identical to days 1–4, launch hash `A0753C59…`), launched 08:23:30 local
(UTC−7), minimized and unattended, exit 0 at 09:34:11. Attempt 6 in `docs/repeatability/ATTEMPTS.md`.
**N=1 chip.**

Before launch: the Claude desktop app had last updated on the evening of 2026-10-18 (AppXDeploymentServer
log), had restarted at 08:22 this morning, and nothing newer had installed. Phone Link (PhoneExperienceHost,
CrossDeviceService, CrossDeviceResume) was stopped as on days 3 and 4. Each pass still began with its own
90 s idle and stock witness.

Day 5 repeats day 1's schedule, as §22 registers: pass 1 ran gemm, copy, reduce, resnet50 ascending
(08:27–08:58); stock was re-witnessed; pass 2 ran resnet50, reduce, copy, gemm descending (09:02–09:33).

## Validity

Scored with the other four days: **SCOREABLE**, no problems. Stock witnesses at 08:25:57 and 09:00:50
(2475 MHz gemm 168.8 W and 180.2 W). Every point is valid, with temperature at most 60 °C. All eight roles
are `quiet`. Every event read is clean, and the final one covers the day. Cleanup was verified. The software
power-cap reason appeared at 13 of 160 points.

## What five days show: gemm and resnet50 WITHIN 3%; copy and reduce INCONCLUSIVE

`python analysis/score_repeatability.py data/repeatability/day*` prints `Scoreable days: 5 of 5 -> COMPLETE`:

| workload | regret at 1575 MHz, days 1 / 2 / 3 / 4 / 5 | mean | 98.75% interval | day SD (95%) | outcome |
|---|---|---|---|---|---|
| gemm | 1.263 / 2.835 / 1.632 / 1.218 / 1.407% | 1.671% | 0.377 to 2.965 | 0.671 pp (0.402–1.927) | **WITHIN 3%** |
| copy | 1.113 / 2.051 / 2.666 / 0.000 / 0.856% | 1.337% | −0.674 to 3.348 | 1.042 pp (0.624–2.995) | INCONCLUSIVE |
| reduce | 4.115 / 2.638 / 5.913 / 2.176 / 5.289% | 4.026% | 0.898 to 7.155 | 1.621 pp (0.971–4.659) | INCONCLUSIVE |
| resnet50 | 0.485 / 1.270 / 0.000 / 1.423 / 1.978% | 1.031% | −0.485 to 2.547 | 0.786 pp (0.471–2.258) | **WITHIN 3%** |

This is the registered, final outcome. gemm's upper bound fell from 3.773% (four days) to 2.965%, just
under 3%; resnet50 stayed WITHIN 3%, its upper bound moving from 2.602% to 2.547%. copy's upper bound is
3.348%. reduce has the largest mean regret, 4.026%, but its lower bound is 0.898%, not above 3%, so it is
not ABOVE 3%. INCONCLUSIVE is never "no day effect". The intervals assume independent, roughly normal day
values; five days are five observations of one card.

Day 5's return gate passed on all four (largest median 0.178%, reduce; maximum 1.986%). Observed peaks:
gemm 1462, copy 1537, reduce 1800, resnet50 1537. Over five days the peak targets were gemm 1425–1537,
copy 1500–1575, reduce 1725–1800 and resnet50 1500–1575, none at a grid edge. Peak labels moving
between neighbouring targets while regret stays small means a flat curve, not an unstable optimum.

## Secondary, descriptive only: the VID floor

gemm, reduce and resnet50 hold 0.720 V through 1575 MHz in both directions and rise at 1612. Both copy
windows step to 0.725 V and then return to 0.720 V, so the scorer flags them as re-entering the floor
(ambiguous). Each was read against the raw log with `tools/rerun15/check_vid_raw.py`:

- **pass 1 copy, ascending, 37–40 °C at the step:** 0.725 V at 1275–1425 (16 to 18 of each window's 18–20
  raw samples), back to 0.720 V at 1462 (38–41 °C) through 1575, rising at 1612.
- **pass 2 copy, descending, 37–40 °C at the step:** 0.725 V at 1350–1462 (16 to 18 of 18–20), 0.720 V at
  1500 and 1537, and 0.730 V at 1575 (12 of 18), so this window's floor ends at 1537.

These are the same two roles that stepped on day 1, which ran the same schedule. In five days every 0.725 V
step has been in a window reading about 36–43 °C, and none has been at a warmer one. It is still not
temperature alone: pass 1 resnet50 read 39–43 °C at 1237–1350 and held 0.720 V, as did pass 2 copy at
1237–1312 (38–43 °C). Descriptive, N=1 chip, five days. The reading is a VID lookup, not a rail
measurement. Temperature-dependent V/F behaviour is known GPU Boost practice (GPT Job 106), so nothing
here is claimed as new.

## Not measured

No ambient instrument. On-card temperatures are not ambient.
