#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_ROOT"
"${PYTHON:-python3}" -m venv backend/.venv
backend/.venv/bin/python -m pip install -c backend/requirements.lock -e './backend[dev]'
backend/.venv/bin/python -m geopol.cli init-db
(cd frontend && npm ci)
printf '%s\n' 'Dependencias y esquema listos. Crea un usuario con la CLI (ver README) y ejecuta api, worker y frontend en terminales separadas.'
