# Section 20b attempt log

Every attempt at a §20b session, failures included, in the order they began
(`docs/REGISTERED-PREDICTIONS.md` §20b, "Attempts and replacements"). **A pilot attempt's line is
committed and pushed before the session is launched**, and its outcome is added afterwards. Nothing
is ever removed from this file. Qualifications are listed for completeness; they are not sessions.

| # | Kind | Index | Local date | Launched from | Directory | Outcome |
|---|---|---|---|---|---|---|
| 1 | qualification (12 windows, 2475 MHz design) | — | 2026-10-09 | `a88c52f` | `docs/section20b/qualification-20261009/` | complete; not data |
| 2 | pilot attempt, **superseded 2475 MHz design** | 1 | 2026-10-11 | `56e29ba` | `docs/section20b/pilot1-attempt1-20261011/` | FAILED at `w020-P` (gemm 2475 on the 180 W cap); excluded, counts for nothing |
| 3 | qualification (36 windows, 2317 MHz) | — | 2026-10-11 | `52e6a4f` | `docs/section20b/qualification-20261011/` | complete; not data |
| 4 | qualification (36 windows, registered code) | — | 2026-10-11 | `96c683f` | `docs/section20b/qualification-20261011b/` | complete, 36 of 36 clean; not data |
| 5 | **pilot session** | 1 | 2026-10-12 | `025588e` logged; ran `72fb0cf` (same §20b code) | `data/section20b/pilot1-20261012/` | **complete, SCOREABLE** (144/144, return gate 0.255%) |
| 6 | **pilot session** | 2 | 2026-10-13 | `3bbdfca` logged; ran `c72630b` (same §20b code) | `data/section20b/pilot2-20261013/` | **complete, SCOREABLE** (144/144, return gate 0.211%) |
| 7 | **pilot session** | 3 | 2026-10-14 | `3d23a1b` logged; ran `317b5ea` (same §20b code) | `data/section20b/pilot3-20261014/` | **complete, SCOREABLE** (144/144, return gate 0.353%). Run knowing confirmation is already unattainable (GPT Job 90: four-pilot d_E SD ≥ 1.98 pp against 1.42 allowed), for the day-to-day record and the registration's formal end |
| 8 | **pilot session** | 4 | 2026-10-20 | `0b8e8d4` logged and ran (§20b path unchanged since pilot 3; the runner has since gained only §22 additions: the `rep` part, a self-copy and source hashes) | `data/section20b/pilot4-20261020/` | **complete, SCOREABLE** (144/144, return gate 0.334%). With four pilots no S from 8 to 32 qualifies (largest SD 2.271 pp), so §20b stops at insufficient precision, no verdict |

**Note, 2026-10-20 (GPT Job 110).** Attempt 8's "`0b8e8d4` logged and ran" is wrong about the second part:
`0b8e8d4` is the parent the line was written against, and the session ran from the attempt-line commit
`248d983`, which its `schedule.json` records. The runner blob is identical in both
(`be6aadd9bc4ba23b3f38e97e26e5da5b1609a148`). The row is left as written; this note corrects it.
