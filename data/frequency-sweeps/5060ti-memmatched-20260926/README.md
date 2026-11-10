# The `membw` plateau with memory matched — worklist item 4j, 2026-09-26

**Five sweeps in one unattended session on the RTX 5060 Ti, driver 616.92**, collected by
`tools/hwinfo-logging/Invoke-LoggedSweep.ps1` with HWiNFO at 0.50 s and every sweep time-joined to
its own voltage extract (minimum 14 samples per point). ChatGPT and Codex were closed; every
preflight read 2.8–3.6% baseline utilisation.

This collects `docs/REGISTERED-PREDICTIONS.md` §12, **registered 2026-09-26 before collection**
(commit `6b01061`).

| order | sweep | profile | grid |
|---|---|---|---|
| 1 | `5060ti-4j-stock-membw` | P3 stock (180 W, memory +0) | 1400–2100, 10 points, default iterations |
| 2 | `5060ti-4j-stock-gemm` | P3 stock | 1237–3090, 13 points, 120 iterations |
| 3 | `5060ti-4j-curve3-membw` | P1 = curve 3: **P4's curve exactly, memory +0**, 200 W | as 1 |
| 4 | `5060ti-4j-curve3-gemm` | P1 = curve 3 | as 2 |
| 5 | `5060ti-4j-stock-membw-r2` | P3 stock, closing drift check | as 1 |

**Memory is matched: `memory_clock_max_mhz` is exactly 13801 at every point of all five sweeps.**
That is the confound this session exists to remove: the only earlier pair with voltage and crossbar
telemetry ran the flattened curve at 16301 and stock at 13801.

---

## Verdict against the registration

| registered | measured | |
|---|---|---|
| **gate:** closing stock `membw` band mean within 1.5% of the opening one | **−0.41%** | interpretable |
| **primary:** curve 3 below stock at every target 1560–1867 | **−7.6% to −13.7%** at all five | **HOLDS** |
| **telemetry:** curve 3 crossbar within 1300–1360, 1402–1867, while stock's rises | **1312–1342**; stock **1335 → 1800** | holds |
| **telemetry:** curve 3 reads **0.720 V** at every target 1402–1867 | **0.725** at 1402 and 1477, **0.7225** at 1560, 0.720 at 1635–1867 | **fails as worded** |
| **secondary:** curve 3 `gemm` draws less power than stock, 1545–2625 | **−3.5% to −22.7%** at all eight (narrowed 2026-10-03: the clean §15 R1 re-run draws equal power at 1545, +0.13%, and less from 1702; see `../5060ti-rerun15-20261003/`) | holds (2625 not clock-matched, below) |

**No registered refutation occurred:** curve 3 is below stock throughout 1560–1867, and its crossbar
does not track the core clock. **So the 2500 MHz memory mismatch in the old pair did not create the
plateau.** It still does not make the crossbar a demonstrated mediator: that needs the crossbar held
fixed at a fixed core curve and memory clock, which this card cannot do.

**The voltage clause fails, and that is reported, not reworded.** Curve 3 reads one 5 mV code above
the registered 0.720 V at the two lowest targets. **Stock reads 0.725 there too**, in this session and
on this workload, so it is not a property of curve 3; the same session's `gemm` sweeps read 0.720 on
both arms at 1237–1545. What the clause was testing still shows: curve 3's voltage stays flat
(0.725 → 0.720) across a 33% rise in core clock while stock's rises 0.725 → 0.805.

## `membw`, by target (GB/s)

| target | stock achieved | stock GB/s | stock V | stock XBAR | curve 3 GB/s | curve 3 V | curve 3 XBAR | curve 3 vs stock | closing stock |
|---|---|---|---|---|---|---|---|---|---|
| 1402 | 1400.2 | 309.0 | 0.725 | 1335 | 303.2 | 0.725 | 1312 | −1.87% | 306.2 |
| 1477 | 1470.0 | 322.1 | 0.725 | 1410 | 304.1 | 0.725 | 1312 | −5.59% | 322.9 |
| **1560** | 1552.0 | 333.8 | 0.730 | 1485 | 308.4 | 0.7225 | 1327 | **−7.62%** | 334.2 |
| **1635** | 1627.0 | 341.9 | 0.740 | 1545 | 311.4 | 0.720 | 1342 | **−8.93%** | 341.5 |
| **1710** | 1702.0 | 350.9 | 0.760 | 1635 | 311.0 | 0.720 | 1342 | **−11.37%** | 352.2 |
| **1792** | 1785.0 | 356.7 | 0.780 | 1710 | 312.5 | 0.720 | 1342 | **−12.40%** | 355.1 |
| **1867** | 1860.0 | 360.7 | 0.805 | 1800 | 311.2 | 0.720 | 1342 | **−13.73%** | 357.4 |
| 1942 | 1935.0 | 362.8 | 0.820 | 1867 | 322.6 | 0.720 | 1395 | −11.07% | 359.7 |
| 2025 | 2017.0 | 363.6 | 0.840 | 1935 | 332.9 | 0.720 | 1470 | −8.45% | 360.6 |
| 2100 | 2084.6 | 363.4 | 0.840 | 1935 | 343.6 | 0.740 | 1552 | −5.47% | 361.0 |

(Achieved clocks on curve 3 match stock's to within 7.4 MHz at every target, and within 5.2 MHz from 1402 to 2025.) `membw` drew 50–67 W,
far below either power limit, so the 180 W / 200 W difference does not touch this comparison.

**Also seen, not registered:**
- **The two arms diverge while reporting the same voltage.** At **1477** both read **0.725 V**, yet
  curve 3 is already **5.6% slower** and its crossbar reads **1312** against stock's **1410**. That
  reproduces, now memory-matched, the observation that retracted the old "they agree where their
  voltages agree" sentence (CLAUDE.md, 2026-09-18): **the reported voltage is not the state variable.**
  XBAR and throughput follow the curve configuration.
- **Curve 3's plateau sits at 303–312 GB/s**, not at the ~281 GB/s where the 2026-08-20 pair's
  plateau began and §3.3.1's concurrency ceiling sits. That older pair is **a different session and a
  profile not proved identical to today's P4**, at a different memory clock, so this is recorded, not
  interpreted. It bears on the open question of whether the curve *creates* the plateau or keeps the
  card under a ceiling that already exists.

## `gemm`, by target

| target | stock achieved | stock W | stock V | curve 3 achieved | curve 3 W | curve 3 V | power | efficiency |
|---|---|---|---|---|---|---|---|---|
| 1237 | 1236.4 | 59.6 | 0.720 | 1235.9 | 59.4 | 0.720 | −0.3% | +0.3% |
| 1395 | 1388.4 | 64.6 | 0.720 | 1393.1 | 66.2 | 0.720 | +2.5% | −2.6% |
| **1545** | 1537.0 | 71.7 | 0.720 | 1537.0 | 69.2 | 0.720 | **−3.5%** | +3.8% |
| **1702** | 1695.0 | 82.4 | 0.755 | 1695.0 | 76.0 | 0.720 | **−7.7%** | +7.5% |
| **1852** | 1845.0 | 96.6 | 0.795 | 1845.0 | 80.7 | 0.720 | **−16.5%** | +18.3% |
| **2010** | 2002.0 | 113.3 | 0.840 | 2002.0 | 87.5 | 0.720 | **−22.7%** | +28.8% |
| **2167** | 2150.8 | 120.8 | 0.840 | 2160.0 | 103.5 | 0.755 | **−14.4%** | +18.3% |
| **2317** | 2310.0 | 142.1 | 0.885 | 2310.0 | 115.6 | 0.790 | **−18.6%** | +22.0% |
| **2475** | 2460.3 | 163.6 | 0.940 | 2467.0 | 139.0 | 0.840 | **−15.1%** | +17.9% |
| **2625** | **2483.2** | 173.6 | 0.950 | 2601.8 | 147.9 | 0.845 | **−14.8%** | +21.6% |
| 2782 | 2488.4 | 167.9 | 0.950 | 2769.9 | 166.3 | 0.890 | −1.0% | +12.8% |
| 2932 | 2484.1 | 172.8 | 0.950 | 2883.2 | 180.5 | 0.9175 | +4.4% | +11.8% |
| 3090 | 2492.6 | 171.1 | 0.950 | 2896.5 | 185.0 | 0.920 | +8.2% | +8.2% |

**From 2625 up, stock is at its 180 W limit and holds ~2485 MHz whatever the target**, so those
rows are not clock-matched; 2625 is inside the registered range and is marked. Without it the
secondary still holds at all seven remaining targets (−3.5% to −22.7%). The registration anticipated
this and stopped the prediction at 2625 rather than at the top of the grid.

This agrees with the §5.7 figure it replicates memory-matched: the flattened curve's `gemm` power
advantage at matched clock (**−17% to −28%** there) is present here at **−14% to −23%** from 1852 to
2475, with memory now removed as a difference.

## Provenance

- **Before applying anything,** the live Afterburner store was byte-identical to the committed
  snapshot `data/afterburner-profiles/5060ti-profiles-20260926-curve3/` (SHA-256 begins
  `8ec197f30e21d116`).
- **Each arm verified live** before its sweeps: memory under load 13801 on all three (no +2500 slot
  was live) and power limit 180 W (stock) or 200 W (curve 3).
- **After the session:** reverted to P3 and verified at 13801 MHz, 180 W.
- NVML offset 0.

**`runner-console-attempt1-refused.log` is a first launch whose data is NOT used.** It completed the
two stock sweeps, then the curve 3 arm's first preflight refused at **20% SM**: it ran straight after
the arm's live-profile witness, which itself runs a short `gemm` load, and only the first arm had a
settle period. The runner reverted to stock and exited 6. **The whole session was re-run** so all five
sweeps come from one continuous session as registered; the runner (`runner-run-4j.ps1.txt`) now waits
90 s after every arm's witness. Attempt 1's sweep files were set aside off-repository and are not
dataset-grade. `runner-console-attempt2.log` is the run.

## Limits

One chip, one session, one sweep per arm. The two arms differ in power limit (200 W against 180 W);
that does not reach `membw` (under 70 W) and is marked where it reaches `gemm`. Raw HWiNFO logs are
in `data/HWiNFO-Data/5060ti-memmatched-20260926/` (gitignored).

## What is dataset-grade

All five sweeps: complete, verified-live, memory-matched, with voltage. Console logs and runner text
are provenance.
