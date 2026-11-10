"""
Fixed-work GPU benchmarks, for measuring performance as a function of locked core clock.

WHY FIXED WORK
    Invoke-FrequencySweep.ps1 pins the core clock and needs a performance number at each
    frequency. A fixed-TIME stress test (OCCT, FurMark, gpu_stressor) cannot provide one -
    it runs for N seconds regardless of how fast the card is. A fixed-WORK benchmark does
    the identical amount of arithmetic every run, so wall-clock duration IS the performance
    metric, and efficiency = work / (duration x power) falls out directly.

TWO WORKLOADS, ON PURPOSE
    The V100 analysis found the efficiency-optimal frequency depends on whether a workload
    is compute-bound or memory-bound (correlation -0.666 between frequency sensitivity and
    optimal clock). Reproducing that on consumer hardware needs both kinds:

      gemm   - large matrix multiply through cuBLAS. Compute-bound; scales nearly linearly
               with core clock. Directly comparable to the "GeMM" workload in the published
               V100 dataset, which is why matmul was chosen over a homemade kernel.
      membw  - large elementwise stream over VRAM. Memory-bandwidth-bound; much LESS
               sensitive to core clock, which is the contrast that makes the comparison
               meaningful. Measured on this card: elasticity of throughput to core clock
               is ~0.35 for membw against ~1.09 for gemm over a 2.2x range. Sub-linear,
               but NOT flat - an earlier version of this comment claimed "largely
               insensitive" and the data does not support it. Below ~1200 MHz the SMs
               cannot issue requests fast enough to saturate DRAM, so the workload is
               issue-limited rather than bandwidth-limited there.

MEASUREMENT INTEGRITY
    Monitoring is not free and must not be counted as GPU work. An nvidia-smi call is a
    process spawn: measured at 42 ms each on this machine. The temperature check used to
    run every 5 iterations INSIDE the timed region, which cost 10% of gemm's reported
    duration and 50.5% of membw's - at 600 iterations that was 120 spawns, so over half
    of the "benchmark" was the GPU sitting idle waiting on a subprocess. Corrected,
    membw measures 414 GB/s against 205 GB/s before. Those runs had a +2500 memory
    overclock applied, so neither figure is a fraction of the 448 GB/s STOCK rating;
    this line said "92% of 448" until 2026-09-28. At stock memory the same benchmark
    reaches 343.7 GB/s, 77% of 448 (tools/frequency-sweep/README.md, "Correction").

    Worse than the absolute error: that cost was a fixed wall-clock offset, so it shrank
    as a fraction of the run when the sweep locked the clock lower. A frequency-dependent
    bias in the duration is a bias in the efficiency optimum, which is the one number this
    project exists to measure. Two rules follow, and both are load-bearing:

      * The check is TIME-based (--temp-check-seconds), not iteration-based, so its
        frequency does not depend on how fast the card happens to be running.
      * The wall time spent inside nvidia-smi is measured and SUBTRACTED. The preceding
        cuda.synchronize() is deliberately left inside the timed region - that is real
        queued work draining, and excluding it would undercount.

    duration_seconds is therefore work-only. wall_seconds and monitoring_overhead_seconds
    are both reported alongside it so the correction is auditable rather than assumed.

    The timed region is also stamped in Unix epoch time (timed_region_start_unix /
    _end_unix) so Invoke-FrequencySweep.ps1 can window its power samples to the benchmark's
    wall-clock region. That region includes the brief nvidia-smi monitoring pauses, which
    duration_seconds subtracts; it is not an exact active-work-only interval. Without the
    stamps, power was averaged over
    the whole process lifetime - including ~2.3 s of Python import and CUDA init at idle,
    which understated load power by 16% (124.77 W recorded against 148.52 W actual).

SAFETY
    This is ordinary arithmetic - the same work any game or training run does. It cannot
    damage hardware: a compute workload has no path to permanent damage, and the card
    enforces its own thermal and power limits underneath anything software asks for.
    Belt and braces anyway:

      * A temperature ceiling is checked periodically; it aborts cleanly if crossed.
      * Iteration count is bounded and finite. No infinite loops, no unattended running.
      * It allocates a fixed, modest fraction of VRAM and frees it on exit, including on
        error, so a failed run does not strand memory.
      * It never touches clocks, voltage, or power limits. Only the sweep script does that,
        and only via documented nvidia-smi calls.

    If this crashes the driver, that is a real finding about GPU stability at the applied
    settings - not damage. Clock locks and OC settings do not survive a reboot.

USAGE
    python gpu_workload.py --workload gemm  --json
    python gpu_workload.py --workload membw --json
    python gpu_workload.py --workload gemm --size 6144 --iterations 40 --max-temp 83
"""

import argparse
import json
import math
import subprocess
import sys
import time
from app_workloads import APP_WORKLOADS, build as buildAppWorkload


# A single matmul of size N does roughly 2*N^3 floating point operations.
FLOPS_PER_GEMM = lambda n: 2.0 * (n ** 3)

# How often to align the CPU with the GPU inside the timed loop. Measured to cost nothing
# (see the loop), and required for the temperature poll to see real progress rather than a
# CPU that has already raced to the end of the queue.
SYNC_EVERY_ITERATIONS = 5


# =====================================================================================
# THE EXTENDED SUITE
#
# WHY IT EXISTS
#     5.6.2's leave-one-workload-out result needs a workload POPULATION. gemm and membw are
#     two points, and two points cannot support a design that removes one and predicts it.
#     Subsampling the V100's 33 workloads says the constrained gap is detectable from about
#     8 and stable from about 12-16, so this suite targets that range.
#
#     The axis that matters is ARITHMETIC INTENSITY - FLOP per byte moved - because that is
#     what the V100 correlation of -0.666 is really about. Fourteen variants of matmul would
#     be fourteen workloads and one data point.
#
# TWO FAMILIES, ON PURPOSE
#     ladder/    batched matmul at a range of inner sizes. For a square fp32 matmul the
#                intensity is exactly N/6, so this family SWEEPS the axis while holding the
#                operation, the library and the access pattern constant. It isolates the
#                variable in a way a set of different operators cannot.
#     operator/  representative operations - copy, reduction, softmax, layer norm,
#                convolution, attention. These establish that any effect is not an artifact
#                of cuBLAS batched matmul specifically. They span the axis more raggedly and
#                that is the price of external validity.
#
#     Reporting a result from one family alone would be weaker than reporting both.
#
# ⚠️ THE INTENSITIES BELOW ARE DECLARED, NOT MEASURED
#     Each entry states the FLOPs and the bytes its operation must move in principle. Real
#     traffic differs: caches serve some of it, fused kernels avoid round trips, and
#     scaled_dot_product_attention may dispatch a flash implementation whose traffic is far
#     below the naive count. So treat these as the INTENDED ordering, not as measurements.
#     3.3.1 is the cautionary case - membw is declared at 0.167 FLOP/byte and is nonetheless
#     issue-limited rather than bandwidth-limited below roughly 2000 MHz. What a workload is
#     bound BY is an empirical question this file cannot answer by declaration.
#
# VRAM
#     Every entry is sized to roughly 1.2 GB of tensors so the whole suite fits on the 8 GB
#     card as well as the 16 GB one. The two chips must run the IDENTICAL suite or the
#     paired comparison they exist for does not hold.
#
# ITERATION COUNTS
#     Deliberately absent. A count that gives 9 seconds of work on one card gives something
#     else on another, and guessing them here would put arbitrary numbers into the one
#     setting that must be held constant across a sweep. Use --calibrate once per card at
#     full clock, then pass the printed count explicitly and never vary it within a sweep.
#
# FIRST EXECUTION, 2026-08-28, RTX 5060 Ti, ~8% baseline load - PROVISIONAL
#
#     APPLIED SETTINGS: the card was TUNED, not stock - memory +2500 and the core V/F curve
#     pinned flat near 3000 MHz above ~925 mV. Recorded here because the first version of this
#     block did not, and got the denominator wrong as a direct result.
#
#     ⚠️ 448 GB/s IS THE WRONG DENOMINATOR FOR THIS CARD AS CONFIGURED. That figure is the
#     14001 MHz rating. Under load the tuned card runs 16301 MHz (5.7.1), so its actual
#     ceiling is 448 * 16301/14001 = 521.6 GB/s; stock under load is 13801 MHz, i.e. 441.6.
#     nvidia-smi is no help - clocks.max.memory still reports 14001, because an Afterburner
#     offset is invisible to it, which is 5.7.6's "a memory overclock is invisible to a
#     core-clock check" in a new place.
#
#     All thirteen ran, including the two since retired. No allocation failure, and conv and
#     attention both work on Blackwell. Implied throughput against 521.6 GB/s and the card's
#     15.71-18.24 TFLOP/s fp32 range:
#
#       bandwidth-bound, 74-86% of bus   reduce, bgemm128, copy, softmax, bgemm32, bgemm64
#       compute-bound                     bgemm256, bgemm1024, conv, attention
#       NEITHER                           bgemm8, bgemm16 (retired, see LADDER_SIZES), layernorm
#
#     THE BOTTOM OF THE LADDER DID NOT MEASURE THE AXIS, which is why it is no longer in it.
#     bgemm8 reached 32.8 GB/s - 6% of the bus - and 0.04 TFLOP/s, so it was bound by
#     batched-matmul launch and occupancy overhead rather than by bandwidth or by arithmetic.
#     bgemm16 the same at 19%. That is 3.3.1 repeating: a declared intensity is not a binding
#     constraint. Retired rather than replaced - copy, membw, reduce and softmax already cover
#     that end of the axis with workloads that are genuinely on it.
#
#     What DOES work is the knee: bgemm128 sits at 79% of the bus and bgemm256 at 42%, so the
#     ladder crosses the roofline between them. That transition is the part worth having.
#
#     layernorm at 47% sits between the two groups and is undiagnosed. It is kept because it is
#     a real operator at a real intensity, not because anyone knows what bounds it.
#
#     ✅ RESOLVED: reduce read 448.4 GB/s, which was 100.1% of 448 and looked like a defect in
#     the byte accounting. It is 86% of the tuned card's actual 521.6 GB/s and entirely
#     ordinary. The measurement was right and the denominator was wrong - which is why the
#     applied settings are now recorded at the top of this block rather than assumed.
#
#     ⚠️ THE PAIRED CROSS-CHIP RUN NEEDS THIS CARD AT STOCK. The 3070 Ti is a customer machine
#     and is measured stock only, so a tuned 5060 Ti against a stock 3070 Ti compares two
#     tunings as much as two architectures. Collect the shared suite at STOCK on this card -
#     tuned as well if there is time, but stock is the leg that pairs.
#
#     Counts from that session are PROVISIONAL twice over: the protocol wants a verified-quiet
#     machine under ~5% and this was 8%, and they were taken on the tuned profile rather than
#     the stock one they will be used against. Recalibrate before collecting anything.
# =====================================================================================

# Tensors per workload, in bytes. Sized for the smaller of the two cards, not the larger.
SUITE_TARGET_BYTES = 1.2e9

# Inner matrix sizes for the ladder. fp32 intensity is N/6 FLOP/byte, so this spans roughly
# 5 to 171 and meets gemm's ~1365 at the top; copy, membw, reduce and softmax cover the bottom.
#
# 8 AND 16 WERE MEASURED AND RETIRED, 2026-08-28. They ran fine and are not broken - they just do
# not measure the axis. At stock they reached 6% and 19% of the memory bus with negligible FLOP/s,
# so both are bound by batched-matmul launch and occupancy overhead rather than by bandwidth or by
# arithmetic, and their declared intensities of 1.3 and 2.7 predict nothing about them. Collecting
# them would spend sweep time on two points that sit off the axis and then need a paragraph in the
# paper explaining why they are there.
#
# To restore them, put 8 and 16 back in this tuple. Nothing else needs changing: buildSuiteWorkload
# parses the size out of the name, so any bgemmN works. Their stock iteration counts are recorded
# in SUITE-ITERATIONS.md if they are ever wanted - 238 and 664.
LADDER_SIZES = (32, 64, 128, 256, 1024)


def suiteWorkloadNames():
    """Every extended workload, in ascending declared arithmetic intensity."""
    return [f"bgemm{n}" for n in LADDER_SIZES] + [
        "copy", "reduce", "softmax", "layernorm", "conv", "attention",
    ]


# Fixed shape parameters, named once so the analytic intensity below and the builders that
# allocate the tensors cannot disagree about them.
SOFTMAX_FLOPS_PER_ELEMENT = 5.0
LAYERNORM_FLOPS_PER_ELEMENT = 8.0
CONV_CHANNELS = 128
CONV_KERNEL = 3
ATTENTION_HEAD_DIM = 64
ATTENTION_HEADS = 16
ATTENTION_DEFAULT_SEQUENCE = 1024


def suiteDeclaredIntensity(name, elementBytes=4):
    """
    Arithmetic intensity in FLOP per byte, from operation counts alone. No GPU, no allocation.

    This exists so the table printed by --list-workloads is COMPUTED rather than typed. The first
    draft of that table hand-wrote six operator intensities and three of them were wrong - conv by
    a factor of two, softmax and layernorm by four - which is the drift this project keeps finding
    in hand-maintained restatements of something the code already knows.

    The GPU-side builders derive their own figures independently from the tensors they actually
    allocate; test_gpu_workload.py asserts the two agree, so a shape changed in one place and not
    the other fails rather than quietly reporting the old number.
    """
    if name.startswith("bgemm"):
        inner = int(name[len("bgemm"):])
        # 2N^3 FLOP against 3N^2 elements of traffic.
        return (2.0 * inner) / (3.0 * elementBytes)
    if name == "copy":
        return 0.0
    if name == "reduce":
        return 1.0 / elementBytes
    if name == "softmax":
        return SOFTMAX_FLOPS_PER_ELEMENT / (2.0 * elementBytes)
    if name == "layernorm":
        return LAYERNORM_FLOPS_PER_ELEMENT / (2.0 * elementBytes)
    if name == "conv":
        # Per output element: 2*C*R*S FLOP against one read and one write, so 2 elements of
        # traffic. The 2s cancel. Weights are negligible and excluded, which makes this a
        # slight OVER-estimate. Do not reintroduce a /2 here - that was the original error.
        return (CONV_KERNEL * CONV_KERNEL * CONV_CHANNELS) / float(elementBytes)
    if name == "attention":
        return ATTENTION_DEFAULT_SEQUENCE / float(elementBytes)
    raise ValueError(f"unknown workload {name!r}")


def buildSuiteWorkload(name, size, torchDtype, elementBytes, device, torch):
    """
    Construct one extended workload.

    Returns (step, flopsPerIteration, bytesPerIteration, resolvedSize). `step` closes over its
    own tensors, exactly as the gemm and membw branches do, so the timed loop is unchanged.

    `size` carries a different meaning per workload and each default is stated in the table
    printed by --list-workloads. 0 selects the default.
    """
    functional = torch.nn.functional

    if name.startswith("bgemm"):
        inner = int(name[len("bgemm"):])
        # Batch chosen so the three tensors land near the VRAM target. At least one, so a
        # very large inner size degenerates to a single un-batched matmul rather than zero.
        batch = max(1, int(SUITE_TARGET_BYTES / (3.0 * inner * inner * elementBytes)))
        left = torch.randn((batch, inner, inner), device=device, dtype=torchDtype)
        right = torch.randn((batch, inner, inner), device=device, dtype=torchDtype)
        flops = 2.0 * batch * (inner ** 3)
        moved = 3.0 * batch * (inner ** 2) * elementBytes

        def step():
            torch.bmm(left, right)

        return step, flops, moved, inner

    if name == "copy":
        count = size if size > 0 else int(SUITE_TARGET_BYTES / (2 * elementBytes))
        source = torch.randn(count, device=device, dtype=torchDtype)
        destination = torch.empty(count, device=device, dtype=torchDtype)
        # No arithmetic at all. This is the zero-intensity end of the axis, and its
        # throughput is reported in bytes for that reason.
        def step():
            destination.copy_(source)

        return step, 0.0, 2.0 * count * elementBytes, count

    if name == "reduce":
        count = size if size > 0 else int(SUITE_TARGET_BYTES / elementBytes)
        source = torch.randn(count, device=device, dtype=torchDtype)

        def step():
            torch.sum(source)

        # One add per element, one read per element. Intensity is 1/elementBytes.
        return step, float(count), float(count) * elementBytes, count

    if name == "softmax":
        rows = 8192
        columns = size if size > 0 else int(SUITE_TARGET_BYTES / (2 * rows * elementBytes))
        source = torch.randn((rows, columns), device=device, dtype=torchDtype)

        def step():
            torch.softmax(source, dim=-1)

        # ~5 operations per element (max, subtract, exp, sum, divide). The byte count is the
        # MINIMUM traffic - one read, one write - so the intensity is an upper bound; a
        # two-pass implementation reads twice and the true figure is lower.
        return step, 5.0 * rows * columns, 2.0 * rows * columns * elementBytes, columns

    if name == "layernorm":
        rows = 8192
        columns = size if size > 0 else int(SUITE_TARGET_BYTES / (2 * rows * elementBytes))
        source = torch.randn((rows, columns), device=device, dtype=torchDtype)
        weight = torch.ones(columns, device=device, dtype=torchDtype)
        bias = torch.zeros(columns, device=device, dtype=torchDtype)

        def step():
            functional.layer_norm(source, (columns,), weight, bias)

        return step, 8.0 * rows * columns, 2.0 * rows * columns * elementBytes, columns

    if name == "conv":
        # Channels-last is what cuDNN actually wants; leaving it contiguous measures a layout
        # conversion as much as a convolution.
        channels = 128
        spatial = size if size > 0 else 128
        batch = max(1, int(SUITE_TARGET_BYTES / (2.0 * channels * spatial * spatial * elementBytes)))
        source = torch.randn((batch, channels, spatial, spatial),
                             device=device, dtype=torchDtype).to(memory_format=torch.channels_last)
        weight = torch.randn((channels, channels, 3, 3),
                             device=device, dtype=torchDtype).to(memory_format=torch.channels_last)

        def step():
            functional.conv2d(source, weight, padding=1)

        flops = 2.0 * batch * channels * channels * 9 * spatial * spatial
        moved = (2.0 * batch * channels * spatial * spatial * elementBytes
                 + channels * channels * 9 * elementBytes)
        return step, flops, moved, spatial

    if name == "attention":
        heads = 16
        headDim = 64
        sequence = size if size > 0 else 1024
        perTensor = 3.0 * heads * sequence * headDim * elementBytes
        batch = max(1, int(SUITE_TARGET_BYTES / max(perTensor, 1.0)))
        shape = (batch, heads, sequence, headDim)
        query = torch.randn(shape, device=device, dtype=torchDtype)
        key = torch.randn(shape, device=device, dtype=torchDtype)
        value = torch.randn(shape, device=device, dtype=torchDtype)

        def step():
            functional.scaled_dot_product_attention(query, key, value)

        # Two matmuls of sequence x sequence x headDim. The naive byte count assumes q, k, v
        # in and one tensor out; a flash implementation moves far less than this, which would
        # make the true intensity HIGHER than declared.
        flops = 4.0 * batch * heads * (sequence ** 2) * headDim
        moved = 4.0 * batch * heads * sequence * headDim * elementBytes
        return step, flops, moved, sequence

    raise ValueError(f"unknown workload {name!r}")


def readGpuTemperature():
    """Read GPU temperature via nvidia-smi. Returns None if unavailable."""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True, text=True, timeout=10,
        )
        if output.returncode != 0:
            return None
        return float(output.stdout.strip().splitlines()[0])
    except Exception:
        return None


def openEnergyCounter(pciBusId=None, supportLog=None):
    """NVML's cumulative board-energy counter, as a zero-argument reader returning millijoules.

    Read through ctypes from the NVML library the driver ships, so the benchmark needs no package.
    It READS a counter and changes nothing. Returns None, never raises, when NVML or the counter is
    unavailable, so a card without it still benchmarks; the payload then says so.

    Why it is here: every power figure in this project is nvidia-smi's power reading sampled at
    2 Hz and averaged over the timed window. That reading is the card's own smoothed estimate
    (Yang et al. 2024), and nothing here had checked it. The counter integrates energy on the device
    instead of being sampled, so energy over the window divided by its length is an independent
    average power to compare against. Measured on the RTX 5060 Ti on 2026-10-06, the counter ticks
    about every 100 ms, so each end of a window is uncertain by up to ~0.1 s of power.

    The device is matched by PCI address when CUDA reports one, because CUDA's and NVML's device
    orderings can differ on a multi-GPU machine. Without an address it is used only when exactly
    one device exists; a guess would put the wrong card's energy beside this card's throughput.
    """
    import ctypes
    try:
        if sys.platform == "win32":
            nvml = ctypes.WinDLL("nvml.dll")
        else:
            nvml = ctypes.CDLL("libnvidia-ml.so.1")
        if nvml.nvmlInit_v2() != 0:
            return None
        handle = ctypes.c_void_p()
        if pciBusId:
            found = nvml.nvmlDeviceGetHandleByPciBusId_v2(pciBusId.encode(), ctypes.byref(handle))
        else:
            count = ctypes.c_uint()
            if nvml.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0 or count.value != 1:
                return None
            found = nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle))
        if found != 0:
            return None
        value = ctypes.c_ulonglong()

        def read():
            if nvml.nvmlDeviceGetTotalEnergyConsumption(handle, ctypes.byref(value)) != 0:
                return None
            return value.value

        if supportLog is None:
            return read if read() is not None else None
        # Section 20b (--endpoint-detail): the same single support read, bracketed and recorded,
        # including a failed one. The default path above is unchanged.
        first, record = bracketedCall(read)
        supportLog.append(dict(record, value_mj=first, ok=first is not None))
        return read if first is not None else None
    except Exception:
        return None


def openClockReader(pciBusId=None):
    """SM and memory clocks through NVML, as a zero-argument reader returning (sm_mhz, mem_mhz).

    Section 20b only (--endpoint-detail): a boundary witness taken just outside the timed region, so
    that the endpoint-only arm, which polls nothing during the window, still records the clock it ran
    at. It reads clocks and changes nothing. Device matching as openEnergyCounter. None when
    unavailable; a failed read returns (None, None).
    """
    import ctypes
    try:
        nvml = ctypes.WinDLL("nvml.dll") if sys.platform == "win32" else ctypes.CDLL("libnvidia-ml.so.1")
        if nvml.nvmlInit_v2() != 0:
            return None
        handle = ctypes.c_void_p()
        if pciBusId:
            found = nvml.nvmlDeviceGetHandleByPciBusId_v2(pciBusId.encode(), ctypes.byref(handle))
        else:
            count = ctypes.c_uint()
            if nvml.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0 or count.value != 1:
                return None
            found = nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle))
        if found != 0:
            return None
        value = ctypes.c_uint()

        def clock(kind):  # NVML_CLOCK_SM = 1, NVML_CLOCK_MEM = 2
            return value.value if nvml.nvmlDeviceGetClockInfo(handle, kind, ctypes.byref(value)) == 0 else None

        return lambda: (clock(1), clock(2))
    except Exception:
        return None


def bracketedCall(function):
    """Call function() and return (result, record) with Unix and perf_counter times either side.

    perf_counter is QueryPerformanceCounter on Windows, one clock for every process, so a reader in
    another process can be aligned to these brackets. Section 20b's duration T is the difference of
    two call midpoints on this clock.
    """
    unixBefore, monoBefore = time.time(), time.perf_counter()
    result = function()
    monoAfter, unixAfter = time.perf_counter(), time.time()
    return result, {"unix_before": unixBefore, "unix_after": unixAfter,
                    "mono_before": monoBefore, "mono_after": monoAfter,
                    "latency_s": monoAfter - monoBefore}


def buildArgumentParser():
    parser = argparse.ArgumentParser(
        description="Fixed-work GPU benchmark for frequency sweeps.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--workload", choices=["gemm", "membw"] + suiteWorkloadNames() + list(APP_WORKLOADS),
                        default="gemm",
                        help="gemm = compute-bound matmul; membw = memory-bandwidth-bound stream. "
                             "The rest are the extended suite - run --list-workloads for the table.")
    parser.add_argument("--list-workloads", action="store_true",
                        help="Print every workload with its declared arithmetic intensity and exit. "
                             "Needs no GPU.")
    parser.add_argument("--calibrate", action="store_true",
                        help="Time a short run and print the iteration count that would give "
                             "--target-seconds of work, then exit without benchmarking. Run this ONCE "
                             "per card at full clock, then pass the printed count explicitly: the "
                             "count must not vary within a sweep.")
    parser.add_argument("--target-seconds", type=float, default=9.0,
                        help="Work duration --calibrate aims for. Long enough that the card reaches "
                             "a steady clock and launch overhead stops being visible.")
    parser.add_argument("--size", type=int, default=0,
                        help="Matrix dimension for gemm, or element count for membw. 0 picks a sensible default.")
    parser.add_argument("--iterations", type=int, default=0,
                        help="Timed iterations. 0 picks a per-workload default sized for ~8-9s of GPU "
                             "work at full clock. MUST be held constant across every frequency in a sweep - "
                             "varying it breaks the fixed-work property that makes duration a valid "
                             "performance metric.")
    parser.add_argument("--warmup", type=int, default=5,
                        help="Untimed iterations first, so clocks and caches settle before measurement.")
    parser.add_argument("--max-temp", type=float, default=88.0,
                        help="Abort if GPU temperature reaches this (Celsius).")
    parser.add_argument("--temp-check-seconds", type=float, default=2.0,
                        help="How often to poll temperature during the run. Time-based on purpose: "
                             "an iteration-based cadence polls more often on a fast card than a slow "
                             "one, which puts a frequency-dependent bias in the measured duration.")
    parser.add_argument("--dtype", choices=["fp32", "fp16"], default="fp32",
                        help="fp32 is the conservative default and stresses the general pipeline.")
    parser.add_argument("--allow-tf32", action="store_true",
                        help="Permit TF32 tensor cores for fp32 convolution and matmul. OFF by "
                             "default here, unlike PyTorch, which enables it for convolution and "
                             "not for matmul - that asymmetry makes conv incomparable with every "
                             "other workload in the suite. Turn it on deliberately or not at all.")
    parser.add_argument("--json", action="store_true",
                        help="Emit a single JSON object on stdout (for the sweep script to parse).")
    parser.add_argument("--preload-seconds", type=float, default=0.0,
                        help="After the warm-up, run the same kernel for this long (synchronized every "
                             "iteration, untimed) before the timed region. 0 keeps the historical "
                             "behaviour. Section 20b uses 1.0.")
    parser.add_argument("--endpoint-detail", action="store_true",
                        help="Section 20b: bracket both energy-counter calls with Unix and perf_counter "
                             "timestamps, read the SM and memory clocks through NVML just outside the "
                             "timed region, log every temperature read, and report all of it under "
                             "endpoint_detail. Off by default, so no other run makes these extra calls.")
    parser.add_argument("--input-seed", type=int, default=None,
                        help="Seed torch's generator before the input tensors are drawn, so every run "
                             "draws the same inputs (the repeatability study, registered 2026-10-14). "
                             "Freezes input values, not floating-point execution order. Off by default, "
                             "so every other protocol keeps its historical unseeded inputs.")
    return parser


def emit(payload, asJson, humanLines):
    if asJson:
        print(json.dumps(payload))
    else:
        for line in humanLines:
            print(line)


def describeSuite(elementBytes=4):
    """The suite as text, computed from the same constants the builders use.

    Written from the declarations rather than from a hand-maintained table, so it cannot drift
    away from what the code actually allocates.
    """
    lines = [
        "[WORKLOAD] Extended suite. Intensities are DECLARED from operation counts, not measured -",
        "[WORKLOAD] see the header. fp32 assumed below; fp16 halves the bytes and doubles each figure.",
        "",
        f"    {'workload':<12} {'family':<9} {'FLOP/byte':>10}  size parameter",
    ]
    parameters = {
        "copy": "element count",
        "reduce": "element count",
        "softmax": "columns, 8192 rows",
        "layernorm": "columns, 8192 rows",
        "conv": f"spatial dimension, {CONV_CHANNELS} channels, {CONV_KERNEL}x{CONV_KERNEL}",
        "attention": f"sequence length, {ATTENTION_HEADS} heads, head dim {ATTENTION_HEAD_DIM}",
    }
    for name in suiteWorkloadNames():
        family = "ladder" if name.startswith("bgemm") else "operator"
        parameter = parameters.get(name, f"inner matrix dimension, fixed at {name[len('bgemm'):]}")
        lines.append(f"    {name:<12} {family:<9} "
                     f"{suiteDeclaredIntensity(name, elementBytes):>10.3f}  {parameter}")
    lines += [
        f"    {'membw':<12} {'existing':<9} {0.167:>10.3f}  element count",
        f"    {'gemm':<12} {'existing':<9} {1365.0:>10.1f}  matrix dimension",
        "",
        "[WORKLOAD] gemm and membw are unchanged and remain comparable with every sweep already",
        "[WORKLOAD] committed. The suite ran and was calibrated at stock on 2026-08-28 - counts and",
        "[WORKLOAD] conditions are in SUITE-ITERATIONS.md. No suite sweep has been collected yet.",
    ]
    return lines


def main():
    args = buildArgumentParser().parse_args()

    if args.list_workloads:
        for line in describeSuite():
            print(line)
        return 0

    try:
        import torch
    except ImportError:
        emit({"ok": False, "error": "torch_not_installed"}, args.json,
             ["[WORKLOAD] PyTorch is not installed.",
              "[WORKLOAD] Install with: pip install torch --index-url https://download.pytorch.org/whl/cu128"])
        return 4

    if not torch.cuda.is_available():
        emit({"ok": False, "error": "cuda_unavailable"}, args.json,
             ["[WORKLOAD] PyTorch is installed but reports no CUDA device.",
              "[WORKLOAD] A CPU-only build cannot benchmark the GPU. Reinstall with the cu128 index URL."])
        return 5

    device = torch.device("cuda:0")
    deviceName = torch.cuda.get_device_name(0)
    props = torch.cuda.get_device_properties(0)
    pciBusId = None
    if getattr(props, "pci_bus_id", None) is not None:
        pciBusId = (f"{props.pci_domain_id:08x}:{props.pci_bus_id:02x}:"
                    f"{props.pci_device_id:02x}.0")
    energySupportLog = [] if args.endpoint_detail else None
    readEnergy = openEnergyCounter(pciBusId, energySupportLog)
    energyStartMj = energyEndMj = None
    energyStartWall = energyEndWall = None
    # Section 20b (--endpoint-detail). Everything here is recorded beside the historical fields and
    # changes none of them; without the flag none of these calls is made.
    detail = bool(args.endpoint_detail)
    readClocks = openClockReader(pciBusId) if detail else None
    temperatureLog = []
    endpointStart = endpointEnd = None
    clocksBeforeStart = clocksAfterEnd = None
    clocksBeforeCall = clocksAfterCall = None
    workMonoStart = workMonoEnd = None
    preloadSeconds = 0.0
    preloadIterations = 0

    def readTemperature():
        if not detail:
            return readGpuTemperature()
        value, record = bracketedCall(readGpuTemperature)
        record["value_c"] = value
        temperatureLog.append(record)
        # Fail closed (GPT Job 73, F3): in this mode a failed read must never silently disable the
        # thermal ceiling, as it does on the historical path.
        if value is None or not math.isfinite(value):
            raise RuntimeError("section20b_temperature_read_failed")
        return value
    torchDtype = torch.float32 if args.dtype == "fp32" else torch.float16

    # PRECISION PARITY, and it is not cosmetic.
    #
    # PyTorch ships these two defaults DIFFERENT: cudnn.allow_tf32 is True and
    # matmul.allow_tf32 is False. So a convolution silently runs on TF32 tensor cores while
    # every matmul runs true fp32 - different arithmetic, in a suite whose entire purpose is
    # comparing workloads to each other.
    #
    # Measured on the 5060 Ti before this was set: conv reported 19.89 TFLOP/s, ABOVE the
    # 15.71-18.24 TFLOP/s gemm has ever reached on the same card. A workload cannot exceed the
    # card's fp32 ceiling by doing fp32, and that impossibility is what exposed it.
    #
    # Forcing both off makes the suite internally comparable. It does NOT change gemm or membw:
    # matmul.allow_tf32 was already False by default, and membw is elementwise. --allow-tf32
    # restores the faster path for anyone who wants it, deliberately and on the record.
    torch.backends.cudnn.allow_tf32 = bool(args.allow_tf32)
    torch.backends.cuda.matmul.allow_tf32 = bool(args.allow_tf32)

    try:
        startTemp = readTemperature()
    except RuntimeError as error:
        emit({"ok": False, "error": str(error), "temperature_reads": temperatureLog}, args.json,
             [f"[WORKLOAD] {error}: refusing to start without a temperature reading."])
        return 9
    if startTemp is not None and startTemp >= args.max_temp:
        emit({"ok": False, "error": "already_too_hot", "temperature_c": startTemp}, args.json,
             [f"[WORKLOAD] GPU is already at {startTemp} C, at or above the {args.max_temp} C ceiling. Refusing to start."])
        return 6

    # Defaults chosen to be heavy enough to saturate the GPU but well inside VRAM on any
    # modern card. gemm at 8192 fp32 is ~768 MB of tensors; membw at 256M floats is ~3 GB.
    isSuite = args.workload not in ("gemm", "membw")

    size = args.size
    if size <= 0 and not isSuite:
        size = 8192 if args.workload == "gemm" else 256 * 1024 * 1024

    # Iteration defaults target roughly 8-9 seconds of ACTUAL GPU WORK at full boost clock,
    # measured on an RTX 5060 Ti: gemm at 120 iterations takes 7.5-8.4 s, membw at 1200
    # takes ~9.3 s. Short runs are actively misleading here - the card needs time to reach a
    # steady clock and thermal state, and launch overhead stays visible in the throughput
    # figure otherwise.
    #
    # membw's default was 600 while monitoring overhead was still inside the timer, which
    # made it look like a 9.4 s run when only 4.7 s of it was memory traffic. Excluding the
    # overhead exposed that, so the count is doubled to put real work back at ~9 s.
    #
    # A sweep locks the clock LOW as well as high, so the same iteration count takes 2-3x
    # longer at the bottom of the range - that is expected and correct.
    iterations = args.iterations
    if iterations <= 0 and not isSuite:
        iterations = 120 if args.workload == "gemm" else 1200

    # No default for the suite, deliberately. gemm and membw carry counts that were measured on
    # a specific card and are correct because somebody ran them; inventing equivalents for
    # thirteen new workloads would put unmeasured numbers into the one setting the fixed-work
    # property depends on. --calibrate produces the count; the operator then passes it and holds
    # it constant.
    if iterations <= 0 and isSuite and not args.calibrate:
        emit({"ok": False, "error": "iterations_required", "workload": args.workload}, args.json,
             [f"[WORKLOAD] {args.workload} has no default iteration count, on purpose.",
              "[WORKLOAD] Run once at full clock to find one:",
              f"[WORKLOAD]     python gpu_workload.py --workload {args.workload} --calibrate",
              "[WORKLOAD] then pass --iterations N and hold N constant across every frequency."])
        return 8

    aborted = False
    abortReason = None
    peakTemp = startTemp if startTemp is not None else 0.0
    if args.input_seed is not None:
        torch.manual_seed(args.input_seed)

    try:
        if args.workload == "gemm":
            left = torch.randn((size, size), device=device, dtype=torchDtype)
            right = torch.randn((size, size), device=device, dtype=torchDtype)
            workPerIteration = FLOPS_PER_GEMM(size)
            # Declared for the intensity field only. Unchanged behaviour: workPerIteration and
            # the unit are exactly what they were. N/6 gives the ~1365 FLOP/byte 5.7 quotes.
            suiteFlops = workPerIteration
            suiteBytes = 3.0 * (size ** 2) * (4 if args.dtype == "fp32" else 2)

            def step():
                torch.matmul(left, right)

        elif args.workload == "membw":
            # Memory-bound: a scaled add over a large buffer. Every element is read twice
            # and written once, so this is bandwidth-limited rather than arithmetic-limited.
            source = torch.randn(size, device=device, dtype=torchDtype)
            other = torch.randn(size, device=device, dtype=torchDtype)
            destination = torch.empty(size, device=device, dtype=torchDtype)
            bytesPerElement = 4 if args.dtype == "fp32" else 2
            workPerIteration = float(size) * bytesPerElement * 3.0
            # One multiply and one add per element over 12 bytes of traffic gives the 0.167
            # FLOP/byte quoted throughout. Declared for the intensity field only.
            suiteFlops = 2.0 * size
            suiteBytes = workPerIteration

            def step():
                torch.add(source, other, alpha=2.0, out=destination)

        elif args.workload in APP_WORKLOADS:
            # One step is one complete application task; throughput is tasks or images per second
            # (app_workloads.py). No FLOP or byte count is declared for these.
            torch.backends.cudnn.benchmark = False  # heuristic algorithm choice, never timing-based
            step, workPerIteration, appUnit, suiteFlops, size = buildAppWorkload(args.workload, device, torch)
            suiteBytes = None

        else:
            elementBytes = 4 if args.dtype == "fp32" else 2
            step, suiteFlops, suiteBytes, size = buildSuiteWorkload(
                args.workload, size, torchDtype, elementBytes, device, torch)
            # A workload with no arithmetic at all cannot report FLOP/s, and one below roughly
            # one FLOP per byte is measuring the memory system whatever its operation is called.
            # The unit follows the intensity rather than the family name.
            intensity = (suiteFlops / suiteBytes) if suiteBytes else 0.0
            workPerIteration = suiteFlops if intensity >= 1.0 else suiteBytes

        for _ in range(max(0, args.warmup)):
            step()
        torch.cuda.synchronize()

        if args.calibrate:
            # Timed with no temperature polling, because a poll inside a short sample would be a
            # large fraction of it. This measures the card as it is RIGHT NOW - so run it at full
            # clock on a quiet machine, or the count it prints will be sized for a throttled card.
            probeIterations = 20
            probeStart = time.perf_counter()
            for _ in range(probeIterations):
                step()
            torch.cuda.synchronize()
            perIteration = (time.perf_counter() - probeStart) / probeIterations
            recommended = max(1, int(round(args.target_seconds / perIteration))) if perIteration > 0 else 0
            emit({"ok": True, "calibration": True, "workload": args.workload, "size": size,
                  "seconds_per_iteration": round(perIteration, 8),
                  "target_seconds": args.target_seconds,
                  "recommended_iterations": recommended}, args.json,
                 [f"[WORKLOAD] Calibration for {args.workload} (size {size}) on {deviceName}:",
                  f"[WORKLOAD]   {perIteration * 1000:.3f} ms per iteration over {probeIterations} iterations",
                  f"[WORKLOAD]   --iterations {recommended} gives about {args.target_seconds:.0f} s at this clock",
                  "[WORKLOAD] This is NOT a benchmark result. Record the count, pass it explicitly,",
                  "[WORKLOAD] and hold it constant across every frequency in the sweep."])
            return 0

        # Section 20b's preload: the same kernel for a fixed elapsed time, synchronized every
        # iteration so the wall clock tracks the GPU rather than a CPU racing ahead of the queue.
        # Untimed. Its actual duration and count are reported, never adjusted.
        if args.preload_seconds > 0:
            preloadStart = time.perf_counter()
            while time.perf_counter() - preloadStart < args.preload_seconds:
                step()
                torch.cuda.synchronize()
                preloadIterations += 1
            preloadSeconds = time.perf_counter() - preloadStart

        if readClocks is not None:
            clocksBeforeStart, clocksBeforeCall = bracketedCall(readClocks)
        if readEnergy is not None:
            if detail:
                energyStartMj, endpointStart = bracketedCall(readEnergy)
            else:
                energyStartMj = readEnergy()
            energyStartWall = time.perf_counter()
        started = time.perf_counter()
        workMonoStart = started
        startedUnix = time.time()
        completedIterations = 0
        monitoringSeconds = 0.0
        lastTempCheck = started
        checkInterval = max(0.1, args.temp_check_seconds)

        for _ in range(iterations):
            step()
            completedIterations += 1

            # Two separate cadences, and the distinction is the whole point.
            #
            # The SYNC is iteration-based. It has to be: CUDA launches are asynchronous, so
            # the CPU queues every kernel in milliseconds and then blocks at the final
            # synchronize(). A purely time-based gate on perf_counter() therefore never fires
            # at all - the loop is over before wall time advances - which silently disables
            # the temperature ceiling. That regression was caught only by running it and
            # noticing monitoring_overhead_seconds come back as exactly 0.000.
            #
            # Syncing this often is free: measured against a no-sync control, gemm ran 7.49 s
            # both ways and membw 4.67 s both ways. The GPU is the bottleneck, so this waits
            # on work that had to finish anyway.
            if completedIterations % SYNC_EVERY_ITERATIONS == 0:
                torch.cuda.synchronize()

                # The nvidia-smi POLL is time-based, because that cost is real (42 ms per
                # spawn) and an iteration cadence would poll a fast card more often than a
                # slow one - putting a frequency-dependent bias in the measured duration.
                now = time.perf_counter()
                if now - lastTempCheck < checkInterval:
                    continue

                monitorStart = time.perf_counter()
                currentTemp = readTemperature()
                monitoringSeconds += time.perf_counter() - monitorStart
                lastTempCheck = time.perf_counter()

                if currentTemp is not None:
                    peakTemp = max(peakTemp, currentTemp)
                    if currentTemp >= args.max_temp:
                        aborted = True
                        abortReason = f"temperature {currentTemp} C reached ceiling {args.max_temp} C"
                        break

        torch.cuda.synchronize()
        if detail:  # gated, so the historical path makes exactly its old calls (GPT Job 75, R8)
            workMonoEnd = time.perf_counter()
        if readEnergy is not None:
            if detail:
                energyEndMj, endpointEnd = bracketedCall(readEnergy)
            else:
                energyEndMj = readEnergy()
            energyEndWall = time.perf_counter()
        if readClocks is not None:
            clocksAfterEnd, clocksAfterCall = bracketedCall(readClocks)
        endedUnix = time.time()
        wallSeconds = time.perf_counter() - started
        elapsed = wallSeconds - monitoringSeconds

    except RuntimeError as error:
        message = str(error)
        errorKind = "out_of_memory" if "out of memory" in message.lower() else "runtime_error"
        failure = {"ok": False, "error": errorKind, "detail": message[:300]}
        if detail:
            failure["temperature_reads"] = temperatureLog  # kept for diagnosis (GPT Job 75, R8)
        emit(failure, args.json, [f"[WORKLOAD] {errorKind}: {message[:300]}"])
        return 7
    finally:
        # Always hand VRAM back, including on abort, so repeated sweep points do not
        # accumulate allocations across runs.
        try:
            torch.cuda.synchronize()
        except Exception:
            pass
        torch.cuda.empty_cache()

    try:
        endTemp = readTemperature()
    except RuntimeError as error:
        emit({"ok": False, "error": str(error), "temperature_reads": temperatureLog}, args.json,
             [f"[WORKLOAD] {error} after the timed region: this run is not usable."])
        return 9
    if endTemp is not None:
        peakTemp = max(peakTemp, endTemp)

    throughput = None
    if elapsed > 0 and completedIterations > 0:
        totalWork = workPerIteration * completedIterations
        throughput = totalWork / elapsed  # FLOP/s for gemm, byte/s for membw

    # Which unit the number above is in. gemm and membw keep the units they have always had;
    # a suite workload follows its declared intensity, because a workload below one FLOP per
    # byte is measuring the memory system whatever its operation is called.
    declaredIntensity = (suiteFlops / suiteBytes) if (suiteFlops and suiteBytes) else 0.0
    isApp = args.workload in APP_WORKLOADS
    reportsFlops = (args.workload == "gemm") or (isSuite and not isApp and declaredIntensity >= 1.0)

    energyJoules = energyPower = energyWindow = None
    if None not in (energyStartMj, energyEndMj, energyStartWall, energyEndWall):
        energyWindow = round(energyEndWall - energyStartWall, 4)
        energyJoules = round((energyEndMj - energyStartMj) / 1000.0, 3)
        if energyWindow > 0:
            energyPower = round(energyJoules / energyWindow, 3)

    payload = {
        "ok": (not aborted) and completedIterations == iterations,
        "workload": args.workload,
        "device": deviceName,
        "dtype": args.dtype,
        "size": size,
        "iterations_requested": iterations,
        "iterations_completed": completedIterations,
        # duration_seconds is work-only: monitoring subprocess time is subtracted. The raw
        # figures are kept alongside it so the correction can be checked, not taken on faith.
        "duration_seconds": round(elapsed, 4),
        "wall_seconds": round(wallSeconds, 4),
        "monitoring_overhead_seconds": round(monitoringSeconds, 4),
        "seconds_per_iteration": round(elapsed / completedIterations, 6) if completedIterations else None,
        "throughput": throughput,
        "throughput_unit": appUnit if isApp else ("FLOP/s" if reportsFlops else "byte/s"),
        # Declared, not measured - see the suite header. Present so an analysis can order the
        # workloads by intensity without a second lookup table that could disagree with this file.
        "flops_per_iteration": suiteFlops,
        "bytes_per_iteration": suiteBytes,
        "arithmetic_intensity_flop_per_byte": round(suiteFlops / suiteBytes, 4) if (suiteFlops and suiteBytes) else None,
        "arithmetic_intensity_is_declared": True,
        # Recorded because it changes what the number above MEANS. A TF32 convolution and an fp32
        # matmul are not the same arithmetic, and a sweep that mixed them would be comparing
        # precisions while appearing to compare frequencies.
        "tf32_allowed": bool(args.allow_tf32),
        # Epoch bounds of the timed region, so the sweep can window its power samples to
        # exactly the interval that produced the throughput above.
        "timed_region_start_unix": round(startedUnix, 4),
        "timed_region_end_unix": round(endedUnix, 4),
        # NVML's cumulative energy counter read at the two edges of the timed region; the
        # average power it implies is independent of the sampled nvidia-smi power. Null when
        # the counter is unavailable. See openEnergyCounter for its ~100 ms tick.
        "energy_counter_start_mj": energyStartMj,
        "energy_counter_end_mj": energyEndMj,
        "energy_window_seconds": energyWindow,
        "energy_joules": energyJoules,
        "energy_avg_power_w": energyPower,
        "temperature_start_c": startTemp,
        "temperature_peak_c": peakTemp,
        "aborted": aborted,
        "abort_reason": abortReason,
    }
    if detail:
        # Section 20b. T is the difference of the two energy-call midpoints on perf_counter; the
        # raw counter integers, both brackets, both boundary clock reads and every temperature
        # read are kept so that any of it can be re-derived. Nothing above is changed by this.
        durationT = None
        if endpointStart and endpointEnd:
            durationT = ((endpointEnd["mono_before"] + endpointEnd["mono_after"]) / 2.0
                         - (endpointStart["mono_before"] + endpointStart["mono_after"]) / 2.0)
        payload["endpoint_detail"] = {
            "energy_start": dict(endpointStart or {}, value_mj=energyStartMj),
            "energy_end": dict(endpointEnd or {}, value_mj=energyEndMj),
            "duration_t_seconds": durationT,
            "work_per_iteration": workPerIteration,
            "work_units": (workPerIteration * completedIterations) if completedIterations else None,
            "warmup_iterations": max(0, args.warmup),
            "preload_seconds_requested": args.preload_seconds,
            "preload_seconds": preloadSeconds,
            "preload_iterations": preloadIterations,
            "clocks_before_start": dict(clocksBeforeCall, sm_mhz=clocksBeforeStart[0], mem_mhz=clocksBeforeStart[1]) if clocksBeforeStart else None,
            "clocks_after_end": dict(clocksAfterCall, sm_mhz=clocksAfterEnd[0], mem_mhz=clocksAfterEnd[1]) if clocksAfterEnd else None,
            # The fixed work's own synchronized bounds on perf_counter, separate from T.
            "work_mono_start": workMonoStart,
            "work_mono_end": workMonoEnd,
            # The direct-API support read made when the counter was opened, outside timing:
            # attempted, bracketed, its value and whether it succeeded.
            "energy_support_reads": energySupportLog,
            "energy_support_check_reads": len(energySupportLog or []),
            "temperature_reads": temperatureLog,
        }

    humanUnit = appUnit if isApp else ("TFLOP/s" if reportsFlops else "GB/s")
    humanValue = throughput if isApp else (throughput / 1e12) if reportsFlops else (throughput / 1e9) if throughput else 0.0
    if throughput is None:
        humanValue = 0.0

    lines = [
        f"[WORKLOAD] {args.workload} on {deviceName} ({args.dtype}, size {size}, "
        f"{declaredIntensity:.3f} FLOP/byte declared)",
        f"[WORKLOAD] {completedIterations}/{iterations} iterations in {elapsed:.3f} s of GPU work "
        f"({wallSeconds:.3f} s wall, {monitoringSeconds:.3f} s monitoring excluded)",
        f"[WORKLOAD] Throughput: {humanValue:.2f} {humanUnit}",
        f"[WORKLOAD] Temperature: start {startTemp} C, peak {peakTemp} C",
    ]
    if aborted:
        lines.append(f"[WORKLOAD] ABORTED: {abortReason}")
        lines.append("[WORKLOAD] This run is NOT comparable to complete runs - discard it.")

    # Only when --input-seed was given, so every other protocol's payload stays exactly as it was
    # (pinned by tools/frequency-sweep/test_gpu_workload_trace.py). App workloads seed themselves.
    if args.input_seed is not None:
        payload["input_seed"] = args.input_seed
    emit(payload, args.json, lines)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
