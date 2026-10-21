"""
Cruce y normalización de justificaciones (`app.domain.reports.justifications`).
"""
from __future__ import annotations

from datetime import date
from typing import Any


def es_justificado_dia(
    justificaciones: dict[tuple[Any, str, str], Any] | None,
    id_usuario: Any,
    fecha_dia: date | str,
    tipo_obs: str,
) -> bool:
    """Verifica si existe justificación registrada para (id_usuario, fecha, tipo_obs)."""
    if not justificaciones or not id_usuario:
        return False
    fecha_iso = fecha_dia.isoformat() if hasattr(fecha_dia, "isoformat") else str(fecha_dia)
    return (
        (id_usuario, fecha_iso, tipo_obs) in justificaciones
        or (str(id_usuario), fecha_iso, tipo_obs) in justificaciones
    )


def obtener_justificacion_persona(
    justificaciones: dict[tuple[str, str, str], Any] | None,
    id_usuario: Any,
    fecha_eval: date | str,
    tipo_obs: str,
) -> dict[str, Any] | None:
    """
    Obtiene la justificación para una persona y fecha dada.
    Si es recuperable, copia y enriquece el motivo con los datos de compensación.
    """
    if not justificaciones or not id_usuario:
        return None
    fecha_iso = fecha_eval.isoformat() if hasattr(fecha_eval, "isoformat") else str(fecha_eval)
    clave = (str(id_usuario), fecha_iso, tipo_obs)
    j = justificaciones.get(clave)
    if not j:
        j = justificaciones.get((id_usuario, fecha_iso, tipo_obs))
    if not j:
        return None

    if j.get("recuperable") == 1:
        h_fin = f" a {j.get('hora_recuperacion_fin')}" if j.get("hora_recuperacion_fin") else ""
        nota = f" [RECUPERABLE – se compensará {j.get('fecha_recuperacion')} {j.get('hora_recuperacion')}{h_fin}]"
        j = dict(j)  # copiar para no mutar el dict global
        j["motivo"] = (j.get("motivo") or "") + nota
    return j
