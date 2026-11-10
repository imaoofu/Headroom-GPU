<#
.SYNOPSIS
    The one stress-test protocol. Same test, same durations, same checks, every time.

.DESCRIPTION
    ROADMAP.md has carried "[BLOCKER] Fix one stress-test protocol and never vary it" since the
    project started, and nothing in this repository has ever been stability-tested - not the
    original tune, not the repaired curve, and not the split-region curve that section 5.7.6 now
    reports as the best configuration on this card. This script is that protocol, written down as
    executable steps so it cannot drift between runs or between machines.

    WHY NOT OCCT OR FURMARK
    Because a conventional stress test answers only "did it crash", and on GDDR7 that is not
    enough. Memory error correction retries silently: a memory overclock can run for hours without
    a single crash, artifact or event-log entry while being NET SLOWER than stock, because every
    corrected read costs a retry nobody reports. A pass/fail stress test scores that as a pass.
    The only way to catch it is to measure throughput continuously and watch for degradation, so
    this protocol drives the project's own fixed-work benchmark in a loop and records what each
    iteration achieved. Crash detection comes free alongside it, from Log-GpuStability.ps1.

    THE PROTOCOL - do not vary these without changing the version below
      1. Preflight. Refuse on active video engines or a busy GPU, exactly as the sweep does.
      2. Thermal soak. The first SOAK_MINUTES of each phase are recorded but EXCLUDED from the
         degradation test. Throughput always falls as a cold card warms up; that is physics, not
         instability, and comparing a cold first sample against a hot last one would flag every
         healthy configuration.
      3. Phase 1 - gemm for half the remaining duration. Compute-bound: loads the SMs and the
         power budget. This is where a core undervolt fails.
      4. Phase 2 - membw for half. Bandwidth-bound: loads the memory system. This is where a
         memory overclock fails, and it is the phase that can catch the GDDR7 trap above.
      5. No clock locking. The card runs its own boost behaviour, because that is how the
         configuration will actually be used. A locked sweep measures something else.
      6. Verdict combines three independent signals: the logger's telemetry verdict, any aborted
         benchmark iteration, and post-soak throughput degradation.
      7. Stop driving load at the first aborted iteration (1.2.0). One abort already forces an
         UNSTABLE verdict, so continuing buys no information and costs repeated driver resets on
         a card that has already answered. The logger keeps running - it is what reads the event
         log for the crash. -ContinueAfterFailure restores the old behaviour.

    WHAT A PASS DOES NOT MEAN
    A clean 30-minute run is not proof of stability. Undervolt failures routinely take hours to
    appear, and this protocol's own degradation threshold is UNCALIBRATED - see the note on
    -DegradationPercent. Treat a pass as "nothing went wrong in thirty minutes", which is a
    weaker and more honest statement than "stable".

.PARAMETER AppliedSettings
    What is applied to the card, in your own words. Refused if empty. Nothing can reconstruct
    this later, and a run without it is close to worthless.

.PARAMETER DurationMinutes
    Total wall time across both phases. Default 30.

.PARAMETER DegradationPercent
    Post-soak throughput fall that counts as degradation. Default 2.0.

    PROVISIONAL AND UNCALIBRATED. Nobody has yet measured what normal post-soak drift looks like
    on a healthy configuration, so this number is a guess informed only by the run-to-run spread
    of the locked sweeps (0.13% on the split curve, 0.76% on the original tune). Until several
    known-good runs establish a baseline, read the reported drift figure itself and do not lean
    on the flag.

.EXAMPLE
    .\Invoke-StabilityProtocol.ps1 -SessionLabel "splitcurve" -AppliedSettings "split curve, mem +2500"
#>

param(
    [string]$SessionLabel = "unlabelled",
    [string]$AppliedSettings = "",
    [int]$DurationMinutes = 30,
    [double]$DegradationPercent = 2.0,
    [int]$SoakMinutes = 5,
    [string]$OutputDirectory = "",
    [switch]$AllowVideoEngines,
    [switch]$ContinueAfterFailure
)

$ErrorActionPreference = "Stop"

# Bump this whenever a step above changes. A run's record carries it, so two runs can be compared
# only when their protocol versions match - which is the entire point of fixing the protocol.
$PROTOCOL_VERSION = "1.2.0"

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$workloadPy = Join-Path $repoRoot "tools\frequency-sweep\gpu_workload.py"
$loggerPs1 = Join-Path $PSScriptRoot "Log-GpuStability.ps1"

if ($OutputDirectory -eq "") { $OutputDirectory = Join-Path $repoRoot "data\stability-runs" }

function Say([string]$text, [string]$colour = "White") {
    Write-Host $text -ForegroundColor $colour
}

if ([string]::IsNullOrWhiteSpace($AppliedSettings)) {
    Say ""
    Say "REFUSING TO START: -AppliedSettings is empty." "Red"
    Say ""
    Say "This is the one field nothing can reconstruct afterwards. A stability run that does not" "Yellow"
    Say "say what it was testing records that SOMETHING survived thirty minutes, which is not a" "Yellow"
    Say "result. If the card is untouched, pass -AppliedSettings ""stock""." "Yellow"
    exit 2
}

foreach ($required in @($workloadPy, $loggerPs1)) {
    if (-not (Test-Path $required)) { Say "Missing: $required" "Red"; exit 2 }
}

$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) {
    $candidate = "C:\Windows\System32\nvidia-smi.exe"
    if (Test-Path $candidate) { $smi = @{ Source = $candidate } }
}
if (-not $smi) { Say "nvidia-smi not found." "Red"; exit 2 }

Say ""
Say "=======================================================" "Cyan"
Say "  Headroom stability protocol v$PROTOCOL_VERSION" "Cyan"
Say "=======================================================" "Cyan"
Say ""
Say ("  configuration : {0}" -f $AppliedSettings) "Gray"
Say ("  duration      : {0} min total, {1} min soak excluded per phase" -f $DurationMinutes, $SoakMinutes) "Gray"
Say ""

# ---- preflight: the same two checks the sweep makes, for the same reasons ----

$encMax = 0
$decMax = 0
for ($i = 0; $i -lt 5; $i++) {
    $vid = (& $smi.Source --query-gpu=utilization.encoder,utilization.decoder --format=csv,noheader,nounits -i 0 2>$null | Select-Object -First 1)
    if ($vid) {
        $parts = "$vid" -split '\s*,\s*'
        if ($parts.Count -ge 2) {
            if ([double]$parts[0] -gt $encMax) { $encMax = [double]$parts[0] }
            if ([double]$parts[1] -gt $decMax) { $decMax = [double]$parts[1] }
        }
    }
    Start-Sleep -Milliseconds 300
}
if (($encMax -gt 0 -or $decMax -gt 0) -and (-not $AllowVideoEngines)) {
    Say ("REFUSING TO START: video engines active (encoder {0}%, decoder {1}%)." -f $encMax, $decMax) "Red"
    Say "Usually NVIDIA Instant Replay. Switch it off and re-run." "Yellow"
    exit 5
}
Say ("  [ok] video engines idle (encoder {0}%, decoder {1}%)" -f $encMax, $decMax) "Green"

$util = (& $smi.Source --query-gpu=utilization.gpu --format=csv,noheader,nounits -i 0 2>$null | Select-Object -First 1)
if ($util -and [int]$util -gt 10) {
    Say "REFUSING TO START: GPU already $util% busy." "Red"
    exit 5
}
Say ("  [ok] GPU idle ({0}%)" -f $util) "Green"

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stem = Join-Path $OutputDirectory "$stamp`_$SessionLabel`_stability"
$iterCsv = "$stem`_iterations.csv"
$summaryJson = "$stem`_protocol.json"

# ---- the logger runs alongside, in its own process ----
# It samples telemetry once a second and owns crash and throttle detection. Kept separate rather
# than reimplemented here, because it already has tests and a known-good failure-detection pass.

$loggerSeconds = $DurationMinutes * 60 + 30
Say ""
Say "Starting the telemetry logger alongside..." "Gray"

# Start-Process -ArgumentList does NOT reliably quote array elements that contain spaces. The
# first version of this script passed the settings string as an array element and PowerShell
# split it on whitespace, so "SMOKE TEST of..." bound "SMOKE" to -AppliedSettings and dropped
# "TEST" onto -IntervalSeconds, which is an int. The logger died on parameter binding before
# writing a single sample. Build one explicitly quoted command line instead.
#
# Double quotes inside the value would break that quoting in turn, and escaping them through
# powershell.exe -File is genuinely unreliable, so they are replaced rather than escaped. The
# substitution is recorded in the run's own JSON so the record says what happened to it.
$loggerSettings = $AppliedSettings -replace '"', "'"
$settingsWereQuoted = ($loggerSettings -ne $AppliedSettings)
$loggerArgs = ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -SessionLabel "{1}" ' +
               '-AppliedSettings "{2}" -TestMethod "{3}" -DurationSeconds {4} -OutputDirectory "{5}"') -f `
              $loggerPs1, $SessionLabel, $loggerSettings,
              "headroom stability protocol v$PROTOCOL_VERSION (gpu_workload.py loop)",
              $loggerSeconds, $OutputDirectory

$loggerErr = "$stem`_logger-stderr.txt"
$loggerOut = "$stem`_logger-stdout.txt"
$loggerProc = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden `
                            -RedirectStandardError $loggerErr -RedirectStandardOutput $loggerOut `
                            -ArgumentList $loggerArgs

# VERIFY IT ACTUALLY STARTED. This is the more important half of the fix. Without it the harness
# happily ran a full load phase against a logger that had already died, and would have printed a
# combined verdict derived from a component that never sampled anything - the exact failure the
# logger itself exists to catch, reproduced one level up. A protocol that cannot tell "the
# telemetry is clean" from "there is no telemetry" is worse than no protocol.
$appeared = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    if ($loggerProc.HasExited) { break }
    $found = @(Get-ChildItem $OutputDirectory -Filter "*_$SessionLabel`_samples.csv" -ErrorAction SilentlyContinue |
               Where-Object { $_.LastWriteTime -gt $loggerProc.StartTime.AddSeconds(-5) })
    if ($found.Count -gt 0) { $appeared = $true; break }
}

if (-not $appeared) {
    Say ""
    Say "REFUSING TO CONTINUE: the telemetry logger did not start." "Red"
    if ($loggerProc.HasExited) {
        # ExitCode can still come back null on a redirected child even after WaitForExit, so this
        # says "unavailable" rather than printing a blank line and looking like a formatting bug.
        # The stderr below is the diagnostic that actually matters; the code is a nicety.
        $loggerProc.WaitForExit()
        $code = $loggerProc.ExitCode
        if ($null -eq $code) { $code = "unavailable" }
        Say ("  it exited immediately, code {0}" -f $code) "Red"
    }
    else { Say "  it is running but wrote no samples file within 15s" "Red"; $loggerProc.Kill() }
    $stderrText = ""
    if (Test-Path $loggerErr) { $stderrText = (Get-Content $loggerErr -Raw) }
    if ($stderrText.Trim() -ne "") {
        Say ""
        Say "  --- logger stderr ---" "Yellow"
        $stderrText.Trim().Split("`n") | Select-Object -First 10 | ForEach-Object { Say ("  {0}" -f $_.TrimEnd()) "Yellow" }
    }
    Say ""
    Say "  No load was run. Fix the logger invocation and try again." "Yellow"
    exit 2
}
Say ("  [ok] logger running (pid {0}), sampling for {1}s, samples file confirmed" -f $loggerProc.Id, $loggerSeconds) "Green"
if ($settingsWereQuoted) { Say "  [note] double quotes in -AppliedSettings were replaced with single quotes for the logger" "Yellow" }

# ---- the load ----

# ITERATION COUNTS, and why they are not the defaults.
#
# gpu_workload.py is fixed-work: it runs, exits, and the loop starts a fresh Python process.
# At the default counts each process does ~8 s of GPU work behind ~2 s of torch import and CUDA
# context creation, so the card idles a quarter of the time. Measured on the 2026-08-23
# negative-control run: 25% of one-second samples below 50% utilisation, mean 75.1%, in a clean
# repeating pattern of roughly eight loaded samples then two idle.
#
# That is not a soak test. It thermally cycles the card, it puts loaded_fraction near the
# logger's 50% INCONCLUSIVE threshold, and - the reason it actually matters - undervolt
# instability characteristically appears under CONTINUOUS load, so periodic recovery gaps are
# exactly what lets a marginal curve survive a test it should fail.
#
# Raising the iteration count puts ~60 s of work behind the same ~2 s of startup, taking the duty
# cycle from ~75% to ~97%. It does NOT eliminate the gap; truly continuous load needs a repeat
# mode inside gpu_workload.py, and that file is a dependency of the frequency sweep, so it is not
# being changed for this. The residual gap is recorded in the run's JSON rather than glossed.
$gemmIterations = 900
$membwIterations = 7000

$phaseSeconds = [int](($DurationMinutes * 60) / 2)
$rows = @()
$aborted = 0
$iteration = 0

# Stop driving load once the card has failed, unless the caller opts out. Added in 1.2.0.
#
# Before this, an aborted iteration was counted and the loop carried on for the rest of the phase.
# On a genuinely dead driver the python call returns no JSON and the `continue` below fired with no
# delay, so the loop relaunched the workload as fast as it could for the remaining minutes - each
# attempt another chance to reset the driver, on a card that had already given its answer. One
# aborted iteration is enough: the combined verdict is UNSTABLE either way, so the extra attempts
# buy no information and cost repeated driver resets.
#
# The LOGGER is deliberately left running. It is what reads the Windows event log for the driver
# crash, so killing it early would discard the evidence the run exists to capture, and it keeps
# sampling the aftermath - whether the card recovers or keeps resetting is itself the finding.
$stopEarly = $false
$stopReason = ""

foreach ($workload in @("gemm", "membw")) {
    if ($stopEarly) {
        Say ""
        Say ("  Phase {0} SKIPPED: {1}" -f $workload, $stopReason) "Yellow"
        continue
    }
    Say ""
    Say "-------------------------------------------------------" "Cyan"
    Say ("  Phase: {0}, {1}s" -f $workload, $phaseSeconds) "Cyan"
    Say "-------------------------------------------------------" "Cyan"

    $phaseStart = Get-Date
    $lastReport = Get-Date
    while (((Get-Date) - $phaseStart).TotalSeconds -lt $phaseSeconds) {
        $iterCount = $gemmIterations
        if ($workload -eq "membw") { $iterCount = $membwIterations }
        # $ErrorActionPreference is "Stop" for this script, and on Windows PowerShell 5.1 that
        # combination is a trap: merging a NATIVE command's stderr with 2>&1 wraps each stderr
        # line in a NativeCommandError ErrorRecord, and under "Stop" that record is TERMINATING.
        # The script dies at this line.
        #
        # Which is the one case this protocol exists for. A crashing workload prints a CUDA
        # traceback to stderr, so on a genuine driver failure the protocol was killed here -
        # before the abort was recorded, before the iterations CSV was written, and before any
        # verdict was computed. Measured 2026-08-30 with a deliberately failing workload: the
        # logger's files were produced and _stability_iterations.csv and _stability_protocol.json
        # were not. The run that mattered would have left almost nothing behind.
        #
        # stderr is still merged into $raw on purpose - the no-JSON branch below quotes it, and
        # that text is the most direct evidence of what killed the workload.
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $raw = & python $workloadPy --workload $workload --iterations $iterCount --json 2>&1
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }
        $line = ($raw | Where-Object { "$_".TrimStart().StartsWith("{") } | Select-Object -First 1)
        if (-not $line) {
            Say ("  [!] iteration produced no JSON: {0}" -f ($raw -join " ")) "Red"
            $aborted++
            if (-not $ContinueAfterFailure) {
                $stopEarly = $true
                $stopReason = "the workload produced no JSON - the driver or the process died"
                Say ("  STOPPING: {0}. Pass -ContinueAfterFailure to override." -f $stopReason) "Yellow"
                break
            }
            continue
        }

        $r = $line | ConvertFrom-Json
        $iteration++
        $elapsed = ((Get-Date) - $phaseStart).TotalSeconds
        if ($r.aborted) {
            $aborted++
            Say ("  [!] iteration aborted: {0}" -f $r.abort_reason) "Red"
            if (-not $ContinueAfterFailure) {
                $stopEarly = $true
                $stopReason = "iteration aborted: $($r.abort_reason)"
            }
        }

        $rows += [pscustomobject]@{
            iteration        = $iteration
            workload         = $workload
            phase_elapsed_s  = [math]::Round($elapsed, 1)
            throughput       = $r.throughput
            unit             = $r.throughput_unit
            duration_s       = $r.duration_seconds
            temp_start_c     = $r.temperature_start_c
            temp_peak_c      = $r.temperature_peak_c
            aborted          = $r.aborted
            in_soak          = ($elapsed -lt ($SoakMinutes * 60))
        }

        if (((Get-Date) - $lastReport).TotalSeconds -ge 60) {
            $scale = 1e12
            $label = "TFLOP/s"
            if ($workload -eq "membw") { $scale = 1e9; $label = "GB/s" }
            Say ("    {0,5:N0}s  iter {1,3}  {2,7:N2} {3}  {4} C" -f `
                 $elapsed, $iteration, ($r.throughput / $scale), $label, $r.temperature_peak_c) "Gray"
            $lastReport = Get-Date
        }

        # The row is appended above before this breaks, so the failing iteration is IN the record
        # rather than inferred from a gap in it.
        if ($stopEarly) {
            Say ("  STOPPING: {0}. Pass -ContinueAfterFailure to keep driving load." -f $stopReason) "Yellow"
            Say "  The telemetry logger is left running: it reads the event log for the driver" "Gray"
            Say "  crash and keeps sampling how the card behaves after it." "Gray"
            break
        }
    }
}

$rows | Export-Csv -Path $iterCsv -NoTypeInformation -Encoding UTF8
Say ""
Say ("  [ok] {0} iterations written to {1}" -f $rows.Count, (Split-Path $iterCsv -Leaf)) "Green"

# ---- degradation test ----
# Post-soak only, and within a workload. Comparing across workloads would be meaningless, and
# comparing a cold card against a hot one measures the thermal ramp rather than the card's health.

function Get-Degradation {
    param($Rows, [string]$Workload)
    $post = @($Rows | Where-Object { $_.workload -eq $Workload -and (-not $_.in_soak) -and (-not $_.aborted) })
    if ($post.Count -lt 8) { return $null }
    $quarter = [math]::Max(2, [int]($post.Count / 4))
    $first = ($post | Select-Object -First $quarter | Measure-Object -Property throughput -Average).Average
    $last = ($post | Select-Object -Last $quarter | Measure-Object -Property throughput -Average).Average
    return [pscustomobject]@{
        Workload = $Workload
        Samples  = $post.Count
        First    = $first
        Last     = $last
        DropPct  = (1 - ($last / $first)) * 100
    }
}

Say ""
Say "=======================================================" "Cyan"
Say "  Result" "Cyan"
Say "=======================================================" "Cyan"

$degraded = $false
$degradations = @()
foreach ($workload in @("gemm", "membw")) {
    $d = Get-Degradation -Rows $rows -Workload $workload
    if ($null -eq $d) {
        Say ("  {0,-6} too few post-soak iterations to test degradation" -f $workload) "Yellow"
        continue
    }
    $degradations += $d
    $scale = 1e12
    if ($workload -eq "membw") { $scale = 1e9 }
    $verdict = "ok"
    $colour = "Green"
    if ($d.DropPct -gt $DegradationPercent) { $verdict = "DEGRADED"; $colour = "Red"; $degraded = $true }
    Say ("  {0,-6} {1,3} post-soak iters, {2,7:N2} -> {3,7:N2}, drift {4,6:N2}%  [{5}]" -f `
         $workload, $d.Samples, ($d.First / $scale), ($d.Last / $scale), $d.DropPct, $verdict) $colour
}

# ---- wait for the logger and read its verdict ----

Say ""
Say "Waiting for the telemetry logger to finish..." "Gray"
$loggerProc.WaitForExit()

# READ THE VERDICT FROM THE LOGGER'S OWN session.json, NOT FROM ITS EXIT CODE.
#
# The exit code is unreliable here: on a redirected child .NET returns $null often enough that
# two successive versions of this script broke on it - the first crashed outright, because
# ContainsKey($null) throws rather than returning false, and the second degraded to a verdict of
# "UNKNOWN" which then SAILED THROUGH AS CLEAN, because nothing downstream treated an unreadable
# telemetry verdict as a problem. That is the third appearance of one bug in this file: a tool
# that cannot tell "the telemetry says fine" from "there is no telemetry".
#
# The session JSON is the logger's actual output and it always contains the verdict it computed.
$loggerVerdict = "UNKNOWN"
$sessionFile = @(Get-ChildItem $OutputDirectory -Filter "*_$SessionLabel`_session.json" -ErrorAction SilentlyContinue |
                 Where-Object { $_.LastWriteTime -ge $loggerProc.StartTime } |
                 Sort-Object LastWriteTime | Select-Object -Last 1)
if ($sessionFile.Count -gt 0) {
    try {
        $session = Get-Content $sessionFile[0].FullName -Raw | ConvertFrom-Json
        if ($session.verdict) { $loggerVerdict = [string]$session.verdict }
        $loadedFraction = $session.loaded_fraction
    } catch {
        Say ("  [warn] could not parse {0}: {1}" -f $sessionFile[0].Name, $_) "Yellow"
    }
}
Say ("  telemetry verdict: {0}" -f $loggerVerdict) "Gray"
Say ("  aborted iterations: {0}" -f $aborted) "Gray"

# ---- combined verdict ----
# Deliberately conservative: any one of the three signals failing sinks the run. They observe
# different failure modes and none of them subsumes the others.

# ORDERED WEAKEST FIRST, so each test can only ESCALATE. These are sequential ifs, not
# elseifs, which means the LAST matching one wins - and until 1.2.0 they ran in the opposite
# order, so a definite failure was overwritten by a weaker signal:
#
#     if ($aborted -gt 0)                    { $verdict = "UNSTABLE" }      # set here
#     if ($loggerVerdict -eq "INCONCLUSIVE") { $verdict = "INCONCLUSIVE" }  # and lost here
#
# An aborted benchmark iteration is a definite failure. INCONCLUSIVE means "the card was barely
# loaded so we cannot tell". The second was silently replacing the first, against this block's
# own comment that any one signal failing sinks the run.
#
# The case where it bites is exactly the case the protocol is for: a crash early in a run kills
# the load, the GPU then sits idle, the logger reports INCONCLUSIVE on the low loaded fraction,
# and it overwrites the UNSTABLE the abort had already established. 1.2.0's early-stop makes
# this fire on EVERY abort rather than occasionally, because stopping the load is what produces
# the low loaded fraction. Measured 2026-08-30: an aborted iteration reported INCONCLUSIVE.
$verdict = "CLEAN"
$exit = 0
# An unreadable telemetry verdict is not a pass. Two of the protocol's three signals came from
# the logger, and if its verdict cannot be read then only the benchmark loop reported - which
# says nothing about driver resets, throttling or telemetry failure.
if ($loggerVerdict -eq "INCONCLUSIVE" -or $loggerVerdict -eq "UNKNOWN") { $verdict = "INCONCLUSIVE"; $exit = 3 }
if ($loggerVerdict -eq "FLAGGED") { $verdict = "FLAGGED"; $exit = 1 }
if ($degraded) { $verdict = "DEGRADED"; $exit = 1 }
if ($aborted -gt 0) { $verdict = "UNSTABLE"; $exit = 2 }
if ($loggerVerdict -eq "UNSTABLE") { $verdict = "UNSTABLE"; $exit = 2 }

$summary = [ordered]@{
    protocol_version    = $PROTOCOL_VERSION
    session_label       = $SessionLabel
    applied_settings    = $AppliedSettings
    # WHAT THE PREFLIGHT SAW, not merely that it ran. Added in 1.1.0 because the claims auditor
    # classifies a run by the evidence its artifacts carry, and 1.0.0 carried none: its runs read
    # as "declared-unverified" - indistinguishable from a run taken before the guard existed -
    # even though the guard demonstrably refuses to start on a busy engine. A guarantee that
    # leaves no record behind cannot be audited, which is this project's recurring defect one
    # level up. Non-zero here is only possible via -AllowVideoEngines.
    encoder_util_pct    = $encMax
    decoder_util_pct    = $decMax
    video_engines_allowed = [bool]$AllowVideoEngines
    duration_minutes    = $DurationMinutes
    soak_minutes        = $SoakMinutes
    degradation_threshold_pct = $DegradationPercent
    iterations          = $rows.Count
    aborted_iterations  = $aborted
    telemetry_verdict   = $loggerVerdict
    telemetry_loaded_fraction = $loadedFraction
    settings_quotes_substituted = $settingsWereQuoted
    gemm_iterations     = $gemmIterations
    membw_iterations    = $membwIterations
    duty_cycle_note     = "Load is not perfectly continuous. Each benchmark iteration is a separate Python process, so roughly 2 s of torch import and CUDA context creation sits between iterations. At these iteration counts that is about 3% of wall time, against 25% at the tool defaults. Read loaded_fraction in the logger's session JSON for the measured figure."
    degradation         = $degradations
    verdict             = $verdict
    iterations_csv      = (Split-Path $iterCsv -Leaf)
    note                = "A clean run is not proof of stability. Undervolt failures routinely take hours to appear, and the degradation threshold is uncalibrated."
}
[IO.File]::WriteAllText($summaryJson, ($summary | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))

Say ""
$colour = "Green"
if ($exit -ne 0) { $colour = "Red" }
Say ("  VERDICT: {0}" -f $verdict) $colour
Say ""
Say ("  {0}" -f (Split-Path $summaryJson -Leaf)) "Gray"
Say ""
Say "  A clean run means nothing went wrong in $DurationMinutes minutes. It is not stability." "Yellow"
Say ""
exit $exit
