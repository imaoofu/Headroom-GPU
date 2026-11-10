"""Distil the NVIDIA memory clock inside each sweep's benchmark window, from HWiNFO and from the sweep
CSV (nvidia-smi), into <sweep dir>/hwinfo-memory-in-window.csv. Written 2026-10-01 for section 14.

    python tools/xbar/hwinfo_memory_in_window.py <sweep dir> <raw HWiNFO dir>

HWiNFO's GPU memory clock is the raw value; x8 is the effective clock nvidia-smi reports. HWiNFO
times are local; the UTC offset below is PDT, correct for 2026-10-01 only."""
import csv, glob, datetime, os, sys
base = sys.argv[1]; rawdir = sys.argv[2]
tz = datetime.timezone(datetime.timedelta(hours=-7))  # HWiNFO local time, PDT on 2026-10-01
out = []
for raw in sorted(glob.glob(os.path.join(rawdir, "*-hwinfo.csv"))):
    label = os.path.basename(raw).replace("-hwinfo.csv", "")
    rows = list(csv.reader(open(raw, encoding="latin-1")))
    h = rows[0]
    # The PC also has an AMD iGPU with its own "GPU Memory Clock" column; the NVIDIA block is the
    # one that carries "GPU Crossbar Clock", so take the memory-clock columns nearest before it.
    x = h.index("GPU Crossbar Clock [MHz]")
    m = max(i for i, c in enumerate(h) if c == "GPU Memory Clock [MHz]" and i < x)
    mm = h.index("GPU Memory Clock (measured) [MHz]")
    assert x - m < 6 and 0 < mm - x < 4, (label, m, x, mm)
    sweep = glob.glob(os.path.join(base, f"*_{label}_sweep.csv"))
    assert len(sweep) == 1, label
    for s in csv.DictReader(open(sweep[0], encoding="utf-8-sig")):
        ws, we = float(s["window_start_unix"]), float(s["window_end_unix"])
        vals = []; meas = []
        for r in rows[1:]:
            try: t = datetime.datetime.strptime(r[0] + " " + r[1], "%d.%m.%Y %H:%M:%S.%f").replace(tzinfo=tz).timestamp()
            except Exception: continue
            if ws <= t <= we: vals.append(float(r[m])); meas.append(float(r[mm]))
        out.append([label, s["target_frequency_mhz"], len(vals), min(vals), max(vals), min(meas), max(meas), s["memory_clock_min_mhz"], s["memory_clock_max_mhz"]])
with open(os.path.join(base, "hwinfo-memory-in-window.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["label", "target", "hwinfoSamples", "hwinfoGpuMemoryClockMin", "hwinfoGpuMemoryClockMax", "hwinfoMeasuredMin", "hwinfoMeasuredMax", "nvsmiMemoryMin", "nvsmiMemoryMax"])
    w.writerows(out)
print(len(out), "points"); print(sorted(set((r[3], r[4]) for r in out)), min(r[5] for r in out), max(r[6] for r in out), min(r[2] for r in out))
