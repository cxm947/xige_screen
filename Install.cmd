@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows.ps1" %*
set "INSTALL_RESULT=%ERRORLEVEL%"
if not "%XIGE_SCREEN_NONINTERACTIVE%"=="1" pause
exit /b %INSTALL_RESULT%
