"""
Tests del paso 2 de `db/migrations/env.py` (migraciones por tenant).

Motivación (incidente de producción 2026-07-28): `alembic upgrade head`
logueaba "Running upgrade 0008 -> ... -> 0011" para cada tenant, pero
**nada persistía**: los schemas de los tenants seguían en 0008, con la
tabla `categorias` sin renombrar. Los tenants llevaban meses estancados
mientras `public` sí avanzaba.

Causa: SQLAlchemy 2.x usa "commit as you go". En el bucle por tenant, el
`connection.execute("SET search_path ...")` abre una transacción implícita
*antes* de que Alembic llame a `context.begin_transaction()`; al detectar
una transacción activa, Alembic la trata como no-op y no commitea. Al
salir del `with connectable.connect()`, SQLAlchemy hace ROLLBACK y las
migraciones del tenant se revierten en silencio.

`public` no se veía afectado porque su paso no ejecuta nada en la conexión
antes de la transacción de Alembic — de ahí que el desfase pasara
desapercibido.

Estos tests usan una base de datos nueva por test (no el pgserver
compartido, que conserva estado entre corridas y enmascaraba el bug).
"""
from __future__ import annotations

import os
import subprocess
import uuid

import pytest
import sqlalchemy as sa


pytestmark = pytest.mark.integration

HEAD = "0011"
TENANTS_EXTRA = ("conduccion_clases", "ecmi")


def _servidor():
    try:
        import pgserver  # type: ignore
    except ImportError:  # pragma: no cover
        pytest.skip("pgserver no disponible")
    return pgserver.get_server("biometrico_test_alembic_multitenant")


def _uri_con_db(uri: str, nombre: str) -> str:
    """Reemplaza el nombre de BD conservando el query string.

    pgserver entrega URIs sobre socket unix
    (`postgresql://postgres:@/postgres?host=/run/...`), así que no basta
    con partir por el último `/`: ese está dentro de la ruta del socket.
    """
    base, _, query = uri.partition("?")
    base = base.rsplit("/", 1)[0] + "/" + nombre
    return f"{base}?{query}" if query else base


@pytest.fixture()
def db_limpia():
    """Crea una base de datos nueva y la destruye al terminar.

    Imprescindible: los tests que reutilizan el pgserver compartido
    arrastran schemas ya migrados de corridas anteriores, que es
    justamente lo que impidió detectar este bug.
    """
    server = _servidor()
    admin_uri = server.get_uri()
    nombre = f"test_mt_{uuid.uuid4().hex[:12]}"

    admin = sa.create_engine(admin_uri, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{nombre}"'))
    admin.dispose()

    yield _uri_con_db(admin_uri, nombre)

    admin = sa.create_engine(admin_uri, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = :n AND pid <> pg_backend_pid()"
        ), {"n": nombre})
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{nombre}"'))
    admin.dispose()


def _alembic_upgrade_head(uri: str) -> None:
    result = subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": uri},
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic upgrade head falló: rc={result.returncode}\n"
            f"STDERR: {result.stderr[-2000:]}"
        )


def _sembrar_tenants_extra(uri: str) -> None:
    """Registra tenants adicionales y crea sus schemas.

    Reproduce el entorno real: varios tenants activos en `public.tenants`,
    no solo el TENANT_DEFAULT.
    """
    engine = sa.create_engine(uri)
    with engine.connect() as conn:
        for slug in TENANTS_EXTRA:
            conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{slug}"'))
            conn.execute(
                sa.text(
                    "INSERT INTO public.tenants (slug, nombre, activo) "
                    "VALUES (:slug, :slug, true) ON CONFLICT (slug) DO NOTHING"
                ),
                {"slug": slug},
            )
        conn.commit()
    engine.dispose()


def _version_de(uri: str, schema: str) -> str | None:
    engine = sa.create_engine(uri)
    with engine.connect() as conn:
        existe = conn.execute(sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :s AND table_name = 'alembic_version'
            )
        """), {"s": schema}).scalar()
        if not existe:
            return None
        return conn.execute(
            sa.text(f'SELECT version_num FROM "{schema}".alembic_version')
        ).scalar()


class TestMigracionesPorTenantPersisten:
    """El corazón del bug: las migraciones del tenant deben COMMITEAR."""

    def test_tenant_default_queda_en_head(self, db_limpia):
        _alembic_upgrade_head(db_limpia)
        assert _version_de(db_limpia, "istpet") == HEAD, (
            "El schema del tenant no quedó en head: las migraciones se "
            "ejecutaron pero se revirtieron (falta connection.commit() en "
            "el bucle por tenant de env.py)."
        )

    def test_todos_los_tenants_activos_quedan_en_head(self, db_limpia):
        # Primera pasada: crea public.tenants para poder sembrar los extra.
        _alembic_upgrade_head(db_limpia)
        _sembrar_tenants_extra(db_limpia)
        # Segunda pasada: ahora el bucle debe alcanzar a los 3 tenants.
        _alembic_upgrade_head(db_limpia)

        for slug in ("istpet", *TENANTS_EXTRA):
            assert _version_de(db_limpia, slug) == HEAD, (
                f"El tenant {slug!r} no llegó a head."
            )

    def test_public_tambien_queda_en_head(self, db_limpia):
        """Regresión inversa: el commit nuevo no debe romper el paso public."""
        _alembic_upgrade_head(db_limpia)
        assert _version_de(db_limpia, "public") == HEAD


class TestEfectosDeLaMigracionPersisten:
    """No basta con el stamp: el DDL del tenant debe seguir ahí."""

    def test_tablas_de_la_0011_existen_en_cada_tenant(self, db_limpia):
        _alembic_upgrade_head(db_limpia)
        _sembrar_tenants_extra(db_limpia)
        _alembic_upgrade_head(db_limpia)

        engine = sa.create_engine(db_limpia)
        with engine.connect() as conn:
            for slug in ("istpet", *TENANTS_EXTRA):
                tablas = {
                    r[0] for r in conn.execute(sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = :s"
                    ), {"s": slug}).fetchall()
                }
                faltan = {
                    "grupos_funcionales",
                    "grupos_funcionales_personas",
                    "horarios_default_grupo",
                    "overrides_horario_persona",
                } - tablas
                assert not faltan, f"Al tenant {slug!r} le faltan tablas: {faltan}"
        engine.dispose()

    def test_no_queda_la_tabla_categorias(self, db_limpia):
        """Tras la 0010 ningún tenant debe conservar el nombre viejo."""
        _alembic_upgrade_head(db_limpia)

        engine = sa.create_engine(db_limpia)
        with engine.connect() as conn:
            sobran = conn.execute(sa.text(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'categorias'"
            )).fetchall()
        engine.dispose()
        assert sobran == [], f"Quedó `categorias` en: {[r[0] for r in sobran]}"
