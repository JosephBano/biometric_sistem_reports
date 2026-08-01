"""
Acceso a datos para el dominio breaks (`app/domain/breaks.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/breaks_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    insertar_break_categorizado,
)

__all__ = [
    "insertar_break_categorizado",
]
