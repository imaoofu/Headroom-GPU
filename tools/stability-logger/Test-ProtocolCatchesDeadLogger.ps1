<#
.SYNOPSIS
    Positive control: prove Invoke-StabilityProtocol.ps1 refuses when its logger fails to start.

.DESCRIPTION
    On 2026-08-23 the protocol harness started its telemetry logger with Start-Process
    -ArgumentList, which does not reliably quote array elements containing spaces. The settings
    string split, "TEST" landed on -IntervalSeconds, and the logger died on parameter binding
    before writing a single sample.

    The harness did not notice. It ran a full six-minute load phase against a dead logger, then
    read that process's exit code of 1, mapped it through its own verdict table to FLAGGED, and
    printed a combined verdict. **The failure did not look like a failure.** It produced a
    plausible telemetry verdict from a component that had never sampled anything, and had the
    exit code been 0 it would have said CLEAN.

    That is the same class of defect as the INCONCLUSIVE verdict the logger itself gained on
    2026-08-20, one level up: a tool that cannot distinguish "the telemetry is clean" from "there
    is no telemetry".

    This test reintroduces the exact bug into a COPY of the harness and asserts that it now
    refuses, quickly, without running any load. A fix verified only against the working case is
    not verified - which is the lesson Test-LoggerCatchesFailure.ps1 recorded when two mutations
    survived because the check asserted an outcome the mutation also produced.

.EXAMPLE
    .\Test-ProtocolCatchesDeadLogger.ps1
#>

param(
    [switch]$KeepCopy
)

$ErrorActionPreference = "Stop"

$harness = Join-Path $PSScriptRoot "Invoke-StabilityProtocol.ps1"
$copy = Join-Path $PSScriptRoot "_deadlogger-control.ps1"

if (-not (Test-Path $harness)) { Write-Host "Missing: $harness" -ForegroundColor Red; exit 2 }

$passed = 0
$failed = 0
function Check([string]$name, [bool]$ok, [string]$detail) {
    if ($ok) { Write-Host "  [PASS] $name" -ForegroundColor Green; $script:passed++ }
    else { Write-Host "  [FAIL] $name - $detail" -ForegroundColor Red; $script:failed++ }
}

Write-Host ""
Write-Host "Positive control: harness must refuse a logger that cannot start" -ForegroundColor Cyan
Write-Host ""

# ---- build the broken copy ----
# The bug is restored by swapping the explicitly quoted command line back for the array form.
# Editing a copy rather than the real script means production code is never the thing under test.

$src = Get-Content $harness -Raw
$start = $src.IndexOf('$loggerArgs = (')
$end = $src.IndexOf('$loggerErr = ')
if ($start -lt 0 -or $end -lt 0 -or $end -le $start) {
    Write-Host "  [FAIL] could not locate the logger argument block to mutate." -ForegroundColor Red
    Write-Host "         Invoke-StabilityProtocol.ps1 has been restructured; update this test." -ForegroundColor Yellow
    exit 1
}
$brokenLine = '$loggerArgs = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$loggerPs1,' +
              '"-SessionLabel",$SessionLabel,"-AppliedSettings",$AppliedSettings,' +
              '"-TestMethod","x","-DurationSeconds",$loggerSeconds,"-OutputDirectory",$OutputDirectory)'
Set-Content -Path $copy -Value ($src.Substring(0, $start) + $brokenLine + "`n`n" + $src.Substring($end)) -Encoding UTF8

try {
    $t0 = Get-Date
    # The settings string MUST contain a space for the bug to bite. That is the whole mechanism.
    # The harness reports through Write-Host, which writes to the HOST and never enters the
    # pipeline - so `& $copy 2>&1` captures none of its messages and every text assertion below
    # would fail against an empty string while the messages sat visibly on screen. That happened
    # on the first version of this test. Run it as a child process with the console redirected.
    $capture = Join-Path $env:TEMP "deadlogger-control-out.txt"
    $captureErr = Join-Path $env:TEMP "deadlogger-control-err.txt"

    # Explicitly quoted, for the same reason the harness is. The first version of this test passed
    # an -ArgumentList ARRAY and hit the very bug it exists to detect: the settings string split
    # and "with" landed on the harness's own -DegradationPercent, so the harness died on parameter
    # binding and never reached the code under test. Two levels of the same mistake in one file.
    # -AllowVideoEngines because this control is about the LOGGER refusing to start, and without
    # it the run depends on whether a browser tab happens to be decoding video: the harness would
    # exit 5 at the preflight instead of exit 2 at the logger, and the test would report a failure
    # that says nothing about the code. The video guard has its own coverage.
    $childArgs = ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -SessionLabel "deadloggercontrol" ' +
                  '-AppliedSettings "POSITIVE CONTROL with spaces that will split" ' +
                  '-DurationMinutes 2 -SoakMinutes 1 -AllowVideoEngines') -f $copy
    $child = Start-Process -FilePath "powershell.exe" -PassThru -Wait -NoNewWindow `
                           -RedirectStandardOutput $capture -RedirectStandardError $captureErr `
                           -ArgumentList $childArgs
    $exit = $child.ExitCode
    $elapsed = ((Get-Date) - $t0).TotalSeconds

    # Both streams, and forced to a single string - Get-Content on a missing or empty file yields
    # $null or an array, and `-match` against either returns something that is not a Boolean, which
    # makes every assertion below fail with a type error rather than a useful message.
    $text = ""
    foreach ($f in @($capture, $captureErr)) {
        if (Test-Path $f) {
            $chunk = (Get-Content $f -Raw -ErrorAction SilentlyContinue)
            if ($null -ne $chunk) { $text += [string]$chunk }
            Remove-Item $f -Force -ErrorAction SilentlyContinue
        }
    }

    Check "refuses (exit 2)" ($exit -eq 2) "got exit $exit"

    # The point is refusing BEFORE the load, not after. A harness that runs thirty minutes and
    # then reports the logger was dead has wasted the run and, worse, still had to decide what to
    # say about telemetry it never collected.
    Check "refuses before running any load (under 30s)" ($elapsed -lt 30) ("took {0:N0}s" -f $elapsed)
    Check "says the logger did not start" ($text -match "logger did not start") "message missing"
    Check "surfaces the logger's own stderr" ($text -match "IntervalSeconds") "root cause not shown"
    Check "states that no load was run" ($text -match "No load was run") "message missing"
    Check "prints no verdict" (-not ($text -match "VERDICT:")) "a verdict was printed anyway"

    # Nothing should have been written for a run that never happened.
    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $outDir = Join-Path $repoRoot "data\stability-runs"
    $leaked = @(Get-ChildItem $outDir -Filter "*deadloggercontrol*" -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like "*_iterations.csv" -or $_.Name -like "*_protocol.json" })
    Check "writes no iterations or verdict file" ($leaked.Count -eq 0) ("{0} file(s) left behind" -f $leaked.Count)

    # The stderr capture files ARE expected - they are the diagnostic. Clean them up.
    Get-ChildItem $outDir -Filter "*deadloggercontrol*" -ErrorAction SilentlyContinue | Remove-Item -Force
}
finally {
    if (-not $KeepCopy) { Remove-Item $copy -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "$passed passed, $failed failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })
Write-Host ""
if ($failed -gt 0) { exit 1 }
exit 0
