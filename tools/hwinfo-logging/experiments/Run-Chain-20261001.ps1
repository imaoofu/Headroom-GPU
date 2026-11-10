<#
.SYNOPSIS
    The 2026-10-01 unattended chain on the RTX 5060 Ti, about 7 h, operator away for 8:
      1. section 14 dry run, quick (every XBAR offset forced to 0)      ~40 min, limit 1.5 h
      2. section 14, the XBAR intervention session                     ~1.5 h, limit 3 h
      3. section 10 re-collection, the negative control P5 -> P2 -> P5  ~3 h,   limit 5 h
      4. the new-card protocol practice run, headless, from the USB kit  ~2 h,  limit 3.5 h
    Each step starts only if the one before it exited 0. A failure or a timeout stops the chain.

.DESCRIPTION
    Runs from an ELEVATED shell. Every step is its own child process with its own safety cleanup
    (clock reset, mVolt+ offset 0, Afterburner Profile 3). This script adds a last cleanup of its own
    on every exit path: clock reset, Profile 3, mVolt+ XBAR offset 0 (written on stock), and the
    ChatGPT desktop app relaunched, because it closes that app before step 1 and keeps it closed.

    Preflight refuses to start unless: the shell is elevated; the driver is 616.92 (calibration and
    every registration were on it); HWiNFO's Sensors window is ready (started here if needed); no
    other mVolt+ process is running; the USB kit is mounted.

    Registrations: section 14 (ba59500, amended 837eb56) and section 10 (1c4e10d, a7bcd44, amended
    2026-09-30). The new-card practice run is a rehearsal of section 11's protocol on a card that has
    its own run list, not a registered test.

.PARAMETER SkipTo
    Start at step 2, 3 or 4, after a failure has been diagnosed. Steps before it are not re-run.
#>
[CmdletBinding()]
param([ValidateSet(1, 2, 3, 4)][int]$SkipTo = 1)
$ErrorActionPreference = "Continue"

$repo   = "C:\Users\Raymond\Documents\headroom"
$mvolt  = "C:\headroom-bench\mvolt\mVolt+.exe"
$gpuId  = "pci-2d0410de-177219da-00002d04-b01-s00"
$ab     = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$kit    = "F:\headroom-kit"
$appId  = "OpenAI.Codex_2p2nqsd0c76g0!App"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$logDir = "C:\headroom-bench\chain-$stamp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "chain.log"

function Say([string]$t) { $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $t; Write-Host $line; Add-Content -Path $log -Value $line }

function Invoke-Mvolt([string[]]$a) {
    $out = & $mvolt --gpu-id $gpuId @a 2>&1 | Out-String
    return @{ code = $LASTEXITCODE; out = $out.Trim() }
}

function Invoke-Step([int]$n, [string]$name, [string]$file, [string[]]$arguments, [int]$limitMinutes) {
    Say "==== STEP ${n}: $name (limit $limitMinutes min) ===="
    $out = Join-Path $logDir ("step{0}.out.txt" -f $n)
    $all = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $file) + $arguments
    $p = Start-Process -FilePath "powershell.exe" -ArgumentList $all -PassThru -WindowStyle Hidden `
         -RedirectStandardOutput $out -RedirectStandardError ($out + ".err")
    $null = $p.Handle
    if (-not $p.WaitForExit($limitMinutes * 60 * 1000)) {
        Say "STEP $n exceeded $limitMinutes min. Killing it and its children."
        & taskkill.exe /PID $p.Id /T /F | Out-Null
        return 99
    }
    Say ("STEP {0} exited {1}. Output: {2}" -f $n, $p.ExitCode, $out)
    return $p.ExitCode
}

function Close-ChatGpt {
    $procs = @(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { Say "ChatGPT/Codex is not running."; return $true }
    foreach ($p in $procs) { if ($p.MainWindowHandle -ne 0) { [void]$p.CloseMainWindow() } }
    Start-Sleep -Seconds 20
    @(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue) | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    $left = @(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue).Count
    Say ("ChatGPT/Codex closed ({0} processes were running; {1} left)." -f $procs.Count, $left)
    return ($left -eq 0)
}

# The new-card practice run, headless: the window's queue and plan, built the way Bench-Window.ps1
# builds them, from the kit's own copies, then Run-Plan.ps1 with no parent window. Its only human
# step (confirm HWiNFO Sensors) passes by itself once the Sensors window is ready.
function Write-NewcardPlan {
    $catalog = Join-Path $kit "tools\bench-app\catalog\newcard-rtx40-50.json"
    $results = Join-Path $kit "results"
    $s = Get-Date -Format "yyyyMMdd-HHmmss"
    $queuePath = Join-Path $results "bench-queue-$s.json"
    $planPath = Join-Path $results "bench-plan-$s.json"
    $session = Join-Path $results "bench-session-$s.json"
    $c = Get-Content $catalog -Raw -Encoding UTF8 | ConvertFrom-Json
    $runs = @($c.runs | Where-Object { $_.preselected })
    [IO.File]::WriteAllText($queuePath, (@{ runs = $runs } | ConvertTo-Json -Depth 30), (New-Object Text.UTF8Encoding($false)))
    & (Join-Path $kit "tools\bench-app\New-Plan.ps1") -CatalogPath $catalog -QueuePath $queuePath -OutputPath $planPath | Out-Null
    [IO.File]::WriteAllText(($session + ".control.json"), (@{ stop = $false; pause = $false; continue = $false } | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Say "New-card plan: $planPath; session record: $session"
    return @{ plan = $planPath; session = $session }
}

# ---- preflight ------------------------------------------------------------------------------
Say "Chain 2026-10-01 starting at step $SkipTo. Log: $log"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Say "Not elevated. Stopping."; exit 2 }
$driver = ((& nvidia-smi --query-gpu=driver_version --format=csv,noheader) | Select-Object -First 1).Trim()
if ($driver -ne "616.92") { Say "Driver is $driver, not 616.92 (calibration and every registration were on 616.92). Stopping."; exit 2 }
if (@(Get-Process | Where-Object { $_.Path -and $_.Path -like "*mVolt*" }).Count -gt 0) { Say "An mVolt+ window is open. Close it. Stopping."; exit 2 }
if (-not (Test-Path (Join-Path $kit "python\python.exe"))) { Say "USB kit not found at $kit. Stopping."; exit 2 }
& (Join-Path $repo "tools\hwinfo-logging\Start-HwinfoSensors.ps1") | ForEach-Object { Say $_ }
if ($LASTEXITCODE -ne 0) { Say "HWiNFO Sensors not ready (exit $LASTEXITCODE). Stopping."; exit 2 }
$closed = $false
if (-not (Close-ChatGpt)) { Say "ChatGPT/Codex would not close. Stopping."; exit 2 }
$closed = $true
Say "Driver $driver. Waiting 120 s for the desktop to settle after closing ChatGPT."
Start-Sleep -Seconds 120

$xbar = Join-Path $repo "tools\xbar\Invoke-Xbar14Session.ps1"
$cal = Join-Path $repo "data\frequency-sweeps\5060ti-xbar14-calibration-20260930\xbar14-calibration.json"
$ctrl = Join-Path $repo "tools\hwinfo-logging\experiments\Run-ControlRepeat-20261001.ps1"
# The steps live in a function so a stop RETURNS a result; a bare `return` at script level would end
# the script after the finally block with exit 0, reporting a failed chain as a success.
function Invoke-Chain {
    if ($SkipTo -le 1) {
        $c = Invoke-Step 1 "section 14 dry run (quick, offsets forced to 0)" $xbar @("-MvoltPath", $mvolt, "-GpuId", $gpuId, "-DryRun", "-Quick") 90
        if ($c -ne 0) { return "stopped at step 1 (exit $c)" }
    }
    if ($SkipTo -le 2) {
        $c = Invoke-Step 2 "section 14, the XBAR intervention session" $xbar @("-MvoltPath", $mvolt, "-GpuId", $gpuId, "-CalibrationPath", $cal) 180
        if ($c -ne 0) { return "stopped at step 2 (exit $c)" }
    }
    if ($SkipTo -le 3) {
        $c = Invoke-Step 3 "section 10 re-collection (P5 -> P2 -> P5)" $ctrl @() 300
        if ($c -ne 0) { return "stopped at step 3 (exit $c)" }
    }
    if ($SkipTo -le 4) {
        & $ab -profile3 -q | Out-Null
        Start-Sleep -Seconds 60
        $nc = Write-NewcardPlan
        $c = Invoke-Step 4 "new-card protocol practice run (headless, kit)" (Join-Path $kit "tools\bench-app\Run-Plan.ps1") @("-PlanPath", $nc.plan, "-SessionPath", $nc.session, "-VolumeLabel", "ESD-USB") 210
        if ($c -ne 0) { return "stopped at step 4 (exit $c)" }
    }
    return "completed"
}

$result = "interrupted before any step finished"
try {
    $result = Invoke-Chain
}
finally {
    Say "Chain cleanup: clocks reset, Profile 3, then mVolt+ XBAR offset 0 on stock."
    & nvidia-smi -rgc | Out-Null
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    $r = Invoke-Mvolt @("--xbar-offset", "0")
    Say ("mVolt+ XBAR reset exit {0}." -f $r.code)
    $st = Invoke-Mvolt @("--status")
    Set-Content -Path (Join-Path $logDir "mvolt-status-end.json") -Value $st.out -Encoding UTF8
    $pl = ((& nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits) | Select-Object -First 1).Trim()
    Say "Power limit $pl W (stock is 180)."
    $events = @(Get-WinEvent -FilterHashtable @{ LogName = "System"; StartTime = [datetime]::ParseExact($stamp, "yyyyMMdd-HHmmss", $null) } -ErrorAction SilentlyContinue |
                Where-Object { $_.Id -eq 4101 -or $_.ProviderName -like "*nvlddmkm*" })
    Say "Display-driver events during the chain: $($events.Count)."
    if ($closed) {
        & explorer.exe "shell:AppsFolder\$appId"
        Start-Sleep -Seconds 15
        Say ("ChatGPT relaunched: {0} processes." -f @(Get-Process -Name "ChatGPT" -ErrorAction SilentlyContinue).Count)
    }
    Say "CHAIN RESULT: $result"
}
if ($result -eq "completed") { exit 0 } else { exit 1 }
