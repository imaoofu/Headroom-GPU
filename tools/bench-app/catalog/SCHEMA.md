# Headroom Bench catalog schema v1

The catalog is UTF-8 JSON. `schemaVersion` is `1`. `Test-Plan.ps1 -PlanPath <absolute file>` validates it before any run. Run `catalog/build_sessiond.py` in the repository to regenerate the shipped Session D example.

Top level: `title`, `volumeLabel`, `card`, `revert`, `runs`, and optional `afterRevertHuman`. `card` has the exact `nvidia-smi` GPU name and the supported graphics clock bounds in MHz. The engine also checks the live card's supported-clock table. `revert` has a profile `slot` and a `witness` object; it runs in cleanup even after failure. `afterRevertHuman` describes a final hands-on action after the revert witness.

Optional `minimizeKnownRenderers` is an array of exact process names without `.exe` or
wildcards, for example `["claude"]`. Omission or `[]` means no windows are minimized.
Shop catalogs omit it; `localtest-5060ti.json` names `claude`. HWiNFO names are refused.
The generated plan preserves this list. The engine applies it at session start (including
resume) and before each suite or sweep, and records affected windows and verification
errors in `desktopPreflights`. Operators edit the catalog list before generating a plan.

Each run has `id`, `name`, `why`, estimated `minutes`, numeric `priority` (lower first), `preselected`, `locked`, and a `steps` array. Optional `requires` lists run IDs that must be present earlier. Optional `group` keeps runs contiguous; `finalRun` requires that run to be last. The window opens with all `preselected` runs checked and ordered as written. A run stays atomic when dragged. Session D's stock/edit sequence stays contiguous and ordered. The operator may untick a run; the resulting selection and every edit are recorded in `customizations` in the generated plan and session JSON. Edit a run by double-clicking its row. A custom sweep is inserted before the final cleanup run.

Step `id` values are unique within a run. Every step has `type` and `name`. Optional `estimatedMinutes` is used only for the window's finish estimate; it never controls a workload or timeout.

| Type | Required fields | Effect and verdict |
|---|---|---|
| `gate-power` | `limit`, `default`, `max` in W | Exact comparison to `nvidia-smi` power limits; records driver. |
| `gate-quiet` | `maxUtil` percent | Five `pmon` samples; SM is summed across processes in each sample and must remain below threshold. Encoder and decoder must stay at zero. |
| `gate-hash` | `path`, `prefix` | Exactly one profile file and SHA-256 prefix match. |
| `gate-drift` | `firstRun`, `lastRun`, `workloads`, `maxMedianAbsPct` | For each workload, median absolute matched-target throughput change across two 13-point suites; fail if any workload exceeds the limit. |
| `minimize-known-renderers` | none | Minimizes visible windows of processes named by the top-level list; records each window, verification and errors. Does not touch HWiNFO or GPU settings. |
| `apply-profile` | `slot` 1..5 | Applies Afterburner, waits eight seconds; following witness decides success. |
| `witness` | `workload`, `iterations`, `coreMin`, `coreMax`, `memoryMin`, `memoryMax` | Runs bundled Python, ignores the first four 1 s samples, checks loaded peaks. Optional `lockMhz`, `voltageMin`, `voltageMax` require a short active HWiNFO log. |
| `hwinfo-start` | `path` | Starts a new CSV with the existing HWiNFO script. Exit 4/6/7 asks the operator to start it and verifies file growth. |
| `hwinfo-stop` | none | Stops and checks the log. |
| `suite` | `label`, `settings`, `workloads`, `iterations`, `expectedMemoryClockMhz` | Calls `Collect.ps1`; verifies one new result directory and throughput-bearing CSVs. |
| `sweep` | `label`, `settings`, `workload`, `iterations`, `minMhz`, `maxMhz`, `points`, `direction`, `output` | Calls `Invoke-FrequencySweep.ps1`; checks its exit and CSV. `direction` is `ascending` or `descending`. |
| `human` | `instruction` | Pauses for Continue. Optional `launchHwinfo` starts the bundled HWiNFO first, and the step then also passes by itself once a Sensors window with a `Log Start` button is detected (recorded as `confirmedBy: auto`, otherwise `operator`). |

The profile-store hash path may be an absolute Windows path. HWiNFO logs and sweep output must use `kit:/results/...`, resolved under the kit root found from the USB volume label; `..` is forbidden. Live plan and session files must also stay on the USB kit. No result or log path is overwritten. A resume keeps the original plan and records a fresh `-resume-<timestamp>` suffix for a restarted run's logs and sweep directory.

The validator requires a log around each suite and sweep and prevents one log from being shared. `iterations` is one integer for a sweep, so work cannot vary between points. It also checks custom sweep bounds against the catalog card range. Live execution is checked again against `nvidia-smi`'s supported graphics clocks.

Every suite and sweep automatically receives a post-step desktop-load screen using its
active log and actual sweep files, including all workloads in a suite. The step record's
`desktopLoad` contains `status` (`quiet`, `DESKTOP LOAD`, or `unchecked`), per-window medians
and sample counts, thresholds (30 fps and 10% bus load), the log and its UTC offset.
A value strictly above either limit pauses the session for a fresh Continue or Stop.
Continue records acknowledgement and keeps the flag; a session whose latest measurement
for any step is flagged cannot finish PASS. Resume may replace that step with a clean
rerun while keeping the old flag in history.
Missing or ambiguous columns and missing benchmark-window samples are unchecked, without
failing the session. Missing checker code or Python is an installation failure. The
screen's limits are not a validated gate, and a quiet result does not prove a clean run.

**Explicit targets whenever a profile is applied (2026-09-30).** A run list for a known card that contains an `apply-profile` step must give every `suite` a `targetsMhz` list: ascending whole MHz, at least 10, inside the card range. A grid derived from the supported-clock table moved under two registered tests: overnight on the 3070 Ti (Session D2) and under an offset profile on the 2060 Super (Session E). Both became NOT SCOREABLE. Run lists written before the rule carry `card.legacyDerivedGrids`, a non-blank reason; the validator refuses the field on a run list that does not need it. `analysis/test_catalog_targets.py` pins which committed run lists may carry it.

For a new card, copy the catalog, replace the exact model and supported-clock range from that card, define stock and revert witnesses from measured same-card values, and check every profile and workload setting against its worklist. A filename alone is not a settings witness.

## Generic run lists (added 2026-09-25, REGISTERED-PREDICTIONS 11)

A run list written **before the card is known**. `card` has `generic: true`, a display `name`, and a
`namePattern` regex anchored with `^`, matched against `nvidia-smi`'s GPU name. The window offers a
generic run list **only when no run list is written for that exact card**. The validator makes it
stock only: no `apply-profile`, `witness` or `gate-hash` step, no `revert`, and no
`suiteTopClockMhz`.

| Addition | Fields | Effect |
|---|---|---|
| `gate-power` with `stockOnly: true` | no limits | Passes only if the enforced power limit equals the card's default. |
| `calibrate` | `workloads` (never `gemm`), `targetSeconds` 5..30 | Runs `gpu_workload.py --calibrate` for each workload before any log starts, and stores the counts in the session's `calibration`. **A resumed session reuses them** and never recalibrates. |
| `suite` with `iterations: "calibrated"` | a `calibrate` step earlier in the plan | Uses the stored counts; `gemm` is always 120. `expectedMemoryClockMhz` may be omitted, and Collect then records the memory clock as unverified. |
| `sweep` with `minPctOfTop`, `maxPctOfTop` | 0.2..1.0, no fixed MHz | Resolved against the live clock table's top at run time; the resolved MHz are in the step's witness. |
| `{session}` in a log or output path | — | Replaced by the session file's name, so a run list reused on several cards never collides on the USB. |

Every run list, generic or not, now also:
- refuses a suite or sweep if the clock table's top has moved since preflight;
- refuses a resume if the top differs from the interrupted attempt's;
- records the GPU's UUID and refuses to resume a session on a different physical card.
