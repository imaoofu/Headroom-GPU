# Profile 4 suite — same-session comparator for 4k, 2026-09-22

**Twelve workloads × 13 frequencies (1237–3090 MHz), Afterburner Profile 4 (full tune),
driver 616.92.** Collected unattended, operator absent, **hours after the P1 suite in
`../5060ti-p1-suite-20260922/` and under an identical protocol.**

## Why it was run

`REGISTERED-PREDICTIONS.md` §2 predicts *"P1's median optimum is 2010 MHz — **the same grid point
as P4**"*. 4k confirmed P1's half of that against **P4 numbers collected weeks earlier**, across a
session boundary this project measures at **~1.47% drift** on one unchanged configuration.

This makes the contrast same-session, same-driver, same-agent-protocol. The prediction stops
resting on an archive number.

## The result

| | P1 | P4 |
|---|---|---|
| **median optimum** | **2010 MHz** | **2010 MHz** |
| workloads on 2010 individually | 7 of 12 | 6 of 12 |

**Both medians land on the registered grid point, measured hours apart on the same card.**

---

## AND THE CAVEAT THAT MATTERS MORE THAN THE CONFIRMATION

**Six of twelve per-workload optima DIFFER between P1 and P4**, even though the medians agree:

| workload | P1 | P4 |
|---|---|---|
| bgemm32 | 1545 | **2167** |
| bgemm64 | 2010 | **1545** |
| conv | 2010 | **1852** |
| layernorm | 2167 | **2010** |
| reduce | 2475 | **2625** |
| softmax | 2167 | **1702** |

**Do not interpret those differences as configuration effects.** An optimum is an **argmax over
13 points**, and `../5060ti-finefloor-20260922/README.md` documents — measured this same morning —
that isolated points lose **8–11% transiently** while their neighbours are untouched. **One
degraded point is enough to push an argmax onto a neighbouring grid step.**

**The median survives this because it is a rank statistic over twelve workloads. A single
workload's pick does not.** These suites are **n=1 per configuration**, so every per-workload
number here is a single draw from a distribution whose tail was characterised only today.

### What this implies beyond these two suites

**The project's existing per-workload optimum shifts need re-reading against this.** CLAUDE.md
records the ABBA manipulation as *"all 12 workloads moving upward, range +79 to +540 MHz"*. The
suite grid is ~155 MHz, so:

- a shift of **+465** is three grid steps and **far outside** what a transient point can produce;
- a shift of **+79** is **under half a grid step** and is exactly what one degraded point looks like.

**So the large shifts are safe and the small ones are not established.** That is not a
retraction of the ABBA result — its median moved +465 and every workload moved upward, which no
transient explains — but **the per-workload range quoted alongside it rests on single draws.**
Replicated suites would settle it; none exist.

---

## Provenance

| checkpoint | memory clock under load |
|---|---|
| before applying P4 | **13801 MHz** (stock) |
| after applying P4 | **16301 MHz** — exactly +2500 |
| after reverting to P3 | **13801 MHz**, 180 W |

**The profile store hashed `e5cbe0ecd89d899c`, byte-identical to the committed
`data/afterburner-profiles/5060ti-profiles-20260918/` snapshot** — so this is the *same* P4 that
produced the committed results, verified rather than assumed. CLAUDE.md's rule that "a slot number
is not an identity" is satisfied by hash, not by trust.

**Hash the per-device `VEN_10DE&DEV_2D04&…cfg`, never `ProfileN.cfg`.** The five `ProfileN.cfg`
files are **31-byte stubs that all hash identically** and hold no curve data, so comparing them
would report "nothing changed" no matter what was edited. The 09-18 snapshot README already
records this; it is repeated here because it is the kind of check that looks done when it is not.

- Iterations matched per workload to `suite-replicate-r10-20260918`.
- HWiNFO at `SensorInterval=500`, one log per sweep.
- **Nothing was edited.** P4 applied and reverted; no curve modified.
