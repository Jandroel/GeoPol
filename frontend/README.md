# GeoPol · Espacio de trabajo

Interfaz React y TypeScript conectada a la API mediante `/api`. No contiene datos institucionales, cuentas predeterminadas ni resultados simulados.

## Desarrollo

Requiere Node.js 24 o posterior y la API iniciada en `http://127.0.0.1:8000`.

```powershell
npm ci
npm run dev
```

Vite sirve la aplicación en `http://127.0.0.1:5173` y redirige `/api` a FastAPI. La cuenta se crea mediante la CLI del backend; consultar el README raíz. En despliegue, usar HTTPS para proteger las sesiones y habilitar Web Crypto fuera de localhost.

## Estructura

- `src/pages`: flujos de operación, composición de consultas y formularios.
- `src/components`: interfaz reutilizable y visor espacial.
- `src/lib`: cliente HTTP, sesión, carga reanudable y presentación de valores.
- `src/types.ts`: contrato tipado de respuestas.
- `src/auth.tsx`: límite de autenticación y limpieza de caché al cambiar la sesión.
- `src/test`: pruebas de integración de revisión, autenticación y reanudación.
- `public`: archivos sintéticos optativos y configuración de fuentes locales.

## Verificación

```powershell
npm run test
npm run build
npm run format:check
```

Las pruebas verifican interrupción y reanudación de una carga, separación entre usuarios, límite de bloques, autenticación expirada, conflictos de revisión, conservación de candidatos, filtros de bandeja, selección explícita de referencia al reprocesar y el reinicio del formulario al guardar y avanzar. `build` comprueba tipos y produce `dist/`. El visor MapLibre se carga de forma diferida; su dependencia genera un aviso de tamaño de Vite, sin afectar la compilación.

La prueba integrada en Chromium se ejecuta con `npm run test:e2e` contra un entorno local aislado. Configuración, alcance y evidencias se describen en [QA.md](QA.md).

## Operación y privacidad

El token se mantiene en `sessionStorage` y las consultas no se persisten. `localStorage` conserva exclusivamente los metadatos de la carga pendiente (identificador, usuario, nombre, tamaño y huella) y los identificadores de exportación por usuario/lote. Para reanudar una carga se selecciona otra vez el mismo archivo; se verifica su contenido completo mediante hashes de bloques, sin cargar el archivo entero en memoria. La huella local identifica la reselección; el SHA-256 oficial del archivo lo calcula el servidor.

Una vez creado el procesamiento, el trabajador del servidor continúa aunque se cierre el navegador. Al regresar, la lista permite abrir el estado actual. Las tablas se filtran y paginan en el servidor. La descarga de exportaciones utiliza autenticación y conserva el manifiesto de procedencia.

La bandeja abre primero las revisiones accionables y muestra por separado los pendientes de catálogo, datos y atención técnica. Los filtros de ejecución, motivo, etapa y búsqueda quedan en la URL. **Finalizados** incluye resoluciones automáticas y decisiones manuales cerradas; no significa que todos tengan un punto. **Guardar y siguiente** conserva los filtros, solicita el siguiente pendiente disponible y reinicia el formulario; el revisor debe tomar el nuevo registro explícitamente. **Volver y liberar reserva** devuelve la reserva propia antes de abandonar la ficha.

Desde una ejecución se puede preparar un nuevo procesamiento y seleccionar otro catálogo. Los resultados anteriores conservan su historial y salen de la bandeja vigente solo al terminar correctamente su sustituto. El dashboard cuenta ubicaciones de ejecuciones terminadas vigentes; el contador de procesamientos conserva el historial completo.

El mapa muestra únicamente las coordenadas y candidatos recibidos de la API. La cartografía base está sin configurar: no se hacen solicitudes a mapas o geocodificadores públicos. El estado vacío y la degradación por falta de WebGL son explícitos. Las fuentes tipográficas son del sistema y no requieren red.

## Ejemplo sintético

`public/demo.csv` contiene cinco filas artificiales, dos de ellas de la misma denuncia y dirección. `public/reference-demo.csv` proporciona dos referencias ficticias compatibles. Primero se puede importar el catálogo desde **Catálogos de referencia** y luego seleccionar el CSV desde **Nuevo procesamiento**. El catálogo no incluye límites territoriales; se espera que algunos resultados requieran revisión o expresen esa limitación. No se importa automáticamente y nunca debe presentarse como cartografía oficial.
