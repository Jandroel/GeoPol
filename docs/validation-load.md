# Validación reproducible de carga

La prueba usa datos completamente sintéticos, una API Uvicorn real en `127.0.0.1`, procesos de worker separados y una base SQLite aislada. Cada fila tiene un identificador de denuncia distinto: el número de unidades de ubicación coincide con el de filas. El campo `synthetic_padding` contiene 3072 caracteres ASCII para alcanzar el tamaño de archivo; no participa en la ubicación.

Se verifica el recorrido completo: generación en flujo, carga HTTP en fragmentos de 8 MiB, perfilado, checksum del original, ingesta, resolución, instantánea de exportación, exportación de todas las filas de origen, descarga HTTP en flujo, checksum y lectura del CSV exportado. También se comprueba que cada fila conserve su relleno y las coordenadas aceptadas.

## Reproducción

Desde la carpeta del proyecto, después de instalar las dependencias de desarrollo:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\benchmark.py --rows 10000 --padding 3072 --batch-size 1000
.\backend\.venv\Scripts\python.exe .\scripts\benchmark.py --rows 400100 --padding 3072 --batch-size 1000 --timeout 14400
```

En Linux, use `backend/.venv/bin/python` con los mismos argumentos. `--profile-worker` permite escribir estadísticas cProfile privadas; no debe utilizarse al comparar tiempos normales. Cada ejecución crea su propia carpeta `.local/load-…`, excluida de Git. Allí quedan los archivos, la base, los logs y `summary.json`. El script comprueba el espacio libre antes de empezar y no transmite datos fuera del equipo.

El plazo de 14 400 s deja margen para este disco y no es un objetivo de rendimiento. La versión publicada guarda además `last-checkpoint.json` con el último contador, el tiempo transcurrido y las métricas disponibles. Ese archivo declara `passed: false`: preserva evidencia parcial si el cliente se interrumpe y nunca sustituye la verificación final.

## Control medido

Ejecutado el 18 de septiembre de 2026 en Windows, compilación 26100, Python 3.11.9 y SQLite, con lotes de 1000 registros. La medición no utilizó cProfile. Los valores agregados están en `validation-load-control.json`.

| Medida | Control de 10 000 filas |
|---|---:|
| Tamaño del CSV original | 31 200 057 bytes |
| Unidades de ubicación | 10 000 |
| Carga y perfilado | 0,726 s |
| Ingesta y procesamiento | 36,754 s |
| Creación de instantánea | 1,763 s |
| Exportación | 4,029 s |
| Descarga y verificación | 0,847 s |
| Filas exportadas | 10 000 |
| Filas con incidencia técnica | 0 |
| Cota superior RSS del árbol del worker de procesamiento | 140 288 000 bytes |
| Pico RSS combinado observado | 338 198 528 bytes |

El monitor consulta memoria residente del sistema operativo cada 250 ms e incluye los procesos Python hijos de los lanzadores de entornos virtuales de Windows. `peak_rss_bytes_by_process_tree` es una cota superior calculada como suma de los máximos históricos individuales de los procesos de cada árbol; esos máximos pueden corresponder a momentos diferentes. `peak_combined_sampled_rss_bytes` sí es la mayor suma simultánea observada, sujeta al intervalo de muestreo. Los tiempos parciales de ingesta/procesamiento que aparecen en el JSON son aproximados, con observación cada cinco segundos; el tiempo conjunto es el medido directamente.

El script publicado también registra muestras correctas y errores del monitor. En Linux tolera que un proceso desaparezca entre descubrirlo y leer `/proc`, y registra errores de permisos sin detener silenciosamente la monitorización. Esta instrumentación de salud se incorporó mientras la carga de Windows ya estaba activa: sus contadores no se pueden reconstruir para las mediciones anteriores y no se atribuyen retrospectivamente a ellas.

## Carga de 400 100 filas completada con recuperación

La validación terminó correctamente el **19 de septiembre de 2026**: 400 100 filas de origen, 400 100 unidades distintas y 400 100 filas exportadas, con cero incidencias. El CSV original tiene **1 248 312 057 bytes** y el exportado **1 339 023 969 bytes**. Se verificaron ambos SHA-256, el manifiesto, todos los ordinales e identificadores sintéticos consecutivos y la conservación de cada relleno y coordenadas. Los valores y la trazabilidad están en [`validation-load-400100.json`](validation-load-400100.json).

La ejecución tuvo tres segmentos. En el primero, el cliente que consultaba el progreso recibió un error de transporte HTTP local (`WinError 10053`) y su cierre detuvo los procesos privados. La base conservó un checkpoint de **268 000 filas**. No se ha atribuido ese error al motor de normalización. La carga y el perfilado iniciales tardaron 28,908 s; no quedó una medición completa de duración ni de memoria de ese segmento.

La primera recuperación reutilizó el mismo lote, archivo, catálogo y base desde ese checkpoint, después de que expirara el arrendamiento del worker anterior. Se verificó nuevamente el SHA-256 del original, sin volver a cargarlo ni crear nuevas entradas. Terminó la ingesta y llegó a **51 000 unidades resueltas** antes de una cancelación controlada para trasladar la base a SSD. Los tiempos y la memoria se presentan por segmento; no se publica un tiempo continuo ni un pico global que no se hayan medido.

El equipo tiene un Intel Core i7-12700 (12 núcleos, 20 procesadores lógicos), 15,7 GiB de RAM, un HDD SATA ST1000DM010-2EP102 en D: y un SSD Micron MTFDKBA512TFK en C:. Con todos los procesos de la prueba cerrados, `sqlite3.Connection.backup()` creó una copia consistente de la base en C: en **20,726 s**. `PRAGMA quick_check` devolvió `ok`; se confirmaron el mismo identificador de lote, carga y catálogo, 400 100 filas/unidades, 51 000 procesadas y 400 100 ordinales únicos consecutivos. La tercera etapa completó esa copia en SSD y mantuvo el CSV y el almacenamiento de archivos en D:. Es un entorno mixto, no una medición íntegra en SSD.

| Medida del tercer segmento | Resultado |
|---|---:|
| Relectura y verificación del original existente | 6,878 s |
| Reactivación y resolución de las 349 100 unidades pendientes | 330,886 s |
| Creación de la instantánea de 400 100 unidades | 88,089 s |
| Exportación de 400 100 filas de origen | 138,554 s |
| Descarga y verificación completa del CSV exportado | 23,596 s |
| Pico RSS combinado simultáneo muestreado | 537 784 320 bytes |
| Cota superior RSS del árbol del worker de procesamiento | 226 656 256 bytes |
| Muestras de memoria correctas / errores | 2131 / 0 |

Estos tiempos corresponden únicamente a la tercera etapa. Su campo JSON `ingest_seconds_approx` refleja los 5,141 s hasta observar el estado de procesamiento, no una nueva ingesta: las 400 100 filas ya estaban incorporadas. La base final conserva exactamente un lote, una carga, un catálogo y una exportación, sin duplicar entradas. Los 400 100 resultados automáticos pertenecen a este caso sintético exacto.

Antes de cancelar la segunda etapa se conservó una observación del árbol de procesos: 657 375 232 bytes RSS simultáneos y una suma de máximos individuales de 708 661 248 bytes. Esa lectura puntual no reconstruye el pico global de la etapa. El JSON conserva su hora y el inicio del proceso, pero deja sin valor la duración íntegra y el pico global de la ejecución interrumpida. Los procesos propios de las tres etapas quedaron cerrados al concluir.

El script puede recuperar una ejecución interrumpida indicando su carpeta privada, conservada por el propio benchmark:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\benchmark.py --rows 400100 --padding 3072 --batch-size 1000 --timeout 14400 --resume-runtime .\.local\load-400100-<carpeta-de-la-ejecucion>
```

La recuperación reutiliza el único lote de esa carpeta y espera la expiración del arrendamiento, o solicita el reintento por API cuando corresponde. El cliente actualizado reintenta únicamente lecturas GET idempotentes y desactiva la reutilización de conexiones HTTP en esta prueba. Las operaciones de escritura no se repiten automáticamente. La aprobación de esta carga depende de los conteos finales y de la comprobación integral del CSV exportado, no únicamente de su tamaño o de checkpoints parciales.

Para reproducir la continuación con otro disco, cierre primero los procesos de la prueba y cree allí una copia con la API de backup de SQLite, que incorpora los cambios confirmados del WAL. No copie únicamente el archivo `.db` mientras haya conexiones activas. Luego use la carpeta de ejecución original con `--database-path` apuntando a esa copia existente:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\benchmark.py --rows 400100 --padding 3072 --batch-size 1000 --timeout 14400 --resume-runtime .\.local\load-400100-<carpeta-de-la-ejecucion> --database-path C:\Temp\geopol-benchmark\benchmark.db
```

## Ajuste de persistencia medido

Una comparación sobre dos copias privadas de la misma base sintética de 100 000 filas incorporó 5000 filas adicionales por copia. Se mantuvieron lotes de 1000, caché SQLite de 64 MiB por conexión y sincronización `FULL`. Se incluyó el tiempo del checkpoint final en ambos resultados:

| Umbral de checkpoint WAL | Tiempo total de las 5000 filas |
|---|---:|
| 1000 páginas | 55,096 s |
| 32 768 páginas | 13,447 s |

La segunda configuración redujo el coste total en este experimento aproximadamente 4,1 veces. El umbral indica cuándo solicitar un checkpoint y no constituye un límite estricto del tamaño del WAL. La sincronización de durabilidad se mantuvo activa. Los valores agregados están en `validation-load-wal.json`; esta comparación sirve para elegir la configuración que se verifica con la carga completa.

## Alcance de la evidencia

El catálogo de la prueba contiene un punto sintético y una vía exacta. Todas las filas usan esa vía, por lo que esta carga ejercita la persistencia, el trabajo por lotes y la cardinalidad, con una búsqueda referencial repetida. El 100 % de aceptaciones de este caso no mide exactitud sobre direcciones reales, amplitud nacional del catálogo, rendimiento fuzzy, consultas espaciales complejas ni concurrencia entre múltiples operadores.

Los resultados son de SQLite local; PostgreSQL/PostGIS, redes institucionales, almacenamiento compartido y disponibilidad de producción requieren su propia validación. El límite configurado de carga no debe interpretarse como un tamaño ya medido. Los datos institucionales usados en una comprobación privada funcional no forman parte de este benchmark, del repositorio ni de sus ejemplos.
