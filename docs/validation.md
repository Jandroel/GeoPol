# Evidencia de validación local

Fechas: 18 y 19 de septiembre de 2026. Entorno de estas comprobaciones: Windows, Python 3.11, base SQLite y archivos temporales con datos sintéticos. Los resultados siguientes corresponden a las pruebas concretas indicadas; no son un benchmark de volumen nacional.

## Pruebas funcionales y muestra suministrada

La suite completa del backend aprobó 83 pruebas y omitió únicamente la integración PostgreSQL/PostGIS, por falta de ese servicio. Después se aprobó una prueba adicional de rechazo de entidades XML en XLSX y se repitieron las 12 pruebas del lector con `defusedxml` instalado. Ruff y la comprobación de dependencias no encontraron errores. Las dos advertencias de deprecación proceden de las dependencias del cliente HTTP de pruebas.

El flujo privado con `MUESTRA.xlsx` se repitió el 19 de septiembre: **40 filas conservadas, 16 unidades procesadas, cero incidencias de lectura y exportaciones de 40/16 registros**. Sin cartografía cargada, nueve unidades quedaron como `NO_EVALUABLE_REFERENCIA` y siete como `REVISION_REQUERIDA`; todas conservaron coordenadas canónicas nulas. El archivo institucional y sus filas no forman parte del repositorio.

La interfaz aprobó cinco pruebas de integración y el flujo completo en Chromium: autenticación, catálogo, carga, finalización, consulta después de recargar, candidatos visibles en el mapa, asignación, decisión y descargas CSV/manifiesto. Se verificó una pantalla móvil de 400 × 900 y navegación por teclado. No se observaron errores de consola ni peticiones a servicios externos. Véase [evidencia del frontend](../frontend/QA.md). GitHub Actions está configurado; no se afirma que haya ejecutado estos jobs remotos.

## Recuperación y concurrencia de trabajos

Tres pruebas de integración adicionales pasaron:

| Prueba | Resultado observado |
| --- | --- |
| Reserva RUNNING vencida | La reserva vigente no se reclama. Al vencer, el mismo trabajo obtiene otro token, termina con dos intentos y conserva tres filas y dos unidades sin duplicar el trabajo. |
| Protección frente al worker anterior | El token anterior no puede insertar filas después de la reasignación. Su confirmación tardía tampoco completa la reserva del nuevo propietario. |
| Cancelación y reintento | La cancelación conserva el checkpoint de dos filas y una unidad. Un único reintento termina con tres filas, dos unidades y dos revisiones automáticas. Un segundo reintento de un trabajo ya en cola devuelve conflicto. |

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q -k 'reclaims_expired or old_worker or cancellation_and_retry'
```

Estas pruebas fuerzan vencimiento y reasignación en SQLite de forma determinística. No equivalen a una prueba de carga ni de concurrencia con varios workers PostgreSQL. La restauración SQLite de base y objetos también se comprueba con la prueba descrita en la [guía de operación](runbook.md).

## Lectura GIS real del producto CSV

Se exportaron dos ubicaciones mediante la API y el worker, una con punto aprobado manualmente y otra sin resolver. El archivo descargado se abrió con **Pyogrio 0.13.0, GDAL 3.12.4 y GeoPandas 1.1.4**. La prueba pasó y verificó:

- Dos registros conservados.
- Un punto en orden GIS X/Y: `POINT (-77.03 -12.04)`.
- Una geometría nula para el caso sin coordenadas; no se convirtió en `(0, 0)`.
- Identificadores `000001` y `000002`, y UBIGEO `010101`, conservados como texto.
- CRS inicial sin declarar en el CSV; asignación explícita de `EPSG:4326` según el contrato del producto.

La lectura utilizó `X_POSSIBLE_NAMES=GEOPOL_longitude`, `Y_POSSIBLE_NAMES=GEOPOL_latitude`, `KEEP_GEOM_COLUMNS=YES`, `EMPTY_STRING_AS_NULL=YES` y `AUTODETECT_TYPE=NO`. Las opciones y el orden de ejes corresponden al [lector CSV de GDAL](https://gdal.org/en/stable/drivers/vector/csv.html).

Para repetir la comprobación, instalar las herramientas únicamente en el entorno de QA y ejecutar el test:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -c backend/requirements.lock pyogrio==0.13.0 geopandas==1.1.4
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q -s -k gdal_reads_actual_export_point_and_null_geometry
```

Pyogrio y GeoPandas no son dependencias de producción. La prueba se omite si no están instaladas. La versión de GDAL depende del wheel de Pyogrio y de la plataforma; el test imprime la versión realmente utilizada. No se probó la interfaz de QGIS ni el GIS institucional.

## Infraestructura

`docker compose config --quiet` valida la configuración declarativa. Los scripts PowerShell y Bash pasan su análisis sintáctico. El intento de iniciar Docker Desktop confirmó que WSL no está instalado; se cerró el proceso de verificación sin cambiar la configuración del equipo. No se ejecutaron contenedores ni una restauración PostgreSQL. CI incluye un servicio PostGIS para comprobar migración idempotente, geometría derivada e índices espaciales.

La capacidad medida se documenta separadamente en [prueba de carga](validation-load.md).
