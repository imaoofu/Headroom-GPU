# GPU Stability Logger

Records what a GPU actually did during a stress test, and writes a verdict plus a machine-readable
session record.

**Requires:** Windows, an NVIDIA GPU with drivers installed. Nothing else — no Python, no packages.
It calls `nvidia-smi`, which ships with the driver.

---

## Usage

```powershell
.\Log-GpuStability.ps1 -SessionLabel "build07-uv900" -AppliedSettings "900mV @ 2700MHz, mem +500" -TestMethod "OCCT 3D Adaptive" -DurationSeconds 900
```

The intended workflow:

1. Apply the clock/voltage settings you want to test, **by hand**, in MSI Afterburner.
2. Start this logger, telling it what you applied via `-AppliedSettings`.
3. Start your stress test — OCCT, FurMark, 3DMark, or a real game.
4. Let it run. It writes a verdict when the duration elapses.

### Parameters

| Parameter | Default | Notes |
|---|---|---|
| `-SessionLabel` | `unlabeled` | Short name; becomes part of the filename. |
| `-AppliedSettings` | *(warns if unset)* | What you set, in your own words. **Nothing can reconstruct this later.** |
| `-TestMethod` | *(warns if unset)* | What stress test is running alongside. |
| `-DurationSeconds` | `600` | How long to sample. |
| `-IntervalSeconds` | `1` | Seconds between samples. |
| `-OutputDirectory` | `..\..\data\stability-runs` | Where logs land. |

### Exit codes

`0` = CLEAN · `1` = FLAGGED · `2` = UNSTABLE · `3` = INCONCLUSIVE — so this can be driven from a
batch script later. `INCONCLUSIVE` is deliberately non-zero: a caller treating "not 0" as failure
will correctly stop on a run whose stress test died.

---

## Output

Two files per run, named `<timestamp>_<label>_*`:

**`_samples.csv`** — one row per sample: timestamp, elapsed seconds, SM clock, memory clock, power
draw, temperature, GPU/memory utilisation, fan speed, memory used, throttle bitmask, and the decoded
throttle reasons.

**`_session.json`** — the run's metadata and summary: GPU identity, driver and VBIOS version, what
settings were applied, the verdict and its flags, and min/avg/max for clock, power and temperature.

Since schema `0.2.0` it also carries **loaded-only statistics**, and those are the ones to read
first: `loaded_fraction`, `loaded_samples`, `sm_clock_avg_loaded_mhz`, `power_avg_loaded_w`,
`temperature_avg_loaded_c` and their min/max. Whole-run averages blend load with idle and describe
neither — on a 25-second test run that was only 23% idle, whole-run power read 135.91 W against
168.88 W actually drawn under load, a 24% understatement. Same failure the frequency sweep had
before it windowed power to the benchmark's timed region.

Every sample is flushed to disk immediately rather than buffered. If the machine hard-locks, the
truncated log is the evidence — the last timestamp is roughly when it died.

---

## Verdicts

| Verdict | Meaning |
|---|---|
| `CLEAN` | Nothing went visibly wrong, **and** the card was genuinely loaded for most of the run. |
| `INCONCLUSIVE` | Nothing went wrong, but the GPU was under load for under half the samples. The run says nothing either way. |
| `FLAGGED` | Thermal or hardware throttling seen, or the run ended early. Not necessarily instability. |
| `UNSTABLE` | A display-driver crash/reset event, or telemetry queries started failing. |

**Why `INCONCLUSIVE` exists.** A verdict computed over an idle card is worthless in a way that looks
exactly like success. An hour-long run on 2026-08-16 finished its workload after 13 minutes and idled
for the remaining 47; the session reported `CLEAN` with `sm_clock_avg` 1699 MHz, `power_avg` 39.3 W
and `util_avg` 24.9% — all plausible figures, none describing the loaded period (2970 MHz, 118 W,
98%). Nothing distinguished *"survived an hour of load"* from *"the load died after 13 minutes."*

That is precisely the event this tool exists to catch: **a stress test that crashes leaves the GPU
idle for the remainder**, so the failure mode and the success signature were identical.

**A CLEAN verdict is not proof of stability.** Undervolt failures routinely take hours to appear, and
a single clean 10-minute run is weak evidence. Report it as "no failure observed in N minutes," never
as "stable."

---

## Non-goals, on purpose

**It does not apply GPU settings.** A script that sweeps voltage unattended can hard-lock or
destabilise a machine mid-test, and on a customer's build that is not an acceptable failure mode.
Automating the sweep is a decision to make deliberately later — not one to inherit by accident from
a logging tool.

**It cannot see a crash that takes the whole machine down instantly.** It infers one from a truncated
log, which is weaker evidence than a recorded event. The verdict says so when it happens.

---

## Protocol — v1.0.0, locked 2026-08-23

**Run it with one command.** `Invoke-StabilityProtocol.ps1` IS the protocol; the steps below
describe what it does so the description cannot drift away from the code.

```powershell
.\tools\stability-logger\Invoke-StabilityProtocol.ps1 `
    -SessionLabel "splitcurve" -AppliedSettings "split curve, mem +2500, PL 111%"
```

| step | what | why this and not something else |
|---|---|---|
| 1 | Preflight: refuse on active video engines or a GPU above 10% | Same two checks as the sweep. Instant Replay is invisible to `utilization.gpu` and cost 1.5-4.2% of measured throughput. |
| 2 | Thermal soak, first 5 min of each phase recorded but excluded | Throughput always falls as a cold card warms. Comparing a cold first sample against a hot last one flags every healthy configuration. |
| 3 | Phase 1: `gemm` for half the duration | Compute-bound. Loads the SMs and the power budget — where a core undervolt fails. |
| 4 | Phase 2: `membw` for half | Bandwidth-bound. Loads the memory system — where a memory overclock fails. |
| 5 | No clock locking | The card runs its own boost behaviour, because that is how the configuration will be used. |
| 6 | Verdict from three independent signals | Telemetry verdict, aborted iterations, post-soak throughput drift. Any one failing sinks the run. |

Default duration 30 minutes. Report a pass as **"no failure observed in 30 minutes"**, never as
"stable".

### Why this supersedes the OCCT protocol locked on 2026-08-14

The earlier protocol specified OCCT GPU:3D Adaptive with Error Detection, 10 minutes, started
before the logger. The reasoning behind that choice was sound and is preserved below. Two things
went wrong with it.

**It was never executed.** Not once in the nine days it stood. It needed OCCT installed, started
by hand, the logger started separately at the right moment, and then a *fourth* manual step — a
three-run benchmark comparison — to cover a gap the section itself identified. Four steps with an
ordering constraint, none automated. A protocol nobody runs is not a protocol, and the honest
diagnosis is that it asked too much rather than that anyone was negligent.

**It could not see the failure mode that matters most here.** Its own text says so:

> OCCT answers "is it stable," not "is the memory OC actually faster."

GDDR7 corrects errors silently, so a memory overclock can pass hours of OCCT without a crash,
an artifact or an event-log entry while being **net slower** than stock, because every corrected
read costs a retry that nothing reports. The old protocol deferred this to a separate manual
comparison that was also never run. v1.0.0 folds it into the same command by driving the
project's own fixed-work benchmark in a loop and watching post-soak throughput directly.

### What carries over unchanged, because it was right

- **Always log a stock baseline for each machine before testing tuned settings.** A tuned result
  with no stock comparison from the same chip measures nothing.
- **Change one variable at a time.** Core curve, memory offset and power limit are three separate
  variables; a config that changes all three cannot tell you which one did what.
- **Never report a short clean run as "stable."** Undervolt failures routinely take hours to
  appear. The tool says this in its own output and so should you.
- FurMark is still avoided: modern drivers detect its constant artificial load and can throttle it
  specifically. That reasoning applies equally to any fixed synthetic load, and is why the
  degradation test looks at drift rather than at absolute throughput.

### The degradation threshold is uncalibrated

`-DegradationPercent` defaults to 2.0 and **that number is a guess.** Nobody has yet measured what
normal post-soak drift looks like on a healthy configuration on this card. The only nearby evidence
is the run-to-run spread of the locked sweeps — 0.13% on the split curve, 0.76% on the original
tune — which is a different quantity measured a different way. Until several known-good runs
establish a baseline, **read the reported drift figure and do not lean on the flag.**

---

## Stopping a run early

Press **Ctrl+C** in the window it's running in. It writes the verdict and session JSON for
whatever was collected up to that point, flagged as a user-stopped short run rather than a full one.

This works because the script deliberately intercepts Ctrl+C as a regular keypress instead of
letting PowerShell's default handling terminate the whole process — the default behaviour would
close the CSV safely but skip the verdict and JSON entirely, which is not what "stops early" should
mean. In a non-interactive context (a scheduled task, a redirected session — not your normal use),
that interception itself isn't available; the script detects that and says so, then simply runs to
its full requested duration instead of crashing.

## Verified status

Tested on an RTX 5060 Ti (driver 610.88, VBIOS 98.06.4e.40.b4) — four short runs at idle. CSV and
JSON output confirmed well-formed; throttle-reason decoding confirmed correct against a known idle
state; graceful degradation in a non-interactive shell (no console handle) confirmed working.

**Now tested under real load (2026-08-16).** One hour of sustained CUDA inference on an
overclocked card: 1760 samples, **zero telemetry failures**, clean exit, well-formed output. The
`INCONCLUSIVE` and `CLEAN` paths were then verified directly — an idle 20-second run returns
`INCONCLUSIVE` with exit 3, and a 77%-loaded 25-second run returns `CLEAN` with exit 0.

**Still never fired against a real failure.** The throttling path has not triggered (the card never
approached its limits — 139 W peak against a 200 W limit, 64 °C), and no driver crash has occurred,
so crash detection remains unvalidated. Treat the detector as unproven for the cases it exists to
catch. **The interactive Ctrl+C keypress path is also still untested** — it can't be simulated from a
non-interactive shell, only reasoned through and tested in its degraded form.

### The `GpuIdle` bit lies under compute load

Throughout that hour the card reported throttle bitmask `0x1` = `GpuIdle` on **every sample**, while
sitting at 98% utilisation and 139 W. The decoding is correct; the driver genuinely reports
`GpuIdle` for compute-only workloads that never touch the graphics pipeline.

**So the throttle mask cannot be used to tell whether the card is busy.** The loaded/idle split is
computed from utilisation percentage instead, which works for both compute and graphics loads. This
matters for the locked OCCT protocol too — a compute-mode stress test would look idle to anything
keying off that bit.

Three bugs were found and fixed by smoke testing, all invisible on inspection:

- Throttle reasons were decoded through an `[ordered]` dictionary indexed by integer, which does a
  **positional** lookup rather than a key lookup in PowerShell. Every reason came back shifted by
  one — `0x1` reported as `ApplicationsClocksSetting` instead of `GpuIdle`.
- `| Select-Object -First 1` on the `nvidia-smi` call stopped the pipeline early, killing the process
  mid-write and producing a spurious exit code 255 on every otherwise-successful run.
- `[Console]::TreatControlCAsInput = $true`, added to fix the Ctrl+C behaviour above, itself threw
  "the handle is invalid" and crashed the whole script when no real console was attached. Now
  wrapped so it degrades to "no early-stop available" instead of failing the run.
