param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference = 'Stop'

function Require($condition, [string]$message) {
    if (-not $condition) { throw $message }
}
function Is-KitPath([string]$value) {
    return ($value -match '^kit:/[^.]' -and $value -notmatch '(^|[\\/])\.\.([\\/]|$)')
}
function Is-Absolute([string]$value) {
    return ([System.IO.Path]::IsPathRooted($value) -or $value -match '^[A-Za-z]:[\\/]' -or (Is-KitPath $value))
}
function Validate-Plan($plan) {
    Require ($null -ne $plan) 'Plan is empty.'
    Require ($plan.schemaVersion -eq 1) 'schemaVersion must be 1.'
    if ($null -ne $plan.minimizeKnownRenderers) {
        Require ($plan.minimizeKnownRenderers -is [array]) 'minimizeKnownRenderers must be an array of exact process names.'
        foreach ($name in @($plan.minimizeKnownRenderers)) {
            Require ($name -is [string] -and $name -match '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$' -and $name -notmatch '[.]exe$') 'Renderer names must be exact process names without .exe or wildcards.'
            Require ($name -notmatch '^HWiNFO') 'HWiNFO windows must remain available for logging.'
        }
    }
    Require ($plan.volumeLabel -match '^[A-Za-z0-9 _-]{1,32}$' -and $plan.card.name) 'Plan needs a USB volume label and GPU name.'
    $generic=[bool]$plan.card.generic
    if ($generic) {
        # A generic run list is written before the card is known (REGISTERED-PREDICTIONS 11). It is
        # stock-only by construction: no profile, no witness, no hash gate and no revert slot, since
        # a slot number means a different curve on every machine.
        $pattern=[string]$plan.card.namePattern
        Require ($pattern.StartsWith('^')) 'A generic card needs a namePattern anchored with ^.'
        try { [void][regex]::new($pattern) } catch { throw 'A generic card namePattern is not a valid regex.' }
        Require ($null -eq $plan.revert) 'A generic run list cannot revert to a profile slot.'
        Require ($null -eq $plan.card.suiteTopClockMhz) 'A generic run list cannot state a table top.'
    } else {
        Require ($plan.card.minClockMhz -gt 0 -and $plan.card.maxClockMhz -gt $plan.card.minClockMhz) 'Invalid card clock range.'
    }
    $calibrated=$false
    # A generic (any-card, stock-only) run list must pass a stockOnly power gate before it measures
    # anything, and may use no other kind (GPT Job 88, R2: ordinary gates validated with 200/180/200).
    $stockGated=$false
    if ($null -ne $plan.card.suiteTopClockMhz) { Require ([int]$plan.card.suiteTopClockMhz -ge $plan.card.minClockMhz -and [int]$plan.card.suiteTopClockMhz -le 4000) 'Invalid suiteTopClockMhz.' }
    Require ($plan.runs.Count -gt 0) 'Select at least one run.'
    $runIds = @{}
    $allowedWorkloads=@('gemm','membw','copy','reduce','softmax','layernorm','bgemm32','bgemm64','bgemm128','bgemm256','bgemm1024','attention','conv')
    $seenRuns = @{}
    $logPaths = @{}
    $runIndex=0
    $closedGroups=@{}
    $activeGroup=''
    $hasProfile=$false
    $derivedSuites=@()
    foreach ($run in $plan.runs) {
        $group=[string]$run.group
        if ($group -ne $activeGroup) {
            if ($activeGroup) { $closedGroups[$activeGroup]=$true }
            Require (-not ($group -and $closedGroups.ContainsKey($group))) "Locked group $group was split."
            $activeGroup=$group
        }
        if ($run.finalRun) { Require ($runIndex -eq ($plan.runs.Count - 1)) "Run $($run.id) must be last." }
        $runIndex++
        Require ($run.id -match '^[a-z0-9][a-z0-9-]{1,63}$') 'Invalid run id.'
        Require (-not $runIds.ContainsKey($run.id)) "Duplicate run id: $($run.id)"
        $runIds[$run.id] = $true
        foreach ($needed in @($run.requires)) { if ($needed) { Require ($seenRuns.ContainsKey([string]$needed)) "Run $($run.id) requires earlier run $needed." } }
        $seenRuns[$run.id]=$true
        Require ($run.steps.Count -gt 0) "Run $($run.id) has no steps."
        $logging = $false
        $usedLog = $false
        $needsWitness = $false
        foreach ($step in $run.steps) {
            Require ($step.id -match '^[a-z0-9][a-z0-9-]{1,63}$') 'Invalid step id.'
            $type = [string]$step.type
            Require (@('gate-power','gate-quiet','gate-hash','gate-drift','apply-profile','witness','hwinfo-start','hwinfo-stop','suite','sweep','human','calibrate','minimize-known-renderers') -contains $type) "Unknown step type: $type"
            if ($generic) { Require (@('apply-profile','witness','gate-hash') -notcontains $type) "A generic run list is stock only and cannot contain a $type step." }
            switch ($type) {
                'gate-power' {
                    if ($generic) { Require ([bool]$step.stockOnly) 'A generic run list may use only stockOnly power gates.' }
                    if ($step.stockOnly) { Require ($null -eq $step.limit -and $null -eq $step.default -and $null -eq $step.max) 'A stockOnly gate-power states no limits.'; $stockGated=$true }
                    else { Require ($step.limit -gt 0 -and $step.default -gt 0 -and $step.max -gt 0) 'gate-power needs limit/default/max.' }
                }
                'calibrate' {
                    if ($generic) { Require ($stockGated) 'A generic run list must pass a stockOnly power gate before any measurement.' }
                    Require (-not $logging) 'Calibrate before a HWiNFO log starts, not inside one.'
                    Require (@($step.workloads).Count -gt 0 -and @($step.workloads | Where-Object { $allowedWorkloads -notcontains $_ -or $_ -eq 'gemm' }).Count -eq 0) 'calibrate needs supported suite workloads, never gemm (it keeps its default 120).'
                    Require ($step.targetSeconds -ge 5 -and $step.targetSeconds -le 30) 'calibrate targetSeconds must be 5..30.'
                    $calibrated=$true
                }
                'gate-quiet' { Require ($step.maxUtil -gt 0 -and $step.maxUtil -le 100) 'gate-quiet needs maxUtil 1..100.' }
                'gate-hash' {
                    Require ($step.path -and (Is-Absolute $step.path)) 'gate-hash needs an absolute path.'
                    Require ($step.prefix -match '^[0-9a-fA-F]{8,64}$') 'gate-hash needs a SHA-256 prefix.'
                    if ($null -ne $step.sections) { Require (@($step.sections | Where-Object { $_ -match '^Profile[1-5]$' }).Count -eq @($step.sections).Count -and @($step.sections).Count -gt 0) 'gate-hash sections must be Profile1..Profile5.' }
                }
                'gate-drift' {
                    Require ($step.firstRun -and $step.lastRun -and $step.workloads.Count -gt 0 -and $step.maxMedianAbsPct -gt 0) 'gate-drift needs firstRun, lastRun, workloads and maxMedianAbsPct.'
                    Require ($seenRuns.ContainsKey([string]$step.firstRun) -and $seenRuns.ContainsKey([string]$step.lastRun) -and $step.firstRun -ne $step.lastRun) 'gate-drift references missing or identical runs.'
                }
                'apply-profile' { Require (-not $logging) 'A profile cannot change while HWiNFO is logging.'; Require ($step.slot -ge 1 -and $step.slot -le 5) 'apply-profile slot must be 1..5.'; $needsWitness=$true; $hasProfile=$true }
                'witness' {
                    Require ($step.iterations -gt 0 -and $allowedWorkloads -contains $step.workload) 'witness needs a supported workload and iterations.'
                    Require ($step.coreMin -gt 0 -and $step.coreMax -ge $step.coreMin -and $step.memoryMin -gt 0 -and $step.memoryMax -ge $step.memoryMin) 'witness needs core and memory bounds.'
                    Require ($step.coreMin -ge $plan.card.minClockMhz -and $step.coreMax -le $plan.card.maxClockMhz) 'Witness core bounds outside card range.'
                    if ($step.lockMhz) { Require ($step.lockMhz -ge $plan.card.minClockMhz -and $step.lockMhz -le $plan.card.maxClockMhz) 'Witness lock outside card range.' }
                    if ($step.voltageMin -or $step.voltageMax) { Require ($logging) 'Voltage witness needs an active HWiNFO log.'; Require ($step.voltageMin -gt 0 -and $step.voltageMax -ge $step.voltageMin) 'Invalid voltage range.' }
                    $needsWitness=$false
                }
                'hwinfo-start' {
                    Require (-not $logging) 'A log is already active.'
                    Require ($step.path -and $step.path -match '^kit:/results/' -and (Is-KitPath $step.path)) 'hwinfo-start needs a kit:/results/ path.'
                    Require (-not $logPaths.ContainsKey($step.path.ToLowerInvariant())) 'Two runs share one HWiNFO log.'
                    $logPaths[$step.path.ToLowerInvariant()] = $true
                    $logging = $true
                    $usedLog = $true
                }
                'hwinfo-stop' { Require ($logging) 'hwinfo-stop without hwinfo-start.'; $logging = $false }
                'suite' {
                    if ($generic) { Require ($stockGated) 'A generic run list must pass a stockOnly power gate before any measurement.' }
                    Require ($logging) 'A suite needs hwinfo-start before it.'
                    Require (-not $needsWitness) 'Applied profile needs a witness before a suite.'
                    Require ($step.label -match '^[a-z0-9][a-z0-9-]{2,63}$' -and $step.settings) 'suite needs label and settings.'
                    foreach ($name in $step.workloads) { Require ($allowedWorkloads -contains $name) "Unsupported suite workload: $name" }
                    if ([string]$step.iterations -eq 'calibrated') {
                        Require ($calibrated) 'A suite with calibrated iterations needs a calibrate step before it.'
                    } else {
                        Require ($step.workloads.Count -gt 0 -and $step.workloads.Count -eq $step.iterations.Count) 'suite workloads and iterations must match.'
                        foreach ($n in $step.iterations) { Require ($n -gt 0) 'Iterations must be positive.' }
                    }
                    # Optional explicit target list (2026-09-27): whole MHz, ascending, unique, inside
                    # the card's range, and at least 10 (the engine's completeness check). A generic
                    # run list cannot state one, since the card's clock table is unknown.
                    $targetList=@($step.targetsMhz | Where-Object { $null -ne $_ })
                    if ($targetList.Count -gt 0) {
                        Require (-not $generic) 'A generic run list cannot state explicit suite targets.'
                        Require ($targetList.Count -ge 10) 'An explicit suite target list needs at least 10 targets.'
                        $prev=0
                        foreach ($t in $targetList) {
                            Require ($t -is [int] -or $t -is [long] -or ([string]$t -match '^\d+$')) 'Suite targets must be whole MHz.'
                            Require ([int]$t -gt $prev) 'Suite targets must be ascending and unique.'
                            Require ([int]$t -ge $plan.card.minClockMhz -and [int]$t -le $plan.card.maxClockMhz) "Suite target $t MHz is outside the card's clock range."
                            $prev=[int]$t
                        }
                    } else {
                        $derivedSuites += [string]$step.label
                    }
                    # A generic run list cannot know the memory clock in advance; Collect records it.
                    if (-not $generic) { Require ($step.expectedMemoryClockMhz -gt 0) 'suite needs expectedMemoryClockMhz.' }
                }
                'sweep' {
                    if ($generic) { Require ($stockGated) 'A generic run list must pass a stockOnly power gate before any measurement.' }
                    Require ($logging) 'A sweep needs hwinfo-start before it.'
                    Require (-not $needsWitness) 'Applied profile needs a witness before a sweep.'
                    Require ($step.label -match '^[a-z0-9][a-z0-9-]{2,63}$' -and $step.settings) 'sweep needs label and settings.'
                    $iterationsValue=0
                    Require ($allowedWorkloads -contains $step.workload -and -not ($step.iterations -is [array]) -and [int]::TryParse([string]$step.iterations,[ref]$iterationsValue) -and $iterationsValue -gt 0) 'sweep needs a supported workload and one fixed iteration count.'
                    if ($generic) {
                        Require ($null -eq $step.minMhz -and $step.minPctOfTop -ge 0.2 -and $step.maxPctOfTop -le 1.0 -and $step.maxPctOfTop -gt $step.minPctOfTop) 'A generic sweep needs minPctOfTop and maxPctOfTop, 0.2 to 1.0, and no fixed MHz.'
                    } else {
                        Require ($step.minMhz -ge $plan.card.minClockMhz -and $step.maxMhz -le $plan.card.maxClockMhz -and $step.maxMhz -gt $step.minMhz) 'Sweep outside card supported clocks.'
                    }
                    Require ($step.points -ge 3 -and $step.points -le 40 -and @('ascending','descending') -contains $step.direction) 'Invalid sweep grid.'
                    Require ($step.output -and $step.output -match '^kit:/results/' -and (Is-KitPath $step.output)) 'sweep output must be under kit:/results/.'
                }
                'human' { Require (-not [string]::IsNullOrWhiteSpace($step.instruction)) 'human needs instruction.' }
            }
        }
        Require (-not $logging) "Run $($run.id) leaves its HWiNFO log open."
        Require (-not $needsWitness) "Run $($run.id) applies a profile without a witness."
        if ($run.requiresLog) { Require ($usedLog) "Run $($run.id) requires a log." }
    }
    # Explicit targets whenever a profile is applied (2026-09-30). A derived grid follows the card's
    # supported-clock table, and that table moved twice under a registered test: overnight on the
    # 3070 Ti (Session D2, 8d NOT SCOREABLE) and under an offset profile on the 2060 Super (Session E,
    # 4c-offset NOT SCOREABLE). A lesson recorded after the first did not prevent the second, so the
    # validator enforces it. Run lists written before the rule carry card.legacyDerivedGrids, a stated
    # reason; the tests pin which ones may.
    $legacy=[string]$plan.card.legacyDerivedGrids
    if (-not $generic -and $hasProfile -and $derivedSuites.Count -gt 0) {
        Require (-not [string]::IsNullOrWhiteSpace($legacy)) ("This run list applies a profile, so every suite must state its targets (targetsMhz): a derived grid moves when the clock table does. Suites without them: {0}." -f ($derivedSuites -join ', '))
    } else {
        Require ([string]::IsNullOrWhiteSpace($legacy)) 'card.legacyDerivedGrids exempts derived grids, but this run list has none that need it.'
    }
    if ($plan.revert) {
        Require ($plan.revert.slot -ge 1 -and $plan.revert.slot -le 5) 'Invalid revert slot.'
        Require ($null -ne $plan.revert.witness) 'Revert needs a witness.'
        $w=$plan.revert.witness
        Require ($allowedWorkloads -contains $w.workload -and $w.iterations -gt 0) 'Revert witness needs a supported workload and iterations.'
        Require ($w.coreMin -ge $plan.card.minClockMhz -and $w.coreMax -le $plan.card.maxClockMhz -and $w.coreMax -ge $w.coreMin) 'Invalid revert core bounds.'
        Require ($w.memoryMin -gt 0 -and $w.memoryMax -ge $w.memoryMin) 'Invalid revert memory bounds.'
    }
    return $true
}

try {
    Require ([System.IO.Path]::IsPathRooted($PlanPath)) 'PlanPath must be absolute.'
    $plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    [void](Validate-Plan $plan)
    Write-Host 'VALID PLAN'
    exit 0
} catch {
    Write-Host ("INVALID PLAN: {0}" -f $_.Exception.Message)
    exit 2
}
