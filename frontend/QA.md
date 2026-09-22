# Verificación de la interfaz

La interfaz se verificó con Chromium real mediante Playwright, una API FastAPI local y su trabajador activos, sobre una base SQLite temporal aislada y exclusivamente datos sintéticos.

## Escenario reproducible

La prueba `e2e/workspace.spec.ts` ejecuta consecutivamente:

1. Inicio de sesión explícito y lectura del dashboard desde la API.
2. Importación de `referencias_sinteticas.geojson` como catálogo privado y versionado.
3. Carga de `denuncias_sinteticas.csv`, verificación del mapeo sugerido, selección del catálogo e inicio del trabajo.
4. Espera del procesamiento real y comprobación de resultados tanto antes como después de recargar el navegador.
5. Apertura de la denuncia ambigua `DEMO-010`, comprobación de dos marcadores visibles, toma de la revisión y aceptación documentada de un candidato.
6. Creación de una exportación, descarga autenticada del CSV y manifiesto, y comprobación de su contenido y pertenencia al lote.
7. Vista de 400 × 900 px, ausencia de desplazamiento horizontal global y navegación del menú mediante Tab, Enter y Escape.
8. Ausencia de errores de consola/excepciones del navegador y de solicitudes HTTP a orígenes externos.

Un segundo escenario comprueba el flujo de revisión con dos ubicaciones sintéticas: procesamiento sin catálogo, categoría de referencia pendiente, reproceso con un catálogo explícito, conservación histórica del padre, aceptación y avance sin reserva automática, cierre sin punto, reapertura, liberación explícita y consulta de finalizados. Verifica también que el formulario no conserva el candidato ni el motivo anteriores y que la bandeja funciona a 400 × 900 px.

El tercer escenario, `e2e/geometry.spec.ts`, importa un tramo y un parque poligonal sintéticos con un límite territorial. Comprueba los contadores automáticos por producto, la geometría conservada y la ausencia de latitud/longitud y marcadores en áreas. Verifica píxeles de la geometría en el canvas WebGL real, atribución OpenStreetMap, vista móvil sin desbordamiento, consentimiento desmarcado inicialmente, reutilización explícita en otro lote y revocación que afecta al siguiente lote sin cambiar el historial. No instrumenta ni sustituye MapLibre y funciona tanto contra Vite como contra el build de producción.

Los escenarios crean catálogos y lotes nuevos en cada ejecución. Se debe usar una base de pruebas y una cuenta con permisos administrativos o equivalentes para ejecutar todos los pasos.

```powershell
npm ci
npx playwright install chromium
$env:GEOPOL_E2E_URL = 'http://127.0.0.1:5174'
$env:GEOPOL_E2E_USER = '<usuario de pruebas>'
$env:GEOPOL_E2E_PASSWORD = '<contraseña de pruebas>'
$env:GEOPOL_E2E_ARTIFACTS = '<carpeta privada de capturas sintéticas>'
npm run test:e2e
```

Antes de ejecutar se deben iniciar API, trabajador y Vite con la configuración de la base aislada. El test no arranca ni detiene servicios existentes. Sin las variables de usuario y contraseña el escenario se omite explícitamente; las credenciales no se incluyen en el repositorio.

## Evidencia local

Actualización del 22 de septiembre de 2026: **20 pruebas Vitest, build TypeScript/Vite y formato aprobados**. Los tres escenarios Chromium pasaron contra Vite en 26,8 segundos y contra el build de producción en 26,1 segundos. La última ejecución incluye el parque poligonal además del tramo. El entorno sintético temporal usó schema 3, API en 18001 y frontend en 15175. El runner privado mantuvo credenciales en memoria, desactivó trazas y cerró exclusivamente los procesos que creó; ambos puertos quedaron libres y la base operativa no fue modificada. Las capturas de tramo en escritorio/móvil y polígono se inspeccionaron visualmente.

Evidencia histórica del 21 de septiembre: 11 pruebas Vitest y los dos escenarios anteriores de Chromium pasaron en 47,1 segundos; la comprobación de acceso y bandeja en el despliegue local tampoco mostró errores del navegador ni desbordamiento horizontal a 400 px.

Las capturas se escriben en `GEOPOL_E2E_ARTIFACTS`, si se configura, o en `.local/` del proyecto; deben excluirse de Git:

- `ui-login.png`: formulario de acceso.
- `ui-dashboard.png`: vista general a 1440 × 1000 px.
- `ui-run.png`: procesamiento finalizado con resultados.
- `ui-review.png`: candidatos y marcadores del visor local.
- `ui-mobile.png`: dashboard móvil a 400 × 900 px.
- `ui-review-prerequisites.png`, `ui-review-queue.png`, `ui-review-finalized.png` y `ui-review-mobile.png`: separación de bloqueos, bandeja accionable, decisión finalizada y consulta móvil del nuevo flujo.
- `ui-geometry-map.png`, `ui-geometry-map-mobile.png` y `ui-geometry-polygon.png`: recortes exclusivos del visor con geometrías sintéticas. La ejecución temporal conserva solo estos recortes en `.local/geometry-qa/`; elimina los demás datos y artefactos del ciclo.

Playwright genera su informe en `frontend/playwright-report/`. En caso de fallo conserva traza y captura en `frontend/test-results/`; estos archivos también se excluyen de Git y pueden contener la sesión sintética del test.

## Ejecución en CI

El job `e2e` de `.github/workflows/ci.yml` configura Python 3.11, Node.js 24 y Chromium en Ubuntu. Instala el backend con `requirements.lock` como restricciones y el frontend con `npm ci`. Después crea una base SQLite y almacenamiento exclusivos del runner, una cuenta administrativa sintética, e inicia API, trabajador y Vite en el puerto 5174. Espera la salud de API y frontend antes de ejecutar el mismo escenario del navegador y detiene los tres procesos al terminar.

Las credenciales del job son valores públicos de prueba, sin relación con cuentas de operación. Solo cuando falla el job se adjuntan el informe, trazas, capturas sintéticas y registros de los servicios, con retención de siete días. No se adjuntan la base SQLite ni los archivos de almacenamiento.

La configuración YAML y la sintaxis Bash de sus pasos se validaron localmente. El escenario ya pasó contra los servicios locales; la ejecución del nuevo job en GitHub Actions se verificará al subir el repositorio y ejecutar el workflow.

## Correcciones verificadas durante esta ejecución

- La tabla ahora solicita el resultado final al cambiar la versión del procesamiento; un lote rápido ya no puede finalizar dejando visible una tabla vacía almacenada en caché.
- El contenedor del visor mantiene su tamaño cuando se carga la hoja de estilos de MapLibre, de modo que los marcadores permanecen visibles.
- MapLibre 6 recibe un worker ESM local mediante `?worker&url` y `setWorkerUrl`, siguiendo su [integración oficial con Vite](https://maplibre.org/maplibre-gl-js/docs/#installation). Esto evita que el visor se monte con fondo vacío sin procesar el GeoJSON; el build emite un worker independiente con sus dependencias incluidas.
- Los textos accesibles de las cabeceras de tabla quedan dentro de su contenedor de desplazamiento; ya no generan ancho adicional en pantallas estrechas.
- Los selectores tienen nombres accesibles explícitos. El menú móvil oculto queda fuera del recorrido de teclado, y al abrirlo/restablecerlo se gestiona el foco y Escape.

## Límites de la comprobación

Las pruebas de componente verifican que MapLibre recibe polígonos y líneas reales, que no se crean marcadores para centroides de áreas y que los puntos conservan su marcador. También verifican el consentimiento explícito de reutilización, su reinicio entre registros y los tres estados del CRS al reprocesar (preservar, borrar o confirmar EPSG:4326). Estas pruebas usan dobles de MapLibre; el escenario de navegador descrito arriba complementa esta cobertura mediante renderizado WebGL real.

La ejecución local cubre Chromium con renderizado WebGL por software y el entorno SQLite. No acredita compatibilidad completa con todos los navegadores, dispositivos físicos o cartografía institucional. El mapa usa un estilo local sin cartografía base, tal como establece el MVP.
