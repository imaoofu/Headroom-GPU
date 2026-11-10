# Section 22 day 3, 2026-10-17: SCOREABLE (three days of five: a PARTIAL result)

`docs/REGISTERED-PREDICTIONS.md` §22, day index 3. Run by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts rep -Session 3 -ManageChatGpt` from `1c1e388` (the
attempt-line commit; runner byte-identical to days 1–2, launch hash `A0753C59…`), launched 14:45:29 local
(UTC−7), minimized and unattended, exit 0 at 15:56:16. Attempt 4 in `docs/repeatability/ATTEMPTS.md`.
**N=1 chip.**

Launched the afternoon of the same date as the new-card practice run (12:25–14:00, a different protocol,
not data). Phone Link (PhoneExperienceHost, CrossDeviceService) was stopped just before launch as a
precaution: it is a candidate for waking the CPU's integrated GPU (practice attempt 1). Each pass still began
with its own 90 s idle and stock witness.

Pass 1 ran reduce, resnet50, gemm, copy ascending (14:50–15:20); stock was re-witnessed; pass 2 ran copy,
gemm, resnet50, reduce descending (15:25–15:55).

## Validity

Scored with the other two days: **SCOREABLE**, no problems. Stock witnesses at 14:49:52 and 15:24:48
(2475 MHz gemm 174.1 W and 179.8 W). Every point is valid, with temperature at most 66 °C. All eight roles
are `quiet`, with idle baselines 0–1.4%. Every event read is clean, and the final one covers the day. Cleanup
was verified. The software power-cap reason appeared at 16 of 160 points.

## What three days show: the registered outcome is PARTIAL, INCONCLUSIVE for every workload

`python analysis/score_repeatability.py data/repeatability/day*`:

| workload | regret at 1575 MHz, days 1 / 2 / 3 | mean | 98.75% interval | day SD (95%) | outcome |
|---|---|---|---|---|---|
| gemm | 1.263 / 2.835 / 1.632% | 1.910% | −2.297 to 6.117 | 0.822 pp (0.428–5.169) | INCONCLUSIVE |
| copy | 1.113 / 2.051 / 2.666% | 1.943% | −2.058 to 5.944 | 0.782 pp (0.407–4.916) | INCONCLUSIVE |
| reduce | 4.115 / 2.638 / 5.913% | 4.222% | −4.169 to 12.612 | 1.640 pp (0.854–10.309) | INCONCLUSIVE |
| resnet50 | 0.485 / 1.270 / 0.000% | 0.585% | −2.694 to 3.864 | 0.641 pp (0.334–4.029) | INCONCLUSIVE |

With two degrees of freedom the Bonferroni t quantile is about 8.9, so every interval spans 3%. **This is a
partial result, not "no day effect"**, exactly as §22 says. Day 3's return gate passed on all four
(largest median 0.674%, reduce). Observed peaks: gemm 1425, copy 1500, reduce 1800, resnet50 1575.

## Secondary, descriptive only: the VID floor, and what day 3 adds

gemm, copy and resnet50 hold 0.720 V through 1575 MHz (copy ascending to 1537) and rise at 1612. **reduce's
first-pass sweep, which ran first and coolest (37–41 °C), reads 0.725 V at 1237 MHz**, so its lowest target is
off the floor, and 7–10 of about 24 raw samples read 0.725 V at 1275–1312 as well. It was checked against the
raw log with `tools/rerun15/check_vid_raw.py`.

**This breaks the schedule-slot pattern of days 1–2.** The slots that stepped on both of those days (pass-1
role 2, pass-2 role 3) held resnet50 today, at 43–46 °C, and it was clean. Across three days, every 0.725 V
window has fallen where the GPU read about 36–41 °C, and no sweep at 43 °C or above shows one. It is still
not temperature alone (day 2's pass-2 reduce was as cool and stepped at one target only). Descriptive, N=1
chip, three days. The reading is a VID lookup, not a rail measurement, and temperature-dependent boost
behaviour is known GPU Boost practice, so nothing here is claimed as new.

## Not measured

No ambient instrument. On-card temperatures are not ambient.
