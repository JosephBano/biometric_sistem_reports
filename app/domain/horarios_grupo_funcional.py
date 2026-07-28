"""
Acceso a datos para el dominio horarios por grupo funcional
(`app/domain/horarios_grupo_funcional.py`).

Re-exporta funciones de `db.queries.horarios_grupo_funcional` para que
`app/web/horarios_gf_bp.py` no importe `db` directamente (regla del
ADR-0001: app/web/* solo importa de app/domain/*).
"""
from __future__ import annotations

from db.queries.horarios_grupo_funcional import (
    asignar_horario_default_grupo,
    asignar_override_horario_persona,
    asignar_persona_a_grupo_funcional,
    cerrar_vinculo_persona_grupo_funcional,
    listar_grupos_funcionales_de_persona,
    listar_horarios_default_grupo,
    listar_overrides_horario_persona,
    resolver_horario_vigente,
)
from db.queries.horarios import listar_horarios

__all__ = [
    "asignar_horario_default_grupo",
    "asignar_override_horario_persona",
    "asignar_persona_a_grupo_funcional",
    "cerrar_vinculo_persona_grupo_funcional",
    "listar_grupos_funcionales_de_persona",
    "listar_horarios_default_grupo",
    "listar_horarios",
    "listar_overrides_horario_persona",
    "resolver_horario_vigente",
]