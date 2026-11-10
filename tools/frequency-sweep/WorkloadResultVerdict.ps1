<#
    Does a finished sweep actually contain benchmark results?

    WHY THIS EXISTS
        On 2026-09-12 a sweep ran to completion, wrote a CSV, printed a normal summary and
        exited 0 - having never once launched its workload. The command line pointed at an
        interpreter on one drive and a script on another, so every invocation failed instantly.
        The card sat at ~18 W for the whole run and every bench_throughput column was empty.

        Nothing in the tool noticed. The sweep's job, as it was written, was to lock clocks and
        sample telemetry, and it did both perfectly. That a fixed-work benchmark had produced no
        work was not a condition it had any opinion about.

        The cost is an hour of wall clock and, worse, a CSV that looks like data. Its power
        column is real - it is the idle draw of a locked card - so nothing downstream fails
        either. It is the same shape as the sampling bug of 2026-08-16, which recorded idle
        power at every frequency and would have been invisible in the output.

    THIS FILE IS SEPARATE FROM Invoke-FrequencySweep.ps1 ON PURPOSE
        That script takes a param block and changes GPU state on load, so it cannot be
        dot-sourced by a test. This function touches nothing, needs no GPU and no elevation,
        and is exercised by tools/frequency-sweep/test_workload_result_verdict.py.

    WHAT IT DOES NOT DO
        It cannot tell a workload that ran badly from one that ran well. A benchmark that
        returns a wrong-but-positive number passes this check. It answers exactly one question:
        did a measurement come back at all.
#>

function Get-WorkloadResultVerdict {
    <#
        .SYNOPSIS
        Classify a sweep's rows by whether the benchmark actually reported a result.

        .OUTPUTS
        An ordered hashtable: verdict, measured, withResult, missing, message.
        verdict is one of "not-applicable", "ok", "partial", "none".
    #>
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [array] $Rows,

        [Parameter(Mandatory = $true)]
        [bool] $WorkloadCommanded
    )

    $measured = $Rows.Count

    if (-not $WorkloadCommanded) {
        # A sweep with no workload is a legitimate mode - it samples an external load - and its
        # own summary already says it carries no performance metric. Silence here, not a pass.
        return [ordered]@{
            verdict = "not-applicable"; measured = $measured; withResult = 0; missing = 0
            message = "No workload was commanded, so there is no benchmark result to verify."
        }
    }

    $withResult = 0
    foreach ($row in $Rows) {
        if (Test-RowHasBenchResult -Row $row) { $withResult++ }
    }
    $missing = $measured - $withResult

    if ($measured -eq 0) {
        $verdict = "none"
        $message = "A workload was commanded but no frequency point was measured at all."
    } elseif ($withResult -eq 0) {
        $verdict = "none"
        $message = (("A workload was commanded at {0} frequencies and NOT ONE returned a benchmark " +
                     "result. The workload did not run. This CSV has no performance metric and is " +
                     "not data - check the interpreter and script paths in -WorkloadCommand.") -f $measured)
    } elseif ($missing -gt 0) {
        $verdict = "partial"
        $message = (("{0} of {1} frequency points returned no benchmark result. Those rows carry " +
                     "telemetry but no performance metric; treat them as missing rather than as " +
                     "zeros.") -f $missing, $measured)
    } else {
        $verdict = "ok"
        $message = ("All {0} frequency points returned a benchmark result." -f $measured)
    }

    return [ordered]@{
        verdict = $verdict; measured = $measured; withResult = $withResult
        missing = $missing; message = $message
    }
}

function Test-RowHasBenchResult {
    <#
        .SYNOPSIS
        True when one sweep row carries a usable benchmark measurement.

        Both halves are required. bench_ok alone would accept a calibration record, which
        reports ok with no throughput; throughput alone would accept a run the workload itself
        declared failed after an abort.
    #>
    param([Parameter(Mandatory = $true)] $Row)

    if ($null -eq $Row) { return $false }

    # A re-read CSV gives the string "True" rather than $true, and this handles both WITHOUT a
    # second comparison: -eq converts the right operand to the left's type, so "True" -eq $true
    # becomes "True" -eq "True". An explicit -or ("$ok" -eq "True") was written here first and
    # then deleted - no mutation of it could be made to fail the suite, because there is no value
    # of bench_ok the two forms disagree on. Dead code that looks like defensiveness.
    if ($Row.bench_ok -ne $true) { return $false }

    $throughput = $Row.bench_throughput
    if ($null -eq $throughput -or "$throughput" -eq "") { return $false }

    $value = 0.0
    if (-not [double]::TryParse("$throughput", [ref] $value)) { return $false }
    return $value -gt 0
}
