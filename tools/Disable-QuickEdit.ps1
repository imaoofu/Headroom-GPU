<#
.SYNOPSIS
    Turns off console QuickEdit mode, so a stray mouse click cannot freeze a long run.

.DESCRIPTION
    Windows consoles enable QuickEdit by default. With it on, a single click inside the window puts
    the console into selection mode, and SELECTION MODE BLOCKS ALL OUTPUT TO THAT CONSOLE. Any
    script that writes progress then stops dead on its next write.

    The failure is silent and looks nothing like a bug in the script:

      * no error, no exception, no exit code
      * the process stays alive, responsive, using almost no CPU
      * whatever GPU state was applied stays applied - a clock lock is NOT released
      * the only visible trace is the word "Select" prepended to the window title

    It cost this project six minutes of a 30-minute unattended sweep, with the card left clock-
    locked and idle the whole time, and it corrupted the two frequency points either side of the
    stall. Both long-running elevated tools here dot-source this file at startup.

    Recovery, if it ever happens anyway: click the console window and press Esc. The script resumes
    exactly where it stopped.

.NOTES
    Dot-source it:  . (Join-Path $PSScriptRoot "..\Disable-QuickEdit.ps1")
    Then call:      Disable-ConsoleQuickEdit -Tag "SWEEP"

    Must degrade gracefully. There is no console at all under a scheduled task or a redirected
    session, and a stress test that refuses to start over a mouse-handling nicety would be a worse
    outcome than the hazard it protects against.
#>

function Disable-ConsoleQuickEdit {
    param([string]$Tag = "TOOL")

    $signature = @'
using System;
using System.Runtime.InteropServices;
public static class HeadroomConsoleMode {
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr GetStdHandle(int nStdHandle);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
    public static bool DisableQuickEdit() {
        IntPtr handle = GetStdHandle(-10);              // STD_INPUT_HANDLE
        if (handle == IntPtr.Zero || handle == new IntPtr(-1)) { return false; }
        uint mode;
        if (!GetConsoleMode(handle, out mode)) { return false; }   // no real console attached
        mode &= ~(uint)0x0040;                          // clear ENABLE_QUICK_EDIT_MODE
        mode |= 0x0080;                                 // ENABLE_EXTENDED_FLAGS, required for the clear to take
        return SetConsoleMode(handle, mode);
    }
}
'@

    try {
        if (-not ("HeadroomConsoleMode" -as [type])) {
            Add-Type -TypeDefinition $signature -ErrorAction Stop
        }
        if ([HeadroomConsoleMode]::DisableQuickEdit()) {
            return $true
        }
        # A non-interactive session has no console to protect, which is fine and not worth a warning.
        Write-Host "[$Tag] NOTE: QuickEdit could not be disabled (likely no interactive console). If this window is interactive, DO NOT CLICK IN IT - a click freezes the run."
        return $false
    } catch {
        Write-Host "[$Tag] NOTE: QuickEdit could not be disabled ($($_.Exception.Message)). DO NOT CLICK IN THIS WINDOW - a click freezes the run."
        return $false
    }
}
