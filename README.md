# Headroom: consumer GPU frequency-efficiency sweeps with voltage telemetry

**Version 1.2.0.** Zi Chen Raymond Chuang. Data CC BY 4.0, code MIT.
DOI: [10.5281/zenodo.23547564](https://doi.org/10.5281/zenodo.23547564); all versions [10.5281/zenodo.23251532](https://doi.org/10.5281/zenodo.23251532). Released 2026-10-21.

This dataset holds **1088 locked-clock frequency sweeps** measured on **four consumer NVIDIA
GPUs across three architectures**, collected between 2026-08-16 and 2026-10-09. Each sweep locks
the core clock at a series of target frequencies and runs a fixed amount of GPU work at each one,
recording throughput, board power, achieved clock and temperature, and in all but ten early sweeps
memory clock; whether each lock held is recorded per target. **729 of the
sweeps also carry a joined extract of core voltage and crossbar clock** read from HWiNFO.

Most sweeps reach far below each card's stock clock, typically down to about 40% of its maximum
lock target. That does not guarantee every sweep brackets its optimum: in 44 sweeps the best sampled
point sits at a grid edge, so check before treating a grid maximum as an optimum. The two modern
consumer DVFS tables this project compared against (HKBU's GTX 1080 Ti and RTX 2070 Super sets) span
about 89–111% of their cards' declared default clocks and record no voltage; they are not part of
this release.

| card | architecture | board | dataset-grade sweeps |
|---|---|---|---:|
| RTX 5060 Ti 16 GB | Blackwell (GB206) | Zotac Twin Edge OC | 846 |
| RTX 3070 Ti | Ampere (GA104) | Gigabyte Gaming OC rev 2.0 | 137 |
| RTX 2060 Super | Turing (TU106) | MSI Ventus 2X | 91 |
| RTX 3060 12 GB | Ampere (GA106) | ASUS Phoenix | 14 |

**There is one physical card per model.** Repeated sweeps and many workloads are repeated
outcomes on that one chip, not independent chips. Read `DATASHEET.md` before using the data; it
states how the data were collected, what is known to be wrong with parts of it, and what it
should not be used for.

## What is in a sweep

Each sweep is a pair of files, plus an optional third, named by start time and session label:

| file | contents |
|---|---|
| `<stamp>_<label>_sweep.json` | session metadata: GPU, driver, power limits, the exact workload command, the declared Afterburner configuration (`applied_settings`), preflight checks (idle load, video engines, free VRAM), sweep order, planned and measured frequencies, schema version |
| `<stamp>_<label>_sweep.csv` | one row per target frequency: achieved clock (avg/min/max), memory clock, whether the lock held, board power (avg/min/max), temperature, utilisation, benchmark throughput and its unit, timed-region bounds; from schema 0.3.4 also NVML's integrated energy over the timed region |
| `<stamp>_<label>_sweep_voltage.csv` | where present: per target, the median HWiNFO core voltage and crossbar clock over the benchmark's timed window, with the sample count (24 early extracts are binned by core clock instead of time; see `DATASHEET.md`) |

Fields vary by collection date: ten sweeps lack memory-clock columns, 357 lack an explicit
`sweep_order`, and 371 lack the timed-region bounds. Throughput units in the CSVs are base units
(`FLOP/s`, `byte/s`, `token/s`, `image/s`, `task/s`), not the TFLOP/s and GB/s that analysis output prints.

Workloads are fixed-work PyTorch kernels from `tools/frequency-sweep/gpu_workload.py`: `gemm`
(compute-bound), `membw` and `copy` (bandwidth-bound), and a twelve-workload suite (`copy`,
`reduce`, `softmax`, `layernorm`, batched `gemm` at five sizes, `attention`, `conv`, `gemm`). Four
sweeps run llama.cpp decode and prefill (`tools/frequency-sweep/llm_workload.py`). Twenty-four
sweeps run four application workloads (`tools/frequency-sweep/app_workloads.py`): AlexNet and
ResNet-50 forward passes with **seeded random weights on a synthetic input batch** (not pretrained
networks or real images), and k-means and HotSpot as **this project's PyTorch ports** on generated
inputs, not the Rodinia binaries. Iteration
counts are constant across a sweep, so throughput at different clocks is directly comparable.

## Where to start

- `data/MANIFEST.json` / `.csv`: every sweep in the release, with card, label, schema, driver,
  number of frequencies and provenance flags. Filter here first.
- `data/frequency-sweeps/**/README.md`: each investigation's own README, giving its purpose, the
  card configuration, what is dataset-grade, and its known problems. **Read the README beside a
  sweep before comparing it with another.**
- `manifest/SOURCE-CENSUS.*` and `manifest/SELECTION.md`: the full source inventory, including
  excluded and verification runs that are not distributed, and the selection rule.
- `data/afterburner-profiles/`: decoded voltage/frequency curves for the hand-edited
  configurations, as numeric JSON with READMEs. The proprietary profile files are not included.

To read the data, install `requirements.txt` in your own Python environment and run, from this
folder:

```
python analysis/analyze_sweep.py --pattern "**/*floor15*_sweep.csv"
```

The collection and analysis code is included so the method can be read and rerun. Collection
needs Windows, an NVIDIA driver, PyTorch with CUDA and a separately installed HWiNFO. **Some
collection tools change GPU state (locked clocks, power limits) and need administrator rights;
read their safety and reset notes first.** Several analysis scripts and the paper's claim audits
also need files not distributed here (raw HWiNFO logs, the project's documents, third-party
datasets), so not every script runs from this release alone. `RELEASE-REPORT.json` lists the
omissions within the source scope it inventories.

## Changes in v1.2.0

Adds two registered studies on the RTX 5060 Ti and the kernel diagnostics behind the bandwidth
discussion. They are **counted separately** from the 1088 sweeps above, with their own manifests under
`manifest/repeatability/`, `manifest/section20b/` and `manifest/probes/`:

- **Day-to-day repeatability (registered §22), `data/repeatability/`.** 40 sweeps: four workloads
  (`gemm`, `copy`, `reduce` and the ResNet-50 forward pass) on a 20-target grid at stock, two passes in
  opposite directions on each of five days, 2026-10-15 to 2026-10-19, with voltage extracts and the
  runner's records. Registered outcome: `gemm` and ResNet-50 lose under 3% of efficiency at 1575 MHz
  (upper bounds 2.965% and 2.547%), and `copy` and `reduce` are inconclusive. Five days are five
  observations of one card.
- **Counter polling (registered §20b), `data/section20b/`.** Four pilot sessions of 144 timed windows
  each, 2026-10-12 to 2026-10-20, asking whether polling NVML's energy counter changes the power it
  reports. **Sizing data, never results:** the study stopped at its registered "insufficient precision"
  outcome with no verdict, because the pilots varied too much between days for any planned confirmation
  stage.
- **Kernel diagnostics, `data/probes/`.** Four probe results with their two READMEs. They are
  diagnostics, not sweeps.
- **Everything needed to re-score both studies from this release:** their scorers and the tools they
  import, both attempt ledgers (`docs/repeatability/`, `docs/section20b/`), and the Afterburner profile
  stores each session witnessed, with the stock reference store
  (`data/afterburner-profiles/5060ti-profiles-20260926-curve3`), which the §22 scorer checks each
  witness against. The registration text (`docs/REGISTERED-PREDICTIONS.md`) ships too, so the
  registered rules can be read beside the outcomes; no scorer reads it. Earlier
  versions did not redistribute profile stores; these are the author's own settings files, shipped only
  as evidence for these two studies. Run, from this folder,
  `python analysis/score_repeatability.py data/repeatability/day*` and
  `python analysis/score_section20b.py data/section20b/pilot*/core`.

No v1.1.0 file was removed, and every v1.1.0 measurement file and per-directory README is
byte-identical here. Updated: code that changed since v1.1.0, the manifests and selection notes, and
`LICENSE-DATA`'s repository link (the repository was renamed; the licence terms are unchanged).

## Changes in v1.1.0

Adds the 24 sweeps of registered session 21 (2026-10-09,
`data/frequency-sweeps/5060ti-session21-20261009/`): the four application workloads above on the RTX
5060 Ti, stock and a tuned curve, each with a voltage extract (73 new files). No v1.0.0 file was
removed, and every v1.0.0 measurement file and per-directory README is byte-identical here. Updated:
the manifests and the desktop-load census (24 more quiet verdicts), and three analysis scripts
(the census totals, a paper-claim check and the citation registry).

## Not included in this version

- Raw HWiNFO logs. The voltage extracts were joined from them, but the logs record whole-PC sensor
  data and are withheld pending a privacy review; without them the joins cannot be redone.
- Per-session runner records (wrapper results, profile-store witnesses) for sessions before the two
  studies added in v1.2.0, which some session READMEs mention.
- Excluded and verification sweeps, the project's paper drafts and private notes, and any
  third-party dataset.

## Integrity

`SHA256SUMS` lists a SHA-256 for every file except itself, computed over the exact bytes
distributed (`CHECKSUMS.md` gives the convention). Measurement files are byte-for-byte copies of
the source repository's committed files; none was edited for this release.

## Citation

See `CITATION.cff`. A paper describing the measurements is in preparation.

## Use of AI tools

The measurements come from the hardware described above. Much of the collection and analysis code
and documentation was written with AI coding assistants (Anthropic's Claude, through Claude Code,
and OpenAI's ChatGPT and Codex) under the author's direction, and much of it was then checked by
separate AI-run audits. The experiments, hardware work and decisions are the author's. See `DATASHEET.md`.

## Section 20b and 22 supplements

See manifest/section20b/README.md (sizing data, never results) and manifest/repeatability/README.md (five-day COMPLETE outcome), and manifest/probes/README.md (diagnostics, not sweep rows). The desktop-load screen is in manifest/DESKTOP-LOAD-CENSUS.csv. Counts and per-cohort README excerpts are separate from the legacy sweep manifest.
