# Section 22 day 1, 2026-10-15: SCOREABLE (one day of five; descriptive only on its own)

`docs/REGISTERED-PREDICTIONS.md` §22, day index 1. Run by
`tools/rerun15/Invoke-Rerun15Session.ps1 -Parts rep -Session 1 -ManageChatGpt` from `3d03761` (the
attempt-line commit; the §22 code is `c068dc2`'s, hardened after GPT Job 94), launched 08:38:56 local
(UTC−7), minimized and unattended, exit 0 at 09:49:45. Attempt 2 in `docs/repeatability/ATTEMPTS.md`;
the dry-run qualification just before it (attempt 1, 08:23) is not data and is not filed. **N=1 chip.**

Pass 1 ran gemm, copy, reduce, resnet50 ascending (08:43–09:14); stock was re-witnessed; pass 2 ran
resnet50, reduce, copy, gemm descending (09:18–09:49). Each sweep is 20 targets, 1237–1875 MHz at
37.5 MHz plus 2010 and 2317. Counts gemm 120, copy 2660, reduce 2870, resnet50 424; gemm, copy and reduce
drew inputs with `--input-seed 20261013`, resnet50 seeds itself.

## Validity

Scored with `python analysis/score_repeatability.py data/repeatability/day1-20261015`: **SCOREABLE**, no
problems. Every check the hardened scorer makes passed, including:
- eight roles, each the registered command, in order without overlap, each pass after its own stock
  witness (08:43:35 and 09:18:22 local; profile store sections hash to the curve3 snapshot,
  `8EC197F30E21D116`; mVolt+ offsets and demands all 0; memory 13801 MHz under load; 180 W; driver
  616.92; the 2475 MHz gemm witness read 180 W, at the cap);
- every point bench-ok, power windowed, achieved clock within ±15 MHz, loaded memory maximum
  13801–14001 MHz, no thermal or hardware slowdown reason, temperature at most 60 °C;
- desktop-load verdict `quiet` on all eight roles; idle baselines 0–1.8% before each sweep;
- the event log read clean after every role and after cleanup; cleanup verified (reset 0, store
  restored, 13801 MHz, 180 W);
- the filed runner matches the hash the runner took of itself at launch (`A0753C59…`).

The software power-cap reason appeared at 10 of 160 points (reported, not a failure).

## What day 1 shows (one day: no interval and no outcome)

| workload | return gate (median, max) | observed peak | within 1% of peak | peak asc / desc | regret at 1575 MHz |
|---|---|---|---|---|---|
| gemm | 0.032%, 0.097% | 1500 | 1462, 1500 | 1500 / 1425 | 1.263% |
| copy | 0.048%, 0.858% | 1500 | 1500 | 1537 / 1575 | 1.113% |
| reduce | 0.316%, 1.429% | 1800 | 1800 | 1800 / 1800 | 4.115% |
| resnet50 | 0.056%, 0.148% | 1537 | 1500, 1537, 1575 | 1537 / 1575 | 0.485% |

All four pass the 1.5% return gate. `reduce` peaks above the floor again, as §20 found (the reason §22
kept it), and its regret at 1575 MHz is above the 3% reference on this day. **One day decides nothing**:
the registered outcome needs at least three scoreable days, and five for a complete one.

## Secondary, descriptive only: the measured VID floor

On gemm, reduce and resnet50, in both directions, the reported VID holds 0.720 V through 1575 MHz and
first rises at 1612 (to 0.740 on gemm), matching the 1567–1575 floor end measured 2026-09-22.

**copy differs, by one 5 mV code.** Its reading steps up to 0.725 V over 1275–1387 MHz ascending and
1350–1462 MHz descending, returns to 0.720 V, and leaves the floor at 1612 ascending and 1575
descending. The scorer flags both copy sweeps as re-entering the floor (GPT Job 94, F8), so no clean
floor end is quoted for copy. One day and one workload; it is not interpreted here. **Raw-log check,
2026-10-16:** the step is a real reading (raw counts and medians equal the extract's), and it fell where the
GPU read 36–40 °C; see day 2's README for the two-day picture. The reported value
is a VID lookup, not a rail measurement (CLAUDE.md, the voltage grid).

## Not measured

No ambient instrument (§22: none is owned). On-card temperatures are recorded and are not ambient. The
Claude window's state is not independently recorded beyond the desktop-load screen, which passed on
every role.
