<#
.SYNOPSIS
    Downloads the external datasets this project builds on.

.DESCRIPTION
    None of these are redistributed in this repository. Their licenses are either unchecked
    or do not clearly permit re-hosting, and re-hosting someone else's data without that
    check is not a thing to do casually. This fetches them from source instead.

    Everything lands under data/ and is gitignored.

.PARAMETER Only
    Fetch a single dataset by key instead of all of them. See the table in the script.
#>

[CmdletBinding()]
param(
    [string]$Only = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent

$datasets = @(
    @{
        Key     = "v100"
        Dir     = "data\raw"
        Files   = @("dataset_performance.csv", "dataset_power.csv", "dataset_efficiency.csv")
        BaseUrl = "https://raw.githubusercontent.com/zyjopensource/GPU-DVFS-Dataset/main/"
        Note    = "Single NVIDIA V100, 33 workloads, 13 core frequencies (757-1530 MHz). Core clock only, no voltage."
    },
    @{
        Key     = "gtx1080ti"
        Dir     = "data\external"
        Files   = @("gtx1080ti-dvfs-real-Performance-Power.csv", "gtx2070s-dvfs-real-Performance-Power.csv")
        BaseUrl = "https://raw.githubusercontent.com/HKBU-HPML/GPU-DVFS-Job-Schedule/master/csvs/"
        Note    = "CONSUMER cards. 1080 Ti: 600 rows, 30 apps, core 1600-2000 x mem 4000-5500 MHz - a 2D sweep, which the V100 set does not have. 2070 Super: 400 rows."
    },
    @{
        # Added 2026-09-29 for Fig. 1, after the second cold novelty check found that older consumer
        # sets reach far lower than the two above. Pinned to a commit, not a branch, so the bytes
        # cannot change under the figure. Only the LOW regime is fetched; the 700-1500 MHz high
        # regime is a separate sweep at a different memory clock.
        Key     = "gtx980"
        Dir     = "data\external"
        Files   = @("gtx980-low-dvfs-real-small-workload-Performance-Power.csv")
        BaseUrl = "https://raw.githubusercontent.com/HKBU-HPML/NV-DVFS-Benchmark/bc70c555d590be38900eff55300d61dc18e56aea/csvs/raw/"
        Note    = "CONSUMER GTX 980 (Maxwell), low regime: core 500-1000 MHz against an 1100 MHz reference file. 1080 rows. No voltage."
    },
    @{
        Key     = "titanx"
        Dir     = "data\external"
        Files   = @("aggregated_dataset_gtxtitanx.csv")
        BaseUrl = "https://raw.githubusercontent.com/hpc-ulisboa/gpuPTXModel/db54a508953880ad3dfb20194a2d5cb39c4af33c/datasets/gtxtitanx/realbenchmarks/"
        Note    = "CONSUMER GTX Titan X (Maxwell), Guerreiro et al., IEEE Access 2019: 16 core clocks 595-1164 MHz, 975 MHz profile default. Not a plain CSV: application-name lines, then 'mem,core,runtime,power,energy' rows. No voltage."
    },
    @{
        Key     = "gpuspecs"
        Dir     = "data\external"
        Files   = @("all-gpus.json")
        BaseUrl = "https://raw.githubusercontent.com/RightNow-AI/RightNow-GPU-Database/main/data/"
        Note    = "2,824 GPUs, already-numeric fields (sms, tdp, memoryBandwidth, memoryBus, processSize, clocks). Apache-2.0. Includes RTX 5060 Ti."
    },
    @{
        Key     = "mining"
        Dir     = "data\external"
        Files   = @("benchmarks.csv")
        BaseUrl = "https://raw.githubusercontent.com/kylemcdonald/ethereum-emissions/main/input/"
        Note    = "~500 rows, 422 with wattage. Consumer-card hashrate and power, aggregated from mining sources. External sanity check on perf-per-watt ordering, not training data."
    }
)

foreach ($dataset in $datasets) {
    if ($Only -ne "" -and $dataset.Key -ne $Only) { continue }

    $targetDir = Join-Path $repoRoot $dataset.Dir
    if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Force -Path $targetDir | Out-Null }

    Write-Host ""
    Write-Host "[DATASET] $($dataset.Key) -> $($dataset.Dir)"
    Write-Host "[DATASET]   $($dataset.Note)"

    foreach ($file in $dataset.Files) {
        $destination = Join-Path $targetDir $file
        try {
            Invoke-WebRequest -Uri ($dataset.BaseUrl + $file) -OutFile $destination -UseBasicParsing -TimeoutSec 60
            $size = (Get-Item $destination).Length
            Write-Host ("[DATASET]   OK   {0} ({1:N0} bytes)" -f $file, $size)
        } catch {
            Write-Host ("[DATASET]   FAIL {0} - {1}" -f $file, $_.Exception.Message)
        }
    }
}

Write-Host ""
Write-Host "[DATASET] Done. Check each dataset's license before quoting its numbers in a write-up."
Write-Host "[DATASET] NOTE: the HKBU-HPML repos use the 'master' branch, not 'main' - raw URLs break silently otherwise."
