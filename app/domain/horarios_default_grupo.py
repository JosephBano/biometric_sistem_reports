"""Servicios de dominio para `horarios_default_grupo` (ADR-0003).

Re-exporta funciones de `db/queries/horarios_grupo_funcional.py` para
que `app/web/grupos_funcionales_bp.py` no importe `db` directamente
(regla del ADR-0001).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from db.queries.horarios_grupo_funcional import (
    cerrar_horario_default_grupo,
    crear_horario_default_grupo,
    listar_horarios_default_grupo,
    listar_horarios_vigentes_para_grupo_funcional,
    resolver_default_para_grupos_funcionales,
)


def listar(grupo_funcional_id: str):
    """Lista TODOS los defaults (vigentes o no) de un grupo funcional."""
    return listar_horarios_default_grupo(grupo_funcional_id)


def listar_vigentes(grupo_funcional_id: str, fecha: date):
    """Lista defaults vigentes de un gf en una fecha."""
    return listar_horarios_vigentes_para_grupo_funcional(
        grupo_funcional_id, fecha
    )


def crear(
    grupo_funcional_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    prioridad: int = 0,
    notas: Optional[str] = None,
):
    """Crea un default por grupo funcional. Idempotente por UNIQUE compuesto."""
    return crear_horario_default_grupo(
        grupo_funcional_id=grupo_funcional_id,
        plantilla_id=plantilla_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        prioridad=prioridad,
        notas=notas,
    )


def cerrar(hdg_id: str, fecha_fin: date) -> bool:
    """Cierra un default poniendo `fecha_fin` (no DELETE: conserva histórico)."""
    return cerrar_horario_default_grupo(hdg_id, fecha_fin)


def resolver_para_grupos(grupo_funcional_ids: list[str], fecha: date):
    """Resuelve el default con mayor prioridad entre los grupos funcionales.

    Helper exportado para que el resolver canónico (`resolver_horario_vigente`)
    lo use. Ver ADR-0003 r2/P11.
    """
    return resolver_default_para_grupos_funcionales(grupo_funcional_ids, fecha)


__all__ = [
    "listar",
    "listar_vigentes",
    "crear",
    "cerrar",
    "resolver_para_grupos",
]
