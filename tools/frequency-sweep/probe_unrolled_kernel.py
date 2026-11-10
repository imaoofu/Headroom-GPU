"""
Can a hand-tuned kernel saturate DRAM at a low core clock, where torch's cannot?

THE QUESTION
    Six torch access patterns were all issue/MLP-limited at 1400 MHz, and concurrency across
    streams bought only 1.29x before plateauing at roughly 54% of available bandwidth. That
    plateau is either (a) a hardware wall no kernel can pass, or (b) an artifact of torch's
    elementwise kernels keeping too few memory requests in flight per thread.

    This distinguishes them. The kernel below issues UNROLL independent float4 loads into
    registers BEFORE storing any of them, so a single thread holds UNROLL outstanding memory
    requests instead of one. Sweeping UNROLL directly sweeps memory-level parallelism with
    everything else held constant.

WHY CUPY AND NOT TORCH
    torch is never imported here. CuPy has its own memory pool, entirely separate from torch's
    caching allocator, and on a 16 GB card two pools competing would contaminate a bandwidth
    measurement. Keeping the process CuPy-only removes that variable. The comparison against
    torch is made indirectly, through CuPy's own elementwise copy, which plays the same role.

REQUIRES an elevated shell.
"""

import ctypes
import json
import pathlib
import subprocess
import sys
import time

import cupy as cp

LOW_MHZ = 1400
HIGH_MHZ = 2800
BYTES_PER_ARRAY = 1024 * 1024 * 1024
FLOAT4_COUNT = BYTES_PER_ARRAY // 16
UNROLL_LEVELS = (1, 2, 4, 8, 16)
BLOCK = 256
ITERATIONS = 40
SETTLE_SECONDS = 6
RATED_GBS_AT_14001 = 448.0

KERNEL = r"""
extern "C" __global__
void copyUnrolled(const float4* __restrict__ source,
                  float4* __restrict__ destination,
                  long long count)
{
    const long long stride = (long long)gridDim.x * blockDim.x;
    const long long start  = (long long)blockIdx.x * blockDim.x + threadIdx.x;

    for (long long base = start; base < count; base += stride * UNROLL) {
        float4 staged[UNROLL];
        // All UNROLL loads are issued before any of them is consumed, so this thread holds
        // UNROLL memory requests in flight rather than one. That is the whole experiment.
        #pragma unroll
        for (int u = 0; u < UNROLL; ++u) {
            const long long index = base + (long long)u * stride;
            if (index < count) staged[u] = source[index];
        }
        #pragma unroll
        for (int u = 0; u < UNROLL; ++u) {
            const long long index = base + (long long)u * stride;
            if (index < count) destination[index] = staged[u];
        }
    }
}
"""


def isElevated():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def smi(*args):
    return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True)


def memoryClockMhz(underLoad):
    """Memory clock MUST be sampled while the GPU is loaded.

    Read at idle it returns the low-power memory P-state - 7001 MHz on this card against
    16301 under load - and the resulting "theoretical peak" is under half the real one. The
    first run of this probe did exactly that and reported throughput as 173% of peak, which
    is the kind of number that should stop a reader rather than be explained away.
    """
    underLoad()
    out = smi("--query-gpu=clocks.current.memory", "--format=csv,noheader,nounits").stdout
    cp.cuda.Stream.null.synchronize()
    return float(out.strip().splitlines()[0])


def build(unroll):
    """Compile one specialisation.

    UNROLL is a -D define rather than a runtime argument because it must be a compile-time
    constant for #pragma unroll to do anything and for staged[] to live in registers. A
    runtime value would spill it to local memory and destroy the effect being measured.
    """
    module = cp.RawModule(code=KERNEL, options=("-DUNROLL=%d" % unroll,))
    return module.get_function("copyUnrolled")


def timeKernel(fn, movedBytes):
    for _ in range(5):
        fn()
    cp.cuda.Stream.null.synchronize()
    started = time.perf_counter()
    for _ in range(ITERATIONS):
        fn()
    cp.cuda.Stream.null.synchronize()
    elapsed = time.perf_counter() - started
    return movedBytes * ITERATIONS / elapsed / 1e9


def main():
    if not isElevated():
        print("REFUSING TO START: not elevated. Clock locking needs administrator rights.")
        return 1

    source = cp.ones(FLOAT4_COUNT * 4, dtype=cp.float32)
    destination = cp.empty_like(source)
    moved = BYTES_PER_ARRAY * 2

    kernels = {}
    for unroll in UNROLL_LEVELS:
        kernels[unroll] = build(unroll)
    print(f"compiled unroll levels: {list(kernels)}")

    grid = (FLOAT4_COUNT + BLOCK - 1) // BLOCK
    grid = min(grid, 65535 * 4)

    results = {}
    try:
        for target in (LOW_MHZ, HIGH_MHZ):
            locked = smi("-lgc", str(target))
            if locked.returncode != 0:
                print(f"could not lock to {target}: {locked.stderr.strip()}")
                return 1
            time.sleep(SETTLE_SECONDS)
            achieved = float(smi("--query-gpu=clocks.sm", "--format=csv,noheader,nounits")
                             .stdout.strip().splitlines()[0])
            # Keep the card busy across the sample so the memory P-state is the loaded one.
            memClock = memoryClockMhz(
                lambda: [cp.copyto(destination, source) for _ in range(30)])
            peak = RATED_GBS_AT_14001 * memClock / 14001.0
            print(f"\n--- {target} MHz (achieved {achieved:.0f}), memory {memClock:.0f} MHz, "
                  f"theoretical peak {peak:.0f} GB/s")

            baseline = timeKernel(lambda: cp.copyto(destination, source), moved)
            print(f"    {'cupy elementwise':<22} {baseline:>7.1f} GB/s  ({baseline/peak:>5.1%} of peak)")
            row = {"achieved_mhz": achieved, "memory_mhz": memClock, "peak_gbs": peak,
                   "elementwise": baseline, "unrolled": {}}

            for unroll in UNROLL_LEVELS:
                kernel = kernels[unroll]
                gbs = timeKernel(
                    lambda k=kernel: k((grid,), (BLOCK,), (source, destination, FLOAT4_COUNT)),
                    moved)
                row["unrolled"][unroll] = gbs
                print(f"    {'raw float4 unroll=' + str(unroll):<22} {gbs:>7.1f} GB/s  "
                      f"({gbs/peak:>5.1%} of peak)")
            results[target] = row
    finally:
        smi("-rgc")
        print("\n[clocks reset]")

    low = results[LOW_MHZ]
    best = max(low["unrolled"].values())
    bestUnroll = max(low["unrolled"], key=low["unrolled"].get)
    print(f"\nAT {LOW_MHZ} MHz:")
    print(f"  cupy elementwise : {low['elementwise']:.1f} GB/s ({low['elementwise']/low['peak_gbs']:.1%} of peak)")
    print(f"  best unrolled    : {best:.1f} GB/s at unroll={bestUnroll} "
          f"({best/low['peak_gbs']:.1%} of peak)")
    print(f"  gain from unrolling: {best/low['elementwise']:.2f}x")
    if best / low["peak_gbs"] > 0.85:
        print("\n  A hand-tuned kernel DOES saturate DRAM at this clock. The roadmap item is")
        print("  achievable and membw should be replaced with this kernel.")
    elif best / low["elementwise"] > 1.15:
        print("\n  Unrolling helps materially but does not saturate. MLP is a real lever with a")
        print("  ceiling above it - report the improved figure and the remaining gap.")
    else:
        print("\n  Unrolling does not help. The plateau is a hardware wall, not a kernel defect,")
        print("  and no workload can be DRAM-saturated at this clock on this part.")

    out = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "probes" / "probe_unrolled_kernel_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"block": BLOCK, "grid": grid, "iterations": ITERATIONS,
                               "bytes_per_array": BYTES_PER_ARRAY,
                               "results": {str(k): v for k, v in results.items()}}, indent=2),
                   encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
