"""
Fixtures para tests de integración (Fase 7.1 del ADR-0001).

Levanta un PostgreSQL embebido con `pgserver`, aplica el DDL via `init_db()`,
y expone un `client` Flask + fixtures de sesión autenticada.

Los tests que requieren esta capa están en `tests/integration/` y marcados
con `@pytest.mark.integration`. Si `pgserver` no puede arrancar (ej. en
entornos sin las extensiones requeridas), todos los tests se saltean
automáticamente.

Concurrencia: por simplicidad, los tests comparten el mismo server (scope
session) pero cada test hace rollback de su transacción (scope function).
"""
from __future__ import annotations

import base64
import os
import secrets
import uuid

import pytest

# Forzar el modo testing ANTES de importar la app.
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault(
    "DB_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)


# ─────────────────────────────────────────────────────────────────────────────
# Embedded PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────


_PG_SERVER = None
_PG_URI = None


def _start_pg_or_skip():
    """Levanta un Postgres embebido con pgserver. Si falla, skip toda la suite."""
    global _PG_SERVER, _PG_URI

    try:
        import pgserver  # type: ignore

        _PG_SERVER = pgserver.get_server("biometrico_test_int")
        _PG_URI = _PG_SERVER.get_uri()
    except Exception as e:
        pytest.skip(f"pgserver no disponible: {e}", allow_module_level=True)
        return None

    # Setear DATABASE_URL antes de que se importe la app.
    os.environ["DATABASE_URL"] = _PG_URI
    return _PG_URI


# Arrancar ANTES de cualquier import de `app` o `db`.
_PG_URI = _start_pg_or_skip()


def _patch_schema_for_pgserver():
    """
    `db/schema.py` pide `CREATE EXTENSION IF NOT EXISTS pgcrypto` para usar
    `gen_random_uuid()`. Pero pgserver (PostgreSQL 16 embebido) NO incluye
    pgcrypto. PG 13+ trae `gen_random_uuid()` built-in, así que solo tenemos
    que saltarnos la línea de CREATE EXTENSION en este entorno de test.

    Esta función se ejecuta UNA vez (session scope) antes del primer test.
    """
    import db.schema as _schema_mod
    import db.init as _init_mod

    # Si `pgcrypto` está disponible, no hacer nada.
    try:
        import sqlalchemy

        engine = sqlalchemy.create_engine(_PG_URI)
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            conn.commit()
        return  # pgcrypto OK, no parcheamos nada.
    except Exception:
        pass

    # Sin pgcrypto → parchear:
    #   1. db.schema.PUBLIC_DDL (el símbolo del módulo schema)
    #   2. db.init.PUBLIC_DDL y db.init.get_tenant_ddl (binding local
    #      que `init_db()` usa; `from X import Y` hace snapshot).
    _schema_mod.PUBLIC_DDL = _schema_mod.PUBLIC_DDL.replace(
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n", "",
    )

    if hasattr(_init_mod, "PUBLIC_DDL"):
        _init_mod.PUBLIC_DDL = _init_mod.PUBLIC_DDL.replace(
            "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n", "",
        )

    if hasattr(_init_mod, "get_tenant_ddl"):
        _original = _init_mod.get_tenant_ddl

        def _patched_get_tenant_ddl(slug):
            return _original(slug).replace(
                "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n", "",
            )

        _init_mod.get_tenant_ddl = _patched_get_tenant_ddl


@pytest.fixture(scope="session", autouse=True)
def _setup_pg_session():
    """Crea el schema (idempotente) una vez por sesión de tests."""
    if _PG_URI is None:
        yield
        return

    _patch_schema_for_pgserver()

    # Importar la app DESPUÉS de setear DATABASE_URL.
    from db.init import init_db

    init_db()
    yield


# ─────────────────────────────────────────────────────────────────────────────
# Flask app + client
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def app(_setup_pg_session):
    """App Flask en modo testing, contra el Postgres embebido."""
    if _PG_URI is None:
        pytest.skip("PostgreSQL embebido no disponible")

    from app import create_app

    flask_app = create_app("testing")
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret",
        DATABASE_URL=_PG_URI,
    )
    return flask_app


@pytest.fixture()
def client(app):
    """Test client síncrono de Flask."""
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# Datos de prueba
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def tenant_id(app):
    """ID del tenant por defecto (`istpet`). Lo crea si no existe."""
    import sqlalchemy as sa
    from db.connection import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT id::text FROM public.tenants WHERE slug = 'istpet'")
        ).fetchone()
        if row:
            return row[0]

        new_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO public.tenants (id, slug, nombre, activo) "
                "VALUES (CAST(:id AS uuid), 'istpet', 'ISTPET Test', true)"
            ),
            {"id": new_id},
        )
        conn.commit()
        return new_id


@pytest.fixture()
def admin_user_id(app, tenant_id):
    """ID de un usuario superadmin para tests que requieren sesión autenticada."""
    import sqlalchemy as sa
    from db.connection import get_engine
    from app.domain.auth import hash_password

    engine = get_engine()
    with engine.connect() as conn:
        # Limpia cualquier usuario de test previo.
        conn.execute(
            sa.text("DELETE FROM public.usuarios WHERE email = :email"),
            {"email": "admin-test@biometrico.local"},
        )
        new_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO public.usuarios "
                "(id, tenant_id, email, password_hash, nombre, roles, activo) "
                "VALUES (CAST(:id AS uuid), CAST(:tid AS uuid), :email, "
                "        :ph, 'Admin Test', ARRAY['superadmin','admin']::text[], true)"
            ),
            {
                "id": new_id,
                "tid": tenant_id,
                "email": "admin-test@biometrico.local",
                "ph": hash_password("test-pass"),
            },
        )
        conn.commit()
        return new_id


@pytest.fixture()
def admin_client(client, admin_user_id, tenant_id):
    """Cliente Flask con sesión autenticada como superadmin."""
    with client.session_transaction() as sess:
        sess["usuario_id"] = admin_user_id
        sess["tenant_schema"] = "istpet"
        sess["tenant_id"] = tenant_id  # FK a public.tenants.id (NO user_id)
        sess["nombre"] = "Admin Test"
        sess["roles"] = ["superadmin", "admin"]
        sess["csrf_token"] = "test-csrf-token"
    return client


@pytest.fixture()
def anonymous_client(client):
    """Cliente Flask sin sesión (para probar RBAC)."""
    return client


@pytest.fixture()
def csrf_token(client):
    """
    Devuelve un token CSRF válido para usar en POSTs de tests.

    Uso:
        def test_x(client, csrf_token):
            r = client.post("/url", data={"csrf_token": csrf_token, ...})
    """
    with client.session_transaction() as sess:
        # El mismo mecanismo que `CsrfProtect.generate_token` usa.
        if "csrf_token" not in sess:
            import secrets
            sess["csrf_token"] = secrets.token_hex(32)
        return sess["csrf_token"]


@pytest.fixture(autouse=True)
def _reset_login_intentos():
    """
    Limpia `public.login_intentos` antes de cada test para que el rate limit
    no acumule estado entre tests. El DDL es idempotente, este TRUNCATE es
    seguro porque solo afecta datos de prueba.
    """
    import sqlalchemy as sa
    from db.connection import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sa.text("TRUNCATE TABLE public.login_intentos RESTART IDENTITY"))
        conn.commit()
    yield
