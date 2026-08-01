"""
Resolución canónica del horario aplicable a una persona (ADR-0003).

El plan original Tarea 3.2 preveía colocar `resolver_horario_vigente`
en `app/domain/schedule.py`, pero ese módulo está ocupado por el
scheduler de sincronización (refactor de Fase 4e del ADR-0001). Para
mantener la regla "1 módulo = 1 responsabilidad", esta función vive
en `app/domain/horarios_resolucion.py` y se re-exporta desde
`app/domain/horarios_grupo_funcional.py` por compat.

Esta función es el PUNTO ÚNICO de verdad para resolver el horario
vigente de una persona en una fecha. El motor de reportes
(`app/domain/reports.py`), el histórico de persona
(`app/web/people_bp.py`), y el blueprint de overrides
(`app/web/grupos_funcionales_bp.py`) deben consultar esta función —
nadie lee `asignaciones_horario` directamente para resolver el
"horario actual".

Precedencia (ADR-0003 r2 / P11):
  1. PERSONALIZADO       (overrides_horario_persona vigente)
  2. INDIVIDUAL_LEGACY   (asignaciones_horario 1:1, ciclo=1, vigente)
  3. DEFAULT_GRUPO       (horarios_default_grupo del gf principal
                          o desempate por `horario_desempate`)
  4. SIN_HORARIO         (no hay match)

Cuando el feature flag `horario_por_grupo=False`, cae al camino
legacy (paso 2) automáticamente; nunca degrada a "sin_horario"
sin haber agotado las opciones (R-A del ADR-0003).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.tenant import get_horario_por_grupo_enabled, get_horario_desempate
from db.queries.horarios_grupo_funcional import resolver_horario_vigente


def resolver_horario_vigente_para_persona(
    persona_id: str,
    fecha: date,
    *,
    feature_flag: Optional[bool] = None,
    horario_desempate: Optional[str] = None,
) -> dict:
    """API pública del dominio.

    Wrapper sobre `db.queries.horarios_grupo_funcional.resolver_horario_vigente`
    que aplica la lógica del feature flag per-tenant.

    Args:
        persona_id: UUID de la persona.
        fecha: Fecha del horario a resolver.
        feature_flag: Si `None`, lee de `tenant.configuracion`.
                       Si `True`, aplica la precedencia completa.
                       Si `False`, cae al legacy (paso 2).
        horario_desempate: Política de desempate cuando hay N grupos
                            funcionales activos sin `es_principal`.
                            `None` → lee de `tenant.configuracion`.

    Returns:
        dict con claves garantizadas:
          - plantilla_id:        str | None
          - plantilla:           dict | None
          - origen:              'personalizado' | 'individual_legacy'
                                 | 'default_grupo' | 'sin_horario'
          - override_id:         str | None
          - asignacion_legacy_id:str | None
          - grupo_funcional_id:  str | None
          - regla_desempate:     str | None
    """
    if feature_flag is None:
        feature_flag = get_horario_por_grupo_enabled()
    if horario_desempate is None:
        horario_desempate = get_horario_desempate()

    return resolver_horario_vigente(
        persona_id,
        fecha,
        feature_flag=feature_flag,
        horario_desempate=horario_desempate,
    )


__all__ = ["resolver_horario_vigente_para_persona"]
