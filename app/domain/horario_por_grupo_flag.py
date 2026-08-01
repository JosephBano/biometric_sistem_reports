"""
Servicio de feature flag `horario_por_grupo` (ADR-0003, Tarea 4.3).

Permite al admin activar/desactivar el feature flag per-tenant desde la
UI (botón en `/admin/horarios-grupo-funcional/feature-flag`) o vía API
JSON. La activación dispara:

  1. `actualizar_configuracion_tenant(...)` en `public.tenants`.
  2. Audit log en `public.audit_log` (`accion='horario_por_grupo_activar'`
     o `..._desactivar'`).
  3. (Opcional) `preflight()` calcula counters antes de activar para
     mostrar al admin cuántas personas se verían afectadas.

Políticas de desempate aceptadas (`horario_desempate`):
  - 'prioridad'   — usa la `prioridad` del default (default seguro).
  - 'orden_grupo' — usa el `orden` del grupo funcional.
  - 'error'       — fuerza RuntimeError si hay ambigüedad sin principal.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from db.connection import get_connection
from db.queries.personas import listar_personas_para_filtros
from db.queries.horarios_grupo_funcional import (
    listar_grupos_funcionales_vigentes_para_persona,
    obtener_asignacion_legacy_vigente,
    obtener_override_vigente_para_persona,
)
from db import registrar_audit


POLITICAS_VALIDAS: set[str] = {"prioridad", "orden_grupo", "error"}


def set_horario_por_grupo_flag(
    *,
    tenant_id: str,
    usuario_id: str,
    ip: Optional[str],
    enabled: bool,
    horario_desempate: str = "prioridad",
    tenant_schema: Optional[str] = None,
    actualizar_configuracion_tenant_fn=None,
    registrar_audit_fn=None,
) -> dict:
    """Activa o desactiva el feature flag `horario_por_grupo` del tenant.

    Returns:
        dict con la nueva configuración.

    Raises:
        ValueError: si `horario_desempate` no es una política válida.
    """
    if horario_desempate not in POLITICAS_VALIDAS:
        raise ValueError(
            f"horario_desempate inválido: {horario_desempate!r}. "
            f"Permitidos: {sorted(POLITICAS_VALIDAS)}."
        )

    nueva_config = {
        "horario_por_grupo": bool(enabled),
        "horario_desempate": horario_desempate,
    }

    # Inyección de dependencias para evitar ciclos de import y para
    # facilitar testing. Si no se pasan, usar las del dominio.
    if actualizar_configuracion_tenant_fn is None:
        # Import perezoso para evitar ciclos: app.domain.admin importa
        # indirectamente db.queries.auth.
        from app.domain.admin import actualizar_tenant
        # actualizar_tenant(tenant_id, {configuracion: ...}) requiere un
        # dict de cambios del tenant. Fusionar la nueva sub-llave
        # `configuracion` requiere `actualizar_tenant` o un helper
        # específico. Por simplicidad, escribir via SQL directo.
        if tenant_schema is None:
            import os
            tenant_schema = os.environ.get("TENANT_DEFAULT", "istpet")

        with get_connection("public") as conn:
            row = conn.execute(
                text("""
                    UPDATE public.tenants
                    SET configuracion = configuracion || CAST(:cfg AS jsonb)
                    WHERE id = CAST(:tid AS uuid)
                    RETURNING id::text, slug, nombre, configuracion
                """),
                {
                    "tid": tenant_id,
                    "cfg": (
                        f'{{"horario_por_grupo": {str(enabled).lower()}, '
                        f'"horario_desempate": "{horario_desempate}"}}'
                    ),
                },
            ).fetchone()
        actualizado = dict(row._mapping) if row else None
    else:
        actualizado = actualizar_configuracion_tenant_fn(
            tenant_id, nueva_config
        )

    # Audit log (idempotente, no rompe la operación si falla).
    audit_fn = registrar_audit_fn if registrar_audit_fn is not None else registrar_audit

    try:
        audit_fn(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            accion=(
                "horario_por_grupo_activar" if enabled
                else "horario_por_grupo_desactivar"
            ),
            entidad="public.tenants",
            entidad_id=tenant_id,
            detalle={
                "horario_por_grupo": bool(enabled),
                "horario_desempate": horario_desempate,
            },
            ip=ip,
        )
    except Exception:  # noqa: BLE001
        # No fallar la operación por un error de auditoría.
        pass

    return actualizado or {"configuracion": nueva_config}


def preflight(
    *,
    tenant_id: str,
    fecha: Optional[date] = None,
    activo: bool = True,
) -> dict:
    """Calcula counters para el modal de activación.

    Útil para mostrar al admin qué pasarías si activa el flag:
      - `personas_activas`: total de personas activas en el tenant.
      - `con_horario_legacy`:   personas con asignación legacy 1:1 vigente.
      - `con_override`:        personas con override vigente.
      - `con_default_grupo`:    personas con gf y default vigente.
      - `sin_horario`:         personas sin horario (potencial gap).
      - `safe_to_enable`:      True si no hay personas sin horario Y
                               todas las personas tienen al menos
                               una capa (legacy, override, o default).

    Args:
        tenant_id: UUID del tenant (uso para logging o filtros futuros).
        fecha:     Fecha a usar para "vigente". Default: hoy.
        activo:    Filtrar solo personas activas.

    Returns:
        dict con los counters calculados.
    """
    fecha = fecha or date.today()
    activas = listar_personas_para_filtros(activo=activo)

    con_legacy = []
    con_default = []
    con_override = []
    sin_horario = []

    for persona_id in activas:
        ov = obtener_override_vigente_para_persona(persona_id, fecha)
        if ov is not None:
            con_override.append(persona_id)
            continue
        legacy = obtener_asignacion_legacy_vigente(persona_id, fecha)
        if legacy is not None:
            con_legacy.append(persona_id)
            continue
        grupos = listar_grupos_funcionales_vigentes_para_persona(
            persona_id, fecha
        )
        if grupos:
            con_default.append(persona_id)
        else:
            sin_horario.append(persona_id)

    safe = (
        not sin_horario
        and len(con_legacy) + len(con_default) + len(con_override)
            == len(activas)
    )
    return {
        "personas_activas": len(activas),
        "con_horario_legacy": len(con_legacy),
        "con_default_grupo": len(con_default),
        "con_override": len(con_override),
        "sin_horario": len(sin_horario),
        "safe_to_enable": safe,
    }


__all__ = ["set_horario_por_grupo_flag", "preflight", "POLITICAS_VALIDAS"]
