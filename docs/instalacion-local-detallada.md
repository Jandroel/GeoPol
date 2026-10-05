# Instalaciones locales anteriores

La instalación vigente utiliza **Bash, Python 3.11 o superior, Node.js 24 y
PostgreSQL 16 con PostGIS** en la computadora. Sigue la
[guía de instalación para principiantes](../INSTALACION_LOCAL.md) y la
[guía Bash detallada](instalacion-bash-detallada.md).

Esta página conserva la referencia para quienes ya tenían una instalación
manual con SQLite. Los scripts anteriores `instalar.cmd`, `iniciar.cmd`,
`scripts/setup.ps1` y `scripts/setup.sh` pertenecen a ese método. No preparan
la nueva instalación PostgreSQL.

## Conservar una instalación anterior

En el método SQLite habitual, la base está en `data/geopol.db` y los originales
y exportaciones en `data/storage`. Si se configuraron otras rutas en `.env`,
conserva también ese archivo privado y respalda las ubicaciones configuradas.

Detén la API y el worker de esa instalación antes de copiar su base y archivos
como un mismo corte. Conserva los archivos SQLite auxiliares que existan o usa
la API de respaldo de SQLite; copiar solo el archivo principal mientras hay
conexiones puede perder cambios del WAL. La
[evidencia de recuperación anterior](validation.md) describe los ensayos
realizados con datos sintéticos.

El flujo Bash nativo guarda su configuración en `.local/native.json` y sus
archivos en `data/storage-native`; su base está en PostgreSQL. No cambia el
`.env` anterior ni importa automáticamente usuarios, procesamientos o archivos.
Tener instalada la aplicación nueva no demuestra que los datos anteriores
hayan sido migrados.

Conserva la instalación y su respaldo hasta preparar una migración explícita y
verificar cuentas, recuentos, históricos, originales, exportaciones y checksums.
Para una primera prueba de la instalación nueva, utiliza los
[ejemplos ficticios](../examples/README.md).