# Same registered stock-return statistic as analysis/score_session_d.py.
function Measure-StockDrift([string]$firstDir,[string]$lastDir,[string[]]$workloads) {
    $per=@{}
    foreach ($name in $workloads) {
        $pattern='*-' + $name + '_sweep.csv'
        $a=@(Get-ChildItem $firstDir -Filter $pattern)
        $b=@(Get-ChildItem $lastDir -Filter $pattern)
        if ($a.Count -ne 1 -or $b.Count -ne 1) { throw "Missing stock return CSV for $name." }
        $rowsA=@(Import-Csv $a[0].FullName); $rowsB=@(Import-Csv $b[0].FullName)
        # The point count comes from the sweep, not a constant: Session D/E suites have 13 targets,
        # Session E2's fixed list has 12 (2026-09-27, when a hard-coded 13 failed E2's gate after
        # all three suites had collected). Both sides must match target for target.
        if ($rowsA.Count -lt 10 -or $rowsB.Count -ne $rowsA.Count) { throw "Stock return $name needs the same number of points (at least 10) on each side; found $($rowsA.Count) and $($rowsB.Count)." }
        $lookup=@{}
        foreach ($row in $rowsA) { $lookup[[string]$row.target_frequency_mhz]=$row }
        if ($lookup.Count -ne $rowsA.Count) { throw "Stock return $name has duplicate first-run targets." }
        $changes=@()
        $seenTargets=@{}
        foreach ($row in $rowsB) {
            $key=[string]$row.target_frequency_mhz
            if ($seenTargets.ContainsKey($key)) { throw "Stock return $name has duplicate last-run target $key." }
            $seenTargets[$key]=$true
            if (-not $lookup.ContainsKey($key)) { throw "Stock return $name has unmatched target $key." }
            $x=[double]::Parse($lookup[$key].bench_throughput,[Globalization.CultureInfo]::InvariantCulture)
            $y=[double]::Parse($row.bench_throughput,[Globalization.CultureInfo]::InvariantCulture)
            if ($x -le 0 -or $y -le 0) { throw "Stock return $name has nonpositive throughput." }
            $changes+=[math]::Abs(100*($y/$x-1))
        }
        # Median as Python's statistics.median: the middle value, or the mean of the middle two.
        $sorted=@($changes | Sort-Object); $n=$sorted.Count
        if ($n % 2 -eq 1) { $per[$name]=[double]$sorted[($n-1)/2] }
        else { $per[$name]=([double]$sorted[$n/2-1]+[double]$sorted[$n/2])/2 }
    }
    $worst=($per.Values | Measure-Object -Maximum).Maximum
    return @{ worstMedianAbsPct=$worst; perWorkload=$per }
}
