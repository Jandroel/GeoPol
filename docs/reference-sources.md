# Cartografía pública local y reproducible

GeoPol puede construir catálogos locales a partir de descargas públicas completas. El descargador no recibe direcciones, personas, expedientes ni selectores territoriales de los lotes. La selección por UBIGEO y nombres se ejecuta después, en el equipo. El constructor no hace solicitudes de red.

## Fuentes disponibles

| Fuente | Contenido y CRS | Procedencia y límites |
| --- | --- | --- |
| [OpenStreetMap Perú, distribuido por Geofabrik](https://download.geofabrik.de/south-america/peru.html) | Nodos, vías y relaciones del extracto nacional; coordenadas WGS84 | Datos comunitarios bajo [ODbL 1.0, atribución a OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Cobertura variable; no es un padrón oficial de puertas. El PBF contiene su fecha de replicación. |
| [MINAM, ServicioPMIZMC, capa 8](https://geoservidorperu.minam.gob.pe/arcgis/rest/services/ServicioPMIZMC/MapServer/8?f=pjson) | Límites distritales con `IDDIST`; la fuente declara EPSG:32718 y se solicita la transformación oficial del servicio mediante `outSR=4326` | La capa pertenece a “Limites Politico Referenciales”. Metadatos sin fecha general de vigencia ni licencia explícita de reutilización. No certifica jurisdicción legal. Se conserva esa condición en cada entidad y en el manifiesto. |

La fecha de descarga identifica una adquisición, no acredita la vigencia territorial. Campos administrativos como `FECHA` no se reinterpretan como fecha de actualización de toda la cartografía. La licencia ODbL de OSM no se aplica automáticamente a la capa independiente del MINAM; el catálogo mantiene ambas procedencias por entidad.

## Instalación opcional y ejecución

El servidor y el worker no requieren el lector PBF. Instalarlo solo en el entorno que construye referencias:

```powershell
backend/.venv/Scripts/python.exe -m pip install osmium==4.3.1
backend/.venv/Scripts/python.exe -m geopol.reference_download --output .local/real-references/raw --source both
backend/.venv/Scripts/python.exe -m geopol.reference_builder --pbf .local/real-references/raw/peru-latest.osm.pbf --boundaries .local/real-references/raw/minam-national-boundaries.geojson --ubigeos .local/real-references/ubigeos.json --selector .local/real-references/selector.json --cutoff 80 --output .local/real-references/catalog
```

`ubigeos.json` es una lista de cadenas de seis dígitos. El selector opcional relaciona cada UBIGEO con una lista de nombres de calles, cruces, lugares o núcleos. Por ejemplo, únicamente con datos ficticios:

```json
{"010101": ["AVENIDA DEMOSTRACION", "CALLE SINTETICA", "PLAZA DE PRUEBA"]}
```

Sin `--selector`, se retienen las entidades compatibles de todos los distritos solicitados. Con selector, se incluyen los nombres principales y los alias explícitos de OSM cuya similitud `rapidfuzz.fuzz.ratio` sea al menos 80 dentro del distrito. También se realiza un filtro nacional previo con la unión de esos nombres. Ese filtro conserva posibles competidores; no concede aceptación automática ni modifica las reglas geográficas. El umbral y los SHA-256 de los selectores quedan en el manifiesto, sin copiar sus nombres al informe de cobertura.

## Transformaciones permitidas

- `door`: nodo OSM con `addr:housenumber` y `addr:street` explícitos. Se conserva el número, incluyendo letras. Un edificio numerado no se convierte en una puerta mediante su centroide.
- `street`: tramos reales de vías nombradas, obtenidos mediante intersección geométrica exacta con el límite distrital. Los segmentos con igual nombre, tipo y distrito se unen y enlazan sin simplificación. La transformación `clip_to_boundary`, el identificador y la versión del límite quedan registrados. El PBF conserva las vías originales completas. Una vía puede conservar varios componentes: el motor debe valorar esa ambigüedad. Las vías no se convierten en puntos ni una tangencia aislada produce un tramo ficticio.
- `intersection`: nodo OSM compartido por dos vías nombradas, con `layer` y `level` iguales a cero o no declarados, y sin indicación de puente, túnel o cobertura. Se conserva el nodo y las vías de origen. La conectividad cartografiada depende de la calidad del etiquetado OSM.
- `site`: punto de interés nombrado en un nodo real (`point_role=mapped_poi`) o polígono real de vía cerrada/relación. No se calculan centroides.
- `nucleus`: polígono real nombrado y etiquetado como asentamiento o barrio; no se utiliza un nodo de localidad como sustituto del área.
- `boundary`: polígono distrital íntegro de la descarga MINAM. Las geometrías inválidas se excluyen y se reportan. No se simplifican, reparan ni inventan bordes.

El constructor no infiere cuadras a partir de números de puerta ni manzanas a partir de edificios o usos del suelo. Los tipos `block` y `manzana` pueden importarse desde otros catálogos que los documenten expresamente. Los alias provienen de `alt_name`, `official_name`, `loc_name` y `short_name`; no se convierten nombres numéricos como UNO en 1.

## Evidencia y comprobación

El descargador conserva páginas nacionales, metadatos oficiales y manifiestos con URL, adquisición, tamaño y SHA-256. Verifica además el MD5 publicado por Geofabrik. La paginación MINAM usa `where=1=1`, orden por `OBJECTID`, total declarado y control de duplicados.

El constructor genera `catalog.geojson` y `manifest.json`, con cobertura por UBIGEO y tipo, geometrías inválidas o distritos faltantes, número de entidades y bytes. Ejecuta el mismo lector que usa la importación de la aplicación. Cada entidad conserva sus identificadores OSM/MINAM, procedencia y versión; el catálogo global no los reemplaza.

El indicador `within_import_limits` compara el archivo con 24 MiB y 100.000 entidades, o el límite de bytes declarado expresamente con `--max-bytes`. Ese argumento documenta la comprobación: **no cambia la configuración de la API**. Si el archivo supera el límite, hay que revisar su partición territorial o configurar y validar expresamente una capacidad mayor. No se reduce silenciosamente la geometría para lograr que el archivo entre.

Brutos, selectores, catálogos derivados y manifiestos de trabajo se guardan bajo `.local/`, excluido de Git. El catálogo debe validarse antes de seleccionarlo en un reproceso nuevo; construirlo no importa nada en la base operativa ni modifica lotes previos.

## Alternativas INEI verificadas por metadatos

El 21 de septiembre de 2026 se consultaron `GetCapabilities`, `DescribeFeatureType` y `GetFeature` con `resultType=hits` del [WFS público Interoperabilidad del INEI](https://geoespacial.inei.gob.pe/geoserver/Interoperabilidad/ows?service=WFS&version=2.0.0&request=GetCapabilities). Estas consultas devolvieron únicamente metadatos y conteos nacionales: no se descargaron las geometrías ni se enviaron selectores privados.

| Capa | Conteo declarado | Geometría/campos | Uso posible y limitación |
| --- | ---: | --- | --- |
| `Interoperabilidad:ig_manzana` | 540.052 | MultiSurface; `ubigeo`, `zona`, `manzana`, `codccpp`, `idmanzana` | Polígonos de manzana censal. Se necesita correspondencia demostrable entre su código censal y la manzana de una dirección; no equiparar automáticamente un código censal con una letra de urbanización. |
| `Interoperabilidad:ig_casco_urbano` | 1.884 | MultiSurface; `ubigeo`, `nombdist`, `descrpcion`, `tematica` | Delimitación urbana para contexto. No prueba que exista un polígono individual de cada barrio o urbanización. |
| `Interoperabilidad:ig_centropoblado` | 94.922 | Point; `idccpp`, `nombccpp`, `codccpp`, `ambito`, `ubigeo`, `fuente` | Nombres y puntos de centros poblados para contraste. El punto de una localidad no es el lugar de un hecho ni satisface el contrato poligonal de `nucleus`. |

Las tres capas anuncian EPSG:4326. Sus esquemas consultados no aportan una fecha general de actualización ni una licencia explícita; los conteos son una observación del servicio, no una certificación de completitud o vigencia. Para consultar un esquema se usa `request=DescribeFeatureType&typeNames=Interoperabilidad:ig_manzana`; para contar sin geometrías, `request=GetFeature&typeNames=Interoperabilidad:ig_manzana&resultType=hits`.

Una comprobación adicional de WFS/WMS encontró títulos genéricos, `Abstract` vacío y ausencia de `MetadataURL` para las tres capas. Una muestra limitada a atributos —sin geometrías— devolvió `fuente=INEI - CPV RESULTADOS` en diez centros poblados, sin año, y `descrpcion=CASCO URBANO`, `tematica=T01` en cinco cascos urbanos. Esos valores no acreditan una versión censal ni proporcionan nombres de barrios para emparejar automáticamente núcleos urbanos. El `timeStamp` de una respuesta WFS es la fecha de la respuesta; no es la fecha de la cartografía.

El [portal de censos del INEI](https://www.inei.gob.pe/estadisticas/censos/) anuncia los Censos Nacionales 2025 y sus primeros resultados. Esa publicación no demuestra que estas capas geográficas concretas estén actualizadas al Censo 2025. Tampoco basta el título genérico de los servicios para atribuirlas al Censo 2017. GeoPol debe conservar la versión como no confirmada hasta contar con documentación del conjunto exacto utilizado.

El [portal oficial IDE INEI](https://ide.inei.gob.pe/) anuncia esas capas y ofrece archivos GPKG de límites administrativos actualizados al 2023. No se identificó allí un catálogo descargable de puertas numeradas o ejes viales urbanos. El [catálogo nacional IDEP](https://www.geoidep.gob.pe/catalogo-nacional-de-servicios-web/servicio-de-descarga-wfs) también publica enlaces antiguos bajo `maps.inei.gob.pe/geoserver/T10Limites`; el enlace de metadatos de manzanas respondió HTTP 401 en la verificación. Se conserva como referencia de catálogo, sin intentar eludir la restricción.

Las presentaciones institucionales aportadas describen numeración de puertas INEI y un archivo ilustrativo `Departamentos_Distritos_CCPP.gdb`, pero no proporcionan URL de descarga, inventario de capas, diccionario ni licencia. Ese material no acredita que las capas de puertas o vías estén incluidas en los servicios públicos anteriores.

El análisis posterior de muestras tabulares de puertas, vías y centros poblados se recoge en el [contrato de integración institucional](institutional-reference-contract.md). Documenta los campos por confirmar y la geometría necesaria; esas muestras todavía no constituyen un catálogo operativo importado.
