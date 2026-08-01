"""
Handlers de error globales (`app/errors.py`).

Se registran una vez en `create_app()`. Devuelven respuesta consistente:
  - API: JSON `{"error": "..."}`
  - HTML: render del template genérico o un flash + redirect

Migrados desde `app.py:70-76` (429) y se añaden 401/403/404/500.
"""
from __future__ import annotations

from flask import jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException


def register_error_handlers(app) -> None:
    """Monta todos los handlers en la app dada."""

    # ── 429 (rate limit) ──────────────────────────────────────────────
    @app.errorhandler(429)
    def ratelimit_handler(e):
        if request.path.startswith("/api/") or \
                "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": "Demasiadas solicitudes. Espere 15 minutos."}), 429
        from flask import flash
        flash("Demasiados intentos. Espere 15 minutos.", "danger")
        return redirect(url_for("auth.login"))

    # ── 401 (sin sesión) ──────────────────────────────────────────────
    @app.errorhandler(401)
    def unauthorized_handler(e):
        if request.path.startswith("/api/") or \
                "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": "No autenticado"}), 401
        return redirect(url_for("auth.login"))

    # ── 403 (sin permisos) ────────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden_handler(e):
        if request.path.startswith("/api/") or \
                "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": "Acceso denegado"}), 403
        return (
            "<h3>403 – Acceso denegado</h3>"
            "<p>No tiene los permisos necesarios para esta acción.</p>"
            "<a href='/'>Volver al panel</a>"
        ), 403

    # ── 404 ──────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found_handler(e):
        if request.path.startswith("/api/") or \
                "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": "Recurso no encontrado"}), 404
        # Para HTML: re-renderizar el template de login con flag 404 si es la página
        # principal; en el resto, dejar el default 404 de Flask.
        if not request.path or request.path == "/":
            return redirect(url_for("auth.login"))
        return ("<h3>404 – Página no encontrada</h3>"
                "<a href='/'>Volver al panel</a>"), 404

    # ── 500 ──────────────────────────────────────────────────────────
    @app.errorhandler(500)
    def internal_error_handler(e):
        # Loggear al servidor (gunicorn captura stdout/stderr)
        app.logger.exception("Error 500 no controlado")
        if request.path.startswith("/api/") or \
                "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": "Error interno del servidor"}), 500
        return render_template("login.html", error="Error interno del servidor"), 500

    # ── HTTPException genérica (catch-all) ───────────────────────────
    @app.errorhandler(HTTPException)
    def http_exception_handler(e):
        return e

    # ── Exception genérica → 500 ────────────────────────────────────
    @app.errorhandler(Exception)
    def generic_exception_handler(e):
        # Si es HTTPException, dejar que werkzeug la maneje (no la interceptamos).
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Unhandled exception")
        return internal_error_handler(e)
