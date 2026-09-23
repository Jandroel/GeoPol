# Interfaz de GeoPol

Este documento es la referencia de diseño del proyecto. Todo cambio de UI/UX
sigue el orden acordado: **UX y sistema → jerarquía y espaciado → dirección visual
→ pulido final**. Las decisiones específicas del usuario prevalecen sobre las
preferencias estéticas generales de una skill.

## Contexto y dirección

GeoPol es una herramienta de operación institucional para cargar Excel de la
PNP/SIDPOL, contrastarlos con referencias geográficas, resolver ubicaciones con
evidencia y revisar las excepciones. Sus usuarios trabajan con miles de registros;
la interfaz debe facilitar la siguiente decisión y hacer visible el trabajo real.
La dirección es sobria, clara y orientada a datos, con identidad INEI.

La prioridad de una pantalla de procesamiento es: archivo y etapa activos,
avance de la operación, resolución geográfica y siguiente acción, distribuciones
por etapa, y resultados/exportaciones. Procesar una ubicación no significa
verificarla. El flag de calidad, el estado de revisión y la precisión geográfica
siguen siendo conceptos independientes.

## Bases consultadas

Revisión de repositorios: 23 de septiembre de 2026. Se consultan como guías de
diseño; sus ejemplos no sustituyen la identidad ni las reglas de GeoPol.

| Referencia | Aplicación en este proyecto |
| ---------- | -------------------------- |
| [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/ui-ux-pro-max/SKILL.md) | UX, accesibilidad, estados, selección de patrones adecuados y revisión responsive. |
| [Refactoring UI](https://github.com/jaywilburn/refactoring-ui-skill/blob/main/skills/refactoring-ui/SKILL.md) | Jerarquía mediante tamaño, peso, contraste y proximidad; densidad apropiada para trabajo operativo. Es una adaptación comunitaria. |
| [Frontend Design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | Dirección visual basada en el uso real, lenguaje específico, una prioridad visual clara y eliminación de adornos repetitivos. |
| [Impeccable](https://github.com/pbakaus/impeccable/blob/e0881d2de397d5e9761d7b35ff5017d8f5ebf69b/skill/SKILL.src.md) | Revisión de consistencia, tipografía, interacción, adaptación y pulido; su modo operativo prioriza completar tareas. |

Impeccable reorganizó su antigua skill `frontend-design`. También se revisaron sus
referencias de [tipografía](https://github.com/pbakaus/impeccable/blob/209444a9d552c18bcaa74e26bf66a25fc568a767/source/skills/frontend-design/reference/typography.md),
[espacio](https://github.com/pbakaus/impeccable/blob/209444a9d552c18bcaa74e26bf66a25fc568a767/source/skills/frontend-design/reference/spatial-design.md)
e [interacción](https://github.com/pbakaus/impeccable/blob/209444a9d552c18bcaa74e26bf66a25fc568a767/source/skills/frontend-design/reference/interaction-design.md)
en esa revisión identificable. No es necesario incorporar sus instaladores o
ejecutables al funcionamiento de la aplicación.

## Sistema y criterios de implementación

- Reutilizar componentes y tokens antes de crear variantes. `src/styles.css`
  contiene la paleta; las hojas de cada componente acotan sus reglas visuales.
- Mantener Segoe UI como familia principal por legibilidad y disponibilidad en
  el entorno Windows de operación, con fallbacks locales. Una nueva familia
  debe resolver una necesidad concreta; no se añaden solicitudes de fuentes remotas.
- Usar 14–16 px para lectura e interacción habitual; 12–13 px para contexto
  secundario, sin microtexto decorativo. Títulos con pesos 600–700 y cifras
  tabulares para cantidades y duración. Evitar mayúsculas espaciadas en etiquetas.
- Agrupar con una escala de 4, 8, 12, 16, 24 y 32 px. La distancia entre secciones
  debe ser mayor que entre elementos relacionados. Excepciones ópticas pequeñas
  son válidas cuando mejoran el resultado, no constituyen nuevas escalas.
- Usar contenedores cuando hay una tarea o conjunto de datos independiente.
  Evitar paneles anidados, sombras y degradados sin función. Reservar el mayor
  contraste para el trabajo activo y las acciones que lo requieren.
- Mantener el blanco pedido por el usuario y los azules INEI aunque una guía
  sugiera otra paleta. Verde comunica resolución; ámbar, atención; rojo, fallo.
  El color siempre lleva texto o una señal adicional.
- Adaptar grupos y columnas al ancho disponible. Las tablas pueden desplazarse
  dentro de su contenedor; la página completa no debe desbordarse. No ocultar
  acciones esenciales para lograr el ajuste.

## Interacción y movimiento

- Las distribuciones por etapa se presentan como pasteles 2D rellenos, según la
  referencia visual aportada por el usuario. Las porciones conservan su proporción
  real; las etiquetas internas solo aparecen cuando caben. Las categorías pequeñas
  permanecen disponibles en la leyenda y el detalle de selección. Una etapa vacía
  muestra «Sin datos»; una única categoría puede ocupar el círculo completo.
- El foco, hover o selección resalta una porción, atenúa las demás y muestra
  cantidad y porcentaje. El desplazamiento es breve y no modifica el área de
  interacción, para evitar parpadeos. El total de ubicaciones permanece debajo.
- Las gráficas permiten explorar categorías con mouse, teclado y controles
  táctiles. La leyenda conserva las cantidades y porcentajes legibles. Explorar
  un gráfico histórico no cambia silenciosamente filtros ni exportaciones.
- El menú lateral se puede contraer; las etiquetas siguen disponibles. En móvil
  se abre como panel con foco contenido, cierre mediante Escape, retorno del foco
  y fondo fuera del recorrido del teclado. Los controles conservan al menos 44 px.
- Diseñar reposo, foco, hover, carga, error y finalización. Los mensajes indican
  qué ocurre y cuál es el siguiente paso; no repetir instrucciones en varias zonas.
- Animar cambios de estado y respuestas a acciones con transiciones breves de
  opacidad o transformación. No animar cifras inventadas ni mover continuamente
  gráficos ya finalizados. Respetar `prefers-reduced-motion`.
- El cronómetro usa tiempos registrados por operación. Un histórico sin ese dato
  muestra «Tiempo no disponible». La barra indica ubicaciones evaluadas en la
  etapa actual, y el avance por calidad indica ubicaciones resueltas: no se mezclan.
- Confirmar guardados y decisiones geográficas con la respuesta del servidor;
  no mostrar una verificación exitosa de forma optimista.

## Flujo de revisión

1. Definir tarea, contenido, estados y siguiente acción antes de cambiar estilos.
2. Revisar jerarquía y agrupación; quitar duplicados y etiquetas innecesarias.
3. Aplicar la dirección institucional y los componentes existentes.
4. Inspeccionar escritorio y móvil, teclado, contraste, etiquetas largas, vacíos,
   errores y movimiento reducido. Corregir los defectos observados en conjunto.
5. Confirmar con pruebas apropiadas y una segunda revisión visual acotada.
   Registrar alcance y límites en `QA.md`; no extender el pulido indefinidamente.

La revisión del 23 de septiembre aplica estos criterios al panel de actividad,
avance por calidad, gráficas y navegación. No acredita una auditoría completa de
todas las pantallas anteriores.

## Referencia de color

La referencia principal es el logotipo del INEI aportado por el usuario el
22 de septiembre de 2026, junto con su indicación de usar azul oscuro, celeste y
blanco. Los valores se obtuvieron de los píxeles predominantes de la imagen;
son una aproximación de esa referencia, no un manual de identidad certificado.

| Color observado       | Aplicación en GeoPol                                               |
| --------------------- | ------------------------------------------------------------------ |
| Azul oscuro `#12426B` | Navegación, acciones principales, enlaces y geometría seleccionada |
| Celeste `#008FD3`     | Marca, acentos decorativos e indicador de navegación activa        |
| Blanco `#FFFFFF`      | Formularios, tablas y paneles                                      |

Los tokens de `src/styles.css` concentran la paleta. Los tonos de texto, bordes,
fondos y estados son ajustes propios para legibilidad. Se derivan un azul secundario
`#076B99`, superficies `#E8F4FB` y un celeste claro `#77D2F5` para el foco sobre azul
oscuro. El celeste original no se usa como fondo de texto blanco pequeño: se reserva
el azul oscuro para ese fin. Verde, ámbar y rojo conservan sus significados de estado,
siempre acompañados por etiquetas. El visor obtiene sus colores de los mismos tokens.

El contraste calculado de blanco sobre azul principal es 10,41:1. El texto secundario
`#526779` sobre las superficies claras alcanza al menos 5,25:1, y el foco celeste claro
sobre azul principal alcanza 6,11:1.

## Jerarquía y contenido

- La carga inicial reúne el archivo PNP y las cinco fuentes en dos columnas.
  Las fuentes usan filas compactas con estado y un único editor desplegado;
  los formularios permanecen montados al ocultarlos para conservar borradores,
  mapeos e importaciones. Una selección no equivale a disponibilidad geográfica.
  Si se prepara un reemplazo, se conserva visible la fuente que se utilizará.
  En móvil, los bloques se apilan y el estado pasa debajo del nombre.
- Resultados presenta el total junto a sus filtros, calculado por el servidor
  para la búsqueda aplicada y su resolución/flag/etapa. La etiqueta distingue
  el total general del total filtrado; el rango indica las ubicaciones visibles
  de esa página, sin confundirlas con las filas originales del Excel.
- Una cabecera identifica cada pantalla. La barra superior conserva la cuenta y
  el control del menú móvil; la barra lateral concentra la navegación.
- El resumen muestra indicadores distintos, su distribución y los procesamientos
  recientes. Se evita repetir el total en el centro del gráfico y duplicar llamadas
  a la bandeja en paneles adicionales.
- Las reglas generales se consultan en Reglas y metodología. Los requisitos que
  afectan una decisión, como CRS, ausencia de referencias o precisión de área,
  permanecen junto a la acción correspondiente.
- Los esquemas de catálogo y el detalle de la exportación se despliegan a petición.
  Reprocesar tiene una única entrada; la configuración conserva sus datos técnicos.
- El acceso presenta un formulario y una descripción breve del propósito del sistema.

Se mantienen el recorrido por teclado, el foco visible, las etiquetas accesibles,
los estados textuales y las tablas con desplazamiento local en pantallas estrechas.
No se añaden fuentes remotas, recursos de marca externos ni cartografía base.

Las verificaciones de funcionamiento y sus límites se registran en [QA.md](QA.md).
