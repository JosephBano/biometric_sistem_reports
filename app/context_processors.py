"""
Context processors globales (`app/context_processors.py`).

Inyectan variables en TODOS los templates Jinja sin que cada blueprint
las pase explícitamente.

Migrados desde `app.py:88-93` (inject_system_info) y `app.py:218-227` (inject_user_info).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def register_context_processors(app: Flask) -> None:
    """Monta los context processors en la app."""

    @app.context_processor
    def inject_system_info():
        return dict(
            nombre_sistema=app.config.get("NOMBRE_SISTEMA", "Informes Biométricos"),
            nombre_institucion=app.config.get("NOMBRE_INSTITUCION", "ISTPET"),
        )

    @app.context_processor
    def inject_user_info():
        from flask import g, session

        def _tenant_tiene_tipo(nombre_tipo: str) -> bool:
            tipos = getattr(g, "tenant_tipos", []) or []
            return any(t["nombre"].lower() == nombre_tipo.lower() for t in tipos)

        return dict(
            current_user_nombre=session.get("nombre", ""),
            current_user_roles=session.get("roles", []),
            tenant=getattr(g, "tenant", None),
            tenant_tipos=getattr(g, "tenant_tipos", []),
            tenant_tiene_tipo=_tenant_tiene_tipo,
        )

    @app.context_processor
    def inject_pending_counts():
        """Inyecta contadores que el layout usa en el menú."""
        # Importación perezosa: la conexión a BD puede no estar disponible en build/sync.
        try:
            from db import get_justificaciones_pendientes
            count = len(get_justificaciones_pendientes())
        except Exception:
            count = 0

        return dict(justificaciones_pendientes_count=count)
