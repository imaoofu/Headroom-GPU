<#
.SYNOPSIS
    The activity A/B test, registered in docs/REGISTERED-PREDICTIONS.md section 5 BEFORE it runs.
    Separates machine activity from warm-up and run order as the cause of isolated 8-11 pct
    throughput losses.

.DESCRIPTION
    WHY. On 2026-09-22 three stock 4i replicates lost 8-11 pct at 4, then 2, then 0 isolated points
    while the driving agent went from busy to silent. An outside audit found that agent activity,
    run order and time since a cold start all changed TOGETHER, so the data cannot say which one
    mattered. This design breaks that tie:

      - warm-up is removed: the script waits until the machine has been up 30 minutes, then runs
        two throwaway warm-up sweeps that are excluded from scoring in advance
      - run order is balanced: S A A S, three times, so a linear time trend cancels
      - activity is the ONLY thing that differs: "A" runs start Start-ActivityLoad.ps1 once the
        sweep wrapper's HWiNFO log appears (after preflight, before the first point; REVISED
        2026-09-24, it used to wait for GPU load), "S" runs start nothing. Both conditions do the
        same waiting, so that part is symmetric.

    Same configuration throughout: stock Profile 3, gemm, 1380-1760 MHz, 13 points, ascending -
    the grid the losses were found on. 14 sweeps, about 85 minutes.

    WHAT IT CHANGES: applies Afterburner Profile 3 (stock) and locks clocks through the existing
    sweep, which always resets them. Nothing else. Requires an ELEVATED shell and HWiNFO already
    running with its Sensors window open - launching HWiNFO needs a UAC approval only a person
    can give.

    Score it with: python analysis/score_activity_ab.py <experiment directory>
#>
# The registered values, fixed rather than parameters: the 2026-09-22 preflight review noted that
# caller-supplied overrides could run something other than the registered collection.
$MinUptimeMinutes = 30
$Blocks = 3
$ErrorActionPreference = "Continue"
$repo      = "C:\Users\Raymond\Documents\headroom"
$wrapper   = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$generator = Join-Path $repo "tools\hwinfo-logging\experiments\Start-ActivityLoad.ps1"
$ab        = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$STOCK_MEM = 13801

function Say([string]$t, [string]$c = "White") { Write-Host ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $t) -ForegroundColor $c }

$expDir = "C:\headroom-bench\results\activity-ab-$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Force -Path $expDir | Out-Null
Say "Experiment directory: $expDir" "Cyan"

# ---- 1. HWiNFO must already be running; this script cannot start it ------------------------------
if (-not (Get-Process -Name "HWiNFO64" -ErrorAction SilentlyContinue)) {
    Say "HWiNFO64 is not running. Open it and its Sensors window first - launching it needs UAC approval." "Red"
    exit 3
}

# ---- 2. uptime gate: removes the cold-start confound -------------------------------------------
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
while (((Get-Date) - $boot).TotalMinutes -lt $MinUptimeMinutes) {
    $left = $MinUptimeMinutes - ((Get-Date) - $boot).TotalMinutes
    Say ("Machine has been up {0:F0} min; waiting {1:F0} more so a cold start cannot be the cause." -f ((Get-Date) - $boot).TotalMinutes, $left) "Yellow"
    Start-Sleep -Seconds 60
}
Say ("Uptime {0:F0} min. Boot time {1}." -f ((Get-Date) - $boot).TotalMinutes, $boot) "Green"

# ---- 3. apply and VERIFY stock ----------------------------------------------------------------
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
& $ab -profile3 -q
Start-Sleep -Seconds 8
$mem = Get-MemClockUnderLoad
Say ("Memory clock under load: {0} MHz (stock is {1})." -f $mem, $STOCK_MEM)
# Two-sided since the preflight review: the first version accepted ANY lower memory clock.
if ($mem -lt ($STOCK_MEM - 200) -or $mem -gt ($STOCK_MEM + 200)) {
    Say "The card is NOT verifiably on stock (memory). Refusing to run." "Red"
    exit 5
}
$plText = (& nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits) | Select-Object -First 1
$pl = 0.0
if (-not [double]::TryParse($plText, [ref]$pl) -or [math]::Abs($pl - 180.0) -gt 0.5) {
    Say "Power limit reads '$plText', not the stock 180 W. Refusing to run." "Red"
    exit 5
}
Say "Stock verified: memory $mem MHz under load, power limit $pl W. The core curve itself cannot be read back; Profile 3 is the verified stock slot." "Green"

# ---- 4. the schedule, fixed here and in the registration --------------------------------------
$schedule = @(@{ tag = "warmup-1"; cond = "warmup" }, @{ tag = "warmup-2"; cond = "warmup" })
$n = 0
for ($b = 1; $b -le $Blocks; $b++) {
    foreach ($c in @("silent", "active", "active", "silent")) {
        $n++
        $schedule += @{ tag = ("{0:D2}-{1}" -f $n, $c); cond = $c }
    }
}

function Wait-ForLogStart([string]$label, [datetime]$since, [int]$timeoutSeconds) {
    # REVISED 2026-09-24, before re-collection (REGISTERED-PREDICTIONS section 5): the first version
    # waited for GPU utilisation >= 50%, and in 3 of 6 active runs that WAS the sweep's first measured
    # point, so the generator started 0.1-0.2 s late. The wrapper creates its HWiNFO log only after
    # preflight passes and before the sweep starts, so waiting for that file starts the generator
    # ahead of every measured window. Identical in both conditions, so the waiting cannot differ.
    $until = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $until) {
        $dirs = @(Get-ChildItem "C:\headroom-bench\results" -Directory -Filter ("*_" + $label) -ErrorAction SilentlyContinue |
            Where-Object { $_.CreationTime -ge $since })
        foreach ($d in $dirs) { if (Test-Path (Join-Path $d.FullName ($label + "-hwinfo.csv"))) { return $true } }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

$records = @()
foreach ($s in $schedule) {
    $label = "5060ti-actab-" + $s.tag
    $uptime = [math]::Round(((Get-Date) - $boot).TotalMinutes, 1)
    $job = @{
        label = $label; workload = "gemm"; minMhz = 1380; maxMhz = 1760; frequencyCount = 13
        descending = $false; iterations = ""; expectedMinutes = 8
        appliedSettings = ("stock Profile 3 verified by memory clock ($mem MHz). HWiNFO SensorInterval 500, " +
            "ASCENDING 1380-1760, 13 points, driver 616.92, OPERATOR ABSENT. ACTIVITY A/B TEST, condition " +
            $s.cond.ToUpper() + ", uptime $uptime min at start. Registered in REGISTERED-PREDICTIONS.md " +
            "section 5 before collection. Driving agent silent; any activity is the scripted generator.")
    }
    $job | ConvertTo-Json | Set-Content -Path "C:\headroom-bench\job.json" -Encoding UTF8

    Say ("==== {0}  ({1}) ====" -f $label, $s.cond.ToUpper()) "Cyan"
    $out = Join-Path $expDir ($s.tag + "-wrapper.log")
    $runStart = (Get-Date).AddSeconds(-1)
    $p = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper, "-JobPath", "C:\headroom-bench\job.json") `
        -RedirectStandardOutput $out -RedirectStandardError ($out + ".err")
    $null = $p.Handle   # PS 5.1: without touching Handle, ExitCode can come back null after exit

    $gen = $null
    $events = $null
    $genExit = $null
    $genKilled = $false
    $loaded = $false
    $stop = Join-Path $expDir ($s.tag + ".stop")
    try {
        $loaded = Wait-ForLogStart $label $runStart 300
        if ($s.cond -eq "active") {
            if ($loaded) {
                $events = Join-Path $expDir ($s.tag + "-events.csv")
                $gen = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden `
                    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $generator, "-EventLog", $events, "-StopFile", $stop)
                $null = $gen.Handle
                Say "  activity generator started" "Yellow"
            } else {
                Say "  HWiNFO log never appeared - generator NOT started; this run will be scored as invalid" "Red"
            }
        }
        $p.WaitForExit()
    }
    finally {
        # Stop the generator whatever happened, so it can never outlive its run into the next one.
        if ($gen) {
            New-Item -ItemType File -Path $stop -Force | Out-Null
            if (-not $gen.WaitForExit(30000)) { $gen.Kill(); $genKilled = $true; [void]$gen.WaitForExit(10000) }
            $genExit = $gen.ExitCode
            Say ("  activity generator stopped (exit {0}, killed {1})" -f $genExit, $genKilled) "Yellow"
        }
    }
    $exit = $p.ExitCode
    Say ("  wrapper exit {0}" -f $exit)
    # Record the exact sweep CSV, so the scorer never has to search for it by label.
    $sweepCsv = $null
    $result = Get-ChildItem "C:\headroom-bench\results" -Directory -Filter ("*_" + $label) |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($result) {
        $csv = Get-ChildItem $result.FullName -Filter "*_sweep.csv" | Select-Object -First 1
        if ($csv) { $sweepCsv = $csv.FullName }
    }
    $records += [pscustomobject]@{
        order = $records.Count; tag = $s.tag; label = $label; condition = $s.cond
        uptime_min_at_start = $uptime; wrapper_exit = $exit; load_seen = $loaded
        event_log = $events; generator_exit = $genExit; generator_killed = $genKilled
        sweep_csv = $sweepCsv; wrapper_log = $out
    }
    $records | ConvertTo-Json | Set-Content -Path (Join-Path $expDir "experiment.json") -Encoding UTF8
    if ($exit -ne 0) { Say "Stopping: a failed run is reported, not worked around." "Red"; exit 6 }
}

Say "All runs complete. Score with: python analysis/score_activity_ab.py `"$expDir`"" "Green"
