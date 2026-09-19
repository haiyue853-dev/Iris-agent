@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-wecom-aibot.ps1"
if errorlevel 1 (
  echo.
  echo Configuration failed. See the error above.
)
pause
