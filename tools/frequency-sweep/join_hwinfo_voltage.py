"""
Join HWiNFO core-voltage and crossbar-clock telemetry to a locked-frequency sweep.

WHY THIS EXISTS
    NVML does not expose GPU core voltage - an exhaustive scan of field IDs 1-259 through
    nvmlDeviceGetFieldValues returns 44 readable fields and none is a voltage at any scale (see
    tools/frequency-sweep/probe_nvml_fields.py). HWiNFO does read it, so every voltage statement
    in this project has to come through an HWiNFO log rather than the sweep tool itself.

HOW IT JOINS
    New sweep CSVs preserve the benchmark's absolute timed-region boundaries. Join HWiNFO's
    dated samples to those windows when every point has valid stamps. This separates targets
    even if the card clips several of them to the same achieved clock. Legacy sweeps have no
    boundaries and still use clock bins; they must have distinct achieved clocks to separate.

    In clock mode, samples taken while the card was idle between points are discarded by a
    power threshold. Time mode uses only the benchmark's timed region, so it keeps every
    sample inside that interval, including a low-power reading that may be a real failure.
    Without that filter the ramp-up and ramp-down samples - which sit at boost voltage - pull
    the per-point medians upward and manufacture a voltage-frequency slope that is not there.

WHICH COLUMNS
    HWiNFO on this machine reports TWO GPU sensor blocks. The first (around indices 277-281)
    carries AMD-style names - VDDCR_GFX, SoC Clock, VCN Clock - and does not describe the
    NVIDIA card. Columns are resolved by name within the block that also contains a plausible
    NVIDIA core clock, not by fixed index, so a different machine layout does not silently read
    the wrong sensor.

Usage:
    python join_hwinfo_voltage.py <sweep.csv> <hwinfo.csv> [--join-by auto|time|clock]
"""

import argparse
import csv
from datetime import datetime, timedelta, timezone
import re
import statistics
import sys
from pathlib import Path

IDLE_POWER_WATTS = 30.0
CLOCK_TOLERANCE_MHZ = 25.0

# Two sweep points closer than this ran at the SAME clock - the card clipped and refused to hold
# them apart. That is a property of the hardware, not of the join, so no bin width fixes it and
# gridSpacingConflict() deliberately ignores such pairs.
SAME_POINT_MHZ = 10.0


def parseUtcOffset(value):
    """Parse an explicit offset for logs collected in another local time zone."""
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if not match or int(match.group(2)) > 23 or int(match.group(3)) > 59:
        raise SystemExit("HWiNFO UTC offset must be signed HH:MM, for example -07:00.")
    minutes = int(match.group(2)) * 60 + int(match.group(3))
    if match.group(1) == "-":
        minutes = -minutes
    return timezone(timedelta(minutes=minutes))


def headerConflict(rows):
    """None, or why a repeated HWiNFO header contradicts the opening one (the rule in
    tools/hwinfo-logging/check_desktop_load.py). HWiNFO appends a sensor that appears mid-log at the
    END and repeats the full header when the log closes, so the columns read here by position stay the
    sensors they name. A later header that drops, renames or reorders an opening name means they moved:
    GPT Job 107 (2026-10-18) showed this joiner then reading power as voltage. A census that day found no
    such header in any of the 528 raw logs on the bench PC, so no committed extract changes."""
    names = [h.strip() for h in rows[0]] if rows else []
    while names and names[-1] == "":
        names.pop()
    for number, row in enumerate(rows[1:], start=2):
        if len(row) > 2 and row[0] == "Date" and row[1] == "Time" and [h.strip() for h in row[:len(names)]] != names:
            return f"the header repeated at row {number} does not keep the opening column names in place"
    return None


def loadHwinfo(path, includeTime=False, utcOffset=None):
    rows = list(csv.reader(open(path, encoding="latin-1")))
    conflict = headerConflict(rows)
    if conflict:
        raise SystemExit(f"{path}: {conflict}; refusing to read its columns by position.")
    header = [h.strip() for h in rows[0]]

    def findAll(name):
        return [i for i, h in enumerate(header) if h == name]

    voltageCandidates = findAll("GPU Core Voltage [V]")
    clockCandidates = findAll("GPU Clock [MHz]")
    crossbarCandidates = findAll("GPU Crossbar Clock [MHz]")
    # The MEASURED crossbar clock, a separate HWiNFO column. At stock it agrees with the reported
    # one to within ~7 MHz (5060ti-memmatched-20260926), but under a crossbar clock OFFSET the
    # reported value may show the request, so REGISTERED-PREDICTIONS section 14 scores its
    # manipulation check on this column only. Added 2026-09-30.
    measuredCrossbarCandidates = findAll("GPU Crossbar Clock (measured) [MHz]")
    powerCandidates = findAll("GPU Power [W]")

    if includeTime and ("Date" not in header or "Time" not in header):
        raise SystemExit("Time join needs HWiNFO Date and Time columns.")
    dateIndex = header.index("Date") if includeTime else None
    timeIndex = header.index("Time") if includeTime else None

    if not voltageCandidates or not clockCandidates:
        raise SystemExit("Could not find 'GPU Core Voltage [V]' and 'GPU Clock [MHz]' columns.")

    # Pick the block whose clock column actually moves and reaches NVIDIA-like values. The
    # AMD-style phantom block sits at a fixed low clock and would otherwise be chosen by index.
    def spread(index):
        values = []
        for r in rows[1:]:
            if index < len(r):
                try:
                    values.append(float(r[index]))
                except ValueError:
                    pass
        return (max(values) - min(values)) if values else 0.0

    clockIndex = max(clockCandidates, key=spread)
    voltageIndex = min(voltageCandidates, key=lambda i: abs(i - clockIndex))
    crossbarIndex = min(crossbarCandidates, key=lambda i: abs(i - clockIndex)) if crossbarCandidates else None
    measuredCrossbarIndex = (min(measuredCrossbarCandidates, key=lambda i: abs(i - clockIndex))
                             if measuredCrossbarCandidates else None)
    powerIndex = min(powerCandidates, key=lambda i: abs(i - clockIndex)) if powerCandidates else None

    samples = []
    for rowNumber, r in enumerate(rows[1:], start=2):
        needed = [clockIndex, voltageIndex]
        if max(needed) >= len(r):
            continue
        try:
            clock = float(r[clockIndex])
            voltage = float(r[voltageIndex])
            crossbar = float(r[crossbarIndex]) if crossbarIndex is not None and crossbarIndex < len(r) else None
            power = float(r[powerIndex]) if powerIndex is not None and powerIndex < len(r) else None
        except ValueError:
            continue
        sample = {"clock": clock, "voltage": voltage, "crossbar": crossbar, "power": power}
        if measuredCrossbarIndex is not None:
            # A blank or non-numeric cell is None for this column alone; it must not drop a row
            # whose voltage and clock are good.
            try:
                sample["crossbarMeasured"] = (float(r[measuredCrossbarIndex])
                                              if measuredCrossbarIndex < len(r) else None)
            except ValueError:
                sample["crossbarMeasured"] = None
        if includeTime:
            try:
                localTime = datetime.strptime(f"{r[dateIndex]} {r[timeIndex]}",
                                              "%d.%m.%Y %H:%M:%S.%f")
            except (IndexError, ValueError):
                raise SystemExit(f"HWiNFO row {rowNumber} has no parseable Date/Time.")
            awareTime = (localTime.replace(tzinfo=utcOffset) if utcOffset is not None
                         else localTime.astimezone())
            sample["timestamp"] = awareTime.timestamp()
            sample["utcOffsetMinutes"] = int(awareTime.utcoffset().total_seconds() / 60)
        samples.append(sample)

    return samples, {"clock": clockIndex, "voltage": voltageIndex,
                     "crossbar": crossbarIndex, "power": powerIndex,
                     "crossbarMeasured": measuredCrossbarIndex}


def loadSweep(path):
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    header = rows[0]
    hasStart = "window_start_unix" in header
    hasEnd = "window_end_unix" in header
    if hasStart != hasEnd:
        raise SystemExit("Sweep CSV has only one timed-region boundary column.")
    out = []
    for r in rows[1:]:
        if not r:
            continue
        d = dict(zip(header, r))
        point = {
            "target": int(float(d["target_frequency_mhz"])),
            "achieved": float(d["achieved_frequency_avg"]),
            "throughputGbs": float(d["bench_throughput"]) / 1e9,
            "powerW": float(d["power_avg_w"]),
            "memoryMhz": float(d.get("memory_clock_avg_mhz", "nan")),
        }
        if hasStart:
            try:
                point["windowStart"] = float(d["window_start_unix"]) if d["window_start_unix"] else None
                point["windowEnd"] = float(d["window_end_unix"]) if d["window_end_unix"] else None
            except ValueError:
                raise SystemExit(f"Sweep row for {point['target']} MHz has invalid timed-region stamps.")
        out.append(point)
    return out


def selectJoinMode(sweep, requested):
    """Choose time for complete new sweeps; refuse a partially stamped one."""
    if requested == "clock":
        return "clock"
    stamped = [p.get("windowStart") is not None and p.get("windowEnd") is not None
               for p in sweep]
    anyStamp = any(p.get("windowStart") is not None or p.get("windowEnd") is not None
                   for p in sweep)
    if not sweep or not all(stamped):
        if requested == "time" or anyStamp:
            raise SystemExit("Time join requires both benchmark window stamps on every sweep point.")
        return "clock"
    windows = sorted((p["windowStart"], p["windowEnd"]) for p in sweep)
    if any(start >= end for start, end in windows):
        raise SystemExit("A benchmark timed region has a non-positive duration.")
    if any(b[0] <= a[1] for a, b in zip(windows, windows[1:])):
        raise SystemExit("Benchmark timed regions overlap; HWiNFO samples would be shared.")
    return "time"


def matchTimeSamples(samples, startUnix, endUnix):
    """Keep dated HWiNFO samples inside the benchmark's inclusive timed region."""
    return [s for s in samples if startUnix <= s["timestamp"] <= endUnix]


def filterIdle(samples, minPower):
    """Drop samples taken while the card was idle between sweep points.

    This is the single most consequential line in the file. HWiNFO polls straight through the
    settle gaps, and an idle card sits at BOOST voltage, not at the voltage the locked point was
    running at. Keeping those samples pulls the per-point medians upward by an amount that grows
    with how long the gaps are - which manufactures a voltage-frequency slope out of nothing.
    Since "stock has a voltage slope and the tuned curve does not" IS the project's mechanism
    result, a defect here does not perturb a number, it invents the finding.

    A sample with no power reading at all is KEPT rather than dropped. An absent power column
    means the log never carried one, so there is nothing to filter on, and discarding every
    sample would silently produce an empty join instead of an obvious error.
    """
    return [s for s in samples if s["power"] is None or s["power"] >= minPower]


def matchSamples(samples, achievedMhz, toleranceMhz=CLOCK_TOLERANCE_MHZ):
    """Bin samples to a sweep point by the core clock they were taken at.

    Legacy sweep CSVs have no absolute timestamps, so the clock itself is the join key. The
    tolerance has to be wide enough to absorb the reported clock jitter
    within one held point and narrow enough not to reach the neighbouring point; the grid steps
    are ~75 MHz apart at the low end, so 25 MHz leaves margin on both sides.

    ⛔ THAT LAST SENTENCE IS AN ASSUMPTION ABOUT THE GRID, AND A FINE SWEEP BREAKS IT. See
    gridSpacingConflict() below - the 2026-09-15 RTX 2060 Super fine-floor sweep stepped 15 MHz
    and every second bin silently absorbed its neighbour's samples.
    """
    return [s for s in samples if abs(s["clock"] - achievedMhz) <= toleranceMhz]


def contestedSamples(samples, sweep, toleranceMhz):
    """How many samples fall within the bin of MORE THAN ONE sweep point.

    ⛔ WHY THIS EXISTS. matchSamples takes every sample within +/-tolerance of a point's achieved
    clock, so where two points sit closer than 2*tolerance they BOTH claim the samples between
    them. Nothing announces it: the join prints a full table, every point gets a voltage, and the
    only visible trace is an inflated sample count that reads as good news.

    🔑 Found on the RTX 2060 Super fine-floor sweep of 2026-09-15 - a deliberately fine 15 MHz grid
    against a tolerance written for ~75 MHz steps. 908 of its 916 loaded samples were contested.
    Re-binned at 7 MHz the per-point counts became uniform (63-80), the joined power column stopped
    being non-monotonic, and two points at the top that the wide bin had merged into one value
    separated into 0.656 and 0.662 V.

    ⚠️ THIS MEASURES THE OVERLAP RATHER THAN PREDICTING IT, AND THE DISTINCTION IS THE WHOLE POINT.
    The first version of this check compared grid SPACING against the tolerance. That flagged 92
    committed sweeps, including both RTX 3070 Ti fine sweeps whose floor table Session D's
    prediction rests on - and every one of those flags was false. Re-derived at a 7 MHz bin the
    3070 Ti voltages came back IDENTICAL to three decimal places, because a hard-locked clock
    reads at its target and its samples never reach the neighbour, however close the grid looks.
    Geometry says contamination is POSSIBLE; only the samples say it HAPPENED.

    Returns (contestedCount, totalCount).
    """
    contested = 0
    for sample in samples:
        claims = 0
        for point in sweep:
            if abs(sample["clock"] - point["achieved"]) <= toleranceMhz:
                claims += 1
                if claims > 1:
                    contested += 1
                    break
    return contested, len(samples)


def summarisePoint(matched, achievedMhz):
    """Median voltage and crossbar clock for one point, plus the crossbar-to-core ratio.

    Median rather than mean because a single sample landing in a ramp is a large outlier and
    there are only 5-7 samples per point. Crossbar is nan rather than 0.0 when the column is
    absent: the ratio is quoted in the paper, and a fabricated 0.0 would read as a stalled
    interconnect - which is exactly the effect being argued about.
    """
    voltage = statistics.median(s["voltage"] for s in matched)
    crossbars = [s["crossbar"] for s in matched if s["crossbar"] is not None]
    crossbar = statistics.median(crossbars) if crossbars else float("nan")
    ratio = crossbar / achievedMhz if crossbars else float("nan")
    return voltage, crossbar, ratio


def measuredCrossbar(matched):
    """Median measured crossbar clock for one point, or nan when no sample carries it.

    Kept apart from summarisePoint so the reported column's behaviour, which committed extracts and
    paper claims depend on, is untouched. nan rather than 0.0 for the same reason as there.
    """
    values = [s["crossbarMeasured"] for s in matched if s.get("crossbarMeasured") is not None]
    return statistics.median(values) if values else float("nan")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sweep")
    parser.add_argument("hwinfo")
    parser.add_argument("--min-power", type=float, default=IDLE_POWER_WATTS,
                        help="Discard HWiNFO samples below this GPU power; they are the idle "
                             "gaps between sweep points and sit at boost voltage.")
    parser.add_argument("--clock-tolerance", type=float, default=None,
                        help=f"Bin width in MHz around each point's achieved clock. Defaults to "
                             f"{CLOCK_TOLERANCE_MHZ}, which is written for grids stepping ~75 MHz "
                             f"or wider. A finer grid REQUIRES an explicit value - the join "
                             f"refuses rather than let neighbouring points share samples.")
    parser.add_argument("--join-by", choices=("auto", "time", "clock"), default="auto",
                        help="Use benchmark windows when present (auto), require them (time), "
                             "or force legacy clock bins (clock).")
    parser.add_argument("--hwinfo-utc-offset", type=parseUtcOffset,
                        help="UTC offset at HWiNFO collection, e.g. --hwinfo-utc-offset=-07:00. "
                             "If omitted, use this computer's local time zone.")
    args = parser.parse_args()

    sweep = loadSweep(args.sweep)
    mode = selectJoinMode(sweep, args.join_by)
    samples, indices = loadHwinfo(args.hwinfo, includeTime=(mode == "time"),
                                  utcOffset=args.hwinfo_utc_offset)
    print(f"HWiNFO columns used: {indices}")
    print(f"{len(samples)} samples, {len(sweep)} sweep points\n")

    if mode == "time":
        loaded = samples
        offsets = {sample["utcOffsetMinutes"] for sample in loaded}
        if len(offsets) > 1:
            raise SystemExit("HWiNFO log spans a UTC-offset change; split it at the time change.")
        offsetMinutes = next(iter(offsets)) if offsets else None
        print("Joining HWiNFO samples inside each benchmark timed region (inclusive).")
        if args.clock_tolerance is not None:
            print("NOTE: --clock-tolerance is ignored in a time join.")
        if args.min_power != IDLE_POWER_WATTS:
            print("NOTE: --min-power is ignored in a time join.")
        if args.hwinfo_utc_offset is None:
            print("HWiNFO Date/Time interpreted in this computer's local time zone. "
                  "Use --hwinfo-utc-offset when the log came from a different zone.")
        else:
            print(f"HWiNFO Date/Time interpreted at UTC offset {args.hwinfo_utc_offset}.")
        print("All in-window power readings are kept; the idle-power filter applies only to clock joins.\n")
    else:
        loaded = filterIdle(samples, args.min_power)
        print(f"{len(loaded)} of {len(samples)} samples are above {args.min_power} W and kept\n")

        tolerance = args.clock_tolerance if args.clock_tolerance is not None else CLOCK_TOLERANCE_MHZ
        contested, totalLoaded = contestedSamples(loaded, sweep, tolerance)
        if contested and args.clock_tolerance is None:
            spacings = sorted({round(b["achieved"] - a["achieved"])
                               for a, b in zip(sorted(sweep, key=lambda p: p["achieved"]),
                                               sorted(sweep, key=lambda p: p["achieved"])[1:])
                               if b["achieved"] - a["achieved"] >= SAME_POINT_MHZ})
            suggested = (spacings[0] / 2 - 0.5) if spacings else tolerance / 2
            print(f"*** REFUSING TO JOIN: {contested} of {totalLoaded} samples are claimed by more "
                  f"than one sweep point. ***")
            print(f"The bin is +/-{tolerance:.0f} MHz and this grid steps "
                  f"{spacings[0] if spacings else '?'} MHz, so neighbouring points share samples.")
            print("Each affected point absorbs its neighbour's readings, inflating its sample count "
                  "and pulling the median toward the wrong clock. Nothing downstream would show it.")
            print(f"Re-run with an explicit bin, e.g.  --clock-tolerance {suggested:.0f}")
            return 2
        if contested:
            print(f"NOTE: {contested} of {totalLoaded} samples are claimed by more than one point at "
                  f"this tolerance. You set it explicitly, so proceeding." + chr(10))
        print(f"binning samples within +/-{tolerance:.0f} MHz of each point's achieved clock\n")

    print(f"{'target':>7} {'achieved':>9} {'GB/s':>8} {'W':>6} {'n':>4} "
          f"{'volts':>7} {'crossbar':>9} {'xbar/core':>10}")
    merged = []
    emptyWindows = []
    for point in sweep:
        matched = (matchTimeSamples(loaded, point["windowStart"], point["windowEnd"])
                   if mode == "time" else matchSamples(loaded, point["achieved"], tolerance))
        if not matched:
            print(f"{point['target']:>7} {point['achieved']:>9.1f} "
                  f"{point['throughputGbs']:>8.1f} {point['powerW']:>6.1f} {0:>4}  (no samples)")
            if mode == "time":
                emptyWindows.append(point["target"])
            continue
        voltage, crossbar, ratio = summarisePoint(matched, point["achieved"])
        print(f"{point['target']:>7} {point['achieved']:>9.1f} {point['throughputGbs']:>8.1f} "
              f"{point['powerW']:>6.1f} {len(matched):>4} {voltage:>7.3f} {crossbar:>9.1f} {ratio:>10.3f}")
        entry = {**point, "voltage": voltage, "crossbar": crossbar,
                 "sampleCount": len(matched)}
        if mode == "time":
            entry["hwinfoUtcOffsetMinutes"] = offsetMinutes
        if indices["crossbarMeasured"] is not None:
            # Appended after the existing columns, so readers keyed by name are unaffected.
            entry["crossbarMeasured"] = measuredCrossbar(matched)
            print(f"{'':>7} measured crossbar {entry['crossbarMeasured']:>9.1f} "
                  f"(reported {crossbar:.1f})")
        merged.append(entry)

    if emptyWindows:
        print(f"REFUSING TO WRITE: no HWiNFO samples in timed regions for targets {emptyWindows} MHz. "
              "Check log coverage and the HWiNFO UTC offset.")
        return 2

    if len(merged) >= 2:
        voltages = [m["voltage"] for m in merged]
        crossbars = [m["crossbar"] for m in merged]
        print(f"\nvoltage across the swept range : {min(voltages):.3f} - {max(voltages):.3f} V "
              f"(spread {max(voltages) - min(voltages):.3f} V)")
        print(f"crossbar across the swept range: {min(crossbars):.0f} - {max(crossbars):.0f} MHz "
              f"(spread {max(crossbars) - min(crossbars):.0f} MHz)")
        coreSpread = merged[-1]["achieved"] - merged[0]["achieved"]
        print(f"core clock rose {coreSpread:.0f} MHz "
              f"({coreSpread / merged[0]['achieved']:.1%}) over the same range")

    outPath = Path(args.sweep).with_suffix("").as_posix() + "_voltage.csv"
    with open(outPath, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(merged[0].keys()) if merged else ["target"])
        writer.writeheader()
        writer.writerows(merged)
    print(f"\nwrote {outPath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
