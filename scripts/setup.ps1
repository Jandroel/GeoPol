param([string]$PythonCommand = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot

& $PythonCommand -m venv backend/.venv
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python. Requiere Python 3.11 o superior.' }
$pythonExecutable = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
& $pythonExecutable -m pip install -c backend/requirements.lock -e './backend[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del backend.' }
& $pythonExecutable -m geopol.cli init-db
if ($LASTEXITCODE -ne 0) { throw 'Falló la inicialización de la base de datos.' }
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del frontend. Requiere Node.js 24 y npm.' }
} finally { Pop-Location }
Write-Host 'Dependencias y esquema listos. Crea un usuario con la CLI (ver README) y ejecuta api, worker y frontend en terminales separadas.'
