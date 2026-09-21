# Revisión por excepción y reprocesamiento

La automatización resuelve los casos con evidencia suficiente. La bandeja distingue qué acción puede desbloquear cada caso; separar una tarea no mejora por sí solo su resolución geográfica. Todos los registros siguen disponibles en el lote y en la exportación.

## Reglas 2026.2

- Los marcadores explícitos de ausencia, como `NULL`, `N/A` y `SIN DATO`, se interpretan como nulos solo en campos estructurados numéricos y UBIGEO. Se conserva la celda original y se registra la transformación. No se borran nombres legítimos ni se interpreta `S/N` como número de puerta.
- Varios candidatos pueden aceptarse automáticamente únicamente si todos cumplen individualmente las condiciones de aceptación y coinciden exactamente en coordenadas, método, precisión y producto. Se conservan todos sus candidatos y procedencias. No hay redondeo, distancia de tolerancia ni aprobación de coincidencias aproximadas.
- Una coordenada original PNP, con CRS confirmado y dentro del límite territorial de referencia, puede aceptarse aunque el texto contenga manzana/lote. Se conserva esa advertencia. Otros conflictos, puntos en el borde o fuera del territorio, coordenadas textuales y centroides heredados mantienen sus controles.

## Bandeja

| Grupo | Tratamiento |
| --- | --- |
| Listas para revisar (`actionable`) | Hay candidatos para contrastar. La interfaz abre este grupo por defecto. |
| Necesitan referencia (`needs_reference`) | Falta un catálogo o un límite territorial válido. Importar una referencia validada y reprocesar evita revisar individualmente la misma carencia. |
| Necesitan datos (`needs_data`) | No hay candidatos. Requieren información adicional del origen o una decisión documentada. |
| Atención técnica (`technical`) | El procesamiento informó un error técnico. |
| Finalizados (`CLOSED`) | Incluye aceptaciones automáticas y decisiones manuales, incluso «sin resolver». |

Los contadores muestran también los casos bloqueados aunque la tabla filtre solo los revisables. Los filtros por ejecución, grupo, etapa y búsqueda permanecen en la URL y se conservan al abrir una ficha y regresar. Las ejecuciones anteriores se consultan con el filtro histórico; no se editan después de ser sustituidas. Las nuevas exportaciones añaden `GEOPOL_review_status` y `GEOPOL_review_bucket`, además de la resolución geográfica, para distinguir un caso sin resolver ya revisado de uno pendiente.

## Trabajo manual

1. Abrir el caso y revisar origen, normalización, motivos, candidatos, mapa e historial.
2. Tomar la reserva, válida durante diez minutos. Solo su propietario puede liberar esa asignación.
3. Registrar una decisión y su motivo. Un punto manual exige evidencia; aceptar candidato exige un candidato existente.
4. Guardar, o usar **Guardar y siguiente**. El servidor busca el siguiente caso abierto del mismo filtro y omite reservas vigentes de otros revisores. No asigna el siguiente automáticamente.
5. La decisión sale de los pendientes. «Sin resolver» conserva la resolución geográfica y las coordenadas vacías, pero finaliza esa tarea. Solo una reapertura explícita vuelve a incluirla; el historial manual permanece.

Al cambiar de caso se reinician candidato, coordenadas, evidencia y motivo. «Salir y liberar reserva» permite devolver un caso sin decidir. Si se abandona la sesión sin liberarlo, la reserva vence; las decisiones con revisión antigua o reserva expirada son rechazadas.

## Reprocesar con otra referencia

En la ficha del procesamiento se puede elegir el catálogo del nuevo intento, conservar el actual o procesar sin catálogo. Se reutiliza el archivo original inmutable y su mapeo, creando otra ejecución con las reglas disponibles. Las decisiones anteriores permanecen en su ejecución; no se trasladan automáticamente al nuevo resultado.

El lote anterior sigue vigente hasta que el nuevo termina como `COMPLETED` o `COMPLETED_WITH_ISSUES`. Una cancelación o fallo no lo sustituye. El historial enlaza padre y sucesor. La bandeja y las métricas de ubicaciones del dashboard cuentan únicamente ejecuciones terminadas vigentes; el contador de procesamientos conserva el historial completo. Las exportaciones anteriores siguen siendo instantáneas de su ejecución y revisión.

## Actualizar una instalación con datos

Detener API y worker de esa instalación, obtener una copia consistente de la base y conservar sus objetos, desplegar el código y ejecutar `python -m geopol.cli init-db` antes de reiniciar los servicios. La migración v2 añade campos e índices y clasifica los casos existentes en bloques; no reemplaza filas de origen ni revisiones. Reconoce la última acción manual por número de revisión para conservar las reaperturas. Se comprueban idempotencia y reversión de una migración interrumpida en SQLite. La comprobación equivalente de PostgreSQL requiere el servicio de prueba dedicado.

Los lotes antiguos conservan su versión de reglas. Un nuevo reproceso aplica 2026.2; la migración del esquema por sí sola no recalcula sus resultados geográficos. Los límites distritales permiten corroborar coordenadas existentes, pero no sustituyen un catálogo de vías, puertas o cruces para direcciones sin punto.

El manifiesto de las nuevas exportaciones identifica el formato CSV como `schema_version: 2`. Una exportación v1 ya solicitada conserva sus columnas originales al reanudarse. Las revisiones históricas anteriores a v2 no se modifican: sus campos de tarea pueden estar vacíos al exportarlas con el formato nuevo.
