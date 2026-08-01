"""
Acceso a datos para el dominio periods (`app/domain/periods.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/periods_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    archivar_periodo,
    calcular_asistencia_periodo,
    cerrar_periodo,
    crear_periodo,
    eliminar_periodo,
    get_periodo,
    listar_periodos_activos,
    listar_periodos_historial,
    procesar_csv_personas_periodo,
)

__all__ = [
    "archivar_periodo",
    "calcular_asistencia_periodo",
    "cerrar_periodo",
    "crear_periodo",
    "eliminar_periodo",
    "get_periodo",
    "listar_periodos_activos",
    "listar_periodos_historial",
    "procesar_csv_personas_periodo",
]
