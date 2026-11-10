"""
Which memory kernel is genuinely DRAM-saturated, rather than issue-limited?

WHY THIS EXISTS
    The `membw` workload is a torch elementwise triad. It was assumed bandwidth-bound, but its
    throughput tracks CORE clock hard - 264.9 GB/s at 1237 MHz against 352.2 at 2932 on stock,
    59% to 79% of this card's rated 448 GB/s. A DRAM-limited kernel would be FLAT against core
    clock. This one is issue-limited over most of the swept range: below roughly 2800 MHz the
    SMs cannot generate memory requests fast enough to keep DRAM busy.

    That matters because the V100 frequency-prediction result was tested against `membw` on the
    assumption it was memory-bound. It is only approximately memory-bound, and only near the top
    of the range, so the premise did not hold where the test was run.

THE MEASUREMENT
    Peak throughput at boost clock does NOT discriminate - every candidate lands within 6% of
    400 GB/s there, because they all roughly saturate when the SMs are fast enough. The
    discriminating statistic is ELASTICITY of throughput to core clock:

        elasticity = ln(T_high / T_low) / ln(f_high / f_low)

    1.0 means throughput scales with core clock, i.e. purely issue-limited.
    0.0 means throughput is independent of core clock, i.e. purely DRAM-limited.

    The winner is the candidate with the LOWEST elasticity that still reaches a high absolute
    throughput. Low elasticity at a low throughput just means uniformly bad.

REQUIRES an elevated shell: locking clocks needs administrator rights.
"""

import ctypes
import json
import pathlib
import subprocess
import sys
import time

import torch

LOW_MHZ = 1400
HIGH_MHZ = 2800
ELEMENTS = 256 * 1024 * 1024
ITERATIONS = 120
SETTLE_SECONDS = 6


def isElevated():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def smi(*args):
    return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True)


def lockClock(mhz):
    result = smi("-lgc", str(mhz))
    if result.returncode != 0:
        raise RuntimeError(f"could not lock to {mhz} MHz: {result.stderr.strip()}")


def achievedClock():
    out = smi("--query-gpu=clocks.sm", "--format=csv,noheader,nounits").stdout.strip()
    return float(out.splitlines()[0])


def main():
    if not isElevated():
        print("REFUSING TO START: not elevated. Clock locking needs administrator rights.")
        return 1
    if not torch.cuda.is_available():
        print("REFUSING TO START: no CUDA device.")
        return 1

    device = torch.device("cuda")
    a = torch.randn(ELEMENTS, device=device)
    b = torch.randn(ELEMENTS, device=device)
    out = torch.empty(ELEMENTS, device=device)
    # Viewing fp32 storage as fp64 halves the element count without changing the bytes moved,
    # so each thread carries twice the payload. That is vectorisation with no custom kernel.
    aWide = a.view(torch.float64)
    outWide = out.view(torch.float64)

    elementBytes = ELEMENTS * 4
    candidates = [
        ("triad_current", lambda: torch.add(a, b, alpha=2.0, out=out), 3 * elementBytes),
        ("copy", lambda: out.copy_(a), 2 * elementBytes),
        ("copy_wide", lambda: outWide.copy_(aWide), 2 * elementBytes),
        ("scale", lambda: torch.mul(a, 2.0, out=out), 2 * elementBytes),
        ("read_only_sum", lambda: torch.sum(a), 1 * elementBytes),
        ("inplace_add", lambda: a.add_(b), 3 * elementBytes),
    ]

    def measure(fn, totalBytes):
        for _ in range(10):
            fn()
        torch.cuda.synchronize()
        started = time.perf_counter()
        for _ in range(ITERATIONS):
            fn()
        torch.cuda.synchronize()
        return totalBytes * ITERATIONS / (time.perf_counter() - started) / 1e9

    results = {name: {} for name, _, _ in candidates}
    try:
        for target in (LOW_MHZ, HIGH_MHZ):
            lockClock(target)
            print(f"\n--- locked to {target} MHz, settling {SETTLE_SECONDS}s")
            time.sleep(SETTLE_SECONDS)
            achieved = achievedClock()
            print(f"    achieved {achieved:.0f} MHz")
            for name, fn, totalBytes in candidates:
                gbs = measure(fn, totalBytes)
                results[name][target] = {"gbs": gbs, "achieved_mhz": achieved}
                print(f"    {name:<16} {gbs:>7.1f} GB/s")
    finally:
        smi("-rgc")
        print("\n[clocks reset]")

    import math
    print(f"\n{'kernel':<16} {LOW_MHZ:>9} {HIGH_MHZ:>9} {'elasticity':>11}  verdict")
    ranked = []
    for name, _, _ in candidates:
        lo = results[name][LOW_MHZ]
        hi = results[name][HIGH_MHZ]
        e = math.log(hi["gbs"] / lo["gbs"]) / math.log(hi["achieved_mhz"] / lo["achieved_mhz"])
        verdict = "DRAM-limited" if e < 0.15 else ("mostly saturated" if e < 0.35 else "issue-limited")
        print(f"{name:<16} {lo['gbs']:>8.1f}  {hi['gbs']:>8.1f}  {e:>10.3f}  {verdict}")
        ranked.append((name, e, lo["gbs"], hi["gbs"]))

    ranked.sort(key=lambda r: r[1])
    print(f"\nMOST SATURATED: {ranked[0][0]} (elasticity {ranked[0][1]:.3f}, "
          f"{ranked[0][2]:.1f} GB/s at {LOW_MHZ} MHz)")
    print(f"CURRENT membw : triad_current (elasticity "
          f"{[r[1] for r in ranked if r[0]=='triad_current'][0]:.3f})")

    resultPath = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "probes" / "probe_saturating_kernel_result.json"
    resultPath.parent.mkdir(parents=True, exist_ok=True)
    with open(resultPath, "w", encoding="utf-8") as handle:
        json.dump({"low_mhz": LOW_MHZ, "high_mhz": HIGH_MHZ, "elements": ELEMENTS,
                   "iterations": ITERATIONS, "results": results}, handle, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
