@echo off
setlocal DisableDelayedExpansion
title Install NOVA Terminal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Nova.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation failed. Read the error above; existing settings were preserved.
  pause
  exit /b 1
)
echo.
echo NOVA is ready. Open a new terminal and type: nova
pause
exit /b 0
