@echo off
setlocal
title AI Monitor
cd /d "%~dp0"
if exist "%~dp0AI-Monitor.exe" (
  start "" "%~dp0AI-Monitor.exe"
  exit /b
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  if errorlevel 1 goto failed
)
"%~dp0.venv\Scripts\python.exe" -c "import serial, psutil, PySide6.QtWidgets" >nul 2>&1
if errorlevel 1 (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  if errorlevel 1 goto failed
)
"%~dp0.venv\Scripts\python.exe" -c "import serial, psutil, PySide6.QtWidgets" >nul 2>&1
if errorlevel 1 (
  echo Required application components could not load after setup.
  echo Use the complete Windows release or check the Python installation and DLL error.
  goto failed
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0tools\aim_desktop.py"
exit /b 0
:failed
echo.
echo Setup or startup failed. Read the message above, then try again.
pause
exit /b 1
