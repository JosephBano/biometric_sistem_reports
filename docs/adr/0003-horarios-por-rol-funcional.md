---
title: "ADR-0003 — Horarios por grupo funcional con override individual, precedencia explícita y compatibilidad hacia atrás"
tags: [adr, arquitectura, horarios, multi-tenant, grupos-funcionales, grupos-laborales]
status: proposed
created: 2026-07-27
updated: 2026-07-27
deciders: [arquitecto, equipo ISTPET]
consulted: [docs/ER.md, docs/AUTENTICACION.md, docs/ARQUITECTURA.md, app/domain/schedule.py, db/queries/horarios.py, db/queries/personas.py, db/queries/grupos.py, db/schema.py, app/web/schedule_bp.py]
supersedes: []
superseded_by: []
related: ["[[ARQUITECTURA]]", "[[AUTENTICACION]]", "[[ER]]", "[[ADR-0000-use-markdown-for-adrs]]", "[[ADR-0001-modularizacion-monolito-flask]]", "[[ADR-0002-sync-observable-y-backups]]", "[[requisito-analitica-grupo-funcional]]"]
---

# ADR-0003 — Horarios por grupo funcional con override individual, precedencia explícita y compatibilidad hacia atrás

> **Nota de nomenclatura (2026-07-27)**: este ADR originalmente se tituló
> "rol funcional". Por confirmación explícita del usuario, **se abandona el
> término "rol"** para este concepto y se reemplaza por **"grupo funcional"**
> (sinónimos aceptados: **"grupo laboral"**). El nombre del archivo se conserva
> para no romper wikilinks existentes; el título, las tablas, los DDL y el
> cuerpo del documento usan la nueva nomenclatura. Las referencias a
> `public.usuarios.roles` (RBAC de autenticación) **no se renombran** porque
> son una capa distinta y siguen llamándose "roles".

- **Status**: proposed
- **Date**: 2026-07-27
- **Deciders**: @arquitecto, equipo ISTPET
- **Consulted**: `docs/ER.md`, `docs/AUTENTICACION.md`, `docs/ARQUITECTURA.md`, `app/domain/schedule.py`, `db/queries/horarios.py`, `db/queries/personas.py`, `db/queries/grupos.py`, `db/schema.py`, `app/web/schedule_bp.py`

## Context and Problem Statement

El sistema actual (`biometric_sistem_reports`, Flask 3 + PostgreSQL 16 multi-tenant por schema) modela horarios como **asignaciones 1:1 persona-plantilla**:

- `tenant.plantillas_horario` es reutilizable (lunes/martes/.../domingo, entradas y salidas, almuerzo, horas_semana/horas_mes).
- `tenant.asignaciones_horario` registra `(persona_id, plantilla_id, fecha_inicio, fecha_fin, ciclo_semanas, posicion_ciclo)`. En la práctica operativa del proyecto, `ciclo_semanas=1` y cada persona tiene una plantilla 1:1 sembrada con `fecha_inicio='2024-01-01'` y `fecha_fin=NULL` (ver `db/queries/horarios.py::upsert_horarios`).
- El importador de archivos `.obd/.ods/.csv` (`app/domain/attendance.py::parsear_obd`, `parsear_csv` + `app/web/schedule_bp.py::cargar_horarios`) crea o actualiza estas asignaciones masivamente por `id_usuario` ZK.
- Los **roles de autenticación** viven en `public.usuarios.roles` = `superadmin/admin/gestor/supervisor_grupo/supervisor_periodo/readonly` (ver `docs/AUTENTICACION.md`). **No se renombran ni se tocan** en este ADR.
- Los **tipos de persona** viven en `tenant.tipos_persona` (Empleado, Practicante, Visitante) y son **dimensión institucional** que activa features de UI (decorador `@require_tipo_persona`).
- Las **categorías** viven en `tenant.categorias` con FK opcional a `tipos_persona` (sub-clasificación).
- El **grupo operativo** es `tenant.grupos` (con FK `personas.grupo_id`) y representa agrupación departamental/operativa. El supervisor de grupo (`@require_role("supervisor_grupo")`) filtra por este eje. Es **una dimensión distinta** del nuevo "grupo funcional" que define este ADR.
- `personas` tiene FK a `tipo_persona_id`, `grupo_id` (operativo), `categoria_id`, `sede_id` (ver `db/schema.py` líneas 180-193).

**El problema concreto** que motiva este ADR es **la ausencia de la abstracción "grupo funcional/laboral"** que el operador del sistema necesita:

1. **No existe "grupo funcional de la persona" como concepto de primera clase**. Una persona tiene `tipo_persona_id` (Empleado/Practicante/...) y `categoria_id`, pero ninguno de los dos modela bien "el grupo laboral que define su horario por defecto". Mezclar `tipos_persona` con horario obliga a reescribir la semántica de UI (`@require_tipo_persona`) y además `tipos_persona` es por tenant y muy cambiante (reglamento interno, legislación).
2. **No hay "horario por defecto por grupo laboral"**. Para cambiar el horario de todos los "administrativos" hay que iterar persona por persona. No hay una capa que diga "el grupo laboral X usa la plantilla Y en este rango".
3. **El horario de la persona debe poder personalizarse con vigencia explícita** (`fecha_inicio` y `fecha_fin`), y ese horario personalizado debe ganar sobre el horario predeterminado del grupo funcional al que pertenece.
4. **No hay precedencia explícita**. Una persona puede pertenecer a varios grupos funcionales simultáneamente (ej. `Profesor` y `Coordinador`); no hay regla documentada de qué horario aplicar. Hoy el modelo no garantiza que una persona tenga 1:1 con un grupo, por lo que se necesita desempate explícito.
5. **No hay asignación masiva con filtros combinados**. El importador es 1:1 por `id_usuario`. Se necesita poder aplicar un horario por defecto a un conjunto definido por `grupo funcional`, `grupo operativo`, `tipo de persona`, `categoría` y `sede`.
6. **No hay "override individual" explícito**. Hoy el override se hace "actualizando la asignación 1:1" — no se distingue entre "esta persona usa el default del grupo pero lo cambió" y "esta persona siempre tuvo horario propio".
7. **El dispositivo biométrico (ZK/Hikvision) no se ve afectado** porque solo guarda marcaciones (`asistencias`); el cálculo de horario aplicable ocurre en el motor de reportes al generar PDF/DOCX/analytics.

El objetivo es introducir un modelo que permita:

- (1) definir un **horario predeterminado por grupo funcional/laboral** (no por `tipo_persona`, no por `categoria`, no por `grupo` operativo);
- (2) aplicar **override individual explícito** con `fecha_inicio`/`fecha_fin` para personas que no respeten el default;
- (3) **resolver la ambigüedad** cuando una persona pertenece a varios grupos funcionales;
- (4) **asignación masiva** con filtros por `grupo funcional`, `grupo` (operativo), `tipo de persona`, `categoría` y `sede`;
- (5) **vigencias y precedencia** auditables;
- (6) **mantener el motor de reportes y el biométrico** funcionando sin cambio disruptivo;
- (7) **compatibilidad total hacia atrás** + **rollout/rollback seguro** de la migración de BD.

> **Decisión crítica ya resuelta**: el concepto se llama **`grupo_funcional`** (sinónimo aceptado: `grupo_laboral`). Ejemplos confirmados por el usuario: `Profesor`, `Administrativo`, `Trabajador`. **No** se llama "rol funcional" para evitar colisión con `public.usuarios.roles` (RBAC). Una persona puede pertenecer a **N grupos funcionales simultáneamente** y se resuelve por prioridad/desempate.

## Decision Drivers

- **D1 — Cero regresión para tenants existentes**. Los datos en producción (asignaciones 1:1) deben seguir resolviendo exactamente igual aunque el nuevo modelo esté desplegado.
- **D2 — Compatibilidad con `tipos_persona`, `categorias`, `sedes` y `grupos` (operativo)**. Cada uno es una dimensión existente con semántica propia. El "grupo funcional" no debe mezclarse ni reemplazar a ninguno.
- **D3 — Distinción explícita `grupos` (operativo) vs `grupos_funcionales` (laboral)**. Ambos conviven en el modelo. Una persona tiene **un grupo operativo** (su departamento) y puede tener **N grupos funcionales** (sus roles laborales). El supervisor de grupo opera sobre `grupos`; el horario se resuelve por `grupos_funcionales`.
- **D4 — Compatibilidad con `public.usuarios.roles`**. El RBAC de la app (superadmin/admin/gestor/...) **no se renombra ni se toca**. Son capas distintas: autenticación vs. operación.
- **D5 — Feature flag por tenant**. Activación gradual tenant-por-tenant, no global, con rollback trivial.
- **D6 — Migración de BD reversible**. La migración Alembic debe ser aditiva (solo `CREATE TABLE` + `ALTER TABLE ADD COLUMN` nullable) y el `downgrade` debe dejar la BD exactamente como estaba.
- **D7 — Resolución de horario con punto único de verdad**. Una sola función `resolver_horario_vigente(persona_id, fecha)` debe encapsular la precedencia. El motor de reportes, el histórico de persona y la UI consultan esa función; nadie lee `asignaciones_horario` directamente para "el horario actual".
- **D8 — Vigencias y solapamientos con regla explícita**. El modelo debe representar `fecha_inicio`/`fecha_fin` en (a) la relación persona↔grupo_funcional, (b) el default grupo_funcional↔plantilla, (c) el override persona↔plantilla, y resolver empates con una regla documentada (no implícita).
- **D9 — Rendimiento aceptable sin cache obligatorio**. 3-4 lecturas por `(persona_id, fecha)` con índices correctos es aceptable para v1; Redis es opcional (P3).
- **D10 — Auditoría**: el sistema debe poder responder "¿por qué esta persona tiene este horario en esta fecha?" → la precedencia debe dejar traza del origen (`override | default_grupo | legacy_1a1 | sin_horario`).
- **D11 — Operatividad**: el importador `.obd/.csv` debe seguir funcionando sin cambio de contrato (no romper integraciones externas con archivos existentes).
- **D12 — Override ≥ Default**: el horario personalizado de la persona (override) tiene **prioridad absoluta** sobre el horario predeterminado del grupo funcional; ambos deben poder tener `fecha_inicio`/`fecha_fin`.

## Considered Options

### Opción A — Usar `tenant.tipos_persona` como "grupo funcional"

Reutilizar la tabla `tipos_persona` ya existente: cada tipo tiene una plantilla por defecto y el `persona.tipo_persona_id` resuelve el horario.

- ✅ No agrega tabla nueva; reusa algo que ya existe.
- ✅ Cada tenant ya tiene su catálogo de tipos.
- ❌ **Rompe la semántica de `@require_tipo_persona`**: hoy el tipo decide qué features de UI están disponibles (workflow de Practicantes con contrato, etc.). Mezclarlo con horario obliga a elegir entre "este tipo está habilitado pero no tiene horario" o "este tipo obliga a tener horario".
- ❌ **Hace 1:1 tipo-plantilla**: si una institución tiene 5 tipos y 3 turnos por tipo, son 15 plantillas atadas al tipo. Cambiar el horario de "Practicante" afecta a TODOS los practicantes, incluso a los del grupo "Becarios" que tienen horario distinto. Pierde la granularidad que se necesita.
- ❌ **`tipos_persona` es muy cambiante** (reglamento interno, legislación, decisiones de RRHH) y **el horario es más estable**. Acoplarlos obliga a versionar el horario cada vez que se ajusta un tipo.
- ❌ **No resuelve "override individual"** porque no hay una capa entre el tipo y la persona donde ponerlo (la asignación persona-plantilla ya existe, no es override).
- ❌ **No resuelve "varios grupos funcionales"**: el `tipo_persona_id` ya es 1:1 con la persona. Si se quiere que "este Practicante además haga tareas de Operativo", no hay dónde ponerlo.

> **Rechazada**: viola D2 (semántica de `tipos_persona`) y D7-D8 (no hay override ni precedencia).

### Opción B — Columna nueva `personas.grupo_funcional_id` (FK a `tenant.grupos_funcionales`)

Agregar tabla `grupos_funcionales` y una sola FK en `personas`.

- ✅ Simple: una FK, un índice.
- ✅ El "grupo funcional" es una dimensión ortogonal a `tipo_persona`, `categoria`, `sede` y `grupo` (operativo).
- ❌ **No permite que una persona tenga varios grupos funcionales simultáneamente** (caso real: un `Profesor` que también es `Coordinador` o un `Administrativo` que rota como `Trabajador` por temporada).
- ❌ **No resuelve "vigencias"** del grupo en la persona: ¿qué pasa si el grupo cambia con fecha? Hay que versionar la persona completa o aceptar que el cambio es retroactivo.
- ❌ **No escala** si en el futuro se quiere "una persona con N grupos funcionales" (requisito confirmado por el usuario).

> **Rechazada** por caso confirmado (P2): se requiere N:M con vigencia.

### Opción C (recomendada) — Cuatro tablas nuevas en el schema del tenant: `grupos_funcionales`, `persona_grupos_funcionales` (N:M con vigencia), `horarios_default_grupo` y `overrides_horario_persona`

Cuatro tablas nuevas en cada schema de tenant + 2 columnas aditivas en `plantillas_horario` y `asignaciones_horario`. Feature flag por tenant.

- ✅ **Ortogonal a `tipos_persona`, `categorias`, `sedes` y `grupos` (operativo)**: el "grupo funcional" es una dimensión nueva, no reemplaza nada.
- ✅ **Permite N grupos funcionales por persona con vigencia** (`fecha_inicio`/`fecha_fin`).
- ✅ **Override individual explícito** con `fecha_inicio`/`fecha_fin` (D12).
- ✅ **Default por grupo funcional** con prioridad: si un grupo tiene varios defaults (ej. horario de verano/invierno), la precedencia por `prioridad DESC, fecha_inicio DESC` los desempata.
- ✅ **Precedencia unificada y documentada**: override > default_grupo > legacy 1:1 > sin_horario.
- ✅ **Feature flag por tenant**: el admin activa `tenant.configuracion['horario_por_grupo']=true` cuando está listo; sin activación, comportamiento legacy.
- ✅ **Migración Alembic aditiva**: solo `CREATE TABLE` + `ADD COLUMN NULLABLE`. Downgrade trivial.
- ✅ **Auditoría**: la función `resolver_horario_vigente` retorna `{plantilla, origen, grupo_funcional_id?, override_id?}` y la UI puede mostrar "Origen del horario".
- ✅ **Asignación masiva natural** con filtros combinados: "todos los del grupo operativo G con grupo funcional X desde fecha F" = insertar N filas en `persona_grupos_funcionales` (no se itera `asignaciones_horario` por persona).
- ❌ **Más superficie de UI**: hay que crear 3 vistas de gestión (grupos funcionales, defaults por grupo, overrides).

> **Recomendada**. Cubre D1–D12 sin imponer restricciones fuertes.

### Opción D — Múltiples columnas en `personas` (`grupo_funcional1_id`, `grupo_funcional2_id`, `grupo_funcional3_id`)

Hardcodear hasta 3 grupos funcionales por persona con columnas NULL-able.

- ❌ **Anti-patrón relacional**: número mágico 3, no escala, queries más complejas.
- ❌ **No admite overrides** (es una sola capa).

> **Rechazada de plano**.

### Opción E — Híbrido: `tipos_persona` con atributo JSONB `horario_default_plantilla_id`

Añadir `configuracion JSONB` a `tipos_persona` y guardar la plantilla por defecto allí.

- ❌ **JSONB con FK lógica**: integridad referencial se pierde (no se puede `JOIN`).
- ❌ **No resuelve el override individual** (sigue siendo 1:1 persona-plantilla).
- ❌ **Mezcla semántica** de tipo con horario (mismo problema que A).

> **Rechazada**.

## Decision Outcome

**Se adopta la Opción C**: **4 tablas nuevas en cada schema de tenant** (`grupos_funcionales`, `persona_grupos_funcionales`, `horarios_default_grupo`, `overrides_horario_persona`) + **2 columnas aditivas** (`plantillas_horario.es_default_grupo`, `plantillas_horario.grupo_funcional_id`, `asignaciones_horario.origen`) + feature flag por tenant (`tenant.configuracion['horario_por_grupo']`).

**Nombre del nuevo concepto: `grupo_funcional`** (sinónimo operativo: `grupo_laboral`). Ejemplos semilla confirmados por el usuario: `Profesor`, `Administrativo`, `Trabajador`. **No** se llama "rol" para evitar colisión con `public.usuarios.roles`.

**Precedencia canónica** de resolución (de mayor a menor prioridad) para una persona P en una fecha D:

```
1. OVERRIDE: ¿Existe fila en overrides_horario_persona
   con persona_id=P, fecha_inicio<=D, (fecha_fin IS NULL OR fecha_fin>=D)?
   → Sí: usar la plantilla de esa fila. origen='override'.
2. DEFAULT_GRUPO: ¿Cuántos grupos_funcionales activos tiene P en D
   (filas en persona_grupos_funcionales con es_principal=true o
    sin es_principal + desempate por tenant.configuracion['horario_desempate'])?
   → Si hay 1 o más: para cada grupo funcional activo, buscar el default
     vigente en horarios_default_grupo (prioridad DESC, fecha_inicio DESC).
     El de mayor prioridad global gana. origen='default_grupo',
     y se registra grupo_funcional_id usado.
3. LEGACY: ¿Existe fila en asignaciones_horario con persona_id=P,
   ciclo_semanas=1, fecha_inicio<=D, (fecha_fin IS NULL OR fecha_fin>=D),
   y origen='historico_legacy' (o cualquier origen que no sea override/default)?
   → Sí: usar la plantilla de esa fila. origen='legacy_1a1'.
4. SIN_HORARIO: no hay match. origen='sin_horario'.
   El motor de reportes trata a la persona como "sin horario definido"
   (mismo comportamiento que hoy cuando una persona no está en
   asignaciones_horario).
```

Regla de **desempate** (paso 2 con varios grupos funcionales) configurable en
`tenant.configuracion['horario_desempate']` ∈ {`prioridad`, `orden_grupo`, `error`}.
Default sugerido: `prioridad` con fallback a `orden_grupo` en empate.

### Modelo de datos (resumen)

#### Nuevas tablas en cada `<tenant>`:

```sql
-- Catálogo de grupos funcionales (laborales) del tenant.
-- Ortogonal a tenant.grupos (operativo/departamental).
CREATE TABLE grupos_funcionales (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo          TEXT NOT NULL,            -- 'profesor', 'administrativo', 'trabajador', ...
    nombre          TEXT NOT NULL,
    descripcion     TEXT,
    color           TEXT,
    orden           INTEGER NOT NULL DEFAULT 0,
    activo          BOOLEAN NOT NULL DEFAULT true,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (codigo)
);

-- N:M persona ↔ grupo funcional con vigencia y marca de principal.
-- Una persona puede tener varios grupos_funcionales activos simultáneamente.
CREATE TABLE persona_grupos_funcionales (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id          UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    grupo_funcional_id  UUID NOT NULL REFERENCES grupos_funcionales(id) ON DELETE RESTRICT,
    fecha_inicio        DATE NOT NULL,
    fecha_fin           DATE,
    es_principal        BOOLEAN NOT NULL DEFAULT false,
    notas               TEXT,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, grupo_funcional_id, fecha_inicio)
);
CREATE INDEX idx_pgf_persona_vigente
    ON persona_grupos_funcionales (persona_id, fecha_inicio DESC)
    WHERE fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE;

-- Horario por defecto por grupo funcional (con prioridad y vigencia).
CREATE TABLE horarios_default_grupo (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grupo_funcional_id  UUID NOT NULL REFERENCES grupos_funcionales(id) ON DELETE CASCADE,
    plantilla_id        UUID NOT NULL REFERENCES plantillas_horario(id) ON DELETE RESTRICT,
    fecha_inicio        DATE NOT NULL,
    fecha_fin           DATE,
    prioridad           INTEGER NOT NULL DEFAULT 0,
    notas               TEXT,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (grupo_funcional_id, plantilla_id, fecha_inicio)
);
CREATE INDEX idx_hdg_grupo_vigente
    ON horarios_default_grupo (grupo_funcional_id, prioridad DESC, fecha_inicio DESC)
    WHERE fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE;

-- Override individual: esta persona usa esta plantilla, ignorando el default
-- del grupo funcional. fecha_inicio y fecha_fin son obligatorios para cierre
-- explícito (no se usa DELETE para mantener histórico).
CREATE TABLE overrides_horario_persona (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id    UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    plantilla_id  UUID NOT NULL REFERENCES plantillas_horario(id) ON DELETE RESTRICT,
    fecha_inicio  DATE NOT NULL,
    fecha_fin     DATE,
    motivo        TEXT,
    creado_por    UUID REFERENCES public.usuarios(id) ON DELETE SET NULL,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, plantilla_id, fecha_inicio)
);
CREATE INDEX idx_ohp_persona_vigente
    ON overrides_horario_persona (persona_id, fecha_inicio DESC)
    WHERE fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE;
```

#### Columnas aditivas (compatibilidad):

```sql
ALTER TABLE plantillas_horario
    ADD COLUMN IF NOT EXISTS es_default_grupo BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS grupo_funcional_id UUID REFERENCES grupos_funcionales(id) ON DELETE SET NULL;

ALTER TABLE asignaciones_horario
    ADD COLUMN IF NOT EXISTS origen TEXT NOT NULL DEFAULT 'historico_legacy'
        CHECK (origen IN ('historico_legacy', 'override_migrado', 'asignacion_directa'));
```

> Nota: la columna `plantillas_horario.grupo_funcional_id` se crea **después** de `grupos_funcionales` (orden de migración). La columna `es_default_grupo` es redundante con la presencia de filas en `horarios_default_grupo` que la apunten; se mantiene como "denormalización para UI rápida" pero **es derivada** (se actualiza vía trigger o aplicación). Decisión: usar **trigger** `AFTER INSERT/UPDATE/DELETE` en `horarios_default_grupo` que mantenga `es_default_grupo` sincronizada.

### Resolución de la ambigüedad (lo que este ADR fija)

| Concepto | Dónde vive | Semántica | RBAC | Cambia con |
|---|---|---|---|---|
| **Rol de autenticación** | `public.usuarios.roles` (TEXT[]) | Quién puede hacer qué en la app | `@require_role(...)` | `admin` lo gestiona |
| **Tipo de persona** | `tenant.tipos_persona` | Categoría institucional (Empleado, Practicante) | `@require_tipo_persona(...)` | `admin` lo gestiona |
| **Categoría** | `tenant.categorias` | Sub-clasificación dentro del tipo | n/a (no usado en RBAC) | `admin` lo gestiona |
| **Sede** | `tenant.sedes` + `personas.sede_id` | Ubicación física | n/a (filtro de asignaciones) | `admin` lo gestiona |
| **Grupo (operativo)** | `tenant.grupos` + `personas.grupo_id` | Agrupación operativa/departamental (1 grupo por persona) | `@require_role("supervisor_grupo")` filtra por `configuracion.supervisor_grupo_id` | `admin` lo gestiona |
| **Grupo funcional / laboral** (NUEVO) | `tenant.grupos_funcionales` + `tenant.persona_grupos_funcionales` | Define el horario por defecto de la persona (N por persona, con vigencia) | ninguno (no es RBAC) | `admin` lo gestiona |

**Clave de la separación — cuatro dimensiones ortogonales sobre la persona**:

1. **Tipo de persona** (`Empleado`, `Practicante`): categoría institucional → activa features de UI.
2. **Categoría** (`Junior`, `Senior`, `Becario`): sub-clasificación dentro del tipo.
3. **Sede** (`Norte`, `Sur`, `Matriz`): ubicación física, filtra asignación masiva.
4. **Grupo (operativo)** (`Departamento de Física`, `Departamento de Sistemas`): agrupación departamental, **1 por persona** aunque el modelo no lo garantiza. Sirve para `@require_role("supervisor_grupo")`.
5. **Grupo funcional / laboral** (`Profesor`, `Administrativo`, `Trabajador`): **N por persona con vigencia**. Define el horario por defecto. Es el único de los cinco que decide horario.

> **Por qué no se usa `tipos_persona` como el grupo funcional**: ver Opción A arriba. Resumen: `tipos_persona` activa features de UI (`@require_tipo_persona`), es 1:1 con la persona por convención, y es muy cambiante. Mezclarlo con horario rompe la semántica de los decoradores existentes y obliga a reescribir la lógica de features. El grupo funcional es una dimensión **nueva y ortogonal** específicamente para el horario.

> **Por qué no se usa `grupos` (operativo) como grupo funcional**: `grupos` representa una jerarquía departamento→persona y sirve para supervisores. Forzar "el grupo del que depende la persona define su horario" acoplaría dos responsabilidades distintas (supervisión y horario) y bloquearía el caso real de una persona que pertenece a un departamento pero cubre funciones de múltiples grupos laborales.

### Función canónica de resolución

```python
# app/domain/schedule.py (extensión)
def resolver_horario_vigente(
    persona_id: str,
    fecha: date,
    *,
    feature_flag: bool | None = None,  # si None, lee de tenant.configuracion
) -> dict:
    """
    Retorna el horario aplicable a la persona en la fecha.

    Returns:
        {
            "plantilla_id": str | None,
            "plantilla": dict | None,   # misma forma que get_horario_en_fecha
            "origen": "override" | "default_grupo" | "legacy_1a1" | "sin_horario",
            "grupo_funcional_id": str | None,   # si origen='default_grupo'
            "override_id": str | None,          # si origen='override'
            "asignacion_legacy_id": str | None, # si origen='legacy_1a1'
            "regla_desempate": str | None,      # si hubo desempate
        }
    """
```

Implementación interna (esqueleto, no se entrega en este ADR):

1. Si `feature_flag` es `False` (o el tenant no lo activó): leer `asignaciones_horario` con `ciclo_semanas=1` y misma lógica que `db/queries/horarios.py::get_horario_en_fecha` actual → retorna `origen='legacy_1a1'`.
2. Si `feature_flag` es `True`: aplicar la precedencia 1-2-3-4 de la sección anterior.
3. La función **es única** y se invoca desde el motor de reportes (`app.domain.reports`), desde la UI de histórico de persona y desde el endpoint de "resolver horario" para que la respuesta sea consistente.

### Reglas funcionales explícitas

| # | Regla | Implementación |
|---|---|---|
| R1 | El **override siempre gana** sobre el default del grupo funcional. El override tiene `fecha_inicio` obligatoria y puede tener `fecha_fin` para vigencia acotada. | Paso 1 de la precedencia. |
| R2 | Un **grupo funcional por defecto tiene prioridad**; el de mayor `prioridad` gana si hay varios en la misma fecha. | ORDER BY `prioridad DESC, fecha_inicio DESC` en `horarios_default_grupo`. |
| R3 | Una **persona con varios grupos funcionales activos sin `es_principal`** se resuelve por la política `horario_desempate` del tenant. | `tenant.configuracion['horario_desempate']` ∈ {`prioridad`, `orden_grupo`, `error`}. Default: `prioridad`. |
| R4 | Una persona **sin grupo funcional y sin asignación legacy** se trata como "sin horario" (mismo comportamiento actual). | Paso 4. |
| R5 | **Una persona sin override y con un solo grupo funcional activo** recibe el default de ese grupo. | Paso 2 con count=1. |
| R6 | El **importador `.obd/.csv` legacy** sigue creando `asignaciones_horario` con `origen='historico_legacy'`. No se cambia el contrato. | Sin cambio en `app/web/schedule_bp.py::cargar_horarios`. |
| R7 | **Cerrar** un override, un default o una asignación persona↔grupo funcional se hace con `fecha_fin`, no con DELETE. Mantiene histórico. | Enforced por aplicación. |
| R8 | **RBAC**: gestión de grupos funcionales, defaults y overrides requiere `admin` o `superadmin`. La lectura está abierta a `gestor` también. | Decorar endpoints con `@require_role("admin", "superadmin", "gestor")` para lectura; `@require_role("admin", "superadmin")` para escritura. |
| R9 | **Auditoría**: cada cambio de override, default o relación persona↔grupo funcional se registra en `public.audit_log` con `accion='horario_override_crear/cerrar'`, `accion='horario_default_crear/cerrar'`, `accion='persona_grupo_funcional_asignar/cerrar'`. | Wrap en `db.queries.audit_log` (ya existe). |
| R10 | **Multi-tenant estricto**: todas las tablas nuevas viven en el schema del tenant. El feature flag vive en `tenant.configuracion` JSONB (per-tenant). | Decisión cerrada: en `tenant` (no en `public`) porque la feature es operativa, no de plataforma. |
| R11 | **Asignación masiva con filtros combinados**: la operación masiva acepta combinaciones de `grupo_funcional_id`, `grupo_id` (operativo), `tipo_persona_id`, `categoria_id`, `sede_id`. | Endpoint `/api/personas/aplicar-grupo-funcional-default` con body `{filtros: {...}, grupo_funcional_id, plantilla_id, fecha_inicio, fecha_fin?}` (ver Implementation Plan). |
| R12 | **El horario personalizado de la persona (override) tiene prioridad absoluta** sobre el default del grupo funcional. Ambos honoran `fecha_inicio`/`fecha_fin`. | Precedencia paso 1 + D12. |

## Confirmation Log (decisiones cerradas 2026-07-27)

Estas preguntas estaban abiertas en versiones anteriores del ADR. Quedan **confirmadas** por el usuario el 2026-07-27 y se cierran como parte del estado `proposed`:

| # | Pregunta original | Respuesta confirmada | Sección de referencia |
|---|---|---|---|
| **P1** | Denominación del nuevo concepto | **`grupo_funcional`** (sinónimo: `grupo_laboral`). Se abandona "rol funcional". | "Context and Problem Statement", "Decision Outcome" |
| **P2** | ¿Una persona puede tener varios grupos funcionales simultáneamente? | **Sí, 1:N con vigencia** (`persona_grupos_funcionales`). | "Decision Drivers" D2, "Considered Options" C |
| **P3** | Política de desempate cuando una persona tiene varios grupos funcionales sin `es_principal` | **`prioridad`** (default), con fallback a `orden_grupo` en empate. Configurable en `tenant.configuracion['horario_desempate']`. | "Decision Outcome", R3 |
| **P4** | ¿Mantener `asignaciones_horario` con `ciclo_semanas=1` como fuente válida indefinidamente? | **Sí**, como paso 3 de la precedencia. Rollback trivial. | "Decision Outcome", R6 |
| **P5** | Asignación masiva: ¿propaga al grupo funcional de las personas o crea overrides individuales? | **Propaga al grupo funcional** (más mantenible). El endpoint acepta filtros combinados: `grupo_funcional`, `grupo` (operativo), `tipo_persona`, `categoria`, `sede`. | R11, "Implementation Plan" Fase 2 |
| **P6** | Catálogo inicial de grupos funcionales (seed) | Confirmado por el usuario: `Profesor`, `Administrativo`, `Trabajador` (los definitivos se ajustan en plan). | "Implementation Plan" Fase 1 |
| **P7** | ¿Quién puede gestionar grupos funcionales, defaults y overrides? | Lectura: `gestor`, `admin`, `superadmin`. Escritura: `admin`, `superadmin`. | R8 |
| **P8** | ¿Reportes deben mostrar la "fuente del horario"? | **Sí**, como columna "Origen" en PDF/DOCX y en UI de histórico. | "Decision Outcome" (función canónica) |
| **P9** | ¿Dónde vive el feature flag `horario_por_grupo`? | **`tenant.configuracion` JSONB** (per-tenant). | R10 |
| **P10** | ¿El decorador `@require_grupo_funcional(nombre)` es necesario en v1? | **No** en v1. Se evalúa en P3 si surge necesidad. | "Consequences — Neutrales" |

**Recomendaciones de seguridad, auditoría, feature flag y rollout gradual**: **aceptadas** (R8, R9, R10, feature flag por tenant, rollout piloto en `istpet` — ver "Implementation Plan" Fase 6).

## Consequences

**Positivas**

- El operador del sistema puede cambiar el horario de "todos los administrativos" tocando 1 fila en `horarios_default_grupo` en lugar de N filas en `asignaciones_horario`.
- Una persona con horario excepcional (ej. médico con turno nocturno) tiene un **override explícito** con `fecha_inicio`/`fecha_fin` que se distingue de la asignación por defecto. La UI puede mostrar "Origen: override" vs "Origen: default del grupo Administrativo".
- Las **vigencias** son de primera clase. Un cambio de horario para "todos los docentes a partir del 1 de marzo" se modela con `fecha_inicio='2026-03-01'` en `horarios_default_grupo` o en `overrides_horario_persona`.
- El **horario personalizado de la persona tiene prioridad absoluta** sobre el default del grupo funcional (D12, R1, R12).
- La **precedencia está documentada y testeada**: tests parametrizados en `tests/unit/test_schedule_resolver.py` con casos: solo legacy, solo default, override+pasa-de-fecha, varios grupos funcionales sin principal, override que cierra y devuelve el default, etc.
- **Rollout seguro**: feature flag por tenant permite activar en 1 piloto (istpet), validar 1 semana, extender. Rollback = poner el flag en `false` y reiniciar el proceso (no requiere migración).
- **Compatibilidad total hacia atrás**: tenants con asignaciones 1:1 que nunca activen la feature ven exactamente el mismo comportamiento.
- **Separación limpia de conceptos**: `tipos_persona` (UI), `categorias` (sub-clasificación), `sedes` (ubicación), `grupos` (operativo/departamental), `grupos_funcionales` (horario), `public.usuarios.roles` (RBAC). Seis capas, ninguna acoplada.
- **Asignación masiva potente**: filtros combinables por `grupo_funcional`, `grupo` (operativo), `tipo_persona`, `categoria`, `sede` permiten workflows de RRHH reales (ej. "todos los administrativos de la sede Norte con grupo funcional Profesor desde 2026-08-01").

**Negativas / costos**

- 4 tablas nuevas por schema de tenant + 2 columnas aditivas → más DDL que mantener; el ADR-0002 (sync observable) ya documenta que el equipo está cómodo con esta superficie.
- Más superficie de UI: 4 vistas de gestión (grupos funcionales, defaults por grupo, overrides, asignación masiva con filtros).
- El motor de reportes (`script.py` / `app.domain.reports`) debe migrar de leer `asignaciones_horario` directamente a llamar `resolver_horario_vigente`. Es 1 función nueva, pero toca la ruta caliente de generación de PDFs.
- El **importador `.obd/.csv`** sigue creando `asignaciones_horario` con `origen='historico_legacy'`. Esto significa que un operador que carga un `.obd` con el flag activo seguirá viendo "horario del legacy" en lugar del default del grupo funcional. **Decisión documentada**: si el operador quiere que el importador use el modelo nuevo, debe pasar `modo='override'` en la llamada. El default es backward-compatible.

**Neutrales**

- No se introduce Repository pattern ni ORM declarativo. La capa `db/queries/*` se mantiene intacta y se añade un módulo `db/queries/grupos_funcionales.py` + `db/queries/horarios_resolucion.py`.
- No se introduce Redis. La precedencia resuelve en 3-4 queries a PostgreSQL con índices. v1 mide y, si es cuello de botella, se añade cache en P3.
- No se renombra `asignaciones_horario` ni `plantillas_horario`. La columna `origen` documenta la proveniencia.
- El decorador `@require_tipo_persona` se mantiene. **No se crea `@require_grupo_funcional`** en v1; si el equipo lo necesita en P3, se evalúa.

**Riesgos a vigilar**

- **R-A — Activación prematura del feature flag**: si el admin lo activa sin configurar defaults, todas las personas sin override que tenían asignación legacy pasan a "sin horario" en los reportes. Mitigación: la función de resolución **siempre cae al paso 3 (legacy)** si no hay default; nunca degrada a "sin_horario" sin haber agotado las opciones. UI debe advertir "Tienes N personas sin default configurado" antes de activar.
- **R-B — Datos de auditoría con flag activo**: si el motor de reportes lee vía `resolver_horario_vigente` y se cambia un default, los reportes del mismo día pero generados después del cambio pueden diferir. Mitigación: los reportes firmados (PDF) llevan timestamp; el cambio de horario por defecto se registra en `public.audit_log` con `detalle={antes, despues}`.
- **R-C — Multi-tenant con catálogo divergente**: cada tenant tiene su propio `grupos_funcionales`. Un admin que gestiona 5 tenants debe aprender 5 catálogos. Mitigación: el seed inicial propuesto (P6) es razonable para la mayoría; los tenants con necesidades especiales lo ajustan.
- **R-D — Confusión entre `grupos` (operativo) y `grupos_funcionales` (laboral)**: ambos usan la palabra "grupo" viven en `tenant.*`. Mitigación: tabla de ambigüedad explícita en este ADR; nomenclatura consistente `grupo_funcional` / `grupo_laboral` en código y docs; **no** se usa jamás "rol" para este concepto; el endpoint de asignación masiva los pide por separado (`grupo_id` vs `grupo_funcional_id`).
- **R-E — Override implícito vs explícito**: una persona puede tener una asignación en `asignaciones_horario` con `origen='historico_legacy'` y también un `overrides_horario_persona`. Si el override no tiene `fecha_inicio`/`fecha_fin` bien seteados, podría no inválidar la legacy. Mitigación: tests E2E que cubran solapamientos y la regla R1.

## Pre-requisito operacional (bloqueante hasta validar)

Esta ADR describe una migración Alembic (`0010`) y un rollout por fases. **No debe ejecutarse `alembic upgrade head` en producción** mientras no estén cerradas, validadas y documentadas las tres pre-condiciones siguientes. Saltarlas es el riesgo operacional más alto de esta decisión y se documenta aquí para que el cambio de status `proposed → accepted` no se apruebe sin ellas.

1. **Alembic como única fuente de verdad** (cierre de la **Fase −1** del roadmap de [[ARQUITECTURA]] → "Fase −1 — Red de seguridad de datos"). Hoy `db/init.py::init_db()` ejecuta DDL propio en cada arranque del contenedor mientras `db/migrations/versions/0001-0008` (Alembic) **no se ejecuta en el deploy** (ver [[ADR-0001-modularizacion-monolito-flask]] → P1 bloqueante y [[ARQUITECTURA]] → "Migraciones duales"). Hasta que `alembic upgrade head` sea paso explícito del deploy y `init_db` solo ejecute seed, una migración nueva puede divergir del DDL que `init_db` aplica en el siguiente arranque (especialmente con `ADD COLUMN` que pueden colisionar si `init_db` los reescribe). La migración `0010` se escribe asumiendo que Fase −1 está cerrada; **si aún no lo está, la implementación de esta ADR queda bloqueada hasta cerrarla**.
2. **Backup verificado inmediatamente antes de la migración**. Antes de `alembic upgrade head` en cualquier tenant de producción, debe existir un dump `pg_dump -Fc` reciente en `/data/backups`, generado por el job de [[ADR-0002-sync-observable-y-backups]], y un `pg_restore` probado contra una BD limpia en los últimos 30 días (ver [[OPERATIONS]] → "Restauración de emergencia"). Sin dump reciente y restore probado, no se aprueba la ventana de deploy.
3. **Rollback ensayado en staging en la misma corrida**. Tras `alembic upgrade head` en staging, debe ejecutarse `alembic downgrade -1` y verificar —con `pg_dump --schema-only` y diff— que el schema queda **exactamente igual** al estado pre-`0010` (sin las 4 tablas nuevas y sin las 2 columnas aditivas). El ensayo se documenta en el runbook de release con timestamp y diff adjunto. Sin ensayo exitoso, no se promueve la migración a producción.

> **Conclusión**: la implementación de esta ADR **no arranca la Fase 2 en adelante** hasta confirmar los 3 puntos anteriores para el primer tenant piloto (`istpet`). Si Fase −1 no está cerrada a nivel de plataforma, esta ADR permanece en `proposed` y su prioridad se reordena después del cierre de Fase −1. Esta sección prevalece sobre el "Implementation Plan" siguiente: ningún paso del plan se ejecuta si los 3 puntos no están `OK` en el runbook de release.

> **Condición adicional para `proposed → accepted`**: además de los 3 puntos anteriores, debe existir un **plan de ejecución detallado** en `docs/superpowers/plans/` (estilo `2026-07-01-adr-0001-refactor-monolito-flask.md`) y una **validación técnica** documentada (al menos: `alembic upgrade head` + `downgrade -1` en staging con diff adjuntado, y suite de tests del resolver verde). Hasta que ambas existan, el status permanece `proposed`.

## Implementation Plan

El plan se ejecuta como **6 fases de PRs pequeños y reversibles**. Cada fase termina con `alembic upgrade head` en staging + smoke test manual + 1 commit.

### Fase 1 — Migración Alembic 0010 (½ día, sin cambio de comportamiento)

**Archivos**:

- Nuevo: `db/migrations/versions/0010_horarios_por_grupo_funcional.py`
- Sin cambio de código de aplicación.

**DDL**: solo el bloque "Nuevas tablas" + "Columnas aditivas" de la sección anterior, **dentro de un loop por tenant activo** (igual que 0001). `down_revision = "0009"`. `downgrade()`: `DROP TABLE` + `DROP COLUMN`.

**Seed opcional** (comentado, no se ejecuta por default): catálogo inicial de grupos funcionales (`Profesor`, `Administrativo`, `Trabajador`) — ver P6.

**Validación**:
- `alembic upgrade head` en staging.
- `alembic downgrade -1` deja la BD en estado pre-0010 (verificar con `\d grupos_funcionales` y `\d plantillas_horario`).
- Sin cambio observable en producción tras el deploy (feature flag en `false`).

### Fase 2 — Endpoints de gestión (1-2 días, sin cambio de comportamiento)

**Archivos**:

- `app/domain/grupos_funcionales.py` (CRUD puro).
- `app/domain/horarios_default_grupo.py` (CRUD puro).
- `app/domain/horarios_override.py` (CRUD puro).
- `app/domain/persona_grupo_funcional.py` (CRUD de la relación persona↔grupo funcional con vigencia).
- `app/web/grupos_funcionales_bp.py` (Blueprint, registro en `app/web/__init__.py`).
- `db/queries/grupos_funcionales.py`, `db/queries/horarios_default_grupo.py`, `db/queries/horarios_override.py`, `db/queries/persona_grupo_funcional.py` (capa de datos, SQL parametrizado).
- `tests/unit/test_grupos_funcionales.py`, `tests/unit/test_horarios_default_grupo.py`, `tests/unit/test_horarios_override.py`, `tests/unit/test_persona_grupo_funcional.py`.

**Endpoints** (sin auth nueva: usan los decoradores existentes):

| Método | Ruta | Rol mínimo | Acción |
|---|---|---|---|
| GET | `/api/grupos-funcionales` | gestor | Lista |
| POST | `/api/grupos-funcionales` | admin | Crea |
| PUT | `/api/grupos-funcionales/<id>` | admin | Actualiza |
| DELETE | `/api/grupos-funcionales/<id>` | admin | Desactiva (soft) |
| GET | `/api/horarios-default-grupo` | gestor | Lista por grupo funcional/fecha |
| POST | `/api/horarios-default-grupo` | admin | Crea |
| PUT | `/api/horarios-default-grupo/<id>` | admin | Cierra (`fecha_fin=today`) |
| GET | `/api/horarios-override?persona_id=...` | gestor | Lista por persona |
| POST | `/api/horarios-override` | admin | Crea |
| PUT | `/api/horarios-override/<id>` | admin | Cierra |
| POST | `/api/personas/<id>/grupos-funcionales` | admin | Asigna grupo funcional a persona (con `fecha_inicio`/`fecha_fin`) |
| DELETE | `/api/personas/<id>/grupos-funcionales/<grupo_id>` | admin | Cierra (`fecha_fin=today`) |
| POST | `/api/asignacion-masiva/grupo-funcional` | admin | Asignación masiva con filtros combinados (ver R11) |

**Endpoint de asignación masiva** (R11):

```
POST /api/asignacion-masiva/grupo-funcional
Rol: admin / superadmin
Body:
{
  "filtros": {
    "grupo_funcional_id": "...",   // opcional
    "grupo_id": "...",             // operativo, opcional
    "tipo_persona_id": "...",      // opcional
    "categoria_id": "...",         // opcional
    "sede_id": "..."               // opcional
  },
  "grupo_funcional_id_destino": "...",   // grupo funcional a aplicar
  "plantilla_id": "...",
  "fecha_inicio": "2026-08-01",
  "fecha_fin": null,              // opcional, default null = vigente
  "modo": "asignar_grupo_funcional"      // o "crear_override"
}
```

Si `modo=asignar_grupo_funcional`: crea N filas en `persona_grupos_funcionales` para las personas que matchean los filtros (excluyendo las que ya tienen ese grupo funcional vigente). Si `modo=crear_override`: crea N filas en `overrides_horario_persona` (más rígido, desaconsejado, se conserva como opción).

**Validación**: `pytest tests/unit/test_*` verde. Smoke: crear 1 grupo funcional, 1 default, asignar a 1 persona vía API con `curl` + token CSRF. Smoke de asignación masiva con filtro por `grupo_id` operativo. Sin cambio en flujos existentes.

### Fase 3 — `resolver_horario_vigente` y feature flag (1 día)

**Archivos**:

- `app/domain/schedule.py` (extensión): nueva función pública `resolver_horario_vigente` documentada arriba.
- `db/queries/horarios_resolucion.py`: queries que la función consume (overrides activos, grupos funcionales activos por persona, defaults por grupo con prioridad, legacy).
- `app/tenant.py` (extensión): helper `get_horario_por_grupo_enabled()` que lee `g.tenant.configuracion['horario_por_grupo']`.
- `app/domain/reports.py` (1 punto de cambio): sustituir la lectura directa de `asignaciones_horario` por `resolver_horario_vigente(persona_id, fecha)` en el hot path de generación de PDF/DOCX.
- `tests/unit/test_schedule_resolver.py`: casos parametrizados.

**Feature flag**:

```python
# tenant.configuracion JSONB
{
    "horario_por_grupo": false,          # default: false
    "horario_desempate": "prioridad",     # 'prioridad' | 'orden_grupo' | 'error'
    "horario_seed_version": 0             # incrementa cuando el admin acepta el seed inicial
}
```

**Validación**:

- Con flag `false`: 100% de los tenants ven exactamente el mismo horario que antes (test A/B comparando el output de `resolver_horario_vigente` vs `get_horario_en_fecha` para 100 personas aleatorias durante 30 días).
- Con flag `true` y sin defaults configurados: 100% cae a "legacy_1a1" (sin cambio observable).
- Con flag `true` y 1 default configurado para 1 grupo funcional: solo las personas con ese grupo se desvían del legacy.

### Fase 4 — UI mínima (1-2 días)

**Archivos**:

- `templates/admin/grupos_funcionales.html` (lista + form de creación).
- `templates/admin/horarios_default_grupo.html` (matriz grupo funcional ↔ plantilla + vigencia).
- `templates/personas/horario_override.html` (CRUD override por persona con `fecha_inicio`/`fecha_fin`).
- `templates/personas/grupos_funcionales.html` (gestión de la relación persona↔grupo funcional con vigencia).
- `templates/admin/asignacion_masiva.html` (form con los 5 filtros combinables + preview de personas afectadas).
- `static/js/grupos_funcionales.js`, `static/js/horarios_default_grupo.js`, `static/js/horario_override.js`, `static/js/asignacion_masiva.js`.
- `templates/personas/historico.html` (extensión): añadir columna "Origen del horario" en la tabla de días analizados.

**Validación**: screenshots de los 4 flujos; un admin puede completar el ciclo "crear grupo funcional → crear default → asignar grupo funcional a 5 personas → ver que el reporte las trata con ese horario" y "crear override con fecha_inicio/fecha_fin para una persona y comprobar que el reporte lo aplica con prioridad".

### Fase 5 — Script de migración de datos opcional (½-1 día, no se ejecuta automáticamente)

**Archivos**:

- `scripts/migrar_asignaciones_a_defaults.py`: analiza las `asignaciones_horario` con `ciclo_semanas=1, origen='historico_legacy'`, agrupa por `(tipo_persona_id, grupo_id, sede_id, plantilla_id)` y propone un CSV con: `tenant_slug, plantilla_id_representante, count_personas, suggested_grupo_funcional_nombre, suggested_default_fecha_inicio`.
- **No escribe en BD**: solo emite el reporte. El admin lo revisa y decide.
- Si el admin aprueba, se ejecuta un segundo script `aplicar_migracion_propuesta.py` que crea `grupos_funcionales`, `horarios_default_grupo` y `persona_grupos_funcionales` en bulk.

**Validación**: diff de `resolver_horario_vigente` antes/después para 100 personas → debe ser idéntico.

### Fase 6 — Rollout controlado (continuo)

1. **Pilot**: activar `horario_por_grupo=true` en `istpet` (tenant por defecto). Monitor durante 1 semana.
2. **Comparación A/B**: correr el motor de reportes con flag `true` y con flag `false` en paralelo sobre el mismo período; diff de los PDFs resultantes (excluyendo timestamps).
3. **Extensión**: activar en tenants adicionales bajo demanda. Cada activación se documenta en `public.audit_log` con `accion='horario_por_grupo_activar', detalle={tenant_slug, fecha}`.
4. **Rollback**: poner `horario_por_grupo=false` en el tenant. Sin migración de BD. Sin reinicio obligatorio (la función lee el flag en cada llamada).

## Validation

Criterios observables que confirman que la decisión se ejecutó correctamente:

- **V1 — Migración reversible**: `alembic upgrade head && alembic downgrade -1` ejecutado en staging deja la BD **exactamente igual** que antes (verificar con `pg_dump --schema-only` diff).
- **V2 — Backward compatibility al 100%**: con `horario_por_grupo=false` en TODOS los tenants, los reportes PDF generados en 2026-W30 (semana del deploy) son byte-idénticos a los generados en 2026-W29. Verificación automatizada en CI.
- **V3 — Función única de resolución**: `grep -rn "asignaciones_horario" app/domain/ | grep -v test` muestra 0 ocurrencias fuera de `db/queries/horarios.py` y `app/domain/schedule.py::resolver_horario_vigente`. Toda lectura operativa del horario actual pasa por la función.
- **V4 — Feature flag funciona**: test e2e con 1 tenant con flag `true` y 1 con flag `false` produce salidas distintas si el tenant con flag activo tiene defaults configurados, e idénticas si no los tiene.
- **V5 — Auditoría**: cada cambio de override, default o relación persona↔grupo funcional crea 1 fila en `public.audit_log` con `detalle={antes, despues}`; cada activación del feature flag crea 1 fila con `accion='horario_por_grupo_activar'`.
- **V6 — Índices correctos**: `EXPLAIN ANALYZE` de la query de resolución con datos de producción sintéticos muestra `Index Scan` en los 3 índices nuevos (no `Seq Scan`).
- **V7 — UI usable**: un admin nuevo (sin training) puede: crear 1 grupo funcional, asignarlo a 1 persona, crear 1 default por grupo, generar 1 reporte PDF, en menos de 10 minutos (medible con test de usabilidad ligero, no obligatorio para v1).
- **V8 — Override gana**: tests E2E confirman que un `overrides_horario_persona` con `fecha_inicio<=D<fecha_fin` **siempre** anula el default del grupo funcional, independientemente de la `prioridad` del grupo.
- **V9 — Filtros de asignación masiva**: tests E2E confirman que `/api/asignacion-masiva/grupo-funcional` con combinaciones de filtros (ej. `grupo_id` operativo + `sede_id`) afecta exactamente las personas esperadas.

## Follow-ups (backlog)

- **P3 — Backlog técnico** (importante, no urgente):
  - Añadir cache Redis para `resolver_horario_vigente` con TTL 60 s y clave `(persona_id, fecha)`. Solo si las métricas de CPU de los workers muestran que la resolución es cuello de botella. **Métricas a recoger en Fase 6** (rollout): p50/p95/p99 de la query.
  - Migrar `asignaciones_horario.ciclo_semanas > 1` (rotaciones cíclicas reales) al modelo nuevo. Hoy está modelado pero no usado operativamente; si un tenant lo necesita, requiere una decisión análoga a este ADR.
  - Versionado de la API: introducir `/api/v2/horarios-resolver` con la nueva semántica; mantener `/api/v1/horarios` con la semántica legacy durante 1 release.
  - Auditoría visual: panel "Cambios recientes de horario" para `admin` que liste los últimos N cambios de override/default con `quien`, `cuando`, `antes/después`.

- **P4 — Backlog futuro**:
  - Si los tenants piden "cambiar el horario de un grupo entero de un día para otro" (caso soporte): endpoint `/api/grupos-funcionales/<id>/horario-temporal` que crea N overrides con `fecha_inicio` y `fecha_fin` acotados.
  - Si se quiere "rotación automática" (turnos 4x3, 5x2, etc.): modelar `plantillas_horario.es_rotativa` + tabla `rotaciones_horario` y ampliar `resolver_horario_vigente` con un paso 0. **Fuera del alcance de este ADR**.
  - Si se introduce Celery + multi-worker (Fase 6 del roadmap de [[ARQUITECTURA]]): cache distribuida y eventual consistency del feature flag.
  - Integración con el requisito de analítica: si el flag `horario_por_grupo` está activo, el endpoint de analytics puede filtrar por `grupo_funcional_id` directamente; si no, recae al selector/buscador de persona. Ver `[[requisito-analitica-grupo-funcional]]`.

## Documentos relacionados

- `[[ARQUITECTURA]]` — Documento principal de arquitectura. La Fase −1 (backups + Alembic único) es prerrequisito de este ADR.
- `[[AUTENTICACION]]` — El sistema de autenticación. Define `public.usuarios.roles` (RBAC) que **no se toca** en este ADR.
- `[[ER]]` — Modelo de datos actual; este ADR lo extiende.
- `[[ADR-0000-use-markdown-for-adrs]]` — Plantilla y convención usada para escribir este ADR.
- `[[ADR-0001-modularizacion-monolito-flask]]` — Reglas de capas (`app/domain/*` no importa `app/web/*`; `app/web/*` no importa `db/queries/*`). Las nuevas tablas respetan la regla: `app/domain/grupos_funcionales.py` consume `db/queries/grupos_funcionales.py`.
- `[[ADR-0002-sync-observable-y-backups]]` — El precedente más cercano: DDL aditivo en `db/migrations/versions/0009_scheduler_runs.py` con `down_revision = "0008"`. Este ADR sigue el mismo patrón (`0010` con `down_revision = "0009"`).
- `[[requisito-analitica-grupo-funcional]]` — Documento de requisitos para la consulta analítica de entradas/salidas (dependiente de este ADR pero con alcance propio).
