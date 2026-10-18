@echo off
setlocal
rem This window uses full color even when launched by a monochrome coding runner.
set NO_COLOR=
set TERM=xterm-256color
set COLORTERM=truecolor
set TEXTUAL_COLOR_SYSTEM=truecolor
title AI Monitor Terminal
cd /d "%~dp0"
set "NOVA_PYTHON=%AI_MONITOR_PYTHON%"
set "NOVA_BUNDLED="
if not defined NOVA_PYTHON if exist "%~dp0runtime\python.exe" (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verify_terminal_runtime.ps1" -Root "%~dp0" >nul
  if errorlevel 1 (
    echo The bundled runtime failed its integrity check. Extract the complete Windows ZIP again.
    pause
    exit /b 1
  )
  set "NOVA_PYTHON=%~dp0runtime\python.exe"
  set "NOVA_BUNDLED=1"
)
if not defined NOVA_PYTHON set "NOVA_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%NOVA_PYTHON%" (
  echo Preparing AI Monitor terminal dependencies for the first start...
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  if errorlevel 1 exit /b 1
)
"%NOVA_PYTHON%" -B -c "import textual" >nul 2>&1
if errorlevel 1 (
  if defined NOVA_BUNDLED (
    echo The bundled runtime is incomplete. Extract the complete Windows ZIP again.
  ) else (
    echo Install terminal dependencies: .venv\Scripts\python.exe -m pip install -r tools\requirements.txt
  )
  pause
  exit /b 1
)
"%NOVA_PYTHON%" -B "%~dp0tools\aim_terminal.py" %*
exit /b %errorlevel%
