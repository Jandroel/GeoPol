# Reto corto de GeoPol

Doce casos completamente ficticios, con dificultades de normalización y cuatro controles que deben quedar pendientes. UBIGEO `999901`, distrito, vías, puntos y límite artificiales. El catálogo es exclusivo de esta demostración, sin uso operativo.

El Excel listo para importar y una copia del catálogo están en [outputs/reto-corto-01a0b545](../../outputs/reto-corto-01a0b545/). La primera hoja, `Casos`, contiene los 12 registros y encabezados reconocidos por GeoPol. La hoja `GUIA` explica la prueba y sus resultados esperados. Se conservan como texto los campos de origen, incluida la puerta `0042`.

## Uso

1. Importar `catalogo_reto_sintetico.geojson` con nombre **DEMO SINTETICA - Reto corto de 12 casos**, versión `reto-corto-2026.2-v1` y fuente `RETO SINTETICO - NO CARTOGRAFIA OFICIAL - NO USO OPERATIVO`.
2. Crear un procesamiento con `RETO_CORTO_GEOPOL.xlsx`, hoja `Casos`, seleccionar ese catálogo y confirmar `EPSG:4326`. Los encabezados se mapean automáticamente.
3. Esperar la finalización y comparar los resultados. No hace falta aprobar manualmente ningún caso para reproducir la prueba.

## Resultado verificado

El 21 de septiembre de 2026 se cargó el Excel mediante la API local, se procesó con el worker y las reglas 2026.2 y se descargó su exportación: **12 filas, 12 unidades, cero incidencias, 8 aceptaciones automáticas y 4 pendientes de revisión**. Cero decisiones manuales. Los estados, métodos, precisiones, coordenadas, candidatos y motivos coincidieron con las expectativas predeclaradas de `esperados.json`.

| Casos | Dificultad | Resultado |
| --- | --- | --- |
| 01–03 | Abreviaturas, tildes, espacios, calle numérica, puerta 0042 y cuadra NULL | Puerta aceptada automáticamente |
| 04 | Cruce con las vías en orden inverso | Cruce a nivel aceptado automáticamente |
| 05–06 | Coordenadas decimales y DMS dentro del texto | Coordenadas extraídas y aceptadas automáticamente |
| 07 | Manzana/lote con coordenada original corroborada | Coordenada original aceptada automáticamente |
| 08 | Dos referencias exactamente equivalentes | Aceptación automática, conservando ambos candidatos |
| 09 | Dos puntos distintos con igual dirección | Revisión por ambigüedad |
| 10 | Similitud ortográfica FOTONIKO/FOTONICO | Revisión de coincidencia aproximada |
| 11 | Coordenada fuera del límite territorial | Revisión de incompatibilidad territorial |
| 12 | Cuadra con un punto representativo | Revisión por precisión aproximada |

La exportación mantuvo los 12 casos: ocho pares de coordenadas aceptadas y cuatro pares vacíos. Su checksum coincidió con el manifiesto. El 8/12 es el resultado de este conjunto diseñado, no una estimación de precisión ni de cobertura sobre registros reales. No se modificó el motor para obtenerlo.

En el navegador se verificaron los 12 resultados, el filtro de ocho aceptados, el filtro de cuatro pendientes y la bandeja de cuatro casos revisables, sin errores de consola ni decisiones manuales.

`casos.json` conserva los datos de origen y la configuración de importación; `esperados.json` documenta las predicciones establecidas antes de validar la ejecución.
