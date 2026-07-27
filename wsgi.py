"""
WSGI entrypoint (`wsgi.py`).

Punto de entrada canónico para gunicorn::

    gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 wsgi:app

Ver `Dockerfile` actualizado.

`app` se construye vía la Application Factory de `app/__init__.py`.
El módulo también monta `DispatcherMiddleware` para mantener el prefijo
`/biometrico` que el frontend y los proxies esperan.
"""
from werkzeug.exceptions import NotFound
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app

# Crea la aplicación Flask con la configuración de producción por defecto.
app = create_app("production")

# ── ProxyFix: respetar X-Forwarded-* del proxy ─────────────────────────
# Equivalente a `app.py:49` original.
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1,
)

# ── DispatcherMiddleware: prefijo /biometrico ──────────────────────────
# Mantiene la URL pública intacta tras el refactor.
app.wsgi_app = DispatcherMiddleware(NotFound(), {
    "/biometrico": app.wsgi_app,
})
