# GeoPol · MVP

Aplicación para recibir CSV/XLSX, conservar sus filas de origen, normalizar ubicaciones, resolverlas contra referencias versionadas, revisar excepciones y exportar resultados para GIS. Implementa el flujo del apartado 20 del documento conceptual con datos y decisiones persistentes.

El repositorio es independiente. Los documentos de análisis y la muestra institucional quedan fuera del control de versiones. Los ejemplos incluidos son totalmente sintéticos y no representan cartografía oficial.

## Inicio local con Bash

Necesitas **Python 3.11 o superior, Node.js 24 y PostgreSQL 16 con PostGIS**.
Prepara tu base y configura `backend/.env` con su conexión siguiendo la
[guía breve](INSTALACION_LOCAL.md). Usa Git Bash en Windows o Bash en Linux/WSL.

En una terminal, prepara el backend **la primera vez**:

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -c requirements.lock -e '.[dev]'
cp -n .env.example .env
```

En Linux/WSL, crea el entorno con `python3 -m venv .venv` y actívalo con
`source .venv/bin/activate`. Edita `backend/.env` con el usuario, contraseña
y nombre de tu base PostgreSQL; después inicia el backend:

```bash
python -m geopol.dev
```

Al iniciar se crean o actualizan las tablas y, si aún no hay usuarios, se
solicita una contraseña para la cuenta web `administrador`. El mismo comando
mantiene activos la API y el trabajador que procesa los archivos.

En otra terminal, desde la raíz del proyecto:

```bash
cd frontend
npm ci
npm run dev
```

Abre [GeoPol local](http://localhost:5173) y mantén las dos terminales abiertas.
Para detenerlo, pulsa **Ctrl+C** en ambas. Los siguientes días solo activa el
entorno del backend y ejecuta `python -m geopol.dev`; en el frontend ejecuta
`npm run dev`. No hace falta reinstalar dependencias ni recrear la base.

La configuración queda en `backend/.env`, los datos en PostgreSQL y los archivos
en `data/storage` con la configuración de ejemplo. La documentación de la API
está en [OpenAPI local](http://localhost:8000/docs). La
[guía detallada](docs/instalacion-bash-detallada.md) cubre herramientas, respaldos
y ayuda. Cada persona prepara su propia base, cuenta y `.env`; comparte el
código y la guía, no las credenciales. Si ya usabas otro método, consulta la
[nota para instalaciones anteriores](docs/instalacion-local-detallada.md).

## Primer recorrido verificable

1. Iniciar sesión con el usuario creado.
2. En Referencias, importar `examples/referencias_sinteticas.geojson` con nombre `DEMO FICTICIA`, versión `demo-1` y fuente `Datos sintéticos, no uso operativo`.
3. Crear una ejecución con `examples/denuncias_sinteticas.csv`, comprobar mapeo y seleccionar esa referencia. Para estas coordenadas ficticias, seleccionar `EPSG:4326` y documentar como fuente «Coordenadas sintéticas EPSG:4326 del ejemplo incluido». En archivos reales, mantener el CRS sin confirmar hasta contar con documentación del proveedor.
4. Esperar que termine. Comparar filas de origen con unidades de ubicación: algunas filas describen la misma ubicación de una denuncia.
5. Abrir una ubicación pendiente de revisión, tomar el caso y registrar una decisión con motivo y evidencia. El mapa no utiliza servicios externos.
6. Solicitar una exportación de ubicaciones y descargar Excel y manifiesto. Para GIS, elegir CSV. Los casos no resueltos permanecen en la salida.
7. Repetir sin catálogo para comprobar que la ausencia de referencia se informa explícitamente y no se sustituye por puntos inventados.

Ver [ejemplos](examples/README.md) para conocer cada caso sintético. Las coordenadas de demostración son ficticias y no deben mezclarse con referencias reales.

## Funciones incluidas

- Cargas reanudables por bloques, checksum del archivo, perfil acotado y mapeo de campos.
- Ingesta CSV/XLSX, conservación de filas, incidencias y agrupación de unidades de ubicación.
- Normalización determinística, componentes, coordenadas originales/textuales y separación de centroides heredados.
- Matching conservador con catálogo elegido: puerta, cuadra y candidatos de otras familias según la referencia disponible.
- Carga de cinco referencias Excel junto al archivo PNP, flags de calidad separados del estado de revisión, avance de pendientes, gráficas y exportaciones filtradas. Ver la [guía del flujo por calidad](docs/quality-workflow.md).
- Referencia base persistente para futuras cargas y declaración documentada del sistema de coordenadas.
- Cola SQL persistente con API y worker separados; cancelación, reintento y nueva ejecución de reproceso.
- Revisión por excepción, grupos según la acción necesaria, reserva, «Guardar y siguiente», cierre/reapertura e histórico.
- Vista previa y decisión compartida para ubicaciones equivalentes, con comprobación transaccional y revisión individual conservada.
- Contexto de vías, límites y áreas del catálogo en el visor local, sin consultas externas.
- Roles, auditoría, indicadores con denominadores explícitos y consultas paginadas.
- Exportación asíncrona Excel con formato INEI o CSV para GIS, revisión, manifiesto y checksum; perfil ampliado restringido por rol. Ver la [guía de exportación](docs/excel-exports.md).

No incluye capas INEI/PNP oficiales, integración SIDPOL/OIDC ni validación de rendimiento con el volumen nacional. El motor espacial inicial utiliza Shapely sobre un catálogo acotado; el despliegue incluye PostGIS como base para evolucionar hacia consultas e índices espaciales. Consulte [alcance y límites](docs/limitations.md).

La [guía de automatización y revisión](docs/automation-operation.md) explica cómo configurar la referencia base, resolver causas comunes y preparar un piloto ArcGIS opcional. El adaptador externo está desactivado y no participa automáticamente en los procesamientos. `python -m geopol.dev` aplica las migraciones pendientes antes del arranque; conservar un respaldo previo al actualizar.

## Arquitectura y estructura

```text
geopol-mvp/
├── backend/
│   ├── geopol/
│   │   ├── main.py         # Composición FastAPI, middleware y registro de routers
│   │   ├── api/            # Routers por responsabilidad y helpers HTTP comunes
│   │   ├── domain/         # Ingesta, normalización y matching sin HTTP
│   │   ├── worker.py       # Trabajos persistentes y checkpoints
│   │   ├── dev.py          # Arranque local de API y trabajador
│   │   └── ...             # Persistencia, seguridad, migraciones y CLI
│   ├── tests/              # Pruebas de reglas y flujo de aplicación
│   ├── .env.example        # Plantilla de conexión a tu PostgreSQL
│   └── pyproject.toml
├── frontend/               # React, TypeScript, Vite y MapLibre local
├── examples/               # Archivos sintéticos y explicación de escenarios
├── docs/                   # Arquitectura, operación, límites y contratos
├── scripts/                # Herramientas de comprobación y soporte
├── .github/workflows/      # Verificaciones automatizadas
├── INSTALACION_LOCAL.md    # Preparación y arranque con Bash
└── AGENTS.md               # Convenciones de desarrollo
```

La [arquitectura](docs/architecture.md) explica las decisiones y fronteras de los módulos. El [contrato de implementación](docs/implementation-contract.md) documenta los endpoints y la [guía de operación](docs/runbook.md) cubre recuperación y respaldo.

El [flujo de revisión y reprocesamiento](docs/review-workflow.md) describe la selección de catálogos y el historial. La ampliación [2026.3](docs/automation-2026.3.md) añade geometrías por precisión, búsqueda territorial y direcciones validadas reutilizables; requiere migración v3. Los casos que requieren referencia permanecen visibles sin mezclarse con los que ya tienen candidatos revisables.

La [evidencia de validación](docs/validation.md) detalla recuperación de trabajos, restauración SQLite y lectura real del CSV con GDAL, incluidos sus límites.

Se verificaron las 40 filas de la muestra suministrada como 16 unidades, y un CSV sintético de **1 248 312 057 bytes con 400 100 filas**, conservadas hasta la descarga de la exportación. La prueba grande incluyó recuperación por checkpoints y traslado de una copia consistente de la base de HDD a SSD; sus tiempos corresponden a etapas separadas. Consulte el [informe reproducible de carga](docs/validation-load.md).

## Verificación y colaboración

Para desarrollar, después de instalar las dependencias, ejecuta desde Bash:

```bash
geopol_python="backend/.venv/bin/python"
if [ -x backend/.venv/Scripts/python.exe ]; then
  geopol_python="backend/.venv/Scripts/python.exe"
fi
"$geopol_python" -m ruff check backend
"$geopol_python" -m pytest backend/tests -q
cd frontend
npm run test
npm run build
```

El bloque elige el ejecutable de Python para Windows o Linux. Los mismos controles están definidos en GitHub Actions. Las pruebas utilizan datos sintéticos y bases aisladas. La prueba opcional PostgreSQL/PostGIS requiere `GEOPOL_TEST_DATABASE_URL` apuntando a una base de pruebas dedicada y vacía; se omite localmente si no está definida. CI prepara PostgreSQL/PostGIS de forma nativa y comprueba las migraciones, geometrías e índices espaciales, además del flujo de instalación y arranque.

Usar [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat(ingestion): ...`, `fix(review): ...`, `test(domain): ...`, `docs(operations): ...`. Mantener cambios pequeños, ejecutar las comprobaciones relevantes y no versionar `.env`, `data/`, muestras institucionales ni exportaciones. La política operativa de acceso y retención debe acordarse antes de incorporar datos reales.
