# GeoPol · MVP

Aplicación para recibir CSV/XLSX, conservar sus filas de origen, normalizar ubicaciones, resolverlas contra referencias versionadas, revisar excepciones y exportar resultados para GIS. Implementa el flujo del apartado 20 del documento conceptual con datos y decisiones persistentes.

El repositorio es independiente. Los documentos de análisis y la muestra institucional quedan fuera del control de versiones. Los ejemplos incluidos son totalmente sintéticos y no representan cartografía oficial.

## Inicio local en Windows

Requisitos: Python 3.11+, Node.js 24 con npm y PowerShell. Ejecutar desde la raíz del proyecto:

```powershell
.\scripts\setup.ps1
.\backend\.venv\Scripts\python.exe -m geopol.cli create-user --username administrador --role admin
```

La CLI solicitará una contraseña propia; no existe usuario ni contraseña predefinidos. Después, abrir tres terminales en la raíz:

```powershell
# Terminal 1
.\scripts\dev.ps1 api
# Terminal 2
.\scripts\dev.ps1 worker
# Terminal 3
.\scripts\dev.ps1 frontend
```

Abrir [GeoPol local](http://localhost:5173). La documentación interactiva de la API está en [OpenAPI local](http://localhost:8000/docs). El worker debe permanecer activo para procesar ejecuciones y exportaciones; su trabajo continúa aunque se cierre el navegador.

El modo local utiliza SQLite en `data/geopol.db` y archivos en `data/storage`, relativos a la raíz desde la que se ejecutan estos scripts. Usar **un solo worker con SQLite**. La configuración lee variables `GEOPOL_*` del entorno y de `.env`; mantener rutas y orígenes coherentes si se alternan los modos local y Compose.

## Inicio local en Linux o macOS

```bash
bash scripts/setup.sh
backend/.venv/bin/python -m geopol.cli create-user --username administrador --role admin
# En tres terminales:
bash scripts/dev.sh api
bash scripts/dev.sh worker
bash scripts/dev.sh frontend
```

Si Python no está en el ejecutable por defecto, usar `scripts/setup.ps1 -PythonCommand <ruta>` en Windows o `PYTHON=python3.11 bash scripts/setup.sh` en Linux/macOS.

## Contenedores con PostgreSQL/PostGIS

Requisitos: Docker Engine o Docker Desktop activo y Docker Compose v2 o superior.

1. Copiar `.env.example` a `.env` y establecer `POSTGRES_PASSWORD` con un valor aleatorio propio, usando caracteres seguros para URL (letras, números, `-`, `_`).
2. Ejecutar los siguientes comandos desde la raíz:

```bash
docker compose up --build -d
docker compose exec api python -m geopol.cli create-user --username administrador --role admin
docker compose ps
```

Abrir [GeoPol en contenedores](http://localhost:8080). La API también se publica en `127.0.0.1:8000`. PostgreSQL no publica un puerto en el host. Compose espera la salud de la base, ejecuta la inicialización del esquema y después inicia API y worker. [Orden de inicio de Compose](https://docs.docker.com/compose/how-tos/startup-order/).

Los volúmenes `database` y `artifacts` conservan base y archivos. `docker compose down` detiene el despliegue conservando volúmenes; **`down -v` los elimina**. El despliegue escucha únicamente en localhost y es una base de piloto: el acceso institucional requiere TLS, respaldo probado y controles adicionales descritos en [seguridad](docs/security.md).

## Primer recorrido verificable

1. Iniciar sesión con el usuario creado.
2. En Referencias, importar `examples/referencias_sinteticas.geojson` con nombre `DEMO FICTICIA`, versión `demo-1` y fuente `Datos sintéticos, no uso operativo`.
3. Crear una ejecución con `examples/denuncias_sinteticas.csv`, comprobar mapeo y seleccionar esa referencia. Mantener el CRS en `EPSG:4326`.
4. Esperar que termine. Comparar filas de origen con unidades de ubicación: algunas filas describen la misma ubicación de una denuncia.
5. Abrir una ubicación pendiente de revisión, tomar el caso y registrar una decisión con motivo y evidencia. El mapa no utiliza servicios externos.
6. Solicitar una exportación de ubicaciones y descargar CSV y manifiesto. Los casos no resueltos permanecen en la salida.
7. Repetir sin catálogo para comprobar que la ausencia de referencia se informa explícitamente y no se sustituye por puntos inventados.

Ver [ejemplos](examples/README.md) para conocer cada caso sintético. Las coordenadas de demostración son ficticias y no deben mezclarse con referencias reales.

## Funciones incluidas

- Cargas reanudables por bloques, checksum del archivo, perfil acotado y mapeo de campos.
- Ingesta CSV/XLSX, conservación de filas, incidencias y agrupación de unidades de ubicación.
- Normalización determinística, componentes, coordenadas originales/textuales y separación de centroides heredados.
- Matching conservador con catálogo elegido: puerta, cuadra y candidatos de otras familias según la referencia disponible.
- Cola SQL persistente con API y worker separados; cancelación, reintento y nueva ejecución de reproceso.
- Revisión con reserva, control de versión, motivo, evidencia e histórico.
- Roles, auditoría, indicadores con denominadores explícitos y consultas paginadas.
- Exportación asíncrona CSV con revisión, manifiesto y checksum; perfil ampliado restringido por rol.

No incluye capas INEI/PNP oficiales, integración SIDPOL/OIDC ni validación de rendimiento con el volumen nacional. El motor espacial inicial utiliza Shapely sobre un catálogo acotado; el despliegue incluye PostGIS como base para evolucionar hacia consultas e índices espaciales. Consulte [alcance y límites](docs/limitations.md).

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

La [evidencia de validación](docs/validation.md) detalla recuperación de trabajos, restauración SQLite y lectura real del CSV con GDAL, incluidos sus límites.

## Verificación y colaboración

```powershell
.\backend\.venv\Scripts\python.exe -m ruff check backend
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
Set-Location frontend
npm run test
npm run build
```

En Linux/macOS sustituir el ejecutable por `backend/.venv/bin/python`. Los mismos controles están definidos en GitHub Actions. Las pruebas utilizan datos sintéticos y bases aisladas. La prueba opcional PostgreSQL/PostGIS requiere `GEOPOL_TEST_DATABASE_URL` apuntando a una base de pruebas dedicada y vacía; se omite localmente si no está definida. El job `postgis` de CI crea ese servicio y valida migración idempotente, geometría derivada y presencia de índices espaciales.

Usar [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat(ingestion): ...`, `fix(review): ...`, `test(domain): ...`, `docs(operations): ...`. Mantener cambios pequeños, ejecutar las comprobaciones relevantes y no versionar `.env`, `data/`, muestras institucionales ni exportaciones. La política operativa de acceso y retención debe acordarse antes de incorporar datos reales.
