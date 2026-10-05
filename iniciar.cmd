@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
    echo Primero ejecuta .\instalar.cmd
    exit /b 1
)
"backend\.venv\Scripts\python.exe" "scripts\run_local.py" %*
exit /b %errorlevel%
