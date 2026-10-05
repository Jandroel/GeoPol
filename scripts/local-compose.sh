#!/usr/bin/env bash
# Simple local PostgreSQL installation; shared by the three Bash entry points.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_ROOT"
CONFIG_FILE=.local/compose.env
COMPOSE_PROJECT=geopol-local

fail() { printf '\n%s\n' "$*" >&2; exit 1; }
trap 'printf "\nNo se completó la operación. Revisa el error anterior. Tus datos no se han eliminado.\n" >&2' ERR

action="${1:-}"
[[ "$action" =~ ^(install|start|stop)$ ]] || fail 'Utiliza bash instalar.sh, bash iniciar.sh o bash detener.sh.'
shift
requested_web=''
requested_api=''
if (( $# )); then
    [[ $# -eq 3 && "$1" == --puertos && "$action" != stop ]] || fail 'Opción disponible: bash instalar.sh --puertos 8081 8003 (web y API).'
    requested_web="$2"
    requested_api="$3"
    for port in "$requested_web" "$requested_api"; do
        [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail 'Los puertos deben ser números entre 1 y 65535, sin ceros iniciales.'
    done
    [[ "$requested_web" != "$requested_api" ]] || fail 'La web y la API deben utilizar puertos diferentes.'
fi
command -v docker >/dev/null 2>&1 || fail 'Falta Docker. Instálalo siguiendo INSTALACION_LOCAL.md y vuelve a abrir Bash.'
docker info --format '{{.OSType}}' > /dev/null 2>&1 || fail 'Docker no está disponible. Abre Docker Desktop (o inicia Docker Engine) y vuelve a intentar.'
[[ "$(docker info --format '{{.OSType}}')" == linux ]] || fail 'GeoPol necesita contenedores Linux. Selecciona ese modo en Docker Desktop.'
compose_version="$(docker compose version --short)" || fail 'Falta Docker Compose. Revisa la instalación de Docker.'
[[ "$compose_version" =~ ^v?([0-9]+)\.([0-9]+) ]] || fail 'No se pudo reconocer la versión de Docker Compose.'
(( BASH_REMATCH[1] > 2 || (BASH_REMATCH[1] == 2 && BASH_REMATCH[2] >= 20) )) || fail 'Actualiza Docker Compose: se necesita la versión 2.20 o posterior.'

# Always use the saved configuration, even if another application's variables
# are exported in the shell. Never source an environment file as shell code.
compose() (
    unset POSTGRES_PASSWORD GEOPOL_ALLOWED_ORIGINS GEOPOL_WEB_PORT GEOPOL_API_PORT
    docker compose --project-name "$COMPOSE_PROJECT" --env-file "$CONFIG_FILE" --file compose.yaml "$@"
)

if [[ ! -f "$CONFIG_FILE" ]]; then
    [[ "$action" == install ]] || fail 'Primero ejecuta bash instalar.sh desde esta carpeta.'
    previous_volumes="$(docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}')"
    [[ -z "$previous_volumes" ]] || fail 'Ya existen datos de GeoPol en Docker, pero falta .local/compose.env. Recupera ese archivo de la instalación anterior; no se generó otra contraseña.'
    web_port="${requested_web:-${GEOPOL_WEB_PORT:-8080}}"
    api_port="${requested_api:-${GEOPOL_API_PORT:-8000}}"
    for port in "$web_port" "$api_port"; do
        [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail 'Los puertos deben ser números entre 1 y 65535, sin ceros iniciales.'
    done
    [[ "$web_port" != "$api_port" ]] || fail 'La web y la API deben utilizar puertos diferentes.'
    umask 077
    mkdir -p .local
    database_password="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    [[ "$database_password" =~ ^[a-f0-9]{64}$ ]] || fail 'No se pudo generar la contraseña de PostgreSQL.'
    # noclobber also prevents two first-time installers from replacing a secret.
    (set -o noclobber; printf 'POSTGRES_PASSWORD=%s\nGEOPOL_WEB_PORT=%s\nGEOPOL_API_PORT=%s\n' "$database_password" "$web_port" "$api_port" > "$CONFIG_FILE")
    unset database_password
    printf '%s\n' 'Configuración de PostgreSQL preparada. La contraseña técnica se guarda en .local/compose.env.'
fi

# Parse only these simple fields, without evaluating expressions from the file.
saved_value() { sed -n "s/^$1=//p" "$CONFIG_FILE" | tr -d '\r'; }
saved_password="$(saved_value POSTGRES_PASSWORD)"
[[ "$saved_password" =~ ^[a-f0-9]{64}$ ]] || fail 'La configuración de PostgreSQL no es válida. Recupera .local/compose.env original; no cambies la contraseña si ya tienes datos.'
unset saved_password
web_port="$(saved_value GEOPOL_WEB_PORT)"
api_port="$(saved_value GEOPOL_API_PORT)"
for port in "$web_port" "$api_port"; do
    [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail 'Revisa GEOPOL_WEB_PORT y GEOPOL_API_PORT en .local/compose.env.'
done
[[ "$web_port" != "$api_port" ]] || fail 'La web y la API deben utilizar puertos diferentes.'
if [[ -n "$requested_web" ]]; then
    # A failed first start may already have saved its configuration. Change only
    # ports on explicit request; the database secret and volumes remain intact.
    umask 077
    temporary_config="$(mktemp .local/compose.env.XXXXXX)"
    sed -e "s/^GEOPOL_WEB_PORT=.*/GEOPOL_WEB_PORT=$requested_web/" \
        -e "s/^GEOPOL_API_PORT=.*/GEOPOL_API_PORT=$requested_api/" \
        "$CONFIG_FILE" > "$temporary_config"
    mv -- "$temporary_config" "$CONFIG_FILE"
    web_port="$requested_web"
    api_port="$requested_api"
fi
compose config --quiet

if [[ "$action" == stop ]]; then
    compose stop
    printf '\n%s\n' 'GeoPol detenido. Se conservan la base de datos, las cuentas y los archivos.'
    exit 0
fi

if [[ "$action" == install ]]; then
    printf '\n%s\n' 'Preparando GeoPol y PostgreSQL. La primera vez puede tardar varios minutos.'
    compose build
fi
printf '\n%s\n' 'Iniciando la base de datos, la aplicación y el procesamiento...'
compose up --detach --wait --wait-timeout 180

# Bash owns the masked prompt; exec -T works in Git Bash/MinTTY as well as Linux.
# The password travels through stdin, never through command arguments or a file.
has_user="$(compose exec -T api python -c 'from sqlalchemy import select; from geopol.db import SessionLocal; from geopol.models import User; db=SessionLocal(); print("yes" if db.scalar(select(User.id).limit(1)) else "no"); db.close()' | tr -d '\r')"
case "$has_user" in
    yes) ;;
    no)
        printf '\n%s\n' 'Crea tu acceso a la web. Usuario: administrador.' 'Elige una contraseña de al menos 12 caracteres. No se mostrará al escribir.'
        while true; do
            IFS= read -r -s -p 'Contraseña: ' account_password || fail 'No se recibió la contraseña. Vuelve a ejecutar bash instalar.sh en tu terminal.'
            printf '\n'
            (( ${#account_password} >= 12 )) || { printf '%s\n' 'Utiliza al menos 12 caracteres.'; continue; }
            IFS= read -r -s -p 'Repite la contraseña: ' confirmation || fail 'Falta confirmar la contraseña. Vuelve a ejecutar bash instalar.sh.'
            printf '\n'
            [[ "$account_password" == "$confirmation" ]] && break
            printf '%s\n' 'Las contraseñas no coinciden. Inténtalo nuevamente.'
        done
        printf '%s' "$account_password" | compose exec -T api python -c 'import os, sys; os.environ["GEOPOL_BOOTSTRAP_PASSWORD"]=sys.stdin.read(); from geopol.cli import main; sys.argv=["geopol", "bootstrap-user"]; main()'
        unset account_password confirmation
        ;;
    *) fail 'No se pudo comprobar la cuenta inicial. Revisa los registros de la API.' ;;
esac

compose exec -T api python -c '
import time
from sqlalchemy import select
from geopol.db import SessionLocal
from geopol.models import Heartbeat
for attempt in range(30):
    with SessionLocal() as db:
        if db.scalar(select(Heartbeat.id).where(Heartbeat.seen_at > time.time()-60).limit(1)):
            break
    time.sleep(1)
else:
    raise SystemExit("El procesamiento no está listo. Revisa los registros del worker.")
'
printf '\nGeoPol está listo: http://localhost:%s\n' "$web_port"
printf '%s\n' 'Puedes cerrar esta terminal. Para detener GeoPol: bash detener.sh' 'Para volver a abrirlo otro día: bash iniciar.sh'
