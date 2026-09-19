# Seguridad y tratamiento de datos

Este proyecto es una implementación de piloto. Tener autenticación y contenedores no demuestra cumplimiento institucional ni autoriza incorporar datos personales.

## Controles del MVP

- Usuarios y roles explícitos; no hay cuenta operativa ni contraseña predeterminada. Las credenciales de tests/CI son exclusivamente sintéticas.
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
- Logs de acceso HTTP desactivados en los scripts y contenedores para evitar registrar direcciones introducidas en búsquedas. Si se inicia Uvicorn manualmente, conservar `--no-access-log` y revisar también los logs del proxy institucional.
- Servicios Compose expuestos solo en localhost, procesos de aplicación sin privilegios, filesystem de contenedores de aplicación de solo lectura salvo volúmenes y temporales.

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

La contraseña PostgreSQL de Compose requiere caracteres seguros para URL porque se incorpora en una URL de conexión. Utilizar un secreto aleatorio propio; `.env` es local y debe tener permisos restringidos. Antes del despliegue institucional, sustituirlo por el mecanismo de secretos aprobado y usar un usuario de aplicación de mínimos privilegios separado del de administración/migraciones.

## Antes de incorporar información real

Establecer la autoridad responsable, usuarios autorizados, uso permitido, categorías de información y política de retención. Revisar permisos de almacenamiento, cifrado del disco y backups, acceso de operadores y administradores, exportaciones y borrado controlado. Definir TLS, proxy institucional, SSO, registros de seguridad, revocación y respuesta a incidentes.

Validar acceso concurrente, recuperación, controles de sesión y cargas malformadas en el entorno objetivo. El límite de archivos aceptado no demuestra capacidad con todos los libros XLSX de ese tamaño. La auditoría en la misma base no protege frente a un administrador que modifique directamente sus tablas; archivado externo inmutable queda fuera de esta entrega.
