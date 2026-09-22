# Integración de tablas institucionales de referencia

Este contrato recoge los esquemas de muestras proporcionadas por el usuario. El nombre de un archivo, sus campos y la fecha de creación del Excel no acreditan institución de origen, año censal ni vigencia cartográfica. Los archivos, perfiles y cruces con datos operativos se conservan exclusivamente en `.local/`.

## Situación de la aplicación

La importación web acepta catálogos CSV o GeoJSON. La herramienta local `python -m geopol.reference_doors` prepara el Excel de puertas conforme al diccionario suministrado: conserva todas las filas y señala los datos pendientes. Solo produce un catálogo GeoJSON cuando se declaran los metadatos necesarios y la dirección supera las validaciones. No importa el catálogo en la base, no geocodifica denuncias ni consulta el servicio de origen. Los esquemas de vías y centros poblados siguen siendo contratos de integración pendientes.

Antes de incorporar una referencia geográfica deben quedar identificados su fuente y versión, el significado de los campos, el sistema de coordenadas y la geometría. Una tabla con una columna `Shape *` que contiene únicamente `Point` o `Polyline` conserva el tipo indicado por la exportación, pero no la geometría.

## Puertas

| Campo recibido | Correspondencia o uso | Condición |
| --- | --- | --- |
| `OBJECTID *` | Identificador de la fila exportada | Vincularlo a fuente y versión; no asumir estabilidad entre exportaciones |
| `UBIGEO` | `ubigeo` | Conservar original y normalizar a seis dígitos; comprobar territorio |
| `CATVIA`, `CATVIA_O`, `NOMVIA` | Categoría, otra categoría y nombre de vía | El diccionario no enumera el significado de los códigos numéricos; requiere un dominio confirmado para esta fuente |
| `P13_1`, `P13_2` | Latitud y longitud, respectivamente | Confirmado por el diccionario; el datum/CRS sigue pendiente |
| `P17`, `P17_A` | Número y letra de puerta | Combinar sin perder ceros o letras; señalar sufijos incompatibles y ausencia de numeración |
| `CODCCPP`, `NOMBCCPP`, `NUCLEO` | Código y nombre de centro poblado; nombre de núcleo urbano | Conservar contexto y códigos; no inferir geometrías |
| `MANZANA` | Código de manzana de la referencia | Mantener separado de `P21`; el diccionario no establece equivalencia entre ambos |
| `P21`, `P22`, `P23_K` | Manzana N°, lote N° y kilómetro N° | Requieren contexto y reglas específicas; esta versión no los convierte en puertas numeradas |
| Grupo `_R` | Atributos adicionales con descripciones rurales/residenciales | El diccionario describe `CATEGORIA_VIA_O_R` como rural y `NOM_VIA_R` como residencial; conservar sin asumir significado del grupo o precedencia |
| Grupo `_RES` | Categoría y nombre de vía residencial | Preservar; no interpretarlo como revisión ni reemplazar automáticamente la vía principal |

El adaptador conserva `raw`, ordinal, atributos normalizados e incidencias por fila en `staging.jsonl`. `manifest.json` registra las huellas SHA-256 de entrada, diccionario y preparación, junto con los conteos y los metadatos faltantes. Los originales no se modifican y una preparación previa no se sobrescribe.

Para preparar datos sin asignar un sistema de coordenadas, ejecutar desde la raíz del proyecto con el entorno del backend:

```powershell
.\backend\.venv\Scripts\python.exe -m geopol.reference_doors --input .local/puertas.xlsx --sheet Hoja1 --dictionary .local/diccionario.jpg --output .local/puertas-preparadas
```

Este comando no supone un CRS ni genera puntos operativos por reconocer las columnas de latitud y longitud. Para habilitar GeoJSON se necesitan `--source`, `--version`, el archivo del diccionario y `--crs EPSG:4326` **solo cuando ese sea el CRS confirmado de las coordenadas exportadas**. Si el origen utiliza otro CRS, primero hay que transformarlo con una herramienta GIS; este adaptador no reproyecta. El código 4326 identifica WGS 84, como muestra la [documentación de SpatialReference de Esri](https://doc.esri.com/es/arcgis-pro/latest/arcpy/classes/spatialreference.html), pero no figura en el diccionario recibido.

`--street-types` recibe un archivo JSON de códigos a etiquetas confirmado para esta fuente. No se reutilizan por suposición los códigos de otra tabla. Las etiquetas soportadas son AVENIDA, CALLE, JIRON, PASAJE, CARRETERA, MALECON y PROLONGACION, con las abreviaturas reconocidas por el normalizador. Categorías desconocidas, genéricas o contradictorias quedan pendientes; los campos alternativos, residenciales, manzana/lote y kilómetro conservan su información para una ampliación explícita del mapeo.

Con los metadatos y la dirección validados, el adaptador produce puntos `kind=door` en orden longitud/latitud, compatibles con el importador del proyecto. Una fila sin número no acredita una puerta numerada. Si una misma clave de UBIGEO, tipo de vía, nombre y número con letra conduce a puntos diferentes, todas esas filas permanecen en la preparación y se excluyen del catálogo generado. No se selecciona el primer punto ni se promedian coordenadas. Las filas repetidas conservan su trazabilidad. La elegibilidad del catálogo no equivale a una denuncia geocodificada: todavía se requiere la validación territorial y de candidatos del motor antes de aceptar resultados.

Límites de esta herramienta: 100 000 filas, 256 MiB de registros preparados y 24 MiB de GeoJSON por ejecución. No es una carga nacional en streaming; hay que particionar referencias mayores.

## Vías

| Campo recibido | Correspondencia o uso | Condición |
| --- | --- | --- |
| `UBIGEO`, `CODCCPP`, `NOMCCPP` | Contexto territorial | `CODCCPP` por sí solo no es una clave nacional |
| `CAT_VIA`, `NOMBRE_CAT` | Tipo de vía | Conservar código y etiqueta; validar el dominio de la fuente |
| `NOMBRE_VIA` | `street_name` | Tratar nombres no informativos según diccionario, sin crear equivalencias geográficas |
| `NOMBRE_ALT` | Posible alias explícito | Confirmar marcadores especiales; no convertir cualquier valor en alias |
| `Shape_Length` | Longitud reportada por la fuente | No acredita unidades o CRS y no permite reconstruir vértices |
| Geometría de la capa original | `geometry` de `kind=street` | Se requiere LineString o MultiLineString en EPSG:4326 |

Los atributos permiten preparar un vocabulario de vías y examinar claves. Para incorporarlos como referencia espacial hay que exportar la capa original con sus geometrías o enlazar por una clave fiable a una capa espacial autorizada. Segmentos con el mismo nombre no son automáticamente duplicados. No construir líneas a partir del orden de filas, la longitud o puntos de centros poblados.

La herramienta [Features To JSON de ArcGIS](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/conversion/features-to-json.html) permite exportar atributos y geometrías a GeoJSON. Al transformar a WGS84 debe estar correctamente definido el sistema de origen. También puede recibirse la clase espacial de la geodatabase, con sus metadatos, y preparar una conversión separada. La API actual no importa directamente `.gdb`.

## Centros poblados

`IDCCPP`, `UBIGEO`, `CODCCPP` y `NOMBCCPP` permiten identificar y relacionar localidades. `LONGITUD` y `LATITUD` contienen ejes explícitos; todavía se requiere identificar su CRS. `AREA_AMBITO`, `CATEGORIA`, `DESC_CATEGORIA` y `CAPITAL` aportan atributos cuyo dominio debe conservarse.

El punto de un centro poblado sirve como referencia de localidad. No acredita la puerta, el lugar preciso de una denuncia ni el polígono del centro poblado. El `kind=nucleus` actual exige polígonos; no se debe adaptar esta tabla cambiando solo el tipo o promoviendo el punto a resultado preciso. Incorporar centros poblados puntuales requerirá un rol de contexto diferenciado y visible en resultados/exportaciones. Un nombre repetido dentro de un UBIGEO no debe resolverse automáticamente sin su código u otro contexto.

## Validación de la integración

1. Conservar original, ordinal, hash y atributos sin reinterpretar.
2. Aplicar un perfil explícito de campos, categorías y valores nulos, con fuente y versión. El significado de los campos de puertas ya está documentado; faltan metadatos y dominios de la fuente.
3. Validar claves, coordenadas, CRS, geometrías y cobertura territorial. Registrar discrepancias con límites disponibles.
4. Conservar homónimos y claves incompatibles como candidatos; distinguir repetición de segmentación espacial.
5. Probar con ejemplos sintéticos y con la muestra en una ejecución separada antes de seleccionar el catálogo operativo.
6. Medir cobertura y precisión por producto. La presencia en un mismo distrito o la coincidencia textual no equivale a una geocodificación aceptada.

Para activar estas referencias se necesita: nombre de capa o servicio y versión, códigos de categorías y valores especiales, CRS de las coordenadas exportadas de cada capa, y geometrías de las vías. Una muestra territorial compartida entre puertas, vías y centros poblados permitirá comprobar las relaciones entre las tres fuentes.
