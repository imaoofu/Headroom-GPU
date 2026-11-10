# Desktop-load test, 2026-10-03: is the Claude window the ~200 fps / bus-load source seen on 10-01?
# ABA on stock P3: membw at 1402/1560/1710/1867 with the Claude window in front, minimized, in front.
# Exploratory, not registered. Uses the repository's own wrapper, so each run logs HWiNFO and writes
# gpu-processes-at-start.txt.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\Raymond\Documents\headroom"
$ab = "${env:ProgramFiles(x86)}\MSI Afterburner\MSIAfterburner.exe"
$wrapper = Join-Path $repo "tools\hwinfo-logging\Invoke-LoggedSweep.ps1"
$jobDir = "C:\headroom-bench\deskload-20261003"
New-Item -ItemType Directory -Force -Path $jobDir | Out-Null
$log = Join-Path $jobDir "run.log"
function Say([string]$t) { $l = "[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $t; Write-Host $l; Add-Content -Path $log -Value $l }
Add-Type @'
using System; using System.Runtime.InteropServices;
public class Win { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p); }
'@
function ClaudeWindows { @(Get-Process -Name claude -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object { $_.MainWindowHandle }) }
function Foreground { $p = [uint32]0; [void][Win]::GetWindowThreadProcessId([Win]::GetForegroundWindow(), [ref]$p); (Get-Process -Id $p -ErrorAction SilentlyContinue).ProcessName }
function SetClaude([string]$state) {
    foreach ($h in ClaudeWindows) {
        if ($state -eq "min") { [void][Win]::ShowWindow($h, 6) } else { [void][Win]::ShowWindow($h, 9); [void][Win]::SetForegroundWindow($h) }
    }
    Start-Sleep -Seconds 5
    Say ("Claude window {0}; foreground is now {1}." -f $state, (Foreground))
}
function RunSweep([string]$label, [string]$state) {
    $job = @{ label = $label; workload = "membw"; targets = @(1402, 1560, 1710, 1867); expectedMinutes = 4
              appliedSettings = "STOCK Afterburner Profile 3 (180 W, memory +0), mVolt+ offsets 0, driver 616.92. Desktop-load test 2026-10-03, exploratory: Claude window $state. Opera, Discord, ChatGPT closed; operator away." }
    $path = Join-Path $jobDir "$label.json"
    [IO.File]::WriteAllText($path, ($job | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Say "sweep $label ($state)"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -JobPath $path *>> (Join-Path $jobDir "$label.out.txt")
    Say "exit $LASTEXITCODE for $label"
}
Say "Desktop-load test starting."
& $ab -profile3 -q; Start-Sleep -Seconds 30
& (Join-Path $repo "tools\hwinfo-logging\Start-HwinfoSensors.ps1") *>> $log
Say ("Power limit {0} W." -f ((& nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits) | Select-Object -First 1).Trim())
try {
    SetClaude "front";  Start-Sleep -Seconds 30; RunSweep "deskload-a1-visible-membw" "visible, in front"
    SetClaude "min";    Start-Sleep -Seconds 30; RunSweep "deskload-b-minimized-membw" "minimized"
    SetClaude "front";  Start-Sleep -Seconds 30; RunSweep "deskload-a2-visible-membw" "visible, in front"
}
finally {
    & nvidia-smi -rgc | Out-Null
    SetClaude "front"
    Say "Done. Clocks reset."
}
