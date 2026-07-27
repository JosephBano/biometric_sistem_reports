---
title: "ADR-0001 — Modularización del monolito Flask en Application Factory + Blueprints por dominio"
tags: [adr, arquitectura, flask, refactor]
status: accepted
created: 2026-07-01
updated: 2026-07-01
deciders: [arquitecto, equipo ISTPET]
consulted: [docs/ER.md, docs/SUPERADMIN.md, README.md, .env.example]
supersedes: []
superseded_by: []
related: ["[[ARQUITECTURA]]", "[[ADR-0000-use-markdown-for-adrs]]", "[[AUTENTICACION]]", "[[API]]"]
---

# ADR 0001 — Modularización del monolito Flask en Application Factory + Blueprints por dominio

- **Status**: proposed
- **Date**: 2026-07-01
- **Deciders**: @architect, equipo ISTPET
- **Consulted**: docs/ER.md, docs/SUPERADMIN.md, README.md, .env.example

> **Nota del documenter**: este ADR es copia del bloque propuesto por `@architect` en su propuesta arquitectónica (sección 7). Las secciones finales ("Relacionado" y el frontmatter YAML Obsidian-compatible) fueron añadidas por `@documenter`. **Revisión 2026-07-01**: se corrigieron dos afirmaciones inexactas (SQLite no es viable para tests; Alembic no corre en el deploy actual) y se añadió el follow-up P1 de la Fase −1 tras la revisión de viabilidad.

## Context and Problem Statement

El repositorio `biometric_sistem_reports` es una aplicación web Flask 3 (Python 3.12) de gestión de asistencia
biométrica multi-tenant. El crecimiento orgánico a través de 7 fases ha producido un único punto de entrada
(`app.py`) de **2 512 líneas** que contiene:

- 81 rutas registradas con `@app.route`
- 61 decoradores `@require_role` / `@require_tipo_persona`
- Validación CSRF custom
- Middleware de autenticación y carga de contexto de tenant
- Helpers de generación de reportes PDF/DOCX
- Configuración de Flask (secret_key, proxy_fix, dispatcher, rate limiting)

Acompañan al monolito módulos top-level (`script.py` 2 281 líneas, `analytics.py`, `sync.py`, `horarios.py`,
`ia_report.py`, `script_docx.py`, `auth.py`, `decorators.py`, `email_utils.py`, `middleware.py`) que conviven con
la app web sin un contrato claro entre "servicio de dominio" y "ruta HTTP". La capa de datos sí está
adecuadamente organizada en `db/queries/*.py` (15 módulos por dominio, SQLAlchemy Core + `text()` parametrizado)
y los drivers de dispositivos siguen el patrón Strategy/Factory en `drivers/`. **Esos dos paquetes no se tocan.**

El problema concreto:

1. **Riesgo de regresión por merge**: cualquier modificación colisiona con las 2 512 líneas de `app.py`.
2. **Imposibilidad de tests aislados**: sin factory, no se puede instanciar la app con configuración `test`
   sin levantar todo el entorno.
3. **Acoplamiento vertical en `before_request`** (líneas 156-227): mezcla endpoints públicos, sesión, CSRF,
   carga de tenant y tipos de persona en un solo bloque.
4. **`auth.py` usa imports locales** dentro de cada función (líneas 94, 116, 131, 147, 153, 159) — un
   anti-patrón nacido del miedo a ciclos de import que la modularización elimina.
5. **`middleware.py` (206 líneas) es un servidor FastAPI/uvicorn** que no se importa desde `app.py` y vive
   en la raíz del repo por error histórico.
6. **Las fases (Fase 2, 4, 5, 6, 7) ya están documentadas como comentarios** dentro de `app.py`. La
   modularización formaliza esa estructura implícita.

## Decision Drivers

- **D1 — Mantenibilidad**: nuevo dev debe leer <500 líneas para tocar un dominio.
- **D2 — Testabilidad**: cada dominio debe tener al menos 1 test unitario + 1 test de integración.
- **D3 — Riesgo de regresión mínimo**: rollout por fases, cada fase reversible.
- **D4 — Compatibilidad con deploy actual**: `gunicorn --workers 1 --threads 4` debe seguir funcionando sin
   cambios de Docker en v1.
- **D5 — No migrar de framework**: el stack Flask sigue siendo válido para el tamaño del proyecto.
- **D6 — Respetar lo que ya funciona**: `db/queries/*` y `drivers/*` no se tocan.

## Considered Options

### Opción A — Solo Blueprints Flask por dominio (mínima invasiva)
Cada dominio vive en `app/<dominio>/routes.py`. `app.py` se mantiene como entrypoint global.

- ✅ Cambio pequeño, fácil de revertir.
- ❌ No habilita tests aislados ni configuración por entorno.
- ❌ `app.py` sigue siendo un módulo "Dios" con configuración, errores y CSRF.

### Opción B — Application Factory + Blueprints por dominio + servicios en `app/domain/*`
`create_app(config_name)` registra blueprints; los servicios de dominio viven en `app/domain/` sin
depender de Flask en casos donde es posible.

- ✅ Tests aislados: `create_app("testing")` contra un PostgreSQL de test efímero (Docker/testcontainers). *(SQLite no es viable: el SQL usa schemas por tenant, `SET search_path`, `DO $$` y `ON CONFLICT`.)*
- ✅ Configuración por entorno (Dev/Prod/Test).
- ✅ CLI `flask` reutilizable (`flask --app wsgi db init`).
- ✅ Cada sub-fase es ~½ día y se commitea por separado.
- ❌ 1.5 semanas de trabajo vs 1 semana de A.
- ❌ Requiere desactivar imports top-level de `script`, `analytics`, etc. en `app.py` y moverlos a `init_app`.

### Opción C — Migración parcial a FastAPI / Quart
Migrar las rutas API (`/api/*`) a FastAPI manteniendo Flask para HTML.

- ✅ Async nativo en endpoints pesados (sync de dispositivos).
- ❌ 3-4 semanas de reescritura vs 1.5 de B.
- ❌ Riesgo alto de regresión en lógica de auth/CSRF/multi-tenant.
- ❌ Stack mixto Flask+FastAPI añade complejidad operacional.
- ❌ **Ya existe un intento fallido**: `middleware.py` (FastAPI) convive sin integrarse.
- ❌ No resuelve ningún dolor inmediato.

### Opción D (rechazada de plano) — Reescribir todo en Django

- ❌ Reescritura completa, cambio de ORM, pérdida de toda la inversión en SQLAlchemy Core.

## Decision Outcome

**Se adopta la Opción B — Application Factory + Blueprints por dominio + servicios en `app/domain/*`**.

Es la única opción que cumple D1, D2 y D4 sin disparar D3. La B es estrictamente incremental: cada sub-fase
(Fase 3a-3i del roadmap) es un PR pequeño y reversible.

### Consequences

**Positivas**

- `app.py` desaparece de la raíz. `wsgi.py` lo reemplaza.
- `grep -rn "@app.route" app/web` da una visión completa del routing en 1 comando.
- Tests por dominio: `tests/unit/test_rbac.py`, `tests/unit/test_reports.py`, etc.
- `create_app("testing")` permite CI contra un Postgres efímero, con salvaguarda: `TestConfig` rechaza `DATABASE_URL` que no sea de test y no ejecuta `init_db()` ni el scheduler implícitamente.
- Cada servicio de dominio es mockeable sin Flask context: `from app.domain.reports import analizar_dia` en REPL.
- El scheduler (`schedule.py`) se conecta al ciclo de vida de Flask vía `init_app(app)` en lugar de arrancar
   como side-effect de import.

**Negativas**

- Deuda temporal: shim `app.py → wsgi.py` durante 1 release. El `Dockerfile` se actualiza a `wsgi:app`.
- Aumento de archivos en repo: de ~25 .py top-level a ~45 .py bajo `app/`. Aceptable.
- Los decoradores `require_role` cambian su punto de importación: de `from decorators import` a
   `from app.domain.rbac import`. Cambio mecánico pero ruidoso en el primer PR.
- `tests/` introduce ~5 archivos y pytest como dev-dep nueva.

**Neutrales**

- `db/queries/*` permanece intacto. El ADR no introduce Repository pattern ni ORM declarativo.
- `drivers/*` permanece intacto.
- Alembic no se toca **por este ADR**, pero queda registrada la deuda: `db/init.py::init_db()` ejecuta DDL propio en cada arranque y las migraciones Alembic no se ejecutan en el deploy (dos fuentes de verdad). Se consolida en la Fase −1 del roadmap de [[ARQUITECTURA]] antes de iniciar el refactor.
- Multi-tenant por schema con `SET search_path` por conexión: el patrón `g.tenant_schema` se mantiene. Solo
   cambia el **lugar** donde se setea `g` (ahora en `app/tenant.py` registrado como `before_request` en factory).

## Implementation Plan

Ver roadmap en respuesta de `@architect` (Fase 0 a Fase 8). Cada fase termina con un commit + smoke test
manual. Reversión = revert del último PR.

## Validation

- `gunicorn wsgi:app` arranca idéntico al actual.
- `pytest -q` pasa con cobertura mínima 60% al cierre de Fase 4.
- Smoke test manual: login → dashboard → generar reporte PDF → sync dispositivo → ver justificaciones → crear
   periodo → historico persona.

## Follow-ups (backlog)

- **P1 (bloqueante, Fase −1)**: consolidar migraciones en Alembic como única fuente de verdad (`init_db` solo seed, `alembic upgrade head` como paso de deploy), backups con restore probado y custodia de `DB_ENCRYPTION_KEY`/`FLASK_SECRET_KEY`. Ver roadmap en [[ARQUITECTURA]].
- **P2**: migrar CSRF custom a Flask-WTF.
- **P2**: extraer `middleware.py` huérfano a `services/biometric_proxy/` con su propio Dockerfile o eliminarlo.
- **P3**: cuando el equipo crezca, evaluar Celery + multi-worker (Fase 6 del roadmap).
- **P3**: Repository pattern solo si se introduce ORM declarativo.

## Relacionado

- [[ADR-0000-use-markdown-for-adrs]] — Plantilla MADR usada para escribir este ADR.
- [[ARQUITECTURA]] — Documento principal de arquitectura, contiene el árbol de carpetas y el mapa de Blueprints derivados de esta decisión.
- [[AUTENTICACION]] — El sistema de autenticación (sesión, CSRF, RBAC, decoradores) que se reorganiza según este ADR.
- [[API]] — Inventario de las 81 rutas afectadas, agrupadas por Blueprint destino.
