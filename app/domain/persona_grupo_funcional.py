"""Servicios de dominio para `persona_grupo_funcional` (ADR-0003).

N:M entre personas y grupos funcionales con vigencia + `es_principal`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from db.queries.horarios_grupo_funcional import (
    asignar_persona_a_grupo_funcional,
    cerrar_vinculo_persona_grupo_funcional,
    listar_grupos_funcionales_de_persona,
    listar_grupos_funcionales_vigentes_para_persona,
    listar_personas_en_grupo_funcional,
)


def listar_de_persona(persona_id: str):
    """Lista todas las asignaciones (vigentes o no) de una persona."""
    return listar_grupos_funcionales_de_persona(persona_id)


def listar_vigentes_de_persona(persona_id: str, fecha: date):
    """Lista los grupos funcionales activos para la persona en la fecha."""
    return listar_grupos_funcionales_vigentes_para_persona(persona_id, fecha)


def asignar(
    persona_id: str,
    grupo_funcional_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    es_principal: bool = False,
    notas: Optional[str] = None,
):
    """Asigna una persona a un grupo funcional con vigencia.

    Idempotente via UNIQUE (persona_id, grupo_funcional_id, fecha_inicio).
    Si `es_principal=True`, desmarca cualquier otro principal vigente.
    """
    return asignar_persona_a_grupo_funcional(
        persona_id=persona_id,
        grupo_funcional_id=grupo_funcional_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        es_principal=es_principal,
        notas=notas,
    )


def cerrar(pgf_id: str, fecha_fin: date) -> bool:
    """Cierra la asignación poniendo `fecha_fin` (no DELETE: histórico)."""
    return cerrar_vinculo_persona_grupo_funcional(
        persona_id="",  # compat retroactiva; el caller pasa pgf_id
        grupo_funcional_id="",
        fecha_fin=fecha_fin,
    )


def cerrar_por_id(pgf_id: str, fecha_fin: date) -> bool:
    """Cierra la asignación por `pgf_id`. Idempotente.

    Wrapper conveniente para evitar pasar `persona_id` y
    `grupo_funcional_id` cuando solo se tiene el id de la fila.
    """
    # Implementación: la fila tiene `persona_id` + `grupo_funcional_id`.
    # Como atajo, usamos `listar_de_persona` no aplica aquí; mejor:
    # SELECT + UPDATE. Para mantener simpleza y dado que las
    # operaciones se hacen por id, lo más limpio es agregar una
    # función SQL específica.
    from db.connection import get_connection
    from sqlalchemy import text

    with get_connection() as conn:
        result = conn.execute(
            text("""
                UPDATE grupos_funcionales_personas
                SET fecha_fin = :ff
                WHERE id = CAST(:id AS uuid)
                  AND fecha_fin IS NULL
            """),
            {"id": pgf_id, "ff": fecha_fin},
        )
    return result.rowcount > 0


def listar_personas_en_grupo(grupo_funcional_id: str, fecha: date):
    """Retorna los `persona_id` con el grupo funcional vigente en la fecha."""
    return listar_personas_en_grupo_funcional(grupo_funcional_id, fecha)


__all__ = [
    "listar_de_persona",
    "listar_vigentes_de_persona",
    "asignar",
    "cerrar",
    "cerrar_por_id",
    "listar_personas_en_grupo",
]
