"""Read-only regression checks for the sweep's achieved-clock report."""

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("ClockBuckets.ps1")
SHELL = shutil.which("powershell") or shutil.which("pwsh")

if SHELL is None:
    print("[SKIP] test_clock_buckets: PowerShell is unavailable on this platform.")
    raise SystemExit(0)


def clock_counts(batches):
    script = (
        f". '{HELPER}';"
        "$parsed = ConvertFrom-Json ([Console]::In.ReadToEnd());"
        # Wrapped in an object: PowerShell 7 (CI's Linux leg) unrolls a top-level JSON array
        # and 5.1 does not, which turned each batch into single rows on Linux and counted 1.
        "$batches = @($parsed.batches);"
        "$counts = @(foreach ($batch in $batches) {"
        "  $rows = @($batch);"
        "  $targets = @($rows | ForEach-Object { [double]$_.target_frequency_mhz });"
        "  @(Get-ClockGroups -Rows $rows -TargetFrequencies $targets).Count"
        "});"
        "ConvertTo-Json -InputObject $counts -Compress"
    )
    command = [SHELL, "-NoProfile", "-NonInteractive"]
    if sys.platform == "win32":
        command += ["-ExecutionPolicy", "Bypass"]
    result = subprocess.run(command + ["-Command", script], input=json.dumps({"batches": batches}),
                            text=True, capture_output=True, timeout=30)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(f"ClockBuckets.ps1 failed: {result.stderr.strip()}")
    return json.loads(result.stdout.strip())


def clock_count(rows):
    return clock_counts([rows])[0]


def rows_at(relative):
    with (ROOT / relative).open(newline="", encoding="utf-8-sig") as source:
        return list(csv.DictReader(source))


cases = [
    ("data/frequency-sweeps/rtx2060s-finefloor-20260915/"
     "20260915-160921_rtx2060s-finefloor-gemm_sweep.csv", 10, 13),
    ("data/frequency-sweeps/5060ti-finefloor-20260918/"
     "20260918-201559_5060ti-finefloor-gemm_sweep.csv", 13, 13),
    ("data/frequency-sweeps/5060ti-finefloor-20260918/"
     "20260918-202543_5060ti-finefloor-gemm-r2_sweep.csv", 13, 13),
    ("data/frequency-sweeps/5060ti-finefloor-20260922/"
     "20260922-093857_5060ti-4h-floorend-r1_sweep.csv", 4, 13),
    ("data/frequency-sweeps/5060ti-finefloor-20260922/"
     "20260922-094425_5060ti-4h-floorend-r2_sweep.csv", 4, 13),
]

for path, historical, expected in cases:
    rows = rows_at(path)
    assert all(row["lock_held"] == "True" for row in rows), path
    old = len({round(float(row["achieved_frequency_avg"]) / 25) for row in rows})
    actual = clock_count(rows)
    assert old == historical and actual == expected, (path, old, actual)
    print(f"[PASS] {Path(path).name}: historical {old}, corrected {actual}")

# Coarse grids keep the old 25 MHz rule exactly. Check every committed sweep with a
# minimum target gap of at least 50 MHz, including runs whose locks did not hold.
coarse_rows = []
coarse_expected = []
for path in (ROOT / "data/frequency-sweeps").rglob("*_sweep.csv"):
    rows = rows_at(path.relative_to(ROOT))
    targets = sorted({float(row["target_frequency_mhz"]) for row in rows})
    if len(targets) < 2 or min(b - a for a, b in zip(targets, targets[1:])) < 50:
        continue
    old = len({round(float(row["achieved_frequency_avg"]) / 25) for row in rows})
    coarse_rows.append(rows)
    coarse_expected.append((path, old))
assert coarse_rows
for (path, old), actual in zip(coarse_expected, clock_counts(coarse_rows)):
    assert old == actual, (path, old, actual)
print(f"[PASS] {len(coarse_rows)} committed coarse sweeps retain their historical counts")

# Separate targets that genuinely clip to the same achieved clock still count once.
clipped = [{"target_frequency_mhz": target, "achieved_frequency_avg": achieved}
           for target, achieved in [(1500, 1492), (1508, 1492), (1515, 1507)]]
assert clock_count(clipped) == 2
print("[PASS] clipped duplicate achieved clocks remain one group")
