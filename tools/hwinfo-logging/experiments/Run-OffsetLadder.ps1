<#
.SYNOPSIS
    Worklist 4o, REGISTERED-PREDICTIONS.md section 7: stock Profile 3, then four
    NVML P0 offset suites at 0 / -150 / -300 / 0 MHz.

.DESCRIPTION
    This runner changes GPU state. It applies Profile 3 BEFORE any offset, checks
    stock memory under load, then runs 12 logged 13-point sweeps at each offset:
    0, -150, -300, then 0 again. The closing stock suite is a drift bracket; the
    draft's -450 rung was dropped at review because it shared -300's prediction.
    Each NVML write, including the reset before the closing suite, is verified
    by Set-NvmlClockOffset.ps1. The offset is reset and read back in finally,
    including after a failed sweep or Ctrl+C.

    Requires an elevated shell and HWiNFO64 Sensors open. -WhatIfOnly prints
    the fixed plan without accessing HWiNFO, Afterburner, NVML or the GPU.
#>
param([switch]$WhatIfOnly)
$ErrorActionPreference = "Stop"
$repo = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
$wrapper = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$offsetTool = Join-Path $repo "tools\nvml-offset\Set-NvmlClockOffset.ps1"
$ab = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$jobPath = "C:\headroom-bench\job.json"
$stockMemMhz = 13801

# Exact counts in both rep1 and rep2 _sweep.json workload_command fields under
# data/frequency-sweeps/5060ti-stock-repro-20260922/ (not new calibrations).
$workloads = @(
    [pscustomobject]@{name="copy"; iterations=2660},
    [pscustomobject]@{name="reduce"; iterations=2870},
    [pscustomobject]@{name="softmax"; iterations=2600},
    [pscustomobject]@{name="layernorm"; iterations=1597},
    [pscustomobject]@{name="bgemm32"; iterations=2673},
    [pscustomobject]@{name="bgemm64"; iterations=2661},
    [pscustomobject]@{name="bgemm128"; iterations=2467},
    [pscustomobject]@{name="bgemm256"; iterations=1579},
    [pscustomobject]@{name="bgemm1024"; iterations=414},
    [pscustomobject]@{name="attention"; iterations=147},
    [pscustomobject]@{name="conv"; iterations=151},
    [pscustomobject]@{name="gemm"; iterations=120}
)
$rungs = @(
    [pscustomobject]@{tag="offset0"; mhz=0},
    [pscustomobject]@{tag="offsetm150"; mhz=-150},
    [pscustomobject]@{tag="offsetm300"; mhz=-300},
    [pscustomobject]@{tag="offset0close"; mhz=0}
)

function Say([string]$message, [string]$color="White") {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $message) -ForegroundColor $color
}

function Get-MemClockUnderLoad {
    $python = (Get-Command python).Source
    $workload = Join-Path $repo "tools\frequency-sweep\gpu_workload.py"
    $probe = Start-Job -ScriptBlock {
        param($py, $script)
        & $py $script --workload gemm --iterations 400 --json 2>&1 | Out-Null
    } -ArgumentList $python, $workload
    $reads = @()
    try {
        Start-Sleep -Seconds 3
        for ($i=0; $i -lt 6; $i++) {
            $value = (& nvidia-smi --query-gpu=clocks.mem --format=csv,noheader,nounits) |
                Select-Object -First 1
            $parsed = 0
            if ([int]::TryParse($value, [ref]$parsed)) { $reads += $parsed }
            Start-Sleep -Milliseconds 400
        }
        Wait-Job $probe -Timeout 60 | Out-Null
    }
    finally {
        if ($probe.State -eq "Running") { Stop-Job $probe -ErrorAction SilentlyContinue }
        Remove-Job $probe -Force -ErrorAction SilentlyContinue
    }
    if ($reads.Count -eq 0) { return -1 }
    return ($reads | Measure-Object -Maximum).Maximum
}

function Run-Sweep([string]$tag, [int]$mhz, $work) {
    $label = "5060ti-4o-$tag-$($work.name)"
    $job = @{
        label=$label; workload=$work.name; minMhz=1237; maxMhz=3090
        frequencyCount=13; descending=$false; iterations=[string]$work.iterations
        expectedMinutes=10
        appliedSettings=("4o offset ladder, registered section 7, suite $tag. Stock Profile 3 verified under load at 13801 MHz. " +
            "NVML P0 graphics offset $mhz MHz, verified by read-back before sweep. " +
            "13-point ascending 1237-3090 MHz grid, HWiNFO SensorInterval 500. " +
            "Iterations $($work.iterations) from 5060ti-stock-repro-20260922. " +
            "No Afterburner profile applied after the offset.")
    }
    $job | ConvertTo-Json | Set-Content -Path $jobPath -Encoding UTF8
    Say "Running $label" "Cyan"
    # Out-Host prevents the wrapper's output from becoming this function's
    # return value; a returned array would corrupt the caller's exit-code test.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -JobPath $jobPath | Out-Host
    $code = $LASTEXITCODE
    Say "Wrapper exit $code for $label"
    return [int]$code
}

Say "4o: stock Profile 3, 13 targets, 12 workloads, offsets 0/-150/-300/0 (closing drift bracket)."
Say "48 sweeps total; stock-repro-20260922 iteration counts; final offset reset in finally."
if ($WhatIfOnly) {
    foreach ($rung in $rungs) {
        Say ("{0}: {1} MHz, {2} workloads" -f $rung.tag, $rung.mhz, $workloads.Count)
    }
    Say "WhatIfOnly: plan only; no GPU state or files changed." "Yellow"
    exit 0
}

# Refuse before any GPU write if another measurement is already running. In
# particular, do not enter the reset-in-finally block and disturb its offset.
$busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -match
        'Invoke-(Frequency|Logged)Sweep[.]ps1|gpu_workload[.]py|Run-(ActivityAB|OffsetPrecondition|OffsetLadder)[.]ps1'
})
if ($busy.Count -gt 0) {
    Say "Another GPU measurement is running. Refusing before changing GPU state." "Red"
    exit 3
}

$failed = $false
$resetOk = $false
try {
    if (-not (Get-Process -Name "HWiNFO64" -ErrorAction SilentlyContinue)) {
        throw "HWiNFO64 is not running. Open Sensors before the session."
    }
    foreach ($path in @($wrapper, $offsetTool, $ab)) {
        if (-not (Test-Path $path)) { throw "Required tool missing: $path" }
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $jobPath -Parent) | Out-Null

    # No exit-code check: MSIAfterburner.exe is a GUI program, so PowerShell does not reliably set
    # LASTEXITCODE for it and a stale or null value would throw here. The memory-clock witness
    # below is the verification. (Fixed at review, 2026-09-22.)
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    $mem = Get-MemClockUnderLoad
    Say "Memory clock under load: $mem MHz (stock reference $stockMemMhz)."
    if ($mem -lt 0 -or [math]::Abs($mem - $stockMemMhz) -gt 100) {
        throw "Stock Profile 3 was not verified by memory clock."
    }
    $powerLine = (& nvidia-smi --query-gpu=power.limit,power.default_limit --format=csv,noheader,nounits) |
        Select-Object -First 1
    $powerFields = @($powerLine -split ',')
    $currentPower = 0.0
    $defaultPower = 0.0
    if ($LASTEXITCODE -ne 0 -or $powerFields.Count -ne 2 -or
        -not [double]::TryParse($powerFields[0].Trim(), [ref]$currentPower) -or
        -not [double]::TryParse($powerFields[1].Trim(), [ref]$defaultPower) -or
        [math]::Abs($currentPower - 180) -gt 0.5 -or
        [math]::Abs($defaultPower - 180) -gt 0.5) {
        throw "Power limit/default were not verified as the stock 180/180 W."
    }
    Say "Power limit $currentPower W, default $defaultPower W verified."

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offsetTool -Reset | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Initial 0 MHz offset did not verify." }

    # On 2026-09-23 a first sweep's preflight refused at 26% SM, drawn by the Claude desktop app
    # rendering the driving agent's message. Let the desktop settle before the first preflight.
    Say "Waiting 90 s for the desktop to settle before the first preflight." "Yellow"
    Start-Sleep -Seconds 90

    foreach ($rung in $rungs) {
        # Every suite sets its own offset and verifies it, so the closing stock
        # suite cannot inherit -300 from the suite before it.
        if ($rung.mhz -eq 0) {
            Say "Setting NVML P0 graphics offset to 0 MHz for $($rung.tag)." "Yellow"
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offsetTool -Reset | Out-Host
        }
        else {
            Say "Setting NVML P0 graphics offset to $($rung.mhz) MHz for $($rung.tag)." "Yellow"
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offsetTool -SetMhz $rung.mhz | Out-Host
        }
        if ($LASTEXITCODE -ne 0) { throw "Offset $($rung.mhz) MHz for $($rung.tag) did not verify." }
        foreach ($work in $workloads) {
            if ((Run-Sweep $rung.tag $rung.mhz $work) -ne 0) {
                throw "Sweep failed at $($rung.tag)/$($work.name); remaining sweeps skipped."
            }
        }
    }
}
catch {
    Say ("Ladder stopped: " + $_.Exception.Message) "Red"
    $failed = $true
}
finally {
    # No script-level return here: it could mask failure. This runs after normal
    # completion, a thrown error, or Ctrl+C, and verifies the 0 MHz read-back.
    Say "Resetting NVML P0 graphics offset to 0 MHz and verifying read-back." "Cyan"
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offsetTool -Reset | Out-Host
        $resetOk = ($LASTEXITCODE -eq 0)
    }
    catch {
        Say ("Offset reset raised an error: " + $_.Exception.Message) "Red"
        $resetOk = $false
    }
    if (-not $resetOk) {
        Say "OFFSET RESET DID NOT VERIFY. Reset it manually or reboot before using this card." "Red"
    }
}
if ($failed -or -not $resetOk) { exit 7 }
Say "Offset ladder complete; NVML offset read back 0 MHz." "Green"
exit 0
