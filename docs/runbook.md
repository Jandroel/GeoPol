# Operación y recuperación

Todos los comandos parten de la raíz del proyecto. No ejecutar acciones de borrado de volúmenes sobre una instancia con información que deba conservarse.

## Arranque y salud

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api worker
```

`GET /api/health` comprueba API y base de datos. No certifica que el worker esté procesando: revisar también `GET /api/health/worker` con sesión autenticada, los logs y los estados de las ejecuciones. Un archivo cargado no comienza a procesarse hasta crear su ejecución. Los estados `COMPLETED` y `COMPLETED_WITH_ISSUES` indican terminación técnica, no que todas las ubicaciones hayan sido aprobadas.

En local, mantener activas las tres terminales indicadas en el README. Los scripts fijan el directorio de trabajo a la raíz para que API, worker y CLI utilicen la misma base SQLite y almacenamiento.

## Usuarios

```bash
docker compose exec api python -m geopol.cli create-user --username operador01 --role operator
docker compose exec api python -m geopol.cli create-user --username revisor01 --role reviewer
docker compose exec api python -m geopol.cli create-user --username analista01 --role analyst
```

Introducir cada contraseña en el prompt. No compartir la cuenta de administración para el trabajo habitual. Para ejecución sin terminal interactiva, definir una variable temporal y utilizar `--password-env NOMBRE_VARIABLE`.

## Trabajo detenido o fallido

1. Confirmar salud de la base y espacio en disco. Revisar el error de la ejecución y los logs del worker sin copiar datos sensibles a sistemas externos.
2. Si el proceso worker cayó, reiniciarlo: `docker compose restart worker`. La cola y los checkpoints residen en la base; una reserva vigente puede impedir reclamar el trabajo hasta vencer.
3. Para un trabajo `FAILED` o `CANCELLED`, utilizar **Reintentar** en la ejecución. Para aplicar un nuevo procesamiento conservando el histórico, utilizar **Reprocesar**, que crea otra ejecución.
4. Corregir un archivo o catálogo inválido mediante una nueva carga/versión. No editar los originales persistidos ni manipular filas directamente para forzar un estado.
5. Si la revisión devuelve conflicto, volver a cargar el resultado y comprobar su reserva y revisión actual. Una decisión obsoleta no debe sobreescribir otra.

La cancelación es cooperativa: puede tardar hasta un límite de procesamiento. Los resultados ya persistidos se conservan. No eliminar archivos de la carpeta de datos mientras existan trabajos que los referencian.

Si una carga devuelve repetidamente «La carga está ocupada» después de una caída, puede quedar un archivo `uploads/<id>.lock`. Detener la API antes de inspeccionarlo, verificar que su proceso ya no está activo y que el UUID corresponde a esa carga; solo entonces retirar ese bloqueo específico. No eliminar el original ni otros bloqueos. Al reiniciar, consultar la carga para obtener el offset efectivo y continuar desde allí. El MVP no roba automáticamente un bloqueo que podría pertenecer a un escritor activo.

## Respaldo consistente del despliegue Compose

Respaldar base **y** originales/exportaciones del mismo corte. La siguiente receta detiene escrituras para una copia simple de piloto; un entorno institucional requiere su política de backups y pruebas de recuperación. El archivo de credenciales se conserva por separado en el almacén de secretos aprobado.

Crear una carpeta de backup fuera del repositorio y protegerla. Los comandos siguientes producen archivos locales: en PowerShell es preferible evitar redirección de datos binarios, por eso se utiliza `docker compose cp`.

```bash
docker compose stop frontend api worker
docker compose exec -T db pg_dump -U geopol -d geopol -Fc -f /tmp/geopol.dump
docker compose cp db:/tmp/geopol.dump ./geopol.dump
docker compose run --rm --no-deps --entrypoint tar api -czf /app/data/artifacts-backup.tgz -C /app/data storage
docker compose cp api:/app/data/artifacts-backup.tgz ./artifacts-backup.tgz
docker compose start api worker frontend
```

Mover los dos archivos a la ubicación de backup protegida, registrar fecha, versión de aplicación y checksum, y verificar que el archivo de objetos contiene la carpeta `storage`. La copia temporal dentro del volumen se puede eliminar **solo después** de verificar y mover el respaldo. No versionar los archivos de backup.

## Evidencia de recuperación local

La prueba automatizada `test_sqlite_database_and_objects_restore_together` crea un lote y una exportación con datos sintéticos, copia la base mediante `sqlite3.Connection.backup` y respalda los objetos mientras no hay escrituras. Restaura ambos en rutas nuevas y verifica salud, recuentos, SHA-256 de la exportación, conservación del original y un nuevo reproceso con el worker restaurado.

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q -k sqlite_database_and_objects_restore
```

Esta prueba demuestra la restauración de un escenario SQLite acotado. La copia consistente de SQLite incluye el estado WAL; copiar solo `geopol.db` mientras está activo puede omitir cambios. Para un respaldo operativo local, detener API y worker y copiar la base y `data/storage` como un mismo corte. No equivale a una prueba de restauración PostgreSQL ni a un objetivo institucional de recuperación; la receta Compose debe ensayarse donde esté disponible Docker.

## Procedimiento de restauración en una instancia vacía

Usar un proyecto Compose distinto evita sobrescribir la instancia original. Crear credenciales propias en `.env` antes de arrancar. Este ejemplo usa el proyecto `geopol-restore` y requiere tener las copias en la raíz de trabajo temporal:

```bash
docker compose -p geopol-restore up -d db
docker compose -p geopol-restore cp ./geopol.dump db:/tmp/geopol.dump
docker compose -p geopol-restore exec -T db pg_restore -U geopol -d geopol --no-owner --exit-on-error /tmp/geopol.dump
docker compose -p geopol-restore create api
docker compose -p geopol-restore cp ./artifacts-backup.tgz api:/app/data/artifacts-backup.tgz
docker compose -p geopol-restore run --rm --no-deps --entrypoint tar api -xzf /app/data/artifacts-backup.tgz -C /app/data
docker compose -p geopol-restore up -d
```

La restauración debe hacerse en un host/puerto que no compita con la instancia original. Esperar a que PostgreSQL esté saludable antes de restaurar y usar la misma versión compatible del esquema. El ejemplo no usa `--clean`: si la base no está vacía, detenerse y preparar una instancia vacía.

Verificar inicio de sesión, número de ejecuciones, descarga de un original autorizado/exportación, checksums, lectura del histórico y un nuevo trabajo sintético. Registrar tiempo de restauración y resultado; un backup sin prueba de restauración no acredita recuperación.

## Actualizaciones

Leer cambios de esquema y límites antes de actualizar. La inicialización `init-db` prepara el esquema inicial; no es un sistema general de migraciones. Respaldar, ensayar actualización/restauración en una copia y fijar versiones de imágenes/dependencias revisadas. Nunca usar la eliminación de volúmenes como mecanismo de actualización con datos reales.

## Exportación a GIS

Conservar juntos CSV y manifiesto. Verificar SHA-256 y registrar ejecución, versión de referencia/reglas y revisiones. Importar UBIGEO e identificadores como texto; interpretar coordenadas vacías como ausencia de geometría. Las columnas geográficas usan EPSG:4326 y orden explícito latitud/longitud; GeoJSON usa longitud/latitud.

El modo seguro para hojas de cálculo puede prefijar apóstrofo a celdas que parecen fórmulas. No removerlo automáticamente al abrir en Excel. Acordar con el consumidor GIS si utilizar ese perfil o una exportación no destinada a hojas de cálculo.
