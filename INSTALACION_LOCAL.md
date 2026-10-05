# GeoPol: instalar y usar con Bash

Esta guía sirve para **Windows con Git Bash** y **Linux con Bash**.
Después de preparar Docker, instalarás GeoPol con un comando y lo abrirás
con otro. No necesitas saber programar ni instalar Python, Node.js o PostgreSQL
por separado.

## 1. Preparar la computadora: solo una vez

Docker ejecuta GeoPol y su base de datos en espacios preparados, como cajas que
ya contienen las herramientas necesarias. Necesitas Internet para descargarlas.

**En Windows:**

1. Instala [Git para Windows](https://git-scm.com/install/windows). Incluye
   **Git Bash**, la terminal donde pegarás los comandos de esta guía.
2. Instala [Docker Desktop siguiendo su guía oficial](https://docs.docker.com/desktop/setup/install/windows-install/).
   Utiliza el modo de contenedores Linux y completa los pasos de WSL 2 que
   indique el instalador; reinicia Windows si te lo solicita.
3. Abre **Docker Desktop** desde Inicio y espera a que su motor esté funcionando.
   Debe permanecer activo mientras uses GeoPol.

En una entidad pública, Docker Desktop requiere una suscripción de pago;
utiliza la instalación autorizada por tu institución. Véanse las
[condiciones oficiales](https://docs.docker.com/desktop/setup/install/windows-install/#start-docker-desktop).

**En Linux:** usa la terminal Bash e instala Docker Engine y el complemento
Compose según tu distribución. Para Ubuntu, sigue la
[instalación oficial](https://docs.docker.com/engine/install/ubuntu/) y la
[configuración de acceso a Docker](https://docs.docker.com/engine/install/linux-postinstall/).
El proyecto requiere **Docker Compose 2.20 o superior**.

## 2. Descargar el proyecto de GitHub

El repositorio es [Jandroel/GeoPol](https://github.com/Jandroel/GeoPol).
Si es privado, primero acepta la invitación con tu cuenta de GitHub.

**La forma más sencilla es descargar un ZIP:**

1. Abre el enlace del repositorio e inicia sesión en GitHub.
2. Pulsa el botón verde **Code** y luego **Download ZIP**.
3. Extrae el ZIP en una carpeta que puedas encontrar. No trabajes dentro del ZIP.
4. Abre la carpeta extraída, normalmente `GeoPol-main`. Debes ver los archivos
   `instalar.sh`, `iniciar.sh` y `compose.yaml`.
5. En Windows, haz clic derecho en un espacio vacío de esa carpeta y elige
   **Open Git Bash here**. En Windows 11 puede estar en **Mostrar más opciones**.

GitHub explica la descarga en su [guía oficial de archivos ZIP](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives).
Si prefieres descargar con Git, abre Bash en la carpeta de destino y ejecuta:

```bash
git clone https://github.com/Jandroel/GeoPol.git
cd GeoPol
```

En Linux, abre la terminal y entra en la carpeta extraída, por ejemplo:

```bash
cd "$HOME/Descargas/GeoPol-main"
```

Cambia la ruta si elegiste otra ubicación. Las comillas permiten usar carpetas
con espacios. Todos los comandos siguientes se ejecutan desde esa misma carpeta.

## 3. Instalar GeoPol: la primera vez

En Bash, copia esta línea y pulsa Enter:

```bash
bash instalar.sh
```

La primera descarga puede tardar varios minutos. El instalador prepara la web,
la aplicación y **PostgreSQL 16 con PostGIS 3.5**, su base de datos.
Si aún no hay usuarios, crea la cuenta **`administrador`** y te pide elegir y
repetir una contraseña de **al menos 12 caracteres**.

Es normal que no aparezcan letras ni asteriscos al escribir la contraseña.
Guárdala: es la que usarás para entrar a GeoPol. Si ya existen cuentas, se
conservan y no se solicita otra contraseña. Espera el mensaje **«GeoPol está listo»**;
si aparece un error, consulta la ayuda al final.

## 4. Abrir GeoPol

```bash
bash iniciar.sh
```

Abre **[http://localhost:8080](http://localhost:8080)** en tu navegador.
Entra con `administrador` y la contraseña que elegiste. Puedes cerrar la
terminal: GeoPol sigue funcionando mientras Docker esté activo.

**Los siguientes días:** abre Docker Desktop si usas Windows, entra en la
carpeta del proyecto con Bash y ejecuta solamente `bash iniciar.sh`.

Para detener GeoPol, vuelve a esa carpeta en Bash y ejecuta:

```bash
bash detener.sh
```

Esto conserva usuarios, archivos y resultados. Cerrar el navegador no detiene
GeoPol.

## 5. PostgreSQL y tus datos, explicado brevemente

PostgreSQL guarda las cuentas, los trabajos y sus resultados. El instalador
crea la base y su contraseña interna automáticamente: **no tienes que abrir
PostgreSQL ni crear tablas**. Esa contraseña es distinta de la de `administrador`.

Los datos se guardan en espacios persistentes administrados por Docker, llamados
volúmenes. El archivo `.local/compose.env` contiene la configuración y una
contraseña privada: **no lo borres, edites ni compartas**. Tampoco borres los
volúmenes de Docker si deseas conservar los datos.

Para compartir el proyecto, envía el enlace de GitHub y esta guía. Cada persona
instala su propia copia y elige su contraseña; GitHub no comparte tus datos ni
tus cuentas. Una instalación anterior con SQLite no se migra automáticamente.

## Si algo no funciona

| Lo que aparece | Qué hacer |
| --- | --- |
| `bash` no se reconoce | En Windows, abre **Git Bash** desde la carpeta del proyecto. |
| `instalar.sh: No such file or directory` | Entra en la carpeta extraída que contiene `instalar.sh`. |
| Docker no está disponible | Abre Docker Desktop y espera a que termine de iniciar. |
| Contraseña demasiado corta o distinta | El instalador vuelve a pedirla. Escribe dos veces la misma contraseña, de al menos 12 caracteres. |
| El puerto está ocupado o falla una descarga | Consulta [puertos, proxy y problemas frecuentes](docs/instalacion-bash-detallada.md#problemas-frecuentes). |

La [guía Bash detallada](docs/instalacion-bash-detallada.md) incluye respaldos,
actualizaciones y acceso técnico a PostgreSQL. Para una primera prueba, usa los
[ejemplos ficticios incluidos](examples/README.md).
