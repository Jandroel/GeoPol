# Ejemplos sintéticos

Todos los nombres, identificadores, direcciones, puntos y polígonos de estos archivos son **ficticios**. El código `150101` solo permite demostrar una igualdad territorial; el polígono incluido no representa su límite oficial. No usar estos archivos en análisis policial, operacional o estadístico.

`denuncias_sinteticas.csv` tiene 12 filas y 11 identificadores de denuncia. La primera denuncia aparece en dos filas con igual ubicación y distinta categoría de ocurrencia. Esto permite verificar la conservación de filas sin duplicar la unidad de ubicación.

`referencias_sinteticas.geojson` contiene seis objetos: un polígono de prueba, una puerta, una cuadra representada por punto, un sitio y dos puertas deliberadamente ambiguas.

| Caso | Escenario a verificar |
| --- | --- |
| DEMO-001 | Puerta exacta en territorio explícito; dos filas para la misma ubicación |
| DEMO-002 | Coordenada original corroborada contra el polígono sintético |
| DEMO-003 | Centroide forzado heredado que no debe aceptarse como coordenada original |
| DEMO-004 | Cuadra aproximada que requiere revisión |
| DEMO-005 | Error tipográfico; similitud no equivale a aceptación ni probabilidad |
| DEMO-006 | Coordenadas extraídas de texto |
| DEMO-007 | Sitio de interés sintético y política conservadora de revisión |
| DEMO-008 | UBIGEO ausente; no resolver usando territorio supuesto |
| DEMO-009 | Ubicación vacía; conservar el registro y su estado |
| DEMO-010 | Dos puertas con los mismos componentes y puntos distintos; ambigüedad |
| DEMO-011 | Territorio sin cobertura en la referencia seleccionada |

Los resultados exactos dependen de la versión de reglas. La finalidad del ejemplo es inspeccionar evidencias y estados, no medir calidad ni cobertura real. Al ejecutar sin referencia debe distinguirse la ausencia de catálogo de una búsqueda sin coincidencias.

Para importar referencias propias, entregar un `FeatureCollection` GeoJSON en EPSG:4326, con `id` único y propiedades `kind`, `ubigeo`, `source`, `version` y componentes aplicables (`street_type`, `street_name`, `door_number`, `block_number`, `cross_street`, `name`). Los puntos usan orden **longitud, latitud**. Los tipos posibles se describen en el contrato de implementación; las fronteras usan `Polygon` o `MultiPolygon`. No publicar catálogos sin verificar su fuente, CRS y cobertura.
