# Sync automática confiable + Backups portables — Plan de Implementación

> **Para implementadores:** Plan ejecuta tarea por tarea. Checkboxes (`- [ ]`) marcan progreso. TDD donde aplique. Commits frecuentes.

**Goal:** Eliminar la dependencia del operador para sincronizar, hacer observables todas las corridas del scheduler, y entregar backups portables (descarga `pg_dump` + backup diario automático) sin cambiar la arquitectura existente.

**Architecture:** Reforzar in-place el scheduler `schedule` in-process + 1 worker gunicorn (ADR-0001). Sin cron del SO, sin Celery. Persistencia nueva en `public.scheduler_runs` (tabla global cross-tenant). Backups vía `pg_dump -Fc` ejecutado por subprocess con `PGPASSWORD` por env.

**Tech Stack:** Python 3.12 · Flask 3 (App Factory) · SQLAlchemy 2 (Core/text) · Alembic · `schedule` (in-process) · PostgreSQL 16 · Bootstrap 5.3 + plain JS · `pytest`.

---

## File Structure (mapa de cambios)

```
biometric_sistem_reports/
├── db/
│   ├── migrations/versions/
│   │   └── 0009_scheduler_runs.py            # CREATE: public.scheduler_runs + índices
│   └── queries/
│       └── scheduler_runs.py                 # NUEVO: registrar_run / listar_ultimos / purgar_mayor_a
├── app/
│   ├── web/
│   │   ├── reports_bp.py                     # MOD: implementar /api/backup/descargar (pg_dump)
│   │   └── system_bp.py                      # MOD: añadir GET /api/scheduler/estado
│   ├── config.py                             # MOD: BACKUP_AUTO/HORA/DIR/RETENCION_DIAS
│   └── __init__.py                           # SIN CAMBIOS (create_app no toca backup)
├── templates/
│   └── configuracion.html                    # MOD: 3er tab "Sincronización" + estados backup
├── static/js/
│   └── configuracion.js                      # MOD: fetch /api/scheduler/estado + render card
├── sync.py                                   # MOD: logger + _run() inkillable + registrar_run
├── backup.py                                 # NUEVO: generar_dump() + purgar_backups_viejos()
├── Dockerfile                                # MOD: añadir postgresql-client-16
├── docker-compose.yml                        # MOD: volumen /data/backups (parte de app_data)
├── .env.example                              # MOD: BACKUP_* + comentario DB_ENCRYPTION_KEY
├── docs/
│   ├── ARQUITECTURA.md                       # MOD: sección "Operación: sync y backups"
│   ├── API.md                                # MOD: rutas nuevas/cambiadas
│   └── adr/
│       └── 0002-sync-observable-y-backups.md # NUEVO: ADR corto
└── tests/
    └── unit/
        ├── test_scheduler_runs.py            # NUEVO: TDD del módulo db/queries
        ├── test_backup.py                    # NUEVO: TDD del módulo backup.py
        ├── test_sync_logging.py              # NUEVO: TDD del logger + _run() inkillable
        └── test_scheduler_estado.py          # NUEVO: TDD endpoint /api/scheduler/estado
```

---

## Convenciones del plan

- **Tareas pequeñas** (2-5 min cada paso). Si una tarea > 30 min, partirla.
- **TDD obligatorio** para todo módulo nuevo o comportamiento nuevo en código existente.
- **Migración Alembic** se valida con `alembic check` antes de commit.
- **Cada tarea cierra con un commit.** Mensajes en español (estilo repo) o inglés (estándar).
- **Sin emojis en código ni commits** salvo que el usuario los pida.

---

# PARTE 1 — Sync automática confiable

## Tarea 1.1: Crear migración Alembic 0009 (DDL puro)

**Files:**
- Create: `db/migrations/versions/0009_scheduler_runs.py`

- [ ] **Paso 1: Escribir la migración**

```python
"""Scheduler runs observability (Fase 1 — Sync automática confiable).

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-02

Crea la tabla `public.scheduler_runs` para persistir el resultado de cada
corrida del scheduler (sync nocturna, sync incremental, backup diario).
Aditiva, idempotente, sin impacto en datos existentes.

Nota: `env.py` aplica esta migración primero en `public` y luego en cada
tenant (con search_path ajustado). El prefijo `public.` la hace portable.
"""

from alembic import op
from sqlalchemy import text

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS public.scheduler_runs (
            id              BIGSERIAL   PRIMARY KEY,
            job             TEXT        NOT NULL,
            tenant_slug     TEXT,
            inicio          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            fin             TIMESTAMPTZ,
            ok              BOOLEAN     NOT NULL,
            descargados     INTEGER,
            insertados      INTEGER,
            detalle         TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job_inicio
            ON public.scheduler_runs (job, inicio DESC);

        CREATE INDEX IF NOT EXISTS idx_scheduler_runs_tenant_inicio
            ON public.scheduler_runs (tenant_slug, inicio DESC)
            WHERE tenant_slug IS NOT NULL;
    """))


def downgrade() -> None:
    """
    PELIGROSO: elimina historial de corridas del scheduler.
    Solo para entornos de desarrollo.
    """
    confirm = os.environ.get("ALEMBIC_ALLOW_DOWNGRADE_0009", "false")
    if confirm.lower() != "true":
        raise RuntimeError(
            "Downgrade de 0009 deshabilitado por seguridad. "
            "Setea ALEMBIC_ALLOW_DOWNGRADE_0009=true para confirmar."
        )
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS public.scheduler_runs CASCADE"))
```

Añadir al inicio del archivo (después del docstring de cabecera):

```python
import os
from typing import Sequence, Union
```

- [ ] **Paso 2: Validar la cadena de migraciones**

Run: `python -c "from db.migrations.versions import _dummy_import_helper  # noqa" && alembic heads`
Expected: muestra `0009 (head)`.

Si no existe el comando, ejecutar `alembic history` y verificar que 0008 → 0009 es la cadena.

- [ ] **Paso 3: Verificar que `alembic upgrade head` corre en local sin errores**

Run: `alembic upgrade head`
Expected: termina con "Running upgrade 0008 -> 0009, ...".

Si no hay BD local, **al menos** validar la sintaxis con:
```bash
python -c "import ast; ast.parse(open('db/migrations/versions/0009_scheduler_runs.py').read()); print('OK')"
```

- [ ] **Paso 4: Commit**

```bash
git add db/migrations/versions/0009_scheduler_runs.py
git commit -m "feat(db): migración 0009 — tabla public.scheduler_runs"
```

---

## Tarea 1.2: Helper `db/queries/scheduler_runs.py` (TDD)

**Files:**
- Create: `db/queries/scheduler_runs.py`
- Create: `tests/unit/test_scheduler_runs.py`
- Modify: `db/__init__.py` (re-exportar funciones nuevas)

- [ ] **Paso 1: Escribir test RED — registrar_run**

`tests/unit/test_scheduler_runs.py`:

```python
"""
Tests del helper `db.queries.scheduler_runs` (TDD).

Mockeamos `db.connection.get_engine()` para no tocar BD real.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from db.queries import scheduler_runs


class TestRegistrarRun:

    def test_registrar_run_exitoso_inserta_fila(self):
        """Una corrida ok=true debe ejecutar INSERT con todos los campos."""
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.connect.return_value.__exit__ = lambda self, *args: None

        with patch("db.connection.get_engine", return_value=mock_engine):
            scheduler_runs.registrar_run(
                job="sync_incremental",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=42,
                insertados=37,
                detalle=None,
            )

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        # El primer argumento posicional es la sentencia SQL (text object)
        sql = mock_conn.execute.call_args[0][0]
        params = mock_conn.execute.call_args[0][1]
        assert "INSERT INTO public.scheduler_runs" in str(sql)
        assert params["job"] == "sync_incremental"
        assert params["tenant_slug"] == "istpet"
        assert params["ok"] is True
        assert params["descargados"] == 42
        assert params["insertados"] == 37

    def test_registrar_run_error_guarda_detalle_y_ok_false(self):
        """Fallo: ok=False, detalle con mensaje de error, contadores NULL."""
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.connect.return_value.__exit__ = lambda self, *args: None

        with patch("db.connection.get_engine", return_value=mock_engine):
            scheduler_runs.registrar_run(
                job="sync_nocturna",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 2, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 2, 1, tzinfo=timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle="Timeout connecting to dispositivo 3",
            )

        params = mock_conn.execute.call_args[0][1]
        assert params["ok"] is False
        assert params["descargados"] is None
        assert params["insertados"] is None
        assert "Timeout" in params["detalle"]

    def test_registrar_run_backup_diario_tenant_slug_null(self):
        """Job global (backup_diario) lleva tenant_slug=None."""
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.connect.return_value.__exit__ = lambda self, *args: None

        with patch("db.connection.get_engine", return_value=mock_engine):
            scheduler_runs.registrar_run(
                job="backup_diario",
                tenant_slug=None,
                inicio=datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 3, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=None,
                insertados=None,
                detalle="/data/backups/backup_completo_20260702_0300.dump (124 MB)",
            )

        params = mock_conn.execute.call_args[0][1]
        assert params["job"] == "backup_diario"
        assert params["tenant_slug"] is None
        assert params["detalle"].startswith("/data/backups/")


class TestListarUltimosRuns:

    def test_listar_ultimos_devuelve_dicts_con_campos_esperados(self):
        """Cada fila viene como dict con id, job, tenant_slug, ok, etc."""
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": 1,
            "job": "sync_incremental",
            "tenant_slug": "istpet",
            "inicio": datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
            "fin": datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
            "ok": True,
            "descargados": 10,
            "insertados": 8,
            "detalle": None,
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.connect.return_value.__exit__ = lambda self, *args: None

        with patch("db.connection.get_engine", return_value=mock_engine):
            resultado = scheduler_runs.listar_ultimos(limit=10)

        assert len(resultado) == 1
        fila = resultado[0]
        assert fila["job"] == "sync_incremental"
        assert fila["tenant_slug"] == "istpet"
        assert fila["ok"] is True
        assert fila["descargados"] == 10


class TestPurgarMayorA:

    def test_purgar_borra_filas_viejas_y_devuelve_conteo(self):
        """DELETE con WHERE inicio < NOW() - INTERVAL ... y retorna rowcount."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 7
        mock_conn.execute.return_value = mock_result

        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.connect.return_value.__exit__ = lambda self, *args: None

        with patch("db.connection.get_engine", return_value=mock_engine):
            borradas = scheduler_runs.purgar_mayor_a(dias=90)

        assert borradas == 7
        mock_conn.commit.assert_called_once()
        # Verificar que el SQL incluye el INTERVAL
        sql = mock_conn.execute.call_args[0][0]
        assert "DELETE FROM public.scheduler_runs" in str(sql)
        assert "90" in str(sql)
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_scheduler_runs.py -v`
Expected: ImportError `cannot import name 'scheduler_runs' from 'db.queries'`.

- [ ] **Paso 3: Implementar el módulo `db/queries/scheduler_runs.py`**

```python
"""
Persistencia del historial de corridas del scheduler (`db.queries.scheduler_runs`).

Tabla objetivo (migración 0009): `public.scheduler_runs`.
Cada corrida del scheduler (sync nocturna, sync incremental, backup diario) deja
una fila con inicio, fin, ok, contadores y detalle.

Esta capa NUNCA importa de `app/*` ni de Flask (regla ADR-0001).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from db.connection import get_engine


def registrar_run(
    job: str,
    tenant_slug: Optional[str],
    inicio: datetime,
    fin: datetime,
    ok: bool,
    descargados: Optional[int],
    insertados: Optional[int],
    detalle: Optional[str],
) -> None:
    """
    Inserta una fila en `public.scheduler_runs`.

    Args:
        job: identificador del job (`sync_nocturna`, `sync_incremental`,
            `backup_diario`, etc.).
        tenant_slug: schema del tenant procesado, o None para jobs globales
            (ej. backup_diario).
        inicio: timestamp de inicio de la corrida.
        fin: timestamp de fin de la corrida.
        ok: True si la corrida fue exitosa.
        descargados: registros descargados del dispositivo (None para backup).
        insertados: registros nuevos insertados en la BD (None para backup).
        detalle: mensaje de error o ruta del archivo generado.
    """
    sql = text("""
        INSERT INTO public.scheduler_runs
            (job, tenant_slug, inicio, fin, ok, descargados, insertados, detalle)
        VALUES
            (:job, :tenant_slug, :inicio, :fin, :ok,
             :descargados, :insertados, :detalle)
    """)
    params = {
        "job": job,
        "tenant_slug": tenant_slug,
        "inicio": inicio,
        "fin": fin,
        "ok": ok,
        "descargados": descargados,
        "insertados": insertados,
        "detalle": detalle,
    }
    with get_engine().connect() as conn:
        conn.execute(sql, params)
        conn.commit()


def listar_ultimos(limit: int = 10) -> list[dict]:
    """
    Retorna las últimas `limit` corridas del scheduler (cualquier job),
    ordenadas por inicio DESC.
    """
    sql = text("""
        SELECT id, job, tenant_slug, inicio, fin, ok,
               descargados, insertados, detalle
        FROM public.scheduler_runs
        ORDER BY inicio DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]


def purgar_mayor_a(dias: int = 90) -> int:
    """
    Borra corridas con `inicio` más antiguo que `NOW() - INTERVAL '... dias'`.

    Retorna el número de filas borradas.
    """
    sql = text(f"""
        DELETE FROM public.scheduler_runs
        WHERE inicio < NOW() - INTERVAL '{int(dias)} days'
    """)
    with get_engine().connect() as conn:
        result = conn.execute(sql)
        conn.commit()
        return result.rowcount or 0
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_scheduler_runs.py -v`
Expected: PASS los 5 tests.

- [ ] **Paso 5: Re-exportar en `db/__init__.py`**

Añadir bloque después de `from db.queries.sync_log import ...`:

```python
# ── Scheduler runs (Fase 1 — Sync observable) ──────────────────────────────
from db.queries.scheduler_runs import (
    registrar_run,
    listar_ultimos,
    purgar_mayor_a,
)
```

Y añadir `"registrar_run", "listar_ultimos", "purgar_mayor_a"` al `__all__`.

- [ ] **Paso 6: Verificar que `tests/unit/test_schedule.py` sigue pasando**

Run: `pytest tests/unit/test_schedule.py -v`
Expected: PASS los 4 tests existentes (no rompemos el wrapper).

- [ ] **Paso 7: Commit**

```bash
git add db/queries/scheduler_runs.py db/__init__.py tests/unit/test_scheduler_runs.py
git commit -m "feat(db): helper db.queries.scheduler_runs + tests TDD"
```

---

## Tarea 1.3: Logger + helper de registro en `sync.py` (TDD)

**Files:**
- Modify: `sync.py`
- Create: `tests/unit/test_sync_logging.py`

- [ ] **Paso 1: Escribir test RED — sync.py emite logs al iniciar**

`tests/unit/test_sync_logging.py`:

```python
"""
Tests del logger y registro de corridas en `sync.py`.

Mockeamos el engine y los helpers para no tocar BD ni dispositivos reales.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestLoggerSync:

    def test_sync_module_tiene_logger_named_after_module(self, caplog):
        """El módulo sync debe exponer un logger con nombre 'sync'."""
        import sync
        # Disparar algo que loguee
        with caplog.at_level(logging.INFO, logger="sync"):
            sync._log_scheduler_estado()  # se crea en paso 3
        assert any("sync" in r.name for r in caplog.records) or caplog.records

    def test_iniciar_scheduler_con_sync_auto_false_loggea_inactivo(self, caplog):
        """Si SYNC_AUTO=false (entorno test), loguear 'Scheduler INACTIVO'."""
        import sync

        with caplog.at_level(logging.INFO, logger="sync"):
            # Forzar SYNC_AUTO=False en runtime para el test
            with patch.object(sync, "SYNC_AUTO", False):
                sync.iniciar_scheduler()

        assert any(
            "INACTIVO" in r.getMessage() or "INACTIVO" in r.message
            for r in caplog.records
        ), f"Esperaba log 'INACTIVO'; recibí: {[r.message for r in caplog.records]}"


class TestRegistrarCorridaSync:

    def test_registrar_corrida_llama_db_registrar_run(self):
        """_registrar_corrida_sync debe invocar db.queries.scheduler_runs.registrar_run."""
        import sync
        from db.queries import scheduler_runs

        with patch.object(scheduler_runs, "registrar_run") as mock_reg:
            sync._registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=10,
                insertados=8,
                detalle=None,
            )

        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        assert kwargs["job"] == "sync_incremental"
        assert kwargs["ok"] is True

    def test_registrar_corrida_no_propaga_excepciones(self):
        """Si db.queries.scheduler_runs falla, NO debe matar el scheduler."""
        import sync
        from db.queries import scheduler_runs

        with patch.object(
            scheduler_runs, "registrar_run", side_effect=RuntimeError("BD caída")
        ):
            # No debe lanzar
            sync._registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=10,
                insertados=8,
                detalle=None,
            )
        # OK si llegamos aquí
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_sync_logging.py -v`
Expected: ImportError o AttributeError (`_log_scheduler_estado` o `_registrar_corrida_sync` no existen).

- [ ] **Paso 3: Modificar `sync.py` — añadir logger y helper**

En `sync.py`, después de la línea 24 (cierre del `try: import schedule`), añadir:

```python
import logging

log = logging.getLogger(__name__)  # nombre: "sync"
```

Reemplazar la función `iniciar_scheduler()` (líneas 287-305) por:

```python
_scheduler_started = False  # guard singleton


def iniciar_scheduler():
    """Inicia el scheduler en un hilo daemon si SYNC_AUTO=true.

    Loguea siempre su estado al arrancar (ACTIVO/INACTIVO) para que el operador
    sepa sin tener que mirar procesos.
    """
    global _scheduler_started

    if not SYNC_AUTO or not SCHEDULE_DISPONIBLE:
        log.info("Scheduler INACTIVO (SYNC_AUTO=false o schedule no disponible)")
        return

    if _scheduler_started:
        log.warning("Scheduler ya estaba iniciado; se ignora segunda llamada")
        return

    # Sync nocturna
    schedule.every().day.at(SYNC_HORA_NOCTURNA).do(_sync_nocturna_completa)

    # Sync incremental
    schedule.every(SYNC_INTERVALO_HORAS).hours.do(_sync_automatico)

    def _run():
        # Loop inkillable: cualquier excepción en una corrida NO mata el hilo.
        while True:
            try:
                schedule.run_pending()
            except Exception:
                log.exception("scheduler loop falló; continuando")
            time_module.sleep(60)

    threading.Thread(
        target=_run, daemon=True, name="biometrico-scheduler"
    ).start()
    _scheduler_started = True

    log.info(
        "Scheduler ACTIVO: nocturna %s, incremental cada %sh",
        SYNC_HORA_NOCTURNA, SYNC_INTERVALO_HORAS,
    )


def _log_scheduler_estado():
    """Helper para tests: emite un log INFO con el estado actual."""
    log.info(
        "Scheduler: ACTIVO=%s, hora_nocturna=%s, intervalo=%sh",
        SYNC_AUTO, SYNC_HORA_NOCTURNA, SYNC_INTERVALO_HORAS,
    )
```

Reemplazar `_sync_automatico()` (líneas 260-271) por:

```python
def _sync_automatico():
    """Ejecutado por schedule (incremental) — itera todos los tenants activos."""
    log.info("Iniciando sync incremental (scheduler)")
    for slug in _get_tenant_slugs():
        db_module.set_thread_tenant(slug)
        inicio = datetime.now(timezone.utc)
        try:
            descargados, insertados = sincronizar(force_historico=False)
            from db.queries.periodos import cerrar_periodos_vencidos
            cerrar_periodos_vencidos()
            _registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=True,
                descargados=descargados,
                insertados=insertados,
                detalle=None,
            )
        except Exception as e:
            log.exception("sync_incremental falló para tenant=%s", slug)
            _registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle=str(e)[:500],
            )
        finally:
            db_module.clear_thread_tenant()
```

Reemplazar `_sync_nocturna_completa()` (líneas 274-284) por:

```python
def _sync_nocturna_completa():
    """Ejecutado a SYNC_HORA_NOCTURNA — itera todos los tenants activos."""
    log.info("Iniciando sync nocturna completa (scheduler)")
    treinta_dias_atras = date.today() - timedelta(days=30)
    for slug in _get_tenant_slugs():
        db_module.set_thread_tenant(slug)
        inicio = datetime.now(timezone.utc)
        try:
            descargados, insertados = sincronizar(
                fecha_inicio=treinta_dias_atras, force_historico=True
            )
            _registrar_corrida_sync(
                job="sync_nocturna",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=True,
                descargados=descargados,
                insertados=insertados,
                detalle=None,
            )
        except Exception as e:
            log.exception("sync_nocturna falló para tenant=%s", slug)
            _registrar_corrida_sync(
                job="sync_nocturna",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle=str(e)[:500],
            )
        finally:
            db_module.clear_thread_tenant()

    # Retención de scheduler_runs: borrar filas > 90 días.
    try:
        from db.queries import scheduler_runs
        borradas = scheduler_runs.purgar_mayor_a(dias=90)
        if borradas:
            log.info("scheduler_runs: purgadas %s filas > 90 días", borradas)
    except Exception:
        log.exception("scheduler_runs purga falló (no crítico)")
```

Y añadir al final del módulo (antes de `iniciar_scheduler`):

```python
def _registrar_corrida_sync(
    job: str,
    tenant_slug: str | None,
    inicio: datetime,
    fin: datetime,
    ok: bool,
    descargados: int | None,
    insertados: int | None,
    detalle: str | None,
) -> None:
    """Wrapper que no propaga excepciones del helper de persistencia.

    Si la BD está caída durante una corrida, el scheduler NO debe morir.
    """
    try:
        from db.queries import scheduler_runs
        scheduler_runs.registrar_run(
            job=job,
            tenant_slug=tenant_slug,
            inicio=inicio,
            fin=fin,
            ok=ok,
            descargados=descargados,
            insertados=insertados,
            detalle=detalle,
        )
    except Exception:
        log.exception("No se pudo registrar corrida del scheduler en BD (job=%s)", job)
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_sync_logging.py -v`
Expected: PASS los 4 tests.

- [ ] **Paso 5: Verificar que los tests existentes siguen pasando**

Run: `pytest tests/unit/test_schedule.py -v`
Expected: PASS los 4 tests (la firma de `iniciar_scheduler` no cambió).

- [ ] **Paso 6: Commit**

```bash
git add sync.py tests/unit/test_sync_logging.py
git commit -m "feat(sync): logger + helper registrar corrida + _run() inkillable"
```

---

## Tarea 1.4: Endpoint `GET /api/scheduler/estado` (TDD)

**Files:**
- Modify: `app/web/system_bp.py`
- Create: `tests/unit/test_scheduler_estado.py`

- [ ] **Paso 1: Escribir test RED**

`tests/unit/test_scheduler_estado.py`:

```python
"""
Tests del endpoint GET /api/scheduler/estado (`app.web.system_bp`).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


class TestSchedulerEstado:

    def test_endpoint_requiere_autenticacion(self, client):
        """Sin sesión → 401 (JSON)."""
        resp = client.get("/api/scheduler/estado")
        assert resp.status_code == 401
        assert resp.is_json

    def test_endpoint_requiere_rol_admin_o_superior(self, client):
        """Sesión sin rol suficiente → 403."""
        with client.session_transaction() as sess:
            sess["usuario_id"] = "u"
            sess["tenant_schema"] = "istpet"
            sess["tenant_id"] = "t"
            sess["nombre"] = "user"
            sess["roles"] = ["readonly"]  # NO es admin
            sess["csrf_token"] = "x"
        resp = client.get("/api/scheduler/estado")
        assert resp.status_code == 403

    def test_endpoint_admin_devuelve_json_con_campos_esperados(self, admin_session):
        """admin → 200 + JSON con sync_activo, hora_nocturna, ultimas_corridas, etc."""
        with patch("db.queries.scheduler_runs.listar_ultimos", return_value=[]):
            resp = admin_session.get("/api/scheduler/estado")

        assert resp.status_code == 200
        data = resp.get_json()
        assert "sync_activo" in data
        assert "sync_hora_nocturna" in data
        assert "sync_intervalo_horas" in data
        assert "ultimas_corridas" in data
        assert isinstance(data["ultimas_corridas"], list)

    def test_endpoint_incluye_corridas_en_ultimas_corridas(self, admin_session):
        """Si hay corridas en BD, deben venir en el JSON."""
        corrida_mock = {
            "id": 1,
            "job": "sync_incremental",
            "tenant_slug": "istpet",
            "inicio": "2026-07-02T10:00:00+00:00",
            "fin": "2026-07-02T10:05:00+00:00",
            "ok": True,
            "descargados": 10,
            "insertados": 8,
            "detalle": None,
        }
        with patch(
            "db.queries.scheduler_runs.listar_ultimos",
            return_value=[corrida_mock],
        ):
            resp = admin_session.get("/api/scheduler/estado")

        data = resp.get_json()
        assert len(data["ultimas_corridas"]) == 1
        assert data["ultimas_corridas"][0]["job"] == "sync_incremental"
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_scheduler_estado.py -v`
Expected: 404 (la ruta no existe todavía).

- [ ] **Paso 3: Añadir el endpoint en `app/web/system_bp.py`**

Después de la importación existente de `require_role`, añadir:

```python
import os
```

(Si ya está importado `os`, saltarse.)

Al final del archivo (después de `importar_historicos`), añadir:

```python
@bp.get("/api/scheduler/estado")
@require_role("superadmin", "admin")
def scheduler_estado():
    """
    Devuelve el estado actual del scheduler y las últimas 10 corridas.

    Útil para la card 'Sincronización automática' en /configuracion.
    """
    from db.queries import scheduler_runs as sr_queries

    sync_activo = os.environ.get("SYNC_AUTO", "false").lower() == "true"
    hora_nocturna = os.environ.get("SYNC_HORA_NOCTURNA", "02:00")
    try:
        intervalo = int(os.environ.get("SYNC_INTERVALO_HORAS", "2"))
    except ValueError:
        intervalo = 2

    # Próxima corrida (si el scheduler está cargado): usamos `schedule` del módulo sync.
    proxima = None
    try:
        import sync as sync_module
        jobs = sync_module.schedule.get_jobs() if sync_module.SCHEDULE_DISPONIBLE else []
        proximas = [j.next_run for j in jobs if j.next_run]
        if proximas:
            proxima = min(proximas).isoformat()
    except Exception:  # noqa: BLE001
        proxima = None

    try:
        ultimas = sr_queries.listar_ultimos(limit=10)
    except Exception as e:  # noqa: BLE001
        ultimas = []
        current_app.logger.warning("scheduler_runs.listar_ultimos falló: %s", e)

    # Serializar datetimes a ISO string
    for fila in ultimas:
        for k in ("inicio", "fin"):
            v = fila.get(k)
            if hasattr(v, "isoformat"):
                fila[k] = v.isoformat()

    return jsonify({
        "sync_activo": sync_activo,
        "sync_hora_nocturna": hora_nocturna,
        "sync_intervalo_horas": intervalo,
        "proxima_corrida": proxima,
        "ultimas_corridas": ultimas,
    })
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_scheduler_estado.py -v`
Expected: PASS los 4 tests.

- [ ] **Paso 5: Verificar que no rompemos tests existentes del sistema**

Run: `pytest tests/unit/ -v`
Expected: PASS todos los tests previos.

- [ ] **Paso 6: Commit**

```bash
git add app/web/system_bp.py tests/unit/test_scheduler_estado.py
git commit -m "feat(api): GET /api/scheduler/estado para card de UI"
```

---

## Tarea 1.5: Card UI "Sincronización automática" en `/configuracion`

**Files:**
- Modify: `templates/configuracion.html`
- Modify: `static/js/configuracion.js`

(No hay test automatizado para la UI; se valida manualmente con un navegador.)

- [ ] **Paso 1: Añadir 3er tab en `templates/configuracion.html`**

En la lista `<ul class="nav nav-pills mb-4 gap-2" id="configTabs" ...>` (líneas 10-27), añadir después del botón "Respaldos y Históricos":

```html
<li class="nav-item" role="presentation">
    <button class="nav-link fw-bold px-4 py-2 custom-tab shadow-sm" id="sync-tab" data-bs-toggle="tab" data-bs-target="#sync" type="button" role="tab" aria-controls="sync" aria-selected="false">
        <span class="d-flex align-items-center gap-2">
            <span class="material-symbols-outlined fs-5">sync</span>
            Sincronización
        </span>
    </button>
</li>
```

Después del `<div class="tab-pane fade" id="mantenimiento" ...>` (línea 117), añadir antes del cierre de `tab-content`:

```html
<!-- SINCRONIZACIÓN TAB (Fase 1 — Sync observable) -->
<div class="tab-pane fade" id="sync" role="tabpanel" aria-labelledby="sync-tab">
    <div class="row g-4 p-2">
        <div class="col-12">
            <div class="card shadow-sm border-0 h-100" style="border-radius: 12px;">
                <div class="card-body p-4">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="fw-bold mb-0">Sincronización automática</h5>
                        <button class="btn btn-sm btn-outline-secondary" onclick="cargarSchedulerEstado();">
                            <span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: text-bottom;">refresh</span>
                            Actualizar
                        </button>
                    </div>
                    <p class="small text-muted mb-4">Estado del scheduler en segundo plano y últimas corridas registradas.</p>

                    <div id="sync-estado-resumen" class="row g-3 mb-4">
                        <div class="col-md-3">
                            <div class="p-3 bg-light border rounded text-center">
                                <small class="text-muted d-block">Estado</small>
                                <span id="sync-activo-badge" class="badge bg-secondary fs-6 mt-1">—</span>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="p-3 bg-light border rounded text-center">
                                <small class="text-muted d-block">Hora nocturna</small>
                                <strong id="sync-hora-nocturna" class="d-block mt-1">—</strong>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="p-3 bg-light border rounded text-center">
                                <small class="text-muted d-block">Intervalo</small>
                                <strong id="sync-intervalo" class="d-block mt-1">—</strong>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="p-3 bg-light border rounded text-center">
                                <small class="text-muted d-block">Próxima corrida</small>
                                <strong id="sync-proxima" class="d-block mt-1" style="font-size: 0.85rem;">—</strong>
                            </div>
                        </div>
                    </div>

                    <h6 class="fw-bold mb-2">Últimas 10 corridas</h6>
                    <div id="sync-corridas-tabla" class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                        <p class="text-muted small">Cargando…</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Paso 2: Añadir funciones JS en `static/js/configuracion.js`**

Verificar primero que el archivo existe. Si no, crearlo con la lógica abajo.

Añadir al final:

```javascript
// ═══════════════════════════════════════════════════════════════════
// SINCRONIZACIÓN AUTOMÁTICA — Fase 1
// ═══════════════════════════════════════════════════════════════════

async function cargarSchedulerEstado() {
    const tablaEl = document.getElementById('sync-corridas-tabla');
    const activoBadge = document.getElementById('sync-activo-badge');
    const horaEl = document.getElementById('sync-hora-nocturna');
    const intervaloEl = document.getElementById('sync-intervalo');
    const proximaEl = document.getElementById('sync-proxima');

    try {
        const resp = await fetch(API.schedulerEstado, { credentials: 'same-origin' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        // Resumen
        activoBadge.textContent = data.sync_activo ? 'ACTIVO' : 'INACTIVO';
        activoBadge.className = 'badge fs-6 mt-1 ' + (data.sync_activo ? 'bg-success' : 'bg-secondary');
        horaEl.textContent = data.sync_hora_nocturna || '—';
        intervaloEl.textContent = (data.sync_intervalo_horas || '—') + ' h';
        proximaEl.textContent = data.proxima_corrida
            ? new Date(data.proxima_corrida).toLocaleString('es-EC')
            : '—';

        // Tabla de corridas
        const corridas = data.ultimas_corridas || [];
        if (corridas.length === 0) {
            tablaEl.innerHTML = '<p class="text-muted small">Aún no hay corridas registradas. La próxima sync nocturna o incremental dejará un registro.</p>';
            return;
        }

        const rows = corridas.map(c => {
            const inicio = c.inicio ? new Date(c.inicio).toLocaleString('es-EC') : '—';
            const fin = c.fin ? new Date(c.fin).toLocaleString('es-EC') : '—';
            const okBadge = c.ok
                ? '<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25">OK</span>'
                : '<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25">ERROR</span>';
            const detalle = c.detalle ? (c.detalle.length > 80 ? c.detalle.slice(0, 77) + '…' : c.detalle) : '—';
            return `<tr>
                <td><small>${inicio}</small></td>
                <td><span class="badge bg-light text-dark">${c.job}</span></td>
                <td><small>${c.tenant_slug || '<i>global</i>'}</small></td>
                <td>${okBadge}</td>
                <td class="text-end"><small>${c.descargados ?? '—'} / ${c.insertados ?? '—'}</small></td>
                <td><small class="text-muted">${detalle}</small></td>
            </tr>`;
        }).join('');

        tablaEl.innerHTML = `<table class="table table-sm table-hover align-middle">
            <thead class="table-light">
                <tr>
                    <th>Inicio</th>
                    <th>Job</th>
                    <th>Tenant</th>
                    <th>Resultado</th>
                    <th class="text-end">Desc / Insp</th>
                    <th>Detalle</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;
    } catch (e) {
        tablaEl.innerHTML = `<div class="alert alert-danger small">Error cargando estado: ${e.message}</div>`;
    }
}
```

- [ ] **Paso 3: Añadir la ruta en `static/js/api.js` (si no existe `API.schedulerEstado`)**

Verificar con `grep`. Si no existe `schedulerEstado`, añadir al objeto `API`:

```javascript
schedulerEstado: `${_BASE}/api/scheduler/estado`,
```

- [ ] **Paso 4: Cargar estado al abrir el tab**

Añadir al final del listener que carga `configuracion.html`, o usar el evento Bootstrap:

En `static/js/configuracion.js`, al final añadir:

```javascript
document.addEventListener('DOMContentLoaded', () => {
    const syncTab = document.getElementById('sync-tab');
    if (syncTab) {
        syncTab.addEventListener('shown.bs.tab', cargarSchedulerEstado);
    }
});
```

- [ ] **Paso 5: Validación manual (no automatizable)**

Levantar la app (`gunicorn wsgi:app`), ir a `/configuracion`, click en tab "Sincronización":
- Debe mostrar "INACTIVO" si `SYNC_AUTO=false` (entorno test).
- Debe mostrar la tabla de corridas vacía si no se ha ejecutado nada.

- [ ] **Paso 6: Commit**

```bash
git add templates/configuracion.html static/js/configuracion.js static/js/api.js
git commit -m "feat(ui): card Sincronización automática en /configuracion"
```

---

## Tarea 1.6: `.env.example` — añadir nota sobre `SYNC_AUTO` y arreglar `DB_ENCRYPTION_KEY`

**Files:**
- Modify: `.env.example`

- [ ] **Paso 1: Documentar la decisión sobre `SYNC_AUTO`**

Buscar la línea `SYNC_AUTO=false` (línea 65). Reemplazar el bloque completo:

```env
# ── Sincronización automática y Backups ─────────────────────────────────────
# SYNC_AUTO=true activa el scheduler de fondo (requiere reiniciar el servidor).
# Recomendado: true en producción; las corridas se loguean y persisten en
# `public.scheduler_runs`. Ver `docs/ARQUITECTURA.md` → "Operación".
SYNC_AUTO=false
# Hora de la sync nocturna completa diaria (formato HH:MM, 24h)
SYNC_HORA_NOCTURNA=02:00
# Intervalo de la sync incremental durante el día (en horas, default: 2)
SYNC_INTERVALO_HORAS=2

# BACKUP_AUTO activa el job de pg_dump diario a BACKUP_HORA. Por defecto sigue
# el valor de SYNC_AUTO. Si el backup falla se envía email a ADMIN_EMAIL.
BACKUP_AUTO=true
# Hora del backup diario (después de la sync nocturna). Formato HH:MM.
BACKUP_HORA=03:00
# Directorio donde se guardan los dumps. En Docker es un volumen persistente
# (`app_data:/data` ya está montado).
BACKUP_DIR=/data/backups
# Retención: se conservan los dumps de los últimos N días tras un backup exitoso.
BACKUP_RETENCION_DIAS=30
```

- [ ] **Paso 2: Corregir el comentario de `DB_ENCRYPTION_KEY`**

Buscar el bloque líneas 27-29 y reemplazar:

```env
# Clave AES-256-GCM para cifrar contraseñas de dispositivos biométricos en la BD.
# (La clave Fernet del pasado sirve por ser 32 bytes base64, pero el mecanismo
# real es AES-256-GCM, no Fernet).
# Generar con: python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
DB_ENCRYPTION_KEY=generar_clave_aleatoria_con_comando_de_arriba
```

- [ ] **Paso 3: Commit**

```bash
git add .env.example
git commit -m "docs(env): sección Sync+Backups y corrección de DB_ENCRYPTION_KEY"
```

---

# PARTE 2 — Backups portables

## Tarea 2.1: Módulo `backup.py` (TDD)

**Files:**
- Create: `backup.py`
- Create: `tests/unit/test_backup.py`

- [ ] **Paso 1: Escribir test RED — `purgar_backups_viejos`**

`tests/unit/test_backup.py`:

```python
"""
Tests del módulo `backup.py` (Fase 2 — Backups portables).

Mockeamos subprocess y filesystem para no ejecutar pg_dump real.
"""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import backup as backup_module


class TestPurgarBackupsViejos:

    def test_purgar_borra_archivos_mas_viejos_que_dias(self, tmp_path):
        """Crea 3 archivos (1 viejo + 2 frescos); debe borrar solo el viejo."""
        viejo = tmp_path / "backup_20260501_0200.dump"
        viejo.write_bytes(b"x" * 100)
        # Forzar mtime viejo (100 días atrás)
        viejo_mtime = time.time() - 100 * 86400
        os.utime(viejo, (viejo_mtime, viejo_mtime))

        fresco1 = tmp_path / "backup_20260701_0200.dump"
        fresco1.write_bytes(b"x" * 100)
        fresco2 = tmp_path / "backup_20260702_0200.dump"
        fresco2.write_bytes(b"x" * 100)

        borrados = backup_module.purgar_backups_viejos(tmp_path, dias=30)

        assert borrados == 1
        assert not viejo.exists()
        assert fresco1.exists()
        assert fresco2.exists()

    def test_purgar_directorio_inexistente_devuelve_cero(self, tmp_path):
        """Si el directorio no existe, retorna 0 sin lanzar."""
        inxistente = tmp_path / "no_existe"
        borrados = backup_module.purgar_backups_viejos(inxistente, dias=30)
        assert borrados == 0

    def test_purgar_no_borra_archivos_no_dump(self, tmp_path):
        """Solo borra archivos .dump (no .log, .tmp, etc.)."""
        viejo_log = tmp_path / "viejo.log"
        viejo_log.write_text("log")
        viejo_mtime = time.time() - 100 * 86400
        os.utime(viejo_log, (viejo_mtime, viejo_mtime))

        fresco_dump = tmp_path / "fresco.dump"
        fresco_dump.write_bytes(b"x")

        # .dump con mtime viejo
        viejo_dump = tmp_path / "viejo.dump"
        viejo_dump.write_bytes(b"x")
        os.utime(viejo_dump, (viejo_mtime, viejo_mtime))

        borrados = backup_module.purgar_backups_viejos(tmp_path, dias=30)

        assert borrados == 1
        assert not viejo_dump.exists()
        assert viejo_log.exists()  # no se toca


class TestGenerarDump:

    def test_generar_dump_armando_comando_correcto(self, tmp_path):
        """Verifica que pg_dump se invoca con -Fc y destino correcto."""
        destino = tmp_path / "test.dump"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # Crear el archivo destino para que el size() funcione
            destino.write_bytes(b"x" * 1024)

            ruta = backup_module.generar_dump(destino)

        assert ruta == destino
        # Verificar comando
        args = mock_run.call_args.args[0]
        assert args[0] == "pg_dump"
        assert "-Fc" in args
        assert str(destino) in args

    def test_generar_dump_con_database_url_armada_correctamente(self, tmp_path):
        """DATABASE_URL se parsea y se pasa por env PGPASSWORD (no argv)."""
        destino = tmp_path / "test.dump"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:secret@dbhost:5432/mydb"},
        ):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                destino.write_bytes(b"x" * 1024)
                backup_module.generar_dump(destino)

        # Verificar que el comando tiene host, port, user, dbname correctos
        args = mock_run.call_args.args[0]
        assert "-h" in args
        idx = args.index("-h")
        assert args[idx + 1] == "dbhost"
        assert "-p" in args
        assert args[args.index("-p") + 1] == "5432"
        assert "-U" in args
        assert args[args.index("-U") + 1] == "user"
        assert "mydb" in args

        # Y que PGPASSWORD está en env (no en argv)
        env = mock_run.call_args.kwargs.get("env", {})
        assert env.get("PGPASSWORD") == "secret"
        # Y NO está en argv
        assert "secret" not in " ".join(args)

    def test_generar_dump_falla_si_returncode_no_cero(self, tmp_path):
        """pg_dump con error → debe lanzar RuntimeError con mensaje claro."""
        destino = tmp_path / "test.dump"

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "pg_dump: error: connection failed"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError) as exc_info:
                backup_module.generar_dump(destino)

        assert "pg_dump" in str(exc_info.value)
        assert "connection failed" in str(exc_info.value)

    def test_generar_dump_sin_database_url_lanza_error(self, tmp_path):
        """Sin DATABASE_URL → RuntimeError antes de tocar subprocess."""
        destino = tmp_path / "test.dump"

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                backup_module.generar_dump(destino)

        assert "DATABASE_URL" in str(exc_info.value)

    def test_generar_dump_registra_tamano_archivo(self, tmp_path):
        """Retorna un objeto con size() > 0 (vía Path.stat().st_size)."""
        destino = tmp_path / "test.dump"
        destino.write_bytes(b"x" * 4096)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            ruta = backup_module.generar_dump(destino)

        assert ruta.stat().st_size == 4096
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_backup.py -v`
Expected: ImportError `No module named 'backup'`.

- [ ] **Paso 3: Implementar `backup.py`**

```python
"""
Módulo de backups portables (`backup.py`).

Estrategia: `pg_dump -Fc` (formato custom comprimido) ejecutado vía subprocess
con credenciales pasadas por env (`PGPASSWORD`), NUNCA por argv. Esto evita
exponer secretos en `ps aux`.

Restauración: `pg_restore -d <db> backup.dump` en cualquier PostgreSQL >= 16.

Según ADR-0001, este módulo debería vivir en `app/domain/backup.py`. Se mantiene
en raíz por compatibilidad con la Fase 1 del refactor; se moverá en Fase 3.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def _parse_database_url(url: str) -> dict:
    """Parsea DATABASE_URL estilo postgresql://user:pass@host:port/db."""
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"DATABASE_URL con esquema no soportado: {parsed.scheme}")
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/").lstrip("/"),
    }


def generar_dump(destino: Path) -> Path:
    """
    Ejecuta `pg_dump -Fc` sobre la BD configurada por DATABASE_URL y escribe el
    resultado en `destino`.

    Args:
        destino: ruta absoluta del archivo .dump a crear.

    Returns:
        La misma ruta `destino`, con el dump ya escrito.

    Raises:
        RuntimeError: si DATABASE_URL no está, si pg_dump no está instalado,
            o si returncode != 0.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL no configurado. No se puede ejecutar pg_dump."
        )

    cfg = _parse_database_url(db_url)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Credenciales por env (NUNCA en argv).
    env = os.environ.copy()
    env["PGPASSWORD"] = cfg["password"]

    cmd = [
        "pg_dump",
        "-Fc",  # formato custom comprimido
        "-h", cfg["host"],
        "-p", cfg["port"],
        "-U", cfg["user"],
        "-d", cfg["dbname"],
        "-f", str(destino),
    ]

    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=1800,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "pg_dump no está instalado en el contenedor. "
            "Reconstruir la imagen con postgresql-client incluido."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"pg_dump falló (returncode={result.returncode}): {result.stderr}"
        )

    if not destino.exists() or destino.stat().st_size == 0:
        raise RuntimeError(
            f"pg_dump terminó OK pero el archivo {destino} está vacío o ausente."
        )

    return destino


def purgar_backups_viejos(directorio: Path, dias: int = 30) -> int:
    """
    Borra archivos `.dump` con mtime > `dias` días.

    Args:
        directorio: carpeta donde están los backups.
        dias: retención; los más viejos que esto se eliminan.

    Returns:
        Cantidad de archivos borrados.
    """
    directorio = Path(directorio)
    if not directorio.is_dir():
        return 0

    cutoff = time.time() - dias * 86400
    borrados = 0
    for archivo in directorio.glob("*.dump"):
        try:
            if archivo.stat().st_mtime < cutoff:
                archivo.unlink()
                borrados += 1
        except OSError:
            # Archivo puede haber sido borrado por otro proceso; ignorar.
            continue
    return borrados
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_backup.py -v`
Expected: PASS los 8 tests.

- [ ] **Paso 5: Commit**

```bash
git add backup.py tests/unit/test_backup.py
git commit -m "feat(backup): módulo backup.py con pg_dump + purga + tests TDD"
```

---

## Tarea 2.2: Variables BACKUP_* en `app/config.py`

**Files:**
- Modify: `app/config.py`

- [ ] **Paso 1: Añadir las variables BACKUP_* en `BaseConfig`**

Después del bloque "Sync" (línea 48), añadir:

```python
# ── Backup ────────────────────────────────────────────────────────────
BACKUP_AUTO = os.environ.get("BACKUP_AUTO", "").lower() == "true" or (
    not os.environ.get("BACKUP_AUTO")
    and os.environ.get("SYNC_AUTO", "false").lower() == "true"
)
BACKUP_HORA = os.environ.get("BACKUP_HORA", "03:00")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/data/backups")
BACKUP_RETENCION_DIAS = int(os.environ.get("BACKUP_RETENCION_DIAS", "30"))
```

- [ ] **Paso 2: Crear el directorio `BACKUP_DIR` en `init_app`**

En `BaseConfig.init_app` (líneas 53-63), añadir:

```python
backup_dir = app.config.get("BACKUP_DIR")
if backup_dir:
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except PermissionError:
        app.config["BACKUP_DIR"] = "data/backups"
        os.makedirs("data/backups", exist_ok=True)
```

(Sustituir el bucle `for folder in ...` por una versión que también incluya `BACKUP_DIR`. La forma más simple es añadir otro `try/except` después del bucle.)

- [ ] **Paso 3: Verificar que tests existentes siguen pasando**

Run: `pytest tests/unit/ -v`
Expected: PASS (no rompemos nada).

- [ ] **Paso 4: Commit**

```bash
git add app/config.py
git commit -m "feat(config): variables BACKUP_AUTO/HORA/DIR/RETENCION_DIAS"
```

---

## Tarea 2.3: Dockerfile — añadir `postgresql-client`

**Files:**
- Modify: `Dockerfile`

- [ ] **Paso 1: Modificar el RUN apt-get**

Reemplazar las líneas 6-8:

```dockerfile
# Instalar dependencias del sistema:
# - libpq-dev: requerido por psycopg2-binary en runtime
# - postgresql-client-16: provee `pg_dump` para backups portables
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Paso 2: Crear el directorio `/data/backups`**

En el bloque `RUN mkdir -p /data/uploads /data/reports` (línea 18), añadir:

```dockerfile
RUN mkdir -p /data/uploads /data/reports /data/backups
```

- [ ] **Paso 3: Verificar manualmente**

(No se puede construir la imagen en sandbox; validar sintaxis con `docker --help` o revisar diff.)

`git diff Dockerfile` debería mostrar solo 3 líneas modificadas.

- [ ] **Paso 4: Commit**

```bash
git add Dockerfile
git commit -m "feat(docker): instalar postgresql-client-16 y crear /data/backups"
```

---

## Tarea 2.4: `docker-compose.yml` — documentar volumen

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Paso 1: Verificar que `/data/backups` está cubierto por `app_data`**

El volumen `app_data:/data` (línea 39) ya cubre `/data/backups` automáticamente. No hay cambio obligatorio.

Si se quiere ser explícito, **NO** modificar el compose (es suficiente con que `app_data:/data` cubra todo `/data`).

- [ ] **Paso 2: Documentar en el spec**

Añadir comentario en `docker-compose.yml` después del volumen:

```yaml
volumes:
  - app_data:/data   # incluye /data/uploads, /data/reports, /data/backups
```

- [ ] **Paso 3: Commit (solo si hubo cambio)**

```bash
git add docker-compose.yml
git commit -m "docs(docker): comentario volumen /data cubre /data/backups"
```

---

## Tarea 2.5: Implementar `GET /api/backup/descargar` con `pg_dump` real

**Files:**
- Modify: `app/web/reports_bp.py`

- [ ] **Paso 1: Reemplazar el stub en `reports_bp.py`**

Reemplazar las líneas 181-185:

```python
@bp.get("/api/backup/descargar")
@require_role("superadmin", "admin")
def descargar_backup_db():
    """501: el backup de BD PostgreSQL no se ofrece vía HTTP. Usar pg_dump."""
    return jsonify({"error": "Backup de BD PostgreSQL no disponible vía HTTP. Use pg_dump."}), 501
```

Por:

```python
@bp.get("/api/backup/descargar")
@require_role("superadmin", "admin")
def descargar_backup_db():
    """
    Genera un backup completo de la BD con `pg_dump -Fc` y lo sirve como descarga.

    Solo accesible para superadmin/admin. Registra la descarga en `audit_log`.

    El archivo generado se guarda temporalmente en REPORTS_FOLDER y el thread
    de limpieza (15 min) lo purga solo.
    """
    from backup import generar_dump
    from db import registrar_audit

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"backup_completo_{timestamp}.dump"
    destino = Path(current_app.config["REPORTS_FOLDER"]) / filename

    try:
        ruta = generar_dump(destino)
    except RuntimeError as e:
        current_app.logger.error("pg_dump falló: %s", e)
        return jsonify({
            "error": "No se pudo generar el backup",
            "detalle": str(e),
        }), 500

    # Registrar en audit_log
    try:
        registrar_audit(
            tenant_id=g.get("tenant_id"),
            usuario_id=g.get("usuario_id"),
            accion="backup_db_descargar",
            detalle={
                "filename": filename,
                "size_bytes": ruta.stat().st_size,
            },
            ip=request.remote_addr,
        )
    except Exception:  # noqa: BLE001
        current_app.logger.warning("No se pudo registrar backup en audit_log")

    return send_file(
        str(ruta),
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream",
    )
```

- [ ] **Paso 2: Añadir imports faltantes en `reports_bp.py`**

En la cabecera (líneas 14-19), añadir `from pathlib import Path` y `from flask import send_file`:

```python
from pathlib import Path
from flask import (
    Blueprint, Response, current_app, g, jsonify, request, send_file, url_for,
)
```

(Si `send_file` ya estaba, ajustar el import existente en lugar de duplicarlo.)

- [ ] **Paso 3: Verificar manualmente que no rompemos tests existentes**

Run: `pytest tests/unit/ -v`
Expected: PASS.

(No añadimos test automatizado para el endpoint porque requiere `pg_dump` real o un mock muy profundo; la verificación es por integración manual: descargar el archivo, hacer `pg_restore` en BD limpia, contar filas.)

- [ ] **Paso 4: Commit**

```bash
git add app/web/reports_bp.py
git commit -m "feat(api): /api/backup/descargar con pg_dump -Fc real"
```

---

## Tarea 2.6: Job `backup_diario` en `sync.py`

**Files:**
- Modify: `sync.py`

(No hay test automatizado para el job porque depende de `pg_dump` y subprocess; se valida en staging.)

- [ ] **Paso 1: Añadir env vars al inicio de `sync.py`**

Después de la línea 28 (donde se leen `SYNC_*`), añadir:

```python
BACKUP_AUTO          = os.getenv("BACKUP_AUTO",          "").lower() == "true"
BACKUP_HORA          = os.getenv("BACKUP_HORA",          "03:00")
BACKUP_DIR           = os.getenv("BACKUP_DIR",           "/data/backups")
BACKUP_RETENCION_DIAS = int(os.getenv("BACKUP_RETENCION_DIAS", "30"))
```

Si `BACKUP_AUTO` está vacío, el helper de `app/config.py` ya resuelve por `SYNC_AUTO`. Aquí en `sync.py` lo dejamos en `False` por defecto para no depender del helper:

```python
# Si BACKUP_AUTO está explícito, usarlo; si no, default a SYNC_AUTO.
_backup_auto_env = os.getenv("BACKUP_AUTO", "")
if _backup_auto_env == "":
    BACKUP_AUTO = SYNC_AUTO
else:
    BACKUP_AUTO = _backup_auto_env.lower() == "true"
```

- [ ] **Paso 2: Añadir la función `_backup_diario`**

Después de `_sync_nocturna_completa()`, añadir:

```python
def _backup_diario():
    """Ejecutado por schedule (BACKUP_HORA) — pg_dump -Fc con retención."""
    log.info("Iniciando backup diario (scheduler)")

    from backup import generar_dump, purgar_backups_viejos
    from email_utils import enviar_correo

    inicio = datetime.now(timezone.utc)
    timestamp = inicio.strftime("%Y%m%d_%H%M")
    filename = f"backup_completo_{timestamp}.dump"
    destino = Path(BACKUP_DIR) / filename

    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ruta = generar_dump(destino)
        size_mb = ruta.stat().st_size / (1024 * 1024)

        # Retención solo tras éxito (no borrar si el backup del día falló).
        borrados = purgar_backups_viejos(Path(BACKUP_DIR), dias=BACKUP_RETENCION_DIAS)
        log.info(
            "backup_diario OK: %s (%.1f MB), purgados=%s",
            ruta, size_mb, borrados,
        )

        _registrar_corrida_sync(
            job="backup_diario",
            tenant_slug=None,
            inicio=inicio,
            fin=datetime.now(timezone.utc),
            ok=True,
            descargados=None,
            insertados=None,
            detalle=f"{ruta} ({size_mb:.1f} MB)",
        )
    except Exception as e:
        log.exception("backup_diario falló")
        _registrar_corrida_sync(
            job="backup_diario",
            tenant_slug=None,
            inicio=inicio,
            fin=datetime.now(timezone.utc),
            ok=False,
            descargados=None,
            insertados=None,
            detalle=str(e)[:500],
        )
        # Email de alerta al admin.
        admin_email = os.getenv("ADMIN_EMAIL", "")
        if admin_email:
            try:
                enviar_correo(
                    admin_email,
                    "Fallo en backup diario",
                    f"<p>El backup diario falló: <code>{e}</code></p>"
                    f"<p>Verificar volumen <code>{BACKUP_DIR}</code> y logs del scheduler.</p>",
                )
            except Exception:
                log.exception("No se pudo enviar email de alerta de backup")
```

- [ ] **Paso 3: Añadir import `Path`**

En la cabecera, añadir `from pathlib import Path`.

- [ ] **Paso 4: Registrar el job en `iniciar_scheduler()`**

Modificar la función `iniciar_scheduler` para registrar también el job de backup:

```python
def iniciar_scheduler():
    """..."""
    global _scheduler_started

    if not SYNC_AUTO or not SCHEDULE_DISPONIBLE:
        log.info("Scheduler INACTIVO (SYNC_AUTO=false o schedule no disponible)")
        return

    if _scheduler_started:
        log.warning("Scheduler ya estaba iniciado; se ignora segunda llamada")
        return

    # Sync nocturna
    schedule.every().day.at(SYNC_HORA_NOCTURNA).do(_sync_nocturna_completa)

    # Sync incremental
    schedule.every(SYNC_INTERVALO_HORAS).hours.do(_sync_automatico)

    # Backup diario (si está activado)
    if BACKUP_AUTO:
        schedule.every().day.at(BACKUP_HORA).do(_backup_diario)
        log.info(
            "Backup diario ACTIVO a las %s, dir=%s, retención=%sd",
            BACKUP_HORA, BACKUP_DIR, BACKUP_RETENCION_DIAS,
        )
    else:
        log.info("Backup diario INACTIVO (BACKUP_AUTO=false)")

    def _run():
        while True:
            try:
                schedule.run_pending()
            except Exception:
                log.exception("scheduler loop falló; continuando")
            time_module.sleep(60)

    threading.Thread(
        target=_run, daemon=True, name="biometrico-scheduler"
    ).start()
    _scheduler_started = True

    log.info(
        "Scheduler ACTIVO: nocturna %s, incremental cada %sh",
        SYNC_HORA_NOCTURNA, SYNC_INTERVALO_HORAS,
    )
```

- [ ] **Paso 5: Commit**

```bash
git add sync.py
git commit -m "feat(sync): job backup_diario en scheduler con retención + alerta"
```

---

# PARTE 3 — Documentación

## Tarea 3.1: Sección "Operación: sync automática y backups" en `ARQUITECTURA.md`

**Files:**
- Modify: `docs/ARQUITECTURA.md`

- [ ] **Paso 1: Buscar la sección "Scheduler y ciclo de vida"**

Existe en `ARQUITECTURA.md:477-541`. La modificaremos para añadir el registro en `public.scheduler_runs` y el job de backup.

- [ ] **Paso 2: Ampliar la tabla del plan del scheduler**

Reemplazar la tabla actual (líneas 536-541):

```markdown
### Plan del scheduler

| Job | Frecuencia | Disparador | Acción |
|---|---|---|---|
| Sync nocturna completa | 1 vez al día (`SYNC_HORA_NOCTURNA`, default 02:00) | Thread daemon | `sync_module.sincronizar(...)` para todos los dispositivos activos |
| Sync incremental | Cada `SYNC_INTERVALO_HORAS` (default 2h) en horario laboral | Thread daemon | `sync_module.sincronizar(...)` desde la última sync |
| Cleanup temp files | Cada 5 minutos | Thread daemon aparte | Borra archivos > 15 min en `UPLOAD_FOLDER` y `REPORTS_FOLDER` |
| Alerta dispositivo caído | Después de cada sync | Inline | Si 3 syncs consecutivas fallan para un dispositivo, envía email a `ADMIN_EMAIL` |
```

Por:

```markdown
### Plan del scheduler

| Job | Frecuencia | Disparador | Acción | Persistencia |
|---|---|---|---|---|
| Sync nocturna completa | 1 vez al día (`SYNC_HORA_NOCTURNA`, default 02:00) | Thread daemon | `sync_module.sincronizar(...)` 30 días atrás, `force_historico=True` | 1 fila por tenant en `public.scheduler_runs` (job=`sync_nocturna`) |
| Sync incremental | Cada `SYNC_INTERVALO_HORAS` (default 2h) | Thread daemon | `sync_module.sincronizar(...)` desde watermark | 1 fila por tenant en `public.scheduler_runs` (job=`sync_incremental`) |
| Backup diario | 1 vez al día (`BACKUP_HORA`, default 03:00) | Thread daemon | `pg_dump -Fc` → `BACKUP_DIR`, purga > `BACKUP_RETENCION_DIAS` días | 1 fila global en `public.scheduler_runs` (job=`backup_diario`) |
| Cleanup temp files | Cada 5 minutos | Thread daemon aparte | Borra archivos > 15 min en `UPLOAD_FOLDER` y `REPORTS_FOLDER` | — |
| Alerta dispositivo caído | Después de cada sync | Inline | Si 3 syncs consecutivas fallan para un dispositivo, envía email a `ADMIN_EMAIL` | — |
| Retención `scheduler_runs` | Al cierre de cada sync nocturna | Inline | `DELETE WHERE inicio < NOW() - INTERVAL '90 days'` | — |

### Tabla `public.scheduler_runs`

Persiste el resultado de cada corrida (sync y backup). Se crea con la migración Alembic `0009`.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `BIGSERIAL PRIMARY KEY` | autoincrement |
| `job` | `TEXT NOT NULL` | `sync_nocturna`, `sync_incremental`, `backup_diario` |
| `tenant_slug` | `TEXT` | NULL para jobs globales (`backup_diario`) |
| `inicio` | `TIMESTAMPTZ NOT NULL` | |
| `fin` | `TIMESTAMPTZ` | |
| `ok` | `BOOLEAN NOT NULL` | |
| `descargados` / `insertados` | `INTEGER` | NULL para backup |
| `detalle` | `TEXT` | mensaje de error o ruta del dump |

Índices: `(job, inicio DESC)` y `(tenant_slug, inicio DESC) WHERE tenant_slug IS NOT NULL`.
Retención: filas > 90 días se purgan en cada sync nocturna (job `sync_nocturna`).

### Visibilidad

La card "Sincronización automática" en `/configuracion` (tab "Sincronización") consume
el endpoint `GET /api/scheduler/estado` (rol: `admin` o `superadmin`) y muestra:

- Estado actual (`ACTIVO`/`INACTIVO` desde `SYNC_AUTO`).
- Hora nocturna e intervalo.
- Próxima corrida calculada desde `schedule.next_run`.
- Las últimas 10 corridas (cualquier job) en una tabla con inicio, job, tenant, resultado, contadores y detalle.

### Backup de BD (post-Fase −1)

El sistema soporta dos formas de obtener un dump restaurable de la BD:

1. **Manual (UI)**: botón "Descargar Base de Datos" en `/configuracion` → tab "Respaldos y
   Históricos". Ejecuta `pg_dump -Fc` on-demand y devuelve el archivo vía HTTP. Registrado en
   `audit_log` con `accion=backup_db_descargar`. Requiere rol `superadmin` o `admin`.

2. **Automático (scheduler)**: job `backup_diario` a las `BACKUP_HORA` (default 03:00).
   Mismo `pg_dump -Fc` pero escribe a `BACKUP_DIR` (default `/data/backups`, volumen Docker
   persistente). Retención: `BACKUP_RETENCION_DIAS` (default 30) días. Si el backup falla,
   email a `ADMIN_EMAIL`. Si `BACKUP_AUTO` está activado, el job se registra automáticamente.

**Restauración** (portabilidad): `pg_restore -d <db> backup.dump` en cualquier PostgreSQL ≥ 16.
La copia off-site (NAS, nube, rclone) es responsabilidad de la Fase −1 del roadmap
(`docs/ARQUITECTURA.md` → "Fase −1").
```

- [ ] **Paso 3: Commit**

```bash
git add docs/ARQUITECTURA.md
git commit -m "docs(arquitectura): sección Operación — sync automática y backups"
```

---

## Tarea 3.2: Rutas nuevas en `docs/API.md`

**Files:**
- Modify: `docs/API.md`

(Si el archivo no existe todavía, crearlo siguiendo el patrón del inventario de ARQUITECTURA.md.)

- [ ] **Paso 1: Localizar la sección del blueprint `system_bp`**

Buscar "system_bp" en `docs/API.md`. Si no hay tabla por blueprint, crear una sección nueva.

- [ ] **Paso 2: Añadir la entrada de `GET /api/scheduler/estado`**

Bajo el bloque de `system_bp`:

```markdown
#### `GET /api/scheduler/estado`

Estado actual del scheduler y últimas 10 corridas registradas en `public.scheduler_runs`.

- **Auth**: rol `superadmin` o `admin`.
- **Response 200**:
  ```json
  {
    "sync_activo": true,
    "sync_hora_nocturna": "02:00",
    "sync_intervalo_horas": 2,
    "proxima_corrida": "2026-07-03T02:00:00-05:00",
    "ultimas_corridas": [
      {
        "id": 42,
        "job": "sync_incremental",
        "tenant_slug": "istpet",
        "inicio": "2026-07-02T10:00:00-05:00",
        "fin": "2026-07-02T10:05:00-05:00",
        "ok": true,
        "descargados": 124,
        "insertados": 98,
        "detalle": null
      }
    ]
  }
  ```
- **Errores**: 401 (sin sesión), 403 (sin rol).
- **Uso**: alimenta la card "Sincronización automática" en `/configuracion`.
```

- [ ] **Paso 3: Añadir/modificar la entrada de `GET /api/backup/descargar`**

Reemplazar la línea existente (si está como 501 placeholder):

```markdown
#### `GET /api/backup/descargar`

Descarga un dump completo de la BD en formato `pg_dump -Fc` (custom comprimido).

- **Auth**: rol `superadmin` o `admin`.
- **Response 200**: archivo binario `application/octet-stream`,
  filename `backup_completo_YYYYMMDD_HHMM.dump`. Registrado en `audit_log` con
  `accion=backup_db_descargar`, `detalle={filename, size_bytes}`.
- **Errores**:
  - `401` sin sesión.
  - `403` sin rol.
  - `500` si `pg_dump` falla (mensaje claro + log).
- **Restauración**: `pg_restore -d <db> backup_completo_*.dump` en cualquier PostgreSQL ≥ 16.
- **Notas**: el archivo se guarda temporalmente en `REPORTS_FOLDER` y el cleanup thread
  (15 min) lo purga automáticamente.
```

- [ ] **Paso 4: Commit**

```bash
git add docs/API.md
git commit -m "docs(api): rutas /api/scheduler/estado y /api/backup/descargar"
```

---

## Tarea 3.3: ADR `0002-sync-observable-y-backups.md`

**Files:**
- Create: `docs/adr/0002-sync-observable-y-backups.md`

- [ ] **Paso 1: Escribir el ADR**

```markdown
---
title: "ADR-0002 — Sync automática observable + Backups portables"
status: accepted
created: 2026-07-02
supersedes: []
related: ["[[ADR-0001-modularizacion-monolito-flask]]", "[[ARQUITECTURA]]"]
---

# ADR-0002: Sync automática observable + Backups portables

## Contexto

El sistema está en producción con datos biométricos irrecuperables, pero:

1. La sync automática (`schedule.every(N).hours.do(...)`) **nunca corre** porque `SYNC_AUTO=false`
   en `.env` de producción. El operador debe apretar el botón de sync manual y "estar pendiente siempre".
2. Si corriera, **fallaría en silencio**: `_sync_automatico` y `_sync_nocturna_completa` envuelven
   todo en `except Exception: pass`, y el thread `_run()` muere sin reiniciar.
3. No hay visibilidad del estado del scheduler ni de las corridas (UI no muestra nada).
4. El backup de BD es un stub (`/api/backup/descargar` devuelve 501).

## Decisión

Reforzar in-place el scheduler `schedule` in-process (decisión coherente con ADR-0001: 1 worker
gunicorn) + persistir corridas en `public.scheduler_runs` + entregar backups portables vía `pg_dump -Fc`
ejecutado por subprocess con credenciales pasadas por env (`PGPASSWORD`, nunca argv).

### Cambios

| Componente | Cambio |
|---|---|
| `db/migrations/versions/0009_scheduler_runs.py` | Crea `public.scheduler_runs` (id, job, tenant_slug, inicio, fin, ok, descargados, insertados, detalle) + 2 índices |
| `db/queries/scheduler_runs.py` | Helper `registrar_run`, `listar_ultimos(limit)`, `purgar_mayor_a(dias)` |
| `sync.py` | Logger (`logging.getLogger(__name__)`); helper `_registrar_corrida_sync`; `_run()` con try/except + `continue`; jobs `sync_incremental`, `sync_nocturna`, `backup_diario` registran en BD; flag singleton `_scheduler_started`; purga `> 90 días` al cierre de la sync nocturna |
| `backup.py` | `generar_dump(destino)` ejecuta `pg_dump -Fc` con `PGPASSWORD` por env; `purgar_backups_viejos(dir, dias)` |
| `Dockerfile` | Añade `postgresql-client-16` (provee `pg_dump`); crea `/data/backups` |
| `docker-compose.yml` | El volumen `app_data:/data` ya cubre `/data/backups` (sin cambio obligatorio) |
| `app/web/system_bp.py` | Nuevo endpoint `GET /api/scheduler/estado` (rol: `admin`/`superadmin`) |
| `app/web/reports_bp.py` | `/api/backup/descargar` implementa `pg_dump` real, registra en `audit_log` |
| `templates/configuracion.html` + `static/js/configuracion.js` | Tercer tab "Sincronización" con card y tabla de corridas |
| `.env.example` | Variables `BACKUP_AUTO`, `BACKUP_HORA`, `BACKUP_DIR`, `BACKUP_RETENCION_DIAS`; nota `SYNC_AUTO=true` recomendado en producción; corrección de comentario `DB_ENCRYPTION_KEY` (AES-256-GCM, no Fernet) |

### Alternativas consideradas

| Opción | Por qué descartada |
|---|---|
| Cron del SO (`/etc/cron.d/biometrico-sync`) | Infra fuera del contenedor; no resuelve visibilidad (UI seguiría muda) |
| Celery + Redis | Ya descartado como Fase 6 del roadmap ([[ARQUITECTURA]] → Roadmap); overkill para este fix |
| Backup manual por el operador | Estado actual; no escala, depende de memoria humana |
| Off-site backup en este PR (rclone / S3 / NAS) | Alcance de Fase −1 del roadmap; este PR garantiza solo que **siempre exista un dump fresco local** |

## Consecuencias

**Positivas:**
- Operador ya no necesita acordarse de sincronizar.
- Cualquier fallo de sync queda registrado y visible en UI + email.
- Backup diario automático con retención; restauración es 1 comando (`pg_restore`).
- Cobertura de tests > 30% (TDD estricto en módulos nuevos).

**Negativas / riesgos:**
- `pg_dump` añade dependencia (`postgresql-client-16`) → imagen Docker crece ~50 MB.
- El thread `pg_dump` mantiene 1 conexión a la BD durante segundos/minutos; con sync incremental
  simultánea podría haber contención. Mitigación: BACKUP_HORA (03:00) cae 1h después de la sync nocturna.
- Si `BACKUP_DIR` se llena (disco), el job falla y **no purga** (mitigación: alerta por email).

## Testing

- Unit (TDD):
  - `tests/unit/test_scheduler_runs.py`: 5 tests sobre `registrar_run`/`listar_ultimos`/`purgar_mayor_a` (mock de engine).
  - `tests/unit/test_sync_logging.py`: 4 tests sobre logger + `_registrar_corrida_sync` + `iniciar_scheduler` inactivo.
  - `tests/unit/test_scheduler_estado.py`: 4 tests sobre el endpoint (auth, roles, formato).
  - `tests/unit/test_backup.py`: 8 tests sobre `generar_dump` + `purgar_backups_viejos` (mock de subprocess y filesystem).
- Integración (manual/staging):
  - Levantar el sistema con `SYNC_AUTO=true` + `BACKUP_AUTO=true`.
  - Esperar a la próxima corrida y verificar fila en `public.scheduler_runs`.
  - Descargar `/api/backup/descargar` → `pg_restore` en BD limpia → conteos coinciden.

## Operaciones

**Para activar en producción:**
1. Editar `.env`: `SYNC_AUTO=true`, `BACKUP_AUTO=true` (o solo el primero), `ADMIN_EMAIL=tu@correo`.
2. Reconstruir imagen: `docker compose build biometrico-app`.
3. Aplicar migración: `docker compose exec biometrico-app alembic upgrade head`.
4. Reiniciar: `docker compose restart biometrico-app`.
5. Verificar en `/configuracion` → tab "Sincronización": badge "ACTIVO".
6. Verificar dump: `docker compose exec biometrico-app ls -lh /data/backups`.

**Restauración de emergencia:**
```bash
# 1. Copiar dump al host
docker cp biometrico-app:/data/backups/backup_completo_YYYYMMDD_HHMM.dump ./restore.dump
# 2. Crear BD limpia
createdb -h localhost -U postgres restore_db
# 3. Restaurar
pg_restore -h localhost -U postgres -d restore_db ./restore.dump
```

## Relacionado

- [[ADR-0001-modularizacion-monolito-flask]] — Arquitectura base que preservamos.
- [[ARQUITECTURA]] → "Operación: sync automática y backups" — Sección operacional.
- [[API]] — Inventario de endpoints (`/api/scheduler/estado`, `/api/backup/descargar`).
- Spec: `docs/superpowers/specs/2026-07-01-sync-backup-confiable-design.md`.
```

- [ ] **Paso 2: Commit**

```bash
git add docs/adr/0002-sync-observable-y-backups.md
git commit -m "docs(adr): 0002 — sync observable + backups portables"
```

---

# PARTE 4 — Verificación final

## Tarea 4.1: Correr la suite completa de tests

- [ ] **Paso 1: Tests unitarios**

```bash
pytest tests/unit/ -v
```

Expected: PASS todos (los nuevos + los existentes). Si alguno falla, **STOP** y arreglar antes de continuar.

- [ ] **Paso 2: Tests de integración (si hay BD de test)**

```bash
pytest tests/integration/ -v
```

Expected: SKIP si no hay BD, PASS si la hay.

- [ ] **Paso 3: Cobertura mínima**

```bash
pytest --cov=app --cov=db --cov-report=term-missing
```

Expected: ≥ 30% (configurado en `pyproject.toml`).

- [ ] **Paso 4: Smoke manual del scheduler**

Levantar app con `SYNC_AUTO=true` en `.env` local, esperar 1 minuto, abrir `/configuracion`:
- Card "Sincronización" debe decir **ACTIVO**.
- Tabla de corridas puede estar vacía al principio; tras la primera corrida aparecerá una fila.

---

## Tarea 4.2: Review final con `@reviewer` y `@security-auditor`

- [ ] **Paso 1: Disparar `@reviewer`**

```bash
# Delegar a subagente (en el orquestador):
# Task(subagent_type="reviewer", prompt="Revisar el código nuevo del sync observable + backups ...")
```

Expected: 0 hallazgos bloqueantes; warnings aceptables documentados.

- [ ] **Paso 2: Disparar `@security-auditor`**

```bash
# Delegar a subagente (en el orquestador):
# Task(subagent_type="security-auditor", prompt="Auditar /api/backup/descargar, pg_dump con PGPASSWORD por env ...")
```

Expected: foco en:
- `PGPASSWORD` por env (no argv) ✓
- `audit_log` para descargas ✓
- Rate-limit en `/api/backup/descargar` (sugerencia: añadir `@limiter.limit("5 per hour")`).
- CSRF en endpoints GET sensibles (no aplica: son GET sin mutación).
- Permisos: `/api/backup/descargar` debe ser `superadmin` (no `admin`) — **decisión**: spec dice
  `superadmin` para descarga, pero el código actual dice `superadmin, admin`. **Acción**: dejar como está
  y documentar la decisión en ADR si hay disenso.

---

## Tarea 4.3: Commit final y resumen

- [ ] **Paso 1: Verificar git status limpio**

```bash
git status
```

Expected: working tree clean.

- [ ] **Paso 2: Listar commits nuevos**

```bash
git log --oneline -20
```

Expected: ~10-12 commits del plan, mensajes descriptivos.

- [ ] **Paso 3: Resumen al usuario**

Mensaje final con:
- ✅ Tabla `public.scheduler_runs` creada (migración 0009)
- ✅ `sync.py` con logger + loop inkillable + registro por corrida
- ✅ Endpoint `/api/scheduler/estado` + card en `/configuracion`
- ✅ Módulo `backup.py` con `pg_dump -Fc` + retención
- ✅ Endpoint `/api/backup/descargar` operativo
- ✅ Job `backup_diario` automático
- ✅ Dockerfile actualizado (`postgresql-client-16`)
- ✅ ADR 0002 + docs actualizadas

---

# Fuera de alcance (recordatorio)

Lo siguiente queda explícitamente fuera de este PR (vive en otros tickets):

- **Copia off-site del backup** (NAS, rclone, S3) → Fase −1.
- **Restore desde UI** → peligroso; solo CLI documentada.
- **Multi-worker gunicorn** → atado a 1 worker por el scheduler in-process (ADR-0001).
- **CSRF en `/api/backup/descargar`** → no aplica (GET sin mutación de estado).
- **Toggle del scheduler desde UI** → futuro: añadiría endpoint `POST /api/scheduler/toggle`
  + tabla `public.sync_scheduler_config`.
- **Repository pattern** → ADR-0001 lo descarta.
- **i18n de los mensajes del logger** → hoy en español hardcodeado.