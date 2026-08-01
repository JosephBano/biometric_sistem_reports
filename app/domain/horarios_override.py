"""Servicios de dominio para `overrides_horario_persona` (ADR-0003).

Override individual: plantilla + vigencia por persona, anula el default
del grupo funcional (precedencia paso 1).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from db.queries.horarios_grupo_funcional import (
    cerrar_override_horario,
    crear_override_horario,
    listar_overrides_por_persona,
    obtener_override_vigente_para_persona,
)


def listar_de_persona(persona_id: str):
    """Lista TODOS los overrides (vigentes o no) de una persona."""
    return listar_overrides_por_persona(persona_id)


def obtener_vigente(persona_id: str, fecha: date):
    """Override vigente para una persona en una fecha, o None."""
    return obtener_override_vigente_para_persona(persona_id, fecha)


def crear(
    persona_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    notas: Optional[str] = None,
    creado_por: Optional[str] = None,
):
    """Crea un override. Idempotente por UNIQUE(persona, plantilla, fecha_inicio)."""
    return crear_override_horario(
        persona_id=persona_id,
        plantilla_id=plantilla_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        notas=notas,
        creado_por=creado_por,
    )


def cerrar(ohp_id: str, fecha_fin: date) -> bool:
    """Cierra el override poniendo `fecha_fin` (no DELETE: histórico)."""
    return cerrar_override_horario(ohp_id, fecha_fin)


__all__ = ["listar_de_persona", "obtener_vigente", "crear", "cerrar"]
