<#
.SYNOPSIS
    Calibrate the extended suite's iteration counts for THIS card, and print the Collect.ps1
    command that uses them.

.DESCRIPTION
    The methodology is fixed-work: duration is the performance metric, so an iteration count must
    be held constant across every frequency in a sweep. That makes the count a property of the
    card, and a count calibrated on one card measures something else on another. The eleven suite
    workloads therefore have NO default and gpu_workload.py refuses to start without an explicit
    count - which is the correct failure, but it means a new card needs eleven calibration runs
    before Collect.ps1 can be given anything.

    This script does those eleven and emits the command, so bringing up a new card is two prompts
    rather than thirteen.

    WHY gemm AND membw ARE NOT CALIBRATED HERE
    They have defaults - 120 and 1200 - and every sweep already committed used them. Those two
    counts are what make a new card's gemm curve comparable with the 67 sweeps on the 5060 Ti and
    with the RTX 3070 Ti runs of 2026-08-25, none of which passed an explicit count. Recalibrating
    them per card would buy a slightly better-sized run and give up every cross-card comparison in
    the paper. gemm is appended to the emitted command at its default so the suite is complete.

    WHY IT REFUSES ON A BUSY GPU
    Calibration times the card as it is at that moment and then that number is frozen for the
    whole sweep, so a count taken under contention is wrong at all thirteen frequencies rather
    than at one. Section 5.4.4 measured ordinary desktop capture software moving throughput by
    several percent while leaving the baseline guard happy, so the check here is deliberately
    stricter than the sweep's own: encoder and decoder must read zero, and the utilisation bar is
    5% rather than the sweep's 10%. The looser bar is not good enough here - run 1 of 5.4.4 passed
    a 10% guard at 6% baseline and still lost 10.3% of throughput at 1545 MHz.

    HOW MUCH THIS MATTERS, MEASURED
    Re-calibrating the 5060 Ti on 2026-09-04 against its own counts of 2026-08-28 gave numbers
    2 to 18% higher, mean about 8%, on the same card at stock. Nothing about the card changed;
    calibration simply runs at whatever clock and load the machine offers that minute. That spread
    is why counts are recorded rather than re-derived, and why re-calibrating a card that already
    has committed sweeps would break comparability with them.

    WHY IT PRINTS THE COMMAND RATHER THAN RUNNING IT
    Two reasons. Collect.ps1 needs -AppliedSettings, which is a sentence only the operator can
    write and which nothing can reconstruct afterwards. And a calibration that fed itself straight
    into a two-hour collection would hide a bad count inside a long run instead of putting it in
    front of someone first.

.PARAMETER TargetSeconds
    Work duration each count is sized for. The default of 9 s matches every committed sweep; a
    shorter run does not let the card reach steady clocks, which is a defect this project has
    already shipped once.

.PARAMETER SkipBusyCheck
    Calibrate anyway on a busy GPU. The counts will be wrong. Present because a machine that is
    not yours may have something running you cannot close, and a stated-as-degraded number beats
    no data - but the emitted command is marked so the sweep records it.

.EXAMPLE
    .\Calibrate-Suite.ps1
#>

param(
    [double]$TargetSeconds = 9.0,
    [switch]$SkipBusyCheck
)

$ErrorActionPreference = "Stop"

# The kit puts this at its root, beside Collect.ps1, with python and tools underneath.
$kit = $PSScriptRoot
$pythonExe = Join-Path $kit "python\python.exe"
$workloadPy = Join-Path $kit "tools\frequency-sweep\gpu_workload.py"

# Running from the repository instead of the kit: the layout differs, so fall back to whatever
# python is on PATH and to the repo's own copy of the workload.
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }
if (-not (Test-Path $workloadPy)) {
    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $workloadPy = Join-Path $repoRoot "tools\frequency-sweep\gpu_workload.py"
}

# The eleven that need a count. gemm is deliberately absent - see the header.
$suite = @("copy", "reduce", "softmax", "layernorm", "bgemm32", "bgemm64",
           "bgemm128", "bgemm256", "bgemm1024", "attention", "conv")

function Say([string]$text, [string]$colour = "White") {
    Write-Host $text -ForegroundColor $colour
}

Say ""
Say "=======================================================" "Cyan"
Say "  Suite calibration - $($suite.Count) workloads, ~$TargetSeconds s of work each" "Cyan"
Say "=======================================================" "Cyan"

if (-not (Test-Path $workloadPy)) {
    Say "Cannot find gpu_workload.py. Looked for: $workloadPy" "Red"
    exit 1
}

# ---- the card ----------------------------------------------------------------------------
$name = (& nvidia-smi --query-gpu=name --format=csv,noheader) | Select-Object -First 1
Say ""
Say "  card: $name" "Gray"

# ---- refuse on a busy GPU ------------------------------------------------------------------
if (-not $SkipBusyCheck) {
    $utilMax = 0
    $encMax = 0
    $decMax = 0
    for ($i = 0; $i -lt 6; $i++) {
        $raw = (& nvidia-smi --query-gpu=utilization.gpu,utilization.encoder,utilization.decoder --format=csv,noheader,nounits) | Select-Object -First 1
        $parts = "$raw".Split(",")
        if ($parts.Count -ge 3) {
            $u = 0; $e = 0; $d = 0
            [void][int]::TryParse($parts[0].Trim(), [ref]$u)
            [void][int]::TryParse($parts[1].Trim(), [ref]$e)
            [void][int]::TryParse($parts[2].Trim(), [ref]$d)
            if ($u -gt $utilMax) { $utilMax = $u }
            if ($e -gt $encMax) { $encMax = $e }
            if ($d -gt $decMax) { $decMax = $d }
        }
        Start-Sleep -Milliseconds 700
    }
    Say "  baseline: GPU $utilMax%, encoder $encMax%, decoder $decMax%" "Gray"

    if ($encMax -gt 0 -or $decMax -gt 0) {
        Say ""
        Say "REFUSING: a video engine is active (encoder $encMax%, decoder $decMax%)." "Red"
        Say "Capture software depresses measured throughput and is invisible at idle (5.4.4)." "Yellow"
        Say "Switch off Instant Replay / ShadowPlay / OBS and run this again." "Yellow"
        exit 1
    }
    if ($utilMax -gt 5) {
        Say ""
        Say "REFUSING: GPU baseline peaked at $utilMax%, which is above the 5% bar." "Red"
        Say "A count calibrated under contention is wrong at EVERY frequency of the sweep that" "Yellow"
        Say "uses it, not just one. Close what is running and try again, or pass -SkipBusyCheck" "Yellow"
        Say "if this machine cannot be quietened and a degraded number is better than none." "Yellow"
        exit 1
    }
}

# ---- calibrate ------------------------------------------------------------------------------
Say ""
Say "  Calibrating. Leave the machine alone - each run times the card." "Gray"
Say ""

$counts = @()
$failed = @()
foreach ($workload in $suite) {
    $index = $suite.IndexOf($workload) + 1
    Write-Host ("  [{0,2}/{1}] {2,-11} " -f $index, $suite.Count, $workload) -NoNewline

    $output = & $pythonExe $workloadPy --workload $workload --calibrate --target-seconds $TargetSeconds 2>&1
    $joined = ($output | Out-String)
    $match = [regex]::Match($joined, "--iterations\s+(\d+)")

    if ($match.Success) {
        $count = [int]$match.Groups[1].Value
        $counts += $count
        Say ("-> {0}" -f $count) "Green"
    } else {
        $failed += $workload
        $counts += 0
        Say "-> FAILED" "Red"
        # The workload's own message is the useful one; a summary here would only paraphrase it.
        Say ($joined.Trim()) "DarkGray"
    }
}

if ($failed.Count -gt 0) {
    Say ""
    Say "$($failed.Count) workload(s) did not calibrate: $($failed -join ', ')" "Red"
    Say "The command below is NOT usable until every count is a real number." "Yellow"
}

# ---- emit the command -----------------------------------------------------------------------
# gemm is appended last at its default so the emitted suite is the full twelve. Its count is not
# passed, because passing it would be the change the header warns against.
$workloadList = ($suite -join ",") + ",gemm"
$countList = ($counts -join ",") + ",120"

Say ""
Say "=======================================================" "Cyan"
Say "  Counts for this card" "Cyan"
Say "=======================================================" "Cyan"
Say ""
for ($i = 0; $i -lt $suite.Count; $i++) {
    Say ("  {0,-11} {1}" -f $suite[$i], $counts[$i]) "White"
}
Say ("  {0,-11} {1}   (default, not calibrated - see this script's header)" -f "gemm", 120) "Gray"

Say ""
Say "  Record these. They are a property of THIS card and this configuration," "Yellow"
Say "  and a sweep that reuses them on different silicon measures something else." "Yellow"
Say ""
# Emitted as ONE line with no placeholder in angle brackets. Both details are deliberate and both
# come from watching this fail: PowerShell treats < as a reserved operator, so a "<card>" stub
# makes the whole line a parse error before anything runs, and a backtick-continued block is
# fragile to paste. The label is filled in from the card name instead of left as a stub.
$label = ($name -replace "NVIDIA GeForce ", "" -replace "[^A-Za-z0-9]", "").ToLower()
if (-not $label) { $label = "card" }

# Three lines, and all three are needed. An elevated shell opens in system32, where
# .\Collect.ps1 does not resolve; and a fresh elevated window carries the default Restricted
# execution policy, so the script refuses to load even though this one just ran - this script is
# normally launched with -ExecutionPolicy Bypass on its own command line, which does not carry
# over. Both were hit for real on the 3070 Ti, 2026-09-04, one after the other.
Say "  Then run these three, FROM AN ELEVATED SHELL:" "Cyan"
Say ""
Say ("  cd " + $kit) "White"
Say "  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force" "White"
$quote = [char]34
Say ("  .\Collect.ps1 -Label {0}-suite -Workloads {1} -Iterations {2} -AppliedSettings {3}STOCK - describe the card and what was closed{3}" -f $label, $workloadList, $countList, $quote) "White"
Say ""
Say "  Edit only the -AppliedSettings sentence. That is one command and roughly 1.5-2 hours." "Gray"
Say "  Leave the machine alone; do not click inside the window, which pauses the run." "Gray"
Say ""

if ($failed.Count -gt 0) { exit 1 }
