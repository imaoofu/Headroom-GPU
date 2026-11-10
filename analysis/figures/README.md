# Submission figures

Each figure is drawn by a script here from the committed data, so it cannot drift from the numbers
it shows. Output: `docs/submission/figures/<name>.pdf` (for the paper) and `.png` (for review).

```
python analysis/figures/fig_floor_optimum.py
python analysis/figures/fig_ladder.py
python analysis/figures/fig_membw.py
python analysis/figures/fig_ranges.py    # needs the fetched data/external and data/raw sets
python analysis/figures/fig_session16.py
python analysis/figures/fig_workloads.py
python analysis/figures/fig_headroom.py
```

| figure | shows | data |
|---|---|---|
| `fig_floor_optimum` | voltage (top) and median twelve-workload efficiency (bottom) against locked clock, one stock session per card | `5060ti-stock-repro-20260922` rep1, `rtx3070ti-sessiond-20260924` stock-1, `rtx3060-20260910` suite, `rtx2060s-sessione2-20260927` stock-4 |
| `fig_ladder` | RTX 5060 Ti: the clock each applied curve reaches at 0.720 V against its median optimum, with the control | every suite `analysis/models/predict_from_curve.py` loads |
| `fig_membw` | RTX 5060 Ti: `membw` throughput and crossbar clock, stock against the flattened curve, memory matched | `5060ti-memmatched-20260926` |
| `fig_session16` | RTX 5060 Ti, §16: each workload's optimum on the opening factory-floor suite (P5) against the lifted floor (P4) and against the control (P2) | `5060ti-session16-20261006`, scored by `analysis/score_session16.py` |
| `fig_workloads` | RTX 5060 Ti: every workload's efficiency against locked clock, one panel each, with its optimum and the floor end | `5060ti-stock-repro-20260922` rep1, the same suite as `fig_floor_optimum` |
| `fig_headroom` | per-workload efficiency gain at the optimum over the highest clock reached, RTX 5060 Ti (mean of six suites) against RTX 3070 Ti (one suite) | `claims_consumer._gainsOf`, the paper's own gain |
| `fig_ranges` | the core-clock range each dataset sweeps, in absolute MHz, with defaults, the highest clock reached at stock, and optima | `data/external/gtx1080ti.csv`, `gtx2070s.csv`, `data/raw/dataset_efficiency.csv`, and the four suites above plus two low-range sweeps |

**Caption facts each figure needs** (they are not visible in the plot):
- `fig_floor_optimum`: the dashed line is the last point *of that suite's grid* at the lowest
  voltage. On the 5060 Ti that grid is ~155 MHz wide, so it reads 1545 MHz; the fine sweep puts the
  floor's end at 1567–1575 MHz. The 3070 Ti's floor wanders by one 6.25 mV code. The 2060 Super's
  E2 grid starts at 855 MHz, so its title's "min. on grid" (the lowest voltage that session's grid
  reached) reads 0.637 V; a separate low-range
  session reads 0.631 V, and the caption must say so (GPT Job 33).
- `fig_ladder`: n counts sweeps, not independent samples; each configuration is one chip. Rung D
  against rung A is the manipulation found after the fact (post hoc); the control and rungs B and C
  were registered before collection.
- `fig_session16`: the control's count is against the OPENING factory-floor suite (4 of 12), the
  like-for-like comparison with the two factory-floor suites' own difference (5 of 12). The
  registered statistic, P2 against BOTH factory-floor suites, is 2 of 12; never set 2 beside 5.
  Coinciding lines are drawn once, with width and a label for their count. One chip, one session.
  The "+465 MHz" in the P4 label is the curves' difference below the floor; **they also differ by
  about −98 MHz near 875 mV**, so the floor contrast is not region-isolated, and a caption must say
  so (GPT Job 56, F02). Label placement was moved off the flat line in response to F09.
- `fig_workloads`: one suite, one session; the floor line comes from that suite's `gemm` voltage
  extract and is the last grid point at 0.720 V, not the fine-grid floor end (1567–1575 MHz).
- `fig_headroom`: the 5060 Ti bar averages six suites, the 3070 Ti bar is one suite, so the two are
  not equally certain; the gain is an upper bound on deployment savings. One card per model.
- `fig_membw`: one sweep per arm; the crossbar was observed, never set, so this is an association.
- `fig_ranges`: **absolute MHz, never a percentage**, because the sources share no reference clock
  (declared default, stock clock, lock ceiling); scoring the public sets against a spec-sheet boost
  is how §2.7 was wrong for four weeks. On this work's cards the grid runs past the diamond because
  the top targets are requested but unreachable at stock. The diamond is the highest clock any of
  the twelve workloads reached in that session, not a rated boost; for the 5060 Ti it differs from
  the ~2584 MHz measured under `gemm` alone. The public consumer sets' optima are not marked: their
  grids bracket only some applications' best points (§2.7). Overlap in absolute MHz does not mean
  equal fractions of each card's default or lock ceiling. The thin extensions are single-workload
  sweeps (decode on the 5060 Ti, `gemm` on the 2060 Super), not the twelve-workload suite.

Style: the repository's dataviz rules for a print figure. One y-axis per panel, colour slots 1–2 of
the validated reference palette plus neutral inks, and markers or dashes so a grayscale print reads.
