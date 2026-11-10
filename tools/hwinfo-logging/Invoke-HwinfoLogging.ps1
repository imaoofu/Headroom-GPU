<#
.SYNOPSIS
    Start and stop HWiNFO sensor logging without a human, and without HWiNFO Pro.

.DESCRIPTION
    HWiNFO's documented logging switches (-l, -max_time, -poll_rate) are PRO ONLY. On the
    freeware build the only way to start logging is the Sensors window's "Log Start" button.
    This script presses it by Win32 message, fills the Save As dialog, and verifies the result.

    WHY THIS EXISTS
        Every multi-configuration bench item in this project is costed as "the operator must be
        present" purely to click that button between runs - see docs/GPU-WORKLIST-5060TI.md item
        4j. This removes that, which is what makes unattended sessions possible at all.

    WHY AN AGENT CANNOT DO THIS DIRECTLY
        HWiNFO runs elevated. UIPI forbids a medium-integrity process from sending input to an
        elevated window, so a computer-use agent's clicks are silently DISCARDED - no error, no
        effect. Screenshots still work, because reading the screen is permitted and injecting is
        not. Verified 2026-09-21 against the Codex desktop agent, whose MSIX manifest has
        runFullTrust but no allowElevation and therefore can never be elevated.

        ✅ The fix is not to elevate the agent. It is to let an ELEVATED script own the clicking
        and have the agent merely trigger it - elevated-to-elevated injection is same-integrity
        and permitted. Run this from a scheduled task registered with highest privileges.

.PARAMETER Start
    Begin logging to -LogPath.

.PARAMETER Stop
    End logging and report the finished file.

.PARAMETER Status
    Report whether logging is running, and change nothing.

.PARAMETER LogPath
    Absolute path for the CSV. Required with -Start.

.EXAMPLE
    .\Invoke-HwinfoLogging.ps1 -Status
    .\Invoke-HwinfoLogging.ps1 -Start -LogPath D:\runs\5060ti-4i-hwinfo.csv
    .\Invoke-HwinfoLogging.ps1 -Stop
#>

[CmdletBinding()]
param(
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [string]$LogPath
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------------------------
# ⛔ THE TWO THINGS THAT COST AN HOUR TO LEARN. Do not "simplify" either of them.
#
# 1. PostMessage, NEVER SendMessage, to press the log button.
#    SendMessage is synchronous. The button opens a MODAL Save As dialog, so SendMessage blocks
#    until that dialog closes - meaning the script that opened it can never be the script that
#    fills it in. The first attempt at this deadlocked and had to be killed.
#
# 2. SetWindowTextW on the filename box is NOT ENOUGH.
#    It puts characters in the edit control but raises no EN_CHANGE, so the Vista-style file
#    dialog never updates the name it actually intends to use and IDOK acts on an empty string.
#    The dialog stays open and nothing says why. WM_SETTEXT plus an explicit EN_CHANGE to the
#    parent, then IDOK, works.
#
# Controls are located by TEXT, never by HWND - handles differ every time HWiNFO starts.
# ---------------------------------------------------------------------------------------------

Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;

public class HwiUi {
    public delegate bool EnumProc(IntPtr h, IntPtr p);

    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", EntryPoint="SendMessageW", CharSet=CharSet.Unicode)] public static extern IntPtr SendText(IntPtr h, uint msg, IntPtr wp, string lp);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
    [DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr h, int id);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);

    public const uint WM_COMMAND = 0x0111;
    public const uint WM_SETTEXT = 0x000C;
    public const int  EN_CHANGE  = 0x0300;
    public const int  IDOK       = 1;

    public static string Text(IntPtr h) { StringBuilder s = new StringBuilder(1024); GetWindowTextW(h, s, 1024); return s.ToString(); }
    public static string Cls(IntPtr h)  { StringBuilder s = new StringBuilder(256);  GetClassNameW(h, s, 256);   return s.ToString(); }

    public static List<IntPtr> VisibleTopLevel(uint want) {
        List<IntPtr> found = new List<IntPtr>();
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            uint pid; GetWindowThreadProcessId(h, out pid);
            if (pid == want && IsWindowVisible(h)) found.Add(h);
            return true;
        }, IntPtr.Zero);
        return found;
    }

    public static List<IntPtr> Children(IntPtr parent) {
        List<IntPtr> found = new List<IntPtr>();
        EnumChildWindows(parent, delegate(IntPtr h, IntPtr p) { found.Add(h); return true; }, IntPtr.Zero);
        return found;
    }

    /// Press a dialog button the way its dialog expects to hear about it, asynchronously.
    public static void PressAsync(IntPtr dialog, IntPtr button) {
        int id = GetDlgCtrlID(button);
        PostMessage(dialog, WM_COMMAND, (IntPtr)(id & 0xFFFF), button);
    }

    /// Put a filename into a Vista-style file dialog so the dialog actually notices.
    public static void SetFileName(IntPtr dialog, IntPtr edit, string path) {
        SendText(edit, WM_SETTEXT, IntPtr.Zero, path);
        int id = GetDlgCtrlID(edit);
        PostMessage(dialog, WM_COMMAND, (IntPtr)((id & 0xFFFF) | (EN_CHANGE << 16)), edit);
    }
}
"@

function Say([string]$text, [string]$colour = "White") { Write-Host $text -ForegroundColor $colour }

function Get-HwinfoProcess {
    $proc = Get-Process HWiNFO64 -ErrorAction SilentlyContinue
    if (-not $proc) {
        Say "HWiNFO is not running." "Red"
        Say "Start it and open the Sensors window before calling this script. It deliberately" "Yellow"
        Say "does NOT launch HWiNFO: the splash and its update nag are extra state to get wrong," "Yellow"
        Say "and a run that begins by guessing at dialogs is not a run worth having." "Yellow"
        exit 3
    }
    return $proc
}

# Returns the Sensors dialog handle and its log button, or $null. The button's own LABEL is the
# state: 'Log Start' means stopped, 'Log Stop' means running. Read it; never assume it.
function Get-LogButton {
    $proc = Get-HwinfoProcess
    foreach ($top in [HwiUi]::VisibleTopLevel([uint32]$proc.Id)) {
        if ([HwiUi]::Text($top) -notmatch "Sensors") { continue }
        foreach ($kid in [HwiUi]::Children($top)) {
            if ([HwiUi]::Cls($kid) -ne "Button") { continue }
            if ([HwiUi]::Text($kid) -match "^Log ") {
                return [pscustomobject]@{
                    Dialog = $top
                    Button = $kid
                    Label  = [HwiUi]::Text($kid)
                }
            }
        }
    }
    return $null
}

function Get-SaveDialog {
    $proc = Get-HwinfoProcess
    foreach ($top in [HwiUi]::VisibleTopLevel([uint32]$proc.Id)) {
        if ([HwiUi]::Text($top) -match "Save As") { return $top }
    }
    return $null
}

function Get-FileSize([string]$path) {
    if (-not (Test-Path $path)) { return -1 }
    return (Get-Item $path).Length
}

# ---- status ----------------------------------------------------------------------------------

if ($Status -or (-not $Start -and -not $Stop)) {
    $state = Get-LogButton
    if (-not $state) {
        Say "HWiNFO is running but no Sensors window with a log button was found." "Red"
        Say "Open Sensors (the main window's sensors icon) and try again." "Yellow"
        exit 4
    }
    Say ("Log button reads '{0}'." -f $state.Label)
    if ($state.Label -match "Stop") { Say "Logging is RUNNING." "Green" } else { Say "Logging is stopped." "Gray" }
    exit 0
}

if ($Start -and $Stop) { Say "Pick one of -Start or -Stop." "Red"; exit 2 }

# ---- start -----------------------------------------------------------------------------------

if ($Start) {
    if (-not $LogPath) { Say "-Start needs -LogPath." "Red"; exit 2 }
    if (-not [System.IO.Path]::IsPathRooted($LogPath)) {
        Say "-LogPath must be absolute. A relative path lands wherever the task's working" "Red"
        Say "directory happens to be, which for a scheduled task is system32." "Yellow"
        exit 2
    }
    $parent = Split-Path $LogPath -Parent
    if (-not (Test-Path $parent)) { Say "Directory does not exist: $parent" "Red"; exit 2 }
    if (Test-Path $LogPath) {
        Say "$LogPath already exists. Refusing to overwrite a log." "Red"
        Say "Measurement provenance depends on one log per configuration; pick a new name." "Yellow"
        exit 2
    }

    $state = Get-LogButton
    if (-not $state) { Say "No Sensors window / log button found." "Red"; exit 4 }
    if ($state.Label -match "Stop") {
        Say "Logging is ALREADY running - the button reads 'Log Stop'." "Red"
        Say "Stop it first. Starting a second log would leave the first one's path unknown." "Yellow"
        exit 5
    }

    Say ""
    Say "Pressing 'Log Start' (async - it opens a modal dialog)..." "Cyan"
    [HwiUi]::PressAsync($state.Dialog, $state.Button)

    $dialog = $null
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 250
        $dialog = Get-SaveDialog
        if ($dialog) { break }
    }
    if (-not $dialog) { Say "The Save As dialog never appeared." "Red"; exit 6 }

    $edit = $null
    foreach ($kid in [HwiUi]::Children($dialog)) {
        if ([HwiUi]::Cls($kid) -eq "Edit") { $edit = $kid; break }
    }
    if (-not $edit) { Say "No filename box in the Save As dialog." "Red"; exit 6 }

    Say "Setting the filename, with the change notification the dialog needs..." "Gray"
    [HwiUi]::SetFileName($dialog, $edit, $LogPath)
    Start-Sleep -Milliseconds 600
    [HwiUi]::PressAsync($dialog, [HwiUi]::GetDlgItem($dialog, [HwiUi]::IDOK))

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 250
        if (-not (Get-SaveDialog)) { break }
    }
    if (Get-SaveDialog) { Say "The Save As dialog did not accept the filename." "Red"; exit 6 }

    # ---- verify by GROWTH, not by the click returning ----
    # A label that says 'Log Stop' only proves the button toggled. Two increasing sizes prove
    # samples are reaching the disk, which is the thing the run actually depends on.
    Start-Sleep -Seconds 3
    $first = Get-FileSize $LogPath
    Start-Sleep -Seconds 4
    $second = Get-FileSize $LogPath
    $after = Get-LogButton

    Say ""
    Say ("  button now : '{0}'" -f $after.Label)
    Say ("  file       : {0}" -f $LogPath)
    Say ("  size       : {0} then {1} bytes" -f $first, $second)

    if ($first -lt 0) { Say "The log file was never created. Logging did NOT start." "Red"; exit 7 }
    if ($second -le $first) {
        Say "The file exists but is not growing. Treat this run as invalid." "Red"
        Say "HWiNFO can hold a handle open and write nothing if the sensor set is empty." "Yellow"
        exit 7
    }
    if ($after.Label -notmatch "Stop") { Say "The button did not switch to 'Log Stop'." "Red"; exit 7 }

    Say ""
    Say "Logging is running and the file is growing." "Green"
    exit 0
}

# ---- stop ------------------------------------------------------------------------------------

if ($Stop) {
    $state = Get-LogButton
    if (-not $state) { Say "No Sensors window / log button found." "Red"; exit 4 }
    if ($state.Label -notmatch "Stop") {
        Say "Logging is not running - the button reads 'Log Start'." "Yellow"
        Say "Nothing to stop. This is reported rather than treated as success, because a" "Yellow"
        Say "silent no-op here would mean a sweep ran with no voltage log at all." "Yellow"
        exit 5
    }

    Say "Pressing 'Log Stop'..." "Cyan"
    [HwiUi]::PressAsync($state.Dialog, $state.Button)
    Start-Sleep -Seconds 4

    $after = Get-LogButton
    Say ("  button now : '{0}'" -f $after.Label)
    if ($after.Label -match "Stop") { Say "The button did not switch back. Logging may still be running." "Red"; exit 7 }

    if ($LogPath) {
        # Confirm it is really finished: a size that still moves means it did not stop.
        $a = Get-FileSize $LogPath
        Start-Sleep -Seconds 5
        $b = Get-FileSize $LogPath
        Say ("  size       : {0} then {1} bytes" -f $a, $b)
        if ($b -ne $a) { Say "The file is still growing. Logging did NOT stop." "Red"; exit 7 }
        if ($b -gt 0) {
            $rows = (Get-Content $LogPath | Measure-Object -Line).Lines
            Say ("  rows       : {0}" -f $rows)
        }
    }

    Say ""
    Say "Logging stopped." "Green"
    exit 0
}
