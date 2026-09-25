# Verificación de la interfaz

La interfaz se verificó con Chromium real mediante Playwright, una API FastAPI local y su trabajador activos, sobre una base SQLite temporal aislada y exclusivamente datos sintéticos.

## Portada abierta y adjunto directo · 25 de septiembre de 2026

Título e ilustración del Perú se presentan sobre el fondo, sin marco exterior.
SIDPOL y referencias son dos secciones de una sola superficie. Los botones verdes
abren el selector nativo; al elegir una referencia se abre su configuración.
La navegación conserva azul INEI en claro y azul profundo en oscuro.

- **49 pruebas de componente verificadas**: navegación/tema (22) y
  automatización/referencias/diálogo (27). Después de los últimos ajustes se
  repitieron las cuatro pruebas del diálogo y el recorrido de reemplazo PNP.
  Se comprueban cancelación del selector, un único input por referencia,
  conservación de borradores/catálogos activos, reutilización sin subir Excel,
  foco y carga en curso con el editor cerrado. El recorrido PNP ampliado conserva
  nombre y mapeo al cancelar, y los renueva al elegir y cargar otro archivo;
  tiene un límite local de 10 s por sus dos idas y vueltas, sin cambiar los demás.
- **Tres escenarios Chromium aprobados contra producción**: cinco módulos,
  actividad/gráficas/navegación y cinco referencias Excel con avance y exportación
  por etapa. El acceso directo se verifica esperando el selector real, comprobando
  que aún no hay diálogo y eligiendo el archivo antes de configurar. Tras alinear
  las acciones se repitió el escenario de módulos completo: aprobado en 27,7 s.
- Sin scroll vertical en la portada a **1366 × 768, 1440 × 900 y 1920 × 1080**,
  vacía, con referencias guardadas y archivo cargado. También se comprueban anchos
  intermedios de 800/1024 px y móvil de 400 px, sin desbordamiento horizontal.
  Se inspeccionaron ambos temas, las ventanas de configuración y el menú móvil.
- Revisión independiente sin defectos importantes adicionales. Se corrigieron
  la altura inicial de la portada, la herencia vertical del botón PNP y la
  alineación de acciones entre filas con y sin catálogo guardado. El cálculo de
  contraste del menú arroja texto mínimo 6,52:1 e iconos mínimo 3,58:1, incluyendo
  selección y hover. Las acciones conservan objetivos de al menos 44 px.
- TypeScript/Vite y formato correctos; continúa el aviso conocido de tamaño de
  MapLibre. Sin cambios de backend, dependencias ni datos operativos.

Un intento del escenario legado de calidad mostró «En cola» durante la espera
de 20 s aunque la API ya devolvía la cuadra resuelta. La repetición completa pasó
sin cambiar el motor; la causa no quedó confirmada en esta revisión.
Las pruebas usan 18001/15175 y datos sintéticos temporales, limpiados al finalizar.
Capturas privadas: `.local/ui-open-overview-20260925/`, excluidas de Git.

## Portada de importación y último procesamiento · 25 de septiembre de 2026

Vista general reúne el archivo SIDPOL y las cinco referencias dentro del panel
del Perú. Se retiran sus métricas y procesamientos recientes. Cada referencia
abre una ventana con desplazamiento interno y conserva su archivo y borrador al
cerrarse. La cabecera es más compacta y los iconos identifican módulos y fuentes
sin recuadros decorativos.

- **65 pruebas de componente aprobadas** en ejecuciones acotadas: selección del
  último procesamiento y estadísticas (17), automatización/referencias/diálogo
  (26), navegación y temas (22). Cubren selección explícita de un histórico,
  lista en caché, ausencia de procesamientos, error y reintento, Escape, retorno
  de foco, borradores y conservación del archivo entre portada y validación.
- **Dos escenarios Chromium aprobados en 48,3 s**, con el build de producción.
  Comprueban la selección del último procesamiento al entrar en Procedimientos
  y Estadística, además de importación, validación, procesamiento, exportación,
  mapas, actividad, gráficas y navegación.
- La portada se comprueba **sin desplazamiento vertical** a 1366 × 768,
  1440 × 900 y 1920 × 1080, vacía, con referencias guardadas y con archivo cargado.
  Se inspeccionaron capturas claras/oscuras de escritorio y móvil (400 × 900),
  junto con la configuración de una referencia en una ventana de altura limitada.
  Las pantallas pequeñas pueden desplazarse para mantener accesibles las acciones.
- La revisión visual adicional confirmó títulos próximos a la cabecera e iconos
  legibles. Se conservó visible el catálogo activo durante un reemplazo pendiente
  y se mantuvo el apilado de la carga a partir de 1000 px. Los escenarios no
  detectaron errores de página, desbordamiento horizontal ni solicitudes externas.
- TypeScript/Vite y comprobación del diff correctos; permanece el aviso conocido
  del tamaño de MapLibre. No se modificaron backend ni datos operativos. La web
  en 5174 sirve el build actualizado y su API responde saludable, con esquema 6.

Las pruebas usaron servicios aislados en 18001/15175 y datos sintéticos temporales,
limpiados al finalizar. Evidencias privadas: `.local/ui-intake-20260925/`, fuera de
Git. JSDOM usa un adaptador mínimo del ciclo de vida de `dialog`; la interacción
nativa, Escape y restauración del foco también se verifican en Chromium.

## Refactoring UI, navegación y biblioteca · 25 de septiembre de 2026

Se retiraron la ruta superior repetida y el enlace de ejemplo sintético. La barra
lateral adopta la superficie del tema y cinco acentos de módulo. Documentación
usa categorías horizontales, catálogo compacto y un lector con mayor prioridad;
en móvil, seleccionar una guía pliega el catálogo y lleva el foco al artículo.

- **17 pruebas de navegación aprobadas**, conservando rutas activas, enlaces
  locales, preferencia del menú, foco, Escape y cambios de breakpoint.
- **Dos escenarios Chromium aprobados en 24,7 s**, contra el build de producción.
  Se comprueban ausencia del breadcrumb y del ejemplo, búsqueda y limpieza,
  filtro de ocho procedimientos, selección de guías en ambos temas, cierre y
  reapertura del catálogo móvil y foco del lector. También pasan importación,
  procesamiento, estadísticas, mapas, exportación Excel y gráficas existentes.
- Capturas inspeccionadas de Documentación en claro y oscuro, catálogo y lector
  móvil, además de barra lateral expandida, compacta y móvil. La comprobación
  incluye escritorio 1440 px, 1280/1024/768 px y móvil 400/375 px, sin errores de
  página ni desbordamiento global. El escenario de módulos no solicita recursos
  externos.
- Se corrigió la herencia antigua que aclaraba demasiado los iconos inactivos.
  Los diez pares de icono/fondo de módulo tienen contraste entre 4,62:1 y 7,06:1.
  La selección conserva texto, fondo y un indicador lateral.
- Build TypeScript/Vite, formato y diff correctos. Permanece el aviso conocido
  del tamaño de MapLibre. No se cambiaron backend ni datos operativos.

Los servicios y archivos de prueba son sintéticos, aislados en 18001/15175 y
eliminados al finalizar. Las capturas privadas se conservan en
`.local/ui-library-20260925/`, excluidas de Git. La web operativa en 5174 sirve la
versión nueva y su API continúa saludable.

## Identidad y cabecera lateral · 25 de septiembre de 2026

La marca con icono de ubicación y subtítulo INEI se trasladó desde Vista general
a la barra lateral. El control de contraer/expandir está junto a la marca, con
nombre accesible y área de 44 px; se retiró el botón del pie. Se ajustó el
encuadre del Perú al reducir la altura de la cabecera de Vista general.

- **17 pruebas de navegación aprobadas**, incluidas preferencia persistente,
  foco, Escape, cambio de breakpoint y acceso a los cinco módulos.
- **Dos escenarios Chromium aprobados contra producción en 21,7 s**: módulos en
  ambos temas y actividad/gráficas/navegación. Incluyen escritorio de 1440 px,
  anchos intermedios 1280/1024/768 px y móvil de 400/375 px, sin desbordamientos
  globales ni errores de página.
- Capturas inspeccionadas de la barra expandida en claro y oscuro, contraída y
  abierta en móvil. La marca ya no se repite dentro de Vista general. Las
  evidencias sintéticas están en `.local/ui-sidebar-20260925/`, fuera de Git.
- TypeScript/Vite, formato y diff correctos. La web 5174 sirve el build nuevo y
  su API responde saludable. Las pruebas usaron servicios y datos aislados que
  se cerraron y limpiaron al finalizar; no se modificó el backend ni la base real.

## Temas y refinamiento visual · 25 de septiembre de 2026

- **106 pruebas de componente aprobadas** en una ejecución serial completa.
  Incluyen preferencia del sistema, elección persistente del tema, sincronización
  entre pestañas y almacenamiento no disponible.
- TypeScript/Vite, formato y comprobación del diff correctos. Permanece únicamente
  el aviso conocido de tamaño del paquete MapLibre.
- El escenario Chromium de los cinco módulos pasó contra producción en **24,9 s**:
  temas claro/oscuro, recarga y persistencia, importación, FLAG 10, exportación Excel,
  mapas reales y navegación móvil. Comprueba la ausencia de auditoría y descarga
  Markdown, la redirección de enlaces antiguos y la imagen solo en Vista general.
- **Tres escenarios adicionales aprobados en 45,5 s**: geometrías y reutilización,
  actividad/gráficas/menú, y cinco referencias Excel con avance y exportación por
  etapa. Las pruebas mantienen las comprobaciones de datos y resultados existentes.
- Se inspeccionaron capturas de acceso, Vista general, Validación, Procedimientos,
  Estadística, Documentación y ficha de resultado, con variantes claras/oscuras en
  escritorio y móvil. Las comprobaciones cubren 1440 × 1000 y 400 × 900 px, sin
  errores de página, solicitudes externas ni desbordamiento global. Los mapas
  actualizan sus colores al cambiar el tema conservando geometría y encuadre.
- Estadística usa más colores para distinguir métricas y categorías, conservando
  etiquetas y cantidades. Procedimientos muestra pasos, estados y tiempos reales.
  La ilustración decorativa del Perú mantiene su canal transparente y se sirve
  localmente; su procedencia está en [visual-assets.md](../docs/visual-assets.md).

Las pruebas que escriben datos usaron servicios aislados en 18001/15175 y una base
temporal sintética; los procesos y datos temporales se limpiaron al finalizar.
Las capturas están en `.local/ui-themes-20260925/`, excluidas de Git. No hubo cambios
de backend ni de datos operativos. La web en 5174 sirve el build actualizado y el
PNG; tanto su proxy como la API en 8002 responden con estado saludable y esquema 6.

## Cinco módulos y validación de origen · 25 de septiembre de 2026

Se revisaron visualmente las siete láminas de Propuesta 2 y se reorganizó la
navegación en Vista general, Validación, Procedimientos, Estadística y
Documentación. El alcance y las diferencias justificadas están registrados en
[propuesta-2.md](../docs/propuesta-2.md).

- Backend: **664 pruebas aprobadas y una omitida** en la suite completa. Después
  de las salvaguardas finales, **128 pruebas relevantes aprobadas**. PostgreSQL
  no estaba configurado; la comprobación local utiliza SQLite.
- Frontend: **100 pruebas de componente verificadas**. La ejecución serial
  aprobó 99; la prueba restante agotó el tiempo al escribir textos largos. Tras
  usar pegado de texto, las 13 pruebas de su archivo pasaron con las mismas
  aserciones. La ejecución paralela anterior también sufrió límites de tiempo;
  no se modificaron esos límites ni se relajaron comprobaciones.
- Chromium: los seis escenarios existentes pasaron contra el build de producción.
  El nuevo escenario de los cinco módulos pasó después de corregir dos selectores
  del test; su última ejecución duró **17 s**. Verifica carga y navegación sin
  pérdida de contexto, FLAG 10 declarado/automático, conteos, filtros, Excel de
  seis filas, descarga de Markdown y menú móvil. Los píxeles del punto se
  comprueban en el mapa real de escritorio y móvil, también al reactivar su capa.
  Sin errores de página, solicitudes externas ni desbordamiento global a 400 px.
- Se inspeccionaron las capturas de los cinco módulos, mapa y menú móvil. Los
  controles de capas usan filas compactas y el visor muestra una espera accesible
  hasta terminar de dibujar. TypeScript/Vite y formato correctos; permanece el
  aviso conocido de tamaño del paquete MapLibre.
- Los borradores del Excel principal y de las cinco referencias se conservan al
  navegar, incluso si una carga o guardado finaliza fuera de la pantalla. Cambiar
  el documento limpia la confirmación de CRS y los metadatos propios del anterior.
- FLAG 10 de origen y FLAG 10 automático se distinguen. Solo los campos de
  ubicación literalmente vacíos habilitan la asignación automática. Texto
  parcial, datos territoriales o coordenadas inválidas impiden ese descarte.
  Las exclusiones se conservan en resultados y exportaciones y no admiten una
  decisión de revisión geográfica.

La web operativa en 5174 y la API en 8002 responden con el build y las rutas nuevas.
Se reiniciaron únicamente sus procesos registrados, sin trabajos en curso y
conservando la base y el almacenamiento. Las pruebas de escritura usaron API
18001, frontend 15175 y una base temporal sintética; sus procesos se cerraron.

Las capturas sintéticas se conservan de forma privada en
`.local/ui-propuesta-20260925/`, excluidas de Git. El mapa utiliza geometrías
aceptadas locales y un fondo neutro; no se acredita cobertura de cartografía base
institucional ni se inventan puntos para representar áreas o tramos.

## Editor de referencias simplificado · 24 de septiembre de 2026

Se retiraron los títulos, etiquetas visibles y explicaciones repetidos. El selector
de catálogo aparece solo cuando existen opciones; el adjunto verde permanece
visible con una sola apertura. La acción de leer columnas aparece después de
elegir el archivo. El aviso de reanudación se integra en el selector de Excel.

**18 pruebas de componente aprobadas**, compilación TypeScript/Vite, formato y
diff correctos. El escenario Chromium de los cinco Excel pasó en **31,4 s**,
incluidas importación, procesamiento y exportación. Se inspeccionaron capturas
de escritorio y móvil a 400 px, con nombre largo y catálogo guardado: foco visible,
etiqueta/selector apilados en móvil y sin desbordamiento horizontal de la página.
Se mantienen los controles de coordenadas, los borradores y la identificación del
catálogo activo tras un fallo. La web operativa 5174 responde con el build nuevo.

## Referencias con un solo desplegable · 24 de septiembre de 2026

Abrir cada tipo de referencia muestra directamente «Adjuntar Excel». La lista
se identifica como «Catálogo guardado» y la procedencia como «Origen de los datos /
institución». La ayuda diferencia reutilizar datos guardados de importar otro
archivo; cuando no hay catálogos, la lista está deshabilitada y se explica el motivo.

**18 pruebas de componente aprobadas**, compilación TypeScript/Vite, formato y
diff correctos. El escenario Chromium de cinco referencias pasó en **34,5 s**,
comprobando el botón tras una única apertura, selección con teclado, importación
y exportación. Se inspeccionaron las capturas de escritorio y móvil con nombre
largo, sin desbordamiento horizontal. Se conservan los borradores, el catálogo
activo y los controles de coordenadas. La web local sirve el build actualizado.

## Selector de Excel destacado · 24 de septiembre de 2026

Los cinco selectores de referencia usan un botón verde con icono de hoja de
cálculo y nombre/tamaño del archivo separado. Se conserva el input nativo,
su etiqueta, la restricción `.xlsx`, la validación y el bloqueo durante carga.

- **10 pruebas de componente aprobadas**, TypeScript/Vite, formato y diff correctos.
- **Escenario Chromium de cinco Excel aprobado en 33,5 s**: apertura del selector
  nativo con Enter, archivo con nombre largo, importación, procesamiento y exportación.
- Capturas inspeccionadas en escritorio y a 400 px: foco visible y nombre completo
  con salto de línea, sin desplazamiento horizontal global. El blanco sobre el
  botón verde alcanza contraste 5,27:1 (7,68:1 en hover).
- El escenario usó datos sintéticos y servicios aislados en 18001/15175. Las
  capturas privadas `ui-excel-attach.png` y `ui-excel-attach-mobile.png` quedan en
  `.local/ui-polish-20260923/`, fuera de Git. La web operativa 5174 sirve el build
  actualizado; no se modificaron datos ni lógica del backend.

## Carga compacta y totales de resultados · 23 de septiembre de 2026

- La carga inicial muestra los cinco tipos de referencia sin desplazar la página
  a 1440 × 1000 px. Se inspeccionaron también la carga y los resultados a
  400 × 900 px, sin desbordamiento horizontal global. Las tablas mantienen su
  desplazamiento local.
- El acordeón permite apertura con teclado y conserva archivo, versión y mapeo
  al cambiar de fuente. Se comprobaron errores de importación con el editor
  cerrado y la identificación del catálogo activo mientras existe un borrador.
  La selección no confirma CRS ni habilita geometrías pendientes.
- El contador usa el total del API, no los 25 elementos de una página. Se
  verificaron búsqueda aplicada frente a texto sin enviar, resolución, filtros
  de calidad, carga, error, total cero y ajuste de página cuando disminuye el
  total. El navegador confirmó cinco ubicaciones totales y dos automáticas en
  la fixture, junto con el rango visible.
- Vitest: suite completa de **81 pruebas aprobadas** con dos workers; después,
  **15 pruebas focalizadas aprobadas**, incluida una nueva para el fallo de
  importación en segundo plano. Son 82 casos distintos verificados. La primera
  ejecución con paralelismo predeterminado agotó los 5 s de una prueba de
  interacción; la ejecución con dos workers pasó sin ampliar ese límite.
- Los **seis escenarios de Chromium** quedaron aprobados: cinco en la ejecución
  completa y el flujo de cinco Excel en la comprobación focalizada final
  (29,9 s). Esta última espera explícitamente que termine el cambio de pestaña
  antes de filtrar, porque Calidad y Resultados contienen tablas independientes.
  Verifica importación real, conservación de puertas resueltas y exportación.
- TypeScript/Vite, formato y `git diff --check` correctos. Se comprobó que
  `127.0.0.1:5174` sirve el build actualizado. No hubo cambios de backend.

Los escenarios que escriben usaron exclusivamente el entorno sintético aislado
18001/15175 y cerraron sus procesos al terminar. Las capturas inspeccionadas
(`ui-quality-upload`, `ui-upload-mobile`, `ui-results-filtered` y
`ui-results-mobile`) permanecen en `.local/ui-polish-20260923/`, fuera de Git.

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

El cuarto escenario, `e2e/automation.spec.ts`, configura una referencia base e importa
tres direcciones sintéticas sin confirmar el CRS de entrada. Comprueba una aceptación
automática contra el catálogo y dos casos equivalentes de revisión. Exige candidato,
motivo y confirmación del alcance antes de aplicar; después verifica el identificador
de grupo compartido, la revisión manual de cada ubicación y la conservación exacta de
la revisión automática anterior. Incluye contexto local en WebGL y vista móvil a 400 px.

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

### Gráficas de pastel · 23 de septiembre de 2026

- Los gráficos por etapa usan porciones rellenas con porcentajes internos cuando
  hay espacio, resaltado, separación visual y detalle flotante. Las áreas de
  interacción permanecen quietas para que el hover no parpadee.
- **16 pruebas de componentes y filtros aprobadas**: círculo del 100 %, minoría
  de 3/1351 (0,2 %), etapa vacía, total estable, selección con SVG/leyenda,
  interacción táctil y teclado, Escape y conservación de filtros/exportaciones.
- La suite completa de interfaz terminó con **76 pruebas aprobadas**. Incluye la
  corrección del foco del menú móvil tras cambios de ancho: visibilidad inmediata
  y foco cuando el control realmente está visible y fuera de `inert`, sin depender
  de un número fijo de frames. Una ejecución simultánea con Chromium agotó el
  tiempo de dos tests; la repetición completa sin esa concurrencia pasó en 25,66 s.
- **Tres escenarios Chromium afectados aprobados** en 35,1 s, con datos sintéticos
  y base aislada: interacción del pastel, procesamiento/revisión/exportación y
  navegación de escritorio/móvil. Capturas inspeccionadas a 1440 y 375 px; también
  se comprobó ausencia de desbordamiento global a 1280, 1024 y 768 px.
  Evidencia privada en `.local/ui-polish-20260923/`, incluyendo `ui-pie-mobile.png`.
- TypeScript, formato y build de producción aprobados. No se añadieron
  dependencias ni se modificaron reglas de resolución o datos de operación.

### Actividad, gráficas y navegación · 23 de septiembre de 2026

- Suite general de backend: **644 pruebas aprobadas y una omitida**. Tras el
  ajuste final del total por etapa, **21 pruebas de actividad y calidad aprobadas**.
  El contador incluye ubicaciones que vuelven a ser elegibles al liberar reservas.
- Suite de interfaz: **72 pruebas aprobadas**. Después del pulido visual final,
  **30 pruebas de los cuatro módulos afectados aprobadas**. Formato, TypeScript y
  build de producción correctos; continúa el aviso conocido de tamaño de MapLibre.
- **Seis escenarios Chromium aprobados** contra API/base/almacenamiento sintéticos
  aislados. Cubren importación, procesamiento, referencias, revisión, exportación,
  mapas, actividad por operación, gráficas interactivas y navegación móvil.
- El escenario visual distingue 12 de 40 ubicaciones evaluadas en la operación
  actual del contador acumulado de 100. Comprueba que el reloj avance, que explorar
  una categoría no altere filtros y que el menú restaure el foco al cerrar.
- Comprobaciones responsive a 1440, 1280, 1024, 768 y 375 px, además del flujo
  de calidad a 400 px. Sin desbordamiento global en las vistas comprobadas.
  Se inspeccionaron capturas de actividad, gráficas y menú móvil. El escenario usa
  movimiento reducido; las pruebas de componente verifican sus clases de estado.
- Contraste calculado sobre el azul de actividad: texto blanco 10,41:1, contexto
  8,37:1 y grupos del menú 6,86:1. La leyenda oscura sobre blanco alcanza 11,18:1.
- El despliegue local respondió en 8000/5174, sirvió el build actualizado y permitió
  consultar los tres procesamientos existentes. Se creó un respaldo privado;
  la comparación de 11 tablas confirmó que los datos originales se conservaron.

No cambió el esquema de base de datos (versión 6). Los tiempos históricos sin
registro de etapa permanecen desconocidos; los tiempos nuevos se guardan por
operación. Evidencias y respaldo en `.local/ui-polish-20260923/`, excluidos de Git.
La revisión aplica las cuatro bases de diseño registradas en [DESIGN.md](DESIGN.md)
a los componentes modificados; no constituye una certificación de accesibilidad
ni una auditoría de toda la aplicación.

### Referencia base y automatización segura · 22 de septiembre de 2026

- **448 pruebas de backend aprobadas y una omitida**, con SQLite. La prueba de
  integración PostgreSQL requiere su servicio; no se acredita aquí su ejecución.
- **35 pruebas Vitest aprobadas**, formato y build TypeScript/Vite correctos.
- **Cuatro escenarios Chromium aprobados contra el build de producción en 38,7 s**,
  con API 18001, frontend 15175, esquema 4 y datos exclusivamente sintéticos.
- La comprobación del despliegue local verificó migración, catálogo predeterminado,
  CRS sin confirmar, contadores reales, diagnóstico, inicio de carga y mapas de
  punto y tramo. Escritorio y móvil sin desbordamiento, errores del navegador,
  peticiones externas ni escrituras ajenas a su propia sesión.
- Se inspeccionaron las capturas de configuración, diagnóstico, vista previa de
  equivalentes y mapas. El visor distingue contexto y resultado; las coordenadas
  originales sin CRS documentado se conservan en ficha y no se dibujan.

La evidencia privada está en `.local/automation-20260922/`, fuera de Git. El ajuste
visual final de Referencias conserva los metadatos completos en una sola tarjeta y
reduce la configuración base a su nombre y acción, evitando repetir información.

### Interfaz INEI y reducción de contenido repetido · 22 de septiembre de 2026

La paleta final usa el logotipo aportado por el usuario: azul oscuro, celeste y
blanco. La procedencia, los tonos derivados y los criterios de jerarquía están
documentados en [DESIGN.md](DESIGN.md).

- **26 pruebas Vitest aprobadas**, formato y build TypeScript/Vite correctos.
- **340 pruebas de backend aprobadas y una omitida**. No se cambió lógica de backend.
- **Tres escenarios Chromium aprobados contra el build de producción en 32,1 s**:
  importación, procesamiento, revisión, exportación, reutilización y revocación,
  geometrías reales en WebGL y navegación móvil. Se actualizó la comprobación de
  píxeles al azul oscuro de la referencia final.
- Comprobación adicional del despliegue local en escritorio (1440 × 1000) y móvil
  (400 × 900): acceso, resumen, carga inicial, procesamientos, referencias, revisión,
  reglas y menú. Sin excepciones del navegador, errores de consola, peticiones a
  otros orígenes ni desplazamiento horizontal global en las pantallas comprobadas.
- Se verificaron el foco visible y la apertura/cierre del menú mediante teclado.
  Las capturas se inspeccionaron tras finalizar las transiciones de la interfaz.

Los escenarios que escriben datos usaron API 18001, frontend 15175, credenciales y
base sintéticas aisladas. Sus procesos se cerraron al terminar. La comprobación del
despliegue 5174 solo leyó datos y abrió/cerró su propia sesión; no importó archivos
ni creó procesamientos o catálogos. Las capturas y el informe privado están en
`.local/inei-ui/` y quedan excluidos de Git. El aviso conocido de tamaño del paquete
MapLibre no impide el build; no se modificó su dependencia.

### Verificaciones anteriores

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

La ejecución local cubre Chromium con renderizado WebGL por software y el entorno SQLite. No acredita compatibilidad completa con todos los navegadores, dispositivos físicos o cartografía institucional. El mapa usa un estilo local y el contexto de líneas y polígonos del catálogo seleccionado; no consulta una cartografía base externa.
