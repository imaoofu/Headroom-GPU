<#
.SYNOPSIS
    Register the scheduled task that lets an unelevated agent trigger a logged sweep.

.DESCRIPTION
    Run this ONCE, from an elevated shell. It creates a task named "headroom-bench" that runs
    Invoke-LoggedSweep.ps1 with highest privileges. After that, an unelevated process - a
    computer-use agent, an ordinary shell, anything - can start a bench run with:

        schtasks /run /tn headroom-bench

    🔑 WHY THIS INDIRECTION IS NECESSARY, NOT MERELY TIDY
        HWiNFO runs elevated and nvidia-smi clock locking requires administrator. UIPI forbids a
        medium-integrity process from injecting input into an elevated window, and a packaged
        MSIX app - which is what the Codex desktop agent is - can never be elevated, because its
        manifest has no allowElevation. So the agent cannot click HWiNFO's button and cannot run
        the sweep. It CAN start a task it has been granted, and that is the supported path.

        ✅ It is also better than the agent driving the GUI: the agent takes no screenshots
        during the run, so it cannot reproduce the 9.38% contamination measured on 2026-09-18.

    🛑 WHAT YOU ARE AUTHORISING
        You are granting standing elevated execution of ONE FIXED SCRIPT. That is why
        Invoke-LoggedSweep.ps1 builds its own workload command from a whitelisted name and
        derives its own output path - the job file is a request, never an instruction. Read the
        NOTES block in that script before changing anything about how the job is validated.

.PARAMETER TaskName
    Defaults to headroom-bench.

.PARAMETER Remove
    Unregister the task instead of creating it.

.EXAMPLE
    .\Register-BenchTask.ps1
    .\Register-BenchTask.ps1 -Remove
#>

[CmdletBinding()]
param(
    [string]$TaskName = "headroom-bench",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

function Say([string]$t, [string]$c = "White") { Write-Host $t -ForegroundColor $c }

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Say "This must run from an ELEVATED shell - registering a highest-privileges task needs it." "Red"
    Say "Right-click PowerShell -> Run as administrator, then run this again." "Yellow"
    exit 1
}

if ($Remove) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) { Say "No task named '$TaskName'." "Yellow"; exit 0 }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Say "Removed '$TaskName'." "Green"
    exit 0
}

$wrapper = Join-Path $PSScriptRoot "Invoke-LoggedSweep.ps1"
if (-not (Test-Path $wrapper)) { Say "Cannot find $wrapper" "Red"; exit 1 }

$benchRoot = "C:\headroom-bench"
foreach ($d in @($benchRoot, (Join-Path $benchRoot "results"))) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null; Say "created $d" "Gray" }
}

$jobPath = Join-Path $benchRoot "job.json"
if (-not (Test-Path $jobPath)) {
    # A template, deliberately INVALID to run: no appliedSettings worth the name, so a stray
    # trigger validates and refuses rather than sweeping something nobody chose.
    [pscustomobject]@{
        label           = "template-do-not-run"
        workload        = "gemm"
        minMhz          = 1380
        maxMhz          = 1760
        frequencyCount  = 13
        descending      = $false
        iterations      = ""
        expectedMinutes = 15
        appliedSettings = ""
    } | ConvertTo-Json | Set-Content -Path $jobPath -Encoding UTF8
    Say "wrote a refusing template job to $jobPath" "Gray"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -JobPath "{1}"' -f $wrapper, $jobPath)

# No trigger: this task exists to be run on demand, never on a schedule. A bench run must
# never start because a clock said so - the machine has to be verified quiet first.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew

$taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Settings $settings `
    -Principal $taskPrincipal -Description "Headroom: one logged GPU sweep, driven by C:\headroom-bench\job.json" -Force | Out-Null

Say ""
Say "Registered '$TaskName' with highest privileges." "Green"
Say ""
Say "To run one sweep, without elevation:" "Cyan"
Say "  1. write the job:  C:\headroom-bench\job.json" "Gray"
Say "  2. trigger it   :  schtasks /run /tn $TaskName" "Gray"
Say "  3. read back    :  C:\headroom-bench\results\<stamp>_<label>\wrapper-result.json" "Gray"
Say ""
Say "Check the plan without touching the GPU first:" "Cyan"
Say ('  powershell -File "{0}" -JobPath "{1}" -WhatIfOnly' -f $wrapper, $jobPath) "Gray"
Say ""
# NOTE: keep non-ASCII OUT of string literals in .ps1 files. These files carry no BOM (neither
# does any other PowerShell tool here), so PowerShell 5.1 reads them as ANSI: a UTF-8 emoji
# becomes several cp1252 bytes, and inside a QUOTED STRING that breaks the terminator and the
# script will not parse. In a COMMENT the same mangling is harmless, which is why the emoji
# elsewhere in this repo's .ps1 files have never caused trouble. Found 2026-09-21, before this
# ever ran - it would have failed inside the scheduled task with a bare syntax error.
Say "HWiNFO must already be running with its Sensors window open. The wrapper does not" "Yellow"
Say "launch it - the splash and update nag are extra state to get wrong." "Yellow"
exit 0
