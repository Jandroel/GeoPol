# Alcance, límites y decisiones abiertas

## Alcance implementado

El flujo cubre recepción, perfil y mapeo, ingesta, separación fila/unidad, normalización, resolución conservadora, revisión, trazabilidad y exportación. API, worker y frontend tienen procesos separados y comparten persistencia. Las funciones se prueban con casos sintéticos.

## Diferencias conscientes respecto al diseño objetivo

| Diseño objetivo | MVP entregado | Paso necesario para escalar |
| --- | --- | --- |
| Cola/broker con outbox | Cola durable en la misma base SQL | Medir concurrencia y throughput; broker si se justifica |
| Matching masivo sobre PostGIS | Catálogo acotado cargado por el worker; operaciones Shapely | Índices espaciales, carga incremental y consultas PostGIS |
| Objetos institucionales S3/NAS | Filesystem privado en volumen persistente | Integrar almacenamiento, políticas y respaldo aprobados |
| OIDC y permisos territoriales | Usuarios locales con roles en toda la instancia | SSO y autorización por ámbito |
| Canal SSE/eventos | Consulta periódica del estado | Ajustar frecuencia o incorporar SSE según carga |
| Cartografía institucional | Importación versionada y constructor local OSM/MINAM | Validar vigencia, cobertura y cartografía censal institucional |
| Reproyección geográfica | EPSG:4326 explícito | Transformaciones controladas y pruebas por CRS |
| Monitorización institucional | Salud API/base y estado persistido del trabajo | Métricas, alertas, trazas y retención |
| Evolución de esquema | Migraciones v1/v2 incrementales con backfill, idempotencia y rollback SQLite comprobados | Ejecutar la prueba equivalente sobre PostgreSQL y mantener migraciones por versión |

## Límites del motor

- No atribuye una probabilidad de acierto a una similitud textual. La evidencia se expresa de forma categórica y conserva el motivo.
- Los centroides heredados no se aceptan como coordenadas originales del hecho.
- Un punto original sin CRS confirmado o corroboración territorial queda para revisión. La versión 2026.3 admite similitud fuerte con componentes independientes y margen entre candidatos; su umbral es una regla determinista, no una tasa de acierto calibrada. La ambigüedad no resuelta exige revisión.
- Puertas, cuadras, cruces, sitios y núcleos dependen de la cobertura real del catálogo. La inexistencia de catálogo no se reporta como búsqueda exitosa sin coincidencias.
- Las reglas de extracción son un baseline para español y direcciones peruanas; no garantizan interpretar todos los textos, manzanas/lotes ni referencias relativas.
- El constructor opcional descarga OSM Perú y límites referenciales MINAM, con manifiestos y selección posterior local. No usa geocodificadores públicos ni envía direcciones de origen. No incorpora automáticamente la cartografía censal INEI/PNP ni atribuye una fecha censal a capas sin metadatos. Las geometrías sintéticas siguen limitadas a pruebas.
- No hay integración en línea con SIDPOL ni escritura directa en el GIS. El contrato de exportación debe validarse con su consumidor real.

## Capacidad y operación

La carga de origen admite hasta 5 GiB, mediante bloques de hasta 8 MiB. Cada catálogo CSV/GeoJSON admite hasta 24 MiB y 100 000 entidades. El lector de origen limita a 512 columnas y, para CSV, a 1 MiB por campo y 8 MiB por registro lógico. Para XLSX valida hasta 512 MiB totales descomprimidos, 64 MiB de cadenas compartidas y 4096 componentes ZIP. Libros que exceden estos controles se rechazan aunque su tamaño comprimido sea menor que el límite de carga.

El límite configurado de carga es un control de aceptación; no constituye un benchmark. La memoria del proceso depende del parser, estructura interna de XLSX y tamaño del catálogo. Se deben ejecutar pruebas con archivos representativos, medir disco/RAM/tiempo y ajustar límites antes del piloto institucional. El procesamiento nacional y archivos grandes no se declaran certificados.

La [prueba sintética documentada](validation-load.md) sí verificó un CSV de 1 248 312 057 bytes y 400 100 filas hasta su exportación, con recuperación del mismo lote y etapas en HDD/SSD. Ese resultado no se extiende a XLSX de igual tamaño, catálogos nacionales, matching complejo o concurrencia de producción.

SQLite está destinado al desarrollo con un solo worker. Para varios procesos concurrentes utilizar PostgreSQL y verificar la recuperación de reservas y la consistencia de resultados en el despliegue objetivo. El flujo local documentado usa PostgreSQL y PostGIS, con conexión en `backend/.env`, backend mediante `python -m geopol.dev` y frontend mediante `npm run dev`. El backend aplica migraciones al arrancar, pero no crea el servidor PostgreSQL ni importa bases de instalaciones anteriores. Consultar [la evidencia de validación](validation.md) para conocer el alcance de las pruebas.

## Validaciones institucionales pendientes

1. Semántica oficial de columnas, FLAGS y cardinalidad denuncia–ubicación.
2. Versiones, cobertura, licencia y control de calidad de las referencias INEI/PNP.
3. Criterios de aceptación, precisión, tolerancias y política de revisión.
4. Corpus etiquetado y métricas de calidad por tipo de ubicación y territorio.
5. Retención, acceso por ámbito, continuidad y restauración con datos autorizados.
6. Compatibilidad GIS: identificadores como texto, nulos, codificación, fórmulas escapadas y CRS.

Estas decisiones no se completan inventando cartografía, confianza estadística o tasas de recuperación.

## Precisión y reutilización

Los resultados de área/tramo son automáticos solo en la precisión declarada; no equivalen a puertas o coordenadas exactas del hecho. La cobertura automática debe medirse separada de la exactitud geográfica mediante una muestra validada independiente. Las confirmaciones humanas se reutilizan únicamente con opt-in explícito, firma de dirección/territorio, procedencia y revisión de origen, y se pueden revocar. No constituyen un modelo de aprendizaje entrenado ni garantizan cobertura futura.
