"""
Reglas de negocio y análisis de asistencia (`app.domain.reports.rules`).
"""
from __future__ import annotations

from app.domain.reports.day_rules import analizar_dia
from app.domain.reports.person_rules import (
    _calcular_horas_contrato,
    _procesar_persona_sin_horario,
    analizar_por_persona,
)
from app.domain.reports.schedules import (
    _WEEKDAY_COL,
    _buscar_horario,
    _get_info_dia,
    _minutos_diferencia,
)

__all__ = [
    "analizar_dia",
    "analizar_por_persona",
    "_minutos_diferencia",
    "_buscar_horario",
    "_get_info_dia",
    "_WEEKDAY_COL",
    "_procesar_persona_sin_horario",
    "_calcular_horas_contrato",
]
