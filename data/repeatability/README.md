# Section 22: day-to-day stock repeatability (RTX 5060 Ti)

`docs/REGISTERED-PREDICTIONS.md` §22, registered 2026-10-14 (`18416e1`) before any day, hardened
before day 1 after GPT Job 94 (the section's dated note; no rule changed). One folder per day, filed by
`tools/rerun15/file_repeatability_day.py` exactly as the runner left it, with paths made relative. Every
attempt, failures included, is in `docs/repeatability/ATTEMPTS.md`; only the first attempt at a day index
is eligible.

**Days are the units, and N=1 chip throughout:** five days are five repeated observations of one card,
never five cards. Fewer than three scoreable days are descriptive only, with no outcome.

| folder | day | date | status | notes |
|---|---|---|---|---|
| `day1-20261015/` | 1 | 2026-10-15 | **SCOREABLE** | first of five; descriptive only on its own |
| `day2-20261016/` | 2 | 2026-10-16 | **SCOREABLE** | first pass descending; two days are still descriptive only |
| `day3-20261017/` | 3 | 2026-10-17 | **SCOREABLE** | three days: PARTIAL, INCONCLUSIVE for all four workloads |
| `day4-20261018/` | 4 | 2026-10-18 | **SCOREABLE** | four days: PARTIAL; resnet50 WITHIN 3%, gemm, copy and reduce INCONCLUSIVE |
| `day5-20261019/` | 5 | 2026-10-19 | **SCOREABLE** | five days: **COMPLETE**; gemm and resnet50 WITHIN 3%, copy and reduce INCONCLUSIVE |

Score every filed day together with
`python analysis/score_repeatability.py data/repeatability/day*` (add `--json out.json` for every
figure). Raw HWiNFO logs are in `data/HWiNFO-Data/<day folder>/`, which git ignores; each extract in a
day folder is joined to its own log by time at the UTC offset the runner recorded. **No ambient
instrument was used on any day**; on-card temperatures are not ambient.
