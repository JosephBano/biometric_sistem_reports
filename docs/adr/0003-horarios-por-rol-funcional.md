---
title: "ADR-0003 — Horarios por rol funcional con override individual, precedencia explícita y compatibilidad hacia atrás"
tags: [adr, arquitectura, horarios, multi-tenant, roles, rbac]
status: proposed
created: 2026-07-27
updated: 2026-07-27
deciders: [arquitecto]
consulted: [docs/ER.md, docs/AUTENTICACION.md, docs/ARQUITECTURA.md, app/domain/schedule.py, db/queries/horarios.py, db/queries/personas.py, db/queries/grupos.py, db/schema.py, app/web/schedule_bp.py]
supersedes: []
superseded_by: []
related: ["[[ARQUITECTURA]]", "[[AUTENTICACION]]", "[[ER]]", "[[ADR-0000-use-markdown-for-adrs]]", "[[ADR-0001-modularizacion-monolito-flask]]", "[[ADR-0002-sync-observable-y-backups]]"]
---

# ADR-0003 — Horarios por rol funcional con override individual, precedencia explícita y compatibilidad hacia atrás

- **Status**: proposed
- **Date**: 2026-07-27
- **Deciders**: @arquitecto, equipo ISTPET
- **Consulted**: `docs/ER.md`, `docs/AUTENTICACION.md`, `docs/ARQUITECTURA.md`, `app/domain/schedule.py`, `db/queries/horarios.py`, `db/queries/personas.py`, `db/queries/grupos.py`, `db/schema.py`, `app/web/schedule_bp.py`

## Context and Problem Statement

El sistema actual (`biometric_sistem_reports`, Flask 3 + PostgreSQL 16 multi-tenant por schema) modela horarios como **asignaciones 1:1 persona-plantilla**:

- `tenant.plantillas_horario` es reutilizable (lunes/martes/.../domingo, entradas y salidas, almuerzo, horas_semana/horas_mes).
- `tenant.asignaciones_horario` registra `(persona_id, plantilla_id, fecha_inicio, fecha_fin, ciclo_semanas, posicion_ciclo)`. En la práctica operativa del proyecto, `ciclo_semanas=1` y cada persona tiene una plantilla 1:1 sembrada con `fecha_inicio='2024-01-01'` y `fecha_fin=NULL` (ver `db/queries/horarios.py::upsert_horarios`).
- El importador de archivos `.obd/.ods/.csv` (`app/domain/attendance.py::parsear_obd`, `parsear_csv` + `app/web/schedule_bp.py::cargar_horarios`) crea o actualiza estas asignaciones masivamente por `id_usuario` ZK.
- Los **roles de autenticación** viven en `public.usuarios.roles` = `superadmin/admin/gestor/supervisor_grupo/supervisor_periodo/readonly` (ver `docs/AUTENTICACION.md`).
- Los **tipos de persona** viven en `tenant.tipos_persona` (Empleado, Practicante, Visitante) y son **dimensión institucional** que activa features de UI (decorador `@require_tipo_persona`).
- Las **categorías** viven en `tenant.categorias` con FK opcional a `tipos_persona` (sub-clasificación).
- `personas` tiene FK a `tipo_persona_id`, `grupo_id`, `categoria_id`, `sede_id` (ver `db/schema.py` líneas 180-193).

**El problema concreto** que motiva este ADR es **una ambigüedad semántica** entre tres cosas distintas que hoy se confunden y la **ausencia de la abstracción "rol funcional"** que el operador del sistema necesita:

1. **No existe "rol funcional de la persona" como concepto de primera clase**. Una persona tiene `tipo_persona_id` (Empleado/Practicante/...) y `categoria_id`, pero ninguno de los dos modela bien "el rol que define su horario por defecto". Mezclar `tipos_persona` con horario obliga a reescribir la semántica de UI (`@require_tipo_persona`) y además `tipos_persona` es por tenant y muy cambiante (reglamento interno, legislación).
2. **No hay "horario por defecto por rol"**. Para cambiar el horario de todos los "administrativos" hay que iterar persona por persona. No hay una capa que diga "el rol X usa la plantilla Y en este rango".
3. **No hay "override individual" explícito**. Hoy el override se hace "actualizando la asignación 1:1" — no se distingue entre "esta persona usa el default del rol pero lo cambió" y "esta persona siempre tuvo horario propio".
4. **No hay precedencia explícita**. Si una persona tiene varios `tipo_persona` o pertenece a varios `grupos`, no hay regla documentada de qué horario aplicar. (En la práctica la persona tiene 1 tipo y 0-1 grupos, pero el modelo no lo garantiza.)
5. **No hay asignación masiva por rol/grupo**; el importador es 1:1 por `id_usuario`.
6. **No hay vigencias reales**. `asignaciones_horario` tiene `fecha_inicio/fecha_fin` pero la práctica operativa siempre es `fecha_inicio='2024-01-01', fecha_fin=NULL`. El motor de reportes (`script.py` / `app.domain.reports`) lee "el primer match" sin auditar de dónde viene.
7. **El dispositivo biométrico (ZK/Hikvision) no se ve afectado** porque solo guarda marcaciones (`asistencias`); el cálculo de horario aplicable ocurre en el motor de reportes al generar PDF/DOCX/analytics.

El objetivo es introducir un modelo que permita:

- (1) definir un **horario predeterminado por un "rol funcional"** (no por `tipo_persona`, no por `categoria`);
- (2) aplicar **override individual** explícito para personas que no respeten el default;
- (3) **resolver la ambigüedad** cuando una persona pertenece a varios grupos/roles;
- (4) **asignación masiva** por rol, por grupo o por selección;
- (5) **vigencias y precedencia** auditables;
- (6) **mantener el motor de reportes y el biométrico** funcionando sin cambio disruptivo;
- (7) **compatibilidad total hacia atrás** + **rollout/rollback seguro** de la migración de BD.

> **Decisión crítica a resolver en este ADR**: ¿el "rol funcional" es `tipos_persona` ya existente, una columna nueva en `personas`, o una tabla nueva por tenant? Esta decisión afecta el modelo de datos, la UI, el RBAC y el rollout.

## Decision Drivers

- **D1 — Cero regresión para tenants existentes**. Los datos en producción (asignaciones 1:1) deben seguir resolviendo exactamente igual aunque el nuevo modelo esté desplegado.
- **D2 — Compatibilidad con `tipos_persona` y `categorias`**. Ambos son **dimensiones existentes con semántica propia** (UI y sub-clasificación respectivamente). El "rol funcional" no debe mezclarse ni reemplazar.
- **D3 — Compatibilidad con el modelo multi-tenant por schema**. La nueva estructura vive en el schema del tenant (no en `public`) porque cada tenant tiene su propio catálogo.
- **D4 — Compatibilidad con `public.usuarios.roles`**. El RBAC de la app (superadmin/admin/gestor/...) **no se renombra ni se toca**. Son capas distintas: autenticación vs. operación.
- **D5 — Feature flag por tenant**. Activación gradual tenant-por-tenant, no global, con rollback trivial.
- **D6 — Migración de BD reversible**. La migración Alembic debe ser aditiva (solo `CREATE TABLE` + `ALTER TABLE ADD COLUMN` nullable) y el `downgrade` debe dejar la BD exactamente como estaba.
- **D7 — Resolución de horario con punto único de verdad**. Una sola función `resolver_horario_vigente(persona_id, fecha)` debe encapsular la precedencia. El motor de reportes, el histórico de persona y la UI consultan esa función; nadie lee `asignaciones_horario` directamente para "el horario actual".
- **D8 — Vigencias y solapamientos con regla explícita**. El modelo debe representar `fecha_inicio`/`fecha_fin` y resolver empates con una regla documentada (no implícita).
- **D9 — Rendimiento aceptable sin cache obligatorio**. 3-4 lecturas por `(persona_id, fecha)` con índices correctos es aceptable para v1; Redis es opcional (P3).
- **D10 — Auditoría**: el sistema debe poder responder "¿por qué esta persona tiene este horario en esta fecha?" → la precedencia debe dejar traza del origen (`override | default_rol | legacy_1a1 | sin_horario`).
- **D11 — Operatividad**: el importador `.obd/.csv` debe seguir funcionando sin cambio de contrato (no romper integraciones externas con archivos existentes).

## Considered Options

### Opción A — Usar `tenant.tipos_persona` como "rol funcional"

Reutilizar la tabla `tipos_persona` ya existente: cada tipo tiene una plantilla por defecto y el `persona.tipo_persona_id` resuelve el horario.

- ✅ No agrega tabla nueva; reusa algo que ya existe.
- ✅ Cada tenant ya tiene su catálogo de tipos.
- ❌ **Rompe la semántica de `@require_tipo_persona`**: hoy el tipo decide qué features de UI están disponibles (workflow de Practicantes con contrato, etc.). Mezclarlo con horario obliga a elegir entre "este tipo está habilitado pero no tiene horario" o "este tipo obliga a tener horario".
- ❌ **Hace 1:1 tipo-plantilla**: si una institución tiene 5 tipos y 3 turnos por tipo, son 15 plantillas atadas al tipo. Cambiar el horario de "Practicante" afecta a TODOS los practicantes, incluso a los del grupo "Becarios" que tienen horario distinto. Pierde la granularidad que se necesita.
- ❌ **`tipos_persona` es muy cambiante** (reglamento interno, legislación, decisiones de RRHH) y **el horario es más estable**. Acoplarlos obliga a versionar el horario cada vez que se ajusta un tipo.
- ❌ **No resuelve "override individual"** porque no hay una capa entre el tipo y la persona donde ponerlo (la asignación persona-plantilla ya existe, no es override).
- ❌ **No resuelve "varios grupos/roles"**: el `tipo_persona_id` ya es 1:1 con la persona. Si se quiere que "este Practicante además haga tareas de Operativo", no hay dónde ponerlo.

> **Rechazada**: viola D2 (semántica de `tipos_persona`) y D7-D8 (no hay override ni precedencia).

### Opción B — Columna nueva `personas.rol_funcional_id` (FK a `tenant.roles_funcionales`)

Agregar tabla `roles_funcionales` y una sola FK en `personas`.

- ✅ Simple: una FK, un índice.
- ✅ El "rol funcional" es una dimensión ortogonal a `tipo_persona` y `categoria`.
- ❌ **No permite que una persona tenga varios roles simultáneamente** (poco realista: alguien que es "Docente" y "Coordinador" al mismo tiempo, o que rota entre "Operativo" y "Administrativo" por temporada).
- ❌ **No resuelve "vigencias"** del rol en la persona: ¿qué pasa si el rol cambia con fecha? Hay que versionar la persona completa o aceptar que el cambio es retroactivo.
- ❌ **No escala** si en el futuro se quiere "una persona con N roles" (que es el caso real de una universidad con docentes que también son coordinadores, tutores, investigadores).

> **Rechazada como opción única** por el caso P2 (ver Preguntas Abiertas). **Mantenida como fallback simplificado** si P2 se responde "no, 1:1 estricto".

### Opción C (recomendada) — Cuatro tablas nuevas en el schema del tenant: `roles_funcionales`, `persona_roles_funcionales` (N:M con vigencia), `horarios_default_rol` y `overrides_horario_persona`

Cuatro tablas nuevas en cada schema de tenant + 2 columnas aditivas en `plantillas_horario` y `asignaciones_horario`. Feature flag por tenant.

- ✅ **Ortogonal a `tipos_persona` y `categorias`**: el "rol funcional" es una dimensión nueva, no reemplaza nada.
- ✅ **Permite N roles por persona con vigencia** (`fecha_inicio`/`fecha_fin`).
- ✅ **Override individual explícito**: tabla dedicada con su propia vida.
- ✅ **Default por rol** con prioridad: si un rol tiene varios defaults (ej. horario de verano/invierno), la precedencia por `prioridad DESC, fecha_inicio DESC` los desempata.
- ✅ **Precedencia unificada y documentada**: override > default_rol > legacy 1:1 > sin_horario.
- ✅ **Feature flag por tenant**: el admin activa `tenant.configuracion['horario_por_rol']=true` cuando está listo; sin activación, comportamiento legacy.
- ✅ **Migración Alembic aditiva**: solo `CREATE TABLE` + `ADD COLUMN NULLABLE`. Downgrade trivial.
- ✅ **Auditoría**: la función `resolver_horario_vigente` retorna `{plantilla, origen, rol_funcional_id?, override_id?}` y la UI puede mostrar "Origen del horario".
- ✅ **Asignación masiva natural**: "todos los del grupo G con rol X desde fecha F" = insertar N filas en `persona_roles_funcionales` (no se itera `asignaciones_horario` por persona).
- ❌ **Más superficie de UI**: hay que crear 3 vistas de gestión (roles funcionales, defaults por rol, overrides).
- ❌ **Requiere responder P2, P3, P6, P7** (ver Preguntas Abiertas) antes de implementar.

> **Recomendada**. Cubre D1-D11 sin imponer restricciones fuertes en P2 (la N:M admite tanto 1:1 como N:M).

### Opción D — Múltiples columnas en `personas` (`rol1_id`, `rol2_id`, `rol3_id`)

Hardcodear hasta 3 roles por persona con columnas NULL-able.

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

**Se adopta la Opción C**: **4 tablas nuevas en cada schema de tenant** (`roles_funcionales`, `persona_roles_funcionales`, `horarios_default_rol`, `overrides_horario_persona`) + **2 columnas aditivas** (`plantillas_horario.es_default_rol`, `plantillas_horario.rol_funcional_id`, `asignaciones_horario.origen`) + feature flag por tenant (`tenant.configuracion['horario_por_rol']`).

**Nombre del nuevo concepto: `rol_funcional`** (ver P1 si se prefiere otro término).

**Precedencia canónica** de resolución (de mayor a menor prioridad) para una persona P en una fecha D:

```
1. OVERRIDE: ¿Existe fila en overrides_horario_persona
   con persona_id=P, fecha_inicio<=D, (fecha_fin IS NULL OR fecha_fin>=D)?
   → Sí: usar la plantilla de esa fila. origen='override'.
2. DEFAULT_ROL: ¿Cuántos roles_funcionales activos tiene P en D
   (filas en persona_roles_funcionales con es_principal=true o
    sin es_principal + desempate por tenant.configuracion['horario_desempate'])?
   → Si hay 1 o más: para cada rol activo, buscar el default vigente
     en horarios_default_rol (prioridad DESC, fecha_inicio DESC).
     El de mayor prioridad global gana. origen='default_rol',
     y se registra rol_funcional_id usado.
3. LEGACY: ¿Existe fila en asignaciones_horario con persona_id=P,
   ciclo_semanas=1, fecha_inicio<=D, (fecha_fin IS NULL OR fecha_fin>=D),
   y origen='historico_legacy' (o cualquier origen que no sea override/default)?
   → Sí: usar la plantilla de esa fila. origen='legacy_1a1'.
4. SIN_HORARIO: no hay match. origen='sin_horario'.
   El motor de reportes trata a la persona como "sin horario definido"
   (mismo comportamiento que hoy cuando una persona no está en
   asignaciones_horario).
```

Regla de **desempate** (paso 2 con varios roles) configurable en
`tenant.configuracion['horario_desempate']` ∈ {`prioridad`, `orden_rol`, `error`}.
Default sugerido: `prioridad` con fallback a `orden_rol` en empate.

### Modelo de datos (resumen)

#### Nuevas tablas en cada `<tenant>`:

```sql
-- Catálogo de roles funcionales del tenant
CREATE TABLE roles_funcionales (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo        TEXT NOT NULL,            -- 'operativo', 'administrativo', ...
    nombre        TEXT NOT NULL,
    descripcion   TEXT,
    color         TEXT,
    orden         INTEGER NOT NULL DEFAULT 0,
    activo        BOOLEAN NOT NULL DEFAULT true,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (codigo)
);

-- N:M persona ↔ rol funcional con vigencia y marca de principal
CREATE TABLE persona_roles_funcionales (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id      UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    rol_funcional_id UUID NOT NULL REFERENCES roles_funcionales(id) ON DELETE RESTRICT,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE,
    es_principal    BOOLEAN NOT NULL DEFAULT false,
    notas           TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, rol_funcional_id, fecha_inicio)
);
CREATE INDEX idx_prf_persona_vigente
    ON persona_roles_funcionales (persona_id, fecha_inicio DESC)
    WHERE fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE;

-- Horario por defecto por rol funcional (con prioridad y vigencia)
CREATE TABLE horarios_default_rol (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rol_funcional_id UUID NOT NULL REFERENCES roles_funcionales(id) ON DELETE CASCADE,
    plantilla_id    UUID NOT NULL REFERENCES plantillas_horario(id) ON DELETE RESTRICT,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE,
    prioridad       INTEGER NOT NULL DEFAULT 0,
    notas           TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rol_funcional_id, plantilla_id, fecha_inicio)
);
CREATE INDEX idx_hdr_rol_vigente
    ON horarios_default_rol (rol_funcional_id, prioridad DESC, fecha_inicio DESC)
    WHERE fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE;

-- Override individual (esta persona usa esta plantilla, ignorando el default del rol)
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
    ADD COLUMN IF NOT EXISTS es_default_rol BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS rol_funcional_id UUID REFERENCES roles_funcionales(id) ON DELETE SET NULL;

ALTER TABLE asignaciones_horario
    ADD COLUMN IF NOT EXISTS origen TEXT NOT NULL DEFAULT 'historico_legacy'
        CHECK (origen IN ('historico_legacy', 'override_migrado', 'asignacion_directa'));
```

> Nota: la columna `plantillas_horario.rol_funcional_id` se crea **después** de `roles_funcionales` (orden de migración). La columna `es_default_rol` es redundante con la presencia de filas en `horarios_default_rol` que la apunten; se mantiene como "denormalización para UI rápida" pero **es derivada** (se actualiza vía trigger o aplicación). Decisión: usar **trigger** `AFTER INSERT/UPDATE/DELETE` en `horarios_default_rol` que mantenga `es_default_rol` sincronizada.

### Resolución de la ambigüedad (lo que este ADR fija)

| Concepto | Dónde vive | Semántica | RBAC | Cambia con |
|---|---|---|---|---|
| **Rol de autenticación** | `public.usuarios.roles` (TEXT[]) | Quién puede hacer qué en la app | `@require_role(...)` | `admin` lo gestiona |
| **Tipo de persona** | `tenant.tipos_persona` | Categoría institucional (Empleado, Practicante) | `@require_tipo_persona(...)` | `admin` lo gestiona |
| **Categoría** | `tenant.categorias` | Sub-clasificación dentro del tipo | n/a (no usado en RBAC) | `admin` lo gestiona |
| **Rol funcional** (NUEVO) | `tenant.roles_funcionales` + `tenant.persona_roles_funcionales` | Define el horario por defecto de la persona | ninguno (no es RBAC) | `admin` lo gestiona |
| **Sede** | `tenant.sedes` + `personas.sede_id` | Ubicación física | n/a | `admin` lo gestiona |
| **Grupo** | `tenant.grupos` + `personas.grupo_id` | Agrupación operativa/departamental | `@require_role("supervisor_grupo")` filtra por `configuracion.supervisor_grupo_id` | `admin` lo gestiona |

**Clave de la separación**: el **rol funcional** no es RBAC ni categoría institucional. Es la dimensión que responde "¿qué horario aplica por defecto?". Un Practicante (tipo) puede tener rol funcional "Operativo" o "Administrativo" según el área donde rote; un Directivo (tipo) puede tener rol funcional "Directivo" con su propio horario. Las tres dimensiones (`tipo_persona`, `categoria`, `rol_funcional`) son **ortogonales** y combinables en una misma persona sin acoplarse.

> **Por qué no usar `tipos_persona` como el rol funcional**: ver Opción A arriba. Resumen: tipos_persona activa features de UI (`@require_tipo_persona`), es 1:1 con la persona por convención, y es muy cambiante. Mezclarlo con horario rompe la semántica de los decoradores existentes y obliga a reescribir la lógica de features. El rol funcional es una dimensión **nueva y ortogonal** específicamente para el horario.

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
            "origen": "override" | "default_rol" | "legacy_1a1" | "sin_horario",
            "rol_funcional_id": str | None,   # si origen='default_rol'
            "override_id": str | None,        # si origen='override'
            "asignacion_legacy_id": str | None,  # si origen='legacy_1a1'
            "regla_desempate": str | None,    # si hubo desempate
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
| R1 | El **override siempre gana** sobre el default del rol. | Paso 1 de la precedencia. |
| R2 | Un **rol funcional por defecto tiene prioridad**; el de mayor `prioridad` gana si hay varios en la misma fecha. | ORDER BY `prioridad DESC, fecha_inicio DESC` en `horarios_default_rol`. |
| R3 | Una **persona con varios roles sin `es_principal`** se resuelve por la política `horario_desempate` del tenant. | `tenant.configuracion['horario_desempate']` ∈ {`prioridad`, `orden_rol`, `error`}. Default: `prioridad`. |
| R4 | Una persona **sin rol funcional y sin asignación legacy** se trata como "sin horario" (mismo comportamiento actual). | Paso 4. |
| R5 | **Una persona sin override y con un solo rol activo** recibe el default de ese rol. | Paso 2 con count=1. |
| R6 | El **importador `.obd/.csv` legacy** sigue creando `asignaciones_horario` con `origen='historico_legacy'`. No se cambia el contrato. | Sin cambio en `app/web/schedule_bp.py::cargar_horarios`. |
| R7 | **Cerrar** un override o un default se hace con `fecha_fin`, no con DELETE. Mantiene histórico. | Enforced por aplicación. |
| R8 | **RBAC**: gestión de roles funcionales, defaults y overrides requiere `admin` o `superadmin`. La lectura está abierta a `gestor` también. | Decorar endpoints con `@require_role("admin", "superadmin", "gestor")` para lectura; `@require_role("admin", "superadmin")` para escritura. Sujeto a P7. |
| R9 | **Auditoría**: cada cambio de override se registra en `public.audit_log` con `accion='horario_override_crear/cerrar'`. | Wrap en `db.queries.audit_log` (ya existe). |
| R10 | **Multi-tenant estricto**: todas las tablas nuevas viven en el schema del tenant. El feature flag vive en `public.tenants.configuracion` (JSONB) o en `tenant.configuracion` JSONB per-tenant. **Decisión**: en `tenant` (no en `public`) porque la feature es operativa, no de plataforma. Sujeto a P9. |

## Consequences

**Positivas**

- El operador del sistema puede cambiar el horario de "todos los administrativos" tocando 1 fila en `horarios_default_rol` en lugar de N filas en `asignaciones_horario`.
- Una persona con horario excepcional (ej. médico con turno nocturno) tiene un **override explícito** que se distingue de la asignación por defecto. La UI puede mostrar "Origen: override" vs "Origen: default del rol Administrativo".
- Las **vigencias** son de primera clase. Un cambio de horario para "todos los docentes a partir del 1 de marzo" se modela con `fecha_inicio='2026-03-01'` en `horarios_default_rol` o en `overrides_horario_persona`.
- La **precedencia está documentada y testeada**: tests parametrizados en `tests/unit/test_schedule_resolver.py` con casos: solo legacy, solo default, override+pasa-de-fecha, varios roles sin principal, etc.
- **Rollout seguro**: feature flag por tenant permite activar en 1 piloto (istpet), validar 1 semana, extender. Rollback = poner el flag en `false` y reiniciar el proceso (no requiere migración).
- **Compatibilidad total hacia atrás**: tenants con asignaciones 1:1 que nunca activen la feature ven exactamente el mismo comportamiento.
- **Separación limpia de conceptos**: `tipos_persona` (UI), `roles_funcionales` (horario), `public.usuarios.roles` (RBAC). Cada uno en su capa, sin acoplar semánticas.

**Negativas / costos**

- 3 tablas nuevas por schema de tenant + 2 columnas aditivas → más DDL que mantener; el ADR-0002 (sync observable) ya documenta que el equipo está cómodo con esta superficie.
- Se necesita UI nueva para gestionar roles funcionales, defaults por rol y overrides. Estimado: 3 vistas + 1 matriz (no es 1 pantalla).
- Hay que **responder 8 preguntas de producto** (P1-P8) antes de implementar. Algunas son políticas (desempate, seeds) y otras son de alcance (P2).
- El motor de reportes (`script.py` / `app.domain.reports`) debe migrar de leer `asignaciones_horario` directamente a llamar `resolver_horario_vigente`. Es 1 función nueva, pero toca la ruta caliente de generación de PDFs.
- El **importador `.obd/.csv`** sigue creando `asignaciones_horario` con `origen='historico_legacy'`. Esto significa que un operador que carga un `.obd` con el flag activo seguirá viendo "horario del legacy" en lugar del default del rol. **Decisión documentada**: si el operador quiere que el importador use el modelo nuevo, debe pasar `modo='override'` en la llamada. El default es backward-compatible.

**Neutrales**

- No se introduce Repository pattern ni ORM declarativo. La capa `db/queries/*` se mantiene intacta y se añade un módulo `db/queries/roles_funcionales.py` + `db/queries/horarios_resolucion.py`.
- No se introduce Redis. La precedencia resuelve en 3-4 queries a PostgreSQL con índices. v1 mide y, si es cuello de botella, se añade cache en P3.
- No se renombra `asignaciones_horario` ni `plantillas_horario`. La columna `origen` documenta la proveniencia.
- El decorador `@require_tipo_persona` se mantiene. **No se crea `@require_rol_funcional`** en v1; si el equipo lo necesita en P3, se evalúa.

**Riesgos a vigilar**

- **R-A — Activación prematura del feature flag**: si el admin lo activa sin configurar defaults, todas las personas sin override que tenían asignación legacy pasan a "sin horario" en los reportes. Mitigación: la función de resolución **siempre cae al paso 3 (legacy)** si no hay default; nunca degrada a "sin_horario" sin haber agotado las opciones. UI debe advertir "Tienes N personas sin default configurado" antes de activar.
- **R-B — Datos de auditoría con flag activo**: si el motor de reportes lee vía `resolver_horario_vigente` y se cambia un default, los reportes del mismo día pero generados después del cambio pueden diferir. Mitigación: los reportes firmados (PDF) llevan timestamp; el cambio de horario por defecto se registra en `public.audit_log` con `detalle={antes, despues}`.
- **R-C — Multi-tenant con catálogo divergente**: cada tenant tiene su propio `roles_funcionales`. Un admin que gestiona 5 tenants debe aprender 5 catálogos. Mitigación: el seed inicial propuesto (P6) es razonable para la mayoría; los tenants con necesidades especiales lo ajustan.
- **R-D — Confusión con "rol de autenticación"**: el término "rol" aparece en dos capas (auth y funcional). Mitigación: documentación explícita con tabla (la de la sección anterior); nomenclatura consistente `rol_funcional` (nunca solo "rol" cuando se habla de horarios); no se renombra `public.usuarios.roles` para no romper nada.

## Pre-requisito operacional (bloqueante hasta validar)

Esta ADR describe una migración Alembic (`0010`) y un rollout por fases. **No debe ejecutarse `alembic upgrade head` en producción** mientras no estén cerradas, validadas y documentadas las tres pre-condiciones siguientes. Saltarlas es el riesgo operacional más alto de esta decisión y se documenta aquí para que el cambio de status `proposed → accepted` no se apruebe sin ellas.

1. **Alembic como única fuente de verdad** (cierre de la **Fase −1** del roadmap de [[ARQUITECTURA]] → "Fase −1 — Red de seguridad de datos"). Hoy `db/init.py::init_db()` ejecuta DDL propio en cada arranque del contenedor mientras `db/migrations/versions/0001-0008` (Alembic) **no se ejecuta en el deploy** (ver [[ADR-0001-modularizacion-monolito-flask]] → P1 bloqueante y [[ARQUITECTURA]] → "Migraciones duales"). Hasta que `alembic upgrade head` sea paso explícito del deploy y `init_db` solo ejecute seed, una migración nueva puede divergir del DDL que `init_db` aplica en el siguiente arranque (especialmente con `ADD COLUMN` que pueden colisionar si `init_db` los reescribe). La migración `0010` se escribe asumiendo que Fase −1 está cerrada; **si aún no lo está, la implementación de esta ADR queda bloqueada hasta cerrarla**.
2. **Backup verificado inmediatamente antes de la migración**. Antes de `alembic upgrade head` en cualquier tenant de producción, debe existir un dump `pg_dump -Fc` reciente en `/data/backups`, generado por el job de [[ADR-0002-sync-observable-y-backups]], y un `pg_restore` probado contra una BD limpia en los últimos 30 días (ver [[OPERATIONS]] → "Restauración de emergencia"). Sin dump reciente y restore probado, no se aprueba la ventana de deploy.
3. **Rollback ensayado en staging en la misma corrida**. Tras `alembic upgrade head` en staging, debe ejecutarse `alembic downgrade -1` y verificar —con `pg_dump --schema-only` y diff— que el schema queda **exactamente igual** al estado pre-`0010` (sin las 4 tablas nuevas y sin las 2 columnas aditivas). El ensayo se documenta en el runbook de release con timestamp y diff adjunto. Sin ensayo exitoso, no se promueve la migración a producción.

> **Conclusión**: la implementación de esta ADR **no arranca la Fase 2 en adelante** hasta confirmar los 3 puntos anteriores para el primer tenant piloto (`istpet`). Si Fase −1 no está cerrada a nivel de plataforma, esta ADR permanece en `proposed` y su prioridad se reordena después del cierre de Fase −1. Esta sección prevalece sobre el "Implementation Plan" siguiente: ningún paso del plan se ejecuta si los 3 puntos no están `OK` en el runbook de release.

## Implementation Plan

El plan se ejecuta como **5 fases de PRs pequeños y reversibles**. Cada fase termina con `alembic upgrade head` en staging + smoke test manual + 1 commit.

### Fase 1 — Migración Alembic 0010 (½ día, sin cambio de comportamiento)

**Archivos**:

- Nuevo: `db/migrations/versions/0010_horarios_por_rol_funcional.py`
- Sin cambio de código de aplicación.

**DDL**: solo el bloque "Nuevas tablas" + "Columnas aditivas" de la sección anterior, **dentro de un loop por tenant activo** (igual que 0001). `down_revision = "0009"`. `downgrade()`: `DROP TABLE` + `DROP COLUMN`.

**Seed opcional** (comentado, no se ejecuta por default): catálogo inicial de roles funcionales (`Operativo`, `Administrativo`, `Directivo`, `Limpieza`, `Seguridad`) — ver P6.

**Validación**:
- `alembic upgrade head` en staging.
- `alembic downgrade -1` deja la BD en estado pre-0010 (verificar con `\d roles_funcionales` y `\d plantillas_horario`).
- Sin cambio observable en producción tras el deploy (feature flag en `false`).

### Fase 2 — Endpoints de gestión (1-2 días, sin cambio de comportamiento)

**Archivos**:

- `app/domain/roles_funcionales.py` (CRUD puro).
- `app/domain/horarios_default.py` (CRUD puro).
- `app/domain/horarios_override.py` (CRUD puro).
- `app/web/roles_funcionales_bp.py` (Blueprint, registro en `app/web/__init__.py`).
- `db/queries/roles_funcionales.py`, `db/queries/horarios_default.py`, `db/queries/horarios_override.py` (capa de datos, SQL parametrizado).
- `tests/unit/test_roles_funcionales.py`, `tests/unit/test_horarios_default.py`, `tests/unit/test_horarios_override.py`.

**Endpoints** (sin auth nueva: usan los decoradores existentes):

| Método | Ruta | Rol mínimo | Acción |
|---|---|---|---|
| GET | `/api/roles-funcionales` | gestor | Lista |
| POST | `/api/roles-funcionales` | admin | Crea |
| PUT | `/api/roles-funcionales/<id>` | admin | Actualiza |
| DELETE | `/api/roles-funcionales/<id>` | admin | Desactiva (soft) |
| GET | `/api/horarios-default` | gestor | Lista por rol/fecha |
| POST | `/api/horarios-default` | admin | Crea |
| PUT | `/api/horarios-default/<id>` | admin | Cierra (`fecha_fin=today`) |
| GET | `/api/horarios-override?persona_id=...` | gestor | Lista por persona |
| POST | `/api/horarios-override` | admin | Crea |
| PUT | `/api/horarios-override/<id>` | admin | Cierra |
| POST | `/api/personas/<id>/roles-funcionales` | admin | Asigna rol a persona |
| DELETE | `/api/personas/<id>/roles-funcionales/<rol_id>` | admin | Cierra (`fecha_fin=today`) |
| POST | `/api/grupos/<id>/aplicar-rol-default` | admin | Asignación masiva: aplica rol+default a todas las personas del grupo sin override (ver P5) |

**Validación**: `pytest tests/unit/test_*` verde. Smoke: crear 1 rol, 1 default, asignar a 1 persona vía API con `curl` + token CSRF. Sin cambio en flujos existentes.

### Fase 3 — `resolver_horario_vigente` y feature flag (1 día)

**Archivos**:

- `app/domain/schedule.py` (extensión): nueva función pública `resolver_horario_vigente` documentada arriba.
- `db/queries/horarios_resolucion.py`: queries que la función consume (overrides activos, roles activos por persona, defaults por rol con prioridad, legacy).
- `app/tenant.py` (extensión): helper `get_horario_por_rol_enabled()` que lee `g.tenant.configuracion['horario_por_rol']`.
- `app/domain/reports.py` (1 punto de cambio): sustituir la lectura directa de `asignaciones_horario` por `resolver_horario_vigente(persona_id, fecha)` en el hot path de generación de PDF/DOCX.
- `tests/unit/test_schedule_resolver.py`: casos parametrizados.

**Feature flag**:

```python
# tenant.configuracion JSONB
{
    "horario_por_rol": false,            # default: false
    "horario_desempate": "prioridad",     # 'prioridad' | 'orden_rol' | 'error'
    "horario_seed_version": 0             # incrementa cuando el admin acepta el seed inicial
}
```

**Validación**:

- Con flag `false`: 100% de los tenants ven exactamente el mismo horario que antes (test A/B comparando el output de `resolver_horario_vigente` vs `get_horario_en_fecha` para 100 personas aleatorias durante 30 días).
- Con flag `true` y sin defaults configurados: 100% cae a "legacy_1a1" (sin cambio observable).
- Con flag `true` y 1 default configurado para 1 rol: solo las personas con ese rol se desvían del legacy.

### Fase 4 — UI mínima (1-2 días)

**Archivos**:

- `templates/admin/roles_funcionales.html` (lista + form de creación).
- `templates/admin/horarios_default.html` (matriz rol ↔ plantilla + vigencia).
- `templates/personas/horario_override.html` (CRUD override por persona).
- `templates/admin/_migrar_asignaciones.html` (form para "Aplicar default a personas sin override" del endpoint masivo).
- `static/js/roles_funcionales.js`, `static/js/horarios_default.js`, `static/js/horario_override.js`.
- `templates/personas/historico.html` (extensión): añadir columna "Origen del horario" en la tabla de días analizados.

**Validación**: screenshots de los 3 flujos; un admin puede completar el ciclo "crear rol → crear default → asignar rol a 5 personas → ver que el reporte las trata con ese horario".

### Fase 5 — Script de migración de datos opcional (½-1 día, no se ejecuta automáticamente)

**Archivos**:

- `scripts/migrar_asignaciones_a_defaults.py`: analiza las `asignaciones_horario` con `ciclo_semanas=1, origen='historico_legacy'`, agrupa por `(tipo_persona_id, categoria_id, plantilla_id)` y propone un CSV con: `tenant_slug, plantilla_id_representante, count_personas, suggested_rol_funcional_nombre, suggested_default_fecha_inicio`.
- **No escribe en BD**: solo emite el reporte. El admin lo revisa y decide.
- Si el admin aprueba, se ejecuta un segundo script `aplicar_migracion_propuesta.py` que crea `roles_funcionales`, `horarios_default_rol` y `persona_roles_funcionales` en bulk.

**Validación**: diff de `resolver_horario_vigente` antes/después para 100 personas → debe ser idéntico.

### Fase 6 — Rollout controlado (continuo)

1. **Pilot**: activar `horario_por_rol=true` en `istpet` (tenant por defecto). Monitor durante 1 semana.
2. **Comparación A/B**: correr el motor de reportes con flag `true` y con flag `false` en paralelo sobre el mismo período; diff de los PDFs resultantes (excluyendo timestamps).
3. **Extensión**: activar en tenants adicionales bajo demanda. Cada activación se documenta en `public.audit_log` con `accion='horario_por_rol_activar', detalle={tenant_slug, fecha}`.
4. **Rollback**: poner `horario_por_rol=false` en el tenant. Sin migración de BD. Sin reinicio obligatorio (la función lee el flag en cada llamada).

## Validation

Criterios observables que confirman que la decisión se ejecutó correctamente:

- **V1 — Migración reversible**: `alembic upgrade head && alembic downgrade -1` ejecutado en staging deja la BD **exactamente igual** que antes (verificar con `pg_dump --schema-only` diff).
- **V2 — Backward compatibility al 100%**: con `horario_por_rol=false` en TODOS los tenants, los reportes PDF generados en 2026-W30 (semana del deploy) son byte-idénticos a los generados en 2026-W29. Verificación automatizada en CI.
- **V3 — Función única de resolución**: `grep -rn "asignaciones_horario" app/domain/ | grep -v test` muestra 0 ocurrencias fuera de `db/queries/horarios.py` y `app/domain/schedule.py::resolver_horario_vigente`. Toda lectura operativa del horario actual pasa por la función.
- **V4 — Feature flag funciona**: test e2e con 1 tenant con flag `true` y 1 con flag `false` produce salidas distintas si el tenant con flag activo tiene defaults configurados, e idénticas si no los tiene.
- **V5 — Auditoría**: cada cambio de override o default crea 1 fila en `public.audit_log` con `detalle={antes, despues}`; cada activación del feature flag crea 1 fila con `accion='horario_por_rol_activar'`.
- **V6 — Índices correctos**: `EXPLAIN ANALYZE` de la query de resolución con datos de producción sintéticos muestra `Index Scan` en los 3 índices nuevos (no `Seq Scan`).
- **V7 — UI usable**: un admin nuevo (sin training) puede: crear 1 rol funcional, asignarlo a 1 persona, crear 1 default por rol, generar 1 reporte PDF, en menos de 10 minutos (medible con test de usabilidad ligero, no obligatorio para v1).

## Preguntas abiertas (requieren confirmación del usuario)

Estas preguntas **bloquean la implementación** de la Fase 2 en adelante. La Fase 1 (solo DDL) puede ejecutarse sin responderlas.

- **P1 — Denominación del nuevo concepto**: ¿`rol_funcional`, `puesto_funcional`, `rol_horario`, `rol_organizacional`? Recomendado: **`rol_funcional`** (corto, ortogonal, no choca con "rol de auth" si se aclara en docs).
- **P2 — ¿Una persona puede tener varios roles funcionales simultáneamente?**: Recomendado: **sí, 1:N con vigencia** (modelo completo de la Opción C). Si la respuesta es "no, 1:1 estricto", se simplifica: `personas.rol_funcional_id` (FK directa) y se elimina `persona_roles_funcionales`. **Esto último reduce 1 tabla y 1 endpoint**.
- **P3 — Política de desempate cuando una persona tiene varios roles sin `es_principal`**: Recomendado: `prioridad` (default, configurable) con fallback a `orden_rol` en empate; alternativa `error` (rechaza y exige al admin marcar uno). **Confirmar preferencia**.
- **P4 — ¿Mantener `asignaciones_horario` con `ciclo_semanas=1` como fuente válida indefinidamente?**: Recomendado: **sí**, como paso 3 de la precedencia. Rollback trivial. Si la respuesta es "no, migrar todo al modelo nuevo", la Fase 5 es obligatoria y el script `aplicar_migracion_propuesta.py` se ejecuta por tenant.
- **P5 — Asignación masiva por grupo: ¿propaga al `rol_funcional` de las personas o crea overrides individuales?**: Recomendado: **propaga al rol funcional** (más mantenible: si mañana cambia el default del rol, el grupo se actualiza). Si se prefiere "overrides individuales" (más rígido pero más explícito), el endpoint `/api/grupos/<id>/aplicar-rol-default` cambia a crear N filas en `overrides_horario_persona`.
- **P6 — Catálogo inicial de roles funcionales** (seed opcional, comentable en la migración): Recomendado: `Operativo`, `Administrativo`, `Directivo`, `Limpieza`, `Seguridad`. **¿Faltan/sobran para los tenants actuales?** (ISTPET tiene Empleados y Practicantes como tipos; no tenemos visibilidad de los otros tenants.)
- **P7 — ¿Quién puede gestionar roles funcionales, defaults y overrides?**: Recomendado:
  - Lectura (GET): `gestor`, `admin`, `superadmin`.
  - Escritura (POST/PUT/DELETE): `admin`, `superadmin`.
  - Overrides por persona: `admin` o el `supervisor_grupo` del grupo al que pertenece la persona (este último, opcional, sujeto a una pregunta aparte).
- **P8 — ¿Reportes deben mostrar la "fuente del horario" (override/default/legacy/ninguno)?**: Recomendado: **sí**, como columna "Origen" en la tabla de días del PDF y en la UI de histórico. Ahorra tiempo de soporte ("¿por qué esta persona tiene este horario? → porque tiene un override").
- **P9 — ¿Dónde vive el feature flag `horario_por_rol`?**: Recomendado: en `tenant.configuracion` JSONB (per-tenant). Alternativa: en `public.tenants.configuracion` (per-tenant también, pero en `public`). **La diferencia es operacional**: si está en `public`, se puede cambiar con un UPDATE de 1 fila; si está en `tenant`, requiere `SET search_path` primero. Recomiendo `tenant.configuracion` por consistencia con la convención del modelo (la feature es operativa, no de plataforma).
- **P10 — ¿El decorador `@require_rol_funcional(nombre)` es necesario en v1?**: Recomendado: **no** en v1. La lectura del rol funcional es ortogonal al RBAC. Si en el futuro se quiere "solo los usuarios con rol 'admin' pueden ver el horario del rol funcional 'Directivo'", se evalúa como P3.

## Follow-ups (backlog)

- **P2 — Backlog técnico** (importante, no urgente):
  - Añadir cache Redis para `resolver_horario_vigente` con TTL 60 s y clave `(persona_id, fecha)`. Solo si las métricas de CPU de los workers muestran que la resolución es cuello de botella. **Métricas a recoger en Fase 6** (rollout): p50/p95/p99 de la query.
  - Migrar `asignaciones_horario.ciclo_semanas > 1` (rotaciones cíclicas reales) al modelo nuevo. Hoy está modelado pero no usado operativamente; si un tenant lo necesita, requiere una decisión análoga a este ADR.
  - Versionado de la API: introducir `/api/v2/horarios-resolver` con la nueva semántica; mantener `/api/v1/horarios` con la semántica legacy durante 1 release.
  - Auditoría visual: panel "Cambios recientes de horario" para `admin` que liste los últimos N cambios de override/default con `quien`, `cuando`, `antes/después`.

- **P3 — Backlog futuro**:
  - Si los tenants piden "cambiar el horario de un grupo entero de un día para otro" (caso soporte): endpoint `/api/grupos/<id>/horario-temporal` que crea N overrides con `fecha_inicio` y `fecha_fin` acotados.
  - Si se quiere "rotación automática" (turnos 4x3, 5x2, etc.): modelar `plantillas_horario.es_rotativa` + tabla `rotaciones_horario` y ampliar `resolver_horario_vigente` con un paso 0. **Fuera del alcance de este ADR**.
  - Si se introduce Celery + multi-worker (Fase 6 del roadmap de [[ARQUITECTURA]]): cache distribuida y eventual consistency del feature flag.

## Relacionado

- [[ARQUITECTURA]] — Documento principal de arquitectura. La Fase −1 (backups + Alembic único) es prerrequisito de este ADR.
- [[AUTENTICACION]] — El sistema de autenticación. Define `public.usuarios.roles` (RBAC) que **no se toca** en este ADR.
- [[ER]] — Modelo de datos actual; este ADR lo extiende.
- [[ADR-0000-use-markdown-for-adrs]] — Plantilla y convención usada para escribir este ADR.
- [[ADR-0001-modularizacion-monolito-flask]] — Reglas de capas (`app/domain/*` no importa `app/web/*`; `app/web/*` no importa `db/queries/*`). Las nuevas tablas respetan la regla: `app/domain/roles_funcionales.py` consume `db/queries/roles_funcionales.py`.
- [[ADR-0002-sync-observable-y-backups]] — El precedente más cercano: DDL aditivo en `db/migrations/versions/0009_scheduler_runs.py` con `down_revision = "0008"`. Este ADR sigue el mismo patrón (`0010` con `down_revision = "0009"`).
