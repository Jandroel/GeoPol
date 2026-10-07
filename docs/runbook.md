# Operación y recuperación

La [guía de instalación](../INSTALACION_LOCAL.md) explica la preparación inicial:
crear una base PostgreSQL con PostGIS, configurar `backend/.env` e instalar las
dependencias de backend y frontend. Los comandos de este documento se ejecutan
en Bash. PostgreSQL debe estar funcionando como servicio.

## Arranque y parada

Abre una terminal en `backend`, activa el entorno virtual y ejecuta:

```bash
# Git Bash en Windows:
source .venv/Scripts/activate

# En Linux o macOS, usa en su lugar:
# source .venv/bin/activate

python -m geopol.dev
```

Este comando lee `backend/.env`, aplica las migraciones pendientes y arranca la
API y el worker juntos. En una base sin usuarios solicita la contraseña inicial
de `administrador`; en los siguientes arranques conserva las cuentas existentes.

Abre otra terminal en `frontend`:

```bash
npm run dev
```

Entra a <http://127.0.0.1:5173>. Mantén ambas terminales abiertas. Para detener
GeoPol, pulsa **Ctrl+C en cada una**. PostgreSQL continúa funcionando y los datos
se conservan. No necesitas reinstalar dependencias cada vez que inicias la app.

## Salud y configuración

Desde otra terminal puedes comprobar la API:

```bash
curl --fail http://127.0.0.1:8000/api/health
```

`GET /api/health` comprueba API y base de datos. No certifica que el worker esté
procesando: revisa también `GET /api/health/worker` con sesión autenticada, la
terminal del backend y los estados de las ejecuciones. Un archivo cargado no
comienza a procesarse hasta crear su ejecución. `COMPLETED` y
`COMPLETED_WITH_ISSUES` indican terminación técnica, no que todas las ubicaciones
hayan sido aprobadas.

Ejecuta también las herramientas `python -m geopol.cli` desde `backend`, con el
entorno virtual activado. Así utilizan el mismo `.env` que la app. La conexión
se define en `GEOPOL_DATABASE_URL`; `GEOPOL_STORAGE_PATH=../data/storage` guarda
los originales y exportaciones en `data/storage`, en la raíz del proyecto.
Una variable `GEOPOL_*` exportada en la terminal tiene prioridad sobre `.env`.

Las instalaciones anteriores conservan su base y sus archivos. Cambiar la
conexión o la ruta no traslada datos: comprueba que ambos apuntan a la misma
instalación antes de iniciar. El arranque no importa automáticamente otra base.

## Almacenamiento para lotes grandes

PostgreSQL administra sus propios archivos de base de datos. GeoPol guarda los
originales y las exportaciones en la carpeta indicada por `GEOPOL_STORAGE_PATH`.
Planifica espacio para la base, originales, exportaciones y respaldos. El
traslado del directorio de datos de PostgreSQL debe realizarlo su administrador.

La [prueba de carga](validation-load.md) documenta un ensayo anterior con SQLite
y almacenamiento HDD/SSD. Sus tiempos no son una medición de la instalación
PostgreSQL actual. Para conservar una instalación SQLite anterior, respalda
su base y almacenamiento del mismo corte y mantén un solo worker.

## Usuarios

Para crear un operador adicional, abre una terminal en `backend` y activa su
entorno virtual. Ejecuta este bloque; la contraseña se solicita de forma oculta
y debe tener al menos 12 caracteres:

```bash
(
  set -eu
  IFS= read -r -s -p 'Contraseña del nuevo usuario: ' GEOPOL_BOOTSTRAP_PASSWORD
  printf '\n'
  export GEOPOL_BOOTSTRAP_PASSWORD
  python -m geopol.cli create-user --username operador01 --role operator
  unset GEOPOL_BOOTSTRAP_PASSWORD
)
```

Cambia el nombre y el rol para crear otra cuenta. Los roles son `admin`,
`operator`, `reviewer` y `analyst`; consulta la
[matriz de permisos](security.md#matriz-funcional). El comando no reemplaza
contraseñas de usuarios existentes. Usa cuentas individuales para el trabajo
habitual. La contraseña de acceso a GeoPol es distinta de la de PostgreSQL.

## Trabajo detenido o fallido

1. Confirma la salud de la base y el espacio en disco. Revisa el error de la
   ejecución y la terminal del backend sin copiar datos sensibles a otros sistemas.
2. Si el worker terminó, pulsa Ctrl+C en la terminal del backend y vuelve a
   ejecutar `python -m geopol.dev`. La cola y los checkpoints residen en la base;
   una reserva vigente puede impedir reclamar el trabajo hasta vencer.
3. Para un trabajo `FAILED` o `CANCELLED`, utiliza **Reintentar**. Para aplicar
   otro procesamiento conservando el histórico, usa **Reprocesar**, que crea
   una nueva ejecución.
4. Corrige archivos o catálogos inválidos mediante una nueva carga o versión.
   No edites los originales persistidos ni filas de la base para forzar estados.
5. Si la revisión devuelve un conflicto, vuelve a cargar el resultado y
   comprueba su reserva y revisión actual.

La cancelación es cooperativa: puede tardar hasta un límite de procesamiento.
Los resultados ya persistidos se conservan. No elimines archivos de datos
mientras existan trabajos que los referencian.

Si una carga devuelve repetidamente «La carga está ocupada» después de una
caída, puede quedar un archivo `uploads/<id>.lock` dentro del almacenamiento.
Detén GeoPol, comprueba que su proceso ya no esté activo y que el UUID
corresponda a esa carga; solo entonces retira ese bloqueo específico. Conserva
el original y los demás bloqueos. Al reiniciar, consulta el offset efectivo
de la carga para continuar desde allí.

## Respaldo de PostgreSQL y archivos

Detén ambas terminales de GeoPol antes de copiar. Deja PostgreSQL encendido.
Desde la **raíz del proyecto**, ejecuta este ejemplo si utilizas la base
`geopol`, el rol `geopol_app` y la carpeta `data/storage` de la guía:

```bash
geopol_backup="../geopol-respaldo-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$geopol_backup"
pg_dump -h 127.0.0.1 -p 5432 -U geopol_app -W -Fc -f "$geopol_backup/geopol.dump" geopol
tar -czf "$geopol_backup/archivos.tgz" -C data storage
```

`pg_dump` pide la contraseña del rol PostgreSQL. Si cambiaste host, puerto,
usuario, base o almacenamiento en `backend/.env`, ajusta los comandos a esos
valores. Comprueba que cada comando terminó correctamente antes de continuar.
Si Bash no encuentra `pg_dump`, añade la carpeta `bin` de PostgreSQL a `PATH`
como indica la [guía detallada](instalacion-bash-detallada.md).

La base y los archivos deben corresponder al mismo corte. Conserva aparte una
copia privada de `backend/.env`, con acceso restringido. Registra fecha,
versión de la aplicación y checksums. Un respaldo operativo debe tener una
prueba de recuperación en una instancia separada. Para uso institucional,
acuerda la frecuencia de copias, la retención y los tiempos de recuperación.

## Restauración en una instancia vacía

Este procedimiento es para quien administra PostgreSQL. Ensáyalo en otra
instancia compatible con PostGIS y en una carpeta de proyecto separada.

1. Verifica el respaldo y conserva intacta la instalación original.
2. Prepara PostgreSQL de destino en otro puerto o equipo. Crea el mismo rol
   limitado indicado en el `.env` respaldado y una **base vacía propiedad de
   ese rol**. El respaldo de `pg_dump` no incluye los roles globales del servidor.
3. Restaura como administrador sobre esa base vacía. El siguiente ejemplo
   supone una instancia separada en el puerto **5433** y una base `geopol`:

```bash
pg_restore -h 127.0.0.1 -p 5433 -U postgres -W -d geopol --exit-on-error "../geopol-respaldo/geopol.dump"
```

Sustituye la ruta por la real. La base debe estar vacía: no arranques GeoPol
antes de restaurar. El administrador permite restaurar también las extensiones
PostGIS incluidas en el respaldo. Si falla, investiga el error antes de continuar.

4. Desde la raíz de la copia del proyecto, restaura los archivos en una carpeta
   `data` vacía:

```bash
mkdir -p data
tar -xzf "../geopol-respaldo/archivos.tgz" -C data
```

5. Recupera la copia privada de `backend/.env` y ajusta conexión y rutas al
   destino. Mantén la misma versión de GeoPol que produjo el respaldo.
6. Instala las dependencias según la [guía](../INSTALACION_LOCAL.md) y arranca
   el backend y el frontend en sus dos terminales. Si usas la misma computadora,
   detén la otra app antes del arranque para liberar sus puertos.

Verifica inicio de sesión, número de ejecuciones, descarga de un original
autorizado y una exportación, checksums, lectura del histórico y un nuevo
trabajo sintético. Registra el tiempo y el resultado de la prueba. Mantén la
instancia original hasta validar la recuperación.

La prueba `test_sqlite_database_and_objects_restore_together` demuestra la
restauración de un escenario SQLite acotado con datos sintéticos. Esa evidencia
histórica no acredita la restauración de PostgreSQL. En SQLite, una copia
consistente mediante `sqlite3.Connection.backup` incluye los cambios del WAL;
copiar solo `geopol.db` mientras está activo puede omitir cambios.

## Actualizaciones

Respalda y detén GeoPol antes de actualizar el código. Desde `backend`, con el
entorno virtual activado, actualiza las dependencias:

```bash
python -m pip install -c requirements.lock -e .
```

Desde `frontend`, ejecuta:

```bash
npm ci
```

Después inicia cada parte como de costumbre. `python -m geopol.dev` aplica las
migraciones pendientes antes de arrancar la API y el worker. Conserva tu `.env`
y los datos al actualizar. Ensaya cambios de esquema y recuperación en una
copia cuando haya información que conservar.

## Exportación a GIS

Conserva juntos CSV y manifiesto. Verifica SHA-256 y registra ejecución, versión
de referencia, reglas y revisiones. Importa UBIGEO e identificadores como texto;
interpreta coordenadas vacías como ausencia de geometría. Las columnas
geográficas usan EPSG:4326 y orden explícito latitud/longitud; GeoJSON usa
longitud/latitud.

El modo seguro para hojas de cálculo puede prefijar apóstrofo a celdas que
parecen fórmulas. No lo retires automáticamente al abrir en Excel. Acuerda con
el consumidor GIS si utilizar ese perfil o una exportación no destinada a
hojas de cálculo.
