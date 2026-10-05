param(
    [string]$PythonCommand = 'python',
    [switch]$BootstrapUser,
    [switch]$BuildFrontend
)
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
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del frontend. Requiere Node.js 24 y npm.' }
    if ($BuildFrontend) {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación del frontend.' }
    }
} finally { Pop-Location }
if ($BootstrapUser) {
    & $pythonExecutable -m geopol.cli bootstrap-user
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo completar la configuración del usuario inicial.' }
}
if ($BootstrapUser -and $BuildFrontend) {
    Write-Host 'Instalación lista. Ejecuta .\iniciar.cmd para abrir GeoPol.'
} else {
    Write-Host 'Dependencias y esquema listos. Crea un usuario con la CLI (ver README) y ejecuta api, worker y frontend en terminales separadas.'
}
