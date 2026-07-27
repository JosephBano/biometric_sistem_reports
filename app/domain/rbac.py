"""
RBAC: decoradores de control de acceso (`app/domain/rbac.py`).

Migrado desde `decorators.py` (raíz).

Reglas arquitectónicas:
  - Este módulo SOLO importa de Flask (`g`, `session`, `request`, etc.).
  - NO importa de `app.domain.auth` ni `db.queries.*` — los ciclos estaban
    prohibidos por el ADR-0001.
  - Los decoradores leen el contexto hidratado por `app/tenant.py`:
      `g.usuario_id`, `g.roles`, `g.tenant_tipos`.

API:
  - `@require_role(*roles)`         → exige al menos uno de los roles
  - `@require_tipo_persona(nombre)`  → exige que el tenant tenga el tipo
"""
from __future__ import annotations

import functools
from collections.abc import Callable

from flask import g, jsonify, redirect, request, session, url_for

# Roles válidos del sistema (sincronizado con docs/AUTENTICACION.md).
ROLES_VALIDOS: set[str] = {
    "superadmin",
    "admin",
    "gestor",
    "supervisor_grupo",
    "supervisor_periodo",
    "readonly",
}


def _is_api_request() -> bool:
    """True si la petición es a una ruta /api/ o espera JSON."""
    if request.path.startswith("/api/"):
        return True
    return "application/json" in request.headers.get("Accept", "")


def require_role(*roles: str) -> Callable:
    """
    Decorador: exige que el usuario tenga al menos uno de los roles.

    Uso::

        @bp.get("/admin/usuarios")
        @require_role("admin", "superadmin")
        def admin_usuarios():
            ...

    Comportamiento:
      - Petición HTML sin sesión → redirect al login.
      - Petición API sin sesión → JSON 401.
      - Sesión sin rol suficiente → 403 (HTML inline / JSON).
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # Sin sesión → no autenticado
            if "usuario_id" not in session:
                if _is_api_request():
                    return jsonify({"error": "No autenticado"}), 401
                return redirect(url_for("auth.login"))

            user_roles = set(g.get("roles", []) or [])
            required = set(roles)

            if not user_roles.intersection(required):
                if _is_api_request():
                    return jsonify({
                        "error": "Acceso denegado. Rol insuficiente.",
                        "roles_requeridos": list(required),
                    }), 403
                return (
                    "<h3>403 – Acceso denegado</h3>"
                    "<p>No tiene los permisos necesarios para esta acción.</p>"
                    "<a href='/'>Volver al panel</a>"
                ), 403

            return f(*args, **kwargs)
        return wrapper
    return decorator


def require_tipo_persona(nombre_tipo: str) -> Callable:
    """
    Decorador: exige que el tenant tenga configurado un tipo de persona
    con el nombre indicado (case-insensitive).

    Lee `g.tenant_tipos`, cargado por `app/tenant.py` en `before_request`.

    Uso::

        @bp.get("/periodos/nuevo")
        @require_role("gestor", "admin", "superadmin")
        @require_tipo_persona("Practicante")
        def nuevo_periodo():
            ...
    """
    nombre_lower = nombre_tipo.lower()

    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            tipos = getattr(g, "tenant_tipos", []) or []
            nombres = {t["nombre"].lower() for t in tipos}

            if nombre_lower not in nombres:
                if _is_api_request():
                    return jsonify({
                        "error": "Esta funcionalidad no está disponible para tu institución."
                    }), 403
                return (
                    "<h3>403 – Funcionalidad no disponible</h3>"
                    "<p>Esta funcionalidad no está disponible para tu institución.</p>"
                    "<a href='/'>Volver al panel</a>"
                ), 403

            return f(*args, **kwargs)
        return wrapper
    return decorator
