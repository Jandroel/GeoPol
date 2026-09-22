# Automatización con referencias y revisión de equivalentes

## Carga y referencia base

El administrador puede definir un catálogo base desde Catálogos de referencia.
La configuración persiste en la base mediante la migración 4 y queda auditada.
Cada procesamiento conserva el identificador de la versión utilizada: cambiar la
base no modifica ejecuciones anteriores. La opción explícita sin catálogo permite
normalizar datos conservando la limitación de cobertura.

El API distingue `reference_id` omitido (utilizar la base) de `null` explícito
(procesar sin referencia). Un reproceso conserva el catálogo anterior salvo
selección explícita. Una referencia configurada pero ausente o vacía se informa;
no se sustituye silenciosamente por otra fuente.

## Coordenadas originales

La carga parte de CRS no confirmado. Declarar EPSG:4326 exige una fuente de
confirmación de 8 a 500 caracteres (`crs_evidence`), guardada junto al mapeo y
el resto de la configuración. La declaración se refiere al archivo concreto;
el rango numérico de una coordenada no demuestra su datum ni su procedencia.

El worker exige esa declaración documentada al ingerir y al resolver pendientes,
incluidos trabajos antiguos que ya hubieran ingerido datos. Un campo CRS del archivo
se conserva como `source_crs`, sin sustituir la declaración documentada del operador.
Una contradicción entre el archivo y la declaración impide la aceptación automática.
El reproceso no hereda como confirmada la asignación WGS84 de versiones antiguas de
la pantalla de carga. Las ejecuciones terminadas y sus revisiones no se reescriben.

Se puede procesar un lote con CRS desconocido usando las direcciones contra un
catálogo documentado. Las coordenadas originales quedan pendientes. Las fuentes
propias del catálogo conservan su CRS y no necesitan que se conozca el del archivo
PNP para contrastar una dirección textual.

Una coordenada original corroborada dentro del distrito no equivale a una puerta
corroborada. Los resultados mantienen método, precisión, evidencia, procedencia y
geometría. Áreas y tramos conservan su forma y dejan vacías las coordenadas puntuales.

## Resolver las causas comunes

El diagnóstico de la ejecución cuenta pendientes por causa y ofrece acciones para
referencias, datos y atención técnica. La falta de catálogo no debe convertirse en
una obligación de aprobar registros individualmente. Incorporar una referencia y
reprocesar permite volver a evaluar todas las ubicaciones preservando el historial.
La bandeja reserva la revisión accionable para casos con evidencia disponible.

## Revisión de grupos equivalentes

La vista previa compara direcciones y UBIGEO, componentes normalizados, coordenadas
originales y todos los datos de los candidatos. Solo omite campos administrativos
que no cambian la evidencia geográfica. Las advertencias, alternativas geográficas,
contradicciones, fuentes incompletas y coordenadas sin CRS documentado impiden
agrupar. La coincidencia textual por sí sola no basta.

La revisión se limita a una ejecución vigente terminada y ubicaciones abiertas
sin revisión manual previa. Excluye reservas ajenas. Presenta los registros y filas
afectados; el revisor selecciona un candidato existente, documenta el motivo y
confirma expresamente el alcance. El máximo es 200 ubicaciones por grupo; si se
supera, la vista previa lo indica y bloquea la aplicación, sin aprobar un subconjunto
oculto.

El servidor vuelve a comprobar token, actor, membresía, revisiones, reservas y
evidencias dentro de la transacción. Si algo cambió, responde 409 y no aplica una
parte de la decisión. Cada ubicación conserva su revisión, motivo y vínculo al
grupo. El resultado se registra como **aceptado manualmente**, sin incrementar
las aceptaciones automáticas ni crear memoria masiva de direcciones.

La reutilización explícita de una dirección individual sigue disponible y conserva
su consentimiento, revocación y comprobaciones para futuros procesamientos.

## Contexto cartográfico local

El visor consulta únicamente la referencia fijada en la ejecución y el UBIGEO
seleccionado. Dibuja vías, límites y áreas disponibles como contexto, detrás de los
candidatos y resultados. Mantiene atribución y separa esa información de la decisión
geográfica. No consulta un servidor de mapas externo ni transmite ubicaciones PNP.

La respuesta se limita a 500 entidades y aproximadamente 2 MiB de geometrías. Una
respuesta recortada indica cobertura parcial; no simplifica ni inventa geometrías.
Este límite del visor no modifica la búsqueda ni los controles del motor.

## Piloto ArcGIS opcional

El adaptador `python -m geopol.geocoding_provider` informa su estado sin consultar
la red. `GET /api/geocoding-provider` expone únicamente ese estado a usuarios
autenticados. El worker no llama al adaptador automáticamente.

Antes de un piloto deben configurarse, en el entorno del proceso autorizado:

- `GEOPOL_ARCGIS_ENABLED=true`.
- `GEOPOL_ARCGIS_ENDPOINT`: URL HTTPS del `GeocodeServer` institucional o contratado,
  sin credenciales ni parámetros.
- `GEOPOL_ARCGIS_TOKEN`: credencial conservada fuera del repositorio.
- `GEOPOL_ARCGIS_STORAGE_AUTHORIZATION`: referencia al permiso de almacenamiento.

La entrada del piloto es un JSON preparado con 1–100 direcciones y exclusivamente
los campos `address`, `district`, `province` y `department`. Exige dirección y
distrito. No acepta un archivo de denuncias completo; el responsable debe comprobar
que incluso los textos permitidos no contengan datos personales o confidenciales.
La consulta solo ocurre con `--allow-network`, `--input` y una salida nueva `--output`.
No sobrescribe archivos, no sigue redirecciones y no registra claves o direcciones
en mensajes de error. Los identificadores enviados son ordinales del piloto.

El resultado conserva tipo de coincidencia, geometría, puntaje del proveedor,
procedencia y fecha de adquisición. Rechaza respuestas parciales, identificadores
duplicados y CRS no declarado. Interpolaciones, puntos representativos de calles o
localidades y tipos desconocidos nunca se convierten en puertas verificadas. Todos
los candidatos salen con `accepted=false`; requieren evaluación local de territorio,
componentes, precisión y contradicciones antes de integrar un servicio al motor.
El puntaje no se presenta como probabilidad.

Se siguieron los contratos oficiales de [geocodeAddresses](https://developers.arcgis.com/rest/geocode/geocode-addresses/)
y [tipos de resultado](https://developers.arcgis.com/rest/geocode/service-output/).
La prueba local usa respuestas sintéticas. La calidad y la cobertura reales, el acceso
y los permisos del proveedor quedan pendientes de un servicio autorizado.
