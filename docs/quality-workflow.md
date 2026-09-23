# Carga de referencias, flags de calidad y revisión

El flujo permite cargar el Excel de la PNP junto a sus referencias, resolver primero las puertas y continuar con las ubicaciones pendientes. Cada decisión conserva su fuente, precisión, motivo e historial. El Excel exportado presenta el **flag de calidad** y el **estado de revisión en columnas separadas**; el archivo original permanece conservado.

Los flags 1 y 2 siguen la lámina suministrada «Alternativas de llenado del campo UBICACION». **Describen la estructura de la ubicación recibida y no aseguran que sea correcta ni esté geográficamente verificada.** La aceptación automática, la revisión rápida y la revisión detallada son estados independientes. La política que mantiene esta separación es `quality-2.0`.

## 1. Cargar los archivos

Abrir **Carga de archivos**. En la columna izquierda se carga el Excel de la PNP. A la derecha aparecen cinco espacios para importar referencias `.xlsx` o elegir versiones previamente importadas:

| Espacio | Fuente prevista | Información que permite contrastar |
| --- | --- | --- |
| Puertas / viviendas | Pre Censos | Dirección y número de puerta con un punto real. |
| Vías y cuadras | Pre Censos | Vías y tramos con geometría lineal; cuadras identificadas e intersecciones documentadas, cuando estén incluidas. |
| Centros poblados | Pre Censos | Nombre o código del centro poblado y su punto de referencia. |
| Límites administrativos | Pre Censos | Polígonos y códigos administrativos; el control territorial de este MVP utiliza límites distritales. |
| Jurisdicciones | SIDPOL / DATACRIM | Polígonos de jurisdicción y sus identificadores o nombres. |

Los nombres de las fuentes indican su uso previsto. La aplicación no descarga estas bases institucionales ni confirma por sí misma que un archivo pertenece a Pre Censos 2025: se debe registrar la fuente y la versión efectivamente recibidas.

Para cada referencia:

1. Seleccionar el Excel y la hoja que corresponde.
2. Revisar la correspondencia de columnas sugerida. Confirmar especialmente UBIGEO, nombre de vía, puerta, latitud, longitud y geometría.
3. Registrar un nombre, fuente y versión que permitan identificar esa entrega.
4. Confirmar `EPSG:4326` únicamente si existe documentación del proveedor y registrar esa evidencia. Si se desconoce el sistema de coordenadas, mantenerlo sin confirmar.
5. Importar y revisar cuántas filas quedaron disponibles y cuántas pendientes, junto con sus motivos.

Las columnas X/Y no confirman el sistema de coordenadas ni su orden. El diccionario de puertas recibido identifica `P13_1` como latitud y `P13_2` como longitud; esa descripción no establece el datum. Los códigos numéricos de categoría de vía, como `CATVIA`, requieren su dominio documentado antes de interpretarse como avenida, calle u otra categoría.

Se puede trabajar con una selección parcial de referencias. El procesamiento informa las capas ausentes; seleccionarlas en pantalla no convierte filas pendientes en referencias utilizables. Cada nueva ejecución conserva una copia de las versiones seleccionadas para que una importación posterior no cambie sus resultados.

### Cuando el Excel todavía no tiene geometría

Las puertas y los centros poblados necesitan un punto real. Las vías y cuadras necesitan una línea; los límites y las jurisdicciones, un polígono. El importador admite geometrías en una columna WKT o GeoJSON. No construye una calle ni un polígono a partir de su nombre o de un único par de coordenadas.

Si falta geometría, el CRS está sin confirmar o la fila presenta otra incidencia, **el archivo y sus filas se conservan pendientes de preparación**. Esas filas no se utilizan para aceptar ubicaciones automáticamente. Cuando se reciba la geometría o se prepare la capa en una herramienta SIG, debe importarse una nueva versión documentada. El MVP no transforma automáticamente otros sistemas de coordenadas a `EPSG:4326`.

Las filas de límites de provincia o departamento también se conservan, pero no sustituyen el límite distrital necesario para comprobar el UBIGEO de una dirección. La coincidencia de nombres, por sí sola, no reemplaza esta comprobación.

## 2. Identificar el flag e iniciar por puertas

En la configuración del archivo de la PNP, seleccionar el flujo por calidad que comienza por puertas, comprobar el mapeo y crear el procesamiento. El flag se identifica a partir de los campos normalizados de la ubicación; esta primera ejecución contrasta únicamente la etapa de puertas.

| Flag | Alternativa de formato identificada | Lo que indica |
| --- | --- | --- |
| 1 | Tipo de vía + nombre + número de puerta + distrito | Están presentes los componentes de una dirección de puerta. |
| 1 | Vía + cuadra + distrito | Están identificadas la vía, la cuadra y el contexto distrital. |
| 1 | Cruce de dos vías distintas + distrito | Está identificado el formato de intersección. |
| 1 | Par de coordenadas válido en formato latitud/longitud | Hay coordenadas declaradas con valores interpretables; todavía pueden necesitar confirmación del CRS y comprobación territorial. |
| 2 | Núcleo urbano o centro poblado + distrito | La ubicación aporta una referencia general nombrada. |
| 2 | Vía + jurisdicción explícita | La ubicación aporta una vía y el nombre o código de su jurisdicción. |
| Sin asignar | Componentes incompletos o contradictorios | No se fuerza el registro dentro de una alternativa que no se puede identificar. |

Para este reconocimiento de formato, el distrito se considera declarado mediante un UBIGEO con estructura distrital válida o un campo de distrito explícito y sin alternativas ambiguas. Eso no equivale a demostrar que el nombre corresponde a una única geometría en el catálogo. Una jurisdicción nunca se deduce únicamente del distrito. El número de cuadra tampoco se deduce aritméticamente del número de puerta.

Si la entrada cumple varias alternativas, **el flag 1 tiene prioridad sobre el flag 2**. Dentro del flag 1 se documenta la alternativa encontrada: coordenadas, puerta, cuadra o cruce. Una dirección con error tipográfico puede conservar flag 1 y quedar en revisión. El flag no cambia porque el motor encuentre un candidato distinto o termine resolviendo con una precisión menor; describe los componentes de entrada, no el resultado del contraste.

### Leer el estado junto al flag

| Estado | Tratamiento |
| --- | --- |
| Automático | El motor aceptó el resultado con evidencia suficiente. Una puerta requiere coincidencia exacta o alias explícito y comprobaciones de número, territorio, punto, CRS y procedencia. |
| Revisión rápida | Hay un candidato de puerta con nombre similar y guardas suficientes para una confirmación humana breve. |
| Revisión detallada | Hay ambigüedad, contradicciones u otros aspectos que necesitan evaluación. |
| Aceptado manualmente | Una persona confirmó el resultado y registró su motivo. |
| Sin coincidencia | La etapa no produjo una ubicación resuelta; puede continuar si corresponde. |
| Referencia pendiente | Falta una capa o documentación necesaria para completar la comprobación. |
| Sin procesar | La ubicación todavía no ha sido evaluada. |

Por ejemplo, **flag 1 + revisión rápida** es una combinación válida. También lo es **flag 2 + automático** cuando la referencia general se corrobora con la precisión que realmente tiene. El flag no sustituye ninguna guarda geográfica ni se interpreta como probabilidad.

Una coordenada original de la PNP puede aportar evidencia o revelar una contradicción, pero no basta para declarar una coincidencia exacta de puerta. Una cuadra conserva su geometría de tramo incluso con flag 1. Un punto de centro poblado conserva la precisión `CENTRO_POBLADO`: representa esa referencia geográfica, no un domicilio exacto. No se generan centroides para suplir ubicaciones faltantes.

## 3. Continuar solamente con los pendientes

Abrir el módulo de calidad y seleccionar el procesamiento. También se puede consultar su pestaña de calidad dentro de la ejecución. El orden disponible es:

**Puertas → Cuadras → Cruces de vías → Vías → Núcleos y centros poblados → Jurisdicciones.**

El botón **Continuar con…** muestra la siguiente etapa y la cantidad de ubicaciones elegibles. Al ejecutarla:

- Las ubicaciones resueltas conservan su decisión y no se vuelven a analizar.
- Las ubicaciones con candidatos pendientes de revisión permanecen en esa revisión; no se desplazan automáticamente hacia una precisión menor.
- Las ubicaciones sin coincidencia o bloqueadas por la falta de referencia pueden continuar a la siguiente etapa. La falta de una capa sigue registrada como tal, separada de una búsqueda completa sin coincidencias.
- Las reservas de revisión vigentes se respetan y no se ejecutan dos avances simultáneos del mismo procesamiento.

El avance depende de que exista una decisión geográfica resuelta, no del número de flag. Un flag 1 pendiente no se omite como si ya estuviera verificado y un flag 2 aceptado no se vuelve a procesar. Las etapas conservan su nombre y precisión; no se inventan otros flags. Una jurisdicción se contrasta con evidencia geográfica o identificación explícita; pertenecer a un distrito no permite elegir por sí solo una jurisdicción policial.

### Resolver la revisión sin repetir el trabajo

Filtrar por el estado **Revisión rápida** y abrir sus pendientes. Confirmar el candidato y registrar el motivo cuando la evidencia lo respalde. La aceptación humana cambia el estado a aceptado manualmente y conserva el flag correspondiente al formato de entrada. El mismo criterio se aplica a la revisión detallada.

Cuando se determina que ningún candidato corresponde, registrar la decisión sin coincidencia para que la ubicación pueda continuar. Una corrección de dirección sin resultado geográfico tampoco equivale a una ubicación resuelta. Si se reabre un resultado aceptado, vuelve a revisión; su flag no es una autorización para omitir esa revisión.

## 4. Interpretar las gráficas

El módulo presenta cantidades y porcentajes de resueltos, por revisar, sin coincidencia y referencias o datos pendientes. El resumen diferencia:

- **Filas de origen:** filas del archivo de la PNP.
- **Unidades de ubicación:** agrupaciones de filas que describen la misma ubicación de una denuncia.

Los porcentajes del gráfico de cada etapa se calculan sobre las unidades evaluadas en esa etapa. Las tablas de flags y estados de revisión utilizan el total de ubicaciones del procesamiento y se presentan por separado. Una ubicación puede aparecer en la historia de varias etapas; por eso **las cantidades de los gráficos no deben sumarse como si fueran ubicaciones distintas**.

La tabla y los filtros muestran la clasificación vigente. El historial de cada etapa permite saber por dónde pasó una ubicación antes de alcanzar su resultado actual.

## 5. Descargar el Excel actualizado

En **Consultar y exportar un filtro**, elegir flag, estado de revisión y/o etapa. Preparar una exportación en formato Excel y descargarla cuando termine. Para obtener el archivo completo, utilizar **Ver acumulado completo** o la opción de exportación acumulada.

El Excel incorpora **Flag de calidad**, **Estado de revisión**, **Motivo del flag**, etapa, motivo de resolución y versión de la política, además de los campos de precisión y resolución geográfica. Los códigos de clasificación usados internamente para compatibilidad no se presentan como flags adicionales. Se mantienen los formatos de lectura, filtros y encabezados de la exportación Excel existente.

- El perfil de ubicaciones genera una fila por unidad de ubicación.
- El perfil ampliado conserva las filas originales vinculadas, incluidas las repetidas, y las presenta en una hoja separada. Requiere rol operador o administrador.
- Una exportación filtrada contiene únicamente las ubicaciones del filtro y, en el perfil ampliado, sus filas de origen correspondientes.
- La exportación acumulada incluye resueltos y pendientes con sus flags y estados vigentes. No es necesario volver a importar el Excel descargado para avanzar: la aplicación ya conserva ese progreso.

Cada exportación es una instantánea de las revisiones vigentes al solicitarla. Si después se confirma una revisión o avanza otra etapa, debe prepararse una nueva exportación para reflejar esos cambios. El CSV continúa disponible para uso en GIS.

## Historial, límites y componentes

Las ejecuciones anteriores conservan sus datos, decisiones y exportaciones. No se reinterpretan silenciosamente sus resultados como nuevos flags. Para probar este flujo, crear una nueva ejecución y seleccionar el procesamiento por calidad que comienza por puertas.

El importador de referencias está acotado para el MVP: hasta **100 000 filas por Excel** y, en el conjunto seleccionado, hasta **100 000 entidades y 24 MiB de referencias espaciales serializadas**. La carga individual de referencia tiene un límite de 24 MiB. El tamaño del conjunto incluye geometrías y metadatos, por lo que no equivale a la suma del tamaño comprimido de los Excel. Para ampliar cobertura, preparar selecciones territoriales que respeten estos límites. Este módulo no constituye una validación para volumen nacional.

La proporción de aceptaciones automáticas depende de cobertura, geometría, calidad de direcciones y documentación de las referencias. Hasta disponer de los cinco archivos reales y evaluar su contenido, no se puede prometer un porcentaje de automatización.

La implementación mantiene las responsabilidades separadas:

| Componente | Responsabilidad |
| --- | --- |
| `reference_excel.py` y API de referencias Excel | Perfil, mapeo, conservación de pendientes y construcción del conjunto versionado. |
| `domain/quality.py` | Reconocimiento del flag de entrada, estado de revisión y reglas geográficas por etapa, independientes de HTTP y base de datos. |
| `quality_workflow.py` y worker | Elegibilidad para avanzar, persistencia de decisiones e historial por etapa. |
| API y panel de calidad | Conteos, porcentajes, filtros y solicitud del avance. |
| Exportaciones | Instantáneas de resultados vigentes, filtros y Excel con flag y estado de revisión separados. |

Consultar también la [guía de exportación](excel-exports.md), el [flujo de revisión](review-workflow.md) y la [guía de operación](runbook.md).
