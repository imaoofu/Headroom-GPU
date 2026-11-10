<#
.SYNOPSIS
    REGISTERED-PREDICTIONS section 10 (registered 1c4e10d, witness amended a7bcd44, both before
    collection): the 5060 Ti's negative control repeated in one session, P5 -> P2 -> P5, twelve
    workloads each. Operator absent. Stops at the first failure and leaves the card on stock P3.

.DESCRIPTION
    Every sweep goes through Invoke-LoggedSweep.ps1: its own preflight, HWiNFO log start and stop,
    and clock reset. Needs an ELEVATED shell. HWiNFO is started by Start-HwinfoSensors.ps1 if it is
    not already up.

    Grid, direction and iteration counts are the original control's, read from the sweep JSONs of
    repair-suite-p2-20260909. Each slot is verified before its suite by memory under load
    (16301 MHz), power limit (200 W) and, to tell P2 from P5, the median gemm power at a locked
    2475 MHz: P5 <= 163 W, P2 >= 165 W (section 10's amendment).

    A preflight refusal for a busy GPU (wrapper exit 4) is retried, up to six times a minute apart.
    Every other failure stops the queue.
#>
$ErrorActionPreference = "Continue"
$repo    = "C:\Users\Raymond\Documents\headroom"
$wrapper = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$ab      = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$stamp   = Get-Date -Format HHmmss
$log     = "C:\headroom-bench\results\queue-20260925-control10-$stamp.log"
New-Item -ItemType Directory -Force -Path "C:\headroom-bench\results" | Out-Null

$workloads = @("copy", "reduce", "softmax", "layernorm", "bgemm32", "bgemm64", "bgemm128",
               "bgemm256", "bgemm1024", "attention", "conv", "gemm")
# From repair-suite-p2-20260909's sweep JSONs, the control this repeats.
$iterations = @{ copy = "2660"; reduce = "2870"; softmax = "2600"; layernorm = "1597"; bgemm32 = "2673"
                 bgemm64 = "2661"; bgemm128 = "2467"; bgemm256 = "1579"; bgemm1024 = "414"
                 attention = "147"; conv = "151"; gemm = "120" }

function Say([string]$t) { $line = "[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $t; Write-Host $line; Add-Content -Path $log -Value $line }

function Get-LoadedSamples([string]$workload, [string]$iters) {
    $py = (Get-Command python).Source
    $wl = Join-Path $repo "tools\frequency-sweep\gpu_workload.py"
    $p = Start-Process -FilePath $py -ArgumentList @($wl, "--workload", $workload, "--iterations", $iters, "--json") -PassThru -WindowStyle Hidden
    $null = $p.Handle
    $s = @()
    while (-not $p.HasExited) {
        $r = ((& nvidia-smi --query-gpu=utilization.gpu,clocks.mem,power.draw --format=csv,noheader,nounits) | Select-Object -First 1) -split ','
        $u = 0
        if ($r.Count -eq 3 -and [int]::TryParse($r[0].Trim(), [ref]$u) -and $u -ge 50) {
            $s += [pscustomobject]@{ mem = [int]$r[1].Trim(); w = [double]$r[2].Trim() }
        }
        Start-Sleep -Milliseconds 500
    }
    return ,$s
}

# Apply a slot, then verify it by what it does: memory and power limit, then locked-2475 power.
function Set-Profile([int]$slot) {
    & $ab "-profile$slot" -q
    Start-Sleep -Seconds 8
    $plText = (& nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits) | Select-Object -First 1
    $pl = 0.0; [void][double]::TryParse($plText, [ref]$pl)
    & nvidia-smi -lgc 2475,2475 | Out-Null
    try { $samples = Get-LoadedSamples "gemm" "300" } finally { & nvidia-smi -rgc | Out-Null }
    $steady = @($samples | Select-Object -Skip 6)
    if ($steady.Count -lt 10) { Say "Profile ${slot}: only $($steady.Count) loaded samples at 2475 MHz. Stopping."; return $false }
    $w = @($steady.w | Sort-Object); $median = $w[[int]($w.Count / 2)]
    $mem = ($samples.mem | Measure-Object -Maximum).Maximum
    Say ("Profile {0}: power limit {1} W (expect 200), memory under load {2} MHz (expect 16301), gemm at locked 2475 MHz median {3:N1} W over {4} samples." -f $slot, $pl, $mem, $median, $steady.Count)
    $ok = ([math]::Abs($pl - 200.0) -le 0.5) -and ([math]::Abs($mem - 16301) -le 200)
    if ($slot -eq 5) { $ok = $ok -and ($median -le 163.0) }
    if ($slot -eq 2) { $ok = $ok -and ($median -ge 165.0) }
    if (-not $ok) { Say "Profile $slot is NOT verifiably applied (section 10 witness). Stopping."; return $false }
    return $true
}

function Invoke-Sweep($job) {
    for ($attempt = 1; $attempt -le 7; $attempt++) {
        $job | ConvertTo-Json | Set-Content -Path "C:\headroom-bench\job.json" -Encoding UTF8
        Say ("==== {0} (attempt {1}) ====" -f $job.label, $attempt)
        $out = "C:\headroom-bench\results\queue-20260925-$($job.label)-wrapper-$attempt.log"
        $p = Start-Process -FilePath "powershell.exe" -PassThru -WindowStyle Hidden `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper, "-JobPath", "C:\headroom-bench\job.json") `
            -RedirectStandardOutput $out -RedirectStandardError ($out + ".err")
        $null = $p.Handle   # PS 5.1: read now so ExitCode survives
        $p.WaitForExit()
        Say ("  wrapper exit {0}" -f $p.ExitCode)
        if ($p.ExitCode -eq 0) { return $true }
        if ($p.ExitCode -ne 4) { return $false }
        Say "  busy-GPU preflight refusal; waiting 60 s and retrying."
        Start-Sleep -Seconds 60
    }
    return $false
}

function Stop-Queue([string]$why) {
    Say "STOPPED: $why"
    & nvidia-smi -rgc | Out-Null
    & $ab -profile3 -q
    Say "Profile 3 (stock) applied on the way out."
    exit 1
}

Say "Section 10 control repeat starting. Log: $log"
& (Join-Path $repo "tools\hwinfo-logging\Start-HwinfoSensors.ps1") | ForEach-Object { Say $_ }
if ($LASTEXITCODE -ne 0) { Stop-Queue "HWiNFO Sensors not ready (exit $LASTEXITCODE)." }
$driver = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader) | Select-Object -First 1

$legs = @(
    @{ slot = 5; leg = "p5a"; name = "SPLIT CURVE P5, opening bracket" },
    @{ slot = 2; leg = "p2";  name = "REPAIR CURVE P2, the control" },
    @{ slot = 5; leg = "p5b"; name = "SPLIT CURVE P5, closing bracket" }
)
foreach ($leg in $legs) {
    if (-not (Set-Profile $leg.slot)) { Stop-Queue "profile check failed before $($leg.leg)." }
    foreach ($w in $workloads) {
        $job = @{ label = ("5060ti-ctrl10-{0}-{1}" -f $leg.leg, $w); workload = $w
                  minMhz = 1236; maxMhz = 3090; frequencyCount = 13; descending = $false
                  iterations = $iterations[$w]; expectedMinutes = 12
                  appliedSettings = ("REGISTERED-PREDICTIONS section 10: {0}, verified by memory 16301, PL 200 W and locked-2475 gemm power; " +
                      "store sections identical to 5060ti-profiles-20260922-rungB; grid 1236-3090 13 points ascending, iterations {1} from " +
                      "repair-suite-p2-20260909; order P5 P2 P5; driver {2}; OPERATOR ABSENT, driving agent idle") -f $leg.name, $iterations[$w], $driver }
        if (-not (Invoke-Sweep $job)) { Stop-Queue "sweep $($job.label) failed." }
    }
}
& nvidia-smi -rgc | Out-Null
& $ab -profile3 -q
Say "Profile 3 (stock) applied. Section 10 queue finished: 36 sweeps."
exit 0
