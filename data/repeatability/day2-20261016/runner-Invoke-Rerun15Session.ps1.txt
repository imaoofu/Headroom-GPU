<#
.SYNOPSIS
    REGISTERED-PREDICTIONS section 15 (registered 2026-10-03, commit 377e1be): the clean re-runs,
    R1 then R3, in one unattended session on the RTX 5060 Ti.

.DESCRIPTION
    R1, section 12 again: stock membw -> stock gemm -> curve 3 membw -> curve 3 gemm -> stock membw.
    R3, both ladder rungs: stock suite -> rung B suite -> rung C suite -> stock suite (12 workloads
    each). R2, the 2026-08-20 pair and the repair: stock membw -> P4 membw -> P2 membw -> stock
    membw. R2 runs on its own (-Parts r2): its stock roles share R1's names, so one session's
    rerun15-inputs.json can hold R1 or R2, not both.

    -Parts s16 is a different section: REGISTERED-PREDICTIONS section 16 (2026-10-06), section 10's
    control re-collected clean with a full-tune suite inserted: P5 -> P4 -> P2 -> P5, twelve
    workloads each. Its P5/P2/P5 sweeps carry section 10's labels (5060ti-ctrl10-{p5a,p2,p5b}-*) so
    analysis/score_control10.py scores them unchanged; analysis/score_session16.py adds P4. P5 and
    P2 are also told apart by section 10's witness, gemm power at a locked 2475 MHz.

    -Parts s19 is REGISTERED-PREDICTIONS sections 18 and 19 (registered 2026-10-06): stock -> P5 ->
    P4 -> rung B -> rung C -> stock, twelve workloads each, every sweep carrying both power figures
    (schema 0.3.4), with tools/power-probe/sample_power.py logging NVML at 20 Hz for the whole
    session. Scored by analysis/score_power_fields.py (section 18) and analysis/score_session19.py
    (section 19). The section 16 witness (gemm at a locked 2475 MHz) is taken for every arm.

    -Parts s20 is REGISTERED-PREDICTIONS section 20 (registered 2026-10-07): the floor's end on a
    fine grid. Stock ascending -> full tune (P4) ascending -> P4 descending -> stock descending,
    twelve workloads each on an 18-point grid at 37.5 MHz spacing around each configuration's floor
    end (stock 1237-1875, P4 1672-2310 MHz). No 20 Hz logger: section 18 left open whether polling
    the counter disturbs it. Scored by analysis/score_session20.py.

    -Parts s21 is REGISTERED-PREDICTIONS section 21 (registered 2026-10-08): section 20's tests on four
    application workloads (AlexNet and ResNet-50 inference, k-means, HotSpot; app_workloads.py). Stock
    coarse ascending -> stock fine ascending -> P4 fine ascending -> P4 fine descending -> stock fine
    descending -> stock coarse descending. Scored by analysis/score_session21.py.

    Every sweep runs through tools/hwinfo-logging/Invoke-LoggedSweep.ps1, which minimizes the Claude
    app, logs HWiNFO and exits 8 when its own log shows a desktop load. Section 15 condition 1: a
    sweep that exits 8 is re-run once; a second exit 8 is recorded and that role is NOT SCOREABLE.
    Any other failure, or any display-driver event, ends the session.

    Profiles (condition 4). The NVIDIA profile store is restored byte for byte from a committed
    snapshot with Afterburner closed, then section-hash verified after Afterburner restarts:
    curve 3 for R1 (and at the end), rung B and rung C for R3. P2-P5 are identical across the three.

    Witnesses (condition 3), saved per arm under the session directory and named in
    rerun15-inputs.json, which analysis/score_rerun15.py reads: a copy of the live store, the slot,
    power limit and memory clock under load read live, the driver, and mVolt+'s XBAR/SYS/video
    offsets and voltage demands (all must be 0). Nothing here writes through mVolt+.

    Safety: one finally block on every exit path: clocks reset, curve 3 store restored, Profile 3
    (stock) applied and read back, ChatGPT relaunched if this script closed it.

    -DryRun prefixes every label with r15dry-, sweeps each list's first target only and runs one
    workload per R3 suite, so the plumbing (restores, witnesses, retries, manifest) is exercised in
    about 20 minutes. Its output is not section 15 data.

    -Parts rep -Session N is REGISTERED-PREDICTIONS section 22 (registered 2026-10-14): day-to-day
    stock repeatability, day N of 5. Stock only: gemm, copy, reduce and resnet50 on section 20's 18-point
    stock grid plus 2010 and 2317 MHz, one pass in the day's workload order and direction, stock
    re-witnessed, then the mirrored pass. No measured-role retry: a desktop-load role is recorded NOT
    SCOREABLE and the day continues. gemm/copy/reduce draw seeded inputs (--input-seed 20261013).
    -DryRun runs the same eight roles at the first target only (a qualification, not data). Scored by
    analysis/score_repeatability.py.

    -Parts s20b is REGISTERED-PREDICTIONS section 20b (GPT Job 71's design): does polling NVML's
    energy or power readings change what the energy counter reports? Stock only. After the stock
    witness, HWiNFO and Afterburner are CLOSED so nothing else polls the card, stock is verified again,
    and tools/section20b/run_core_session.py runs the 144-window balanced session (-Session N). No
    sweep and no HWiNFO log: the desktop-load screen is unavailable by design, and the controller's
    process checks stand in for it. -DryRun runs the 36-window hardware qualification instead (not
    data). Scored by analysis/score_section20b.py.

    Requires an elevated shell and HWiNFO. Close Opera, Discord, Obsidian and games first.
#>
[CmdletBinding()]
param(
    [string]$MvoltPath = "C:\headroom-bench\mvolt\mVolt+.exe",
    [string]$GpuId = "pci-2d0410de-177219da-00002d04-b01-s00",
    [ValidateSet("r1", "r2", "r3", "r1r3", "s16", "s19", "s20", "s21", "s20b", "rep")][string]$Parts = "r1r3",
    [int]$Session = 0,
    [switch]$DryRun,
    [switch]$ManageChatGpt
)
$ErrorActionPreference = "Continue"
$CHATGPT_APPID = "OpenAI.Codex_2p2nqsd0c76g0!App"

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$wrapper = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$wl = Join-Path $repo "tools\frequency-sweep\gpu_workload.py"
$ab = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$storeDir = "${env:ProgramFiles(x86)}\MSI Afterburner\Profiles"
$STORE_NAME = "VEN_10DE&DEV_2D04&SUBSYS_177219DA&REV_A1&BUS_1&DEV_0&FN_0.cfg"
$storePath = Join-Path $storeDir $STORE_NAME
$SNAPSHOTS = [ordered]@{
    curve3 = Join-Path $repo "data\afterburner-profiles\5060ti-profiles-20260926-curve3"
    rungB  = Join-Path $repo "data\afterburner-profiles\5060ti-profiles-20260922-rungB"
    rungC  = Join-Path $repo "data\afterburner-profiles\5060ti-profiles-20260926-rungC"
}
$STOCK_MEM = 13801
$OC_MEM = 16301
$BAND = @(1402, 1477, 1560, 1635, 1710, 1792, 1867, 1942, 2025, 2100)
$GRID = @(1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090)
# Section 20: every fifth supported clock (37.5 MHz), 9 points below each floor-end target and 8 above.
$FINE_STOCK = @(1237, 1275, 1312, 1350, 1387, 1425, 1462, 1500, 1537, 1575, 1612, 1650, 1687, 1725, 1762, 1800, 1837, 1875)
$FINE_P4 = @(1672, 1710, 1747, 1785, 1822, 1860, 1897, 1935, 1972, 2010, 2047, 2085, 2122, 2160, 2197, 2235, 2272, 2310)
# The original rung suites' iteration counts (runner-run-4e / 4f, from 5060ti-stock-repro-20260922).
$ITER = [ordered]@{
    copy = 2660; reduce = 2870; softmax = 2600; layernorm = 1597; bgemm32 = 2673
    bgemm64 = 2661; bgemm128 = 2467; bgemm256 = 1579; bgemm1024 = 414
    attention = 147; conv = 151; gemm = 120
}
# Section 21's application workloads: counts from the 2026-10-08 timing pilot (stock, unlocked boost,
# about 9 s each; 11-17 s at 1237 MHz). One iteration is one complete task.
if ($Parts -eq "s21") { $ITER = [ordered]@{ alexnet = 3484; resnet50 = 424; kmeans = 85; hotspot = 14 } }
# Section 22 (repeatability): the counts sections 10/20 and 21 used, never recalibrated per day.
if ($Parts -eq "rep") { $ITER = [ordered]@{ gemm = 120; copy = 2660; reduce = 2870; resnet50 = 424 } }
$REP_GRID = @(1237, 1275, 1312, 1350, 1387, 1425, 1462, 1500, 1537, 1575, 1612, 1650, 1687, 1725, 1762, 1800, 1837, 1875, 2010, 2317)
$REP_SEED = 20261013
# Section 22's frozen schedule, day index -> first-pass order and direction; the second pass reverses both.
# Day 5 repeats day 1 on purpose (five days cannot balance four positions and two directions).
$REP_DAYS = @{
    1 = @{ order = @("gemm", "copy", "reduce", "resnet50"); descending = $false }
    2 = @{ order = @("copy", "reduce", "resnet50", "gemm"); descending = $true }
    3 = @{ order = @("reduce", "resnet50", "gemm", "copy"); descending = $false }
    4 = @{ order = @("resnet50", "gemm", "copy", "reduce"); descending = $true }
    5 = @{ order = @("gemm", "copy", "reduce", "resnet50"); descending = $false }
}
$prefix = if ($Parts -in @("s16", "s19", "s20", "s21", "s20b", "rep")) { if ($DryRun) { "${Parts}dry" } else { $Parts } } elseif ($DryRun) { "r15dry" } else { "r15" }
$SECTION = if ($Parts -eq "rep") { "REGISTERED-PREDICTIONS section 22 (day-to-day repeatability)" } elseif ($Parts -eq "s20b") { "REGISTERED-PREDICTIONS section 20b" } elseif ($Parts -eq "s21") { "REGISTERED-PREDICTIONS section 21 (2026-10-09)" } elseif ($Parts -eq "s16") { "REGISTERED-PREDICTIONS section 16 (2026-10-06)" } elseif ($Parts -eq "s20") { "REGISTERED-PREDICTIONS section 20 (2026-10-08)" } elseif ($Parts -eq "s19") { "REGISTERED-PREDICTIONS sections 18 and 19 (2026-10-07)" } else { "REGISTERED-PREDICTIONS section 15 (377e1be)" }
$settle = if ($DryRun) { 20 } else { 90 }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$sessionDir = Join-Path "C:\headroom-bench\rerun15" "$stamp-$prefix"
$witnessDir = Join-Path $sessionDir "witnesses"
New-Item -ItemType Directory -Force -Path $witnessDir | Out-Null
$transcript = Join-Path $sessionDir "session.log"
$manifestPath = Join-Path $sessionDir "rerun15-inputs.json"
$sessionStart = Get-Date
$script:manifest = [ordered]@{ section = $SECTION; dryRun = [bool]$DryRun; sweeps = [ordered]@{}; references = [ordered]@{}; notScoreable = @() }
$script:snapshot = ""
$script:restoredByMe = $false
# Section 22 (GPT Job 94, F7): the filer copies THIS file into the day, never the checkout it is run from
# later, and the scorer checks the hashes of what the runner called.
if ($Parts -eq "rep") {
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $sessionDir "runner-as-run.ps1.txt")
    $script:manifest["sources"] = [ordered]@{}
    foreach ($src in @($PSCommandPath, $wrapper, $wl, (Join-Path $repo "tools\frequency-sweep\app_workloads.py"))) {
        $script:manifest.sources[(Split-Path $src -Leaf)] = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
    }
}

function Say([string]$t, [string]$c = "White") {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $t
    Write-Host $line -ForegroundColor $c
    # A reader holding the file (the 2026-10-03 dry run lost lines to one) must not lose the line.
    for ($i = 0; $i -lt 10; $i++) {
        try { Add-Content -Path $transcript -Value $line -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 300 }
    }
}

function Save-Manifest {
    $json = $script:manifest | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($manifestPath, $json, (New-Object Text.UTF8Encoding($false)))
}

function Get-SectionHash([string]$path) {
    # [Startup] and [Profile1]-[Profile5] only, byte for byte in file order: Afterburner appends
    # [Defaults] and [Settings] by itself (2026-10-01). A committed snapshot holds exactly these six.
    $latin1 = [Text.Encoding]::GetEncoding(28591)
    $sections = [regex]::Split([IO.File]::ReadAllText($path, $latin1), '(?m)^(?=\[)')
    $kept = ($sections | Where-Object { $_ -match '^\[(Startup|Profile[1-5])\]' }) -join ''
    $sha = [Security.Cryptography.SHA256]::Create()
    return (($sha.ComputeHash($latin1.GetBytes($kept)) | ForEach-Object { $_.ToString("X2") }) -join '')
}

function Invoke-Mvolt([string[]]$a) {
    $out = & $MvoltPath --gpu-id $GpuId @a 2>&1 | Out-String
    return @{ code = $LASTEXITCODE; out = $out.Trim() }
}

# mVolt+'s own domains only. Core and memory offsets are Afterburner's and are witnessed by the
# profile store, the power limit and the memory clock instead.
function Get-MvoltOffsets([string]$name) {
    $r = Invoke-Mvolt @("--status")
    Set-Content -Path (Join-Path $witnessDir "$name-mvolt-status.json") -Value $r.out -Encoding UTF8
    if ($r.code -ne 0) { return $null }
    try { $s = $r.out | ConvertFrom-Json } catch { return $null }
    $o = [ordered]@{
        xbar_offset_mhz  = $s.xbar_offset_mhz
        sys_offset_mhz   = $s.sys_offset_mhz
        video_offset_mhz = $s.video_offset_mhz
        demand_core_mv   = $s.voltage_demand_mv.Core
        demand_xbar_mv   = $s.voltage_demand_mv.Xbar
        demand_sys_mv    = $s.voltage_demand_mv.SYS
        demand_video_mv  = $s.voltage_demand_mv.Video
    }
    foreach ($k in @($o.Keys)) { if ($null -eq $o[$k]) { return $null } ; $o[$k] = [int]$o[$k] }
    return $o
}

function Get-MemClockUnderLoad {
    $py = (Get-Command python).Source
    $job = Start-Job -ScriptBlock { param($py, $wl) & $py $wl --workload gemm --iterations 400 --json 2>&1 | Out-Null } -ArgumentList $py, $wl
    $reads = @(); $loadedSince = $null; $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $v = First-Line (Invoke-BoundedSmi "--query-gpu=clocks.mem --format=csv,noheader,nounits" 30)
        $n = 0; if ([int]::TryParse($v, [ref]$n)) { $reads += $n }
        if ($n -gt 5000 -and $null -eq $loadedSince) { $loadedSince = Get-Date }
        if ($null -ne $loadedSince -and ((Get-Date) - $loadedSince).TotalSeconds -ge 5) { break }
        Start-Sleep -Milliseconds 400
    }
    Wait-Job $job -Timeout 60 | Out-Null
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    $loaded = @($reads | Where-Object { $_ -gt 5000 } | Sort-Object)
    Say ("Memory readings under load: {0}" -f ($loaded -join " "))
    if ($loaded.Count -eq 0) { return -1 }
    return $loaded[[int][math]::Floor(($loaded.Count - 1) / 2)]
}

# Section 10's slot witness (amended a7bcd44): median gemm board power at a locked 2475 MHz, loaded
# samples after the first six. P5 <= 163 W, P2 >= 165 W; P4 is recorded, not gated (no threshold
# was ever measured for it).
# nvidia-smi with a deadline (GPT Job 73, F6): the whole output is read before any line is chosen, so
# the early-pipeline-termination bug (CLAUDE.md, bug 2) cannot come back. $null on timeout or failure.
function Invoke-BoundedNative([string]$arguments, [int]$seconds = 30) {
    # Any nvidia-smi call, with a deadline, killed and reaped on timeout (GPT Job 75, R5). Returns
    # ok (finished with exit 0), the exit code (-1 when it could not start or timed out) and stdout.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "nvidia-smi"
    $psi.Arguments = $arguments
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    # A kill or reap that fails is returned in error/reaped, never swallowed (GPT Job 76, R5).
    try { $proc = [System.Diagnostics.Process]::Start($psi) } catch { return @{ ok = $false; code = -1; out = ""; reaped = $true; error = "start: $($_.Exception.Message)" } }
    try {
        $text = $proc.StandardOutput.ReadToEndAsync()
        if (-not $proc.WaitForExit($seconds * 1000)) {
            $err = "timed out after $seconds s"
            try { $proc.Kill() } catch { $err += "; kill failed: $($_.Exception.Message)" }
            $reaped = $false
            try { $reaped = $proc.WaitForExit(10000) } catch { $err += "; reap failed: $($_.Exception.Message)" }
            return @{ ok = $false; code = -1; out = ""; reaped = $reaped; error = $err }
        }
        # The output has its own deadline: a child that exits but holds its pipe open must not hang us.
        if (-not $text.Wait(10000)) { return @{ ok = $false; code = -1; out = ""; reaped = $true; error = "output did not close" } }
        return @{ ok = ($proc.ExitCode -eq 0); code = $proc.ExitCode; out = $text.Result; reaped = $true; error = $null }
    } catch {
        $err = "native call failed: $($_.Exception.Message)"
        try { if (-not $proc.HasExited) { $proc.Kill(); [void]$proc.WaitForExit(10000) } } catch { $err += "; cleanup failed: $($_.Exception.Message)" }
        return @{ ok = $false; code = -1; out = ""; reaped = $false; error = $err }
    }
}

function Invoke-BoundedSmi([string]$arguments, [int]$seconds = 30) {
    $r = Invoke-BoundedNative $arguments $seconds
    if (-not $r.ok) { return $null }
    return $r.out
}

function First-Line([string]$text) {
    # The first non-empty line of output already read in full, never a pipeline cut short.
    if ($null -eq $text) { return "" }
    $line = @(($text -split "`r?`n") | Where-Object { $_.Trim() })
    if ($line.Count -eq 0) { return "" }
    return $line[0].Trim()
}

function Get-LockedGemmPower {
    $py = (Get-Command python).Source
    $s = @()
    $p = $null
    $resetOk = $true
    $json = Join-Path $witnessDir ("gemm-witness-{0}.json" -f (Get-Date -Format "HHmmss"))
    try {
        # The lock is inside the protected block, bounded, and checked before any load (R5).
        $lock = Invoke-BoundedNative "-lgc 2475,2475" 60
        if (-not $lock.ok) { Say "Locking 2475 MHz for the witness failed (exit $($lock.code))." "Red"; return -1 }
        $p = Start-Process -FilePath $py -ArgumentList @($wl, "--workload", "gemm", "--iterations", "300", "--json") -PassThru -WindowStyle Hidden -RedirectStandardOutput $json
        $null = $p.Handle
        # Bounded (GPT Job 73, F6): a hung benchmark or query cannot hold the session forever.
        $deadline = (Get-Date).AddSeconds(300)
        while (-not $p.HasExited) {
            if ((Get-Date) -ge $deadline) { Say "The 2475 MHz witness benchmark did not finish in 300 s." "Red"; return -1 }
            $out = Invoke-BoundedSmi "--query-gpu=utilization.gpu,power.draw --format=csv,noheader,nounits" 30
            if ($null -ne $out) {
                $r = (($out -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1) -split ','
                $u = 0
                if ($r.Count -eq 2 -and [int]::TryParse($r[0].Trim(), [ref]$u) -and $u -ge 50) { $s += [double]$r[1].Trim() }
            }
            Start-Sleep -Milliseconds 500
        }
    } finally {
        # The reset runs whatever the benchmark's reap does (GPT Job 76, R5).
        try {
            if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue; [void]$p.WaitForExit(10000) }
        } catch { $resetOk = $false; Say "Stopping the witness benchmark failed: $($_.Exception.Message)" "Red" }
        finally {
            $reset = Invoke-BoundedNative "-rgc" 60
            if (-not $reset.ok) { $resetOk = $false; Say "Clock reset after the witness failed (exit $($reset.code); $($reset.error))." "Red" }
        }
    }
    if (-not $resetOk) { return -1 }
    # The benchmark must itself have completed cleanly, or its power is not a witness of anything.
    $result = $null
    try { $result = (Get-Content -LiteralPath $json -Raw) | ConvertFrom-Json } catch { }
    # Exit 0, ok, not aborted and all 300 iterations, or its power witnesses nothing (R5).
    if ($p.ExitCode -ne 0 -or $null -eq $result -or -not $result.ok -or $result.aborted -or $result.iterations_completed -ne 300) {
        Say "The 2475 MHz witness benchmark did not complete cleanly (exit $($p.ExitCode))." "Red"; return -1
    }
    $steady = @($s | Select-Object -Skip 6 | Sort-Object)
    if ($steady.Count -lt 10) { return -1 }
    return $steady[[int]($steady.Count / 2)]
}

function Get-PowerLimit {
    # Bounded (R5). -1 when unreadable, which no caller accepts as 180 W.
    $v = 0.0
    if ([double]::TryParse((First-Line (Invoke-BoundedSmi "--query-gpu=power.limit --format=csv,noheader,nounits" 30)), [ref]$v)) { return $v }
    return -1
}

function Get-DriverEvents {
    return @(Get-WinEvent -FilterHashtable @{ LogName = "System"; StartTime = $sessionStart } -ErrorAction SilentlyContinue |
             Where-Object { $_.Id -eq 4101 -or $_.ProviderName -like "*nvlddmkm*" })
}

# Section 20b (GPT Job 73, F5): "no events" must be told apart from "the log could not be read".
function Get-DriverEventsChecked {
    try {
        $e = @(Get-WinEvent -FilterHashtable @{ LogName = "System"; StartTime = $sessionStart } -ErrorAction Stop |
               Where-Object { $_.Id -eq 4101 -or $_.ProviderName -like "*nvlddmkm*" })
        return @{ ok = $true; count = $e.Count; ids = @($e | ForEach-Object { $_.Id }) }
    } catch {
        if ($_.FullyQualifiedErrorId -like "NoMatchingEventsFound*") { return @{ ok = $true; count = 0; ids = @() } }
        return @{ ok = $false; count = $null; ids = @(); error = $_.Exception.Message }
    }
}

function Write-JsonNoBom([string]$path, $object) {
    # PowerShell 5.1's Set-Content -Encoding UTF8 writes a byte-order mark (GPT Job 73, F9).
    [IO.File]::WriteAllText($path, ($object | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
}

# Condition 4: Afterburner closed, the store copied byte for byte, the copy verified, Afterburner
# restarted, and the six profile sections verified against the snapshot after its restart.
function Restore-Store([string]$name) {
    $src = Join-Path $SNAPSHOTS[$name] $STORE_NAME
    $expect = Get-SectionHash $src
    Say "Restoring the profile store from snapshot $name ($($expect.Substring(0,16)))." "Cyan"
    $procs = @(Get-Process -Name "MSIAfterburner" -ErrorAction SilentlyContinue)
    if ($procs.Count -gt 0) { $procs | Stop-Process -Force -ErrorAction SilentlyContinue }
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline -and @(Get-Process -Name "MSIAfterburner" -ErrorAction SilentlyContinue).Count -gt 0) { Start-Sleep -Milliseconds 500 }
    if (@(Get-Process -Name "MSIAfterburner" -ErrorAction SilentlyContinue).Count -gt 0) { Say "Afterburner would not close." "Red"; return $false }
    Copy-Item -LiteralPath $src -Destination $storePath -Force
    $copied = (Get-FileHash -LiteralPath $storePath -Algorithm SHA256).Hash
    $source = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
    if ($copied -ne $source) { Say "The copied store is not byte-identical to the snapshot." "Red"; return $false }
    Start-Process -FilePath $ab -WindowStyle Minimized | Out-Null
    Start-Sleep -Seconds 12
    $live = Get-SectionHash $storePath
    if ($live -ne $expect) { Say "After Afterburner restarted, the profile sections hash $($live.Substring(0,16)), not $($expect.Substring(0,16))." "Red"; return $false }
    $script:snapshot = $name
    $script:restoredByMe = $true
    Say "Store restored byte for byte from $name; sections verified after restart ($($live.Substring(0,16)))." "Green"
    return $true
}

# Apply a slot, verify it live, and save the arm's witness. Returns the witness or $null.
function Set-Arm([string]$arm, [int]$slot, [double]$expectPl, [int]$expectMem) {
    Say "Applying Afterburner Profile $slot ($arm)." "Cyan"
    & $ab "-profile$slot" -q
    Start-Sleep -Seconds 8
    $w2475 = $null
    if ($Parts -in @("s16", "s19", "s20", "s21", "s20b", "rep")) {
        # Section 16 amendment (2026-10-06, before collection): the witness is the first load after
        # the slot is applied, after 90 s idle, as section 10's runner took it. The dry run measured it
        # after the memory check's gemm load and read P5 at 144 W cold but 156 W warm.
        Start-Sleep -Seconds 90
        $w2475 = Get-LockedGemmPower
        $tC = First-Line (Invoke-BoundedSmi "--query-gpu=temperature.gpu --format=csv,noheader,nounits" 30)
        Say ("{0}: gemm at a locked 2475 MHz, median {1:N1} W, {2} C after (section 10 witness: P5 <= 163, P2 >= 165; P4 recorded only)." -f $arm, $w2475, $tC)
        if ($w2475 -lt 0) { Say "Too few loaded samples for the 2475 MHz witness. Refusing." "Red"; return $null }
        if ($slot -eq 5 -and $w2475 -gt 163) { Say "$arm is not verifiably P5 by the section 10 witness. Refusing." "Red"; return $null }
        if ($slot -eq 2 -and $w2475 -lt 165) { Say "$arm is not verifiably P2 by the section 10 witness. Refusing." "Red"; return $null }
    }
    $mem = Get-MemClockUnderLoad
    $pl = Get-PowerLimit
    Say ("Memory under load {0} MHz (expect {1}); power limit {2} W (expect {3})." -f $mem, $expectMem, $pl, $expectPl)
    if ($mem -ne $expectMem -or [math]::Abs($pl - $expectPl) -gt 0.5) { Say "$arm did NOT verify as live. Refusing to sweep." "Red"; return $null }
    $offsets = Get-MvoltOffsets $arm
    if ($null -eq $offsets) { Say "mVolt+ status could not be read for $arm." "Red"; return $null }
    $nonzero = @($offsets.Keys | Where-Object { $offsets[$_] -ne 0 })
    if ($nonzero.Count -gt 0) { Say ("mVolt+ reads non-zero {0} for {1}. Refusing." -f ($nonzero -join ", "), $arm) "Red"; return $null }
    $storeCopy = Join-Path $witnessDir "$arm-store.cfg"
    Copy-Item -LiteralPath $storePath -Destination $storeCopy -Force
    $driver = First-Line (Invoke-BoundedSmi "--query-gpu=driver_version --format=csv,noheader" 30)
    Say "$arm verified live; mVolt+ offsets and voltage demands all 0. Settling $settle s." "Green"
    Start-Sleep -Seconds $settle
    $w = [ordered]@{
        profile_store          = $storeCopy
        snapshot               = $script:snapshot
        profile_slot           = $slot
        witnessed_at_unix      = [math]::Round(((Get-Date).ToUniversalTime() - [datetime]'1970-01-01').TotalSeconds, 3)
        driver                 = $driver
        power_limit_w          = [int][math]::Round($pl)
        memory_loaded_mhz      = $mem
        offsets_mhz            = $offsets
        restored_byte_for_byte = $script:restoredByMe
        afterburner_closed     = $script:restoredByMe
        gemm_2475_power_w      = $w2475
    }
    ($w | ConvertTo-Json -Depth 5) | Set-Content -Path (Join-Path $witnessDir "$arm-witness.json") -Encoding UTF8
    return $w
}

function Get-UtcOffsetMinutes { return [int]([TimeZoneInfo]::Local.GetUtcOffset((Get-Date)).TotalMinutes) }

function Run-Wrapper([string]$label, [string]$workload, [int[]]$targets, [string]$iterations, [string]$settings, [bool]$descending = $false) {
    $job = [ordered]@{ label = $label; workload = $workload; targets = $targets; descending = $descending; expectedMinutes = 12; appliedSettings = $settings }
    if ($iterations) { $job["iterations"] = $iterations }
    # Section 22: the kernel workloads draw seeded inputs; resnet50 seeds itself (app_workloads.SEED).
    if ($Parts -eq "rep" -and $workload -ne "resnet50") { $job["inputSeed"] = $REP_SEED }
    $job | ConvertTo-Json | Set-Content -Path "C:\headroom-bench\job.json" -Encoding UTF8
    $before = Get-Date
    # Exit 4 is a preflight refusal (SM baseline or a video engine busy) before anything is logged or
    # swept. Unattended, a transient one must not end a five-hour session: wait and ask again, twice.
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -JobPath "C:\headroom-bench\job.json" | Out-Host
        $code = $LASTEXITCODE
        if ($code -ne 4 -or $attempt -eq 3) { break }
        Say "Preflight refused $label (exit 4, nothing swept). Waiting 120 s before asking again." "Yellow"
        Start-Sleep -Seconds 120
    }
    $dir = Get-ChildItem "C:\headroom-bench\results" -Directory -Filter "*_$label" | Where-Object { $_.CreationTime -ge $before.AddSeconds(-5) } | Sort-Object CreationTime | Select-Object -Last 1
    $d = $null
    if ($dir) {
        $csv = Get-ChildItem $dir.FullName -Filter "*_sweep.csv" | Select-Object -First 1
        $d = [ordered]@{
            sweep              = $(if ($csv) { $csv.FullName } else { (Join-Path $dir.FullName "missing_sweep.csv") })
            hwinfo             = Join-Path $dir.FullName "$label-hwinfo.csv"
            utc_offset_minutes = Get-UtcOffsetMinutes
            wrapper            = Join-Path $dir.FullName "wrapper-result.json"
        }
    }
    return @{ code = $code; descriptor = $d }
}

# One registered role: the sweep, and on a desktop-load exit (8) its sole retry (condition 1).
function Invoke-Role([string]$role, [string]$workload, [int[]]$targets, [string]$iterations, [string]$settings, $witness, [bool]$descending = $false) {
    if ($DryRun) { $targets = @($targets[0]) }
    $label = "$prefix-$role"
    Say ("sweep {0}: {1} at {2} MHz" -f $label, $workload, ($targets -join ", ")) "Cyan"
    $a = Run-Wrapper $label $workload $targets $iterations $settings $descending
    if ($Parts -eq "rep") {
        # Section 22 (GPT Job 94, F2): an unreadable event log is not "no events".
        $checked = Get-DriverEventsChecked
        Say ("exit {0} for {1}; event log read ok: {2}; display-driver events since session start: {3}" -f $a.code, $label, $checked.ok, $checked.count)
        if ($null -ne $a.descriptor) { $a.descriptor["driver_events"] = $checked }
        if (-not $checked.ok -or $checked.count -ne 0) { return "driver" }
        $events = @()
    } else {
        $events = Get-DriverEvents
        Say ("exit {0} for {1}; display-driver events since session start: {2}" -f $a.code, $label, $events.Count)
    }
    if ($events.Count -gt 0) { return "driver" }
    if ($a.code -eq 0) {
        $a.descriptor["witness"] = $witness
        $script:manifest.sweeps[$role] = $a.descriptor
        Save-Manifest
        return "ok"
    }
    if ($a.code -ne 8 -or $null -eq $a.descriptor) { return "failed" }
    if ($Parts -eq "rep") {
        # Section 22: no measured-role retry. The role is kept, marked NOT SCOREABLE, and the day goes on.
        $a.descriptor["witness"] = $witness
        $script:manifest.sweeps[$role] = $a.descriptor
        $script:manifest.notScoreable += $role
        Save-Manifest
        Say "DESKTOP LOAD in $label. Section 22 allows no retry: recorded NOT SCOREABLE, continuing." "Yellow"
        return "ok"
    }
    Say "DESKTOP LOAD in $label. Settling 60 s, then the sole retry." "Yellow"
    $a.descriptor["witness"] = $witness
    Start-Sleep -Seconds 60
    $b = Run-Wrapper "$label-retry" $workload $targets $iterations $settings $descending
    $events = Get-DriverEvents
    Say ("retry exit {0} for {1}; display-driver events: {2}" -f $b.code, $label, $events.Count)
    if ($events.Count -gt 0) { return "driver" }
    if ($null -eq $b.descriptor) { return "failed" }
    $b.descriptor["witness"] = $witness
    $script:manifest.sweeps[$role] = @($a.descriptor, $b.descriptor)
    if ($b.code -eq 8) {
        $script:manifest.notScoreable += $role
        Save-Manifest
        Say "${role}: second DESKTOP LOAD. Recorded; this role is NOT SCOREABLE (section 15 condition 1). Continuing." "Yellow"
        return "ok"
    }
    Save-Manifest
    if ($b.code -ne 0) { return "failed" }
    return "ok"
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

# ---- preflight ------------------------------------------------------------------------------
Say ("{3} session, parts {0}, {1}. Directory: {2}" -f $Parts, $(if ($DryRun) { "DRY RUN (first target only, one workload per suite)" } else { "REAL" }), $sessionDir, $SECTION) "Cyan"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Say "Not elevated." "Red"; exit 2 }
foreach ($p in @($MvoltPath, $ab, $wrapper, $storePath)) { if (-not (Test-Path -LiteralPath $p)) { Say "Missing: $p" "Red"; exit 2 } }
foreach ($k in $SNAPSHOTS.Keys) { if (-not (Test-Path -LiteralPath (Join-Path $SNAPSHOTS[$k] $STORE_NAME))) { Say "Missing snapshot store for $k." "Red"; exit 2 } }
$driver = First-Line (Invoke-BoundedSmi "--query-gpu=driver_version --format=csv,noheader" 30)
if ($driver -ne "616.92") { Say "Driver is $driver, not 616.92 (section 15 condition 3)." "Red"; exit 2 }
if (Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'") { Say "llama-server is running." "Red"; exit 3 }
if (@(Get-Process | Where-Object { $_.Path -and $_.Path -like "*mVolt*" }).Count -gt 0) { Say "An mVolt+ window is open. Close it." "Red"; exit 3 }
# Section 15 condition 1 names these. They are the operator's to close; this script does not kill them.
$open = @(Get-Process -Name "opera", "Discord", "Obsidian", "RobloxPlayerBeta", "steam", "EpicGamesLauncher" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName -Unique)
if ($open.Count -gt 0) { Say ("Close these before the session: {0}." -f ($open -join ", ")) "Red"; exit 3 }
if ($Parts -eq "rep" -and -not $REP_DAYS.ContainsKey($Session)) { Say "Section 22 needs -Session N, the day index 1-5 (a dry run too: it sets the order)." "Red"; exit 2 }
if ($Parts -eq "s20b") {
    if ($Session -lt 1 -and -not $DryRun) { Say "Section 20b needs -Session N (1-4 for the pilot)." "Red"; exit 2 }
    # Section 20b: HWiNFO must not run at all during the core arms (it polls the card), so it is
    # closed rather than started. Its windows are never HWiNFO-screened, and the record says so.
    @(Get-Process -Name "HWiNFO64" -ErrorAction SilentlyContinue) | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    if (@(Get-Process -Name "HWiNFO64" -ErrorAction SilentlyContinue).Count -gt 0) { Say "HWiNFO would not close." "Red"; exit 3 }
    Say "HWiNFO closed for section 20b (no sensor polling during the session)."
} else {
    & (Join-Path $repo "tools\hwinfo-logging\Start-HwinfoSensors.ps1") | ForEach-Object { Say $_ }
    if ($LASTEXITCODE -ne 0) { Say "HWiNFO Sensors not ready (exit $LASTEXITCODE)." "Red"; exit 3 }
}
$script:closedChatGpt = $false
if ($ManageChatGpt) {
    $wasRunning = @(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue).Count -gt 0
    if (-not (Close-ChatGpt)) { exit 3 }
    # Relaunch at the end only what was open at the start.
    $script:closedChatGpt = $wasRunning
} elseif (@(Get-Process -Name "ChatGPT", "codex" -ErrorAction SilentlyContinue).Count -gt 0) {
    Say "ChatGPT/Codex is running. Close it, or pass -ManageChatGpt." "Red"; exit 3
}
if ($Parts -in @("s20b", "rep")) {
    $pre = Get-DriverEventsChecked
    if (-not $pre.ok -or $pre.count -gt 0) { Say "Display-driver events since this script started, or the event log could not be read." "Red"; exit 3 }
} elseif ((Get-DriverEvents).Count -gt 0) { Say "Display-driver events already logged since this script started." "Red"; exit 3 }
# Sections 18 and 19: NVML's power readings and energy counter at 20 Hz for the whole session,
# the same load beside every arm (tools/power-probe/README.md). Stopped in the finally block.
$script:sampler = $null
$samplerStop = Join-Path $sessionDir "stop-sampler"
if ($Parts -eq "s19") {
    $samplerOut = Join-Path $sessionDir "power-samples.csv"
    $script:sampler = Start-Process -FilePath "python" -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
        -ArgumentList (Join-Path $repo "tools\power-probe\sample_power.py"), "--out", $samplerOut, "--hz", "20", "--stop-file", $samplerStop
    Start-Sleep -Seconds 5
    if ($script:sampler.HasExited -or -not (Test-Path -LiteralPath $samplerOut)) { Say "The NVML power logger did not start." "Red"; exit 3 }
    $script:manifest["powerSamples"] = $samplerOut
    Say "NVML power logger running at 20 Hz (pid $($script:sampler.Id)): $samplerOut" "Green"
}
Save-Manifest

$common = ("$SECTION. HWiNFO 0.50 s, driver $driver, operator absent, " +
    "Claude minimized, ChatGPT/Codex/Opera/Discord/Obsidian closed. mVolt+ offsets and voltage demands read 0.") +
    $(if ($DryRun) { " DRY RUN: not $SECTION data." } else { "" })
function Text([string]$arm, $w) {
    return ("{0} Store restored byte for byte from snapshot {1} with Afterburner closed, sections verified. " +
        "Applied by MSIAfterburner.exe -profile{2} -q, VERIFIED LIVE: memory under load {3} MHz, power limit {4} W. {5}") -f $arm, $w.snapshot, $w.profile_slot, $w.memory_loaded_mhz, $w.power_limit_w, $common
}
$STOCK = "AFTERBURNER PROFILE 3 = STOCK (180 W, memory +0, curve offsets 0)."
$CURVE3 = "AFTERBURNER PROFILE 1 = CURVE 3 (P4's curve exactly, memory +0, 200 W)."
$RUNGB = "AFTERBURNER PROFILE 1 = RUNG B (P5 with points at or below 840 mV raised ~+170 MHz; memory +2500, 200 W)."
$RUNGC = "AFTERBURNER PROFILE 1 = RUNG C (registered rung C curve; memory +2500, 200 W)."
$P4 = "AFTERBURNER PROFILE 4 = FULL TUNE (flattened curve above ~925 mV; memory +2500, 200 W)."
$P2 = "AFTERBURNER PROFILE 2 = REPAIR (stock slope below ~925 mV, P4's top; memory +2500, 200 W)."
$P5 = "AFTERBURNER PROFILE 5 = SPLIT (factory floor region below ~840 mV, flattened top; memory +2500, 200 W)."

function Invoke-Suite([string]$arm, [string]$text, $w, [bool]$descending = $false) {
    $names = @($ITER.Keys)
    if ($DryRun) { $names = @(@($ITER.Keys)[0]) }
    foreach ($n in $names) {
        $note = $(if ($descending) { "{0} Sweep order DESCENDING." -f (Text $text $w) } else { (Text $text $w) })
        $r = Invoke-Role "$arm-$n" $n $GRID ([string]$ITER[$n]) $note $w $descending
        if ($r -ne "ok") { return $false }
    }
    return $true
}

# Section 20: one twelve-workload suite on a fine grid, in the given direction.
function Invoke-FineSuite([string]$arm, [string]$text, $w, [int[]]$targets, [bool]$descending) {
    $names = @($ITER.Keys)
    if ($DryRun) { $names = @(@($ITER.Keys)[0]) }
    $order = $(if ($descending) { "DESCENDING" } else { "ascending" })
    foreach ($n in $names) {
        $r = Invoke-Role "$arm-$n" $n $targets ([string]$ITER[$n]) ("{0} Sweep order {1}." -f (Text $text $w), $order) $w $descending
        if ($r -ne "ok") { return $false }
    }
    return $true
}

# Section 20b: stock witnessed, then every other poller closed and stock verified again, then the
# Python controller runs the balanced session. Display-driver events are written beside its output.
function Invoke-Section20b {
    $w = Set-Arm "s20b-stock" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
    Say "Closing Afterburner and RTSS so nothing else polls the card; Profile 3 (stock) stays applied." "Cyan"
    @(Get-Process -Name "MSIAfterburner", "RTSS", "RTSSHooksLoader64" -ErrorAction SilentlyContinue) | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 10
    $left = @(Get-Process -Name "MSIAfterburner", "RTSS" -ErrorAction SilentlyContinue)
    if ($left.Count -gt 0) { Say "Afterburner or RTSS would not close." "Red"; return 5 }
    $mem = Get-MemClockUnderLoad
    $pl = Get-PowerLimit
    Say ("With Afterburner closed: memory under load {0} MHz, power limit {1} W." -f $mem, $pl)
    if ($mem -ne $STOCK_MEM -or [math]::Abs($pl - 180) -gt 0.5) { Say "Stock did not hold with Afterburner closed. Refusing." "Red"; return 5 }
    try {
        Add-Type -Namespace HeadroomS20b -Name Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c); [DllImport("user32.dll")] public static extern bool IsIconic(System.IntPtr h);' -ErrorAction Stop
        $n = 0
        foreach ($h in @(Get-Process -Name claude -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object { $_.MainWindowHandle })) {
            if (-not [HeadroomS20b.Win]::IsIconic($h)) { [void][HeadroomS20b.Win]::ShowWindow($h, 6); $n++ }
        }
        Say "Claude windows minimized now: $n."
    } catch { Say ("Could not minimize Claude ({0})." -f $_.Exception.Message) "Yellow" }
    $core = Join-Path $sessionDir "core"
    $py = (Get-Command python).Source
    $ctl = Join-Path $repo "tools\section20b\run_core_session.py"
    $since = @("--events-since", $sessionStart.ToString("o"))
    $ctlArgs = if ($DryRun) { @($ctl, "--qualification", "--out", $core) + $since } else { @($ctl, "--session-index", "$Session", "--stage", "pilot", "--out", $core) + $since }
    $script:s20bCore = $core
    Say ("Controller: {0}" -f ($ctlArgs -join " ")) "Cyan"
    & $py @ctlArgs | ForEach-Object { Say $_ }
    $code = $LASTEXITCODE
    $events = Get-DriverEventsChecked
    if (Test-Path -LiteralPath $core) {
        Write-JsonNoBom (Join-Path $core "driver-events.json") ([ordered]@{ query_ok = $events.ok; count = $events.count; since = $sessionStart.ToString("o"); ids = $events.ids; error = $events.error })
    }
    $script:manifest["core"] = $core
    $script:manifest["controllerExit"] = $code
    Save-Manifest
    Say ("Controller exit {0}; event log read {1}; display-driver events since session start: {2}." -f $code, $events.ok, $events.count)
    # A driver event, or an unreadable event log, fails the session even if the controller finished (F5).
    if ($code -ne 0 -or -not $events.ok -or $events.count -ne 0) { return 7 }
    return 0
}

# Section 22: one day. Stock witnessed, the first pass, stock re-witnessed, the mirrored second pass.
function Invoke-Repeatability {
    $day = $REP_DAYS[$Session]
    $order1 = @($day.order); $desc1 = [bool]$day.descending
    $order2 = @($order1[($order1.Count - 1)..0]); $desc2 = -not $desc1
    $commit = (& git -C $repo rev-parse HEAD 2>$null | Select-Object -First 1)
    $script:manifest["repeatability"] = [ordered]@{
        day = $Session; localDate = (Get-Date -Format "yyyy-MM-dd"); utcOffsetMinutes = Get-UtcOffsetMinutes
        commit = [string]$commit; grid = $REP_GRID; inputSeed = $REP_SEED; iterations = $ITER
        pass1 = [ordered]@{ order = $order1; descending = $desc1 }; pass2 = [ordered]@{ order = $order2; descending = $desc2 }
    }
    Save-Manifest
    Say ("==== Section 22, day {0}: pass 1 {1} {2}; pass 2 {3} {4}; stock only ====" -f $Session, ($order1 -join ","), $(if ($desc1) { "descending" } else { "ascending" }), ($order2 -join ","), $(if ($desc2) { "descending" } else { "ascending" })) "Cyan"
    foreach ($pass in @(@{ n = 1; order = $order1; desc = $desc1 }, @{ n = 2; order = $order2; desc = $desc2 })) {
        $w = Set-Arm ("rep-d{0}-pass{1}" -f $Session, $pass.n) 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        $dir = $(if ($pass.desc) { "DESCENDING" } else { "ascending" })
        foreach ($n in $pass.order) {
            $note = "{0} Day {1} pass {2} {3}." -f (Text $STOCK $w), $Session, $pass.n, $dir
            $r = Invoke-Role ("pass{0}-{1}" -f $pass.n, $n) $n $REP_GRID ([string]$ITER[$n]) $note $w ([bool]$pass.desc)
            if ($r -ne "ok") { return 7 }
        }
    }
    Say "Section 22 day $Session complete." "Green"
    return 0
}

function Invoke-Session {
    if (-not (Restore-Store "curve3")) { return 4 }
    if ($Parts -eq "s20b") { return (Invoke-Section20b) }
    if ($Parts -eq "rep") { return (Invoke-Repeatability) }
    if ($Parts -eq "s16") {
        Say "==== Section 16: P5 -> P4 -> P2 -> P5, twelve workloads each ====" "Cyan"
        $w = Set-Arm "s16-p5a" 5 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "5060ti-ctrl10-p5a" $P5 $w)) { return 7 }
        $w = Set-Arm "s16-p4" 4 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "5060ti-s16-p4" $P4 $w)) { return 7 }
        $w = Set-Arm "s16-p2" 2 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "5060ti-ctrl10-p2" $P2 $w)) { return 7 }
        $w = Set-Arm "s16-p5b" 5 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "5060ti-ctrl10-p5b" $P5 $w)) { return 7 }
        Say "Section 16 complete." "Green"
        return 0
    }
    if ($Parts -eq "s21") {
        Say "==== Section 21: stock coarse asc -> stock fine asc -> P4 fine asc -> P4 fine desc -> stock fine desc -> stock coarse desc, four application workloads ====" "Cyan"
        $w = Set-Arm "s21-stock-coarse-asc" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "stock-coarse-asc" $STOCK $w $false)) { return 7 }
        $w = Set-Arm "s21-stock-fine-asc" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "stock-fine-asc" $STOCK $w $FINE_STOCK $false)) { return 7 }
        $w = Set-Arm "s21-p4-fine-asc" 4 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "p4-fine-asc" $P4 $w $FINE_P4 $false)) { return 7 }
        $w = Set-Arm "s21-p4-fine-desc" 4 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "p4-fine-desc" $P4 $w $FINE_P4 $true)) { return 7 }
        $w = Set-Arm "s21-stock-fine-desc" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "stock-fine-desc" $STOCK $w $FINE_STOCK $true)) { return 7 }
        $w = Set-Arm "s21-stock-coarse-desc" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "stock-coarse-desc" $STOCK $w $true)) { return 7 }
        Say "Section 21 complete." "Green"
        return 0
    }
    if ($Parts -eq "s20") {
        Say "==== Section 20: stock ascending -> P4 ascending -> P4 descending -> stock descending, fine grid, twelve workloads each ====" "Cyan"
        $w = Set-Arm "s20-stock-asc" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "stock-asc" $STOCK $w $FINE_STOCK $false)) { return 7 }
        $w = Set-Arm "s20-p4-asc" 4 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "p4-asc" $P4 $w $FINE_P4 $false)) { return 7 }
        $w = Set-Arm "s20-p4-desc" 4 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "p4-desc" $P4 $w $FINE_P4 $true)) { return 7 }
        $w = Set-Arm "s20-stock-desc" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-FineSuite "stock-desc" $STOCK $w $FINE_STOCK $true)) { return 7 }
        Say "Section 20 complete." "Green"
        return 0
    }
    if ($Parts -eq "s19") {
        Say "==== Sections 18 and 19: stock -> P5 -> P4 -> rung B -> rung C -> stock, twelve workloads each ====" "Cyan"
        $w = Set-Arm "s19-stock-open" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "stock-open" $STOCK $w)) { return 7 }
        $w = Set-Arm "s19-p5" 5 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "p5" $P5 $w)) { return 7 }
        $w = Set-Arm "s19-p4" 4 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "p4" $P4 $w)) { return 7 }
        if (-not (Restore-Store "rungB")) { return 4 }
        $w = Set-Arm "s19-rungB" 1 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "rungB" $RUNGB $w)) { return 7 }
        if (-not (Restore-Store "rungC")) { return 4 }
        $w = Set-Arm "s19-rungC" 1 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "rungC" $RUNGC $w)) { return 7 }
        $w = Set-Arm "s19-stock-close" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "stock-close" $STOCK $w)) { return 7 }
        Say "Sections 18 and 19 complete." "Green"
        return 0
    }
    if ($Parts -in @("r1", "r1r3")) {
        Say "==== R1: section 12 again, memory matched ====" "Cyan"
        $w = Set-Arm "r1-stock-open" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if ((Invoke-Role "stock-open-membw" "membw" $BAND "" (Text $STOCK $w) $w) -ne "ok") { return 7 }
        if ((Invoke-Role "stock-gemm" "gemm" $GRID "120" (Text $STOCK $w) $w) -ne "ok") { return 7 }
        $w = Set-Arm "r1-curve3" 1 200 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if ((Invoke-Role "curve3-membw" "membw" $BAND "" (Text $CURVE3 $w) $w) -ne "ok") { return 7 }
        if ((Invoke-Role "curve3-gemm" "gemm" $GRID "120" (Text $CURVE3 $w) $w) -ne "ok") { return 7 }
        $w = Set-Arm "r1-stock-close" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if ((Invoke-Role "stock-close-membw" "membw" $BAND "" (Text $STOCK $w) $w) -ne "ok") { return 7 }
        Say "R1 complete." "Green"
    }
    if ($Parts -eq "r2") {
        Say "==== R2: the 2026-08-20 pair and the repair, clean ====" "Cyan"
        $w = Set-Arm "r2-stock-open" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if ((Invoke-Role "stock-open-membw" "membw" $BAND "" (Text $STOCK $w) $w) -ne "ok") { return 7 }
        $w = Set-Arm "r2-p4" 4 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if ((Invoke-Role "p4-membw" "membw" $BAND "" (Text $P4 $w) $w) -ne "ok") { return 7 }
        $w = Set-Arm "r2-p2" 2 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if ((Invoke-Role "p2-membw" "membw" $BAND "" (Text $P2 $w) $w) -ne "ok") { return 7 }
        $w = Set-Arm "r2-stock-close" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if ((Invoke-Role "stock-close-membw" "membw" $BAND "" (Text $STOCK $w) $w) -ne "ok") { return 7 }
        Say "R2 complete." "Green"
    }
    if ($Parts -in @("r3", "r1r3")) {
        Say "==== R3: both ladder rungs between stock suites ====" "Cyan"
        $w = Set-Arm "r3-stock-open" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "stock-open" $STOCK $w)) { return 7 }
        if (-not (Restore-Store "rungB")) { return 4 }
        $w = Set-Arm "r3-rungB" 1 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "rungB" $RUNGB $w)) { return 7 }
        if (-not (Restore-Store "rungC")) { return 4 }
        $w = Set-Arm "r3-rungC" 1 200 $OC_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "rungC" $RUNGC $w)) { return 7 }
        $w = Set-Arm "r3-stock-close" 3 180 $STOCK_MEM; if ($null -eq $w) { return 5 }
        if (-not (Invoke-Suite "stock-close" $STOCK $w)) { return 7 }
        Say "R3 complete." "Green"
    }
    return 0
}

$exitCode = 8
$script:s20bCore = $null
try { $exitCode = Invoke-Session }
finally {
    Say "Restoring: clocks reset, curve 3 store, Profile 3 (stock)." "Cyan"
    # Each step is attempted whatever the one before it did, and every error is kept (GPT Job 76, R5).
    $cleanupErrors = @()
    $resetCode = -1
    try {
        $reset = Invoke-BoundedNative "-rgc" 60
        $resetCode = $reset.code
        if ($reset.error) { $cleanupErrors += "reset: $($reset.error)" }
    } catch { $cleanupErrors += "reset: $($_.Exception.Message)" }
    $storeOk = $true
    try {
        if ($script:snapshot -ne "curve3") { $storeOk = [bool](Restore-Store "curve3") }
    } catch { $storeOk = $false; $cleanupErrors += "store: $($_.Exception.Message)" }
    try { & $ab -profile3 -q } catch { $cleanupErrors += "profile 3: $($_.Exception.Message)" }
    Start-Sleep -Seconds 8
    $mem = -1
    try { $mem = Get-MemClockUnderLoad } catch { $cleanupErrors += "memory witness: $($_.Exception.Message)" }
    $pl = -1
    try { $pl = Get-PowerLimit } catch { $cleanupErrors += "power limit: $($_.Exception.Message)" }
    $stockOk = ($mem -eq $STOCK_MEM -and [math]::Abs($pl - 180) -le 0.5)
    if (-not $stockOk) { Say "** NOT back on stock: memory $mem MHz, power limit $pl W. Apply Profile 3 by hand. **" "Red" }
    else { Say "Back on stock: memory $mem MHz under load, power limit $pl W." "Green" }
    # Section 20b (GPT Job 73, F1): the cleanup is evidence the scorer requires, and a failed one fails
    # the session rather than being a red line in a log.
    $cleanupOk = ($resetCode -eq 0 -and $storeOk -and $stockOk -and $cleanupErrors.Count -eq 0)
    foreach ($e in $cleanupErrors) { Say "Cleanup error: $e" "Red" }
    if ($null -ne $script:s20bCore -and (Test-Path -LiteralPath $script:s20bCore)) {
        try {
            Write-JsonNoBom (Join-Path $script:s20bCore "runner-cleanup.json") ([ordered]@{ ok = $cleanupOk; reset_exit = $resetCode; store_restored = $storeOk; memory_loaded_mhz = $mem; power_limit_w = $pl; errors = @($cleanupErrors) })
        } catch { $cleanupOk = $false; Say "Writing runner-cleanup.json failed: $($_.Exception.Message)" "Red" }
    }
    if ($Parts -eq "rep") {
        # Section 22: the cleanup is evidence the scorer requires, as for section 20b.
        try {
            Write-JsonNoBom (Join-Path $sessionDir "runner-cleanup.json") ([ordered]@{ ok = $cleanupOk; reset_exit = $resetCode; store_restored = $storeOk; memory_loaded_mhz = $mem; power_limit_w = $pl; errors = @($cleanupErrors) })
        } catch { $cleanupOk = $false; Say "Writing runner-cleanup.json failed: $($_.Exception.Message)" "Red" }
    }
    if ($Parts -eq "rep") {
        # GPT Job 94, F2: the event log is read once more after cleanup, so the last role and the
        # restore are covered too; the scorer requires this record.
        $final = Get-DriverEventsChecked
        $final["read_at_unix"] = [math]::Round(((Get-Date).ToUniversalTime() - [datetime]'1970-01-01').TotalSeconds, 3)
        $final["session_start_unix"] = [math]::Round(($sessionStart.ToUniversalTime() - [datetime]'1970-01-01').TotalSeconds, 3)
        $script:manifest["driverEventsFinal"] = $final
        if (-not $final.ok -or $final.count -ne 0) { $cleanupOk = $false; Say "Display-driver events after the session, or the event log could not be read." "Red" }
    }
    if ($Parts -in @("s20b", "rep") -and -not $cleanupOk -and $exitCode -eq 0) { $exitCode = 9 }
    if ($null -ne $script:sampler) {
        New-Item -ItemType File -Force -Path $samplerStop | Out-Null
        if (-not $script:sampler.WaitForExit(10000)) { $script:sampler | Stop-Process -Force -ErrorAction SilentlyContinue }
        Say "NVML power logger stopped."
    }
    $script:manifest["exitCode"] = $exitCode
    Save-Manifest
    if ($script:closedChatGpt) {
        & explorer.exe "shell:AppsFolder\$CHATGPT_APPID"
        Say "ChatGPT relaunched."
    }
    $ns = @($script:manifest.notScoreable)
    $why = $(if ($Parts -eq "rep") { "after a desktop load (section 22 allows no retry)" } else { "after a second desktop load" })
    Say ("Exit code {0}. Roles NOT SCOREABLE {3}: {1}. Manifest: {2}" -f $exitCode, $(if ($ns.Count) { $ns -join ", " } else { "none" }), $manifestPath, $why)
}
exit $exitCode
