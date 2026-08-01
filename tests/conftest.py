"""
Fixtures compartidos para todos los tests.

Convenciones:
- `app`        → instancia Flask con config "testing"
- `client`     → test client de Flask (síncrono)
- `auth_client`→ cliente con sesión autenticada como admin (mockeado, sin DB)

Los tests de integración que necesitan PostgreSQL están marcados con
`@pytest.mark.integration` y se saltean automáticamente si no hay BD
disponible (ver `_is_postgres_available`).
"""
from __future__ import annotations

import base64
import os
import secrets

import pytest

# Forzar el modo testing ANTES de importar la app.
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "postgresql://test_user:test_pass@localhost:5432/test_db")
# Generar una clave AES de 32 bytes válida para tests de auth.
os.environ.setdefault(
    "DB_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-for-pytest-only")


def _is_postgres_available() -> bool:
    """Devuelve True si hay un PostgreSQL accesible en DATABASE_URL."""
    try:
        import sqlalchemy

        engine = sqlalchemy.create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        return True
    except Exception:
        return False


# ── Pytest markers ───────────────────────────────────────────────────────────

def pytest_collection_modifyitems(config, items):
    """Saltea tests de integración si no hay PostgreSQL de test disponible."""
    if _is_postgres_available():
        return
    skip_integration = pytest.mark.skip(
        reason="PostgreSQL de test no disponible (DATABASE_URL no responde)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


# ── Fixtures compartidos ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """
    App Flask en modo testing.

    Usa PostgreSQL de test si está disponible. Si no, los tests de integración
    se saltean (ver `pytest_collection_modifyitems`) y solo corren los unit.
    """
    from app import create_app
    flask_app = create_app("testing")
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret",
    )
    return flask_app


@pytest.fixture()
def client(app):
    """Test client síncrono de Flask."""
    return app.test_client()


@pytest.fixture()
def app_ctx(app):
    """Context manager para tests que necesitan `flask.g` / `current_app`."""
    with app.app_context():
        yield app


@pytest.fixture()
def admin_session(client):
    """
    Inyecta una sesión falsa de admin sin tocar la BD real.
    Útil para tests unitarios de RBAC y decoradores.
    """
    with client.session_transaction() as sess:
        sess["usuario_id"] = "test-admin-id"
        sess["tenant_schema"] = "istpet"
        sess["tenant_id"] = "test-tenant-id"
        sess["nombre"] = "Admin de Prueba"
        sess["roles"] = ["superadmin", "admin"]
        sess["csrf_token"] = "test-csrf-token"
    return client
