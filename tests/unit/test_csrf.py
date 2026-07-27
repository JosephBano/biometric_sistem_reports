"""
Tests del CSRF custom (`app.extensions`).

Cubre:
  - El token se genera al primer acceso
  - El token es estable dentro de la misma sesión
  - `validate()` rechaza tokens vacíos o distintos
  - Las rutas /api/* están exentas (no requieren CSRF)
"""
from __future__ import annotations

import pytest

from app import create_app
from app.extensions import csrf


@pytest.fixture()
def flask_app():
    app = create_app("testing")
    app.config.update(WTF_CSRF_ENABLED=False)
    return app


class TestTokenGeneracion:

    def test_generate_token_retorna_string(self, flask_app):
        with flask_app.test_request_context():
            token = csrf.generate_token()
            assert isinstance(token, str)
            assert len(token) >= 32

    def test_generate_token_es_estable_en_sesion(self, flask_app):
        """Llamadas múltiples a generate_token devuelven el mismo valor."""
        with flask_app.test_request_context():
            t1 = csrf.generate_token()
            t2 = csrf.generate_token()
            assert t1 == t2


class TestValidate:

    def test_validate_sin_request_falla(self, flask_app):
        """Sin contexto de request, validate() lanza RuntimeError (diseño de Flask)."""
        # csrf.validate() accede a `request` que requiere contexto activo.
        # En el flujo real SIEMPRE hay request context (viene de before_request).
        with pytest.raises(RuntimeError):
            csrf.validate()

    def test_validate_con_token_correcto_pasa(self, flask_app):
        with flask_app.test_request_context("/admin/usuarios", method="POST"):
            from flask import request
            token = csrf.generate_token()
            request.form = {"csrf_token": token}
            assert csrf.validate() is True

    def test_validate_con_token_incorrecto_falla(self, flask_app):
        with flask_app.test_request_context("/admin/usuarios", method="POST"):
            from flask import request
            csrf.generate_token()  # crea el token
            request.form = {"csrf_token": "token-equivocado"}
            assert csrf.validate() is False

    def test_validate_sin_token_en_form_falla(self, flask_app):
        with flask_app.test_request_context("/admin/usuarios", method="POST"):
            from flask import request
            csrf.generate_token()
            request.form = {}
            assert csrf.validate() is False


class TestApiExenta:

    def test_rutas_api_no_bloqueadas_por_csrf(self, flask_app, client):
        """Las rutas /api/* están exentas de CSRF (siguen a decorador RBAC)."""
        # /api/sincronizar sin sesión → cae en RBAC y devuelve 401, NO 403 por CSRF.
        resp = client.post("/api/sincronizar", json={"fecha_inicio": "2025-01-01"})
        assert resp.status_code != 403, (
            f"Las rutas API no deben ser bloqueadas por CSRF. Obtuve {resp.status_code}"
        )
        # Probablemente 401 (no autenticado) por tenant loader, no 403 CSRF.
        assert resp.status_code in (401, 200, 400, 500)
