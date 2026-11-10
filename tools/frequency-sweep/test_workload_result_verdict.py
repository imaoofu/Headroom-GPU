"""
Known-answer checks for WorkloadResultVerdict.ps1.

WHY THIS FUNCTION NEEDS TESTS AT ALL
    It is the only thing standing between the operator and the failure it was written for: on
    2026-09-12 a sweep locked clocks, sampled telemetry, wrote a CSV and exited 0 without ever
    launching its workload. Every performance column was empty and the power column was the
    genuine idle draw of a locked card, so nothing downstream errored either. An hour of wall
    clock produced a file that looked like data.

    A defect in the verdict therefore does not shift a number. It decides whether that hour is
    spent, and whether the resulting file is labelled.

THE SUBTLE CASES, each of which a careless implementation gets wrong with no error
    - PowerShell 5.1 reads a re-parsed CSV back as STRINGS, so a round-tripped row says "True"
      rather than $true. A check written against the boolean alone passes in memory and fails
      on a file.
    - The workload emits `ok: true` with NO throughput for a calibration run. Accepting ok on
      its own would pass a sweep that measured nothing.
    - The workload emits a throughput alongside `ok: false` when it aborts partway. Accepting
      throughput on its own would pass a run the benchmark itself declared failed.
    - A sweep with NO workload command is a legitimate mode that samples an external load. It
      must come back "not-applicable", not "none" - marking it failed would make the guard
      something operators route around.

WHY THIS SHELLS OUT TO POWERSHELL
    The function lives in PowerShell because the sweep does, and the repo's runner is Python.
    Invoke-FrequencySweep.ps1 takes a param block and changes GPU state on load, which is why
    the function was split into its own file: this suite dot-sources that file alone and needs
    no GPU, no elevation and no driver.

Run: python tools/frequency-sweep/test_workload_result_verdict.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parent / "WorkloadResultVerdict.ps1"

# Windows PowerShell 5.1 FIRST, because that is what the sweep actually runs under and several of
# its behaviours are version-specific. pwsh is a fallback so the suite is not simply absent on a
# Linux runner - but a pass under pwsh is weaker evidence, and the banner below says which ran
# rather than letting the distinction disappear into a green tick.
SHELL = shutil.which("powershell") or shutil.which("pwsh")

if SHELL is None:
    # CI runs this matrix on ubuntu-latest as well as windows-latest, and neither shell need be
    # present. Exiting 0 with an explicit sentence is deliberate: the alternative is a red build
    # on a platform the tool under test cannot run on, which trains people to ignore red.
    print("[SKIP] test_workload_result_verdict: no PowerShell on this platform, so "
          "WorkloadResultVerdict.ps1 was NOT exercised in this run. The sweep's guard against a "
          "workload that never launched is therefore unverified here - it is verified on the "
          "windows-latest leg, which is the platform the sweep runs on.")
    raise SystemExit(0)

print(f"[INFO] Exercising WorkloadResultVerdict.ps1 through {Path(SHELL).name}.")
if Path(SHELL).name.lower().startswith("pwsh"):
    print("[INFO] This is PowerShell 7, NOT the 5.1 the sweep runs under. Version-specific "
          "behaviour - notably how @() enumerates ConvertFrom-Json output - differs between "
          "them, so a pass here does not stand in for the windows-latest leg.")

failures = []


def check(description, condition, detail=""):
    if not condition:
        print(f"[FAIL] {description}")
        if detail:
            print(f"  Detail: {detail}")
        failures.append(description)
    else:
        print(f"[PASS] {description}")


def verdictFor(rows, workloadCommanded=True):
    """Run the real PowerShell function over rows given as JSON, and return its result."""
    script = (
        f". '{HELPER}';"
        # Two PowerShell 5.1 traps in one line, both of which made every scenario report exactly
        # one row - so the suite ran green-ish against nothing.
        #   $input is EMPTY under -Command, and @($null) has a Count of ONE.
        #   @(ConvertFrom-Json ...) is also ONE, because the array arrives as a single object;
        #   it must be assigned to a variable BEFORE @() will enumerate it.
        "$parsed = ConvertFrom-Json ([Console]::In.ReadToEnd());"
        "$rows = @($parsed);"
        f"$v = Get-WorkloadResultVerdict -Rows $rows -WorkloadCommanded ${workloadCommanded};"
        "$v | ConvertTo-Json -Compress"
    )
    # -ExecutionPolicy Bypass applies to THIS process only and changes no system setting. It is
    # needed because the default policy refuses to dot-source a .ps1 from a freshly spawned
    # shell, which is how this suite differs from an operator running the sweep interactively.
    #
    # It is WINDOWS ONLY. Execution policy does not exist on Linux or macOS, and pwsh there
    # rejects the switch outright rather than ignoring it - which would fail the ubuntu leg of CI
    # for a reason that has nothing to do with the code under test.
    command = [SHELL, "-NoProfile", "-NonInteractive"]
    if sys.platform == "win32":
        command += ["-ExecutionPolicy", "Bypass"]
    command += ["-Command", script]
    completed = subprocess.run(
        command, input=json.dumps(rows), capture_output=True, text=True, timeout=120)
    # PowerShell returned exit 0 while failing to load the script at all when this was written,
    # so the exit code is not sufficient evidence that anything ran. Empty stdout is.
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit("PowerShell produced no verdict "
                         f"(rc {completed.returncode}): {completed.stderr.strip()[:400]}")
    return json.loads(completed.stdout.strip())


def row(ok, throughput):
    return {"bench_ok": ok, "bench_throughput": throughput}


# Test 1: the failure this exists for. Every point launched, none returned a number.
dead = verdictFor([row(None, None) for _ in range(13)])
check("thirteen empty points give verdict 'none'", dead["verdict"] == "none",
      f"verdict was {dead['verdict']!r}")
check("none-verdict counts every point as measured", dead["measured"] == 13,
      f"measured was {dead['measured']!r}")
check("none-verdict counts no results", dead["withResult"] == 0,
      f"withResult was {dead['withResult']!r}")
check("none-verdict message names the workload as the cause",
      "workload did not run" in dead["message"].lower(),
      f"message was {dead['message']!r}")

# Test 2: a healthy sweep.
good = verdictFor([row(True, 15.7) for _ in range(13)])
check("thirteen good points give verdict 'ok'", good["verdict"] == "ok",
      f"verdict was {good['verdict']!r}")
check("ok-verdict reports nothing missing", good["missing"] == 0,
      f"missing was {good['missing']!r}")

# Test 3: one point failed out of thirteen. This must NOT be treated as a dead run - a single
# frequency can legitimately fail while the rest of the curve is sound.
partial = verdictFor([row(True, 15.7)] * 12 + [row(None, None)])
check("one bad point in thirteen gives verdict 'partial'", partial["verdict"] == "partial",
      f"verdict was {partial['verdict']!r}")
check("partial-verdict reports the missing count", partial["missing"] == 1,
      f"missing was {partial['missing']!r}")
check("partial-verdict says the rows are missing, not zero",
      "rather than as" in partial["message"],
      f"message was {partial['message']!r}")

# Test 4: STRING round-trip. PowerShell 5.1 reads a CSV back with every cell a string, so the
# same data that passes as objects must also pass as "True" / "15.7".
stringy = verdictFor([row("True", "15.7") for _ in range(3)])
check("string 'True' and '15.7' still count as a result", stringy["verdict"] == "ok",
      f"verdict was {stringy['verdict']!r}, withResult {stringy['withResult']!r}")

# Test 5: a calibration record - ok with no throughput. Accepting ok alone would pass this.
calibration = verdictFor([row(True, None) for _ in range(3)])
check("ok with no throughput does NOT count as a result", calibration["verdict"] == "none",
      f"verdict was {calibration['verdict']!r}")

# Test 6: an aborted run - a throughput alongside ok false. Accepting throughput alone would
# pass this.
aborted = verdictFor([row(False, 9.9) for _ in range(3)])
check("throughput with ok false does NOT count as a result", aborted["verdict"] == "none",
      f"verdict was {aborted['verdict']!r}")

# Test 7: zero and negative throughput are not measurements.
zero = verdictFor([row(True, 0) for _ in range(3)])
check("zero throughput does not count as a result", zero["verdict"] == "none",
      f"verdict was {zero['verdict']!r}")

# Test 8: a non-numeric throughput cell.
junk = verdictFor([row(True, "n/a") for _ in range(3)])
check("non-numeric throughput does not count as a result", junk["verdict"] == "none",
      f"verdict was {junk['verdict']!r}")

# Test 9: the no-workload mode. Sampling an external load is legitimate and must not be failed,
# or the guard becomes something operators learn to ignore.
external = verdictFor([row(None, None) for _ in range(5)], workloadCommanded=False)
check("no workload commanded gives 'not-applicable'", external["verdict"] == "not-applicable",
      f"verdict was {external['verdict']!r}")
check("not-applicable still reports how many points were measured", external["measured"] == 5,
      f"measured was {external['measured']!r}")

# Test 10: a workload commanded but nothing measured at all - distinct message, same verdict.
empty = verdictFor([])
check("no points at all with a workload gives 'none'", empty["verdict"] == "none",
      f"verdict was {empty['verdict']!r}")
check("empty run says no point was measured",
      "no frequency point was measured" in empty["message"],
      f"message was {empty['message']!r}")

if failures:
    print(f"FAILED: {', '.join(failures)}")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
