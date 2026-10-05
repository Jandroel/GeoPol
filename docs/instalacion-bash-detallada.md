# GeoPol con Bash: PostgreSQL, respaldo y ayuda

Empieza por la [guía breve](../INSTALACION_LOCAL.md). Esta página amplía el mismo
método: Bash y Docker Compose, en Windows con Git Bash o en Linux.
Ejecuta los comandos desde la carpeta que contiene `instalar.sh` y `compose.yaml`.

## Comprobar que estás en la carpeta correcta

```bash
pwd
ls instalar.sh iniciar.sh detener.sh compose.yaml
docker --version
docker compose version
docker info
```

`ls` debe encontrar los cuatro archivos. Docker debe responder sin errores y
Compose debe ser versión 2.20 o superior. `docker info` comprueba que el motor
está encendido; tener instalado el comando `docker` por sí solo no basta.

En Git Bash, una carpeta de Windows como `C:\Users\Ana\Downloads\GeoPol-main`
se escribe así; sustituye `Ana` por tu usuario y ajusta la ubicación:

```bash
cd "/c/Users/Ana/Downloads/GeoPol-main"
```

Si ya trabajas dentro de WSL, utiliza su terminal Bash con Docker disponible.
Docker Desktop permite [integrar una distribución WSL](https://docs.docker.com/desktop/features/wsl/#enable-docker-in-a-wsl-2-distribution).
Mantén el proyecto y la ejecución en el entorno que elegiste.

## Qué hace cada comando

| Comando | Cuándo usarlo | Resultado |
| --- | --- | --- |
| `bash instalar.sh` | Primera instalación o actualización del código | Prepara las imágenes de la aplicación, aplica el esquema e inicia los servicios. Crea `administrador` si aún no hay cuentas. |
| `bash iniciar.sh` | Para volver a usar GeoPol | Inicia los servicios ya preparados y muestra la dirección web. |
| `bash detener.sh` | Al terminar de trabajar | Detiene los servicios y conserva los datos. |

El sitio habitual es [http://localhost:8080](http://localhost:8080); la API está
en [http://localhost:8000/docs](http://localhost:8000/docs). Ambos accesos son
locales a esta computadora. Puedes cerrar Bash después de iniciar la aplicación.

## Qué es PostgreSQL y qué necesitas configurar

PostgreSQL es el programa que organiza los datos de GeoPol en tablas: usuarios,
ejecuciones, ubicaciones y decisiones. PostGIS añade herramientas para datos
geográficos. En esta instalación Docker ejecuta **PostgreSQL 16 y PostGIS 3.5**
como parte del proyecto.

El instalador crea la base y configura la conexión automáticamente. No necesitas
instalar PostgreSQL en Windows/Linux, usar pgAdmin, crear tablas ni abrir el
puerto 5432 de la computadora.

| Dato técnico | Valor de esta instalación |
| --- | --- |
| Proyecto Compose | `geopol-local` |
| Servicio de base de datos | `db` |
| Base de datos | `geopol` |
| Usuario interno de PostgreSQL | `geopol` |
| Puerto dentro de Docker | `5432`, sin publicación en la computadora |
| Contraseña interna | Generada una vez y conservada en `.local/compose.env` |
| Volumen de la base | `geopol-local_database` |
| Volumen de originales y exportaciones | `geopol-local_artifacts` |

La cuenta web `administrador` y el usuario interno `geopol` tienen funciones y
contraseñas diferentes. Elige y recuerda la contraseña web; deja que el
instalador administre la contraseña de PostgreSQL. **No edites, borres ni
compartas `.local/compose.env`**. No lo incluyas en capturas ni mensajes de ayuda.

Cambiar o borrar ese archivo no cambia la contraseña ya guardada en PostgreSQL;
puede impedir que la aplicación se conecte a una base que conserva sus datos.
Si falta el archivo de una instalación existente, recupera su copia privada
con ayuda de quien administra el equipo.

### Consultar PostgreSQL, solo si lo necesitas

Con GeoPol iniciado, esta consulta comprueba el nombre de la base sin mostrar
contraseñas ni datos de usuarios:

```bash
(
unset POSTGRES_PASSWORD GEOPOL_WEB_PORT GEOPOL_API_PORT GEOPOL_ALLOWED_ORIGINS
docker compose -p geopol-local --env-file .local/compose.env -f compose.yaml exec -T db psql -U geopol -d geopol -c "SELECT current_database();"
)
```

Para abrir una consola interactiva de PostgreSQL:

```bash
(
unset POSTGRES_PASSWORD GEOPOL_WEB_PORT GEOPOL_API_PORT GEOPOL_ALLOWED_ORIGINS
docker compose -p geopol-local --env-file .local/compose.env -f compose.yaml exec db psql -U geopol -d geopol
)
```

Sal de esa consola escribiendo `\q` y pulsando Enter. Si Git Bash indica que
la entrada no es una terminal (`the input device is not a TTY`), usa la consulta
con `-T` de arriba. No necesitas la consola para trabajar con GeoPol.

## Dónde quedan los datos y cómo conservarlos

Docker guarda los volúmenes fuera de la carpeta de código. Reiniciar GeoPol o
ejecutar `bash detener.sh` conserva su contenido. Descargar otra vez el código
no es un respaldo de los datos. Tampoco reemplaza la configuración privada de
una instalación existente.

Para conservar los datos, no uses la opción de borrar volúmenes de Docker ni
añadas `-v` a un comando `docker compose down`. El código de GitHub y sus ZIP
contienen la aplicación; las cuentas, archivos reales y resultados se quedan
en cada computadora.

### Crear un respaldo de base y archivos

Espera a que terminen los trabajos y deja Docker abierto. Estos comandos
detienen temporalmente las escrituras, crean una carpeta de respaldo junto al
proyecto y copian la base y los archivos del mismo momento. Pega el bloque
completo en Bash:

```bash
(
  set -eu
  umask 077
  export MSYS_NO_PATHCONV=1
  geopol_compose() (
    unset POSTGRES_PASSWORD GEOPOL_WEB_PORT GEOPOL_API_PORT GEOPOL_ALLOWED_ORIGINS
    docker compose -p geopol-local --env-file .local/compose.env -f compose.yaml "$@"
  )
  respaldo="../geopol-respaldo-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$respaldo"
  geopol_compose stop frontend api worker
  geopol_compose exec -T db pg_dump -U geopol -d geopol -Fc > "$respaldo/geopol.dump"
  geopol_compose run --rm --no-deps -T --entrypoint tar api -czf - -C /app/data storage > "$respaldo/artifacts-backup.tgz"
  test -s "$respaldo/geopol.dump"
  tar -tzf "$respaldo/artifacts-backup.tgz" > /dev/null
  geopol_compose start api worker frontend
  printf 'Respaldo guardado en: %s\n' "$respaldo"
)
```

Si cualquier paso falla, el bloque se detiene: conserva el mensaje y solicita
ayuda. La carpeta creada puede contener una copia incompleta. Para volver a
usar GeoPol después de resolver el fallo, ejecuta `bash iniciar.sh`.

`geopol.dump` contiene la base y `artifacts-backup.tgz` los originales y
exportaciones. Conserva ambos juntos en una ubicación privada de respaldo,
junto con la fecha y versión del proyecto. Conserva también una copia privada
de `.local/compose.env` en el lugar autorizado para secretos, por separado.
El formato de la base corresponde a [pg_dump de PostgreSQL](https://www.postgresql.org/docs/16/app-pgdump.html).

Este procedimiento crea copias; la recuperación debe probarse en una instancia
vacía antes de considerar el respaldo validado. El [manual de operación](runbook.md#procedimiento-de-restauración-en-una-instancia-vacía)
describe ese proceso avanzado. Sus comandos genéricos de Compose deben adaptarse
al proyecto y archivo de configuración de la instancia de destino; no los
ejecutes sobre la instalación que deseas conservar.

## Actualizar GeoPol

Primero crea un respaldo. Si descargaste con `git clone`, revisa el estado y
detén GeoPol:

```bash
git status --short
bash detener.sh
git pull --ff-only origin main
bash instalar.sh
bash iniciar.sh
```

Ejecuta los comandos uno por uno. Si hay cambios locales de código o un comando
falla, resuélvelo antes de continuar. Conserva `.local/compose.env` y los
volúmenes: reinstalar aplica el esquema pendiente y conserva las cuentas.

Si descargaste un ZIP, descarga la versión nueva y actualiza los archivos de
código en la misma carpeta, conservando la carpeta privada `.local`. Después
ejecuta `bash instalar.sh` y `bash iniciar.sh`. No reemplaces los datos por una
carpeta vacía ni compartas un ZIP de tu instalación con sus archivos privados.

## Problemas frecuentes

| Problema | Solución |
| --- | --- |
| GitHub muestra `Repository not found` | Acepta la invitación con la cuenta correcta. Para un ZIP, inicia sesión en el navegador; para clonar, autentícate cuando Git lo solicite. |
| `bash` no se reconoce | Abre Git Bash en Windows; los comandos de esta guía se pegan allí. |
| No encuentra `instalar.sh` | Extrae el ZIP y entra en la carpeta que contiene ese archivo. Comprueba la ubicación con `pwd` y `ls`. |
| `docker: command not found` | Instala Docker, cierra Bash y abre una terminal nueva. |
| No puede conectar al motor de Docker | Abre Docker Desktop y espera a que arranque. En Linux, comprueba el servicio y los permisos según la documentación oficial. |
| Docker informa que necesita contenedores Linux | Cambia Docker Desktop al modo Linux y repite la instalación. |
| Docker Compose demasiado antiguo | Actualiza Docker Desktop o el complemento Compose. Se requiere 2.20 o superior. |
| La contraseña no se ve mientras escribes | Es normal. Escribe la contraseña y pulsa Enter. |
| Contraseña de menos de 12 caracteres o confirmación distinta | El instalador vuelve a pedirla automáticamente. Escribe dos veces una contraseña válida. |
| El inicio de sesión falla | Usa la cuenta de esta instalación y la contraseña web elegida al instalar. Reinstalar no cambia contraseñas de cuentas existentes. |
| Falla la conexión interna con PostgreSQL después de editar `.local/compose.env` | Recupera la configuración original. No borres los volúmenes para intentar corregir la contraseña. |
| El navegador no muestra GeoPol | Ejecuta `bash iniciar.sh`, espera a que termine y abre la dirección que muestra. Comprueba que Docker siga activo. |
| Se queda descargando o aparece un error de red | Revisa Internet y, en una red institucional, la configuración de proxy indicada debajo. |

### Un puerto ya está ocupado

Si es otra sesión de GeoPol, detén esa sesión. Si GeoPol debe convivir con otra
aplicación, elige otros puertos. El primer número corresponde a la web y el
segundo a la API:

```bash
bash instalar.sh --puertos 8081 8003
bash iniciar.sh
```

En este ejemplo la web será [http://localhost:8081](http://localhost:8081).
Los puertos se guardan para los siguientes arranques. Esta opción también
funciona si el primer intento falló porque un puerto estaba ocupado: conserva
la contraseña interna y los datos. No edites el archivo privado manualmente.

### Proxy institucional

Aplica esta sección únicamente si soporte te indica que la red requiere proxy.
Sustituye el ejemplo por la dirección y puerto que te proporcionen:

```bash
export http_proxy="http://proxy.ejemplo:3128"
export https_proxy="$http_proxy"
export no_proxy="localhost,127.0.0.1,::1,db,api"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export NO_PROXY="$no_proxy"
```

Estas variables afectan a Bash y sus comandos; se pierden al cerrar la terminal.
No configuran por sí solas el motor de Docker. En Docker Desktop, abre
**Settings → Resources → Proxies** y usa el proxy del sistema o el indicado por
soporte, según la [documentación oficial](https://docs.docker.com/desktop/settings-and-maintenance/settings/#proxies).
En Linux, soporte debe configurar el [proxy del motor Docker](https://docs.docker.com/engine/daemon/proxy/)
si las imágenes no se descargan. No desactives la verificación de certificados
para eludir un error de la red.

### Consultar el estado y los registros

```bash
(
unset POSTGRES_PASSWORD GEOPOL_WEB_PORT GEOPOL_API_PORT GEOPOL_ALLOWED_ORIGINS
docker compose -p geopol-local --env-file .local/compose.env -f compose.yaml ps
docker compose -p geopol-local --env-file .local/compose.env -f compose.yaml logs --tail=80 api worker db
)
```

Al pedir ayuda, incluye el mensaje de error y el comando ejecutado. Revisa los
registros antes de compartirlos y excluye datos reales y secretos. Evita
compartir la salida de `docker compose config`, que puede contener la contraseña.

## Si ya utilizabas el método anterior con SQLite

Los scripts `instalar.cmd`, `iniciar.cmd` y `scripts/setup.sh` corresponden al
método anterior con herramientas instaladas en la computadora. Su base habitual
es `data/geopol.db`, no la base PostgreSQL creada por esta guía.

El método Bash con Docker inicia su propia base: **no importa automáticamente
usuarios, archivos ni resultados de SQLite**. Conserva la instalación anterior
y su respaldo si contienen información necesaria. La [guía manual anterior](instalacion-local-detallada.md)
se mantiene como alternativa para esas instalaciones.
