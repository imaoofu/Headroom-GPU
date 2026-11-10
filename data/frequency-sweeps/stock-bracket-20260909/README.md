# `stock-bracket-20260909` — the first same-session stock-versus-tuned comparison in this project

**Three twelve-workload suites, 36 sweeps, 13 of 13 frequencies each, 10:38–13:39, zero failures.**
RTX 5060 Ti, driver 616.64, schema 0.3.3. Collected 2026-09-09.

**Dataset-grade.** Standard 1236–3090 MHz 13-point grid, iteration counts unchanged since r1.

| leg | tag | configuration | Afterburner | enforced PL | launched |
|---|---|---|---|---|---|
| 1 | `p4t1` | full tune, 3030 plateau | Profile 4 | 200 W | 10:38, **35 °C, no cooldown** |
| 2 | `r9` | **STOCK** | **Profile 3** | **180 W** | 11:43, 31 °C after 602 s |
| 3 | `p4t2` | full tune, 3030 plateau | Profile 4 | 200 W | 12:47, 31 °C after 602 s |

**Why this run exists.** Every stock-versus-tuned number in this repository until today was assembled
from sweeps taken on *different days*, because stock could not be applied from the command line —
all five Afterburner slots carried offsets. On 2026-09-09 Profile 3 was found to hold stock, so for
the first time both sides of the comparison could be measured in one session, with the stock leg
**centred between two tuned legs** so that linear session drift cancels on the tuned side.

`CLAUDE.md` records ~**1.47%** cross-session drift on one *unchanged* configuration against ~0.76%
within-session. Every earlier stock-versus-tuned gap carries an offset of that order. This one does
not.

---

## The result

| | mean efficiency gain |
|---|---|
| **stock (`r9`)** | **56.99%** |
| **full tune (mean of `p4t1`, `p4t2`)** | **34.16%** |
| **GAP** | **22.83 points** |

**Stock has more headroom in 12 of 12 workloads**, no exceptions. That is a stronger consistency than
the full-tune-versus-split comparison in `abba-20260908`, which was 7 of 12 and could not be
distinguished from a coin.

**Against the same gap assembled across sessions:** stock `r2`–`r6` (55.93) minus full tune `abba`
(34.32) = 21.61 points. The in-session figure is **1.2 points larger**. So the cross-session
construction was not badly wrong — worth saying plainly, because it means the older comparisons in
this repository are not invalidated, only less precise than they looked.

---

## The bracket's first job was to audit itself, and it retracts a claim from `abba-20260908`

| | drift, same configuration |
|---|---|
| `abba-20260908`, full tune `a1` → `a2`, ~2.5 h | **+0.04 points** |
| **this run, full tune `p4t1` → `p4t2`, ~2 h** | **−1.25 points** |

**`abba-20260908`'s README says "The full tune reproduces to 0.04 points."** That sentence was an
n=1 bracket. At n=2 the tuned configuration's session reproducibility is **±1.3 points**, and the
+0.04 was luck rather than precision.

**This is the failure this project keeps rediscovering** — an n=1 or n=2 methods finding that does
not survive a second sample. It has now happened to the "mean of top 3" metric fix (4× at n=2,
1.1× at n=8), to the `membw` configuration ranking, and now to a reproducibility figure. The
correction belongs in `abba-20260908/README.md`; the number here is the one to quote.

**What it costs this result, and what it does not.** The 22.83-point gap carries roughly ±1.3 points
of tuned-side measurement uncertainty. That is 5% of the effect. **The gap survives comfortably; the
precision claim does not.** Do not quote 22.83 to two decimals as though it were pinned — quote it as
**~23 points, ±1.3**.

**Leg 1 had no preceding cooldown** and launched at 35 °C where legs 2 and 3 launched at 31 °C
after identical 602-second settles. That asymmetry sits on `p4t1`, one half of the drift bracket, so
the −1.25 conflates session drift with a 4 °C starting difference and **cannot separate them**. The
same defect sat on `a1` in `abba-20260908`. It is now twice; the opening leg of a bracket should get
a cooldown like every other leg.

---

## Both registered predictions hit, and stock's is newly independent

The prediction is: **the efficiency optimum is the last frequency the V/F curve reaches at the
0.720 V load floor** (measured in `voltage-curve-20260908`).

| configuration | curve reaches 720 mV at | predicted | measured |
|---|---|---|---|
| **stock (`r9`)** | 1530 MHz | **1537** | **1537** (yes) |
| **full tune (`p4t1`)** | 2002 MHz | **2002** | **2002** (yes) |
| **full tune (`p4t2`)** | 2002 MHz | **2002** | **2002** (yes) |

**Stock's prediction is now derived rather than borrowed.** `abba-20260908` predicted stock's
optimum using a floor voltage measured on *other* data, and the stock curve itself had never been
decoded — no stock profile existed to decode. Profile 3 supplies it: 122 curve points, every
per-point offset zero, reaching **1530 MHz at 720 mV**. The prediction is now computed from the
factory curve and confirmed against a fresh measurement of it.

**The grid is ~155 MHz, so a prediction only needs to fall within ±78 MHz to select the right
point.** This is a genuine success and not a fine-grained one. See `abba-20260908` for the window
analysis; nothing here narrows it.

---

## The mechanism, in the power domain, same session, matched clock

Mean over all 12 workloads. Full tune is the mean of both its legs.

| target MHz | stock W | full tune W | tune saves | achieved stock / tune |
|---|---|---|---|---|
| 1237 | 56.38 | 58.14 | **−3.1%** | 1236 / 1236 |
| 1395 | 58.93 | 61.49 | **−4.3%** | 1393 / 1392 |
| 1545 | 62.63 | 63.25 | **−1.0%** | 1537 / 1540 |
| 1702 | 69.35 | 65.79 | +5.1% | 1695 / 1697 |
| 1852 | 78.03 | 67.37 | +13.7% | 1845 / 1846 |
| **2010** | 86.77 | 70.56 | **+18.7%** | 2002 / 2002 |
| 2167 | 90.96 | 79.21 | +12.9% | 2157 / 2160 |
| 2317 | 99.92 | 88.79 | +11.1% | 2310 / 2310 |
| 2475 | 113.47 | 100.81 | +11.2% | 2467 / 2467 |
| 2625 | 125.07 | 102.24 | +18.3% | 2589 / 2605 |
| 2782 | 132.41 | 112.80 | +14.8% | 2678 / 2763 |
| 2932 | 131.56 | 122.23 | +7.1% | **2677** / 2898 |
| 3090 | 132.24 | 123.08 | +6.9% | **2676** / 2957 |

**The saving is not a constant offset. It is a bump, and its shape is the prediction.**

- **Below ~1545 MHz the tune costs power** (−1.0% to −4.3%). Both configurations are on the 0.720 V
  floor there, so their voltages are equal and the undervolt has nothing to give. What remains is the
  tune's **+2500 memory overclock**, which draws power that stock does not pay. This is the cleanest
  isolation of the memory overclock's power cost in the repository.
- **The saving peaks at 2010 MHz, +18.7%** — precisely where the full tune's floor ends and stock's
  ended ~470 MHz earlier. Stock is climbing its voltage curve while the tune is still at 0.720 V.
- **Above that both are off the floor** and the gap narrows toward the top.

**The voltage half of this is inferred, not measured.** HWiNFO was not running — it cannot be
started remotely — so voltages come from the decoded curves plus the floor measured on 2026-09-08.
`voltage-curve-20260908` measured voltage directly; this run does not. **A repeat with HWiNFO joined
would make this the strongest table in the project.**

**Stock is boost-capped at the top three targets**, achieving 2676–2678 MHz for targets of 2782,
2932 and 3090, against the tune's 2957. That ceiling is why stock's headroom denominator is lower and
is part of why its measured headroom is larger.

---

## `r9` as a stock replicate — it is the highest of the series

| replicate | mean gain |
|---|---|
| r3 | 56.31% |
| r4 | 55.40% |
| r5 | 55.75% |
| r6 | 56.55% |
| r7 | 54.02% |
| r8 | 55.88% |
| **prior series** | **55.65%, sd 0.90, n=6** |
| **r9 (this run)** | **56.99%** |

r9 sits **+1.34 points above the prior mean, about 1.5 sd**, and is the highest value in the series.

**A candidate explanation, not a measurement:** r9 was collected with the operator at school and the
machine otherwise unused — the sweep preflight read a **0% idle baseline**, against the 3–4% typical
of r1–r8. §5.4.4 records that desktop contention depresses measured throughput most in the mid-band,
which is exactly where stock's optimum (1537 MHz) sits, so a quieter machine should *raise* stock's
measured headroom. That is consistent with r9 being high and is **not** evidence for it. Nothing here
tests it.

**n=6, not 8.** `r1` and `r2` are excluded because the r2 directory also contains bgemm64 sweeps
tagged `-r3` and `-r4` dated 2026-08-30 — an early, separate set of four bgemm64 runs whose tags were
later reused for the full replicates of 09-02 and 09-04. The collision is already known and handled;
`claims_consumer.py` pins explicit paths rather than globbing. It is noted here only so the n=6 is
not mistaken for missing data.

---

## What this run does NOT show

**The stock-minus-tune gap does not track arithmetic intensity at this n.** Spearman **ρ = −0.455,
t = −1.61 on 10 df, p ≈ 0.14** — not significant, with `conv` (288 FLOP/byte, +36.7 points) a large
outlier against the trend. The bottom-six/top-six split is +33.26 against +12.40, which looks like
structure, but the rank correlation does not support reporting it as one.

**This is a DIFFERENT quantity from `abba-20260908`'s ρ = +0.685 and the two must not be pooled.**
That result compared two *tuned* profiles with similar top clocks. This compares configurations whose
top achieved clocks differ by ~280 MHz, and the headroom metric divides by efficiency at each
configuration's own top clock. **A changed denominator is confounded with a changed mechanism**, so
this comparison is the weaker instrument for the intensity question and its null is not evidence
against the `abba` result.

**The headroom metric is internal to each configuration.** "Stock has 56.99% and the tune has 34.16%"
means stock leaves more on the table relative to *its own* ceiling — **not** that stock is more
efficient. It is not: the matched-clock power table above shows the tune drawing up to 18.7% less at
the same frequency. Do not read the gap as a performance ranking.

---

## Provenance

- **Profiles applied programmatically**, `MSIAfterburner.exe -profileN -q`, operator away from the
  machine for all three legs. Profile 5 was restored automatically at the end.
- **Profile 3 verified stock two ways.** On disk: 122 curve points with **every per-point offset
  zero**, memory +0, core +0, PL 100 = the card's 180 W factory default. In application, probed at
  11:38 before the run: power limit fell 200 → **180 W**, peak memory clock under load read **13801**
  not 16301, peak core clock **2640** against Profile 4's ~2976. Profile store sha256 `e5cbe0ec`.
- **Configuration confirmed from every leg's own data.** Across all 13 rows of all 36 sweeps,
  `memory_clock_min_mhz` takes only the values 810 (idle) and either 13801 (`r9`) or 16301
  (`p4t1`, `p4t2`) — **no leg contains a single row from the other configuration.**
- **Power limits are not a confound.** `r9` ran at 180 W enforced = 180 W default, which is exactly
  what r1–r8 used; the sweep tool only *reads* the power limit and never sets it, so 180 W came from
  Profile 3's PL 100 and 200 W from Profile 4's PL 111. Stock at 180 W is stock.
- **Lock behaviour.** All 36 sweeps reached 13 of 13 planned frequencies. Locks held at **every point
  from 1237 through 2475 MHz in all 36 sweeps**; every miss is at 2625 MHz or above and every one is
  `below`, i.e. the card's boost ceiling rather than a tooling fault. Stock misses hardest (−414 MHz
  mean at the 3090 target, 12 of 12 workloads) because its ceiling is ~2677. **Both optima, 1537 and
  2002, sit deep inside the perfectly-locked region.**
- **The 2026-09-08 `-f` precedence bug did not recur.** No `applied_settings` string in these 36
  files contains a literal `{0}`; the runner builds them by plain concatenation.
- Cooldowns before legs 2 and 3: 600 s floor, 42 °C target, 900 s ceiling. Both settled at 602 s,
  at 31 °C and 32 °C. Leg 1 had none — see the warning above.
- Preflight every sweep: encoder 0%, decoder 0%, ~15.6 GB free, **baseline utilisation 0%**.
  The NVIDIA **Instant Replay setting** could not be inspected remotely — only its encoder
  signature, which read 0%. §5.4.4 records that Instant Replay is invisible at idle, so a 0% encoder
  reading is suggestive and not proof.
- **NVML P0 graphics clock offset read back as 0 MHz** before and after applying each profile. No
  offset was ever written; the write path remains unexercised on this card.
- All 36 sweeps: driver **616.64**, schema **0.3.3**, one chip.
- **None of the Afterburner profiles has been stability tested.** The operator reports P4 and P5
  as game-stable, which is weak evidence and recorded as such. Profile 3 is stock, so the question
  does not arise for `r9`.
- **n=1 stock leg against n=2 tuned legs, one chip.** The tuned side has a drift bracket; the stock
  side does not, so stock's own session reproducibility in this run is **unmeasured**. A second stock
  leg is the cheapest thing that would strengthen this.
