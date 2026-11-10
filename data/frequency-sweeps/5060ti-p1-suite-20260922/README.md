# Profile 1 suite — worklist item 4k, 2026-09-22

**Twelve workloads × 13 frequencies (1237–3090 MHz), Afterburner Profile 1, driver 616.92.**
Collected **unattended**, operator absent, by `tools/hwinfo-logging/Invoke-LoggedSweep.ps1`.

This collects `docs/REGISTERED-PREDICTIONS.md` §2, **registered 2026-09-11 and never swept until
today**.

---

## THE REGISTERED PREDICTION HOLDS

> **Registered 2026-09-11:** *"P1's median optimum is 2010 MHz — the same grid point as P4 —
> because their floor extents are 1972 and 2002 MHz, 30 MHz apart against a ~150 MHz grid, and the
> mechanism claims the optimum is set by the floor extent alone."*
> **Refuted by:** a median optimum on any grid point other than 2010.

**Measured median: 2010 MHz. Seven of twelve workloads land individually on it.**

| workload | optimum target | achieved |
|---|---|---|
| attention, bgemm1024, bgemm128, bgemm256, bgemm64, conv, copy | **2010** | 2002 |
| layernorm, softmax | 2167 | 2160 |
| reduce | 2475 | 2467 |
| gemm | 1852 | 1845 |
| bgemm32 | 1545 | 1537 |

**Why this is worth more than one more confirmation.** The manipulation moved the floor and the
optimum followed; the negative control moved the curve *above* the floor and it did not.
**P1 holds the floor region fixed and changes POWER LIMIT (180 W vs P4's 200 W) and MEMORY
(+2000 vs +2500).** Those are the two variables neither existing arm touches, and the optimum did
not move.

**Two variables at once, so a movement would not have said which caused it** — but the
prediction is refuted *by movement*, whatever its cause, because the mechanism claims the floor
extent is sufficient. It did not move. **The asymmetry is what makes a two-variable test
admissible here**, and it should be stated that way rather than as a clean single-variable control.

**Still one chip, one profile pair.** Twelve workloads are repeated outcomes on it, not twelve
chips.

---

## How we know this is P1 and not stock silicon wearing a P1 label

CLAUDE.md records the failure mode directly: *"A driver reset silently clears Afterburner offsets.
If one happens mid-suite, that suite is stock silicon wearing a tuned settings string."* That has
already cost this project a run.

**P1 carries memory +2000 where stock carries +0, so the memory clock is an independent
witness** — one that does not depend on the settings string being honest:

| checkpoint | memory clock under load |
|---|---|
| before applying P1 | **13801 MHz** (stock) |
| after applying P1 | **15801 MHz** — exactly +2000 |
| after reverting to P3 | **13801 MHz** (stock), 180 W |

The runner refused to sweep at all unless the post-apply reading cleared stock by >200 MHz, and
reverted inside a `finally`.

**`memory_clock_avg_mhz` is NOT the column to check, and it looks alarming if you do.** Its
minimum reads **810 MHz** in nine of twelve workloads — that is the *idle* memory state sampled
between benchmark iterations, not a lapsed profile. Per-point averages therefore run 14730–15801
depending on how much idle the window caught. **The maximum is the honest witness**: 15801–16001
throughout, so the +2000 offset was live at every point. *(16001 is a higher memory P-state plus
the same +2000, not an anomaly.)*

---

## Provenance

- **Iterations matched to `suite-replicate-r10-20260918`** per workload, so this suite is directly
  comparable to the stock suite rather than merely similar.
- HWiNFO at `SensorInterval=500`, one log per sweep.
- **Operator absent; the driving agent was silent during every run.** See
  `../5060ti-finefloor-20260922/README.md` for why that matters — agent activity was measured that
  same morning to remove 8–11% from *isolated* points, and this suite was run under the protocol
  that finding produced.
- Profile store snapshotted with SHA-256 before anything was applied.
- **Nothing was edited.** P1 was applied and reverted; no curve was modified.
