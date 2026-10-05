# GeoPol · MVP

Aplicación para recibir CSV/XLSX, conservar sus filas de origen, normalizar ubicaciones, resolverlas contra referencias versionadas, revisar excepciones y exportar resultados para GIS. Implementa el flujo del apartado 20 del documento conceptual con datos y decisiones persistentes.

El repositorio es independiente. Los documentos de análisis y la muestra institucional quedan fuera del control de versiones. Los ejemplos incluidos son totalmente sintéticos y no representan cartografía oficial.

## Inicio local con Bash

Necesitas **Bash y Docker activo con Compose 2.20 o superior**. En Windows,
utiliza Git Bash y Docker Desktop con contenedores Linux; en Linux, Bash y
Docker Engine. La [guía para principiantes](INSTALACION_LOCAL.md) explica cómo
preparar la computadora y descargar el proyecto como ZIP o con Git.

Desde la carpeta del proyecto, ejecuta:

```bash
bash instalar.sh
bash iniciar.sh
```

El instalador prepara la aplicación y **PostgreSQL 16 con PostGIS 3.5**. No
necesitas instalar Python, Node.js ni PostgreSQL por separado. Si la base no
tiene usuarios, crea `administrador` y pide una contraseña propia de al menos
12 caracteres; conserva las cuentas de instalaciones existentes.

Abre [GeoPol local](http://localhost:8080). Puedes cerrar la terminal y mantener
Docker activo. Los siguientes días ejecuta solo `bash iniciar.sh`; para detener
la aplicación conservando los datos, usa `bash detener.sh`.

Los datos persisten en los volúmenes `geopol-local_database` y
`geopol-local_artifacts`. El instalador genera la contraseña interna de la base
y la conserva en `.local/compose.env`: no edites, borres ni compartas ese
archivo. PostgreSQL no publica su puerto en la computadora. La documentación
de la API está en [OpenAPI local](http://localhost:8000/docs).

La [guía Bash detallada](docs/instalacion-bash-detallada.md) explica PostgreSQL,
respaldo, actualizaciones, puertos y proxy. Para compartir el proyecto, envía
el enlace de GitHub y la guía; cada persona tendrá su propia cuenta y datos.
El acceso desde otras computadoras requiere un despliegue administrado; consulta
los controles de [seguridad](docs/security.md).

## Alternativa anterior: instalación manual con SQLite

La [guía manual de Windows y Linux/macOS](docs/instalacion-local-detallada.md)
conserva la instalación con Python 3.11+, Node.js 24 y SQLite. Los scripts
`instalar.cmd`, `iniciar.cmd` y **`scripts/setup.sh` pertenecen a esa alternativa**;
no preparan el nuevo despliegue Bash con PostgreSQL.

En ese método, la base habitual es `data/geopol.db` y los archivos están en
`data/storage`; usar un solo worker con SQLite. El método Docker no migra esos
datos automáticamente. Conserva la instalación anterior y su respaldo si ya
contienen información necesaria.

Para lotes grandes en la instalación SQLite, consulta la [configuración de
almacenamiento en SSD](docs/runbook.md#almacenamiento-para-lotes-grandes).
La [prueba de carga](docs/validation-load.md) documenta el efecto observado del
almacenamiento y la recuperación por checkpoints.

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

La [guía de automatización y revisión](docs/automation-operation.md) explica cómo configurar la referencia base, resolver causas comunes y preparar un piloto ArcGIS opcional. El adaptador externo está desactivado y no participa automáticamente en los procesamientos. Esta actualización requiere aplicar la migración 4 con `python -m geopol.cli init-db` antes de iniciar API y worker; conservar un respaldo previo.

## Arquitectura y estructura

```text
geopol-mvp/
├── backend/
│   ├── geopol/
│   │   ├── main.py         # Composición FastAPI, middleware y registro de routers
│   │   ├── api/            # Routers por responsabilidad y helpers HTTP comunes
│   │   ├── domain/         # Ingesta, normalización y matching sin HTTP
│   │   ├── worker.py       # Trabajos persistentes y checkpoints
│   │   └── ...             # Persistencia, seguridad, migraciones y CLI
│   ├── tests/              # Pruebas de reglas y flujo de aplicación
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/               # React, TypeScript, Vite y MapLibre local
├── examples/               # Archivos sintéticos y explicación de escenarios
├── docs/                   # Arquitectura, operación, límites y contratos
├── scripts/                # Instalación y ejecución local PS/Bash
├── .github/workflows/      # Verificaciones automatizadas
├── compose.yaml
└── AGENTS.md               # Convenciones de desarrollo
```

La [arquitectura](docs/architecture.md) explica las decisiones y fronteras de los módulos. El [contrato de implementación](docs/implementation-contract.md) documenta los endpoints y la [guía de operación](docs/runbook.md) cubre recuperación y respaldo.

El [flujo de revisión y reprocesamiento](docs/review-workflow.md) describe la selección de catálogos y el historial. La ampliación [2026.3](docs/automation-2026.3.md) añade geometrías por precisión, búsqueda territorial y direcciones validadas reutilizables; requiere migración v3. Los casos que requieren referencia permanecen visibles sin mezclarse con los que ya tienen candidatos revisables.

La [evidencia de validación](docs/validation.md) detalla recuperación de trabajos, restauración SQLite y lectura real del CSV con GDAL, incluidos sus límites.

Se verificaron las 40 filas de la muestra suministrada como 16 unidades, y un CSV sintético de **1 248 312 057 bytes con 400 100 filas**, conservadas hasta la descarga de la exportación. La prueba grande incluyó recuperación por checkpoints y traslado de una copia consistente de la base de HDD a SSD; sus tiempos corresponden a etapas separadas. Consulte el [informe reproducible de carga](docs/validation-load.md).

## Verificación y colaboración

Para desarrollar con Python y Node.js instalados, ejecuta desde Bash:

```bash
backend/.venv/bin/python -m ruff check backend
backend/.venv/bin/python -m pytest backend/tests -q
cd frontend
npm run test
npm run build
```

Si usas un entorno Python creado en Windows, cambia el ejecutable por `backend/.venv/Scripts/python.exe`. Los mismos controles están definidos en GitHub Actions. Las pruebas utilizan datos sintéticos y bases aisladas. La prueba opcional PostgreSQL/PostGIS requiere `GEOPOL_TEST_DATABASE_URL` apuntando a una base de pruebas dedicada y vacía; se omite localmente si no está definida. El job `postgis` de CI crea ese servicio y valida migración idempotente, geometría derivada y presencia de índices espaciales. El job `compose` comprueba una instalación Bash nueva y la conservación de cuentas y archivos después de reiniciar PostgreSQL y la aplicación.

Usar [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat(ingestion): ...`, `fix(review): ...`, `test(domain): ...`, `docs(operations): ...`. Mantener cambios pequeños, ejecutar las comprobaciones relevantes y no versionar `.env`, `data/`, muestras institucionales ni exportaciones. La política operativa de acceso y retención debe acordarse antes de incorporar datos reales.
