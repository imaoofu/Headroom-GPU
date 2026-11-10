<#
.SYNOPSIS
    Measures the memory clock while the probe workload is doing its timed work. Dot-sourced by
    Collect.ps1; kept in its own file so it can be tested without running a collection.

.DESCRIPTION
    Starts the probe, samples memory clock and GPU utilisation with a wall-clock timestamp until the
    probe exits, then reads the probe's own JSON result. Only samples that fall inside the probe's
    timed region (timed_region_start_unix .. timed_region_end_unix) and show the GPU at least
    $BusyUtilizationPct busy count, so start-up, import and post-exit readings never decide the
    result.

    HISTORY. Until 2026-10-13 this was a fixed 60 x 400 ms window in Collect.ps1 that a slow cold
    start could outrun, after which an idle clock was printed as the loaded one (GPT Job 88). The
    first replacement counted any device-busy sample from launch onwards; GPT Job 89 (W1) showed that
    start-up or another process could then supply the reading, and that "work began" was really "the
    GPU was first busy". It also found no cleanup on an exception (W2), an unbounded nvidia-smi call
    that defeated the deadline (W3) and a bare `nvidia-smi` that ignored Collect's resolved path (W4).

    LIMITS. Utilisation is device-wide: inside the timed region it shows the GPU was busy while the
    probe worked, not that the probe alone made it busy. Collect's quiet-process checks are what keep
    other GPU work away. One NVIDIA GPU only: two make every query unparseable and the result a
    refusal. The deadline is a hang guard kept well above the ~12 minute cold start seen from the USB
    kit; nothing is locked or changed while this runs, so waiting is safe.
#>

function Invoke-SmiQuery([string]$SmiExe, [int]$TimeoutMs) {
    # nvidia-smi run as a bounded child: a hung query is killed rather than stalling the witness.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $SmiExe
    $psi.Arguments = '--query-gpu=clocks.current.memory,utilization.gpu --format=csv,noheader,nounits'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $process = $null
    try {
        $process = [System.Diagnostics.Process]::Start($psi)
        $out = $process.StandardOutput.ReadToEndAsync()
        $null = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit([Math]::Max(1, $TimeoutMs))) {
            try { $process.Kill() } catch { }
            return @{ ok = $false; text = ''; why = 'timed out' }
        }
        return @{ ok = ($process.ExitCode -eq 0); text = [string]$out.Result; why = "exit $($process.ExitCode)" }
    } catch {
        return @{ ok = $false; text = ''; why = $_.Exception.Message }
    } finally {
        if ($process) { $process.Dispose() }
    }
}

function Get-UnixNow { return [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 }

function Measure-LoadedMemoryClock {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string[]]$ProbeArguments,
        [string]$WorkingDirectory = (Get-Location).Path,
        [string]$SmiExe = 'nvidia-smi',
        [int]$BusyUtilizationPct = 50,
        [double]$EdgeGuardSeconds = 0.05,
        [int]$MinLoadedSamples = 3,
        [int]$DeadlineSeconds = 1800,
        [int]$QueryTimeoutSeconds = 10,
        [int]$PollMilliseconds = 400
    )
    $result = @{ ok = $false; mhz = 0; loadedSamples = 0; busyAnywhere = 0; polls = 0; queryFailures = 0
                 exitCode = $null; seconds = $null; timedRegionStartSeconds = $null; reason = ''; probeStopped = $true }
    $stem = Join-Path ([IO.Path]::GetTempPath()) ('headroom-witness-' + [guid]::NewGuid().ToString('N'))
    $stdout = "$stem.out"; $stderr = "$stem.err"
    $probe = $null
    $launched = Get-UnixNow
    $samples = New-Object System.Collections.ArrayList
    try {
        $probe = Start-Process -FilePath $PythonExe -WorkingDirectory $WorkingDirectory -ArgumentList $ProbeArguments `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
        # Touching Handle keeps the process handle open, without which ExitCode reads empty after exit.
        $null = $probe.Handle
        $deadline = $launched + $DeadlineSeconds
        while ($true) {
            $exited = $probe.HasExited
            $remainingMs = [int](($deadline - (Get-UnixNow)) * 1000)
            if (-not $exited -and $remainingMs -le 0) {
                $result.reason = "the probe workload was still running after $DeadlineSeconds s"
                return $result
            }
            $before = Get-UnixNow
            $query = Invoke-SmiQuery $SmiExe ([Math]::Min($QueryTimeoutSeconds * 1000, [Math]::Max(1, $remainingMs)))
            $after = Get-UnixNow
            $result.polls++
            $parts = $query.text.Trim().Split(',')
            $mem = 0; $util = 0
            if ($query.ok -and $parts.Count -eq 2 -and [int]::TryParse($parts[0].Trim(), [ref]$mem) -and
                [int]::TryParse($parts[1].Trim(), [ref]$util)) {
                [void]$samples.Add(@{ from = $before; to = $after; mem = $mem; util = $util })
            } else {
                $result.queryFailures++
            }
            if ($exited) { break }
            Start-Sleep -Milliseconds $PollMilliseconds
        }
        $probe.WaitForExit()
        $result.exitCode = $probe.ExitCode
        $result.seconds = [math]::Round((Get-UnixNow) - $launched, 1)
        foreach ($s in $samples) { if ($s.util -ge $BusyUtilizationPct) { $result.busyAnywhere++ } }
        if ($result.exitCode -ne 0) {
            $result.reason = "the probe workload exited with code $($result.exitCode)"
            return $result
        }
        $line = @(Get-Content -LiteralPath $stdout -ErrorAction SilentlyContinue | Where-Object { $_.Trim().StartsWith('{') }) | Select-Object -Last 1
        $report = $null
        if ($line) { try { $report = $line | ConvertFrom-Json } catch { $report = $null } }
        if ($null -eq $report -or $report.ok -ne $true) {
            $result.reason = 'the probe did not report a completed run (no JSON result with ok = true)'
            return $result
        }
        $start = 0.0; $end = 0.0
        if (-not ([double]::TryParse([string]$report.timed_region_start_unix, [ref]$start) -and
                  [double]::TryParse([string]$report.timed_region_end_unix, [ref]$end) -and $end -gt $start)) {
            $result.reason = 'the probe reported no usable timed region'
            return $result
        }
        $result.timedRegionStartSeconds = [math]::Round($start - $launched, 1)
        foreach ($s in $samples) {
            # The whole query must fall inside the timed region, with a guard band: a query that
            # straddles an edge may have read the state just outside it (GPT Job 89's boundary note),
            # and Windows PowerShell's clock (.NET Framework DateTime.UtcNow) moves in system-timer
            # ticks of up to ~15.6 ms while the probe's Python clock is precise. Found by a full gate
            # run, twice, before the band was added.
            if ($s.from -ge ($start + $EdgeGuardSeconds) -and $s.to -le ($end - $EdgeGuardSeconds) -and
                $s.util -ge $BusyUtilizationPct) {
                $result.loadedSamples++
                if ($s.mem -gt $result.mhz) { $result.mhz = $s.mem }
            }
        }
        if ($result.loadedSamples -lt $MinLoadedSamples) {
            $result.reason = ("only $($result.loadedSamples) samples inside the probe's timed work showed the GPU at least " +
                              "$BusyUtilizationPct% busy (need $MinLoadedSamples; $($result.polls) polls, " +
                              "$($result.queryFailures) failed queries)")
            return $result
        }
        $result.ok = $true
        return $result
    } catch {
        $result.ok = $false
        $result.reason = "the witness failed: $($_.Exception.Message)"
        return $result
    } finally {
        if ($probe) {
            try {
                if (-not $probe.HasExited) {
                    try { $probe.Kill() } catch { }
                    [void]$probe.WaitForExit(10000)
                }
                if (-not $probe.HasExited) {
                    $result.ok = $false; $result.probeStopped = $false
                    $result.reason = ($result.reason + "; the probe (process $($probe.Id)) could NOT be stopped").TrimStart('; ')
                } elseif ($result.reason -like '*still running*') {
                    $result.reason += ' and was stopped'
                }
            } catch {
                $result.ok = $false; $result.probeStopped = $false
                $result.reason = ($result.reason + "; stopping the probe failed: $($_.Exception.Message)").TrimStart('; ')
            }
            $probe.Dispose()
        }
        Remove-Item -LiteralPath $stdout, $stderr -ErrorAction SilentlyContinue
    }
}
