# Organización de GeoPol según Propuesta 2

Referencia revisada: las siete diapositivas de la propuesta entregada el 25 de septiembre de 2026. Sus capturas ilustran distribución y jerarquía; las cifras, versiones, mapas y documentos de ejemplo no se incorporan como datos del sistema.

| Diapositiva | Interpretación e implementación |
| --- | --- |
| 1 · Vista 1A | Identidad institucional, presentación de la herramienta y resumen operativo. Los indicadores proceden del API de GeoPol. |
| 2 · Vista 1B | Temas claro y oscuro para todo el sistema, con elección persistente. Vista general incorpora una ilustración limpia del Perú adaptada a ambos temas. |
| 3 · Vista 1C | Vista general permite adjuntar el archivo principal SIDPOL y las cinco referencias de Censos. La ilustración se limita a su presentación; los formularios mantienen superficies legibles. |
| 4 · Validación | Comprobación del nombre con fecha, cabeceras, correspondencia de columnas y FLAG. Los avisos sobre nombre o ausencia de FLAG permiten mantener compatibilidad con archivos anteriores. La falta de datos/columnas necesarios bloquea el inicio. |
| 5 · Procedimientos | Expediente del procesamiento, progreso real y ocho procedimientos documentados. Se conserva la secuencia de ejecución disponible y se identifica qué controles están integrados en el motor. |
| 6 · Estadística | Resumen por procesamiento, mapa de geometrías aceptadas, distribución por UBIGEO, estados, detalle y exportación. Los totales incluyen todos los registros; el mapa identifica su muestra limitada. |
| 7 · Documentación | Biblioteca navegable con categorías, búsqueda y lectura de guías. Se retiraron la descarga Markdown y los pies técnicos de procedencia por indicación del usuario. |

## Cinco módulos

- **Vista general:** carga del Excel SIDPOL/PNP y las cinco referencias, resumen operativo e historial reciente.
- **Validación:** comprobaciones del archivo y configuración del mapeo y sistema de coordenadas.
- **Procedimientos:** ejecución, seguimiento, historial y revisión de excepciones.
- **Estadística:** resultados, distribución territorial, flags y exportaciones.
- **Documentación:** guías y metodología. Auditoría ya no aparece en la interfaz; sus registros internos se conservan.

Las rutas existentes se conservan; el antiguo enlace de auditoría redirige a Documentación. Cambiar entre Vista general y Validación dentro de la sesión mantiene el archivo y su configuración. Después de recargar la página se puede reanudar la carga seleccionando el mismo archivo, con la comprobación de identidad ya existente.

## Reglas de información

El flag de calidad es independiente del estado de revisión y de la precisión espacial. Un FLAG 1 o 2 en el archivo no demuestra que la ubicación sea correcta.

El **FLAG 10 de origen se conserva**. La asignación automática se limita a filas sin ningún dato utilizable de ubicación declarado, con una regla conservadora: un texto presente, un territorio declarado, una referencia parcial o coordenadas inválidas impiden tratar la fila como totalmente vacía. Una búsqueda sin coincidencias tampoco justifica el descarte. Las filas excluidas permanecen en resultados y exportaciones, con su motivo y procedencia; no pasan por la cola de revisión geográfica. Para incorporarlas se corrige el archivo y se importa una nueva versión.

El nombre recomendado es `DATACRIM_DDMMYYYY.xlsx`. Esta convención se valida con una fecha real y se comunica como observación para no impedir reutilizar los archivos existentes. La columna FLAG ausente no modifica el Excel original: el resultado incorpora la clasificación calculada.

Las estadísticas usan unidades de ubicación y muestran por separado las filas de origen. Los resultados históricos de etapas no se suman como si fueran ubicaciones distintas. Las fechas disponibles son del procesamiento, no del hecho delictivo; no se muestran tendencias trimestrales sin una serie que las respalde.

El mapa utiliza geometrías locales aceptadas. No consulta proveedores de cartografía externa ni representa como puerta exacta una geometría de área o tramo. Las guías describen la implementación actual y no se presentan como documentos oficiales aprobados.
