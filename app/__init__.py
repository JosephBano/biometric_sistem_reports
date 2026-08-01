"""
Paquete principal `app` post-refactor.

Migración del monolito Flask a Application Factory + Blueprints por dominio + Servicios.
Ver `docs/adr/0001-modularizacion-monolito-flask.md` para la decisión.

Reglas arquitectónicas (ver `docs/ARQUITECTURA.md`):
  - `app/web/*` solo importa de `app/domain/*` y nunca de `db.queries.*`
  - `app/domain/*` nunca importa de `app/web/*`
  - `db/queries/*` nunca importa de `app/*` ni de Flask

Entry point::

    from app import create_app
    app = create_app("production")  # arranca gunicorn / Flask dev server
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export perezoso para no tocar el orden de registro de imports.
__all__ = ["create_app"]

# Flask se importa eagerly (no TYPE_CHECKING) porque `create_app()` lo usa
# en tiempo de ejecución, no solo para anotaciones.
from flask import Flask

if TYPE_CHECKING:
    # Alias para tipadores estrictos.
    FlaskApp = Flask


def create_app(config_name: str = "production") -> Flask:
    """
    Application Factory.

    Args:
        config_name: clave en `app.config.config_map` ("development",
            "production", "testing"). Por defecto "production" para que
            `gunicorn wsgi:app` siga funcionando idéntico.

    Returns:
        Una instancia de Flask configurada y con todos los blueprints
        registrados. Lista para servir tráfico.
    """
    # Import dentro de la función para evitar ciclos al cargar el paquete.
    from app.config import config_map
    from app.errors import register_error_handlers
    from app.extensions import csrf, limiter
    from app.tenant import cargar_contexto_usuario
    from app.web import all_blueprints

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    # ── Config ────────────────────────────────────────────────────────────
    cfg_class = config_map[config_name]
    cfg = cfg_class()             # instanciar para poder pasar a init_app
    app.config.from_object(cfg)
    cfg.init_app(app)

    # ── Extensions ───────────────────────────────────────────────────────
    limiter.init_app(app)
    csrf.init_app(app)

    # ── Tenant loader (debe ir ANTES de los blueprints) ──────────────────
    app.before_request(cargar_contexto_usuario)

    # ── Blueprints ────────────────────────────────────────────────────────
    for bp in all_blueprints:
        app.register_blueprint(bp)

    # ── Hooks de seguridad (CSP, X-Frame-Options, etc.) ─────────────────
    from app.security_headers import apply_security_headers
    apply_security_headers(app)

    # ── Context processors (datos inyectados en cada render Jinja) ───────
    from app.context_processors import register_context_processors
    register_context_processors(app)

    # ── Manejadores de error ─────────────────────────────────────────────
    register_error_handlers(app)

    # ── Lifecycle: scheduler solo si SYNC_AUTO=true ─────────────────────
    if app.config.get("SYNC_AUTO"):
        from app.domain.schedule import init_scheduler
        init_scheduler(app)

    # ── Lifecycle: thread de limpieza de archivos temporales ────────────
    from app.cleanup import start_cleanup_thread
    start_cleanup_thread(app)

    return app
