<#
.SYNOPSIS
    Records GPU telemetry during a stress test and reports whether the run looked stable.

.DESCRIPTION
    This script OBSERVES. It does not apply overclock or undervolt settings, and that is
    a deliberate choice rather than a missing feature - see NON-GOALS below.

    Workflow:
      1. Apply whatever clock/voltage settings you want to test, by hand, in MSI Afterburner.
      2. Start this logger, telling it what you applied via -AppliedSettings.
      3. Start your stress test (OCCT, FurMark, 3DMark, a real game - your choice).
      4. The logger samples nvidia-smi until the duration elapses, then writes a verdict.

    Every sample is flushed to disk immediately. If the machine hard-locks, the truncated
    log is itself the evidence: the last timestamp is roughly when it died.

.PARAMETER SessionLabel
    Short name for this run. Becomes part of the output filename. Use something you will
    recognise later, like "5060ti-build07-uv900mv".

.PARAMETER AppliedSettings
    What you actually set before starting, in your own words - "core +150, mem +500, 900mV @ 2700MHz".
    This is the single most important field in the whole log and nothing can infer it for you.

.PARAMETER TestMethod
    What stress test is running alongside this. "OCCT 3D Adaptive", "FurMark 1080p", "Cyberpunk 30min".

.PARAMETER DurationSeconds
    How long to sample for. Default 600 (10 minutes).

.PARAMETER IntervalSeconds
    Seconds between samples. Default 1.

.PARAMETER OutputDirectory
    Where logs are written. Defaults to ..\..\data\stability-runs relative to this script.

.EXAMPLE
    .\Log-GpuStability.ps1 -SessionLabel "build07-stock" -AppliedSettings "stock, no changes" -TestMethod "OCCT 3D" -DurationSeconds 300

.NOTES
    NON-GOALS for this version, on purpose:
      * It does not change any GPU setting. A script that sweeps voltage unattended can
        hard-lock or destabilise a machine mid-build, and on a customer's machine that is
        not an acceptable failure mode. Automating the sweep is a later decision, made
        deliberately, not something to inherit by accident from a logging tool.
      * It cannot see a crash that takes the whole machine down instantly. It infers one
        from a truncated log, which is weaker evidence than a recorded event, and the
        verdict says so when it happens.
#>

[CmdletBinding()]
param(
    [string]$SessionLabel = "unlabeled",
    [string]$AppliedSettings = "UNRECORDED - fill this in",
    [string]$TestMethod = "UNRECORDED - fill this in",
    [int]$DurationSeconds = 600,
    [int]$IntervalSeconds = 1,
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

# --- Throttle reason decoding ---------------------------------------------------------
# Moved into ThrottleReasons.ps1 on 2026-09-12 so it could be tested: this script starts sampling
# on load and its decode could not be exercised from a test. That move immediately turned up a
# defect - a mask mixing known and unknown bits DROPPED the unknown part silently, so 0x604 read
# "SwPowerCap" and the 0x600 vanished. See that file's header for the measurements.
$throttleHelper = Join-Path $PSScriptRoot "ThrottleReasons.ps1"
if (-not (Test-Path $throttleHelper)) {
    throw "ThrottleReasons.ps1 not found beside this script. Throttle decoding is not optional - a run without it records masks nobody can read."
}
. $throttleHelper

# DO NOT use the GpuIdle bit to decide whether the card is busy. Measured on an RTX 5060 Ti
# (driver 610.88) during an hour of sustained CUDA inference: the card reported bit 0x1 = GpuIdle
# on EVERY sample while sitting at 98% utilisation and 139 W. The decode is correct - the driver
# genuinely reports GpuIdle for compute-only workloads that never touch the graphics pipeline.
#
# Utilisation percentage is the signal that works for both compute and graphics loads, which is
# why the loaded/idle split below is computed from it and not from the throttle mask.
$LoadedUtilisationThresholdPct = 50

# Below this fraction of loaded samples, the run cannot certify anything about stability and the
# verdict is downgraded. Half is deliberately lenient: it exists to catch a stress test that died
# or never started, not to police a slightly bursty workload.
$MinimumLoadedFraction = 0.5

function Resolve-NvidiaSmi {
    $candidates = @(
        "C:\Windows\System32\nvidia-smi.exe",
        "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $onPath = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($null -ne $onPath) { return $onPath.Source }
    throw "nvidia-smi.exe not found. This tool requires an NVIDIA GPU with drivers installed."
}

function Get-DisplayDriverCrashEvents {
    param([datetime]$Since)

    # Event ID 4101 from the "Display" provider is the classic TDR: "Display driver
    # stopped responding and has recovered". A crash that survives long enough to be
    # logged shows up here.
    try {
        $events = Get-WinEvent -FilterHashtable @{
            LogName   = "System"
            StartTime = $Since
        } -ErrorAction Stop | Where-Object {
            $_.Id -eq 4101 -or ($_.ProviderName -like "*nvlddmkm*")
        }
        return @($events)
    } catch {
        return @()
    }
}

# --- Preflight ------------------------------------------------------------------------

$nvidiaSmi = Resolve-NvidiaSmi

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $PSScriptRoot "..\..\data\stability-runs"
}
if (-not (Test-Path $OutputDirectory)) {
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
}
$OutputDirectory = (Resolve-Path $OutputDirectory).Path

$identityFields = "name,driver_version,vbios_version,clocks.max.sm,power.max_limit,memory.total"
$identityRaw = & $nvidiaSmi --query-gpu=$identityFields --format=csv,noheader,nounits -i 0
$identityParts = $identityRaw -split "\s*,\s*"

$gpuName = $identityParts[0]
$driverVersion = $identityParts[1]
$vbiosVersion = $identityParts[2]
$maxSmClock = $identityParts[3]
$powerLimit = $identityParts[4]

$startTime = Get-Date
$stamp = $startTime.ToString("yyyyMMdd-HHmmss")
$safeLabel = ($SessionLabel -replace "[^\w\-\.]", "_")
$logPath = Join-Path $OutputDirectory "$stamp`_$safeLabel`_samples.csv"
$metaPath = Join-Path $OutputDirectory "$stamp`_$safeLabel`_session.json"

Write-Host ""
Write-Host "[LOGGER] GPU:      $gpuName (driver $driverVersion, VBIOS $vbiosVersion)"
Write-Host "[LOGGER] Limits:   max SM clock $maxSmClock MHz, power limit $powerLimit W"
Write-Host "[LOGGER] Settings: $AppliedSettings"
Write-Host "[LOGGER] Test:     $TestMethod"
Write-Host "[LOGGER] Sampling every $IntervalSeconds s for $DurationSeconds s. Ctrl+C stops early."
Write-Host "[LOGGER] Writing:  $logPath"
Write-Host ""

if ($AppliedSettings -like "UNRECORDED*") {
    Write-Warning "No -AppliedSettings given. The log will record what the card DID but not what you ASKED it to do, which makes the run much less useful later."
}

# --- Sample loop ----------------------------------------------------------------------

$queryFields = "clocks.current.sm,clocks.current.memory,power.draw,temperature.gpu,utilization.gpu,utilization.memory,fan.speed,memory.used,clocks_throttle_reasons.active"

$writer = New-Object System.IO.StreamWriter($logPath, $false, [System.Text.Encoding]::UTF8)
$writer.AutoFlush = $true    # never buffer: a hard lock must not take the last samples with it
$writer.WriteLine("timestamp_iso,elapsed_seconds,sm_clock_mhz,memory_clock_mhz,power_draw_w,temperature_c,gpu_utilization_pct,memory_utilization_pct,fan_speed_pct,memory_used_mb,throttle_bitmask,throttle_reasons")

$sampleCount = 0
$queryFailureCount = 0
$concerningSampleCount = 0
$unknownThrottleSampleCount = 0
$samples = New-Object System.Collections.ArrayList
$completedFullDuration = $false
$stoppedByUser = $false

# Ctrl+C in PowerShell's default handling unwinds through try/finally (so the CSV writer
# below still closes safely) but then terminates the WHOLE script - which would skip the
# verdict and session.json entirely, despite this script's own banner promising "Ctrl+C
# stops early" as a clean way to stop. TreatControlCAsInput turns Ctrl+C into an ordinary
# keypress instead of a termination signal, so it can be detected inside the loop and
# handled as a normal early exit that still reaches the verdict section below.
#
# This throws "the handle is invalid" with no real console attached (a scheduled task, a
# redirected/non-interactive session). MUST degrade gracefully rather than crash - a stress
# test that dies before it starts because of a keyboard-handling nicety would be worse than
# not having the nicety at all. Caught during testing, in a non-interactive shell.
$consoleControlAvailable = $true
try {
    [Console]::TreatControlCAsInput = $true
} catch {
    $consoleControlAvailable = $false
    Write-Host "[LOGGER] No interactive console detected - early Ctrl+C detection is unavailable this run. Duration will run to completion; the script still works, it just cannot be told to stop early."
}

# A click in the console window puts it into selection mode, which blocks all output and freezes
# this script silently - mid-stress-test, with no error and the process still alive. See
# tools/Disable-QuickEdit.ps1; it cost a frequency sweep six minutes and two corrupted points.
$quickEditGuard = Join-Path $PSScriptRoot "..\Disable-QuickEdit.ps1"
if (Test-Path $quickEditGuard) {
    . $quickEditGuard
    [void](Disable-ConsoleQuickEdit -Tag "LOGGER")
} else {
    Write-Host "[LOGGER] NOTE: tools\Disable-QuickEdit.ps1 not found - DO NOT CLICK IN THIS WINDOW while the logger runs."
}

try {
    $deadline = $startTime.AddSeconds($DurationSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($consoleControlAvailable -and [Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq "C" -and ($key.Modifiers -band [ConsoleModifiers]::Control)) {
                Write-Host ""
                Write-Host "[LOGGER] Ctrl+C received - stopping now and writing a verdict for what was collected so far."
                $stoppedByUser = $true
                break
            }
        }

        $now = Get-Date
        $elapsed = [math]::Round(($now - $startTime).TotalSeconds, 1)

        # No "| Select-Object -First 1" here. Select-Object stops the pipeline early, which
        # kills nvidia-smi mid-write and leaves it reporting exit 255 on an otherwise fine
        # query. With -i 0 the command returns exactly one line anyway.
        $raw = $null
        try {
            $rawLines = @(& $nvidiaSmi --query-gpu=$queryFields --format=csv,noheader,nounits -i 0 2>$null)
            if ($rawLines.Count -gt 0) { $raw = $rawLines[0] }
        } catch {
            $raw = $null
        }

        if ([string]::IsNullOrWhiteSpace($raw)) {
            $queryFailureCount++
            $writer.WriteLine("$($now.ToString('o')),$elapsed,,,,,,,,,,QUERY_FAILED")
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        $parts = $raw -split "\s*,\s*"
        $throttleMask = $parts[8]
        $throttleReasons = ConvertTo-ThrottleReasonList -HexMask $throttleMask

        if (Test-ThrottleReasonsConcerning -Reasons $throttleReasons) { $concerningSampleCount++ }

        # Counted separately and NOT escalated. A bit the table cannot explain has covered 589 of
        # 603 samples in a perfectly healthy stock baseline since driver 616.56, so treating it as
        # trouble would turn every recent run red. Recording it is what stops it being invisible.
        if (Test-ThrottleReasonsUnknown -Reasons $throttleReasons) { $unknownThrottleSampleCount++ }

        $writer.WriteLine("$($now.ToString('o')),$elapsed,$($parts[0]),$($parts[1]),$($parts[2]),$($parts[3]),$($parts[4]),$($parts[5]),$($parts[6]),$($parts[7]),$throttleMask,$throttleReasons")

        [void]$samples.Add([pscustomobject]@{
            SmClock     = [double]$parts[0]
            PowerDraw   = [double]$parts[2]
            Temperature = [double]$parts[3]
            Utilization = [double]$parts[4]
        })

        $sampleCount++
        if ($sampleCount % 15 -eq 0) {
            Write-Host ("[LOGGER] {0,5}s  {1,5} MHz  {2,6} W  {3,3} C  {4,3}% util  {5}" -f `
                [int]$elapsed, $parts[0], $parts[2], $parts[3], $parts[4], $throttleReasons)
        }

        Start-Sleep -Seconds $IntervalSeconds
    }
    if (-not $stoppedByUser) { $completedFullDuration = $true }
} finally {
    $writer.Close()
    $writer.Dispose()
    if ($consoleControlAvailable) {
        try { [Console]::TreatControlCAsInput = $false } catch { }
    }
}

# --- Verdict --------------------------------------------------------------------------

$endTime = Get-Date
$crashEvents = Get-DisplayDriverCrashEvents -Since $startTime

$flags = New-Object System.Collections.ArrayList
if ($crashEvents.Count -gt 0) {
    # Say WHICH events, not just how many. The count alone is unfalsifiable by the person
    # reading the log: a self-test found this flag firing on nvlddmkm Error 153, which was a
    # genuine GPU context reset caused by force-killing a CUDA process - real, but not the
    # hard crash the bare wording implies. Provider, id, level and time let a human judge.
    $eventDetail = ($crashEvents | ForEach-Object {
        "{0} {1} id={2} ({3})" -f $_.TimeCreated.ToString("HH:mm:ss"), $_.ProviderName, $_.Id, $_.LevelDisplayName
    }) -join "; "
    [void]$flags.Add("$($crashEvents.Count) display-driver crash/reset event(s) in the Windows System log during this run: $eventDetail")
}
if ($queryFailureCount -gt 0) {
    [void]$flags.Add("$queryFailureCount telemetry query failure(s) - the driver may have been unresponsive")
}
if ($unknownThrottleSampleCount -gt 0) {
    # A flag, not a failure. It says the decode was incomplete, which is a statement about this
    # tool rather than about the card.
    [void]$flags.Add("$unknownThrottleSampleCount sample(s) carried a throttle bit this tool cannot decode - see throttle_reasons in the samples CSV")
}
if ($concerningSampleCount -gt 0) {
    [void]$flags.Add("$concerningSampleCount sample(s) showed hardware slowdown or thermal throttling")
}
if (-not $completedFullDuration) {
    if ($stoppedByUser) {
        [void]$flags.Add("stopped early by the user (Ctrl+C) - shorter sample window, weaker evidence than a full run")
    } else {
        [void]$flags.Add("run did not reach its full duration for an unknown reason - stopped early or interrupted")
    }
}
if ($sampleCount -eq 0) {
    [void]$flags.Add("no samples were collected at all")
}

# Was the card actually under load? A verdict computed over an idle GPU is worthless, and worse,
# it is worthless in a way that looks exactly like success.
#
# This was found by running an hour under a real workload that finished after 13 minutes. The rest
# of the run was idle, and the session reported verdict CLEAN with sm_clock_avg 1699 MHz, power_avg
# 39.3 W and util_avg 24.9% - all plausible numbers, none of them describing the loaded period
# (2970 MHz, 118 W, 98%). Nothing in the output distinguished "survived an hour of load" from
# "the load died after 13 minutes and the card sat idle", which is precisely the event a stability
# tool exists to catch: a stress test that crashes leaves the GPU idle for the remainder.
$loadedSamples = @($samples | Where-Object { $_.Utilization -gt $LoadedUtilisationThresholdPct })
$loadedFraction = if ($sampleCount -gt 0) { $loadedSamples.Count / $sampleCount } else { 0 }
$loadWasInadequate = ($sampleCount -gt 0 -and $loadedFraction -lt $MinimumLoadedFraction)

if ($loadWasInadequate) {
    [void]$flags.Add(("the GPU was loaded for only {0:P0} of this run ({1} of {2} samples above {3}% utilisation) - if a stress test was supposed to be running it stopped early or never started, and this run cannot certify stability" -f `
        $loadedFraction, $loadedSamples.Count, $sampleCount, $LoadedUtilisationThresholdPct))
}

if ($flags.Count -eq 0) {
    $verdict = "CLEAN"
} elseif ($crashEvents.Count -gt 0 -or $queryFailureCount -gt 0) {
    $verdict = "UNSTABLE"
} elseif ($concerningSampleCount -gt 0 -or -not $completedFullDuration -or $sampleCount -eq 0) {
    # A real problem was observed. That outranks "we could not tell", so check it first.
    $verdict = "FLAGGED"
} else {
    # Nothing went wrong, but the card was not under load often enough for that to mean anything.
    # This must not be CLEAN: absence of evidence is not evidence of stability.
    $verdict = "INCONCLUSIVE"
}

$clockValues = @($samples | Select-Object -ExpandProperty SmClock)
$powerValues = @($samples | Select-Object -ExpandProperty PowerDraw)
$tempValues = @($samples | Select-Object -ExpandProperty Temperature)
$utilValues = @($samples | Select-Object -ExpandProperty Utilization)

# Loaded-only statistics, reported ALONGSIDE the whole-run ones rather than replacing them.
# Same reasoning as the frequency sweep windowing its power to the benchmark's timed region: an
# average taken over a window wider than the thing being measured describes neither.
$loadedClockValues = @($loadedSamples | Select-Object -ExpandProperty SmClock)
$loadedPowerValues = @($loadedSamples | Select-Object -ExpandProperty PowerDraw)
$loadedTempValues = @($loadedSamples | Select-Object -ExpandProperty Temperature)

function Get-Stat {
    param([double[]]$Values, [string]$Kind)
    if ($Values.Count -eq 0) { return $null }
    $measured = $Values | Measure-Object -Average -Maximum -Minimum
    if ($Kind -eq "avg") { return [math]::Round($measured.Average, 2) }
    if ($Kind -eq "max") { return [math]::Round($measured.Maximum, 2) }
    if ($Kind -eq "min") { return [math]::Round($measured.Minimum, 2) }
    return $null
}

$session = [ordered]@{
    session_label            = $SessionLabel
    applied_settings         = $AppliedSettings
    test_method              = $TestMethod
    verdict                  = $verdict
    crash_events             = @($crashEvents | ForEach-Object {
        [ordered]@{
            time     = $_.TimeCreated.ToString("o")
            provider = $_.ProviderName
            id       = $_.Id
            level    = $_.LevelDisplayName
        }
    })
    flags                    = @($flags)
    gpu_name                 = $gpuName
    driver_version           = $driverVersion
    vbios_version            = $vbiosVersion
    max_sm_clock_mhz         = $maxSmClock
    power_limit_w            = $powerLimit
    started_at               = $startTime.ToString("o")
    ended_at                 = $endTime.ToString("o")
    requested_duration_s     = $DurationSeconds
    actual_duration_s        = [math]::Round(($endTime - $startTime).TotalSeconds, 1)
    sample_interval_s        = $IntervalSeconds
    samples_collected        = $sampleCount
    telemetry_failures       = $queryFailureCount
    throttled_samples        = $concerningSampleCount
    # Added 2026-09-12. Runs before this have no such field, so they cannot be audited for it -
    # the masks are in their samples CSV, but nothing counted them.
    unknown_throttle_samples = $unknownThrottleSampleCount
    driver_crash_events      = $crashEvents.Count
    sm_clock_avg_mhz         = Get-Stat -Values $clockValues -Kind "avg"
    sm_clock_max_mhz         = Get-Stat -Values $clockValues -Kind "max"
    sm_clock_min_mhz         = Get-Stat -Values $clockValues -Kind "min"
    power_avg_w              = Get-Stat -Values $powerValues -Kind "avg"
    power_max_w              = Get-Stat -Values $powerValues -Kind "max"
    temperature_avg_c        = Get-Stat -Values $tempValues -Kind "avg"
    temperature_max_c        = Get-Stat -Values $tempValues -Kind "max"
    gpu_utilization_avg_pct  = Get-Stat -Values $utilValues -Kind "avg"
    # How much of the run the card was actually working, and what it looked like while it was.
    # Whole-run averages blend load with idle and describe neither; read these first.
    loaded_samples           = $loadedSamples.Count
    loaded_fraction          = [math]::Round($loadedFraction, 4)
    loaded_threshold_pct     = $LoadedUtilisationThresholdPct
    sm_clock_avg_loaded_mhz  = Get-Stat -Values $loadedClockValues -Kind "avg"
    sm_clock_min_loaded_mhz  = Get-Stat -Values $loadedClockValues -Kind "min"
    sm_clock_max_loaded_mhz  = Get-Stat -Values $loadedClockValues -Kind "max"
    power_avg_loaded_w       = Get-Stat -Values $loadedPowerValues -Kind "avg"
    power_max_loaded_w       = Get-Stat -Values $loadedPowerValues -Kind "max"
    temperature_avg_loaded_c = Get-Stat -Values $loadedTempValues -Kind "avg"
    temperature_max_loaded_c = Get-Stat -Values $loadedTempValues -Kind "max"
    samples_file             = Split-Path $logPath -Leaf
    # 0.3.0 adds unknown_throttle_samples. Bumped rather than left alone because a consumer
    # cannot otherwise tell "no undecodable bits" from "this run predates the counter".
    schema_version           = "0.3.0"
}

# NOT Out-File -Encoding utf8: on Windows PowerShell 5.1 that writes a UTF-8 BOM, and a BOM
# in front of "{" makes this file fail every standard JSON parser - Python's json.load raises
# "Expecting value: line 1 column 1". This is a machine-readable artifact, so it gets BOM-less
# UTF-8 written explicitly.
[IO.File]::WriteAllText($metaPath, ($session | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "[LOGGER] ===================== RESULT ====================="
Write-Host "[LOGGER] Verdict: $verdict"
foreach ($flag in $flags) { Write-Host "[LOGGER]   - $flag" }
if ($sampleCount -gt 0) {
    Write-Host ("[LOGGER] Collected {0} samples over {1}s." -f $sampleCount, $session.actual_duration_s)
    Write-Host ("[LOGGER] SM clock: avg {0} MHz, range {1}-{2} MHz." -f $session.sm_clock_avg_mhz, $session.sm_clock_min_mhz, $session.sm_clock_max_mhz)
    Write-Host ("[LOGGER] Power:    avg {0} W, peak {1} W (limit {2} W)." -f $session.power_avg_w, $session.power_max_w, $powerLimit)
    Write-Host ("[LOGGER] Temp:     avg {0} C, peak {1} C." -f $session.temperature_avg_c, $session.temperature_max_c)
    Write-Host ("[LOGGER] GPU util: avg {0}%." -f $session.gpu_utilization_avg_pct)
    Write-Host ("[LOGGER] Loaded:   {0:P0} of samples above {1}% utilisation ({2} of {3})." -f `
        $loadedFraction, $LoadedUtilisationThresholdPct, $loadedSamples.Count, $sampleCount)
    if ($loadedSamples.Count -gt 0 -and $loadedFraction -lt 0.99) {
        # Only worth printing when the two differ; on a fully-loaded run they are the same numbers.
        Write-Host "[LOGGER] While actually under load (the numbers that describe the test, not the idle time):"
        Write-Host ("[LOGGER]   SM clock: avg {0} MHz, range {1}-{2} MHz." -f `
            $session.sm_clock_avg_loaded_mhz, $session.sm_clock_min_loaded_mhz, $session.sm_clock_max_loaded_mhz)
        Write-Host ("[LOGGER]   Power:    avg {0} W, peak {1} W." -f $session.power_avg_loaded_w, $session.power_max_loaded_w)
        Write-Host ("[LOGGER]   Temp:     avg {0} C, peak {1} C." -f $session.temperature_avg_loaded_c, $session.temperature_max_loaded_c)
    }
}
Write-Host "[LOGGER] Samples: $logPath"
Write-Host "[LOGGER] Session: $metaPath"
Write-Host "[LOGGER] =================================================="
Write-Host ""
Write-Host "[LOGGER] A CLEAN verdict means nothing went visibly wrong during this window. It is"
Write-Host "[LOGGER] not proof of stability - undervolt failures often need hours to show up, and"
Write-Host "[LOGGER] a single clean 10-minute run is weak evidence. Say so when reporting it."
if ($verdict -eq "INCONCLUSIVE") {
    Write-Host ""
    Write-Host "[LOGGER] INCONCLUSIVE means nothing went wrong AND the card was barely loaded, so this"
    Write-Host "[LOGGER] run tells you nothing either way. The usual cause is a stress test that exited"
    Write-Host "[LOGGER] or crashed partway through, leaving the GPU idle for the rest of the window."
    Write-Host "[LOGGER] Check the stress test was running for the whole duration, then run it again."
}

# Exit code carries the verdict so this can be driven from a batch script later:
#   0 = CLEAN, 1 = FLAGGED, 2 = UNSTABLE, 3 = INCONCLUSIVE
#
# INCONCLUSIVE is deliberately NOT 0. A caller that treats "not CLEAN" as failure will now stop on
# a run where the load died, which is the correct behaviour and the whole point of the verdict.
if ($verdict -eq "CLEAN") { exit 0 }
if ($verdict -eq "FLAGGED") { exit 1 }
if ($verdict -eq "INCONCLUSIVE") { exit 3 }
exit 2
