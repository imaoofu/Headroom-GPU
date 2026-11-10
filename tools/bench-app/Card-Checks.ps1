# Checks on the live card that a registered design depends on.
#
# WHY. Collect.ps1 builds its suite grid from the card's supported-clock table: 40% of the table's
# top entry, up to that top entry, in 13 points. On 2026-09-25 the 3070 Ti's table had 116 entries
# and topped out at 2130 MHz, against 115 entries and 2115 the day before. Session D2's top six
# targets moved by 15 MHz, and its registered prediction (8d), which named Session D's grid, became
# NOT SCOREABLE after three hours of collection. A catalog can now state the table top its grid
# needs, and the engine refuses at the start instead.

# Returns $null when the table top matches, or a sentence saying why the session must not start.
function Get-SuiteTopProblem([int]$tableTopMhz, $card) {
    if ($null -eq $card.suiteTopClockMhz) { return $null }
    $expected = [int]$card.suiteTopClockMhz
    if ($tableTopMhz -eq $expected) { return $null }
    return ("The card's supported-clock table tops out at {0} MHz, not the {1} MHz this run list's " +
            "registered suite grid is built from. The suites would sweep a different grid and the " +
            "registered prediction could not be scored. Nothing was run.") -f $tableTopMhz, $expected
}

# A GENERIC run list (card.generic) is written before the card is known, for any card whose name
# matches card.namePattern. It may only run stock (Test-Plan refuses profiles, witnesses and a
# revert slot in one), so matching by pattern cannot apply a curve meant for another card.
# Added 2026-09-25 for REGISTERED-PREDICTIONS 11, the new-card protocol.
function Test-CardMatches([string]$gpuName, $card) {
    if ($card.generic) { return ($gpuName -match [string]$card.namePattern) }
    return ($gpuName -eq [string]$card.name)
}

# A generic sweep states its range as fractions of the table top, because the top is not known
# until the card is. Returns @(minMhz, maxMhz); a fixed sweep passes through unchanged.
function Resolve-SweepRange($step, [int]$tableTopMhz) {
    if ($null -ne $step.minPctOfTop) {
        return @([int][math]::Round($tableTopMhz * [double]$step.minPctOfTop),
                 [int][math]::Round($tableTopMhz * [double]$step.maxPctOfTop))
    }
    return @([int]$step.minMhz, [int]$step.maxMhz)
}

# The table top must not move INSIDE a session either: every suite and sweep grid is computed from
# it, so a move between two runs puts them on different grids (what cost D2 its verdict, across
# two days). Returns $null, or a sentence saying why the step must not start.
function Get-TableTopMoveProblem([int]$recordedTopMhz, [int]$currentTopMhz) {
    if ($recordedTopMhz -le 0 -or $recordedTopMhz -eq $currentTopMhz) { return $null }
    return ("The card's supported-clock table top moved from {0} MHz to {1} MHz during this " +
            "session. Later grids would not match earlier ones, so nothing more was run.") -f $recordedTopMhz, $currentTopMhz
}
