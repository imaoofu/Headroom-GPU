<#
.SYNOPSIS
    REGISTERED-PREDICTIONS section 14, step 0: does an mVolt+ XBAR clock offset move the MEASURED
    crossbar clock on this card, under an nvidia-smi core lock? Clocks only.

.DESCRIPTION
    Applies an Afterburner profile, locks the core with nvidia-smi -lgc, then for each requested
    XBAR offset runs a steady load and records HWiNFO's reported and measured crossbar clocks, the
    reported core voltage (VID), the core clock and the memory clock.

    THIS SCRIPT NEVER READS OR PRINTS THROUGHPUT. Section 14 forbids looking at membw or gemm
    results before collection, because seeing an outcome first would void the registration. The
    load is `layernorm`, which no section 14 test uses, and its output is discarded unread.

    Every exit path - success, refusal, error, Ctrl+C - goes through one finally block that sets the
    XBAR offset back to 0, releases the core lock (-rgc), stops HWiNFO logging and re-applies
    Afterburner Profile 3 (stock), then reads the state back and says if it did not take.

    Requires an ELEVATED shell (nvidia-smi -lgc and every mVolt+ write need administrator rights),
    HWiNFO running with its Sensors window open, and Afterburner installed. Close Codex, ChatGPT
    and llama-server first. Never run while another mVolt+ instance is open (mVolt issue #12).

.PARAMETER MvoltPath
    Full path to mVolt+.exe.

.PARAMETER GpuId
    Stable adapter id from `mVolt+.exe --list-gpus`. Recommended once known.

.PARAMETER ReadOnly
    Only save --version, --list-gpus and --status output. No GPU state changes at all.

.PARAMETER Profile
    Afterburner slot to calibrate on: 3 = stock (180 W), 1 = curve 3 (200 W).

.PARAMETER TargetMhz
    Core clock to lock. Must be in the supported-clock table.

.PARAMETER OffsetsMhz
    Comma-separated XBAR offsets to apply in order, e.g. "0,-100,0". Section 14 C0b is "0,-100,0".
    Positive offsets are refused unless -AllowPositive is given, and must step by at most +50.

.EXAMPLE
    .\Invoke-XbarCalibration.ps1 -MvoltPath C:\headroom-bench\mvolt\mVolt+.exe -ReadOnly
    .\Invoke-XbarCalibration.ps1 -MvoltPath C:\headroom-bench\mvolt\mVolt+.exe -Profile 3 -TargetMhz 1560 -OffsetsMhz "0,-100,0"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MvoltPath,
    [string]$GpuId = "",
    [switch]$ReadOnly,
    [ValidateSet(1, 3)][int]$Profile = 3,
    [int]$TargetMhz = 1560,
    [string]$OffsetsMhz = "0,-100,0",
    [switch]$AllowPositive,
    [int]$SettleSeconds = 8,
    [int]$HoldSeconds = 25,
    [int]$LoadIterations = 1500,
    [string]$OutDir = "C:\headroom-bench\xbar-calibration"
)
$ErrorActionPreference = "Stop"

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ab = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$logTool = Join-Path $repo "tools\hwinfo-logging\Invoke-HwinfoLogging.ps1"
$workload = Join-Path $repo "tools\frequency-sweep\gpu_workload.py"
$report = Join-Path $PSScriptRoot "calibration_report.py"
$expectPl = @{ 3 = 180.0; 1 = 200.0 }

function Say([string]$t, [string]$c = "White") { Write-Host ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $t) -ForegroundColor $c }

function Invoke-Mvolt([string[]]$a, [switch]$NoGpu) {
    # mVolt+ reports refusals as JSON on stderr. Under "Stop" PowerShell turned that into an
    # exception BEFORE the output was saved and before the offset was marked written, so the reset
    # in finally was skipped (2026-09-30, the curve 3 refusal). Collect it as output instead.
    $ErrorActionPreference = "Continue"
    $all = @()
    if ($GpuId -and -not $NoGpu) { $all += @("--gpu-id", $GpuId) }
    $all += $a
    # mVolt+ is a GUI-subsystem executable: piping makes PowerShell wait for it and collect output.
    $out = & $MvoltPath @all 2>&1 | Out-String
    return @{ code = $LASTEXITCODE; out = $out.Trim(); args = ($all -join " ") }
}

function Save-Text([string]$name, [string]$text) {
    Set-Content -Path (Join-Path $runDir $name) -Value $text -Encoding UTF8
}

function Get-Smi {
    $line = (& nvidia-smi --query-gpu=clocks.sm,clocks.mem,power.draw,power.limit --format=csv,noheader,nounits) | Select-Object -First 1
    $p = $line -split "\s*,\s*"
    return @{ sm = [double]$p[0]; mem = [double]$p[1]; power = [double]$p[2]; limit = [double]$p[3] }
}

function Median([double[]]$v) {
    if ($v.Count -eq 0) { return [double]::NaN }
    $s = $v | Sort-Object
    $m = [int][math]::Floor($s.Count / 2)
    if ($s.Count % 2) { return $s[$m] } else { return ($s[$m - 1] + $s[$m]) / 2 }
}

# ---- preflight ------------------------------------------------------------------------------

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Say "Not elevated. nvidia-smi -lgc and mVolt+ writes need administrator rights." "Red"; exit 2 }
if (-not (Test-Path $MvoltPath)) { Say "mVolt+ not found at $MvoltPath" "Red"; exit 2 }

$offsets = @()
foreach ($part in ($OffsetsMhz -split '[,\s]+')) {
    if ($part -eq '') { continue }
    if ($part -notmatch '^-?\d+$') { Say "Offset '$part' is not a whole number of MHz." "Red"; exit 2 }
    $offsets += [int]$part
}
$previous = 0
foreach ($o in $offsets) {
    if ($o -gt 0 -and -not $AllowPositive) { Say "Positive offset $o refused without -AllowPositive (section 14 C0c)." "Red"; exit 2 }
    # The +50 limit applies to raising the fabric clock ABOVE its stock request. Returning toward 0
    # from a negative offset is the safe direction and is not limited (first run, 2026-09-30, refused
    # "0,-100,0" because the -100 -> 0 return looked like a +100 step).
    if ($o -gt 0 -and ($o - [math]::Max($previous, 0)) -gt 50) { Say "Offset rises by more than +50 MHz above 0 ($previous -> $o). Section 14 C0c steps +50 at a time." "Red"; exit 2 }
    $previous = $o
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runName = if ($ReadOnly) { "$stamp-readonly" } else { "$stamp-p$Profile-$TargetMhz" }
$runDir = Join-Path $OutDir $runName
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
Say "Output: $runDir" "Cyan"

$others = @(Get-Process | Where-Object { $_.Path -and $_.Path -like "*mVolt*" })
if ($others.Count -gt 0) {
    Say ("Another mVolt+ process is running ({0}). Close it first: two writers is mVolt issue #12." -f (($others | ForEach-Object { $_.Id }) -join ", ")) "Red"
    exit 3
}

$version = Invoke-Mvolt @("--version") -NoGpu
$gpus = Invoke-Mvolt @("--list-gpus") -NoGpu
$status0 = Invoke-Mvolt @("--status")
Save-Text "mvolt-version.txt" $version.out
Save-Text "mvolt-list-gpus.json" $gpus.out
Save-Text "mvolt-status-before.json" $status0.out
Say ("mVolt+ --version: {0} (exit {1})" -f $version.out, $version.code)
Say ("--list-gpus exit {0}, --status exit {1}; both saved." -f $gpus.code, $status0.code)
if ($ReadOnly) { Say "Read-only: nothing written to the GPU. Read the saved JSON before any write." "Green"; exit 0 }

if (-not (Test-Path $ab)) { Say "Afterburner not found at $ab" "Red"; exit 2 }
if (-not (Get-Process -Name "HWiNFO64" -ErrorAction SilentlyContinue)) { Say "HWiNFO64 is not running. Open it and its Sensors window first." "Red"; exit 3 }
if (Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'") { Say "llama-server is running. Stop it first." "Red"; exit 3 }
$supported = @((& nvidia-smi --query-supported-clocks=graphics --format=csv,noheader,nounits) | ForEach-Object { [int]($_.Trim()) })
if ($supported -notcontains $TargetMhz) { Say "$TargetMhz MHz is not in the supported-clock table." "Red"; exit 2 }

# ---- run ------------------------------------------------------------------------------------

$windows = @()
$wroteOffset = $false
$locked = $false
$logging = $false
$sinceStart = Get-Date
$exitCode = 1
try {
    Say "Applying Afterburner Profile $Profile." "Cyan"
    & $ab "-profile$Profile" -q
    Start-Sleep -Seconds 8
    $pl = (Get-Smi).limit
    if ([math]::Abs($pl - $expectPl[$Profile]) -gt 0.5) { throw "Profile $Profile did not verify: power limit $pl W, expected $($expectPl[$Profile])." }
    Say "Profile $Profile verified by power limit $pl W." "Green"

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $logTool -Start -LogPath (Join-Path $runDir "calibration-hwinfo.csv") | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "HWiNFO logging did not start (exit $LASTEXITCODE)." }
    $logging = $true

    & nvidia-smi -lgc "$TargetMhz,$TargetMhz" | Out-Host
    $locked = $true
    Say "Core locked at $TargetMhz MHz." "Green"

    $i = 0
    foreach ($o in $offsets) {
        $i++
        if ($Profile -eq 1) {
            # mVolt+ refuses EVERY write while curve 3 is live ("The profile contains an invalid V/F
            # point offset", 2026-09-30): curve 3's stored point offsets fall outside its range. So
            # the offset is written on stock, then Afterburner applies curve 3 over it, then the
            # core is locked again.
            & nvidia-smi -rgc | Out-Null
            & $ab -profile3 -q
            Start-Sleep -Seconds 8
        }
        $set = Invoke-Mvolt @("--xbar-offset", "$o")
        $wroteOffset = $true
        if ($Profile -eq 1 -and $set.code -eq 0) {
            & $ab -profile1 -q
            Start-Sleep -Seconds 8
            $pl = (Get-Smi).limit
            if ([math]::Abs($pl - 200) -gt 0.5) { throw "Curve 3 did not re-apply over the offset: power limit $pl W." }
            & nvidia-smi -lgc "$TargetMhz,$TargetMhz" | Out-Null
        }
        Save-Text ("mvolt-set-{0:D2}-{1}.txt" -f $i, $o) ("args: " + $set.args + "`r`nexit: " + $set.code + "`r`n" + $set.out)
        $st = Invoke-Mvolt @("--status")
        Save-Text ("mvolt-status-{0:D2}-{1}.json" -f $i, $o) $st.out
        if ($set.code -ne 0) { throw "mVolt+ --xbar-offset $o returned exit $($set.code): $($set.out)" }
        Say ("XBAR offset {0} MHz requested (exit 0). Running the clocks-only load." -f $o) "Cyan"

        $py = (Get-Command python).Source
        $until = (Get-Date).AddSeconds($SettleSeconds + $HoldSeconds + 3)
        $job = Start-Job -ScriptBlock {
            param($py, $wl, $until, $iters)
            while ((Get-Date) -lt $until) { & $py $wl --workload layernorm --iterations $iters --json 2>&1 | Out-Null }
        } -ArgumentList $py, $workload, $until, $LoadIterations
        Start-Sleep -Seconds $SettleSeconds
        $start = [DateTimeOffset]::Now.ToUnixTimeMilliseconds() / 1000.0
        $sm = @(); $mem = @(); $pw = @()
        $deadline = (Get-Date).AddSeconds($HoldSeconds)
        $midStatus = $null
        while ((Get-Date) -lt $deadline) {
            $s = Get-Smi; $sm += $s.sm; $mem += $s.mem; $pw += $s.power
            # One mVolt+ status read mid-window, UNDER LOAD, for the SYS clock and applied offset.
            if ($null -eq $midStatus -and $sm.Count -ge [int]($HoldSeconds / 2)) {
                $midStatus = Invoke-Mvolt @("--status")
                Save-Text ("mvolt-status-{0:D2}-{1}-loaded.json" -f $i, $o) $midStatus.out
            }
            Start-Sleep -Milliseconds 1000
        }
        $end = [DateTimeOffset]::Now.ToUnixTimeMilliseconds() / 1000.0
        Wait-Job $job -Timeout 120 | Out-Null
        Remove-Job $job -Force -ErrorAction SilentlyContinue
        $sysMhz = $null; $appliedOffset = $null
        try { $j = $midStatus.out | ConvertFrom-Json; $sysMhz = $j.sys_mhz; $appliedOffset = $j.xbar_offset_mhz } catch { }
        $windows += [ordered]@{ step = $i; offsetMhz = $o; windowStart = $start; windowEnd = $end;
                               smiCoreMedian = (Median $sm); smiMemMedian = (Median $mem);
                               smiPowerMedian = (Median $pw); smiMemMax = ($mem | Measure-Object -Maximum).Maximum;
                               mvoltSysMhz = $sysMhz; mvoltAppliedOffset = $appliedOffset }
        Say ("  core {0:N0} MHz, memory {1:N0} MHz, power {2:N1} W (nvidia-smi medians); mVolt+ SYS {3} MHz, applied offset {4}." -f (Median $sm), (Median $mem), (Median $pw), $sysMhz, $appliedOffset)
        # First run, 2026-09-30: layernorm refused to start without --iterations, every window was
        # idle at 13 W, and C0b "passed" on an idle card. A window that is not loaded is a failure.
        if ((Median $pw) -lt 30 -or (Median $mem) -lt 13000) {
            throw ("Step {0} (offset {1}) was NOT LOADED: power {2:N1} W, memory {3:N0} MHz. The load did not reach the GPU." -f $i, $o, (Median $pw), (Median $mem))
        }
    }
    $exitCode = 0
}
catch {
    Say ("STOPPED: {0}" -f $_.Exception.Message) "Red"
    $exitCode = 4
}
finally {
    Say "Restoring: Profile 3, then XBAR offset 0, core unlocked, logging stopped." "Cyan"
    # Stock FIRST: mVolt+ cannot write while curve 3 is live, so a reset attempted on curve 3 fails.
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    if ($wroteOffset) {
        $r = Invoke-Mvolt @("--xbar-offset", "0")
        Save-Text "mvolt-reset.txt" ("exit: " + $r.code + "`r`n" + $r.out)
        Save-Text "mvolt-status-after.json" (Invoke-Mvolt @("--status")).out
        if ($r.code -ne 0) { Say "** XBAR offset reset returned exit $($r.code). Reset it in mVolt+ by hand. **" "Red" }
    }
    if ($locked) { & nvidia-smi -rgc | Out-Host }
    if ($logging) { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $logTool -Stop | Out-Host }
    & $ab -profile3 -q
    Start-Sleep -Seconds 8
    $after = Get-Smi
    if ([math]::Abs($after.limit - 180) -gt 0.5) { Say "** Power limit reads $($after.limit) W after revert, not 180. Apply Profile 3 by hand. **" "Red" }
    else { Say "Profile 3 (stock) re-applied: power limit 180 W." "Green" }
    $crashes = @(Get-WinEvent -FilterHashtable @{ LogName = "System"; StartTime = $sinceStart } -ErrorAction SilentlyContinue |
                 Where-Object { $_.Id -eq 4101 -or $_.ProviderName -like "*nvlddmkm*" })
    if ($crashes.Count -gt 0) { Say "** $($crashes.Count) display-driver event(s) during this run. Every setting may have been cleared; treat the run as void. **" "Red" }
    ($windows | ConvertTo-Json -Depth 4) | Set-Content -Path (Join-Path $runDir "windows.json") -Encoding UTF8
}

if ($windows.Count -gt 0 -and (Test-Path (Join-Path $runDir "calibration-hwinfo.csv"))) {
    & python $report (Join-Path $runDir "calibration-hwinfo.csv") (Join-Path $runDir "windows.json") | Out-Host
}
exit $exitCode
