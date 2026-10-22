"""Servicios de dominio para `grupos_funcionales` (ADR-0003, Tarea 4.1).

API estable consumida por `app/web/grupos_funcionales_bp.py`. Re-exporta
funciones de `db.queries.grupos_funcionales` para que `app/web/*` no
importe `db` directamente (regla del ADR-0001: app/web solo importa de
app/domain).
"""
from __future__ import annotations

from db.queries.grupos import (
    actualizar_grupo_funcional,
    crear_grupo_funcional,
    listar_grupos_funcionales,
)


def listar(solo_activos: bool = True):
    """Lista grupos funcionales (catálogo del tenant)."""
    return listar_grupos_funcionales(activo=True if solo_activos else None)


def crear(nombre: str = None, codigo: str = None, tipo_persona_id: str = None, **kwargs):
    """Crea un grupo funcional. Idempotente por UNIQUE(nombre)."""
    nombre_final = nombre or codigo or kwargs.get("nombre") or kwargs.get("codigo")
    return crear_grupo_funcional(nombre=nombre_final, tipo_persona_id=tipo_persona_id)


def actualizar(grupo_funcional_id: str, datos: dict):
    """Actualiza campos permitidos del grupo funcional."""
    return actualizar_grupo_funcional(grupo_funcional_id, datos)


__all__ = ["listar", "crear", "actualizar"]
