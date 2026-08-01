"""
Acceso a datos para el dominio system (`app/domain/system.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/system_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    insertar_asistencias,
)

__all__ = [
    "insertar_asistencias",
]
