<#
.SYNOPSIS
    The 5060 Ti's unattended queue for 2026-09-24, operator away: 4n, then 4m, then the activity A/B
    re-run, then back to stock. Stops at the first failure, reports it and leaves the card on stock.

.DESCRIPTION
    4n  EXPLORATORY, no prediction (docs/GPU-WORKLIST-5060TI.md): is the membw stall at 1627 MHz a
        notch or a change of slope? membw 1550-1710 MHz, 13 points (~13 MHz apart), ascending, on
        stock P3 and the split curve P5, in the order P3 P5 P5 P3.
    4m  REGISTERED, docs/REGISTERED-PREDICTIONS.md section 9: stock P3, the suite grid, reduce and
        copy in the order R C C R R C C R, with the suite iteration counts.
    A/B REGISTERED, section 5 plus its 2026-09-24 amendment: Run-ActivityAB.ps1 unchanged except
        for the generator trigger.

    Each sweep goes through Invoke-LoggedSweep.ps1, which does its own preflight, HWiNFO log start
    and stop, and a clock reset. Needs an ELEVATED shell; HWiNFO is started by
    Start-HwinfoSensors.ps1 if it is not already up.
#>
$ErrorActionPreference = "Continue"
$repo    = "C:\Users\Raymond\Documents\headroom"
$wrapper = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$ab      = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$log     = "C:\headroom-bench\results\queue-20260924-$(Get-Date -Format HHmmss).log"
New-Item -ItemType Directory -Force -Path "C:\headroom-bench\results" | Out-Null

function Say([string]$t) { $line = "[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $t; Write-Host $line; Add-Content -Path $log -Value $line }

function Get-MemClockUnderLoad {
    $py = (Get-Command python).Source
    $wl = Join-Path $repo "tools\frequency-sweep\gpu_workload.py"
    $j = Start-Job -ScriptBlock { param($p, $w) & $p $w --workload gemm --iterations 400 --json 2>&1 | Out-Null } -ArgumentList $py, $wl
    # Sample only while the load is actually running. The first run of this queue (09:07) read the
    # idle 810 MHz: a fixed 3 s wait was shorter than a cold PyTorch start, so no read was under load.
    $reads = @()
    $until = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $until -and $reads.Count -lt 6 -and $j.State -eq 'Running') {
        $row = ((& nvidia-smi --query-gpu=utilization.gpu,clocks.mem --format=csv,noheader,nounits) | Select-Object -First 1) -split ','
        $u = 0; $n = 0
        if ($row.Count -eq 2 -and [int]::TryParse($row[0].Trim(), [ref]$u) -and $u -ge 50 -and [int]::TryParse($row[1].Trim(), [ref]$n)) { $reads += $n }
        Start-Sleep -Milliseconds 400
    }
    Wait-Job $j -Timeout 90 | Out-Null; Remove-Job $j -Force -ErrorAction SilentlyContinue
    if ($reads.Count -eq 0) { return -1 }
    return ($reads | Measure-Object -Maximum).Maximum
}

# Apply a slot and verify it by what it changes: memory under load and the power limit.
function Set-Profile([int]$slot) {
    $expect = @{ 3 = @(13801, 180.0); 5 = @(16301, 200.0) }[$slot]
    & $ab "-profile$slot" -q
    Start-Sleep -Seconds 8
    $mem = Get-MemClockUnderLoad
    $plText = (& nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits) | Select-Object -First 1
    $pl = 0.0; [void][double]::TryParse($plText, [ref]$pl)
    Say ("Profile {0}: memory under load {1} MHz (expect {2}), power limit {3} W (expect {4})." -f $slot, $mem, $expect[0], $pl, $expect[1])
    if ([math]::Abs($mem - $expect[0]) -gt 200 -or [math]::Abs($pl - $expect[1]) -gt 0.5) {
        Say "Profile $slot is NOT verifiably applied. Stopping."
        return $false
    }
    return $true
}

function Invoke-Sweep($job) {
    $job | ConvertTo-Json | Set-Content -Path "C:\headroom-bench\job.json" -Encoding UTF8
    Say ("==== {0} ====" -f $job.label)
    $out = "C:\headroom-bench\results\queue-20260924-$($job.label)-wrapper.log"
    $p = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper, "-JobPath", "C:\headroom-bench\job.json") `
        -RedirectStandardOutput $out -RedirectStandardError ($out + ".err")
    $null = $p.Handle   # PS 5.1: read now so ExitCode survives
    $p.WaitForExit()
    Say ("  wrapper exit {0}" -f $p.ExitCode)
    return ($p.ExitCode -eq 0)
}

function Stop-Queue([string]$why) {
    Say "STOPPED: $why"
    & $ab -profile3 -q
    Say "Profile 3 (stock) applied on the way out."
    exit 1
}

Say "Queue 2026-09-24 starting. Log: $log"
& (Join-Path $repo "tools\hwinfo-logging\Start-HwinfoSensors.ps1") | ForEach-Object { Say $_ }
if ($LASTEXITCODE -ne 0) { Stop-Queue "HWiNFO Sensors not ready (exit $LASTEXITCODE)." }

$driver = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader) | Select-Object -First 1

# ---- 4n ---------------------------------------------------------------------------------------
$k = @{ 3 = 0; 5 = 0 }
foreach ($slot in @(3, 5, 5, 3)) {
    if (-not (Set-Profile $slot)) { Stop-Queue "4n profile check failed." }
    $k[$slot]++
    $name = @{ 3 = "stock P3"; 5 = "split curve P5" }[$slot]
    $job = @{ label = ("5060ti-4n-membw1627-p{0}-r{1}" -f $slot, $k[$slot]); workload = "membw"
              minMhz = 1550; maxMhz = 1710; frequencyCount = 13; descending = $false; iterations = ""; expectedMinutes = 8
              appliedSettings = ("4n EXPLORATORY (no prediction): membw stall at 1627 MHz, {0}, 1550-1710 13 points ascending, " +
                  "HWiNFO SensorInterval 500, driver {1}, OPERATOR ABSENT, driving agent idle, order P3 P5 P5 P3") -f $name, $driver }
    if (-not (Invoke-Sweep $job)) { Stop-Queue "4n sweep $($job.label) failed." }
}

# ---- 4m ---------------------------------------------------------------------------------------
if (-not (Set-Profile 3)) { Stop-Queue "4m stock check failed." }
$order = @("reduce", "copy", "copy", "reduce", "reduce", "copy", "copy", "reduce")
$iterations = @{ reduce = "2870"; copy = "2660" }
for ($i = 0; $i -lt $order.Count; $i++) {
    $w = $order[$i]
    $job = @{ label = ("5060ti-4m-{0:D2}-{1}" -f ($i + 1), $w); workload = $w
              minMhz = 1237; maxMhz = 3090; frequencyCount = 13; descending = $false; iterations = $iterations[$w]; expectedMinutes = 10
              appliedSettings = ("4m REGISTERED section 9: stock P3 verified, suite grid 1237-3090 13 points ascending, sweep {0} of 8 in " +
                  "R C C R R C C R, iterations {1} from 5060ti-stock-repro-20260922, driver {2}, OPERATOR ABSENT, driving agent idle") -f ($i + 1), $iterations[$w], $driver }
    if (-not (Invoke-Sweep $job)) { Stop-Queue "4m sweep $($job.label) failed." }
}

# ---- A/B --------------------------------------------------------------------------------------
Say "==== activity A/B re-run (section 5, amended 2026-09-24) ===="
$abOut = "C:\headroom-bench\results\queue-20260924-activity-ab.log"
& (Join-Path $repo "tools\hwinfo-logging\experiments\Run-ActivityAB.ps1") *>&1 | Tee-Object -FilePath $abOut | Out-Null
$abExit = $LASTEXITCODE
Say "  Run-ActivityAB exit $abExit (output in $abOut)"
& $ab -profile3 -q
Say "Profile 3 (stock) applied. Queue finished."
if ($abExit -ne 0) { exit 1 }
exit 0
