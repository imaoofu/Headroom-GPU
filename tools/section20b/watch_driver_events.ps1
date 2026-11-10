<#
.SYNOPSIS
    Section 20b: watch the System event log for display-driver events while a session runs, and
    signal them at once (GPT Job 75, R4). Observes only; makes no GPU query.

.DESCRIPTION
    Subscribes to every new System-log record and applies, in the callback, exactly the predicate the
    session runner and controller query with: EventID 4101 (display driver stopped responding and
    recovered) or a provider name -like '*nvlddmkm*', case-insensitive. An XPath provider filter is
    exact and case-sensitive, so it caught less than that query (GPT Job 76, R4). On the
    first match it writes -FlagFile (the event's id and time). Every 2 s it rewrites -HeartbeatFile, so
    the controller can tell a live watcher from a dead one. It stops when -StopFile appears. The
    subscription is event-driven: between heartbeats it sleeps, so it adds the same negligible host
    work to every arm.

    If the subscription reports an error, or the flag cannot be written, the watcher stops writing
    heartbeats and exits non-zero, so the controller sees a dead watcher rather than a healthy one.

    -LogName, -MatchId and -ProviderLike exist only so a test can watch another log; a session uses
    the defaults.
#>
param(
    [Parameter(Mandatory = $true)][string]$FlagFile,
    [Parameter(Mandatory = $true)][string]$HeartbeatFile,
    [Parameter(Mandatory = $true)][string]$StopFile,
    [string]$LogName = "System",
    [int]$MatchId = 4101,
    [string]$ProviderLike = "*nvlddmkm*"
)
$ErrorActionPreference = "Stop"
$global:WatcherFailure = $null
$query = New-Object System.Diagnostics.Eventing.Reader.EventLogQuery($LogName, [System.Diagnostics.Eventing.Reader.PathType]::LogName, "*")
$watcher = New-Object System.Diagnostics.Eventing.Reader.EventLogWatcher($query)
$action = {
    try {
        $d = $Event.MessageData
        if ($null -ne $Event.SourceEventArgs.EventException) {
            $global:WatcherFailure = "event subscription error: " + $Event.SourceEventArgs.EventException.Message
            [IO.File]::WriteAllText($d.Flag, $global:WatcherFailure)
            return
        }
        $r = $Event.SourceEventArgs.EventRecord
        if ($null -ne $r -and ($r.Id -eq $d.Id -or $r.ProviderName -like $d.Provider)) {
            $text = "{0} {1} {2}" -f $r.Id, $r.ProviderName, $r.TimeCreated.ToString("o")
            [IO.File]::WriteAllText($d.Flag, $text)
        }
    } catch {
        $global:WatcherFailure = "event action failed: " + $_.Exception.Message
    }
}
$data = [pscustomobject]@{ Flag = $FlagFile; Id = $MatchId; Provider = $ProviderLike }
$subscription = Register-ObjectEvent -InputObject $watcher -EventName EventRecordWritten -Action $action -MessageData $data
try {
    $watcher.Enabled = $true
    while (-not (Test-Path -LiteralPath $StopFile)) {
        # No heartbeat once the action has failed or its job has: the controller then sees a dead watcher.
        if ($global:WatcherFailure) { throw $global:WatcherFailure }
        if ($subscription.State -eq "Failed") { throw "the event action job failed" }
        [IO.File]::WriteAllText($HeartbeatFile, (Get-Date).ToString("o"))
        Start-Sleep -Seconds 2
    }
} finally {
    $watcher.Enabled = $false
    Unregister-Event -SourceIdentifier $subscription.Name -ErrorAction SilentlyContinue
    $watcher.Dispose()
}
