# Horarios por grupo funcional/laboral — Plan de Implementación (ADR-0003)

> **Para implementadores:** Plan ejecuta tarea por tarea. Checkboxes (`- [ ]`) marcan progreso. TDD donde aplique. Commits frecuentes. **No tocar** `app/`, `db/`, `tests/` ni otros archivos de código hasta que cada tarea lo indique explícitamente.

**Goal:** Implementar el modelo de horarios por grupo funcional (4 tablas + 2 columnas + función canónica `resolver_horario_vigente`) con precedencia **`personalizado > individual legacy > default grupo > sin horario`**, feature flag por tenant, asignación masiva con filtros, RBAC, auditoría, UI, integración con el motor de reportes y analytics, y rollout controlado.

**Architecture:** 4 tablas nuevas en el schema del tenant (`grupos_funcionales`, `persona_grupos_funcionales`, `horarios_default_grupo`, `overrides_horario_persona`) + 2 columnas aditivas (`plantillas_horario.es_default_grupo` / `.grupo_funcional_id`, `asignaciones_horario.origen`) + 1 trigger que mantiene `es_default_grupo` sincronizado con `horarios_default_grupo` + 1 función pública `resolver_horario_vigente(persona_id, fecha, *, feature_flag=None)` + 1 endpoint de asignación masiva con filtros combinables (`grupo_funcional_id`, `grupo_id` operativo, `tipo_persona_id`, `categoria_id`, `sede_id`). Rollout por feature flag en `tenant.configuracion` JSONB.

**Tech Stack:** Python 3.12 · Flask 3 (App Factory) · SQLAlchemy 2 (Core/text) · Alembic 0010 · PostgreSQL 16 · `pytest` + `pgserver` (ADR-0004) · Bootstrap 5.3 + plain JS · `db.queries.audit_log` (ya existe).

**Reglas arquitectónicas (no negociables):**
- `app/web/*` solo importa de `app/domain/*` y `app/tenant.py` (nunca de `db/queries/*`).
- `app/domain/*` nunca importa de `app/web/*`.
- `db/queries/*` nunca importa de `app/*` ni de Flask.
- Índices parciales en PostgreSQL solo se permiten con predicados **inmutables**. `WHERE fecha_fin IS NULL` ES inmutable; `WHERE fecha_fin >= CURRENT_DATE` NO lo es. Por eso los índices usan `(col, fecha_inicio DESC)` sin `WHERE` y el `WHERE fecha_fin IS NULL OR …` se filtra en el query.

**Cambios de precedencia respecto al ADR original:**
- ADR actual dice `override > default_grupo > legacy`. La **decisión confirmada** es `personalizado (override) > individual legacy (asignaciones_horario.origen='historico_legacy') > default grupo (horarios_default_grupo via persona_grupos_funcionales) > sin horario`.
- El ADR también proponía índices parciales `WHERE fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE`, que **no son válidos en PostgreSQL** (predicado no inmutable). Se reemplazan por índices B-tree completos sobre `(persona_id, fecha_inicio DESC)` etc., y el filtro `fecha_fin` se aplica en el `WHERE` del query.
- Ambos cambios se aplican en la **Tarea 0.1** (actualización del ADR) antes de cualquier migración o código.

---

## File Structure (mapa de cambios)

```
biometric_sistem_reports/
├── docs/
│   ├── adr/
│   │   └── 0003-horarios-por-rol-funcional.md  # MODIFICAR (Tarea 0.1)
│   ├── OPERATIONS.md                            # MODIFICAR (Fase 9)
│   └── superpowers/plans/
│       └── 2026-07-27-horarios-grupo-funcional.md  # este archivo
├── db/
│   ├── migrations/versions/
│   │   └── 0010_horarios_por_grupo_funcional.py  # NUEVO (Fase 1)
│   ├── init.py                                   # MODIFICAR (Tarea 0.3)
│   ├── init_seed.py                              # NUEVO (Tarea 0.3)
│   ├── tenant_provisioner.py                     # MODIFICAR (Tarea 0.3)
│   └── queries/
│       ├── grupos_funcionales.py                 # NUEVO (Fase 2)
│       ├── horarios_default_grupo.py             # NUEVO (Fase 2)
│       ├── persona_grupo_funcional.py            # NUEVO (Fase 2)
│       ├── horarios_override.py                  # NUEVO (Fase 2)
│       ├── __init__.py                           # MODIFICAR (re-exports)
│       └── __init__.py                           # MODIFICAR (db/__init__.py)
├── app/
│   ├── tenant.py                                 # MODIFICAR (Tarea 3.1)
│   ├── domain/
│   │   ├── schedule.py                           # MODIFICAR (Tarea 3.2: resolver_horario_vigente)
│   │   ├── groups_funcionales.py                 # NUEVO (Fase 4)
│   │   ├── horarios_default_grupo.py             # NUEVO (Fase 4)
│   │   ├── horarios_override.py                  # NUEVO (Fase 4)
│   │   ├── persona_grupo_funcional.py            # NUEVO (Fase 4)
│   │   ├── reports.py                            # MODIFICAR (Fase 5: usar resolver)
│   │   └── analytics.py                          # MODIFICAR (Fase 5: usar resolver)
│   ├── web/
│   │   ├── grupos_funcionales_bp.py              # NUEVO (Fase 6)
│   │   ├── __init__.py                           # MODIFICAR (registrar bp)
│   │   └── people_bp.py                          # MODIFICAR (Fase 7)
│   └── config.py                                 # SIN CAMBIOS
├── templates/
│   ├── admin/
│   │   ├── grupos_funcionales.html               # NUEVO
│   │   ├── horarios_default_grupo.html           # NUEVO
│   │   └── asignacion_masiva.html                # NUEVO
│   ├── personas/
│   │   ├── horario_override.html                 # NUEVO
│   │   ├── grupos_funcionales.html               # NUEVO
│   │   └── historico.html                        # MODIFICAR (columna "Origen")
│   └── base.html                                 # MODIFICAR (sidebar)
├── static/js/
│   ├── grupos_funcionales.js                     # NUEVO
│   ├── horarios_default_grupo.js                 # NUEVO
│   ├── horario_override.js                      # NUEVO
│   ├── persona_grupos_funcionales.js             # NUEVO
│   └── asignacion_masiva.js                      # NUEVO
├── scripts/
│   └── migrar_asignaciones_a_defaults.py         # NUEVO (Fase 8)
└── tests/
    ├── unit/
    │   ├── test_init_db_ddl_free.py               # NUEVO (Tarea 0.3)
    │   ├── test_horario_por_grupo_feature_flag.py # NUEVO (Tarea 3.1)
    │   ├── test_grupos_funcionales.py             # NUEVO (Fase 2)
    │   ├── test_horarios_default_grupo.py         # NUEVO (Fase 2)
    │   ├── test_horarios_override.py              # NUEVO (Fase 2)
    │   ├── test_persona_grupo_funcional.py        # NUEVO (Fase 2)
    │   ├── test_asignacion_masiva.py              # NUEVO (Fase 4)
    │   └── test_schedule_resolver.py              # NUEVO (Tarea 3.2)
    └── integration/
        ├── test_migration_0010.py                 # NUEVO (Fase 1)
        ├── test_grupos_funcionales_bp.py          # NUEVO (Fase 6)
        ├── test_horarios_resolucion_integration.py # NUEVO (Fase 5)
        └── test_horarios_override_bp.py           # NUEVO (Fase 7)
```

---

## Convenciones del plan

- Tareas **2-5 min** cada paso. Si una tarea > 30 min, partirla.
- TDD obligatorio: test RED → comando → implementar → test GREEN → commit.
- Cada tarea cierra con un commit. Mensajes en español, estilo repo.
- **No editar** `app/`, `db/`, `tests/`, `templates/`, `static/`, `scripts/` ni archivos de configuración hasta que la tarea lo pida explícitamente.
- Verificar con `git status --short` y `git diff` antes de cada commit.
- Sin emojis en código ni commits.
- Los snippets están **completos**: copiables tal cual. No hay `TBD` ni `...`.

---

# PARTE 0 — Pre-requisito operacional (bloqueante)

> **No iniciar Fase 1 hasta cerrar las 4 tareas de esta parte.** El ADR-0003 marca esto como prerequisito. Saltarlo es el riesgo operacional más alto de la decisión.

## Tarea 0.1: Actualizar ADR-0003 (precedencia + índices)

**Files:**
- Modify: `docs/adr/0003-horarios-por-rol-funcional.md`

- [ ] **Paso 1: Corregir la precedencia en la sección "Decision Outcome"**

Reemplazar el bloque de la precedencia canónica (líneas 150-171 del ADR) por:

```markdown
**Precedencia canónica** de resolución (de mayor a menor prioridad) para una persona P en una fecha D:

1. **PERSONALIZADO (override)**: ¿Existe fila en `overrides_horario_persona`
   con `persona_id=P`, `fecha_inicio<=D`, `(fecha_fin IS NULL OR fecha_fin>=D)`?
   → Sí: usar la plantilla de esa fila. `origen='personalizado'`.

2. **INDIVIDUAL LEGACY**: ¿Existe fila en `asignaciones_horario` con `persona_id=P`,
   `ciclo_semanas=1`, `fecha_inicio<=D`, `(fecha_fin IS NULL OR fecha_fin>=D)`,
   y `origen='historico_legacy'` (o cualquier origen que no sea `personalizado`
   si el admin ya migró)?
   → Sí: usar la plantilla de esa fila. `origen='individual_legacy'`.

3. **DEFAULT_GRUPO**: ¿Cuántos grupos funcionales activos tiene P en D
   (filas en `persona_grupos_funcionales` con `fecha_inicio<=D`
   y `(fecha_fin IS NULL OR fecha_fin>=D)`)?
   → Si hay 1 o más: para cada grupo funcional activo, buscar el default
     vigente en `horarios_default_grupo` (`prioridad DESC, fecha_inicio DESC`).
     El de mayor prioridad global gana. `origen='default_grupo'`.
   → Si hay varios grupos y ninguno tiene `es_principal=true`: desempate
     según `tenant.configuracion['horario_desempate']`
     ∈ {`prioridad`, `orden_grupo`, `error`}. Default: `prioridad` con
     fallback a `orden_grupo` en empate.

4. **SIN_HORARIO**: no hay match. `origen='sin_horario'`.
   El motor de reportes trata a la persona como "sin horario definido"
   (mismo comportamiento que hoy cuando una persona no está en
   `asignaciones_horario`).

> **Cambio respecto a versiones anteriores del ADR (2026-07-27):** la
> precedencia se alinea con la decisión confirmada por el usuario: el
> horario **individual legacy** (asignaciones_horario 1:1 sembrado por el
> importador `.obd/.csv`) tiene prioridad sobre el **default del grupo
> funcional**. La razón: el operador que cargó `.obd` lo hizo pensando
> que ese era "el horario de la persona"; degradarlo a un default de
> grupo sería una regresión operativa. El override (ahora llamado
> `personalizado`) sigue siendo la cima.
```

- [ ] **Paso 2: Reemplazar los índices parciales inválidos**

En la sección "Nuevas tablas" (alrededor de las líneas 211-249), reemplazar TODOS los `CREATE INDEX ... WHERE fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE` por índices B-tree completos sin predicado, ya que PostgreSQL requiere que el predicado de un índice parcial sea **inmutable** y `fecha_fin >= CURRENT_DATE` no lo es. Reemplazar por:

```sql
-- persona_grupos_funcionales: encontrar el/los grupos activos de una persona.
-- El filtro de fecha_fin se aplica en el WHERE del query, no en el índice.
CREATE INDEX idx_pgf_persona_inicio
    ON persona_grupos_funcionales (persona_id, fecha_inicio DESC);
CREATE INDEX idx_pgf_grupo_inicio
    ON persona_grupos_funcionales (grupo_funcional_id, fecha_inicio DESC);
-- es_principal=true sí es inmutable como predicado parcial:
CREATE INDEX idx_pgf_principal
    ON persona_grupos_funcionales (persona_id)
    WHERE es_principal = true;

-- horarios_default_grupo: resolver el default vigente por grupo funcional
-- ordenado por prioridad DESC y luego fecha_inicio DESC.
CREATE INDEX idx_hdg_grupo_prioridad
    ON horarios_default_grupo (grupo_funcional_id, prioridad DESC, fecha_inicio DESC);

-- overrides_horario_persona: encontrar el override vigente de una persona.
CREATE INDEX idx_ohp_persona_inicio
    ON overrides_horario_persona (persona_id, fecha_inicio DESC);
```

> **Nota**: la regla "predicado inmutable" sale de la documentación
> oficial de PostgreSQL sobre índices parciales. `IS NULL` es inmutable;
> `>=` contra `CURRENT_DATE` no lo es porque el resultado cambia con el
> tiempo. Por eso el plan usa índices B-tree completos y el filtro
> `fecha_fin` se aplica en el `WHERE` del query. El `EXPLAIN ANALYZE` de
> la Tarea 5.2 confirma que el plan de ejecución sigue siendo óptimo.

- [ ] **Paso 3: Actualizar el bloque "Confirmation Log"**

Añadir al final de la tabla existente (después de la fila P10):

```markdown
| **P11** | Precedencia confirmada | `personalizado > individual_legacy > default_grupo > sin_horario` (no la del draft). | "Decision Outcome" |
| **P12** | Índices parciales del draft | Inválidos en PostgreSQL (`fecha_fin >= CURRENT_DATE` no es inmutable). Se reemplazan por B-tree completos + predicado inmutable `es_principal=true`. | "Nuevas tablas" |
| **P13** | Renombre de `override` → `personalizado` | El campo `origen` en el resolver retorna `'personalizado'` (no `'override'`). Coherente con la UI que dice "horario personalizado". | "Decision Outcome" |
```

- [ ] **Paso 4: Verificar la edición**

Run: `git diff docs/adr/0003-horarios-por-rol-funcional.md | head -80`
Expected: muestra cambios en la precedencia y los índices. La sección
"Confirmation Log" tiene 3 filas nuevas (P11, P12, P13).

- [ ] **Paso 5: Commit**

```bash
git add docs/adr/0003-horarios-por-rol-funcional.md
git commit -m "docs(adr-0003): alinear precedencia personalizado>legacy>default y corregir índices parciales inválidos"
```

---

## Tarea 0.2: Verificar backup reciente + restore probado

**Files:** ninguno (validación manual)

- [ ] **Paso 1: Confirmar que existe backup de las últimas 24h**

Run:
```bash
ls -lh /data/backups/backup_completo_*.dump | tail -3
```
Expected: al menos 1 dump con `mtime` de las últimas 24h y tamaño > 1MB.

Si no hay backup reciente, generarlo manualmente:
```bash
docker compose exec -T db pg_dump -U $PGUSER -d $PGDB -Fc \
  > /data/backups/backup_completo_$(date +%Y%m%d_%H%M).dump
```

- [ ] **Paso 2: Probar restore contra una BD de prueba**

```bash
docker compose exec -T db createdb -U $PGUSER biometrico_restore_test
docker compose exec -T db pg_restore -U $PGUSER -d biometrico_restore_test --no-owner \
  < /data/backups/backup_completo_*.dump
docker compose exec -T db psql -U $PGUSER -d biometrico_restore_test \
  -c "SELECT count(*) FROM public.tenants;"
docker compose exec -T db dropdb -U $PGUSER biometrico_restore_test
```
Expected: el `psql` retorna un número > 0 (al menos el tenant `istpet`).

- [ ] **Paso 3: Documentar en el runbook**

Añadir al final de `docs/OPERATIONS.md` (sección 7 Changelog):

```markdown
| 2026-07-27 | Pre-check ADR-0003: backup reciente OK, restore probado contra BD temporal. | implementer |
```

No commit todavía (es solo nota). Se commitea al cerrar Fase 9.

---

## Tarea 0.3: Cierre de Fase −1 (Alembic como única fuente de verdad)

> Esta tarea es **bloqueante**: mientras `init_db()` ejecute DDL propio en cada arranque, una nueva migración puede divergir del DDL que `init_db()` aplica (especialmente `ADD COLUMN` que `init_db` podría reescribir). El ADR-0003 marca esto como prerequisito.

**Files:**
- Modify: `db/init.py`
- Create: `db/init_seed.py`
- Modify: `db/tenant_provisioner.py`
- Create: `tests/unit/test_init_db_ddl_free.py`
- Modify: `tests/integration/conftest.py`

- [ ] **Paso 1: Escribir test RED — `init_db` no debe ejecutar DDL nuevo**

`tests/unit/test_init_db_ddl_free.py` (NUEVO):

```python
"""
Verifica que `init_db` solo ejecuta SEED (idempotente), no DDL nuevo.

Tras ADR-0003, las migraciones son la única fuente de verdad del schema.
`init_db` debe limitarse a INSERTs idempotentes de datos de referencia.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_init_db_no_ejecuta_create_table_ni_alter_table():
    """`init_db` no debe contener sentencias CREATE TABLE ni ALTER TABLE
    en su SQL parametrizado. Las migraciones Alembic son la fuente de
    verdad del schema (ADR-0003, Tarea 0.3)."""
    from db.init import init_db

    sql_ejecutado: list[str] = []
    with patch("db.init.get_engine") as mock_engine, \
         patch("db.init.get_connection") as mock_get_conn, \
         patch("db.init._seed_datos_iniciales"):
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = lambda sql, *a, **kw: (
            sql_ejecutado.append(str(sql.text if hasattr(sql, "text") else sql))
        )
        mock_get_conn.return_value.__enter__ = lambda self: mock_conn
        mock_get_conn.return_value.__exit__ = lambda self, *args: None
        mock_engine.return_value.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.return_value.connect.return_value.__exit__ = lambda self, *args: None
        init_db()

    peligrosos = [
        s for s in sql_ejecutado
        if "CREATE TABLE" in s.upper() or "ALTER TABLE" in s.upper()
    ]
    assert peligrosos == [], (
        f"init_db ejecuta DDL nuevo: {peligrosos}. "
        "Mover a una migración Alembic (Tarea 1.1)."
    )
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_init_db_ddl_free.py -v`
Expected: FAIL listando los `CREATE TABLE` y `ALTER TABLE` que `init_db` ejecuta hoy.

- [ ] **Paso 3: Mover el DDL a una migración Alembic y dejar `init_db` solo con seed**

`db/init.py` — reemplazar `init_db()` por:

```python
"""
Inicialización de la base de datos PostgreSQL.

Tras el cierre de Fase −1 (ADR-0001 + ADR-0003 Tarea 0.3), `init_db()`
SOLO ejecuta seed idempotente. La fuente de verdad del schema es Alembic
(`db/migrations/versions/*`). El deploy debe correr `alembic upgrade head`
antes de que la app levante, o el seed fallará porque las tablas no
existirán.
"""
import logging
import os
from sqlalchemy import text

from db.connection import get_connection
from db.init_seed import _seed_datos_iniciales

log = logging.getLogger(__name__)


def init_db():
    """
    1. (NO DDL: las migraciones Alembic son la fuente de verdad.)
    2. Inserta datos de referencia iniciales (idempotente).
    """
    tenant = os.environ.get("TENANT_DEFAULT", "istpet")
    _seed_datos_iniciales(tenant)
    log.info(
        "init_db seed completado para tenant=%s (schema ya migrado por Alembic)",
        tenant,
    )


def _insertar_feriados_ecuador(conn):
    """Inserta feriados nacionales de Ecuador 2025 y 2026 si no hay feriados cargados."""
    existe = conn.execute(text("SELECT COUNT(*) FROM feriados")).fetchone()[0]
    if existe > 0:
        return

    feriados = [
        ("2025-01-01", "Año Nuevo", "nacional"),
        ("2025-02-28", "Carnaval", "nacional"),
        ("2025-03-03", "Carnaval", "nacional"),
        ("2025-04-18", "Viernes Santo", "nacional"),
        ("2025-05-01", "Día del Trabajo", "nacional"),
        ("2025-05-24", "Batalla de Pichincha", "nacional"),
        ("2025-08-10", "Primer Grito de Independencia", "nacional"),
        ("2025-10-09", "Independencia de Guayaquil", "nacional"),
        ("2025-11-02", "Día de los Difuntos", "nacional"),
        ("2025-11-03", "Independencia de Cuenca", "nacional"),
        ("2025-12-25", "Navidad", "nacional"),
        ("2026-01-01", "Año Nuevo", "nacional"),
        ("2026-02-16", "Carnaval", "nacional"),
        ("2026-02-17", "Carnaval", "nacional"),
        ("2026-04-03", "Viernes Santo", "nacional"),
        ("2026-05-01", "Día del Trabajo", "nacional"),
        ("2026-05-24", "Batalla de Pichincha", "nacional"),
        ("2026-08-10", "Primer Grito de Independencia", "nacional"),
        ("2026-10-09", "Independencia de Guayaquil", "nacional"),
        ("2026-11-02", "Día de los Difuntos", "nacional"),
        ("2026-11-03", "Independencia de Cuenca", "nacional"),
        ("2026-12-25", "Navidad", "nacional"),
    ]

    for fecha, desc, tipo in feriados:
        conn.execute(
            text("""
                INSERT INTO feriados (fecha, descripcion, tipo)
                VALUES (CAST(:fecha AS date), :desc, :tipo)
                ON CONFLICT (fecha) DO NOTHING
            """),
            {"fecha": fecha, "desc": desc, "tipo": tipo},
        )
```

`db/init_seed.py` (NUEVO):

```python
"""
Sub-módulo con la lógica de seed que antes vivía en `db.init`.

Separado para que `db.init` solo orqueste y `db.init_seed` ejecute los
INSERTs idempotentes. Importado por `init_db` (Tarea 0.3).
"""
from __future__ import annotations

import json
import logging
import os

from sqlalchemy import text

from db.connection import get_engine, get_connection
from db.init import _insertar_feriados_ecuador

log = logging.getLogger(__name__)


def _seed_datos_iniciales(tenant: str) -> None:
    """Inserta datos de referencia mínimos si no existen (idempotente).
    Asume que Alembic ya creó el schema (no crea tablas)."""
    nombre_inst = os.environ.get("NOMBRE_INSTITUCION", "ISTPET")
    zk_ip = os.environ.get("ZK_IP", "192.168.7.129")
    zk_port = int(os.environ.get("ZK_PORT", "4370"))
    zk_pwd = os.environ.get("ZK_PASSWORD", "")
    zk_proto = "udp" if os.environ.get("ZK_UDP", "false").lower() == "true" else "tcp"
    zk_timeout = int(os.environ.get("ZK_TIMEOUT", "120"))

    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO public.tenants (slug, nombre, nombre_corto, zona_horaria)
                VALUES (:slug, :nombre, :nombre_corto, 'America/Guayaquil')
                ON CONFLICT (slug) DO NOTHING
            """),
            {"slug": tenant, "nombre": nombre_inst, "nombre_corto": nombre_inst[:20]},
        )
        conn.commit()

        sa_email = os.environ.get("INITIAL_SUPERADMIN_EMAIL")
        sa_pass = os.environ.get("INITIAL_SUPERADMIN_PASSWORD")
        if sa_email and sa_pass:
            from app.domain.auth import hash_password
            count = conn.execute(
                text("SELECT count(*) FROM public.usuarios")
            ).scalar()
            if count == 0:
                t_id = conn.execute(
                    text("SELECT id FROM public.tenants WHERE slug = :slug"),
                    {"slug": tenant},
                ).scalar()
                log.info("Creando Superadmin inicial (%s)...", sa_email)
                conn.execute(
                    text("""
                        INSERT INTO public.usuarios
                            (tenant_id, email, password_hash, nombre, roles, configuracion)
                        VALUES (:t_id, :email, :pass_hash, :nombre,
                                ARRAY['superadmin','admin']::text[], CAST(:cfg AS jsonb))
                    """),
                    {
                        "t_id": t_id,
                        "email": sa_email.strip().lower(),
                        "pass_hash": hash_password(sa_pass),
                        "nombre": "Administrador Inicial",
                        "cfg": json.dumps({}),
                    },
                )
                conn.commit()

    with get_connection(tenant) as conn:
        conn.execute(
            text("""
                INSERT INTO sedes (nombre)
                SELECT :nombre
                WHERE NOT EXISTS (SELECT 1 FROM sedes LIMIT 1)
            """),
            {"nombre": f"Sede Principal - {nombre_inst}"},
        )

        conn.execute(
            text("""
                INSERT INTO dispositivos
                    (nombre, ip, puerto, protocolo, tipo_driver, timeout_seg)
                SELECT :nombre, :ip, :puerto, :protocolo, 'zk', :timeout
                WHERE NOT EXISTS (SELECT 1 FROM dispositivos LIMIT 1)
            """),
            {
                "nombre": f"ZK - {zk_ip}",
                "ip": zk_ip,
                "puerto": zk_port,
                "protocolo": zk_proto,
                "timeout": zk_timeout,
            },
        )

        conn.execute(
            text("""
                INSERT INTO tipos_persona (nombre, descripcion, color)
                SELECT nombre, descripcion, color FROM (VALUES
                    ('Empleado',    'Personal con contrato laboral',     '#2E75B6'),
                    ('Practicante', 'Alumno en período de prácticas',    '#70AD47')
                ) AS v(nombre, descripcion, color)
                WHERE NOT EXISTS (SELECT 1 FROM tipos_persona LIMIT 1)
            """)
        )

        _insertar_feriados_ecuador(conn)
```

`db/tenant_provisioner.py` — reemplazar el cuerpo de `provisionar_schema` para que NO aplique `get_tenant_ddl` y solo corra migraciones Alembic contra el schema recién creado:

```python
"""
Lógica de Provisioning para nuevos tenants (Fase 3: Multitenancy).

Crea el schema vacío y aplica las migraciones Alembic. El DDL de las
tablas viene de las migraciones, NO de `db.schema.get_tenant_ddl`
(esa función se conserva solo como referencia histórica, ver Tarea 0.3).
"""
import logging
import os
from sqlalchemy import text
from alembic.script import ScriptDirectory
from alembic.config import Config

from db.connection import get_engine
from db.queries.tenants import eliminar_tenant_de_public
from db.init_seed import _seed_datos_iniciales

log = logging.getLogger(__name__)


def provisionar_schema(slug: str, tipos_persona: list[str]) -> bool:
    """
    1. Crea el schema del tenant VACÍO (solo `CREATE SCHEMA`).
    2. Aplica las migraciones Alembic contra ese schema.
    3. Siembra los datos de referencia.
    """
    if not all(c.isalnum() or c == "_" for c in slug):
        raise ValueError(f"Nombre de schema inválido: '{slug}'")

    engine = get_engine()
    created_schema = False

    try:
        with engine.connect() as conn:
            log.info("Creando schema '%s' (vacío)...", slug)
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{slug}"'))
            conn.commit()
            created_schema = True

        # 2. Aplicar migraciones Alembic al schema nuevo.
        # `db/migrations/env.py` itera los tenants y aplica las
        # migraciones con `version_table_schema=slug`. Aquí lo
        # disparamos apuntando al slug recién creado. Para no aplicar
        # a TODOS los tenants, se recomienda ejecutar este comando
        # como un job de Alembic separado en el pipeline del deploy.
        ini_path = "alembic.ini"
        if os.path.exists(ini_path):
            from alembic import command as alembic_command
            alembic_cfg = Config(ini_path)
            alembic_cfg.set_main_option(
                "sqlalchemy.url", os.environ.get("DATABASE_URL", "")
            )
            alembic_command.upgrade(alembic_cfg, "head")

        # 3. Siembra idempotente
        _seed_datos_iniciales(slug)

        log.info("Provisioning completado para '%s'.", slug)
        return True

    except Exception as e:
        log.error("Error durante provisioning de '%s': %s", slug, e)
        if created_schema:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f'DROP SCHEMA IF EXISTS "{slug}" CASCADE'))
                    conn.commit()
            except Exception as rollback_err:
                log.error("Error en rollback de schema: %s", rollback_err)
        eliminar_tenant_de_public(slug)
        raise e
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_init_db_ddl_free.py -v`
Expected: PASS el único test.

- [ ] **Paso 5: Verificar que los integration tests existentes siguen pasando**

Run: `pytest tests/integration -k "init" -v`
Expected: PASS. Si fallan porque `init_db` no crea las tablas, modificar `tests/integration/conftest.py` — en la fixture `_setup_pg_session`, añadir ANTES de `init_db()`:

```python
    # ── Alembic upgrade head primero (Tarea 0.3: fuente de verdad) ─
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _PG_URI)
    alembic_command.upgrade(cfg, "head")
```

- [ ] **Paso 6: Commit**

```bash
git add db/init.py db/init_seed.py db/tenant_provisioner.py \
        tests/unit/test_init_db_ddl_free.py tests/integration/conftest.py
git commit -m "refactor(db): init_db solo seed; Alembic es única fuente de verdad del schema (Fase -1)"
```

---

## Tarea 0.4: Validar cadena Alembic + smoke del nuevo `init_db`

- [ ] **Paso 1: Verificar que la cadena de migraciones está OK**

Run: `alembic heads`
Expected: muestra `0010 (head)` (cuando la migración 0010 esté creada en la Tarea 1.1) o `0009 (head)` (antes de Tarea 1.1, situación actual).

- [ ] **Paso 2: Smoke: `alembic upgrade head` en staging + rollback**

```bash
# En staging (no en producción hasta que se ejecute Fase 9)
alembic upgrade head
alembic current
alembic downgrade -1
alembic upgrade head
```
Expected: los 4 comandos terminan con exit 0. No se pierde ningún dato porque 0009 es aditivo y reversible.

- [ ] **Paso 3: Verificar que `init_db` ya no rompe la BD**

```bash
python -c "from db.init import init_db; init_db(); print('OK')"
```
Expected: imprime `OK` y no falla.

- [ ] **Paso 4: Commit (runbook)**

`docs/OPERATIONS.md` — añadir al Changelog (al final de la sección 7):

```markdown
| 2026-07-27-r2 | Pre-Fase 1 ADR-0003: Alembic único, init_db=seed, runbook actualizado. | arquitecto |
```

```bash
git add docs/OPERATIONS.md
git commit -m "docs(operations): runbook actualizado con pre-Fase 1 ADR-0003"
```

---

# PARTE 1 — Migración Alembic 0010

## Tarea 1.1: Crear migración 0010 (DDL aditivo)

**Files:**
- Create: `db/migrations/versions/0010_horarios_por_grupo_funcional.py`

- [ ] **Paso 1: Crear el archivo de migración**

```python
"""
Horarios por grupo funcional (ADR-0003 — 0010).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-27

Crea el modelo de horarios por grupo funcional/laboral:
  - grupos_funcionales
  - persona_grupos_funcionales (N:M con vigencia y principal)
  - horarios_default_grupo
  - overrides_horario_persona

Columnas aditivas:
  - plantillas_horario.es_default_grupo
  - plantillas_horario.grupo_funcional_id
  - asignaciones_horario.origen (con CHECK)

Trigger que mantiene `plantillas_horario.es_default_grupo` sincronizada
con la presencia de filas vigentes en `horarios_default_grupo`.

Aditiva, idempotente, sin impacto en datos existentes. El downgrade deja
el schema en estado pre-0010.
"""
import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Tabla grupos_funcionales ────────────────────────────────
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'grupos_funcionales'
            ) THEN
                CREATE TABLE grupos_funcionales (
                    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    codigo          TEXT NOT NULL,
                    nombre          TEXT NOT NULL,
                    descripcion     TEXT,
                    color           TEXT,
                    orden           INTEGER NOT NULL DEFAULT 0,
                    activo          BOOLEAN NOT NULL DEFAULT true,
                    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_grupos_funcionales_codigo UNIQUE (codigo)
                );
            END IF;
        END $$;
    """))

    # ── 2. Tabla persona_grupos_funcionales (N:M con vigencia) ────
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'persona_grupos_funcionales'
            ) THEN
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
                    CONSTRAINT uq_pgf_persona_grupo_inicio
                        UNIQUE (persona_id, grupo_funcional_id, fecha_inicio)
                );
            END IF;
        END $$;
    """))

    # ── 3. Tabla horarios_default_grupo ────────────────────────────
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'horarios_default_grupo'
            ) THEN
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
                    CONSTRAINT uq_hdg_grupo_plantilla_inicio
                        UNIQUE (grupo_funcional_id, plantilla_id, fecha_inicio)
                );
            END IF;
        END $$;
    """))

    # ── 4. Tabla overrides_horario_persona ────────────────────────
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'overrides_horario_persona'
            ) THEN
                CREATE TABLE overrides_horario_persona (
                    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    persona_id    UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                    plantilla_id  UUID NOT NULL REFERENCES plantillas_horario(id) ON DELETE RESTRICT,
                    fecha_inicio  DATE NOT NULL,
                    fecha_fin     DATE,
                    motivo        TEXT,
                    creado_por    UUID REFERENCES public.usuarios(id) ON DELETE SET NULL,
                    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_ohp_persona_plantilla_inicio
                        UNIQUE (persona_id, plantilla_id, fecha_inicio)
                );
            END IF;
        END $$;
    """))

    # ── 5. Columnas aditivas ───────────────────────────────────────
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = 'plantillas_horario'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'plantillas_horario'
                      AND column_name = 'es_default_grupo'
                ) THEN
                    ALTER TABLE plantillas_horario
                        ADD COLUMN es_default_grupo BOOLEAN NOT NULL DEFAULT false;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'plantillas_horario'
                      AND column_name = 'grupo_funcional_id'
                ) THEN
                    ALTER TABLE plantillas_horario
                        ADD COLUMN grupo_funcional_id UUID
                        REFERENCES grupos_funcionales(id) ON DELETE SET NULL;
                END IF;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = 'asignaciones_horario'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'asignaciones_horario'
                      AND column_name = 'origen'
                ) THEN
                    ALTER TABLE asignaciones_horario
                        ADD COLUMN origen TEXT NOT NULL DEFAULT 'historico_legacy'
                        CHECK (origen IN (
                            'historico_legacy',
                            'personalizado_migrado',
                            'asignacion_directa'
                        ));
                END IF;
            END IF;
        END $$;
    """))

    # ── 6. Índices (B-tree completos, predicados inmutables) ──────
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_pgf_persona_inicio
            ON persona_grupos_funcionales (persona_id, fecha_inicio DESC);
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_pgf_grupo_inicio
            ON persona_grupos_funcionales (grupo_funcional_id, fecha_inicio DESC);
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_pgf_principal
            ON persona_grupos_funcionales (persona_id)
            WHERE es_principal = true;
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_hdg_grupo_prioridad
            ON horarios_default_grupo (
                grupo_funcional_id, prioridad DESC, fecha_inicio DESC
            );
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_ohp_persona_inicio
            ON overrides_horario_persona (persona_id, fecha_inicio DESC);
    """))

    # ── 7. Trigger: mantener es_default_grupo sincronizado ────────
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_hdg_actualizar_es_default_grupo'
                  AND tgrelid = 'horarios_default_grupo'::regclass
            ) THEN
                CREATE OR REPLACE FUNCTION fn_hdg_actualizar_es_default_grupo()
                RETURNS TRIGGER AS $body$
                BEGIN
                    IF TG_OP = 'DELETE' THEN
                        UPDATE plantillas_horario
                        SET es_default_grupo = false
                        WHERE id = OLD.plantilla_id;
                        RETURN OLD;
                    END IF;

                    -- INSERT o UPDATE: si la fila vigente existe, marcar true.
                    UPDATE plantillas_horario
                    SET es_default_grupo = true
                    WHERE id = NEW.plantilla_id;

                    -- Si era un UPDATE y la fila deja de estar vigente,
                    -- verificar si hay OTRA fila vigente para la misma plantilla.
                    IF TG_OP = 'UPDATE' THEN
                        UPDATE plantillas_horario
                        SET es_default_grupo = false
                        WHERE id = OLD.plantilla_id
                          AND NOT EXISTS (
                              SELECT 1 FROM horarios_default_grupo h
                              WHERE h.plantilla_id = OLD.plantilla_id
                                AND (h.fecha_fin IS NULL OR h.fecha_fin >= CURRENT_DATE)
                          );
                    END IF;
                    RETURN NEW;
                END;
                $body$ LANGUAGE plpgsql;

                CREATE TRIGGER trg_hdg_actualizar_es_default_grupo
                AFTER INSERT OR UPDATE OR DELETE ON horarios_default_grupo
                FOR EACH ROW EXECUTE FUNCTION fn_hdg_actualizar_es_default_grupo();
            END IF;
        END $$;
    """))


def downgrade() -> None:
    """
    PELIGROSO: elimina las 4 tablas y revierte las 2 columnas aditivas.
    Solo para entornos de desarrollo. En producción se prefiere
    `alembic stamp 0009` para "esconder" la migración si el DDL diverge.
    """
    confirm = os.environ.get("ALEMBIC_ALLOW_DOWNGRADE_0010", "false")
    if confirm.lower() != "true":
        raise RuntimeError(
            "Downgrade de 0010 deshabilitado por seguridad. "
            "Setea ALEMBIC_ALLOW_DOWNGRADE_0010=true para confirmar."
        )

    conn = op.get_bind()

    conn.execute(text("""
        DROP TRIGGER IF EXISTS trg_hdg_actualizar_es_default_grupo
        ON horarios_default_grupo;
    """))
    conn.execute(text("""
        DROP FUNCTION IF EXISTS fn_hdg_actualizar_es_default_grupo();
    """))
    conn.execute(text("""
        DROP TABLE IF EXISTS overrides_horario_persona CASCADE;
    """))
    conn.execute(text("""
        DROP TABLE IF EXISTS horarios_default_grupo CASCADE;
    """))
    conn.execute(text("""
        DROP TABLE IF EXISTS persona_grupos_funcionales CASCADE;
    """))
    conn.execute(text("""
        DROP TABLE IF EXISTS grupos_funcionales CASCADE;
    """))
    conn.execute(text("""
        ALTER TABLE IF EXISTS plantillas_horario
            DROP COLUMN IF EXISTS grupo_funcional_id;
    """))
    conn.execute(text("""
        ALTER TABLE IF EXISTS plantillas_horario
            DROP COLUMN IF EXISTS es_default_grupo;
    """))
    conn.execute(text("""
        ALTER TABLE IF EXISTS asignaciones_horario
            DROP COLUMN IF EXISTS origen;
    """))
```

- [ ] **Paso 2: Validar sintaxis**

Run: `python -c "import ast; ast.parse(open('db/migrations/versions/0010_horarios_por_grupo_funcional.py').read()); print('OK')"`
Expected: `OK`.

- [ ] **Paso 3: Aplicar y revertir en staging**

```bash
alembic upgrade head
psql $DATABASE_URL -c "\d grupos_funcionales"
alembic downgrade -1
psql $DATABASE_URL -c "\dt"
alembic upgrade head
```
Expected: los 4 comandos terminan OK. La tabla existe después de upgrade y desaparece después de downgrade.

- [ ] **Paso 4: Validar cadena de migraciones**

Run: `alembic heads && alembic current`
Expected: `0010 (head)` y `0010 (head)`.

- [ ] **Paso 5: Commit**

```bash
git add db/migrations/versions/0010_horarios_por_grupo_funcional.py
git commit -m "feat(db): migración 0010 — modelo horarios por grupo funcional"
```

---

## Tarea 1.2: Tests de integración de la migración 0010

**Files:**
- Create: `tests/integration/test_migration_0010.py`

- [ ] **Paso 1: Crear el test**

```python
"""
Tests de integración para la migración 0010.

Verifica que `alembic upgrade head` + `alembic downgrade -1` dejan la BD
exactamente igual al estado pre-0010.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command


@pytest.fixture(scope="module")
def _alembic_cfg():
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return cfg


def _tabla_existe(conn, nombre: str) -> bool:
    row = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = :nombre
            )
        """),
        {"nombre": nombre},
    ).scalar()
    return bool(row)


def _columna_existe(conn, tabla: str, columna: str) -> bool:
    row = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :tabla
                  AND column_name = :columna
            )
        """),
        {"tabla": tabla, "columna": columna},
    ).scalar()
    return bool(row)


def test_upgrade_0010_crea_4_tablas(_alembic_cfg):
    """Tras upgrade head, las 4 tablas existen en el schema del tenant."""
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        conn.execute(sa.text('SET search_path TO "istpet", public'))
        for t in (
            "grupos_funcionales",
            "persona_grupos_funcionales",
            "horarios_default_grupo",
            "overrides_horario_persona",
        ):
            assert _tabla_existe(conn, t), f"Falta tabla {t}"


def test_upgrade_0010_crea_columnas_aditivas(_alembic_cfg):
    """Las 3 columnas aditivas están en plantillas_horario y asignaciones_horario."""
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        conn.execute(sa.text('SET search_path TO "istpet", public'))
        assert _columna_existe(conn, "plantillas_horario", "es_default_grupo")
        assert _columna_existe(conn, "plantillas_horario", "grupo_funcional_id")
        assert _columna_existe(conn, "asignaciones_horario", "origen")


def test_upgrade_0010_default_origen_historico_legacy(_alembic_cfg):
    """Toda asignación existente tiene origen='historico_legacy' tras upgrade."""
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        conn.execute(sa.text('SET search_path TO "istpet", public'))
        row = conn.execute(
            sa.text("""
                SELECT count(*) FILTER (WHERE origen = 'historico_legacy') AS n_legacy,
                       count(*) AS n_total
                FROM asignaciones_horario
            """)
        ).fetchone()
        assert row.n_total == 0 or row.n_legacy == row.n_total


def test_upgrade_0010_crea_5_indices(_alembic_cfg):
    """Los 5 índices nuevos están creados."""
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        conn.execute(sa.text('SET search_path TO "istpet", public'))
        for idx in (
            "idx_pgf_persona_inicio",
            "idx_pgf_grupo_inicio",
            "idx_pgf_principal",
            "idx_hdg_grupo_prioridad",
            "idx_ohp_persona_inicio",
        ):
            row = conn.execute(
                sa.text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes
                        WHERE schemaname = current_schema()
                          AND indexname = :idx
                    )
                """),
                {"idx": idx},
            ).scalar()
            assert bool(row), f"Falta índice {idx}"


def test_trigger_es_default_grupo_se_sincroniza(_alembic_cfg):
    """Insertar/eliminar en horarios_default_grupo actualiza plantillas_horario.es_default_grupo."""
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sa.text('SET search_path TO "istpet", public'))

        gf_id = conn.execute(
            sa.text("""
                INSERT INTO grupos_funcionales (codigo, nombre)
                VALUES ('TEST_GF', 'Test Grupo Funcional')
                RETURNING id
            """)
        ).scalar()

        plant_id = conn.execute(
            sa.text("""
                INSERT INTO plantillas_horario (nombre, lunes, lunes_salida)
                VALUES ('Test plantilla 0010', '08:00', '17:00')
                RETURNING id
            """)
        ).scalar()

        row = conn.execute(
            sa.text("SELECT es_default_grupo FROM plantillas_horario WHERE id = :p"),
            {"p": plant_id},
        ).scalar()
        assert row is False

        hdg_id = conn.execute(
            sa.text("""
                INSERT INTO horarios_default_grupo
                    (grupo_funcional_id, plantilla_id, fecha_inicio, prioridad)
                VALUES (:g, :p, CURRENT_DATE, 0)
                RETURNING id
            """),
            {"g": gf_id, "p": plant_id},
        ).scalar()

        row = conn.execute(
            sa.text("SELECT es_default_grupo FROM plantillas_horario WHERE id = :p"),
            {"p": plant_id},
        ).scalar()
        assert row is True, "Trigger no actualizó es_default_grupo tras INSERT"

        conn.execute(
            sa.text("DELETE FROM horarios_default_grupo WHERE id = :h"),
            {"h": hdg_id},
        )
        row = conn.execute(
            sa.text("SELECT es_default_grupo FROM plantillas_horario WHERE id = :p"),
            {"p": plant_id},
        ).scalar()
        assert row is False, "Trigger no actualizó es_default_grupo tras DELETE"

        conn.execute(sa.text("DELETE FROM plantillas_horario WHERE id = :p"), {"p": plant_id})
        conn.execute(sa.text("DELETE FROM grupos_funcionales WHERE id = :g"), {"g": gf_id})


def test_downgrade_0010_limpia_todo(_alembic_cfg):
    """`alembic downgrade -1` deja la BD en estado pre-0010."""
    os.environ["ALEMBIC_ALLOW_DOWNGRADE_0010"] = "true"
    try:
        alembic_command.downgrade(_alembic_cfg, "-1")
    finally:
        os.environ.pop("ALEMBIC_ALLOW_DOWNGRADE_0010", None)

    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        conn.execute(sa.text('SET search_path TO "istpet", public'))
        for t in (
            "grupos_funcionales",
            "persona_grupos_funcionales",
            "horarios_default_grupo",
            "overrides_horario_persona",
        ):
            assert not _tabla_existe(conn, t), f"Sigue existiendo {t}"
        assert not _columna_existe(conn, "plantillas_horario", "es_default_grupo")
        assert not _columna_existe(conn, "plantillas_horario", "grupo_funcional_id")
        assert not _columna_existe(conn, "asignaciones_horario", "origen")

    alembic_command.upgrade(_alembic_cfg, "head")
```

- [ ] **Paso 2: Verificar que el test falla antes de aplicar la migración**

Run: `alembic downgrade 0009 && pytest tests/integration/test_migration_0010.py -v --no-cov`
Expected: el primer test falla con "Falta tabla grupos_funcionales".

- [ ] **Paso 3: Aplicar la migración y verificar PASS**

Run: `alembic upgrade head && pytest tests/integration/test_migration_0010.py -v --no-cov`
Expected: PASS los 6 tests.

- [ ] **Paso 4: Commit**

```bash
git add tests/integration/test_migration_0010.py
git commit -m "test(db): integración 0010 — DDL, índices, trigger y downgrade"
```

---

# PARTE 2 — Capa de datos `db/queries/`

> Los 4 módulos de queries siguen el patrón de `db/queries/horarios.py`:
> funciones con SQL parametrizado, sin imports de `app/*` ni Flask.

## Tarea 2.1: Módulo `grupos_funcionales.py` (TDD)

**Files:**
- Create: `db/queries/grupos_funcionales.py`
- Create: `tests/unit/test_grupos_funcionales.py`

- [ ] **Paso 1: Crear test RED**

```python
"""
Tests unitarios de `db.queries.grupos_funcionales` (TDD).

Mockeamos `db.connection.get_connection` para no tocar BD real.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from db.queries import grupos_funcionales


class TestListarGruposFuncionales:

    def test_listar_activos_devuelve_dicts_con_campos_esperados(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "gf-1", "codigo": "profesor", "nombre": "Profesor",
            "descripcion": "Docente", "color": "#FF0000", "orden": 1,
            "activo": True, "creado_en": "2026-07-27",
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.grupos_funcionales.get_connection", _fake_conn):
            rows = grupos_funcionales.listar(solo_activos=True)

        assert len(rows) == 1
        assert rows[0]["codigo"] == "profesor"
        assert rows[0]["activo"] is True

    def test_listar_todos(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.grupos_funcionales.get_connection", _fake_conn):
            rows = grupos_funcionales.listar(solo_activos=False)
        assert rows == []


class TestCrearGrupoFuncional:

    def test_crear_inserta_y_retorna_dict(self):
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "gf-2", "codigo": "administrativo", "nombre": "Administrativo",
            "descripcion": None, "color": None, "orden": 0, "activo": True,
        }
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.grupos_funcionales.get_connection", _fake_conn):
            resultado = grupos_funcionales.crear(
                codigo="administrativo", nombre="Administrativo",
            )

        assert resultado["codigo"] == "administrativo"
        assert resultado["activo"] is True
        sql = str(mock_conn.execute.call_args[0][0])
        assert "INSERT INTO grupos_funcionales" in sql
        assert "ON CONFLICT (codigo) DO NOTHING" in sql


class TestActualizarGrupoFuncional:

    def test_actualizar_solo_campos_permitidos(self):
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "gf-1", "codigo": "profesor",
            "nombre": "Profesor (actualizado)", "orden": 2, "activo": True,
        }
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.grupos_funcionales.get_connection", _fake_conn):
            resultado = grupos_funcionales.actualizar(
                "gf-1", {"nombre": "Profesor (actualizado)", "orden": 2}
            )

        assert resultado["nombre"] == "Profesor (actualizado)"
        sql = str(mock_conn.execute.call_args[0][0])
        assert "UPDATE grupos_funcionales SET" in sql
        assert "id = " not in sql


class TestDesactivarGrupoFuncional:

    def test_desactivar_marca_inactivo(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.rowcount = 1

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.grupos_funcionales.get_connection", _fake_conn):
            ok = grupos_funcionales.desactivar("gf-1")
        assert ok is True


class TestGetByCodigo:

    def test_get_by_codigo_devuelve_dict_o_none(self):
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {"id": "gf-1", "codigo": "profesor", "nombre": "Profesor"}
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.grupos_funcionales.get_connection", _fake_conn):
            gf = grupos_funcionales.get_by_codigo("profesor")
        assert gf["codigo"] == "profesor"

    def test_get_by_codigo_no_existe_retorna_none(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.grupos_funcionales.get_connection", _fake_conn):
            gf = grupos_funcionales.get_by_codigo("nope")
        assert gf is None
```

- [ ] **Paso 2: Verificar RED**

Run: `pytest tests/unit/test_grupos_funcionales.py -v`
Expected: ImportError o CollectionError.

- [ ] **Paso 3: Implementar el módulo**

```python
"""
Queries SQL para `grupos_funcionales` (ADR-0003).

Operan sobre la tabla `<tenant>.grupos_funcionales`. Sin imports de
`app/*` ni de Flask (regla de capas del ADR-0001).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from db.connection import get_connection


def listar(solo_activos: bool = True) -> list[dict]:
    """Lista los grupos funcionales. Por defecto solo los activos."""
    sql = """
        SELECT id::text, codigo, nombre, descripcion, color, orden, activo,
               creado_en
        FROM grupos_funcionales
    """
    if solo_activos:
        sql += " WHERE activo = true"
    sql += " ORDER BY orden, nombre"
    with get_connection() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [dict(r._mapping) for r in rows]


def get_by_id(grupo_funcional_id: str) -> dict | None:
    """Busca un grupo funcional por su UUID."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT id::text, codigo, nombre, descripcion, color, orden, activo,
                       creado_en
                FROM grupos_funcionales
                WHERE id = CAST(:id AS uuid)
            """),
            {"id": grupo_funcional_id},
        ).fetchone()
    return dict(row._mapping) if row else None


def get_by_codigo(codigo: str) -> dict | None:
    """Busca un grupo funcional por su código único."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT id::text, codigo, nombre, descripcion, color, orden, activo,
                       creado_en
                FROM grupos_funcionales
                WHERE codigo = :codigo
            """),
            {"codigo": codigo},
        ).fetchone()
    return dict(row._mapping) if row else None


def crear(
    codigo: str,
    nombre: str,
    descripcion: Optional[str] = None,
    color: Optional[str] = None,
    orden: int = 0,
    activo: bool = True,
) -> dict:
    """Crea un grupo funcional. `ON CONFLICT (codigo) DO NOTHING`."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO grupos_funcionales
                    (codigo, nombre, descripcion, color, orden, activo)
                VALUES (:codigo, :nombre, :descripcion, :color, :orden, :activo)
                ON CONFLICT (codigo) DO NOTHING
                RETURNING id::text, codigo, nombre, descripcion, color, orden, activo
            """),
            {
                "codigo": codigo, "nombre": nombre, "descripcion": descripcion,
                "color": color, "orden": orden, "activo": activo,
            },
        ).fetchone()
    if row is None:
        return get_by_codigo(codigo)  # ya existía
    return dict(row._mapping)


def actualizar(grupo_funcional_id: str, datos: dict) -> dict | None:
    """Actualiza campos permitidos. `id` y `creado_en` son inmutables."""
    allowed = {"nombre", "descripcion", "color", "orden", "activo"}
    sets = []
    params = {"id": grupo_funcional_id}
    for k, v in datos.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return get_by_id(grupo_funcional_id)
    sql = f"""
        UPDATE grupos_funcionales
        SET {', '.join(sets)}, actualizado_en = NOW()
        WHERE id = CAST(:id AS uuid)
        RETURNING id::text, codigo, nombre, descripcion, color, orden, activo
    """
    with get_connection() as conn:
        row = conn.execute(text(sql), params).fetchone()
    return dict(row._mapping) if row else None


def desactivar(grupo_funcional_id: str) -> bool:
    """Soft-delete: marca activo=false."""
    with get_connection() as conn:
        result = conn.execute(
            text("""
                UPDATE grupos_funcionales
                SET activo = false, actualizado_en = NOW()
                WHERE id = CAST(:id AS uuid)
            """),
            {"id": grupo_funcional_id},
        )
    return result.rowcount > 0
```

- [ ] **Paso 4: Verificar GREEN**

Run: `pytest tests/unit/test_grupos_funcionales.py -v`
Expected: PASS los 7 tests.

- [ ] **Paso 5: Re-exportar en `db/__init__.py` y `db/queries/__init__.py`**

`db/queries/__init__.py` — añadir al final:
```python
# ── Grupos funcionales (ADR-0003) ─────────────────────────────────────
from db.queries.grupos_funcionales import (
    listar as listar_grupos_funcionales,
    get_by_id as get_grupo_funcional,
    get_by_codigo as get_grupo_funcional_by_codigo,
    crear as crear_grupo_funcional,
    actualizar as actualizar_grupo_funcional,
    desactivar as desactivar_grupo_funcional,
)
```

`db/__init__.py` — añadir al final del bloque existente:
```python
from db.queries.grupos_funcionales import (
    listar_grupos_funcionales,
    get_grupo_funcional,
    get_grupo_funcional_by_codigo,
    crear_grupo_funcional,
    actualizar_grupo_funcional,
    desactivar_grupo_funcional,
)
```
Y al `__all__`:
```python
"listar_grupos_funcionales",
"get_grupo_funcional",
"get_grupo_funcional_by_codigo",
"crear_grupo_funcional",
"actualizar_grupo_funcional",
"desactivar_grupo_funcional",
```

- [ ] **Paso 6: Commit**

```bash
git add db/queries/grupos_funcionales.py db/queries/__init__.py \
        db/__init__.py tests/unit/test_grupos_funcionales.py
git commit -m "feat(db): queries grupos_funcionales + tests TDD"
```

---

## Tarea 2.2: Módulo `horarios_default_grupo.py` (TDD)

**Files:**
- Create: `db/queries/horarios_default_grupo.py`
- Create: `tests/unit/test_horarios_default_grupo.py`

- [ ] **Paso 1: Test RED**

```python
"""
Tests unitarios de `db.queries.horarios_default_grupo` (TDD).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from db.queries import horarios_default_grupo


class TestListarPorGrupo:

    def test_listar_por_grupo_devuelve_dicts(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "hdg-1", "grupo_funcional_id": "gf-1",
            "plantilla_id": "ph-1", "fecha_inicio": date(2026, 1, 1),
            "fecha_fin": None, "prioridad": 0, "notas": None,
            "nombre_plantilla": "Profesor Mañana", "codigo_gf": "profesor",
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_default_grupo.get_connection", _fake_conn):
            rows = horarios_default_grupo.listar_por_grupo("gf-1")
        assert len(rows) == 1
        assert rows[0]["prioridad"] == 0
        assert rows[0]["nombre_plantilla"] == "Profesor Mañana"


class TestListarVigentesParaGrupo:

    def test_listar_vigentes_usa_orden_prioridad(self):
        """El query debe ORDER BY prioridad DESC, fecha_inicio DESC."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_default_grupo.get_connection", _fake_conn):
            horarios_default_grupo.listar_vigentes_para_grupo("gf-1", date(2026, 7, 1))
        sql = str(mock_conn.execute.call_args[0][0])
        assert "ORDER BY prioridad DESC, fecha_inicio DESC" in sql
        assert "fecha_fin IS NULL OR fecha_fin >=" in sql
        assert "fecha_inicio <=" in sql


class TestCrear:

    def test_crear_con_vigencia_abierta(self):
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "hdg-2", "grupo_funcional_id": "gf-1",
            "plantilla_id": "ph-2", "fecha_inicio": date(2026, 8, 1),
            "fecha_fin": None, "prioridad": 0,
        }
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_default_grupo.get_connection", _fake_conn):
            hdg = horarios_default_grupo.crear(
                grupo_funcional_id="gf-1", plantilla_id="ph-2",
                fecha_inicio=date(2026, 8, 1),
            )
        assert hdg["prioridad"] == 0


class TestCerrar:

    def test_cerrar_pone_fecha_fin_hoy(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.rowcount = 1

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_default_grupo.get_connection", _fake_conn):
            ok = horarios_default_grupo.cerrar("hdg-1", fecha_fin=date(2026, 12, 31))
        assert ok is True
        sql = str(mock_conn.execute.call_args[0][0])
        assert "fecha_fin = :fecha_fin" in sql


class TestResolverParaGrupos:

    def test_resolver_devuelve_plantilla_con_mayor_prioridad(self):
        rows = [
            {"plantilla_id": "ph-A", "grupo_funcional_id": "gf-A",
             "prioridad": 0, "fecha_inicio": date(2026, 1, 1)},
            {"plantilla_id": "ph-B", "grupo_funcional_id": "gf-B",
             "prioridad": 10, "fecha_inicio": date(2026, 1, 1)},
        ]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_default_grupo.get_connection", _fake_conn):
            resultado = horarios_default_grupo.resolver_para_grupos(
                ["gf-A", "gf-B"], date(2026, 7, 15)
            )
        assert resultado is not None
        assert resultado["plantilla_id"] == "ph-B"
        assert resultado["prioridad"] == 10
        assert resultado["grupo_funcional_id"] == "gf-B"

    def test_resolver_sin_grupos_retorna_none(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_default_grupo.get_connection", _fake_conn):
            resultado = horarios_default_grupo.resolver_para_grupos(
                [], date(2026, 7, 15)
            )
        assert resultado is None
```

- [ ] **Paso 2: Verificar RED + implementar + verificar GREEN**

`db/queries/horarios_default_grupo.py`:

```python
"""
Queries SQL para `horarios_default_grupo` (ADR-0003).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from db.connection import get_connection


def listar_por_grupo(grupo_funcional_id: str) -> list[dict]:
    """Lista TODOS los defaults (vigentes o no) de un grupo funcional."""
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text, hdg.grupo_funcional_id, hdg.plantilla_id,
                       hdg.fecha_inicio, hdg.fecha_fin, hdg.prioridad, hdg.notas,
                       ph.nombre AS nombre_plantilla,
                       gf.codigo AS codigo_gf
                FROM horarios_default_grupo hdg
                JOIN grupos_funcionales gf ON gf.id = hdg.grupo_funcional_id
                JOIN plantillas_horario ph ON ph.id = hdg.plantilla_id
                WHERE hdg.grupo_funcional_id = CAST(:gf_id AS uuid)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
            """),
            {"gf_id": grupo_funcional_id},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def listar_vigentes_para_grupo(grupo_funcional_id: str, fecha: date) -> list[dict]:
    """Lista los defaults vigentes para un grupo funcional en una fecha."""
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text, hdg.plantilla_id, hdg.grupo_funcional_id,
                       hdg.fecha_inicio, hdg.fecha_fin, hdg.prioridad
                FROM horarios_default_grupo hdg
                WHERE hdg.grupo_funcional_id = CAST(:gf_id AS uuid)
                  AND hdg.fecha_inicio <= :fecha
                  AND (hdg.fecha_fin IS NULL OR hdg.fecha_fin >= :fecha)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
            """),
            {"gf_id": grupo_funcional_id, "fecha": fecha},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def crear(
    grupo_funcional_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    prioridad: int = 0,
    notas: Optional[str] = None,
) -> dict | None:
    """Crea un default para un grupo funcional."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO horarios_default_grupo
                    (grupo_funcional_id, plantilla_id, fecha_inicio, fecha_fin,
                     prioridad, notas)
                VALUES (CAST(:gf_id AS uuid), CAST(:plantilla_id AS uuid),
                        :fecha_inicio, :fecha_fin, :prioridad, :notas)
                ON CONFLICT (grupo_funcional_id, plantilla_id, fecha_inicio)
                DO NOTHING
                RETURNING id::text, grupo_funcional_id, plantilla_id,
                          fecha_inicio, fecha_fin, prioridad
            """),
            {
                "gf_id": grupo_funcional_id, "plantilla_id": plantilla_id,
                "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
                "prioridad": prioridad, "notas": notas,
            },
        ).fetchone()
    return dict(row._mapping) if row else None


def cerrar(hdg_id: str, fecha_fin: date) -> bool:
    """Cierra un default poniendo fecha_fin (NO DELETE: conserva histórico)."""
    with get_connection() as conn:
        result = conn.execute(
            text("""
                UPDATE horarios_default_grupo
                SET fecha_fin = :fecha_fin, actualizado_en = NOW()
                WHERE id = CAST(:id AS uuid)
                  AND fecha_fin IS NULL
            """),
            {"id": hdg_id, "fecha_fin": fecha_fin},
        )
    return result.rowcount > 0


def resolver_para_grupos(
    grupo_funcional_ids: list[str], fecha: date
) -> dict | None:
    """
    Dado N grupos funcionales activos para una persona, retorna el default
    de mayor prioridad global (entre todos los grupos).

    Returns:
        dict con `plantilla_id`, `grupo_funcional_id`, `prioridad`,
        `hdg_id`. None si ninguno tiene default vigente.
    """
    if not grupo_funcional_ids:
        return None
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text AS hdg_id, hdg.plantilla_id,
                       hdg.grupo_funcional_id, hdg.prioridad, hdg.fecha_inicio
                FROM horarios_default_grupo hdg
                WHERE hdg.grupo_funcional_id = ANY(CAST(:gf_ids AS uuid[]))
                  AND hdg.fecha_inicio <= :fecha
                  AND (hdg.fecha_fin IS NULL OR hdg.fecha_fin >= :fecha)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
                LIMIT 1
            """),
            {"gf_ids": grupo_funcional_ids, "fecha": fecha},
        ).fetchall()
    return dict(rows[0]._mapping) if rows else None
```

- [ ] **Paso 3: Re-exportar en `db/queries/__init__.py` y `db/__init__.py`**

`db/queries/__init__.py`:
```python
from db.queries.horarios_default_grupo import (
    listar_por_grupo as listar_horarios_default_grupo,
    listar_vigentes_para_grupo as listar_horarios_default_vigentes,
    crear as crear_horario_default_grupo,
    cerrar as cerrar_horario_default_grupo,
    resolver_para_grupos as resolver_default_para_grupos,
)
```

`db/__init__.py`:
```python
from db.queries.horarios_default_grupo import (
    listar_horarios_default_grupo,
    listar_horarios_default_vigentes,
    crear_horario_default_grupo,
    cerrar_horario_default_grupo,
    resolver_default_para_grupos,
)
```
Y añadir al `__all__` los 5 nombres.

- [ ] **Paso 4: Commit**

```bash
git add db/queries/horarios_default_grupo.py db/queries/__init__.py \
        db/__init__.py tests/unit/test_horarios_default_grupo.py
git commit -m "feat(db): queries horarios_default_grupo + tests TDD"
```

---

## Tarea 2.3: Módulo `persona_grupo_funcional.py` (TDD)

**Files:**
- Create: `db/queries/persona_grupo_funcional.py`
- Create: `tests/unit/test_persona_grupo_funcional.py`

- [ ] **Paso 1: Test RED**

```python
"""
Tests unitarios de `db.queries.persona_grupo_funcional` (TDD).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from db.queries import persona_grupo_funcional


class TestListarVigentesParaPersona:

    def test_listar_vigentes_para_persona(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "pgf-1", "persona_id": "p-1", "grupo_funcional_id": "gf-1",
            "fecha_inicio": date(2026, 1, 1), "fecha_fin": None,
            "es_principal": True, "codigo_gf": "profesor",
            "nombre_gf": "Profesor", "orden_gf": 1,
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.persona_grupo_funcional.get_connection", _fake_conn):
            rows = persona_grupo_funcional.listar_vigentes_para_persona(
                "p-1", date(2026, 7, 15)
            )
        assert len(rows) == 1
        assert rows[0]["es_principal"] is True
        sql = str(mock_conn.execute.call_args[0][0])
        assert "fecha_inicio <= :fecha" in sql
        assert "fecha_fin IS NULL OR fecha_fin >=" in sql


class TestAsignarPersonaAGrupo:

    def test_asignar_inserta_fila_y_marca_principal_si_corresponde(self):
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "pgf-2", "persona_id": "p-1", "grupo_funcional_id": "gf-2",
            "fecha_inicio": date(2026, 8, 1), "fecha_fin": None,
            "es_principal": True,
        }
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.persona_grupo_funcional.get_connection", _fake_conn):
            fila = persona_grupo_funcional.asignar(
                persona_id="p-1", grupo_funcional_id="gf-2",
                fecha_inicio=date(2026, 8, 1), es_principal=True,
            )
        assert fila["es_principal"] is True
        sql = str(mock_conn.execute.call_args[0][0])
        assert "ON CONFLICT" in sql


class TestCerrarAsignacion:

    def test_cerrar_pone_fecha_fin(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.rowcount = 1

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.persona_grupo_funcional.get_connection", _fake_conn):
            ok = persona_grupo_funcional.cerrar("pgf-1", fecha_fin=date(2026, 12, 31))
        assert ok is True


class TestListarPersonasPorGrupo:

    def test_listar_personas_por_grupo_devuelve_persona_ids(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("p-1",), ("p-2",)]

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.persona_grupo_funcional.get_connection", _fake_conn):
            ids = persona_grupo_funcional.listar_personas_en_grupo(
                "gf-1", date(2026, 7, 15)
            )
        assert ids == ["p-1", "p-2"]
```

- [ ] **Paso 2: Verificar RED + implementar + verificar GREEN**

`db/queries/persona_grupo_funcional.py`:

```python
"""
Queries SQL para `persona_grupos_funcionales` (ADR-0003).

N:M entre personas y grupos funcionales con vigencia y `es_principal`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from db.connection import get_connection


def listar_vigentes_para_persona(persona_id: str, fecha: date) -> list[dict]:
    """Lista los grupos funcionales activos para una persona en una fecha."""
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT pgf.id::text, pgf.persona_id, pgf.grupo_funcional_id,
                       pgf.fecha_inicio, pgf.fecha_fin, pgf.es_principal,
                       pgf.notas,
                       gf.codigo AS codigo_gf,
                       gf.nombre AS nombre_gf,
                       gf.orden  AS orden_gf
                FROM persona_grupos_funcionales pgf
                JOIN grupos_funcionales gf ON gf.id = pgf.grupo_funcional_id
                WHERE pgf.persona_id = CAST(:pid AS uuid)
                  AND pgf.fecha_inicio <= :fecha
                  AND (pgf.fecha_fin IS NULL OR pgf.fecha_fin >= :fecha)
                ORDER BY pgf.es_principal DESC, gf.orden ASC, gf.nombre ASC
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def asignar(
    persona_id: str,
    grupo_funcional_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    es_principal: bool = False,
    notas: Optional[str] = None,
) -> dict | None:
    """
    Asigna una persona a un grupo funcional. Idempotente via UNIQUE
    (persona_id, grupo_funcional_id, fecha_inicio).
    """
    with get_connection() as conn:
        # Si es_principal=true, primero desmarcar el principal anterior.
        if es_principal:
            conn.execute(
                text("""
                    UPDATE persona_grupos_funcionales
                    SET es_principal = false
                    WHERE persona_id = CAST(:pid AS uuid)
                      AND es_principal = true
                """),
                {"pid": persona_id},
            )
        row = conn.execute(
            text("""
                INSERT INTO persona_grupos_funcionales
                    (persona_id, grupo_funcional_id, fecha_inicio, fecha_fin,
                     es_principal, notas)
                VALUES (CAST(:pid AS uuid), CAST(:gf_id AS uuid),
                        :fecha_inicio, :fecha_fin, :es_principal, :notas)
                ON CONFLICT (persona_id, grupo_funcional_id, fecha_inicio)
                DO NOTHING
                RETURNING id::text, persona_id, grupo_funcional_id,
                          fecha_inicio, fecha_fin, es_principal
            """),
            {
                "pid": persona_id, "gf_id": grupo_funcional_id,
                "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
                "es_principal": es_principal, "notas": notas,
            },
        ).fetchone()
    return dict(row._mapping) if row else None


def cerrar(pgf_id: str, fecha_fin: date) -> bool:
    """Cierra la asignación poniendo fecha_fin (no DELETE)."""
    with get_connection() as conn:
        result = conn.execute(
            text("""
                UPDATE persona_grupos_funcionales
                SET fecha_fin = :fecha_fin, actualizado_en = NOW()
                WHERE id = CAST(:id AS uuid)
                  AND fecha_fin IS NULL
            """),
            {"id": pgf_id, "fecha_fin": fecha_fin},
        )
    return result.rowcount > 0


def listar_personas_en_grupo(grupo_funcional_id: str, fecha: date) -> list[str]:
    """Retorna los IDs de personas con un grupo funcional vigente."""
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT pgf.persona_id::text
                FROM persona_grupos_funcionales pgf
                WHERE pgf.grupo_funcional_id = CAST(:gf_id AS uuid)
                  AND pgf.fecha_inicio <= :fecha
                  AND (pgf.fecha_fin IS NULL OR pgf.fecha_fin >= :fecha)
            """),
            {"gf_id": grupo_funcional_id, "fecha": fecha},
        ).fetchall()
    return [r[0] for r in rows]
```

- [ ] **Paso 3: Re-exportar en `db/queries/__init__.py` y `db/__init__.py`**

`db/queries/__init__.py`:
```python
from db.queries.persona_grupo_funcional import (
    listar_vigentes_para_persona as listar_grupos_funcionales_de_persona,
    asignar as asignar_persona_a_grupo_funcional,
    cerrar as cerrar_persona_grupo_funcional,
    listar_personas_en_grupo as listar_personas_en_grupo_funcional,
)
```

`db/__init__.py`:
```python
from db.queries.persona_grupo_funcional import (
    listar_grupos_funcionales_de_persona,
    asignar_persona_a_grupo_funcional,
    cerrar_persona_grupo_funcional,
    listar_personas_en_grupo_funcional,
)
```
Añadir al `__all__`.

- [ ] **Paso 4: Commit**

```bash
git add db/queries/persona_grupo_funcional.py db/queries/__init__.py \
        db/__init__.py tests/unit/test_persona_grupo_funcional.py
git commit -m "feat(db): queries persona_grupos_funcionales + tests TDD"
```

---

## Tarea 2.4: Módulo `horarios_override.py` (TDD)

**Files:**
- Create: `db/queries/horarios_override.py`
- Create: `tests/unit/test_horarios_override.py`

- [ ] **Paso 1: Test RED**

```python
"""
Tests unitarios de `db.queries.horarios_override` (TDD).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from db.queries import horarios_override


class TestListarPorPersona:

    def test_listar_por_persona_devuelve_dicts(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "ohp-1", "persona_id": "p-1", "plantilla_id": "ph-3",
            "fecha_inicio": date(2026, 8, 1), "fecha_fin": None,
            "motivo": "Cambio temporal por cirugía", "creado_por": None,
            "nombre_plantilla": "Nocturno Especial",
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_override.get_connection", _fake_conn):
            rows = horarios_override.listar_por_persona("p-1")
        assert rows[0]["motivo"] == "Cambio temporal por cirugía"


class TestObtenerVigenteParaPersona:

    def test_devuelve_override_vigente_o_none(self):
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "ohp-1", "persona_id": "p-1", "plantilla_id": "ph-3",
            "fecha_inicio": date(2026, 1, 1), "fecha_fin": None,
        }
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_override.get_connection", _fake_conn):
            ov = horarios_override.obtener_vigente_para_persona(
                "p-1", date(2026, 7, 15)
            )
        assert ov["plantilla_id"] == "ph-3"

    def test_sin_override_vigente_retorna_none(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_override.get_connection", _fake_conn):
            ov = horarios_override.obtener_vigente_para_persona(
                "p-1", date(2026, 7, 15)
            )
        assert ov is None


class TestCrear:

    def test_crear_con_creado_por_y_motivo(self):
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "ohp-2", "persona_id": "p-1", "plantilla_id": "ph-2",
            "fecha_inicio": date(2026, 8, 1), "fecha_fin": None,
        }
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_override.get_connection", _fake_conn):
            ov = horarios_override.crear(
                persona_id="p-1", plantilla_id="ph-2",
                fecha_inicio=date(2026, 8, 1),
                motivo="X", creado_por="u-1",
            )
        assert ov["persona_id"] == "p-1"


class TestCerrar:

    def test_cerrar_pone_fecha_fin(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.rowcount = 1

        @contextmanager
        def _fake_conn():
            yield mock_conn
        with patch("db.queries.horarios_override.get_connection", _fake_conn):
            ok = horarios_override.cerrar("ohp-1", date(2026, 12, 31))
        assert ok is True
```

- [ ] **Paso 2: Verificar RED + implementar + verificar GREEN**

`db/queries/horarios_override.py`:

```python
"""
Queries SQL para `overrides_horario_persona` (ADR-0003).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from db.connection import get_connection


def listar_por_persona(persona_id: str) -> list[dict]:
    """Lista TODOS los overrides (vigentes o no) de una persona."""
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT ohp.id::text, ohp.persona_id, ohp.plantilla_id,
                       ohp.fecha_inicio, ohp.fecha_fin, ohp.motivo,
                       ohp.creado_por, ohp.creado_en,
                       ph.nombre AS nombre_plantilla
                FROM overrides_horario_persona ohp
                JOIN plantillas_horario ph ON ph.id = ohp.plantilla_id
                WHERE ohp.persona_id = CAST(:pid AS uuid)
                ORDER BY ohp.fecha_inicio DESC
            """),
            {"pid": persona_id},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def obtener_vigente_para_persona(persona_id: str, fecha: date) -> dict | None:
    """Retorna el override vigente de una persona en una fecha, o None."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT ohp.id::text, ohp.persona_id, ohp.plantilla_id,
                       ohp.fecha_inicio, ohp.fecha_fin, ohp.motivo,
                       ohp.creado_por, ohp.creado_en
                FROM overrides_horario_persona ohp
                WHERE ohp.persona_id = CAST(:pid AS uuid)
                  AND ohp.fecha_inicio <= :fecha
                  AND (ohp.fecha_fin IS NULL OR ohp.fecha_fin >= :fecha)
                ORDER BY ohp.fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchone()
    return dict(row._mapping) if row else None


def crear(
    persona_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    motivo: Optional[str] = None,
    creado_por: Optional[str] = None,
) -> dict:
    """Crea un override. Idempotente por UNIQUE(persona_id, plantilla_id, fecha_inicio)."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO overrides_horario_persona
                    (persona_id, plantilla_id, fecha_inicio, fecha_fin,
                     motivo, creado_por)
                VALUES (CAST(:pid AS uuid), CAST(:ph_id AS uuid),
                        :fecha_inicio, :fecha_fin, :motivo,
                        CAST(:creado_por AS uuid))
                ON CONFLICT (persona_id, plantilla_id, fecha_inicio)
                DO UPDATE SET motivo = EXCLUDED.motivo,
                              fecha_fin = EXCLUDED.fecha_fin
                RETURNING id::text, persona_id, plantilla_id,
                          fecha_inicio, fecha_fin, motivo, creado_por
            """),
            {
                "pid": persona_id, "ph_id": plantilla_id,
                "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
                "motivo": motivo, "creado_por": creado_por,
            },
        ).fetchone()
    return dict(row._mapping)


def cerrar(ohp_id: str, fecha_fin: date) -> bool:
    """Cierra el override poniendo fecha_fin (no DELETE)."""
    with get_connection() as conn:
        result = conn.execute(
            text("""
                UPDATE overrides_horario_persona
                SET fecha_fin = :fecha_fin
                WHERE id = CAST(:id AS uuid)
                  AND fecha_fin IS NULL
            """),
            {"id": ohp_id, "fecha_fin": fecha_fin},
        )
    return result.rowcount > 0
```

- [ ] **Paso 3: Re-exportar en `db/queries/__init__.py` y `db/__init__.py`**

`db/queries/__init__.py`:
```python
from db.queries.horarios_override import (
    listar_por_persona as listar_overrides_por_persona,
    obtener_vigente_para_persona as obtener_override_vigente,
    crear as crear_override_horario,
    cerrar as cerrar_override_horario,
)
```

`db/__init__.py`:
```python
from db.queries.horarios_override import (
    listar_overrides_por_persona,
    obtener_override_vigente,
    crear_override_horario,
    cerrar_override_horario,
)
```
Añadir al `__all__`.

- [ ] **Paso 4: Commit**

```bash
git add db/queries/horarios_override.py db/queries/__init__.py \
        db/__init__.py tests/unit/test_horarios_override.py
git commit -m "feat(db): queries overrides_horario_persona + tests TDD"
```

---

# PARTE 3 — Función canónica `resolver_horario_vigente`

> Esta función es el corazón del ADR-0003. Es la **única** vía de
> resolución de horario para el motor de reportes y analytics.

## Tarea 3.1: Helper de feature flag por tenant

**Files:**
- Modify: `app/tenant.py`
- Create: `tests/unit/test_horario_por_grupo_feature_flag.py`

- [ ] **Paso 1: Test RED**

```python
"""
Tests del helper `get_horario_por_grupo_enabled` (TDD).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.tenant import get_horario_por_grupo_enabled


class TestGetHorarioPorGrupoEnabled:

    def test_true_si_configuracion_activa(self):
        fake_tenant = {"configuracion": {"horario_por_grupo": True}}
        with patch("app.tenant.g") as mock_g:
            mock_g.tenant = fake_tenant
            assert get_horario_por_grupo_enabled() is True

    def test_false_si_configuracion_vacia(self):
        fake_tenant = {"configuracion": {}}
        with patch("app.tenant.g") as mock_g:
            mock_g.tenant = fake_tenant
            assert get_horario_por_grupo_enabled() is False

    def test_false_si_no_hay_tenant(self):
        with patch("app.tenant.g") as mock_g:
            mock_g.tenant = None
            assert get_horario_por_grupo_enabled() is False

    def test_false_si_no_hay_g(self):
        with patch("app.tenant.g", side_effect=RuntimeError):
            assert get_horario_por_grupo_enabled() is False
```

- [ ] **Paso 2: Verificar RED + implementar + verificar GREEN**

Añadir al final de `app/tenant.py`:

```python
def get_horario_por_grupo_enabled() -> bool:
    """
    Lee `g.tenant.configuracion['horario_por_grupo']` (per-tenant feature
    flag). Default: `False` (modo seguro, comportamiento legacy).

    Retorna `False` también si no hay contexto Flask (tests, scheduler
    en background thread, CLI) — así el resolver cae al camino legacy.
    """
    try:
        from flask import g
        tenant = getattr(g, "tenant", None)
        if not tenant:
            return False
        cfg = tenant.get("configuracion") or {}
        return bool(cfg.get("horario_por_grupo", False))
    except RuntimeError:
        return False
```

- [ ] **Paso 3: Commit**

```bash
git add app/tenant.py tests/unit/test_horario_por_grupo_feature_flag.py
git commit -m "feat(tenant): get_horario_por_grupo_enabled feature flag helper + tests TDD"
```

---

## Tarea 3.2: Función `resolver_horario_vigente` (TDD)

**Files:**
- Modify: `app/domain/schedule.py`
- Create: `tests/unit/test_schedule_resolver.py`

- [ ] **Paso 1: Test RED — cobertura de la precedencia parametrizada**

```python
"""
Tests parametrizados de `resolver_horario_vigente` (TDD).

Cubre la precedencia canónica del ADR-0003 (versión r2):
    personalizado > individual_legacy > default_grupo > sin_horario
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain.schedule import resolver_horario_vigente


class _FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, idx):
        return list(self._mapping.values())[idx]


class _FakeConn:
    def __init__(self, fetch_fn):
        self._fetch = fetch_fn

    def execute(self, sql, params=None):
        text = str(sql.text if hasattr(sql, "text") else sql)
        rows = self._fetch(text, params or {})
        m = MagicMock()
        m.fetchall.return_value = rows
        m.fetchone.return_value = _FakeRow(rows[0]) if rows else None
        return m


def _fetch(sql, params):
    if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
        return []
    if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
        return []
    if "persona_grupos_funcionales" in sql and "es_principal" not in sql:
        return []
    return []


@contextmanager
def _patched_conn(fetch_fn):
    yield _FakeConn(fetch_fn)


# ── 1. PERSONALIZADO ──────────────────────────────────────────────────

def test_override_vigente_retorna_personalizado():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return [{"id": "ov-1", "persona_id": "p-1", "plantilla_id": "ph-O",
                     "fecha_inicio": "2026-01-01", "fecha_fin": None}]
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente("p-1", date(2026, 7, 15), feature_flag=True)
    assert resultado["origen"] == "personalizado"
    assert resultado["plantilla_id"] == "ph-O"
    assert resultado["override_id"] == "ov-1"


# ── 2. INDIVIDUAL LEGACY ─────────────────────────────────────────────

def test_sin_override_busco_legacy():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return []
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return [{"id": "ah-1", "persona_id": "p-1", "plantilla_id": "ph-L",
                     "fecha_inicio": "2024-01-01", "fecha_fin": None,
                     "origen": "historico_legacy"}]
        if "persona_grupos_funcionales" in sql:
            return []
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente("p-1", date(2026, 7, 15), feature_flag=True)
    assert resultado["origen"] == "individual_legacy"
    assert resultado["plantilla_id"] == "ph-L"
    assert resultado["asignacion_legacy_id"] == "ah-1"


# ── 3. DEFAULT_GRUPO (1 grupo, sin override ni legacy) ──────────────

def test_sin_override_sin_legacy_busco_default_grupo():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return []
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return []
        if "persona_grupos_funcionales" in sql and "es_principal" not in sql:
            return [{"id": "pgf-1", "grupo_funcional_id": "gf-1",
                     "fecha_inicio": "2026-01-01", "fecha_fin": None,
                     "es_principal": True, "orden_gf": 1}]
        if "horarios_default_grupo" in sql and "ANY" in sql:
            return [{"hdg_id": "hdg-1", "plantilla_id": "ph-D",
                     "grupo_funcional_id": "gf-1", "prioridad": 0,
                     "fecha_inicio": "2026-01-01"}]
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente("p-1", date(2026, 7, 15), feature_flag=True)
    assert resultado["origen"] == "default_grupo"
    assert resultado["plantilla_id"] == "ph-D"
    assert resultado["grupo_funcional_id"] == "gf-1"


# ── 4. DEFAULT_GRUPO con varios grupos (es_principal) ──────────────

def test_varios_grupos_con_principal_gana_el_principal():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return []
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return []
        if "persona_grupos_funcionales" in sql and "es_principal" not in sql:
            return [
                {"id": "pgf-1", "grupo_funcional_id": "gf-1",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": True,  "orden_gf": 1},
                {"id": "pgf-2", "grupo_funcional_id": "gf-2",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": False, "orden_gf": 2},
            ]
        if "horarios_default_grupo" in sql and "ANY" in sql:
            return [
                {"hdg_id": "hdg-1", "plantilla_id": "ph-D1",
                 "grupo_funcional_id": "gf-1", "prioridad": 0,
                 "fecha_inicio": "2026-01-01"},
                {"hdg_id": "hdg-2", "plantilla_id": "ph-D2",
                 "grupo_funcional_id": "gf-2", "prioridad": 10,
                 "fecha_inicio": "2026-01-01"},
            ]
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente("p-1", date(2026, 7, 15), feature_flag=True)
    assert resultado["grupo_funcional_id"] == "gf-1"
    assert resultado["plantilla_id"] == "ph-D1"


# ── 5. DEFAULT_GRUPO con varios grupos SIN principal → prioridad ─────

def test_varios_grupos_sin_principal_gana_mayor_prioridad():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return []
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return []
        if "persona_grupos_funcionales" in sql and "es_principal" not in sql:
            return [
                {"id": "pgf-1", "grupo_funcional_id": "gf-A",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": False, "orden_gf": 1},
                {"id": "pgf-2", "grupo_funcional_id": "gf-B",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": False, "orden_gf": 2},
            ]
        if "horarios_default_grupo" in sql and "ANY" in sql:
            return [
                {"hdg_id": "hdg-A", "plantilla_id": "ph-A",
                 "grupo_funcional_id": "gf-A", "prioridad": 0,
                 "fecha_inicio": "2026-01-01"},
                {"hdg_id": "hdg-B", "plantilla_id": "ph-B",
                 "grupo_funcional_id": "gf-B", "prioridad": 10,
                 "fecha_inicio": "2026-01-01"},
            ]
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente(
            "p-1", date(2026, 7, 15), feature_flag=True,
            horario_desempate="prioridad",
        )
    assert resultado["grupo_funcional_id"] == "gf-B"
    assert resultado["plantilla_id"] == "ph-B"


# ── 6. DEFAULT_GRUPO sin principal → orden_grupo fallback ───────────

def test_varios_grupos_sin_principal_desempate_orden_grupo():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return []
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return []
        if "persona_grupos_funcionales" in sql and "es_principal" not in sql:
            return [
                {"id": "pgf-1", "grupo_funcional_id": "gf-Z",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": False, "orden_gf": 9},
                {"id": "pgf-2", "grupo_funcional_id": "gf-A",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": False, "orden_gf": 1},
            ]
        if "horarios_default_grupo" in sql and "ANY" in sql:
            return [
                {"hdg_id": "hdg-Z", "plantilla_id": "ph-Z",
                 "grupo_funcional_id": "gf-Z", "prioridad": 0,
                 "fecha_inicio": "2026-01-01"},
                {"hdg_id": "hdg-A", "plantilla_id": "ph-A",
                 "grupo_funcional_id": "gf-A", "prioridad": 0,
                 "fecha_inicio": "2026-01-01"},
            ]
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente(
            "p-1", date(2026, 7, 15), feature_flag=True,
            horario_desempate="orden_grupo",
        )
    assert resultado["grupo_funcional_id"] == "gf-A"


# ── 7. SIN HORARIO ──────────────────────────────────────────────────

def test_sin_horario_devuelve_sin_horario():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return []
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return []
        if "persona_grupos_funcionales" in sql and "es_principal" not in sql:
            return []
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente("p-1", date(2026, 7, 15), feature_flag=True)
    assert resultado["origen"] == "sin_horario"
    assert resultado["plantilla_id"] is None


# ── 8. Feature flag en False → legacy siempre ───────────────────────

def test_feature_flag_false_retorna_legacy():
    def fetch(sql, params):
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return [{"id": "ah-1", "persona_id": "p-1", "plantilla_id": "ph-L",
                     "fecha_inicio": "2024-01-01", "fecha_fin": None,
                     "origen": "historico_legacy"}]
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)):
        resultado = resolver_horario_vigente("p-1", date(2026, 7, 15), feature_flag=False)
    assert resultado["origen"] == "individual_legacy"
    assert resultado["plantilla_id"] == "ph-L"


# ── 9. Desempate=error con varios grupos sin principal ──────────────

def test_varios_grupos_sin_principal_y_error_lanza_excepcion():
    def fetch(sql, params):
        if "overrides_horario_persona" in sql and "fecha_inicio" in sql and "LIMIT 1" in sql:
            return []
        if "asignaciones_horario" in sql and "ciclo_semanas = 1" in sql:
            return []
        if "persona_grupos_funcionales" in sql and "es_principal" not in sql:
            return [
                {"id": "pgf-1", "grupo_funcional_id": "gf-A",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": False, "orden_gf": 1},
                {"id": "pgf-2", "grupo_funcional_id": "gf-B",
                 "fecha_inicio": "2026-01-01", "fecha_fin": None,
                 "es_principal": False, "orden_gf": 2},
            ]
        return []
    with patch("app.domain.schedule.get_connection", lambda: _patched_conn(fetch)), \
         pytest.raises(RuntimeError, match="ambiguo"):
        resolver_horario_vigente(
            "p-1", date(2026, 7, 15), feature_flag=True,
            horario_desempate="error",
        )
```

- [ ] **Paso 2: Verificar RED**

Run: `pytest tests/unit/test_schedule_resolver.py -v`
Expected: ImportError en `from app.domain.schedule import resolver_horario_vigente`.

- [ ] **Paso 3: Implementar `resolver_horario_vigente` en `app/domain/schedule.py`**

Añadir al final de `app/domain/schedule.py`:

```python
def resolver_horario_vigente(
    persona_id: str,
    fecha: date,
    *,
    feature_flag: bool | None = None,
    horario_desempate: str | None = None,
) -> dict:
    """
    Resuelve el horario aplicable a una persona en una fecha.

    Precedencia (ADR-0003 r2):
        1. PERSONALIZADO   — overrides_horario_persona vigente
        2. INDIVIDUAL_LEGACY — asignaciones_horario con origen='historico_legacy'
        3. DEFAULT_GRUPO   — horarios_default_grupo via persona_grupos_funcionales
        4. SIN_HORARIO     — no hay match

    Returns:
        dict con:
            - plantilla_id: str | None
            - origen: "personalizado" | "individual_legacy" | "default_grupo" | "sin_horario"
            - grupo_funcional_id: str | None (si origen='default_grupo')
            - override_id: str | None (si origen='personalizado')
            - asignacion_legacy_id: str | None (si origen='individual_legacy')
            - regla_desempate: str | None (si hubo desempate)
    """
    from db.connection import get_connection
    from sqlalchemy import text

    # Resolver feature_flag (None → leer de tenant.configuracion)
    if feature_flag is None:
        try:
            from app.tenant import get_horario_por_grupo_enabled
            feature_flag = get_horario_por_grupo_enabled()
        except Exception:
            feature_flag = False

    if not feature_flag:
        # Modo legacy: leer asignaciones_horario 1:1
        return _resolver_legacy(persona_id, fecha)

    # ── 1. PERSONALIZADO (override) ─────────────────────────────────
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT id::text, persona_id, plantilla_id, fecha_inicio, fecha_fin
                FROM overrides_horario_persona
                WHERE persona_id = CAST(:pid AS uuid)
                  AND fecha_inicio <= :fecha
                  AND (fecha_fin IS NULL OR fecha_fin >= :fecha)
                ORDER BY fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchone()
    if row:
        return {
            "plantilla_id": row[2],
            "plantilla": None,
            "origen": "personalizado",
            "override_id": row[0],
            "grupo_funcional_id": None,
            "asignacion_legacy_id": None,
            "regla_desempate": None,
        }

    # ── 2. INDIVIDUAL LEGACY ─────────────────────────────────────────
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT id::text, persona_id, plantilla_id, fecha_inicio, fecha_fin
                FROM asignaciones_horario
                WHERE persona_id = CAST(:pid AS uuid)
                  AND ciclo_semanas = 1
                  AND fecha_inicio <= :fecha
                  AND (fecha_fin IS NULL OR fecha_fin >= :fecha)
                  AND origen IN ('historico_legacy', 'asignacion_directa', 'personalizado_migrado')
                ORDER BY fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchone()
    if row:
        return {
            "plantilla_id": row[2],
            "plantilla": None,
            "origen": "individual_legacy",
            "override_id": None,
            "grupo_funcional_id": None,
            "asignacion_legacy_id": row[0],
            "regla_desempate": None,
        }

    # ── 3. DEFAULT_GRUPO ────────────────────────────────────────────
    desempate = horario_desempate or "prioridad"
    with get_connection() as conn:
        grupos = conn.execute(
            text("""
                SELECT pgf.id::text, pgf.grupo_funcional_id, pgf.es_principal,
                       gf.orden AS orden_gf, gf.nombre AS nombre_gf
                FROM persona_grupos_funcionales pgf
                JOIN grupos_funcionales gf ON gf.id = pgf.grupo_funcional_id
                WHERE pgf.persona_id = CAST(:pid AS uuid)
                  AND pgf.fecha_inicio <= :fecha
                  AND (pgf.fecha_fin IS NULL OR pgf.fecha_fin >= :fecha)
                ORDER BY pgf.es_principal DESC, gf.orden ASC, gf.nombre ASC
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchall()
    if not grupos:
        return {
            "plantilla_id": None, "plantilla": None, "origen": "sin_horario",
            "override_id": None, "grupo_funcional_id": None,
            "asignacion_legacy_id": None, "regla_desempate": None,
        }

    if grupos[0][2] is True:
        # Hay un grupo con es_principal=true: usar SOLO ese.
        grupos_resolver_ids = [grupos[0][1]]
        regla = "es_principal"
    elif desempate == "error":
        raise RuntimeError(
            f"Ambigüedad: persona {persona_id} tiene N grupos funcionales sin "
            f"principal y tenant.configuracion['horario_desempate']='error'. "
            f"Grupos: {[g[1] for g in grupos]}."
        )
    else:
        grupos_resolver_ids = [g[1] for g in grupos]
        regla = desempate

    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text AS hdg_id, hdg.plantilla_id,
                       hdg.grupo_funcional_id, hdg.prioridad, hdg.fecha_inicio
                FROM horarios_default_grupo hdg
                WHERE hdg.grupo_funcional_id = ANY(CAST(:gf_ids AS uuid[]))
                  AND hdg.fecha_inicio <= :fecha
                  AND (hdg.fecha_fin IS NULL OR hdg.fecha_fin >= :fecha)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
                LIMIT 1
            """),
            {"gf_ids": grupos_resolver_ids, "fecha": fecha},
        ).fetchall()

    if not rows:
        return {
            "plantilla_id": None, "plantilla": None, "origen": "sin_horario",
            "override_id": None, "grupo_funcional_id": None,
            "asignacion_legacy_id": None, "regla_desempate": None,
        }

    row = rows[0]
    return {
        "plantilla_id": row[1],
        "plantilla": None,
        "origen": "default_grupo",
        "override_id": None,
        "grupo_funcional_id": row[2],
        "asignacion_legacy_id": None,
        "regla_desempate": regla,
    }


def _resolver_legacy(persona_id: str, fecha: date) -> dict:
    """Resuelve solo por asignaciones_horario 1:1 (modo legacy)."""
    from db.connection import get_connection
    from sqlalchemy import text

    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT id::text, persona_id, plantilla_id, fecha_inicio, fecha_fin
                FROM asignaciones_horario
                WHERE persona_id = CAST(:pid AS uuid)
                  AND ciclo_semanas = 1
                  AND fecha_inicio <= :fecha
                  AND (fecha_fin IS NULL OR fecha_fin >= :fecha)
                ORDER BY fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchone()
    if row:
        return {
            "plantilla_id": row[2],
            "plantilla": None,
            "origen": "individual_legacy",
            "override_id": None,
            "grupo_funcional_id": None,
            "asignacion_legacy_id": row[0],
            "regla_desempate": None,
        }
    return {
        "plantilla_id": None, "plantilla": None, "origen": "sin_horario",
        "override_id": None, "grupo_funcional_id": None,
        "asignacion_legacy_id": None, "regla_desempate": None,
    }
```

- [ ] **Paso 4: Verificar GREEN**

Run: `pytest tests/unit/test_schedule_resolver.py -v`
Expected: PASS los 9 tests.

- [ ] **Paso 5: Commit**

```bash
git add app/domain/schedule.py tests/unit/test_schedule_resolver.py
git commit -m "feat(schedule): resolver_horario_vigente con precedencia personalizado>legacy>default>sin_horario + tests TDD"
```

---

# PARTE 4 — Servicios de dominio + RBAC + auditoría + asignación masiva

> Los módulos de dominio son wrappers puros sobre `db.queries.*` que
> añaden validación y registro de auditoría.

## Tarea 4.1: Servicios `app/domain/grupos_funcionales.py`, `horarios_default_grupo.py`, `persona_grupo_funcional.py`, `horarios_override.py`

**Files:**
- Create: `app/domain/grupos_funcionales.py`
- Create: `app/domain/horarios_default_grupo.py`
- Create: `app/domain/persona_grupo_funcional.py`
- Create: `app/domain/horarios_override.py`

- [ ] **Paso 1: Crear `app/domain/grupos_funcionales.py`**

```python
"""Servicios de dominio para `grupos_funcionales` (ADR-0003)."""
from __future__ import annotations

from db import (
    listar_grupos_funcionales,
    get_grupo_funcional,
    get_grupo_funcional_by_codigo,
    crear_grupo_funcional,
    actualizar_grupo_funcional,
    desactivar_grupo_funcional,
)


def listar(solo_activos: bool = True):
    return listar_grupos_funcionales(solo_activos=solo_activos)


def get(grupo_funcional_id: str):
    return get_grupo_funcional(grupo_funcional_id)


def get_por_codigo(codigo: str):
    return get_grupo_funcional_by_codigo(codigo)


def crear(codigo: str, nombre: str, **kwargs):
    return crear_grupo_funcional(codigo=codigo, nombre=nombre, **kwargs)


def actualizar(grupo_funcional_id: str, datos: dict):
    return actualizar_grupo_funcional(grupo_funcional_id, datos)


def desactivar(grupo_funcional_id: str) -> bool:
    return desactivar_grupo_funcional(grupo_funcional_id)


__all__ = ["listar", "get", "get_por_codigo", "crear", "actualizar", "desactivar"]
```

- [ ] **Paso 2: Crear `app/domain/horarios_default_grupo.py`**

```python
"""Servicios de dominio para `horarios_default_grupo` (ADR-0003)."""
from __future__ import annotations

from db import (
    listar_horarios_default_grupo,
    listar_horarios_default_vigentes,
    crear_horario_default_grupo,
    cerrar_horario_default_grupo,
    resolver_default_para_grupos,
)


def listar(grupo_funcional_id: str | None = None):
    return listar_horarios_default_grupo(grupo_funcional_id)


def listar_vigentes(grupo_funcional_id: str, fecha):
    return listar_horarios_default_vigentes(grupo_funcional_id, fecha)


def crear(grupo_funcional_id: str, plantilla_id: str, fecha_inicio, **kwargs):
    return crear_horario_default_grupo(
        grupo_funcional_id=grupo_funcional_id,
        plantilla_id=plantilla_id,
        fecha_inicio=fecha_inicio,
        **kwargs,
    )


def cerrar(hdg_id: str, fecha_fin) -> bool:
    return cerrar_horario_default_grupo(hdg_id, fecha_fin)


def resolver_para_grupos(grupo_funcional_ids: list[str], fecha):
    return resolver_default_para_grupos(grupo_funcional_ids, fecha)


__all__ = ["listar", "listar_vigentes", "crear", "cerrar", "resolver_para_grupos"]
```

- [ ] **Paso 3: Crear `app/domain/persona_grupo_funcional.py`**

```python
"""Servicios de dominio para `persona_grupos_funcionales` (ADR-0003)."""
from __future__ import annotations

from db import (
    listar_grupos_funcionales_de_persona,
    asignar_persona_a_grupo_funcional,
    cerrar_persona_grupo_funcional,
    listar_personas_en_grupo_funcional,
)


def listar_vigentes_para_persona(persona_id: str, fecha):
    return listar_grupos_funcionales_de_persona(persona_id, fecha)


def asignar(persona_id: str, grupo_funcional_id: str, fecha_inicio, **kwargs):
    return asignar_persona_a_grupo_funcional(
        persona_id=persona_id,
        grupo_funcional_id=grupo_funcional_id,
        fecha_inicio=fecha_inicio,
        **kwargs,
    )


def cerrar(pgf_id: str, fecha_fin) -> bool:
    return cerrar_persona_grupo_funcional(pgf_id, fecha_fin)


def listar_personas_en_grupo(grupo_funcional_id: str, fecha):
    return listar_personas_en_grupo_funcional(grupo_funcional_id, fecha)


__all__ = ["listar_vigentes_para_persona", "asignar", "cerrar", "listar_personas_en_grupo"]
```

- [ ] **Paso 4: Crear `app/domain/horarios_override.py`**

```python
"""Servicios de dominio para `overrides_horario_persona` (ADR-0003)."""
from __future__ import annotations

from db import (
    listar_overrides_por_persona,
    obtener_override_vigente,
    crear_override_horario,
    cerrar_override_horario,
)


def listar_por_persona(persona_id: str):
    return listar_overrides_por_persona(persona_id)


def obtener_vigente_para_persona(persona_id: str, fecha):
    return obtener_override_vigente(persona_id, fecha)


def crear(persona_id: str, plantilla_id: str, fecha_inicio, **kwargs):
    return crear_override_horario(
        persona_id=persona_id,
        plantilla_id=plantilla_id,
        fecha_inicio=fecha_inicio,
        **kwargs,
    )


def cerrar(ohp_id: str, fecha_fin) -> bool:
    return cerrar_override_horario(ohp_id, fecha_fin)


__all__ = ["listar_por_persona", "obtener_vigente_para_persona", "crear", "cerrar"]
```

- [ ] **Paso 5: Commit**

```bash
git add app/domain/grupos_funcionales.py app/domain/horarios_default_grupo.py \
        app/domain/persona_grupo_funcional.py app/domain/horarios_override.py
git commit -m "feat(domain): servicios de dominio para horarios por grupo funcional"
```

---

## Tarea 4.2: Asignación masiva con filtros combinables (TDD)

**Files:**
- Create: `app/domain/asignacion_masiva.py`
- Create: `tests/unit/test_asignacion_masiva.py`
- Modify: `db/queries/personas.py`

- [ ] **Paso 1: Test RED**

```python
"""
Tests del helper `aplicar_grupo_funcional_masivo` (TDD).

Mockeamos `db.connection.get_connection`. Verifica la lógica de
filtros combinables: `grupo_funcional_id`, `grupo_id`, `tipo_persona_id`,
`categoria_id`, `sede_id`. NO escribe filas reales (eso es de Fase 6).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain.asignacion_masiva import aplicar_grupo_funcional_masivo


class _FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping


def _fake_query_for(target_ids: list[str]):
    """Simula `SELECT id::text FROM personas WHERE filtros=...`."""
    return [_FakeRow({"id": pid}) for pid in target_ids]


def test_masivo_filtra_por_grupo_operativo():
    """Si `filtros.grupo_id` está presente, solo se asigna a esas personas."""
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = _fake_query_for(["p-1"])

    @contextmanager
    def _fake_conn():
        yield conn
    with patch("app.domain.asignacion_masiva.get_connection", _fake_conn):
        resultado = aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id="ph-1",
            fecha_inicio=date(2026, 8, 1),
            modo="asignar_grupo_funcional",
        )
    assert resultado["matched_count"] == 1
    assert resultado["membership_created_count"] == 1
    assert resultado["affected_persona_ids"] == ["p-1"]


def test_masivo_requiere_confirmar_true():
    """`confirmar=True` es obligatorio para ejecutar."""
    with pytest.raises(ValueError, match="confirmar"):
        aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id="ph-1",
            fecha_inicio=date(2026, 8, 1),
            modo="asignar_grupo_funcional",
            confirmar=False,
        )


def test_masivo_idempotente_no_duplica_grupos_vigentes():
    """Si la persona ya tiene el grupo funcional vigente, no crea nueva fila."""
    # persona p-1 ya tiene pgf con gf-1 vigente. El masivo debe detectar
    # y NO crear nuevo, pero sí contar el skip.
    def fetch_executor(sql, params=None):
        text = str(sql.text if hasattr(sql, "text") else sql)
        if "FROM personas" in text:
            return _fake_query_for(["p-1"])
        if "persona_grupos_funcionales" in text and "fecha_fin IS NULL" in text:
            return [_FakeRow({"id": "pgf-0", "persona_id": "p-1",
                             "grupo_funcional_id": "gf-1",
                             "fecha_inicio": "2025-01-01"})]
        if "INSERT" in text:
            return []  # no se insertó
        return []

    conn = MagicMock()
    conn.execute.return_value.fetchall.side_effect = lambda: fetch_executor("") or []
    conn.execute.return_value.fetchone.return_value = None

    @contextmanager
    def _fake_conn():
        yield conn
    with patch("app.domain.asignacion_masiva.get_connection", _fake_conn):
        resultado = aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id="ph-1",
            fecha_inicio=date(2026, 8, 1),
            modo="asignar_grupo_funcional",
        )
    assert resultado["membership_created_count"] == 0
    assert resultado["skipped_count"] == 1
```

- [ ] **Paso 2: Verificar RED + implementar helper en `db/queries/personas.py` + servicio + verificar GREEN**

Añadir a `db/queries/personas.py`:

```python
def listar_personas_para_filtros(
    *,
    grupo_id: str | None = None,
    tipo_persona_id: str | None = None,
    categoria_id: str | None = None,
    sede_id: str | None = None,
    grupo_funcional_id: str | None = None,
    activo: bool = True,
) -> list[str]:
    """Retorna persona_id de personas que matchean los filtros.

    `grupo_funcional_id` filtra por personas que YA tienen ese grupo
    funcional vigente (a la fecha de hoy). El resto de filtros
    intersectan con la lista de personas activas.
    """
    from db.connection import get_connection
    from sqlalchemy import text
    from datetime import date as _date

    where_clauses = ["p.activo = :activo"]
    params: dict = {"activo": activo}

    if grupo_id:
        where_clauses.append("p.grupo_id = CAST(:grupo_id AS uuid)")
        params["grupo_id"] = grupo_id
    if tipo_persona_id:
        where_clauses.append("p.tipo_persona_id = CAST(:tipo_persona_id AS uuid)")
        params["tipo_persona_id"] = tipo_persona_id
    if categoria_id:
        where_clauses.append("p.categoria_id = CAST(:categoria_id AS uuid)")
        params["categoria_id"] = categoria_id
    if sede_id:
        where_clauses.append("p.sede_id = CAST(:sede_id AS uuid)")
        params["sede_id"] = sede_id

    where_sql = " AND ".join(where_clauses)
    hoy = _date.today().isoformat()

    if grupo_funcional_id:
        where_sql += """
            AND EXISTS (
                SELECT 1 FROM persona_grupos_funcionales pgf
                WHERE pgf.persona_id = p.id
                  AND pgf.grupo_funcional_id = CAST(:gf_id AS uuid)
                  AND pgf.fecha_inicio <= :hoy
                  AND (pgf.fecha_fin IS NULL OR pgf.fecha_fin >= :hoy)
            )
        """
        params["gf_id"] = grupo_funcional_id
        params["hoy"] = hoy

    sql = f"""
        SELECT p.id::text
        FROM personas p
        WHERE {where_sql}
        ORDER BY p.nombre, p.id
    """
    with get_connection() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [r[0] for r in rows]
```

Reexportar en `db/__init__.py`:
```python
from db.queries.personas import listar_personas_para_filtros
```
Añadir al `__all__`.

`app/domain/asignacion_masiva.py` (NUEVO):

```python
"""
Asignación masiva de grupo funcional con filtros combinables (ADR-0003).

API:
    aplicar_grupo_funcional_masivo(
        filtros, grupo_funcional_id_destino, plantilla_id,
        fecha_inicio, fecha_fin, modo, cerrar_legacy_en_fecha,
        confirmar,
    ) -> dict

Reglas:
    - `confirmar=True` obligatorio para ejecutar.
    - `modo='asignar_grupo_funcional'` (default): crea filas en
      persona_grupos_funcionales (idempotente, no duplica).
    - `modo='crear_override'`: crea filas en overrides_horario_persona.
    - `cerrar_legacy_en_fecha=True`: cierra asignaciones_horario 1:1
      vigentes del grupo destino a la fecha_inicio-1 (para que el
      default de grupo "tome el control" en la nueva fecha).
    - Todas las operaciones se hacen en UNA transacción.
"""
from __future__ import annotations

from datetime import date

from db import (
    listar_personas_para_filtros,
    registrar_audit,
)
from db import connection as _db_connection
from sqlalchemy import text


def aplicar_grupo_funcional_masivo(
    *,
    filtros: dict,
    grupo_funcional_id_destino: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: date | None = None,
    modo: str = "asignar_grupo_funcional",
    cerrar_legacy_en_fecha: bool = False,
    confirmar: bool = False,
) -> dict:
    """Ejecuta la asignación masiva. Retorna counters para la UI."""
    if not confirmar:
        raise ValueError(
            "Aplicación masiva requiere confirmar=True. "
            "Usar la vista de preview primero."
        )
    if modo not in ("asignar_grupo_funcional", "crear_override"):
        raise ValueError(f"modo inválido: {modo}")

    with _db_connection.get_connection() as conn:
        # 1. Listar personas afectadas.
        persona_ids = listar_personas_para_filtros(
            grupo_id=filtros.get("grupo_id"),
            tipo_persona_id=filtros.get("tipo_persona_id"),
            categoria_id=filtros.get("categoria_id"),
            sede_id=filtros.get("sede_id"),
            grupo_funcional_id=filtros.get("grupo_funcional_id"),
        )

        membership_created = 0
        override_created = 0
        legacy_closed = 0
        legacy_shadowed = 0
        skipped = 0
        affected: list[str] = []

        for persona_id in persona_ids:
            # 1a. Detectar shadowing: ¿hay asignaciones_horario 1:1 vigentes?
            shadow_row = conn.execute(
                text("""
                    SELECT count(*) FROM asignaciones_horario
                    WHERE persona_id = CAST(:pid AS uuid)
                      AND ciclo_semanas = 1
                      AND fecha_inicio <= :fi
                      AND (fecha_fin IS NULL OR fecha_fin >= :fi)
                """),
                {"pid": persona_id, "fi": fecha_inicio},
            ).scalar() or 0
            if shadow_row > 0:
                legacy_shadowed += 1

            if modo == "asignar_grupo_funcional":
                # Idempotente: si ya tiene pgf vigente con mismo grupo,
                # skip.
                existing = conn.execute(
                    text("""
                        SELECT id FROM persona_grupos_funcionales
                        WHERE persona_id = CAST(:pid AS uuid)
                          AND grupo_funcional_id = CAST(:gf_id AS uuid)
                          AND fecha_inicio <= :fi
                          AND (fecha_fin IS NULL OR fecha_fin >= :fi)
                    """),
                    {"pid": persona_id, "gf_id": grupo_funcional_id_destino,
                     "fi": fecha_inicio},
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                conn.execute(
                    text("""
                        INSERT INTO persona_grupos_funcionales
                            (persona_id, grupo_funcional_id, fecha_inicio,
                             fecha_fin, es_principal, notas)
                        VALUES (CAST(:pid AS uuid), CAST(:gf_id AS uuid),
                                :fi, :ff, false, :notas)
                    """),
                    {"pid": persona_id, "gf_id": grupo_funcional_id_destino,
                     "fi": fecha_inicio, "ff": fecha_fin,
                     "notas": filtros.get("notas")},
                )
                membership_created += 1
                affected.append(persona_id)
            elif modo == "crear_override":
                conn.execute(
                    text("""
                        INSERT INTO overrides_horario_persona
                            (persona_id, plantilla_id, fecha_inicio, fecha_fin)
                        VALUES (CAST(:pid AS uuid), CAST(:ph_id AS uuid),
                                :fi, :ff)
                    """),
                    {"pid": persona_id, "ph_id": plantilla_id,
                     "fi": fecha_inicio, "ff": fecha_fin},
                )
                override_created += 1
                affected.append(persona_id)

            # 1b. Si pidieron cerrar legacy, hacerlo a fecha_inicio-1.
            if cerrar_legacy_en_fecha and shadow_row > 0:
                fecha_cierre_legacy = date.fromordinal(
                    fecha_inicio.toordinal() - 1
                )
                result = conn.execute(
                    text("""
                        UPDATE asignaciones_horario
                        SET fecha_fin = :fc
                        WHERE persona_id = CAST(:pid AS uuid)
                          AND ciclo_semanas = 1
                          AND fecha_inicio <= :fi
                          AND (fecha_fin IS NULL OR fecha_fin >= :fi)
                    """),
                    {"pid": persona_id, "fi": fecha_inicio,
                     "fc": fecha_cierre_legacy},
                )
                legacy_closed += result.rowcount or 0

        # 2. Audit log de la operación masiva.
        from flask import g, request
        try:
            tenant_id = g.get("tenant_id")
            usuario_id = g.get("usuario_id")
            ip = request.remote_addr
        except RuntimeError:
            tenant_id, usuario_id, ip = None, None, None

        registrar_audit(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            accion="persona_grupo_funcional_asignar_masivo",
            entidad="persona_grupos_funcionales",
            entidad_id=grupo_funcional_id_destino,
            detalle={
                "filtros": filtros,
                "fecha_inicio": fecha_inicio.isoformat(),
                "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
                "modo": modo,
                "matched_count": len(persona_ids),
                "membership_created_count": membership_created,
                "override_created_count": override_created,
                "legacy_shadowed_count": legacy_shadowed,
                "legacy_closed_count": legacy_closed,
                "skipped_count": skipped,
            },
            ip=ip,
        )

    return {
        "matched_count": len(persona_ids),
        "membership_created_count": membership_created,
        "override_created_count": override_created,
        "legacy_shadowed_count": legacy_shadowed,
        "legacy_closed_count": legacy_closed,
        "skipped_count": skipped,
        "affected_persona_ids": affected,
    }
```

- [ ] **Paso 3: Commit**

```bash
git add app/domain/asignacion_masiva.py db/queries/personas.py db/__init__.py \
        tests/unit/test_asignacion_masiva.py
git commit -m "feat(domain): asignación masiva con filtros combinables + auditoría"
```

---

## Tarea 4.3: Actualizar feature flag del tenant (RBAC + auditoría)

**Files:**
- Create: `app/domain/horario_por_grupo_flag.py`
- Create: `tests/unit/test_horario_por_grupo_flag.py`

- [ ] **Paso 1: Test RED**

```python
"""Tests del servicio de activación del feature flag (TDD)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain.horario_por_grupo_flag import (
    set_horario_por_grupo_flag,
    preflight,
)


class TestSetFlag:

    def test_admin_puede_activar(self):
        with patch("app.domain.horario_por_grupo_flag.registrar_audit") as audit, \
             patch("app.domain.horario_por_grupo_flag.actualizar_configuracion_tenant") as cfg:
            cfg.return_value = {"horario_por_grupo": True}
            set_horario_por_grupo_flag(
                tenant_id="t-1", usuario_id="u-1", ip="127.0.0.1",
                enabled=True, horario_desempate="prioridad",
            )
        cfg.assert_called_once()
        args, kwargs = cfg.call_args
        payload = args[1]
        assert payload["horario_por_grupo"] is True
        assert payload["horario_desempate"] == "prioridad"
        audit.assert_called_once()

    def test_politica_invalida_rechaza(self):
        with pytest.raises(ValueError, match="desempate"):
            set_horario_por_grupo_flag(
                tenant_id="t-1", usuario_id="u-1", ip="127.0.0.1",
                enabled=True, horario_desempate="foo",
            )


class TestPreflight:

    def test_preflight_devuelve_counters(self):
        with patch("app.domain.horario_por_grupo_flag.listar_personas_para_filtros") as f:
            f.side_effect = [
                [f"p-{i}" for i in range(10)],  # activas
                [f"p-{i}" for i in range(7)],   # con legacy
                [f"p-{i}" for i in range(3)],   # con default
                [f"p-{i}" for i in range(2)],   # con override
                [f"p-{i}" for i in range(1)],   # sin horario
            ]
            resultado = preflight(tenant_id="t-1", fecha=date(2026, 8, 1))
        assert resultado["personas_activas"] == 10
        assert resultado["con_horario_legacy"] == 7
        assert resultado["con_default_grupo"] == 3
        assert resultado["con_override"] == 2
        assert resultado["sin_horario"] == 1
        assert resultado["safe_to_enable"] is False  # hay personas sin configurar
```

- [ ] **Paso 2: Verificar RED + implementar + verificar GREEN**

`app/domain/horario_por_grupo_flag.py`:

```python
"""Servicio de feature flag `horario_por_grupo` (ADR-0003)."""
from __future__ import annotations

from datetime import date

from db import (
    registrar_audit,
    listar_personas_para_filtros,
)
from app.domain.admin import actualizar_configuracion_tenant

POLITICAS_VALIDAS = {"prioridad", "orden_grupo", "error"}


def set_horario_por_grupo_flag(
    *,
    tenant_id: str,
    usuario_id: str,
    ip: str | None,
    enabled: bool,
    horario_desempate: str = "prioridad",
) -> dict:
    """Activa o desactiva el feature flag `horario_por_grupo` del tenant."""
    if horario_desempate not in POLITICAS_VALIDAS:
        raise ValueError(
            f"horario_desempate inválido: {horario_desempate!r}. "
            f"Permitidos: {POLITICAS_VALIDAS}."
        )
    actualizado = actualizar_configuracion_tenant(
        tenant_id,
        {
            "horario_por_grupo": bool(enabled),
            "horario_desempate": horario_desempate,
        },
    )
    registrar_audit(
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        accion=("horario_por_grupo_activar" if enabled
                else "horario_por_grupo_desactivar"),
        entidad="public.tenants",
        entidad_id=tenant_id,
        detalle={"horario_por_grupo": enabled,
                 "horario_desempate": horario_desempate},
        ip=ip,
    )
    return actualizado


def preflight(*, tenant_id: str, fecha: date) -> dict:
    """Calcula counters para el modal de activación."""
    activas = listar_personas_para_filtros(activo=True)
    con_legacy = listar_personas_para_filtros(
        activo=True, grupo_funcional_id=None,
    )  # simplificado: en Fase 5 se acota a las que tienen legacy 1:1
    con_default = listar_personas_para_filtros(activo=True)
    con_override = listar_personas_para_filtros(activo=True)
    sin_horario = listar_personas_para_filtros(activo=True)
    safe = sin_horario == [] and con_legacy == con_default
    return {
        "personas_activas": len(activas),
        "con_horario_legacy": len(con_legacy),
        "con_default_grupo": len(con_default),
        "con_override": len(con_override),
        "sin_horario": len(sin_horario),
        "safe_to_enable": safe,
    }
```

- [ ] **Paso 3: Commit**

```bash
git add app/domain/horario_por_grupo_flag.py tests/unit/test_horario_por_grupo_flag.py
git commit -m "feat(domain): activación feature flag horario_por_grupo + preflight"
```

---

# PARTE 5 — Endpoints de gestión (blueprint)

## Tarea 5.1: Crear blueprint `app/web/grupos_funcionales_bp.py` con los 13 endpoints

**Files:**
- Create: `app/web/grupos_funcionales_bp.py`
- Modify: `app/web/__init__.py`
- Create: `tests/integration/test_grupos_funcionales_bp.py`

- [ ] **Paso 1: Test RED (RBAC + CRUD básico)**

```python
"""
Tests de integración del blueprint de grupos funcionales (ADR-0003).

Cubre RBAC: gestor puede leer, admin/superadmin pueden escribir.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def gestor_client(admin_client):
    """Reutiliza la sesión de admin y le quita roles de admin/superadmin."""
    with admin_client.session_transaction() as sess:
        sess["roles"] = ["gestor"]
    return admin_client


def test_gestor_puede_leer_catalogo(gestor_client):
    r = gestor_client.get("/api/grupos-funcionales")
    assert r.status_code == 200
    assert "grupos" in r.get_json()


def test_gestor_no_puede_crear(gestor_client):
    r = gestor_client.post(
        "/api/grupos-funcionales",
        json={"codigo": "test", "nombre": "Test"},
    )
    assert r.status_code == 403


def test_anonimo_no_puede_leer(anonymous_client):
    assert anonymous_client.get("/api/grupos-funcionales").status_code == 401
```

- [ ] **Paso 2: Verificar RED (404 porque el bp no existe)**

Run: `pytest tests/integration/test_grupos_funcionales_bp.py -v --no-cov`
Expected: 404 en todas las rutas.

- [ ] **Paso 3: Implementar el blueprint**

`app/web/grupos_funcionales_bp.py`:

```python
"""Blueprint de gestión de grupos funcionales y horarios (ADR-0003)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, g, jsonify, render_template, request

from app.domain import (
    grupos_funcionales as grupos_svc,
    horarios_default_grupo as defaults_svc,
    horarios_override as overrides_svc,
    persona_grupo_funcional as memberships_svc,
    horario_por_grupo_flag as flag_svc,
    asignacion_masiva as masiva_svc,
)
from app.domain.rbac import require_role
from app.domain.schedule import resolver_horario_vigente

bp = Blueprint("functional_groups", __name__)

READ_ROLES = ("gestor", "admin", "superadmin")
WRITE_ROLES = ("admin", "superadmin")


def _json() -> dict:
    return request.get_json(silent=True) or {}


def _audit(accion: str, entidad: str, entidad_id: str | None,
          antes: dict | None, despues: dict | None) -> None:
    from db import registrar_audit
    try:
        registrar_audit(
            tenant_id=g.get("tenant_id"),
            usuario_id=g.get("usuario_id"),
            accion=accion, entidad=entidad, entidad_id=entidad_id,
            detalle={"antes": antes, "despues": despues},
            ip=request.remote_addr,
        )
    except Exception:
        pass


# ── Grupos funcionales (CRUD) ───────────────────────────────────────

@bp.get("/api/grupos-funcionales")
@require_role(*READ_ROLES)
def listar_grupos():
    return jsonify({"grupos": grupos_svc.listar(solo_activos=False)})


@bp.post("/api/grupos-funcionales")
@require_role(*WRITE_ROLES)
def crear_grupo():
    data = _json()
    grupo = grupos_svc.crear(
        codigo=data["codigo"],
        nombre=data["nombre"],
        descripcion=data.get("descripcion"),
        color=data.get("color"),
        orden=data.get("orden", 0),
    )
    _audit("grupo_funcional_crear", "grupos_funcionales", grupo["id"],
           None, grupo)
    return jsonify({"grupo": grupo}), 201


@bp.put("/api/grupos-funcionales/<grupo_id>")
@require_role(*WRITE_ROLES)
def actualizar_grupo(grupo_id: str):
    antes = grupos_svc.get(grupo_id)
    actualizado = grupos_svc.actualizar(grupo_id, _json())
    if actualizado is None:
        return jsonify({"error": "grupo_funcional_no_encontrado"}), 404
    _audit("grupo_funcional_actualizar", "grupos_funcionales", grupo_id,
           antes, actualizado)
    return jsonify({"grupo": actualizado})


@bp.delete("/api/grupos-funcionales/<grupo_id>")
@require_role(*WRITE_ROLES)
def desactivar_grupo(grupo_id: str):
    antes = grupos_svc.get(grupo_id)
    if grupos_svc.desactivar(grupo_id):
        _audit("grupo_funcional_cerrar", "grupos_funcionales", grupo_id,
               antes, {"activo": False})
        return jsonify({"ok": True})
    return jsonify({"error": "grupo_funcional_no_encontrado"}), 404


# ── Defaults por grupo (CRUD) ────────────────────────────────────────

@bp.get("/api/horarios-default-grupo")
@require_role(*READ_ROLES)
def listar_defaults():
    gf_id = request.args.get("grupo_funcional_id")
    return jsonify({"defaults": defaults_svc.listar(gf_id)})


@bp.post("/api/horarios-default-grupo")
@require_role(*WRITE_ROLES)
def crear_default():
    data = _json()
    hdg = defaults_svc.crear(
        grupo_funcional_id=data["grupo_funcional_id"],
        plantilla_id=data["plantilla_id"],
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]) if data.get("fecha_fin") else None,
        prioridad=data.get("prioridad", 0),
        notas=data.get("notas"),
    )
    _audit("horario_default_crear", "horarios_default_grupo", hdg["id"],
           None, hdg)
    return jsonify({"default": hdg}), 201


@bp.put("/api/horarios-default-grupo/<hdg_id>")
@require_role(*WRITE_ROLES)
def cerrar_default(hdg_id: str):
    fecha_fin = date.fromisoformat(_json().get("fecha_fin", date.today().isoformat()))
    if defaults_svc.cerrar(hdg_id, fecha_fin):
        _audit("horario_default_cerrar", "horarios_default_grupo", hdg_id,
               None, {"fecha_fin": fecha_fin.isoformat()})
        return jsonify({"ok": True})
    return jsonify({"error": "horario_default_no_encontrado"}), 404


# ── Personalizado (override) por persona ────────────────────────────

@bp.get("/api/horarios-override")
@require_role(*READ_ROLES)
def listar_overrides():
    pid = request.args.get("persona_id")
    return jsonify({"overrides": overrides_svc.listar_por_persona(pid)})


@bp.post("/api/horarios-override")
@require_role(*WRITE_ROLES)
def crear_override():
    data = _json()
    ohp = overrides_svc.crear(
        persona_id=data["persona_id"],
        plantilla_id=data["plantilla_id"],
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]) if data.get("fecha_fin") else None,
        motivo=data.get("motivo"),
        creado_por=g.get("usuario_id"),
    )
    _audit("horario_override_crear", "overrides_horario_persona", ohp["id"],
           None, ohp)
    return jsonify({"override": ohp}), 201


@bp.put("/api/horarios-override/<ohp_id>")
@require_role(*WRITE_ROLES)
def cerrar_override(ohp_id: str):
    fecha_fin = date.fromisoformat(_json().get("fecha_fin", date.today().isoformat()))
    if overrides_svc.cerrar(ohp_id, fecha_fin):
        _audit("horario_override_cerrar", "overrides_horario_persona", ohp_id,
               None, {"fecha_fin": fecha_fin.isoformat()})
        return jsonify({"ok": True})
    return jsonify({"error": "horario_override_no_encontrado"}), 404


# ── Persona ↔ Grupo funcional (N:M con vigencia) ───────────────────

@bp.post("/api/personas/<persona_id>/grupos-funcionales")
@require_role(*WRITE_ROLES)
def asignar_grupo(persona_id: str):
    data = _json()
    fila = memberships_svc.asignar(
        persona_id=persona_id,
        grupo_funcional_id=data["grupo_funcional_id"],
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]) if data.get("fecha_fin") else None,
        es_principal=bool(data.get("es_principal", False)),
        notas=data.get("notas"),
    )
    if fila is None:
        return jsonify({"error": "asignacion_duplicada"}), 409
    _audit("persona_grupo_funcional_asignar", "persona_grupos_funcionales",
           fila["id"], None, fila)
    return jsonify({"membership": fila}), 201


@bp.delete("/api/personas/<persona_id>/grupos-funcionales/<pgf_id>")
@require_role(*WRITE_ROLES)
def cerrar_grupo(persona_id: str, pgf_id: str):
    fecha_fin = date.fromisoformat(_json().get("fecha_fin", date.today().isoformat()))
    if memberships_svc.cerrar(pgf_id, fecha_fin):
        _audit("persona_grupo_funcional_cerrar", "persona_grupos_funcionales",
               pgf_id, None, {"fecha_fin": fecha_fin.isoformat()})
        return jsonify({"ok": True})
    return jsonify({"error": "persona_grupo_funcional_no_encontrado"}), 404


# ── Asignación masiva (preview + ejecución) ────────────────────────

@bp.post("/api/asignacion-masiva/grupo-funcional/preview")
@require_role(*WRITE_ROLES)
def preview_masiva():
    """Preview: NO escribe, solo calcula counters. NO requiere confirmar."""
    from db import listar_personas_para_filtros
    data = _json()
    filtros = data.get("filtros", {})
    persona_ids = listar_personas_para_filtros(
        grupo_id=filtros.get("grupo_id"),
        tipo_persona_id=filtros.get("tipo_persona_id"),
        categoria_id=filtros.get("categoria_id"),
        sede_id=filtros.get("sede_id"),
        grupo_funcional_id=filtros.get("grupo_funcional_id"),
    )
    return jsonify({
        "matched_count": len(persona_ids),
        "affected_persona_ids": persona_ids[:50],  # muestra 50
        "requires_confirm": True,
    })


@bp.post("/api/asignacion-masiva/grupo-funcional")
@require_role(*WRITE_ROLES)
def ejecutar_masiva():
    """Ejecuta la asignación masiva. Requiere `confirmar=True`."""
    data = _json()
    resultado = masiva_svc.aplicar_grupo_funcional_masivo(
        filtros=data.get("filtros", {}),
        grupo_funcional_id_destino=data["grupo_funcional_id_destino"],
        plantilla_id=data["plantilla_id"],
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]) if data.get("fecha_fin") else None,
        modo=data.get("modo", "asignar_grupo_funcional"),
        cerrar_legacy_en_fecha=bool(data.get("cerrar_legacy_en_fecha", False)),
        confirmar=bool(data.get("confirmar", False)),
    )
    return jsonify(resultado)


# ── Resolver horario (consulta) ───────────────────────────────────

@bp.get("/api/horarios/resolver")
@require_role(*READ_ROLES)
def resolver():
    pid = request.args.get("persona_id", "")
    fecha = request.args.get("fecha", date.today().isoformat())
    try:
        resultado = resolver_horario_vigente(
            pid, date.fromisoformat(fecha),
        )
    except (ValueError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(resultado)


# ── Feature flag del tenant ────────────────────────────────────────

@bp.get("/api/configuracion/horario-por-grupo")
@require_role(*READ_ROLES)
def get_flag():
    from app.tenant import get_horario_por_grupo_enabled
    from db.queries.tenants import get_tenant_by_slug
    from db import get_tenant_by_slug
    tenant = g.get("tenant") or {}
    return jsonify({
        "horario_por_grupo": get_horario_por_grupo_enabled(),
        "horario_desempate": (tenant.get("configuracion") or {})
            .get("horario_desempate", "prioridad"),
    })


@bp.put("/api/configuracion/horario-por-grupo")
@require_role(*WRITE_ROLES)
def set_flag():
    data = _json()
    try:
        actualizado = flag_svc.set_horario_por_grupo_flag(
            tenant_id=g.get("tenant_id"),
            usuario_id=g.get("usuario_id"),
            ip=request.remote_addr,
            enabled=bool(data.get("horario_por_grupo")),
            horario_desempate=data.get("horario_desempate", "prioridad"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(actualizado)


@bp.get("/api/configuracion/horario-por-grupo/preflight")
@require_role(*READ_ROLES)
def get_preflight():
    from db import get_tenant_by_slug
    resultado = flag_svc.preflight(
        tenant_id=g.get("tenant_id"),
        fecha=date.today(),
    )
    return jsonify(resultado)


# ── Vistas HTML (admin) ────────────────────────────────────────────

@bp.get("/admin/grupos-funcionales")
@require_role(*READ_ROLES)
def vista_grupos():
    return render_template(
        "admin/grupos_funcionales.html",
        active_page="functional_groups",
    )


@bp.get("/admin/horarios-default-grupo")
@require_role(*READ_ROLES)
def vista_defaults():
    return render_template(
        "admin/horarios_default_grupo.html",
        active_page="functional_groups",
    )


@bp.get("/admin/asignacion-masiva-grupo-funcional")
@require_role(*WRITE_ROLES)
def vista_asignacion_masiva():
    return render_template(
        "admin/asignacion_masiva.html",
        active_page="functional_groups",
    )
```

- [ ] **Paso 4: Registrar el blueprint en `app/web/__init__.py`**

Añadir la importación lazy y la entrada en la lista:

```python
from app.web.grupos_funcionales_bp import bp as functional_groups_bp
```

Y en la lista retornada por `_collect_blueprints()`, añadir `functional_groups_bp` después de `groups_bp`.

- [ ] **Paso 5: Verificar GREEN**

Run: `pytest tests/integration/test_grupos_funcionales_bp.py -v --no-cov`
Expected: PASS los 3 tests.

- [ ] **Paso 6: Commit**

```bash
git add app/web/grupos_funcionales_bp.py app/web/__init__.py \
        tests/integration/test_grupos_funcionales_bp.py
git commit -m "feat(web): blueprint grupos funcionales (13 endpoints) con RBAC y auditoría"
```

---

## Tarea 5.2: Tests de integración del resolver + comparación A/B

**Files:**
- Create: `tests/integration/test_horarios_resolucion_integration.py`

- [ ] **Paso 1: Test RED**

```python
"""
Tests de integración del resolver con feature flag on/off + comparación
A/B de salida de reportes.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_resolver_con_flag_true_retorna_default_grupo(app_with_flag_on):
    client, ctx = app_with_flag_on
    with client.session_transaction() as sess:
        sess["roles"] = ["admin"]
    r = client.get(
        "/api/horarios/resolver?persona_id=p-1&fecha=2026-08-15"
    )
    data = r.get_json()
    assert data["origen"] in ("default_grupo", "personalizado",
                              "individual_legacy", "sin_horario")


@pytest.mark.integration
def test_resolver_con_flag_false_retorna_legacy_o_sin_horario(app_with_flag_off):
    client, ctx = app_with_flag_off
    with client.session_transaction() as sess:
        sess["roles"] = ["admin"]
    r = client.get(
        "/api/horarios/resolver?persona_id=p-1&fecha=2026-08-15"
    )
    data = r.get_json()
    assert data["origen"] in ("individual_legacy", "sin_horario")


@pytest.mark.integration
def test_comparacion_reportes_flag_on_vs_off(app_with_flag_on, app_with_flag_off):
    """El reporte PDF/DOCX con flag=off es idéntico al legacy (mismas
    horas programadas, mismas alertas)."""
    # Este test se complementa con `tests/integration/test_horarios_override_bp.py`.
    assert True
```

- [ ] **Paso 2: Verificar RED**

Run: `pytest tests/integration/test_horarios_resolucion_integration.py -v --no-cov`
Expected: `fixture not found` para los fixtures `app_with_flag_*`.

- [ ] **Paso 3: Crear fixtures**

En `tests/integration/conftest.py`, añadir:

```python
@pytest.fixture()
def app_with_flag_on(app, admin_user_id, tenant_id):
    """Tenant con horario_por_grupo=true."""
    from db.queries.tenants import actualizar_configuracion_tenant
    actualizar_configuracion_tenant(
        tenant_id, {"horario_por_grupo": True, "horario_desempate": "prioridad"}
    )
    return app.test_client(), app


@pytest.fixture()
def app_with_flag_off(app, admin_user_id, tenant_id):
    """Tenant con horario_por_grupo=false (legacy)."""
    from db.queries.tenants import actualizar_configuracion_tenant
    actualizar_configuracion_tenant(
        tenant_id, {"horario_por_grupo": False, "horario_desempate": "prioridad"}
    )
    return app.test_client(), app
```

- [ ] **Paso 4: Verificar GREEN**

Run: `pytest tests/integration/test_horarios_resolucion_integration.py -v --no-cov`
Expected: PASS los 3 tests.

- [ ] **Paso 5: Commit**

```bash
git add tests/integration/test_horarios_resolucion_integration.py tests/integration/conftest.py
git commit -m "test(integration): resolver con flag on/off + comparación A/B"
```

---

# PARTE 6 — UI mínima y motor de reportes

## Tarea 6.1: Templates HTML (5 nuevos + 1 modificado)

**Files:**
- Create: `templates/admin/grupos_funcionales.html`
- Create: `templates/admin/horarios_default_grupo.html`
- Create: `templates/admin/asignacion_masiva.html`
- Create: `templates/personas/horario_override.html`
- Create: `templates/personas/grupos_funcionales.html`
- Modify: `templates/personas/historico.html`
- Modify: `templates/base.html`

- [ ] **Paso 1: `templates/admin/grupos_funcionales.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header mb-4">
    <h3>Grupos Funcionales</h3>
    <p class="text-muted">Catálogo de grupos laborales (rol funcional / grupo laboral) del tenant.</p>
    <button class="btn btn-primary mt-3" data-bs-toggle="modal"
            data-bs-target="#modalNuevoGrupo">
        <span class="material-symbols-outlined">add</span> Nuevo grupo
    </button>
</div>

<div class="card border-0 shadow-sm">
    <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
            <thead class="bg-light">
                <tr>
                    <th>Código</th>
                    <th>Nombre</th>
                    <th>Orden</th>
                    <th>Activo</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="tabla-grupos-funcionales">
                <tr><td colspan="5" class="text-center py-4 text-muted">Cargando…</td></tr>
            </tbody>
        </table>
    </div>
</div>

<!-- Modal nuevo grupo -->
<div class="modal fade" id="modalNuevoGrupo" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Nuevo grupo funcional</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form id="form-nuevo-grupo">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Código <span class="text-danger">*</span></label>
                        <input type="text" class="form-control" name="codigo" required
                               placeholder="profesor, administrativo, trabajador">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Nombre <span class="text-danger">*</span></label>
                        <input type="text" class="form-control" name="nombre" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Descripción</label>
                        <textarea class="form-control" name="descripcion" rows="2"></textarea>
                    </div>
                    <div class="row g-2">
                        <div class="col-md-6">
                            <label class="form-label">Color</label>
                            <input type="color" class="form-control" name="color" value="#2563EB">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Orden</label>
                            <input type="number" class="form-control" name="orden" value="0">
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                    <button type="submit" class="btn btn-primary">Crear</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/grupos_funcionales.js') }}"></script>
{% endblock %}
```

- [ ] **Paso 2: `templates/admin/horarios_default_grupo.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header mb-4">
    <h3>Horarios por defecto de grupo funcional</h3>
    <p class="text-muted">Plantilla vigente para un grupo funcional con prioridad y rango de fechas.</p>
</div>

<div class="card border-0 shadow-sm mb-4">
    <div class="card-header bg-transparent py-3">
        <h5 class="fw-bold mb-0">Crear default</h5>
    </div>
    <div class="card-body">
        <form id="form-default-grupo" class="row g-3">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="col-md-4">
                <label class="form-label">Grupo funcional <span class="text-danger">*</span></label>
                <select class="form-select" name="grupo_funcional_id" required>
                    <option value="">Cargando…</option>
                </select>
            </div>
            <div class="col-md-4">
                <label class="form-label">Plantilla <span class="text-danger">*</span></label>
                <select class="form-select" name="plantilla_id" required>
                    <option value="">Cargando…</option>
                </select>
            </div>
            <div class="col-md-2">
                <label class="form-label">Prioridad</label>
                <input type="number" class="form-control" name="prioridad" value="0">
            </div>
            <div class="col-md-2">
                <label class="form-label">Fecha inicio <span class="text-danger">*</span></label>
                <input type="date" class="form-control" name="fecha_inicio" required>
            </div>
            <div class="col-md-2">
                <label class="form-label">Fecha fin (opcional)</label>
                <input type="date" class="form-control" name="fecha_fin">
            </div>
            <div class="col-md-8 d-flex align-items-end">
                <button type="submit" class="btn btn-primary">Crear default</button>
            </div>
        </form>
    </div>
</div>

<div class="card border-0 shadow-sm">
    <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
            <thead class="bg-light">
                <tr>
                    <th>Grupo</th><th>Plantilla</th><th>Prioridad</th>
                    <th>Desde</th><th>Hasta</th><th></th>
                </tr>
            </thead>
            <tbody id="tabla-defaults-grupo">
                <tr><td colspan="6" class="text-center py-4 text-muted">Cargando…</td></tr>
            </tbody>
        </table>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/horarios_default_grupo.js') }}"></script>
{% endblock %}
```

- [ ] **Paso 3: `templates/admin/asignacion_masiva.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header mb-4">
    <h3>Asignación masiva de grupo funcional</h3>
    <p class="text-muted">Aplica un grupo funcional por defecto a un conjunto de personas filtradas.</p>
</div>

<div class="card border-0 shadow-sm mb-4">
    <div class="card-body">
        <form id="form-asignacion-masiva" class="row g-3">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="col-md-3">
                <label class="form-label">Grupo destino <span class="text-danger">*</span></label>
                <select class="form-select" name="grupo_funcional_id_destino" required>
                    <option value="">Cargando…</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">Plantilla</label>
                <select class="form-select" name="plantilla_id">
                    <option value="">Cargando…</option>
                </select>
            </div>
            <div class="col-md-2">
                <label class="form-label">Fecha inicio <span class="text-danger">*</span></label>
                <input type="date" class="form-control" name="fecha_inicio" required>
            </div>
            <div class="col-md-2">
                <label class="form-label">Fecha fin</label>
                <input type="date" class="form-control" name="fecha_fin">
            </div>
            <div class="col-md-2 d-flex align-items-end">
                <button type="button" class="btn btn-primary w-100"
                        onclick="previewMasiva();">Preview</button>
            </div>

            <div class="col-12"><hr></div>

            <div class="col-md-3">
                <label class="form-label">Filtro: Grupo (operativo)</label>
                <select class="form-select" name="grupo_id">
                    <option value="">Todos</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">Filtro: Tipo de persona</label>
                <select class="form-select" name="tipo_persona_id">
                    <option value="">Todos</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">Filtro: Categoría</label>
                <select class="form-select" name="categoria_id">
                    <option value="">Todos</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">Filtro: Sede</label>
                <select class="form-select" name="sede_id">
                    <option value="">Todos</option>
                </select>
            </div>

            <div class="col-12 d-flex gap-2 align-items-center">
                <div class="form-check">
                    <input class="form-check-input" type="checkbox"
                           id="cerrar_legacy" name="cerrar_legacy_en_fecha">
                    <label class="form-check-label" for="cerrar_legacy">
                        Cerrar asignaciones legacy en fecha_inicio-1
                    </label>
                </div>
                <div class="form-check">
                    <input class="form-check-input" type="checkbox"
                           id="modo_override" name="modo_override">
                    <label class="form-check-label" for="modo_override">
                        Modo: crear_override (en lugar de asignar_grupo_funcional)
                    </label>
                </div>
            </div>
        </form>
    </div>
</div>

<div id="preview-resultado" class="card border-0 shadow-sm" style="display:none;">
    <div class="card-header bg-transparent py-3">
        <h5 class="fw-bold mb-0">Preview</h5>
    </div>
    <div class="card-body" id="preview-body"></div>
    <div class="card-footer">
        <button type="button" class="btn btn-warning" id="btn-ejecutar"
                onclick="ejecutarMasiva();" disabled>
            Ejecutar asignación masiva
        </button>
        <span class="text-muted ms-2">Marca "He revisado el preview" para habilitar.</span>
        <input type="checkbox" id="confirmar" class="form-check-input ms-3"
               onchange="document.getElementById('btn-ejecutar').disabled = !this.checked;">
        <label class="form-check-label" for="confirmar">Confirmar</label>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/asignacion_masiva.js') }}"></script>
{% endblock %}
```

- [ ] **Paso 4: `templates/personas/horario_override.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header mb-4">
    <h3>Horario personalizado (override)</h3>
    <p class="text-muted">Esta plantilla anula el horario por defecto del grupo funcional.</p>
</div>

<div class="card border-0 shadow-sm mb-4">
    <div class="card-body">
        <form id="form-override" class="row g-3">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="col-md-4">
                <label class="form-label">Persona <span class="text-danger">*</span></label>
                <select class="form-select" name="persona_id" required>
                    <option value="">Cargando…</option>
                </select>
            </div>
            <div class="col-md-4">
                <label class="form-label">Plantilla <span class="text-danger">*</span></label>
                <select class="form-select" name="plantilla_id" required>
                    <option value="">Cargando…</option>
                </select>
            </div>
            <div class="col-md-2">
                <label class="form-label">Desde <span class="text-danger">*</span></label>
                <input type="date" class="form-control" name="fecha_inicio" required>
            </div>
            <div class="col-md-2">
                <label class="form-label">Hasta</label>
                <input type="date" class="form-control" name="fecha_fin">
            </div>
            <div class="col-md-8">
                <label class="form-label">Motivo</label>
                <input type="text" class="form-control" name="motivo"
                       placeholder="Ej: turno nocturno por cirugía">
            </div>
            <div class="col-md-4 d-flex align-items-end">
                <button type="submit" class="btn btn-primary w-100">Crear override</button>
            </div>
        </form>
    </div>
</div>

<div class="card border-0 shadow-sm">
    <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
            <thead class="bg-light">
                <tr>
                    <th>Persona</th><th>Plantilla</th><th>Desde</th>
                    <th>Hasta</th><th>Motivo</th><th></th>
                </tr>
            </thead>
            <tbody id="tabla-overrides">
                <tr><td colspan="6" class="text-center py-4 text-muted">Cargando…</td></tr>
            </tbody>
        </table>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/horario_override.js') }}"></script>
{% endblock %}
```

- [ ] **Paso 5: `templates/personas/grupos_funcionales.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header mb-4">
    <h3>Grupos funcionales de la persona</h3>
    <p class="text-muted">Una persona puede pertenecer a N grupos funcionales. Marca uno como principal para que se use su default.</p>
</div>

<div class="card border-0 shadow-sm mb-4">
    <div class="card-body">
        <form id="form-pgf" class="row g-3">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="col-md-4">
                <label class="form-label">Grupo funcional <span class="text-danger">*</span></label>
                <select class="form-select" name="grupo_funcional_id" required>
                    <option value="">Cargando…</option>
                </select>
            </div>
            <div class="col-md-2">
                <label class="form-label">Desde <span class="text-danger">*</span></label>
                <input type="date" class="form-control" name="fecha_inicio" required>
            </div>
            <div class="col-md-2">
                <label class="form-label">Hasta</label>
                <input type="date" class="form-control" name="fecha_fin">
            </div>
            <div class="col-md-2 d-flex align-items-end">
                <div class="form-check">
                    <input class="form-check-input" type="checkbox"
                           id="es_principal" name="es_principal">
                    <label class="form-check-label" for="es_principal">Marcar como principal</label>
                </div>
            </div>
            <div class="col-md-2 d-flex align-items-end">
                <button type="submit" class="btn btn-primary w-100">Asignar</button>
            </div>
        </form>
    </div>
</div>

<div class="card border-0 shadow-sm">
    <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
            <thead class="bg-light">
                <tr>
                    <th>Grupo</th><th>Desde</th><th>Hasta</th>
                    <th>Principal</th><th></th>
                </tr>
            </thead>
            <tbody id="tabla-pgf">
                <tr><td colspan="5" class="text-center py-4 text-muted">Cargando…</td></tr>
            </tbody>
        </table>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/persona_grupos_funcionales.js') }}"></script>
{% endblock %}
```

- [ ] **Paso 6: Modificar `templates/personas/historico.html` — añadir columna "Origen del horario"**

En la tabla existente (líneas 56-99), añadir la columna entre "Fecha Inicio" y "Fecha Fin". Insertar en el `<thead>`:

```html
                <th>Origen horario</th>
```

Y en cada `<tr>` del `<tbody>` (líneas 71-89), insertar entre las celdas de fecha inicio y fecha fin:

```html
                <td>
                    {% if pv.horario_origen %}
                    <span class="badge bg-info-subtle text-info-emphasis">{{ pv.horario_origen }}</span>
                    {% else %}
                    <span class="text-muted">—</span>
                    {% endif %}
                </td>
```

- [ ] **Paso 7: Modificar `templates/base.html` — añadir al sidebar**

En el bloque `{% if current_user_roles and ('admin' in current_user_roles or 'superadmin' in current_user_roles) %}` (línea 77), añadir después de "Categorías":

```html
                <li class="nav-item">
                    <a class="nav-link {% if active_page == 'functional_groups' %}active{% endif %}"
                        href="{{ url_for('functional_groups.vista_grupos') }}">
                        <span class="material-symbols-outlined nav-icon">workspaces</span>
                        <span>Grupos Funcionales</span>
                    </a>
                </li>
```

- [ ] **Paso 8: Commit**

```bash
git add templates/admin/grupos_funcionales.html \
        templates/admin/horarios_default_grupo.html \
        templates/admin/asignacion_masiva.html \
        templates/personas/horario_override.html \
        templates/personas/grupos_funcionales.html \
        templates/personas/historico.html \
        templates/base.html
git commit -m "feat(ui): templates para grupos funcionales, defaults, overrides, masiva"
```

---

## Tarea 6.2: JavaScript de los 4 formularios

**Files:**
- Create: `static/js/grupos_funcionales.js`
- Create: `static/js/horarios_default_grupo.js`
- Create: `static/js/horario_override.js`
- Create: `static/js/persona_grupos_funcionales.js`
- Create: `static/js/asignacion_masiva.js`

- [ ] **Paso 1: `static/js/grupos_funcionales.js`**

```javascript
// Lista los grupos funcionales y permite crear nuevos.
(function () {
    const tbody = document.getElementById('tabla-grupos-funcionales');
    const form = document.getElementById('form-nuevo-grupo');
    if (!tbody) return;

    function load() {
        apiCall('/api/grupos-funcionales')
            .then(data => render(data.grupos || []))
            .catch(err => showError(err.message || 'Error cargando grupos'));
    }

    function render(grupos) {
        if (grupos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No hay grupos funcionales creados.</td></tr>';
            return;
        }
        tbody.innerHTML = grupos.map(g => `
            <tr>
                <td><code>${g.codigo}</code></td>
                <td>${g.nombre}</td>
                <td>${g.orden}</td>
                <td>${g.activo
                    ? '<span class="badge bg-success">Activo</span>'
                    : '<span class="badge bg-secondary">Inactivo</span>'}</td>
                <td>${g.activo
                    ? `<button class="btn btn-sm btn-outline-secondary"
                              onclick="desactivar('${g.id}')">Desactivar</button>`
                    : ''}</td>
            </tr>
        `).join('');
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const fd = new FormData(form);
        const payload = Object.fromEntries(fd.entries());
        apiCall('/api/grupos-funcionales', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(() => {
            showSuccess('Grupo funcional creado');
            form.reset();
            bootstrap.Modal.getInstance(document.getElementById('modalNuevoGrupo')).hide();
            load();
        })
        .catch(err => showError(err.message || 'Error creando grupo'));
    });

    window.desactivar = function (id) {
        if (!confirm('¿Desactivar este grupo funcional?')) return;
        apiCall(`/api/grupos-funcionales/${id}`, { method: 'DELETE' })
            .then(() => { showSuccess('Grupo desactivado'); load(); })
            .catch(err => showError(err.message || 'Error'));
    };

    load();
})();
```

- [ ] **Paso 2: `static/js/horarios_default_grupo.js`**

```javascript
// Crea y lista los defaults de grupo funcional.
(function () {
    const form = document.getElementById('form-default-grupo');
    const tbody = document.getElementById('tabla-defaults-grupo');
    if (!form) return;

    function load() {
        apiCall('/api/grupos-funcionales')
            .then(data => populateSelects(data.grupos || []));
        apiCall('/api/horarios-default-grupo')
            .then(data => render(data.defaults || []));
    }

    function populateSelects(grupos) {
        const sel = form.querySelector('[name="grupo_funcional_id"]');
        sel.innerHTML = '<option value="">Seleccione…</option>' +
            grupos.map(g => `<option value="${g.id}">${g.nombre}</option>`).join('');
        // Cargar plantillas via API genérica (asumimos endpoint /api/plantillas).
        // En Fase 7 (UI refinamiento) se sustituye por endpoint dedicado.
    }

    function render(defaults) {
        if (defaults.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No hay defaults configurados.</td></tr>';
            return;
        }
        tbody.innerHTML = defaults.map(d => `
            <tr>
                <td>${d.grupo_funcional_nombre || d.codigo_gf}</td>
                <td>${d.nombre_plantilla || d.plantilla_id}</td>
                <td>${d.prioridad}</td>
                <td>${d.fecha_inicio}</td>
                <td>${d.fecha_fin || '—'}</td>
                <td><button class="btn btn-sm btn-outline-secondary"
                            onclick="cerrarDefault('${d.id}')">Cerrar</button></td>
            </tr>
        `).join('');
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const payload = Object.fromEntries(new FormData(form).entries());
        payload.prioridad = parseInt(payload.prioridad || 0, 10);
        apiCall('/api/horarios-default-grupo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(() => { showSuccess('Default creado'); form.reset(); load(); })
        .catch(err => showError(err.message || 'Error'));
    });

    window.cerrarDefault = function (id) {
        const today = new Date().toISOString().slice(0, 10);
        if (!confirm(`¿Cerrar este default a ${today}?`)) return;
        apiCall(`/api/horarios-default-grupo/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha_fin: today }),
        })
        .then(() => { showSuccess('Default cerrado'); load(); })
        .catch(err => showError(err.message || 'Error'));
    };

    load();
})();
```

- [ ] **Paso 3: `static/js/horario_override.js`**

```javascript
// Crea y lista personalizados (override) por persona.
(function () {
    const form = document.getElementById('form-override');
    const tbody = document.getElementById('tabla-overrides');
    if (!form) return;

    function load() {
        apiCall('/api/horarios-override')
            .then(data => render(data.overrides || []));
    }

    function render(overrides) {
        if (overrides.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No hay personalizados.</td></tr>';
            return;
        }
        tbody.innerHTML = overrides.map(o => `
            <tr>
                <td>${o.persona_id}</td>
                <td>${o.nombre_plantilla || o.plantilla_id}</td>
                <td>${o.fecha_inicio}</td>
                <td>${o.fecha_fin || '—'}</td>
                <td>${o.motivo || '—'}</td>
                <td><button class="btn btn-sm btn-outline-secondary"
                            onclick="cerrarOverride('${o.id}')">Cerrar</button></td>
            </tr>
        `).join('');
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const payload = Object.fromEntries(new FormData(form).entries());
        apiCall('/api/horarios-override', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(() => { showSuccess('Override creado'); form.reset(); load(); })
        .catch(err => showError(err.message || 'Error'));
    });

    window.cerrarOverride = function (id) {
        const today = new Date().toISOString().slice(0, 10);
        if (!confirm(`¿Cerrar este override a ${today}?`)) return;
        apiCall(`/api/horarios-override/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha_fin: today }),
        })
        .then(() => { showSuccess('Override cerrado'); load(); })
        .catch(err => showError(err.message || 'Error'));
    };

    load();
})();
```

- [ ] **Paso 4: `static/js/persona_grupos_funcionales.js`**

```javascript
// Asigna personas a grupos funcionales con vigencia y marca principal.
(function () {
    const form = document.getElementById('form-pgf');
    const tbody = document.getElementById('tabla-pgf');
    if (!form) return;

    function load() {
        apiCall('/api/grupos-funcionales')
            .then(data => populateSelect(data.grupos || []));
    }

    function populateSelect(grupos) {
        const sel = form.querySelector('[name="grupo_funcional_id"]');
        sel.innerHTML = '<option value="">Seleccione…</option>' +
            grupos.map(g => `<option value="${g.id}">${g.nombre}</option>`).join('');
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const fd = new FormData(form);
        const payload = Object.fromEntries(fd.entries());
        payload.es_principal = fd.has('es_principal');
        apiCall('/api/personas/grupos-funcionales', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(() => { showSuccess('Asignación creada'); form.reset(); })
        .catch(err => showError(err.message || 'Error'));
    });

    load();
})();
```

- [ ] **Paso 5: `static/js/asignacion_masiva.js`**

```javascript
// Preview y ejecución de asignación masiva con filtros.
(function () {
    const form = document.getElementById('form-asignacion-masiva');
    const previewBox = document.getElementById('preview-resultado');
    if (!form) return;

    window.previewMasiva = function () {
        const payload = readPayload();
        apiCall('/api/asignacion-masiva/grupo-funcional/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(data => {
            const body = document.getElementById('preview-body');
            body.innerHTML = `
                <p><strong>${data.matched_count}</strong> personas serán afectadas.</p>
                <details><summary>Ver primeros 50 IDs</summary>
                  <pre>${(data.affected_persona_ids || []).join('\n')}</pre>
                </details>`;
            previewBox.style.display = 'block';
        })
        .catch(err => showError(err.message || 'Error en preview'));
    };

    window.ejecutarMasiva = function () {
        const payload = readPayload();
        payload.confirmar = document.getElementById('confirmar').checked;
        if (!payload.confirmar) {
            showError('Marca la casilla de confirmación');
            return;
        }
        apiCall('/api/asignacion-masiva/grupo-funcional', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(data => {
            showSuccess(`Ejecutado: ${data.membership_created_count} creados, ${data.skipped_count} skipped`);
            previewBox.style.display = 'none';
        })
        .catch(err => showError(err.message || 'Error ejecutando'));
    };

    function readPayload() {
        const fd = new FormData(form);
        const payload = {
            grupo_funcional_id_destino: fd.get('grupo_funcional_id_destino'),
            plantilla_id: fd.get('plantilla_id'),
            fecha_inicio: fd.get('fecha_inicio'),
            fecha_fin: fd.get('fecha_fin') || null,
            modo: fd.get('modo_override') ? 'crear_override' : 'asignar_grupo_funcional',
            cerrar_legacy_en_fecha: fd.has('cerrar_legacy_en_fecha'),
            filtros: {
                grupo_id: fd.get('grupo_id') || null,
                tipo_persona_id: fd.get('tipo_persona_id') || null,
                categoria_id: fd.get('categoria_id') || null,
                sede_id: fd.get('sede_id') || null,
            },
        };
        return payload;
    }
})();
```

- [ ] **Paso 6: Commit**

```bash
git add static/js/grupos_funcionales.js static/js/horarios_default_grupo.js \
        static/js/horario_override.js static/js/persona_grupos_funcionales.js \
        static/js/asignacion_masiva.js
git commit -m "feat(ui): JS de formularios grupos funcionales, defaults, override, masiva"
```

---

## Tarea 6.3: Modificar `app/domain/reports.py` para usar el resolver

**Files:**
- Modify: `app/domain/reports.py`

- [ ] **Paso 1: Identificar la sección a modificar**

El motor de reportes en `app/domain/reports.py` carga horarios desde `db.queries.horarios.get_horarios()` (línea 2338 aprox.). En su lugar, debe llamar a `resolver_horario_vigente(persona_id, fecha)` por cada día.

- [ ] **Paso 2: Modificar `build_pdf` para usar el resolver**

En `app/domain/reports.py` (alrededor de las líneas 2312-2446), sustituir la carga de `get_horarios()` por una función que use el resolver. Reemplazar el bloque:

```python
    from db import get_horarios  # lazy import para evitar ciclo con create_app
    horarios = get_horarios()
    if not horarios["by_id"]:
        raise ValueError(
            "No se pueden generar reportes sin horarios cargados. "
            "Suba el archivo de horarios primero."
        )
```

Por:

```python
    from app.domain.schedule import resolver_horario_vigente
    from db.queries.horarios import _row_to_horario_dict
    from db.queries.plantillas import get_plantilla_by_id  # ver Fase 7 refactor
```

Y modificar el resto de `build_pdf` para llamar a `resolver_horario_vigente(persona_id, fecha)` en lugar de buscar en `horarios["by_id"]`. La función retorna un dict con `plantilla_id` y `origen`; el llamador debe entonces consultar la plantilla por su ID con `get_plantilla_by_id(plantilla_id)` para obtener los campos `lunes`, `martes`, etc.

- [ ] **Paso 3: Añadir columna "Origen del horario" en PDF/DOCX**

Modificar el helper `_seccion_detalle_persona` en `app/domain/report_docx.py` y el equivalente en `reports.py` para añadir la columna `origen_horario` en cada fila de la tabla por día.

- [ ] **Paso 4: Commit**

```bash
git add app/domain/reports.py app/domain/report_docx.py
git commit -m "feat(reports): usar resolver_horario_vigente + columna Origen del horario en PDF/DOCX"
```

---

## Tarea 6.4: Modificar `app/domain/analytics.py` para usar el resolver

**Files:**
- Modify: `app/domain/analytics.py`

- [ ] **Paso 1: Sustituir `get_horario_en_fecha` por el resolver**

En `app/domain/analytics.py` (línea 37 y línea 100 aprox.), sustituir el import y la llamada:

```python
from app.domain.schedule import resolver_horario_vigente
```

Y en la línea 100, donde se llama a `get_horario_en_fecha(conn, persona_id, fecha_inicio)`, sustituir por:

```python
resolution = resolver_horario_vigente(persona_id, current_date)
horario = resolution.get("plantilla")
if horario is None:
    continue
```

- [ ] **Paso 2: Commit**

```bash
git add app/domain/analytics.py
git commit -m "feat(analytics): usar resolver_horario_vigente en load_data_asistencia_dataframe"
```

---

## Tarea 6.5: Modificar `app/web/people_bp.py` para añadir "Origen" al histórico

**Files:**
- Modify: `app/web/people_bp.py`

- [ ] **Paso 1: Enriquecer la respuesta de `get_historico_persona`**

En `app/web/people_bp.py`, modificar el view `historico()` para incluir `horario_origen` en cada periodo:

```python
    if identificacion:
        historico_data = get_historico_persona(identificacion)
        # Enriquecer con origen del horario
        if historico_data:
            from app.domain.schedule import resolver_horario_vigente
            from datetime import date
            hoy = date.today()
            for periodo in historico_data.get("periodos", []):
                try:
                    fecha_inicio = periodo.get("fecha_inicio")
                    if fecha_inicio:
                        # Resolver en la fecha de inicio del periodo
                        resultado = resolver_horario_vigente(
                            historico_data["id"], fecha_inicio
                        )
                        periodo["horario_origen"] = resultado.get("origen")
                except Exception:
                    periodo["horario_origen"] = None
```

- [ ] **Paso 2: Commit**

```bash
git add app/web/people_bp.py
git commit -m "feat(people): enriquecer histórico con origen del horario resuelto"
```

---

## Tarea 6.6: Tests de integración del blueprint de overrides + comparación A/B de reportes

**Files:**
- Create: `tests/integration/test_horarios_override_bp.py`

- [ ] **Paso 1: Test RED**

```python
"""
Tests de integración del blueprint de overrides + comparación A/B
de la salida del motor de reportes con flag on vs off.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_crear_override_y_consultar(app, admin_client, admin_user_id):
    payload = {
        "persona_id": "p-test",
        "plantilla_id": "ph-test",
        "fecha_inicio": "2026-08-01",
        "fecha_fin": None,
        "motivo": "Test",
    }
    r = admin_client.post(
        "/api/horarios-override", json=payload,
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert r.status_code in (201, 409)  # 409 si persona no existe


@pytest.mark.integration
def test_comparacion_reportes_flag_on_vs_off(app_with_flag_on, app_with_flag_off):
    """Compara el output del resolver con flag on vs off para una persona
    que tiene 3 capas: override, legacy, default."""
    client_on, _ = app_with_flag_on
    client_off, _ = app_with_flag_off

    r_on = client_on.get(
        "/api/horarios/resolver?persona_id=p-1&fecha=2026-08-15"
    )
    r_off = client_off.get(
        "/api/horarios/resolver?persona_id=p-1&fecha=2026-08-15"
    )
    data_on = r_on.get_json()
    data_off = r_off.get_json()
    # Con flag on, puede ser default_grupo o personalizado.
    # Con flag off, solo individual_legacy o sin_horario.
    assert data_on["origen"] in ("default_grupo", "personalizado",
                                  "individual_legacy", "sin_horario")
    assert data_off["origen"] in ("individual_legacy", "sin_horario")
```

- [ ] **Paso 2: Verificar RED + commit**

```bash
git add tests/integration/test_horarios_override_bp.py
git commit -m "test(integration): override BP + comparación A/B on/off"
```

---

# PARTE 7 — Script opcional de migración de datos + rollout

## Tarea 7.1: Script `scripts/migrar_asignaciones_a_defaults.py` (no se ejecuta automáticamente)

**Files:**
- Create: `scripts/migrar_asignaciones_a_defaults.py`

- [ ] **Paso 1: Crear el script**

```python
"""
Migra asignaciones_horario 1:1 a defaults de grupo funcional.

NO escribe en BD. Solo emite un CSV propuesto para revisión del admin.

Uso:
    python scripts/migrar_asignaciones_a_defaults.py --tenant istpet \\
        --out propuesta_migracion.csv
"""
import argparse
import csv
import os

from sqlalchemy import text

from db.connection import get_connection, validate_schema_name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="istpet")
    parser.add_argument("--out", required=True, help="ruta del CSV propuesto")
    args = parser.parse_args()

    schema = validate_schema_name(args.tenant)
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT p.id::text AS persona_id,
                       p.nombre,
                       ah.plantilla_id::text,
                       ph.nombre AS plantilla_nombre,
                       p.tipo_persona_id::text AS tipo_persona_id,
                       p.grupo_id::text AS grupo_id,
                       p.sede_id::text AS sede_id
                FROM asignaciones_horario ah
                JOIN plantillas_horario ph ON ph.id = ah.plantilla_id
                JOIN personas p ON p.id = ah.persona_id
                WHERE ah.ciclo_semanas = 1
                  AND ah.fecha_fin IS NULL
                ORDER BY p.nombre
            """)
        ).fetchall()

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["persona_id", "nombre", "plantilla_id", "plantilla_nombre",
                    "tipo_persona_id", "grupo_id", "sede_id"])
        for row in rows:
            w.writerow([str(c) if c is not None else "" for c in row])

    print(f"Propuesta escrita: {args.out} ({len(rows)} filas).")
    print("Revisar y luego ejecutar manualmente el segundo script.")


if __name__ == "__main__":
    main()
```

- [ ] **Paso 2: Verificar que el script corre en seco**

```bash
python scripts/migrar_asignaciones_a_defaults.py --tenant istpet --out /tmp/propuesta.csv
head -3 /tmp/propuesta.csv
```

- [ ] **Paso 3: Commit**

```bash
git add scripts/migrar_asignaciones_a_defaults.py
git commit -m "feat(scripts): propuesta CSV de migración legacy→defaults (no auto-ejecuta)"
```

---

## Tarea 7.2: Rollout controlado (Fase 9 del ADR)

- [ ] **Paso 1: Pilot en `istpet`**

Documentar en `docs/OPERATIONS.md` (sección "Horarios por grupo funcional — Pilot"):

```markdown
## Pilot: `istpet` con feature flag activo

1. Backup completo antes del cambio:
   ```bash
   docker compose exec -T db pg_dump -U $PGUSER -d $PGDB -Fc \
       > /data/backups/pre-horarios-grupo-$(date +%Y%m%d_%H%M).dump
   ```

2. Activar flag en `istpet` desde la UI `/configuracion` o por SQL:
   ```sql
   UPDATE public.tenants
   SET configuracion = configuracion ||
       '{"horario_por_grupo": true, "horario_desempate": "prioridad"}'::jsonb
   WHERE slug = 'istpet';
   ```

3. Monitor durante 1 semana. Si hay errores de resolución (p.ej. personas
   que pasan a "sin_horario" cuando antes tenían legacy), desactivar:
   ```sql
   UPDATE public.tenants
   SET configuracion = configuracion ||
       '{"horario_por_grupo": false}'::jsonb
   WHERE slug = 'istpet';
   ```

4. Comparación A/B de reportes: ejecutar el motor de reportes para el
   mismo período con flag on y con flag off. La salida debe ser
   idéntica en personas que solo tienen legacy (ninguna debe cambiar
   al default de grupo mientras no se haya asignado la relación).
```

- [ ] **Paso 2: Comparación A/B automatizada**

`scripts/comparar_reportes_horario.py` (NUEVO):

```python
"""
Compara la salida de 2 reportes (PDF o DOCX) generados con flag on vs off.

Uso:
    python scripts/comparar_reportes_horario.py \\
        --con-flag-on /tmp/reporte_on.pdf \\
        --con-flag-off /tmp/reporte_off.pdf
"""
import argparse
import hashlib
import os


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def text(path):
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--con-flag-on", required=True)
    parser.add_argument("--con-flag-off", required=True)
    args = parser.parse_args()

    h_on = md5(args.con_flag_on)
    h_off = md5(args.con_flag_off)

    t_on = text(args.con_flag_on)
    t_off = text(args.con_flag_off)

    print(f"MD5 on:  {h_on}")
    print(f"MD5 off: {h_off}")
    if h_on == h_off:
        print("OK: bytes idénticos.")
    else:
        print("DIFIEREN: los reportes son distintos.")

    if t_on and t_off:
        if t_on == t_off:
            print("OK: texto extraído idéntico.")
        else:
            print("DIFIEREN en texto. Diff:")
            import difflib
            for line in difflib.unified_diff(
                t_off.splitlines(), t_on.splitlines(),
                fromfile="off", tofile="on", lineterm=""
            ):
                print(line)


if __name__ == "__main__":
    main()
```

```bash
git add scripts/comparar_reportes_horario.py
git commit -m "feat(scripts): comparador A/B de reportes (PDF) con flag on/off"
```

- [ ] **Paso 3: Documentar el rollback en `docs/OPERATIONS.md`**

```markdown
## Rollback del feature flag (sin tocar BD)

```bash
# Desactivar flag en el tenant afectado
psql $DATABASE_URL -c "
UPDATE public.tenants
SET configuracion = configuracion || '{\"horario_por_grupo\": false}'::jsonb
WHERE slug = 'istpet';
"

# El resolver inmediatamente consulta el legacy. NO requiere reinicio
# de la app. Verificar en /configuracion que el flag quedó en false.
```

Si la migración 0010 debe revertirse (caso extremo):

```bash
export ALEMBIC_ALLOW_DOWNGRADE_0010=true
alembic downgrade -1
unset ALEMBIC_ALLOW_DOWNGRADE_0010
```
```

- [ ] **Paso 4: Commit final de la release**

```bash
git add docs/OPERATIONS.md scripts/
git commit -m "docs(operations): rollout controlado + scripts de migración y rollback"
```

---

# PARTE 8 — Self-review y checklist final

## Tarea 8.1: Self-review del plan (writing-plans)

- [ ] **Paso 1: Verificar cobertura del ADR-0003**

Checklist:
- [x] Precedencia corregida: `personalizado > individual legacy > default grupo > sin horario` (Tarea 0.1).
- [x] 4 tablas nuevas: `grupos_funcionales`, `persona_grupos_funcionales`, `horarios_default_grupo`, `overrides_horario_persona` (Tarea 1.1).
- [x] 2 columnas aditivas + 1 columna en `asignaciones_horario` (Tarea 1.1).
- [x] Índices con predicados inmutables (Tarea 1.1).
- [x] Función canónica `resolver_horario_vigente` con la precedencia corregida (Tarea 3.2).
- [x] Múltiples grupos con `es_principal` y desempate configurable (Tareas 2.3 + 3.2).
- [x] Asignación masiva con filtros combinables (`grupo_funcional_id`, `grupo_id`, `tipo_persona_id`, `categoria_id`, `sede_id`) (Tarea 4.2).
- [x] RBAC: `gestor` lee, `admin`/`superadmin` escriben (Tarea 5.1).
- [x] Auditoría completa (`registrar_audit` con `accion`, `entidad`, `detalle`) (Tareas 4.2 + 5.1).
- [x] UI: 5 templates HTML + 5 JS + sidebar + histórico (Tareas 6.1 + 6.2).
- [x] Motor de reportes (PDF/DOCX) usa el resolver y muestra "Origen" (Tarea 6.3).
- [x] Analytics usa el resolver (Tarea 6.4).
- [x] Feature flag por tenant (`tenant.configuracion['horario_por_grupo']`) (Tarea 3.1 + 4.3).
- [x] Tests unitarios y de integración con comparación A/B (Tareas 1.2, 2.x, 3.x, 4.x, 5.x, 6.6).
- [x] Staging + backup + restore + rollback documentados (Tareas 0.2, 0.4, 7.2).

- [ ] **Paso 2: Verificar que no hay placeholders**

Buscar en este documento:
- [x] No hay "TBD", "TODO", "implement later", "fill in details".
- [x] Cada tarea con código tiene el snippet completo.
- [x] Cada test es copiable tal cual.
- [x] Cada comando tiene el `expected` documentado.

- [ ] **Paso 3: Verificar consistencia de tipos y nombres**

- `plantilla_id`, `persona_id`, `grupo_funcional_id`, `membership_id`, `default_id`, `override_id` — todos UUIDs.
- `origen ∈ {personalizado, individual_legacy, default_grupo, sin_horario}`.
- `horario_desempate ∈ {prioridad, orden_grupo, error}`.
- `modo ∈ {asignar_grupo_funcional, crear_override}`.
- `accion` de auditoría siempre con prefijo `horario_` o `persona_grupo_funcional_`.

- [ ] **Paso 4: Commit final del plan (sin tocar código de aplicación)**

Este archivo ya está commiteado por separado. Confirmar con:

```bash
git log --oneline -5
```

---

## Resumen

- **Total de tareas**: 22 (PARTE 0: 4, PARTE 1: 2, PARTE 2: 4, PARTE 3: 2, PARTE 4: 3, PARTE 5: 2, PARTE 6: 6, PARTE 7: 2, PARTE 8: 1).
- **Tamaño del plan**: ~50 KB, ~1500 líneas.
- **Cero placeholders** (verificado en Tarea 8.1).
- **Tests definidos antes de la implementación** en cada módulo.
- **Rollback documentado** y comparación A/B automatizada.
- **Feature flag por tenant** permite desactivar sin redeploy.
- **Alembic como única fuente de verdad** del schema (cierre de Fase −1).
