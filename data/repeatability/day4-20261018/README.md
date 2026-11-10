# Section 22 day 4, 2026-10-18: SCOREABLE (four days of five: a PARTIAL result)

`docs/REGISTERED-PREDICTIONS.md` §22, day index 4. Run by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts rep -Session 4 -ManageChatGpt` from `39e72e3` (the
attempt-line commit; runner byte-identical to days 1–3, launch hash `A0753C59…`), launched 13:33:52 local
(UTC−7), minimized and unattended, exit 0 at 14:44:44. Attempt 5 in `docs/repeatability/ATTEMPTS.md`.
**N=1 chip.**

Before launch: no Claude desktop update had been installed since 2026-10-15 and none was pending (the
AppXDeploymentServer log), and Phone Link (PhoneExperienceHost, CrossDeviceService, CrossDeviceResume) was
stopped as on day 3. Each pass still began with its own 90 s idle and stock witness. This is the first day
filed after the 2026-10-18 desktop-screen hardening (§22's dated note); the screen read every window.

Pass 1 ran resnet50, gemm, copy, reduce descending (13:38–14:09); stock was re-witnessed; pass 2 ran reduce,
copy, gemm, resnet50 ascending (14:13–14:44).

## Validity

Scored with the other three days: **SCOREABLE**, no problems. Stock witnesses at 13:36:16 and 14:11:14
(2475 MHz gemm 171.6 W and 178.9 W). Every point is valid, with temperature at most 62 °C. All eight roles
are `quiet` (0 of 20 windows flagged in each). Every event read is clean, and the final one covers the day.
Cleanup was verified. The software power-cap reason appeared at 13 of 160 points.

## What four days show: PARTIAL; resnet50 WITHIN 3%, the other three INCONCLUSIVE

`python analysis/score_repeatability.py data/repeatability/day*`:

| workload | regret at 1575 MHz, days 1 / 2 / 3 / 4 | mean | 98.75% interval | day SD (95%) | outcome |
|---|---|---|---|---|---|
| gemm | 1.263 / 2.835 / 1.632 / 1.218% | 1.737% | −0.299 to 3.773 | 0.755 pp (0.428–2.816) | INCONCLUSIVE |
| copy | 1.113 / 2.051 / 2.666 / 0.000% | 1.457% | −1.677 to 4.592 | 1.163 pp (0.659–4.335) | INCONCLUSIVE |
| reduce | 4.115 / 2.638 / 5.913 / 2.176% | 3.710% | −0.833 to 8.254 | 1.685 pp (0.955–6.284) | INCONCLUSIVE |
| resnet50 | 0.485 / 1.270 / 0.000 / 1.423% | 0.795% | −1.013 to 2.602 | 0.671 pp (0.380–2.500) | **WITHIN 3%** |

**resnet50's upper bound, 2.602%, is the first to fall below 3%.** It is a four-day label inside a PARTIAL
result, as §22 says three or four days are; day 5 completes the section and can still move it. gemm's
upper bound is 3.773% and reduce's lower bound is −0.833%, so neither is decided. INCONCLUSIVE is never "no
day effect". Day 4's return gate passed on all four (largest median 0.358%, reduce, maximum 2.074%). Observed
peaks: gemm 1425, copy 1575, reduce 1800, resnet50 1500.

## Secondary, descriptive only: the VID floor

gemm and resnet50 hold 0.720 V through 1575 MHz in both directions and rise at 1612. Three windows differ,
each read against the raw log with `tools/rerun15/check_vid_raw.py`:

- **pass 2 copy, ascending, 38–42 °C:** the floor ends at 1462. 0.725 V at 1500 and 1537 (11 of 18 and
  18 of 18 raw samples), 0.730 V at 1575.
- **pass 2 reduce, ascending, ran first after the second witness, 36–40 °C:** 0.725 V at 1237 and 1275 (23
  of 25, 22 of 25), so its lowest target is off the floor. It returns to 0.720 V from 1312, at 40 °C and
  above, through 1575.
- **pass 1 reduce, descending, 38–43 °C:** 0.720 V through 1537, 0.730 V at 1575 (18 of 20).

Every one of these windows read 43 °C or less. The 47–50 °C pass 1 copy held 0.720 V through 1575, one
step later than its cool pass 2 twin. That fits the association recorded on day 3, a step only where the GPU
reads about 36–43 °C. It is still not temperature alone: pass 1 reduce read 0.720 V at 1237–1537 at 38–42 °C.
Descriptive, N=1 chip, four days. The reading is a VID lookup, not a rail measurement. Temperature-dependent
V/F behaviour is known GPU Boost practice (GPT Job 106), so nothing here is claimed as new.

## Not measured

No ambient instrument. On-card temperatures are not ambient.
