"""
Acceso a datos para el dominio groups (`app/domain/groups.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/groups_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    actualizar_grupo,
    actualizar_grupo_funcional,
    crear_grupo,
    crear_grupo_funcional,
    listar_grupos,
    listar_grupos_funcionales,
)

__all__ = [
    "actualizar_grupo",
    "actualizar_grupo_funcional",
    "crear_grupo",
    "crear_grupo_funcional",
    "listar_grupos",
    "listar_grupos_funcionales",
]