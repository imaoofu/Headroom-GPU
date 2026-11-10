# `splitcurve-suite-20260907` — the suite on a tuned card: undervolting and frequency reduction are substitutes

**Twelve sweeps, 13 of 13 frequencies each, 49 minutes plus a top-up.** RTX 5060 Ti on the
**split-region V/F curve with memory +2500**, driver 616.64, schema 0.3.3, 2026-09-07.

**Dataset-grade.** Same suite, same 1236–3090 MHz grid, same iteration counts as every stock
replicate. **The first time the twelve-workload suite has been run on any tuned configuration** —
every prior tuned sweep in this project is `gemm` or `membw`, two points on the arithmetic-intensity
axis, and `softmax`, `layernorm`, `bgemm32`, `bgemm256` and `attention` had never been swept tuned.

---

## The result: the two levers overlap almost entirely

| | mean efficiency gain, optimum vs highest achieved clock |
|---|---|
| stock (r2–r6 mean) | **55.9%** |
| **split curve** | **27.4%** |

**The gap narrows by 28.5 points.** That is not a contradiction of §5.1 — it is what the thesis
predicts. Headroom exists because the stock configuration is inefficient at high clock, and a curve
that fixes some of that has already taken part of what was recoverable.

**AN EARLIER VERSION OF THIS SECTION SAID TUNING "CAPTURES ABOUT HALF THE HEADROOM". THAT READS
AS ADDITIVE AND IT IS WRONG.** The two numbers are ratios against *different* baselines — each
configuration's own top clock — so they cannot be subtracted. Put all three against ONE common
baseline, the stock card at its top clock:

| what you do | gain over stock at its top clock |
|---|---|
| drop frequency only, no tune | **+55.9%** |
| tune only, stay at top clock | **+26.4%** |
| **both** | **+60.9%** |

**55.9 + 26.4 = 82.3, but together they deliver 60.9.** **Frequency reduction and undervolting
are substitutes, not complements.** They are two routes to the same thing — running the chip at
lower voltage for the work being done. One moves *down* the stock V/F curve; the other moves the
curve *down*. You cannot collect both.

Three consequences, and the third is the useful one:

1. **Frequency reduction alone reaches ~92% of everything achievable** (55.9 of 60.9). Tuning alone
   reaches 43%.
2. **Tuning on top of frequency reduction adds about 5 points** (55.9 → 60.9) — a small return for
   hand-drawing a curve, accepting stability exposure, and having it silently cleared by any driver
   reset.
3. **If you do one thing, lock the clock.** It is scriptable through `nvidia-smi -lgc`, needs no
   per-chip hand-tuning, survives driver updates, and carries none of the stability risk. That is a
   stronger and better-supported recommendation than "undervolt your GPU".

**This also connects the measurement to the guardband literature quantitatively.** Leng et al. [8]
report a ~20% voltage guardband and up to 25% energy savings; a hand-drawn curve here captures
**+26.4%**, in that range, and frequency reduction is shown reaching the same underlying
inefficiency by a different route. It suggests the headroom is substantially guardband — which would
also explain why 952 MHz was optimal for 24 of 33 V100 workloads in §5.1: voltage margin does not
vary much by workload.

**This bounds who the 55.9% figure is for.** It is the gap for a user running stock. A user who
already undervolts has roughly half as much left. Any framing of the headline number should say
which population it describes.

**It is not an artifact of the reference point moving.** The split curve reaches ~2977 MHz against
stock's ~2593, so its reference sits at a *higher* clock — which should make the measured headroom
*larger*, not smaller. It shrank anyway, because the tuned card's efficiency at its own top clock is
so much better than stock's at stock's.

## Efficiency at matched commanded frequency

The fair comparison, 13 shared targets per workload, against the r2–r6 stock mean:

| workload | Δ efficiency | | workload | Δ efficiency |
|---|---|---|---|---|
| `attention` | **+26.0%** | | `bgemm256` | +13.3% |
| `bgemm1024` | +19.2% | | `layernorm` | +13.0% |
| `conv` | +17.1% | | `bgemm128` | +9.5% |
| `copy` | +15.6% | | `reduce` | +9.4% |
| `bgemm64` | +14.2% | | `gemm` | **+7.6%** |
| `softmax` | +14.0% | | | |
| `bgemm32` | +13.9% | | **mean** | **+14.4%** |

**Every workload gains, and the spread is 7.6% to 26.0%.**

**There is no benefit/harm crossover on this configuration.** The question this run was designed
to answer — where along the arithmetic-intensity axis the tune stops helping — has the answer
"nowhere, on the split curve." That is the split curve's whole point: §5.7 documents the *original*
tune costing up to 22.9% on bandwidth-bound `membw` at 1560–1867 MHz (a 29.6% gap to memory-only; "29.6%" here until 2026-09-24), and the split design was
derived to remove exactly that. Twelve workloads say it did.

**Do not read this as the split curve dominating everywhere.** §5.7.5 records that the original
tune still beats it on `gemm` *efficiency* from 1545–2625 MHz by up to 30.5%. This run does not
include the original tune and cannot speak to that trade.

## Throughput and power

Peak throughput **+17.7%** mean (range +12.1% `conv` to +23.5% `bgemm256`), band-mean throughput
**+10.5%**, band-mean power **−4.9%**.

**The peak figure is mostly overclocking, not efficiency.** The split curve reaches ~2977 MHz
where stock reaches ~2593, so a higher peak is expected and is not a headroom result. The
matched-frequency efficiency table above is the one that isolates the tune's effect.

## Provenance, and a labelling defect this run exposed

**Configuration identified by clock signature, not assumed**: peak core 2977 MHz, peak memory
16301 MHz under load before launch. This card's signatures are stock ~2593, memory-only ~2584,
rebuilt repair ~2906, full tuned ~2947, **split ~2977**. n=1 signature match.

### THE CURVE, READ OFF THE EDITOR AFTERWARDS — and it is not what the run declared

The operator supplied a screenshot of the Afterburner V/F editor after collection. The applied curve
has **four** regions, not two:

| region | behaviour |
|---|---|
| 700 → ~845 mV | smooth stock-like slope, ~1430 → ~1980 MHz |
| **~845–850 mV** | **near-vertical step, ~1980 → ~2750 MHz — roughly 770 MHz across about 5 mV** |
| ~850 → 925 mV | shallower slope, ~2750 → ~3020 MHz |
| 925 mV and above | **flat at ~3020 MHz** through to 1250 mV |

`applied_settings` in every JSON from this run describes it as *"stock voltage slope restored below
~925 mV, flattened region above it left intact"*. **The flat top from 925 mV is correct. The rest is
not.** There is no simple stock slope below 925 mV — there is a ~770 MHz discontinuity at ~848 mV
that the declaration omits entirely, and a distinct third region between the step and the flat.

**The JSONs are deliberately NOT edited.** `applied_settings` records what was declared at run time,
and rewriting it later would destroy the only honest record of what the operator believed while
collecting. The correction lives here instead, and anything reading those files should read this
section with them.

**What this costs.** The signature match to "split ~2977" stands as a clock measurement, but
"this is the split curve" is now a weaker claim than it looked: the previously-recorded split design
is described in `CLAUDE.md` as a two-region curve, and this is a four-region one that happens to
share its flat top. **Whether it is the same curve as the 2026-08-23 split runs is unresolved**, and
no claim in this file should be read as asserting they are identical.

**The step is a hazard worth naming.** A ~770 MHz jump across ~5 mV means any small voltage
excursion near 848 mV moves the requested clock enormously. Nothing in this run misbehaved — zero
crash events across 49 minutes — but that region is not a place to assume stability from one clean
session, and the 875 mV crash of 2026-08-30 sits close to it.

*Figures read off a screenshot by eye; treat every voltage as ±5 mV and every frequency as ±20 MHz.*

**A read-only watcher ran for the whole session** (`run-watcher.csv`), polling the Windows System
log for Event 4101 / `nvlddmkm` and checking the memory clock under load every 20 s. Result: **zero
driver-crash events and zero offset clears**, with the last loaded sample at 16301 MHz — so the tune
is demonstrably still applied at the *end*, not merely at the start. That matters because a driver
reset silently clears Afterburner offsets (2026-08-30), and any sweep after such an event would be
stock silicon under a tuned label.

**`copy` was refused during the main run** at a transient 10.8% baseline and re-run alone in the
same session, per the tool's own instruction. Same configuration untouched, baseline re-verified at
4%. Kept in-session deliberately: cross-session `gemm` drift on this card runs ~1.47%.

**EVERY FILE FROM THIS RUN WAS ORIGINALLY NAMED `5060ti-stock-suite-*`.**
`Invoke-SuiteReplicate.ps1` hardcoded "stock" into the session label, which was true when written —
every suite run was stock — and became a lie the first time the script was pointed at a tuned card.
The `applied_settings` inside each file was correct and loud, but a filename is what a person skims.
Files renamed and `samples_file` updated with them; the script now takes `-ConfigurationLabel`,
defaulting to "stock" so r1–r8 naming is unchanged.

## Limits

**n = 1** on the split curve, against n = 5 stock. Single session. The comparison to stock uses the
r2–r6 mean, which spans four sessions, so between-session variance is in the baseline but not in
this run. A second split-curve suite would be needed before any per-workload ordering here is
treated as real.

## Related

`../suite-replicate-r2-20260830/` … `../suite-replicate-r6-20260905/` (the stock baseline),
`../splitcurve-clean-20260824/` (the `membw` fine-grid runs that established the design),
`../membw-anomaly-20260819/` (the mechanism the split curve repairs).
