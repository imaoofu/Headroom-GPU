<#
.SYNOPSIS
    Sweeps locked GPU core clocks and measures power at each one, to build a
    frequency-power-efficiency curve on real consumer hardware.

.DESCRIPTION
    This is the consumer-hardware equivalent of the public GPU-DVFS-Dataset: for each
    of N core frequencies, pin the clock, hold a load, and record what the card draws.

    Unlike Log-GpuStability.ps1 (which only observes), this script DOES change GPU state -
    it locks the core clock via nvidia-smi. That makes the reset path the most important
    code here, not the measurement:

      * The sweep body is wrapped in try/finally. The finally ALWAYS runs -rgc.
      * After resetting it READS BACK the clock state and shouts if the reset did not take.
      * Ctrl+C is intercepted rather than allowed to kill the process, so it unwinds
        through the same reset path instead of leaving the card pinned.
      * Clock locks do not survive a reboot, so a total loss of the process is recoverable
        by restarting the machine. Say so out loud if that ever happens.

    WORKLOAD: the GPU must be under sustained load or every measurement is an idle
    measurement. Two ways to supply it:

      -WorkloadCommand "<cmd>"   the script runs this at each frequency and times it.
                                 Duration becomes the performance metric (fixed work,
                                 varying clock), which is what makes efficiency computable.

      (nothing)                  the script assumes YOU started a load externally (OCCT,
                                 FurMark, a game) and just measures power. Gives the
                                 power curve but NOT performance, so efficiency cannot
                                 be computed from that run alone.

.PARAMETER SessionLabel
    Short name for this sweep. Becomes part of the output filename.

.PARAMETER WorkloadCommand
    Optional. Command run at each frequency; its wall-clock duration is recorded as the
    performance metric. Must be fixed-work (same amount of work every time), not fixed-time.

.PARAMETER FrequencyCount
    How many frequencies to test across the swept range. Default 13, matching the public
    V100 dataset's grid so the two are directly comparable.

.PARAMETER MinFrequencyPercent
    Floor of the sweep, as a percentage of the card's max clock. Default 40.

    Consumer cards report absurdly low clocks as "supported" - an RTX 5060 Ti offers 180 MHz,
    under 6% of its 3090 MHz max. Sweeping evenly from there wastes a third of the run on
    frequencies that will never be efficiency-optimal for real work, and makes any fixed-work
    benchmark crawl. The public V100 dataset only swept 757-1530 MHz, i.e. 49-100% of its max,
    and found its optimum at 62%. This default keeps the grid concentrated where the answer
    actually lives. Lower it if a card's optimum looks like it sits at the floor.

.PARAMETER TargetFrequenciesMhz
    An explicit list of target clocks, swept exactly as given (sorted, then reversed by
    -Descending). Every value must be in the card's supported-clock table; the sweep refuses
    otherwise, and cannot be combined with MinFrequencyMhz / MaxFrequencyMhz.

    Added 2026-09-27 after Session E: a -165 MHz core offset on the RTX 2060 Super moved the
    supported-clock table's top from 2115 to 2100, so a grid DERIVED from the table shifted every
    target by 15 MHz and the registered comparison could not be scored. A list does not move
    with the table. The JSON records sweep_targets_explicit.

.PARAMETER MinFrequencyMhz
.PARAMETER MaxFrequencyMhz
    Absolute bounds on the swept band, in MHz. Both default to 0, meaning "unset" - the grid then
    runs from the MinFrequencyPercent floor to the card's maximum, as before.

    These exist for FINE sweeps: once a coarse sweep has bracketed the efficiency optimum, the
    useful next run concentrates all N points into the neighbourhood of the peak rather than
    re-measuring a range whose shape is already known. MinFrequencyPercent cannot express that,
    since it only moves the floor.

    A fine sweep needs enough span to be worth fitting. Near its optimum an efficiency curve is
    flat by construction, so a band tight around the peak buys resolution in frequency and pays
    for it in signal: if the curve only falls a percent or two across the whole band, per-point
    noise decides which point wins. Choose a band across which efficiency visibly falls.

.PARAMETER SettleSeconds
    Wait after locking a clock before measuring, so the card reaches steady state. Default 8.

.PARAMETER MeasureSeconds
    How long to sample telemetry at each frequency. Default 20. Applies only when NO
    -WorkloadCommand is given; with a workload, sampling runs for as long as it runs.

.PARAMETER Descending
    Walk the frequency grid from HIGHEST to LOWEST instead of the default lowest-to-highest.

    ⛔ ADDED 2026-09-15 BECAUSE THE DEFAULT ORDER IS A CONFOUND AND NOTHING HERE COULD VARY IT.
    A sweep that climbs in frequency also warms the card as it goes, so frequency and temperature
    rise together and any voltage that changes with temperature is indistinguishable from one that
    changes with clock. The RTX 2060 Super fine-floor sweep of 2026-09-15 measured core voltage
    FALLING 0.644 -> 0.631 V from 900 to 1005 MHz while the card went 42.0 -> 58.7 C; above
    1005 MHz the temperature had saturated and the voltage rise there is attributable, but the
    fall is not. Every load-floor measurement in this project was taken ascending.

    Running the identical grid both ways separates them. Nothing else about the sweep changes.

.PARAMETER SampleIntervalSeconds
    Telemetry sampling period, in seconds. Default 0.5.

    When a workload is supplied, power is averaged over only the benchmark's timed region
    (see below), which is a window of roughly 8-10 seconds. At the old 1 s period that left
    under ten samples to average; 0.5 s doubles the resolution for a cost of ~42 ms per
    nvidia-smi call, on a thread that is otherwise sleeping.

.PARAMETER MinFreeVramMb
    Refuse to start unless at least this much VRAM is free, in MB. Default 4000, which is not a
    round number chosen for looking sensible - membw allocates three 256M-float buffers totalling
    3.07 GB and gemm about 0.8 GB, and the CUDA context costs a few hundred MB on top. It is the
    SAME constant tools/collection-kit/preflight.py already enforces (REQUIRED_VRAM_BYTES), and
    they are deliberately identical: two guards on the same quantity that disagree are worse than
    one, because a run refused by one tool and accepted by the other tells the operator nothing.
    Set to 0 to disable, and say so in -AppliedSettings if you do.

.PARAMETER MaxBaselineUtilization
    Refuse to start if the GPU is already busier than this percentage before our workload
    runs. Default 10.

    This guard protects the whole dataset. A sweep run while a game, a video, a local LLM
    server or an animated wallpaper is on the card measures that load mixed with ours at
    every frequency, inseparably. The output looks like ordinary data and is worthless.

.PARAMETER AllowVideoEngines
    Proceed even though NVENC/NVDEC are active. Off by default, and it should stay off.

    An always-on clipper is the most damaging contaminant this project has measured, precisely
    because it is invisible - no window, enabled by default, and running on engines that
    utilization.gpu does not report. Use this switch only to measure contaminated conditions
    deliberately, as a control, and say so in -AppliedSettings when you do.

.PARAMETER AppliedSettings
    Free text describing the GPU configuration this run was made under - the V/F curve shape,
    memory offset, power limit, and anything else changed by hand before starting.

    This is the only field in the output that nothing else can reconstruct afterwards. Clocks,
    power and throughput are all measured; what was DELIBERATELY SET is not, because it is set
    outside this tool in Afterburner, and the card does not report the curve back. A sweep whose
    configuration is unknown can still be compared against itself, but it cannot be compared
    against anything else, which is most of what a sweep is for.

    Learned the hard way: two runs on 2026-08-21 produced the best result recorded on this card
    and it was not possible, the following morning, to say from the repo what curve had produced
    it. Voltage telemetry could confirm the lower half of the curve and nothing above 2100 MHz.

    Be specific enough to reproduce. "split curve, stock slope below 845 mV, tuned flat shape
    850-920 mV, top point 920 mV at 3000 MHz, memory +2500, power limit 111%" is the standard;
    "tuned" is not.

.PARAMETER DryRun
    Plan the sweep and print the frequencies WITHOUT touching GPU state. Always do this first.

.EXAMPLE
    .\Invoke-FrequencySweep.ps1 -SessionLabel "5060ti-baseline" -DryRun

.EXAMPLE
    .\Invoke-FrequencySweep.ps1 -SessionLabel "5060ti-baseline" -MeasureSeconds 25

.NOTES
    Requires an ELEVATED shell. nvidia-smi clock locking needs administrator rights;
    the script checks and refuses to start otherwise rather than failing halfway through.
#>

[CmdletBinding()]
param(
    [string]$SessionLabel = "sweep",
    [string]$WorkloadCommand = "",
    [int]$FrequencyCount = 13,
    [int]$MinFrequencyPercent = 40,
    [int]$MinFrequencyMhz = 0,
    [int]$MaxFrequencyMhz = 0,
    [string[]]$TargetFrequenciesMhz = @(),
    [int]$SettleSeconds = 8,
    [int]$MeasureSeconds = 20,
    [double]$SampleIntervalSeconds = 0.5,
    [double]$MaxBaselineUtilization = 10,
    [int]$MinFreeVramMb = 4000,
    [switch]$AllowVideoEngines,
    [switch]$Descending,
    [string]$AppliedSettings = "",
    [string]$OutputDirectory = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

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

function Test-Elevated {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-SupportedGraphicsClocks {
    param([string]$Smi)
    # Returns every graphics clock the card will accept, descending.
    $raw = @(& $Smi --query-supported-clocks=graphics --format=csv,noheader,nounits 2>$null)
    $clocks = @()
    foreach ($line in $raw) {
        $trimmed = ("$line").Trim()
        if ($trimmed -match '^\d+$') { $clocks += [int]$trimmed }
    }
    return ($clocks | Sort-Object -Unique -Descending)
}

function Select-SweepFrequencies {
    param([int[]]$Supported, [int]$Count)
    # Evenly spaced across the supported range, always including both endpoints.
    if ($Supported.Count -le $Count) { return ($Supported | Sort-Object) }
    $ascending = @($Supported | Sort-Object)
    $picked = @()
    for ($i = 0; $i -lt $Count; $i++) {
        $index = [int][math]::Round(($ascending.Count - 1) * $i / ($Count - 1))
        $picked += $ascending[$index]
    }
    return ($picked | Sort-Object -Unique)
}

function Read-Telemetry {
    param([string]$Smi)
    # Memory clock is appended LAST so the existing positional offsets are untouched. It is
    # here because a bandwidth-bound workload tracks memory clock, not SM clock, and sweeps
    # that recorded only the SM clock could not explain why membw capped at ~295 GB/s across
    # 1545-1852 MHz on a tuned card while stock rose 312 -> 342. That question is unanswerable
    # from telemetry that never looked at the relevant clock.
    $fields = "clocks.current.sm,power.draw,temperature.gpu,utilization.gpu,clocks_throttle_reasons.active,clocks.current.memory"
    $lines = @(& $Smi --query-gpu=$fields --format=csv,noheader,nounits -i 0 2>$null)
    if ($lines.Count -eq 0) { return $null }
    $parts = ("$($lines[0])") -split "\s*,\s*"
    if ($parts.Count -lt 6) { return $null }
    return [pscustomobject]@{
        # Unix epoch seconds, same clock the benchmark stamps its timed region with, so
        # samples can be matched to the interval that actually produced the performance number.
        Timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
        SmClock      = [double]$parts[0]
        PowerDraw    = [double]$parts[1]
        Temperature  = [double]$parts[2]
        Utilization  = [double]$parts[3]
        ThrottleMask = $parts[4]
        MemClock     = [double]$parts[5]
    }
}

function Get-BaselineUtilization {
    param([string]$Smi, [int]$Samples = 5)
    # Measures what the GPU is doing BEFORE our workload starts. Anything materially above
    # zero means something else is competing for the card.
    $values = @()
    for ($i = 0; $i -lt $Samples; $i++) {
        $reading = Read-Telemetry -Smi $Smi
        if ($null -ne $reading) { $values += $reading.Utilization }
        Start-Sleep -Milliseconds 600
    }
    if ($values.Count -eq 0) { return $null }
    return [math]::Round((($values | Measure-Object -Average).Average), 1)
}

function Get-EncoderActivity {
    param([string]$Smi, [int]$Samples = 5)
    # Video encode/decode runs on NVENC/NVDEC, engines separate from the SMs, so a capture tool
    # can be busy while utilization.gpu still looks acceptable. It is not free to us: it competes
    # for memory bandwidth, PCIe and the copy engines, and it periodically reads the framebuffer.
    #
    # This is not a hypothetical. NVIDIA Instant Replay - enabled by default with the NVIDIA app,
    # and with no window of its own - measured 21% encoder at idle on this machine and cost 1.5%
    # of peak gemm throughput, 4.2% across 1237-2010 MHz, and a fivefold increase in run-to-run
    # spread. The same applies to any always-on clipper: ShadowPlay, OBS replay buffer, Discord
    # or Steam recording, Xbox Game Bar, AMD ReLive.
    $enc = @(); $dec = @()
    for ($i = 0; $i -lt $Samples; $i++) {
        $lines = @(& $Smi --query-gpu=utilization.encoder,utilization.decoder --format=csv,noheader,nounits -i 0 2>$null)
        if ($lines.Count -gt 0) {
            $parts = ("$($lines[0])") -split "\s*,\s*"
            if ($parts.Count -ge 2) { $enc += [double]$parts[0]; $dec += [double]$parts[1] }
        }
        Start-Sleep -Milliseconds 300
    }
    if ($enc.Count -eq 0) { return $null }
    return [pscustomobject]@{
        Encoder = [math]::Round((($enc | Measure-Object -Maximum).Maximum), 1)
        Decoder = [math]::Round((($dec | Measure-Object -Maximum).Maximum), 1)
    }
}

function Get-FreeVramMb {
    param([string]$Smi)
    # WHY FREE AND NOT USED. The obvious guard is "refuse above N MB used", and it is wrong: the
    # workload needs an ABSOLUTE amount, so the same used-figure is fine on a 16 GB card and fatal
    # on an 8 GB one. This project runs both. Free is the quantity that means the same thing on
    # every card, which is the only way one default can be correct across the fleet.
    try {
        $line = @(& $Smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0 2>$null)
        if ($line.Count -eq 0) { return $null }
        $value = 0
        if ([int]::TryParse(("$($line[0])").Trim(), [ref]$value)) { return $value }
    } catch { }
    return $null
}

function Get-VramHolders {
    param([string]$Smi)
    # Named the way the encoder check names its offender: a percentage tells the operator to go
    # hunting, a name tells them what to close.
    #
    # ⚠️ THE PER-PROCESS FIGURE DOES NOT EXIST ON THIS PLATFORM, AND THE FIRST VERSION OF THIS
    # FUNCTION ASSUMED IT DID. `--query-compute-apps=used_memory` returns the STRING "[N/A]" for
    # every process under WDDM, the consumer Windows driver model, because NVML cannot account
    # memory per process when the OS owns the allocator. Measured 2026-09-05 with a python
    # process demonstrably holding 6 GB: its NAME was listed, its memory read "[N/A]". The
    # original code parsed the figure, skipped anything under 200 MB, and therefore skipped
    # EVERY process on every Windows consumer card - it would have printed an empty list under
    # exactly the conditions it was written for, while looking correct on inspection.
    #
    # So: report the figure where the platform supplies it (Linux, and TCC-mode datacenter
    # cards), report names alone where it does not, and let the caller say which happened.
    # A name with no number is worth having. A silent empty list is not.
    $withMemory = @()
    $namesOnly = @()
    try {
        $lines = @(& $Smi --query-compute-apps=process_name,used_memory --format=csv,noheader,nounits 2>$null)
        foreach ($line in $lines) {
            $parts = ("$line") -split "\s*,\s*"
            if ($parts.Count -lt 2) { continue }
            $name = [System.IO.Path]::GetFileNameWithoutExtension(("$($parts[0])").Trim())
            if ($name -eq "") { continue }
            $mb = 0
            if ([int]::TryParse(("$($parts[1])").Trim(), [ref]$mb)) {
                if ($mb -ge 200) { $withMemory += [pscustomobject]@{ Name = $name; Mb = $mb } }
            } elseif ($namesOnly -notcontains $name) {
                $namesOnly += $name
            }
        }
    } catch { }
    if ($withMemory.Count -gt 0) {
        return [pscustomobject]@{
            HasMemoryFigures = $true
            Holders = @($withMemory | Sort-Object -Property Mb -Descending)
        }
    }
    # Windows lists a dozen shell and compositor processes that are always present and never the
    # cause. Filtering through the known-offenders list keeps the hint pointed at things the
    # operator can actually close - and that list now knows llama-server, which is the whole
    # reason this guard exists on this machine.
    $interesting = @(Get-HeavyGpuProcesses -Smi $Smi)
    if ($interesting.Count -eq 0) { $interesting = $namesOnly }
    return [pscustomobject]@{ HasMemoryFigures = $false; Holders = @($interesting) }
}

function Get-HeavyGpuProcesses {
    param([string]$Smi)
    # Windows always has a dozen shell/compositor processes touching the GPU; those are
    # unavoidable and near-free. These are the ones that render CONTINUOUSLY and will
    # contaminate a measurement.
    $known = @(
        "wallpaper64", "wallpaper32", "wallpaperservice32",   # Wallpaper Engine - animated wallpapers render nonstop
        "opera", "chrome", "msedge", "firefox", "brave",      # browsers composite and play video
        "Discord", "Spotify", "steamwebhelper",
        "obs64", "obs32",
        # Local LLM inference. llama-server is the one THIS project runs - the delegation moved
        # from Ollama to llama.cpp on 2026-08-25 and this list did not follow until 2026-09-05,
        # so for eleven days the hint was blind to the single most likely offender on this machine.
        "ollama", "ollama_llama_server", "llama-server", "llama-cli", "koboldcpp", "lm-studio",
        "python", "pythonw"                                   # another sweep or training run already going
    )
    $found = @()
    try {
        $lines = @(& $Smi --query-compute-apps=process_name --format=csv,noheader 2>$null)
        foreach ($line in $lines) {
            $name = [System.IO.Path]::GetFileNameWithoutExtension(("$line").Trim())
            foreach ($candidate in $known) {
                if ($name -like "*$candidate*" -and ($found -notcontains $name)) { $found += $name }
            }
        }
    } catch { }
    return $found
}

function Reset-GpuClocks {
    param([string]$Smi)
    # The single most important function in this file.
    try {
        & $Smi -rgc 2>&1 | Out-Null
    } catch {
        Write-Host "[SWEEP] WARNING: -rgc threw: $($_.Exception.Message)"
    }
    Start-Sleep -Milliseconds 700
    $after = Read-Telemetry -Smi $Smi
    if ($null -ne $after) {
        Write-Host ("[SWEEP] Clocks reset. Card is now reporting {0} MHz at idle/load." -f $after.SmClock)
    } else {
        Write-Host "[SWEEP] Clocks reset issued, but telemetry did not respond - VERIFY MANUALLY with: nvidia-smi -q -d CLOCK"
    }
}

# --- Preflight -----------------------------------------------------------------------

$nvidiaSmi = Resolve-NvidiaSmi
$elevated = Test-Elevated

# power.limit is the ENFORCED cap; power.max_limit is only the most a user could set. Asking
# for max_limit alone is what left 5.5.3 unable to cite the limit a SwPowerCap was hitting - the
# 3070 Ti OC BIOS reports 350 W max against 310 W enforced. default_limit comes along because the
# ratio of enforced to default IS the power-limit tuning knob, and on the 5060 Ti that is 200 W
# against a 180 W default: a third setting the paper's "tuned is two knobs" framing does not count.
$identityRaw = & $nvidiaSmi --query-gpu=name,driver_version,clocks.max.sm,power.max_limit,power.limit,power.default_limit --format=csv,noheader,nounits -i 0
$identityParts = ("$identityRaw") -split "\s*,\s*"
$gpuName = $identityParts[0]
$driverVersion = $identityParts[1]
$maxClock = $identityParts[2]
$powerLimit = $identityParts[3]
# Older drivers can report [N/A] for these. Kept as whatever came back rather than coerced to a
# number: "[N/A]" in the JSON says the query ran and the driver declined, which is information.
# A silent 0 would read as a real measurement of zero watts.
$powerLimitEnforced = if ($identityParts.Count -gt 4) { $identityParts[4] } else { "[N/A]" }
$powerLimitDefault  = if ($identityParts.Count -gt 5) { $identityParts[5] } else { "[N/A]" }

$supported = Get-SupportedGraphicsClocks -Smi $nvidiaSmi
if ($supported.Count -eq 0) {
    throw "Could not read supported graphics clocks. This card may not support clock locking."
}

# Pick the band. An explicit target list wins over everything; explicit MHz bounds win over the
# percentage floor when given.
# Taken as TEXT and split here. Declared [int[]], a list typed on a powershell -File command line
# arrives as one string, and "465,1561" converts silently to 4651561 (the comma read as a thousands
# separator) - found by the first dry run, 2026-09-27. Every element must be plain digits.
$targetList = @()
foreach ($part in (@($TargetFrequenciesMhz) -join ',') -split '[,\s]+') {
    if ($part -eq '') { continue }
    if ($part -notmatch '^\d+$') { throw "TargetFrequenciesMhz entry '$part' is not a whole number of MHz." }
    $targetList += [int]$part
}
$explicitTargets = ($targetList.Count -gt 0)
$explicitBand = ($MinFrequencyMhz -gt 0 -or $MaxFrequencyMhz -gt 0)
if ($explicitTargets) {
    if ($explicitBand) {
        throw "TargetFrequenciesMhz cannot be combined with MinFrequencyMhz / MaxFrequencyMhz. Give one or the other."
    }
    $missing = @($targetList | Where-Object { $supported -notcontains $_ })
    if ($missing.Count -gt 0) {
        throw ("Target(s) {0} MHz are not in this card's supported-clock table ({1}-{2} MHz, {3} clocks). " +
               "An explicit list is swept exactly or not at all.") -f ($missing -join ', '), $supported[-1], $supported[0], $supported.Count
    }
    $inRange = @($targetList | Sort-Object -Unique)
    $floorMhz = $inRange[0]
    $ceilMhz = $inRange[-1]
} elseif ($explicitBand) {
    $floorMhz = if ($MinFrequencyMhz -gt 0) { $MinFrequencyMhz } else { $supported[-1] }
    $ceilMhz = if ($MaxFrequencyMhz -gt 0) { $MaxFrequencyMhz } else { $supported[0] }
    if ($floorMhz -gt $ceilMhz) {
        throw "MinFrequencyMhz ($floorMhz) is above MaxFrequencyMhz ($ceilMhz). Nothing to sweep."
    }
    $inRange = @($supported | Where-Object { $_ -ge $floorMhz -and $_ -le $ceilMhz })
    if ($inRange.Count -eq 0) {
        throw "No supported graphics clock falls in $floorMhz-$ceilMhz MHz. Supported range is $($supported[-1])-$($supported[0]) MHz."
    }
    # Do NOT silently widen an explicitly-requested band the way the percentage floor does.
    # Asking for a fine sweep and receiving a coarse one over the whole range would produce a
    # file that answers a different question than the one it was run to answer.
    if ($inRange.Count -lt $FrequencyCount) {
        Write-Host "[SWEEP] NOTE: $floorMhz-$ceilMhz MHz contains only $($inRange.Count) supported clocks; sweeping all of them instead of $FrequencyCount."
    }
} else {
    # Trim the pointless bottom end before picking the grid - see MinFrequencyPercent.
    $floorMhz = [int][math]::Round(($supported[0] * $MinFrequencyPercent) / 100.0)
    $ceilMhz = $supported[0]
    $inRange = @($supported | Where-Object { $_ -ge $floorMhz })
    if ($inRange.Count -lt $FrequencyCount) {
        Write-Host "[SWEEP] NOTE: floor of $floorMhz MHz leaves only $($inRange.Count) clocks; using the full supported range instead."
        $inRange = $supported
    }
}
$targets = if ($explicitTargets) { $inRange } else { Select-SweepFrequencies -Supported $inRange -Count $FrequencyCount }
if ($Descending) {
    # [array] because reversing a single-element result would otherwise unwrap to a scalar and
    # break the foreach below - the same shape of defect as the -First 1 pipeline bug.
    $targets = [array]($targets | Sort-Object -Descending)
}

Write-Host ""
Write-Host "[SWEEP] GPU:        $gpuName (driver $driverVersion)"
Write-Host "[SWEEP] Max clock:  $maxClock MHz | power limit $powerLimitEnforced W enforced ($powerLimitDefault W default, $powerLimit W max)"
Write-Host "[SWEEP] Supported:  $($supported.Count) discrete graphics clocks, $($supported[-1])-$($supported[0]) MHz"
if ($explicitTargets) {
    Write-Host "[SWEEP] Sweep grid:  explicit list of $($targets.Count) targets, $floorMhz-$ceilMhz MHz - NOT derived from the clock table."
} elseif ($explicitBand) {
    $stepMhz = if ($targets.Count -gt 1) { [int][math]::Round([math]::Abs($targets[-1] - $targets[0]) / ($targets.Count - 1)) } else { 0 }
    Write-Host "[SWEEP] Sweep band:  $floorMhz-$ceilMhz MHz (explicit) - FINE sweep, ~$stepMhz MHz apart. Not a full-range curve."
} else {
    Write-Host "[SWEEP] Sweep floor: $floorMhz MHz ($MinFrequencyPercent% of max) - lower clocks exist but are not swept"
}
Write-Host "[SWEEP] Testing:    $($targets.Count) frequencies -> $($targets -join ', ') MHz"
if ($WorkloadCommand -ne "") {
    Write-Host "[SWEEP] Workload:   $WorkloadCommand   (timed; duration is the performance metric)"
} else {
    Write-Host "[SWEEP] Workload:   NONE SUPPLIED - start a load yourself, or this measures idle."
}

$perPointSeconds = $SettleSeconds + $MeasureSeconds
Write-Host ("[SWEEP] Estimated:  ~{0:N1} min of measurement (plus workload time if any)" -f (($targets.Count * $perPointSeconds) / 60))
Write-Host ""

# --- Applied configuration ------------------------------------------------------------

# Placed BEFORE the dry-run exit on purpose: the dry run is the rehearsal that exists to catch
# mistakes, and a forgotten -AppliedSettings is one of them. Warning only after the real run has
# started would be telling someone their 15 minutes are unattributable too late to fix it.
#
# Not a hard refusal: a stock run genuinely has nothing to declare, and blocking would tempt
# someone to type a space to get past it. The JSON records which of the two cases this was rather
# than leaving an empty string to be interpreted later. The pause is skipped on a dry run, where
# nothing is at stake and it would only cost patience.
if ([string]::IsNullOrWhiteSpace($AppliedSettings)) {
    Write-Host "[SWEEP] WARNING: no -AppliedSettings given."
    Write-Host "[SWEEP] Clocks and power are measured, but what you SET is not - the card does not"
    Write-Host "[SWEEP] report its V/F curve back, so nothing can reconstruct it after the fact."
    Write-Host "[SWEEP] If anything is non-stock, stop now and pass -AppliedSettings ""...""."
    if (-not $DryRun) {
        Write-Host "[SWEEP] Continuing in 5s - Ctrl+C to abort."
        Start-Sleep -Seconds 5
    }
} else {
    Write-Host ("[SWEEP] Configuration: {0}" -f $AppliedSettings)
}
Write-Host ""

if ($DryRun) {
    Write-Host "[SWEEP] DRY RUN - no GPU state was changed. Re-run without -DryRun to sweep."
    exit 0
}

if (-not $elevated) {
    Write-Host "[SWEEP] REFUSING TO START: not running as Administrator."
    Write-Host "[SWEEP] nvidia-smi clock locking requires elevation. Right-click PowerShell -> Run as administrator."
    Write-Host "[SWEEP] Checking now rather than failing halfway through a sweep with the clock pinned."
    exit 3
}

# --- Is anything else using the GPU? -------------------------------------------------
#
# This is the guard that protects the entire dataset. A sweep run while a game, a browser
# playing video, a local LLM, or an animated wallpaper is on the card measures THAT load
# mixed with ours, at every frequency, with no way to separate them afterwards. The result
# looks like perfectly ordinary data and is silently worthless.
#
# Utilisation is the robust signal - it catches anything, including processes not on any
# known-offenders list. Process names are only a hint for what to go close.

# Null unless the preflight actually sampled them, which only happens when a workload was
# given. A run with no workload records "not checked" rather than a misleading zero.
$encoderUtilPct = $null
$decoderUtilPct = $null
$freeVramMb = $null
$baselineUtilPct = $null
$maxBaselineAllowed = $MaxBaselineUtilization

if ($WorkloadCommand -ne "") {
    Write-Host "[SWEEP] Checking the GPU is quiet before starting..."
    $baseline = Get-BaselineUtilization -Smi $nvidiaSmi
    $heavy = Get-HeavyGpuProcesses -Smi $nvidiaSmi

    # Checked BEFORE the utilisation threshold, because it names the specific thing to go and
    # switch off rather than leaving the operator to guess from a percentage.
    $media = Get-EncoderActivity -Smi $nvidiaSmi
    if ($null -ne $media -and $AllowVideoEngines -and ($media.Encoder -gt 0 -or $media.Decoder -gt 0)) {
        Write-Host ("[SWEEP] Video engines ACTIVE (encoder {0}%, decoder {1}%) and -AllowVideoEngines was given." -f $media.Encoder, $media.Decoder)
        Write-Host "[SWEEP] This run is deliberately contaminated. Make sure -AppliedSettings says so."
    }
    elseif ($null -ne $media -and ($media.Encoder -gt 0 -or $media.Decoder -gt 0)) {
        Write-Host ""
        Write-Host ("[SWEEP] REFUSING TO START: the video engines are active - encoder {0}%, decoder {1}%." -f $media.Encoder, $media.Decoder)
        Write-Host "[SWEEP] Something is capturing or playing video. The usual cause is an always-on"
        Write-Host "[SWEEP] clipper: NVIDIA Instant Replay / ShadowPlay (ON BY DEFAULT, and it has no"
        Write-Host "[SWEEP] window), OBS replay buffer, Discord or Steam recording, Xbox Game Bar, AMD ReLive."
        Write-Host "[SWEEP] MEASURED ON THIS PROJECT: Instant Replay cost 1.5% of peak gemm throughput,"
        Write-Host "[SWEEP] 4.2% across 1237-2010 MHz, moved the measured efficiency optimum by a full"
        Write-Host "[SWEEP] grid step, and raised run-to-run spread at 1545 MHz from 0.13% to 6.95%."
        Write-Host "[SWEEP] utilization.gpu alone does NOT reliably catch it - the encoder is a separate engine."
        Write-Host "[SWEEP] Switch it off and re-run. Override with -AllowVideoEngines to measure"
        Write-Host "[SWEEP] contaminated conditions on purpose, and say so in -AppliedSettings if you do."
        exit 5
    }
    if ($null -ne $media) {
        $encoderUtilPct = $media.Encoder
        $decoderUtilPct = $media.Decoder
        if ($media.Encoder -eq 0 -and $media.Decoder -eq 0) {
            Write-Host ("[SWEEP] Video engines idle (encoder {0}%, decoder {1}%)." -f $media.Encoder, $media.Decoder)
        }
    }

    # ---- FREE VRAM ---------------------------------------------------------------------
    # THE FAILURE THIS CATCHES IS THE OPPOSITE SHAPE TO THE ONE ABOVE. The utilisation guard was
    # built for a BUSY card - a gaming session read 79% baseline and took gemm from 8.03 to
    # 4.84 TFLOP/s. A local LLM server that is loaded but idle is the inverse: ~0% utilisation
    # and most of the card's memory held. It walks straight past every check above, and on this
    # machine that is the NORMAL state, because llama-server holds a 27B on the same card this
    # script measures.
    #
    # What it would do to a run, if unguarded. gemm allocates ~768 MB and would RUN TO
    # COMPLETION under memory pressure, producing a number indistinguishable from a good one.
    # membw allocates ~3 GB and would not fit - failing outright, or falling back to system
    # memory the way this driver has already been shown to do silently, where throughput
    # collapses and nothing errors. A membw sweep measuring spilled memory is plausible, wrong,
    # and unrecoverable afterwards.
    $freeVramMb = Get-FreeVramMb -Smi $nvidiaSmi
    if ($null -ne $freeVramMb -and $MinFreeVramMb -gt 0 -and $freeVramMb -lt $MinFreeVramMb) {
        Write-Host ""
        Write-Host ("[SWEEP] REFUSING TO START: only {0} MB of VRAM is free, and the workloads need {1} MB." -f $freeVramMb, $MinFreeVramMb)
        $vramReport = Get-VramHolders -Smi $nvidiaSmi
        if ($vramReport.Holders.Count -gt 0 -and $vramReport.HasMemoryFigures) {
            Write-Host "[SWEEP] Holding the card right now, heaviest first:"
            foreach ($holder in $vramReport.Holders) {
                Write-Host ("[SWEEP]     {0}  {1} MB" -f $holder.Name, $holder.Mb)
            }
        } elseif ($vramReport.Holders.Count -gt 0) {
            Write-Host ("[SWEEP] On the GPU right now: {0}" -f ($vramReport.Holders -join ", "))
            Write-Host "[SWEEP] (Windows does not report per-process VRAM, so these are names without figures.)"
        }
        Write-Host "[SWEEP] The usual cause is a local LLM server left loaded - llama-server, Ollama,"
        Write-Host "[SWEEP] LM Studio, KoboldCpp. It sits at 0% utilisation with the model resident, so"
        Write-Host "[SWEEP] NEITHER the utilisation guard NOR the encoder guard above can see it."
        Write-Host "[SWEEP] membw allocates about 3 GB. Without it, this driver spills to system RAM"
        Write-Host "[SWEEP] WITHOUT FAILING - throughput collapses and no error is raised, which is a"
        Write-Host "[SWEEP] wrong number that looks exactly like a right one."
        Write-Host ("[SWEEP] Override with -MinFreeVramMb 0 if you know what you are doing, and say so in -AppliedSettings.")
        exit 6
    }
    if ($null -ne $freeVramMb) {
        Write-Host ("[SWEEP] Free VRAM {0} MB - clear to start." -f $freeVramMb)
    } else {
        # Not fatal: nvidia-smi answered every other query to get this far, so a null here is a
        # field this driver does not report rather than a broken card. Said out loud because a
        # silent skip would be indistinguishable from a passing check.
        Write-Host "[SWEEP] WARNING: could not read free VRAM. This run is NOT checked for a resident model."
    }

    if ($null -ne $baseline -and $baseline -gt $MaxBaselineUtilization) {
        Write-Host ""
        Write-Host ("[SWEEP] REFUSING TO START: GPU is already {0}% busy before any workload of ours." -f $baseline)
        if ($heavy.Count -gt 0) {
            Write-Host ("[SWEEP] Likely culprits on the GPU right now: {0}" -f ($heavy -join ", "))
        }
        Write-Host "[SWEEP] Close games, browsers playing video, animated wallpapers, and local LLM"
        Write-Host "[SWEEP] servers, then re-run. Competing load contaminates EVERY frequency point"
        Write-Host "[SWEEP] and cannot be separated out afterwards - the data would look fine and be wrong."
        Write-Host ("[SWEEP] Override with -MaxBaselineUtilization <pct> if you know what you are doing.")
        exit 4
    }

    $baselineUtilPct = $baseline
    Write-Host ("[SWEEP] Baseline utilisation {0}% - clear to start." -f $baseline)

} else {
    $idleCheck = Read-Telemetry -Smi $nvidiaSmi
    if ($null -ne $idleCheck -and $idleCheck.Utilization -lt 20) {
        Write-Host ("[SWEEP] WARNING: GPU utilisation is {0}% and no -WorkloadCommand was given." -f $idleCheck.Utilization)
        Write-Host "[SWEEP] An idle sweep measures nothing useful. Start your stress test, then re-run."
        Write-Host "[SWEEP] Continuing anyway in 5s - Ctrl+C to abort."
        Start-Sleep -Seconds 5
    }
}

# --- Output paths --------------------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $PSScriptRoot "..\..\data\frequency-sweeps"
}
if (-not (Test-Path $OutputDirectory)) {
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
}
$OutputDirectory = (Resolve-Path $OutputDirectory).Path

$startTime = Get-Date
$stamp = $startTime.ToString("yyyyMMdd-HHmmss")
$safeLabel = ($SessionLabel -replace "[^\w\-\.]", "_")
$csvPath = Join-Path $OutputDirectory "$stamp`_$safeLabel`_sweep.csv"
$jsonPath = Join-Path $OutputDirectory "$stamp`_$safeLabel`_sweep.json"

# Same Ctrl+C handling as the stability logger: intercept rather than terminate, so the
# finally block's clock reset is guaranteed to run. Degrades if no console is attached.
$consoleControlAvailable = $true
try {
    [Console]::TreatControlCAsInput = $true
} catch {
    $consoleControlAvailable = $false
    Write-Host "[SWEEP] No interactive console - Ctrl+C interception unavailable. The finally block still resets clocks."
}

# A click in the console window freezes this script mid-sweep with the clock still locked. See
# tools/Disable-QuickEdit.ps1 - it has happened, it cost six minutes and two corrupted points.
$quickEditGuard = Join-Path $PSScriptRoot "..\Disable-QuickEdit.ps1"
if (Test-Path $quickEditGuard) {
    . $quickEditGuard
    [void](Disable-ConsoleQuickEdit -Tag "SWEEP")
} else {
    Write-Host "[SWEEP] NOTE: tools\Disable-QuickEdit.ps1 not found - DO NOT CLICK IN THIS WINDOW while the sweep runs."
}

# Whether the benchmark actually produced numbers. A sweep that never launched its workload
# wrote a clean CSV and exited 0 on 2026-09-12; see WorkloadResultVerdict.ps1 for the story.
$verdictHelper = Join-Path $PSScriptRoot "WorkloadResultVerdict.ps1"
$workloadVerdictAvailable = Test-Path $verdictHelper
if ($workloadVerdictAvailable) {
    . $verdictHelper
} else {
    Write-Host "[SWEEP] NOTE: WorkloadResultVerdict.ps1 not found - this run will NOT check that the"
    Write-Host "[SWEEP] benchmark produced any result. A workload that fails to launch will look normal."
}

# Reporting only: derive clock bucket width from the requested grid. This helper never
# changes a lock, voltage, power limit, or any measurement.
. (Join-Path $PSScriptRoot "ClockBuckets.ps1")

$results = New-Object System.Collections.ArrayList
$abortedByUser = $false
$workloadNeverRan = $false

# --- Sweep ---------------------------------------------------------------------------

try {
    foreach ($target in $targets) {

        if ($consoleControlAvailable -and [Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq "C" -and ($key.Modifiers -band [ConsoleModifiers]::Control)) {
                Write-Host ""
                Write-Host "[SWEEP] Ctrl+C received - stopping sweep and resetting clocks."
                $abortedByUser = $true
                break
            }
        }

        Write-Host ("[SWEEP] --> locking {0} MHz" -f $target)
        $lockOutput = & $nvidiaSmi -lgc $target 2>&1
        $lockFailed = ($LASTEXITCODE -ne 0)
        if ($lockFailed) {
            Write-Host "[SWEEP] LOCK FAILED at $target MHz: $lockOutput"
            Write-Host "[SWEEP] Aborting rather than recording measurements at an unknown clock."
            break
        }

        Start-Sleep -Seconds $SettleSeconds

        $samples = New-Object System.Collections.ArrayList
        $throttleSeen = @{}
        $workloadSeconds = $null
        $workloadJson = $null

        if ($WorkloadCommand -ne "") {
            # Telemetry MUST be sampled while the workload is running. Running the workload
            # first and sampling afterwards measures the card at IDLE, which would produce a
            # power curve that says nothing about power under load - a silently worthless
            # dataset. So: launch the workload as a separate process, sample power for as
            # long as it runs, then collect its output.
            $stdoutPath = [System.IO.Path]::GetTempFileName()
            $stderrPath = [System.IO.Path]::GetTempFileName()
            $workloadStart = Get-Date

            $process = Start-Process -FilePath "cmd.exe" `
                -ArgumentList "/c", $WorkloadCommand `
                -PassThru -NoNewWindow `
                -RedirectStandardOutput $stdoutPath `
                -RedirectStandardError $stderrPath

            # Touching .Handle caches the process handle while the process is still alive.
            # Without it, Start-Process -PassThru returns an object whose ExitCode reads back
            # as $null after exit - and "$null -ne 0" is TRUE, so every successful point
            # printed a failure message with a blank code. That made a real crash and a clean
            # run produce identical output, i.e. no failure detection at all.
            $processHandle = $process.Handle

            while (-not $process.HasExited) {
                $reading = Read-Telemetry -Smi $nvidiaSmi
                if ($null -ne $reading) {
                    [void]$samples.Add($reading)
                    $throttleSeen[$reading.ThrottleMask] = $true
                }
                Start-Sleep -Milliseconds ([int]($SampleIntervalSeconds * 1000))
            }
            $process.WaitForExit()
            $workloadSeconds = [math]::Round(((Get-Date) - $workloadStart).TotalSeconds, 3)

            $stdoutText = ""
            if (Test-Path $stdoutPath) { $stdoutText = (Get-Content $stdoutPath -Raw) }
            $exitCode = $process.ExitCode
            if ($null -eq $exitCode) {
                Write-Host "[SWEEP] WARNING: could not read the workload's exit code at $target MHz - relying on bench_ok from its JSON."
            } elseif ($exitCode -ne 0) {
                $errText = ""
                if (Test-Path $stderrPath) { $errText = (Get-Content $stderrPath -Raw) }
                Write-Host "[SWEEP] Workload exited $exitCode at $target MHz. stderr: $(($errText -split "`n" | Select-Object -First 2) -join ' ')"
            }

            # The benchmark's own --json output carries its internal timing, which is more
            # precise than our wall-clock wrapper (it excludes process startup and CUDA init).
            foreach ($line in ($stdoutText -split "`r?`n")) {
                $trimmed = $line.Trim()
                if ($trimmed.StartsWith("{") -and $trimmed.EndsWith("}")) {
                    try { $workloadJson = $trimmed | ConvertFrom-Json } catch { }
                }
            }

            Remove-Item $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
        } else {
            # No workload supplied: assume an external load is already running and just
            # sample for the configured window.
            $deadline = (Get-Date).AddSeconds($MeasureSeconds)
            while ((Get-Date) -lt $deadline) {
                $reading = Read-Telemetry -Smi $nvidiaSmi
                if ($null -ne $reading) {
                    [void]$samples.Add($reading)
                    $throttleSeen[$reading.ThrottleMask] = $true
                }
                Start-Sleep -Milliseconds ([int]($SampleIntervalSeconds * 1000))
            }
        }

        if ($samples.Count -eq 0) {
            Write-Host "[SWEEP] No telemetry collected at $target MHz - skipping this point."
            continue
        }

        # Window the samples to the benchmark's timed region.
        #
        # Sampling necessarily spans the whole workload PROCESS, but performance is measured
        # over a strictly smaller interval inside it. Averaging power across the difference
        # mixes in ~2.3 s of Python import and CUDA init at idle - measured on this machine as
        # 124.77 W recorded against 148.52 W actually drawn under load, a 16% understatement.
        # Efficiency is throughput / power, so an efficiency curve built from the process-wide
        # average is dividing a load number by a partly-idle one.
        #
        # The dilution also shrinks as the clock drops (the run lengthens while init stays
        # ~2.3 s), so it is a frequency-dependent bias, not a constant offset that would
        # cancel out of the comparison.
        $statSamples = @($samples)
        $windowApplied = $false
        if ($null -ne $workloadJson -and
            $null -ne $workloadJson.timed_region_start_unix -and
            $null -ne $workloadJson.timed_region_end_unix) {

            $windowStart = [double]$workloadJson.timed_region_start_unix
            $windowEnd = [double]$workloadJson.timed_region_end_unix
            $inWindow = @($samples | Where-Object { $_.Timestamp -ge $windowStart -and $_.Timestamp -le $windowEnd })

            # Two samples is the floor for an average worth reporting. Below that, fall back to
            # the whole process and say so - a loudly-flagged diluted number beats a silent one
            # computed from a single reading.
            if ($inWindow.Count -ge 2) {
                $statSamples = $inWindow
                $windowApplied = $true
            } else {
                Write-Host ("[SWEEP] WARNING: only {0} sample(s) fell inside the benchmark's timed region at {1} MHz." -f $inWindow.Count, $target)
                Write-Host "[SWEEP] Falling back to whole-process averages for this point - its power figure is diluted by CUDA init."
            }
        } elseif ($WorkloadCommand -ne "") {
            Write-Host "[SWEEP] WARNING: workload emitted no timed-region stamps at $target MHz - power averaged over the whole process."
        }

        $clockStats = $statSamples | Select-Object -ExpandProperty SmClock | Measure-Object -Average -Minimum -Maximum
        $memClockStats = $statSamples | Select-Object -ExpandProperty MemClock | Measure-Object -Average -Minimum -Maximum
        $powerStats = $statSamples | Select-Object -ExpandProperty PowerDraw | Measure-Object -Average -Minimum -Maximum
        $tempStats = $statSamples | Select-Object -ExpandProperty Temperature | Measure-Object -Average -Maximum
        $utilStats = $statSamples | Select-Object -ExpandProperty Utilization | Measure-Object -Average
        $processPowerStats = $samples | Select-Object -ExpandProperty PowerDraw | Measure-Object -Average

        $row = [pscustomobject]@{
            target_frequency_mhz   = $target
            achieved_frequency_avg = [math]::Round($clockStats.Average, 1)
            achieved_frequency_min = $clockStats.Minimum
            achieved_frequency_max = $clockStats.Maximum
            memory_clock_avg_mhz   = [math]::Round($memClockStats.Average, 1)
            memory_clock_min_mhz   = $memClockStats.Minimum
            memory_clock_max_mhz   = $memClockStats.Maximum
            # Every in-window reading, so a median and a count of low readings can be computed
            # later (REGISTERED-PREDICTIONS.md section 15). Empty when no timed window applied.
            memory_clock_samples_mhz = if ($windowApplied) { "[" + ((@($statSamples | ForEach-Object { [string]$_.MemClock })) -join ",") + "]" } else { "[]" }
            lock_held              = ([math]::Abs($clockStats.Average - $target) -le 30)
            # Direction matters, and conflating the two hides the more dangerous failure.
            # BELOW target = the card could not sustain the request (power/thermal limits) -
            # ordinary, and expected at the top of the range where max boost is a bin the card
            # never actually holds. ABOVE target = the cap was not applied at all, which
            # nvidia-smi cannot do on its own. That means something outside nvidia-smi owns the
            # V/F curve - typically an MSI Afterburner profile with a flattened curve, which
            # pins a clock the card then refuses to drop below. That case is corrosive: several
            # grid points collapse onto the SAME clock, and a sweep that looks like N points is
            # really N-k, with duplicate rows that quietly overweight one frequency.
            lock_miss_mhz          = [math]::Round($clockStats.Average - $target, 1)
            lock_miss_direction    = if ([math]::Abs($clockStats.Average - $target) -le 30) { "none" }
                                     elseif ($clockStats.Average -gt $target) { "above" }
                                     else { "below" }
            power_avg_w            = [math]::Round($powerStats.Average, 2)
            power_min_w            = $powerStats.Minimum
            power_max_w            = $powerStats.Maximum
            temperature_avg_c      = [math]::Round($tempStats.Average, 1)
            temperature_max_c      = $tempStats.Maximum
            utilization_avg_pct    = [math]::Round($utilStats.Average, 1)
            power_avg_process_w    = [math]::Round($processPowerStats.Average, 2)
            power_window_applied   = $windowApplied
            # Preserve the benchmark's wall-clock timed region for an HWiNFO time join.
            # These stamps remain useful even if sparse power telemetry forced a fallback.
            window_start_unix      = if ($null -ne $workloadJson) { $workloadJson.timed_region_start_unix } else { $null }
            window_end_unix        = if ($null -ne $workloadJson) { $workloadJson.timed_region_end_unix } else { $null }
            workload_seconds       = $workloadSeconds
            bench_seconds          = if ($null -ne $workloadJson) { $workloadJson.duration_seconds } else { $null }
            bench_wall_seconds     = if ($null -ne $workloadJson) { $workloadJson.wall_seconds } else { $null }
            bench_monitoring_s     = if ($null -ne $workloadJson) { $workloadJson.monitoring_overhead_seconds } else { $null }
            bench_throughput       = if ($null -ne $workloadJson) { $workloadJson.throughput } else { $null }
            bench_throughput_unit  = if ($null -ne $workloadJson) { $workloadJson.throughput_unit } else { $null }
            bench_ok               = if ($null -ne $workloadJson) { $workloadJson.ok } else { $null }
            samples                = $statSamples.Count
            samples_process        = $samples.Count
            throttle_masks_seen    = ($throttleSeen.Keys -join ";")
            # ADDED 0.3.4: NVML's integrated energy over the timed region, from the benchmark's own
            # counter reads. An average power independent of the 2 Hz samples above; null when the
            # benchmark or card does not report it. The counter ticks about every 100 ms.
            energy_joules          = if ($null -ne $workloadJson) { $workloadJson.energy_joules } else { $null }
            energy_window_seconds  = if ($null -ne $workloadJson) { $workloadJson.energy_window_seconds } else { $null }
            energy_avg_power_w     = if ($null -ne $workloadJson) { $workloadJson.energy_avg_power_w } else { $null }
        }
        [void]$results.Add($row)

        # Fail on the FIRST point rather than at the end. A workload that cannot launch fails
        # identically at every frequency, so continuing buys nothing and costs the rest of the
        # run - an hour, on the sweep that prompted this. The throw unwinds through the finally
        # block below, so clocks are still reset.
        if ($workloadVerdictAvailable -and $WorkloadCommand -ne "" -and $results.Count -eq 1) {
            if (-not (Test-RowHasBenchResult -Row $row)) {
                Write-Host ""
                Write-Host "[SWEEP] *** THE WORKLOAD PRODUCED NO RESULT AT THE FIRST FREQUENCY. ***"
                Write-Host ("[SWEEP] Command: {0}" -f $WorkloadCommand)
                Write-Host "[SWEEP] The process was launched and the card was sampled, but no benchmark JSON"
                Write-Host "[SWEEP] came back, so there is no performance metric. The usual cause is a command"
                Write-Host "[SWEEP] line whose interpreter and script are on different drives."
                Write-Host "[SWEEP] Stopping now rather than measuring an idle card at every remaining point."
                # break rather than throw, so the one bad point is still written out. The CSV is
                # evidence of what went wrong; the non-zero exit below is what stops it being
                # mistaken for data.
                $workloadNeverRan = $true
                break
            }
        }

        $heldNote = "held"
        if ($row.lock_miss_direction -eq "above") { $heldNote = "OVERSHOT +$($row.lock_miss_mhz)" }
        elseif ($row.lock_miss_direction -eq "below") { $heldNote = "UNDERSHOT $($row.lock_miss_mhz)" }
        $powerNote = "whole process"
        if ($windowApplied) { $powerNote = "{0} in-window of {1}" -f $statSamples.Count, $samples.Count }
        Write-Host ("[SWEEP]     {0,5} MHz -> achieved {1,6} MHz ({2}), {3,6} W [{4}], {5,3} C, util {6,3}%" -f `
            $target, $row.achieved_frequency_avg, $heldNote, $row.power_avg_w, $powerNote, $row.temperature_avg_c, $row.utilization_avg_pct)
    }
} finally {
    Write-Host ""
    Write-Host "[SWEEP] Resetting GPU clocks..."
    Reset-GpuClocks -Smi $nvidiaSmi
    if ($consoleControlAvailable) {
        try { [Console]::TreatControlCAsInput = $false } catch { }
    }
}

# --- Output --------------------------------------------------------------------------

if ($results.Count -eq 0) {
    Write-Host "[SWEEP] No results collected. Nothing written."
    exit 2
}

$results | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8

# Computed HERE, above the session hashtable, because that hashtable records it. An earlier
# arrangement assigned it below and wrote null into every JSON, healthy runs included.
$workloadVerdict = $null
if ($workloadVerdictAvailable) {
    $workloadVerdict = Get-WorkloadResultVerdict -Rows @($results) -WorkloadCommanded ($WorkloadCommand -ne "")
}

$driftedPoints = @($results | Where-Object { -not $_.lock_held })
$undilutedPoints = @($results | Where-Object { -not $_.power_window_applied })
$overshotPoints = @($results | Where-Object { $_.lock_miss_direction -eq "above" })
$undershotPoints = @($results | Where-Object { $_.lock_miss_direction -eq "below" })

# The 25 MHz bucket is retained for coarse grids. Fine grids use half their smallest target
# spacing so adjacent achieved clocks cannot collapse solely because of the reporting bucket.
$clockGroups = @(Get-ClockGroups -Rows @($results) -TargetFrequencies @($targets))
$collapsedGroups = @($clockGroups | Where-Object { $_.Count -gt 1 })

$session = [ordered]@{
    session_label        = $SessionLabel
    gpu_name             = $gpuName
    driver_version       = $driverVersion
    max_clock_mhz        = $maxClock
    # UNCHANGED MEANING: this has always been power.max_limit and every historical session JSON
    # reports it that way. Redefining the key would make old files silently wrong.
    power_limit_w        = $powerLimit
    power_limit_enforced_w = $powerLimitEnforced
    power_limit_default_w  = $powerLimitDefault
    workload_command     = $WorkloadCommand
    # The one field nothing else can reconstruct. Absent means the operator was not asked or did
    # not answer - NOT that the card was at stock. Do not read it as stock.
    applied_settings     = $AppliedSettings
    applied_settings_declared = (-not [string]::IsNullOrWhiteSpace($AppliedSettings))
    # Recorded because a run made with a clipper running is not comparable to one without, and
    # this is not recoverable afterwards. Null when no workload ran, since the check is skipped.
    encoder_util_pct     = $encoderUtilPct
    decoder_util_pct     = $decoderUtilPct
    video_engines_allowed = [bool]$AllowVideoEngines
    # ADDED 0.3.3. The tool has ALWAYS measured this, used it to decide whether to refuse, printed
    # it, and then thrown it away. That is the wrong field to discard: 5.4.4 makes competing desktop
    # load the single most consequential contaminant in this project - up to 10.3% at 1545 MHz from
    # a baseline that passed the guard at 6% - and every sweep before this version can only be
    # checked against whatever the operator happened to type into -AppliedSettings. Across the six
    # stock suite replicates, five recorded a figure in free text and one recorded none at all.
    # Null means no workload ran, so the check was skipped - NOT that the GPU was idle.
    baseline_util_pct    = $baselineUtilPct
    max_baseline_allowed_pct = $maxBaselineAllowed
    # ADDED 0.3.2. Every sweep collected before this schema version has NO record of VRAM
    # occupancy, so those runs cannot be audited for a resident model retrospectively - the
    # information was never captured. That is the specific, unfixable cost of having shipped the
    # guard late, and it is recorded here rather than in a commit message nobody will read.
    # Null means the field could not be read, NOT that the card was empty.
    free_vram_mb_at_start = $freeVramMb
    min_free_vram_mb_required = $MinFreeVramMb
    started_at           = $startTime.ToString("o")
    ended_at             = (Get-Date).ToString("o")
    aborted_by_user      = $abortedByUser
    frequencies_planned  = $targets.Count
    frequencies_measured = $results.Count
    # Added 2026-09-12. Sweeps taken before this carry no record of whether their workload
    # produced anything, exactly as pre-0.3.2 sweeps carry no VRAM occupancy - the field did not
    # exist, so they cannot be audited for it retrospectively.
    workload_result_verdict = if ($workloadVerdictAvailable) { $workloadVerdict.verdict } else { $null }
    frequencies_with_bench_result = if ($workloadVerdictAvailable) { $workloadVerdict.withResult } else { $null }
    # Band provenance. A fine sweep and a full-range sweep produce structurally identical CSVs
    # and must never be pooled or compared as if they covered the same thing.
    sweep_band_min_mhz   = $floorMhz
    sweep_band_max_mhz   = $ceilMhz
    sweep_band_explicit  = $explicitBand
    sweep_targets_explicit = $explicitTargets
    # The ORDER the grid was walked. Sweeps taken before 2026-09-15 carry no such field and were
    # all ascending; absent must therefore be read as "ascending", never as "unknown".
    sweep_order          = if ($Descending) { "descending" } else { "ascending" }
    settle_seconds       = $SettleSeconds
    measure_seconds      = $MeasureSeconds
    drifted_points       = $driftedPoints.Count
    overshot_points      = $overshotPoints.Count
    undershot_points     = $undershotPoints.Count
    distinct_clocks_measured = $clockGroups.Count
    sample_interval_s    = $SampleIntervalSeconds
    power_windowed_points = ($results.Count - $undilutedPoints.Count)
    supported_clock_count = $supported.Count
    samples_file         = Split-Path $csvPath -Leaf
    schema_version       = "0.3.4"
}
# Out-File -Encoding utf8 writes a BOM in PowerShell 5.1, and json.load, jq and every other
# standard parser choke on it with "Expecting value: line 1 column 1". This is a
# machine-readable artifact, so it gets BOM-less UTF-8 written explicitly. Same defect and same
# fix as the stability logger's session.json, found there 2026-08-20 and missed here until a
# collection-kit verification run parsed the output on 2026-08-23.
[IO.File]::WriteAllText($jsonPath, ($session | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "[SWEEP] ===================== RESULT ====================="
Write-Host ("[SWEEP] Measured {0} of {1} planned frequencies." -f $results.Count, $targets.Count)
if ([string]::IsNullOrWhiteSpace($AppliedSettings)) {
    Write-Host "[SWEEP] NO CONFIGURATION RECORDED. This run cannot be compared against any other."
    Write-Host "[SWEEP] If the card was not at stock, note the settings beside the CSV now."
} else {
    Write-Host ("[SWEEP] Configuration: {0}" -f $AppliedSettings)
}
if ($abortedByUser) { Write-Host "[SWEEP] Sweep was stopped early by the user - partial curve." }
if ($undershotPoints.Count -gt 0) {
    Write-Host ("[SWEEP] NOTE: {0} point(s) ran BELOW their target by more than 30 MHz." -f $undershotPoints.Count)
    Write-Host "[SWEEP] The card could not sustain the requested clock - power or thermal limits. Expected"
    Write-Host "[SWEEP] at the top of the range, where max boost is a bin the card never actually holds."
}

if ($overshotPoints.Count -gt 0) {
    Write-Host ""
    Write-Host ("[SWEEP] *** {0} point(s) ran ABOVE their target - THE CLOCK CAP DID NOT APPLY. ***" -f $overshotPoints.Count)
    Write-Host "[SWEEP] nvidia-smi cannot exceed its own cap, so something else owns the V/F curve -"
    Write-Host "[SWEEP] typically an MSI Afterburner profile with a flattened curve pinning a high clock."
    Write-Host "[SWEEP] Close it / reset to stock and re-run before trusting this data."
    Write-Host "[SWEEP] Why this matters more than it looks: overshooting points collapse onto the SAME"
    Write-Host "[SWEEP] achieved clock, so the run yields fewer distinct frequencies than it claims and"
    Write-Host "[SWEEP] silently duplicates one. Check achieved_frequency_avg for repeats:"
    foreach ($group in $collapsedGroups) {
        Write-Host ("[SWEEP]   targets {0} MHz all ran at ~{1} MHz" -f `
            (($group.Group | ForEach-Object { $_.target_frequency_mhz }) -join ", "), $group.Group[0].achieved_frequency_avg)
    }
    Write-Host ("[SWEEP] Distinct frequencies actually measured: {0} of {1} planned." -f $clockGroups.Count, $targets.Count)
}
if ($WorkloadCommand -ne "" -and $undilutedPoints.Count -gt 0) {
    Write-Host ("[SWEEP] WARNING: {0} point(s) could not be windowed to the benchmark's timed region." -f $undilutedPoints.Count)
    Write-Host "[SWEEP] Their power_avg_w is averaged over the whole workload process, so it includes"
    Write-Host "[SWEEP] CUDA init at idle and understates load power. Check power_window_applied in the CSV."
}
if ($workloadVerdictAvailable) {
    if ($workloadVerdict.verdict -eq "none") {
        Write-Host ""
        Write-Host "[SWEEP] *** THIS RUN HAS NO PERFORMANCE DATA. ***"
        Write-Host ("[SWEEP] {0}" -f $workloadVerdict.message)
        Write-Host "[SWEEP] The power column is real - it is the idle draw of a locked card - so nothing"
        Write-Host "[SWEEP] downstream will fail on this file. Do not treat it as a sweep."
    } elseif ($workloadVerdict.verdict -eq "partial") {
        Write-Host ""
        Write-Host ("[SWEEP] WARNING: {0}" -f $workloadVerdict.message)
    }
}
if ($WorkloadCommand -eq "") {
    Write-Host "[SWEEP] No workload command was given, so there is NO performance metric in this data."
    Write-Host "[SWEEP] You have a power-vs-frequency curve. Efficiency needs performance too - re-run with -WorkloadCommand."
}
Write-Host "[SWEEP] CSV:  $csvPath"
Write-Host "[SWEEP] JSON: $jsonPath"
Write-Host "[SWEEP] =================================================="
Write-Host ""
Write-Host "[SWEEP] Clock locks do NOT survive a reboot. If anything looks wrong with the card's"
Write-Host "[SWEEP] clocks after this, reboot and it returns to stock."

# A run whose benchmark never produced a number is a failure, and it used to exit 0. Anything
# driving this in a loop - Invoke-SuiteReplicate.ps1 above all - can now tell.
# 7, because 2 through 6 are taken above - 3 in particular already means "not elevated", and
# two meanings for one code is how a caller silently mishandles the rarer of them.
if ($workloadNeverRan -or ($workloadVerdictAvailable -and $workloadVerdict.verdict -eq "none")) {
    exit 7
}

exit 0
