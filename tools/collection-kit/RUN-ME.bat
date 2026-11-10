@echo off
REM Headroom collection kit - double-click this file.
REM
REM Self-elevates, because locking GPU clocks needs Administrator. The UAC prompt is
REM expected; click Yes. Everything runs from this folder - nothing is installed.

setlocal

net session >nul 2>&1
if %errorLevel% == 0 goto :elevated

echo.
echo  Headroom collection kit
echo.
echo  Asking for Administrator (needed to lock GPU clocks)...
echo  Click YES on the prompt that appears.
echo.
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b

:elevated
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Collect.ps1"
exit /b
