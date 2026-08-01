"""
Tests del decorador RBAC (`app.domain.rbac`).

Cubre:
  - Redirección a login cuando no hay sesión (HTML)
  - 401 cuando no hay sesión (API)
  - 403 con mensaje de rol insuficiente (HTML y API)
  - Permitir acceso si el usuario tiene al menos un rol de los requeridos
"""
from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture()
def flask_app():
    """App mínima para tests de RBAC (sin tocar BD)."""
    app = create_app("testing")
    app.config.update(WTF_CSRF_ENABLED=False)
    return app


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


# ── Sin sesión ────────────────────────────────────────────────────────────

class TestAnonimo:

    def test_htmml_redirige_a_login(self, client):
        """Un GET a un endpoint protegido sin sesión debe redirigir a /login."""
        # Usamos un endpoint cualquiera protegido por sesión (sin requerir rol)
        resp = client.get("/admin/usuarios", headers={"Accept": "text/html"})
        # 302 → redirect a login
        assert resp.status_code in (302, 308), f"Esperado redirect, obtuve {resp.status_code}"
        assert "/login" in resp.headers.get("Location", "")

    def test_api_devuelve_401_json(self, client):
        """Un GET a un endpoint API sin sesión debe responder 401 JSON."""
        resp = client.get("/api/dispositivos", headers={"Accept": "application/json"})
        assert resp.status_code == 401
        assert resp.is_json
        assert "No autenticado" in resp.get_json()["error"]

    def test_ruta_api_sin_accept_tambien_401(self, client):
        """Las rutas /api/* siempre devuelven JSON 401 sin importar Accept."""
        resp = client.get("/api/dispositivos")
        assert resp.status_code == 401
        assert resp.is_json


# ── Con sesión pero sin rol ───────────────────────────────────────────────

class TestRoles:

    @pytest.fixture(autouse=True)
    def _mock_db(self, monkeypatch):
        """Mockea las llamadas a DB para que el tenant loader funcione sin BD."""
        # El tenant loader importa `db.get_tenant_by_slug` y `db.get_tipos_persona`
        # con lazy imports dentro de la función, así que parchamos `db.*` directamente.
        import db as db_module
        monkeypatch.setattr(
            db_module,
            "get_tenant_by_slug",
            lambda slug: {"id": "t-1", "slug": slug, "activo": True, "nombre": "Test"},
        )
        monkeypatch.setattr(
            db_module,
            "get_tipos_persona",
            lambda schema=None: [{"id": "tp-1", "nombre": "Empleado"}],
        )

    def test_rol_insuficiente_devuelve_403_en_html(self, flask_app, client):
        """Sesión con rol 'readonly' intentando /admin/usuarios → 403 HTML."""
        with client.session_transaction() as sess:
            sess["usuario_id"] = "user-1"
            sess["tenant_schema"] = "istpet"
            sess["tenant_id"] = "tenant-1"
            sess["nombre"] = "Read Only"
            sess["roles"] = ["readonly"]
            sess["csrf_token"] = "csrf-1"

        # /admin/usuarios requiere admin/superadmin
        resp = client.get("/admin/usuarios")
        assert resp.status_code == 403
        # Respuesta HTML inline (no template)
        assert b"403" in resp.data or b"Acceso denegado" in resp.data

    def test_rol_correcto_pasa_decorador(self, flask_app, client):
        """Sesión con rol 'admin' accede a /admin/usuarios."""
        with client.session_transaction() as sess:
            sess["usuario_id"] = "user-2"
            sess["tenant_schema"] = "istpet"
            sess["tenant_id"] = "tenant-1"
            sess["nombre"] = "Admin"
            sess["roles"] = ["admin"]
            sess["csrf_token"] = "csrf-2"

        # /admin/usuarios renderiza un template (puede 200 o 500 si BD no está)
        # Lo importante: NO redirige a login ni devuelve 403.
        resp = client.get("/admin/usuarios")
        assert resp.status_code not in (302, 401, 403), (
            f"Esperado acceso permitido, obtuve {resp.status_code}"
        )


# ── Validación del conjunto de roles válidos ──────────────────────────────

def test_roles_validos_incluye_todos_los_roles_del_sistema():
    from app.domain.rbac import ROLES_VALIDOS
    assert "superadmin" in ROLES_VALIDOS
    assert "admin" in ROLES_VALIDOS
    assert "gestor" in ROLES_VALIDOS
    assert "readonly" in ROLES_VALIDOS


def test_roles_valos_no_incluye_basura():
    from app.domain.rbac import ROLES_VALIDOS
    assert "guest" not in ROLES_VALIDOS
    assert "root" not in ROLES_VALIDOS
