@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" -BootstrapUser -BuildFrontend %*
exit /b %errorlevel%
