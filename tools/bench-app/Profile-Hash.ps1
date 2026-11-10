# Hash only the named sections of an Afterburner profile store.
#
# Added 2026-09-24. The whole-file hash stopped Session D on the 3070 Ti because Afterburner had
# added [Defaults] and [Settings] sections to the store by itself (CaptureDefaults), while
# Profile1-3 were unchanged key for key. The runs apply only named slots by command line, so the
# slots are what must be pinned; a section Afterburner rewrites on its own must not stop a run.
#
# Canonical form, so line endings, key order and other sections cannot change the result: for each
# section in the order given, "[Name]" then every "key=value" of that section sorted by key, one
# per line joined with LF, hashed as UTF-8. A missing section is an error, never a skipped one.
function Get-ProfileSectionHash([string]$path, [string[]]$sections) {
    if (-not $sections -or $sections.Count -eq 0) { throw 'Name at least one section to hash.' }
    $found = @{}
    $current = $null
    foreach ($raw in [IO.File]::ReadAllLines($path)) {
        $line = $raw.Trim()
        if ($line -match '^\[(.+)\]$') { $current = $Matches[1]; if (-not $found.ContainsKey($current)) { $found[$current] = @{} }; continue }
        if ($null -eq $current -or $line -eq '' -or $line.StartsWith(';')) { continue }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { continue }
        $found[$current][$line.Substring(0, $eq).Trim()] = $line.Substring($eq + 1).Trim()
    }
    $text = New-Object Text.StringBuilder
    foreach ($name in $sections) {
        if (-not $found.ContainsKey($name)) { throw "Profile store has no [$name] section." }
        [void]$text.Append("[$name]`n")
        # Ordinal, not Sort-Object: culture-aware ordering could differ between the shop PC and CI.
        $keys = [string[]]@($found[$name].Keys)
        [Array]::Sort($keys, [StringComparer]::Ordinal)
        foreach ($key in $keys) { [void]$text.Append("$key=$($found[$name][$key])`n") }
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text.ToString())))).Replace('-', '') }
    finally { $sha.Dispose() }
}
