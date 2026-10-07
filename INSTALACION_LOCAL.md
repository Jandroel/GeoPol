# Ejecutar GeoPol en tu computadora

El flujo es el habitual: **crear tu base, configurar `backend/.env`, instalar dependencias y abrir dos terminales: una para el backend y otra para el frontend**.
Las tablas se crean automáticamente al iniciar el backend por primera vez.

Necesitas **Python 3.11 o superior, Node.js 24 y PostgreSQL 16 con PostGIS**.
Usa **Git Bash en Windows** o **Bash en Linux/WSL**. Si te falta alguna
herramienta, sigue la [preparación de la computadora](docs/instalacion-bash-detallada.md#preparar-la-computadora).

## 1. Descargar el proyecto

Descarga y extrae el ZIP de [Jandroel/GeoPol](https://github.com/Jandroel/GeoPol)
o usa Git:

```bash
git clone https://github.com/Jandroel/GeoPol.git
cd GeoPol
```

Abre Bash en la carpeta que contiene `backend` y `frontend`. En Windows puedes hacer clic derecho en esa carpeta y elegir **Open Git Bash here**.

## 2. Crear tu base: solo una vez

Con PostgreSQL funcionando, ejecuta estos comandos **uno por uno**:

```bash
createuser -h 127.0.0.1 -U postgres --pwprompt geopol_app
createdb -h 127.0.0.1 -U postgres -O geopol_app geopol
psql -h 127.0.0.1 -U postgres -d geopol -c 'CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pg_trgm;'
```

El primer comando pide elegir y repetir una contraseña para **`geopol_app`**: la usarás en el `.env`. Cuando se pida la contraseña de **`postgres`**, escribe la que elegiste al instalar PostgreSQL. Es normal que no aparezca al escribir.
Los comandos crean un usuario de aplicación, la base `geopol` y sus extensiones; no tienes que crear tablas. Si ya preparaste esa base, omite este paso.

En Windows, si no encuentra `createuser` o `psql`, ejecuta primero:

```bash
export PATH="/c/Program Files/PostgreSQL/16/bin:$PATH"
```

## 3. Preparar el backend: solo una vez

Desde la carpeta del proyecto, en **Windows con Git Bash**:

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
```

En **Linux o WSL**, usa este bloque en su lugar:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

Ahora, en cualquiera de los dos sistemas:

```bash
python -m pip install -c requirements.lock -e '.[dev]'
cp -n .env.example .env
```

Abre **`backend/.env`** en tu editor y cambia `TU_CLAVE` por la contraseña que elegiste para `geopol_app`. Guarda el archivo:

```dotenv
GEOPOL_DATABASE_URL=postgresql+psycopg://geopol_app:TU_CLAVE@127.0.0.1:5432/geopol
```

Si tu contraseña tiene caracteres como `@`, `:`, `/`, `#` o `%`, consulta [cómo escribirla en la URL](docs/instalacion-bash-detallada.md#contraseñas-y-env).

## 4. Iniciar backend y frontend

En la terminal del **backend**, con el entorno activado:

```bash
python -m geopol.dev
```

Este comando crea o actualiza las tablas e inicia la API y el proceso que
analiza los archivos. Solo si aún no hay usuarios, pide una contraseña de
al menos 12 caracteres para la cuenta web **`administrador`**. Esta contraseña
es distinta de la conexión PostgreSQL. Si Git Bash no permite escribirla de forma oculta, define `GEOPOL_BOOTSTRAP_PASSWORD` en `backend/.env` y vuelve a iniciar. Mantén la terminal abierta.

Abre **otra terminal** en la carpeta del proyecto:

```bash
cd frontend
npm ci
npm run dev
```

Entra a **[http://localhost:5173](http://localhost:5173)** e inicia sesión con `administrador` y la contraseña web que elegiste. Para detener GeoPol, pulsa **Ctrl+C en ambas terminales**. Tus datos se conservan.

**Los siguientes días:** entra en `backend`, activa `.venv` y ejecuta
`python -m geopol.dev`; en otra terminal entra en `frontend` y ejecuta
`npm run dev`. No necesitas repetir la creación de la base ni la instalación
de dependencias. Más ayuda y respaldos en la [guía detallada](docs/instalacion-bash-detallada.md).
