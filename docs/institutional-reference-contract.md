# Integración de tablas institucionales de referencia

Este contrato recoge los esquemas de muestras proporcionadas por el usuario. El nombre de un archivo, sus campos y la fecha de creación del Excel no acreditan institución de origen, año censal ni vigencia cartográfica. Los archivos, perfiles y cruces con datos operativos se conservan exclusivamente en `.local/`.

## Situación de la aplicación

La importación vigente acepta catálogos CSV o GeoJSON. No importa directamente estos tres esquemas Excel ni consulta el servicio del que proceden. Las correspondencias siguientes especifican la preparación necesaria; no están activadas como nuevas reglas ni como aprendizaje automático de direcciones.

Antes de incorporar una referencia geográfica deben quedar identificados su fuente y versión, el significado de los campos, el sistema de coordenadas y la geometría. Una tabla con una columna `Shape *` que contiene únicamente `Point` o `Polyline` conserva el tipo indicado por la exportación, pero no la geometría.

## Puertas

| Campo recibido | Correspondencia o uso | Condición |
| --- | --- | --- |
| `OBJECTID *` | Identificador de la fila exportada | Vincularlo a fuente y versión; no asumir estabilidad entre exportaciones |
| `UBIGEO` | `ubigeo` | Conservar original y normalizar a seis dígitos; comprobar territorio |
| `CATVIA`, `CATVIA_O`, `NOMVIA` | Tipo y nombre de vía | Confirmar diccionario de categorías y significado de valores nulos |
| `P13_1`, `P13_2` | Posibles ejes de coordenadas | Los rangos son indicios; confirmar orden de ejes y CRS antes de construir puntos |
| `P17`, `P17_A` | Posible número y complemento | Confirmar diccionario; conservar letras, sufijos y ausencia de numeración |
| `CODCCPP`, `NOMBCCPP`, `NUCLEO`, `MANZANA` | Contexto territorial y de dirección | No equiparar códigos de manzana censal con manzana de urbanización |
| `P21`, `P22`, `P23_K` | Atributos por identificar | Preservar sin asignar semántica supuesta |
| Campos terminados en `_R` o `_RES` | Posibles valores revisados | Confirmar precedencia respecto al original, no elegirla por el nombre del campo |

Con ejes y CRS confirmados, el adaptador podría producir puntos `kind=door` en EPSG:4326. Una fila sin número no acredita una puerta numerada. Si una misma clave de dirección conduce a puntos diferentes, se conservan candidatos y procedencias: no seleccionar el primero ni fusionar geometrías por el texto. Las filas repetidas conservan su trazabilidad.

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

## Validación del adaptador futuro

1. Conservar original, ordinal, hash y atributos sin reinterpretar.
2. Aplicar un perfil explícito de campos, categorías y valores nulos, con fuente y versión.
3. Validar claves, coordenadas, CRS, geometrías y cobertura territorial. Registrar discrepancias con límites disponibles.
4. Conservar homónimos y claves incompatibles como candidatos; distinguir repetición de segmentación espacial.
5. Probar con ejemplos sintéticos y con la muestra en una ejecución separada antes de seleccionar el catálogo operativo.
6. Medir cobertura y precisión por producto. La presencia en un mismo distrito o la coincidencia textual no equivale a una geocodificación aceptada.

Para preparar la siguiente integración se necesita: nombre de capa o servicio y versión, diccionario de campos y valores especiales, CRS de cada capa, y geometrías de las vías. Una muestra territorial compartida entre puertas, vías y centros poblados permitirá comprobar las relaciones entre las tres fuentes.
