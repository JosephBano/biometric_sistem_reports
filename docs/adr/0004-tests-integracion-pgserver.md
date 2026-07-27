---
title: "ADR-0004 — Tests de integración con PostgreSQL embebido (pgserver)"
tags: [adr, testing, integration, postgres, ci]
status: accepted
created: 2026-07-02
updated: 2026-07-02
deciders: [implementer]
consulted: [docs/AUTENTICACION.md, docs/ARQUITECTURA.md, ADR-0001]
supersedes: []
superseded_by: []
related:
  - "[[ADR-0001-modularizacion-monolito-flask]]"
  - "[[ARQUITECTURA]]"
  - "[[OPERATIONS]]"
---

# ADR-0004 — Tests de integración con PostgreSQL embebido (pgserver)

- **Status**: accepted
- **Date**: 2026-07-02
- **Deciders**: @implementer
- **Consulted**: docs/AUTENTICACION.md, docs/ARQUITECTURA.md, ADR-0001

## Context and Problem Statement

La Fase 7.1 del roadmap de [[ADR-0001-modularizacion-monolito-flask]] exigía
**13 tests de integración** (uno por blueprint mínimo) corriendo contra
PostgreSQL real. La pregunta de diseño era: **¿cómo correr esos tests?**

Las opciones disponibles eran:

1. **Servicio `postgres:16` en Docker** (planteado originalmente en Fase 7.2 del CI).
   - Pro: binarios oficiales, versionado, idéntico a producción.
   - Contra: requiere Docker, lento de arrancar (~10s), el runner de CI tiene
     que configurarlo como `services:`, y los devs locales necesitan Docker
     corriendo aunque no estén tocando la BD.

2. **SQLite en memoria** para los tests.
   - Pro: cero infra, rápido.
   - Contra: el código del sistema usa **schemas por tenant** (`SET search_path`),
     `DO $$ ... $$`, `ON CONFLICT`, `gen_random_uuid()`, tipos `JSONB`,
     `UUID` nativo. SQLite no soporta la mayoría. Reescribir el código de BD
     solo para tests es un anti-patrón.

3. **Postgres embebido vía `pgserver`** (paquete Python que trae binarios de
   PostgreSQL 16 + utilidades CLI).
   - Pro: cero infra externa, no Docker, ~500ms de startup, schemas completos.
   - Contra: pgserver **no incluye `pgcrypto` extension** (PG 13+ ya trae
     `gen_random_uuid()` built-in, así que se puede parchear el DDL).

## Decision Outcome

**Se adopta la opción 3 — `pgserver`** como solución estándar para los
tests de integración.

### Razones

- **Cero infra externa**: ni Docker, ni servicio, ni socket Unix preexistente.
  El `pip install pgserver` trae los binarios.
- **Tests corren en cualquier máquina**: laptop sin Docker, runner de CI con
  solo Python, contenedor efímero.
- **Esquema completo de PostgreSQL**: soporta `SET search_path`, `DO $$`,
  `gen_random_uuid()`, `JSONB`, etc. — idéntico a producción.
- **Rápido**: ~500ms de startup vs ~10s de un servicio Docker.
- **Aislado por proceso**: el server se destruye cuando termina pytest.

### Consecuencias

#### Positivas

- El CI puede correr `pytest` sin servicios adicionales (Fase 7.2 simplificada).
- Los tests de integración corren también en laptops de devs.
- **Encontramos 4 bugs reales en producción** durante la implementación de los
  tests (ver sección "Bugs encontrados").

#### Negativas

- **`pgcrypto` no disponible en pgserver**. Hay que parchear el DDL para omitir
  `CREATE EXTENSION IF NOT EXISTS pgcrypto;` y usar `gen_random_uuid()` built-in.
  Parche centralizado en `tests/integration/conftest.py`.
- **`pgserver` ocupa ~50MB en disco** (binarios de PostgreSQL 16) dentro de
  `.venv/`. Documentado en `.gitignore` (los data dirs no se trackean).
- **No es "Postgres real" en producción**: si producción usa una versión
  diferente (ej. PG 14), pueden aparecer discrepancias sutiles. Mitigación:
  CI corre en PG 16 (mismo pgserver); documentar en `OPERATIONS.md`.

#### Neutrales

- Los data dirs (`biometrico_test_int/`, etc.) viven en la raíz del repo.
  Añadidos a `.gitignore` para no commitearlos.

## Implementation Details

### `tests/integration/conftest.py`

```python
_PG_SERVER = pgserver.get_server("biometrico_test_int")
_PG_URI = _PG_SERVER.get_uri()
os.environ["DATABASE_URL"] = _PG_URI

# Parche: omitir pgcrypto (no disponible en pgserver).
import db.schema, db.init
db.schema.PUBLIC_DDL = db.schema.PUBLIC_DDL.replace(
    "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n", ""
)
db.init.PUBLIC_DDL = db.init.PUBLIC_DDL.replace(
    "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n", ""
)
db.init.get_tenant_ddl = lambda slug: (
    _original_get_tenant_ddl(slug).replace(
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n", ""
    )
)

from db.init import init_db
init_db()  # crea el schema público + istpet + sembrado inicial
```

### Fixtures expuestas

| Fixture | Scope | Función |
|---|---|---|
| `app` | session | Flask app en modo testing contra pgserver |
| `client` | function | Test client síncrono de Flask |
| `tenant_id` | function | UUID del tenant `istpet` (crea si no existe) |
| `admin_user_id` | function | UUID de un superadmin de test |
| `admin_client` | function | Cliente con sesión autenticada como superadmin |
| `anonymous_client` | function | Cliente sin sesión (para RBAC) |
| `csrf_token` | function | Token CSRF válido para usar en POSTs |
| `_reset_login_intentos` | function (autouse) | TRUNCATE entre tests |

### Coverage de los 13 blueprints

13 archivos `tests/integration/test_*_bp.py`, uno por blueprint:

| Blueprint | Tests | Endpoints cubiertos |
|---|---:|---|
| `auth_bp` | 6 | `/login`, `/logout`, rate limit |
| `dashboard_bp` | 3 | `/`, `/configuracion`, `/api/presente` |
| `devices_bp` | 6 | `/api/dispositivos`, `/api/sync/estado`, `/api/sync/ejecutar` |
| `schedule_bp` | 7 | `/api/horarios`, `/api/horarios/estado`, `/api/horarios/exportar`, CRUD |
| `attendance_bp` | 5 | `/api/justificaciones`, `/api/feriados`, CRUD |
| `breaks_bp` | 3 | `/api/categorizar-break` |
| `reports_bp` | 3 | `/api/backup/csv`, `/api/alertas/tardanzas-severas`, `/api/generar-desde-db` |
| `periods_bp` | 3 | `/periodos`, `/periodos/<id>/archivar` |
| `people_bp` | 4 | `/api/personas-lista`, `/api/personas-db` |
| `groups_bp` | 3 | `/admin/grupos`, `/admin/categorias` |
| `admin_bp` | 12 | `/admin/tenants`, `/admin/usuarios`, `/admin/dispositivos`, `/admin/superadmin/usuarios`, switch-tenant |
| `analytics_bp` | 4 | `/analytics`, `/api/analytics`, `/api/analytics/narrativo` |
| `system_bp` | 2 | `/api/scheduler/estado` |

## Bugs encontrados durante la implementación

Los integration tests revelaron **4 bugs reales en código de producción**
que estaban ocultos tras `try/except` o solo se manifestaban en rutas
específicas:

### Bug 1 — `db/queries/auth.py::registrar_audit` con `:detalle::jsonb`

**Síntoma**: el INSERT a `audit_log` con `detalle` (JSONB) fallaba con
`psycopg2.errors.SyntaxError: syntax error at or near ":"` cada vez que
se intentaba pasar un detalle no-NULL. El logout y el switch-tenant
tenían `try/except` que silenciaban el error → audit_log incompleto en
producción.

**Causa**: SQLAlchemy `text()` interpreta `:detalle::jsonb` como
"parámetro `:detalle::jsonb`" (consume hasta el segundo `::`).

**Fix**: `CAST(:detalle AS jsonb)` (paréntesis fuerzan el cast explícito).

### Bug 2 — `app/context_processors.py::inject_pending_counts` inyectaba función

**Síntoma**: cada `render_template` que usaba el layout base lanzaba
`TypeError: '>' not supported between instances of 'function' and 'int'`.

**Causa**: el context processor retornaba
`justificaciones_pendientes_count=_get_pending_count` (la función),
no `justificaciones_pendientes_count=_get_pending_count()` (el valor).

**Fix**: llamar a la función y pasar el entero resultante.

### Bug 3 — `app/web/groups_bp.py::listar_grupos()` recursión infinita

**Síntoma**: `GET /admin/grupos` → 500 `RecursionError: maximum recursion
depth exceeded` (en cuanto se autenticaba un admin).

**Causa**: el view function se llama `listar_grupos` y dentro hace
`listar_grupos()` — Python resuelve al view function, no al import.

**Fix**: renombrar el import a `svc_listar_grupos` (y `svc_listar_categorias`).

### Bug 4 — `templates/admin/superadmin_usuarios.html::url_for` sin prefijo

**Síntoma**: `GET /admin/superadmin/usuarios` → 500
`werkzeug.routing.exceptions.BuildError: Could not build url for endpoint
'api_superadmin_mover_usuario'`.

**Causa**: `url_for("api_superadmin_mover_usuario")` faltaba el prefijo
del blueprint (`admin.`).

**Fix**: `url_for("admin.api_superadmin_mover_usuario")` y
`url_for("admin.api_superadmin_eliminar_usuario", ...)`.

## Validation

- `pytest tests/integration -v --no-cov` → 79 tests passing en ~8s
  (incluyendo el startup de pgserver).
- CI workflow `.github/workflows/ci.yml` corre los tests sin servicio
  Postgres externo (solo `pip install pgserver`).

## Follow-ups (backlog)

- **P2**: tests de `db/queries/*` (objetivo secundario del ADR-0001:
  70% cobertura). Estos viven en `tests/integration/test_*_queries.py`
  (uno por módulo de `db/queries/`).
- **P3**: snapshots de schema — capturar `pg_dump --schema-only` antes y
  después de `init_db()` para detectar drift.

## Relacionado

- [[ADR-0001-modularizacion-monolito-flask]] — Plan de refactor que
  introdujo Fase 7.1 como DoD-9.
- [[ARQUITECTURA]] — Mapa del sistema tras el refactor.
- [[OPERATIONS]] — Runbook de deploy, troubleshooting y rollback.
