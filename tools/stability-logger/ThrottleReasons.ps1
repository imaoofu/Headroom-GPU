<#
    Decoding the throttle bitmask nvidia-smi reports.

    WHY THIS IS A SEPARATE FILE
        Log-GpuStability.ps1 takes a param block and starts sampling on load, so its decode could
        not be tested. This file touches nothing and is exercised by
        tools/stability-logger/test_throttle_reasons.py.

    WHY IT WAS CHANGED, 2026-09-12
        The table stopped at 0x100. A mask of 0x400 has been present since the 610.88 -> 616.56
        driver update and the decode had two separate problems with it:

          1. A mask of ONLY unknown bits returned "Unrecognised:<mask>", which is honest but
             carried no weight - nothing counted it, and the run was classed CLEAN.
          2. ⛔ A mask MIXING known and unknown bits silently dropped the unknown part. 0x604
             decoded as "SwPowerCap" alone and the 0x600 vanished with no trace at all. That is
             the worse of the two, because the output looks complete.

        Measured across the repository when this was written: 0 of 102 sweeps on driver 610.88
        carry 0x400, against 82 of 82 on 616.56. It arrived with a driver update.

    🛑 WHAT 0x200 AND 0x400 ACTUALLY MEAN IS NOT KNOWN, AND THIS FILE DOES NOT GUESS.
        They are reported as Unknown:<hex> and nothing infers a cause from them. Naming a
        throttle reason wrongly is precisely the defect this project has already had once, when
        an [ordered] dictionary indexed by integer did a positional lookup and shifted every
        reason by one. An unknown bit that says so is worth more than a named bit that is wrong.

    WHAT THEY ARE NOT TREATED AS
        They do NOT make a run concerning. 0x400 covers 589 of 603 samples in a healthy stock
        baseline, so escalating it would turn every post-616.56 run red and teach the reader to
        ignore the verdict. They are recorded, counted and surfaced - not judged.
#>

# Per NVML documentation. MUST stay a plain hashtable: indexing an [ordered] dictionary with an
# integer does a POSITIONAL lookup rather than a key lookup, which shifted every reason by one
# and decoded 0x1 as "ApplicationsClocksSetting". Caught by smoke test, kept as a warning.
$ThrottleReasonBits = @{
    1   = "GpuIdle"
    2   = "ApplicationsClocksSetting"
    4   = "SwPowerCap"
    8   = "HwSlowdown"
    16  = "SyncBoost"
    32  = "SwThermalSlowdown"
    64  = "HwThermalSlowdown"
    128 = "HwPowerBrakeSlowdown"
    256 = "DisplayClockSetting"
}

# Bits that mean the card is protecting itself rather than merely idle or power-limited.
$ConcerningReasons = @("HwSlowdown", "SwThermalSlowdown", "HwThermalSlowdown", "HwPowerBrakeSlowdown")


function ConvertTo-ThrottleReasonList {
    <#
        .SYNOPSIS
        Decode a throttle bitmask into a ";"-joined reason list.

        Unknown bits are reported as Unknown:<hex of the leftover>, ALONGSIDE any known reasons
        rather than instead of them.
    #>
    param([string]$HexMask)

    if ([string]::IsNullOrWhiteSpace($HexMask)) { return "unknown" }
    try {
        $value = [Convert]::ToInt64($HexMask.Replace("0x", ""), 16)
    } catch {
        return "unparsed:$HexMask"
    }
    if ($value -eq 0) { return "None" }

    $active = @()
    $knownMask = 0
    foreach ($bit in ($ThrottleReasonBits.Keys | Sort-Object)) {
        $knownMask = $knownMask -bor $bit
        if (($value -band $bit) -ne 0) { $active += $ThrottleReasonBits[$bit] }
    }

    # The leftover is what the table cannot explain. Reporting it beside the known reasons is the
    # whole point: a mask of 0x604 used to read "SwPowerCap" with the 0x600 discarded silently.
    $leftover = $value -band (-bnot $knownMask)
    if ($leftover -ne 0) {
        $active += ("Unknown:0x{0:X}" -f $leftover)
    }

    return ($active -join ";")
}


function Test-ThrottleReasonsConcerning {
    <#
        .SYNOPSIS
        True when a decoded reason list contains a reason meaning the card is protecting itself.

        An Unknown bit is deliberately NOT concerning - see the header. It is counted separately
        so that it is visible without being escalated.
    #>
    param([string]$Reasons)

    foreach ($reason in $ConcerningReasons) {
        if ($Reasons -like "*$reason*") { return $true }
    }
    return $false
}


function Test-ThrottleReasonsUnknown {
    <#
        .SYNOPSIS
        True when the decode could not account for every bit in the mask.
    #>
    param([string]$Reasons)

    return ($Reasons -like "*Unknown:*") -or ($Reasons -like "*Unrecognised:*")
}
