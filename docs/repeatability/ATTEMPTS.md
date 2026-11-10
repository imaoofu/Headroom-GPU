# Section 22 attempt log

Every attempt at a §22 day, failures included, in the order they began (`docs/REGISTERED-PREDICTIONS.md`
§22). **A day's line is committed and pushed before the day is launched**, and its outcome is added
afterwards. Nothing is ever removed from this file. Qualifications are listed for completeness; they are
not days. No day may share a local date with a §20b attempt (`docs/section20b/ATTEMPTS.md`).

| # | Kind | Day | Local date | Launched from | Directory | Outcome |
|---|---|---|---|---|---|---|
| 1 | qualification (dry run, first target only; hardened code) | — | 2026-10-15 | `c068dc2` | `C:/headroom-bench/rerun15/20261015-082318-repdry` (not filed) | complete, exit 0: 8 of 8 roles quiet, every event read clean, sources hashed; not data |
| 2 | **day** | 1 | 2026-10-15 | `3d03761` logged and ran (§22 code of `c068dc2`) | `data/repeatability/day1-20261015/` | **complete, SCOREABLE** (exit 0, 8 of 8 roles quiet; return gate max median 0.316%, reduce) |
| 3 | **day** | 2 | 2026-10-16 | `37c9dae` (runner unchanged since `c068dc2`) | `data/repeatability/day2-20261016/` | **complete, SCOREABLE** (exit 0, 8 of 8 roles quiet; return gate max median 0.209%, reduce) |
| 4 | **day** | 3 | 2026-10-17 | `f40299a` (runner unchanged since `c068dc2`) | `data/repeatability/day3-20261017/` | **complete, SCOREABLE** (exit 0, 8 of 8 roles quiet; return gate max median 0.674%, reduce) |
| 5 | **day** | 4 | 2026-10-18 | `399ba3d` (runner unchanged since `c068dc2`) | `data/repeatability/day4-20261018/` | **complete, SCOREABLE** (exit 0, 8 of 8 roles quiet; return gate max median 0.358%, reduce) |
| 6 | **day** | 5 | 2026-10-19 | `dd7ca7c` (runner unchanged since `c068dc2`) | `data/repeatability/day5-20261019/` | **complete, SCOREABLE** (exit 0, 8 of 8 roles quiet; return gate max median 0.178%, reduce) |

**Note, 2026-10-20 (GPT Job 109).** "Launched from" names the HEAD the day's line was written against. Each
day actually ran from its attempt-line commit, which the day's `rerun15-inputs.json` records as
`repeatability.commit`: day 1 `3d03761` (the same commit), day 2 `510aa1c`, day 3 `1c1e388`, day 4
`39e72e3`, day 5 `e903149`. The runner is byte-identical across all of them, so no day's status changes.
