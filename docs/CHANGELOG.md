---
title: "CHANGELOG — Sistema Biométrico RRHH ISTPET"
tags: [changelog, release-notes, historial, superpowers]
status: active
created: 2026-07-02
updated: 2026-07-02
authors: [implementer, documenter]
related:
  - "[[ADR-0001-modularizacion-monolito-flask]]"
  - "[[ADR-0002-sync-observable-y-backups]]"
  - "[[ADR-0004-tests-integracion-pgserver]]"
  - "[[ARQUITECTURA]]"
  - "[[OPERATIONS]]"
supersedes: []
superseded_by: []
---

# CHANGELOG

> Bitácora de cambios del proyecto, organizada por fecha. Cada entrada resume
> qué se hizo, qué commits lo cierran, y qué issues / PRs / ADRs están
> relacionados. Para el detalle por commit, ver `git log --oneline`.

---

## [Unreleased] — Refactor monolito Flask → Application Factory

**Fecha**: 2026-07-01 → 2026-07-02
**Tipo**: refactor + tests + docs
**ADR**: [[ADR-0001-modularizacion-monolito-flask]] (status: completed), [[ADR-0004-tests-integracion-pgserver]]

### Summary

Cierre del plan de modularización del monolito Flask. `app.py` (2 512 LOC) y
`db.py` fueron eliminados; el código se reorganizó en `app/` (Application
Factory + 13 Blueprints + 20 módulos de dominio) con regla de capas
verificada por AST.

### Changed

- **Eliminados** (código migrado a `app/domain/*` o reescrito):
  - `app.py` (2 512 LOC) → dividido entre `app/__init__.py` (factory), `app/web/*.py`
    (13 blueprints), `app/extensions.py`, `app/errors.py`, `app/security_headers.py`,
    `app/context_processors.py`, `app/tenant.py`, `app/cleanup.py`.
  - `db.py` (root, eclipsado por el paquete `db/`).
  - `auth.py` (165 LOC) → `app/domain/auth.py` (con todas las funciones que
    `app.web.*` necesita re-exportadas).
  - `decorators.py` (114 LOC) → `app/domain/rbac.py`.
  - `email_utils.py` (51 LOC) → `app/domain/emailer.py`.
  - `script.py` (2 281 LOC) → `app/domain/reports.py`.
  - `script_docx.py` (782 LOC) → `app/domain/report_docx.py`.
  - `analytics.py` (555 LOC) → `app/domain/analytics.py`.
  - `ia_report.py` (145 LOC) → `app/domain/ai_narrative.py`.
  - `horarios.py` (416 LOC) → `app/domain/attendance.py`.
  - `sync.py` (540 LOC) → `app/domain/schedule.py` (la migración más delicada;
    `_jobs` y el flag `_scheduler_started` ahora viven en el módulo; `schedule`
    library se importa solo dentro de `init_scheduler(app)` para evitar
    side-effects al importar).
  - `backup.py` (124 LOC) → `app/domain/backup.py`.
  - `middleware.py` (206 LOC, FastAPI/uvicorn huérfano) → eliminado por no usarse
    (DoD-6 cerrado).
- **Nuevos**:
  - `app/__init__.py::create_app(config_name)` — Application Factory con
    `init_app` por extensión.
  - `app/config.py` — `BaseConfig`, `DevelopmentConfig`, `ProductionConfig`,
    `TestingConfig` (este último con salvaguarda: rechaza `DATABASE_URL` que no
    contenga `test`).
  - `app/web/{auth,dashboard,devices,schedule,attendance,breaks,reports,periods,people,groups,admin,analytics,system}_bp.py`
    — 13 Blueprints que registran 82 rutas (= 81 originales + `/api/backup/descargar`
    agregado en Fase 1 de sync/backup).
  - `app/extensions.py` — instancias globales de `csrf` y `limiter` (sin `app=...`,
    Application Factory pattern).
  - `app/errors.py` — handlers 401/403/404/429/500 (JSON para API, HTML para UI).
  - `app/security_headers.py` — `after_request` con `X-Content-Type-Options`,
    `X-Frame-Options`, `CSP`, `Referrer-Policy`.
  - `app/context_processors.py` — `inject_system_info`, `inject_user_info`,
    `inject_pending_counts` para Jinja.
  - `app/tenant.py` — `before_request` que hidrata `g.tenant_schema`, `g.tenant_tipos`.
  - `app/cleanup.py` — thread daemon de limpieza de archivos temporales.
  - `wsgi.py` — entrypoint canónico para gunicorn (`wsgi:app`) con
    `DispatcherMiddleware(/biometrico)` + `ProxyFix`.
  - `requirements-dev.txt` — `pytest>=8`, `pytest-cov>=5`, `ruff>=0.5`.
  - `pyproject.toml` — configuración de `ruff`, `pytest`, `coverage` (gate actual 30%).
  - `.github/workflows/ci.yml` — CI con 2 jobs (test + coverage-gate), usa
    `pgserver` (no requiere servicio Docker Postgres).
  - `docs/OPERATIONS.md` — runbook de operaciones (deploy, monitoring,
    troubleshooting, rollback).
  - `docs/adr/0004-tests-integracion-pgserver.md` — decisión de usar `pgserver`.
  - `tests/integration/conftest.py` — fixtures con `pgserver` + `pgcrypto`
    patch + autouse `TRUNCATE login_intentos`.
  - `tests/integration/test_*_bp.py` — 16 archivos (uno por blueprint +
    ampliados para subir cobertura).
  - `tests/unit/test_arquitectura.py` — verifica la regla de capas (AST) y
    que no queden módulos top-level de negocio.
  - `tests/unit/test_factory.py` — verifica 13 blueprints + 82 rutas +
    headers de seguridad.
  - `tests/unit/test_schedule_migrado.py` — verifica que `import app.domain.schedule`
    no arranca el scheduler.
  - `tests/unit/test_sync_logging.py` — migrado para usar `app.domain.schedule`
    en lugar del `sync.py` raíz.

### Fixed

- **`db/queries/auth.py::registrar_audit` con `:detalle::jsonb`** (descubierto
  durante Fase 7.1): SQLAlchemy interpretaba `:detalle::jsonb` como un solo
  parámetro. Cambiado a `CAST(:detalle AS jsonb)`. Antes, todo INSERT a
  `audit_log` con `detalle` no-NULL fallaba silenciosamente (gracias al
  try/except del caller).

- **`app/context_processors.py::inject_pending_counts`** (descubierto durante
  Fase 7.1): inyectaba la función `_get_pending_count` en vez del entero
  resultante. El template `{% if justificaciones_pendientes_count > 0 %}`
  lanzaba `TypeError: '>' not supported between instances of 'function' and
  'int'` en cada render.

- **`app/web/groups_bp.py::listar_grupos()` y `listar_categorias()`** (descubierto
  durante Fase 7.1): las views se llamaban a sí mismas recursivamente porque
  el `import` tenía el mismo nombre. Renombrados a `svc_listar_grupos` y
  `svc_listar_categorias`.

- **`templates/admin/superadmin_usuarios.html`** (descubierto durante Fase 7.1):
  `url_for("api_superadmin_mover_usuario")` faltaba el prefijo del blueprint.
  Cambiado a `url_for("admin.api_superadmin_mover_usuario")`.

### Security

- **CSRF más estricto**: el validador rechaza cualquier POST a `/api/*` que
  no traiga token CSRF en form data o header `X-CSRF-Token`. Endpoints exentos
  se marcan explícitamente con `@csrf.exempt`.

- **Rate limiting**: `/api/backup/descargar` con 3/h + 1/10min (commit
  `ae5e58c`). Login con 5/15min (Flask-Limiter + `contar_intentos_fallidos`).

- **Redacción de errores**: las excepciones en `sync.py::sincronizar` y
  `app.domain.schedule::_backup_diario` se redactan antes de loguearse o
  enviarse por email (quitan credenciales, passwords, hostnames internos).

- **Validación de `tenant_slug`**: regex `^[a-z0-9_-]{1,63}$` en
  `db.queries.scheduler_runs` (commit `ae5e58c`).

- **XSS en UI**: `static/js/configuracion.js` usa `createElement` + `textContent`
  en lugar de `innerHTML` (commit `ae5e58c`).

### Performance

- **Backups portables**: `pg_dump -Fc` con credenciales por env (`PGPASSWORD`),
  nunca en argv (commit `915b3dc`). Restaurable con `pg_restore` en cualquier
  PostgreSQL ≥ 16.

- **Scheduler observable**: cada corrida se persiste en `public.scheduler_runs`
  (job, tenant_slug, inicio, fin, ok, descargados, insertados, detalle).
  Permite auditoría y debugging post-mortem (commits `224d5fa`, `62a6d46`).

### Added — Funcionalidad

- **`GET /api/scheduler/estado`** (admin+): JSON con `proxima_corrida` y
  `ultimas_corridas` (commit `a2d8e20`).
- **`GET /api/backup/descargar`** (admin+, rate-limited): `pg_dump -Fc` con
  retención (commit `cabe812`).
- **Sync nocturna automática** a `02:00` con `force_historico=True`
  (commit `a2d8e20`).
- **Backup diario automático** a `BACKUP_HORA` (default `03:00`) si
  `BACKUP_AUTO=true` (commit `fc6ced6`).
- **Gestión cross-tenant de usuarios** desde panel superadmin
  (commit `1a773ef`).
- **Diseño visual v2.0** (Design System): Bootstrap 5, Plus Jakarta Sans,
  iconografía Material Symbols (commit `1152509`).

### Documentation

- `docs/ADR/0001-modularizacion-monolito-flask.md` — ADR original.
- `docs/ADR/0002-sync-observable-y-backups.md` — ADR de sync observable.
- `docs/ADR/0004-tests-integracion-pgserver.md` — ADR de pgserver.
- `docs/ARQUITECTURA.md` — actualizado con la estructura post-refactor.
- `docs/API.md` — inventario de las 82 rutas.
- `docs/AUTENTICACION.md` — flujo de auth + CSRF + RBAC.
- `docs/OPERATIONS.md` — runbook de deploy + monitoring + troubleshooting
  + rollback.
- `docs/CHANGELOG.md` — este archivo.
- `docs/superpowers/plans/2026-07-01-adr-0001-refactor-monolito-flask.md` —
  plan de ejecución (status: in-progress, en actualización).

### Métricas finales

| Métrica | Antes | Después | Δ |
|---|---:|---:|---:|
| `app.py` LOC | 2 512 | 0 | ✅ |
| Blueprints | 0 (inline) | 13 | +13 |
| Rutas registradas | 81 | 82 | +1 |
| Módulos top-level de negocio | 11 | 0 | ✅ DoD-7 |
| Archivos `.py` en raíz (no-wsgi) | 11 | 2 | -9 |
| Tests passing | 0 | 428 (320 unit + 108 integration) | +428 |
| Cobertura (`app + db`) | 0% | 43.73% (gate 43%) | +43.73 pp |
| db/queries/* cobertura | 0% | ~80% (5 módulos al 100%) | +80 pp |

### DoD (Definition of Done) verificados

- ✅ DoD-1: `app.py` no existe.
- ✅ DoD-2: `db.py` no existe.
- ✅ DoD-3: 13 blueprints registrados.
- ✅ DoD-4: 82 rutas registradas.
- ✅ DoD-5: regla de capas verificada por AST (`tests/unit/test_arquitectura.py`).
- ✅ DoD-6: `middleware.py` eliminado por no usarse.
- ✅ DoD-7: no quedan módulos top-level de negocio.
- 🔴 DoD-8: cobertura 60% — **parcial al 43.73%** (gate 43%). Pendiente
  tests focalizados de `app/domain/reports.py` (1244 stmts, 11%) y
  `app/domain/report_docx.py` (451 stmts, 8%) — requieren mocks
  pesados del flujo de PDF/DOCX.
- ✅ DoD-9: 13+ tests de integración por blueprint (79 tests) +
  14 tests de `db/queries/*` (objetivo secundario 70% de queries).
- 🔴 DoD-10: branch protection en GitHub — manual (UI).
- ✅ DoD-11: `Dockerfile` → `wsgi:app`.
- ✅ DoD-12: runbook en `docs/OPERATIONS.md` (enlazado desde `docs/README.md`).
- ✅ DoD-13: Alembic como única fuente de verdad — `db/init.py` detecta
  `public.alembic_version` y salta DDL legacy; tests de `tests/integration/test_alembic.py`
  verifican que Alembic + init_db funcionan juntos.
- ⛔ DoD-14: `services/biometric_proxy/` con Dockerfile — descartado al
  eliminar `middleware.py`.

### Commits incluidos (en orden cronológico)

```
c2fbff2 refactor(monolith): Fase 3 complete + stabilization
9167550 chore(refactor): complete Fase 4e — domain services migration
5a4c70a refactor(domain): migrate script.py → app/domain/reports.py
74ed0aa refactor(domain): migrate script_docx.py → app/domain/report_docx.py
5c9d1a2 refactor(domain): migrate horarios.py → app/domain/attendance.py
fc2b709 refactor(domain): migrate analytics.py → app/domain/analytics.py
56bf733 refactor(domain): migrate ia_report.py → app/domain/ai_narrative.py
cc78aa4 refactor(domain): migrate backup.py → app/domain/backup.py
be3cc83 refactor(domain): migrate sync.py → app/domain/schedule.py
63dfd97 ci(github-actions): Fase 7.2 — CI workflow con PostgreSQL de test
38000d2 docs(operations): Fase 8 — docs/OPERATIONS.md runbook
1197aac docs(plan): mark Fase 4e + 7.2 + 8 as completed in plan frontmatter
890387c test(integration): Fase 7.1 — 13 integration tests per blueprint
8df10c0 test(coverage): Fase 7.4 — más integration tests + unit tests
9009cf9 test(coverage): Fase 7.4 — más tests + pyproject gate + CI usa pgserver
7bfa3aa docs(plan): update frontmatter — Fase 7.1 cerrada, 271 tests
84b52ff test(coverage): Fase 7.4 — sync_log + breaks insert + gate a 43%
4d9d0ea ci: update coverage gate to 43% (DoD-13 cerrado, db/queries ya testeados)
```

(Los commits previos de seguridad, sync observable y backups están en
`git log --oneline` pero no listados aquí.)

### Commits posteriores (Fase 7.4 continuación + DoD-13)

```
docs: comprehensive documentation of ADR-0001 refactor closure
  (ADR-0004, CHANGELOG.md, ARQUITECTURA.md, plan completed)
test(coverage): Fase 7.4 — db/queries tests (feriados, breaks, tenants, grupos, auth, dispositivos, asistencias)
test(coverage): Fase 7.4 — más db/queries tests (justificaciones, horarios, periodos)
test(coverage): Fase 7.4 — más db/queries tests (personas, asistencia_periodo)
test(coverage): Fase 7.4 — sync_log + breaks insert + gate a 43%
feat(alembic): Fase -1 / DoD-13 — Alembic como fuente de verdad
```

---

## [Pre-refactor] — Estado inicial del monolito

**Fecha**: hasta 2026-07-01
**Tipo**: legacy
**LOC `app.py`**: 2 512

### Características del monolito original

- 81 rutas registradas con `@app.route` inline.
- 61 decoradores `@require_role` / `@require_tipo_persona` directamente
  importados desde `decorators.py`.
- CSRF custom (sin Flask-WTF).
- Middleware de autenticación y carga de contexto de tenant en
  `before_request` único (líneas 156-227).
- `auth.py` con imports locales dentro de cada función (anti-patrón).
- 11 módulos top-level de negocio: `script.py`, `analytics.py`, `sync.py`,
  `horarios.py`, `ia_report.py`, `script_docx.py`, `auth.py`, `decorators.py`,
  `email_utils.py`, `middleware.py`, `db.py`.
- Capa de datos limpia: `db/queries/*.py` (15 módulos por dominio, SQLAlchemy
  Core + `text()` parametrizado).
- Drivers limpios: `drivers/` (Strategy + Factory).

### Tests

- 0 tests unitarios automatizados.
- 0 tests de integración.
- Cobertura 0%.

### CI

- No había CI workflow.

### Documentación

- `docs/ER.md` — Modelo de datos.
- `docs/SUPERADMIN.md` — Operaciones cross-tenant.
- `docs/API.md` — Inventario de rutas (pre-refactor).
- `docs/AUTENTICACION.md` — Flujo de autenticación.
- `DEPLOYMENT.md` — Guía de instalación.

### Commits notables previos

- `1152509 feat: rediseño visual completo (Design System v2.0)`
- `1a773ef feat: gestión global de usuarios para superadmin (cross-tenant)`
- `73ee13a fix: local deploy on internal red`
- `d14c801 docs: spec de diseño — sync automática confiable + backups portables`

---

## Convención

Cada release sigue este formato:

```
## [versión o tag] — Título descriptivo

**Fecha**: YYYY-MM-DD
**Tipo**: major | minor | patch | refactor | docs | test | security
**ADRs**: enlaces a ADRs afectados
**PRs**: enlaces a PRs (cuando se migre a PR-based workflow)

### Summary
Párrafo breve describiendo el cambio principal.

### Added (funcionalidad nueva)
- Bullet points

### Changed (modificaciones a funcionalidad existente)
- Bullet points

### Deprecated (deprecation warnings)
- Bullet points

### Removed (funcionalidad eliminada)
- Bullet points

### Fixed (bugs)
- Bullet points con descripción breve

### Security
- Bullet points

### Performance
- Bullet points

### Documentation
- Bullet points

### Métricas (opcional)
Tabla antes/después.

### DoD (opcional)
Tabla de Definition of Done.
```

Inspirado en [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
adaptado a wikilinks Obsidian (`[[...]]`) y al estilo del proyecto.
