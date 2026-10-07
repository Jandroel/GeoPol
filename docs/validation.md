# Evidencia de validación local

Fechas: 18 a 22 de septiembre de 2026. Entorno de estas comprobaciones: Windows, Python 3.11, base SQLite y archivos temporales con datos sintéticos. Los resultados siguientes corresponden a las pruebas concretas indicadas; no son un benchmark de volumen nacional.

## Actualización del 22 de septiembre: diccionario y preparación de puertas

La suite completa del backend aprobó **340 pruebas en 99,13 segundos**, con una omisión de PostgreSQL/PostGIS y dos avisos de deprecación de dependencias. Ruff y su comprobación de formato pasan. La compilación TypeScript/Vite del frontend pasa, con el aviso conocido de tamaño del paquete de MapLibre. Esta actualización no modifica la interfaz ni el motor operativo y no repite los E2E de la sección siguiente.

Las **73 pruebas nuevas**, con datos sintéticos, comprueban el mapeo del diccionario, conservación del original, número y letra de puerta, códigos y valores ausentes, ejes y rangos, separación de `MANZANA` y `P21`, tratamiento de campos alternativos, rechazo de tipos de vía no soportados, conservación de conflictos y exclusión de puntos sin metadatos confirmados. La prueba de integración genera un catálogo sintético, lo lee con el importador vigente y obtiene una coincidencia de puerta con procedencia y geometría compatibles con el motor. No se asigna un CRS a partir de los rangos numéricos.

La ejecución privada sobre el Excel de puertas conservó las **3.000 filas**. Una lectura independiente verificó valores y tipos del original, ordinales completos y SHA-256 de entrada, diccionario y preparación. Los 3.000 pares numéricos están dentro de rangos de latitud/longitud; 327 filas tienen vía y número con sufijo válido. Doce sufijos numéricos contradicen la descripción de letra y permanecen pendientes; se identifican 17 claves con coordenadas diferentes que afectan a 35 filas. Los conteos de incidencias se superponen. No se generó GeoJSON ni se importaron referencias: siguen pendientes CRS, fuente, versión y dominio de categorías. Esta preparación no cambia los resultados de geocodificación previos. La evidencia y los datos reales permanecen fuera de Git, en `.local/institutional-samples-20260922/`.

## Actualización del 22 de septiembre: reglas 2026.3 y geometrías

La suite completa aprobó **267 pruebas**, con una omisión de PostgreSQL/PostGIS por falta de una base de prueba configurada, y dos avisos de deprecación de dependencias. Ruff, formato y comprobación de dependencias pasan. La interfaz aprobó **20 pruebas**, compilación TypeScript/Vite y formato. Los **tres recorridos E2E de Chromium** aprobaron tanto con el servidor de desarrollo como con el build de producción, contra API, worker y SQLite sintéticos temporales. No se ejecutó CI remoto ni PostgreSQL/PostGIS.

La cobertura nueva comprueba geometrías de punto, línea y polígono; límites territoriales y procedencia; candidatos competidores y alias; diferencias entre manzana y cuadra; búsqueda territorial que encuentra elementos después del antiguo límite de 500; preservación de geometrías en exportaciones; y migración aditiva v2 → v3. La memoria exige confirmación explícita, conserva su revisión y procedencia, reconoce conflictos y puede revocarse. Las pruebas incluyen direcciones repetidas en denuncias diferentes y compatibilidad espacial entre evidencias de distinta precisión.

El navegador verificó píxeles WebGL de líneas y polígonos reales, ausencia de marcadores y ejes ficticios en áreas, atribución OpenStreetMap, vista móvil, reutilización explícita y revocación sin reescribir resultados anteriores. Se corrigió la carga del worker ESM de MapLibre para que Vite lo incluya localmente. La evidencia de interfaz y sus límites se detallan en [QA del frontend](../frontend/QA.md).

El catálogo público construido localmente pasó controles independientes de SHA-256, origen, versión, selector, geometrías e importación. Los selectores privados se aplicaron después de descargar fuentes nacionales. La instalación local recibió la migración v3 con respaldo SQLite y se reprocesó la muestra autorizada mediante API y worker. El original y todas las filas persistidas se compararon exactamente; las dos exportaciones se verificaron contra sus manifiestos y geometrías. El informe de cobertura y resultados de la muestra, los archivos y las exportaciones permanecen en `.local/`, fuera de Git.

La aceptación automática mide la cobertura de las reglas sobre el catálogo disponible; **no acredita exactitud contra una verdad de terreno independiente**. La referencia pública sigue siendo parcial, el CRS de los ejes institucionales sigue sin confirmarse y no se ha atribuido ninguna capa utilizada al Censo 2025. Los benchmarks históricos siguientes corresponden a las versiones y entornos indicados; no se repitió el benchmark de 1,2 GB para esta actualización.

## Actualización del 21 de septiembre: reglas 2026.2 y revisión

La suite completa de esa versión aprobó **178 pruebas**, con una omisión correspondiente a PostgreSQL/PostGIS y dos avisos de deprecación del cliente de pruebas. Ruff y formato pasan. La interfaz aprobó **11 pruebas**, compilación TypeScript/Vite y formato. Los **dos recorridos E2E de Chromium** aprobaron en 47,1 segundos contra API, worker, base SQLite y almacenamiento sintéticos temporales; los procesos se cerraron al terminar. Cubren importación/exportación y el nuevo flujo: falta de referencia → reproceso con catálogo → historial → guardar y siguiente → cierre, reapertura y liberación → navegación móvil. No se ejecutó CI remoto ni PostgreSQL.

La instalación local recibió la migración v2 después de detener sus procesos y respaldar base y objetos. Las huellas de las 40 filas de origen, 16 revisiones existentes, carga y usuario coinciden exactamente antes y después de migrar. Las comprobaciones SQLite de integridad y claves foráneas pasan. API y worker volvieron a responder correctamente. La prueba de acceso y consulta en el navegador desplegado no encontró errores de consola ni desbordamiento horizontal a 400 px.

Se reprocesó la misma carga de `MUESTRA.xlsx`, sin introducir catálogos sintéticos en la instalación del usuario:

| Comprobación | Resultado |
| --- | --- |
| Origen | 40 filas idénticas por ordinal; SHA-256 del archivo coincide con la carga |
| Ubicaciones | 16 unidades procesadas, cero incidencias |
| Resolución geográfica | 9 `NO_EVALUABLE_REFERENCIA`, 7 `REVISION_REQUERIDA`, 0 puntos aceptados |
| Trabajo pendiente | 11 necesitan referencia, 5 necesitan datos, 0 con candidatos listos para decidir, 0 errores técnicos |
| Advertencia por cuadra `NULL` | Eliminada en las 16 unidades; original conservado |
| Historial | Ejecución anterior y sus revisiones conservadas, enlazadas al sucesor |
| Dashboard | 2 ejecuciones históricas; 40 filas y 16 unidades vigentes, sin duplicar el lote |

La corrección evita falsos avisos y tareas repetidas; **no aumentó la cantidad de puntos aceptados en esta muestra sin catálogo**. Los once bloqueos de referencia incluyen nueve casos no evaluables y dos candidatos de coordenadas que necesitan corroboración territorial. Separar la bandeja no equivale a resolver esos registros. La prueba de carga anterior sigue siendo evidencia de la versión evaluada entonces; no se repitió el benchmark de 1,2 GB para esta actualización.

## Pruebas funcionales y muestra suministrada

La suite completa final del backend aprobó **86 pruebas** en 48,28 segundos y omitió únicamente la integración PostgreSQL/PostGIS, por falta de ese servicio. Incluye rechazo de entidades XML en XLSX, conservación de candidatos ambiguos al normalizar alias de vías y rechazo de CRS de catálogo incompatibles. Ruff, su comprobación de formato y la comprobación de dependencias no encontraron errores. Las dos advertencias de deprecación proceden de las dependencias del cliente HTTP de pruebas.

El flujo privado con `MUESTRA.xlsx` se repitió el 19 de septiembre: **40 filas conservadas, 16 unidades procesadas, cero incidencias de lectura y exportaciones de 40/16 registros**. Sin cartografía cargada, nueve unidades quedaron como `NO_EVALUABLE_REFERENCIA` y siete como `REVISION_REQUERIDA`; todas conservaron coordenadas canónicas nulas. El archivo institucional y sus filas no forman parte del repositorio.

La interfaz aprobó cinco pruebas de integración y el flujo completo en Chromium: autenticación, catálogo, carga, finalización, consulta después de recargar, candidatos visibles en el mapa, asignación, decisión y descargas CSV/manifiesto. Se verificó una pantalla móvil de 400 × 900 y navegación por teclado. No se observaron errores de consola ni peticiones a servicios externos. Véase [evidencia del frontend](../frontend/QA.md). GitHub Actions está configurado; no se afirma que haya ejecutado estos jobs remotos.

## Recuperación y concurrencia de trabajos

Tres pruebas de integración adicionales pasaron:

| Prueba | Resultado observado |
| --- | --- |
| Reserva RUNNING vencida | La reserva vigente no se reclama. Al vencer, el mismo trabajo obtiene otro token, termina con dos intentos y conserva tres filas y dos unidades sin duplicar el trabajo. |
| Protección frente al worker anterior | El token anterior no puede insertar filas después de la reasignación. Su confirmación tardía tampoco completa la reserva del nuevo propietario. |
| Cancelación y reintento | La cancelación conserva el checkpoint de dos filas y una unidad. Un único reintento termina con tres filas, dos unidades y dos revisiones automáticas. Un segundo reintento de un trabajo ya en cola devuelve conflicto. |

Para repetir estos casos, ejecuta desde `backend`, con su entorno virtual y
dependencias de desarrollo activados:

```bash
python -m pytest tests/test_api.py -q -k 'reclaims_expired or old_worker or cancellation_and_retry'
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

Para repetir la comprobación, instala las herramientas únicamente en el entorno de QA. Desde `backend`, con su entorno virtual y dependencias de desarrollo activados, ejecuta:

```bash
python -m pip install -c requirements.lock pyogrio==0.13.0 geopandas==1.1.4
python -m pytest tests/test_api.py -q -s -k gdal_reads_actual_export_point_and_null_geometry
```

Pyogrio y GeoPandas no son dependencias de producción. La prueba se omite si no están instaladas. La versión de GDAL depende del wheel de Pyogrio y de la plataforma; el test imprime la versión realmente utilizada. No se probó la interfaz de QGIS ni el GIS institucional.

## Infraestructura

El flujo local vigente utiliza dependencias instaladas por componente, una base PostgreSQL/PostGIS creada previamente y `backend/.env`. Los comandos de arranque son `python -m geopol.dev` desde `backend` y `npm run dev` desde `frontend`; las tablas se crean o actualizan al iniciar el backend.

El job `manual-postgres` está destinado a comprobar este mismo recorrido en una instancia sintética de Ubuntu: preparar PostgreSQL, configurar `.env`, arrancar ambas partes, iniciar sesión y reiniciar conservando datos. La integración PostgreSQL comprueba además migraciones e índices PostGIS en una base separada. La configuración de una prueba en CI no acredita por sí sola que haya terminado correctamente; su resultado debe consultarse en la ejecución correspondiente. Una prueba de arranque tampoco sustituye una restauración PostgreSQL ensayada en el entorno de destino.

## Capacidad medida

Se completó una carga sintética CSV de **1 248 312 057 bytes y 400 100 filas**: 400 100 unidades procesadas, cero incidencias y 400 100 filas verificadas en la exportación descargada. Se comprobaron SHA-256, ordinales e identificadores. La prueba incluyó recuperación del mismo lote desde un checkpoint y el traslado de una copia consistente de la base de HDD a SSD; no constituye una ejecución continua ni una medición de exactitud geográfica real. Los tiempos, memoria, entorno y límites se documentan en la [prueba de carga](validation-load.md).
