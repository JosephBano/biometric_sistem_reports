---
title: "Requisito — Analítica de entradas y salidas por persona con filtro opcional por grupo funcional"
status: draft
created: 2026-07-27
updated: 2026-07-27
authors: [producto, documenter]
related:
  - "[[ADR-0003-horarios-por-rol-funcional]]"
  - "[[ARQUITECTURA]]"
  - "[[API]]"
  - "[[ER]]"
---

# Requisito — Analítica de entradas y salidas por persona con filtro opcional por grupo funcional

> **Estado**: draft (2026-07-27). Este documento **no es un ADR** y **no decide
> el modelo de horarios**. Registra un requisito de analítica que **consume**
> (pero no modifica) la decisión de [[ADR-0003-horarios-por-rol-funcional]].
> Si el ADR 0003 no se aprueba, este requisito se reduce al escenario
> `feature_flag=off` (búsqueda por persona únicamente).

## Problema

El operador del sistema necesita una vista analítica que responda:

> "¿Cuáles fueron las entradas y salidas de una persona (o de un grupo funcional
> completo) en un rango de fechas?"

Hoy el sistema tiene:

- `app/domain/analytics.py::resumen_periodo` → resumen agregado por persona en un periodo.
- `app/web/analytics_bp.py` → endpoints `/analytics*` y `/api/analytics*`.

Pero **no existe** una vista tabular cronológica de entradas/salidas filtrable
por `grupo funcional` cuando el tenant lo tenga implementado. El usuario
confirmó este requisito el 2026-07-27 como dependencia funcional del ADR 0003.

## Alcance

### En alcance (v1)

1. **Consulta por rango de fechas**: cualquier par `fecha_inicio <= fecha <= fecha_fin` (inclusive).
2. **Filtro por grupo funcional** cuando el tenant tenga `tenant.configuracion['horario_por_grupo'] = true`:
   - El parámetro `grupo_funcional_id` aparece en la UI y en el endpoint.
   - Devuelve las entradas/salidas de **todas las personas** que tengan ese grupo funcional vigente en **algún día** del rango (unión, no intersección).
3. **Fallback a selector/buscador de persona** cuando:
   - El flag `horario_por_grupo` está `false` (legacy), **o**
   - El operador elige "Buscar persona" en la UI, **o**
   - El tenant no tiene `grupos_funcionales` cargados.
4. **Resultado**: lista de marcaciones (entradas y salidas) con timestamp, dispositivo, tipo
   (`entrada`/`salada`) y, si el flag está activo, la persona a la que pertenece.

### Fuera de alcance (v1)

- Cálculo de tardanzas, horas trabajadas o sanciones (ver `app.domain.analytics` para resumen agregado).
- Exportación a PDF/DOCX (la salida es HTML/JSON para la UI; el PDF/DOCX sigue yendo por `app.domain.reports`).
- Filtros combinados con `tipo_persona`, `categoria`, `sede` o `grupo` (operativo) para el endpoint
  de analytics. Estos filtros existen para la **asignación masiva** del ADR 0003, pero **no** se
  exponen en analítica en v1. Si surge la necesidad, se evalúa como P3.
- Gráficos o visualizaciones. Este requisito es **tabla**, no dashboard.

## Comportamiento esperado

### Caso A — Tenant con `horario_por_grupo = true` y `grupo_funcional_id` provisto

```text
GET /api/analytics/entradas-salidas?fecha_inicio=2026-07-01&fecha_fin=2026-07-31&grupo_funcional_id=<uuid>
```

- Resuelve: personas con `persona_grupos_funcionales.grupo_funcional_id = X` y `(fecha_inicio <= fecha_fin_rango) AND (fecha_fin IS NULL OR fecha_fin >= fecha_inicio_rango)`.
- Devuelve: lista de marcaciones del rango, ordenadas por `persona_id, timestamp`.

### Caso B — Tenant con `horario_por_grupo = false` o `grupo_funcional_id` ausente

```text
GET /api/analytics/entradas-salidas?fecha_inicio=2026-07-01&fecha_fin=2026-07-31&persona_id=<uuid>
```

- Resuelve: marcaciones de la persona indicada.
- La UI **no muestra** el filtro `grupo_funcional_id` (lo oculta o lo deshabilita).

### Caso C — Operador elige "Buscar persona" en la UI

- Abre un modal/buscador (similar al ya existente en `templates/personas/`).
- El endpoint recibe `persona_id` (no `grupo_funcional_id`).
- El flag del tenant se ignora.

### Caso D — Combinación inválida

- Si el flag está `false` y llega `grupo_funcional_id` → 400 con código `grupo_funcional_no_disponible`.
- Si el flag está `true` pero no llega ni `grupo_funcional_id` ni `persona_id` → 400 con código `filtro_requerido`.

## RBAC

| Caso | Rol mínimo |
|---|---|
| Lectura de sus propias marcaciones | `gestor`, `admin`, `superadmin` (con filtro por tenant del usuario) |
| Lectura de marcaciones de cualquier persona | `admin`, `superadmin` |
| Lectura cruzada entre grupos funcionales | `admin`, `superadmin` |

Los `supervisor_grupo` y `supervisor_periodo` **no** se incluyen en v1 para
este endpoint. Si se requiere, se evalúa en P3 (usar el mismo patrón de
filtrado por `configuracion.supervisor_grupo_id` que el resto de la app).

## Auditoría

- Toda llamada al endpoint registra 1 fila en `public.audit_log` con
  `accion='analytics_entradas_salidas_consultar'` y `detalle={filtros, count_resultados}`.
- Sin PII del detalle de marcaciones en el log (solo el resumen).

## Dependencias

- **Bloqueante**: el modelo de horarios resuelto por `resolver_horario_vigente`
  (ADR 0003, Fase 3) **no es necesario** para este requisito, porque la consulta
  es por `asistencias` (marcaciones) y no por horarios. El requisito funciona
  con o sin el ADR 0003 implementado.
- **Nice-to-have**: cuando el ADR 0003 esté implementado, la UI puede mostrar
  junto a cada persona "Grupo funcional: Profesor" como anotación.
- **Sin dependencia con migración Alembic**: el endpoint opera sobre tablas
  ya existentes (`asistencias`, `personas`, `dispositivos`).

## UI mínima propuesta (v1)

- Botón en el dashboard o en `/analytics` → "Entradas y salidas por persona".
- Form con: `fecha_inicio` (date), `fecha_fin` (date), y **uno de**:
  - `select grupo_funcional` (visible solo si `horario_por_Grupo = true` en el tenant), **o**
  - `select persona` con buscador (siempre visible).
- Tabla de resultados: `persona` | `timestamp` | `tipo` | `dispositivo`.
- Paginación server-side (50 filas por página).

## Validación

- **VA1**: con `horario_por_grupo=false`, el endpoint devuelve 200 con `persona_id` y 400 con `grupo_funcional_id`.
- **VA2**: con `horario_por_grupo=true` y `grupo_funcional_id` válido, devuelve la unión de personas que tuvieron ese grupo funcional en **algún día** del rango.
- **VA3**: la respuesta del endpoint es estable ante migraciones del ADR 0003 (los campos de salida no cambian si el flag se activa después).
- **VA4**: las marcaciones devueltas coinciden con `SELECT * FROM <tenant>.asistencias WHERE persona_id IN (...) AND timestamp BETWEEN ? AND ?` (verificable con `EXPLAIN` y un diff de 50 filas).

## No-objetivos

- **No** redefine la precedencia de horarios (eso es el ADR 0003).
- **No** introduce nuevos decoradores (`@require_grupo_funcional` no se crea en v1, tampoco para analítica).
- **No** agrega cache Redis ni optimizaciones de rendimiento (la consulta es directa y acotada por rango + paginación).

## Preguntas abiertas (no bloquean el draft)

- **PA1**: ¿La UI debe recordar el último `grupo_funcional_id` seleccionado por tenant? (recomendado: sí, en `localStorage`).
- **PA2**: ¿El resultado debe permitir ordenar por `persona` o por `timestamp`? (recomendado: ambos, con toggle).
- **PA3**: ¿Se requiere exportar el resultado a CSV? (recomendado: no en v1, se evalúa en P3).

## Decisión registrada

> **Decisión 2026-07-27**: el alcance analítico se registra como **requisito separado** del ADR 0003. No se mezcla con la decisión de horarios. El requisito funciona independientemente del ADR 0003 (con `grupo_funcional_id` opcional, y siempre con `persona_id` como fallback). El ADR 0003 solo **habilita** el parámetro `grupo_funcional_id` cuando el flag está activo; no lo exige.

## Relacionado

- `[[ADR-0003-horarios-por-rol-funcional]]` — Modelo de horarios por grupo funcional. Este requisito es **consumidor** de esa información cuando está activa, pero no depende de su implementación.
- `[[ARQUITECTURA]]` — Capas de la app y reglas de dependency.
- `[[API]]` — Inventario de rutas (este requisito agrega 1 ruta: `GET /api/analytics/entradas-salidas`).
- `[[ER]]` — Tabla `<tenant>.asistencias` (fuente de marcaciones).
