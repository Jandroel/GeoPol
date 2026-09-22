# Interfaz de GeoPol

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
