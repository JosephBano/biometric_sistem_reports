"""
Tests de Alembic como fuente de verdad de schema (Fase −1 / DoD-13).

Verifica que:
  - `alembic upgrade head` aplica todas las migraciones.
  - `init_db()` es idempotente contra una BD ya migrada por Alembic
    (detecta `public.alembic_version` y salta el DDL legacy).
  - Los datos seed se aplican en ambos modos.
"""
from __future__ import annotations

import os
import subprocess

import pytest
import sqlalchemy as sa


pytestmark = pytest.mark.integration


# Guardar el DATABASE_URL original para restaurarlo después de cada test.
_ORIGINAL_DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _run_alembic(database_url: str) -> None:
    """Ejecuta `alembic upgrade head` en un subprocess."""
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic upgrade head falló: rc={result.returncode}\n"
            f"STDERR: {result.stderr[-1500:]}"
        )


def _reset_engine_cache():
    """Resetea el engine cacheado en db.connection para usar nueva DATABASE_URL."""
    import db.connection as _conn
    _conn._engine = None


@pytest.fixture(autouse=True)
def _restore_database_url():
    """Restaura el DATABASE_URL original después de cada test."""
    yield
    os.environ["DATABASE_URL"] = _ORIGINAL_DATABASE_URL
    _reset_engine_cache()


class TestAlembicMigraciones:

    def test_alembic_upgrade_head_crea_tablas_public(self):
        """`alembic upgrade head` crea todas las tablas del schema public."""
        import pgserver
        server = pgserver.get_server("biometrico_test_alembic_public")
        uri = server.get_uri()

        _reset_engine_cache()
        _run_alembic(uri)

        # Verificar tablas del schema public
        engine = sa.create_engine(uri)
        with engine.connect() as conn:
            rows = conn.execute(sa.text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
            """)).fetchall()
            tablas = {row[0] for row in rows}

        # Tablas esperadas
        esperadas = {"tenants", "usuarios", "audit_log", "login_intentos", "alembic_version"}
        assert esperadas.issubset(tablas), (
            f"Faltan tablas: {esperadas - tablas}"
        )

    def test_alembic_upgrade_head_crea_tablas_tenant(self):
        """`alembic upgrade head` crea las tablas del schema istpet."""
        import pgserver
        server = pgserver.get_server("biometrico_test_alembic_tenant")
        uri = server.get_uri()

        _reset_engine_cache()
        _run_alembic(uri)

        engine = sa.create_engine(uri)
        with engine.connect() as conn:
            rows = conn.execute(sa.text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'istpet'
                ORDER BY tablename
            """)).fetchall()
            tablas = {row[0] for row in rows}

        # Tablas de negocio esperadas
        esperadas = {
            "personas", "asistencias", "justificaciones", "feriados",
            "grupos", "categorias", "tipos_persona", "dispositivos",
            "periodos_vigencia", "sync_log", "breaks_categorizados",
        }
        assert esperadas.issubset(tablas), (
            f"Faltan tablas de tenant: {esperadas - tablas}"
        )

    def test_alembic_aplica_todas_las_migraciones(self):
        """La versión final de Alembic es 0009 (última migración)."""
        import pgserver
        server = pgserver.get_server("biometrico_test_alembic_version")
        uri = server.get_uri()

        _reset_engine_cache()
        _run_alembic(uri)

        engine = sa.create_engine(uri)
        with engine.connect() as conn:
            version = conn.execute(
                sa.text("SELECT version_num FROM public.alembic_version")
            ).scalar()

        assert version == "0011", f"Versión Alembic esperada 0011, obtuve {version}"


class TestInitDbConAlembic:

    def test_init_db_detecta_alembic_y_salta_ddl(self):
        """Si alembic_version existe, init_db() salta el DDL legacy."""
        import pgserver
        server = pgserver.get_server("biometrico_test_init_con_alembic")
        uri = server.get_uri()
        os.environ["DATABASE_URL"] = uri
        _reset_engine_cache()

        # 1. Alembic crea el schema
        _run_alembic(uri)

        # 2. init_db() debe detectar alembic_version y solo sembrar
        from db.init import init_db
        init_db()

        # 3. Verificar que el tenant 'istpet' existe (sembrado por init_db)
        engine = sa.create_engine(uri)
        with engine.connect() as conn:
            tenants = conn.execute(
                sa.text("SELECT slug FROM public.tenants WHERE slug = 'istpet'")
            ).fetchall()
        assert len(tenants) == 1, "Tenant 'istpet' no se sembró"

    def test_init_db_sin_alembic_aplica_ddl_legacy(self):
        """Sin alembic_version, init_db() aplica DDL legacy (modo compatibilidad)."""
        import pgserver
        server = pgserver.get_server("biometrico_test_init_sin_alembic")
        uri = server.get_uri()
        os.environ["DATABASE_URL"] = uri
        _reset_engine_cache()

        # NO ejecutamos alembic — init_db() debe crear el schema por sí solo
        from db.init import init_db
        init_db()

        engine = sa.create_engine(uri)
        with engine.connect() as conn:
            # Verificar que init_db creó alembic_version? No — solo crea el schema
            # Tablas del schema public
            tenants = conn.execute(
                sa.text("SELECT count(*) FROM public.tenants WHERE slug = 'istpet'")
            ).scalar()
        assert tenants == 1, "Tenant 'istpet' no se creó con init_db() legacy"

    def test_init_db_es_idempotente(self):
        """Llamar init_db() múltiples veces no rompe nada."""
        import pgserver
        server = pgserver.get_server("biometrico_test_init_idempotente")
        uri = server.get_uri()
        os.environ["DATABASE_URL"] = uri
        _reset_engine_cache()

        from db.init import init_db

        # Primera llamada
        init_db()
        # Segunda llamada (idempotente)
        try:
            init_db()
        except Exception as e:
            pytest.fail(f"init_db() no es idempotente: {type(e).__name__}: {e}")

        # Verificar que el tenant sigue existiendo
        engine = sa.create_engine(uri)
        with engine.connect() as conn:
            n = conn.execute(
                sa.text("SELECT count(*) FROM public.tenants WHERE slug = 'istpet'")
            ).scalar()
        assert n == 1, "Tenant duplicado después de doble init_db()"
