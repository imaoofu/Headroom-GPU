"""
At a LOW locked core clock, can more concurrency buy more bandwidth?

WHY THIS IS THE DECIDING TEST
    Six torch access patterns were measured at 1400 and 2800 MHz. All six are issue-limited
    (elasticity 0.45-0.96 against core clock); none is DRAM-limited. The open question is
    whether that is fixable:

      * If the ceiling is memory-level parallelism - not enough requests in flight - then more
        concurrent work SHOULD raise aggregate bandwidth, and a hand-tuned kernel with deep
        unrolling could saturate DRAM at low clocks. The [CORE] roadmap item is then worth doing.
      * If the ceiling is the SM instruction issue rate, concurrency changes nothing, because
        issue rate is shared hardware that no kernel can escape. No workload can be
        bandwidth-saturated at this clock, and the roadmap item is not achievable on this part.

    An earlier version of this test ran at free boost and was uninformative: the kernel is
    already near the achievable DRAM ceiling there (~406 GB/s against a ~521 GB/s theoretical
    peak at this memory clock, about 78%, which is normal for GDDR). Concurrency cannot help
    where the workload is already saturated. The test only discriminates at a clock where the
    workload is known NOT to be saturated.

REQUIRES an elevated shell.
"""

import ctypes
import json
import pathlib
import subprocess
import sys
import time

import torch

LOW_MHZ = 1400
ELEMENTS = 64 * 1024 * 1024
STREAM_COUNTS = (1, 2, 4, 8)
ITERATIONS = 60
SETTLE_SECONDS = 6


def isElevated():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def smi(*args):
    return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True)


def main():
    if not isElevated():
        print("REFUSING TO START: not elevated. Clock locking needs administrator rights.")
        return 1

    device = torch.device("cuda")
    sources, destinations, streams = [], [], []
    for _ in range(max(STREAM_COUNTS)):
        sources.append(torch.randn(ELEMENTS, device=device))
        destinations.append(torch.empty(ELEMENTS, device=device))
        streams.append(torch.cuda.Stream())
    bytesPerCopy = ELEMENTS * 4 * 2

    def run(count):
        for _ in range(5):
            for i in range(count):
                destinations[i].copy_(sources[i])
        torch.cuda.synchronize()
        started = time.perf_counter()
        for _ in range(ITERATIONS):
            for i in range(count):
                with torch.cuda.stream(streams[i]):
                    destinations[i].copy_(sources[i])
        torch.cuda.synchronize()
        return bytesPerCopy * count * ITERATIONS / (time.perf_counter() - started) / 1e9

    results = {}
    try:
        locked = smi("-lgc", str(LOW_MHZ))
        if locked.returncode != 0:
            print(f"could not lock: {locked.stderr.strip()}")
            return 1
        time.sleep(SETTLE_SECONDS)
        achieved = float(smi("--query-gpu=clocks.sm", "--format=csv,noheader,nounits")
                         .stdout.strip().splitlines()[0])
        print(f"locked to {LOW_MHZ} MHz, achieved {achieved:.0f} MHz\n")
        print("concurrent copies -> aggregate GB/s")
        for count in STREAM_COUNTS:
            gbs = run(count)
            results[count] = gbs
            base = results[STREAM_COUNTS[0]]
            print(f"  {count} stream(s): {gbs:>7.1f} GB/s   ({gbs/base:.2f}x vs 1 stream)")
    finally:
        smi("-rgc")
        print("\n[clocks reset]")

    base = results[STREAM_COUNTS[0]]
    best = max(results.values())
    gain = best / base
    print()
    if gain >= 1.15:
        print(f"CONCLUSION: concurrency buys {gain:.2f}x at {LOW_MHZ} MHz. The ceiling is")
        print("memory-level parallelism, NOT issue rate. A hand-tuned kernel with deep")
        print("unrolling could plausibly saturate DRAM here. The [CORE] item is achievable.")
    else:
        print(f"CONCLUSION: concurrency buys only {gain:.2f}x at {LOW_MHZ} MHz. The ceiling is")
        print("the SM instruction issue rate, which is shared hardware no kernel can escape.")
        print("No workload can be DRAM-saturated at this clock on this part. The [CORE] item")
        print("is not achievable as written, and that is itself the answer it was asking for.")

    resultPath = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "probes" / "probe_issue_ceiling_result.json"
    resultPath.parent.mkdir(parents=True, exist_ok=True)
    with open(resultPath, "w", encoding="utf-8") as handle:
        json.dump({"low_mhz": LOW_MHZ, "achieved_mhz": achieved, "elements": ELEMENTS,
                   "iterations": ITERATIONS,
                   "aggregate_gbs": {str(k): v for k, v in results.items()}}, handle, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
