<!-- dataset-grade: yes -->

# `5060ti-finefloor-20260918` — the 0.720 V floor, finally measured finely

**Two `gemm` sweeps, 1380–1760 MHz, 13 points ~31 MHz apart, stock Profile 3, Zotac RTX 5060 Ti.**
Driver **616.92**, 180 W enforced, schema 0.3.3. Both: 13 of 13 measured, 13 distinct clocks, all
locks held, 0 drifted / overshot / undershot, `workload_result_verdict: ok`, memory **13801 MHz**
at every point.

**Why.** The project's most load-bearing number — the 0.720 V floor ending at "1537" — rested on
**three points at 158 MHz spacing**. The RTX 2060 Super looked flat at 60 MHz and turned out
non-monotonic at 15. Band chosen by dry run so a target lands exactly on 1537.

---

## Result 1: the floor is genuinely flat

| MHz | 1378 | 1402 | 1432 | 1462 | 1500 | **1530** | **1560** | 1590 | 1620 | 1657 | 1687 | 1717 | 1747 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | **0.720** | **0.720** | 0.730 | 0.740 | 0.745 | 0.755 | 0.760 | 0.765 |

Seven consecutive points at 0.720 V, then a clean monotonic rise. **No Turing-style
non-monotonicity on this card.**

## Result 2: the floor ends LATER than the project recorded

0.720 V still holds at **1560**; the first rise is at **1590**. `CLAUDE.md` said the floor ends at
**1537** — a figure that was never measured, inferred from a coarse grid whose nearest points were
1545 (0.720) and 1702 (0.755), a 157 MHz gap with nothing in it.

**The rule still selects the right grid point** — the suite grid is ~158 MHz and a prediction
only needs to land within half a step. But **the floor end and the measured optimum are not the
same number**, and the project had been treating them as one.

**The exit is gradual** — ~5–10 mV steps, not the 3060's single 31 mV jump.

## Result 3: contamination destroys throughput and leaves voltage alone

`…-201559` was contaminated: the operator ran the 792-check test suite and git alongside it.
`…-202543-r2` is the clean re-run.

| | contaminated → clean |
|---|---|
| **throughput** | faster at **every** point, mean **+9.38%**, range +5.9 to +13.2% |
| **voltage** | **identical at 11 of 13 points**, max difference **5 mV** (< one 6.25 mV code) |
| **crossbar** | within 11 MHz at every point |

**So voltage from a contaminated sweep is usable; throughput is not.** It follows from the
fixed-frequency droop test — the reading is a VID lookup, not a measurement, so it cannot respond
to load. That matters for the whole corpus, since §5.4.4 records that every cross-configuration
comparison here was taken under uncontrolled desktop load.

**AND A DIAGNOSTIC LESSON.** The contamination was first assessed by point-to-point residual
(does throughput track clock between neighbours?). That flagged five mid-band points and called the
rest clean. **It was wrong — a point-to-point test measures SHAPE and is blind to a uniform
offset**, which was most of the effect. Only comparing two runs exposed the 9% level shift.
**Never certify a sweep clean from within-run shape alone.**

## Provenance

**Both sweeps are kept and both are dataset-grade**, per this project's rule that a flag records
a condition rather than disqualifying data. `…-201559`'s `applied_settings` records a verified-quiet
**preflight**, which was true when taken — the load arrived afterwards. **Use r2 for any throughput
number. Either is fine for voltage.**

Sampling was the main machine's **2.00 s**, giving 5–9 samples per point. Adequate for a constant
median, **not** for the dither analysis the kit's 0.50 s supports.

**Driver 616.92** — first data in this project on it, up from 616.56 in `CLAUDE.md` and 616.64
earlier the same day. A reboot pulled the update mid-session.

Joined with `--clock-tolerance 7`; the ±25 MHz default correctly refuses on a 31 MHz grid.
