@echo off
setlocal
powershell.exe -NoProfile -Command "$p=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent()); if($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){exit 0}else{exit 1}" >nul 2>&1
if %errorlevel% neq 0 (
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
set "BENCH_WINDOW=%~dp0tools\bench-app\Bench-Window.ps1"
if not exist "%BENCH_WINDOW%" set "BENCH_WINDOW=%~dp0Bench-Window.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BENCH_WINDOW%"
exit /b %errorlevel%
