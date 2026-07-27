"""
Headers de seguridad HTTP (`app/security_headers.py`).

Se aplican en `after_request` para que toda respuesta los incluya.

Reglas (ver `docs/ARQUITECTURA.md#reglas-arquitectónicas`):
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: SAMEORIGIN (evita clickjacking via iframe externo)
  - Referrer-Policy: strict-origin-when-cross-origin
  - Content-Security-Policy: whitelist de CDNs (Bootstrap, Google Fonts)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


# Política CSP: whitelist explícita de CDNs conocidos (Bootstrap, Google Fonts, jsdelivr).
# Si añades un CDN, agrégalo aquí y documenta por qué.
_DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'self';"
)


def apply_security_headers(app: Flask) -> None:
    """Registra `after_request` que añade los headers de seguridad."""

    @app.after_request
    def _add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # CSP sólo para HTML; las API no lo necesitan
        if response.content_type and response.content_type.startswith("text/html"):
            response.headers.setdefault("Content-Security-Policy", _DEFAULT_CSP)
        return response
