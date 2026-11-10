# Desktop observation and window minimization only. No GPU settings are changed.
function Initialize-BenchWindows {
    if ('HeadroomBench.Desktop' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
namespace HeadroomBench {
    public static class Desktop {
        public delegate bool EnumProc(IntPtr h, IntPtr l);
        [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
        [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
        [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
        public static IntPtr[] VisibleWindows(uint id) {
            var result = new List<IntPtr>();
            EnumWindows(delegate(IntPtr h, IntPtr l) {
                uint p; GetWindowThreadProcessId(h, out p);
                if (p == id && IsWindowVisible(h)) result.Add(h);
                return true;
            }, IntPtr.Zero);
            return result.ToArray();
        }
    }
}
'@
}

function Measure-BenchGpuUsers($samples, [int]$sampleCount=2) {
    $engine=@{}
    foreach ($sample in @($samples)) {
        if ($sample.InstanceName -match 'pid_(\d+)_.*engtype_(.+)$') {
            $processId=[int]$Matches[1]; $kind=[string]$Matches[2]
            $key="$processId/$kind"
            if (-not $engine.ContainsKey($key)) { $engine[$key]=@{ pid=$processId; engine=$kind; percent=0.0 } }
            $engine[$key].percent += [double]$sample.CookedValue / $sampleCount
        }
    }
    # Keep PIDs distinct even when several processes have the same executable name.
    return @($engine.Values | Where-Object { $_.percent -gt 0.1 } | Sort-Object { $_.percent } -Descending)
}

function Get-BenchDesktopSnapshot($mock=$null) {
    $result=@{ timestamp=(Get-Date).ToString('o'); foreground=$null; gpuUsers=@(); errors=@(); mocked=($null -ne $mock) }
    try {
        if ($null -ne $mock) { $result.foreground=$mock.foreground }
        else {
            Initialize-BenchWindows
            $h=[HeadroomBench.Desktop]::GetForegroundWindow()
            $foregroundPid=[uint32]0
            [void][HeadroomBench.Desktop]::GetWindowThreadProcessId($h,[ref]$foregroundPid)
            $title=New-Object Text.StringBuilder 1024
            [void][HeadroomBench.Desktop]::GetWindowText($h,$title,$title.Capacity)
            $name=(Get-Process -Id $foregroundPid -ErrorAction SilentlyContinue).ProcessName
            $result.foreground=@{ pid=$foregroundPid; process=$name; title=$title.ToString(); handle=$h.ToInt64() }
        }
    } catch { $result.errors+=('Foreground window not recorded: '+$_.Exception.Message) }
    try {
        if ($null -ne $mock) {
            if ($mock.counterError) { throw [string]$mock.counterError }
            $samples=@($mock.samples)
        } else {
            $samples=@((Get-Counter '\GPU Engine(*)\Utilization Percentage' -SampleInterval 2 -MaxSamples 2 -ErrorAction Stop).CounterSamples)
        }
        $result.gpuUsers=@(Measure-BenchGpuUsers $samples)
        foreach ($user in $result.gpuUsers) {
            $name=if ($null -ne $mock) { 'mock-process' } else { (Get-Process -Id $user.pid -ErrorAction SilentlyContinue).ProcessName }
            $user.process=if ($name) { [string]$name } else { 'pid '+$user.pid }
        }
    } catch { $result.errors+=('GPU engine counters not recorded: '+$_.Exception.Message) }
    return $result
}

function Minimize-BenchRenderers($names, [bool]$mocked=$false, $mockWindows=@()) {
    $names=@($names | Where-Object { $null -ne $_ })
    $result=@{ names=@($names); windows=@(); errors=@(); mocked=$mocked }
    $windows=@()
    try {
        if ($mocked) { $windows=@($mockWindows | Where-Object { @($names) -contains $_.process }) }
        elseif (@($names).Count -gt 0) {
            Initialize-BenchWindows
            foreach ($name in @($names)) {
                foreach ($process in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
                    foreach ($h in @([HeadroomBench.Desktop]::VisibleWindows([uint32]$process.Id))) {
                        $windows+=@{ pid=$process.Id; process=$name; handle=$h.ToInt64(); alreadyMinimized=[HeadroomBench.Desktop]::IsIconic($h) }
                    }
                }
            }
        }
        $changed=0
        foreach ($window in $windows) {
            $verified=[bool]$window.alreadyMinimized
            if (-not $verified) {
                if ($mocked) { $verified=(-not [bool]$window.fail) }
                else { [void][HeadroomBench.Desktop]::ShowWindow([IntPtr]$window.handle,6); $verified=[HeadroomBench.Desktop]::IsIconic([IntPtr]$window.handle) }
                if ($verified) { $changed++ }
            }
            $result.windows+=@{ pid=$window.pid; process=$window.process; handle=$window.handle; alreadyMinimized=[bool]$window.alreadyMinimized; minimizedVerified=$verified }
            if (-not $verified) { $result.errors+=('Could not verify minimized window '+$window.handle+' of '+$window.process+'.') }
        }
        if ($changed -gt 0 -and -not $mocked) { Start-Sleep -Seconds 5 }
    } catch { $result.errors+=$_.Exception.Message }
    return $result
}

function Invoke-BenchDesktopCheck([string]$python, [string]$checker, $sweepFiles, [string]$log, [string]$utcOffset) {
    $arguments=@($checker,'--hwinfo-log',$log,"--utc-offset=$utcOffset")
    foreach ($file in @($sweepFiles)) { $arguments+=@('--sweep',[string]$file) }
    $output=@(& $python @arguments 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Desktop-load checker exited $LASTEXITCODE : $($output -join ' ')" }
    $result=($output -join "`n") | ConvertFrom-Json
    if (@('quiet','DESKTOP LOAD','unchecked') -notcontains $result.status) { throw 'Desktop-load checker returned an invalid status.' }
    return $result
}
