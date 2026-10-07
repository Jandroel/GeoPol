# Preparación y ayuda para ejecutar GeoPol con Bash

El recorrido principal está en [INSTALACION_LOCAL.md](../INSTALACION_LOCAL.md):
base propia, `backend/.env`, dependencias y dos terminales. Esta página reúne
solo los detalles que puedes necesitar durante ese recorrido.

## Preparar la computadora

### Windows con Git Bash

1. Instala [Git para Windows](https://git-scm.com/install/windows), que incluye
   **Git Bash**. Esta es la terminal de los ejemplos.
2. Instala [Python](https://www.python.org/downloads/windows/), versión 3.11 o
   superior. En el instalador clásico marca **Add Python to PATH**.
3. Instala [Node.js 24](https://nodejs.org/en/download); incluye `npm`.
4. Instala [PostgreSQL 16](https://www.postgresql.org/download/windows/) con
   **PostgreSQL Server**, **Command Line Tools** y **Stack Builder**. Conserva
   el puerto `5432` y guarda la contraseña que elijas para `postgres`.
5. En **Stack Builder**, selecciona PostgreSQL 16 e instala **PostGIS Bundle**
   desde **Spatial Extensions**, siguiendo la [guía de PostGIS](https://postgis.net/documentation/getting_started/install_windows/).
   No necesitas crear una base de ejemplo.

Cierra las terminales anteriores y abre una nueva Git Bash. PostgreSQL debe
estar funcionando como servicio de Windows; pgAdmin no necesita estar abierto.
Para disponer de sus comandos en esa terminal:

```bash
export PATH="/c/Program Files/PostgreSQL/16/bin:$PATH"
python --version
node --version
psql --version
```

Si elegiste otra carpeta de instalación, ajusta el `PATH`. En Git Bash, una
ruta como `C:\Users\Ana\Downloads\GeoPol-main` se escribe
`/c/Users/Ana/Downloads/GeoPol-main`; usa comillas cuando contenga espacios.

### Preparar Ubuntu 24.04 o WSL

En Ubuntu 24.04, instala Python, PostgreSQL 16 y PostGIS:

```bash
sudo apt update
sudo apt install git curl ca-certificates python3 python3-venv python3-pip postgresql-16 postgresql-client-16 postgresql-contrib postgresql-16-postgis-3
sudo systemctl start postgresql
```

Si WSL no utiliza systemd, inicia PostgreSQL con `sudo service postgresql start`.
Instala todas las herramientas y guarda el proyecto dentro de la misma
distribución. En una instalación **nueva** de PostgreSQL, establece la contraseña
de `postgres` con una pregunta interactiva:

```bash
sudo -u postgres psql -c '\password postgres'
```

Si el servidor ya tiene un administrador, utiliza las credenciales que te
proporcione. Para Node.js, sigue la [instalación oficial con nvm](https://nodejs.org/en/download)
o la [guía de nvm](https://github.com/nvm-sh/nvm#installing-and-updating).
Con `nvm` instalado, abre una Bash nueva y ejecuta:

```bash
nvm install 24
nvm alias default 24
nvm use 24
python3 --version
node --version
pg_isready -h 127.0.0.1 -p 5432
```

Python debe ser 3.11 o superior y Node.js debe ser 24. `pg_isready` debe indicar
que PostgreSQL acepta conexiones. En otras versiones de Ubuntu consulta el
[repositorio oficial de PostgreSQL](https://www.postgresql.org/download/linux/ubuntu/).

## Crear una base propia

Los comandos de la guía principal crean `geopol_app` sin permisos de
superusuario y una base `geopol` que le pertenece. `--pwprompt` pide la
contraseña del nuevo usuario; `-U postgres` identifica a quien tiene permiso
para crearlo. Consulta [createuser](https://www.postgresql.org/docs/16/app-createuser.html)
y [createdb](https://www.postgresql.org/docs/16/app-createdb.html).

Si prefieres preparar la base en pgAdmin, crea un usuario con inicio de sesión
`geopol_app`, asigna una contraseña y crea `geopol` con ese usuario como dueño.
Conectado como `postgres` a esa base, activa `postgis` y `pg_trgm`. Después
continúa en el paso del backend; no repitas la creación por Bash.

PostGIS debe estar instalado en el servidor antes de activar su extensión.
Si ya tienes otra base destinada a GeoPol, utiliza su nombre, dueño, host y
puerto en `backend/.env`. El backend necesita permiso para crear y actualizar
sus propias tablas; no lo conectes a una base destinada a otra aplicación.

## Contraseñas y .env

| Credencial | Para qué se usa |
| --- | --- |
| `postgres` | Crear el usuario, la base y sus extensiones. No se guarda en el `.env` de GeoPol. |
| `geopol_app` | Conectar GeoPol a su base. Su contraseña se escribe en `backend/.env`. |
| `administrador` | Iniciar sesión en la web. El backend la solicita al crear la primera cuenta. |

El comando `cp -n .env.example .env` conserva un `.env` que ya exista. Edita
**`backend/.env`**, el archivo ubicado junto a `pyproject.toml`, y ejecuta el
backend desde esa misma carpeta. No compartas el `.env`: cada computadora
debe usar la conexión a su propia base.

La contraseña dentro de `GEOPOL_DATABASE_URL` debe estar codificada para una
URL si contiene caracteres especiales. Por ejemplo, `@` se escribe `%40`,
`:` como `%3A`, `/` como `%2F`, `#` como `%23` y `%` como `%25`.
Para convertir tu contraseña sin escribirla en el historial, ejecuta con
el entorno Python activado:

```bash
(
  IFS= read -r -s -p "Clave de geopol_app: " GEOPOL_PASSWORD_TO_ENCODE || exit 1
  printf '\n'
  export GEOPOL_PASSWORD_TO_ENCODE
  python -c 'import os; from urllib.parse import quote; print(quote(os.environ["GEOPOL_PASSWORD_TO_ENCODE"], safe=""))'
)
```

Copia el resultado solo en la parte `TU_CLAVE` del `.env`. Esa salida sigue
siendo tu contraseña, aunque se vea diferente. La contraseña original de
PostgreSQL no cambia.

Si tu terminal no permite escribir la contraseña web al iniciar el backend,
abre `backend/.env`, descomenta `GEOPOL_BOOTSTRAP_PASSWORD` y asígnale una
contraseña propia de al menos 12 caracteres. Luego ejecuta `python -m geopol.dev`.
Esta opción solo crea la cuenta inicial cuando no existen usuarios; no cambia
contraseñas de cuentas existentes. Puedes borrar esa línea después de crear
la cuenta.

## Qué ocurre al iniciar

`python -m geopol.dev` lee `backend/.env`, comprueba la conexión, aplica las
migraciones y crea la cuenta inicial solo si la base no tiene usuarios.
Después mantiene funcionando la API y el trabajador que procesa las cargas
y exportaciones. Al presionar Ctrl+C, detiene ambos. PostgreSQL sigue activo.

`npm run dev`, ejecutado desde `frontend`, sirve la web y conecta sus peticiones
a la API local. La dirección habitual es [http://localhost:5173](http://localhost:5173);
la API se puede consultar en [http://localhost:8000/docs](http://localhost:8000/docs).
Mantén abiertas las dos terminales mientras uses el sistema.

No vuelvas a crear la base, el entorno `.venv` ni el `.env` cada vez que abras
GeoPol. Las tablas existentes y las cuentas se conservan al reiniciar.

## Datos y respaldos

PostgreSQL guarda cuentas, ejecuciones, resultados y revisiones. Los originales
y las exportaciones se guardan en la ruta `GEOPOL_STORAGE_PATH` del `.env`;
con el ejemplo incluido corresponde a **`data/storage` en la raíz del proyecto**.
Conserva juntos un respaldo de la base y los archivos, además de una copia
privada del `.env`.

Espera a que terminen los trabajos y detén las dos terminales con Ctrl+C.
Desde la raíz del proyecto, ajustando los nombres si usaste otros:

```bash
(
  set -eu
  umask 077
  respaldo="../geopol-respaldo-$(date +%Y%m%d-%H%M%S)"
  mkdir "$respaldo"
  pg_dump -h 127.0.0.1 -U postgres -W -d geopol -Fc -f "$respaldo/geopol.dump"
  tar -czf "$respaldo/archivos.tgz" -C data storage
  cp backend/.env "$respaldo/backend.env"
  pg_restore --list "$respaldo/geopol.dump" > /dev/null
  tar -tzf "$respaldo/archivos.tgz" > /dev/null
  printf 'Respaldo guardado en: %s\n' "$respaldo"
)
```

Si cambiaste `GEOPOL_STORAGE_PATH`, adapta la línea de `tar` para copiar esa
carpeta. El bloque se detiene si algo falla; no des por completo un respaldo
fallido. Guarda la carpeta en una ubicación privada. La lectura del respaldo
comprueba su estructura, pero es necesario probar su restauración para
confirmar que puede recuperarse.

Para restaurar en otra computadora, prepara PostgreSQL, el usuario de aplicación
y una base vacía. Restaura el `.dump` con `pg_restore` como administrador,
restituye los archivos en su carpeta y configura el `.env` con la conexión de
esa computadora. Utiliza la misma versión del proyecto durante la comprobación
y verifica cuentas, recuentos y descargas antes de continuar trabajando.

## Actualizar las dependencias

Después de respaldar y detener GeoPol, actualiza el código. Si lo descargaste
con Git, ejecuta desde la raíz:

```bash
git pull --ff-only origin main
```

En la terminal del backend, con `.venv` activado:

```bash
python -m pip install -c requirements.lock -e '.[dev]'
python -m geopol.dev
```

En la terminal del frontend:

```bash
npm ci
npm run dev
```

Si actualizas mediante ZIP, conserva `backend/.env` y la carpeta de archivos.
Descargar el código no respalda ni recupera por sí solo la base de datos.

## Problemas frecuentes

| Problema | Qué revisar |
| --- | --- |
| GitHub muestra `Repository not found` | Acepta la invitación al repositorio privado e inicia sesión con la cuenta correcta. |
| No encuentra `backend` o `frontend` | Extrae el ZIP y abre Bash en la carpeta que contiene ambas carpetas. |
| No encuentra Python, Node.js o `psql` | Instala la herramienta y abre otra terminal; en Windows revisa el `PATH` indicado arriba. |
| `No module named geopol` | Entra en `backend`, activa `.venv` e instala sus dependencias. |
| No puede crear `.venv` en Linux | Instala `python3-venv` para tu versión de Python. |
| PostgreSQL rechaza la conexión | Comprueba su servicio, host, puerto y la contraseña de `geopol_app` en el `.env`. |
| No encuentra PostGIS | Instala PostGIS compatible con PostgreSQL 16 y activa su extensión en la base. |
| Ya existe la base o el usuario | Si son los que preparaste para GeoPol, reutilízalos y omite su creación. |
| Pide la cuenta inicial aunque ya tenías usuarios | Comprueba que el `.env` apunte a la base correcta. |
| El login falla | Usa `administrador` y la contraseña web, no las credenciales de PostgreSQL. |
| La web abre pero no conecta | Comprueba que `python -m geopol.dev` siga funcionando en la otra terminal. |
| El puerto está ocupado | Detén la otra instancia que esté usando ese puerto antes de iniciar GeoPol. |
| Las cargas no avanzan | Revisa la terminal del backend: también debe estar funcionando su trabajador. |

### Proxy institucional

Solo si tu red lo requiere, usa la dirección indicada por soporte en la
terminal donde instalarás dependencias:

```bash
export http_proxy="http://proxy.ejemplo:3128"
export https_proxy="$http_proxy"
export no_proxy="localhost,127.0.0.1,::1"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export NO_PROXY="$no_proxy"
export npm_config_proxy="$http_proxy"
export npm_config_https_proxy="$https_proxy"
```

Después ejecuta `pip` o `npm ci` en esa terminal. Las conexiones locales a
GeoPol deben permanecer fuera del proxy.
