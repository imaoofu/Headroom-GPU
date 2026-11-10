<#
.SYNOPSIS
    Collect one complete replicate of the twelve-workload suite, at stock, in one sitting.

.DESCRIPTION
    Everything the consumer half of this paper rests on was measured once. Section 5.5's
    arithmetic-intensity table, 5.6.1.1's fixed-versus-per-workload comparison and 5.6.2.1's
    constrained-model retest all read from twelve curves collected a single time each, so nothing
    in them carries an interval. This script collects another complete set under identical
    conditions so they can.

    IT ALSO FIXES A PROVENANCE SPLIT
    The existing "twelve-workload suite" is really eight plus four. copy, bgemm128, bgemm1024 and
    conv came from the pilot batch collected earlier the same day under looser conditions, and
    stock-suite-20260829/README.md forbids leaning on sub-percent differences between the two
    batches. A replicate taken in one sitting has no such split, which is arguably worth more
    than the error bars.

    WHY THE ITERATION COUNTS ARE HARD-CODED HERE
    The methodology is fixed-work: duration is the performance metric, so a count must not vary
    within or between sweeps that will be compared. These are the counts from
    SUITE-ITERATIONS.md, calibrated 2026-08-28 on this card at stock for ~9 s of GPU work each.
    They are per card AND per configuration. Running this on a different card, or on this one
    with a different curve, needs its own calibration - the counts below would be measuring
    something else. gemm keeps its own long-standing default of 120, which is not re-set here
    because changing it would break comparability with every gemm sweep already committed. That
    is deliberately not a count: the figure here read 67 while the repository held 112 sweeps, and
    a number in a comment nothing recomputes drifts by design.

    THE STOCK CHECK IS NOT OPTIONAL, AND IT IS NOT nvidia-smi's max clock
    `clocks.max.memory` reports 14001 MHz whether or not an Afterburner memory offset is applied,
    so it CANNOT distinguish stock from tuned. That mistake was made on 2026-08-30: a run was
    labelled "memory untouched - verified 14001 MHz stock" while a +2500 offset was live, and the
    run's own telemetry later showed 16301 MHz. The only field that distinguishes them is the
    memory clock UNDER LOAD - 13801 stock, 16301 at +2500. This script measures it before
    collecting anything and refuses if it disagrees.

.PARAMETER Replicate
    Short tag distinguishing this set from the others, e.g. "r2". Becomes part of every label.

.PARAMETER AppliedSettings
    What is on the card, in your own words. Refused if empty - nothing can reconstruct it later.

.PARAMETER ExpectedMemoryClockMhz
    The memory clock this configuration should show under load. Default 13801, this card at
    stock. Set it deliberately if replicating a tuned configuration.

.EXAMPLE
    .\Invoke-SuiteReplicate.ps1 -Replicate r2 -AppliedSettings "STOCK - no Afterburner offsets"
#>

param(
    [Parameter(Mandatory = $true)][string]$Replicate,
    [string]$AppliedSettings = "",
    # Names the configuration in every output filename. Defaults to "stock" so existing usage is
    # unchanged. Set it for anything else - the filename is the only part of a run most people read.
    [string]$ConfigurationLabel = "stock",
    [int]$ExpectedMemoryClockMhz = 13801,
    # 400, not 150, and the difference is a measured false refusal rather than caution. The probe
    # takes the MAXIMUM memory clock seen while the workload runs, and this card briefly touches a
    # higher P-state on the way up: at stock, minutes apart, it reads 13801 on one run and 14001 on
    # the next. At 150 the 14001 reading REFUSES A PERFECTLY GOOD CARD - observed 2026-09-05 in the
    # preflight for r6. 400 clears ~200 MHz of P-state jitter while still rejecting the smallest
    # offset worth catching on this card, +2500. Collect.ps1 was fixed on 2026-09-05 and this copy
    # was not; two tolerances for one quantity is how they drift apart.
    [int]$MemoryClockToleranceMhz = 400,
    # Passed straight through to the sweep. Default 10 leaves behaviour unchanged.
    #
    # 🔑 THIS IS THE BACKSTOP, NOT THE BAR. CLAUDE.md's collection protocol requires a dataset-grade
    # sweep to run with the baseline "stable and under ~5%"; this guard refuses above 10%. The two
    # numbers are different on purpose and the protocol is the stricter one, so RAISING THIS DOES
    # NOT MAKE A RUN ACCEPTABLE - it only moves the automated floor. A run at 15% would pass a
    # threshold of 25 and still violate the protocol.
    #
    # The protocol says so in as many words: "A passing 10% guard is not enough; run 1 passed at 6%
    # and still lost 10.3% at 1545 MHz."
    #
    # ⚠️ RAISE THIS ONLY WITH A MEASUREMENT BEHIND IT. On 2026-09-05, driver 616.64 reported an
    # idle baseline of 16-21% on a machine whose Task Manager showed 0% and whose desktop had not
    # changed. `utilization.gpu` is TIME-OCCUPANCY - the fraction of sampling windows in which any
    # kernel was resident - so a compositor drawing at 240 Hz makes the GPU non-idle almost always
    # while consuming nearly no capacity. A 13-point gemm sweep run at 18.8% came out FASTER than
    # its 616.56 counterpart at 12 of 13 points, +1.75% in the mid band where 5.4.4 says
    # contamination bites hardest, with achieved clocks identical to a tenth of a megahertz.
    # Contamination makes runs slower; that one was not contaminated.
    #
    # ⛔ AND THE READING WAS TRANSIENT, WHICH RETIRES THE ONLY REASON THIS PARAMETER WAS ADDED.
    # After a reboot the same machine, same driver 616.64, same 240 Hz desktop, same applications,
    # read 4% flat over ten samples - straight back in line with the 3-4% of r1-r6. The elevated
    # figure was post-install settling work (shader cache and similar), NOT a property of the
    # driver. An earlier version of this comment said "on this driver the proxy overstates"; that
    # is withdrawn. What survives is narrower and still worth having: utilization.gpu is an
    # occupancy proxy, it CAN read high without costing throughput, and the sweep above measured
    # that directly on one occasion.
    #
    # So the default stays 10 and no run has needed it raised. The guard is right to exist - it
    # caught a 79% gaming session costing 8.03 -> 4.84 TFLOP/s - and this parameter exists so a
    # future override is explicit and recorded rather than done by editing the guard. schema 0.3.3
    # stores max_baseline_allowed_pct beside the reading so a raised threshold is visible in the
    # data, not only in a comment nobody reads.
    #
    # 🔑 IF THE BASELINE READS HIGH, REBOOT AND RE-CHECK BEFORE RAISING ANYTHING.
    [int]$MaxBaselineUtilization = 10,
    [switch]$SkipStockCheck
)

$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$repoRoot = Split-Path (Split-Path $here -Parent) -Parent
$workloadPy = "tools\frequency-sweep\gpu_workload.py"
$sweepPs1 = Join-Path $here "Invoke-FrequencySweep.ps1"

# Ascending declared arithmetic intensity. The order is fixed so that replicates are comparable
# to EACH OTHER; note it is not the order the original suite was collected in, which was split
# across two batches and not principled. Any thermal-ordering effect therefore sits between this
# set and the original, not between replicates - which is the comparison the intervals come from.
$SUITE = @(
    @{ Workload = "copy";      Iterations = 2660 },
    @{ Workload = "reduce";    Iterations = 2870 },
    @{ Workload = "softmax";   Iterations = 2600 },
    @{ Workload = "layernorm"; Iterations = 1597 },
    @{ Workload = "bgemm32";   Iterations = 2673 },
    @{ Workload = "bgemm64";   Iterations = 2661 },
    @{ Workload = "bgemm128";  Iterations = 2467 },
    @{ Workload = "bgemm256";  Iterations = 1579 },
    @{ Workload = "bgemm1024"; Iterations = 414  },
    @{ Workload = "attention"; Iterations = 147  },
    @{ Workload = "conv";      Iterations = 151  },
    @{ Workload = "gemm";      Iterations = 120  }
)

function Say([string]$text, [string]$colour = "White") { Write-Host $text -ForegroundColor $colour }

if ([string]::IsNullOrWhiteSpace($AppliedSettings)) {
    Say "REFUSING: -AppliedSettings is empty." "Red"
    Say "Nothing can reconstruct what was on the card later. A sweep without it is close to" "Yellow"
    Say "worthless, and a WRONG one is worse - see the 2026-08-30 memory-offset mislabelling." "Yellow"
    exit 1
}

Say ""
Say "=======================================================" "Cyan"
Say ("  Suite replicate {0} - {1} workloads" -f $Replicate, $SUITE.Count) "Cyan"
Say "=======================================================" "Cyan"
Say ("  configuration : {0}" -f $AppliedSettings)
Say ("  estimated     : ~{0} min at ~4.5 min per sweep" -f ([int]($SUITE.Count * 4.5)))

# ---- the check that distinguishes stock from tuned --------------------------------------
if (-not $SkipStockCheck) {
    Say ""
    Say "Verifying the memory clock UNDER LOAD before collecting anything..." "Cyan"
    Say "  (clocks.max.memory reads 14001 either way and cannot tell them apart)" "Gray"

    $probe = Start-Process -FilePath "python" -WorkingDirectory $repoRoot `
        -ArgumentList $workloadPy, "--workload", "membw", "--iterations", "1200", "--json" `
        -PassThru -WindowStyle Hidden

    # 60 polls at 400 ms is 24 s, not the 10 s this loop used until 2026-09-06. That budget starts
    # at PROCESS LAUNCH and must cover Python starting, torch importing, CUDA initialising and a
    # multi-GB allocation before the GPU sees any work at all. At 10 s the probe returned 810 MHz -
    # the IDLE memory floor - and refused r7 on a card that was perfectly stock, reporting it as a
    # configuration mismatch.
    #
    # ⚠️ THIS IS THE SECOND TIME THIS EXACT DEFECT HAS BEEN FIXED. Collect.ps1 hit it on 2026-09-02
    # and was widened to 24 s with this reasoning written beside it; this copy was left at 10 s, and
    # when its TOLERANCE was corrected on 2026-09-05 the window was not. Two probes of the same
    # quantity in two files is how one gets fixed and the other does not.
    $observed = 0
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 400
        $raw = & nvidia-smi --query-gpu=clocks.current.memory --format=csv,noheader,nounits 2>$null
        $value = 0
        if ([int]::TryParse(("$raw").Trim(), [ref]$value)) {
            if ($value -gt $observed) { $observed = $value }
        }
        if ($probe.HasExited) { break }
    }
    if (-not $probe.HasExited) { $probe.WaitForExit() }

    Say ("  peak memory clock under load: {0} MHz (expected {1})" -f $observed, $ExpectedMemoryClockMhz)
    $delta = [math]::Abs($observed - $ExpectedMemoryClockMhz)
    if ($observed -eq 0) {
        Say "REFUSING: could not read a memory clock under load at all." "Red"
        exit 1
    }
    if ($delta -gt $MemoryClockToleranceMhz) {
        Say "" "Red"
        # Distinguish "the card is wrong" from "the probe never saw load". A reading at or near
        # the idle floor is the latter, and reporting it as the former sends the operator to check
        # a card that was fine - which is exactly what happened to r7 on 2026-09-06.
        if ($observed -lt 2000) {
            Say ""
            Say ("PROBE FAILED: memory clock never rose above {0} MHz, which is the IDLE floor." -f $observed) "Red"
            Say "This is NOT a statement about the card's configuration - the benchmark almost" "Yellow"
            Say "certainly had not reached the GPU before the probe window closed. A cold start" "Yellow"
            Say "pays for Python, torch, CUDA init and a multi-GB allocation first." "Yellow"
            Say "Re-run: the second attempt starts warm and normally succeeds. If it fails twice," "Yellow"
            Say "run the workload by hand and watch nvidia-smi to see whether the GPU is loaded." "Yellow"
            exit 3
        }
        Say ("REFUSING: memory clock under load is {0} MHz, not {1} +/- {2}." -f `
             $observed, $ExpectedMemoryClockMhz, $MemoryClockToleranceMhz) "Red"
        Say "The card is not in the configuration this run claims. 13801 is stock on this card;" "Yellow"
        Say "16301 is the +2500 offset. Fix the card, or pass -ExpectedMemoryClockMhz if you are" "Yellow"
        Say "deliberately replicating a tuned configuration." "Yellow"
        exit 1
    }
    Say "  [ok] configuration matches what this run claims" "Green"
}

# ---- collect ----------------------------------------------------------------------------
$started = Get-Date
$failed = @()

for ($i = 0; $i -lt $SUITE.Count; $i++) {
    $item = $SUITE[$i]
    # ⚠️ "stock" WAS HARDCODED HERE UNTIL 2026-09-07, AND IT PRODUCED ELEVEN TUNED SWEEPS NAMED
    # "5060ti-stock-suite-*". The applied_settings inside each file was correct and loud, but a
    # filename is what a person skims, and a file that says "stock" while holding split-curve data
    # is the 2026-08-30 mislabelling class exactly. The string was true when written - every suite
    # run was stock - and became a lie the first time the script was pointed at a tuned card.
    #
    # -ConfigurationLabel defaults to "stock", so nothing about the r1-r8 naming changes; a tuned
    # run must now say what it is to get a filename.
    $label = "5060ti-{0}-suite-{1}-{2}" -f $ConfigurationLabel, $item.Workload, $Replicate
    $command = "python {0} --workload {1} --iterations {2} --json" -f `
               $workloadPy, $item.Workload, $item.Iterations

    Say ""
    Say "-------------------------------------------------------" "Cyan"
    Say ("  [{0}/{1}] {2}  ({3} iterations)" -f ($i + 1), $SUITE.Count, $item.Workload, $item.Iterations) "Cyan"
    Say "-------------------------------------------------------" "Cyan"

    & powershell.exe -ExecutionPolicy Bypass -File $sweepPs1 `
        -SessionLabel $label `
        -WorkloadCommand $command `
        -FrequencyCount 13 `
        -MinFrequencyPercent 40 `
        -MaxBaselineUtilization $MaxBaselineUtilization `
        -AppliedSettings $AppliedSettings

    if ($LASTEXITCODE -ne 0) {
        # Not fatal on its own: one refused sweep (a busy GPU, a video engine waking up) should
        # not discard the eleven that would have succeeded. Recorded and reported at the end so
        # it cannot be missed, because a replicate missing a workload is not a replicate.
        Say ("  [!] {0} exited {1}" -f $item.Workload, $LASTEXITCODE) "Red"
        $failed += $item.Workload
    }
}

$minutes = ((Get-Date) - $started).TotalMinutes
Say ""
Say "=======================================================" "Cyan"
Say ("  Replicate {0} finished in {1:N0} min" -f $Replicate, $minutes) "Cyan"
Say "=======================================================" "Cyan"

if ($failed.Count -gt 0) {
    Say ("  {0} of {1} sweeps FAILED: {2}" -f $failed.Count, $SUITE.Count, ($failed -join ", ")) "Red"
    Say "  A replicate missing a workload cannot be compared to a complete one. Re-run those" "Yellow"
    Say "  workloads in this same session, or discard the set." "Yellow"
    exit 1
}

Say ("  all {0} sweeps completed" -f $SUITE.Count) "Green"
Say ""
Say "  Next: check every sweep reached 13 of 13 planned frequencies and that its locks held," "Gray"
Say "  then write a README recording the configuration, the baseline and this replicate's tag." "Gray"
exit 0
