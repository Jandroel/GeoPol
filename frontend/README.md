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

Las pruebas verifican interrupción y reanudación de una carga, separación entre usuarios, límite de bloques, autenticación expirada, conflictos de revisión y conservación de candidatos después de tomar una revisión. `build` comprueba tipos y produce `dist/`. El visor MapLibre se carga de forma diferida; su dependencia genera un aviso de tamaño de Vite, sin afectar la compilación.

La prueba integrada en Chromium se ejecuta con `npm run test:e2e` contra un entorno local aislado. Configuración, alcance y evidencias se describen en [QA.md](QA.md).

## Operación y privacidad

El token se mantiene en `sessionStorage` y las consultas no se persisten. `localStorage` conserva exclusivamente los metadatos de la carga pendiente (identificador, usuario, nombre, tamaño y huella) y los identificadores de exportación por usuario/lote. Para reanudar una carga se selecciona otra vez el mismo archivo; se verifica su contenido completo mediante hashes de bloques, sin cargar el archivo entero en memoria. La huella local identifica la reselección; el SHA-256 oficial del archivo lo calcula el servidor.

Una vez creado el procesamiento, el trabajador del servidor continúa aunque se cierre el navegador. Al regresar, la lista permite abrir el estado actual. Las tablas se filtran y paginan en el servidor. La descarga de exportaciones utiliza autenticación y conserva el manifiesto de procedencia.

El mapa muestra únicamente las coordenadas y candidatos recibidos de la API. La cartografía base está sin configurar: no se hacen solicitudes a mapas o geocodificadores públicos. El estado vacío y la degradación por falta de WebGL son explícitos. Las fuentes tipográficas son del sistema y no requieren red.

## Ejemplo sintético

`public/demo.csv` contiene cinco filas artificiales, dos de ellas de la misma denuncia y dirección. `public/reference-demo.csv` proporciona dos referencias ficticias compatibles. Primero se puede importar el catálogo desde **Catálogos de referencia** y luego seleccionar el CSV desde **Nuevo procesamiento**. El catálogo no incluye límites territoriales; se espera que algunos resultados requieran revisión o expresen esa limitación. No se importa automáticamente y nunca debe presentarse como cartografía oficial.
