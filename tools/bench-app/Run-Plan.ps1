param(
    [Parameter(Mandatory=$true)][string]$PlanPath,
    [string]$SessionPath = '',
    [string]$VolumeLabel = 'ESD-USB',
    [string]$MockPath = '',
    [int]$ParentPid = 0,
    [switch]$DryRun,
    [switch]$Resume
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Hwinfo-Csv.ps1')
. (Join-Path $PSScriptRoot 'Stock-Drift.ps1')
. (Join-Path $PSScriptRoot 'Pmon-Gate.ps1')
. (Join-Path $PSScriptRoot 'Profile-Hash.ps1')
. (Join-Path $PSScriptRoot 'Write-Atomic.ps1')
. (Join-Path $PSScriptRoot 'Card-Checks.ps1')
. (Join-Path $PSScriptRoot 'Desktop-Load.ps1')
$script:kit = $null
$script:record = $null
$script:activeLog = ''
$script:activeLogMode = ''
$script:activeLogUtcOffset = ''
$script:mock = $null
$script:failed = $false
$script:statePath = ''
$script:controlPath = ''
$script:resumeRunId = ''
$script:resumeSuffix = ''
$script:currentSlot = 0
$script:lastWitness = $null
$script:sessionStarted = $false
$script:cleaningUp = $false
$script:startedProcesses = @()
$script:mockLoggingRunning = $false
$script:tableTop = 0
$script:tableTopReads = 0
$script:sessionStamp = ''

function Set-RecordProperty([string]$name, $value) {
    if ($script:record -is [System.Collections.IDictionary]) { $script:record[$name]=$value }
    elseif ($script:record.PSObject.Properties.Name -contains $name) { $script:record.$name=$value }
    else { $script:record | Add-Member -NotePropertyName $name -NotePropertyValue $value }
}

function Save-Record {
    $json = $script:record | ConvertTo-Json -Depth 30
    # Write-FileAtomic, not Move-Item -Force: the window reads this file every tick, and a read
    # between Move-Item's delete and rename stopped Session D at step 27 (2026-09-24).
    [void](Write-FileAtomic $script:sessionPath $json)
    $state = @{ sessionPath = $script:sessionPath; planHash = $script:record.planHash; status = $script:record.status; finishedSteps = @($script:record.steps | Where-Object { $_.verdict -eq 'PASS' } | ForEach-Object { $_.key }) }
    [IO.File]::WriteAllText($script:statePath, ($state | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
}
function Resolve-KitPath([string]$path) {
    if ($path -match '^kit:/') {
        $relative = $path.Substring(5).Replace('/', '\')
        if ($relative -match '(^|\\)\.\.(\\|$)') { throw 'Path escapes kit root.' }
        return (Join-Path $script:kit $relative)
    }
    if (-not [IO.Path]::IsPathRooted($path) -and $path -notmatch '^[A-Za-z]:[\\/]') { throw "Relative path refused: $path" }
    return $path
}
function Sha256([string]$path) {
    $sha=[Security.Cryptography.SHA256]::Create()
    $stream=[IO.File]::OpenRead($path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function Get-SpaceFreePath([string]$path) {
    # The same rule as Collect.ps1: a short (8.3) name never contains a space; without one, the path
    # comes back unchanged and the caller refuses it.
    try {
        $short = (New-Object -ComObject Scripting.FileSystemObject).GetFile($path).ShortPath
        if ($short -and $short -notmatch '\s') { return $short }
    } catch { }
    return $path
}
function Find-Kit([string]$label) {
    if ($DryRun -and $MockPath) { return (Split-Path $MockPath -Parent) }
    $matches = @(Get-Volume | Where-Object { $_.FileSystemLabel -eq $label -and $_.DriveLetter })
    if ($matches.Count -ne 1) { throw "Expected one mounted volume labelled $label, found $($matches.Count)." }
    $root = ('{0}:\headroom-kit' -f $matches[0].DriveLetter)
    if (-not (Test-Path (Join-Path $root 'python\python.exe'))) { throw "Kit Python missing in $root." }
    return $root
}
function Call-External([string]$file, [string[]]$arguments) {
    $out = & $file @arguments 2>&1
    $code = $LASTEXITCODE
    foreach ($line in @($out)) { Write-Host $line }
    if ($code -ne 0) { throw "$file exited $code." }
    return $out
}
function Get-SupportedClockRange {
    # @(min, max) of the supported graphics clocks. In a dry run the mock supplies the top: either
    # tableTop, or tableTopSequence, one entry per read (the last repeats), to test a moving table.
    if ($DryRun) {
        $sequence=@($script:mock.tableTopSequence | Where-Object { $null -ne $_ })
        if ($sequence.Count -gt 0) {
            $i=[math]::Min($script:tableTopReads, $sequence.Count - 1); $script:tableTopReads++
            return @(180, [int]$sequence[$i])
        }
        if ($script:mock.tableTop) { return @(180, [int]$script:mock.tableTop) }
        return @(0, 0)
    }
    $raw=@(& nvidia-smi --query-supported-clocks=graphics --format=csv,noheader,nounits)
    if ($LASTEXITCODE -ne 0) { throw 'Could not query supported graphics clocks.' }
    $clocks=@($raw | Where-Object { $_ -match '^\s*\d+\s*$' } | ForEach-Object { [int]$_.Trim() })
    if ($clocks.Count -eq 0) { throw 'No supported graphics clocks reported.' }
    return @(($clocks | Measure-Object -Minimum).Minimum, ($clocks | Measure-Object -Maximum).Maximum)
}
function Assert-TableTopUnchanged {
    if ($script:tableTop -le 0) { return }
    $problem=Get-TableTopMoveProblem $script:tableTop (Get-SupportedClockRange)[1]
    if ($problem) { throw $problem }
}
function Get-CalibratedIterations($workloads) {
    # gemm is never calibrated: 120 is its default, and every committed gemm sweep on every card
    # used it, which is what keeps a new card's gemm curve comparable (Calibrate-Suite.ps1 header).
    $calibration=$script:record.calibration
    if ($null -eq $calibration) { throw 'This suite uses calibrated iterations, but no calibrate step has run.' }
    $names=@($calibration.workloads); $counts=@($calibration.iterations)
    $result=@()
    foreach ($name in @($workloads)) {
        if ($name -eq 'gemm') { $result+=120; continue }
        $i=[array]::IndexOf($names, [string]$name)
        if ($i -lt 0 -or [int]$counts[$i] -le 0) { throw "No calibrated iteration count for $name." }
        $result+=[int]$counts[$i]
    }
    return ,$result
}
function Get-Smi([string]$query) {
    if ($DryRun) { return $script:mock.telemetry }
    $row = @(& nvidia-smi ("--query-gpu=$query") '--format=csv,noheader,nounits' 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "nvidia-smi query failed: $row" }
    return @(([string]$row[0]).Split(',') | ForEach-Object { $_.Trim() })
}
function Reset-Clocks {
    if ($DryRun) { return @{ verified=$true; mocked=$true; resetCommandSucceeded=$true; readbackSmClockMhz=[double]$script:mock.witnesses.'1'.core } }
    & nvidia-smi -rgc | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Clock reset failed.' }
    Start-Sleep -Milliseconds 700
    $clock=@(Get-Smi 'clocks.sm')
    $readback=0.0
    if (-not [double]::TryParse([string]$clock[0],[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$readback) -or $readback -le 0) { throw 'Clock reset read-back failed.' }
    Write-Host "Clocks reset; read-back SM clock $($clock[0]) MHz."
    return @{ verified=$true; mocked=$false; resetCommandSucceeded=$true; readbackSmClockMhz=$readback }
}
function Register-BenchProcess($process,[string]$kind) {
    $started=Get-Date
    try { $started=[datetime]$process.StartTime } catch { }
    $script:startedProcesses+=@{ pid=[int]$process.Id; started=$started; kind=$kind }
}
function Get-BenchSurvivors {
    $all=@(Get-CimInstance Win32_Process -ErrorAction Stop)
    $found=@{}
    foreach ($root in $script:startedProcesses) {
        $live=@($all | Where-Object { $_.ProcessId -eq $root.pid -and [math]::Abs((([datetime]$_.CreationDate)-$root.started).TotalSeconds) -lt 3 })
        foreach ($process in $live) { $found[[string]$process.ProcessId]=$process }
        $children=@($all | Where-Object {
            $_.ParentProcessId -eq $root.pid -and ([datetime]$_.CreationDate) -ge $root.started.AddSeconds(-1) -and
            ([string]$_.CommandLine).IndexOf($script:kit,[StringComparison]::OrdinalIgnoreCase) -ge 0
        })
        foreach ($process in $children) { $found[[string]$process.ProcessId]=$process }
    }
    # A live child can have its own children; include that tree before deciding it is clear.
    $frontier=@($found.Values)
    while ($frontier.Count -gt 0) {
        $next=@()
        foreach ($parent in $frontier) {
            foreach ($child in @($all | Where-Object { $_.ParentProcessId -eq $parent.ProcessId })) {
                $id=[string]$child.ProcessId
                if (-not $found.ContainsKey($id)) { $found[$id]=$child; $next+=$child }
            }
        }
        $frontier=$next
    }
    return @($found.Values)
}
function Confirm-BenchProcesses {
    if ($DryRun) { return @{ verified=$true; mocked=$true; killedPids=@(); runningPids=@(); detail='none' } }
    $before=@(Get-BenchSurvivors)
    $killed=@()
    foreach ($process in $before) {
        & taskkill.exe /PID ([string]$process.ProcessId) /T /F | Out-Host
        $killed+=[int]$process.ProcessId
    }
    if ($killed.Count -gt 0) { Start-Sleep -Seconds 1 }
    $after=@(Get-BenchSurvivors)
    $running=@($after | ForEach-Object { [int]$_.ProcessId })
    $detail=if ($running.Count -gt 0) { 'still running: '+($running -join ',') } elseif ($killed.Count -gt 0) { 'killed survivors: '+($killed -join ',') } else { 'none' }
    return @{ verified=($running.Count -eq 0); mocked=$false; killedPids=$killed; runningPids=$running; detail=$detail }
}
function Get-BenchLogStatus {
    if ($DryRun) { if ($script:mockLoggingRunning) { return 'running' }; return 'stopped' }
    # *>&1, not 2>&1: the helper prints with Write-Host, which PS 5.1 sends to the information stream.
    # With 2>&1 nothing was captured, so every real session would have ended "unknown" and FAIL
    # (found at review 2026-09-23 by running this exact call; the dry-run tests mock it).
    $output=@(& (Join-Path $script:kit 'tools\hwinfo-logging\Invoke-HwinfoLogging.ps1') -Status *>&1)
    $code=$LASTEXITCODE
    foreach ($line in $output) { Write-Host $line }
    # No HWiNFO process means nothing can be logging; check the process, not printed text.
    if ($code -eq 3 -and -not (Get-Process HWiNFO64 -ErrorAction SilentlyContinue)) { return 'stopped' }
    if ($code -ne 0) { return 'unknown' }
    $joined=$output -join "`n"
    if ($joined -match 'Logging is RUNNING[.]') { return 'running' }
    if ($joined -match 'Logging is stopped[.]') { return 'stopped' }
    return 'unknown'
}
function Confirm-BenchLogStopped {
    $first=Get-BenchLogStatus
    $stopAttempted=$false
    $stopError=''
    if ($first -eq 'running') {
        $stopAttempted=$true
        if ($DryRun) {
            if (-not $script:mock.finalLoggingStopFails) { $script:mockLoggingRunning=$false }
        } else {
            $output=@(& (Join-Path $script:kit 'tools\hwinfo-logging\Invoke-HwinfoLogging.ps1') -Stop *>&1)
            $code=$LASTEXITCODE
            foreach ($line in $output) { Write-Host $line }
            if ($code -ne 0) { $stopError="HWiNFO stop exited $code." }
        }
    }
    $last=Get-BenchLogStatus
    return @{ status=$last; stoppedVerified=($last -eq 'stopped'); stopAttempted=$stopAttempted; stopError=$stopError; mocked=[bool]$DryRun }
}
function Read-Voltage([string]$path) {
    if ($DryRun) { return [double]$script:mock.voltage }
    return (Get-HwinfoCoreVoltage $path)
}
function Check-Control([bool]$betweenSteps) {
    # Cleanup must never abort on the Stop (or closed window) that caused it. Without this, the
    # revert witness always failed after Stop, so the card was reverted but never verified.
    # Found at review 2026-09-23; dry-run tests cannot see it (the dry witness skips polling).
    if ($script:cleaningUp) { return }
    if ($ParentPid -gt 0 -and -not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { throw 'Window closed; stopping safely.' }
    if (-not (Test-Path $script:controlPath)) { return }
    $control = Get-Content $script:controlPath -Raw | ConvertFrom-Json
    if ($control.stop) { throw 'Operator requested Stop.' }
    if ($betweenSteps -and $control.pause) {
        Write-Host 'Paused after this step. Press Continue in the window.'
        Set-RecordProperty 'operatorState' 'Paused'; Save-Record
        while ($true) {
            Start-Sleep -Milliseconds 500
            if ($ParentPid -gt 0 -and -not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { throw 'Window closed.' }
            $control = Get-Content $script:controlPath -Raw | ConvertFrom-Json
            if ($control.stop) { throw 'Operator requested Stop.' }
            if ($control.continue) { break }
        }
        $control.pause = $false; $control.continue = $false
        [IO.File]::WriteAllText($script:controlPath, ($control | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
        Set-RecordProperty 'operatorState' 'Running'; Save-Record
    }
}
function Test-HwinfoSensorsReady {
    # True when HWiNFO shows a Sensors window whose Log button reads 'Log Start': the state every
    # hwinfo-start step needs. Same detector as the final stop check. Quiet: polled every 2 s.
    if (-not (Get-Process HWiNFO64 -ErrorAction SilentlyContinue)) { return $false }
    $output=@(& (Join-Path $script:kit 'tools\hwinfo-logging\Invoke-HwinfoLogging.ps1') -Status *>&1)
    return ($LASTEXITCODE -eq 0 -and (($output -join "`n") -match 'Logging is stopped[.]'))
}
function Wait-Human([string]$instruction,[scriptblock]$autoReady=$null,[switch]$ForceWait) {
    # Returns 'operator' when Continue was pressed, 'auto' when $autoReady came true first.
    Write-Host "ACTION NEEDED: $instruction"
    if ($DryRun -and -not $ForceWait) { if ($autoReady -and $script:mock.sensorsReady) { return 'auto' }; return 'operator' }
    if ($script:cleaningUp) {
        # After Stop or a closed window there may be nobody to press Continue. Say it, record
        # it, and keep cleaning up rather than waiting forever.
        Write-Host 'Cleanup does not wait for this; do it by hand.'
        $script:record.cleanupWarnings += $instruction
        return
    }
    if ($ParentPid -le 0 -and -not $autoReady) { [void](Read-Host 'Press Enter after completing the instruction'); return 'operator' }
    $tick=0
    while ($true) {
        Start-Sleep -Milliseconds 500
        $tick++
        if ($autoReady -and ($tick % 4) -eq 1) {
            $ready=$false
            try { $ready=[bool](& $autoReady) } catch { }
            if ($ready) { Write-Host 'Detected automatically; continuing without Continue.'; return 'auto' }
        }
        if ($ParentPid -le 0) { continue }
        if (-not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { throw 'Window closed.' }
        $control = Get-Content $script:controlPath -Raw | ConvertFrom-Json
        if ($control.stop) { throw 'Operator requested Stop.' }
        if ($control.continue) {
            $control.continue = $false
            [IO.File]::WriteAllText($script:controlPath, ($control | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
            return 'operator'
        }
    }
}
function Check-Growth([string]$path) {
    if ($DryRun) { return }
    [void](Assert-HwinfoLogGrowth $path)
}
function Record-DesktopPreflight([string]$key) {
    $mockSnapshot=if ($DryRun) {
        if ($script:mock.desktopSnapshot) { $script:mock.desktopSnapshot } else { [pscustomobject]@{ foreground=$null; samples=@() } }
    } else { $null }
    $minimize=Minimize-BenchRenderers @($plan.minimizeKnownRenderers) ([bool]$DryRun) @($script:mock.rendererWindows)
    $snapshot=Get-BenchDesktopSnapshot $mockSnapshot
    $entry=@{ key=$key; minimizeKnownRenderers=$minimize; snapshot=$snapshot }
    Set-RecordProperty 'desktopPreflights' (@($script:record.desktopPreflights | Where-Object { $null -ne $_ }) + @($entry))
    Save-Record
    Write-Host "Desktop preflight $key recorded $(@($snapshot.gpuUsers).Count) GPU process/engine entries."
    foreach ($errorText in @($minimize.errors)+@($snapshot.errors)) { Write-Host "Desktop preflight: $errorText" }
}
function Check-StepDesktopLoad($step,$witness) {
    $offset=$script:activeLogUtcOffset
    $files=@()
    $log=$script:activeLog
    if ($DryRun) {
        $fixture=$script:mock.desktopLoadFixtures.([string]$step.label)
        if ($null -eq $fixture) { return @{ status='unchecked'; reason='Dry run has no desktop-load fixture.'; mocked=$true; windows=@() } }
        $files=@($fixture.sweepFiles); $log=[string]$fixture.log
        $offset=[string]$fixture.utcOffset
        $python=[string]$script:mock.desktopCheckPython
        $checker=Join-Path $PSScriptRoot 'check_desktop_load.py'
    } else {
        # Collect's suite label is not each workload's label: inspect the actual files, never infer
        # a log-to-sweep filename match. All suite workloads share this step's active HWiNFO log.
        if ($step.type -eq 'suite') { $files=@(Get-ChildItem -LiteralPath $witness.directory -Filter '*_sweep.csv' | ForEach-Object FullName) }
        else { $files=@($witness.csv) }
        $python=Join-Path $script:kit 'python\python.exe'
        $checker=Join-Path $script:kit 'tools\bench-app\check_desktop_load.py'
    }
    # A missing executable or broken checker is an installation error, not missing telemetry.
    return (Invoke-BenchDesktopCheck $python $checker $files $log $offset)
}
function Pause-DesktopLoad($item) {
    $message='DESKTOP LOAD was detected in this step. Minimize or close rendering windows. This measurement remains flagged; use Stop to end safely or Continue to run later steps.'
    Set-RecordProperty 'operatorState' 'Paused'
    Set-RecordProperty 'operatorMessage' $message
    # A Continue pressed for an earlier human step must not acknowledge this new warning.
    if (Test-Path $script:controlPath) {
        $control=Get-Content $script:controlPath -Raw | ConvertFrom-Json
        $control.continue=$false
        [IO.File]::WriteAllText($script:controlPath,($control | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
    }
    Save-Record
    $by=Wait-Human $message -ForceWait:([bool]($DryRun -and $script:mock.desktopPauseWait))
    $item.desktopLoad | Add-Member -NotePropertyName acknowledgedBy -NotePropertyValue $by -Force
    Set-RecordProperty 'operatorState' 'Running'
    Set-RecordProperty 'operatorMessage' $null
    Save-Record
}
function Run-Child($job) {
    $jobPath=Join-Path $script:kit ('results\bench-child-' + [guid]::NewGuid().ToString('N') + '.json')
    $outputPath=$jobPath+'.out.txt'
    $errorPath=$jobPath+'.err.txt'
    [IO.File]::WriteAllText($jobPath,($job | ConvertTo-Json -Depth 15),(New-Object Text.UTF8Encoding($false)))
    $p=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'Run-Child.ps1'),'-JobPath',$jobPath) -PassThru -WindowStyle Hidden -RedirectStandardOutput $outputPath -RedirectStandardError $errorPath
    # PS 5.1: read Handle at once, or ExitCode comes back empty once a redirected process exits
    # (reproduced 2026-09-23; the first live suite completed and was then reported as failed).
    $null=$p.Handle
    Register-BenchProcess $p 'Run-Child'
    $previousLength=0
    $pointIndex=0
    $pointCount=if ($job.type -eq 'sweep') { [int]$job.points } else { 13 }
    $workload=''
    try {
        while (-not $p.HasExited) {
            Check-Control $false
            if (Test-Path $outputPath) {
                $content=Get-Content $outputPath -Raw -ErrorAction SilentlyContinue
                if ($content -and $content.Length -gt $previousLength) {
                    $delta=$content.Substring($previousLength)
                    $previousLength=$content.Length
                    Write-Host $delta
                    foreach ($line in @($delta -split "`n")) {
                        if ($line -match 'Sweep \d+ of \d+: ([a-z0-9]+)') { $workload=$matches[1]; $pointIndex=0 }
                        if ($line -match 'Testing:\s+(\d+) frequencies') { $pointCount=[int]$matches[1]; $pointIndex=0 }
                        if ($line -match '--> locking (\d+) MHz') { $pointIndex++; $script:record.live=@{ point=$pointIndex; of=$pointCount; targetMhz=[int]$matches[1]; achievedMhz=$null; workload=$workload }; Save-Record }
                        if ($line -match '(\d+) MHz -> achieved\s+(\d+) MHz') { if ($script:record.live) { $script:record.live.achievedMhz=[int]$matches[2]; Save-Record } }
                    }
                }
            }
            Start-Sleep -Seconds 1
            $p.Refresh()
        }
        $handle=$p.Handle
        $p.WaitForExit()
        if (Test-Path $errorPath) { $errors=Get-Content $errorPath -Raw -ErrorAction SilentlyContinue; if ($errors) { Write-Host $errors } }
        if ($p.ExitCode -ne 0) { throw "Child job exited $($p.ExitCode)." }
    } finally {
        if (-not $p.HasExited) {
            & taskkill.exe /PID $p.Id /T /F | Out-Host
            $p.WaitForExit()
        }
        $p.Dispose()
        $script:record.live=$null
        Save-Record
    }
}
function Stop-Log {
    if (-not $script:activeLog) { return }
    if ($DryRun) { $script:activeLog = ''; return }
    $stopped=$false
    try {
        & (Join-Path $script:kit 'tools\hwinfo-logging\Invoke-HwinfoLogging.ps1') -Stop -LogPath $script:activeLog | Out-Host
        $stopped=($LASTEXITCODE -eq 0)
    } catch { Write-Host "HWiNFO automatic stop failed: $($_.Exception.Message)" }
    if (-not $stopped) {
        [void](Wait-Human 'Click Log Stop in the HWiNFO Sensors window.')
        $a = (Get-Item $script:activeLog).Length
        Start-Sleep -Seconds 5
        $b = (Get-Item $script:activeLog).Length
        if ($a -ne $b) { throw 'Manual HWiNFO log is still growing.' }
    }
    $script:activeLog = ''
}
function Run-Witness($step) {
    $locked = $false
    $samples = @()
    $voltageError = ''
    try {
        if ($step.lockMhz -and -not $DryRun) {
            & nvidia-smi -lgc "$($step.lockMhz),$($step.lockMhz)" | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Witness clock lock failed.' }
            $locked = $true
        }
        if ($DryRun) {
            $w = $script:mock.witness
            if ($script:mock.witnesses) { $w = $script:mock.witnesses.([string]$script:currentSlot) }
            # Dry run only: a slot with two locked witnesses (Session E's edit, 2026-09-24) needs
            # one mock per lock, keyed "slot@lock", which may carry its own voltage.
            if ($script:mock.witnesses -and $step.lockMhz) {
                $byLock = $script:mock.witnesses.("$($script:currentSlot)@$($step.lockMhz)")
                if ($null -ne $byLock) { $w = $byLock }
            }
            if ($null -eq $w) { throw 'Mock witness missing.' }
            $peak = [double]$w.core; $memory = [double]$w.memory
        } else {
            $python = Join-Path $script:kit 'python\python.exe'
            $workload = Join-Path $script:kit 'tools\frequency-sweep\gpu_workload.py'
            $args = @($workload,'--workload',$step.workload,'--iterations',[string]$step.iterations,'--json')
            $p = Start-Process -FilePath $python -ArgumentList $args -PassThru -WindowStyle Hidden
            $null = $p.Handle   # PS 5.1: read at once so ExitCode survives the exit
            Register-BenchProcess $p 'gpu_workload witness'
            try {
                while (-not $p.HasExited) {
                    Check-Control $false
                    $values = @(Get-Smi 'clocks.sm,clocks.mem,power.draw')
                    $voltageSample=$null
                    if ($step.voltageMin -and $script:activeLog) {
                        # Keep the reader's own error: swallowing it turned "two voltage columns"
                        # into "too few samples" on the first live run, 2026-09-23.
                        try { $voltageSample=Get-HwinfoCoreVoltage $script:activeLog } catch { if (-not $voltageError) { $voltageError=$_.Exception.Message } }
                    }
                    $samples += [pscustomobject]@{ core=[double]$values[0]; memory=[double]$values[1]; power=[double]$values[2]; voltage=$voltageSample }
                    Start-Sleep -Seconds 1
                    $p.Refresh()
                }
                $handle = $p.Handle
                $p.WaitForExit()
                if ($p.ExitCode -ne 0) { throw "Witness workload exited $($p.ExitCode)." }
            } finally { if (-not $p.HasExited) { $p.Kill(); $p.WaitForExit() }; $p.Dispose() }
            $steady = @($samples | Select-Object -Skip 4)
            if ($steady.Count -lt 4) { throw 'Witness has fewer than four steady samples.' }
            $peak = ($steady | Measure-Object core -Maximum).Maximum
            $memory = ($steady | Measure-Object memory -Maximum).Maximum
        }
        $script:lastWitness=@{ coreMhz=$peak; memoryMhz=$memory; samples=$samples.Count }
        if ($peak -lt $step.coreMin -or $peak -gt $step.coreMax) { throw "Witness core $peak MHz outside [$($step.coreMin),$($step.coreMax)]." }
        if ($memory -lt $step.memoryMin -or $memory -gt $step.memoryMax) { throw "Witness memory $memory MHz outside [$($step.memoryMin),$($step.memoryMax)]." }
        $voltage = $null
        if ($step.voltageMin) {
            if ($DryRun) {
                if ($null -ne $w.voltage) { $voltage=[double]$w.voltage } else { $voltage=Read-Voltage $script:activeLog }
            }
            else {
                $loaded=@($steady | Where-Object { $null -ne $_.voltage -and $_.voltage -gt 0 } | ForEach-Object { [double]$_.voltage } | Sort-Object)
                if ($loaded.Count -lt 4) {
                    $why=''
                    if ($voltageError) { $why=" First reader error: $voltageError" }
                    throw ("Too few loaded HWiNFO voltage samples for the witness ($($loaded.Count))." + $why)
                }
                $voltage=$loaded[[int][math]::Floor($loaded.Count/2)]
            }
            $script:lastWitness.voltageV=$voltage
            if ($voltage -lt $step.voltageMin -or $voltage -gt $step.voltageMax) { throw "Witness voltage $voltage V outside [$($step.voltageMin),$($step.voltageMax)]." }
        }
        return @{ coreMhz=$peak; memoryMhz=$memory; voltageV=$voltage; samples=$samples.Count }
    } finally {
        if ($locked) { [void](Reset-Clocks) }
    }
}
function Check-StockDrift($step) {
    if ($DryRun) {
        $pct=0.0
        if ($null -ne $script:mock.driftPct) { $pct=[double]$script:mock.driftPct }
        if ($pct -gt $step.maxMedianAbsPct) {
            if ($step.blocking -eq $false) { Write-Host "WARNING: stock drift $pct% exceeds $($step.maxMedianAbsPct)%. Recorded; not stopping."; return @{ worstMedianAbsPct=$pct; perWorkload=@{}; exceeded=$true } }
            throw "Stock drift $pct% exceeds $($step.maxMedianAbsPct)%."
        }
        return @{ worstMedianAbsPct=$pct; perWorkload=@{}; exceeded=$false }
    }
    $first=@($script:record.steps | Where-Object { $_.key -eq "$($step.firstRun)/collect" -and $_.verdict -eq 'PASS' } | Select-Object -Last 1)
    $last=@($script:record.steps | Where-Object { $_.key -eq "$($step.lastRun)/collect" -and $_.verdict -eq 'PASS' } | Select-Object -Last 1)
    if ($first.Count -ne 1 -or $last.Count -ne 1) { throw 'Stock drift needs both completed suite directories.' }
    $measurement=Measure-StockDrift $first[0].witness.directory $last[0].witness.directory $step.workloads
    if ($measurement.worstMedianAbsPct -gt $step.maxMedianAbsPct) {
        # "blocking": false records the breach and carries on. Added 2026-09-23 for the unattended
        # 3070 Ti Session D: a stop here would lose every later run, while the scorer applies the
        # same 1.5% rule afterwards and marks the prediction NOT SCOREABLE on its own.
        if ($step.blocking -eq $false) {
            Write-Host "WARNING: worst stock return median absolute change $($measurement.worstMedianAbsPct)% exceeds $($step.maxMedianAbsPct)%. Recorded; not stopping."
            $measurement.exceeded=$true
            return $measurement
        }
        throw "Worst stock return median absolute change $($measurement.worstMedianAbsPct)% exceeds $($step.maxMedianAbsPct)%."
    }
    $measurement.exceeded=$false
    return $measurement
}
function Run-Step($step) {
    switch ($step.type) {
        'gate-power' {
            $row = @(Get-Smi 'power.limit,power.default_limit,power.max_limit,driver_version')
            if ($step.stockOnly) {
                # A generic run list does not know the card's limits in advance; it only requires the
                # enforced limit to BE the default, which is what stock means for power.
                if ([double]$row[0] -ne [double]$row[1]) { throw "Power limit $($row[0]) W is not this card's default $($row[1]) W. This run list measures stock only." }
            }
            elseif ([double]$row[0] -ne $step.limit -or [double]$row[1] -ne $step.default -or [double]$row[2] -ne $step.max) { throw "Power gate expected $($step.limit)/$($step.default)/$($step.max), got $($row[0])/$($row[1])/$($row[2])." }
            $script:record.driver = $row[3]
            $script:record.power = @($row[0],$row[1],$row[2])
            return @{ power=$script:record.power; driver=$row[3] }
        }
        'gate-quiet' {
            if ($DryRun) { $reading=@{ maxSm=[double]$script:mock.quietUtil; maxEncoder=0; maxDecoder=0; samples=5 } }
            else {
                $lines = @(& nvidia-smi pmon -c 5 -s u)
                if ($LASTEXITCODE -ne 0) { throw 'pmon failed.' }
                $reading=Measure-PmonQuiet $lines
            }
            if ($reading.maxSm -ge $step.maxUtil -or $reading.maxEncoder -ne 0 -or $reading.maxDecoder -ne 0) { throw "Quiet gate failed: SM=$($reading.maxSm), ENC=$($reading.maxEncoder), DEC=$($reading.maxDecoder)." }
            return $reading
        }
        'gate-hash' {
            $path = Resolve-KitPath $step.path
            if ($DryRun) { $hash = [string]$script:mock.profileHash }
            else {
                $files = @(Get-ChildItem -Path $path -ErrorAction Stop)
                if ($files.Count -ne 1) { throw 'Expected exactly one profile store file.' }
                # With "sections", only those slots are pinned, so a section Afterburner rewrites by
                # itself ([Defaults], 2026-09-24) cannot stop a run. Without it, the whole file.
                if ($step.sections) { $hash = Get-ProfileSectionHash $files[0].FullName @($step.sections) }
                else { $hash = Sha256 $files[0].FullName }
            }
            if (-not $hash.StartsWith($step.prefix,[StringComparison]::OrdinalIgnoreCase)) { throw "Profile hash mismatch: $hash" }
            $script:record.profileHash = $hash
            return @{ sha256=$hash }
        }
        'gate-drift' { return (Check-StockDrift $step) }
        'minimize-known-renderers' { return (Minimize-BenchRenderers @($plan.minimizeKnownRenderers) ([bool]$DryRun) @($script:mock.rendererWindows)) }
        'apply-profile' {
            if (-not $DryRun) {
                $exe = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
                if (-not (Test-Path $exe)) { throw 'MSI Afterburner missing.' }
                & $exe "-profile$($step.slot)" -q | Out-Host
                Start-Sleep -Seconds 8
            }
            $script:currentSlot=$step.slot
            return @{ appliedSlot=$step.slot; verifiedBy='following witness' }
        }
        'witness' { return (Run-Witness $step) }
        'hwinfo-start' {
            $path = Resolve-KitPath ([string]$step.path).Replace('{session}', $script:sessionStamp)
            if ($script:resumeRunId) { $path = [IO.Path]::Combine([IO.Path]::GetDirectoryName($path), ([IO.Path]::GetFileNameWithoutExtension($path) + $script:resumeSuffix + [IO.Path]::GetExtension($path))) }
            if (Test-Path $path) { throw "Refusing to overwrite HWiNFO log: $path" }
            $script:activeLog = $path
            $script:activeLogUtcOffset=(Get-Date).ToString('zzz')
            if (-not $DryRun) {
                $hw = Join-Path $script:kit 'HWiNFO64.exe'
                if (-not (Get-Process HWiNFO64 -ErrorAction SilentlyContinue)) { Start-Process -FilePath $hw -WindowStyle Normal | Out-Null; Start-Sleep -Seconds 4 }
                & (Join-Path $script:kit 'tools\hwinfo-logging\Invoke-HwinfoLogging.ps1') -Start -LogPath $path | Out-Host
                $code = $LASTEXITCODE
                if ($code -ne 0) {
                    if (@(4,6,7) -notcontains $code) { throw "HWiNFO start failed with exit $code." }
                    [void](Wait-Human "Click Log Start in the Sensors window, save as $path")
                    Check-Growth $path
                    $script:activeLogMode='manual'
                } else { $script:activeLogMode='automatic' }
            } else {
                if ($script:mock.hwinfoStartFail) { [void](Wait-Human "Click Log Start in the Sensors window, save as $path"); $script:activeLogMode='manual' }
                else { $script:activeLogMode='automatic' }
            }
            return @{ path=$path; mode=$script:activeLogMode }
        }
        'hwinfo-stop' {
            # Dry-run only: lets a test fail one log-stop step (GPT Job 93, R2's resume trace).
            if ($DryRun -and $script:mock.failHwinfoStop) { throw 'Mock HWiNFO stop failure.' }
            $path=$script:activeLog; $mode=$script:activeLogMode; Stop-Log; return @{ path=$path; mode=$mode }
        }
        'calibrate' {
            # Counts are a property of the card and are taken ONCE per session: recalibrating the same
            # card has moved counts 2-18% (Calibrate-Suite.ps1). A resume skips a finished calibrate
            # run anyway; this guard keeps the counts if that run ever gains a later step.
            if ($null -ne $script:record.calibration) { return @{ reused=$true; iterations=@($script:record.calibration.iterations) } }
            if ($DryRun) {
                $counts=@($step.workloads | ForEach-Object { if ($script:mock.calibration) { [int]$script:mock.calibration } else { 100 } })
            } else {
                $resultPath=Join-Path $script:kit ('results\bench-calibration-' + [guid]::NewGuid().ToString('N') + '.json')
                $job=@{ type='calibrate'; python=(Join-Path $script:kit 'python\python.exe'); workloadScript=(Join-Path $script:kit 'tools\frequency-sweep\gpu_workload.py'); workloads=@($step.workloads); targetSeconds=$step.targetSeconds; resultPath=$resultPath }
                Run-Child $job
                $counts=@((Get-Content $resultPath -Raw | ConvertFrom-Json).iterations)
            }
            if ($counts.Count -ne @($step.workloads).Count -or @($counts | Where-Object { [int]$_ -le 0 }).Count -gt 0) { throw 'Calibration did not give a positive count for every workload.' }
            Set-RecordProperty 'calibration' ([ordered]@{ workloads=@($step.workloads); iterations=@($counts | ForEach-Object { [int]$_ }); targetSeconds=$step.targetSeconds })
            Save-Record
            return @{ reused=$false; iterations=@($counts) }
        }
        'suite' {
            if (-not $script:activeLog) { throw 'Suite has no active HWiNFO log.' }
            # The table-top check exists because a suite's grid is DERIVED from the table top. A
            # suite with an explicit target list does not move with the table, and an offset moves
            # the table by design (Session E, 2026-09-27: -165 MHz took the top 2115 -> 2100), so the
            # check is skipped there and the targets are verified in the CSVs below instead.
            $explicitTargets=@($step.targetsMhz | Where-Object { $null -ne $_ })
            if ($explicitTargets.Count -eq 0) { Assert-TableTopUnchanged }
            $iterations=if ([string]$step.iterations -eq 'calibrated') { Get-CalibratedIterations $step.workloads } else { @($step.iterations) }
            $memory=if ($step.expectedMemoryClockMhz) { $step.expectedMemoryClockMhz } else { 0 }
            if ($DryRun) { if ($script:mock.failSuite) { throw 'Mock suite failure.' }; return @{ label=$step.label; workloads=@($step.workloads); iterations=@($iterations) } }
            $before = @(Get-ChildItem (Join-Path $script:kit 'results') -Directory -Filter "*_$($step.label)" -ErrorAction SilentlyContinue | ForEach-Object FullName)
            $job=@{ type='suite'; script=(Join-Path $script:kit 'Collect.ps1'); label=$step.label; settings=$step.settings; workloads=$step.workloads; iterations=@($iterations); expectedMemoryClockMhz=$memory }
            if ($explicitTargets.Count -gt 0) { $job.targetsMhz=@($explicitTargets) }
            Run-Child $job
            $after = @(Get-ChildItem (Join-Path $script:kit 'results') -Directory -Filter "*_$($step.label)" | Where-Object { $before -notcontains $_.FullName })
            if ($after.Count -ne 1) { throw 'Suite did not produce one new result directory.' }
            $files = @(Get-ChildItem $after[0].FullName -Filter '*_sweep.csv')
            if ($files.Count -ne $step.workloads.Count) { throw 'Suite CSV count mismatch.' }
            foreach ($file in $files) {
                $rows=@(Import-Csv $file.FullName)
                if (@($rows | Where-Object { $_.bench_throughput }).Count -lt 10) { throw "Incomplete suite CSV: $($file.FullName)" }
                if ($explicitTargets.Count -gt 0) {
                    $got=@($rows | ForEach-Object { [int][double]$_.target_frequency_mhz } | Sort-Object)
                    $want=@($explicitTargets | ForEach-Object { [int]$_ } | Sort-Object)
                    if (($got -join ',') -ne ($want -join ',')) { throw "Suite CSV targets ($($got -join ',')) are not the plan's list ($($want -join ',')): $($file.FullName)" }
                }
            }
            return @{ directory=$after[0].FullName; csvCount=$files.Count }
        }
        'sweep' {
            if (-not $script:activeLog) { throw 'Sweep has no active HWiNFO log.' }
            Assert-TableTopUnchanged
            if ($null -ne $step.minPctOfTop -and $script:tableTop -le 0) { throw 'This sweep is set as a share of the clock table top, which is unknown.' }
            $sweepRange=Resolve-SweepRange $step $script:tableTop
            $out = Resolve-KitPath ([string]$step.output).Replace('{session}', $script:sessionStamp)
            if ($script:resumeRunId) { $out += $script:resumeSuffix }
            if (Test-Path $out) { throw "Refusing to overwrite sweep output: $out" }
            if ($DryRun) { return @{ output=$out; points=$step.points; minMhz=$sweepRange[0]; maxMhz=$sweepRange[1] } }
            # The sweep hands this string to cmd /c, where a quoted path fails (Collect.ps1 records why), so a
            # path with a space must become its short 8.3 form or be refused here, before any clock is
            # locked or output created (GPT Job 88, R3).
            $pyForCmd = Get-SpaceFreePath (Join-Path $script:kit 'python\python.exe')
            $wlForCmd = Get-SpaceFreePath (Join-Path $script:kit 'tools\frequency-sweep\gpu_workload.py')
            if ($pyForCmd -match '\s' -or $wlForCmd -match '\s') { throw "The kit path contains a space ($script:kit) and has no short name. Move the kit to a folder without spaces, for example E:\headroom-kit." }
            New-Item -ItemType Directory -Path $out | Out-Null
            $command = '{0} {1} --workload {2} --iterations {3} --json' -f $pyForCmd,$wlForCmd,$step.workload,$step.iterations
            $job=@{ type='sweep'; script=(Join-Path $script:kit 'tools\frequency-sweep\Invoke-FrequencySweep.ps1'); label=$step.label; command=$command; minMhz=$sweepRange[0]; maxMhz=$sweepRange[1]; points=$step.points; direction=$step.direction; output=$out; settings=$step.settings }
            Run-Child $job
            $files=@(Get-ChildItem $out -Filter '*_sweep.csv')
            if ($files.Count -ne 1) { throw 'Sweep CSV missing.' }
            return @{ output=$out; csv=$files[0].FullName; minMhz=$sweepRange[0]; maxMhz=$sweepRange[1] }
        }
        'human' {
            if ($step.launchHwinfo -and -not $DryRun -and -not (Get-Process HWiNFO64 -ErrorAction SilentlyContinue)) {
                Start-Process -FilePath (Join-Path $script:kit 'HWiNFO64.exe') -WindowStyle Normal | Out-Null
            }
            # With launchHwinfo, the step also passes by itself once the Sensors window is detected
            # (suggested by Raymond 2026-09-23), so a session can run start to finish untouched.
            # Continue still works; if Sensors never appears it waits exactly as before.
            $ready=if ($step.launchHwinfo) { { Test-HwinfoSensorsReady } } else { $null }
            $by=Wait-Human $step.instruction $ready
            return @{ acknowledged=$true; confirmedBy=$by }
        }
    }
}

try {
    if (-not [IO.Path]::IsPathRooted($PlanPath)) { throw 'PlanPath must be absolute.' }
    $validator=Join-Path $PSScriptRoot 'Test-Plan.ps1'
    & $validator -PlanPath $PlanPath | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Plan validation failed.' }
    if (-not $DryRun) {
        $principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run-Plan needs an elevated PowerShell.' }
    }
    $script:kit=Find-Kit $VolumeLabel
    if (-not $DryRun) {
        $kitPrefix=[IO.Path]::GetFullPath($script:kit).TrimEnd('\') + '\'
        $planFull=[IO.Path]::GetFullPath($PlanPath)
        if (-not $planFull.StartsWith($kitPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Live plan must be on the USB kit.' }
    }
    if ($MockPath) { $script:mock=Get-Content $MockPath -Raw | ConvertFrom-Json }
    elseif ($DryRun) { throw '-DryRun requires -MockPath for deterministic checks.' }
    if ($DryRun) { $script:mockLoggingRunning=[bool]$script:mock.finalLoggingStillRunning }
    $plan=Get-Content $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $planHash=Sha256 $PlanPath
    if (-not $SessionPath) { $SessionPath=Join-Path $script:kit ('results\bench-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json') }
    if (-not [IO.Path]::IsPathRooted($SessionPath)) { throw 'SessionPath must be absolute.' }
    if (-not $DryRun) {
        $resultsPrefix=[IO.Path]::GetFullPath((Join-Path $script:kit 'results')).TrimEnd('\') + '\'
        if (-not [IO.Path]::GetFullPath($SessionPath).StartsWith($resultsPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Live session must be under the USB kit results folder.' }
    }
    $script:sessionPath=$SessionPath
    # {session} in a log or sweep path becomes this session's own name, so a run list reused on
    # several cards (the generic protocol) never collides with an earlier card's files on the USB.
    $script:sessionStamp=[IO.Path]::GetFileNameWithoutExtension($SessionPath)
    $script:statePath=$SessionPath + '.state.json'
    $script:controlPath=$SessionPath + '.control.json'
    if ($Resume) {
        if (-not (Test-Path $SessionPath)) { throw 'Resume session is missing.' }
        $script:record=Get-Content $SessionPath -Raw | ConvertFrom-Json
        if ($script:record.planHash -ne $planHash) { throw 'Resume plan differs from original.' }
        if ($script:record.status -eq 'PASS') { throw 'Completed session cannot be resumed.' }
        # Each step's LATEST attempt decides, as the final verdict and the importer do. Counting every
        # historical PASS let two failed attempts of one run look complete (GPT Job 93, R2).
        $latestByKey=@{}
        foreach ($s in @($script:record.steps)) { $latestByKey[[string]$s.key]=$s }
        foreach ($run in $plan.runs) {
            $done=@($run.steps | Where-Object { $k="$($run.id)/$($_.id)"; $latestByKey.ContainsKey($k) -and $latestByKey[$k].verdict -eq 'PASS' })
            if ($done.Count -lt $run.steps.Count) { $script:resumeRunId=$run.id; break }
        }
        if (-not $script:resumeRunId) { throw 'No interrupted run to resume.' }
        $script:resumeSuffix='-resume-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
        # A resumed session is running again; the earlier FAIL stays in its step history.
        $script:record.status='RUNNING'; $script:record.error=$null; $script:record.end=$null
        Set-RecordProperty 'attemptStart' (Get-Date).ToString('o')
        Set-RecordProperty 'resumeRunId' $script:resumeRunId
        Set-RecordProperty 'operatorState' 'Running'
        Set-RecordProperty 'finalState' $null
    } else {
        if (Test-Path $SessionPath) { throw "Refusing to overwrite session: $SessionPath" }
        $started=(Get-Date).ToString('o')
        $script:record=[ordered]@{ schemaVersion=1; planHash=$planHash; start=$started; attemptStart=$started; resumeRunId=''; end=$null; status='RUNNING'; operatorState='Running'; finalState=$null; dryRun=[bool]$DryRun; selectedRuns=@($plan.runs | ForEach-Object id); customizations=@($plan.customizations); driver=$null; power=$null; profileHash=$null; supportedClockRange=$null; calibration=$null; progress=$null; live=$null; steps=@(); revert=$null; error=$null; afterRevertHumanCompleted=$false }
    }
    if (-not (Test-Path (Split-Path $SessionPath -Parent))) { New-Item -ItemType Directory -Path (Split-Path $SessionPath -Parent) -Force | Out-Null }
    Save-Record
    $script:sessionStarted=$true
    Set-RecordProperty 'operatorMessage' $null
    # Repeated on resume and before every measured step, including custom sweeps.
    Record-DesktopPreflight 'session-start'
    if (-not $DryRun) {
        # Keep the PC awake for the whole session. Nothing in the kit did, and a shop PC on default
        # power settings would sleep mid-suite in an unattended run. This is a per-process request,
        # released when the engine exits; it changes no setting. Added 2026-09-23 before the first
        # overnight Session D; verified with powercfg /requests.
        try {
            Add-Type -Namespace HeadroomBench -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);' -ErrorAction Stop
            $keep=[HeadroomBench.Power]::SetThreadExecutionState([uint32]2147483649)
            if ($keep -eq 0) { throw 'SetThreadExecutionState returned 0.' }
            Write-Host 'Keeping the PC awake for this session.'
        } catch { throw "Could not keep the PC awake; refusing an unattended session: $($_.Exception.Message)" }
    }
    if (-not $DryRun) {
        $gpu=@(Get-Smi 'name')
        if (-not (Test-CardMatches ([string]$gpu[0]) $plan.card)) { throw "Wrong GPU: $($gpu[0])." }
        Set-RecordProperty 'gpuName' ([string]$gpu[0])
    }
    # A generic run list matches every card of a pattern, so a name cannot tell two cards of one
    # model apart. Resume only on the SAME physical card: its calibrated counts, clock table and
    # silicon belong to it. (Dry runs take the UUID from the mock.)
    $uuid=if ($DryRun) { [string]$script:mock.uuid } else { [string]@(Get-Smi 'uuid')[0] }
    if ($uuid) {
        if ($Resume -and $script:record.gpuUuid -and $script:record.gpuUuid -ne $uuid) { throw "This session was started on another card ($($script:record.gpuUuid)); refusing to resume it on $uuid." }
        Set-RecordProperty 'gpuUuid' $uuid
    }
    $range=Get-SupportedClockRange
    $min=$range[0]; $max=$range[1]
    if ($max -gt 0) {
        $topProblem=Get-SuiteTopProblem $max $plan.card
        if ($topProblem) { throw $topProblem }
        if (-not $plan.card.generic -and -not $DryRun -and ($plan.card.minClockMhz -lt $min -or $plan.card.maxClockMhz -gt $max)) { throw "Catalog clock range [$($plan.card.minClockMhz),$($plan.card.maxClockMhz)] outside card [$min,$max]." }
        # A resumed session restarts one run on grids its earlier runs no longer share if the table
        # moved in between, which is how Session D2 lost its verdict across two days.
        if ($Resume -and $null -ne $script:record.supportedClockRange) {
            $moved=Get-TableTopMoveProblem ([int]@($script:record.supportedClockRange)[1]) $max
            if ($moved) { throw $moved }
        }
        $script:record.supportedClockRange=@($min,$max)
        $script:tableTop=$max
    }
    if (-not $DryRun) {
        $script:cardVerified=$true
        Save-Record
    }
    $total=0; foreach ($run in $plan.runs) { $total += $run.steps.Count }
    $index=0
    foreach ($run in $plan.runs) {
        foreach ($step in $run.steps) {
            $index++
            $key="$($run.id)/$($step.id)"
            $prior=@($script:record.steps | Where-Object { $_.key -eq $key })
            if ($prior.Count -gt 0 -and $prior[$prior.Count - 1].verdict -eq 'PASS' -and $run.id -ne $script:resumeRunId) { continue }
            Check-Control $true
            $item=[ordered]@{ key=$key; name=$step.name; type=$step.type; start=(Get-Date).ToString('o'); end=$null; verdict='RUNNING'; witness=$null; desktopLoad=$null; error=$null }
            $script:lastWitness=$null
            $script:record.progress=@{ index=$index; total=$total }
            $script:record.steps += $item
            Save-Record
            Write-Host "STEP $index/$total $key $($step.name)"
            try {
                if (@('suite','sweep') -contains $step.type) { Record-DesktopPreflight $key }
                $item.witness=Run-Step $step
                $item.verdict='PASS'
                if (@('suite','sweep') -contains $step.type) {
                    $item.desktopLoad=Check-StepDesktopLoad $step $item.witness
                    Write-Host "Desktop-load check: $($item.desktopLoad.status). Quiet does not prove a clean run."
                    if ($item.desktopLoad.status -eq 'DESKTOP LOAD') {
                        $item.verdict='DESKTOP LOAD'
                        Pause-DesktopLoad $item
                    }
                }
                Write-Host "$($item.verdict) $key"
            } catch {
                $item.verdict='FAIL'; $item.error=$_.Exception.Message
                if ($step.type -eq 'witness') { $item.witness=$script:lastWitness }
                $script:record.error=$item.error; $script:failed=$true
                Write-Host "FAIL $key : $($item.error)"
            } finally { $item.end=(Get-Date).ToString('o'); Save-Record }
            if ($script:failed) { throw $script:record.error }
        }
    }
    $script:record.status='PASS'
    # Resume keeps the old flag in history, but a clean replacement for that key can pass.
    $latestSteps=@{}
    foreach ($finishedStep in $script:record.steps) { $latestSteps[$finishedStep.key]=$finishedStep }
    if (@($latestSteps.Values | Where-Object { $_.desktopLoad.status -eq 'DESKTOP LOAD' }).Count -gt 0) {
        $script:record.status='FAIL'; $script:failed=$true
        $script:record.error='Desktop load was detected. Continue retains flagged measurements; a clean rerun is needed.'
    }
} catch {
    $script:failed=$true
    if ($script:record) { $script:record.status='FAIL'; $script:record.error=$_.Exception.Message }
    Write-Host "SESSION FAILED: $($_.Exception.Message)"
} finally {
    if ($script:record -and $script:sessionStarted) {
        $script:cleaningUp=$true
        try { Set-RecordProperty 'operatorState' 'Stopping and reverting'; Save-Record }
        catch { Write-Host "Could not publish cleanup state: $($_.Exception.Message)" }
        # A resumed record is a PSCustomObject from JSON, which cannot gain a property by
        # assignment; a new one is an ordered dictionary. Handle both, and never let this block cleanup.
        try {
            if ($script:record -is [System.Collections.IDictionary]) {
                if (-not $script:record.Contains('cleanupWarnings')) { $script:record['cleanupWarnings']=@() }
            } elseif (-not ($script:record.PSObject.Properties.Name -contains 'cleanupWarnings')) {
                $script:record | Add-Member -NotePropertyName cleanupWarnings -NotePropertyValue @()
            }
        } catch { Write-Host "Could not add cleanupWarnings: $($_.Exception.Message)" }
        $cleanupErrors=@()
        $final=@{ logging=@{ status='unknown'; stoppedVerified=$false; stopAttempted=$false }; clocks=@{ verified=$false; error='reset not completed' }; processes=@{ verified=$false; detail='not checked' } }
        try { $final.clocks=Reset-Clocks } catch { $final.clocks=@{ verified=$false; error=$_.Exception.Message }; $cleanupErrors+=$_.Exception.Message }
        try { Stop-Log } catch { $cleanupErrors+=$_.Exception.Message }
        try {
            # Never revert a card the plan was not written for: the revert slot is a slot number, and
            # on another machine it is a different curve. On 2026-09-23 a 5060 Ti plan resumed on the
            # 3070 Ti failed "Wrong GPU" and then applied its revert slot, P3, which there is Edit 2.
            if ($plan.revert -and -not ($DryRun -or $script:cardVerified)) {
                Write-Host 'Card identity not verified; no profile applied and no revert witness run.'
            } elseif ($plan.revert) {
                $revertStep=[pscustomobject]@{ type='apply-profile'; slot=$plan.revert.slot }
                [void](Run-Step $revertStep)
                $script:record.revert=Run-Witness $plan.revert.witness
            }
        } catch { $cleanupErrors+=$_.Exception.Message }
        try {
            $final.logging=Confirm-BenchLogStopped
            if (-not $final.logging.stoppedVerified) { $cleanupErrors+='HWiNFO logging was not verified stopped: '+$final.logging.status }
        } catch { $final.logging=@{ status='unknown'; stoppedVerified=$false; error=$_.Exception.Message }; $cleanupErrors+=$_.Exception.Message }
        try {
            $final.processes=Confirm-BenchProcesses
            if (-not $final.processes.verified) { $cleanupErrors+='Bench processes remain: '+$final.processes.detail }
        } catch { $final.processes=@{ verified=$false; detail=$_.Exception.Message }; $cleanupErrors+=$_.Exception.Message }
        Set-RecordProperty 'finalState' $final
        if ($cleanupErrors.Count -gt 0) { $script:record.status='FAIL'; $script:record.error='Cleanup: '+($cleanupErrors -join '; '); $script:failed=$true }
        $script:record.end=(Get-Date).ToString('o')
        Save-Record
    }
    if (-not $DryRun) {
        try { [void][HeadroomBench.Power]::SetThreadExecutionState([uint32]2147483648) } catch { }
    }
}
if ($script:failed) { exit 1 }
if ($plan.afterRevertHuman -and -not $script:failed) {
    try {
        [void](Wait-Human $plan.afterRevertHuman)
        $script:record.afterRevertHumanCompleted=$true
        Save-Record
    } catch {
        $script:record.status='FAIL'; $script:record.error=$_.Exception.Message; Save-Record
        exit 1
    }
}
exit 0
