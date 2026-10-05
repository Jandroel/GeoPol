# Operación y recuperación

Este manual corresponde a la instalación nativa descrita en la
[guía Bash](../INSTALACION_LOCAL.md). Todos los comandos parten de la raíz del
proyecto y se ejecutan en Bash. PostgreSQL debe estar funcionando como servicio.

## Arranque y salud

```bash
bash iniciar.sh
```

Mantén esa terminal abierta: administra la API, el worker y la web. Para detener
GeoPol, pulsa Ctrl+C o ejecuta `bash detener.sh` desde otra terminal.
PostgreSQL continúa funcionando y los datos se conservan.

Desde una segunda Bash, con los puertos predeterminados:

```bash
curl --fail http://127.0.0.1:8000/api/health
```

`GET /api/health` comprueba API y base de datos. No certifica que el worker esté
procesando: revisa también `GET /api/health/worker` con sesión autenticada, los
registros del arranque y los estados de las ejecuciones. Un archivo cargado no
comienza a procesarse hasta crear su ejecución. `COMPLETED` y
`COMPLETED_WITH_ISSUES` indican terminación técnica, no que todas las ubicaciones
hayan sido aprobadas.

API, worker y las herramientas `scripts/native_cli.py` utilizan la configuración
privada de `.local/native.json`. No ejecutes una CLI manual con el `.env` de una
instalación anterior esperando modificar esta misma base.

## Almacenamiento para lotes grandes

En esta instalación PostgreSQL administra sus propios archivos de base de
datos y GeoPol guarda originales y exportaciones en `data/storage-native`.
Planifica espacio para la base, originales, exportaciones y respaldos.
El traslado del directorio de datos de PostgreSQL debe realizarlo su
administrador; cambiar una ruta no traslada datos existentes.

La [prueba de carga](validation-load.md) documenta un ensayo anterior con SQLite
y almacenamiento HDD/SSD. Sus tiempos no son una medición de la instalación
PostgreSQL actual. Para conservar una instalación SQLite anterior, respalda
su base y almacenamiento del mismo corte y mantén un solo worker.

## Usuarios

La instalación crea `administrador` solo si no existe ninguna cuenta. Para
crear un operador adicional, ejecuta este bloque en Bash. La contraseña se
solicita de forma oculta y debe tener al menos 12 caracteres:

```bash
(
  set -eu
  geopol_python="backend/.venv/bin/python"
  if [ -x backend/.venv/Scripts/python.exe ]; then
    geopol_python="backend/.venv/Scripts/python.exe"
  fi
  IFS= read -r -s -p 'Contraseña del nuevo usuario: ' GEOPOL_BOOTSTRAP_PASSWORD
  printf '\n'
  export GEOPOL_BOOTSTRAP_PASSWORD
  "$geopol_python" scripts/native_cli.py create-user --username operador01 --role operator
  unset GEOPOL_BOOTSTRAP_PASSWORD
)
```

Cambia el nombre y el rol antes de ejecutar el bloque para crear otra cuenta.
Los roles disponibles son `admin`, `operator`, `reviewer` y `analyst`; consulta
la [matriz de permisos](security.md#matriz-funcional). El comando no reemplaza
contraseñas de usuarios existentes. Usa cuentas individuales para el trabajo
habitual.

## Trabajo detenido o fallido

1. Confirma la salud de la base y el espacio en disco. Revisa el error de la
   ejecución y los registros sin copiar datos sensibles a sistemas externos.
2. Si el worker terminó, detén la sesión con `bash detener.sh` y vuelve a
   ejecutar `bash iniciar.sh`. La cola y los checkpoints residen en la base;
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

## Respaldo consistente de PostgreSQL y archivos

Sigue el [procedimiento de respaldo nativo](instalacion-bash-detallada.md#crear-un-respaldo-de-base-y-archivos):
detiene GeoPol, exporta la base con `pg_dump` y copia `data/storage-native`.
La base y los archivos deben corresponder al mismo corte. Conserva aparte
una copia privada de `.local/native.json`, con acceso restringido.

Registra fecha, versión de la aplicación y checksums. Un respaldo operativo
debe tener una prueba de recuperación en una instancia separada. Para uso
institucional, acuerda la frecuencia de copias, la retención y los tiempos
máximos de recuperación.

## Evidencia de recuperación local

La prueba `test_sqlite_database_and_objects_restore_together` demuestra la
restauración de un escenario SQLite acotado con datos sintéticos. Incluye base,
original, exportación, checksums y un nuevo reproceso. Esa evidencia histórica
no acredita la restauración de PostgreSQL.

En SQLite, una copia consistente mediante `sqlite3.Connection.backup` incluye
los cambios del WAL. Copiar solo `geopol.db` mientras está activo puede omitir
cambios. La [evidencia de validación](validation.md) describe el alcance del
ensayo; la instalación nativa necesita su propia prueba de recuperación.

## Procedimiento de restauración en una instancia vacía

Este es un procedimiento para quien administra PostgreSQL. Ensáyalo en otra
instancia de PostgreSQL 16 con PostGIS compatible, sin información que deba
conservarse, y con una carpeta de proyecto separada.

1. Verifica el respaldo y conserva intacta la instalación original.
2. Prepara la instancia PostgreSQL de destino en otro puerto o equipo. Recrea
   el rol limitado de la aplicación con el mismo nombre que figura en la
   configuración privada respaldada y crea **una base vacía propiedad de ese rol**. Establece
   su secreto por un mecanismo interactivo protegido; no lo escribas en
   comandos ni archivos de código. El archivo de `pg_dump` no incluye los
   roles globales del servidor.
3. Usa `pg_restore` como administrador sobre esa base vacía. El respaldo
   conserva los propietarios de objetos; el rol del paso anterior debe
   existir. El siguiente ejemplo supone una instancia separada en el puerto
   **5433**, una base vacía llamada `geopol` y la ruta de respaldo indicada:

```bash
pg_restore -h 127.0.0.1 -p 5433 -U postgres -W -d geopol --exit-on-error "../geopol-respaldo/geopol.dump"
```

Sustituye la ruta por la real antes de ejecutar. Consulta las opciones en la
[documentación de pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).
No ejecutes el comando contra una base ya inicializada por el instalador:
debe estar vacía. Si la restauración falla, investiga el error antes de continuar.

4. Restaura `artifacts-backup.tgz` en la carpeta `data` del proyecto de destino,
   manteniendo la estructura `data/storage-native`.
5. Recupera allí la copia privada de `.local/native.json`. Quien administra
   la recuperación debe ajustar exclusivamente la conexión y las rutas al
   destino, conservar la identidad del rol y verificar sus permisos antes de
   arrancar. Esta operación avanzada no la realiza automáticamente
   `bash instalar.sh`.
6. Con el proyecto en la misma versión que el respaldo, prepara las
   dependencias con `bash instalar.sh` y arranca con
   `bash iniciar.sh --puertos 5174 8002`, en una terminal propia.

Verifica inicio de sesión, número de ejecuciones, descarga de un original
autorizado y una exportación, checksums, lectura del histórico y un nuevo
trabajo sintético. Registra el tiempo y el resultado de la prueba. Mantén la
instancia original hasta validar la recuperación.

## Actualizaciones

Respalda antes de actualizar. `bash instalar.sh` instala las dependencias,
compila la web y aplica las migraciones pendientes con la configuración nativa.
Ensaya cambios de esquema y recuperación en una copia cuando haya información
que conservar. El [procedimiento de actualización](instalacion-bash-detallada.md#actualizar-geopol)
incluye los comandos para Git y las indicaciones para ZIP.

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
