# Exportaciones Excel y CSV

En **Procesamientos → abrir procesamiento → Exportaciones**, seleccionar el perfil y **Excel (.xlsx)**, pulsar **Preparar exportación** y esperar **Descargar Excel**. Excel es la opción inicial de la interfaz. Una descarga antigua conserva su formato: para obtener el nuevo libro es necesario preparar otra exportación.

El libro utiliza azul y celeste INEI, encabezados en español, filtros, filas alternadas, anchos de columna ajustados y encabezados e identificadores inmovilizados. Dirección, resolución y precisión aparecen antes de los detalles técnicos. Las columnas finales de ID interno y geometría quedan agrupadas; se pueden desplegar en Excel. Los estados mantienen sus códigos originales, además de su color, para conservar la trazabilidad.

## Perfiles

| Perfil | Hojas | Cardinalidad |
| --- | --- | --- |
| Ubicaciones | Resultados | Una fila por unidad de ubicación, incluidos casos pendientes y sin resultado. |
| Filas originales y resultados | Resultados y Datos originales | Una fila por registro de origen en cada hoja; el ordinal permite relacionarlas. Una ubicación puede repetirse. |

El perfil ampliado requiere rol administrador u operador. Las columnas del archivo de origen se conservan en su orden y con sus valores, en una hoja separada. El perfil de ubicaciones no añade esas columnas originales restringidas.

UBIGEO y los identificadores de resultado se escriben como texto para conservar ceros iniciales. Los enteros de origen con más de 15 dígitos y los decimales originales que perderían precisión en Excel también se conservan como texto. Las coordenadas son números con ocho decimales de presentación; un valor ausente permanece vacío. Las áreas y los tramos conservan su geometría y no reciben una coordenada central inventada. Los textos que comienzan por símbolos de fórmula se guardan literalmente.

Si un texto supera la capacidad de una celda, se conserva completo en la hoja **Textos extensos**, dividido en partes numeradas. La celda inicial indica su clave; para reconstruirlo se concatenan sus partes en orden, sin separadores. Si el volumen excede la capacidad de filas o columnas de Excel, o contiene caracteres incompatibles con ese formato, la exportación falla con una indicación de utilizar CSV.

## Trazabilidad y compatibilidad

Cada exportación fija una instantánea de los resultados al solicitarse. Revisiones posteriores no cambian un archivo ya solicitado. El manifiesto conserva reglas, referencia, cantidad de registros y checksum; para XLSX añade `format: xlsx`, `workbook_schema_version: 1` y la descripción de las hojas y columnas. La presentación no modifica decisiones geográficas ni datos importados.

CSV sigue disponible para herramientas GIS y conserva sus nombres y orden de columnas. La API acepta `format: "xlsx"` o `format: "csv"` en `POST /api/runs/{id}/exports`; omitirlo conserva CSV para clientes existentes. Las exportaciones históricas sin formato explícito siguen siendo CSV. No se requiere una migración de base de datos para esta mejora.

## Validación del 23 de septiembre de 2026

- Suite general del backend: 475 pruebas aprobadas y una prueba PostgreSQL omitida por falta de una base de pruebas dedicada. Tras los últimos ajustes de fidelidad de originales, las 30 pruebas de exportación Excel también pasaron.
- Frontend: 40 pruebas aprobadas y compilación TypeScript/Vite correcta. Los cuatro recorridos E2E con base aislada pasaron, incluida descarga XLSX predeterminada, CSV explícito, manifiesto y vista móvil.
- Inspección visual de libros sintéticos con estados, ceros iniciales, direcciones extensas y ambas hojas. Se verificó además la apertura y representación con Microsoft Excel en modo de solo lectura; el importador de vistas previas de Artifact Tool no reflejó todos los formatos de las celdas de texto y combinadas.
- Exportación local del procesamiento disponible: 1.351 filas, 18 columnas y 24.318 celdas cotejadas con su instantánea. Se comprobaron MIME, SHA-256, filtros, tipos y valores vacíos. Los hashes de las tablas de origen/resultados y de los CSV anteriores permanecieron iguales. Los datos y archivos generados se mantienen fuera del repositorio.

La prueba previa de carga masiva de CSV no constituye una medición de rendimiento XLSX. Esta versión conserva escritura incremental y bloqueo de publicación por lease; el tiempo de compresión final de libros excepcionalmente grandes requiere una evaluación de carga propia.
