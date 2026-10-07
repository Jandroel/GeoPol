# Seguridad y tratamiento de datos

Este proyecto es una implementación de piloto. Tener autenticación y una base de datos local no demuestra cumplimiento institucional ni autoriza incorporar datos personales.

## Controles del MVP

- Usuarios y roles explícitos; no se entrega una cuenta ya activa ni una contraseña predeterminada. El administrador inicial se crea con la contraseña elegida en la instalación local. Las credenciales de tests/CI son exclusivamente sintéticas.
- Contraseñas derivadas mediante función de hash para contraseñas y sesiones revocables con vencimiento.
- Validación de permisos en el backend, además de las acciones visibles en la interfaz.
- Exportación con originales reservada a roles autorizados; las vistas operativas evitan devolver todas las columnas de origen.
- Originales y exportaciones privados fuera del directorio estático, con identificadores generados por el servidor.
- Límites de carga y validación de formatos. Los archivos no se interpretan como instrucciones y las fórmulas de una planilla no se ejecutan.
- XML de XLSX protegido con `defusedxml`, según la [recomendación de openpyxl](https://openpyxl.readthedocs.io/en/stable/#security); una prueba rechaza entidades DTD.
- Neutralización de fórmulas en CSV para hojas de cálculo cuando está activada la opción correspondiente.
- Reserva de revisión y control de versión, con motivo y evidencia para las decisiones.
- Auditoría de operaciones y trazabilidad de versiones; los originales se preservan.
- Sin mapa base público, geocodificador público, analítica externa ni carga remota de fuentes tipográficas por defecto.
- Logs de acceso HTTP desactivados por `python -m geopol.dev` para evitar registrar direcciones introducidas en búsquedas. Si se inicia Uvicorn por separado, conservar `--no-access-log` y revisar también los logs del proxy institucional.
- API y servidor de desarrollo web accesibles solo desde la computadora local. La guía configura PostgreSQL con un rol de aplicación sin privilegios de superusuario, separado del administrador que prepara la base y sus extensiones.

## Matriz funcional

| Rol | Lectura de resultados | Cargas/ejecuciones | Revisión | Exportación de originales | Auditoría |
| --- | --- | --- | --- | --- | --- |
| admin | Sí | Sí | Sí | Sí | Sí |
| operator | Sí | Sí | No | Sí | No |
| reviewer | Sí | No | Sí | No | No |
| analyst | Sí | No | No | No | No |

El alcance es por rol dentro de una instancia. No existe separación multiinstitución ni autorización por distrito, dependencia policial o caso. Incluso la ubicación o el identificador de una denuncia pueden ser sensibles: un perfil de exportación reducido no se declara anónimo.

## Secretos y sesiones

Crear usuarios con el prompt de la CLI. Para automatización, la CLI puede leer una variable de entorno mediante `--password-env GEOPOL_BOOTSTRAP_PASSWORD`; eliminar la variable al terminar y no guardarla en archivos versionados. No pasar contraseñas literales por argumentos de línea de comandos.

El frontend conserva la sesión en memoria y almacenamiento de sesión del navegador. Este mecanismo queda expuesto a JavaScript del mismo origen; la mitigación principal es evitar contenido ejecutable no confiable y limitar origen/CSP. La siguiente etapa institucional debe evaluar cookies seguras, SSO/OIDC y políticas de sesión. Servir el sistema con TLS para uso fuera de localhost.

La conexión PostgreSQL se configura en `backend/.env`, incluido el secreto del rol de aplicación creado al preparar la base. Ese archivo es privado y no se versiona; debe conservarse con acceso restringido. La app no necesita guardar la contraseña del administrador de PostgreSQL. La plantilla de configuración contiene solo valores de ejemplo que deben completarse con los datos de la instalación.

La contraseña web es independiente: `python -m geopol.dev` permite definirla al primer arranque cuando no existen cuentas. Los arranques posteriores conservan usuarios y contraseñas. La variable `GEOPOL_BOOTSTRAP_PASSWORD` es una alternativa para entornos sin prompt; úsala de forma transitoria, no como una contraseña fija en el repositorio. Antes de un despliegue institucional, integrar la configuración con el mecanismo de secretos aprobado y revisar los permisos de base y almacenamiento.

## Antes de incorporar información real

Establecer la autoridad responsable, usuarios autorizados, uso permitido, categorías de información y política de retención. Revisar permisos de almacenamiento, cifrado del disco y backups, acceso de operadores y administradores, exportaciones y borrado controlado. Definir TLS, proxy institucional, SSO, registros de seguridad, revocación y respuesta a incidentes.

Validar acceso concurrente, recuperación, controles de sesión y cargas malformadas en el entorno objetivo. El límite de archivos aceptado no demuestra capacidad con todos los libros XLSX de ese tamaño. La auditoría en la misma base no protege frente a un administrador que modifique directamente sus tablas; archivado externo inmutable queda fuera de esta entrega.
