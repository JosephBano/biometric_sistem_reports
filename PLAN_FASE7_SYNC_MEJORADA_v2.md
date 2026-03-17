# Plan de Implementación — Fase 7: Sincronización Mejorada
**Versión:** 2.0 — Sync unificada, sin routing por módulo
**Fecha:** 2026-03-17
**Prerequisito:** Fases 1–6 v2 completadas y verificadas

---

## 1. Contexto y cambios respecto a v1

### 1.1 Qué cambia

Esta fase es la de **menor impacto** del modelo horizontal. Las mejoras de sync son de infraestructura pura — ninguna depende de si existe un "módulo de alumnos" o no.

El único cambio es conceptual: la v1 mencionaba "deduplicación avanzada de registros entre dispositivos (para el caso de empleado en múltiples ZKs) — se abordará si surge el caso". 

En v2 ese caso ya está **resuelto desde la Fase 1** por diseño. `personas_dispositivos` garantiza que una misma persona marcando en dos dispositivos distintos produce dos registros en `asistencias` con el mismo `persona_id`. No hay deduplicación — son marcaciones legítimas de dos dispositivos. El análisis de `script.py` ya agrupa por `persona_id` (o por `id_usuario` en la capa de compatibilidad), así que esto funciona correctamente sin trabajo adicional.

### 1.2 Lo que no cambia

Todo el contenido técnico de la v1:
- Sync incremental por watermark
- Sync paralela con ThreadPoolExecutor
- Sistema de prioridades por dispositivo
- Reintentos con backoff exponencial
- Sync nocturna completa de verificación
- Progreso granular en la UI
- Alertas de conectividad

---

## 2. Alcance

**Qué incluye:**
- Sync incremental: descargar solo registros nuevos desde el último watermark
- Sync paralela: múltiples dispositivos simultáneos con ThreadPoolExecutor
- Prioridades por dispositivo (campo en `dispositivos`)
- Reintentos con backoff exponencial para dispositivos que fallan
- Sync nocturna completa de verificación (una vez por día)
- Progreso granular en UI: porcentaje y estado por dispositivo
- Alertas automáticas cuando un dispositivo lleva N syncs fallidas consecutivas

**Qué NO incluye:**
- Cola de tareas con Redis/Celery
- Sync en tiempo real / webhooks
- "Deduplicación entre dispositivos" (ya resuelto por personas_dispositivos en Fase 1)

---

## 3. Mejora 1: Sync incremental por watermark

### 3.1 Concepto

Los campos `watermark_ultimo_id` y `watermark_ultima_fecha` en `dispositivos` ya existen desde la Fase 1 (reservados con NULL). En esta fase se activan.

```
Sync normal (incremental):
  driver.get_asistencias(desde=dispositivo.watermark_ultima_fecha)
  → Solo descarga registros más nuevos que el watermark
  → Al finalizar, actualiza watermark con el último registro procesado

Sync nocturna completa (verificación):
  driver.get_asistencias(desde=None)
  → Descarga todo el historial
  → Detecta y rellena huecos que la sync incremental haya podido perder
  → Se ejecuta a las 2:00 AM
```

### 3.2 Actualización del watermark

```python
# Al finalizar sync exitosa:
if registros:
    ultimo_registro = max(registros, key=lambda r: r['fecha_hora'])
    db.actualizar_watermark(
        dispositivo_id=dispositivo_id,
        ultimo_id=str(ultimo_registro.get('id_interno_zk')),
        ultima_fecha=ultimo_registro['fecha_hora']
    )
```

### 3.3 Primera sync de un dispositivo nuevo

Si `watermark_ultima_fecha = NULL`, el driver descarga todo el historial disponible. Es el comportamiento actual, aplicado solo la primera vez.

---

## 4. Mejora 2: Sync paralela

```python
# sync.py
from concurrent.futures import ThreadPoolExecutor, as_completed

def sincronizar_todos(tenant_schema: str):
    dispositivos = db.get_dispositivos_activos()
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(sincronizar_dispositivo, d['id']): d
            for d in dispositivos
        }
        for future in as_completed(futures):
            dispositivo = futures[future]
            try:
                resultado = future.result()
                db.actualizar_estado_sync_ui(dispositivo['id'], resultado)
            except Exception as e:
                db.registrar_sync_fallida(dispositivo['id'], str(e))
```

**Nota:** Cada hilo opera en su propio contexto de conexión de BD. El pool de SQLAlchemy maneja la concurrencia correctamente con `pool_size` apropiado.

---

## 5. Mejora 3: Prioridades por dispositivo

Agregar campo `prioridad` (INTEGER DEFAULT 5, rango 1-10) a `dispositivos` en una migración Alembic:

```
0005_sync_prioridad_dispositivo.py
```

Los dispositivos con `prioridad > 7` se sincronizan cada 15 minutos. Los demás, cada 30. Configurable desde la UI de dispositivos.

---

## 6. Mejora 4: Reintentos con backoff exponencial

```python
def sincronizar_con_reintento(dispositivo_id: str, max_intentos: int = 3):
    for intento in range(max_intentos):
        try:
            sincronizar_dispositivo(dispositivo_id)
            return  # éxito, salir
        except Exception as e:
            if intento == max_intentos - 1:
                db.registrar_sync_fallida(dispositivo_id, str(e))
                return
            espera = 2 ** intento * 5  # 5s, 10s, 20s
            time.sleep(espera)
```

---

## 7. Mejora 5: Sync nocturna completa de verificación

Tarea del scheduler a las 2:00 AM:

```python
def sync_nocturna_completa():
    """
    Descarga el historial completo de todos los dispositivos.
    Detecta y rellena huecos que la sync incremental haya podido perder.
    Actualiza watermarks con los valores correctos.
    """
    dispositivos = db.get_dispositivos_activos()
    for d in dispositivos:
        driver = get_driver(d)
        todos = driver.get_asistencias(desde=None)
        nuevos = db.insertar_asistencias(todos)  # INSERT ON CONFLICT DO NOTHING
        # Los registros ya existentes se ignoran silenciosamente
```

---

## 8. Mejora 6: Progreso granular en la UI

Nueva tabla `sync_estado` en el schema del tenant (o en `sync_log` con campos adicionales):

| Campo | Tipo | Descripción |
|---|---|---|
| `dispositivo_id` | UUID FK | |
| `estado` | TEXT | `'idle'`, `'sincronizando'`, `'completado'`, `'error'` |
| `progreso_pct` | INTEGER | 0-100 estimado |
| `registros_procesados` | INTEGER | |
| `actualizado_en` | TIMESTAMPTZ | |

La UI consulta este estado via `GET /sync/estado` (polling cada 2 segundos durante sync activa).

---

## 9. Mejora 7: Alertas de conectividad

```python
def verificar_dispositivos_desconectados():
    """
    Si un dispositivo tiene N syncs fallidas consecutivas, notifica al admin.
    N configurable (default: 3).
    """
    dispositivos_problema = db.get_dispositivos_con_fallas_consecutivas(n=3)
    for d in dispositivos_problema:
        if not d['alerta_enviada_hoy']:
            enviar_email_alerta_dispositivo(d)
            db.marcar_alerta_enviada(d['id'])
```

---

## 10. Migración Alembic para esta fase

```
0005_sync_mejoras.py:
  - ADD COLUMN prioridad INTEGER DEFAULT 5 en dispositivos
  - CREATE TABLE sync_estado (o ADD COLUMNS en sync_log)
```

---

## 11. Pasos de implementación

### Paso 1 — Migración `0005_sync_mejoras`

**Verificación:** `alembic upgrade head` sin errores. `dispositivos` tiene campo `prioridad`.

### Paso 2 — Sync incremental

Activar uso de `watermark_ultima_fecha` en todos los drivers. Actualizar watermark al finalizar sync exitosa.

**Verificación:** Segunda sync del mismo dispositivo descarga 0 o pocos registros (solo los nuevos desde el último watermark).

### Paso 3 — Sync paralela

Refactorizar el bucle de sync para usar `ThreadPoolExecutor`.

**Verificación:** Con 3 dispositivos activos, los 3 se sincronizan simultáneamente (visible en logs por timestamps).

### Paso 4 — Reintentos con backoff

Envolver `sincronizar_dispositivo()` con la lógica de reintentos.

**Verificación:** Dispositivo offline → 3 intentos con espera creciente → se registra falla en `sync_log`.

### Paso 5 — Sync nocturna completa

Agregar la tarea al scheduler a las 2:00 AM.

**Verificación:** Crear hueco artificial en `asistencias` → la sync nocturna lo detecta y rellena.

### Paso 6 — Progreso granular en UI

Implementar `sync_estado` y el endpoint de polling.

**Verificación:** Durante una sync activa, la UI muestra el progreso por dispositivo actualizándose cada 2 segundos.

### Paso 7 — Alertas de conectividad

Agregar la tarea al scheduler.

**Verificación:** Simular 3 syncs fallidas consecutivas → email de alerta enviado al admin.

---

## 12. Criterio de finalización

- [ ] Sync incremental activa: la segunda sync de un dispositivo no reprocesa registros ya existentes
- [ ] Watermarks actualizados correctamente después de cada sync exitosa
- [ ] Sync paralela: múltiples dispositivos sincronizan simultáneamente
- [ ] Reintentos con backoff: dispositivo offline → 3 intentos → falla registrada
- [ ] Sync nocturna completa a las 2:00 AM sin intervención manual
- [ ] Progreso granular visible en la UI durante sync activa
- [ ] Alertas de conectividad enviadas al admin tras 3 fallas consecutivas
- [ ] No existe referencia a "deduplicación entre dispositivos" como tarea pendiente (ya resuelto en Fase 1)
- [ ] No existe routing condicional por tipo de persona en ningún punto del código de sync

**El sistema está completo en todas las fases planificadas.**
