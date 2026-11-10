<#
.SYNOPSIS
    Start HWiNFO in Sensors-only mode with nobody at the machine: launch it, choose "Sensors-only"
    in its startup dialog, press Start, and verify a Sensors window with a Log button is up.

.DESCRIPTION
    WHY. Every unattended run so far needed a person to open HWiNFO and click through its startup
    dialog before leaving. Written 2026-09-24, when the operator was away and the 5060 Ti was idle.

    HOW. The dialog is driven by window messages (CB_SETCURSEL + CBN_SELCHANGE on the mode combo,
    BM_CLICK on Start), not synthetic input, so the screen does not need to be on. It must run
    ELEVATED: HWiNFO runs elevated, and UIPI blocks messages from a lower-integrity process
    (tools/hwinfo-logging/README.md). Launched from an elevated shell, HWiNFO inherits elevation with
    no UAC prompt.

    Found on HWiNFO 8.50-6020: the dialog is class #32770 titled "HWiNFO(R) 64"; the mode combo is
    control 2746, with items "Full mode", "Sensors-only", "Summary-only", "Memory-only"; Start is
    control 1. The item is matched by TEXT, never by index, so a reordered list fails loudly.

    It changes no HWiNFO setting and writes no file. If HWiNFO is already running with a Sensors
    window, it does nothing.

    Exit codes: 0 Sensors ready; 2 not elevated; 3 HWiNFO not found; 4 dialog or item not found;
    5 Sensors window never appeared.
#>
param([string]$Exe = 'C:\Program Files\HWiNFO64\HWiNFO64.EXE', [int]$TimeoutSeconds = 60)
$ErrorActionPreference = 'Stop'
$status = Join-Path $PSScriptRoot 'Invoke-HwinfoLogging.ps1'

function Test-Ready {
    if (-not (Get-Process HWiNFO64 -ErrorAction SilentlyContinue)) { return $false }
    $out = @(& $status -Status *>&1)
    return ($LASTEXITCODE -eq 0 -and (($out -join "`n") -match 'Log button reads'))
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Not elevated: HWiNFO runs elevated, and its windows ignore messages from a normal process.'
    exit 2
}
if (Test-Ready) { Write-Host 'HWiNFO Sensors window already up; nothing to do.'; exit 0 }
if (-not (Test-Path $Exe)) { Write-Host "HWiNFO not found at $Exe."; exit 3 }

Add-Type @'
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices;
public static class HwStart {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr h, int id);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, StringBuilder l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  public static string T(IntPtr h){var s=new StringBuilder(256);GetWindowText(h,s,256);return s.ToString();}
  public static string C(IntPtr h){var s=new StringBuilder(256);GetClassName(h,s,256);return s.ToString();}
  public static List<IntPtr> Top(uint pid){var r=new List<IntPtr>();EnumWindows((h,l)=>{uint p;GetWindowThreadProcessId(h,out p);if(p==pid&&IsWindowVisible(h))r.Add(h);return true;},IntPtr.Zero);return r;}
}
'@

if (-not (Get-Process HWiNFO64 -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $Exe | Out-Null
    Write-Host 'HWiNFO launched.'
}
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$dialog = [IntPtr]::Zero
while ((Get-Date) -lt $deadline -and $dialog -eq [IntPtr]::Zero) {
    Start-Sleep -Milliseconds 500
    $process = Get-Process HWiNFO64 -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $process) { continue }
    foreach ($w in [HwStart]::Top([uint32]$process.Id)) {
        if ([HwStart]::C($w) -eq '#32770' -and [HwStart]::T($w) -like 'HWiNFO*' -and [HwStart]::GetDlgItem($w, 2746) -ne [IntPtr]::Zero) { $dialog = $w }
    }
}
if ($dialog -eq [IntPtr]::Zero) {
    if (Test-Ready) { Write-Host 'No startup dialog, and the Sensors window is up.'; exit 0 }
    Write-Host 'HWiNFO startup dialog not found.'; exit 4
}
$combo = [HwStart]::GetDlgItem($dialog, 2746)
$count = [int][HwStart]::SendMessage($combo, 0x146, [IntPtr]::Zero, [IntPtr]::Zero)   # CB_GETCOUNT
$index = -1
for ($i = 0; $i -lt $count; $i++) {
    $text = New-Object Text.StringBuilder 256
    [void][HwStart]::SendMessage($combo, 0x148, [IntPtr]$i, $text)                     # CB_GETLBTEXT
    if ($text.ToString() -eq 'Sensors-only') { $index = $i }
}
if ($index -lt 0) { Write-Host 'No "Sensors-only" item in the startup dialog.'; exit 4 }
[void][HwStart]::SendMessage($combo, 0x14E, [IntPtr]$index, [IntPtr]::Zero)             # CB_SETCURSEL
# The dialog only learns of the change through CBN_SELCHANGE (1) in a WM_COMMAND (0x111).
[void][HwStart]::SendMessage($dialog, 0x111, [IntPtr](2746 -bor (1 -shl 16)), $combo)
[void][HwStart]::SendMessage([HwStart]::GetDlgItem($dialog, 1), 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero)   # BM_CLICK Start
Write-Host 'Chose Sensors-only and pressed Start.'
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    if (Test-Ready) { Write-Host 'HWiNFO Sensors window is up and its Log button is readable.'; exit 0 }
}
Write-Host 'Pressed Start, but no Sensors window with a Log button appeared.'
exit 5
