@echo off
setlocal DisableDelayedExpansion
title Install LimitBuddy
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-LimitBuddy.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation failed. Read the error above; existing settings were preserved.
  pause
  exit /b 1
)
echo.
echo LimitBuddy is ready. Open a new terminal and type: limitbuddy
pause
exit /b 0
