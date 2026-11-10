<#
.SYNOPSIS
    Read, set or reset the NVML P0 graphics clock offset on GPU 0. CHANGES GPU STATE when not -Status.

.DESCRIPTION
    -Status             read the current P0 graphics offset and its allowed range. Changes nothing.
    -SetMhz <n>         write a NEGATIVE offset (n < 0, n >= -500), then read it back.
    -Reset              write 0, then read it back.

    SAFETY. Only negative offsets are accepted. A negative offset lowers the clock at every voltage,
    so any given clock needs MORE voltage than stock - instability is not reachable in that
    direction. Positive values are refused outright; this tool is for the 4c/4d experiments, not
    for tuning.

    WHAT IS NOT KNOWN. As of 2026-09-22 this write had never been exercised on this card. The read
    worked, and un-elevated writes return NO_PERMISSION rather than NOT_SUPPORTED. Whether the
    offset persists across a driver reset, or how it interacts with an Afterburner profile applied
    AFTER it, is unverified - so -Reset and read the value back at the end of every session, and
    apply any Afterburner profile BEFORE the offset, never after.

    Exit codes: 0 done and verified, 2 bad arguments, 3 NVML call failed, 4 read-back disagrees,
    5 needs elevation.
#>
param(
    [switch]$Status,
    [int]$SetMhz = 0,
    [switch]$Reset
)
$ErrorActionPreference = "Stop"

$modes = @($Status.IsPresent, ($SetMhz -ne 0), $Reset.IsPresent) | Where-Object { $_ }
if ($modes.Count -ne 1) {
    Write-Host "Give exactly one of -Status, -SetMhz <negative MHz>, -Reset." -ForegroundColor Red
    exit 2
}
if ($SetMhz -gt 0) {
    Write-Host "Refused: positive offsets raise clocks at every voltage and can make the card unstable." -ForegroundColor Red
    exit 2
}
if ($SetMhz -lt -500) {
    Write-Host "Refused: offsets below -500 MHz are outside what the 4c/4d experiments need." -ForegroundColor Red
    exit 2
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
public struct NvmlClockOffsetV1 {
    public uint version;
    public int type;
    public int pstate;
    public int clockOffsetMHz;
    public int minClockOffsetMHz;
    public int maxClockOffsetMHz;
}

public static class Nvml {
    [DllImport("nvml.dll")] public static extern int nvmlInit_v2();
    [DllImport("nvml.dll")] public static extern int nvmlShutdown();
    [DllImport("nvml.dll")] public static extern int nvmlDeviceGetHandleByIndex_v2(uint index, out IntPtr device);
    [DllImport("nvml.dll")] public static extern int nvmlDeviceGetClockOffsets(IntPtr device, ref NvmlClockOffsetV1 info);
    [DllImport("nvml.dll")] public static extern int nvmlDeviceSetClockOffsets(IntPtr device, ref NvmlClockOffsetV1 info);
    [DllImport("nvml.dll")] public static extern IntPtr nvmlErrorString(int result);
    public static string Err(int r) { return Marshal.PtrToStringAnsi(nvmlErrorString(r)); }
}
"@

# nvmlClockOffset_v1 = sizeof(struct) | (1 << 24); the struct is six 4-byte fields.
$VERSION_V1 = [uint32](24 -bor (1 -shl 24))
$NVML_CLOCK_GRAPHICS = 0
$NVML_PSTATE_0 = 0
$NVML_ERROR_NO_PERMISSION = 4

function New-Query {
    $q = New-Object NvmlClockOffsetV1
    $q.version = $VERSION_V1
    $q.type = $NVML_CLOCK_GRAPHICS
    $q.pstate = $NVML_PSTATE_0
    return $q
}

function Read-Offset($device) {
    $q = New-Query
    $r = [Nvml]::nvmlDeviceGetClockOffsets($device, [ref]$q)
    if ($r -ne 0) { throw ("nvmlDeviceGetClockOffsets failed: " + [Nvml]::Err($r)) }
    return $q
}

$r = [Nvml]::nvmlInit_v2()
if ($r -ne 0) { Write-Host ("NVML init failed: " + [Nvml]::Err($r)) -ForegroundColor Red; exit 3 }
try {
    $device = [IntPtr]::Zero
    $r = [Nvml]::nvmlDeviceGetHandleByIndex_v2(0, [ref]$device)
    if ($r -ne 0) { Write-Host ("No GPU 0: " + [Nvml]::Err($r)) -ForegroundColor Red; exit 3 }

    $before = Read-Offset $device
    Write-Host ("Current P0 graphics offset: {0} MHz (allowed {1} to {2})." -f `
        $before.clockOffsetMHz, $before.minClockOffsetMHz, $before.maxClockOffsetMHz)
    if ($Status) { exit 0 }

    $target = 0
    if (-not $Reset) { $target = $SetMhz }
    if ($target -lt $before.minClockOffsetMHz -or $target -gt $before.maxClockOffsetMHz) {
        Write-Host "Refused: $target MHz is outside the range the driver reports." -ForegroundColor Red
        exit 2
    }

    $w = New-Query
    $w.clockOffsetMHz = $target
    $r = [Nvml]::nvmlDeviceSetClockOffsets($device, [ref]$w)
    if ($r -eq $NVML_ERROR_NO_PERMISSION) {
        Write-Host "The write needs an elevated shell (NVML returned NO_PERMISSION)." -ForegroundColor Red
        exit 5
    }
    if ($r -ne 0) { Write-Host ("nvmlDeviceSetClockOffsets failed: " + [Nvml]::Err($r)) -ForegroundColor Red; exit 3 }

    $after = Read-Offset $device
    if ($after.clockOffsetMHz -ne $target) {
        Write-Host ("READ-BACK DISAGREES: wrote {0} MHz, the driver now reports {1} MHz." -f $target, $after.clockOffsetMHz) -ForegroundColor Red
        exit 4
    }
    Write-Host ("Verified by read-back: P0 graphics offset is now {0} MHz." -f $after.clockOffsetMHz) -ForegroundColor Green
    Write-Host "A read-back proves the driver accepted the value, not what it does to clocks or voltage. The sweep measures that."
    exit 0
}
finally {
    [void][Nvml]::nvmlShutdown()
}
