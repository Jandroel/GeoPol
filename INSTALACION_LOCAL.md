# GeoPol: instalar y usar con Bash

GeoPol se instala directamente en tu computadora. Esta guía sirve para
**Windows con Git Bash** y **Linux o WSL con Bash**. Prepararás las herramientas
una sola vez; después usarás `instalar.sh`, `iniciar.sh` y `detener.sh`.

## 1. Preparar la computadora: solo una vez

Necesitas Internet para la instalación, **Python 3.11 o superior**, **Node.js 24**
y **PostgreSQL 16 con PostGIS**. PostGIS es obligatorio: permite guardar y
consultar información geográfica. No necesitas crear tablas manualmente.

### Windows

1. Instala [Git para Windows](https://git-scm.com/install/windows). Incluye
   **Git Bash**, la terminal donde pegarás los comandos de esta guía.
2. Instala [Python para Windows](https://www.python.org/downloads/windows/),
   versión 3.11 o superior, de 64 bits. En el instalador clásico marca
   **Add Python to PATH** antes de instalar; esa opción permite encontrar Python
   desde Bash ([instrucciones oficiales](https://docs.python.org/3.11/using/windows.html#finding-the-python-executable)).
3. Instala [Node.js 24 LTS](https://nodejs.org/en/download), eligiendo el
   instalador de Windows. Incluye `npm`; conserva las opciones predeterminadas.
4. Descarga **PostgreSQL 16** desde la [página oficial para Windows](https://www.postgresql.org/download/windows/).
   En el instalador conserva **PostgreSQL Server**, **Command Line Tools** y
   **Stack Builder**. Usa el puerto **5432**, salvo que ya esté ocupado.
   Elige y guarda la contraseña del usuario **`postgres`**: GeoPol la pedirá
   durante su primera instalación.
5. Abre **Stack Builder**, selecciona la instalación PostgreSQL 16 y, dentro de
   **Spatial Extensions**, instala el paquete **PostGIS Bundle** compatible con
   esa versión. Es el procedimiento de la [guía oficial de PostGIS](https://postgis.net/workshops/en/postgis-intro/installation.html#postgresql-for-microsoft-windows).
   No hace falta crear una base de ejemplo.
6. Cierra las terminales abiertas y abre una nueva **Git Bash**. PostgreSQL debe
   estar funcionando como servicio de Windows; no necesitas mantener pgAdmin abierto.

### Linux o WSL

Usa la terminal Bash de tu distribución. La [preparación para Ubuntu 24.04](docs/instalacion-bash-detallada.md#preparar-ubuntu-2404-o-wsl)
incluye los comandos para Python, PostgreSQL y PostGIS, además de la instalación
de Node.js 24. Si eliges WSL, instala y ejecuta todas las herramientas dentro de
esa distribución y conserva allí el proyecto.

## 2. Descargar el proyecto de GitHub

Abre [Jandroel/GeoPol](https://github.com/Jandroel/GeoPol). Si es privado,
acepta primero la invitación con tu cuenta de GitHub.

1. Pulsa **Code → Download ZIP** y extrae el archivo.
2. Abre la carpeta extraída, normalmente `GeoPol-main`. Busca `instalar.sh`,
   `iniciar.sh` y `detener.sh`; si están en una subcarpeta, entra en ella.
3. En Windows, haz clic derecho en un espacio vacío de esa carpeta y elige
   **Open Git Bash here**; puede estar en **Mostrar más opciones**.

Si prefieres Git, ejecuta en Bash:

```bash
git clone https://github.com/Jandroel/GeoPol.git
cd GeoPol
```

En Linux puedes entrar en la carpeta del ZIP con `cd`, ajustando la ruta:

```bash
cd "$HOME/Descargas/GeoPol-main"
```

Todos los comandos siguientes se ejecutan desde la carpeta que contiene
`instalar.sh`. Las comillas permiten usar rutas con espacios.

## 3. Instalar GeoPol: la primera vez

Con PostgreSQL funcionando, escribe en Bash y pulsa Enter:

```bash
bash instalar.sh
```

El instalador descarga las dependencias y prepara la web. Después solicita:

| Pregunta | Qué escribir en una instalación nueva |
| --- | --- |
| Servidor PostgreSQL | Pulsa Enter para usar `127.0.0.1`, tu computadora. |
| Puerto PostgreSQL | Pulsa Enter para usar `5432`, o indica el elegido al instalar PostgreSQL. |
| Nombre de la base nueva | Pulsa Enter para usar `geopol`, si ese nombre está libre. |
| Usuario administrador de PostgreSQL | Pulsa Enter para usar `postgres`. |
| Contraseña de PostgreSQL | La que elegiste para `postgres` en el paso 1. |

La contraseña se escribe de forma oculta: es normal que no aparezcan letras ni
asteriscos. El instalador crea una base nueva, activa PostGIS y crea un usuario
interno con permisos limitados. Si el nombre de la base ya está ocupado, elige
otro nombre nuevo; no se sobrescribe una base existente.

Finalmente, si aún no hay cuentas, te pide elegir y repetir una contraseña de
**al menos 12 caracteres** para entrar a GeoPol como **`administrador`**. Usa
una contraseña distinta de la de PostgreSQL y guárdala. Espera el mensaje de
instalación terminada antes de continuar.

## 4. Abrir y detener GeoPol

```bash
bash iniciar.sh
```

Abre **[http://localhost:5173](http://localhost:5173)** e inicia sesión con
`administrador` y tu contraseña web. Este comando inicia la API, el proceso que
ejecuta los trabajos y la web. **Mantén esta terminal abierta mientras trabajas.**

Para terminar, pulsa **Ctrl+C** en esa terminal. También puedes abrir una
segunda Bash en la misma carpeta y ejecutar:

```bash
bash detener.sh
```

Se detienen los procesos de GeoPol y se conservan los datos. PostgreSQL continúa
funcionando como servicio. Cerrar el navegador no detiene GeoPol.

**Los siguientes días:** comprueba que PostgreSQL esté funcionando, abre Bash
en la carpeta del proyecto y ejecuta solamente `bash iniciar.sh`.

## 5. Conservar tus datos

PostgreSQL guarda las cuentas y resultados; `data/storage-native` guarda los
archivos. `.local/native.json` guarda la configuración y la contraseña interna
de la aplicación, **no la contraseña de administración de PostgreSQL**.
Conserva ese archivo privado: no lo borres, edites ni compartas.

Volver a ejecutar `bash instalar.sh` conserva la configuración, las cuentas y
los datos. Para compartir GeoPol, envía el enlace de GitHub y esta guía: cada
persona prepara su propia instalación. Las instalaciones anteriores conservan
sus datos por separado; este método no los importa automáticamente ni modifica
su archivo `.env`.

## Si algo no funciona

| Problema | Qué hacer |
| --- | --- |
| `bash` no se reconoce | En Windows, abre **Git Bash**. |
| No encuentra `instalar.sh` | Entra en la carpeta extraída que contiene ese archivo. |
| No encuentra Python o Node.js | Termina de instalarlos y abre una nueva Bash. |
| No conecta con PostgreSQL | Comprueba que su servicio esté iniciado y que el puerto y la contraseña sean correctos. |
| No encuentra PostGIS | Instala el paquete compatible con PostgreSQL 16 y repite `bash instalar.sh`. |
| El puerto web está ocupado | Usa `bash iniciar.sh --puertos 5174 8002` y abre la dirección que muestre. |

La [guía Bash detallada](docs/instalacion-bash-detallada.md) incluye respaldos,
actualizaciones y más soluciones. Para probar el programa, usa los
[ejemplos ficticios incluidos](examples/README.md).