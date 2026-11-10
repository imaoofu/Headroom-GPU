# Probes

One-off diagnostic experiments that answer a specific question about whether a *measurement* is
sound, rather than collecting dataset rows. Kept because a threat to validity that was checked and
dismissed is worth as much as one that was found — and because a reader has no way to tell the two
apart unless the check is on record.

## Runs

### `20260817-204900_5060ti-launch-bound.json` — is `membw` limited by kernel launch rate?

**Answer: no.** Produced by `tools/frequency-sweep/probe_launch_bound.py --rounds 3`.

**The question.** Sweep points reported GPU utilisation below 100% even after subtracting the known
`nvidia-smi` monitoring cost, and the residual looked like it grew with clock — 0.9% at 1200 MHz,
5.5% at 1897 MHz, 7.5% at 2754 MHz. If the CPU were failing to feed the GPU as kernels shortened,
high-clock throughput would be suppressed, high-clock efficiency understated, and `membw`'s measured
optimum biased downward. That would be a defect in the §5.4.1 result.

**Design.** Total bytes moved held constant while bytes-per-kernel varied over a 32× range, so the
launch count varies from 320 to 10240 while the work does not. Launch overhead is a fixed cost per
launch, so a launch-limited workload must speed up as kernels grow. Then the same kernel sequence
replayed from a CUDA graph, which removes nearly all per-launch CPU work — a comparison of a kernel
size against *itself*, so cache behaviour is identical on both sides.

**Result**, at 2992 MHz sustained, 3 interleaved rounds with order reversed on alternate rounds:

| elements/kernel | launches | ms/kernel | GB/s | CPU submit | util |
|---|---|---|---|---|---|
| 16 M | 10240 | 0.482 | 417.6 | 90.1% | 99.0% |
| 32 M | 5120 | 0.966 | 416.8 | 80.4% | 99.0% |
| 128 M | 1280 | 3.862 | 417.0 | 20.5% | 99.0% |
| 256 M | 640 | 7.754 | 415.4 | 0.1% | 99.0% |
| 512 M | 320 | 15.511 | 415.3 | 0.0% | 99.0% |

Total spread **0.5%** across a 32× change in kernel size, and it runs the *wrong way* for the
hypothesis — the smallest kernels are marginally fastest. CUDA graph replay moved throughput
**−0.1%** at both 16 M and 256 M.

**The interesting part is the `CPU submit` column.** At 16 M elements the CPU spent **90% of wall
time** inside the launch path and still did not limit anything: it stays ahead of the GPU right up
until it doesn't, and 90% occupancy is not 100%. A high CPU cost is not the same finding as a CPU
bottleneck, and this run separates them. The sweep's own configuration (256 M elements, 7.75 ms
kernels) sits at 0.1% submit — three orders of magnitude of headroom.

**Conclusion.** The sub-100% utilisation in the sweeps is a telemetry artifact, not lost work.
Corroborated independently by the fine sweep's own counterbalanced passes: at 1897 MHz the two
passes recorded utilisation of 99.0% and 92.7% while both measured **342.3 GB/s** — a 6.3-point
utilisation difference with no throughput difference at all. `utilization.gpu` over ~25 samples is
too coarse to carry an argument about lost work. See §5.4.3.

**Caveats.** Clocks were not locked — that needs elevation — so conditions were interleaved with
reversed ordering and the achieved clock was windowed per condition from a separate sampler process.
Measured clock spread across conditions was 0 MHz, and the script refuses to report a verdict if it
exceeds 60 MHz. This tests the shipped `membw` kernel at maximum clock only; it does not speak to
the separate open question of building a genuinely bandwidth-saturated kernel.
