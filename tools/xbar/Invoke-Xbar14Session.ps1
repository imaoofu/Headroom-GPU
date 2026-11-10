<#
.SYNOPSIS
    REGISTERED-PREDICTIONS section 14: one unattended session of the XBAR intervention tests on the
    RTX 5060 Ti (stock brackets, S, S-gemm, C, curve 3 baselines, N), in the registered order.

.DESCRIPTION
    Registered 2026-09-30 before mVolt+ was installed (commit ba59500). Order:
      1 stock bracket A: membw 1402/1560/1710/1867, gemm 1867
      2 S arms (stock + offset) at 1560, 1710, 1867, then S-gemm at 1867
      3 C arm (stock + offset) at 1402
      4 stock bracket B: as 1
      5 curve 3 baseline: membw 1710/1867
      6 N arms (curve 3 + offset) at 1710, 1867
      7 curve 3 baseline again
      8 stock bracket C: membw 1402/1560/1710/1867
    Offsets come from the calibration file written in step 0 (clocks only).

    -DryRun forces EVERY offset to 0 and prefixes every label with "xbar14dry-", so the pipeline is
    exercised end to end - Afterburner, mVolt+ writes and readback, HWiNFO logging, the sweeps,
    driver-event checks, the restore - while producing no treatment outcome to look at.

    Safety, in one finally block on every exit path: XBAR offset 0, Afterburner Profile 3 (stock),
    read back. A display-driver event anywhere outside N ends the session: a driver reset clears
    settings silently, so nothing after it can be trusted. During N (curve 3 with a raised fabric
    clock, the registered risky arm) a failure ends N only; it is recorded NOT SCOREABLE and the
    session re-applies curve 3 and continues, because the closing brackets are what make S and C
    interpretable.

    Requires an elevated shell, HWiNFO running with its Sensors window open, Afterburner with the
    committed curve 3 profile store, and mVolt+ with no other instance open. Close Codex, ChatGPT
    and llama-server.

.PARAMETER CalibrationPath
    JSON written after step 0: { "gpuId": "...", "mvoltVersion": "...", "offsets": { "S1560": -n,
    "S1710": -n, "S1867": -n, "C1402": n, "N1710": n, "N1867": n } }. Not needed with -DryRun.

.PARAMETER Quick
    Dry runs only: every multi-target sweep runs its first target only. For checking plumbing fast.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MvoltPath,
    [string]$CalibrationPath = "",
    [string]$GpuId = "",
    [switch]$DryRun,
    [switch]$Quick,
    [switch]$ManageChatGpt
)
$ErrorActionPreference = "Continue"
# The ChatGPT desktop app (package OpenAI.Codex) runs ChatGPT.exe plus a codex.exe backend. With
# -ManageChatGpt the session closes it before the first sweep (an open app is load on the machine)
# and relaunches it after the card is back on stock, on every exit path. Closing it kills anything
# running inside it, such as a GPT job in progress.
$CHATGPT_APPID = "OpenAI.Codex_2p2nqsd0c76g0!App"

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$wrapper = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$wl = Join-Path $repo "tools\frequency-sweep\gpu_workload.py"
$ab = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$store = "${env:ProgramFiles(x86)}\MSI Afterburner\Profiles"
$CURVE3_HASH = "8EC197F30E21D116"
$STOCK_MEM = 13801
$BRACKET = @(1402, 1560, 1710, 1867)
$CURVE3_BASE = @(1710, 1867)
$prefix = if ($DryRun) { "xbar14dry" } else { "xbar14" }
$sessionStart = Get-Date
$logDir = Join-Path "C:\headroom-bench\xbar14-logs" ((Get-Date -Format "yyyyMMdd-HHmmss") + "-" + $prefix)
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$transcript = Join-Path $logDir "session.log"

function Say([string]$t, [string]$c = "White") {
    $line = "[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $t
    Write-Host $line -ForegroundColor $c
    Add-Content -Path $transcript -Value $line
}

function Invoke-Mvolt([string[]]$a, [switch]$NoGpu) {
    # mVolt+ reports refusals as JSON on stderr; collect it as output, never as an exception.
    $ErrorActionPreference = "Continue"
    $all = @()
    if ($GpuId -and -not $NoGpu) { $all += @("--gpu-id", $GpuId) }
    $all += $a
    $out = & $MvoltPath @all 2>&1 | Out-String
    return @{ code = $LASTEXITCODE; out = $out.Trim(); args = ($all -join " ") }
}

$script:xbarStep = 0
$script:currentOffset = $null
function Set-Xbar([int]$offset, [string]$why) {
    $script:xbarStep++
    $r = Invoke-Mvolt @("--xbar-offset", "$offset")
    $st = Invoke-Mvolt @("--status")
    $name = "{0:D2}-xbar{1}" -f $script:xbarStep, $offset
    Set-Content -Path (Join-Path $logDir "$name-set.txt") -Value ("why: $why`r`nargs: " + $r.args + "`r`nexit: " + $r.code + "`r`n" + $r.out) -Encoding UTF8
    Set-Content -Path (Join-Path $logDir "$name-status.json") -Value $st.out -Encoding UTF8
    if ($r.code -ne 0) { Say "mVolt+ --xbar-offset $offset returned exit $($r.code). Refusing." "Red"; return $false }
    $script:currentOffset = $offset
    Say ("XBAR offset {0} MHz requested ({1}); status saved as {2}." -f $offset, $why, $name) "Cyan"
    Start-Sleep -Seconds 15
    return $true
}

function Get-MemClockUnderLoad {
    $py = (Get-Command python).Source
    $job = Start-Job -ScriptBlock { param($py, $wl) & $py $wl --workload gemm --iterations 400 --json 2>&1 | Out-Null } -ArgumentList $py, $wl
    $reads = @(); $loadedSince = $null; $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $v = (& nvidia-smi --query-gpu=clocks.mem --format=csv,noheader,nounits) | Select-Object -First 1
        $n = 0; if ([int]::TryParse($v, [ref]$n)) { $reads += $n }
        if ($n -gt 5000 -and $null -eq $loadedSince) { $loadedSince = Get-Date }
        if ($null -ne $loadedSince -and ((Get-Date) - $loadedSince).TotalSeconds -ge 5) { break }
        Start-Sleep -Milliseconds 400
    }
    Wait-Job $job -Timeout 60 | Out-Null
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    # The MEDIAN of the loaded readings, not the maximum: on 2026-10-01 one check read 14001 (the card's
    # P0 maximum) and three repeats minutes later read 13801 at every sample, so a single transient
    # sample at load start must not decide. A sustained 14001 or 16301 still fails.
    $loaded = @($reads | Where-Object { $_ -gt 5000 } | Sort-Object)
    Say ("Memory readings under load: {0}" -f ($loaded -join " "))
    if ($loaded.Count -eq 0) { return -1 }
    return $loaded[[int][math]::Floor(($loaded.Count - 1) / 2)]
}

function Get-PowerLimit { return [double]((& nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits) | Select-Object -First 1).Trim() }

function Set-Arm([int]$slot, [double]$expectPl, [string]$name) {
    Say "Applying Afterburner Profile $slot ($name)." "Cyan"
    & $ab "-profile$slot" -q
    Start-Sleep -Seconds 8
    $mem = Get-MemClockUnderLoad
    $pl = Get-PowerLimit
    Say ("Memory under load {0} MHz (expect ~{1}); power limit {2} W (expect {3})." -f $mem, $STOCK_MEM, $pl, $expectPl)
    if ([math]::Abs($mem - $STOCK_MEM) -gt 100 -or [math]::Abs($pl - $expectPl) -gt 0.5) {
        Say "$name did NOT verify as live. Refusing to sweep." "Red"
        return $null
    }
    Say "$name verified live. Settling 90 s." "Green"
    Start-Sleep -Seconds 90
    return ("memory under load $mem MHz, power limit $pl W")
}

# mVolt+ refuses EVERY write while curve 3 is live ("The profile contains an invalid V/F point
# offset", calibration 2026-09-30). So an N offset is written on stock and Afterburner then applies
# curve 3 over it; calibration run 211301 showed the measured XBAR follows. Section 14 amendment 3.
function Set-XbarOnCurve3([int]$offset, [string]$why) {
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    if (-not (Set-Xbar $offset "$why (written on stock)")) { return $null }
    & $ab -profile1 -q
    Start-Sleep -Seconds 8
    $pl = Get-PowerLimit
    if ([math]::Abs($pl - 200) -gt 0.5) { Say "Curve 3 did not re-apply over the offset: power limit $pl W." "Red"; return $null }
    Say "Curve 3 re-applied over XBAR offset $offset (power limit $pl W). Settling 60 s." "Green"
    Start-Sleep -Seconds 60
    return ("curve 3 applied by MSIAfterburner.exe -profile1 -q over an XBAR offset written on stock, power limit $pl W")
}

function Get-DriverEvents {
    return @(Get-WinEvent -FilterHashtable @{ LogName = "System"; StartTime = $sessionStart } -ErrorAction SilentlyContinue |
             Where-Object { $_.Id -eq 4101 -or $_.ProviderName -like "*nvlddmkm*" })
}

function Invoke-Sweep([string]$label, [string]$workload, [int[]]$targets, [string]$iterations, [string]$settings) {
    if ($Quick) { $targets = @($targets[0]) }
    $label = "$prefix-$label"
    Say ("sweep {0}: {1} at {2} MHz" -f $label, $workload, ($targets -join ", ")) "Cyan"
    $job = [ordered]@{
        label           = $label
        workload        = $workload
        targets         = $targets
        descending      = $false
        expectedMinutes = 6
        appliedSettings = $settings
    }
    if ($iterations) { $job["iterations"] = $iterations }
    $job | ConvertTo-Json | Set-Content -Path "C:\headroom-bench\job.json" -Encoding UTF8
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -JobPath "C:\headroom-bench\job.json" | Out-Host
    $code = $LASTEXITCODE
    $events = Get-DriverEvents
    Say ("exit {0} for {1}; display-driver events since session start: {2}" -f $code, $label, $events.Count)
    if ($events.Count -gt 0) { return "driver" }
    if ($code -ne 0) { return "failed" }
    return "ok"
}

function Close-ChatGpt {
    $procs = @(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { Say "ChatGPT/Codex is not running."; return $true }
    Say "Closing the ChatGPT desktop app ($($procs.Count) processes)." "Cyan"
    foreach ($p in $procs) { if ($p.MainWindowHandle -ne 0) { [void]$p.CloseMainWindow() } }
    Start-Sleep -Seconds 20
    $left = @(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue)
    if ($left.Count -gt 0) {
        Say "$($left.Count) process(es) still running after the window closed (tray). Ending them." "Yellow"
        $left | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
    }
    $still = @(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue)
    if ($still.Count -gt 0) { Say "ChatGPT/Codex would not close." "Red"; return $false }
    Say "ChatGPT/Codex closed." "Green"
    return $true
}

function Open-ChatGpt {
    # Through Explorer, so the app starts as the signed-in user, not with this shell's elevation.
    & explorer.exe "shell:AppsFolder\$CHATGPT_APPID"
    Start-Sleep -Seconds 15
    $n = @(Get-Process -Name "ChatGPT" -ErrorAction SilentlyContinue).Count
    if ($n -gt 0) { Say "ChatGPT desktop app relaunched ($n processes)." "Green" }
    else { Say "ChatGPT desktop app did not appear after relaunch. Open it from the Start menu." "Yellow" }
}

# ---- preflight ------------------------------------------------------------------------------

Say ("Section 14 session, {0}. Log: {1}" -f $(if ($DryRun) { "DRY RUN (every offset forced to 0)" } else { "REAL" }), $logDir) "Cyan"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Say "Not elevated." "Red"; exit 2 }
if ($Quick -and -not $DryRun) { Say "-Quick is for dry runs only; a real session sweeps every registered target." "Red"; exit 2 }
foreach ($p in @($MvoltPath, $ab, $wrapper)) { if (-not (Test-Path $p)) { Say "Missing: $p" "Red"; exit 2 } }
if (-not (Get-Process -Name "HWiNFO64" -ErrorAction SilentlyContinue)) { Say "HWiNFO64 is not running." "Red"; exit 3 }
if (Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'") { Say "llama-server is running." "Red"; exit 3 }
$others = @(Get-Process | Where-Object { $_.Path -and $_.Path -like "*mVolt*" })
if ($others.Count -gt 0) { Say "Another mVolt+ process is running. Close it (mVolt issue #12)." "Red"; exit 3 }

$off = @{ S1560 = 0; S1710 = 0; S1867 = 0; C1402 = 0; N1710 = 0; N1867 = 0 }
if (-not $DryRun) {
    if (-not (Test-Path $CalibrationPath)) { Say "A real session needs -CalibrationPath from step 0." "Red"; exit 2 }
    $cal = Get-Content $CalibrationPath -Raw | ConvertFrom-Json
    foreach ($k in @($off.Keys)) {
        $v = $cal.offsets.$k
        if ($null -eq $v) { Say "Calibration file has no offset for $k." "Red"; exit 2 }
        $off[$k] = [int]$v
    }
    if ($off.S1560 -ge 0 -or $off.S1710 -ge 0 -or $off.S1867 -ge 0) { Say "S offsets must be negative (S lowers XBAR)." "Red"; exit 2 }
    if ($off.C1402 -le 0 -or $off.N1710 -le 0 -or $off.N1867 -le 0) { Say "C and N offsets must be positive (they raise XBAR)." "Red"; exit 2 }
    if (-not $GpuId -and $cal.gpuId) { $GpuId = [string]$cal.gpuId }
    Copy-Item $CalibrationPath (Join-Path $logDir "calibration-used.json")
}
Say ("Offsets: S {0}/{1}/{2}, C {3}, N {4}/{5} MHz. GPU id: {6}" -f $off.S1560, $off.S1710, $off.S1867, $off.C1402, $off.N1710, $off.N1867, $(if ($GpuId) { $GpuId } else { "(default adapter)" }))

$cfg = Get-ChildItem $store -Filter "VEN_10DE*.cfg" | Select-Object -First 1
# Hash only the [Startup] and [Profile1]-[Profile5] sections, byte for byte and in file order. Afterburner
# appends [Defaults] and [Settings] (a capture of stock values) on its own; it did so during the
# 2026-10-01 dry run without touching any profile, and the whole-file hash then refused a correct store.
# The committed snapshot holds exactly those six sections, so its whole-file hash is the expected value.
$latin1 = [Text.Encoding]::GetEncoding(28591)
$sections = [regex]::Split([IO.File]::ReadAllText($cfg.FullName, $latin1), '(?m)^(?=\[)')
$kept = ($sections | Where-Object { $_ -match '^\[(Startup|Profile[1-5])\]' }) -join ''
$sha = [Security.Cryptography.SHA256]::Create()
$hash = (($sha.ComputeHash($latin1.GetBytes($kept)) | ForEach-Object { $_.ToString("X2") }) -join '')
$wholeHash = (Get-FileHash $cfg.FullName -Algorithm SHA256).Hash
if (-not $hash.StartsWith($CURVE3_HASH)) { Say "Profile store sections are NOT the committed curve 3 snapshot ($($hash.Substring(0,16)); whole file $($wholeHash.Substring(0,16))). Refusing." "Red"; exit 4 }
Say "Profile sections hash $($hash.Substring(0,16)); whole file $($wholeHash.Substring(0,16))."
$version = (Invoke-Mvolt @("--version") -NoGpu).out
Set-Content -Path (Join-Path $logDir "mvolt-version.txt") -Value $version -Encoding UTF8
Set-Content -Path (Join-Path $logDir "mvolt-status-start.json") -Value (Invoke-Mvolt @("--status")).out -Encoding UTF8
Say "Profile store matches curve 3 ($($hash.Substring(0,16))); mVolt+ $version." "Green"
$script:closedChatGpt = $false
if ($ManageChatGpt) {
    if (-not (Close-ChatGpt)) { exit 3 }
    $script:closedChatGpt = $true
} elseif (@(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue).Count -gt 0) {
    Say "ChatGPT/Codex is running. Close it, or pass -ManageChatGpt to close and relaunch it." "Red"
    exit 3
}
$events0 = Get-DriverEvents
if ($events0.Count -gt 0) {
    Say "There are already display-driver events since this script started. Refusing." "Red"
    if ($script:closedChatGpt) { Open-ChatGpt }
    exit 3
}

$common = ("REGISTERED-PREDICTIONS section 14 (commit ba59500). mVolt+ $version XBAR clock offset only; no voltage, " +
    "ratio, SYS, video, core, memory or power control. Profile store $($hash.Substring(0,16)). HWiNFO 0.50 s, " +
    "operator absent, ChatGPT and Codex closed.") + $(if ($DryRun) { " DRY RUN: every offset forced to 0." } else { "" })
$stockText = "AFTERBURNER PROFILE 3 = STOCK (180 W, memory +0). "
$curveText = "AFTERBURNER PROFILE 1 = CURVE 3 (P4's curve exactly, memory +0, 200 W). "
function Text([string]$arm, [string]$verified, [int]$offset) { return ("{0}XBAR offset {1} MHz. {2}. {3}" -f $arm, $offset, $verified, $common) }

$script:nStatus = "not run"
function Invoke-Session {
    $v = Set-Arm 3 180 "stock"
    if ($null -eq $v) { return 5 }
    if (-not (Set-Xbar 0 "bracket A")) { return 6 }
    foreach ($s in @(@("a-membw", "membw", $BRACKET, ""), @("a-gemm", "gemm", @(1867), "120"))) {
        $r = Invoke-Sweep $s[0] $s[1] $s[2] $s[3] (Text $stockText $v 0)
        if ($r -ne "ok") { return 7 }
    }
    foreach ($t in @(1560, 1710, 1867)) {
        if (-not (Set-Xbar $off["S$t"] "S at $t")) { return 6 }
        if ((Invoke-Sweep "s$t-membw" "membw" @($t) "" (Text $stockText $v $off["S$t"])) -ne "ok") { return 7 }
    }
    if ((Invoke-Sweep "s1867-gemm" "gemm" @(1867) "120" (Text $stockText $v $off["S1867"])) -ne "ok") { return 7 }
    if (-not (Set-Xbar $off.C1402 "C at 1402")) { return 6 }
    if ((Invoke-Sweep "c1402-membw" "membw" @(1402) "" (Text $stockText $v $off.C1402)) -ne "ok") { return 7 }
    if (-not (Set-Xbar 0 "bracket B")) { return 6 }
    foreach ($s in @(@("b-membw", "membw", $BRACKET, ""), @("b-gemm", "gemm", @(1867), "120"))) {
        if ((Invoke-Sweep $s[0] $s[1] $s[2] $s[3] (Text $stockText $v 0)) -ne "ok") { return 7 }
    }

    $v1 = Set-Arm 1 200 "curve 3"
    if ($null -eq $v1) { return 5 }
    if ((Invoke-Sweep "c3base1-membw" "membw" $CURVE3_BASE "" (Text $curveText $v1 0)) -ne "ok") { return 7 }
    $script:nStatus = "completed"
    foreach ($t in @(1710, 1867)) {
        $vN = Set-XbarOnCurve3 $off["N$t"] "N at $t"
        if ($null -eq $vN) { $script:nStatus = "NOT SCOREABLE: offset or curve 3 did not apply at $t"; break }
        $r = Invoke-Sweep "n$t-membw" "membw" @($t) "" (Text $curveText $vN $off["N$t"])
        if ($r -ne "ok") { $script:nStatus = "NOT SCOREABLE: sweep $r at $t (stop rule)"; break }
    }
    Say "N: $($script:nStatus)" $(if ($script:nStatus -eq "completed") { "Green" } else { "Yellow" })
    if ((Get-DriverEvents).Count -gt 0) { Say "A driver event occurred during N. Continuing, as registered: N is NOT SCOREABLE." "Yellow"; $script:nStatus = "NOT SCOREABLE: driver event during N" }
    # Back to offset 0 the only way mVolt+ allows: stock first, then the write, then curve 3 again.
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    if (-not (Set-Xbar 0 "after N (on stock)")) { return 6 }
    $v1 = Set-Arm 1 200 "curve 3 (re-applied after N, offset 0)"
    if ($null -eq $v1) { return 5 }
    # Outside N, a driver event is fatal. Count only events after this point.
    $script:sessionStart = Get-Date
    if ((Invoke-Sweep "c3base2-membw" "membw" $CURVE3_BASE "" (Text $curveText $v1 0)) -ne "ok") { return 7 }

    $v = Set-Arm 3 180 "stock (closing)"
    if ($null -eq $v) { return 5 }
    if ((Invoke-Sweep "cbr-membw" "membw" $BRACKET "" (Text $stockText $v 0)) -ne "ok") { return 7 }
    Say "Session complete. N: $($script:nStatus)." "Green"
    return 0
}

$exitCode = 8
try { $exitCode = Invoke-Session }
finally {
    Say "Restoring: Afterburner Profile 3, then XBAR offset 0." "Cyan"
    # Stock FIRST: mVolt+ cannot write while curve 3 is live.
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    $r = Invoke-Mvolt @("--xbar-offset", "0")
    Set-Content -Path (Join-Path $logDir "zz-reset.txt") -Value ("exit: " + $r.code + "`r`n" + $r.out) -Encoding UTF8
    Set-Content -Path (Join-Path $logDir "zz-status-end.json") -Value (Invoke-Mvolt @("--status")).out -Encoding UTF8
    if ($r.code -ne 0) { Say "** XBAR offset reset returned exit $($r.code). Reset it in mVolt+ by hand. **" "Red" }
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    $mem = Get-MemClockUnderLoad
    $pl = Get-PowerLimit
    if ([math]::Abs($mem - $STOCK_MEM) -gt 100 -or [math]::Abs($pl - 180) -gt 0.5) { Say "** NOT back on stock: memory $mem MHz, power limit $pl W. **" "Red" }
    else { Say "Back on stock: memory $mem MHz under load, power limit $pl W." "Green" }
    if ($script:closedChatGpt) { Open-ChatGpt }
    Say "Exit code $exitCode. N: $($script:nStatus). Logs: $logDir"
}
exit $exitCode
