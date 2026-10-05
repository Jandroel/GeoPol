# GeoPol: alternativa manual con SQLite

> Esta guía conserva la alternativa anterior con SQLite y herramientas
> instaladas en la computadora, incluida la opción `scripts/setup.sh` de
> Linux/macOS. Para una instalación nueva con Bash y PostgreSQL, sigue la
> [guía breve de dos comandos](../INSTALACION_LOCAL.md). Las bases de ambos
> métodos son independientes; no hay migración automática entre ellos.

Esta guía permite instalar GeoPol en otra computadora, crear una cuenta propia y
probar la aplicación con archivos de ejemplo. El recorrido principal utiliza
**Windows y PowerShell**, con SQLite como base local. No requiere Docker,
PostgreSQL ni tener Microsoft Excel instalado.

Repositorio: [Jandroel/GeoPol](https://github.com/Jandroel/GeoPol).
Guía revisada el **5 de octubre de 2026** contra los scripts del proyecto.

## 1. Preparar la computadora

Instala estas herramientas y después abre una terminal nueva:

| Herramienta   | Requisito del proyecto                       | Descarga oficial                                                 |
| ------------- | -------------------------------------------- | ---------------------------------------------------------------- |
| Git           | Para descargar y actualizar el repositorio   | [Git para Windows](https://git-scm.com/install/windows)          |
| Python        | 3.11 o superior, versión de 64 bits          | [Python para Windows](https://www.python.org/downloads/windows/) |
| Node.js y npm | Node.js 24 o superior; npm viene con Node.js | [Node.js](https://nodejs.org/en/download/)                       |

Comprueba que están disponibles desde PowerShell:

```powershell
git --version
python --version
node --version
npm.cmd --version
```

Las dependencias de Python están fijadas en `backend/requirements.lock` y fueron
verificadas con Python 3.11. La instalación descarga paquetes de Internet; si tu
red requiere proxy, configura primero la [sección de proxy](#proxy-institucional-opcional).

## 2. Obtener acceso y descargar el proyecto

El repositorio es privado. El propietario debe invitar la cuenta de GitHub del
compañero desde la configuración del repositorio, en **Collaborators**. El
compañero debe aceptar la invitación antes de clonar y autenticarse con su propia
cuenta cuando Git lo solicite.

Ejecuta en PowerShell:

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE\proyectos" -Force | Out-Null
Set-Location "$env:USERPROFILE\proyectos"
git clone https://github.com/Jandroel/GeoPol.git
Set-Location GeoPol
```

La carpeta actual debe contener `README.md`, `backend`, `frontend` y `scripts`.
En adelante, **raíz del proyecto** significa esta carpeta `GeoPol`.

Si ya tienes una copia, entra en ella; no vuelvas a clonar dentro de la misma
carpeta. Consulta la sección de actualización para traer cambios posteriores.

## 3. Instalar las dependencias y preparar la base

Desde la raíz del proyecto:

```powershell
.\scripts\setup.ps1
```

El script realiza estas tareas:

1. Crea el entorno de Python en `backend/.venv`.
2. Instala las dependencias del backend con las versiones del proyecto.
3. Inicializa SQLite y aplica las migraciones pendientes.
4. Instala las dependencias del frontend mediante `npm ci`.

Espera el mensaje **«Dependencias y esquema listos»** antes de continuar.
No es necesario activar el entorno virtual: los comandos de esta guía utilizan
directamente su ejecutable.

Para esta instalación **no hace falta crear `.env` ni copiar `.env.example`**:
ese ejemplo está destinado a Docker Compose. Sin configuración adicional, la
base se guarda en `data/geopol.db` y los archivos en `data/storage`.

Si PowerShell bloquea los scripts, utiliza la solución indicada en
[Problemas frecuentes](#problemas-frecuentes) y vuelve a ejecutar este paso.

## 4. Crear el usuario de acceso

En la misma terminal, desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe -m geopol.cli create-user --username administrador --role admin
```

La terminal pedirá una contraseña de **al menos 12 caracteres**. Escríbela y
presiona Enter; es normal que no se vean los caracteres mientras escribes.

Las credenciales de esta nueva instalación serán:

- **Usuario:** `administrador`.
- **Contraseña:** la que acabas de elegir.

No hay una contraseña predeterminada. Las cuentas, contraseñas y datos de otra
computadora no se incluyen en GitHub. Este paso se hace una sola vez; repetirlo
con un usuario existente no cambia su contraseña.

## 5. Iniciar GeoPol

Abre **tres terminales de PowerShell** y deja cada una ejecutándose. Si elegiste
otra carpeta al descargar el proyecto, sustituye la ruta de los ejemplos.

### Terminal 1: API

```powershell
Set-Location "$env:USERPROFILE\proyectos\GeoPol"
.\scripts\dev.ps1 api
```

Debe aparecer un mensaje que indique que Uvicorn está disponible en
`http://127.0.0.1:8000`.

### Terminal 2: procesamiento de archivos

```powershell
Set-Location "$env:USERPROFILE\proyectos\GeoPol"
.\scripts\dev.ps1 worker
```

El worker ejecuta procesamientos y exportaciones. Puede permanecer esperando sin
mostrar actividad cuando no hay trabajos. **Mantén un solo worker** para esta
instalación con SQLite.

### Terminal 3: aplicación web

```powershell
Set-Location "$env:USERPROFILE\proyectos\GeoPol"
.\scripts\dev.ps1 frontend
```

Vite mostrará la dirección de la web. Normalmente será:

**[Abrir GeoPol: http://127.0.0.1:5173](http://127.0.0.1:5173/)**

Si 5173 está ocupado, utiliza el puerto alternativo que indique Vite. Introduce
el usuario y la contraseña creados en el paso 4.

| Servicio             | Dirección predeterminada           | Función                        |
| -------------------- | ---------------------------------- | ------------------------------ |
| Aplicación web       | `http://127.0.0.1:5173`            | Interfaz de usuario            |
| API                  | `http://127.0.0.1:8000`            | Acceso a datos y operaciones   |
| Estado de API y base | `http://127.0.0.1:8000/api/health` | Comprobación técnica           |
| Documentación de API | `http://127.0.0.1:8000/docs`       | Referencia técnica opcional    |
| Worker               | No tiene una página propia         | Procesamiento en segundo plano |

Estos son los puertos de los scripts incluidos en GitHub. Las direcciones
**5174 y 8002** utilizadas en la computadora de desarrollo corresponden a una
configuración local particular y no son necesarias para una instalación nueva.
La carpeta `.local` tampoco forma parte del repositorio.

## 6. Comprobar que funciona

Con las tres terminales abiertas, visita
[el estado de la API](http://127.0.0.1:8000/api/health). Debe mostrar
`"status": "ok"` y `"database": "ok"`.

Después inicia sesión en la web. Verás los cinco módulos: **Vista general,
Validación, Procedimientos, Estadística y Documentación**. Una instalación nueva
comienza sin procesamientos ni referencias importadas.

### Primera prueba con datos ficticios

1. En **Vista general**, adjunta `examples/denuncias_sinteticas.csv` en
   **SIDPOL / DATACRIM**. El sistema admite CSV además de Excel.
2. Para comprobar el recorrido básico, puedes dejar las referencias vacías.
   Los resultados indicarán las limitaciones de referencia que correspondan.
3. Pulsa **Continuar validación** y revisa las columnas sugeridas. Elige el flujo
   de procesamiento ofrecido y completa los campos obligatorios.
4. Si para este ejemplo declaras `EPSG:4326`, documenta como fuente
   «Coordenadas sintéticas WGS84 del ejemplo incluido». En archivos propios,
   confirma el sistema únicamente con información del proveedor.
5. Inicia el procesamiento y consulta su avance en **Procedimientos**. Después
   revisa resultados y exportaciones en **Estadística**.

El CSV contiene **12 filas**, con una ubicación repetida: filas de origen y
ubicaciones no tienen por qué dar el mismo total. Esta prueba sin referencias
comprueba el funcionamiento del flujo; no debe esperarse que todas las
ubicaciones sean aceptadas automáticamente.

Para probar las cinco referencias en Excel y la resolución por etapas, consulta
la [guía del flujo por calidad](quality-workflow.md). Los
[ejemplos incluidos](../examples/README.md) son ficticios y están separados de los
archivos institucionales.

La respuesta de `/api/health` confirma API y base, pero no el worker. Si un
procesamiento o una exportación permanece en cola, revisa la terminal 2. El
endpoint `/api/health/worker`, disponible con una sesión autenticada, permite
consultar su actividad reciente.

### Generar Excel de prueba (opcional)

Si prefieres probar la carga de un Excel principal y las cinco referencias,
ejecuta desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe .\frontend\e2e\fixtures\quality_excels.py .\.local\ejemplos
```

El generador incluido en el proyecto crea estos archivos ficticios:

| Archivo en `.local/ejemplos` | Dónde adjuntarlo        |
| ---------------------------- | ----------------------- |
| `pnp.xlsx`                   | SIDPOL / DATACRIM       |
| `doors.xlsx`                 | Puertas / viviendas     |
| `roads.xlsx`                 | Vías y cuadras          |
| `centers.xlsx`               | Centros poblados        |
| `boundaries.xlsx`            | Límites administrativos |
| `jurisdictions.xlsx`         | Jurisdicciones          |

En cada referencia, lee las columnas y completa nombre, versión y procedencia.
Para estos archivos, la fuente puede ser «Datos sintéticos de GeoPol», la versión
«prueba-local» y la evidencia de `EPSG:4326` «Fixture sintética WGS84 incluida en
el proyecto». Guarda y utiliza cada referencia antes de continuar a Validación.
La carpeta de ejemplos se crea localmente y queda excluida de Git; volver a
ejecutar el generador sobrescribe únicamente estos seis archivos de ejemplo.

## 7. Detener y volver a ejecutar

Para detener GeoPol, pulsa **Ctrl + C** en cada una de las tres terminales.
Cerrar solo el navegador no detiene los servicios.

Para utilizarlo otro día, repite únicamente el **paso 5**. No necesitas instalar
de nuevo las dependencias ni volver a crear el usuario. La base, los archivos y
los procesamientos permanecen en `data/`.

## 8. Actualizar desde GitHub

Detén los tres servicios. Si necesitas conservar información, copia la carpeta
`data` completa a una ubicación de respaldo **con API y worker detenidos**;
incluye la base y `storage` en el mismo respaldo. Si configuraste rutas distintas
en `.env`, respalda esas ubicaciones.

Desde la raíz del proyecto:

```powershell
git status --short
git pull --ff-only origin main
.\scripts\setup.ps1
```

Si `git status` muestra archivos de código modificados, conserva o resuelve esos
cambios antes de actualizar. Si un comando falla, resuelve el error antes de
continuar. `setup.ps1` actualiza las dependencias y aplica migraciones pendientes
sin recrear usuarios ni borrar los datos existentes. Después repite el paso 5.

## Problemas frecuentes

Las indicaciones sobre `setup.ps1`, Vite y las tres terminales corresponden al
método manual de esta guía. En el método simplificado, `instalar.cmd` prepara
también la interfaz compilada y `iniciar.cmd` administra los tres procesos.

| Problema                                              | Qué hacer                                                                                                                                                                                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GitHub dice «Repository not found» o pide acceso      | Comprueba que aceptaste la invitación al repositorio privado y que Git usa la cuenta invitada.                                                                                                                                                         |
| `python`, `node` o `git` no se reconoce               | Revisa la instalación y el PATH. Cierra PowerShell y abre una terminal nueva.                                                                                                                                                                          |
| `python` abre Microsoft Store o apunta a otra versión | Utiliza la ruta del Python instalado: `.\scripts\setup.ps1 -PythonCommand "C:\ruta\a\python.exe"`. Sustituye la ruta por la real.                                                                                                                      |
| PowerShell bloquea `.ps1` o `npm.ps1`                 | En esa terminal, ejecuta `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` y repite el comando. El ajuste termina al cerrar la terminal; no modifica la política global. Si una política institucional lo impide, consulta a soporte. |
| El puerto 8000 está ocupado                           | Cierra la instancia anterior de GeoPol si es tuya. Si pertenece a otra aplicación, usa la alternativa explicada debajo.                                                                                                                                |
| La web abre, pero muestra errores de conexión         | Confirma que la API está activa y que `frontend/vite.config.ts` apunta al puerto correcto. Reinicia el frontend tras cambiar esa configuración.                                                                                                        |
| `/api/health` indica base sin inicializar             | Desde la raíz ejecuta `.\backend\.venv\Scripts\python.exe -m geopol.cli init-db`. API, worker y CLI deben usar la misma configuración.                                                                                                                 |
| Usuario o contraseña incorrectos                      | Usa la cuenta creada en esta computadora. `create-user` no restablece contraseñas de usuarios existentes.                                                                                                                                              |
| El procesamiento o la exportación queda en cola       | Comprueba que la terminal del worker continúa abierta y sin errores. No abras varios workers para intentar acelerarlo.                                                                                                                                 |
| Falla la descarga de dependencias                     | Comprueba acceso a Internet y, si corresponde, el proxy de la siguiente sección. Para errores de certificados corporativos, utiliza la configuración indicada por soporte.                                                                             |

### Opciones del iniciador de Windows

Si utilizas los iniciadores anteriores `instalar.cmd` e `iniciar.cmd`, puedes
elegir otros puertos sin editar la configuración del frontend:

```powershell
.\iniciar.cmd --api-port 8002 --port 5174
```

La web se abre en `http://127.0.0.1:5174` y su proxy apunta a la API elegida.
El iniciador avisa si un puerto está ocupado; no detiene otra aplicación ni
escoge un puerto diferente automáticamente. Para mantener los puertos habituales
sin abrir una pestaña del navegador, utiliza `.\iniciar.cmd --no-browser`.
Los registros de este método quedan en `.local/runtime`.

Si Python tiene otra ruta, pásala al instalador:

```powershell
.\instalar.cmd -PythonCommand "C:\ruta\a\python.exe"
```

No combines `iniciar.cmd` con los tres servicios del método manual. Para volver
al método simplificado después de una actualización manual, ejecuta
`instalar.cmd` antes de iniciar: así se recompila la interfaz.

### Usar otro puerto para la API en el método manual

Si necesitas evitar el puerto 8000, sustituye **solo el comando de la terminal 1**
por este, ejecutándolo desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn geopol.main:app --host 127.0.0.1 --port 8002 --reload --no-access-log
```

En `frontend/vite.config.ts`, cambia el destino del proxy `/api` de
`http://127.0.0.1:8000` a `http://127.0.0.1:8002` y reinicia la terminal del
frontend. El comando del worker no cambia. Consulta la salud de la API en el
nuevo puerto. No es necesario cambiar el puerto de la web.

### Proxy institucional (opcional)

Aplica esta sección únicamente si tu equipo necesita el proxy de la red INEI
indicado para el proyecto. Fuera de esa red, omítela o utiliza la configuración
que te proporcione soporte.

En la terminal donde vas a clonar o instalar:

```powershell
$env:HTTP_PROXY = "http://mikasa.inei.gob.pe:3128"
$env:HTTPS_PROXY = "http://mikasa.inei.gob.pe:3128"
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:npm_config_proxy = $env:HTTP_PROXY
$env:npm_config_https_proxy = $env:HTTPS_PROXY
```

Después ejecuta el comando que necesitabas, por ejemplo `git clone` o
`.\scripts\setup.ps1`. Estas variables se aplican solo a esa terminal y a sus
procesos hijos. Si cierras la terminal, debes configurarlas nuevamente cuando
sean necesarias. `NO_PROXY` mantiene las conexiones locales fuera del proxy.

## Linux o macOS: método manual anterior con SQLite

Con Git, Python 3.11 o superior y Node.js 24 o superior ya instalados:

```bash
git clone https://github.com/Jandroel/GeoPol.git
cd GeoPol
bash scripts/setup.sh
backend/.venv/bin/python -m geopol.cli create-user --username administrador --role admin
```

Después, desde la raíz del proyecto y en **tres terminales separadas**:

```bash
# Terminal 1
bash scripts/dev.sh api
```

```bash
# Terminal 2
bash scripts/dev.sh worker
```

```bash
# Terminal 3
bash scripts/dev.sh frontend
```

Las direcciones y el funcionamiento son los mismos que en Windows. Si Python
tiene otro ejecutable, indícalo al instalar, por ejemplo
`PYTHON=python3.11 bash scripts/setup.sh`.

## Qué se comparte y qué permanece en cada computadora

GitHub contiene código, documentación, recursos visuales y ejemplos ficticios.
Las cuentas, bases, archivos importados, exportaciones y configuraciones locales
permanecen en cada instalación; no se deben añadir al repositorio.

Todos los servicios de esta guía escuchan en `127.0.0.1`: la aplicación se utiliza
desde la misma computadora. Para un despliegue compartido en una red, consulta
el [manual de operación](runbook.md) y la [guía de seguridad](security.md).
