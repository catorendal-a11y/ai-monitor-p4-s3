@echo off
rem Compatibility launcher: NOVA is a terminal application.
call "%~dp0AI-Monitor-Terminal.bat" %*
exit /b %errorlevel%
