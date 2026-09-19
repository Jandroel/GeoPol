param([Parameter(Mandatory)][ValidateSet('api', 'worker', 'frontend')][string]$Service)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'

switch ($Service) {
    'api' { & $pythonExecutable -m uvicorn geopol.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log }
    'worker' { & $pythonExecutable -m geopol.worker }
    'frontend' {
        Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
        try { & npm run dev -- --host 127.0.0.1 } finally { Pop-Location }
    }
}
if ($LASTEXITCODE -ne 0) { throw "El servicio $Service terminó con código $LASTEXITCODE." }
