# Revisión de excepciones (issue #12)

## Resultado

El inventario de esta revisión encontró 113 cláusulas `except Exception` en
`app/`, `db/` y `drivers/` (el issue estimaba unas 106). El número incluye las
cláusulas que se mantienen en los límites HTTP, jobs, limpieza, drivers y
migraciones. La presencia de una captura amplia no se considera por sí sola un
defecto; sí lo es absorberla sin traza, exponer detalles internos o continuar
una transacción PostgreSQL que ya falló.

## Política aplicada

- Las excepciones inesperadas en rutas se registran con `logger.exception` y
  devuelven un mensaje genérico. Las rutas que convierten errores esperados de
  validación en 400/409 mantienen mensajes de dominio controlados.
- El handler global de `Exception` ya existía en `app/errors.py`; registra la
  traza y responde con `Error interno del servidor` para JSON y HTML. Se
  conservó como última barrera. Los fallos absorbidos por rutas y helpers ahora
  también dejan traza.
- Los errores del scheduler se registran con traza. Las fallas de backup,
  sincronización incremental y nocturna registran resultado fallido en
  `public.scheduler_runs` a través de `_registrar_corrida_sync`. Si falla la
  escritura de esa tabla, el propio helper registra la excepción.
- `db.connection.get_connection()` ejecuta rollback y propaga la excepción.
  Se eliminó la captura que ignoraba fallos de inserción por fila en
  `agregar_personas_a_periodo_bulk`; cualquier error aborta y revierte la
  transacción completa.
- En importadores CSV, cada fila se ejecuta dentro de un savepoint. Una falla
  se registra y revierte solo esa fila antes de continuar; un fallo al leer el
  archivo o la transacción completa se propaga al límite exterior y se reporta
  de forma genérica. Esto evita seguir dentro de una transacción abortada y
  evita filtrar mensajes SQL.
- Los fallbacks que se mantienen (contadores del menú, enriquecimiento
  opcional, dispositivos, auditoría secundaria y consultas no críticas)
  registran la traza antes de usar un valor alternativo. Las excepciones de
  parseo de horas/fechas se restringen a `TypeError` y `ValueError` cuando
  corresponde.

## Superficies corregidas

- Endpoints JSON de dispositivos, asistencias, feriados, reportes, analytics,
  grupos y administración: trazas de servidor y mensajes 500 genéricos.
- Formularios HTML de personas, grupos, períodos y horarios: mensajes
  genéricos al usuario y detalles en el log.
- Middleware tenant: los errores de base de datos se registran y propagan al
  handler global; ya no se interpretan como un tenant ausente ni como una lista
  vacía de tipos de persona.
- Drivers Hikvision y ZKTeco: los fallos de conexión, lectura, credenciales y
  desconexión se registran con traza.
- Consultas CSV de períodos y grupos funcionales: errores de fila sin texto de
  excepción en el resultado y rollback ante fallo de BD.

## Límites de esta revisión

Se mantuvieron capturas amplias en límites donde es necesario convertir un
fallo a una respuesta, un estado de sincronización, un fallback controlado o un
error de CLI. Cada una registra la excepción o la propaga. Las capturas de
`db/connection.py` y `app/domain/auth.py` preservan rollback/repropagación o
convierten un duplicado en un error de dominio; no continúan silenciosamente.

Verificación manual del inventario:

```powershell
rg -n "except Exception" app db drivers
rg -n "str\(e\)|\{e\}" app/web
```

Las apariciones restantes de `str(e)` en blueprints pertenecen a excepciones
`ValueError`/`RuntimeError` tratadas como errores de entrada o reglas de
negocio. Las rutas que capturan excepciones inesperadas ya no retornan su
contenido. No se ejecutó la suite automatizada en esta revisión.
