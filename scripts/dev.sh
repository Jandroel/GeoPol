#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_ROOT"
case "${1:-}" in
  api) exec backend/.venv/bin/python -m uvicorn geopol.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log ;;
  worker) exec backend/.venv/bin/python -m geopol.worker ;;
  frontend) cd frontend; exec npm run dev -- --host 127.0.0.1 ;;
  *) printf '%s\n' 'Uso: bash scripts/dev.sh api|worker|frontend' >&2; exit 2 ;;
esac
