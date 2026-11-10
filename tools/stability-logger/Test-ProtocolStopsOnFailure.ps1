<#
  Does the protocol stop when the card fails, and does it say so correctly?

  Three bugs were found here on 2026-08-30, each one while testing the fix for the previous, and
  none of them visible by reading the code. All three only appear on a run that FAILS, and the
  protocol had been run four times before that day and reported CLEAN every time - so none of
  them could ever have shown themselves. A tool that has only seen success is indistinguishable
  from one that only reports success.

    1. NO STOP. An aborted iteration was counted and the loop carried on. On a dead driver the
       workload returns no JSON and the `continue` fired with no delay, relaunching as fast as it
       could for the rest of the phase - each attempt another chance to reset the driver, on a
       card that had already given its answer.

    2. STDERR KILLED THE RUN. $ErrorActionPreference is "Stop", and on Windows PowerShell 5.1
       merging a native command's stderr with 2>&1 wraps each line in a NativeCommandError
       ErrorRecord, which under "Stop" is TERMINATING. A crashing CUDA workload prints a
       traceback to stderr, so the protocol died at that line - before recording the abort,
       before writing the iterations CSV, before computing any verdict. Exactly the run it exists
       for produced almost nothing.

    3. VERDICT PRECEDENCE INVERTED. The combined verdict is a sequence of ifs, not elseifs, so
       the LAST match wins - and INCONCLUSIVE was tested after UNSTABLE. An aborted iteration is
       a definite failure; INCONCLUSIVE means "the card was barely loaded so we cannot tell". The
       weaker one silently replaced the stronger. It bites in precisely the failure case: a crash
       kills the load, the GPU goes idle, the logger reports INCONCLUSIVE on the low loaded
       fraction, and the abort's UNSTABLE is lost. Fix 1 made this fire on EVERY abort rather
       than occasionally, because stopping the load is what produces the low loaded fraction.

  HOW THIS TESTS WITHOUT AN UNSTABLE CARD
      A workload that exists but exits non-zero writing to stderr is what a dead driver looks
      like from the protocol's point of view. It must EXIST - the preflight refuses a missing
      workload, and that guard is separate and already works.

      This runs the REAL protocol script, copied beside itself with only $workloadPy redirected,
      so $PSScriptRoot and $repoRoot still resolve. Nothing else is stubbed.

  Takes about three minutes: the telemetry logger runs its full window even after the load stops,
  deliberately, because it is what reads the Windows event log for the driver crash.

  Run: powershell -ExecutionPolicy Bypass -File tools\stability-logger\Test-ProtocolStopsOnFailure.ps1
#>

$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$protocol = Join-Path $here "Invoke-StabilityProtocol.ps1"
$scratch = Join-Path $env:TEMP ("protocol-stoptest-" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
$stub = Join-Path $scratch "failing_workload.py"
$copy = Join-Path $here "_stoptest-generated.ps1"
$outDir = Join-Path $scratch "out"

$failures = New-Object System.Collections.ArrayList
function Check([string]$description, [bool]$condition, [string]$detail = "") {
    if ($condition) { Write-Host "[PASS] $description" -ForegroundColor Green }
    else {
        Write-Host "[FAIL] $description" -ForegroundColor Red
        if ($detail) { Write-Host "  Detail: $detail" -ForegroundColor DarkGray }
        [void]$failures.Add($description)
    }
}

New-Item -ItemType Directory -Force -Path $scratch | Out-Null
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

@"
import sys
sys.stderr.write('simulated driver death: no JSON on stdout\n')
sys.exit(1)
"@ | Set-Content -Path $stub -Encoding UTF8

try {
    $text = [System.IO.File]::ReadAllText($protocol)
    $needle = '$workloadPy = Join-Path $repoRoot "tools\frequency-sweep\gpu_workload.py"'
    $occurrences = ([regex]::Matches($text, [regex]::Escape($needle))).Count
    if ($occurrences -ne 1) {
        throw "expected exactly one workloadPy assignment in the protocol, found $occurrences - the test needs updating"
    }
    [System.IO.File]::WriteAllText($copy, $text.Replace($needle, '$workloadPy = "' + $stub + '"'))

    Write-Host ""
    Write-Host "Running the real protocol against a workload that always fails..." -ForegroundColor Cyan
    $output = & powershell.exe -ExecutionPolicy Bypass -File $copy `
        -SessionLabel "stoptest" `
        -AppliedSettings "STOP-PATH TEST - workload deliberately fails, not a real measurement" `
        -DurationMinutes 2 -SoakMinutes 1 -OutputDirectory $outDir 2>&1
    $joined = ($output | ForEach-Object { "$_" }) -join "`n"

    Write-Host ""

    # Bug 1. Before the fix this looped for the whole phase. One attempt, and only one.
    $attempts = ([regex]::Matches($joined, "simulated driver death")).Count
    Check "the load stops after the first failure rather than relaunching" ($attempts -eq 1) `
          "workload was launched $attempts time(s)"
    Check "it says why it stopped" ($joined -match "STOPPING: the workload produced no JSON")
    Check "the second phase is skipped, not run into the same failure" ($joined -match "Phase membw SKIPPED")

    # Bug 2. The run must survive the workload's stderr and still produce its own artifacts.
    $iterCsv = @(Get-ChildItem $outDir -Filter "*_stability_iterations.csv" -ErrorAction SilentlyContinue)
    $protoJson = @(Get-ChildItem $outDir -Filter "*_stability_protocol.json" -ErrorAction SilentlyContinue)
    Check "the iterations CSV is written despite the workload writing to stderr" ($iterCsv.Count -eq 1) `
          "found $($iterCsv.Count)"
    Check "the protocol JSON is written despite the workload writing to stderr" ($protoJson.Count -eq 1) `
          "found $($protoJson.Count)"

    # Bug 3. An abort is a definite failure and must not be downgraded by a weaker signal.
    if ($protoJson.Count -eq 1) {
        $record = Get-Content $protoJson[0].FullName -Raw | ConvertFrom-Json
        Check "an aborted iteration is recorded" ($record.aborted_iterations -ge 1) `
              "aborted_iterations=$($record.aborted_iterations)"
        Check "the verdict is UNSTABLE, not downgraded to INCONCLUSIVE" ($record.verdict -eq "UNSTABLE") `
              "verdict=$($record.verdict)"
        # The point of the previous check: the logger genuinely DOES report INCONCLUSIVE here,
        # because the card really was idle. The test is that the abort outranks it.
        Check "the logger still reports INCONCLUSIVE, so the escalation is what is being tested" `
              ($joined -match "telemetry verdict: INCONCLUSIVE")
    }
}
finally {
    Remove-Item $copy -Force -ErrorAction SilentlyContinue
    Remove-Item $scratch -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
if ($failures.Count -gt 0) {
    Write-Host ("FAILED CHECKS: " + ($failures -join ", ")) -ForegroundColor Red
    exit 1
}
Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
exit 0
