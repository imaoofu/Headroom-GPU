# Pure display calculations used by the window and its no-GPU tests.
function Get-BenchEstimate {
    param($Plan, $Record, [datetime]$Now)
    $entries=@()
    foreach ($run in @($Plan.runs)) {
        foreach ($step in @($run.steps)) {
            $minutes=if ($null -ne $step.estimatedMinutes) { [double]$step.estimatedMinutes } else { [double]$run.minutes / [math]::Max(1,@($run.steps).Count) }
            $entries+=@{ key=([string]$run.id+'/'+[string]$step.id); runId=[string]$run.id; minutes=[math]::Max(0,$minutes) }
        }
    }
    $attemptStart=if ($Record.attemptStart) { [datetime]$Record.attemptStart } else { [datetime]$Record.start }
    $current=@($Record.steps | Where-Object { $_.verdict -eq 'RUNNING' -and [datetime]$_.start -ge $attemptStart } | Select-Object -Last 1)
    $currentIndex=-1
    if ($current.Count -gt 0) {
        for ($i=0;$i -lt $entries.Count;$i++) { if ($entries[$i].key -eq $current[0].key) { $currentIndex=$i; break } }
    }
    $resumeRunId=[string]$Record.resumeRunId
    $remaining=0.0
    $currentRemaining=0.0
    $overrun=$false
    for ($i=0;$i -lt $entries.Count;$i++) {
        $entry=$entries[$i]
        if ($currentIndex -ge 0) {
            if ($i -lt $currentIndex) { continue }
            if ($i -eq $currentIndex) {
                $elapsed=[math]::Max(0,($Now-([datetime]$current[0].start)).TotalMinutes)
                $currentRemaining=[math]::Max(0,$entry.minutes-$elapsed)
                $overrun=($elapsed -ge $entry.minutes)
                $remaining+=$currentRemaining
                continue
            }
        } else {
            $done=@($Record.steps | Where-Object {
                $_.key -eq $entry.key -and $_.verdict -eq 'PASS' -and
                ($entry.runId -ne $resumeRunId -or ([datetime]$_.start -ge $attemptStart))
            })
            if ($done.Count -gt 0) { continue }
        }
        $remaining+=$entry.minutes
    }
    $stepFinish=$null
    if ($currentIndex -ge 0 -and -not $overrun) { $stepFinish=$Now.AddMinutes($currentRemaining) }
    return @{ stepFinish=$stepFinish; sessionFinish=$Now.AddMinutes($remaining); stepOverrun=$overrun; remainingMinutes=$remaining }
}

function Get-BenchStatus {
    param([string]$State)
    $states=@('Ready','Running','Pause requested','Paused','Stop requested','Stopping and reverting','PASS','FAIL')
    if ($states -notcontains $State) { throw "Unknown bench status: $State" }
    $color=if ($State -eq 'PASS') { 'Green' } elseif ($State -eq 'FAIL') { 'Red' } else { 'Black' }
    return @{ caption='Status:'; value=$State; color=$color }
}

function Format-BenchReadings {
    param([string]$SmiLine, [string]$Voltage='', [bool]$Logging=$false)
    $parts=@($SmiLine -split ',')
    $labels=@('Core','Memory','Power','Temp','Util')
    $units=@('MHz','MHz','W','C','%')
    $formatted=@()
    for ($i=0;$i -lt 5;$i++) {
        $value='--'
        if ($i -lt $parts.Count -and -not [string]::IsNullOrWhiteSpace($parts[$i])) {
            $number=0.0
            if ([double]::TryParse($parts[$i].Trim(),[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$number)) {
                if ($i -eq 2) { $value=$number.ToString('0.0',[Globalization.CultureInfo]::InvariantCulture) }
                else { $value=$number.ToString('0.##',[Globalization.CultureInfo]::InvariantCulture) }
            }
        }
        $gap=if ($i -eq 4) { '' } else { ' ' }
        $formatted+=($labels[$i]+' '+$value+$gap+$units[$i])
    }
    if ($Logging) {
        $v='--'
        $number=0.0
        if ([double]::TryParse($Voltage,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$number)) {
            $v=$number.ToString('0.000',[Globalization.CultureInfo]::InvariantCulture)
        }
        $formatted+=('Voltage '+$v+' V')
    }
    return ($formatted -join '   ')
}
