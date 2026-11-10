<#
  One focused membw sweep over the plateau band, with a caller-supplied label.

  BACKGROUND
      The 2026-08-19 tuned run sat flat at ~295 GB/s across 1545-1852 MHz while the stock run
      rose 312 -> 332 -> 342. A clean re-run with no stability logger reproduced the plateau to
      within 1%, and memory clock telemetry (added to the sweep tool for that run) showed a
      rock-steady 16301 MHz at every point. Throttle masks are clean in all three runs. So the
      plateau is not the logger, not a memory downclock, and not throttling.

      The remaining hypothesis is the core V/F curve: the tuned profile pins it flat near
      3000 MHz at and above ~925 mV, so locking the SM clock into the plateau band forces a
      voltage selection BELOW the flattened region, where the custom and stock curves diverge
      most. Separating the memory overclock from the core curve settles it.

  USAGE
      -Label memonly    memory overclock only, core V/F curve reverted to stock
      -Label oc         both applied (the original tuned configuration)
      -Label stock      neither

      -Workload membw   default. Sweeps 1400-2100 MHz over the plateau band, 10 points.
      -Workload gemm    sweeps the FULL default 13-point grid (1237-3090 MHz), which is the
                        exact grid both existing gemm sweeps used, so the three configurations
                        are comparable at identical targets rather than nearest-neighbours.

  WHAT IS DELIBERATELY NOT RUNNING
      No stability logger. The first tuned run had one spawning nvidia-smi once per second and
      the stock run did not, which made them methodologically different. Nothing else may touch
      the GPU during this.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Label,

    [ValidateSet("membw", "gemm")]
    [string]$Workload = "membw",

    # membw defaults to the 1400-2100 plateau band. That band lies ENTIRELY below ~925 mV on
    # the stock curve (0.840 V at 2085 MHz, measured), so a curve flattened only above 925 mV
    # is identical to stock inside it and a band sweep would re-measure a known result. Use
    # -FullRange to cover 1237-3090, where the flattened region actually takes effect.
    [switch]$FullRange
)

$ErrorActionPreference = "Stop"

$sweepDir = $PSScriptRoot
$repoRoot = Split-Path (Split-Path $sweepDir -Parent) -Parent
$python = "C:\Users\Raymond\AppData\Local\Programs\Python\Python312\python.exe"
# NOT $workload: PowerShell variables are case-insensitive, so that name would
# silently overwrite the $Workload parameter and the command would ask for a
# workload named after the script's own path.
$workloadScript = Join-Path $sweepDir "gpu_workload.py"
$outputDir = Join-Path $repoRoot "data\frequency-sweeps\membw-anomaly-20260819"

Write-Host "[RUN] label:    $Label" -ForegroundColor Cyan
Write-Host "[RUN] workload: $Workload$(if ($FullRange) { '  (FULL RANGE 1237-3090)' })" -ForegroundColor Cyan
Write-Host "[RUN] repo:     $repoRoot" -ForegroundColor Gray
Write-Host "[RUN] output:   $outputDir" -ForegroundColor Gray
Write-Host ""

# Both paths are space-free, so no quoting or 8.3 shortening is needed here. Check rather than
# assume - this command is handed to cmd /c, where an unquoted space silently truncates it.
foreach ($path in @($python, $workloadScript)) {
    if ($path -match '\s') { throw "Path contains a space and would break under cmd /c: $path" }
    if (-not (Test-Path $path)) { throw "Not found: $path" }
}

$command = "$python $workloadScript --workload $Workload --json"

$sweepArgs = @{
    SessionLabel    = "5060ti-$Label-$Workload"
    WorkloadCommand = $command
    SettleSeconds   = 8
    MeasureSeconds  = 20
    OutputDirectory = $outputDir
}
if ($Workload -eq "membw" -and -not $FullRange) {
    # The plateau band plus anchors either side of it.
    $sweepArgs.MinFrequencyMhz = 1400
    $sweepArgs.MaxFrequencyMhz = 2100
    $sweepArgs.FrequencyCount  = 10
} else {
    # Leaving the band unset reproduces the default 40%-of-max floor with 13 points, which is
    # the exact target list both existing gemm sweeps used.
    $sweepArgs.FrequencyCount = 13
}

& (Join-Path $sweepDir "Invoke-FrequencySweep.ps1") @sweepArgs

Write-Host ""
Write-Host "[RUN] Done. Leave this window open and tell Claude." -ForegroundColor Green
