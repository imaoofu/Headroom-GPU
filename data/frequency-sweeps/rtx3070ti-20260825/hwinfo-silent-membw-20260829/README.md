# Session C, part 1 — the SILENT `membw` matched-2130 sweep, 2026-08-29

The sweep Session B planned and never collected. Its own README records the gap:
*"`membw` matched 852–2130, 13 pts — **never collected.** No sweep output exists and no HWiNFO
log covers a `membw` run."* This closes it.

**Collected on the customer's machine, SILENT BIOS as found, stock throughout.** VBIOS
`94.04.5a.00.91`. HWiNFO logging at 500 ms, deliberately — the OC counterpart it is compared
against was also HWiNFO-logged, and matching a clean run against a logged one would put a
condition difference inside the one comparison this sweep exists to close.

13 points, 13 with performance data, 11 locks held, peak SM 1947 MHz, `COLLECTION SUCCEEDED`.
Two points ran below target at the top of the range, which is the usual boost-bin behaviour and is
recorded by the tool rather than hidden.

Raw HWiNFO log is `hwinfo-silent-membw-matched2130.csv`, kept whole in `data/HWiNFO-Data/`
(gitignored, 1.87 MB, 327 columns). **Do not distil and discard it** — fan RPM was nearly lost that
way and turned out to answer §5.5.1.1's last open candidate.

---

## The result: the OC BIOS costs far more on the memory-bound workload

Matched frequency, both positions, 13 shared targets from 855 to 2130 MHz:

| | mean | range |
|---|---|---|
| throughput, OC against SILENT | **+0.65%** | +0.42% to +0.79% |
| power, OC against SILENT | **+56.3 W** | +48.7 to +66.9 |

+37.7% more power for two thirds of one percent of bandwidth. §5.5.1 found the same position
costing +23.11% power for −0.00% throughput on `gemm`; the shape is the same and the magnitude is
not.

## The offset is NOT constant — it scales with memory traffic

§5.5.1.1 described the gap as *"a roughly constant ~34 W that does not scale with core clock"* and
excluded voltage, core dynamic power, memory **clock**, crossbar clock, leakage and cooling. This
sweep adds the observation that breaks the "constant" half of that description.

Restricted to the **identical 855–1485 MHz band and the same 7 points** the `gemm` comparison used:

| workload | memory traffic | offset, OC vs SILENT |
|---|---|---|
| `gemm` | ~12 GB/s | **+34.1 W** |
| `membw` | ~545 GB/s | **+57.0 W** |

**Same card, same BIOS pair, same frequencies, same instrument — and a 67% larger offset on the
workload that moves 45× more memory traffic.** A genuinely constant board-level draw cannot do
that.

**What this does and does not license.** It does not identify a mechanism. What it does is point
where the previous exclusions did not reach: §5.5.1.1 ruled out memory *clock*, which is identical
at 9251 MHz in both positions, but a matching clock says nothing about the power drawn by the
memory subsystem at that clock. An OC BIOS running a higher memory rail voltage, or a more
permissive memory controller, would produce exactly this signature — near-zero cost on a
compute-bound workload and a large one on a bandwidth-bound one.

That is a hypothesis, and this project's own record on hypotheses about this gap is two for two
against. It is written here as a lead, not a finding.

## Caveats

- **n = 1 per side.** One SILENT sweep against one OC sweep. A second OC `membw` run exists
  (`oc-bios-membw-r2`) but on the unmatched grid.
- **Four days apart**, 2026-08-25 against 2026-08-29. Both verified quiet, both HWiNFO-logged, so
  the conditions match in the ways this project has previously been burned by — but they are not
  the same session.
- The magnitude is far outside any run-to-run spread this project has measured, which is why the
  direction is reported at all at n = 1.

## One thing it reproduces

`membw` throughput is flat across the whole band — 544.1 to 546.5 GB/s from 855 to 2130 MHz, a
0.44% span while core clock rises 149%. §5.5.3 measured 0.28% across the same range on the OC
position. The SILENT position behaves the same way, so that finding is not a property of one BIOS.
