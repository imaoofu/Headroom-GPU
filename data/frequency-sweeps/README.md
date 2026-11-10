# Frequency sweeps

Output of `tools/frequency-sweep/Invoke-FrequencySweep.ps1`. One CSV of per-frequency rows
plus one JSON of session metadata per run.

These are committed for the same reason the stability runs are: the measurements *are* the
contribution. Published consumer DVFS datasets sweep too narrow a window around
their default clock to contain an efficiency optimum - down to 89% of it, against an optimum that
sat at 62% of maximum on the V100 - so open data that sweeps far below stock is the thing this
project has to offer. (This sentence said they "sweep at or above stock"; that was corrected
2026-09-13, having been computed against a reference card rather than the authors' own.) Smoke-test output is excluded via `.gitignore`; anything else
kept here needs an entry below saying what it is and whether it is dataset-grade.

## Before trusting any run

Check `distinct_clocks_measured` against `frequencies_planned` in the session JSON, and
`lock_miss_direction` per row in the CSV:

- `none` — the lock held.
- `below` — the card could not sustain the requested clock (power/thermal). Ordinary, and
  expected at the top of the range, where max boost is a bin no card actually holds.
- `above` — **the clock cap was not applied at all.** nvidia-smi cannot exceed its own cap, so
  something outside it owns the V/F curve. Overshooting points collapse onto the same achieved
  clock, so the run yields fewer distinct frequencies than the row count suggests, with
  duplicates quietly overweighting one frequency.

Reset any overclocking utility to stock before collecting data intended for the dataset.

## Inventory gap closed, 2026-09-12

**Recorded 2026-09-11 as "32 `*_sweep.csv` files sit directly in this directory and are NOT listed
below".** Six were already described individually further down; the other 26 are grouped below.
They are not leftovers - several are cited by timestamp from other READMEs in this tree and from
`CORRECTION-20260822-splitcurve-membw-r2.txt` beside them, and they count toward the published
dataset-grade total.

They sit in the root rather than in a subdirectory because they predate the convention of one
directory per investigation. Kept where they are so existing links stay valid.

**This is an INVENTORY, not results.** Every row below comes from the file's own CSV and
session JSON - point count, workload, schema version - and nothing here says what a run found. For
that, follow the investigation READMEs in the subdirectories.

The 26 root-level CSVs in this directory are frequency sweep runs that predate the convention of placing each investigation in its own subdirectory. They remain in the directory root alongside the 32 subdirectories because they were generated before that structural rule was adopted. Each file is a standalone sweep output; none of them is described in the existing README sections.

### Fine-grained baseline sweeps

These runs are the earliest sweeps in the set, named `fine-p1` and `fine-p2` with no rerun or tuning suffix. They measure the `membw` and `gemm` workloads on a 13-point grid.

| stem | points | workload | schema |
|---|---|---|---|
| `20260816-125959_5060ti-membw-fine-p1` | 13 | `membw` | 0.1.0 |
| `20260816-130549_5060ti-membw-fine-p2` | 13 | `membw` | 0.1.0 |
| `20260816-131140_5060ti-gemm-fine-p2` | 13 | `gemm` | 0.1.0 |

### Split-curve sweeps

These runs carry the `splitcurve` name and cover the `gemm` and `membw` workloads. They include round markers (`r1` through `r5`), a `quiet` variant, and explicit `instantreplay` on/off pairs.

| stem | points | workload | schema |
|---|---|---|---|
| `20260822-160740_5060ti-splitcurve-gemm-r1` | 13 | `gemm` | 0.2.0 |
| `20260822-161322_5060ti-splitcurve-gemm-r2` | 13 | `gemm` | 0.2.0 |
| `20260822-161921_5060ti-splitcurve-membw-r2` | 10 | `membw` | 0.2.0 |
| `20260822-163705_5060ti-splitcurve-gemm-r3-quiet` | 13 | `gemm` | 0.2.0 |
| `20260822-165213_5060ti-splitcurve-gemm-r4-instantreplay-on` | 13 | `gemm` | 0.2.0 |
| `20260822-165944_5060ti-splitcurve-gemm-r5-instantreplay-off` | 13 | `gemm` | 0.2.0 |
| `20260822-220443_5060ti-splitcurve-gemm-clean-r3` | 13 | `gemm` | 0.3.0 |

### Floor-15 reruns

These runs are named `floor15-rerun` and re-measure the `gemm` and `membw` workloads on a 13-point grid.

| stem | points | workload | schema |
|---|---|---|---|
| `20260822-173451_5060ti-gemm-floor15-rerun` | 13 | `gemm` | 0.3.0 |
| `20260822-174118_5060ti-membw-floor15-rerun` | 13 | `membw` | 0.3.0 |

### Fine-p1/p2 reruns

These runs are re-measurements of the earlier fine-grained baseline sweeps, named `fine-p1-rerun` and `fine-p2-rerun` for both `gemm` and `membw`.

| stem | points | workload | schema |
|---|---|---|---|
| `20260822-174624_5060ti-gemm-fine-p1-rerun` | 13 | `gemm` | 0.3.0 |
| `20260822-175205_5060ti-membw-fine-p1-rerun` | 13 | `membw` | 0.3.0 |
| `20260822-175706_5060ti-membw-fine-p2-rerun` | 13 | `membw` | 0.3.0 |
| `20260822-180206_5060ti-gemm-fine-p2-rerun` | 13 | `gemm` | 0.3.0 |

### Tuned clean sweeps

These runs are named `tuned` and `clean`, with round markers `r1` through `r5` for `gemm` and a single `membw` run. They measure the `gemm` and `membw` workloads.

| stem | points | workload | schema |
|---|---|---|---|
| `20260822-182129_5060ti-tuned-gemm-clean-r1` | 13 | `gemm` | 0.3.0 |
| `20260822-182619_5060ti-tuned-gemm-clean-r2` | 13 | `gemm` | 0.3.0 |
| `20260822-183112_5060ti-tuned-membw-clean` | 10 | `membw` | 0.3.0 |
| `20260822-213750_5060ti-tuned-gemm-clean-r3` | 13 | `gemm` | 0.3.0 |
| `20260822-215317_5060ti-tuned-gemm-clean-r4` | 13 | `gemm` | 0.3.0 |
| `20260822-215811_5060ti-tuned-gemm-clean-r5` | 13 | `gemm` | 0.3.0 |

### Stock clean sweeps

These runs are named `stock` and `clean`, with round markers `r1` and `r2` for the `gemm` workload.

| stem | points | workload | schema |
|---|---|---|---|
| `20260822-201101_5060ti-stock-gemm-clean-r1` | 13 | `gemm` | 0.3.0 |
| `20260822-201554_5060ti-stock-gemm-clean-r2` | 13 | `gemm` | 0.3.0 |

### Mem-only clean sweeps

These runs are named `memonly` and `clean`, with round markers `r1` and `r2` for the `gemm` workload.

| stem | points | workload | schema |
|---|---|---|---|
| `20260822-211705_5060ti-memonly-gemm-clean-r1` | 13 | `gemm` | 0.3.0 |
| `20260822-212156_5060ti-memonly-gemm-clean-r2` | 13 | `gemm` | 0.3.0 |

### Data quality limitations

- **3 of the 26 runs carry schema `0.1.0`** and therefore **cannot be checked for capture-software contamination retrospectively**, because schema `0.1.0` has no video-engine telemetry. A reader using these files cannot rule out that the measured frequencies were affected by unrelated GPU activity.
- **3 of the 26 runs carry a null `applied_settings` field**, which means **the configuration was not recorded**. Null does not mean stock: it means nothing reconstructs what the card was set to. A reader cannot determine the clock, power, or other settings under which these sweeps ran.

## Runs

### `20260816-124651` / `125959` / `130549` / `131140` — `*-fine-p1/p2` — the two optima, separated

**Dataset-grade.** Four sweeps: 13 points over 1200–1900 MHz (~58 MHz step), both workloads, two
passes each, run in the order `gemm, membw, membw, gemm`.

The numbers below come from this exact command, which drops the two contaminated rows described
further down. Without `--exclude` the script reports −167 MHz instead of −146 MHz, because those
rows bias `gemm`'s vertex *toward* the reported effect; both figures are given so the difference is
visible rather than buried in a flag:

```powershell
python analysis/analyze_fine_sweep.py --exclude "gemm:1:1725,gemm:1:1785"
```

| | `gemm` | `membw` |
|---|---|---|
| Efficiency optimum | **1488 MHz** | **1634 MHz** |
| pass 1 / pass 2 fitted alone | 1508 / 1480 MHz | 1636 / 1632 MHz |
| Difference | **−146 MHz** (95% CI −187 to −93) | |

*Superseded 2026-10-03 (found by GPT Job 48): the pooled fit the paper now pins
(`5.4.1-pooled-optima`) gives **1492 / 1604 MHz, −112 MHz (95% CI −146 to −70)**. The table above
is the earlier fit, kept as history; the direction of the result is unchanged.*

**The optima do differ, in the direction opposite to the prediction.** The V100's −0.666
correlation implies the *less* frequency-sensitive workload should prefer a *lower* clock; `membw`
prefers a **higher** one. Two reasons this is not a refutation, both in `docs/PAPER_DRAFT.md` §5.4.1:
`membw` retains 78% of peak throughput at the equivalent relative floor and so belongs to neither
the V100's ≥90% memory-bound class nor its <70% compute-bound class; and the effect is
statistically clear but practically small — using one workload's optimum for the other costs under
2% efficiency.

Integrity: 52/52 points locked exactly (0 above, 0 below), 52/52 power-windowed, ≥20 in-window
samples per point. Counterbalancing worked — `gemm` ran 47–53 °C then 44–51 °C, `membw` 39–49 °C
then 45–52 °C, so thermal drift fell on both workloads rather than on the difference.

**Two points in `gemm` pass 1 are contaminated and are documented rather than deleted.** A console
QuickEdit freeze (see §5.4.2) stalled that sweep for six minutes; its 1725 and 1785 MHz points read
7.3% and 4.6% below their pass-2 counterparts, with throughput *falling* as clock *rose*. The
conclusion survives dropping them — the effect moves from −167 to −146 MHz — and the previous
session's coarse sweep independently gives the same sign. **Do not use those two rows.**

Note the repeatability figures before treating any single sweep as precise: median pass-to-pass
efficiency difference was 2.4% for `gemm` (excluding the two contaminated rows) and 1.7% for
`membw` — driven by power, not by throughput, whose pass-to-pass agreement is 0.2–1%. That is why
this run has two passes, and why the optimum is fitted rather than picked.

### `20260816-001048_5060ti-gemm-floor15` + `20260816-001734_5060ti-membw-floor15` — the result

**The primary dataset.** 13 points each, 464–3090 MHz, stock V/F curve, both workloads on an
identical grid. Every point locked or undershot honestly; no overshoot, no collapse below the
power-limited top. Analyse with `python analysis/analyze_sweep.py`.

| | `gemm` | `membw` |
|---|---|---|
| Efficiency optimum | **1552 MHz** | **1552 MHz** |
| as % of sustained max | 60% (of 2597) | 56% (of 2755) |
| Efficiency gain vs sustained max | +46.5% | +41.6% |
| Performance cost at optimum | −43.2% | **−11.3%** |
| Power saved at optimum | −61.2% | −37.4% |

**The V100 headroom result reproduces on consumer silicon.** `membw`'s 41.6% / 11.3% / 37.4% against
the V100's 44.4% / 13.7% / 40.1% at 62% of max — matching on every axis, on a 2025 consumer part
four architectural generations later.

**The compute/memory split shows up in the cost, not the location.** Both optima land on the same
grid point, so at 217 MHz resolution they are indistinguishable — *not* the same as equal. What
separates cleanly is price: `gemm` gives up 43.2% throughput to sit at its optimum, `membw` only
11.3%. Downclocking to ~56% is nearly free for bandwidth-bound work and a real trade for
compute-bound work.

Both curves are single-peaked with the optimum well inside the range, so these are interior optima,
not edge artefacts.

### `20260816-000447_verify-3pt-membw` — the compute/memory contrast, measured

Same grid, same stock curve, `membw` instead of `gemm`. Matched targets are the point: the
comparison only means anything if the frequencies line up.

| Target | Achieved | Throughput | Power | Efficiency |
|---|---|---|---|---|
| 1237 MHz | 1236.0 MHz | 254.3 GB/s | 47.80 W | 5.32 GB/J |
| 2167 MHz | 2152.7 MHz | 322.6 GB/s | 64.08 W | 5.03 GB/J |
| 3090 MHz | 2753.2 MHz | 343.7 GB/s | 90.89 W | 3.78 GB/J |

**The contrast is real and it is 3.1×**: elasticity of throughput to core clock is 0.35 for `membw`
against 1.09 for `gemm`. **But "largely insensitive" was wrong** — `membw` gained 35% throughput for
a 123% clock increase, which is strongly sub-linear, not flat. At 1236 MHz the SMs cannot issue
requests fast enough to saturate DRAM, so it is issue-limited there. The tool README and
`gpu_workload.py` have been corrected.

Efficiency again falls monotonically, and again the best point is the lowest measured — 40.7% above
sustained max boost, against `gemm`'s 39.4%. **This was read at the time as "the optimum sits at or
below the floor", which the 13-point sweep above disproves:** the optimum is at 1552 MHz, between
this run's first and second points. Three points can bracket an optimum; they cannot locate one.

Also note `3090 → 2753.2 MHz` here against `3090 → 2617.6 MHz` for `gemm`. Sustained max boost is
**workload-dependent** — the more power-hungry workload holds a lower clock — so "stock" is not one
number, and grid points above ~2800 MHz will collapse onto one achieved clock for benign reasons
distinct from a V/F override.

**A discarded first attempt.** The initial `20260816-000221` run was contaminated: Afterburner
settings were changed by hand while the 1237 MHz point was being measured. The overshoot detector
added in `33ffe56` caught it independently — that row read 2713 MHz averaged over a 1747–2767 MHz
range, while the two clean points held to a single value each. Corroborated by the operator, run
discarded and repeated. Recorded because it is the detector's first true positive on an event it had
never seen.

### `20260815-234947_verify-3pt-stock` — first usable sweep

Same 3-point grid, Afterburner reset to stock. All three targets locked or undershot honestly, so
this measured **3 distinct frequencies**. Baseline utilisation 3.6%, no throttle flags at any point.

| Target | Achieved | Throughput | Power | Efficiency |
|---|---|---|---|---|
| 1237 MHz | 1235.9 MHz | 6.68 TFLOP/s | 51.97 W | 128.5 GFLOP/J |
| 2167 MHz | 2143.8 MHz | 12.21 TFLOP/s | 107.44 W | 113.6 GFLOP/J |
| 3090 MHz | 2617.6 MHz | 15.40 TFLOP/s | 167.03 W | 92.2 GFLOP/J |

It also settled the cause of the previous run's lock failure. `-lgc 2167` gave 2942 MHz with the
flattened curve applied and 2143.8 MHz with it reset — same script, same grid, one variable. The
V/F override is the cause, not merely consistent with the symptom.

**Two findings, both provisional at three points on one unit:**

1. Efficiency falls monotonically with frequency; the lowest point measured is **39.4% more
   efficient** than sustained max boost. Same direction and comparable magnitude to the V100's
   44.4%, and a lower bound rather than an estimate — the optimum was bracketed, not located.
2. ~~**The 40% sweep floor is too high.** Efficiency is still climbing at 1236 MHz, which is exactly
   the signature this project uses in commit `14b4c46` to disqualify other consumer datasets.~~
   **Retracted.** The 13-point sweep puts the optimum at 1552 MHz — inside the 40% range, between
   this run's first and second points. The floor was never the problem; three points were. The
   `14b4c46` signature only implies a truncated range for a *dense* sweep.

### `20260815-233703_verify-3pt` — TOOL VERIFICATION, NOT DATASET

Three-point sweep run to verify the benchmark measures anything real. It does, and the run is
kept as evidence, but **it is not dataset material and must not be pooled with real sweeps.**

What it established: fixed-work duration tracks core clock (2.38× the clock gave 2.57× the
throughput), so the performance metric is valid. It also quantified the power-window fix on live
data — 8.6% recovered at 1236 MHz against 22.8% at 2942 MHz, confirming the bias was
frequency-dependent rather than a constant offset.

Two reasons it is not dataset-grade:

1. **An MSI Afterburner profile was active**, with the V/F curve flattened at ~3010 MHz above
   925 mV. `-lgc 2167` was overridden to 2942 MHz. `-lgc 1237` held, being below the curve's
   ~1900 MHz floor where the override does not reach. So 2 of 3 targets landed on the same
   clock and the run measured **2 distinct frequencies, not 3**.
2. **It predates the detection columns.** This CSV was written by the version of the script
   before `lock_miss_direction`, `lock_miss_mhz`, `power_avg_process_w` and
   `distinct_clocks_measured` existed. The columns that would flag problem 1 are absent from the
   file itself, which is precisely why this note exists.

Background desktop load (Wallpaper Engine, browser, Discord, Spotify) was also present at ~6%
baseline utilisation — under the script's 10% guard, but not a quiet machine.
