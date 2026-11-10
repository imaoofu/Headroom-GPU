<#
  Does the stability logger actually NOTICE a failure?

  The logger has never been tested against one. It has only ever been run on sessions that
  went fine, which means a logger that unconditionally reported CLEAN would have looked
  identical so far. ROADMAP lists this as [CORE] and it has sat undone since the beginning.

  Three cases, and the first one is the reason this is a real test rather than a formality:

    1. POSITIVE CONTROL - sustained load for the whole window. Must report CLEAN.
       Without this, a logger stuck on INCONCLUSIVE would "pass" cases 2 and 3.
    2. LOAD NEVER STARTS - logger runs over an idle GPU. Must NOT report CLEAN.
       This is the failure mode the logger's own comments say was found the hard way: a
       session reported CLEAN with plausible-looking averages that described an idle card.
    3. LOAD DIES PARTWAY - load covers roughly a third of the window, then stops. Must NOT
       report CLEAN. This is what a stress test crashing actually looks like from here.

  Exit codes from the logger carry the verdict: 0 CLEAN, 1 FLAGGED, 2 UNSTABLE, 3 INCONCLUSIVE.
#>

$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$repoRoot = Split-Path (Split-Path $here -Parent) -Parent
$python = "C:\Users\Raymond\AppData\Local\Programs\Python\Python312\python.exe"
$workloadScript = Join-Path $repoRoot "tools\frequency-sweep\gpu_workload.py"
$outputDir = Join-Path $repoRoot "data\stability-runs\logger-selftest-20260820"
$logger = Join-Path $here "Log-GpuStability.ps1"

$WINDOW = 45

function Start-Load {
    param([int]$Iterations)
    # membw rather than gemm: far lower power for the same utilisation, and this test cares
    # only that the card is busy.
    return Start-Process -FilePath $python `
        -ArgumentList $workloadScript, "--workload", "membw", "--iterations", $Iterations, "--json" `
        -PassThru -WindowStyle Hidden
}

function Invoke-Case {
    param([string]$Name, [string]$Label, [int]$LoadIterations, [string]$Expectation)

    Write-Host ""
    Write-Host "=== $Name" -ForegroundColor Cyan
    Write-Host "    expecting: $Expectation" -ForegroundColor Gray

    $proc = $null
    if ($LoadIterations -gt 0) { $proc = Start-Load -Iterations $LoadIterations }

    & $logger -SessionLabel $Label `
        -AppliedSettings "memory +2500, core V/F curve at stock" `
        -TestMethod "logger self-test: $Name" `
        -DurationSeconds $WINDOW -IntervalSeconds 1 -OutputDirectory $outputDir | Out-Null
    $code = $LASTEXITCODE

    # Let the load finish on its own wherever possible. Stop-Process -Force on a process with
    # live CUDA kernels makes the driver reset the GPU context and log nvlddmkm Error 153,
    # which the logger then correctly reports as a driver reset - contaminating the NEXT case
    # with an event this harness caused. That is exactly what happened on the first run of this
    # test: the idle case came back UNSTABLE because of a kill issued 1 second earlier.
    if ($null -ne $proc -and -not $proc.HasExited) {
        $proc | Stop-Process -Force
        Write-Host "    (load force-stopped; settling before next case)" -ForegroundColor DarkGray
    }
    # Settle regardless, so any driver event lands BEFORE the next logger window opens rather
    # than inside it.
    Start-Sleep -Seconds 12

    $verdict = switch ($code) { 0 {"CLEAN"} 1 {"FLAGGED"} 2 {"UNSTABLE"} 3 {"INCONCLUSIVE"} default {"UNKNOWN($code)"} }
    Write-Host "    got: $verdict" -ForegroundColor Yellow
    return $verdict
}

Write-Host "Each case takes $WINDOW seconds. Three cases plus load settling."

# The idle case runs FIRST. It is the one that needs a pristine Windows event log, because it
# is the only case whose expected verdict can be flipped by a stray driver event from a
# previous case's teardown.
$r2 = Invoke-Case -Name "load never starts (idle GPU)" -Label "selftest-idle" `
    -LoadIterations 0 -Expectation "NOT CLEAN, and no crash flag"
# ~1500 iterations is roughly 12-15 s, about a third of the window, and it exits on its own.
$r3 = Invoke-Case -Name "load dies partway" -Label "selftest-loaddies" `
    -LoadIterations 1500 -Expectation "NOT CLEAN"
# ~7000 iterations comfortably outlasts a 45 s window, so this one gets force-stopped. It runs
# last so its teardown cannot contaminate anything.
$r1 = Invoke-Case -Name "positive control (load throughout)" -Label "selftest-loaded" `
    -LoadIterations 7000 -Expectation "CLEAN"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
$failures = @()
if ($r1 -ne "CLEAN")  { $failures += "positive control returned $r1, expected CLEAN - the logger cannot certify a good run" }
if ($r2 -eq "CLEAN")  { $failures += "idle GPU returned CLEAN - the logger cannot tell load from no load" }
if ($r3 -eq "CLEAN")  { $failures += "load dying partway returned CLEAN - the logger cannot notice a stress test crashing" }

if ($failures.Count -eq 0) {
    Write-Host " VERDICT: the logger discriminates. CLEAN=$r1  idle=$r2  died=$r3" -ForegroundColor Green
} else {
    Write-Host " VERDICT: the logger does NOT discriminate:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
}
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "Logs: $outputDir"
exit $failures.Count
