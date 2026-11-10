# Prediction models

Everything in this repository that **predicts** rather than **measures**.

The split is not organisational tidiness. The project's headline results are measurements —
`characterize.py` reports the stock-vs-optimum gap with no model involved, and `analyze_sweep.py`
reads what the card actually did. Those numbers stand on their own. Everything in this directory
outputs an *estimate*, and every estimate here has so far been beaten or tied by something that
needed no fitting at all. Keeping them in one place makes that pattern visible instead of
scattered across ten files.

| File | Question it asks | Current verdict |
|---|---|---|
| `predict_optimal_frequency.py` | Which frequency gives the best performance-per-watt? | **Ties** a fixed 952 MHz — 0.883% vs 0.837% mean regret |
| `predict_constrained_frequency.py` | Same, subject to keeping ≥95% of stock performance | **Loses** to straight-line interpolation between the same probes |
| `curve_model.py` | Can a few probes reconstruct the *whole* curve? | **Reconstruction works** (MAE 0.0261); frequency *selection* ties |
| `predict_from_curve.py` | Can the applied **V/F curve** predict the optimum with no workload measurement at all? | **Prospective, 2026-09-26:** on two pre-registered configurations it never saw (rungs B, C), 1.03% / 0.48% mean regret against 4.41% / 6.67% for the old best constant. On the original 192: **Ties a hindsight-fitted per-configuration constant exactly** — 0.675% vs 0.675% — while needing no data |
| `select_probes.py` | How **few** frequencies must be measured, and does choosing *which* ones beat not choosing? | **Selection wins on the curve** (14–18% over even spacing) and **changes the decision by nothing at all** |

## Reconstruction accuracy and decision quality are not the same quantity (2026-09-11)

`select_probes.py` asks the follow-up `curve_model.py` never did: how few probes, which ones, and
does selecting them cleverly beat not selecting at all? The baseline is deliberately the no-thought
one — frequencies spaced **evenly** across the range, which is what anyone characterising a new card
would do without any analysis.

Probes selected **inside each fold**, on training units only. 33 workloads, one V100.

| probes | reconstruction MAE | evenly spaced | regret | where the argmax lands |
|---|---|---|---|---|
| 1 | 0.0336 | 0.0336 *(tie — same frequency)* | **0.84** | 952 MHz, 33 of 33 |
| 2 | 0.0290 | 0.0336 | **0.84** | 952 MHz, 33 of 33 |
| 3 | 0.0261 | 0.0318 | **0.84** | 952 MHz, 33 of 33 |
| 4 | 0.0243 | 0.0294 | **0.84** | 952 MHz, 33 of 33 |
| 5 | 0.0230 | 0.0281 | **0.84** | 952 MHz, 33 of 33 |

**Going from one probe to five improves the reconstructed curve by 31% and improves the decision
by 0.00 points.** The argmax lands on 952 MHz in 33 of 33 folds at every probe count — and 0.84 is
also exactly what the best fixed frequency scores with no probing whatsoever. The efficiency curve
is flat near its peak, so a measurably better curve produces an identical choice.

**This is the V100 null in its sharpest available form, and it is a warning about a common
shortcut.** "Our model reconstructs the curve to MAE 0.023" sounds like progress and is, for the
curve. It is worth nothing for the decision the curve exists to inform. Any claim that better
curve-fitting yields better tuning has to show the decision moving, not the fit improving.

**Probe SELECTION does earn something — on the curve, from k=2 up**, beating even spacing by
14–18%. The reason is mechanical: per-frequency variance across units falls monotonically from
0.142 at 757 MHz to **exactly zero** at 1530, so selection piles probes at the low end while even
spacing wastes them near the top. At k=1 the two strategies pick the same frequency and tie, which
is a tie and is reported as one.

**No probe count tested reconstructs to inside this project's own measurement noise.** Five
probes give 0.0230 against the 0.0076 within-session spread `CLAUDE.md` records — still 3× outside
it. So "characterise a card from a handful of probes" is **not** supported at the curve level by
this data, only at the level of the single decision, where one probe is already as good as thirteen.

### Two audit findings that came out of building it

**`curve_model.evaluate()` selects its probes with hindsight**, on all 33 units, then scores the
model on those same units — the selection sits outside the fold even though the reconstruction
error inside it is leave-one-out. **Measured at exactly 0.0000 at every k**, because all 33 folds
choose the identical probe set (1 distinct set in 33, every time). Wrong in principle, free in
practice, annotated rather than rewritten — the fix lives in `select_probes.py`, which is nested by
construction and has a spy test proving the held-out unit never reaches the selector.

**The published "four probes" are three.** Curves are normalised to the top frequency, so that
column is exactly 1.0 for all 33 units — zero variance, no information — and `alwaysIncludeTop=True`
spends a slot on it. Free in wall-clock terms, worthless in information terms, and it means probe
counts across this directory are not counting the same thing.

**Greedy selection is optimal here**, matching an exhaustive search over every subset to six
decimal places at k=1, 2 and 3. Not checked at k=4 or 5, and the docstring now says so.

**And the test suite for this file initially failed its own mutation gate.** The fold-isolation
check built an outlier and asserted that selecting with and without it agreed, reasoning that a leak
would pull the selection toward the outlier. Reintroducing the exact leak did not fail it — one
outlier in twelve does not change which single column wins. **A test whose premise is "the defect
would change the answer" is only as good as that premise.** It was replaced with a spy that asserts
what the selector is *handed*, which fails on the mutation immediately.

---

## The fourth file asks a different question, and it changes what the null means

The three files above all predict from **measurements of the workload**, and all of them tie or lose.
`predict_from_curve.py` predicts from the **hardware configuration** instead: the optimum is the last
frequency the V/F curve reaches at the card's 0.720 V load floor.

**This is why the others lose, and it is a property of the DATASET rather than of modelling.**
Across 192 consumer sweeps under four applied curves, a variance decomposition puts **61.9%** of the
optimum's variance on the configuration and **19.0%** on the workload. The public V100 set contains
**exactly one configuration**, so that 62% is invisible in it by construction — all a model can see
there is the 19% term against roughly as much noise, which is why a constant is nearly the right
answer. "The model loses" is the correct result and now has a mechanism behind it.

**What the curve-reading predictor actually earns, stated carefully:**

| | mean regret | exact |
|---|---|---|
| oracle | 0.000% | 100% |
| **read the curve at the load floor** | **0.675%** | **74.0%** |
| best constant **per configuration**, fitted with hindsight | **0.675%** | 74.0% |
| best **single** constant, fitted with hindsight | 1.961% | 60.9% |

- It beats the best single constant **2.90×**, and 142 of 192 sweeps come out exactly optimal.
  **ALL of that 2.90× is one configuration** — drop `fulltune` and the mechanism, the single
  constant and the per-configuration constant are **identical** at 0.626% over 144 curves. The tool
  prints this decomposition itself; do not quote the ratio without it.
- **It ties the per-configuration constant to three decimals** because it picks the identical
  frequency every time. **The next clause said "it extracts everything the configuration axis
  holds", and that was withdrawn 2026-09-20** — both strategies emit the same **two** discrete
  frequencies on a ~155 MHz grid, which bounds nothing about the axis. **What the tie DOES show is
  that the mechanism loses nothing to a constant fitted on the answers.** Its value is needing no
  measurement — a per-config constant requires sweeping every
  configuration first — not being cleverer.
- **It is not "zero-parameter" in a fair comparison.** It reads the V/F curve, which the constant
  and the Ridge baselines never had. The curve is free to obtain, so this is not cheating, but it is
  a **different information set**. The honest claim is *"there is a free feature nobody was using"*,
  not *"fitting was done better"*.
- **AND THE WHOLE AXIS IS WORTH 1.29 POINTS OF REGRET, against a headroom of 30–57 points.**
  Predictor choice barely matters. Anyone quoting the 2.90× without this sentence is overselling it.

**The residual is one workload.** `reduce` is sub-optimal in **16 of 16** sweeps and carries most of
what is left; with `gemm` it accounts for **70%** of all remaining regret. That is structure, not
noise, and it is a mechanism question rather than a modelling one.

**Limits:** one chip; four configurations but only **two distinct predicted values** (1537 and
2002), so "configuration" is close to a binary variable here and the 61.9% must be read with that in
mind.

### The floor voltage does NOT transfer between cards — corrected 2026-09-10

This section said the 0.720 V floor "was measured on this card and is assumed to transfer." **The
assumption was wrong, and testing it produced a better result than confirming it would have.**

An **RTX 3060 (Ampere, 8 nm) has a load floor of 0.756 V.** Its floor ends at **1260 MHz** and its
efficiency optimum is **1260 MHz** — nine of twelve workloads land there individually. The rule holds
exactly, with a different constant. Full record in `data/frequency-sweeps/rtx3060-20260910/`.

**The rule transfers; the parameter is per card.** A shared constant would most likely have meant
a driver policy. A differing one means the floor is a property of the silicon **and the relationship
survives it anyway** — which is what turns this from a finding about one card into a finding about
GPUs.

**So applying the predictor to a new card requires measuring that card's floor first.** Borrowing
0.720 V for the 3060 predicts ~1530 MHz against a true optimum of 1260 — a **270 MHz error**, worse
than the best single constant. The evaluation above is 5060 Ti data only and stands as written;
nothing in it is fitted across cards.

Each has a `test_*.py` beside it. All three are mutation-gated: the suites were accepted only
after deliberate bugs were introduced and caught.

## The result this directory exists to keep honest

Read the three verdicts together and they say something more useful than any one of them:

- **Probing carries real information.** Under a 95% performance floor a probe-based strategy
  reaches 25.4% mean efficiency gain against a fixed frequency's 4.9% — 87% of the gap between the
  fixed policy and a perfect oracle.
- **The fitting is not what extracts it.** The strategy that gets there is four straight line
  segments. Ridge appears to do better only by breaking the floor on 8 of 33 workloads; made to
  respect it, it does worse than the interpolation.
- **And unconstrained, none of it matters**, because 952 MHz is optimal for 24 of 33 workloads and
  a constant is nearly the right answer everywhere.

So the honest summary is *measure a few points, interpolate, and attach a performance guarantee* —
not *fit a model*. That conclusion is only visible because the baselines were built to embarrass
the models rather than to flatter them, which is the rule these files are held to.

## What these models actually are, and the weakness in how they are built

Worth stating plainly, because "model" oversells them. Every file here fits **`Ridge(alpha=1.0)`** —
ordinary least squares with an L2 penalty. No trees, no ensembles, nothing deep. The fitted object
has `coef_` of shape `(13, 8)`, which means it is **13 independent linear equations**, one per
frequency in the sweep, each predicting efficiency there as a weighted sum of the same 8 features:
performance at 4 probe frequencies, and power at those same 4 expressed as a ratio against stock.

**117 learned parameters against 32 training rows** in each leave-one-out fold. More parameters
than examples, which is why the L2 penalty is load-bearing rather than decorative.

That is the right size of model for this data and not an apology. With 33 workloads and a matrix
carrying no workload feature columns at all, anything larger overfits on contact. The comparison
ladder the three files establish runs *constant → nonparametric interpolation → regularised linear
→ oracle*, and two of those four are not statistical models: the fixed-frequency baseline is a
constant predictor using zero features, and the interpolation baseline has zero learned parameters
and simply joins the probes with straight lines.

**THE WEAKNESS: the 13 output equations are fit independently, so nothing constrains the
predicted curve to be smooth or single-peaked.** `chooseByProbeModel` takes `argmax` over 13
unconnected linear predictions. In principle that argmax can land on a jagged artifact rather than
a peak, and no part of the construction prevents it.

It is mitigated rather than solved. Predicting the whole curve and taking its peak — instead of
regressing the optimal frequency directly — means a wrong answer tends to land on a neighbouring
frequency on a flat part of the curve rather than somewhere arbitrary, which is why the code is
written that way and says so. But that is a property of the efficiency curve being flat near its
top, not a guarantee the model provides.

**It is deliberately not fixed.** The obvious repair is to fit a parametric curve shape, or to
constrain the outputs to be unimodal. That is effort spent making a model that already loses to
straight-line interpolation lose by less. If the constrained result is ever revisited on data with
real workload features — the consumer suite characterises arithmetic intensity, which the V100
matrix does not have — the fix belongs in that work rather than this one.

If a reader asks why no parametric curve was fitted, the answer is the honest one: a fit was tried,
and the unfitted baseline beat it.

## Running them

Every file is a script, run directly. No package, no `-m`, no install:

```bash
python analysis/models/predict_constrained_frequency.py
```

They import `load_data.py` from `analysis/`, one level up, via an explicit `sys.path` line at the
top of each file. That is deliberate rather than a `__init__.py` package: the whole toolchain is
built to run on a machine with no setup, and relative imports would force `python -m` and break
every command written down in the README, `HANDOFF.md` and the paper.

**If you add a suite here, it is already covered** — `analysis/models` is listed in
`run_tests.py`, and that runner now fails if it finds a `test_*.py` under a directory it is not
running. It gained that guard because moving these three files into this directory would
otherwise have dropped them from every future run while still printing *All suites passed*.

## What is deliberately not here

`analyze_constrained.py` computes the constrained **oracle** — the best achievable answer with the
whole measured curve in hand. That is a measurement of an upper bound, not a prediction, so it
stays in `analysis/`. `predict_constrained_frequency.py` cross-checks itself against it on every
run, reproducing 28.5% and 4.9% at 1462 MHz before it reports anything of its own.

`curve_model.py`'s `specs` mode — predicting a never-measured chip from its spec sheet — is an
inactive extension point. It needs a specs database and enough distinct chips to fit against.
Two chips is not enough, and the file says so rather than printing a number.
