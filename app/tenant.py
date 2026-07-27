"""
Tenant loader (`app/tenant.py`).

Migrado desde `app.py:156-227` (`autenticar_request`). Se registra como
`before_request` en `create_app()` ANTES de los blueprints, para que
cuando llegue el dispatch ya esté cargado:

  - `g.usuario_id`
  - `g.tenant_schema`
  - `g.roles`
  - `g.nombre`
  - `g.tenant_id`
  - `g.tenant`           (dict con info del tenant o `None`)
  - `g.tenant_tipos`     (lista para @require_tipo_persona)

**Importante:** este loader NO autentica (eso lo hace el `auth_bp` con
`/login` + sesión). Solo hidrata `g` cuando ya hay sesión válida.
"""
from __future__ import annotations

import os

from flask import g, jsonify, redirect, request, session, url_for

# Endpoints que NO requieren autenticación (login, static).
_ENDPOINTS_PUBLICOS = {"auth.login", "static", None}


def _es_request_api() -> bool:
    """True si el request es a /api/* o espera JSON."""
    if request.path.startswith("/api/"):
        return True
    return "application/json" in request.headers.get("Accept", "")


def cargar_contexto_usuario():
    """
    Before request de hidratación de contexto.

    Si no hay sesión, redirige a login (HTML) o devuelve 401 (API).
    Si hay sesión, popula `g.usuario*` y `g.tenant*`.
    """
    # ── 1. Endpoints públicos: pasar de largo ────────────────────────
    if request.endpoint in _ENDPOINTS_PUBLICOS:
        return None

    # ── 2. Sin sesión → redirigir / 401 ──────────────────────────────
    if "usuario_id" not in session:
        if _es_request_api():
            return jsonify({"error": "No autenticado"}), 401
        return redirect(url_for("auth.login"))

    # ── 3. Hidratar `g` con lo que ya tenemos en sesión ───────────────
    g.usuario_id    = session["usuario_id"]
    g.tenant_schema = session.get(
        "tenant_schema", os.environ.get("TENANT_DEFAULT", "istpet")
    )
    g.roles         = session.get("roles", []) or []
    g.nombre        = session.get("nombre", "")
    g.tenant_id     = session.get("tenant_id")

    # ── 4. Validar que el tenant está activo ─────────────────────────
    # El schema `public` es de uso superadmin (no es un tenant real).
    if g.tenant_schema != "public":
        try:
            from db import get_tenant_by_slug
            tenant_info = get_tenant_by_slug(g.tenant_schema)
        except Exception:  # noqa: BLE001
            tenant_info = None

        if not tenant_info:
            # Tenant fue eliminado entre login y esta request
            session.clear()
            if _es_request_api():
                return jsonify({"error": "Tenant no encontrado"}), 404
            return redirect(url_for("auth.login"))

        if not tenant_info.get("activo", True):
            session.clear()
            if _es_request_api():
                return jsonify({"error": "Cuenta de institución suspendida"}), 403
            # Redirigir a login con mensaje; en HTML lo pinta el template.
            return redirect(url_for("auth.login"))

        g.tenant = tenant_info
    else:
        g.tenant = None

    # ── 5. Cargar tipos de persona del tenant (para @require_tipo_persona) ──
    try:
        from db import get_tipos_persona
        g.tenant_tipos = get_tipos_persona(g.tenant_schema)
    except Exception:  # noqa: BLE001
        g.tenant_tipos = []

    return None
