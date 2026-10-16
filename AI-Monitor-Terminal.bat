@echo off
setlocal
title AI Monitor Terminal
cd /d "%~dp0"
if exist "%~dp0AI-Monitor-Terminal.exe" (
  "%~dp0AI-Monitor-Terminal.exe" %*
  exit /b %errorlevel%
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run setup.ps1 from this directory first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -c "import textual" >nul 2>&1
if errorlevel 1 (
  echo Install terminal dependencies: .venv\Scripts\python.exe -m pip install -r tools\requirements.txt
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\aim_terminal.py" %*
exit /b %errorlevel%
