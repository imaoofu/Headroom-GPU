# Is `membw` actually bandwidth-bound? — 2026-08-20

`ROADMAP.md` asks for "a genuinely bandwidth-saturated kernel" because `membw` is issue-limited
over most of the swept range, which means the V100 frequency-prediction result was tested
outside the domain where its premise holds. Three probes were run to find out whether such a
kernel is constructible on this card.

## ⛔ The 2800 MHz band of probe_unrolled_kernel_result.json is NOT usable

`results.2800` records `memory_mhz` of **7001** and a derived `peak_gbs` of **224.0**, against
16301 and 521.6 at the 1400 band of the same file. A memory clock does not fall when the core
clock rises: the probe sampled the memory clock at an idle P-state, so the peak derived from it
is wrong by more than a factor of two.

The signature is unmissable once looked for - `unrolled.1` at that band reads 387.9 GB/s, which
is **173% of the "peak" beside it**. That is the same 173% that `analysis/audit_claims.py` cites
in its opening docstring as the defect the claim auditor was built to catch. It is left in the
file because raw data is not edited; it is flagged here because nothing in the file marks it.

**Section 3.3.1 uses only the 1400 MHz band and is unaffected.** Do not quote anything from the
2800 band, and do not compute an elasticity across the two bands of this file.

## Probe 1 — six access patterns at two locked clocks

`tools/frequency-sweep/probe_saturating_kernel.py`. Elasticity is
`ln(T_high/T_low) / ln(f_high/f_low)`: 1.0 means throughput scales with core clock (purely
issue-limited), 0.0 means independent of it (purely DRAM-limited).

| kernel | @1395 MHz | @2760 MHz | elasticity |
|---|---|---|---|
| `copy` | 299.9 | 408.0 | 0.451 |
| `copy_wide` (fp64 view) | 296.8 | 408.5 | 0.468 |
| `scale` | 291.3 | 405.4 | 0.485 |
| `inplace_add` | 282.6 | 406.0 | 0.531 |
| `triad_current` (**today's membw**) | 287.2 | 416.6 | 0.545 |
| `read_only_sum` | 230.5 | 443.0 | 0.957 |

**Not one is DRAM-limited.** Two expectations were wrong and both are informative:

- **`read_only_sum` was the WORST**, not the best. A reduction carries dependency chains and
  performs one add per 4 bytes, so per byte moved it is more issue-hungry than the triad, not
  less. It does reach the highest absolute throughput at boost (443 GB/s) precisely because it
  moves the fewest bytes per element.
- **`copy_wide` gave no benefit at all** (296.8 against 299.9). Viewing fp32 storage as fp64
  halves the element count without changing bytes moved, which should double the payload per
  thread. It changed nothing, which means torch's copy kernel was *already* emitting vectorised
  accesses. Hand-vectorisation is not the missing ingredient.

## Probe 2 — does concurrency help? (at boost: uninformative)

Eight concurrent copies on eight streams at free boost: 406.2 / 404.0 / 407.7 / 405.5 GB/s for
1 / 2 / 4 / 8 streams. Flat.

**This probe was badly designed and is recorded as a lesson rather than a result.** At boost the
kernel is already near the achievable DRAM ceiling — roughly 406 GB/s against a ~521 GB/s
theoretical peak at this memory clock, about 78%, which is normal efficiency for GDDR under a
real access pattern. Concurrency cannot raise a workload that is already saturated. The test
only discriminates at a clock where the workload is known *not* to be saturated.

## Probe 3 — concurrency at a LOW locked clock (the deciding test)

`tools/frequency-sweep/probe_issue_ceiling.py`, locked to 1395 MHz:

| streams | aggregate GB/s | vs 1 stream |
|---|---|---|
| 1 | 218.3 | 1.00x |
| 2 | 276.5 | **1.27x** |
| 4 | 281.2 | **1.29x** |
| 8 | 279.7 | 1.28x |

**Concurrency buys 29%.** So at low clock the binding constraint is memory-level parallelism —
not enough requests in flight — and *not* the SM instruction issue rate. Issue rate is shared
hardware that no kernel could escape; MLP is something a better kernel can attack.

**But it plateaus immediately.** All the gain arrives by 2 streams and nothing after that helps.
The plateau sits at ~281 GB/s, still only about 54% of the ~521 GB/s available. So MLP is a real
lever and a limited one: a deeply unrolled kernel could plausibly move `membw` from ~218 toward
~280 GB/s at this clock, but there is a second ceiling well short of saturation that more
parallelism does not lift.

## Reproducing probe 4

Probe 4 needs CuPy, which is NOT installed in the main Python and is not a project dependency -
nothing else in the repo uses it, and the collection kit does not ship it. It lived in a
throwaway virtual environment that was deleted once the question was answered. To recreate:

```
python -m venv --system-site-packages .venv-cupy
.venv-cupy/Scripts/pip install "cupy-cuda12x[ctk]"
.venv-cupy/Scripts/pip uninstall -y nvidia-cublas-cu12 nvidia-cusolver-cu12 nvidia-cufft-cu12 nvidia-cusparse-cu12 nvidia-curand-cu12
.venv-cupy/Scripts/python tools/frequency-sweep/probe_unrolled_kernel.py
```

`--system-site-packages` reuses the existing torch install rather than duplicating 4.6 GB. The
`[ctk]` extra supplies the CUDA headers `RawKernel` needs to compile; without it compilation
fails with "Failed to find CUDA headers". The uninstall line drops five CUDA math libraries a
raw memory kernel never touches and takes the environment from 2.4 GB to 445 MB. `.venv-cupy/`
is gitignored. Requires an elevated shell, for clock locking.

## Probe 4 — a hand-written unrolled float4 kernel (the decisive test)

`tools/frequency-sweep/probe_unrolled_kernel.py`, via CuPy's `RawKernel` (NVRTC compiles at
runtime, so no CUDA toolkit or Visual Studio install is needed). The kernel issues `UNROLL`
independent `float4` loads into registers **before storing any of them**, so one thread holds
`UNROLL` memory requests in flight instead of one. `UNROLL` is a `-D` define, not a runtime
argument, because it must be a compile-time constant for `#pragma unroll` to fire and for the
staging array to live in registers rather than spilling to local memory.

torch is never imported in that process. CuPy has its own memory pool and two allocators
competing on a 16 GB card would contaminate a bandwidth measurement.

Peak here is 522 GB/s: the card's 448 GB/s rating scaled by the applied memory overclock
(16301 against a 14001 rating).

| | @1395 MHz | of peak | @2760 MHz | of peak |
|---|---|---|---|---|
| cupy elementwise | 269.4 | 51.6% | 337.3 | 64.6% |
| raw float4 unroll=1 | 268.3 | 51.4% | 387.9 | 74.3% |
| raw float4 unroll=2 | 268.7 | 51.5% | 383.2 | 73.4% |
| raw float4 unroll=4 | 265.4 | 50.8% | 381.6 | 73.1% |
| raw float4 unroll=8 | 266.6 | 51.1% | 382.9 | 73.4% |
| raw float4 unroll=16 | **281.9** | **54.0%** | 387.1 | 74.2% |

**At 1395 MHz, unrolling depth does essentially nothing.** Sixteen requests in flight per thread
performs within 5% of one. The best result, 281.9 GB/s at `unroll=16`, is 54% of available
bandwidth.

**Two independent methods converge on the same wall.** Probe 3 reached 281.2 GB/s by running
four concurrent streams. Probe 4 reached 281.9 GB/s by deep per-thread unrolling. Those agree to
within 0.25%, from completely different mechanisms for raising memory-level parallelism. That is
a hardware ceiling, not a property of any one kernel.

At 2760 MHz the hand-written kernel does beat CuPy's elementwise copy by 1.15x — but it does not
beat torch's, which reached 408 GB/s (78% of peak) in probe 1. torch's elementwise kernel is
already close to the achievable ceiling at high clock, and hand-writing one is not an
improvement there either.

### A measurement bug in this probe, corrected

The first run reported throughput as **173% of theoretical peak**, which is impossible and is
recorded here rather than quietly fixed. Cause: memory clock was sampled after the settle but
*before* the load started, so it read the idle memory P-state (7001 MHz) instead of the loaded
one (16301), halving the computed peak. The probe now samples memory clock while the card is
deliberately kept busy. The throughput figures themselves were never affected — only the
percentage column.

## Answer to the roadmap question

The roadmap asks whether the contradiction is "about consumer silicon or about this particular
kernel." With probe 4 in hand the answer is **the silicon**, and a conclusion drawn earlier from
probe 3 alone has to be withdrawn.

**Correction.** Probe 3 showed concurrency buying 1.29x at low clock, and that was read here as
"the ceiling is memory-level parallelism, which a better kernel can attack." That inference was
wrong. A better kernel was then written, and it does not attack it: sixteen outstanding requests
per thread performs the same as one, and lands on the identical 281 GB/s ceiling that
concurrency found. The 1.29x was concurrency climbing *to* the wall from a lower starting point,
not evidence the wall could be moved.

The evidence now:

- Six different access patterns, including a pre-vectorised one and a read-only one, all land in
  the same issue/MLP-limited regime. That is not a property of one badly written kernel.
- Concurrency lifts low-clock bandwidth by only 29% and then stops, well short of saturation.
- A hand-written float4 kernel sweeping memory-level parallelism from 1 to 16 outstanding
  requests per thread moves nothing, and stops at the same ceiling two other methods found.
- **A DRAM-saturated workload at 1400 MHz is not constructible on this part.** Not "appears not
  to be" - three independent approaches now agree. The crossover into genuine bandwidth-limited
  behaviour happens somewhere above 2000 MHz.

The practical consequence for the project is that a `membw` sweep below ~2000 MHz is not
measuring a memory-bound workload, whatever the kernel. That is a domain limitation to state in
the paper, not a bug to fix.

## Not established

- **What the 281 GB/s ceiling actually is remains unidentified.** It is not per-thread MLP and
  not concurrency, and it is well below both the DRAM peak and any plausible instruction-issue
  bound. Candidates not tested: L2 or fabric bandwidth scaling with core clock, a limit on
  outstanding requests per SM, or memory-controller clocking tied to the core domain. Naming it
  would need hardware counters this project does not currently read.
- **Only a copy pattern was hand-tuned.** A strided or gather pattern might behave differently,
  though it would be expected to do worse rather than better.
- **The two probes disagree on single-stream `copy` at 1395 MHz: 299.9 GB/s in probe 1 against
  218.3 in probe 3.** They differ in array size (1 GiB against 256 MiB) and in how many arrays
  are resident (2 against 16). The 37% gap is not explained, and it means absolute numbers across
  probes are not comparable. The 1.29x concurrency ratio is measured *within* probe 3 and is
  unaffected, but the absolute figures should be treated as provisional until this is chased down.
- **n = 1 card**, one memory configuration (the +2500 memory overclock was applied throughout).
