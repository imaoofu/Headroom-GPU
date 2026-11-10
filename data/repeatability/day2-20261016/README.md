# Section 22 day 2, 2026-10-16: SCOREABLE (two days of five; descriptive only)

`docs/REGISTERED-PREDICTIONS.md` §22, day index 2. Run by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts rep -Session 2 -ManageChatGpt` from `510aa1c` (the
attempt-line commit; the runner is byte-identical to day 1's, launch hash `A0753C59…` both days), launched
08:22:24 local (UTC−7), minimized and unattended, exit 0 at 09:33:26. Attempt 3 in
`docs/repeatability/ATTEMPTS.md`. **N=1 chip.**

Pass 1 ran copy, reduce, resnet50, gemm **descending** (08:27–08:57); stock was re-witnessed; pass 2 ran
gemm, resnet50, reduce, copy ascending (09:02–09:32). Same 20 targets, counts and input seed as day 1.

## Validity

`python analysis/score_repeatability.py data/repeatability/day1-20261015 data/repeatability/day2-20261016`:
**SCOREABLE**, no problems, with every check the scorer makes as hardened after GPT Jobs 94, 99 and 100.
In brief:
- stock witnesses at 08:27:12 and 09:02:02, store sections = curve3, full mVolt+ records all zero, 180 W,
  13801 MHz; the 2475 MHz gemm witness read 172.5 W and 180.1 W;
- every point valid, temperature at most 62 °C;
- desktop-load verdict `quiet` on all eight roles, with idle baselines 0–3.8%;
- every event read clean, and the final one covers the day;
- cleanup verified.

The software power-cap reason appeared at 16 of 160 points (reported, not a failure).

## What day 2 shows

| workload | return gate (median, max) | observed peak | peak asc / desc | regret at 1575 MHz | day 1, for comparison |
|---|---|---|---|---|---|
| gemm | 0.111%, 0.167% | 1537 | 1537 / 1537 | 2.835% | 1500, 1.263% |
| copy | 0.197%, 0.741% | 1500 | 1500 / 1500 | 2.051% | 1500, 1.113% |
| reduce | 0.209%, 2.219% | 1725 | 1725 / 1725 | 2.638% | 1800, 4.115% |
| resnet50 | 0.129%, 0.228% | 1500 | 1500 / 1500 | 1.270% | 1537, 0.485% |

All four pass the 1.5% return gate on the median; reduce's single largest change is 2.2%. **Two days are
descriptive only**: the registered outcome needs three scoreable days at least, and the two-day intervals the
scorer prints are too wide to mean anything (t with one degree of freedom).

## Secondary, descriptive only: the VID floor

gemm and resnet50 hold 0.720 V through 1575 MHz in both directions and first rise at 1612, as on day 1. copy
is clean today (0.720 V to 1537 ascending and 1575 descending). **reduce** shows a one-code (5 mV) step to
0.725 V at 1312–1387 MHz in pass 1 and at 1312 alone in pass 2, then returns to 0.720 V, so the scorer flags
both reduce sweeps as re-entering the floor.

**Observation across the two days, not interpreted:** the re-entering step appears in the same schedule
slots both days, the second role of pass 1 and the third of pass 2. On day 1 those slots held copy; on day 2
they held reduce, and copy, moved to the first and last slots, was clean.

**Checked against the raw logs the same day** (`python tools/rerun15/check_vid_raw.py <day> <role>`; the
logs are gitignored, which is why GPT Job 100 could not): in every window the raw sample count and median
equal the extract's, and 12–21 samples per window read 0.725 V, so **the step is a real reading, not a join
artifact**. Every 0.725 V window in both days falls where the GPU read **36–41 °C**, the coolest stretches
of these sessions (those slots follow low-power sweeps); sweeps that ran at 45–53 °C show none. It is not
temperature alone: day 2's pass-2 reduce ran at 38–41 °C and stepped at one target only. Two days cannot say
more. Temperature-dependent boost behaviour is known GPU Boost practice, so nothing here is claimed as new.
The reading is a VID lookup, not a rail measurement.

## Not measured

No ambient instrument. On-card temperatures are not ambient.
