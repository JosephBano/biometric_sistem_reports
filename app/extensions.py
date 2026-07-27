"""
Extensiones Flask compartidas (`app/extensions.py`).

El patrón es: instancias globales creadas a nivel de módulo, SIN `app=...`
en el constructor. Se vinculan a la app en `create_app()` con `init_app(app)`.

Reglas:
  - CSRF / Rate Limiter viven aquí, no en `app/__init__.py`
  - Las blueprints importan estos objetos vía `from app.extensions import csrf, limiter`
"""
from __future__ import annotations

import secrets

from flask import jsonify, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ══════════════════════════════════════════════════════════════════════════
# CSRF (custom, port del monolito — Flask-WTF queda como backlog P2)
# ══════════════════════════════════════════════════════════════════════════

class CsrfProtect:
    """
    Implementación de CSRF compatible con el monolito anterior.

    API pública:
      - `init_app(app)`     → registra `generate_csrf_token` como global Jinja
                              y valida automáticamente en `before_request`.
      - `generate_token()`  → token actual (lo usa el template)
      - `validate()`        → bool, valida el token presente en el form/header
    """

    def __init__(self) -> None:
        self._exempt_endpoints: set[str] = set()

    def init_app(self, app) -> None:
        """Registra hooks. Llamar una sola vez desde `create_app()`."""
        app.jinja_env.globals["csrf_token"] = self.generate_token

        @app.before_request
        def _validate_csrf_each_request():
            # Solo aplica a mutaciones sobre rutas HTML (no /api/*)
            if request.method == "POST" and not request.path.startswith("/api/"):
                if request.endpoint in self._exempt_endpoints:
                    return
                if not self.validate():
                    return jsonify({"error": "Token CSRF inválido"}), 403

    def generate_token(self) -> str:
        """Devuelve el token actual, creándolo si no existía en la sesión."""
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    def validate(self) -> bool:
        """Valida el token presente en form data o header `X-CSRF-Token`."""
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        return bool(token) and token == session.get("csrf_token", "")

    def exempt(self, view_func):
        """Marca un endpoint como exento de CSRF (decorador)."""
        if hasattr(view_func, "__name__"):
            self._exempt_endpoints.add(view_func.__name__)
        return view_func


csrf = CsrfProtect()


# ══════════════════════════════════════════════════════════════════════════
# Rate Limiter
# ══════════════════════════════════════════════════════════════════════════

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
