# Group achieved clocks at a resolution appropriate for the requested grid. The old fixed
# 25 MHz bucket merged separate measurements on 7-8 MHz grids. Coarse grids retain 25 MHz.
function Get-ClockGroups {
    param(
        [object[]]$Rows,
        [double[]]$TargetFrequencies
    )

    $grid = @($TargetFrequencies | Sort-Object -Unique)
    $bucketMHz = 25.0
    for ($i = 1; $i -lt $grid.Count; $i++) {
        $gap = [double]$grid[$i] - [double]$grid[$i - 1]
        if ($gap -gt 0 -and ($gap / 2.0) -lt $bucketMHz) {
            $bucketMHz = $gap / 2.0
        }
    }

    $Rows | Group-Object { [math]::Round([double]$_.achieved_frequency_avg / $bucketMHz) }
}
