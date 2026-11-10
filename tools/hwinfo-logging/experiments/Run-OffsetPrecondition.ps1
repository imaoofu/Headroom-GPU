<#
.SYNOPSIS
    Worklist item 4c: does the 0.720 V load floor survive an NVML clock offset? Registered in
    docs/REGISTERED-PREDICTIONS.md section 6 BEFORE it runs. CHANGES GPU STATE: applies Afterburner
    Profile 3 (stock), writes an NVML P0 graphics offset of -300 MHz, and always resets it to 0.

.DESCRIPTION
    A - B - A on one grid, stock Profile 3 throughout, gemm, ascending:
      A1  no offset
      B   -300 MHz NVML P0 graphics offset, verified by read-back
      A2  offset reset to 0 and verified; closes the drift bracket and proves the reset took

    GRID 1000-1700 MHz, 15 points, 50 MHz apart. The worklist said 1380-1760, which was wrong for
    this question: a -300 MHz shift should move the floor end from ~1570 to ~1270, BELOW that band,
    so it could not tell "two regions, shifted" from "no floor at all". This band holds both. And
    because 300 is six 50 MHz steps, B at f pairs with A at f+300 on the same grid for 4d.

    The offset is ALWAYS reset in a finally block, then read back, whatever happens to the sweeps.
    Requires an elevated shell and HWiNFO already open with its Sensors window.
#>
$ErrorActionPreference = "Continue"
$repo    = "C:\Users\Raymond\Documents\headroom"
$wrapper = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$offset  = Join-Path $repo "tools\nvml-offset\Set-NvmlClockOffset.ps1"
$ab      = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$STOCK_MEM = 13801
$OFFSET_MHZ = -300

function Say([string]$t, [string]$c = "White") { Write-Host ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $t) -ForegroundColor $c }

function Get-MemClockUnderLoad {
    $py = (Get-Command python).Source
    $wl = Join-Path $repo "tools\frequency-sweep\gpu_workload.py"
    $j = Start-Job -ScriptBlock { param($p, $w) & $p $w --workload gemm --iterations 400 --json 2>&1 | Out-Null } -ArgumentList $py, $wl
    Start-Sleep -Seconds 3
    $reads = @()
    for ($i = 0; $i -lt 6; $i++) {
        $v = (& nvidia-smi --query-gpu=clocks.mem --format=csv,noheader,nounits) | Select-Object -First 1
        $n = 0; if ([int]::TryParse($v, [ref]$n)) { $reads += $n }
        Start-Sleep -Milliseconds 400
    }
    Wait-Job $j -Timeout 60 | Out-Null; Remove-Job $j -Force -ErrorAction SilentlyContinue
    if ($reads.Count -eq 0) { return -1 }
    return ($reads | Measure-Object -Maximum).Maximum
}

function Run-Sweep([string]$label, [string]$state) {
    $job = @{
        label = $label; workload = "gemm"; minMhz = 1000; maxMhz = 1700; frequencyCount = 15
        descending = $false; iterations = ""; expectedMinutes = 9
        appliedSettings = ("stock Profile 3 verified by memory clock. NVML P0 graphics offset: " + $state +
            ". HWiNFO SensorInterval 500, ASCENDING 1000-1700, 15 points. Worklist 4c, registered in " +
            "REGISTERED-PREDICTIONS.md section 6 before collection. OPERATOR PRESENT for the first offset write.")
    }
    $job | ConvertTo-Json | Set-Content -Path "C:\headroom-bench\job.json" -Encoding UTF8
    Say ("==== " + $label + " (offset " + $state + ") ====") "Cyan"
    # Out-Host, or the wrapper's printed lines become part of this function's return value and
    # "-ne 0" on that array is always true.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -JobPath "C:\headroom-bench\job.json" | Out-Host
    $code = $LASTEXITCODE
    Say ("  wrapper exit " + $code)
    return $code
}

if (-not (Get-Process -Name "HWiNFO64" -ErrorAction SilentlyContinue)) {
    Say "HWiNFO64 is not running. Open it and its Sensors window first." "Red"; exit 3
}

& $ab -profile3 -q
Start-Sleep -Seconds 8
$mem = Get-MemClockUnderLoad
Say ("Memory clock under load: {0} MHz (stock is {1})." -f $mem, $STOCK_MEM)
if ($mem -lt 0 -or $mem -gt ($STOCK_MEM + 200)) { Say "Not verifiably on stock. Refusing." "Red"; exit 5 }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offset -Status
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offset -Reset
if ($LASTEXITCODE -ne 0) { Say "Could not confirm a 0 MHz offset before starting. Refusing." "Red"; exit 6 }

$failed = $false
try {
    # No "return" in here: at script level it would exit with code 0 and skip the failure exit.
    if ((Run-Sweep "5060ti-4c-offset0-a1" "0 MHz, verified by read-back") -ne 0) { $failed = $true }

    if (-not $failed) {
        Say "Writing the -300 MHz offset - the first offset write on this card." "Yellow"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offset -SetMhz $OFFSET_MHZ | Out-Host
        if ($LASTEXITCODE -ne 0) { Say "The offset write did not verify. Stopping." "Red"; $failed = $true }
    }
    if (-not $failed) {
        if ((Run-Sweep "5060ti-4c-offsetm300-b" "-300 MHz, verified by read-back") -ne 0) { $failed = $true }
    }
}
finally {
    Say "Resetting the NVML offset to 0 and reading it back." "Cyan"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offset -Reset
    if ($LASTEXITCODE -ne 0) {
        Say "** THE OFFSET DID NOT VERIFY AT 0. Run Set-NvmlClockOffset.ps1 -Reset by hand, or reboot. **" "Red"
        $failed = $true
    }
}
if ($failed) { exit 7 }

if ((Run-Sweep "5060ti-4c-offset0-a2" "0 MHz after reset, verified by read-back") -ne 0) { exit 7 }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $offset -Status
Say "A - B - A complete. The offset is back at 0." "Green"
