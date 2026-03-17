"""
Decoradores de ruta — Fase 2.

@require_role(*roles)
    El usuario autenticado debe tener AL MENOS UNO de los roles indicados.
    - Peticiones HTML → redirect al login (401) o 403 con mensaje
    - Peticiones API  → JSON 401/403

@require_tipo_persona(nombre)
    El tenant debe tener configurado al menos un tipo de persona con ese nombre
    (case-insensitive). Lee g.tenant_tipos cargado por el middleware.
    - Falla → 403 con mensaje "Funcionalidad no disponible"
"""

import functools
from flask import g, request, redirect, url_for, jsonify, session


# Roles válidos del sistema
ROLES_VALIDOS = {
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
    accept = request.headers.get("Accept", "")
    return "application/json" in accept


def require_role(*roles):
    """
    Decorador: exige que el usuario tenga al menos uno de los roles.

    Uso::

        @app.route('/admin/usuarios')
        @require_role('admin', 'superadmin')
        def admin_usuarios():
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # Sin sesión → no autenticado
            if "usuario_id" not in session:
                if _is_api_request():
                    return jsonify({"error": "No autenticado"}), 401
                return redirect(url_for("login"))

            user_roles = set(g.get("roles", []))
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


def require_tipo_persona(nombre_tipo: str):
    """
    Decorador: exige que el tenant tenga configurado un tipo de persona
    con el nombre indicado (case-insensitive).

    Lee ``g.tenant_tipos`` cargado por el middleware before_request.

    Uso::

        @app.route('/periodos/nuevo')
        @require_role('gestor', 'admin', 'superadmin')
        @require_tipo_persona('Practicante')
        def nuevo_periodo():
            ...
    """
    nombre_lower = nombre_tipo.lower()

    def decorator(f):
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
