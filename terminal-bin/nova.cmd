@echo off
setlocal DisableDelayedExpansion
if exist "%~dp0..\AI-Monitor-Console.exe" (
  "%~dp0..\AI-Monitor-Console.exe" --terminal %*
) else (
  call "%~dp0..\AI-Monitor-Terminal.bat" %*
)
exit /b %errorlevel%
