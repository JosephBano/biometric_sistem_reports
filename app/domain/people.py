"""
Acceso a datos para el dominio people (`app/domain/people.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/people_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    actualizar_persona,
    crear_persona,
    get_historico_persona,
    listar_grupos,
    listar_grupos_funcionales,
    listar_personas,
)

__all__ = [
    "actualizar_persona",
    "crear_persona",
    "get_historico_persona",
    "listar_grupos",
    "listar_grupos_funcionales",
    "listar_personas",
]
