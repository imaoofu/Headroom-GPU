# pmon -s u columns: gpu pid type sm mem enc dec jpg ofa command.
# Sum SM across processes within a sample. A repeated PID begins the next sample.
function Measure-PmonQuiet([string[]]$lines) {
    $samples=@{}
    $seenPids=@{}
    $index=-1
    $encoder=0
    $decoder=0
    foreach ($line in $lines) {
        if ($line -match '^\s*#|^\s*$') { continue }
        $cols=@($line.Trim() -split '\s+')
        if ($cols.Count -lt 7) { continue }
        $pidValue=$cols[1]
        if ($seenPids.ContainsKey($pidValue)) { $seenPids=@{} }
        if ($seenPids.Count -eq 0) { $index++; $samples[$index]=0 }
        $seenPids[$pidValue]=$true
        $sm=0
        if ([int]::TryParse($cols[3],[ref]$sm)) { $samples[$index]+=$sm }
        $v=0
        if ([int]::TryParse($cols[5],[ref]$v)) { $encoder=[math]::Max($encoder,$v) }
        if ([int]::TryParse($cols[6],[ref]$v)) { $decoder=[math]::Max($decoder,$v) }
    }
    if ($samples.Count -eq 0) { throw 'pmon returned no usable samples.' }
    $peak=($samples.Values | Measure-Object -Maximum).Maximum
    return @{ maxSm=$peak; maxEncoder=$encoder; maxDecoder=$decoder; samples=$samples.Count }
}
