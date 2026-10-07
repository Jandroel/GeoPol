# Nota para instalaciones anteriores

Para una computadora nueva, sigue [INSTALACION_LOCAL.md](../INSTALACION_LOCAL.md):
crea tu base PostgreSQL, configura `backend/.env`, instala las dependencias y
ejecuta `python -m geopol.dev` y `npm run dev` en terminales separadas.
La [guía Bash detallada](instalacion-bash-detallada.md) amplía esos pasos.

Esta página sirve únicamente para conservar datos de quienes ya usaban otro
método de arranque. El cambio de comandos no migra datos entre bases.

## Si utilizabas los scripts Bash anteriores

Los antiguos `instalar.sh`, `iniciar.sh` y `detener.sh` usaban
`.local/native.json` para la conexión y `data/storage-native` para los archivos.
Conserva una copia privada de esa configuración y respalda la base antes de
cambiar de método. No vuelvas a crear una base que ya contenga tus datos.

Para seguir utilizando esa misma base con el arranque por carpetas:

1. Detén la instancia anterior.
2. Prepara `backend/.env` desde `backend/.env.example`.
3. Copia el valor de `database_url` de tu configuración anterior a
   `GEOPOL_DATABASE_URL`, sin compartirlo: contiene una contraseña.
4. Establece `GEOPOL_STORAGE_PATH` con la ruta de tus archivos anteriores;
   normalmente `../data/storage-native` al ejecutar desde `backend`.
5. Instala las dependencias e inicia el backend y el frontend como indica la
   guía principal. Comprueba que conserva tus usuarios y resultados.

Los puertos habituales son `8000` para la API y `5173` para la web; no se
importan los puertos guardados en la configuración anterior.

## Si utilizabas Windows CMD o SQLite

`instalar.cmd`, `iniciar.cmd`, `scripts/setup.ps1` y `scripts/setup.sh`
pertenecen al flujo anterior. Habitualmente utilizaba una base
`data/geopol.db`, archivos en `data/storage` y un `.env` en la raíz. Conserva
las rutas reales de tu configuración si son distintas.

Detén la API y el trabajador antes de obtener un respaldo consistente de esa
base. Conserva sus archivos auxiliares SQLite cuando existan o utiliza la API
de respaldo de SQLite: copiar solo el archivo principal mientras hay conexiones
puede omitir cambios del WAL. La [evidencia de recuperación](validation.md)
documenta los ensayos anteriores con datos sintéticos.

Crear una nueva base PostgreSQL no importa automáticamente los usuarios,
procesamientos ni archivos de SQLite. Conserva la instalación y su respaldo
hasta preparar y verificar una migración explícita. Para una prueba nueva,
puedes usar los [ejemplos ficticios incluidos](../examples/README.md).
