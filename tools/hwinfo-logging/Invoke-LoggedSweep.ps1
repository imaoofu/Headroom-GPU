<#
.SYNOPSIS
    Run one logged sweep start to finish, with no human and no GUI interaction by any agent.

.DESCRIPTION
    Reads a JOB FILE, validates every field, then does the whole boundary sequence itself:

        preflight -> HWiNFO log start -> frequency sweep -> HWiNFO log stop -> result file

    Designed to be the ONLY thing a scheduled task runs, so that an unelevated agent can trigger
    a bench run with `schtasks /run` and never touch an elevated window. See README.md for why
    that indirection is necessary rather than merely tidy (UIPI; the Codex MSIX cannot elevate).

.PARAMETER JobPath
    The job file. Defaults to the fixed location the scheduled task uses.

.PARAMETER WhatIfOnly
    Validate the job and print the plan. Changes no GPU state, starts no log.

.NOTES
    🛑 THE SECURITY RULE THIS SCRIPT ENFORCES, AND WHY IT IS NOT PARANOIA.
        The scheduled task runs ELEVATED. If the job file could name the command to run, or the
        path to write, then any process that can write a file would have arbitrary administrator
        execution. So:

          - The workload COMMAND is constructed here from a whitelisted workload NAME. The job
            file cannot supply a command line.
          - The output directory is DERIVED from the label. The job file cannot supply a path,
            so path traversal has nothing to traverse.
          - Every numeric field is range-checked, and the label is pattern-matched.
          - Anything unrecognised is a refusal, not a default.

        The job file is a REQUEST. It is never an instruction.
#>

[CmdletBinding()]
param(
    [string]$JobPath = "C:\headroom-bench\job.json",
    [switch]$WhatIfOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$sweep    = Join-Path $repoRoot "tools\frequency-sweep\Invoke-FrequencySweep.ps1"
$gpuWorkload = Join-Path $repoRoot "tools\frequency-sweep\gpu_workload.py"
$llmWorkload = Join-Path $repoRoot "tools\frequency-sweep\llm_workload.py"
$logTool  = Join-Path $PSScriptRoot "Invoke-HwinfoLogging.ps1"

# Output always lands under here, one directory per label. Never taken from the job.
$resultsRoot = "C:\headroom-bench\results"

# The only workloads this wrapper will ever run.
$allowedWorkloads = @("gemm", "membw", "copy", "reduce", "softmax", "layernorm",
                      "bgemm32", "bgemm64", "bgemm128", "bgemm256", "bgemm1024",
                      "attention", "conv", "llm-prefill", "llm-decode",
                      "alexnet", "resnet50", "kmeans", "hotspot")

function Say([string]$t, [string]$c = "White") { Write-Host $t -ForegroundColor $c }
function Die([string]$t, [int]$code) { Say $t "Red"; exit $code }

# ---- read and validate the job ---------------------------------------------------------------

if (-not (Test-Path $JobPath)) { Die "No job file at $JobPath." 2 }

try { $job = Get-Content $JobPath -Raw | ConvertFrom-Json }
catch { Die "Job file is not valid JSON: $($_.Exception.Message)" 2 }

$label = [string]$job.label
if ($label -notmatch '^[a-z0-9][a-z0-9-]{2,63}$') {
    Die "label must be 3-64 chars of lowercase letters, digits and hyphens. Got '$label'." 2
}

$work = [string]$job.workload
if ($allowedWorkloads -notcontains $work) {
    Die ("workload '{0}' is not in the allowed list: {1}" -f $work, ($allowedWorkloads -join ", ")) 2
}
$workload = if ($work -in @("llm-prefill", "llm-decode")) { $llmWorkload } else { $gpuWorkload }

function Need-Int($value, $name, $lo, $hi) {
    $n = 0
    if (-not [int]::TryParse([string]$value, [ref]$n)) { Die "$name must be an integer. Got '$value'." 2 }
    if ($n -lt $lo -or $n -gt $hi) { Die "$name must be between $lo and $hi. Got $n." 2 }
    return $n
}

# An explicit target list (added 2026-09-30 for REGISTERED-PREDICTIONS section 14, whose arms are
# single targets) replaces minMhz / maxMhz / frequencyCount; giving both is refused. It is passed
# to Invoke-FrequencySweep.ps1 -TargetFrequenciesMhz, which sweeps exactly those clocks or refuses.
$targets = @()
$hasTargets = ($job.PSObject.Properties.Name -contains "targets") -and ($null -ne $job.targets)
if ($hasTargets) {
    foreach ($name in @("minMhz", "maxMhz", "frequencyCount")) {
        if ($job.PSObject.Properties.Name -contains $name) { Die "targets cannot be combined with $name. Give one or the other." 2 }
    }
    foreach ($value in @($job.targets)) { $targets += (Need-Int $value "targets entry" 200 4000) }
    if ($targets.Count -lt 1 -or $targets.Count -gt 40) { Die "targets must hold 1 to 40 clocks. Got $($targets.Count)." 2 }
    $minMhz = ($targets | Measure-Object -Minimum).Minimum
    $maxMhz = ($targets | Measure-Object -Maximum).Maximum
    $count = $targets.Count
} else {
    $minMhz = Need-Int $job.minMhz "minMhz" 200 4000
    $maxMhz = Need-Int $job.maxMhz "maxMhz" 200 4000
    $count  = Need-Int $job.frequencyCount "frequencyCount" 3 40
    if ($maxMhz -le $minMhz) { Die "maxMhz ($maxMhz) must exceed minMhz ($minMhz)." 2 }
}

$applied = [string]$job.appliedSettings
if ($applied.Trim().Length -lt 20) {
    Die "appliedSettings is required and must actually describe the configuration. It is the one field nothing can reconstruct afterwards." 2
}
if ($applied.Length -gt 600) { Die "appliedSettings is implausibly long ($($applied.Length) chars)." 2 }

# ⚠️ ONE workload per sweep here, so iterations is ONE integer - not the comma-separated list the
# kit's Collect.ps1 takes for a twelve-workload suite. It reaches the benchmark through
# gpu_workload.py --iterations, because Invoke-FrequencySweep.ps1 has no such parameter.
$iterations = ""
if ($job.PSObject.Properties.Name -contains "iterations" -and $job.iterations) {
    $iterations = [string]$job.iterations
    if ($iterations -notmatch '^\d{1,9}$') {
        Die "iterations must be a single integer for a one-workload sweep. Got '$iterations'." 2
    }
}

# Optional input seed (the repeatability study, 2026-10-14): passed to gpu_workload.py --input-seed as
# structured data, range-checked here. Absent means the historical unseeded inputs.
$inputSeed = ""
if ($job.PSObject.Properties.Name -contains "inputSeed" -and $null -ne $job.inputSeed) {
    $inputSeed = [string](Need-Int $job.inputSeed "inputSeed" 0 2147483647)
}

$descending = $false
if ($job.PSObject.Properties.Name -contains "descending") { $descending = [bool]$job.descending }

$expectMinutes = Need-Int $job.expectedMinutes "expectedMinutes" 1 240

# ---- derived paths ---------------------------------------------------------------------------

$stamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir  = Join-Path $resultsRoot ("{0}_{1}" -f $stamp, $label)
$logPath = Join-Path $outDir ("{0}-hwinfo.csv" -f $label)
$result  = Join-Path $outDir "wrapper-result.json"

Say ""
Say "================ PLAN ================" "Cyan"
Say ("  label        : {0}" -f $label)
Say ("  workload     : {0}" -f $work)
Say ("  runner       : {0}" -f $workload)
if ($hasTargets) {
    Say ("  targets      : {0} MHz, exactly{1}" -f ($targets -join ", "), $(if ($descending) { ", DESCENDING" } else { "" }))
} else {
    Say ("  band         : {0}-{1} MHz, {2} points{3}" -f $minMhz, $maxMhz, $count, $(if ($descending) { ", DESCENDING" } else { "" }))
}
Say ("  iterations   : {0}" -f $(if ($iterations) { $iterations } else { "(tool default)" }))
if ($inputSeed) { Say ("  input seed   : {0}" -f $inputSeed) }
Say ("  output dir   : {0}" -f $outDir)
Say ("  hwinfo log   : {0}" -f $logPath)
Say ("  expected     : ~{0} min" -f $expectMinutes)
Say ("  applied      : {0}" -f $applied)
Say ""

if ($WhatIfOnly) { Say "WhatIfOnly - validated, nothing run, no GPU state touched." "Yellow"; exit 0 }

# An idle llama-server holds almost the whole 5060 Ti VRAM while showing zero SM activity.
# Refuse before opening the HWiNFO log, with the process named in the message.
$server = Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" -ErrorAction Stop
if ($server) { Die "Preflight failed: llama-server is running. Stop llama-server before any sweep." 4 }

foreach ($needed in @($sweep, $workload, $logTool)) {
    if (-not (Test-Path $needed)) { Die "Missing required script: $needed" 3 }
}
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# ---- preflight -------------------------------------------------------------------------------
# ⛔ This is a gate, not a formality. A run that begins on a contaminated machine produces data
# that looks fine and is worth nothing - measured at 9.38% on 2026-09-18, and a point-to-point
# residual cannot find it afterwards because it is blind to a uniform offset.

Say "---- preflight ----" "Cyan"
$power = (& nvidia-smi --query-gpu=power.limit,power.default_limit --format=csv,noheader) -join " | "
Say ("  power limit : {0}" -f $power)

# Minimize the Claude desktop app before measuring (2026-10-03). Its visible window costs 6-9% of
# membw even when another window covers it, and shows in HWiNFO as ~200 fps presented with ~45% GPU
# bus load (data/frequency-sweeps/5060ti-deskload-20261003/). Minimized, the load is gone. Only its
# windows are touched; HWiNFO's Sensors window must stay up for the log buttons.
try {
    Add-Type -Namespace HeadroomSweep -Name Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c); [DllImport("user32.dll")] public static extern bool IsIconic(System.IntPtr h);' -ErrorAction Stop
    $claudeWindows = @(Get-Process -Name claude -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object { $_.MainWindowHandle })
    $minimized = 0
    foreach ($h in $claudeWindows) { if (-not [HeadroomSweep.Win]::IsIconic($h)) { [void][HeadroomSweep.Win]::ShowWindow($h, 6); $minimized++ } }
    if ($minimized -gt 0) { Start-Sleep -Seconds 5 }
    Say ("  claude app  : {0} window(s) found, {1} minimized now" -f $claudeWindows.Count, $minimized)
} catch {
    Say ("  claude app  : could not minimize ({0})" -f $_.Exception.Message) "Yellow"
}

# Which processes use the GPU at the start, and which window is in front. RECORDED, NOT GATED
# (2026-10-01): an unidentified desktop load presenting ~150-240 fps sat under section 12, the
# section 14 dry run and section 10's re-collection, about 10% on membw, and nothing logged which
# process it was. Windows' per-process GPU engine counters name it. No threshold is set until the
# source is known; check_desktop_load.py flags it from the HWiNFO log afterwards.
try {
    Add-Type -Namespace HeadroomSweep -Name Fg -MemberDefinition '[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow(); [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr h, out uint p);' -ErrorAction Stop
    $fgPid = [uint32]0; [void][HeadroomSweep.Fg]::GetWindowThreadProcessId([HeadroomSweep.Fg]::GetForegroundWindow(), [ref]$fgPid)
    $fgName = (Get-Process -Id $fgPid -ErrorAction SilentlyContinue).ProcessName
    $engine = @{}
    foreach ($s in (Get-Counter '\GPU Engine(*)\Utilization Percentage' -SampleInterval 2 -MaxSamples 2 -ErrorAction Stop).CounterSamples) {
        if ($s.InstanceName -match 'pid_(\d+)_.*engtype_(.+)$') {
            $n = (Get-Process -Id ([int]$Matches[1]) -ErrorAction SilentlyContinue).ProcessName
            $key = "{0} ({1})" -f $(if ($n) { $n } else { "pid " + $Matches[1] }), $Matches[2]
            $engine[$key] = [double]$engine[$key] + $s.CookedValue / 2
        }
    }
    $gpuUsers = @($engine.GetEnumerator() | Where-Object { $_.Value -ge 0.1 } | Sort-Object Value -Descending | ForEach-Object { "{0} {1:N1}%" -f $_.Key, $_.Value })
    $snapshot = @("foreground window: $fgName") + $(if ($gpuUsers.Count) { $gpuUsers } else { @("no process above 0.1% on any GPU engine") })
    Set-Content -Path (Join-Path $outDir "gpu-processes-at-start.txt") -Value $snapshot -Encoding ASCII
    Say ("  foreground  : {0}" -f $fgName)
    Say ("  GPU users   : {0}" -f $(if ($gpuUsers.Count) { ($gpuUsers | Select-Object -First 4) -join "; " } else { "none above 0.1%" }))
} catch {
    Say ("  GPU users   : not recorded ({0})" -f $_.Exception.Message) "Yellow"
}

# ⛔ THIS GATED ON THE `mem` COLUMN UNTIL 2026-09-22 AND REFUSED A LEGITIMATE RUN.
# pmon -s u prints: gpu pid type sm mem enc dec jpg ofa command. `mem` is memory-BANDWIDTH
# utilisation, not a busy signal - a desktop compositor reads 12% there while doing nothing that
# competes for SMs. The documented protocol gates on SM baseline and on the VIDEO ENGINES
# (Instant Replay is invisible in sm and shows up in enc), so those are what is checked.
# 🔑 Sum sm ACROSS PROCESSES per sample: two processes at 6% is a busier card than one at 9%.
$pmon = & nvidia-smi pmon -c 4 -s u 2>&1

$samples = @{}          # sample index -> summed sm
$videoBusy = $false
$sampleIndex = -1
$seenPids = @{}
foreach ($line in $pmon) {
    if ($line -match '^\s*#') { continue }
    $cols = ($line -split '\s+') | Where-Object { $_ -ne "" }
    if ($cols.Count -lt 7) { continue }
    $processId = $cols[1]
    # pmon repeats the whole process list once per sample, so a repeated pid starts a new sample.
    if ($seenPids.ContainsKey($processId)) { $seenPids = @{}; }
    if ($seenPids.Count -eq 0) { $sampleIndex++; $samples[$sampleIndex] = 0 }
    $seenPids[$processId] = $true

    $sm = 0
    if ([int]::TryParse($cols[3], [ref]$sm)) { $samples[$sampleIndex] += $sm }
    foreach ($videoIdx in 5, 6) {
        $v = 0
        if ([int]::TryParse($cols[$videoIdx], [ref]$v)) { if ($v -gt 0) { $videoBusy = $true } }
    }
}

$smValues = @($samples.Values)
$smPeak = 0
foreach ($v in $smValues) { if ($v -gt $smPeak) { $smPeak = $v } }
$smMean = 0
if ($smValues.Count -gt 0) { $smMean = [math]::Round(($smValues | Measure-Object -Sum).Sum / $smValues.Count, 1) }

Say ("  pmon sm     : mean {0}%, peak {1}% across {2} sample(s)" -f $smMean, $smPeak, $smValues.Count)

if ($videoBusy) {
    $pmon | ForEach-Object { Say ("    " + $_) "Gray" }
    Die "Preflight failed: encoder or decoder is active. Switch off Instant Replay / ShadowPlay." 4
}
# 10% matches Invoke-FrequencySweep's own -MaxBaselineUtilization default, so this refuses
# before the sweep does rather than after it has locked clocks.
if ($smPeak -gt 10) {
    $pmon | ForEach-Object { Say ("    " + $_) "Gray" }
    Die ("Preflight failed: SM baseline peaked at {0}%, over the 10% guard." -f $smPeak) 4
}
# ⚠️ Not a pass/fail, but it goes in the record: the committed CLEAN reference run of 2026-09-18
# declares "baseline 3.4 pct mean / 5 pct max". A run materially above that is comparable to it
# only with the caveat stated.
if ($smMean -gt 5) {
    Say "  NOTE: baseline is above the 5% the 2026-09-18 clean reference declares - recorded, not fatal." "Yellow"
}
Say "  pmon        : idle enough to proceed" "Green"

# ---- log start -------------------------------------------------------------------------------

Say ""
Say "---- HWiNFO log start ----" "Cyan"
& $logTool -Start -LogPath $logPath
if ($LASTEXITCODE -ne 0) { Die "Could not start HWiNFO logging (exit $LASTEXITCODE). Nothing was swept." 5 }

# ---- the sweep -------------------------------------------------------------------------------
# From here on, always stop the log - a sweep that dies must not leave logging running, or the
# next run's log would span two configurations and the join bins by core clock.

$sweepExit = -1
$startedAt = Get-Date
try {
    Say ""
    Say "---- sweep ----" "Cyan"
    $py = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $py) { throw "python is not on PATH - the workload cannot be launched." }

    # ⛔ DO NOT QUOTE THESE PATHS. Invoke-FrequencySweep runs the command through
    #      Start-Process -FilePath cmd.exe -ArgumentList "/c", $WorkloadCommand
    #    and `cmd /c` strips the outer quote pair of the string it is handed. A command that
    #    begins with a quote therefore arrives mangled, and the workload dies with
    #    "The filename, directory name, or volume label syntax is incorrect" - which looks like
    #    a path problem and is really a quoting problem. Cost one run on 2026-09-22.
    #    ✅ The committed 2026-09-18 sweep that this run is compared against is unquoted too.
    #
    # 🔑 Unquoted only works while no path contains a space, so that is checked rather than
    #    assumed. Refusing here is far better than discovering it at the first frequency.
    foreach ($p in @($py.Source, $workload)) {
        if ($p -match '\s') {
            Die ("Cannot build an unquoted workload command: '{0}' contains a space. " -f $p +
                 "Quoting would be stripped by cmd /c inside the sweep tool. Move it to a path without spaces.") 3
        }
    }

    $cmd = '{0} {1} --workload {2} --json' -f $py.Source, $workload, $work
    if ($iterations) { $cmd = "$cmd --iterations $iterations" }
    if ($inputSeed) { $cmd = "$cmd --input-seed $inputSeed" }
    Say ("  workload cmd: {0}" -f $cmd) "Gray"

    # ⛔ TWO BUGS LIVED HERE UNTIL 2026-09-22 AND BOTH SURFACED ON THE FIRST REAL RUN.
    #
    # 1. This built an ARRAY called $args and splatted it. `$args` is a PowerShell AUTOMATIC
    #    variable, and an array splat binds POSITIONALLY rather than treating "-Name" strings as
    #    parameter names - so FrequencyCount received the literal string "-WorkloadCommand".
    #    A HASHTABLE splat is unambiguous. Never name a variable $args.
    #
    # 2. It passed "-Iterations" to Invoke-FrequencySweep.ps1, WHICH HAS NO SUCH PARAMETER.
    #    Iteration count is a property of the WORKLOAD, not of the sweep, and reaches it through
    #    gpu_workload.py's --iterations. The kit's Collect.ps1 does take -Iterations, which is
    #    where the wrong idea came from - two different scripts with two different interfaces.
    $sweepArgs = @{
        SessionLabel    = $label
        WorkloadCommand = $cmd
        OutputDirectory = $outDir
        AppliedSettings = $applied
    }
    if ($hasTargets) {
        $sweepArgs["TargetFrequenciesMhz"] = ($targets -join ",")
    } else {
        $sweepArgs["MinFrequencyMhz"] = $minMhz
        $sweepArgs["MaxFrequencyMhz"] = $maxMhz
        $sweepArgs["FrequencyCount"] = $count
    }
    if ($descending) { $sweepArgs["Descending"] = $true }

    & $sweep @sweepArgs
    $sweepExit = $LASTEXITCODE
}
finally {
    Say ""
    Say "---- HWiNFO log stop ----" "Cyan"
    & $logTool -Stop -LogPath $logPath
    $stopExit = $LASTEXITCODE
}

$elapsed = [math]::Round(((Get-Date) - $startedAt).TotalMinutes, 1)

# ---- result file the agent can read unelevated ------------------------------------------------

$logBytes = 0
$logRows = 0
if (Test-Path $logPath) {
    $logBytes = (Get-Item $logPath).Length
    $logRows = (Get-Content $logPath | Measure-Object -Line).Lines
}

# Desktop load inside the benchmark windows, from this run's own HWiNFO log (2026-10-03). Exit 1 from
# the checker means at least one window was above 30 fps presented or 10% GPU bus load; 2 means the
# log lacks those columns and nothing could be checked, which is recorded rather than refused.
$deskVerdict = "not checked"
$deskExit = -1
$deskSummary = ""
$checker = Join-Path $PSScriptRoot "check_desktop_load.py"
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($sweepExit -eq 0 -and $pyCmd -and (Test-Path $checker) -and (Test-Path $logPath)) {
    $deskOut = & $pyCmd.Source $checker $outDir $outDir 2>&1
    $deskExit = $LASTEXITCODE
    Set-Content -Path (Join-Path $outDir "desktop-load-check.txt") -Value $deskOut -Encoding UTF8
    $deskSummary = (@($deskOut) | Select-Object -Last 1)
    $deskVerdict = switch ($deskExit) { 0 { "quiet" } 1 { "DESKTOP LOAD" } 2 { "unchecked: log lacks the columns" } default { "checker error" } }
}

[pscustomobject]@{
    desktopLoad     = $deskVerdict
    desktopLoadSummary = [string]$deskSummary
    label           = $label
    startedAt       = $startedAt.ToString("o")
    finishedAt      = (Get-Date).ToString("o")
    elapsedMinutes  = $elapsed
    sweepExitCode   = $sweepExit
    logStopExitCode = $stopExit
    outputDirectory = $outDir
    hwinfoLog       = $logPath
    hwinfoLogBytes  = $logBytes
    hwinfoLogRows   = $logRows
    appliedSettings = $applied
} | ConvertTo-Json | Set-Content -Path $result -Encoding UTF8

Say ""
Say "================ RESULT ================" "Cyan"
Say ("  sweep exit    : {0}" -f $sweepExit)
Say ("  elapsed       : {0} min (expected ~{1})" -f $elapsed, $expectMinutes)
Say ("  hwinfo log    : {0} bytes, {1} rows" -f $logBytes, $logRows)
Say ("  result file   : {0}" -f $result)

if ($sweepExit -ne 0) { Say "  THE SWEEP FAILED. Treat this run as invalid." "Red"; exit 6 }
if ($logRows -lt 5)   { Say "  The HWiNFO log is nearly empty. There is no voltage evidence for this run." "Red"; exit 7 }
Say ("  desktop load  : {0}" -f $deskVerdict)
if ($deskExit -eq 1) {
    Say ("  {0}" -f $deskSummary) "Red"
    Say "  A window was rendering beside the benchmark. Throughput from this run is contaminated; see desktop-load-check.txt." "Red"
    exit 8
}

Say ""
Say "Run complete and both halves verified." "Green"
exit 0
