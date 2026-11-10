# `abba-20260908` — the optimum tracks the V/F curve, and the tune's benefit tracks arithmetic intensity

**Four twelve-workload suites, 48 sweeps, 13 of 13 frequencies each, 190 minutes, zero failures.**
RTX 5060 Ti, driver 616.64, enforced 200 W, schema 0.3.3. Collected 2026-09-08.

**Dataset-grade.** Standard 1236–3090 MHz 13-point grid, iteration counts unchanged since r1.

| leg | tag | configuration | Afterburner |
|---|---|---|---|
| 1 | `a1` | full tune | Profile 4 |
| 2 | `b1` | split curve | Profile 5 |
| 3 | `b2` | split curve | Profile 5 |
| 4 | `a2` | full tune | Profile 4 |

**Profile 4 WAS EDITED LATER THE SAME DAY, after this run.** `a1` and `a2` measured it with a
**3015 MHz plateau**; the operator then raised the plateau to 3030 to match Profile 5, changing 49 of
127 curve points at 940 mV and above and leaving the low-voltage region identical. Any future run
labelled "Profile 4" is therefore a *different configuration* from these two legs. Both versions are
snapshotted in `data/afterburner-profiles/`, distinguished by date and by sha256 of the cfg.

**ABBA, not ABAB.** A sits at positions 1 and 4, B at 2 and 3, so both configurations are centred
on the same instant in the session and linear drift cancels exactly. Every other cross-configuration
comparison in this repository is day-1 versus day-2, carrying the ~1.47% cross-session drift
`CLAUDE.md` records for a single *unchanged* configuration. This design removes it, and measures it.

---

## Result 1: the efficiency optimum tracks the applied V/F curve, quantitatively

The two profiles are a **constant +465 MHz apart** in the low-voltage region of their decoded curves
(1912 vs 1447 MHz at 700 mV; 2317 vs 1852 at 800 mV — the same offset at both).

**The measured optimum shifted by +465 MHz, in 12 of 12 workloads.**

| | median optimum |
|---|---|
| full tune (P4) | **2002 MHz** |
| split curve (P5) | **1537 MHz** |
| shift | **+465 MHz** |

Predicting each optimum from its curve alone — the frequency the curve reaches at the **stock
voltage floor of 0.720 V**, a figure measured independently in §5.5.7 on different data:

| | predicted | measured |
|---|---|---|
| full tune | **2002 MHz** | **2002 MHz** |
| split curve | **1530 MHz** | **1537 MHz** |
| stock | 1552 MHz | 1537 MHz |

**How much of that is luck.** The optimum can only land on a grid point and the grid is ~155 MHz,
so a prediction needs to fall within ±78 MHz to select the right one. The floor voltage that works
for both is a window of roughly **715–740 mV**: at 700 mV both predictions pick the wrong point, at
750 mV both pick the wrong point. The independently-measured stock floor falls inside that window.
That is a genuine success and **not** a unique determination — say "the stock-measured floor lies in
the window that predicts both", never "720 mV is derived".

**No voltage telemetry in these runs.** HWiNFO was not logging, so this relates a *decoded
intended* curve to a *measured* optimum. The voltage itself is inferred from the profile store, not
observed. A repeat with HWiNFO joined by timestamp would close that gap and is the obvious next step.

**Why this matters.** §5.5.7 previously observed that the optimum *coincides with* the voltage knee
on two chips. That is correlational. This is a **manipulation**: change the curve, and the optimum
moves with it, by the amount the curve moved, on every workload. It was not planned — these are two
profiles the operator built by hand months ago, and the experiment fell out of comparing them.

---

## Result 2: the dose-response prediction FAILED, and what replaced it is better

**The prediction.** Frequency reduction and undervolting are claimed to be substitutes drawing on
one pool of headroom. Profile 4 is the measurably deeper undervolt — 11.4% less power than Profile 5
across 1237–2010 MHz at matched achieved clock, 26.9% less at 2010 MHz. So it should leave **less**
headroom than the split curve's 27.5%.

**The observation.** It leaves **more**.

| | mean efficiency gain |
|---|---|
| full tune (deeper undervolt) | **34.32%** |
| split curve | **28.27%** |
| difference | **+6.05 points** |

**DO NOT REPORT THE +6.05 AS A UNIFORM EFFECT. It is not.** Per workload the sign is mixed —
positive in 7 of 12, which a sign test cannot distinguish from noise (p ≈ 0.39). The mean is carried
by a subset.

### What the subset is: arithmetic intensity

| | mean (full tune − split) |
|---|---|
| bottom six by intensity (`copy`…`bgemm64`) | **−1.00** |
| top six by intensity (`bgemm128`…`gemm`) | **+13.11** |

**Spearman rank correlation with arithmetic intensity: ρ = +0.685, t = 2.98 on 10 df, p < 0.05.**

**This is the mechanism this repository already documented, seen across the whole suite for the
first time.** §5.7 found that the full tune's pinned-low voltage goes with a starved crossbar and
harms bandwidth-bound work while being pure benefit to compute-bound work (an association with a
predicted repair, not the crossbar isolated as the cause; this said "established that… starves the
crossbar" until 2026-09-24, see §5.7.3) — measured on **two**
workloads, `gemm` at 1365 FLOP/byte and `membw` at 0.167. Here it is twelve workloads spanning
0 to 1365 FLOP/byte, ordered, with the advantage growing along the axis.

So the substitution framing is the wrong frame for this comparison. The two curves are not "more"
and "less" undervolt on one axis; they trade compute-bound efficiency against bandwidth-bound
efficiency, and which is better depends on the workload.

---

## The bracket: a drift measurement no other comparison here has

Same configuration, same session, ~2.5 hours apart:

| | drift |
|---|---|
| full tune `a1` → `a2` | **+0.04 points** |
| split `b1` → `b2` | **−1.85 points** |

**"The full tune reproduces to 0.04 points" is RETRACTED, 2026-09-09.** A second bracket on the
same configuration — `stock-bracket-20260909`, legs `p4t1` and `p4t2`, ~2 h apart — drifted
**−1.25 points**. At n=2 brackets the full tune's session reproducibility is **±1.3 points**, and the
+0.04 below was luck, not precision. **Quote ±1.3, not 0.04.**

This is the project's recurring failure arriving again: an n=1 methods finding that did not survive a
second sample, exactly like the "mean of top 3" metric fix in the retraction further down this file.
Note the asymmetry it creates with the sentence that follows — **the split curve's −1.85 is no
longer distinguishable from the full tune's own spread**, so the contrast drawn below between a
reproducible configuration and an unreproducible one is not supported. What survives is the
*explanation* offered for it, which was measured independently: the split legs' top point drew 179.7
against 169.3 W at essentially identical clocks, and a metric dividing by efficiency at the top clock
inherits that. A tuned card near its ceiling is noisy to measure. Which of the two tuned
configurations is noisier is not established.

**The original text, kept because the reasoning that followed it still stands:** *The full tune
reproduces to 0.04 points. The split curve does not, and the reason is measurable.*
At the top of the grid, at essentially identical achieved clocks (2977.0 vs 2978.8 MHz), the two
split legs drew **179.7 W and 169.3 W — 10.4 W apart, 6.1%**. The efficiency gain divides by
efficiency at that point, so a 6% power swing there moves the ratio by exactly the observed amount.

The full tune tops out at ~2964 MHz drawing far less power at matched clock, so it sits further from
its power and voltage ceiling and its top point is correspondingly stable. **The configuration
closer to its ceiling is the noisier one to measure**, which means tuned configurations need more
replicates than stock does, not fewer.

**`a1` is the one leg with no preceding cooldown.** It began at 39 °C where `b1`, `b2` and `a2`
all began at 33 °C after an identical 601-second settle. The thermal-versus-drift diagnostic is
inconclusive and does not need to be conclusive — `a1` and `a2` agree to 0.04 points, so there is
nothing to attribute.

---

## A retraction, recorded because the reasoning looked good

Mid-run it appeared that the headroom metric's denominator — efficiency at the *highest achieved
clock* — was the dominant noise source, and that averaging the top three points fixed it: on the
`b1`/`b2` pair that cut the spread from 1.85 to 0.47 points, **4× tighter**, while making the
full-tune-versus-split difference larger.

**Validated against the eight stock replicates, the improvement is 1.1×, not 4×** (sd 0.77 → 0.68).
The effect was specific to that one tuned pair. **The metric was not changed and the standard
definition is retained.** An n=2 methods finding did not survive n=8 — the failure this project
documents repeatedly, arrived at again.

What survives is narrower and still worth having: **near a tuned card's ceiling the top-of-grid
point is unstable in power at fixed clock**, and any metric dividing by it inherits that. It is not
a general property of the metric; stock's top point is stable, which is why the eight-replicate
validation barely moved.

---

## Provenance

- **Curve applied programmatically**, `MSIAfterburner.exe -profileN -q`, operator away for legs 1–3.
- **Every leg's configuration verified from its own sweep data**, not only from the pre-run probe.
  Power at a locked 2010 MHz: `a1` 79.1 W, `b1` 109.3 W, `b2` 107.7 W, `a2` 73.4 W against
  references of 79.5 (full tune) and 108.8 (split). Top achieved clocks 2964 / 2977 / 2979 match the
  same assignment.
- **The pre-run power fingerprint cannot distinguish stock from the split curve** — 104.0 W vs
  108.8 W at 2010 MHz, inside run-to-run variation. It separates the *full-tune family* only. The
  memory-clock check (13801 vs 16301) covers the stock-versus-tuned pair. **Neither check is
  sufficient alone.**
- **Offsets held on every row**: across all 624 rows, `memory_clock_min` is 810 (idle), 7001
  (intermediate P-state) or 16301 (tuned); **zero rows at stock 13801**, and every row's
  `memory_clock_max` is ≥16301.
- Cooldowns before legs 2–4: 10-minute floor, 42 °C target, 15-minute ceiling. All three settled
  identically at **33 °C after 601 s**. Gated on time because `temperature.gpu` is the die sensor and
  recovers in 2–3 minutes while the heatsink, VRM and memory do not, and `temperature.memory` reads
  N/A on this card.
- **`applied_settings` contains a literal `{0}` where the launch temperature should be.** In
  PowerShell `-f` binds tighter than `+`, so a format string spanning a concatenation formats only
  its last literal. Every other substitution in that string is correct. The temperatures are
  recoverable from the run console log and from `temperature_avg_c` in each CSV.
- A display-driver crash watcher ran throughout. **Zero Event 4101 (TDR) all day.** One `nvlddmkm`
  Event 153 at 11:49:54 is attributable to the operator's own kill of a running CUDA process during
  a restart, not to instability.
- **None of the Afterburner profiles has been stability tested.** The operator reports P4 and P5
  as game-stable, which is weak evidence and recorded as such. Curves are snapshotted verbatim in
  `data/afterburner-profiles/`.
