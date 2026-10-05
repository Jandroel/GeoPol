# GeoPol con Bash: preparación, respaldo y ayuda

Empieza por la [guía breve](../INSTALACION_LOCAL.md). Esta página amplía el mismo
método nativo: PostgreSQL con PostGIS, Python y Node.js instalados en la
computadora. Ejecuta los comandos desde la carpeta que contiene `instalar.sh`.

## Preparar Ubuntu 24.04 o WSL

Estos pasos corresponden a **Ubuntu 24.04**, que ofrece Python 3.12 y
PostgreSQL 16. Python debe ser **3.11 o superior**; PostGIS es obligatorio.
Consulta los paquetes oficiales de [Python](https://packages.ubuntu.com/noble/python3)
y [PostGIS para PostgreSQL 16](https://packages.ubuntu.com/noble/postgresql-16-postgis-3).

En Bash:

```bash
sudo apt update
sudo apt install git curl ca-certificates python3 python3-venv python3-pip postgresql-16 postgresql-client-16 postgresql-contrib postgresql-16-postgis-3
sudo systemctl start postgresql
```

En WSL, si `systemctl` indica que no se utiliza systemd, inicia el servicio con
`sudo service postgresql start`. Mantén la distribución WSL funcionando mientras
uses GeoPol. Instala las herramientas y guarda el proyecto dentro de la misma
distribución.

Para una instalación nueva de PostgreSQL, establece una contraseña propia
para su usuario administrador. El siguiente comando la solicita de forma
interactiva; no escribas la contraseña como parte del comando:

```bash
sudo -u postgres psql -c '\password postgres'
```

Si PostgreSQL ya está administrado por tu institución, utiliza las credenciales
que te proporcionen; no cambies su contraseña. El comando `\password` evita
dejarla en el historial ([documentación de psql](https://www.postgresql.org/docs/16/app-psql.html)).

Para **Node.js 24**, elige Linux y la versión 24 en la
[página oficial de Node.js](https://nodejs.org/en/download) y sigue su opción de
instalación con `nvm`. También puedes instalar `nvm` siguiendo su
[guía oficial](https://github.com/nvm-sh/nvm#installing-and-updating).
Abre una Bash nueva y ejecuta:

```bash
nvm install 24
nvm alias default 24
nvm use 24
python3 --version
node --version
npm --version
pg_isready -h 127.0.0.1 -p 5432
```

`node --version` debe comenzar por `v24.`; instalar el paquete `nodejs` que
ofrezca por defecto otra versión de Ubuntu puede dar una versión diferente.
`pg_isready` debe indicar que PostgreSQL acepta conexiones; la contraseña se
comprobará durante la instalación.

En otras versiones de Ubuntu, sigue el [repositorio oficial de PostgreSQL](https://www.postgresql.org/download/linux/ubuntu/)
para disponer de la versión 16 y su paquete PostGIS. Comprueba también
`python3 --version`: si es menor que 3.11, instala una versión compatible antes
de continuar. Usa los mismos tres scripts de GeoPol en cualquier entorno.

## Comprobar la carpeta y las herramientas

```bash
pwd
ls instalar.sh iniciar.sh detener.sh
git --version
node --version
npm --version
```

En Windows comprueba Python con `python --version`; en Linux, con
`python3 --version`. Si acabas de instalar una herramienta, cierra Bash y abre
una nueva terminal para que reconozca su ubicación.

En Git Bash, una ruta de Windows como `C:\Users\Ana\Downloads\GeoPol-main`
se escribe así; sustituye el usuario y la carpeta:

```bash
cd "/c/Users/Ana/Downloads/GeoPol-main"
```

Para usar `psql`, `pg_dump` y `pg_restore` desde Git Bash, si no se encuentran,
añade la carpeta de PostgreSQL a la terminal actual. Ajusta la ruta si elegiste
otra ubicación al instalar:

```bash
export PATH="/c/Program Files/PostgreSQL/16/bin:$PATH"
psql --version
```

Este ajuste se repite en cada terminal donde necesites esas herramientas. No es
necesario abrir pgAdmin para instalar o usar GeoPol.

## Qué hace cada comando

| Comando | Cuándo usarlo | Resultado |
| --- | --- | --- |
| `bash instalar.sh` | Primera instalación o actualización | Instala dependencias, compila la web, prepara PostgreSQL/PostGIS y aplica migraciones. Crea `administrador` solo si aún no hay usuarios. |
| `bash iniciar.sh` | Para trabajar | Inicia API, worker y web en primer plano. Mantén abierta la terminal. |
| `bash detener.sh` | Desde otra Bash, al terminar | Detiene los procesos registrados de GeoPol; conserva los datos y deja PostgreSQL funcionando. |

También puedes detener GeoPol con **Ctrl+C** en la terminal de arranque.
La dirección habitual es [http://localhost:5173](http://localhost:5173);
la documentación técnica de la API está en [http://localhost:8000/docs](http://localhost:8000/docs).
Ambos accesos están limitados a esta computadora.

## PostgreSQL y las contraseñas

En la primera instalación se solicitan servidor (`127.0.0.1`), puerto (`5432`),
nombre de una base nueva (`geopol`), usuario administrador (`postgres`) y su
contraseña. Pulsa Enter para aceptar los valores predeterminados cuando
correspondan a tu equipo.

El instalador utiliza esos permisos para crear una base nueva, un usuario
interno sin privilegios de superusuario y las extensiones necesarias. La base
y el usuario interno deben tener nombres disponibles; no se adopta ni se
sobrescribe una base ajena. Si aparece un conflicto, repite la instalación con
otro nombre nuevo.

Hay tres credenciales distintas:

| Credencial | Para qué sirve | Dónde se conserva |
| --- | --- | --- |
| Administrador de PostgreSQL, normalmente `postgres` | Preparar la base y sus extensiones | La conserva quien administra PostgreSQL; GeoPol no la guarda. |
| Usuario interno de la aplicación | Conexión habitual de API y worker | Se genera y guarda en `.local/native.json`. |
| Cuenta web `administrador` | Iniciar sesión en GeoPol | Tú eliges una contraseña de al menos 12 caracteres; la base guarda su hash. |

Elige una contraseña web distinta de la de PostgreSQL. Escribir contraseñas sin
que aparezcan caracteres es normal. Si ya existen cuentas, volver a instalar
las conserva y no restablece sus contraseñas.

## Dónde quedan los datos

- **PostgreSQL:** cuentas, ejecuciones, resultados, revisiones y auditoría.
- **`data/storage-native`:** originales y exportaciones de esta instalación.
- **`.local/native.json`:** conexión privada, usuario interno, puertos y rutas.

Conserva la configuración y los archivos junto con la base. No publiques
`.local/native.json` ni lo pegues en mensajes de ayuda: contiene un secreto.
Descargar el código otra vez no recupera los datos ni sustituye un respaldo.

Una instalación anterior con SQLite u otro método conserva sus datos por
separado. El flujo nativo no modifica el `.env` anterior ni migra sus cuentas
o archivos. Conserva esa instalación y su respaldo hasta preparar y verificar
una migración explícita.

## Crear un respaldo de base y archivos

Espera a que terminen los trabajos. Utiliza `pg_dump` y `pg_restore` de
PostgreSQL 16, disponibles con las herramientas de línea de comandos de
PostgreSQL. En Windows, consulta arriba cómo añadirlas al PATH.

Este ejemplo utiliza los valores predeterminados. **Si elegiste otro servidor,
puerto, administrador o nombre de base, cambia esos valores antes de ejecutarlo.**
Pega el bloque completo desde la raíz del proyecto:

```bash
(
  set -eu
  umask 077
  bash detener.sh
  respaldo="../geopol-respaldo-$(date +%Y%m%d-%H%M%S)"
  mkdir "$respaldo"
  pg_dump -h 127.0.0.1 -p 5432 -U postgres -W -d geopol -Fc -f "$respaldo/geopol.dump"
  tar -czf "$respaldo/artifacts-backup.tgz" -C data storage-native
  test -s "$respaldo/geopol.dump"
  pg_restore --list "$respaldo/geopol.dump" > /dev/null
  tar -tzf "$respaldo/artifacts-backup.tgz" > /dev/null
  printf 'Respaldo guardado en: %s\n' "$respaldo"
)
```

`pg_dump` solicita la contraseña de PostgreSQL de forma oculta. La base permanece
encendida, pero GeoPol queda detenido durante la copia. Si cualquier comando
falla, el bloque se detiene: la carpeta puede contener un respaldo incompleto.
Después de resolverlo, vuelve a iniciar con `bash iniciar.sh`.

Guarda los dos archivos juntos en una ubicación privada autorizada, registra
fecha y versión del proyecto y conserva **por separado una copia privada de
`.local/native.json`**. El formato `-Fc` permite restaurar con `pg_restore`
([documentación de pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html)).
Leer el archivo comprueba su estructura, pero no sustituye una
[prueba de restauración](runbook.md#procedimiento-de-restauración-en-una-instancia-vacía).

## Actualizar GeoPol

Crea primero un respaldo. Si descargaste con Git, ejecuta uno por uno:

```bash
git status --short
bash detener.sh
git pull --ff-only origin main
bash instalar.sh
bash iniciar.sh
```

Si hay cambios locales de código o un comando falla, resuélvelo antes de
continuar. Conserva `.local/native.json` y `data/storage-native`: reinstalar
actualiza las dependencias y el esquema y conserva las cuentas y los datos.

Si descargaste un ZIP, actualiza los archivos de código en la misma carpeta,
conservando `.local` y `data`. Después ejecuta `bash instalar.sh` y
`bash iniciar.sh`. No envíes un ZIP de tu instalación con sus archivos privados.

## Problemas frecuentes

| Problema | Solución |
| --- | --- |
| GitHub muestra `Repository not found` | Acepta la invitación con la cuenta correcta. Para descargar un ZIP, inicia sesión en GitHub. |
| No encuentra `instalar.sh` | Extrae el ZIP y entra en la carpeta que contiene ese archivo. Compruébalo con `pwd` y `ls`. |
| Python no aparece o abre Microsoft Store | Revisa la instalación y la opción **Add Python to PATH**; abre una Bash nueva. |
| Python es menor que 3.11 o Node.js es de otra versión | Instala Python compatible y Node.js 24 antes de continuar. |
| En Linux no puede crear el entorno Python | Instala el paquete `python3-venv` correspondiente a tu Python. |
| `Connection refused` al conectar con PostgreSQL | Comprueba que el servicio esté iniciado. Revisa servidor y puerto; instalar pgAdmin no inicia por sí solo un servidor. |
| PostgreSQL rechaza la contraseña | Usa la del administrador PostgreSQL, no la contraseña web. Confirma los datos con quien administra el servidor. |
| PostGIS no está disponible | Instala el paquete PostGIS de la misma versión principal de PostgreSQL y repite la instalación. |
| Ya existe la base o el rol | Para una instalación nueva, elige otro nombre de base libre. Para una existente, conserva su configuración privada original. |
| Falta `.local/native.json` de una instalación existente | Recupera su copia privada. No borres la base ni intentes recrearla con el mismo nombre. |
| La contraseña no se ve | Es normal. Escríbela y pulsa Enter. |
| La contraseña web es corta o no coincide | Introduce dos veces la misma contraseña, de al menos 12 caracteres. |
| El inicio de sesión falla | Usa la cuenta de esta instalación. Reinstalar no cambia contraseñas existentes. |
| La web no abre | Ejecuta `bash iniciar.sh`, espera la dirección y mantén abierta la terminal. |
| Falla la descarga de dependencias | Comprueba Internet y, si corresponde, el proxy indicado por soporte. |

### Un puerto ya está ocupado

Si pertenece a otra sesión tuya de GeoPol, detenla. Para convivir con otra
aplicación, elige otros puertos. El primer número es la web y el segundo la API:

```bash
bash iniciar.sh --puertos 5174 8002
```

La web se abrirá en [http://localhost:5174](http://localhost:5174).
También puedes elegirlos al instalar: `bash instalar.sh --puertos 5174 8002`.
Se guardan para los siguientes arranques. No cambian el puerto de PostgreSQL.

### Proxy institucional

Solo si soporte indica que tu red utiliza proxy, ajusta la dirección del ejemplo
y configura la terminal donde descargarás las dependencias:

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

Después ejecuta `bash instalar.sh` en esa misma terminal. Para certificados
corporativos, utiliza la configuración que indique soporte. Las conexiones
locales deben permanecer fuera del proxy.
