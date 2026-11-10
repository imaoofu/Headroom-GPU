<#
.SYNOPSIS
    The "active" condition of the activity A/B test: a DEFINED, LOGGED imitation of what the
    driving agent was doing during 5060ti-4i-finefloor-asc (2026-09-22), the run with 4 degraded
    points.

.DESCRIPTION
    That run's agent was "running nvidia-smi pmon checks and composing replies". This script
    reproduces the parts of that which can be scripted, on a fixed 5-second cycle:

      every cycle       nvidia-smi pmon -c 1 -s u          (driver query, as the agent ran)
      every 3rd cycle   ~2 s single-thread CPU burst       (stands in for the agent's own work)
      every 3rd cycle,  one full-screen capture to memory  (desktop readback through DWM)
        offset by one

    Every action is written to -EventLog as unix start/end times, so each degraded sweep point
    can be matched against what was happening inside its timed window.

    LIMITATION, stated in the output as well: this is a PROXY. The real agent also streamed text
    into an Electron window, which this does not imitate. A null result here weakens the activity
    hypothesis for THIS bundle; it does not refute it for the real thing.

    It never touches clocks, power limits or Afterburner. It stops when -StopFile appears or after
    -MaxMinutes, whichever is first.
#>
param(
    [Parameter(Mandatory = $true)][string]$EventLog,
    [Parameter(Mandatory = $true)][string]$StopFile,
    [int]$MaxMinutes = 20
)
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

function Now-Unix { [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 }

# The ok column exists because the first version logged every action whether or not it worked
# (found by the 2026-09-22 preflight review). A generator that silently failed would have made
# "active" runs silent ones, and the scorer could not have told.
"event,start_unix,end_unix,ok" | Set-Content -Path $EventLog -Encoding ASCII
function Log-Event([string]$name, [double]$t0, [bool]$ok) {
    ("{0},{1:F3},{2:F3},{3}" -f $name, $t0, (Now-Unix), [int]$ok) | Add-Content -Path $EventLog -Encoding ASCII
}
Log-Event "generator_start" (Now-Unix) $true

$deadline = (Get-Date).AddMinutes($MaxMinutes)
$cycle = 0
while (-not (Test-Path $StopFile) -and (Get-Date) -lt $deadline) {
    $cycleStart = Get-Date

    $t = Now-Unix
    & nvidia-smi pmon -c 1 -s u 2>&1 | Out-Null
    Log-Event "pmon" $t ($LASTEXITCODE -eq 0)

    if ($cycle % 3 -eq 0) {
        $t = Now-Unix
        $until = (Get-Date).AddSeconds(2)
        $x = 0.0
        while ((Get-Date) -lt $until) { for ($i = 0; $i -lt 20000; $i++) { $x += [math]::Sqrt($i) } }
        Log-Event "cpu_burst" $t $true
    }
    if ($cycle % 3 -eq 1) {
        $t = Now-Unix
        $captured = $false
        try {
            $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
            $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
            $g.Dispose(); $bmp.Dispose()
            $captured = $true
        } catch { $captured = $false }
        Log-Event "screen_capture" $t $captured
    }

    $cycle++
    $left = 5 - ((Get-Date) - $cycleStart).TotalSeconds
    if ($left -gt 0) { Start-Sleep -Milliseconds ([int]($left * 1000)) }
}
$reason = "stop_file"
if (-not (Test-Path $StopFile)) { $reason = "max_minutes_reached" }
Log-Event ("generator_stop_" + $reason) (Now-Unix) ($reason -eq "stop_file")
Write-Host ("Activity generator stopped after {0} cycles ({1}). It is a PROXY for agent activity, not the real thing." -f $cycle, $reason)
