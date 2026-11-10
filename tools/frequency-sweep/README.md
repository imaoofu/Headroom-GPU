# Frequency Sweep

Builds a frequency-power-performance curve on real consumer hardware — the equivalent of the
public V100 dataset, measured on a card you actually own.

Two pieces:

| File | Role |
|---|---|
| `Invoke-FrequencySweep.ps1` | Locks the core clock to each of N frequencies and measures power, temperature, and achieved clock. |
| `gpu_workload.py` | Fixed-work GPU benchmark. Supplies the *performance* half of the measurement. |
| `llm_workload.py` | Fixed-token llama.cpp prompt processing or generation for an inference sweep. |

---

## LLM benchmark (Job 28, unregistered)

`llm_workload.py` invokes the pinned local `llama-bench.exe` and Qwen3-8B-Q4_K_M GGUF after verifying
the model's SHA-256. It never downloads a model. `llm-prefill` runs `-p 512 -n 0` (512 prompt tokens
per repetition); `llm-decode` runs `-p 0 -n 256` (256 generation steps per repetition). The installed
llama.cpp source at build `d222767c7` loops over exactly those counts and does not terminate on an
end-of-sequence token. The benchmark uses random token IDs, batch 1, full GPU-layer request, batch
and ubatch 512, eight CPU threads, flash attention on, and f16 K/V cache. It is a fixed-work
throughput test, not a quality or request-serving test.

The JSON payload's `throughput` is **token/s** across all timed repetitions. The sweep divides it
by windowed average **GPU board watts** to produce tokens per joule of **board energy**. Wall-plug,
CPU, memory and host energy are outside scope. Per-repetition token rates, their sample standard
deviation, exact arguments, model hash, and llama.cpp build are retained in the payload.

The timer excludes model loading and warm-up. This pinned llama.cpp build emits a progress message
inside each timed repetition, immediately after starting its timer, then reports each duration in
`samples_ns`. The workload stamps the progress event of the **first counted repetition** and adds the
last repetition's measured duration to its last progress stamp.

**Lead-in repetitions (Claude's review, 2026-09-27).** llama-bench's generation warm-up is one token,
so timed work starts from a near-idle GPU and NVML power lags by about a second. At stock the first
second of the window read **53 W against ~136 W steady** (decode) and 66 against ~150 (prefill),
pulling mean power ~4% and ~2% low, by an amount that would vary with clock across a sweep. So
**1 decode and 15 prefill repetitions run first and are excluded** from the window, token count and
rate (recorded as `lead_in_repetitions` / `lead_in_seconds`). Re-measured at stock with a 50 ms
trace: in-window mean and median power agree to **0.02% (decode, 139.8 W) and 0.06% (prefill,
154.9 W)**, and the first second reads 138.5 W and 151.7 W. Stock throughput: **74.2 token/s decode,
3344 token/s prefill**. Decode is memory-bound, not CPU-bound: 97% utilisation, ~373 GB/s of model
reads, and it scales with the memory clock (88 token/s at +2500 memory, ratio 1.19 against 1.18). This includes tiny inter-repetition gaps in both the power
window and aggregate throughput. It refuses a changed build, missing event, changed token count,
nonzero exit, wrong model hash, or missing executable. The window validation is in the [Job 28 report's review](../../docs/gpt-findings/2026-09-27-llm-workload-build.md). The 200-repetition default
for prefill gives a roughly 28-second window on the first tested 5060 Ti. Five decode repetitions
give roughly 15 seconds. Shorter explicit `--iterations` values make a sparse or delayed power
window less trustworthy, even if `llama-bench` returns valid timings.

The elevated logged-sweep wrapper accepts only the names `llm-prefill` and `llm-decode` for this
runner. It checks for `llama-server` before logging; the standalone workload also refuses if that
process exists. The sweep's existing free-VRAM, baseline, video-engine, clock-reset and no-spaces
command guards still apply. This test covers **one model, one quantization, batch 1 and one pinned
llama.cpp build**. It cannot by itself establish an LLM-wide optimum, cross-card behavior, or a
voltage-floor mechanism. Claude will register any GPU sweep after review.

---

## Application workloads (2026-10-08, REGISTERED-PREDICTIONS §21)

`gpu_workload.py --workload alexnet|resnet50|kmeans|hotspot` runs one complete application task per
iteration, from `app_workloads.py`, and reports `image/s` or `task/s`. The CNNs are the torchvision
architectures with seeded random weights on a seeded synthetic batch (no download, no pretrained
checkpoint); k-means and HotSpot are PyTorch ports of the algorithms on generated inputs. Read the
module docstring before quoting them as "real applications". Checked by `test_app_workloads.py`
(CPU references); iteration counts from the 2026-10-08 pilot are in the §21 registration.

## Why a separate benchmark exists

The sweep needs a performance number at every frequency. A fixed-**time** stress test (OCCT,
FurMark, Afterburner's bundled `gpu_stressor.exe`) cannot give one — it runs for N seconds no
matter how fast the card is. A fixed-**work** benchmark does identical arithmetic every run, so
duration *is* the performance metric and efficiency falls out as `work / (duration × power)`.

Without `-WorkloadCommand`, the sweep still produces a valid power-vs-frequency curve. It just
cannot compute efficiency, and it says so in its own output.

### Two workloads, deliberately

The V100 analysis found the efficiency-optimal frequency depends on whether a workload is
compute-bound or memory-bound — correlation **−0.666** between frequency sensitivity and optimal
clock. Reproducing that contrast on consumer hardware needs both:

- **`gemm`** — large matrix multiply via cuBLAS. Compute-bound, scales nearly linearly with core
  clock. Chosen over a homemade kernel because `GeMM` is one of the 33 workloads in the published
  V100 dataset, making the two directly comparable.
- **`membw`** — large elementwise stream over VRAM. Bandwidth-bound and much *less* sensitive to
  core clock. That contrast is the point.

  Measured, not assumed — and weaker than first claimed. Over a 2.2× clock range this card gives
  an elasticity of throughput to core clock of **≈0.35** for `membw` against **≈1.09** for `gemm`.
  So `membw` is strongly sub-linear but **not flat**: it gained 35% throughput for a 123% clock
  increase. At 1236 MHz the SMs cannot issue memory requests fast enough to saturate DRAM, so the
  workload is issue-limited there rather than bandwidth-limited. Earlier wording in this file and
  in `gpu_workload.py` called it "largely insensitive", which the data does not support.

---

## Usage

**Always dry-run first.** It changes no GPU state and prints the planned grid:

```powershell
.\Invoke-FrequencySweep.ps1 -SessionLabel "5060ti-first" -DryRun
```

Then, from an **elevated** PowerShell (clock locking requires administrator rights — the script
refuses to start otherwise rather than failing halfway through with the clock pinned):

```powershell
.\Invoke-FrequencySweep.ps1 -SessionLabel "5060ti-gemm" -WorkloadCommand "python tools\frequency-sweep\gpu_workload.py --workload gemm --json"
```

Run the benchmark standalone to sanity-check it first:

```powershell
python gpu_workload.py --workload gemm
```

### Key parameters

| Parameter | Default | Notes |
|---|---|---|
| `-FrequencyCount` | 13 | Matches the V100 dataset's grid size. |
| `-MinFrequencyPercent` | 40 | Floor as a % of max clock. See below. |
| `-MinFrequencyMhz` / `-MaxFrequencyMhz` | 0 (unset) | Absolute band in MHz, for **fine** sweeps. Overrides the percentage floor. |
| `-SettleSeconds` | 8 | Wait after locking before measuring. |
| `-MeasureSeconds` | 20 | Telemetry window per point — **only** when no `-WorkloadCommand` is given. With a workload, sampling runs as long as the workload does. |
| `-SampleIntervalSeconds` | 0.5 | Telemetry period. Power is averaged over the benchmark's timed region only (~8–10 s), so this needs to be fast enough to leave a usable number of samples inside it. |
| `-DryRun` | off | Plan only, touch nothing. |

**On `-MinFrequencyPercent`:** consumer cards report absurdly low clocks as supported — an
RTX 5060 Ti offers 180 MHz against a 3090 MHz max, under 6%. Sweeping evenly from there wastes a
third of the run on frequencies that will never be efficiency-optimal and makes a fixed-work
benchmark crawl. The V100 dataset only swept 49–100% of its max and found its optimum at 62%. The
default of 40% keeps the grid where the answer lives.

---

## Measurement integrity

Two bugs were found by benchmarking the benchmark against known hardware limits, on an
RTX 5060 Ti. Both are fixed; both are recorded here because both produced data that looked
entirely ordinary and was wrong.

**1. Monitoring was inside the timed region.** The temperature check ran every 5 iterations
between the start and stop of the performance timer. An `nvidia-smi` call is a process spawn —
**42 ms** on this machine — so at `membw`'s 600 iterations that was 120 spawns, and *over half*
the measured duration was the GPU sitting idle waiting on a subprocess.

| | before | after |
|---|---|---|
| `gemm` | 15.60 TFLOP/s | **17.62 TFLOP/s** |
| `membw` | 204.83 GB/s | **414.23 GB/s** |

Both halves were measured back-to-back on the same machine state, so the before/after
comparison is sound and the `membw` figure roughly doubling is the real size of the bug.

> **Correction.** This table originally cited "92% of its 448 GB/s" as the sanity check that
> made the corrected `membw` number credible. That comparison was wrong: these runs were taken
> while a **memory overclock was still applied**, and 448 GB/s is the *stock* rating
> (14001 MHz × 128-bit). Measured later at stock memory, the same benchmark reaches
> 343.7 GB/s — 77% of 448 GB/s, a normal stream efficiency. The bug and its magnitude are
> unaffected; only the "92% of peak" gloss was, and it is recorded here rather than edited away
> because it is the same class of mistake as the ones this section exists to document —
> a plausible number that nobody checked the conditions of.

The check is now **time-based** rather than iteration-based (an iteration cadence polls more
often on a fast card than a slow one) and its subprocess time is measured and subtracted.
`duration_seconds` is work-only; `wall_seconds` and `monitoring_overhead_seconds` are reported
alongside it so the correction is auditable.

**2. Power was averaged over a wider window than performance.** The sweep sampled power for the
whole workload *process* while taking performance from the benchmark's internal timer — so the
average included **~2.3 s of Python import and CUDA init at idle**. Replicating the sweep's exact
sampling loop: `power_avg_w` recorded **124.77 W** against **148.52 W** actually drawn under
load, a **16%** understatement of a number that efficiency divides by.

The benchmark now stamps its timed region in epoch time (`timed_region_start_unix` /
`_end_unix`) and the sweep windows its samples to that interval, recording `power_window_applied`
and keeping the whole-process figure as `power_avg_process_w` for comparison. If stamps are
missing or fewer than two samples land in the window, it falls back to the process-wide average
and says so loudly rather than reporting a diluted number silently.

Since 2026-09-21 the sweep CSV also preserves those bounds as `window_start_unix` and
`window_end_unix`. `join_hwinfo_voltage.py` uses the benchmark windows automatically when both
stamps are present on every point; older CSVs still join by achieved clock. A partially stamped
CSV is refused. Time joins keep every HWiNFO reading inside the timed region, including a low-power
reading that could signal a failed run, and refuse to write an extract if any point has no samples.
HWiNFO writes local Date/Time without a time zone: join on the collection machine or supply
`--hwinfo-utc-offset=-07:00` with the offset that applied when the log was collected. The tool
records the resolved UTC offset in every time-joined extract row and refuses a log spanning an
offset change. It has a `--join-by clock` override for comparing against the historical method.
No existing voltage extract is changed by this update. A synthetic clipped-clock test covers the
new path. **Verified on hardware 2026-09-22:** all 61 sweeps collected that day time-joined,
775 points, none empty, minimum 13 samples, 1.99 samples/s recovered against a 0.50 s interval. The stamps bound
the benchmark's wall-clock region, including brief monitoring pauses; `duration_seconds` subtracts
those pauses, so the window is not an exact active-work-only interval.

**3. A second power figure, from schema 0.3.4 (2026-10-06).** `gpu_workload.py` also reads NVML's
cumulative energy counter (`nvmlDeviceGetTotalEnergyConsumption`, millijoules) at the two edges of
its timed region, matched to the card by PCI bus id (`openEnergyCounter`; it returns nothing rather
than guess on a multi-GPU machine). The sweep CSV carries `energy_joules`, `energy_window_seconds`
and `energy_avg_power_w` beside `power_avg_w`. **The two figures disagree per window by several
percent, and the sign flipped between two sessions** (REGISTERED-PREDICTIONS §17–§19): the 2 Hz
figure often opens on an idle sample (GPT Job 57), `power.draw` is a trailing one-second average, and
the counter's per-window figure may be disturbed by polling (untested). Every registered median
optimum is the same on either figure; per-workload optima can move by up to three grid steps. Neither
is a shunt measurement. `analysis/compare_energy_power.py` compares them per point.

**Why this mattered more than the absolute error:** both were fixed wall-clock offsets, so each
shrank as a fraction of the run when the sweep locked the clock lower — and they tilted the
efficiency curve in *opposite* directions. Overhead-in-timer penalised high frequencies (pushing
the apparent optimum down); power dilution flattered them (pushing it up). Frequency-dependent
bias in duration or power is bias in the location of the efficiency optimum, which is the single
number this project exists to measure.

### Verified end-to-end (3-point sweep, RTX 5060 Ti, `20260815-233703_verify-3pt`)

| target | achieved | duration | throughput | power (windowed) | power (process-wide) |
|---|---|---|---|---|---|
| 1237 MHz | 1236 (yes) | 19.47 s | 6.78 TFLOP/s | 52.34 W | 47.83 W |
| 2167 MHz | 2942 (no) | 7.57 s | 17.42 TFLOP/s | 162.91 W | 132.67 W |
| 3090 MHz | 2941 | 7.69 s | 17.16 TFLOP/s | 162.62 W | 133.81 W |

**Frequency response holds.** 2.38× the clock produced 2.57× the throughput, so fixed-work
duration does track core clock and the performance metric is real. (Slightly super-linear;
the low-clock point ran 19 s and was exposed to background desktop load for longer, which is
the likeliest explanation and a reason to sweep on a quiet machine.)

**The power-window fix is worth more than the static estimate suggested**, and in the predicted
pattern: it recovered 8.6% at 1236 MHz but **22.8%** at 2942 MHz, because a fixed ~2.3 s of CUDA
init is a larger share of a 7.6 s run than a 19.5 s one. Efficiency computed from the diluted
numbers reads 141.7 vs 131.3 GFLOP/J — a 7.9% gap. Corrected: 129.5 vs 106.9 GFLOP/J — a **21.1%**
gap. The bug would have understated the consumer headroom gap by more than half.

**Still unverified:** the `membw` half. That `gemm` is clock-sensitive is now measured; that
`membw` is *insensitive* — the contrast the whole compute-vs-memory-bound comparison rests on —
has not been swept yet.

### A sweep whose workload never launched used to look exactly like a good one

**Added 2026-09-12, after it happened.** A sweep locked clocks, sampled telemetry at every
frequency, wrote a CSV, printed a normal summary and exited **0** — having never once launched
its benchmark. The `-WorkloadCommand` named an interpreter on one drive and a script on another,
so every invocation failed instantly. The card sat at ~18 W for the whole run.

**Nothing in the tool noticed, and nothing downstream would have.** The power column is real —
it is the genuine idle draw of a locked card — so the file parses, plots and joins like any
other. Only the empty `bench_throughput` column gives it away, and only if someone looks. It is
the same shape as the 2026-08-16 sampling defect that recorded idle power at every frequency.

Two guards now exist, both in `WorkloadResultVerdict.ps1`:

| guard | when it fires |
|---|---|
| **fail fast** | the FIRST measured point returns no benchmark result — the sweep stops there rather than spending the remaining hour measuring an idle card |
| **final verdict** | at the end, classifying the run `ok` / `partial` / `none` / `not-applicable`, printed and written to the session JSON as `workload_result_verdict` |

**A run with no benchmark result at any point now exits 7**, so `Invoke-SuiteReplicate.ps1` and
anything else driving this in a loop can tell. A run with SOME missing points exits 0 and warns:
one frequency can legitimately fail while the rest of the curve is sound.

**A sweep with no `-WorkloadCommand` is `not-applicable`, not a failure.** Sampling an
external load is a legitimate mode, and failing it would make the guard something operators
route around rather than read.

**It answers one question only: did a measurement come back at all.** A workload that ran
badly and returned a wrong-but-positive number passes. And **sweeps collected before this date
carry no `workload_result_verdict` field**, so they cannot be audited for it retrospectively —
the same unfixable cost as the VRAM-occupancy guard that shipped late.

### Grid resolution matters more than grid floor

An earlier 3-point sweep found efficiency highest at its lowest point and this file concluded
**"the 40% floor is too high on this card."** That was wrong, and it is corrected here rather than
deleted because the reasoning error is the useful part.

A 13-point sweep puts the efficiency optimum at **1552 MHz** — inside the original 40%-floor range
all along, just never sampled by three points. The floor was fine; three points were not. The
mistake was over-applying the project's own criterion, where "the optimum lands on the lowest
frequency tested" indicates a range that stops short: **that only follows for a dense sweep.** On a
sparse one it is equally consistent with the optimum sitting between the first and second points.

Lowering the floor to 15% still earned its keep, for a different reason than the one given: with
points down to 464 MHz, efficiency is seen to *fall* below 1552 MHz, which proves the optimum is
interior rather than an edge. Finding a peak and showing it is a peak are different claims.

**Practical guidance:** default to 13 points. If you must run fewer, do not conclude anything about
where the optimum is — a sparse sweep can bracket it, not locate it.

### Fine sweeps, and why a tight band is the wrong instinct

Once a coarse sweep has bracketed the optimum, `-MinFrequencyMhz` / `-MaxFrequencyMhz` put all 13
points in its neighbourhood:

```powershell
.\Invoke-FrequencySweep.ps1 -SessionLabel "5060ti-gemm-fine-p1" -MinFrequencyMhz 1200 -MaxFrequencyMhz 1900 -WorkloadCommand "..."
```

The obvious move is to sweep tightly around the peak — and it is the wrong one. **An efficiency
curve is flat near its optimum by definition**, so a tight band buys frequency resolution and pays
for it in signal. In the 13-point coarse run `gemm`'s peak stood only 1.8% above points ±218 MHz
away, while that same run contained an unexplained 0.6% non-monotonicity between 1987 and 2205 MHz.
Squeeze the band and the point-to-point differences fall below that noise, at which point the
highest point is chosen by chance.

Two consequences, both of which apply to any fine sweep in this repo:

- **Choose a band across which efficiency visibly falls** — 1200–1900 MHz here, where the curve
  drops ~7% from peak, rather than 1300–1800 where it drops ~2%.
- **Run at least two passes and analyse the shape, not the argmax.** On synthetic curves with a
  known peak, this grid and realistic noise, the raw argmax moved **53–60 MHz between identical
  passes**. `analysis/analyze_fine_sweep.py` fits the curve instead, and
  `analysis/test_analyze_fine_sweep.py` is the evidence that the fit works.

Order the passes so each workload appears both early and late in the run (`gemm, membw, membw,
gemm`). The card warms over a long sweep, so run position is confounded with temperature, and the
comparison between workloads is the whole measurement.

### A manual OC silently destroys a sweep

In that run `-lgc 2167` produced **2942 MHz** — the cap was not applied at all, overshooting by
775 MHz. Re-running the identical grid with the Afterburner curve reset to stock produced
**2143.8 MHz, held** (`20260815-234947_verify-3pt-stock`). Same script, same targets, one variable:
the flattened V/F curve (≈3010 MHz above 925 mV) is the cause, not merely consistent with it.
1237 MHz locked normally in both runs, being below the curve's ~1900 MHz floor where the override
does not reach.

The damage is not the one bad row. **Overshooting points collapse onto the same achieved clock**,
so a grid that reports N points delivers fewer, with duplicates quietly overweighting one
frequency. That 3-point sweep measured 2 distinct clocks. On a 13-point grid, the entire middle
of the range can vanish into one value while the CSV still looks complete.

The sweep now detects this: `lock_miss_direction` separates `above` (cap not applied — investigate)
from `below` (power/thermal limits — ordinary, and expected at max boost, where 3090 MHz honestly
runs at 2941). It reports distinct-clocks-measured against planned, and names the collapsed
targets. **Reset any overclocking utility to stock before a real sweep, and check
`distinct_clocks_measured` in the session JSON before using the data.**

---

## Safety

This is the first tool in the repo that **changes GPU state** rather than only observing it, so
the reset path matters more than the measurement.

- **Do not click inside the console window while a sweep runs.** Windows enables QuickEdit by
  default, so a click puts the console into selection mode, and selection mode **blocks all output**,
  freezing the script on its next write — with no error, the process still alive, and *the clock
  still locked*. It happened: a sweep stalled for six minutes and corrupted the two frequency points
  either side of the stall. The script now disables QuickEdit at startup
  (`tools/Disable-QuickEdit.ps1`), so this should not recur; if it ever does, click the window and
  press <kbd>Esc</kbd> and the run resumes where it stopped. The tell is the word `Select` prepended
  to the window title.
- The sweep body is wrapped in `try/finally`; the finally **always** issues `nvidia-smi -rgc`,
  then reads the clock back and reports loudly if the reset did not take.
- **Ctrl+C is intercepted** rather than allowed to terminate the process, so stopping early
  unwinds through that same reset path instead of leaving the card pinned.
- **Clock locks do not survive a reboot.** If anything ever looks wrong, restarting returns the
  card to stock. That is the backstop.
- It refuses to run un-elevated, and warns when utilisation is low with no workload supplied —
  an idle sweep measures nothing.

`gpu_workload.py` is ordinary arithmetic, the same work any game or training run does. A compute
workload has no path to permanent hardware damage, and the card enforces its own thermal and power
limits underneath anything software requests. Additional rails regardless:

- Temperature ceiling polled every `--temp-check-seconds` (default 2 s) against `--max-temp`
  (default 88 °C), aborts cleanly.
- Finite, bounded iteration count. No infinite loops.
- VRAM freed on exit including on error, so repeated sweep points don't accumulate allocations.
- It never touches clocks, voltage, or power limits — only the sweep script does, and only through
  documented `nvidia-smi` calls.

If a run crashes the display driver, that is a **finding about stability at the applied settings**,
not damage. It is also exactly what the stability logger's verdict logic is built to catch.

---

## `probe_launch_bound.py` — is the workload CPU-launch-limited?

A diagnostic, not a sweep. Answers one question: does the CPU fail to feed the GPU as kernels
shorten at high clock? It matters because a yes would suppress high-clock throughput and bias the
measured efficiency optimum downward.

```bash
python tools/frequency-sweep/probe_launch_bound.py --rounds 3 --json out.json
```

It holds total bytes moved constant while varying bytes-per-kernel over a 32× range, so the launch
count changes 320 → 10240 while the work does not. A launch-limited workload must speed up as
kernels grow. It then replays the identical sequence from a CUDA graph, which removes nearly all
per-launch CPU work — the same kernel size against itself, so cache behaviour is controlled.

**Answer on this card: not launch-limited.** 0.5% throughput spread across the range, −0.1% from
graph replay. Full result in `data/probes/README.md`.

Two things this script does that are worth copying into any similar probe:

- **It refuses to report a verdict it cannot support.** If achieved clock varies more than 60 MHz
  between conditions, or any condition runs under 2 s, it prints `UNTRUSTWORTHY` and says what to
  change. Both guards fired during development and both were correct: the first draft ran each
  condition in 250 ms, which left the 100 ms sampler two or three samples per window, and the clock
  guard then correctly flagged a 1302 MHz "spread" that was really the card boosting up from idle.
- **It settles before measuring.** 20 s of untimed work first. Without it, the ramp from idle is
  charged to whichever condition happened to run first — which on a reversed-order design is a
  different condition every round.

The `cpu_submit_fraction` field is the one to read. At 16 M elements per kernel the CPU spent 90% of
wall time submitting launches and throughput was unaffected; at 512 M it spent 0.0% and throughput
was the same. **A high CPU cost is not a CPU bottleneck**, and only one of those is a defect.

---

## What the control APIs actually allow

Verified directly against an RTX 5060 Ti on driver 610.88 by dumping `nvml.dll`'s export table and
calling the API through P/Invoke — not assumed from documentation.

| Capability | Status |
|---|---|
| Lock core clock (`nvidia-smi -lgc`) | **Works.** Volta+; Blackwell qualifies. Needs admin. 389 discrete clocks supported, 180–3090 MHz. |
| Set power limit | **Works.** Adjustable 150–200 W on this card (default 180 W). Needs admin. |
| Per-P-state clock offsets (`nvmlDeviceSetClockOffsets`) | **Available.** Reads SUCCESS; graphics ±1000 MHz, memory −2000/+6000 MHz. Writes return `NO_PERMISSION` un-elevated — meaning the API works and wants elevation, not that it is unsupported. |
| Global V/F offset (`nvmlDeviceGetGpcClkVfOffset`) | **NOT_SUPPORTED** on this card. Closed on consumer Blackwell. |
| Read or write **voltage** | **Impossible via NVML.** Zero voltage exports across all 260 device functions. |
| Per-point V/F curve reshaping | Undocumented NVAPI only (`ClockClientClkVfPointsSetControl`). Out of scope — can break on any driver update. |

The voltage limitation is the honest constraint on this whole project: **the sweep measures
frequency versus power, not voltage.** Any write-up must say so plainly rather than describing
this as undervolting research.
