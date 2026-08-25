"""
Acceso a datos para el dominio people (`app/domain/people.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/people_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db.queries.personas_crud import (
    actualizar_persona,
    crear_persona,
    get_historico_persona,
    get_persona,
    listar_personas,
)
from db.queries.grupos import (
    listar_grupos,
    listar_grupos_funcionales,
)
from db.queries.auth import (
    get_tipos_persona as listar_tipos_persona,
)

from app.domain.periods import reordenar_a_apellido_nombre

__all__ = [
    "actualizar_persona",
    "crear_persona",
    "get_historico_persona",
    "get_persona",
    "listar_grupos",
    "listar_grupos_funcionales",
    "listar_personas",
    "listar_tipos_persona",
    "reordenar_a_apellido_nombre",
]
