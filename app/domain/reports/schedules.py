"""
Resolución y búsqueda de horarios individuales y de turnos (`app.domain.reports.schedules`).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

_WEEKDAY_COL: dict[int, str] = {
    0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
    4: "viernes", 5: "sabado", 6: "domingo",
}


def _minutos_diferencia(hora_limite: Any, hora_real: Any) -> int:
    """Minutos de diferencia entre hora_limite y hora_real."""
    dt_base = datetime.combine(datetime.today().date(), hora_limite)
    dt_real = datetime.combine(datetime.today().date(), hora_real)
    return int((dt_real - dt_base).total_seconds() / 60)


def _buscar_horario(nombre: str, id_usuario: Any, horarios: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Busca el horario de un empleado en el dict de horarios.
    Intenta por id_usuario primero; cae en búsqueda por nombre en mayúsculas,
    y luego por coincidencia de palabras/nombre invertido.
    """
    if not horarios:
        return None
    by_id     = horarios.get("by_id",     {})
    by_nombre = horarios.get("by_nombre", {})

    if id_usuario and str(id_usuario) in by_id:
        return by_id[str(id_usuario)]

    if nombre:
        nom_clean = nombre.strip().upper()
        if nom_clean in by_nombre:
            return by_nombre[nom_clean]

        palabras_target = set(nom_clean.replace(",", " ").split())
        for k, v in by_nombre.items():
            if set(k.replace(",", " ").split()) == palabras_target:
                return v

    return None


def _get_info_dia(horario_persona: dict[str, Any], fecha: date) -> dict[str, Any]:
    """Retorna la información de horario aplicable para una persona en una fecha."""
    weekday   = fecha.weekday()
    es_sabado = weekday == 5
    es_domingo = weekday == 6

    if es_domingo:
        hora_entrada = horario_persona.get("domingo")
        hora_salida = horario_persona.get("domingo_salida")
        return {
            "trabaja":      hora_entrada is not None,
            "hora_entrada": hora_entrada,
            "hora_salida":  hora_salida,
            "almuerzo_min": 0,
        }

    columna      = _WEEKDAY_COL.get(weekday, "viernes")
    hora_entrada = horario_persona.get(columna)
    hora_salida  = horario_persona.get(f"{columna}_salida")

    col_almuerzo = f"{columna}_almuerzo_min"
    almuerzo_dia = horario_persona.get(col_almuerzo)
    if almuerzo_dia is None:
        almuerzo_dia = horario_persona.get("almuerzo_min", 0)

    almuerzo_min = 0 if es_sabado else almuerzo_dia

    return {
        "trabaja":      hora_entrada is not None,
        "hora_entrada": hora_entrada,
        "hora_salida":  hora_salida,
        "almuerzo_min": almuerzo_min,
    }
