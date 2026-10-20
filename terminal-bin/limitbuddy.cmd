@echo off
setlocal DisableDelayedExpansion
call "%~dp0..\AI-Monitor-Terminal.bat" %*
exit /b %errorlevel%
