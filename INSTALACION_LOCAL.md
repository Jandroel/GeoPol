# GeoPol: instalación rápida en Windows

Una vez descargado el proyecto, utiliza **dos comandos**: `instalar.cmd` prepara
la aplicación y `iniciar.cmd` la abre. Trabajarás con una sola terminal.

## Antes de comenzar

Necesitas estas herramientas instaladas y disponibles en una terminal nueva:

- [Git para Windows](https://git-scm.com/install/windows).
- [Python de 64 bits](https://www.python.org/downloads/windows/), versión 3.11 o
  superior. Las dependencias del proyecto se verifican con Python 3.11.
- [Node.js](https://nodejs.org/en/download/), versión 24 o superior, con npm.

La instalación descarga dependencias de Internet. No necesitas Docker,
PostgreSQL ni Microsoft Excel instalado. Si tu red exige proxy, configura la
[conexión institucional](docs/instalacion-local-detallada.md#proxy-institucional-opcional)
antes de descargar o instalar.

## 1. Descargar el proyecto

Acepta la invitación al repositorio privado con tu cuenta de GitHub. Abre
PowerShell en la carpeta donde quieras guardar el proyecto y ejecuta:

```powershell
git clone https://github.com/Jandroel/GeoPol.git
Set-Location GeoPol
```

Si ya tienes el proyecto, entra en su carpeta; no necesitas volver a clonarlo.

## 2. Instalar: la primera vez

Desde la carpeta `GeoPol`:

```powershell
.\instalar.cmd
```

El comando instala las dependencias, prepara la base y compila la interfaz.
En una instalación nueva crea el usuario **`administrador`** y te pide elegir
una contraseña de **al menos 12 caracteres**. Al escribirla no se muestran los
caracteres. Guárdala: no existe una contraseña predeterminada.

Si la base ya contiene usuarios, conserva esas cuentas y no solicita otra
contraseña. Espera a que termine la instalación antes de continuar.

## 3. Abrir GeoPol

En la misma terminal:

```powershell
.\iniciar.cmd
```

El comando inicia la API, el procesamiento de archivos y la web, y abre el
navegador. Inicia sesión con tu cuenta; en una instalación nueva, el usuario es
`administrador` y la contraseña es la que elegiste al instalar.

La dirección habitual es **[http://127.0.0.1:5173](http://127.0.0.1:5173/)**.
Mantén abierta esta terminal mientras utilices GeoPol. Para cerrar los tres
servicios, pulsa **Ctrl + C** en ella; cerrar el navegador no los detiene.

**Los siguientes días solo necesitas ejecutar `.\iniciar.cmd`.** No reinstales
ni vuelvas a crear la cuenta. Los archivos y procesamientos se conservan.

## Si aparece un problema

| Situación | Qué hacer |
| --- | --- |
| GitHub indica que no tienes acceso | Acepta la invitación y utiliza la cuenta de GitHub invitada. |
| Falta Python, Node.js o npm | Instala las herramientas indicadas y abre una terminal nueva. |
| La instalación no termina | Revisa el error en la terminal y la [guía detallada](docs/instalacion-local-detallada.md#problemas-frecuentes); después repite `instalar.cmd`. |
| GeoPol ya está abierto | Usa la instancia existente o ciérrala con Ctrl + C antes de iniciar otra. |
| Un puerto está ocupado por otra aplicación | Usa las [opciones de puertos](docs/instalacion-local-detallada.md#opciones-del-iniciador-de-windows). |
| No se abre el navegador | Abre la dirección que muestra la terminal. |

El iniciador guarda los registros técnicos en `.local/runtime`. No abre
automáticamente otros puertos ni requiere mantener tres terminales separadas.

## Actualizar una instalación existente

Cierra GeoPol con Ctrl + C. Si tienes datos que conservar, respalda la carpeta
`data` completa con los servicios detenidos. Para rutas personalizadas, sigue
las [indicaciones de respaldo](docs/runbook.md#evidencia-de-recuperación-local).
Desde la carpeta del proyecto, revisa tus cambios y actualiza:

```powershell
git status --short
git pull --ff-only origin main
.\instalar.cmd
.\iniciar.cmd
```

Si hay cambios locales o un comando falla, resuélvelo antes de continuar.
La instalación aplica las migraciones pendientes y conserva usuarios y datos.

## Probar la aplicación y consultar detalles

Para una primera prueba, usa los [ejemplos ficticios incluidos](examples/README.md)
o [genera los Excel de demostración](docs/instalacion-local-detallada.md#generar-excel-de-prueba-opcional).
Una instalación nueva comienza sin archivos ni referencias importados.

La [guía detallada](docs/instalacion-local-detallada.md) conserva el método manual,
el proxy y las instrucciones para Linux/macOS. En Windows, los datos se guardan
por defecto en `data/geopol.db` y `data/storage`; no necesitas crear `.env`.
