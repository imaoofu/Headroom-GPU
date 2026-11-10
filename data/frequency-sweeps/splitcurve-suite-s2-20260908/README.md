# `splitcurve-suite-s2-20260908` — the tuned configuration gets its first error bar, and it is tiny

**Twelve sweeps, 13 of 13 frequencies each, 52 minutes, all complete.** RTX 5060 Ti on the
**split-region V/F curve with memory +2500**, enforced **200 W**, driver 616.64, schema 0.3.3.
Collected 2026-09-08.

**Dataset-grade.** Replicate of `splitcurve-suite-20260907` (`s1`). Same suite, same 1236–3090 MHz
grid, same iteration counts, same configuration.

---

## Why this replicate exists

`s1` was n=1. The **27.4% mean efficiency gain** it reported — the number the whole
undervolt-versus-frequency substitution argument rests on — carried no spread at all, while the
stock side had five replicates and therefore did. The paper was comparing a figure with an interval
against a figure without one, at the exact place a reader would push hardest.

---

## The result: it reproduces to 0.18 points

| | mean efficiency gain |
|---|---|
| `s1` (2026-09-07) | 27.45% |
| **`s2` (2026-09-08)** | **27.63%** |
| **difference** | **+0.18 points** |

**The tuned configuration is more reproducible than the stock one.** Between-run spread is 0.18
points here against a standard deviation of 0.48 across the five stock replicates r2–r6. That was
not the expected direction and no mechanism is offered for it; with n=2 it is an observation, not
a finding.

### The substitution gap, now with a spread on both sides

| | mean | sd | n |
|---|---|---|---|
| stock (r2–r6) | 55.93% | 0.48 | 5 |
| tuned (`s1`, `s2`) | 27.54% | 0.13 | 2 |
| **gap** | **28.39 points** | | |

This is the first time both sides of that comparison have carried a spread. The gap is roughly
sixty times the larger of the two standard deviations, so **the substitution result does not depend
on the measurement precision at all** — it was never at risk from this, and now that is shown
rather than asserted.

---

## The mean is stable; the individual workloads are NOT

| workload | `s1` | `s2` | delta |
|---|---|---|---|
| copy | 27.2 | 26.2 | −1.0 |
| reduce | 12.0 | 11.2 | −0.9 |
| softmax | 31.6 | 24.8 | **−6.7** |
| layernorm | 30.7 | 27.7 | −3.0 |
| bgemm32 | 40.6 | 35.8 | −4.8 |
| bgemm64 | 38.5 | 46.5 | **+7.9** |
| bgemm128 | 1.4 | 6.9 | +5.4 |
| bgemm256 | 16.3 | 15.2 | −1.1 |
| bgemm1024 | 33.9 | 39.7 | +5.8 |
| attention | 18.4 | 22.2 | +3.8 |
| conv | 47.4 | 39.4 | **−7.9** |
| gemm | 31.4 | 36.0 | +4.6 |
| **MEAN** | **27.45** | **27.63** | **+0.18** |

**Individual workloads move by up to 7.9 points while the mean moves by 0.18.** The excursions
are in both directions and they cancel. This is the single most useful thing in this directory:
**every per-workload figure quoted from `s1` alone is unreliable at the several-point level, even
though `s1`'s mean was excellent.** `bgemm128` at 1.4% versus 6.9% is a factor of five.

Any sentence in the paper of the form "on the tuned card, workload X gives Y%" needs both runs
behind it or an explicit n=1 warning. The mean does not inherit this problem.

The same caution applies to the optima: the median is **1537 MHz in both runs**, but **5 of 12
workloads land on a different grid point** between them (`copy`, `softmax`, `layernorm`, `bgemm128`
and `gemm`, all moving one step among 1388 / 1537 / 1695). The median is robust; the individual
optima are not.

---

## Configuration identification — what actually established it

**The decisive check is the locked-sweep peak achieved clock, same workload in both runs:**

| workload | `s1` | `s2` | delta |
|---|---|---|---|
| gemm | 2977.0 MHz | 2977.0 MHz | **+0.0** |
| bgemm1024 | 3015.0 MHz | 3015.0 MHz | **+0.0** |
| conv | 3015.0 MHz | 3015.0 MHz | **+0.0** |

Exact agreement on three workloads. `s2` ran the same curve as `s1`.

**THE CORE-CLOCK LINE IN THIS RUN'S `applied_settings` DOES NOT ESTABLISH THAT, AND SHOULD NOT
BE READ AS IF IT DOES.** The pre-launch probe reported "peak core 3022 MHz" beside this card's
signatures of stock ~2593 / full tune ~2947 / split ~2977. Those signatures are **`gemm`-derived**,
and the probe runs **`membw`** — under a memory-bound load the SMs draw less power and the card
boosts higher than it ever does under `gemm`, so the two are not comparable. 3022 is also within
this card's ~15 MHz clock granularity of Profile 2's decoded plateau (3022) as well as Profile 5's
(3030), so it could not have separated them either. **The identification rests on the memory clock,
on `-profile5` being what was requested, and above all on the table above** — not on that line.

**The offsets held on every row, not just at the ends.** Across all 156 rows of the twelve sweeps:

| `memory_clock_min` | rows |
|---|---|
| 810 MHz (idle floor) | 27 |
| 7001 MHz (intermediate P-state) | 4 |
| **16301 MHz (tuned)** | **125** |

**Zero rows at 13801**, and every row's `memory_clock_max` is ≥16301. The low minima are idle-state
dips inside the settle window, not stock silicon. A first pass at this flagged nine sweeps as
"stock rows present" by thresholding the per-sweep *average*; that was a badly chosen threshold and
not a finding.

---

## A difference from the stock replicates worth recording

**Nine of the twelve `s2` sweeps report `baseline_util_pct` of 0**, against 3.0–3.6% for every
sweep of r8. The operator was away from the machine and the display had almost certainly gone to
sleep, removing compositor load entirely. `s1` shows the same pattern in four of its twelve.

This matters because §5.4.4 established that desktop load depresses the mid band roughly four times
harder than the top, and the optimum lives in the mid band — so a quieter run would *inflate* the
measured gain, and the tuned suites are the quiet ones. That would make the 28.39-point gap an
underestimate rather than an overestimate.

**The data argues the effect is small here:** `s1` had four zero-baseline sweeps and `s2` had nine,
and their means agree to 0.18 points. That is not a controlled test, but it is the comparison
available, and it does not support a large baseline-driven bias.

---

## Provenance

- Collected 2026-09-08 10:07–10:59 by `tools/frequency-sweep/Invoke-SuiteReplicate.ps1`
  via a chained script that handled cooldown, profile application, verification and collection.
- **The curve was applied PROGRAMMATICALLY with the operator away from the machine** —
  `MSIAfterburner.exe -profile5 -q` — which is a first for this project. Every prior tuned run was
  set by hand with a person watching. This is recorded because it changes who verified what.
- **Profile 5 was decoded from disk before it was applied**, rather than trusted by slot number:
  MemClkBoost +2500, PowerLimit 111, and a V/F curve following the stock slope low down (1447 MHz
  at 700 mV, 2180 at 850) then pinning flat at 3030 MHz from ~925 mV up — the split-region shape,
  and consistent with the operator's own description of "925 mV at 3 GHz".
- Pre-launch probe: memory **16301** under load. The suite's own independent probe agreed, 16301
  against 16301 expected. Post-run probe: **16301** — no silent driver reset across the run, which
  is a guard `s1` did not have.
- Enforced power limit **200.00 W**, matching `s1` exactly (Profile 5 carries PL 111%). Note that
  `power_limit_w` reads 200.00 on the stock replicates too — that is the *settable* limit; the
  field that distinguishes them is `power_limit_enforced_w`, 180.00 at stock.
- Cooldown before launch: **30 minutes**, the ceiling rather than the 15-minute floor, because the
  card's idle floor today was 39 °C and the ≤38 °C condition never passed. Launched at 39 °C
  against `s1`'s 38 °C. The wait was gated on time by design — `temperature.gpu` is the die sensor
  and recovers in 2–3 minutes while the heatsink, VRM and memory do not, and `temperature.memory`
  reads N/A on this card, so no available sensor reports the slow thermal mass.
- All twelve reached 13 of 13 planned frequencies. Filenames carry `splitcurve` correctly, unlike
  eleven of `s1`'s, which say `stock` from the hardcoded-label bug fixed on 2026-09-07.
- Analysis: `suiteRowFigures()` from `analysis/claims_consumer.py`, the reader the paper uses.
