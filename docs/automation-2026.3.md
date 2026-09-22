# Automatización por evidencia y precisión — 2026.3

Esta versión amplía la resolución automática con referencias reales y conserva la precisión obtenida. El porcentaje de resoluciones depende de la cobertura del catálogo seleccionado y de la calidad de las direcciones; no hay una tasa de acierto garantizada.

## Flujo

1. Construir o importar una referencia versionada. El [constructor público](reference-sources.md) descarga cartografía nacional, verifica huellas y selecciona los nombres localmente. No transmite expedientes o direcciones a geocodificadores externos.
2. Crear una ejecución o reprocesar una completada, seleccionando el catálogo. Confirmar EPSG:4326 únicamente si se conoce el sistema de las coordenadas originales. Una dirección de texto puede resolverse usando el CRS de la referencia sin confirmar el de los ejes originales.
3. Leer el resumen separado entre puntos y áreas/tramos. Una vía identificada no implica haber encontrado la puerta solicitada. En ese caso el resultado conserva la línea y declara VIA; la exportación deja latitud/longitud vacías y guarda la geometría en GEOPOL_geometry.
4. Revisar las excepciones. Cuando una dirección concreta queda confirmada, el revisor puede marcar su reutilización en futuros lotes. La firma incluye texto completo, territorio y componentes; denuncias diferentes pueden compartir la misma dirección validada.
5. Si esa confirmación deja de ser válida, desactivar su reutilización desde la ficha. Reabrir o modificar su decisión también retira la referencia originada allí. Los resultados históricos y sus exportaciones no se reescriben.

## Decisión geográfica

Los nombres se recuperan por distrito y se ordenan antes de limitar la búsqueda. Se conservan alias explícitos y candidatos competidores. Los números de puerta, nombres numéricos, tipos de vía, manzana y contexto se comparan sin inventar equivalencias. Una búsqueda truncada se informa y no concede aceptación automática.

La similitud fuerte requiere controles adicionales y margen frente a otra opción; el puntaje ordena texto y no representa probabilidad. Las geometrías se contrastan con el límite territorial y su procedencia. Los tramos discontinuos o ramificados no se presentan como una calle inequívoca. Los límites MINAM son referenciales, y su fecha de adquisición no acredita vigencia legal.

No se generan centroides para completar una dirección. La manzana censal no se equipara automáticamente con una letra o código de manzana de una urbanización. Las áreas censales requieren identificadores y contexto compatibles. La infraestructura pública INEI consultada no acredita por sí sola una versión del Censo 2025.

## Actualización local

Detener únicamente los procesos registrados de GeoPol y respaldar la base SQLite mediante su API de backup, junto con los objetos privados. Ejecutar `python -m geopol.cli init-db` con el entorno de la instalación; el comando aplica migraciones pendientes, incluida v3. Luego reiniciar API, worker y frontend compilado.

La migración añade la geometría y la tabla de direcciones confirmadas. Conserva filas originales, estados de revisión, resultados y revisiones previas. No aprende automáticamente de decisiones históricas. Los nuevos lotes usan reglas 2026.3; los antiguos conservan su versión hasta crear un reproceso nuevo. Los trabajos de reglas anteriores deben finalizar antes de actualizar el worker.

Las nuevas exportaciones usan esquema 3. Las exportaciones pendientes de esquema 1 o 2 conservan su contrato original. PostgreSQL/PostGIS requiere validación en el despliegue objetivo; una prueba SQLite no sustituye esa comprobación.
