"""
Wrapper para `analytics` (`app.domain.analytics`).

Re-exporta las funciones de análisis desde el módulo top-level `analytics.py`.

API pública:
  - `resumen_periodo(periodo_id) -> dict`
  - `distribucion_asistencia_periodo(periodo_id) -> dict`
  - `analizar(tipo_persona_id, grupo_id, persona_id, fecha_inicio, fecha_fin) -> dict`
"""
from __future__ import annotations

from analytics import (  # noqa: F401  (re-export)
    analizar,
    distribucion_asistencia_periodo,
    resumen_periodo,
)

__all__ = [
    "resumen_periodo",
    "distribucion_asistencia_periodo",
    "analizar",
    "calcular_asistencia_periodo",
    "get_periodo",
    "listar_grupos",
]

# Re-exports de `db` (capa de datos), añadidos para cumplir la regla de
# capas del ADR-0001 (antes: `app/web/analytics_bp.py` importaba `db` directo).
from db import (
    calcular_asistencia_periodo,
    get_periodo,
    listar_grupos,
)
