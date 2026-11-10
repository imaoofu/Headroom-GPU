"""
Known-answer checks for ThrottleReasons.ps1.

WHY THIS NEEDS TESTS AT ALL
    The throttle decode has been wrong twice, and both times it produced a plausible answer
    rather than an error.

    The first time, an [ordered] dictionary indexed by integer did a positional lookup instead of
    a key lookup, so 0x1 decoded as "ApplicationsClocksSetting" instead of "GpuIdle" and every
    reason was shifted by one. The second, found 2026-09-12, is subtler: the bit table stopped at
    0x100, and a mask MIXING known and unknown bits dropped the unknown part without trace. A
    mask of 0x604 read "SwPowerCap" and the 0x600 simply disappeared.

    That matters because 0x400 is not rare. It appears in 0 of 102 sweeps on driver 610.88 and in
    82 of 82 on 616.56 - it arrived with a driver update - and in 48 of the 53 samples of the one
    real driver crash this project has recorded, beginning at the first sample after the reset.

WHAT IS DELIBERATELY NOT TESTED HERE
    What 0x200 and 0x400 MEAN. Nobody knows, this project does not guess, and a test asserting a
    meaning would encode the guess as fact.

Run: python tools/stability-logger/test_throttle_reasons.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parent / "ThrottleReasons.ps1"

# Windows PowerShell 5.1 first: that is the version the logger runs under. pwsh is a fallback so
# the suite is not simply absent on a Linux CI runner.
SHELL = shutil.which("powershell") or shutil.which("pwsh")

if SHELL is None:
    print("[SKIP] test_throttle_reasons: no PowerShell on this platform, so ThrottleReasons.ps1 "
          "was NOT exercised in this run. It is verified on the windows-latest leg, which is the "
          "platform the stability logger runs on.")
    raise SystemExit(0)

failures = []


def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"  Detail: {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")


def decode(masks):
    """Decode a list of hex masks through the real PowerShell function."""
    script = (
        f". '{HELPER}';"
        "$masks = ConvertFrom-Json ([Console]::In.ReadToEnd());"
        "$out = @();"
        "foreach ($m in @($masks)) {"
        "  $r = ConvertTo-ThrottleReasonList -HexMask $m;"
        "  $out += [pscustomobject]@{"
        "    mask = $m; reasons = $r;"
        "    concerning = [bool](Test-ThrottleReasonsConcerning -Reasons $r);"
        "    unknown = [bool](Test-ThrottleReasonsUnknown -Reasons $r) } };"
        "ConvertTo-Json -Compress -InputObject @($out)"
    )
    command = [SHELL, "-NoProfile", "-NonInteractive"]
    if sys.platform == "win32":
        command += ["-ExecutionPolicy", "Bypass"]
    command += ["-Command", script]
    completed = subprocess.run(command, input=json.dumps(masks),
                               capture_output=True, text=True, timeout=120)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit("PowerShell produced no decode "
                         f"(rc {completed.returncode}): {completed.stderr.strip()[:400]}")
    parsed = json.loads(completed.stdout.strip())
    return {row["mask"]: row for row in (parsed if isinstance(parsed, list) else [parsed])}


MASKS = ["0x0000000000000000", "0x0000000000000001", "0x0000000000000004",
         "0x0000000000000024", "0x0000000000000400", "0x0000000000000600",
         "0x0000000000000604", "0x0000000000000404", "0x0000000000000008"]
d = decode(MASKS)

# Test 1: the positional-lookup regression. 0x1 is GpuIdle, not the next entry along.
check("0x1 decodes as GpuIdle", d["0x0000000000000001"]["reasons"] == "GpuIdle",
      f"got {d['0x0000000000000001']['reasons']!r}")
check("0x4 decodes as SwPowerCap", d["0x0000000000000004"]["reasons"] == "SwPowerCap",
      f"got {d['0x0000000000000004']['reasons']!r}")
check("0x0 decodes as None", d["0x0000000000000000"]["reasons"] == "None",
      f"got {d['0x0000000000000000']['reasons']!r}")

# Test 2: THE BUG THIS FILE EXISTS FOR. A mask mixing known and unknown bits must report BOTH.
# 0x604 = SwPowerCap (0x4) plus an unaccounted 0x600.
mixed = d["0x0000000000000604"]["reasons"]
check("0x604 still reports the known SwPowerCap", "SwPowerCap" in mixed, f"got {mixed!r}")
check("0x604 ALSO reports the leftover 0x600 rather than dropping it",
      "Unknown:0x600" in mixed, f"got {mixed!r}")
check("0x404 reports leftover 0x400 beside SwPowerCap",
      "SwPowerCap" in d["0x0000000000000404"]["reasons"]
      and "Unknown:0x400" in d["0x0000000000000404"]["reasons"],
      f"got {d['0x0000000000000404']['reasons']!r}")

# Test 3: a mask of only unknown bits.
check("0x400 alone reports Unknown:0x400",
      d["0x0000000000000400"]["reasons"] == "Unknown:0x400",
      f"got {d['0x0000000000000400']['reasons']!r}")
check("0x600 alone reports Unknown:0x600",
      d["0x0000000000000600"]["reasons"] == "Unknown:0x600",
      f"got {d['0x0000000000000600']['reasons']!r}")

# Test 4: unknown bits are FLAGGED but NOT escalated. 0x400 covers 589 of 603 samples in a
# healthy stock baseline; making it concerning would turn every post-616.56 run red.
check("0x400 is marked unknown", d["0x0000000000000400"]["unknown"] is True)
check("0x400 is NOT marked concerning", d["0x0000000000000400"]["concerning"] is False)

# Test 5: genuinely concerning bits still escalate. 0x24 = SwThermalSlowdown + SwPowerCap, and
# exactly one sweep in this repository carries it.
thermal = d["0x0000000000000024"]
check("0x24 decodes both SwPowerCap and SwThermalSlowdown",
      "SwPowerCap" in thermal["reasons"] and "SwThermalSlowdown" in thermal["reasons"],
      f"got {thermal['reasons']!r}")
check("0x24 is concerning", thermal["concerning"] is True)
check("0x24 is not marked unknown", thermal["unknown"] is False)
check("0x8 HwSlowdown is concerning", d["0x0000000000000008"]["concerning"] is True,
      f"got {d['0x0000000000000008']!r}")

# Test 6: a known-good mask must not be flagged unknown, or the flag means nothing.
check("0x1 is not marked unknown", d["0x0000000000000001"]["unknown"] is False)
check("0x1 is not concerning", d["0x0000000000000001"]["concerning"] is False)

# Test 7: malformed input degrades rather than throwing.
bad = decode(["", "nonsense"])
check("an empty mask returns 'unknown'", bad[""]["reasons"] == "unknown",
      f"got {bad['']['reasons']!r}")
check("an unparseable mask says so", bad["nonsense"]["reasons"].startswith("unparsed:"),
      f"got {bad['nonsense']['reasons']!r}")

if failures:
    print(f"FAILED: {', '.join(failures)}")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
