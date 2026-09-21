@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1" %*
set "RUN_RESULT=%ERRORLEVEL%"
if "%~1"=="" if not "%XIGE_SCREEN_NONINTERACTIVE%"=="1" pause
exit /b %RUN_RESULT%
