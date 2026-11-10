# Collection kit

A self-contained folder that runs a stock frequency sweep on a machine with **nothing
installed** — no Python, no PyTorch, no admin setup beyond one UAC click. Built for shop
builds, where the machine belongs to a customer, time is short, and nobody is available to
debug a failure.

Delete the folder when done and the machine is exactly as it was.

## What it collects

Two 13-point sweeps at stock (`gemm` and `membw`), plus a `machine-info.txt` recording GPU,
driver, VBIOS, CPU, RAM and OS. **About 15 minutes total**, measured — not estimated:

| sweep | duration on an RTX 5060 Ti |
|---|---|
| `gemm`, 13 points | 6 min 42 s |
| `membw`, 13 points | 5 min 11 s |

This matters because `ROADMAP.md` and the original execution plan both budgeted ~5 hours per
machine, which is why collection felt too expensive to start. It is not. A sweep is a coffee
break, and the correction is what makes per-build collection realistic.

## Building the kit

The kit is not committed here — it contains a 4.65 GB copy of Python and PyTorch. Rebuild it:

```powershell
# 1. Copy a working Python that already has torch+cu128 installed.
robocopy "C:\Users\<you>\AppData\Local\Programs\Python\Python312" "E:\headroom-kit\python" /E /MT:16

# 2. Copy the tooling. Sync-Kit.ps1 holds the full file list and refuses when a copied script's
#    import or dot source would not resolve on the kit. (A hand-copy list stood here until
#    2026-10-13; it had fallen several files behind, including two the benchmark cannot run without.)
.\tools\collection-kit\Sync-Kit.ps1 -KitPath E:\headroom-kit
```

Then verify before trusting it:

```powershell
E:\headroom-kit\python\python.exe -c "import torch; print(torch.cuda.is_available())"
```

## Keeping the kit current — do this before every build

**The kit is a snapshot, and it rots.** Because the 4.65 GB Python copy keeps it out of version
control, nothing links the tooling on the USB drive to the tooling in this repository. Every
improvement made here has to be carried across by hand, and a kit that is a version behind still
runs perfectly and still prints `COLLECTION SUCCEEDED`.

```powershell
.\tools\collection-kit\Sync-Kit.ps1 -KitPath F:\headroom-kit -WhatIfOnly   # report
.\tools\collection-kit\Sync-Kit.ps1 -KitPath F:\headroom-kit               # apply
```

It copies tooling only — Python, PyTorch and any collected results are never touched — then
re-hashes every file to confirm the copy landed, and prints the sweep's schema version, which is
the field stamped into every session JSON the kit produces.

**This is not hypothetical maintenance.** Checked on 2026-08-23, three days before a build, the
kit was carrying:

| file | state on the kit | consequence |
|---|---|---|
| `Invoke-FrequencySweep.ps1` | schema 0.1.0 vs 0.3.0 | no `-AppliedSettings`, **no video-engine guard** |
| `Collect.ps1` | pre-08-19 | hardcoded `-stock` into the label, so an OC run wrote `…-oc-gemm-stock_sweep.csv` |
| `Log-GpuStability.ps1` | pre-08-20 | `session.json` written with a UTF-8 BOM, unreadable by any standard JSON parser |
| `CHECKLIST.txt` | pre-08-22 | no mention of Instant Replay, the contaminant that cost this project two days |

Not one of those announces itself at collection time. Each produces a run that looks completely
successful and is quietly worth less than it should be.

**A plain copy of a normal Python install is relocatable** — verified on a different drive
letter, CUDA still detected, and the workload returned 412 GB/s against 415 GB/s from the
installed copy. An embeddable-Python build is not required and is harder to get right.

First `import torch` from cold storage takes ~45 s; subsequent imports are ~1.5 s once the OS
caches the DLLs. The sweep launches Python once per frequency, so this is a one-off cost, not
13 × 45 s. Copying the kit to the target machine's local disk before running keeps it fast.

## Two things that will bite whoever rebuilds this

**Paths must not contain spaces.** `Invoke-FrequencySweep.ps1` hands its `-WorkloadCommand`
string to `cmd /c` via `Start-Process -ArgumentList`, which mangles embedded quotes. Measured
directly: the quoted form fails with *"The filename, directory name, or volume label syntax is
incorrect"*, the unquoted form runs fine. The existing sweeps only ever worked because they
used unquoted relative paths. `Collect.ps1` resolves 8.3 short names and refuses up front if
the resulting command still contains a space — because discovering this halfway through a
clock-locked sweep is much worse than refusing to start.

**`tuning_state_claimed` is an assertion the script cannot verify.** Nothing in `nvidia-smi`
reliably reports whether an Afterburner profile is applied, so that field records what the
operator was *supposed* to do — and it would say `STOCK` just as confidently on a run where
someone forgot. This is the same gap that made an earlier stability run unusable.

The fix is that the kit also appends `peak_sm_clock_mhz[<workload>]`, taken from the achieved
clock the sweep already records. That is a measurement, not a claim, and on a known model the
stock/tuned gap dwarfs run-to-run noise — on this RTX 5060 Ti, **2588 MHz stock against
~2950 MHz tuned**.

**The memory clock under load is witnessed inside the probe's own timed work (2026-10-13).** Until
then `Collect.ps1` sampled for a fixed 24 s and then waited without sampling, so a slow cold start
could put all the probe's work after the window (GPT Job 88). Reproduced live on the 5060 Ti with a
40 s delayed start: the old loop recorded **405 MHz "under load"**, an idle clock, while the probe
was still loading.

The first replacement counted any GPU-busy sample from launch on. GPT Job 89 showed that start-up or
another process could then supply the reading (W1), that an exception could orphan the probe (W2), that
a hung `nvidia-smi` defeated the deadline (W3), and that the witness ignored Collect's resolved
`nvidia-smi` (W4). `MemoryWitness.ps1` now:
- samples memory clock and utilisation with a timestamp, each query a bounded child process;
- reads the probe's JSON result, requires `ok` and a timed region, and counts only samples inside
  `timed_region_start_unix`..`timed_region_end_unix` with the GPU at least 50% busy (three needed);
- kills and verifies the probe on a deadline (30 minutes, a hang guard only) or an error.
Inside the timed region utilisation is still device-wide: it shows the GPU was busy while the probe
worked, not that the probe alone made it busy. The quiet-process checks keep other GPU work away.

**Live, 2026-10-13 evening, with a +2500 memory overclock applied** (so 16301 MHz is the right reading):
this PC's Python, timed work beginning 21.2 s after launch, 20 samples inside it; **the USB kit's own
Python, timed work beginning 929.1 s (15.5 minutes) after launch**, 19 inside and 2 busy outside, both
16301 MHz. The cold start from the USB is real and long, which is why the deadline is not shorter.
(An earlier figure here, "760.6 s", was the first device-busy sample under the old witness, not the
probe's own timing.) One NVIDIA GPU only: two make it refuse. Fixtures, nine Windows tests with a fake
`nvidia-smi` and a CPU-only probe: `analysis/test_memory_witness.py`.

**Peak clock is recorded per workload and must never be pooled.** The two workloads draw
different power and so reach different clocks at identical settings: measured at stock,
`gemm` 2598 MHz against `membw` 2753 MHz — a 165 MHz spread from workload alone. A pooled
figure reports membw's 2753 and invites comparison against gemm's ~2597 stock reference, which
looks like a 156 MHz overclock and is nothing of the sort. Compare each workload only against
the same workload's reference.

## Running it

`RUN-ME.bat` — double-click, click Yes on UAC, type a label, wait. Full operator instructions,
including every failure message and what to do about it, are in `CHECKLIST.txt`. That file is
written to be printed and followed by someone who has never seen the project.
