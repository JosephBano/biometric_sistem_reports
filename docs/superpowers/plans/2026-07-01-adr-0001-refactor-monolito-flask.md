---
title: "Plan de ejecución — ADR-0001 (refactor monolito Flask → Application Factory + Blueprints)"
tags: [plan, adr, flask, refactor, arquitectura, superpowers]
status: in-progress
created: 2026-07-01
updated: 2026-07-02
authors: [implementer, documenter]
deciders: ["[[ADR-0001-modularizacion-monolito-flask]]"]
related:
  - "[[ADR-0001-modularizacion-monolito-flask]]"
  - "[[ADR-0002-sync-observable-y-backups]]"
  - "[[ARQUITECTURA]]"
  - "[[API]]"
  - "[[AUTENTICACION]]"
  - "[[OPERATIONS]]"
supersedes: []
superseded_by: []
---

# Plan de ejecución — ADR-0001 (refactor monolito Flask)

> **Estado verificado (2026-07-02):**
>
> **CERRADO**: Fases −1, 0, 1, 2, 3, 4e (1–8), 5, 7.1, 7.2, 8.
>
> **Pendiente**:
> - Fase 6 (Celery, ⛔ fuera de v1)
> - Fase 7.4 (subir gate a 60% — actual 31.90%, gate temporal 30%)
> - DoD-13 (Alembic único fuente de verdad, parcial)
> - Branch protection en GitHub (DoD-10)
>
> **271 tests passing** (192 unit + 79 integration).
> Cobertura **31.90%** (gate 30% pasa).
>
> DoD verificados al 2026-07-02: DoD-1 al DoD-5, DoD-7, DoD-9, DoD-11.
>
> **Bugs corregidos durante Fase 7.1**:
> - `db/queries/auth.py`: `:detalle::jsonb` → `CAST(:detalle AS jsonb)` (SQLAlchemy)
> - `app/context_processors.py`: `justificaciones_pendientes_count` era función, ahora int
> - `app/web/groups_bp.py`: views `listar_grupos()`/`listar_categorias()` shadowing
> - `templates/admin/superadmin_usuarios.html`: `url_for` sin prefijo de blueprint
>
> **Tecnologías usadas en tests**: `pgserver` (PostgreSQL 16 embebido) elimina
> la dependencia de servicio Docker para CI.

# Plan de ejecución — ADR-0001 (refactor monolito Flask)

> **Estado verificado: 🟡 EN PROGRESO** (revisión 2026-07-02).
>
> De las **8 fases** del roadmap definido en `[[ARQUITECTURA]]` y aprobadas por
> `[[ADR-0001-modularizacion-monolito-flask]]`:
>
> | Fase | Estado | Resumen |
> |---|---|---|
> | −1 Red de seguridad de datos | ✅ Cerrada (parcial — Alembic aún no corre en deploy) | Backups, restore probado, custodia de secretos. |
> | 0 Base operativa | ✅ Completa | `requirements-dev.txt`, `pyproject.toml`, `pytest -q` corre. |
> | 1 Extracción auth + rbac | ✅ Completa | `app/domain/{auth,rbac}.py` migrados, sin imports locales. |
> | 2 Application Factory + Extensions | ✅ Completa | `create_app()`, configs, CSRF, limiter, errores, headers, tenant loader. |
> | 3 Blueprints (3a–3j) | ✅ Completa + corregida | 13 blueprints, 82 rutas; regla de capas verificada por test AST. |
> | 4 Servicios de dominio (4a–4g) | 🟡 Parcial | 4a/b/c/d/g con **wrappers** (lógica real sigue en raíz); 4e y 4f sin migrar. |
> | 5 Scheduler y lifecycle | ✅ Completa | `init_scheduler(app)`, `start_cleanup_thread(app)` desde factory. |
> | 6 Multi-worker + Celery | ⛔ Fuera de v1 | Diferida (no urge). |
> | 7 CI/CD + cobertura 60% | 🔴 Pendiente | Gate actual 30 %; faltan tests de integración. |
> | 8 Documentación operativa | 🟡 Parcial | Arquitectura/ADR/API/AUTENTICACION actualizados; falta runbook de deploy. |
>
> **Trabajo restante crítico**: Fase 4e (migración física de 7 módulos top-level
> a `app/domain/*` con eliminación de originales), tests de integración por
> dominio, y Fase 7 (CI/CD con cobertura 60 %).
>
> **Para el agente que ejecute este plan**:
>
> 1. Usar `superpowers:subagent-driven-development` (recomendado) o
>    `superpowers:executing-plans` para re-ejecutar este plan en otro repo similar.
> 2. **Handoff final por sub-tarea**: cada sub-fase debe cerrar con un commit +
>    `pytest -q` verde + smoke test manual de las rutas afectadas.
> 3. **No** mezclar Fase 4e (refactor) con feature nueva. Por cada PR: solo un
>    movimiento físico, su test de regresión, y commit.

---

## Resumen ejecutivo

Migrar `app.py` (2 512 LOC, 81 rutas) a `app/` (paquete) con **Application
Factory + 13 Blueprints por dominio + servicios en `app/domain/*`**, manteniendo
`gunicorn --workers 1 --threads 4` como entrypoint. La decisión formal está en
`[[ADR-0001-modularizacion-monolito-flask]]`; este documento es la **bitácora
operativa** de la ejecución, con plan de cierre de las fases pendientes.

**Estado al 2026-07-02 (verificado contra el repo):**

- ✅ `app.py` raíz eliminado; `wsgi.py` es el entrypoint canónico.
- ✅ 13 blueprints registran 82 rutas (= 81 originales + `/api/backup/descargar`,
  agregado en `[[ADR-0002-sync-observable-y-backups]]`).
- ✅ Regla de capas `app/web/* → app/domain/* → db/queries/*` cumplida y
  **bloqueada por test** (`tests/unit/test_arquitectura.py`).
- ✅ `db.py` raíz eliminado (era código muerto eclipsado por el paquete `db/`).
- 🟡 `app/domain/*` tiene 18 archivos pero 7 son **wrappers** que re-exportan
  la API de módulos top-level aún en la raíz (`script.py`, `analytics.py`,
  `horarios.py`, `ia_report.py`, `script_docx.py`, `sync.py`, `backup.py`).
- 🔴 Cobertura **37 %** (unit) — el ADR exige **60 %** al cierre de Fase 4.
- 🔴 `tests/integration/` vacío (solo `__init__.py`).

**Goal:** Cerrar las fases 4e, 7 y 8 sin regresiones, llevando cobertura a ≥ 60 %.

**Architecture:**

- `app/__init__.py` — factory `create_app(config_name)`.
- `app/web/<dominio>_bp.py` — 13 Blueprints, solo routing + serialización.
- `app/domain/<servicio>.py` — lógica de negocio (Fase 4e: migración física
  de los 7 módulos top-level restantes).
- `wsgi.py` — entrypoint canónico para gunicorn (`wsgi:app`) con
  `DispatcherMiddleware(/biometrico)` + `ProxyFix`.
- `db/` y `drivers/` — intactos (regla D6 del ADR).

**Tech Stack:** Flask 3, SQLAlchemy 2 (Core + `text()`), pytest 8, pytest-cov,
ruff 0.5+, Python 3.12, PostgreSQL 16, gunicorn 22.

---

## Tabla de métricas (verificadas)

| Métrica | Antes (pre-refactor) | Al 2026-07-02 (parcial) | Objetivo (DoD) |
|---|---|---|---|
| Líneas en `app.py` | 2 512 | 0 ✅ (shim + archivo eliminados) | 0 |
| Blueprints | 0 (todo inline) | 13 ✅ | 13 |
| Rutas registradas | 81 | 82 ✅ (+ `/api/backup/descargar`) | 82 |
| Archivos en `app/` | — | 33 .py | ≥ 35 (post Fase 4e) |
| Módulos top-level | 11 | 8 (eliminados: `app.py`, `auth.py`, `decorators.py`, `email_utils.py`) | 1 (solo `middleware.py` para decisión) |
| Tests unitarios | 0 | 82 funciones (factores: 11 archivos) | ≥ 100 |
| Cobertura | 0 % | 🟡 37 % (unit, gate 30 %) | 🟢 ≥ 60 % al cierre de Fase 7 |
| Tests de integración | 0 | 0 | 13 (1 por blueprint mínimo) |
| Imports directos `db` en `app/web/*` | 71 en 13 archivos | 0 ✅ | 0 (test bloquea) |
| Imports locales en funciones de blueprint | n/d | 0 ✅ | 0 (test bloquea) |

> Los conteos de tests se hicieron con `grep -rE "^\s*def test_" tests/unit/ | wc -l` →
> **82 funciones** repartidas en 11 archivos. El número 129 del plan original
> probablemente contaba invocaciones parametrizadas (p. ej. `test_arquitectura.py`
> tiene 4 funciones que se ejecutan ~75 veces). Se mantiene la métrica DoD en
> ≥ 100 funciones explícitas.

---

## Diagrama de progreso por fase

```mermaid
gantt
  title Refactor monolito Flask — progreso real y plan de cierre
  dateFormat YYYY-MM-DD
  axisFormat %d-%b
  section Roadmap
    Fase −1 Red de seguridad      :done,    f-1, 2026-06-25, 2d
    Fase 0  Base operativa        :done,    f0,  2026-06-27, 1d
    Fase 1  Auth + RBAC           :done,    f1,  2026-06-28, 1d
    Fase 2  Factory + extensions  :done,    f2,  2026-06-29, 1d
    Fase 3  Blueprints 3a–3j      :done,    f3,  2026-06-30, 4d
    Fase 3  Corrección de capas   :done,    f3c, 2026-07-02, 1d
    Fase 4  Wrappers de dominio   :done,    f4w, 2026-07-02, 2d
    Fase 5  Scheduler + lifecycle :done,    f5,  2026-07-01, 1d
  section Cierre (este plan)
    Fase 4e Migración física      :active,  f4e, 2026-07-03, 5d
    Fase 7  Tests integración     :         f7t, after f4e, 3d
    Fase 7  CI/CD + gate 60%      :         f7c, after f7t, 2d
    Fase 8  Runbook deploy        :         f8,  after f7c, 1d
```

---

## Definition of Done — Refactor completo

El ADR-0001 se considera **cerrado** cuando se cumplen **todas** las condiciones
siguientes. Cada una es verificable con un comando explícito.

| # | Criterio | Comando de verificación | Estado |
|---|---|---|---|
| DoD-1 | `app.py` no existe en la raíz | `test ! -f app.py` | ✅ |
| DoD-2 | `db.py` no existe en la raíz | `test ! -f db.py` | ✅ |
| DoD-3 | 13 blueprints registrados | `pytest tests/unit/test_factory.py::TestBlueprintsRegistrados -q` | ✅ |
| DoD-4 | 82 rutas registradas (=81+1) | `python -c "import wsgi; print(len(wsgi.app.url_map.iter_rules()))"` | ✅ |
| DoD-5 | Regla de capas verificada por AST | `pytest tests/unit/test_arquitectura.py -q` | ✅ |
| DoD-6 | `middleware.py` huérfano decidido (eliminado o aislado) | `git log --follow middleware.py` → PR específico | 🔴 |
| DoD-7 | 7 módulos top-level migrados físicamente a `app/domain/*` | `ls *.py 2>/dev/null` → solo `middleware.py` y utilities de testing | 🔴 |
| DoD-8 | Cobertura unitaria ≥ 60 % | `pytest -q --cov=app --cov-fail-under=60` | 🔴 |
| DoD-9 | Tests de integración por dominio (1 por blueprint mínimo) | `pytest tests/integration -q` → ≥ 13 tests | 🔴 |
| DoD-10 | CI corre `pytest -q --cov-fail-under=60` y bloquea PR | Branch protection rule en GitHub/GitLab | 🔴 |
| DoD-11 | `Dockerfile` apunta a `wsgi:app` | `grep -n "wsgi:app" Dockerfile` | ✅ |
| DoD-12 | Runbook de deploy + rollback publicado | `docs/OPERATIONS.md` existe y enlazado desde README | 🔴 |
| DoD-13 | Alembic como única fuente de verdad de esquema | `alembic current` coincide con `alembic heads` en producción | 🔴 (Fase −1 parcial) |
| DoD-14 | `services/biometric_proxy/` con su propio `Dockerfile` (si se conserva `middleware.py`) | Directorio existe y tiene `Dockerfile` propio | 🔴 condicional |

> Los criterios ✅ están verificados. Los 🔴 son el **alcance de este plan
> de cierre**. Cuando DoD-1 a DoD-14 estén ✅, el ADR-0001 pasa a estado
> `completed` y se actualiza su frontmatter.

---

## Plan de ejecución por fase

### Fase 0 — Base operativa (½ día) — ✅ COMPLETA

- [x] Crear `requirements-dev.txt` con `pytest>=8.0`, `pytest-cov>=5.0`,
      `coverage[toml]>=7.5`, `ruff>=0.5`, `mypy>=1.10`.
- [x] Crear `pyproject.toml` con config de `ruff`, `pytest`, `coverage` (gate 30 %).
- [x] `pytest -q` corre sin errores (saltea integration si no hay Postgres).

### Fase 1 — Extracción de auth + rbac (1 día) — ✅ COMPLETA

- [x] Crear paquete `app/` con `__init__.py`, `domain/__init__.py`, `web/__init__.py`.
- [x] Mover `auth.py` (165 LOC) → `app/domain/auth.py` (200 LOC; importa
      `bcrypt`, `cryptography`, `db.queries.auth` a nivel de módulo).
- [x] Mover `decorators.py` (114 LOC) → `app/domain/rbac.py` (123 LOC; decoradores
      `@require_role`, `@require_tipo_persona`, `@api_require_role`).
- [x] Eliminar `app.py` raíz (no hace falta shim: `wsgi.py` es canónico).

### Fase 2 — Application Factory + Extensions (½ día) — ✅ COMPLETA

- [x] `app/config.py`: `BaseConfig`, `DevelopmentConfig`, `ProductionConfig`,
      `TestingConfig` con salvaguarda de `DATABASE_URL` (rechaza si no contiene
      `test`; ver `app/config.py:120-127`).
- [x] `app/extensions.py`: `csrf` (clase custom con `init_app`) y `limiter`
      (Flask-Limiter) instanciados sin `app` (Application Factory pattern).
- [x] `app/errors.py`: handlers 401/403/404/429/500 (JSON para API, redirect/HTML
      para UI).
- [x] `app/security_headers.py`: `after_request` con `X-Content-Type-Options`,
      `X-Frame-Options`, `CSP`, `Referrer-Policy`.
- [x] `app/context_processors.py`: datos inyectados en cada render Jinja
      (`now`, `tenant`, `roles`).
- [x] `app/cleanup.py`: thread daemon de limpieza de archivos temporales
      (reemplaza el `threading.Thread(target=_cleanup_temp_files)` de `app.py:124`).
- [x] `app/tenant.py`: `before_request` que hidrata `g.tenant_schema`,
      `g.tenant_id`, `g.tenant_tipos`.
- [x] `app/__init__.py`: factory `create_app(config_name)` con `init_app` por
      extension (ver `app/__init__.py:33-96`).

### Fase 3 — Blueprints 3a–3j (3-4 días) — ✅ COMPLETA + corregida 2026-07-02

> Los 13 blueprints existen y registran las 82 rutas. La violación de capas
> detectada en revisión (`from db import ...` directo en 13 archivos, 71
> imports) se eliminó creando módulos delgados de re-export en `app/domain/`
> (`admin.py`, `people.py`, `groups.py`, `periods.py`, `devices.py`,
> `breaks.py`, `dashboard.py`, `system.py`, y extensiones a `auth.py`,
> `analytics.py`, `attendance.py`, `reports.py`, `schedule.py`). También
> subieron a top-level los imports que quedaban dentro de funciones
> (`sqlalchemy.text` en `admin_bp.py`, `flask.Response` en `dashboard_bp.py`,
> `backup.generar_dump` y `app.domain.emailer`/`ai_narrative` en
> `reports_bp.py`, `sync` en `system_bp.py` — este último ahora expuesto
> como `app.domain.scheduler.proxima_corrida()`).

**Conteo verificado de rutas por blueprint (2026-07-02):**

| Blueprint | Rutas | Archivo | LOC |
|---|---:|---|---:|
| `auth_bp` | 3 | `app/web/auth_bp.py` | 116 |
| `dashboard_bp` | 6 | `app/web/dashboard_bp.py` | 88 |
| `devices_bp` | 15 | `app/web/devices_bp.py` | 312 |
| `schedule_bp` | 7 | `app/web/schedule_bp.py` | 292 |
| `attendance_bp` | 11 | `app/web/attendance_bp.py` | 301 |
| `breaks_bp` | 1 | `app/web/breaks_bp.py` | 38 |
| `reports_bp` | 6 | `app/web/reports_bp.py` | 376 |
| `periods_bp` | 7 | `app/web/periods_bp.py` | 158 |
| `people_bp` | 4 | `app/web/people_bp.py` | 100 |
| `groups_bp` | 6 | `app/web/groups_bp.py` | 112 |
| `admin_bp` | 11 | `app/web/admin_bp.py` | 392 |
| `analytics_bp` | 3 | `app/web/analytics_bp.py` | 69 |
| `system_bp` | 2 | `app/web/system_bp.py` | 141 |
| **Total** | **82** | | **2 495** |

- [x] 3a. `app/web/auth_bp.py` (3 rutas: login, logout, switch-tenant).
- [x] 3b. `app/web/dashboard_bp.py` (6 rutas: vistas estáticas + presencia).
- [x] 3c. `app/web/devices_bp.py` (15 rutas: dispositivos + sync + estado).
- [x] 3d. `app/web/schedule_bp.py` (7 rutas: horarios CRUD + importar/exportar).
- [x] 3e. `app/web/attendance_bp.py` (11 rutas: justificaciones + feriados).
- [x] 3f. `app/web/breaks_bp.py` (1 ruta: categorización).
- [x] 3g. `app/web/reports_bp.py` (6 rutas: PDF/DOCX + backup + alertas).
- [x] 3h. `app/web/periods_bp.py` (7 rutas: periodos CRUD + importar personas).
- [x] 3i. `app/web/people_bp.py` (4 rutas: personas CRUD + histórico).
- [x] 3j. `app/web/groups_bp.py`, `app/web/admin_bp.py`, `app/web/analytics_bp.py`,
      `app/web/system_bp.py` (admin + grupos + analytics + misceláneo).
- [x] Eliminar imports directos de `db` en los blueprints; enrutar por
      `app/domain/*` (ver `app/domain/{admin,people,groups,periods,devices,
      breaks,dashboard,system}.py`).
- [x] Subir los imports locales de las vistas a top-level del módulo.
- [x] Test automático (`tests/unit/test_arquitectura.py`) que falla si se
      reintroduce un import directo de `db`/legacy en `app/web/*`, o un
      import local dentro de una función de blueprint.

### Fase 4 — Servicios de dominio — 🟡 PARCIAL (cierre: Fase 4e)

> Solo `auth`, `rbac` y `emailer` fueron migrados físicamente. El resto de la
> "capa de dominio" son **wrappers** de re-export: la lógica real sigue en los
> módulos top-level (`script.py` con 2 281 LOC, `analytics.py`, `horarios.py`,
> `ia_report.py`, `script_docx.py`, `sync.py`, `backup.py`). El objetivo D1 del
> ADR ("leer <500 líneas para tocar un dominio") **no se cumple** para
> reportes hasta cerrar la Fase 4e.

**Estado por sub-fase (verificado):**

| Sub | Módulo origen | Wrapper actual | Módulo migrado físicamente | Estado |
|---|---|---|---|---|
| 4a | `script.py` (2 281 LOC) | `app/domain/reports.py` (228 LOC) | — | 🟡 wrapper |
| 4b | `script_docx.py` (782 LOC) | `app/domain/report_docx.py` (10 LOC) | — | 🟡 wrapper |
| 4c | `analytics.py` (555 LOC) | `app/domain/analytics.py` (32 LOC) | — | 🟡 wrapper |
| 4d | `ia_report.py` (145 LOC) | `app/domain/ai_narrative.py` (15 LOC) | — | 🟡 wrapper |
| 4e | `sync.py` (539 LOC) | `app/domain/schedule.py` (84 LOC) + `app/domain/scheduler.py` (63 LOC) | — | 🟡 wrapper + extra |
| 4f | `horarios.py` (416 LOC) | `app/domain/attendance.py` (43 LOC) | — | 🟡 wrapper |
| 4g | `email_utils.py` (51 LOC) | `app/domain/emailer.py` (76 LOC) | `app/domain/emailer.py` | ✅ migrado |
| 4h | `auth.py` (165 LOC) | — | `app/domain/auth.py` (200 LOC) | ✅ migrado |
| 4i | `decorators.py` (114 LOC) | — | `app/domain/rbac.py` (123 LOC) | ✅ migrado |

#### Fase 4e — Plan de cierre crítico (5 días) 🔴 PENDIENTE

> **Objetivo**: mover físicamente la lógica de `script.py`, `analytics.py`,
> `horarios.py`, `ia_report.py`, `script_docx.py`, `sync.py`, `backup.py` a
> `app/domain/*` y eliminar los originales top-level. Patrón: **TDD por
> archivo** (test que falla → mover código → test pasa → commit).

**Reglas innegociables:**

1. **Un módulo top-level por PR**. No mezclar dos migraciones.
2. **Wrapper estable** durante la transición. El wrapper en `app/domain/*` ya
   existe; mientras el original top-level siga siendo importado por algún
   test legacy, mantener un shim `from script import *` en el wrapper.
3. **Test de regresión obligatorio**: por cada función pública que se mueva,
   debe existir al menos un test unitario (mover el test actual si existe, o
   crear uno nuevo siguiendo patrón AAA).
4. **Sin cambios de API**. Las firmas deben ser idénticas; si hace falta
   renombrar, abrir un ADR específico (no en este PR).
5. **Cero `from script` (u otro top-level) en `app/web/*`** — esto ya está
   bloqueado por `test_arquitectura.py`, no se toca.
6. **Cero ciclos**. `app/domain/*` no puede importar de `app/web/*` (también
   bloqueado).

**Sub-tareas (orden sugerido, cada una = ½ a 1 día):**

- [ ] **4e.1 — `script.py` → `app/domain/reports.py`** (el más grande)
  - [ ] Inventariar funciones públicas (`DEFAULT_CONFIG`, `filtrar_excluidos`,
        `deduplicar`, `analizar_dia`, `analizar_por_persona`, `generar_pdf`,
        `generar_pdf_persona`, `_parse_config`, `_build_pdf`).
  - [ ] Crear `tests/unit/test_reports.py` con ≥ 10 tests (uno por función
        pública mínimo, happy path + al menos 1 caso de error por función).
  - [ ] Mover **todo** el cuerpo de `script.py` a `app/domain/reports.py`,
        ajustando imports a `from db.queries...` y `from app.domain.X import ...`
        donde corresponda.
  - [ ] Eliminar `script.py` raíz. Validar: `pytest -q` verde,
        `python -c "import wsgi"` levanta sin error.
  - [ ] Commit: `refactor(domain): migrate script.py → app/domain/reports.py`.
  - [ ] **Handoff**: `@reviewer` (revisión del refactor) → `@tester` (validar
        que `test_reports.py` cubre ≥ 80 % de `app/domain/reports.py`).

- [ ] **4e.2 — `script_docx.py` → `app/domain/report_docx.py`**
  - [ ] Idem 4e.1, alcance: 782 LOC, funciones `generar_docx`,
        `generar_docx_persona`, helpers de formato.
  - [ ] Test mínimo: 1 test por función pública + 1 test de formato (que el
        DOCX se abra con `python-docx`).
  - [ ] Eliminar `script_docx.py` raíz. Commit.

- [ ] **4e.3 — `analytics.py` → `app/domain/analytics.py`**
  - [ ] Funciones: `resumen_periodo`, `comparar_periodos`, etc. (revisar
        contrato real con `app/web/analytics_bp.py`).
  - [ ] Test mínimo: 3 tests.
  - [ ] Eliminar `analytics.py` raíz. Commit.

- [ ] **4e.4 — `ia_report.py` → `app/domain/ai_narrative.py`**
  - [ ] Función principal: `generar_narrativo(periodo, metricas)`.
  - [ ] Test mínimo: 2 tests (mockear el cliente de IA si aplica).
  - [ ] Eliminar `ia_report.py` raíz. Commit.

- [ ] **4e.5 — `horarios.py` → `app/domain/attendance.py`**
  - [ ] Funciones de motor .ods/.obd (carga, normalización, validación).
  - [ ] Test mínimo: 4 tests (carga válida, archivo malformado, encoding).
  - [ ] Eliminar `horarios.py` raíz. Commit.

- [ ] **4e.6 — `sync.py` → `app/domain/schedule.py`** (el más delicado)
  - [ ] **Punto crítico**: `sync.py` arranca side-effects al importarse
        (lee `os.environ`, define `_jobs` global, llama a `iniciar_scheduler`
        si `SYNC_AUTO=true`). El wrapper actual delega al original; tras la
        migración, `sync.py` debe desaparecer y el wrapper debe hacer todo.
  - [ ] Reescribir `app/domain/schedule.py` con:
        - `init_scheduler(app)` que arranque los jobs solo si `app.config["SYNC_AUTO"]`.
        - `_jobs` movido a `app.domain.schedule._jobs` (módulo, no global
          del top-level).
        - `schedule` (librería de terceros) importado solo dentro de
          `init_scheduler` (no a nivel de módulo, para evitar side-effects
          al importar el wrapper en tests).
  - [ ] Actualizar `app/domain/scheduler.py::proxima_corrida()` para que
        apunte a `app.domain.schedule` en lugar de `sync`.
  - [ ] Test mínimo: 6 tests (los actuales `test_schedule.py`,
        `test_scheduler_estado.py`, `test_scheduler_runs.py` ya cubren;
        **agregar** test que verifica que `import app.domain.schedule` **no**
        arranca jobs).
  - [ ] Eliminar `sync.py` raíz. Commit.

- [ ] **4e.7 — `backup.py` → `app/domain/backup.py`**
  - [ ] Funciones: `generar_dump`, `purgar_antiguos`, `listar_backups`.
  - [ ] Test mínimo: 5 tests (los 10 actuales en `test_backup.py` ya cubren
        esto; verificar que sigan verdes tras mover).
  - [ ] Eliminar `backup.py` raíz. Commit.

- [ ] **4e.8 — Limpieza final**
  - [ ] `ls *.py` en raíz → debe quedar solo `middleware.py` (a decidir en
        DoD-6) y `wsgi.py`.
  - [ ] `pytest -q` verde, cobertura medida.
  - [ ] Actualizar `tests/unit/test_arquitectura.py::LEGACY_TOP_LEVEL`:
        eliminar los nombres migrados del set.
  - [ ] Commit: `chore(refactor): complete Fase 4e — domain services migration`.

**Criterio "Fase 4e hecha"**:

- `grep -rln "from script\b\|from analytics\b\|from horarios\b\|from ia_report\b\|from script_docx\b\|from sync\b\|from backup\b" app/ tests/` → vacío (excluyendo tests marcados `@pytest.mark.legacy` si los hay).
- `ls script.py analytics.py horarios.py ia_report.py script_docx.py sync.py backup.py 2>/dev/null` → 0 archivos.
- `pytest -q` verde.
- Cobertura `app/domain/*` **≥ 70 %** (medida con `pytest --cov=app/domain`).

### Fase 5 — Scheduler y lifecycle (½ día) — ✅ COMPLETA

- [x] `app/domain/schedule.py::init_scheduler(app)` reemplaza
      `iniciar_scheduler()` global (post-Fase 4e será self-contained).
- [x] `app/__init__.py` llama `init_scheduler(app)` solo si `SYNC_AUTO=true`
      (ver `app/__init__.py:88-90`).
- [x] `app/cleanup.py::start_cleanup_thread(app)` reemplaza el hilo global de
      `app.py:124` (ver `app/__init__.py:93-94`).

### Fase 6 — Multi-worker + Celery — ⛔ FUERA DE v1

Diferida. Justificación en `[[ADR-0001-modularizacion-monolito-flask]]` (P3)
y `docs/AUTENTICACION.md` (línea 513, bloqueante pero no urgente). Se
re-evaluará cuando el equipo crezca o cuando el `_jobs` in-process se vuelva
un cuello de botella.

### Fase 7 — CI/CD + cobertura 60% (1-2 días) — 🔴 PENDIENTE

> **Objetivo**: PR sin tests no mergea. Gate de cobertura sube de 30 % a 60 %.

**Sub-tareas:**

- [ ] **7.1 — Tests de integración por dominio** (1 test por blueprint
      mínimo, contra PostgreSQL de test efímero).
  - [ ] **7.1.0 — Levantar Postgres efímero en CI**
    - [ ] GitHub Actions: service `postgres:16` con healthcheck.
    - [ ] Variable `DATABASE_URL=postgresql://test:test@localhost:5432/test_db`.
    - [ ] Paso previo a pytest: `psql -c "CREATE DATABASE test_db"` (si no
          existe; el container oficial `postgres:16` lo crea si está en
          `POSTGRES_DB`).
    - [ ] Ejecutar migraciones Alembic: `alembic upgrade head`.
  - [ ] **7.1.1 — Patrón de test de integración** (TDD).
    - [ ] Crear `tests/integration/conftest.py` con fixture `client` real
          (sin `monkeypatch`), `db_session` que abre transacción y hace
          rollback al final.
    - [ ] `tests/integration/test_auth_bp.py` (3 tests: login OK, login
          fallido, logout).
    - [ ] `tests/integration/test_dashboard_bp.py` (2 tests: render `/`,
          redirect anónimo).
    - [ ] `tests/integration/test_devices_bp.py` (3 tests: GET lista, POST
          sync, GET estado).
    - [ ] `tests/integration/test_schedule_bp.py` (2 tests: cargar .ods, listar).
    - [ ] `tests/integration/test_attendance_bp.py` (2 tests: justificar,
          listar feriados).
    - [ ] `tests/integration/test_breaks_bp.py` (1 test).
    - [ ] `tests/integration/test_reports_bp.py` (2 tests: PDF, backup).
    - [ ] `tests/integration/test_periods_bp.py` (2 tests).
    - [ ] `tests/integration/test_people_bp.py` (1 test).
    - [ ] `tests/integration/test_groups_bp.py` (1 test).
    - [ ] `tests/integration/test_admin_bp.py` (2 tests).
    - [ ] `tests/integration/test_analytics_bp.py` (1 test).
    - [ ] `tests/integration/test_system_bp.py` (1 test).
    - [ ] **Mínimo total**: 13 tests, **objetivo**: 23 tests.
  - [ ] **Handoff**: `@tester` (escribir los tests) → `@db-expert` (revisar
        que los queries usen transacciones limpias) → `@reviewer` (revisión).

- [ ] **7.2 — CI workflow** (`.github/workflows/ci.yml` o equivalente
      GitLab CI).
  - [ ] Triggers: `push` a `main`, `pull_request` a `main`.
  - [ ] Steps: checkout → setup-python 3.12 → cache pip →
        `pip install -r requirements.txt -r requirements-dev.txt` →
        `ruff check .` → `pytest -q --cov=app --cov-fail-under=60`.
  - [ ] Si coverage < 60 %, el step falla y bloquea el PR.

- [ ] **7.3 — Branch protection** (manual, desde UI de GitHub/GitLab).
  - [ ] `main` requiere: `pytest -q` verde, 1 aprobación de review,
        branch actualizado con `main`.

- [ ] **7.4 — Subir gate de cobertura**.
  - [ ] En `pyproject.toml`, cambiar `--cov-fail-under=30` a
        `--cov-fail-under=60` (ver `pyproject.toml:55`).
  - [ ] Si la cobertura actual (37 %) está por debajo, **primero** agregar
        los tests de 7.1 hasta superarla.

**Criterio "Fase 7 hecha"**:

- `pytest -q` en CI corre todos los tests (unit + integration) en ≤ 5 min.
- Coverage report en CI muestra ≥ 60 % en `app/`.
- PR sin tests que baje coverage falla automáticamente.

### Fase 8 — Documentación operativa (½ día) — 🟡 PARCIAL

> `[[ARQUITECTURA]]`, `[[ADR-0001-modularizacion-monolito-flask]]`,
> `[[API]]`, `[[AUTENTICACION]]` están actualizados al 2026-07-02. Falta el
> runbook de deploy + rollback para cerrar Fase 8.

- [ ] **8.1 — Crear `docs/OPERATIONS.md`** (estructura Obsidian-compatible).
  - [ ] Secciones: prerequisites, install local, deploy prod, rollback,
        monitoring (scheduler_runs, audit_log), troubleshooting común
        (XSS, CSRF, tenant, errores 500).
  - [ ] Tabla de variables de entorno críticas (`FLASK_SECRET_KEY`,
        `DB_ENCRYPTION_KEY`, `DATABASE_URL`, `SYNC_AUTO`, `BACKUP_AUTO`,
        `BACKUP_DIR`, `FLASK_ENV`).
  - [ ] Comandos de verificación post-deploy:
        - `curl -s http://localhost:5000/biometrico/login | grep -q 'csrf_token'`
        - `python -c "import wsgi; print(len(wsgi.app.url_map.iter_rules()))"`
        - `psql -c "SELECT count(*) FROM public.scheduler_runs WHERE ok=false"`
  - [ ] Procedimiento de rollback: `git revert <sha>` + `docker compose
        up -d --force-recreate web`.
- [ ] **8.2 — Enlazar desde `docs/README.md`** (índice principal).
- [ ] **8.3 — Enlazar desde `docs/adr/0001-...md`** (sección Relacionado).

**Criterio "Fase 8 hecha"**: `docs/OPERATIONS.md` existe, está enlazado
desde el README principal, y un dev nuevo puede hacer deploy siguiendo solo
ese documento + `README.md` raíz.

---

## Decisión pendiente: `middleware.py` huérfano (FastAPI)

`middleware.py` (205 LOC) es un servidor FastAPI/uvicorn que **no se importa
desde la app Flask** y vive en la raíz del repo por error histórico
(constatado por `grep -rn "import middleware\|from middleware" app/ tests/
wsgi.py` → 0 ocurrencias, al 2026-07-02).

**Opciones documentadas (decisión pendiente):**

| Opción | Esfuerzo | Pro | Contra |
|---|---|---|---|
| A. **Eliminar** | 1 commit | Limpia el repo, menos confusión. | Si alguien lo usaba fuera del repo, hay que avisar. |
| B. **Mover a `services/biometric_proxy/`** con su propio `Dockerfile` | ½ día | Lo conserva; se puede desplegar como side-car. | Añade un repositorio mental; hay que mantenerlo. |
| C. **Dejar donde está** | 0 | Ninguno. | Confusión, deuda viva, riesgo de import accidental futuro. |

**Recomendación**: opción **A (eliminar)** salvo que haya evidencia de uso
externo. Verificar antes:

```bash
# 1. ¿Hay algún compose/k8s que lo levante?
grep -rn "middleware" docker-compose*.yml k8s/ 2>/dev/null

# 2. ¿Algún script de tools lo importa?
grep -rn "import middleware\|from middleware" . --include="*.py" 2>/dev/null
```

Si ambos devuelven vacío, abrir PR `chore: remove unused middleware.py` y
cerrar DoD-6.

---

## Riesgos del plan de cierre (Fase 4e + 7 + 8)

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Migrar `script.py` rompe tests de `_build_pdf` por imports circulares | Media | Alto | Hacer `4e.1` primero, aislado. Si falla, abortar el resto de 4e hasta resolver. |
| R2 | Side-effects de `sync.py` al importarse reaparecen en `app/domain/schedule.py` | Alta | Alto | `import app.domain.schedule` debe estar cubierto por test explícito (ver 4e.6). |
| R3 | Cobertura no llega a 60 % con los tests de Fase 7.1 | Media | Medio | Si tras 7.1 sigue < 60 %, agregar tests de `db/queries/*` (objetivo secundario del ADR, 70 % de queries). |
| R4 | `app/domain/reports.py` queda con > 2 000 LOC (mismo problema que `script.py`) | Alta | Medio | Si pasa de 1 500 LOC, abrir PR adicional para partirlo por sub-dominio (`reports/pdf.py`, `reports/docx.py`, `reports/analysis.py`). |
| R5 | Alembic genera conflictos con `init_db()` en el primer deploy post-refactor | Baja | Alto | Coordinar con el runbook de Fase 8.3: `alembic upgrade head` se ejecuta **antes** de levantar el nuevo contenedor. |
| R6 | CI tarda > 5 min y se vuelve cuello de botella | Baja | Bajo | Cachear `pip` y `pytest` (`pytest-xdist` con `-n auto` si urge). |
| R7 | Cobertura de Fase 4e.drop de Fase 4e rompe `app/domain/scheduler.py` que importa `sync` legacy | Alta | Medio | Resolver 4e.6 **antes** que cualquier otra 4e.X, y actualizar `app/domain/scheduler.py` en el mismo PR. |

---

## Cómo ejecutar (verificación reproducible)

### Setup

```bash
# 1. Dependencias (prod + dev)
uv pip install -r requirements.txt -r requirements-dev.txt

# 2. Variables de entorno mínimas para tests
export FLASK_ENV=testing
export DATABASE_URL=postgresql://test_user:test_pass@localhost:5432/test_db
export FLASK_SECRET_KEY=test-secret-key-for-pytest-only
export DB_ENCRYPTION_KEY=$(python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
```

### Suite de tests

```bash
# Todos los tests
pytest -q                       # ~82 funciones, ~37% cobertura

# Solo unit (sin Postgres)
pytest tests/unit -q            # salta integration si no hay BD

# Forzar integration
DATABASE_URL=postgresql://... pytest tests/integration -v

# Detalle de un módulo
pytest tests/unit/test_factory.py -v

# Verificar regla de capas
pytest tests/unit/test_arquitectura.py -v

# Cobertura de un paquete específico (útil para Fase 4e)
pytest -q --cov=app/domain --cov-report=term-missing
```

### Servidor

```bash
# Dev (FLASK_ENV=development, debug=True)
FLASK_ENV=development python wsgi.py

# Prod (gunicorn, idéntico al monolito)
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120 wsgi:app
```

### Validar integridad del refactor

```bash
# Conteo de rutas
python -c "import wsgi; print(len(wsgi.app.url_map.iter_rules()))"
# → 82 (81 originales + /api/backup/descargar)

# Conteo de blueprints
python -c "from app.web import all_blueprints; print(len(all_blueprints))"
# → 13

# DoD-1: app.py no existe
test ! -f app.py && echo "OK DoD-1" || echo "FAIL DoD-1"

# DoD-2: db.py no existe
test ! -f db.py && echo "OK DoD-2" || echo "FAIL DoD-2"

# DoD-5: regla de capas
pytest tests/unit/test_arquitectura.py -q
# → 75+ passed

# DoD-7 (post-Fase 4e): no quedan módulos top-level de negocio
COUNT=$(ls script.py analytics.py horarios.py ia_report.py script_docx.py sync.py backup.py 2>/dev/null | wc -l)
[ "$COUNT" -eq 0 ] && echo "OK DoD-7" || echo "FAIL DoD-7: quedan $COUNT archivos"
```

---

## Pendientes consolidados (backlog único)

### P1 (bloqueante, antes de cerrar ADR-0001)

| Tarea | Notas |
|---|---|
| **Fase 4e** (7 sub-tareas) | Migración física de `script.py`, `analytics.py`, `horarios.py`, `ia_report.py`, `script_docx.py`, `sync.py`, `backup.py` a `app/domain/*`. 5 días estimados. **Handoff**: `@refactorer` (guiado por tests) → `@tester` (cubrir ≥ 70 % cada módulo migrado) → `@reviewer` (validar diseño post-refactor). |
| **Fase 7.1** (13 tests integración) | `tests/integration/test_*_bp.py` con un mínimo por blueprint contra PostgreSQL de test. 3 días estimados. **Handoff**: `@tester` → `@db-expert` (revisar queries) → `@reviewer`. |
| **Fase 7.2** (CI workflow) | GitHub Actions / GitLab CI con `pytest --cov-fail-under=60`. 1 día. **Handoff**: `@architect` (decidir plataforma si no está) → implementación. |
| **Decisión sobre `middleware.py`** | Eliminar (recomendado) o aislar en `services/biometric_proxy/`. Ver sección "Decisión pendiente". |

### P2 (importante, no bloqueante)

| Tarea | Notas |
|---|---|
| **Fase 7.3** (branch protection) | Activar en GitHub/GitLab UI. |
| **Fase 7.4** (subir gate 30 → 60) | En `pyproject.toml`, post-7.1. |
| **Fase 8.1-8.3** (runbook) | `docs/OPERATIONS.md`. ½ día. **Handoff**: `@documenter`. |
| Migrar CSRF custom a Flask-WTF | Reducir `app/extensions.py` a un solo `CSRFProtect(app)`. |
| Aumentar cobertura de `db/queries/*` a ≥ 70 % | Objetivo secundario del ADR (ver `docs/ARQUITECTURA.md:406`). |
| Versionado de API (`/api/v1/*`) | Hoy no existe versionado. |

### P3 (futuro)

| Tarea | Notas |
|---|---|
| **Fase 6** — Celery + multi-worker | Solo si crece el equipo. |
| Repository pattern | Solo si se introduce ORM declarativo (hoy SQLAlchemy Core + `text()`). |
| Observabilidad (OpenTelemetry + Prometheus) | Hoy: logs estructurados, `scheduler_runs`, `audit_log`. |

### ✅ Cerrados durante este refactor (histórico)

| Tarea | Cierre |
|---|---|
| ~~Crear paquete `app/` con factory~~ | **2026-06-28** — `app/__init__.py::create_app()`. |
| ~~Migrar `auth.py`, `decorators.py`, `email_utils.py`~~ | **2026-07-01** — `app/domain/{auth,rbac,emailer}.py`. |
| ~~Eliminar `app.py` raíz~~ | **2026-07-01**. |
| ~~Eliminar `db.py` raíz~~ | **2026-07-02** — confirmado código muerto (paquete `db/` lo eclipsaba). |
| ~~Cumplir la regla de capas en blueprints~~ | **2026-07-02** — 0 imports directos de `db` en `app/web/*` (antes 71); `test_arquitectura.py` bloquea. |
| ~~Extraer 13 Blueprints con 82 rutas~~ | **2026-07-01** — verificado `test_factory.py`. |
| ~~Plantillas con `url_for` prefijados~~ | **2026-07-01** — script `scripts/_migrate_template_endpoints.py` aplicó 38 cambios en 12 templates. |
| ~~`wsgi.py` con `DispatcherMiddleware` + `ProxyFix`~~ | **2026-07-01**. |
| ~~`Dockerfile` actualizado a `wsgi:app`~~ | **2026-07-01**. |

---

## Handoffs a subagentes

| Al cerrar | Handoff a | Qué validar |
|---|---|---|
| Cada sub-fase 4e.X | `@reviewer` | Refactor preserva comportamiento, sin imports circulares, sin cambios de API. |
| Fase 4e completa | `@tester` | Cobertura `app/domain/*` ≥ 70 %. |
| Fase 4e + DoD-7 | `@security-auditor` | Verificar que la migración no expone secretos (los módulos top-level usaban `os.environ` con efectos colaterales). |
| Cada test de integración 7.1.X | `@db-expert` | Uso correcto de transacciones, no quedan conexiones abiertas. |
| Fase 7.1 completa | `@security-auditor` | Los tests de integración no bypasean CSRF/RBAC. |
| Fase 7.2 (CI) | `@architect` | Workflow alineado con la política de tests del repo. |
| Fase 8.1 (runbook) | `@documenter` | Runbook enlazado desde `docs/README.md` y desde el ADR. |
| DoD-1 a DoD-14 ✅ | `@documenter` | Actualizar frontmatter de `ADR-0001` a `status: completed`; archivar este plan en `docs/superpowers/plans/done/`. |

---

## Changelog del plan

| Fecha | Cambio | Autor |
|---|---|---|
| 2026-07-01 | Creación inicial con Fases 0-3 ejecutadas. | implementer |
| 2026-07-02 | Marcado INCOMPLETO. Detección de violación de capas (71 imports directos de `db` en 13 blueprints). | implementer |
| 2026-07-02 | Corrección de Fase 3: wrappers de re-export en `app/domain/*`, test AST `test_arquitectura.py`, eliminación de `db.py` raíz. | implementer |
| 2026-07-02 | **Esta revisión** (v2): reescritura integral del plan con DoD verificable, plan de Fase 4e accionable, plan de Fase 7 con tests de integración por blueprint, decisión pendiente sobre `middleware.py`, riesgos del cierre, handoffs a subagentes. | documenter |

---

## Relacionado

- `[[ADR-0001-modularizacion-monolito-flask]]` — Decisión formal origen de este plan.
- `[[ADR-0002-sync-observable-y-backups]]` — Sync automática + backups portables
  (introdujo `/api/backup/descargar` y `/api/scheduler/estado`, ya integrados).
- `[[ARQUITECTURA]]` — Roadmap de fases 0-8 con criterios de aceptación detallados.
- `[[API]]` — Inventario de las 82 rutas, agrupadas por Blueprint.
- `[[AUTENTICACION]]` — Auth, CSRF, RBAC, decoradores (todos migrados a `app/domain/`).
- `docs/OPERATIONS.md` — (por crear en Fase 8) Runbook de deploy + rollback.
- `tests/unit/test_arquitectura.py` — Test AST que hace cumplir la regla de capas.
- `tests/conftest.py` — Fixtures compartidos y skip automático de integration.
