# Datasheet: Headroom consumer GPU frequency-efficiency sweeps, v1.2.0

Following the questions of Gebru et al., *Datasheets for Datasets* (CACM 2021). Author: Zi Chen
Raymond Chuang. Every count below was computed from this release's `data/MANIFEST.json` and files.

## Motivation

**Why was it created?** To measure, openly and reproducibly, how far stock GPU behaviour sits from
the energy-efficiency optimum on current consumer hardware, and to release the measurements. The
public consumer DVFS datasets the project compared against (the GTX 1080 Ti and RTX 2070 Super sets
from HKBU's `GPU-DVFS-Job-Schedule`) sweep about 89–111% of their cards' declared default clocks and
record no voltage. In those tables many applications' best sampled point sits at a grid edge, so the
grid cannot show where their optimum lies. Those tables are not part of this release.

**Who created it, and who funded it?** Zi Chen Raymond Chuang, an independent high-school
researcher, as a solo project. No grant funded it.
The cards were the author's own: the RTX 5060 Ti is the GPU in the author's PC, and the other three
were in PCs the author built and owned while they were on the bench, before sale.

## Composition

**What are the instances?** A sweep: one card, one configuration, one workload, the core clock
locked in turn at a list of target frequencies, with one row of measurements per target. **1088
sweeps, 13,935 target-frequency rows**, collected 2026-08-16 to 2026-10-09.

| card | sweeps | drivers |
|---|---:|---|
| RTX 5060 Ti (Blackwell GB206, Zotac Twin Edge OC) | 846 | 610.88, 616.56, 616.64, 616.92 |
| RTX 3070 Ti (Ampere GA104, Gigabyte Gaming OC rev 2.0) | 137 | 610.88, 617.14 |
| RTX 2060 Super (Turing TU106, MSI Ventus 2X) | 91 | 616.92, 617.14 |
| RTX 3060 12 GB (Ampere GA106, ASUS Phoenix) | 14 | 616.92 |

By workload: `gemm` 192; `copy` and `reduce` 77 each; `bgemm64` 75; `bgemm1024` 73; `softmax`,
`layernorm`, `bgemm32`, `bgemm128`, `bgemm256`, `attention` and `conv` 72 each; `membw` 62; the application
workloads `alexnet`, `resnet50`, `kmeans` and `hotspot` 6 each (AlexNet and ResNet-50 with seeded
random weights on synthetic input; k-means and HotSpot as PyTorch ports); llama.cpp decode and prefill
2 each.

**Configurations.** Most RTX 5060 Ti sweeps vary the card's voltage/frequency curve through MSI
Afterburner profiles: stock, a full tune (flattened upper curve, memory +2500 MHz, 200 W), and
several hand-edited curves that move where the curve leaves its lowest voltage. Each session JSON
records the declared configuration in `applied_settings`, and decoded curves are in
`data/afterburner-profiles/`. A profile slot number is not an identity; slots were overwritten
over time, so use the session's own README and the decoded snapshot, not the slot number.

**Is there a label or target?** No. Throughput (in the base unit given per row: `FLOP/s`, `byte/s`, `token/s`, `image/s` or `task/s`)
and board power are measurements, and efficiency is derived from them by the user.

**Is anything missing?**
- 359 of the 1088 sweeps have no voltage extract (729 do). The 24 oldest extracts were joined by
  binning HWiNFO samples on core clock rather than on the timed window, which is less exact.
- Early schemas lack later fields. Schemas 0.1.0 and 0.2.0 (26 sweeps) have no video-engine
  telemetry, so capture-software contamination cannot be checked; only schema 0.3.4 (156 sweeps) has
  the NVML energy-counter column;
  `free_vram_mb_at_start` is missing from 165 sweeps (flag `no-vram-record`). Ten early sweeps lack
  memory-clock columns, 357 lack an explicit `sweep_order`, and 371 lack the timed-region bounds
  (including 194 of schema 0.3.3, so the schema number alone does not tell you).
- In 44 sweeps the best sampled efficiency sits at a grid edge (33 low, 11 high), and 29 sweeps are
  single-target; a grid maximum there does not bracket the optimum.
- Raw HWiNFO logs, from which the voltage extracts were derived, are not in this version.

**Are there errors, noise or redundancy? Known problems, read before use:**
- **One physical card per model.** No result here establishes chip-to-chip variation, and any
  per-card figure describes one unit.
- **Desktop load.** Ordinary desktop activity depresses measured throughput: NVIDIA Instant Replay
  cost about 4% on average across 1237–2010 MHz in one test, and later the Claude desktop app's visible window cost 6–9% of
  `membw` (in diagnostic runs that are not in this release). Of the 846 RTX 5060 Ti sweeps, a screen of the surviving raw HWiNFO logs finds **91 with
  the rendering signature, 444 checked quiet and 311 that cannot be checked**; the per-sweep result
  is in `manifest/DESKTOP-LOAD-CENSUS.csv`. A quiet verdict is a screen, not proof. Voltage readings
  are much less affected than throughput.
- **Provenance flags.** 180 sweeps carry at least one flag in the manifest (for example
  `no-vram-record`, `no-encoder-telemetry`, `settings-declared-unverified`, or a `baseline-N%` idle
  load). A flag records a condition that differed; it is not an exclusion.
- **Power is the card's own telemetry, not a shunt.** `power_avg_w` averages `nvidia-smi` samples,
  normally at 2 Hz, over the benchmark's timed region; 15 sample-rate test sweeps used 4, 1 and 0.5 Hz
  (five each, see `sample_interval_s`). On the RTX 5060 Ti it disagrees with NVML's integrated
  energy counter (`energy_avg_power_w`) by several percent, and the sign of the disagreement changed
  between two sessions; neither figure is known to be correct.
- **Voltage is a reported VID code, not a measured rail.** It is quantised (5 mV on the RTX 5060 Ti,
  6.25 mV on the other three cards) and did not respond to load in a fixed-frequency test.
- **Cross-session drift.** The same configuration measured on different days differed by about 1.5%
  in `gemm` throughput, so comparisons across sessions carry an offset of that order.
- Lock misses: check `lock_miss_direction` per row. `below` (the card could not hold the target,
  usually at the top of the range) is ordinary; `above` means something outside the sweep owned the
  curve.

**Does it contain personal or sensitive data?** No personal data about anyone other than the author.
File paths in session JSONs contain the author's Windows user name, and READMEs the author's first name and
GitHub handle. Board and device identifiers are model-level PCI IDs; there are no serial numbers or
GPU UUIDs.

## Collection process

- **Method.** `tools/frequency-sweep/Invoke-FrequencySweep.ps1` locks the core clock with
  `nvidia-smi -lgc`, waits 8 s to settle, then runs `gpu_workload.py` (or `llm_workload.py`) for a fixed
  number of iterations, constant across the sweep. Telemetry is normally sampled every 0.5 s (the
  exceptions are above) and power is averaged over the benchmark's timed region only. The tool resets
  clocks in a `finally` block on every exit path and reads the reset back.
- **Preflight.** The current tool checks idle GPU utilisation, video-engine activity (from schema
  0.3.0) and free VRAM, and records them in its JSON; older versions recorded less, as listed above. From 2026-10-03, registered sessions also screened every
  window for desktop rendering through HWiNFO.
- **Voltage.** HWiNFO logged core voltage and crossbar clock at 2.00 s (main PC, early) or 0.50 s;
  `tools/frequency-sweep/join_hwinfo_voltage.py` takes the median over each benchmark window.
- **Who and when.** The author, on the author's own machines, 2026-08-16 to 2026-10-09 for the 1088
  sweeps and 2026-10-12 to 2026-10-20 for the two v1.2.0 studies; many later
  sessions ran unattended while the author was at school.
- **Registered predictions.** Many sessions tested predictions registered before collection; their
  READMEs say which, and failed predictions are kept as recorded.
- **Ethical review.** No human participants are involved; the author judged that no ethical review
  was needed.

## Preprocessing

No measurement was cleaned, re-encoded or edited for release. Selection follows
`analysis/build_data_manifest.py`: only sweeps it classifies dataset-grade are distributed (25
excluded and 3 tool-verification runs are listed in `manifest/SOURCE-CENSUS.*` but not distributed).
The voltage extracts are the only derived per-sweep files.

## Uses

**Suitable for:** frequency/power/performance characterisation of these four cards; testing DVFS
or efficiency models against measured consumer data; studying how voltage/frequency curve edits
move the efficiency optimum on the RTX 5060 Ti; methodological work on measurement contamination.

**Not suitable for:** claims about a GPU model in general (N=1 per model); absolute power accuracy
(no shunt); stability or safety of any curve edit (sweeps are short and lock clocks, and no
configuration here is certified stable); comparing sweeps across sessions or configurations
without reading both READMEs and their flags.

## Distribution

On Zenodo, DOI [10.5281/zenodo.23547564](https://doi.org/10.5281/zenodo.23547564) for this version, [10.5281/zenodo.23251532](https://doi.org/10.5281/zenodo.23251532) for all versions. Measurements and their READMEs: CC BY 4.0 (`LICENSE-DATA`). Code: MIT
(`LICENSE`). Third-party datasets and proprietary tools are not redistributed. Afterburner profile
files are redistributed only as evidence for the two v1.2.0 studies: the stores each of their sessions
witnessed and the stock reference store, which are the author's own settings files.

## Maintenance

Maintained by the author (GitHub `imaoofu`). Corrections and additions will be released as new
Zenodo versions under the same concept DOI, with the change recorded; published versions are not
altered. v1.1.0 adds the 24 application-workload sweeps of session 21 and changes nothing in
v1.0.0. v1.2.0 adds the day-to-day repeatability study (§22: 40 sweeps on five days), the
counter-polling pilots (§20b: four sessions of 144 windows, sizing data that stopped at insufficient
precision with no verdict) and the kernel diagnostics, each counted separately from the 1088 sweeps,
with what is needed to re-score both studies; it changes no v1.1.0 measurement file or README. A raw-log supplement may follow in a later version after a privacy review.

## Use of AI tools

The measurements were taken on the hardware above. Much of the collection and analysis code, the
census and claim-auditing tools, and the documentation (including drafts of this datasheet) was
written by AI coding assistants (Anthropic's Claude via Claude Code; OpenAI's ChatGPT and Codex)
under the author's direction, and much of it was then checked by separate AI-run audits. The author
designed and ran the experiments, built and handled the hardware, made the curve edits, and decided
what to measure and release.
