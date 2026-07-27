"""
Wrapper para `horarios` (`app.domain.attendance`).

Re-exporta la API de parseo de horarios desde el módulo top-level
`horarios.py`. Ver `app.domain.schedule` para contexto sobre la estrategia
de wrappers transitorios.

API pública:
  - `parsear_csv(filepath) -> list[dict]`
  - `parsear_obd(filepath) -> list[dict]`
"""
from __future__ import annotations

from horarios import parsear_csv, parsear_obd  # noqa: F401  (re-export)

__all__ = [
    "parsear_csv",
    "parsear_obd",
    "actualizar_estado_justificacion",
    "actualizar_justificacion_completa",
    "eliminar_feriado",
    "eliminar_justificacion",
    "get_feriados",
    "get_justificacion_by_id",
    "get_justificaciones",
    "importar_feriados_csv",
    "insertar_feriado",
    "insertar_justificacion",
]

# Re-exports de `db` (capa de datos), añadidos para cumplir la regla de
# capas del ADR-0001 (antes: `app/web/attendance_bp.py` importaba `db` directo).
from db import (
    actualizar_estado_justificacion,
    actualizar_justificacion_completa,
    eliminar_feriado,
    eliminar_justificacion,
    get_feriados,
    get_justificacion_by_id,
    get_justificaciones,
    importar_feriados_csv,
    insertar_feriado,
    insertar_justificacion,
)
