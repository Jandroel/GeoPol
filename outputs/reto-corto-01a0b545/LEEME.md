# Prueba corta para GeoPol

1. Cargar `RETO_CORTO_GEOPOL.xlsx`, hoja **Casos**.
2. Seleccionar el catálogo **DEMO SINTETICA - Reto corto de 12 casos** y CRS **EPSG:4326**. Ya está importado en la instalación local. Para otra instalación, importar primero `catalogo_reto_sintetico.geojson`.
3. Procesar y comparar con la hoja **GUIA** del Excel.

Resultado comprobado: **8 de 12 casos aceptados automáticamente y 4 en revisión**, sin decisiones manuales. La carga y exportación conservaron los 12 registros. Los cuatro controles pendientes contienen ambigüedad, similitud aproximada, un punto fuera del límite o precisión de cuadra.

[Abrir el procesamiento probado](http://127.0.0.1:5174/runs/b9bd6611-018b-4bb4-8bcc-e24f7baeff96).

Todos los datos y las geometrías son ficticios. El catálogo solo corresponde a este reto; no es cartografía oficial ni una referencia para las denuncias reales.
