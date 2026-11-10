# Read HWiNFO's latest complete CSV row without locking the writer.
# HWiNFO repeats some header names, so ConvertFrom-Csv is not usable here.
function Get-HwinfoCoreVoltage([string]$path) {
    if (-not (Test-Path $path)) { throw "HWiNFO CSV missing: $path" }
    $stream=New-Object IO.FileStream($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
    try {
        $reader=New-Object IO.StreamReader($stream)
        $header=$reader.ReadLine()
        if (-not $header) { throw 'HWiNFO CSV has no header.' }
        $head=@([regex]::Split($header, ',(?=(?:[^"]*"[^"]*")*[^"]*$)'))
        # A CPU with integrated graphics adds its own "GPU Core Voltage (VDDCR_GFX) [V]" column, so a
        # prefix match finds two. Found live on 2026-09-23 (Ryzen 9700X + RTX 5060 Ti): every read
        # threw. Prefer the exact name, as tools/frequency-sweep/join_hwinfo_voltage.py does; if that
        # still matches several, the choice is made below by whose own GPU clock reads highest.
        $names=@($head | ForEach-Object { $_.Trim('"') })
        $indices=@(for($i=0;$i -lt $names.Count;$i++) { if ($names[$i] -eq 'GPU Core Voltage [V]') { $i } })
        if ($indices.Count -eq 0) { $indices=@(for($i=0;$i -lt $names.Count;$i++) { if ($names[$i] -like 'GPU Core Voltage*') { $i } }) }
        if ($indices.Count -eq 0) { throw 'No GPU Core Voltage column in the HWiNFO CSV.' }
        $clockFor=@{}
        foreach ($i in $indices) {
            for ($k=$i+1; $k -lt $names.Count; $k++) { if ($names[$k] -eq 'GPU Clock [MHz]') { $clockFor[$i]=$k; break } }
        }
        [void]$stream.Seek([math]::Max(0,$stream.Length-65536),[IO.SeekOrigin]::Begin)
        $reader.DiscardBufferedData()
        $tail=$reader.ReadToEnd()
        $lines=@($tail -split "`n" | Where-Object { $_.Trim() })
        for($j=$lines.Count-1;$j -ge [math]::Max(0,$lines.Count-15);$j--) {
            $fields=@([regex]::Split($lines[$j].TrimEnd("`r"), ',(?=(?:[^"]*"[^"]*")*[^"]*$)'))
            if ($fields.Count -ne $head.Count) { continue }
            $pick=$indices[0]
            if ($indices.Count -gt 1) {
                # Several candidates: the card under test is the one whose own clock reads highest.
                $best=-1.0
                foreach ($i in $indices) {
                    if (-not $clockFor.ContainsKey($i)) { continue }
                    $clock=0.0
                    if ([double]::TryParse($fields[$clockFor[$i]].Trim('"'),[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$clock) -and $clock -gt $best) { $best=$clock; $pick=$i }
                }
                if ($best -lt 0) { throw 'Several GPU Core Voltage columns and no GPU clock to tell them apart.' }
            }
            $value=$fields[$pick].Trim('"')
            $number=0.0
            if ([double]::TryParse($value,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$number)) { return $number }
        }
        throw 'No complete core-voltage sample in HWiNFO CSV tail.'
    } finally { $stream.Dispose() }
}

function Assert-HwinfoLogGrowth([string]$path, [int]$FirstDelayMs=3000, [int]$SecondDelayMs=4000) {
    Start-Sleep -Milliseconds $FirstDelayMs
    if (-not (Test-Path $path)) { throw "HWiNFO log was not created: $path" }
    $first=(Get-Item $path).Length
    Start-Sleep -Milliseconds $SecondDelayMs
    $second=(Get-Item $path).Length
    if ($second -le $first) { throw "HWiNFO log is not growing: $path" }
    return @{ first=$first; second=$second }
}
