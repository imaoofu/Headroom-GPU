param(
    [Parameter(Mandatory=$true)][string]$CatalogPath,
    [Parameter(Mandatory=$true)][string]$QueuePath,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference='Stop'
if (-not [IO.Path]::IsPathRooted($CatalogPath) -or -not [IO.Path]::IsPathRooted($QueuePath) -or -not [IO.Path]::IsPathRooted($OutputPath)) { throw 'All paths must be absolute.' }
if (Test-Path $OutputPath) { throw "Refusing to overwrite plan: $OutputPath" }
$catalog=Get-Content $CatalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
$queue=Get-Content $QueuePath -Raw -Encoding UTF8 | ConvertFrom-Json
$original=@{}
foreach ($run in $catalog.runs) { $original[$run.id]=$run }
$changes=@()
foreach ($run in $queue.runs) {
    if (-not $original.ContainsKey($run.id)) { $changes+=@{ kind='custom'; run=$run.id; actual=$run }; continue }
    $before=$original[$run.id] | ConvertTo-Json -Depth 30 -Compress
    $after=$run | ConvertTo-Json -Depth 30 -Compress
    if ($before -ne $after) { $changes+=@{ kind='edited'; run=$run.id; requested=$original[$run.id]; actual=$run } }
}
$requested=@($catalog.runs | Where-Object { $_.preselected } | ForEach-Object id)
$selected=@($queue.runs | ForEach-Object id)
if (($requested -join ',') -ne ($selected -join ',')) { $changes+=@{ kind='selection-or-order'; requested=$requested; actual=$selected } }
$afterRevertHuman=$null
if (@($queue.runs | Where-Object { $_.finalRun }).Count -gt 0) { $afterRevertHuman=$catalog.afterRevertHuman }
$plan=@{ schemaVersion=1; title=$catalog.title; volumeLabel=$catalog.volumeLabel; card=$catalog.card; revert=$catalog.revert; afterRevertHuman=$afterRevertHuman; runs=@($queue.runs); customizations=$changes }
$plan.minimizeKnownRenderers=@($catalog.minimizeKnownRenderers | Where-Object { $null -ne $_ })
$json=$plan | ConvertTo-Json -Depth 40
[IO.File]::WriteAllText($OutputPath,$json,(New-Object Text.UTF8Encoding($false)))
Write-Host "PLAN WRITTEN: $($changes.Count) customization(s)."
