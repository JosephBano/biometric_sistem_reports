# Plan de Implementación — Fase 5: Analytics e IA
**Versión:** 2.0 — Analytics unificado por tipo de persona
**Fecha:** 2026-03-17
**Prerequisito:** Fases 1–4 v2 completadas y verificadas

---

## 1. Contexto y cambios respecto a v1

### 1.1 Qué cambia

La v1 tenía dos motores de analytics separados: `analytics.py` para empleados y `analytics_alumnos.py` para alumnos. Esta separación era una consecuencia del modelo de datos dual (módulos separados).

Con el modelo horizontal:
- Existe una sola tabla `asistencias`
- Todos los tipos de persona están en `personas`
- Los grupos son universales (departamentos, carreras, bloques → todos son `grupos`)

Esto permite un único motor de analytics con filtros por `tipo_persona_id`, `grupo_id`, `periodo_vigencia_id`.

| v1 | v2 |
|---|---|
| `analytics.py` (empleados) + `analytics_alumnos.py` | `analytics.py` unificado |
| Dimensiones: departamento, oficina, cargo | Dimensiones: grupo (cualquier nivel), categoría |
| Risk Score solo para empleados | Risk Score para cualquier tipo de persona |
| Separación por módulo | Filtros por tipo_persona_id |

### 1.2 Lo que no cambia

- Dependencias: pandas, numpy, requests
- DeepSeek API con fallback automático
- Risk Score 0-100 con semáforo
- Detección de anomalías estadísticas
- Integración con scheduler para alertas

---

## 2. Alcance

**Qué incluye:**
- `analytics.py` — Motor unificado de análisis estadístico
- `ia_report.py` — Reportes narrativos con DeepSeek API + fallback
- Análisis por dimensiones: grupo (cualquier nivel jerárquico), categoría, tipo de persona
- Risk Score por persona (0-100 con semáforo)
- Detección de anomalías estadísticas
- Analytics de cumplimiento por período (porcentual, para personas con fecha fin)
- Analytics de comportamiento continuo (tardanzas, patrones, para personas con período indefinido)
- Rutas API para exponer hallazgos
- Sección "Analytics" en la UI
- Alertas de riesgo integradas en el scheduler

**Qué NO incluye:**
- Dashboard interactivo con gráficos
- Text-to-SQL
- ML entrenado

---

## 3. Nuevas dependencias

```
pandas>=2.2
numpy>=1.26
```

`requests` ya disponible. Variable nueva: `DEEPSEEK_API_KEY` (opcional).

---

## 4. Datos disponibles para analytics

Con el modelo horizontal, `analytics.py` puede cruzar:

```
asistencias (persona_id, fecha_hora, tipo, periodo_vigencia_id)
  JOIN personas (tipo_persona_id, grupo_id, categoria_id)
  JOIN tipos_persona (nombre)
  JOIN grupos (nombre, padre_id)
  JOIN categorias (nombre)
  JOIN periodos_vigencia (fecha_inicio, fecha_fin, estado)
  JOIN asignaciones_horario + plantillas_horario
  JOIN feriados
```

Esto habilita análisis que la v1 no podía hacer: comparar comportamiento entre tipos de persona, entre grupos de diferentes niveles jerárquicos, entre categorías.

---

## 5. `analytics.py` — Motor unificado

### 5.1 Funciones de análisis de comportamiento continuo

Para personas con `periodo_vigencia.fecha_fin = NULL` (empleados indefinidos):

```python
calcular_risk_score(persona_id, fecha_inicio, fecha_fin) → int (0-100)
detectar_anomalias(grupo_id, fecha_inicio, fecha_fin) → list[dict]
patron_semanal(persona_id, semanas=8) → dict
comparar_grupos(grupo_ids, fecha_inicio, fecha_fin) → dict
ranking_departamento(grupo_id, fecha_inicio, fecha_fin) → list
tendencia_mensual(tipo_persona_id, meses=6) → list
```

### 5.2 Funciones de análisis de cumplimiento por período

Para personas con `periodo_vigencia.fecha_fin IS NOT NULL`:

```python
resumen_periodo(periodo_vigencia_id) → dict
distribucion_asistencia_periodo(periodo_vigencia_id) → dict
comparar_periodos_historicos(tipo_persona_id, n=5) → list
tasa_riesgo_por_grupo(grupo_id) → dict
```

### 5.3 Función central: `analizar(filtros)` 

Punto de entrada unificado que detecta el tipo de análisis según los filtros:

```python
def analizar(
    tipo_persona_id: str = None,
    grupo_id: str = None,
    periodo_vigencia_id: str = None,
    fecha_inicio: date = None,
    fecha_fin: date = None,
) -> dict:
    """
    Detecta automáticamente qué tipo de análisis corresponde
    y retorna el dict de hallazgos estandarizado.
    """
```

---

## 6. `ia_report.py` — Reportes narrativos

Sin cambios conceptuales respecto a la v1. El input es el dict de hallazgos de `analytics.py`. El output es texto narrativo.

```python
generar_narrativo(hallazgos: dict, contexto: str = "") → str
```

- Intenta con DeepSeek API si `DEEPSEEK_API_KEY` está configurada
- Fallback automático a generador textual basado en reglas si la API falla
- El narrativo es agnóstico al tipo de persona — describe los patrones en lenguaje natural

---

## 7. Integración en la UI

### 7.1 Sección Analytics

Nueva sección en la navegación (visible para `gestor` y `admin`):

- **Resumen del tenant:** risk scores de todas las personas, top 5 en riesgo
- **Por grupo:** comparación entre grupos del mismo nivel jerárquico
- **Por período:** cumplimiento de períodos activos y comparación con histórico
- **Reporte narrativo:** botón para generar el informe IA del período o rango seleccionado

### 7.2 Integración en reportes existentes

El Risk Score y el narrativo se pueden incluir opcionalmente al final de los PDFs existentes.

---

## 8. Pasos de implementación

### Paso 1 — Implementar `analytics.py` unificado

Empezar con las funciones de comportamiento continuo (las que ya existían para empleados), luego agregar las de cumplimiento por período.

**Verificación:** `analizar(grupo_id=X, fecha_inicio=Y, fecha_fin=Z)` retorna dict con hallazgos correctos.

### Paso 2 — Implementar `ia_report.py`

Implementar con fallback automático. Verificar sin API key (usa generador de reglas).

### Paso 3 — Rutas API de analytics

```
GET /analytics/resumen
GET /analytics/grupo/<id>
GET /analytics/periodo/<id>
POST /analytics/narrativo
```

### Paso 4 — Integración en UI

Sección Analytics con las vistas descritas en 7.1.

### Paso 5 — Alertas en scheduler

Agregar `generar_alertas_riesgo()` al scheduler nocturno. Usa `calcular_risk_score()` para todas las personas activas y notifica si alguna supera el umbral de riesgo.

---

## 9. Criterio de finalización

- [ ] `analytics.py` produce hallazgos correctos para personas con período indefinido y con período acotado
- [ ] `ia_report.py` genera narrativo con y sin API key
- [ ] Rutas API de analytics accesibles con los roles correctos
- [ ] Sección Analytics visible en la UI para `gestor` y `admin`
- [ ] Alertas de riesgo integradas en el scheduler nocturno
- [ ] Analytics funciona para cualquier `tipo_persona_id`, no solo para empleados
- [ ] No existen referencias a `analytics_alumnos.py` en el código

**Una vez completados estos criterios, el sistema está listo para la Fase 6 (Multi-institución y Multi-driver).**
