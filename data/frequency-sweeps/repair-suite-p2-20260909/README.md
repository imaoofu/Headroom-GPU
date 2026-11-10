# `repair-suite-p2-20260909` — the negative control: change the curve *above* the floor and the optimum does not move

**One twelve-workload suite, 12 sweeps, 13 of 13 frequencies each, 19:39–20:34.** RTX 5060 Ti,
driver 616.64, enforced 200 W, schema 0.3.3. Collected 2026-09-09.

**Dataset-grade.** Standard 1236–3090 MHz 13-point grid, iteration counts unchanged since r1.

| tag | configuration | Afterburner | PL |
|---|---|---|---|
| `p2t1` | **the repaired / curve-fixed shape** | **Profile 2** | 111% (200 W) |

**Profile 2 was the only one of the five never swept.** It is the geometry §5.7 calls the repair:
stock voltage slope restored across the whole lower range, with a low mid-band.

---

## Why this run exists: it is a designed negative control

`abba-20260908` changed the **floor region** of the V/F curve and the efficiency optimum moved
**+465 MHz in 12 of 12 workloads**. That is a manipulation, but a one-sided one — it shows the
optimum responds to *something*, not that it responds to the floor *specifically*.

This is the other side. P2 and P5 are **identical below 800 mV** and differ enormously above it:

| | 700 mV | 720 mV | 800 mV | 875 mV | 925 mV | plateau |
|---|---|---|---|---|---|---|
| **P2** | 1447 | **1530** | 1852 | **2280** | **2455** | 3022 |
| **P5** | 1447 | **1530** | 1852 | **2850** | **3030** | 3030 |
| difference | 0 | **0** | 0 | **570** | **575** | 8 |

The mechanism says the optimum is the last frequency on the **0.720 V load floor**, which both
reach at ~1530 MHz. So a 570 MHz change to the mid-band should move the optimum by **nothing**.

**The prediction was registered in `applied_settings` before the run.**

### Result: it did not move

| | measured median optimum |
|---|---|
| **predicted** | **1537 MHz** |
| **measured** | **1537 MHz** (yes) |

**9 of 12 workloads land on 1537 MHz individually** — the tightest concentration of any
configuration in this repository. The other three are `layernorm` and `gemm` at 1695 and `reduce`
at 2160.

### The four configurations together

| configuration | curve reaches 720 mV at | median optimum | mean gain |
|---|---|---|---|
| stock (`r9`) | 1530 | **1537** | 56.99% |
| split P5 (`b1`) | 1530 | **1537** | 29.20% |
| split P5 (`s2`) | 1530 | **1537** | 27.63% |
| **repair P2 (`p2t1`)** | **1530** | **1537** | **31.15%** |
| full tune P4 (`p4t1`) | 2002 | **2002** | 34.79% |
| full tune P4 (`p4t2`) | 2002 | **2002** | 33.54% |

**Four configurations, two distinct floor extents, and the optimum tracks the extent — not the
plateau, not the mid-band, not the mean efficiency gain.** P2 and P4 have plateaus 8 MHz apart and
optima 465 MHz apart. P2 and P5 differ by 570 MHz in the mid-band and have identical optima.

**The grid is ~155 MHz wide, so a prediction only needs to fall within ±78 MHz to select the
right point.** This is a real success and a coarse one. Nothing here narrows that window.

**A negative control cannot confirm a mechanism on its own.** It rules out "the optimum follows
the plateau" and "the optimum follows the mid-band". It is the *pair* — `abba-20260908` moving the
floor and this run not moving it — that carries the argument.

---

## Identity: confirmed post hoc, because it could not be confirmed in advance

**The pre-run checks cannot separate P2 from P5.** Their curves are identical below 800 mV, so
the power fingerprint at 2010 MHz — the method `docs/AFTERBURNER-PROFILES.md` prescribes — is blind
here. The memory-clock check rules out stock and nothing more. **This was written into
`applied_settings` before the run rather than discovered afterwards.**

The decoded curves put P2 near 928 mV at 2475 MHz against P5 near 862 mV, so P2 must draw
**more** power at matched clock in the mid band and the **same** power low down. Mean over 12
workloads, against `abba-20260908`'s two split legs:

| target | P2 (`p2t1`) | P5 (`b1`) | P5 (`b2`) | P2 vs P5 |
|---|---|---|---|---|
| 1545 | 65.36 | 65.04 | 65.11 | **+0.4%** |
| 2010 | 94.43 | 91.96 | 91.98 | +2.7% |
| 2317 | 107.16 | 97.07 | 96.88 | +10.5% |
| **2475** | 117.19 | 101.40 | 101.57 | **+15.5%** |
| 2625 | 120.08 | 103.60 | 103.05 | +16.2% |
| 2782 | 121.35 | 107.38 | 108.34 | +12.5% |

**The two configurations agree to 0.4% exactly where their curves are identical and diverge exactly
where the curves separate.** That is the same argument shape §5.7 used for the crossbar result —
two configurations agreeing where their voltages agree — and it identifies the profile
unambiguously.

**Top achieved clock, mean over 12 workloads:** P2 **2888.5 MHz** against P5's 2973.2 / 2971.7.
P2 sits ~84 MHz lower despite a plateau only 8 MHz lower, because it needs **940 mV** to reach that
plateau where P5 needs **925 mV**. Consistent with the curves; not a separate finding.

---

## `copy` was refused on the first attempt and re-run — read this before using it

The preflight measured the GPU **22.6% busy** before the first sweep started and refused, naming
`msedgewebview2` and `SpotifyXboxGamebarWebView`. **The guard worked: nothing contaminated was
collected**, and the run continued through the other eleven workloads, which read 0–1.6% baseline.

`copy` was then re-run at **20:29, two minutes after the last of the other eleven finished**, under
the same applied profile, re-verified quiet at 4.1% mean over ten samples with only desktop
processes resident. **It is in-session with its replicate, not a cross-session substitute** — but it
is the one sweep here whose timing differs, and that is recorded in its own `applied_settings`.

**This is the guard from §5.4.4 paying for itself in the ordinary case.** The 22.6% reading came
from background webviews the operator was not using, appearing in the ninety seconds between
applying a profile and starting a run. A sweep collected then would have looked completely normal.

---

## What this run does NOT show

**No voltage telemetry.** HWiNFO was not running and cannot be started remotely, so every voltage
in this file is **read off the decoded curve, not measured**. `voltage-curve-20260908` measured the
0.720 V floor directly on two other configurations; this run assumes it transfers to P2. The
identity check above is evidence that the *curve* is being applied as decoded, which is weaker than
observing the voltage.

**The mean efficiency gain is not the point and should not be ranked.** P2's 31.15% sits between the
split curve's 27.63–29.20% and the full tune's 33.54–34.79%, but this is n=1 for P2 against a tuned
side whose own session reproducibility was measured today at **±1.3 points**
(`stock-bracket-20260909`). **No ordering among the three tuned configurations is supported by this
run.**

**n=1 suite, one chip, one session.** The optimum's *location* is robust to the cross-session drift
that afflicts efficiency percentages — it is a grid point, not a continuous quantity — which is why
a single suite is enough for the prediction test and not enough for anything else here.

---

## Provenance

- **Profile applied programmatically**, `MSIAfterburner.exe -profile2 -q`, operator away from the
  machine. Profile 4 restored automatically at the end.
- **Configuration confirmed from the run's own data** — see the identity section. Across all 156
  rows `memory_clock_min_mhz` takes only 810 (idle), 7001 (intermediate P-state) and 16301 (the
  +2500 offset); **zero rows at stock's 13801**.
- Profile store sha256 `e5cbe0ec`. Decoded curve: 1447 MHz at 700 mV, 1530 at 720, 1852 at 800,
  2280 at 875, 2455 at 925, plateau 3022, knee 940 mV. **Only 12 of 125 curve points carry a
  non-zero offset** — P2's low end is literally stock, offsets zero.
- **NVML P0 graphics clock offset read back as 0 MHz and was never written.**
- All 12 sweeps reached 13 of 13 planned frequencies. Launch temperature 35 °C, card settled idle;
  no cooldown, as the preceding load was hours earlier.
- Preflight every sweep: encoder 0%, decoder 0%, baseline 0–1.6% for eleven of twelve and 4.2% for
  the re-run `copy`.
- The 2026-09-08 `-f` precedence bug did not recur: no `applied_settings` string here contains a
  literal `{0}`.
- **Profile 2 has never been stability tested.** The operator reports P4 and P5 as game-stable
  and says nothing about P2. It is the gentlest curve of the five — the most voltage per clock in
  the low and mid band — so it sits further from an undervolt edge than the profiles that are used
  daily, but that is an argument, not a test.
