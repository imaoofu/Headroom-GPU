# How reproducible is a PER-WORKLOAD optimum? — 2026-09-22

**Two twelve-workload suites, same configuration, back to back, one session, agent silent.**
Stock Profile 3 verified live by memory clock (13801 MHz) before starting. Grid 1237–3090 MHz,
13 points; iterations matched per workload to `suite-replicate-r10-20260918`.

## Why this was run

**Nothing in this repository has ever measured it**, and every per-workload claim depends on it:

- CLAUDE.md quotes the ABBA manipulation as **"+79 to +540 MHz"** per workload
- the negative control is quoted as **"4 of 12 workloads move"**
- the predictor audit counts **"`reduce` misses 16 of 16"**

Each is a **per-workload argmax from n=1**. Today's P1 and P4 suites agree on the median (both
2010 MHz) while **six of twelve per-workload optima differ** — and there was no baseline to say
whether six is a lot.

## The answer: 9 of 12

| | |
|---|---|
| per-workload optima agreeing between two identical runs | **9 of 12** |
| median optimum | **1545 in both passes** |
| workloads that differed | `bgemm1024` (1545→1395), `bgemm64` (1545→1395), `reduce` (1852→1702) |

**And the mechanism is in the margins.** The gap between the winning frequency and the
runner-up is **median 0.99%, minimum 0.03%, and 13 of 24 are under 1%**. The optimum is usually a
near-tie, and every workload that flipped had a margin under 1% in both passes:

| flipped workload | margin pass 1 | margin pass 2 |
|---|---|---|
| bgemm1024 | 0.45% | 0.39% |
| bgemm64 | 0.98% | **0.03%** |
| reduce | 0.65% | 0.09% |

**An argmax decided by 0.03% is not a measurement of anything.** It is a coin flip between two
adjacent grid points whose efficiency is indistinguishable.

---

## What this recalibrates

**NARROWED 2026-09-22 by an outside audit (`docs/gpt-findings/2026-09-22-5060ti-session-results-audit.md`), recomputed here.**
The counts all reproduce: 9 of 12, margin median 0.986%, 13 of 24 under 1%. **But one stock pair is ONE
draw of a movement count.** It cannot estimate the null distribution for a comparison that changes
profiles, and P1/P4 and the P2 control each rest on single suites. **Read §1 and §2 below as
cautions, not calibrations**: a per-workload count of 3–6 of 12 cannot be *distinguished* from
noise at this n. It is not *shown* to be noise. The headings below are kept as written.

### 1. "6 of 12 per-workload optima differ between P1 and P4" means nothing

**3 of 12 differ between two runs of the SAME configuration.** Six is barely above that floor.
**Do not read the P1/P4 per-workload differences as a configuration effect** — the caveat
written into `../5060ti-p4-suite-20260922/README.md` this morning is now quantified rather than
merely suspected.

### 2. The negative control looks BETTER, not worse

CLAUDE.md records the `repair-suite-p2-20260909` control as **"partially leaky"** because
**4 of 12 workloads move**, and warns it "must not be described as a clean null."

**Two identical runs move 3 of 12.** So "4 of 12" is within one workload of the noise floor.
~~**The leak that the file treats as a real weakness is largely measurement reproducibility**, and
the control is closer to clean than it has been credited.~~ **Struck 2026-09-22:** one pair
cannot show that. What it shows is that the leak is **of the same size as** one measured
same-configuration flip count. This does not license calling it a
clean null either — it licenses saying that a per-workload movement count near 3–4 of 12 carries
almost no information, in either direction.

### 3. The ABBA manipulation is untouched

**All 12 moving upward** is nothing like this. Between identical runs, 3 of 12 move and they move
in **both** directions, by one grid step, on near-ties. A systematic 12-of-12 upward shift with a
median of +465 MHz — three grid steps — is far outside anything measured here.

**But the quoted RANGE still is not safe.** A per-workload shift of **+79 MHz** is under half a
grid step and is exactly what a near-tie flip produces. The large shifts are real; the small end of
"+79 to +540" is not established.

### 4. Use the median. It is the statistic that survives.

Both passes give **1545**. Across today's five suites — stock ×2, P1, P4 — every median landed on
a single grid point and none moved. **Per-workload counts are fragile; the median is not.**

---

## The floor, measured from these same runs

Voltage extracted from each sweep's own HWiNFO log rather than borrowed:

| configuration | floor V | highest grid point still at floor | median optimum (achieved) |
|---|---|---|---|
| stock | 0.720 | **1537** (12 of 12 workloads) | **1537** |
| P1 | 0.720 | **2002** (10 of 12) | **2002** |
| P4 | 0.720 | **2002** (11 of 12) | **2002** |

**The rule — the optimum is the top of the floor — lands EXACTLY on all three configurations,
with floor and optimum taken from the same sweeps.**

**This is a COARSE grid and that is the whole caveat.** CLAUDE.md's 2026-09-20 audit found that
on the one clean **fine-grid** record the efficiency argmax sits **158 MHz below** the floor's end,
and that *"the optimum IS the top of the floor" is a coarse-grid artifact*. Today's agreement is
on a 155 MHz grid where the top of the floor and the argmax are the same point by construction.
**It confirms the rule is useful for picking a grid point. It does not overturn the fine-grid
finding, and must not be quoted as if it did.**

The prediction registered on 2026-09-11 assumed floor extents of **1972 (P1)** and **2002 (P4)**,
*"30 MHz apart"*. Measured here both sit at **2002** — but a 155 MHz grid cannot resolve 30 MHz, so
this is consistent with the assumption rather than a correction to it.
