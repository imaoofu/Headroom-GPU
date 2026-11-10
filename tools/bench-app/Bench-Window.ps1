param([switch]$DryRun,[int]$AutoCloseSeconds=0,[string]$CatalogPath='', [string]$MockPath='',[switch]$Hidden)
$ErrorActionPreference='Stop'
# -Hidden is for the test suite only (2026-09-29): the dry-run test opened the full window on screen
# for a second on every test run, Claude's and GPT's alike. A real bench window is never hidden.
if ($Hidden -and -not $DryRun) { throw '-Hidden is allowed only with -DryRun.' }
. (Join-Path $PSScriptRoot 'Hwinfo-Csv.ps1')
. (Join-Path $PSScriptRoot 'Bench-Display.ps1')
. (Join-Path $PSScriptRoot 'Card-Checks.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$script:kit=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $script:kit 'Collect.ps1'))) {
    if ($DryRun) { $script:kit=[IO.Path]::GetTempPath() }
    else { throw 'Bench-Window must run from a synced USB kit.' }
}
if (-not $CatalogPath -and $DryRun) { $CatalogPath=Join-Path $PSScriptRoot 'catalog\sessiond-3070ti.json' }
if (-not $CatalogPath) {
    # Pick the catalog written for THIS card: its card.name must equal nvidia-smi's GPU name.
    # Added at review 2026-09-23: the window used to load the 3070 Ti catalog on every machine.
    $gpuName=([string]((& nvidia-smi --query-gpu=name --format=csv,noheader) | Select-Object -First 1)).Trim()
    $candidates=@()
    $genericCandidates=@()
    foreach ($file in @(Get-ChildItem (Join-Path $PSScriptRoot 'catalog') -Filter '*.json' | Sort-Object Name)) {
        try {
            $candidate=Get-Content $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            # A retired catalog (a session already collected) is never offered again (2026-09-25).
            if ($candidate.retired -or -not (Test-CardMatches $gpuName $candidate.card)) { continue }
            $entry=[pscustomobject]@{ Path=$file.FullName; Title=[string]$candidate.title }
            if ($candidate.card.generic) { $genericCandidates+=$entry } else { $candidates+=$entry }
        } catch { }
    }
    # A run list written for THIS card always wins. The generic stock-only protocol is offered
    # only on a card that has none (REGISTERED-PREDICTIONS 11, 2026-09-25).
    if ($candidates.Count -eq 0) { $candidates=$genericCandidates }
    if ($candidates.Count -eq 0) {
        [void][System.Windows.Forms.MessageBox]::Show("No run list on this USB is written for this card ($gpuName). Nothing was changed. Ask Claude for one.", 'Headroom Bench')
        exit 2
    }
    if ($candidates.Count -eq 1) { $CatalogPath=$candidates[0].Path }
    else {
        $pick=New-Object System.Windows.Forms.Form
        $pick.Text="Headroom Bench: choose a run list for $gpuName"; $pick.Width=640; $pick.Height=260; $pick.StartPosition='CenterScreen'
        $box=New-Object System.Windows.Forms.ListBox; $box.Left=12; $box.Top=12; $box.Width=600; $box.Height=150
        foreach ($c in $candidates) { [void]$box.Items.Add($c.Title) }
        $box.SelectedIndex=0
        $ok=New-Object System.Windows.Forms.Button; $ok.Text='Open'; $ok.Left=12; $ok.Top=172; $ok.DialogResult=[System.Windows.Forms.DialogResult]::OK
        $pick.Controls.Add($box); $pick.Controls.Add($ok); $pick.AcceptButton=$ok
        if ($pick.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 2 }
        $CatalogPath=$candidates[$box.SelectedIndex].Path
    }
}
$script:catalog=Get-Content $CatalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
$script:original=@{}
$script:originalIndex=@{}
for ($i=0; $i -lt $script:catalog.runs.Count; $i++) {
    $r=$script:catalog.runs[$i]
    $script:original[$r.id]=($r | ConvertTo-Json -Depth 20 -Compress)
    $script:originalIndex[$r.id]=$i
}
$script:session=''
$script:engine=$null
$script:outputPath=''
$script:errorPath=''
$script:lastOutput=''
$script:resumeSession=''
$script:activePlan=$null
$script:lastSmiLine=''

function Button($text,$x,$y,$w,$action) {
    $b=New-Object Windows.Forms.Button
    $b.Text=$text; $b.SetBounds($x,$y,$w,29)
    $b.Add_Click($action); $form.Controls.Add($b)
    return $b
}
function Label($text,$x,$y,$w,$h) {
    $l=New-Object Windows.Forms.Label
    $l.Text=$text; $l.SetBounds($x,$y,$w,$h)
    $form.Controls.Add($l)
    return $l
}
function Set-BenchStatus([string]$state) {
    $display=Get-BenchStatus $state
    $statusValue.Text=$display.value
    $statusValue.ForeColor=[Drawing.Color]::FromName($display.color)
}
function Write-Control($name,$value) {
    if (-not $script:session) { return }
    $path=$script:session+'.control.json'
    $control=@{ stop=$false; pause=$false; continue=$false }
    if (Test-Path $path) { $control=Get-Content $path -Raw | ConvertFrom-Json }
    $control.$name=$value
    [IO.File]::WriteAllText($path,($control | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
}
function Write-WindowError($err) {
    # The refresh tick must never raise the modal .NET dialog: it freezes the display until
    # someone clicks it, which on an unattended run is never. Show it and keep a record instead.
    # The engine is a separate process and is unaffected either way.
    $key=$err.Exception.Message+'  '+($err.ScriptStackTrace -replace "`r?`n",' <- ')
    try { $errorLabel.Text='Window refresh error (measurement unaffected): '+$err.Exception.Message } catch { }
    if ($key -eq $script:lastWindowError) { return }   # a repeating error is written once, not every second
    $script:lastWindowError=$key
    try {
        $path=if ($script:session) { $script:session+'.window-errors.txt' } else { Join-Path ([IO.Path]::GetTempPath()) 'headroom-bench-window-errors.txt' }
        [IO.File]::AppendAllText($path,(Get-Date).ToString('s')+'  '+$key+"`r`n",(New-Object Text.UTF8Encoding($false)))
    } catch { }
}
function Update-Row($item) {
    $run=$item.Tag
    $custom=-not $script:original.ContainsKey($run.id)
    $edited= $custom -or ($script:original[$run.id] -ne ($run | ConvertTo-Json -Depth 20 -Compress))
    $selectionChanged= $custom -or ($item.Checked -ne [bool]$script:catalog.runs[$script:originalIndex[$run.id]].preselected)
    $moved= (-not $custom) -and ($item.Index -ne $script:originalIndex[$run.id])
    $markers=@()
    if ($custom) { $markers+='CUSTOM' }
    elseif ($edited) { $markers+='EDITED' }
    if ($selectionChanged -and -not $custom) { $markers+='SELECTED' }
    if ($moved) { $markers+='MOVED' }
    $item.Text=$run.name
    $item.SubItems[1].Text=[string]$run.minutes+' min'
    $item.SubItems[2].Text=[string]$run.priority
    $item.SubItems[3].Text=$run.why
    $item.BackColor=if ($markers.Count) { [Drawing.Color]::LightYellow } else { [Drawing.Color]::White }
    $item.SubItems[4].Text=($markers -join ', ')
}
function Refresh-Differences { foreach ($row in $list.Items) { Update-Row $row } }
function Add-Run($run,$checked) {
    $item=New-Object Windows.Forms.ListViewItem($run.name)
    [void]$item.SubItems.Add(''); [void]$item.SubItems.Add(''); [void]$item.SubItems.Add(''); [void]$item.SubItems.Add('')
    $item.Tag=$run; $item.Checked=$checked
    [void]$list.Items.Add($item)
    Update-Row $item
}
function Build-Plan {
    $selected=@()
    $changes=@()
    foreach ($item in $list.Items) {
        if (-not $item.Checked) { continue }
        $selected+= $item.Tag
        if ($script:original.ContainsKey($item.Tag.id)) {
            if ($script:original[$item.Tag.id] -ne ($item.Tag | ConvertTo-Json -Depth 20 -Compress)) {
                $changes+=@{ run=$item.Tag.id; kind='edited'; requested=($script:original[$item.Tag.id] | ConvertFrom-Json); actual=$item.Tag }
            }
        } else { $changes+=@{ run=$item.Tag.id; kind='custom'; actual=$item.Tag } }
    }
    $originalSelection=@($script:catalog.runs | Where-Object preselected | ForEach-Object id)
    $actualSelection=@($selected | ForEach-Object id)
    if (($originalSelection -join ',') -ne ($actualSelection -join ',')) {
        $changes+=@{ kind='selection-or-order'; requested=$originalSelection; actual=$actualSelection }
    }
    return @{ schemaVersion=1; title=$script:catalog.title; volumeLabel=$script:catalog.volumeLabel; card=$script:catalog.card; revert=$script:catalog.revert; afterRevertHuman=$script:catalog.afterRevertHuman; runs=$selected; customizations=$changes }
}
function Validate-Queue($planPath) {
    $result=& (Join-Path $PSScriptRoot 'Test-Plan.ps1') -PlanPath $planPath 2>&1
    if ($LASTEXITCODE -ne 0) { [Windows.Forms.MessageBox]::Show(($result -join "`n"),'Invalid plan') | Out-Null; return $false }
    return $true
}
function Read-VoltageTail([string]$path) {
    if (-not $path -or -not (Test-Path $path)) { return '' }
    try { return [string](Get-HwinfoCoreVoltage $path) } catch { return '' }
}
function Edit-Selected {
    if ($list.SelectedItems.Count -ne 1) { return }
    $item=$list.SelectedItems[0]
    $dialog=New-Object Windows.Forms.Form
    $dialog.Text='Edit run JSON'; $dialog.Width=760; $dialog.Height=600; $dialog.StartPosition='CenterParent'
    $box=New-Object Windows.Forms.TextBox
    $box.Multiline=$true; $box.ScrollBars='Both'; $box.Font=New-Object Drawing.Font('Consolas',9)
    $box.SetBounds(10,10,720,500); $box.Text=($item.Tag | ConvertTo-Json -Depth 20)
    $dialog.Controls.Add($box)
    $ok=New-Object Windows.Forms.Button; $ok.Text='Save'; $ok.SetBounds(630,520,95,27)
    $ok.Add_Click({
        try {
            $edited=$box.Text | ConvertFrom-Json
            if ($edited.id -ne $item.Tag.id) { throw 'Run id cannot change.' }
            $item.Tag=$edited; Refresh-Differences
            $dialog.DialogResult=[Windows.Forms.DialogResult]::OK; $dialog.Close()
        } catch { [Windows.Forms.MessageBox]::Show($_.Exception.Message,'Edit error') | Out-Null }
    })
    $dialog.Controls.Add($ok); [void]$dialog.ShowDialog($form)
}
function Add-Custom {
    $dialog=New-Object Windows.Forms.Form
    $dialog.Text='Custom sweep'; $dialog.Width=440; $dialog.Height=550; $dialog.StartPosition='CenterParent'
    $names=@('Label','Workload','Minimum MHz','Maximum MHz','Points','Direction','Iterations','Profile slot','Loaded core min','Loaded core max','Memory min','Memory max')
    $defaults=@('custom-gemm','gemm','1200','1590','10','ascending','120','1','1700','1820','9450','9550')
    $boxes=@()
    for($i=0;$i -lt $names.Count;$i++) {
        $l=New-Object Windows.Forms.Label; $l.Text=$names[$i]; $l.SetBounds(12,(15+38*$i),130,24); $dialog.Controls.Add($l)
        $b=New-Object Windows.Forms.TextBox; $b.Text=$defaults[$i]; $b.SetBounds(150,(12+38*$i),250,24); $dialog.Controls.Add($b); $boxes+=$b
    }
    $ok=New-Object Windows.Forms.Button; $ok.Text='Add'; $ok.SetBounds(310,470,90,28)
    $ok.Add_Click({
        try {
            $id='custom-'+[guid]::NewGuid().ToString('N').Substring(0,8)
            $label=$boxes[0].Text
            if ($label -notmatch '^[a-z0-9][a-z0-9-]{2,63}$') { throw 'Use a lowercase label with hyphens.' }
            $run=@{ id=$id; name='Custom: '+$label; why='Operator custom sweep'; minutes=15; priority=3; preselected=$false; locked=$false; requires=@('preflight'); steps=@(
                @{ id='profile'; type='apply-profile'; name='Apply profile'; estimatedMinutes=0.2; slot=[int]$boxes[7].Text },
                @{ id='witness'; type='witness'; name='Verify selected profile under load'; estimatedMinutes=0.7; workload='gemm'; iterations=400; coreMin=[int]$boxes[8].Text; coreMax=[int]$boxes[9].Text; memoryMin=[int]$boxes[10].Text; memoryMax=[int]$boxes[11].Text },
                @{ id='log-start'; type='hwinfo-start'; name='Start HWiNFO log'; estimatedMinutes=0.3; path='kit:/results/hwinfo-'+$label+'.csv' },
                @{ id='sweep'; type='sweep'; name='Custom sweep'; estimatedMinutes=15; label=$label; workload=$boxes[1].Text; minMhz=[int]$boxes[2].Text; maxMhz=[int]$boxes[3].Text; points=[int]$boxes[4].Text; direction=$boxes[5].Text; iterations=[int]$boxes[6].Text; output='kit:/results/'+$label; settings='CUSTOM profile P'+$boxes[7].Text+'; operator-selected grid and workload' },
                @{ id='log-stop'; type='hwinfo-stop'; name='Stop HWiNFO log'; estimatedMinutes=0.2 }) }
            Add-Run $run $true
            $newItem=$list.Items[$list.Items.Count-1]
            $cleanupIndex=-1
            foreach ($row in $list.Items) { if ($row.Tag.id -eq 'cleanup') { $cleanupIndex=$row.Index; break } }
            if ($cleanupIndex -ge 0) { $list.Items.Remove($newItem); $list.Items.Insert($cleanupIndex,$newItem) }
            Refresh-Differences
            $dialog.DialogResult=[Windows.Forms.DialogResult]::OK; $dialog.Close()
        } catch { [Windows.Forms.MessageBox]::Show($_.Exception.Message,'Custom sweep error') | Out-Null }
    })
    $dialog.Controls.Add($ok); [void]$dialog.ShowDialog($form)
}

$form=New-Object Windows.Forms.Form
$form.Text='Headroom Bench'; $form.Width=1120; $form.Height=760; $form.StartPosition='CenterScreen'
if ($Hidden) { $form.StartPosition='Manual'; $form.Location=New-Object Drawing.Point(-32000,-32000); $form.ShowInTaskbar=$false; $form.Opacity=0 }
$form.Font=New-Object Drawing.Font('Segoe UI',9)
[void](Label 'Requested runs (yellow = changed from catalog). Drag rows to reorder.' 12 12 730 22)
$list=New-Object Windows.Forms.ListView
$list.CheckBoxes=$true; $list.FullRowSelect=$true; $list.View='Details'; $list.AllowDrop=$true
$list.SetBounds(12,38,1078,244)
foreach ($c in @(@('Run',290),@('Time',70),@('Priority',65),@('Why',540),@('Change',100))) { [void]$list.Columns.Add($c[0],[int]$c[1]) }
$form.Controls.Add($list)
foreach ($run in $script:catalog.runs) { Add-Run $run ([bool]$run.preselected) }
$list.Add_ItemChecked({ Refresh-Differences })
Write-Host ("CATALOG LOADED: {0} runs, {1} preselected." -f $list.Items.Count,@($list.Items | Where-Object Checked).Count)
$list.Add_ItemDrag({ [void]$list.DoDragDrop($list.SelectedItems[0],[Windows.Forms.DragDropEffects]::Move) })
$list.Add_DragEnter({ param($sender,$e) $e.Effect=[Windows.Forms.DragDropEffects]::Move })
$list.Add_DragDrop({ param($sender,$e)
    $source=$e.Data.GetData([Windows.Forms.ListViewItem])
    if (-not $source) { return }
    $point=$list.PointToClient((New-Object Drawing.Point($e.X,$e.Y)))
    $target=$list.GetItemAt($point.X,$point.Y)
    if (-not $target -or $source -eq $target) { return }
    $from=$source.Index; $to=$target.Index
    $list.Items.Remove($source); $list.Items.Insert($to,$source)
    $order=@($list.Items | ForEach-Object { $_.Tag.id })
    $core=@('stock-1','edit1-2','edit2-3','stock-4')
    $positions=@($core | ForEach-Object { [array]::IndexOf($order,$_) })
    if (-not ($order[0] -eq 'preflight' -and $order[$order.Count-1] -eq 'cleanup' -and $positions[1] -eq ($positions[0]+1) -and $positions[2] -eq ($positions[1]+1) -and $positions[3] -eq ($positions[2]+1))) {
        $list.Items.Remove($source); $list.Items.Insert($from,$source)
    }
    Refresh-Differences
})
$list.Add_DoubleClick({ Edit-Selected })
[void](Button 'Edit selected' 12 291 120 { Edit-Selected })
[void](Button 'Add custom sweep' 140 291 150 { Add-Custom })
$start=Button 'Start' 300 291 90 {
    if ($script:engine -and -not $script:engine.HasExited) { return }
    $root=Join-Path $script:kit 'results'
    if (-not (Test-Path $root)) { New-Item -ItemType Directory -Path $root -Force | Out-Null }
    $resume=$false
    if ($script:resumeSession) {
        $session=$script:resumeSession
        $stamp=[regex]::Match([IO.Path]::GetFileName($session),'bench-session-(.*)[.]json').Groups[1].Value
        $planPath=Join-Path $root ('bench-plan-'+$stamp+'.json')
        $plan=Get-Content $planPath -Raw | ConvertFrom-Json
        $resume=$true
    } else {
        $plan=Build-Plan
        $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
        $planPath=Join-Path $root ('bench-plan-'+$stamp+'.json')
        $session=Join-Path $root ('bench-session-'+$stamp+'.json')
        if (Test-Path $planPath) { [Windows.Forms.MessageBox]::Show('Plan name collision. Wait one second and try again.') | Out-Null; return }
        $queuePath=Join-Path $root ('bench-queue-'+$stamp+'.json')
        [IO.File]::WriteAllText($queuePath,(@{ runs=$plan.runs } | ConvertTo-Json -Depth 30),(New-Object Text.UTF8Encoding($false)))
        & (Join-Path $PSScriptRoot 'New-Plan.ps1') -CatalogPath $CatalogPath -QueuePath $queuePath -OutputPath $planPath | Out-Null
        $plan=Get-Content $planPath -Raw | ConvertFrom-Json
    }
    if (-not (Validate-Queue $planPath)) { return }
    $script:activePlan=$plan
    $script:session=$session
    $script:outputPath=$session+'.output.txt'
    $script:errorPath=$session+'.error.txt'
    $script:lastOutput=''
    $control=@{ stop=$false; pause=$false; continue=$false }
    [IO.File]::WriteAllText(($session+'.control.json'),($control | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
    $engine=Join-Path $PSScriptRoot 'Run-Plan.ps1'
    $args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$engine,'-PlanPath',$planPath,'-SessionPath',$session,'-VolumeLabel',$plan.volumeLabel,'-ParentPid',[string]$PID)
    if ($resume) { $args+='-Resume' }
    if ($DryRun) { $args+=@('-DryRun','-MockPath',$MockPath) }
    $script:engine=Start-Process -FilePath 'powershell.exe' -ArgumentList $args -PassThru -WindowStyle Hidden -RedirectStandardOutput $script:outputPath -RedirectStandardError $script:errorPath
    $null=$script:engine.Handle   # PS 5.1: keep ExitCode readable after exit
    $script:resumeSession=''; $script:stepBase=''
    Set-BenchStatus 'Running'; $start.Enabled=$false
}
$pause=Button 'Pause after step' 398 291 130 { Write-Control 'pause' $true; Set-BenchStatus 'Pause requested' }
$stop=Button 'Stop' 536 291 80 { $script:stopAsked=$true; Write-Control 'stop' $true; Set-BenchStatus 'Stop requested' }
$continue=Button 'Continue' 624 291 90 { Write-Control 'continue' $true; Set-BenchStatus 'Running' }
$statusCaption=Label 'Status:' 12 330 55 23
$statusValue=Label 'Ready' 70 330 500 23
$errorLabel=Label '' 12 353 1070 34
$errorLabel.ForeColor=[Drawing.Color]::Red
$stepLabel=Label 'Step 0 of 0' 12 392 740 24
$stepLabel.AutoEllipsis=$true   # one line: a wrapped second line is clipped by the label height
$estimate=Label 'Finish estimate appears after Start.' 760 392 330 24
$estimate.TextAlign=[Drawing.ContentAlignment]::TopRight
$progress=New-Object Windows.Forms.ProgressBar; $progress.SetBounds(12,421,1078,18); $form.Controls.Add($progress)
$telemetry=Label (Format-BenchReadings '') 12 450 1070 24
$logging=Label 'HWiNFO logging: not yet verified' 12 479 1070 24
$finished=New-Object Windows.Forms.TextBox; $finished.Multiline=$true; $finished.ReadOnly=$true; $finished.ScrollBars='Vertical'; $finished.SetBounds(12,508,1078,78); $form.Controls.Add($finished)
$output=New-Object Windows.Forms.TextBox; $output.Multiline=$true; $output.ReadOnly=$true; $output.ScrollBars='Vertical'; $output.Font=New-Object Drawing.Font('Consolas',8)
$output.SetBounds(12,592,1078,112); $form.Controls.Add($output)
$timer=New-Object Windows.Forms.Timer; $timer.Interval=1000
$timer.Add_Tick({ try {
    if ($script:engine -and -not $script:engine.HasExited -and -not $DryRun) {
        # PS 5.1 under Stop turns ANY nvidia-smi stderr line into a terminating error, even with
        # 2>$null. Unguarded here it raised a modal .NET dialog ("...set to Stop: Access is denied")
        # at the end of the 2026-09-23 21:26 live run and froze the window. A failed read keeps the last line.
        try {
            $smi=@(& nvidia-smi '--query-gpu=clocks.sm,clocks.mem,power.draw,temperature.gpu,utilization.gpu' '--format=csv,noheader,nounits' 2>$null)
            if ($LASTEXITCODE -eq 0 -and $smi.Count -gt 0) { $script:lastSmiLine=[string]$smi[0] }
        } catch { }
    }
    if ($script:outputPath -and (Test-Path $script:outputPath)) {
        $lines=@(Get-Content $script:outputPath -Tail 100 -ErrorAction SilentlyContinue)
        if ($script:errorPath -and (Test-Path $script:errorPath)) { $lines+=@(Get-Content $script:errorPath -Tail 20 -ErrorAction SilentlyContinue) }
        $joined=$lines -join "`r`n"
        if ($joined -ne $script:lastOutput) {
            $output.Text=$joined; $output.SelectionStart=$output.TextLength; $output.ScrollToCaret(); $script:lastOutput=$joined
        }
    }
    # The engine saves the record by writing a .tmp and moving it over the old file; a check that
    # lands mid-move gets "Access is denied" (window-errors.txt, 3070 Ti, 2026-09-24 16:20). The
    # next tick reads it fine, so a failed check just skips this tick.
    if ($script:session -and (Test-Path $script:session -ErrorAction SilentlyContinue)) {
        try {
            $record=Get-Content $script:session -Raw | ConvertFrom-Json
            $all=if ($record.progress) { [int]$record.progress.total } else { 1 }
            $done=if ($record.progress) { [int]$record.progress.index-1 } else { 0 }
            $progress.Maximum=[math]::Max(1,$all); $progress.Value=[math]::Min($done,$progress.Maximum)
            # progress.index is the step in hand, so index-1 never counts the last step: a PASS
            # session ended at 22 of 23 (3070 Ti shakedown, 2026-09-23). Full once it has passed.
            if ($record.status -eq 'PASS' -and $record.finalState) { $progress.Value=$progress.Maximum }
            $attemptStart=if ($record.attemptStart) { [datetime]$record.attemptStart } else { [datetime]$record.start }
            $current=@($record.steps | Where-Object { $_.verdict -eq 'RUNNING' -and [datetime]$_.start -ge $attemptStart } | Select-Object -Last 1)
            if ($current.Count -gt 0) { $script:stepBase=('Step {0} of {1}: {2}' -f ($done+1),$all,$current[0].name) }
            if ($script:stepBase) { $stepLabel.Text=$script:stepBase }
            if ($script:activePlan -and $record.status -eq 'RUNNING') {
                $prediction=Get-BenchEstimate $script:activePlan $record (Get-Date)
                $stepText=if ($prediction.stepOverrun) { 'step running past its estimate' } elseif ($prediction.stepFinish) { 'Step finish: '+$prediction.stepFinish.ToString('t') } else { 'Next step pending' }
                $estimate.Text=$stepText+'   Session finish: '+$prediction.sessionFinish.ToString('t')
            } elseif ($record.finalState) { $estimate.Text='Measurement work complete.' }
            $finished.Text=(@($record.steps | Where-Object { $_.verdict -ne 'RUNNING' } | ForEach-Object {
                $duration=[math]::Round((([datetime]$_.end)-([datetime]$_.start)).TotalSeconds,1)
                '{0} {1} ({2}s) {3}' -f $_.verdict,$_.key,$duration,($_.witness | ConvertTo-Json -Compress -Depth 4)
            }) -join "`r`n")
            $active=@($record.steps | Where-Object { $_.type -eq 'hwinfo-start' -and $_.verdict -eq 'PASS' } | Select-Object -Last 1)
            $lastStop=@($record.steps | Where-Object { $_.type -eq 'hwinfo-stop' -and $_.verdict -eq 'PASS' } | Select-Object -Last 1)
            $isLogging=($active.Count -gt 0 -and ($lastStop.Count -eq 0 -or [datetime]$active[0].end -gt [datetime]$lastStop[0].end))
            if ($record.finalState) {
                $isLogging=($record.finalState.logging.status -eq 'running')
                $logging.Text=if ($record.finalState.logging.stoppedVerified) { 'HWiNFO logging: stopped (verified)' } else { 'HWiNFO logging: '+[string]$record.finalState.logging.status+' (unverified)' }
                $logging.ForeColor=if ($record.finalState.logging.stoppedVerified) { [Drawing.Color]::DarkGreen } else { [Drawing.Color]::Red }
            } else { $logging.Text=if ($isLogging) { 'HWiNFO logging: '+$active[0].witness.path+' ('+$active[0].witness.mode+')' } else { 'HWiNFO logging: stopped; final check pending' } }
            $voltage=if ($isLogging -and $active.Count -gt 0) { Read-VoltageTail $active[0].witness.path } else { '' }
            $telemetry.Text=Format-BenchReadings $script:lastSmiLine $voltage $isLogging
            if ($record.live) {
                $achieved=if ($record.live.achievedMhz) { [string]$record.live.achievedMhz+' MHz' } else { 'pending' }
                $stepLabel.Text+=('   {0} point {1}/{2}: target {3} MHz, achieved {4}' -f $record.live.workload,$record.live.point,$record.live.of,$record.live.targetMhz,$achieved)
            }
            if ($script:engine -and $script:engine.HasExited) {
                $start.Enabled=$false
                $result=if ($record.status -eq 'PASS') { 'PASS' } else { 'FAIL' }
                Set-BenchStatus $result
                $errorLabel.Text=if ($result -eq 'FAIL') { [string]$record.error } else { '' }
                $issues=@()
                if (-not $record.finalState -or -not $record.finalState.logging.stoppedVerified) { $issues+='HWiNFO stop unverified: '+[string]$record.finalState.logging.status }
                if (-not $record.finalState -or -not $record.finalState.processes.verified) { $issues+='bench processes: '+[string]$record.finalState.processes.detail }
                if (-not $record.finalState -or -not $record.finalState.clocks.verified) { $issues+='clock reset unverified' }
                if ($issues.Count -gt 0) {
                    $logging.Text=$issues -join '; '
                    $logging.ForeColor=[Drawing.Color]::Red
                } else {
                    $processText=if (@($record.finalState.processes.killedPids).Count -gt 0) { 'bench survivors killed: '+(@($record.finalState.processes.killedPids) -join ',') } else { 'bench processes stopped (verified)' }
                    $logging.Text='HWiNFO logging: stopped (verified); clocks reset; '+$processText
                    $logging.ForeColor=[Drawing.Color]::DarkGreen
                }
                $telemetry.Text=Format-BenchReadings $script:lastSmiLine
            } elseif ($record.operatorState -eq 'Paused' -and $statusValue.Text -ne 'Stop requested' -and $statusValue.Text -ne 'Stopping and reverting') { Set-BenchStatus 'Paused' }
            elseif ($record.operatorState -eq 'Stopping and reverting') { Set-BenchStatus 'Stopping and reverting' }
            # A resumed session inherits 'Stopping and reverting' from the attempt that failed. The
            # window could read it before the engine reset it to Running, and nothing set it back:
            # Session D's resume showed it for hours while collecting normally (2026-09-24).
            elseif ($record.operatorState -eq 'Running' -and -not $script:stopAsked -and $statusValue.Text -eq 'Stopping and reverting') { Set-BenchStatus 'Running' }
            if ($record.status -eq 'RUNNING') {
                $errorLabel.Text=[string]$record.operatorMessage
                if ($record.operatorState -eq 'Running' -and $statusValue.Text -eq 'Paused') { Set-BenchStatus 'Running' }
            }
        } catch { }
    }
} catch { Write-WindowError $_ } })
$timer.Start()
$form.Add_FormClosing({
    if ($script:engine -and -not $script:engine.HasExited) {
        $script:stopAsked=$true
        Write-Control 'stop' $true
        Set-BenchStatus 'Stopping and reverting'
        $_.Cancel=$true
    }
})
if ($AutoCloseSeconds -gt 0) {
    $auto=New-Object Windows.Forms.Timer; $auto.Interval=$AutoCloseSeconds*1000
    $auto.Add_Tick({ $auto.Stop(); $form.Close() }); $auto.Start()
}
function Test-ResumableHere($file) {
    # Offer to resume only a session whose plan was written for THIS card's run list. One USB
    # serves several machines: on 2026-09-23 the 3070 Ti was offered the 5060 Ti's failed
    # session, a Yes loaded the 5060 Ti plan, and the engine stopped at "Wrong GPU".
    try {
        $stamp=[regex]::Match($file.Name,'bench-session-(.*)[.]json').Groups[1].Value
        $planPath=Join-Path $file.DirectoryName ('bench-plan-'+$stamp+'.json')
        if (-not (Test-Path $planPath)) { return $false }
        # Same card AND the same run list. By card alone, Session D2 (2026-09-25) would have been
        # offered Session D's failed 08:19 attempt, and a Yes would have rerun the old plan.
        $sessionPlan=Get-Content $planPath -Raw | ConvertFrom-Json
        return ($sessionPlan.card.name -eq $script:catalog.card.name -and $sessionPlan.title -eq $script:catalog.title)
    } catch { return $false }
}
$resultDir=Join-Path $script:kit 'results'
if ((Test-Path $resultDir) -and -not $Hidden) {
    # Only the session file itself: its .state.json and .control.json siblings also match the
    # wildcard and are often written in the same second (found live, 2026-09-23).
    $pending=@(Get-ChildItem $resultDir -Filter 'bench-session-*.json' -File |
        Where-Object { $_.Name -match '^bench-session-\d{8}-\d{6}\.json$' } |
        Sort-Object LastWriteTime -Descending |
        Where-Object { try { (Get-Content $_.FullName -Raw | ConvertFrom-Json).status -ne 'PASS' } catch { $false } } |
        Where-Object { Test-ResumableHere $_ } |
        Select-Object -First 1)
    if ($pending.Count -gt 0) {
        $choice=[Windows.Forms.MessageBox]::Show(('Resume interrupted session '+$pending[0].Name+'?'),'Headroom Bench',[Windows.Forms.MessageBoxButtons]::YesNo)
        if ($choice -eq [Windows.Forms.DialogResult]::Yes) { $script:resumeSession=$pending[0].FullName; Set-BenchStatus 'Ready' }
    }
}
[void]$form.ShowDialog()
