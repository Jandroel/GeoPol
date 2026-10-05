#!/usr/bin/env bash
# Install/start the application directly on Windows (Git Bash) or Linux.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_ROOT"
fail() { printf '\n%s\n' "$*" >&2; exit 1; }
trap 'printf "\nNo se completó la operación. Revisa el error anterior. Tus datos se conservan.\n" >&2' ERR
action="${1:-}"
[[ "$action" =~ ^(install|start|stop)$ ]] || fail 'Usa bash instalar.sh, bash iniciar.sh o bash detener.sh.'
shift
port_args=()
configure_ports=()
if (( $# )); then
    [[ $# -eq 3 && "$1" == --puertos && "$action" != stop ]] || fail 'Opción disponible: --puertos 5174 8002 (web y API).'
    for port in "$2" "$3"; do
        [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail 'Los puertos deben estar entre 1 y 65535, sin ceros iniciales.'
    done
    [[ "$2" != "$3" ]] || fail 'La web y la API necesitan puertos distintos.'
    port_args=(--port "$2" --api-port "$3")
    configure_ports=(--web-port "$2" --api-port "$3")
fi
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) venv_python=backend/.venv/Scripts/python.exe; python_default=python ;;
    *) venv_python=backend/.venv/bin/python; python_default=python3 ;;
esac

if [[ "$action" == stop ]]; then
    [[ -f "$venv_python" ]] || fail 'No se encontró una instalación. Ejecuta bash instalar.sh primero.'
    exec "$venv_python" scripts/run_local.py --native --stop
fi
if [[ "$action" == start ]]; then
    [[ -f "$venv_python" ]] || fail 'Primero ejecuta bash instalar.sh.'
    [[ -f .local/native.json ]] || fail 'Primero configura PostgreSQL con bash instalar.sh.'
    if (( ${#configure_ports[@]} )); then
        "$venv_python" scripts/configure_postgres.py "${configure_ports[@]}" < /dev/null
    fi
    exec "$venv_python" -u scripts/run_local.py --native "${port_args[@]}"
fi

python_command="${PYTHON:-$python_default}"
command -v "$python_command" >/dev/null 2>&1 || fail 'Falta Python. Instala Python 3.11 o superior, abre una terminal nueva y repite este comando.'
"$python_command" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else "Se necesita Python 3.11 o superior.")'
command -v node >/dev/null 2>&1 || fail 'Falta Node.js. Instala Node.js 24 o superior y abre otra terminal Bash.'
command -v npm >/dev/null 2>&1 || fail 'Falta npm. Vuelve a instalar Node.js con npm incluido.'
node -e 'if(Number(process.versions.node.split(".")[0])<24){console.error("Se necesita Node.js 24 o superior.");process.exit(1)}'
if [[ ! -f "$venv_python" ]]; then
    [[ ! -d backend/.venv ]] || fail 'El entorno Python pertenece a otro sistema. Usa una copia nueva del código; no copies .venv ni node_modules entre computadoras.'
    "$python_command" -m venv backend/.venv
fi
printf '\n%s\n' '1/3 Instalando las dependencias y preparando la interfaz...'
"$venv_python" -m pip install -c backend/requirements.lock -e './backend[dev]' < /dev/null
(cd frontend && npm ci < /dev/null && npm run build < /dev/null)

printf '\n%s\n' '2/3 Configurando PostgreSQL local...'
if [[ ! -f .local/native.json ]]; then
    prompt_setting() {
        local variable="$1" label="$2" default="$3" answer
        if [[ ! -v "$variable" ]]; then
            IFS= read -r -p "$label [$default]: " answer || fail 'Falta completar la configuración. Ejecuta el instalador desde Bash.'
            printf -v "$variable" '%s' "${answer:-$default}"
        fi
        export "$variable"
    }
    if [[ -f .local/native.pending.json ]]; then
        printf '%s\n' 'Se retomará la instalación pendiente con el servidor y la base ya guardados.'
        admin_default="$("$venv_python" -c '
import json
import sys
from pathlib import Path
try:
    admin = json.loads(Path(".local/native.pending.json").read_text(encoding="utf-8"))["admin_user"]
    if not isinstance(admin, str) or not admin.strip() or not admin.isprintable():
        raise ValueError
except (OSError, ValueError, KeyError, TypeError):
    raise SystemExit("La configuración pendiente no contiene un administrador válido. Consérvala para recuperar la instalación.") from None
sys.stdout.buffer.write(admin.encode("utf-8"))
' < /dev/null)"
    else
        printf '%s\n' 'PostgreSQL debe estar instalado y encendido, con PostGIS disponible.' 'Pulsa Enter para aceptar cada valor sugerido.'
        prompt_setting GEOPOL_SETUP_PGHOST 'Servidor' '127.0.0.1'
        prompt_setting GEOPOL_SETUP_PGPORT 'Puerto PostgreSQL' '5432'
        prompt_setting GEOPOL_SETUP_PGDATABASE 'Nombre de una base nueva' 'geopol'
        admin_default=postgres
    fi
    prompt_setting GEOPOL_SETUP_PGUSER 'Administrador de PostgreSQL' "$admin_default"
    if [[ ! -v GEOPOL_SETUP_PGPASSWORD ]]; then
        IFS= read -r -s -p 'Contraseña de PostgreSQL (la elegida al instalar PostgreSQL): ' GEOPOL_SETUP_PGPASSWORD || fail 'No se recibió la contraseña de PostgreSQL.'
        printf '\n'
    fi
    export GEOPOL_SETUP_PGPASSWORD
    unset admin_default
fi
"$venv_python" scripts/configure_postgres.py "${configure_ports[@]}" < /dev/null
unset GEOPOL_SETUP_PGPASSWORD
"$venv_python" scripts/native_cli.py init-db < /dev/null

printf '\n%s\n' '3/3 Preparando tu cuenta de GeoPol...'
has_user="$("$venv_python" scripts/native_cli.py has-users < /dev/null | tr -d '\r')"
case "$has_user" in
    yes) printf '%s\n' 'Se conservan las cuentas existentes.' ;;
    no)
        if [[ -n "${GEOPOL_BOOTSTRAP_PASSWORD:-}" ]]; then
            account_password="$GEOPOL_BOOTSTRAP_PASSWORD"
        else
            printf '%s\n' 'Usuario: administrador. Elige una contraseña web distinta de la de PostgreSQL, de al menos 12 caracteres.'
            while true; do
                IFS= read -r -s -p 'Contraseña para GeoPol: ' account_password || fail 'No se recibió la contraseña para GeoPol.'
                printf '\n'
                (( ${#account_password} >= 12 )) || { printf '%s\n' 'Utiliza al menos 12 caracteres.'; continue; }
                IFS= read -r -s -p 'Repite la contraseña: ' confirmation || fail 'Falta confirmar la contraseña.'
                printf '\n'
                [[ "$account_password" == "$confirmation" ]] && break
                printf '%s\n' 'Las contraseñas no coinciden. Inténtalo nuevamente.'
            done
        fi
        printf '%s' "$account_password" | "$venv_python" scripts/native_cli.py bootstrap-user --password-stdin
        unset account_password confirmation
        ;;
    *) fail 'No se pudo comprobar la cuenta inicial.' ;;
esac
printf '\n%s\n' 'Instalación lista. Ejecuta bash iniciar.sh para abrir GeoPol.'
