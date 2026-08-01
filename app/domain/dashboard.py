"""
Acceso a datos para el dominio dashboard (`app/domain/dashboard.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/dashboard_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    consultar_asistencias,
)

__all__ = [
    "consultar_asistencias",
]
