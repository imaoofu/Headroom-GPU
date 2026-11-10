# Replace a file's contents so a reader never sees a half-written file, and a reader holding it
# open never fails the writer.
#
# WHY. Session D stopped at step 27 on 2026-09-24 with "Cannot create a file when that file already
# exists", after about ten hours and thousands of saves. Save-Record wrote <session>.tmp and then
# ran Move-Item -Force over the session file. On Windows that deletes the target and then renames,
# and the window reads the same file every tick: a read between the two leaves the delete pending,
# so the rename finds the name still taken. It is a timing race, so it cost nothing for ten hours
# and then ended the session.
#
# HOW. The target is swapped with [IO.File]::Replace (one ReplaceFile call), or moved if it does
# not exist yet. Any IOException, which is what a reader holding the file open produces, is
# retried every 100 ms for up to 10 s, and the .tmp file stays in place until the swap succeeds.
# Only after that does it throw.
function Write-FileAtomic([string]$Path, [string]$Text, [int]$TimeoutMs = 10000) {
    $tmp = $Path + '.tmp'
    [IO.File]::WriteAllText($tmp, $Text, (New-Object Text.UTF8Encoding($false)))
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    $attempts = 0
    while ($true) {
        $attempts++
        try {
            if ([IO.File]::Exists($Path)) { [IO.File]::Replace($tmp, $Path, [NullString]::Value) }
            else { [IO.File]::Move($tmp, $Path) }
            return $attempts
        } catch {
            # A .NET call's exception can arrive wrapped; look at the innermost one.
            $inner = $_.Exception
            while ($inner.InnerException) { $inner = $inner.InnerException }
            $transient = ($inner -is [System.IO.IOException]) -or ($inner -is [System.UnauthorizedAccessException])
            if (-not $transient -or [DateTime]::UtcNow -ge $deadline) {
                throw "Could not replace $Path after $attempts attempts: $($inner.Message)"
            }
            Start-Sleep -Milliseconds 100
        }
    }
}
