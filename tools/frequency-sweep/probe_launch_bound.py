"""Is `membw` throughput at high clock limited by the CPU's kernel launch rate?

WHY THIS EXISTS
    Sweep points showed GPU utilisation below 100% even after subtracting the known
    nvidia-smi monitoring cost, and the gap appeared to grow with clock (0.9% at 1200 MHz,
    5.5% at 1897 MHz, 7.5% at 2754 MHz). The worrying reading is that the CPU cannot
    launch kernels fast enough to keep the GPU fed as kernels shorten - which would
    suppress high-clock throughput, understate high-clock efficiency, and bias `membw`'s
    measured optimum downward. That is a defect in a published result if true, so it
    needs testing rather than arguing about.

THE TEST
    Hold TOTAL bytes moved constant and vary bytes-per-kernel over a 64x range. Launch
    overhead is a fixed cost per launch, so if launches are the limiter, throughput must
    rise as kernels get larger and launches get rarer. If throughput is flat across the
    range, the gaps are not costing work.

    Then the direct check: replay the identical kernel sequence from a CUDA graph, which
    removes nearly all per-launch CPU work. If the small-kernel condition is launch-bound,
    graph replay recovers the loss. If it changes nothing, launches were never the limit.

    The smallest size is chosen so the working set stays well clear of this card's 32 MB
    L2. That matters because cache and launch cost push the small-kernel condition in
    OPPOSITE directions - residency would make small kernels look faster, launch overhead
    makes them look slower - so a naive range confounds the two. An earlier version of
    this script started at 8 M elements, which put a buffer at exactly 1.0x L2, and the
    smoke run caught it. The CUDA graph test is immune either way: it compares the same
    kernel size against itself, so cache behaviour is identical on both sides.

CONFOUND CONTROL
    Clocks are not locked (that needs elevation), so conditions run in interleaved rounds
    with the order reversed on alternate rounds, and achieved clock and power are sampled
    by a SEPARATE nvidia-smi process - never inside the timed region - then windowed to
    each condition. If clock differs materially across conditions the comparison is not
    trustworthy, and the summary says so rather than leaving the reader to notice.

USAGE
    python probe_launch_bound.py --json out.json
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime

# Bytes touched per element per iteration: read source, read other, write destination.
BYTES_PER_ELEMENT_TOUCHED = 3
L2_BYTES = 32 * 1024 * 1024

# Elements per kernel launch, in millions. Total work is held constant, so the launch
# count scales inversely. The smallest is sized so its three-buffer working set is several
# times L2 - see the module docstring for why that bound is load-bearing.
ELEMENTS_PER_KERNEL_M = [16, 32, 128, 256, 512]

# Total elements processed per condition, in millions. At ~415 GB/s this is ~5 s per
# condition. The first draft used 8192 and ran each condition in 250 ms, which left the
# 100 ms telemetry sampler with two or three samples per window - so the reported clock
# and utilisation were noise, and the clock-drift guard fired on an artifact. A condition
# must be long enough to be sampled properly, not just long enough to time.
TOTAL_ELEMENTS_M = 163840

# A condition shorter than this cannot be characterised by a 100 ms sampler.
MIN_CONDITION_SECONDS = 2.0

# Seconds of untimed work before measurement, to bring clocks and temperature to steady
# state. Without it the first condition measured is the one still boosting up from idle.
SETTLE_SECONDS = 20.0

# Kernels captured into one graph. Replay submits the whole block with a single CPU call.
GRAPH_BLOCK = 32


def sampleStart(path):
    """Start an out-of-process telemetry sampler. Never call nvidia-smi in a timed loop."""
    handle = open(path, "w", encoding="utf-8")
    process = subprocess.Popen(
        ["nvidia-smi", "--query-gpu=timestamp,clocks.sm,power.draw,utilization.gpu",
         "--format=csv,noheader,nounits", "-lms", "100", "-i", "0"],
        stdout=handle, stderr=subprocess.DEVNULL,
    )
    return process, handle


def sampleRead(path):
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 4:
                    continue
                try:
                    stamp = datetime.strptime(parts[0], "%Y/%m/%d %H:%M:%S.%f").timestamp()
                    rows.append((stamp, float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def windowStats(rows, startUnix, endUnix):
    inside = [r for r in rows if startUnix <= r[0] <= endUnix]
    if not inside:
        return None
    return {
        "samples": len(inside),
        "clock_avg_mhz": round(sum(r[1] for r in inside) / len(inside), 1),
        "clock_min_mhz": min(r[1] for r in inside),
        "clock_max_mhz": max(r[1] for r in inside),
        "power_avg_w": round(sum(r[2] for r in inside) / len(inside), 1),
        "util_avg_pct": round(sum(r[3] for r in inside) / len(inside), 1),
    }


def runCondition(torch, elementsM, useGraph, device):
    """One condition. Returns a dict, or None if it could not be run."""
    elements = elementsM * 1024 * 1024
    launches = (TOTAL_ELEMENTS_M * 1024 * 1024) // elements

    source = other = destination = graph = None
    try:
        source = torch.randn(elements, device=device, dtype=torch.float32)
        other = torch.randn(elements, device=device, dtype=torch.float32)
        destination = torch.empty(elements, device=device, dtype=torch.float32)

        def step():
            torch.add(source, other, alpha=2.0, out=destination)

        # Warm up allocator and clocks before anything is timed.
        for _ in range(5):
            step()
        torch.cuda.synchronize()

        replays = 0
        if useGraph:
            blockSize = min(GRAPH_BLOCK, launches)
            side = torch.cuda.Stream()
            side.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(side):
                for _ in range(3):
                    step()
            torch.cuda.current_stream().wait_stream(side)

            graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):
                for _ in range(blockSize):
                    step()
            torch.cuda.synchronize()
            replays = launches // blockSize
            launches = replays * blockSize

        torch.cuda.synchronize()
        started = time.perf_counter()
        startUnix = time.time()

        if graph is not None:
            for _ in range(replays):
                graph.replay()
        else:
            for _ in range(launches):
                step()

        # How long the CPU spent submitting. If this approaches the total, the CPU never
        # got ahead of the GPU and the launch path is the suspect.
        submitSeconds = time.perf_counter() - started

        torch.cuda.synchronize()
        seconds = time.perf_counter() - started
        endUnix = time.time()

    except RuntimeError as error:
        print(f"[PROBE] {elementsM} M/kernel graph={useGraph} failed: {str(error)[:160]}")
        return None
    finally:
        del source, other, destination, graph
        try:
            torch.cuda.synchronize()
        except Exception:
            pass
        torch.cuda.empty_cache()

    bytesMoved = float(elements) * 4 * BYTES_PER_ELEMENT_TOUCHED * launches
    return {
        "elements_m": elementsM,
        "graph": useGraph,
        "launches": launches,
        "seconds": round(seconds, 4),
        "ms_per_kernel": round(seconds / launches * 1000, 4),
        "gb_per_s": round(bytesMoved / seconds / 1e9, 2),
        "cpu_submit_seconds": round(submitSeconds, 4),
        "cpu_submit_fraction": round(submitSeconds / seconds, 4),
        "start_unix": startUnix,
        "end_unix": endUnix,
    }


def median(values):
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return None
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=3,
                        help="Interleaved repeats. Order reverses on alternate rounds.")
    parser.add_argument("--json", default="", help="Write full results to this path.")
    parser.add_argument("--telemetry", default="probe_telemetry.csv")
    args = parser.parse_args()

    try:
        import torch
    except ImportError:
        print("[PROBE] PyTorch is not installed.")
        return 4
    if not torch.cuda.is_available():
        print("[PROBE] No CUDA device.")
        return 5

    device = torch.device("cuda:0")
    name = torch.cuda.get_device_name(0)
    props = torch.cuda.get_device_properties(0)
    # Cache residency is judged on the WORKING SET - all three buffers - not one buffer.
    smallestSet = ELEMENTS_PER_KERNEL_M[0] * 1024 * 1024 * 4 * 3
    ratio = smallestSet / L2_BYTES

    print(f"[PROBE] {name}, {props.total_memory / 1e9:.1f} GB")
    print(f"[PROBE] {TOTAL_ELEMENTS_M} M elements per condition "
          f"({TOTAL_ELEMENTS_M * 1024 * 1024 * 12 / 1e9:.0f} GB of traffic), work held constant")
    print(f"[PROBE] smallest working set {smallestSet / 1e6:.0f} MB = {ratio:.1f}x L2")
    if ratio < 3.0:
        print("[PROBE] WARNING: smallest condition is close to L2. Cache residency would "
              "flatter it and mask launch cost. Raise ELEMENTS_PER_KERNEL_M[0].")
    print()

    sampler, handle = sampleStart(args.telemetry)
    time.sleep(1.0)

    # Settle. The card idles at ~1500 MHz and takes seconds to reach its sustained boost
    # clock; measuring during that ramp assigns the ramp to whichever condition ran first.
    print(f"[PROBE] settling for {SETTLE_SECONDS:.0f} s to reach steady clocks...")
    settleElements = 256 * 1024 * 1024
    settleA = torch.randn(settleElements, device=device, dtype=torch.float32)
    settleB = torch.randn(settleElements, device=device, dtype=torch.float32)
    settleOut = torch.empty(settleElements, device=device, dtype=torch.float32)
    settleEnd = time.perf_counter() + SETTLE_SECONDS
    while time.perf_counter() < settleEnd:
        for _ in range(20):
            torch.add(settleA, settleB, alpha=2.0, out=settleOut)
        torch.cuda.synchronize()
    del settleA, settleB, settleOut
    torch.cuda.empty_cache()
    settled = subprocess.run(
        ["nvidia-smi", "--query-gpu=clocks.sm,temperature.gpu,power.draw",
         "--format=csv,noheader,nounits", "-i", "0"],
        capture_output=True, text=True)
    print(f"[PROBE] settled at {settled.stdout.strip()} (MHz, C, W)\n")

    results = []
    tooShort = []
    try:
        for roundIndex in range(args.rounds):
            order = list(ELEMENTS_PER_KERNEL_M)
            if roundIndex % 2 == 1:
                order.reverse()
            for elementsM in order:
                entry = runCondition(torch, elementsM, False, device)
                if entry is None:
                    continue
                entry["round"] = roundIndex
                results.append(entry)
                if entry["seconds"] < MIN_CONDITION_SECONDS:
                    tooShort.append((elementsM, entry["seconds"]))
                print(f"[PROBE] round {roundIndex}  {elementsM:>4} M/kernel  "
                      f"{entry['launches']:>6} launches  {entry['gb_per_s']:7.1f} GB/s  "
                      f"{entry['ms_per_kernel']:7.3f} ms/kernel  "
                      f"cpu submit {entry['cpu_submit_fraction'] * 100:5.1f}%")

        print()
        for elementsM in (ELEMENTS_PER_KERNEL_M[0], 256):
            for useGraph in (False, True):
                entry = runCondition(torch, elementsM, useGraph, device)
                if entry is None:
                    continue
                entry["round"] = "graph-test"
                results.append(entry)
                label = "CUDA graph" if useGraph else "normal    "
                print(f"[PROBE] {label}  {elementsM:>4} M/kernel  {entry['gb_per_s']:7.1f} GB/s")
    finally:
        sampler.terminate()
        try:
            sampler.wait(timeout=5)
        except Exception:
            sampler.kill()
        handle.close()

    telemetry = sampleRead(args.telemetry)
    for entry in results:
        entry["telemetry"] = windowStats(telemetry, entry["start_unix"], entry["end_unix"])

    # ---- summary ----
    print("\n" + "=" * 72)
    print("WORK-PER-LAUNCH (total work constant; medians over rounds)")
    print("=" * 72)
    print(f"{'M/kernel':>9}{'launches':>10}{'ms/kernel':>11}{'GB/s':>9}{'clock':>8}{'util%':>7}")
    swept = []
    for elementsM in ELEMENTS_PER_KERNEL_M:
        runs = [r for r in results if r["elements_m"] == elementsM and not r["graph"]
                and r["round"] != "graph-test"]
        if not runs:
            continue
        gbps = median([r["gb_per_s"] for r in runs])
        clocks = [r["telemetry"]["clock_avg_mhz"] for r in runs if r["telemetry"]]
        utils = [r["telemetry"]["util_avg_pct"] for r in runs if r["telemetry"]]
        swept.append((elementsM, gbps, median(clocks), median(utils)))
        print(f"{elementsM:>9}{runs[0]['launches']:>10}{median([r['ms_per_kernel'] for r in runs]):>11.3f}"
              f"{gbps:>9.1f}{(median(clocks) or 0):>8.0f}{(median(utils) or 0):>7.1f}")

    verdicts = []
    if tooShort:
        shortest = min(s[1] for s in tooShort)
        verdicts.append(f"UNTRUSTWORTHY - {len(tooShort)} condition(s) ran under "
                        f"{MIN_CONDITION_SECONDS:.0f} s (shortest {shortest:.2f} s); the 100 ms "
                        f"sampler cannot characterise a window that short. Raise TOTAL_ELEMENTS_M")
    if len(swept) >= 2:
        best = max(s[1] for s in swept)
        worst = min(s[1] for s in swept)
        spread = (best - worst) / worst * 100
        clockValues = [s[2] for s in swept if s[2]]
        clockSpread = (max(clockValues) - min(clockValues)) if len(clockValues) > 1 else 0
        print(f"\nThroughput spread across a {ELEMENTS_PER_KERNEL_M[-1] // ELEMENTS_PER_KERNEL_M[0]}x "
              f"range of kernel size: {spread:.1f}%")
        print(f"Clock spread across the same conditions: {clockSpread:.0f} MHz")
        if clockSpread > 60:
            verdicts.append(f"UNTRUSTWORTHY - clock varied {clockSpread:.0f} MHz between "
                            f"conditions; lock the clock and re-run")
        elif spread < 2.0:
            verdicts.append("NOT launch-bound - throughput is flat across kernel size")
        else:
            smallGbps = swept[0][1]
            largeGbps = swept[-1][1]
            direction = "larger" if largeGbps > smallGbps else "smaller"
            verdicts.append(f"launch rate MATTERS - {direction} kernels are "
                            f"{abs(largeGbps - smallGbps) / min(largeGbps, smallGbps) * 100:.1f}% faster")

    print("\n" + "=" * 72)
    print("CUDA GRAPH REPLAY (removes per-launch CPU cost)")
    print("=" * 72)
    for elementsM in (ELEMENTS_PER_KERNEL_M[0], 256):
        pair = {r["graph"]: r for r in results if r["round"] == "graph-test"
                and r["elements_m"] == elementsM}
        if False in pair and True in pair:
            plain = pair[False]["gb_per_s"]
            graphed = pair[True]["gb_per_s"]
            delta = (graphed - plain) / plain * 100
            print(f"{elementsM:>4} M/kernel: normal {plain:7.1f} GB/s -> "
                  f"graph {graphed:7.1f} GB/s  ({delta:+.1f}%)")
            if elementsM == ELEMENTS_PER_KERNEL_M[0]:
                if abs(delta) < 1.5:
                    verdicts.append("graph replay changes nothing - the launch path is not "
                                    "the limiter even at the smallest kernel")
                else:
                    verdicts.append(f"graph replay moves throughput {delta:+.1f}% at the "
                                    f"smallest kernel - launch cost is real")

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    for line in verdicts:
        print(f"  * {line}")
    if not verdicts:
        print("  * inconclusive - not enough conditions completed")

    payload = {"device": name, "total_elements_m": TOTAL_ELEMENTS_M,
               "rounds": args.rounds, "verdicts": verdicts, "results": results}
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\n[PROBE] wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
