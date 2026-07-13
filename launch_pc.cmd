@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch_pc.ps1" %*
if errorlevel 1 pause
endlocal
