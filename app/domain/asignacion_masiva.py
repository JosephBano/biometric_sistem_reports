"""
Asignación masiva con filtros combinables (ADR-0003, Tarea 4.2).

Permite aplicar un grupo funcional (o un override individual) a un
conjunto de personas seleccionadas por filtros:
  - `grupo_funcional_id`  → gf ya vigente de la persona
  - `grupo_id`            → persona.grupo_id (operativo)
  - `tipo_persona_id`     → persona.tipo_persona_id
  - `categoria_id`        → persona.categoria_id (compat)
  - `sede_id`             → persona.sede_id
  - `activo`              → estado de la persona

Operaciones (mutuamente excluyentes, controladas por `modo`):
  - `asignar_grupo_funcional`:  crea filas en `grupos_funcionales_personas`
                                  (idempotente por UNIQUE compuesto).
  - `crear_override`:           crea filas en `overrides_horario_persona`
                                  (también idempotente).

Adicional:
  - `cerrar_legacy_en_fecha=True`: cierra las `asignaciones_horario` 1:1
    vigentes del grupo destino a `fecha_inicio - 1`, para que el default
    de grupo "tome el control" en la nueva fecha (workflow de migración
    gradual).

Auditoría:
  - Inserta en `public.audit_log` con `accion='persona_grupo_funcional_asignar_masivo'`
    y `detalle={filtros, contadores}` por invocación (no por persona).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from db.connection import get_connection
from db.queries.personas import listar_personas_para_filtros


def aplicar_grupo_funcional_masivo(
    *,
    filtros: dict,
    grupo_funcional_id_destino: str,
    plantilla_id: Optional[str] = None,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    modo: str = "asignar_grupo_funcional",
    cerrar_legacy_en_fecha: bool = False,
    confirmar: bool = False,
    tenant_schema: Optional[str] = None,
) -> dict:
    """Aplica una asignación masiva con filtros combinables.

    Args:
        filtros:               dict con claves opcionales
                                (grupo_id, tipo_persona_id,
                                categoria_id, sede_id,
                                grupo_funcional_id).
        grupo_funcional_id_destino: UUID del gf a aplicar.
        plantilla_id:          Solo para `modo='crear_override'`.
        fecha_inicio:          Vigencia desde cuándo.
        fecha_fin:             Vigencia hasta cuándo (None = indefinida).
        modo:                  'asignar_grupo_funcional' | 'crear_override'.
        cerrar_legacy_en_fecha: Si True, cierra las asignaciones legacy 1:1
                                vigentes a `fecha_inicio - 1`.
        confirmar:             Debe ser True para ejecutar (safety net).
        tenant_schema:         Schema del tenant (default: TENANT_DEFAULT).

    Returns:
        dict con counters y `affected_persona_ids`.

    Raises:
        ValueError: si `confirmar=False` (la UI debe pedir preview
                     primero) o `modo` no soportado.
    """
    if not confirmar:
        raise ValueError(
            "Aplicación masiva requiere confirmar=True. "
            "Usar la vista de preview primero (Tarea 4.2)."
        )
    if modo not in ("asignar_grupo_funcional", "crear_override"):
        raise ValueError(f"modo inválido: {modo!r}")
    if modo == "crear_override" and not plantilla_id:
        raise ValueError(
            "modo='crear_override' requiere plantilla_id."
        )

    # 1) Listar personas afectadas por los filtros.
    persona_ids = listar_personas_para_filtros(
        grupo_id=filtros.get("grupo_id"),
        tipo_persona_id=filtros.get("tipo_persona_id"),
        categoria_id=filtros.get("categoria_id"),
        sede_id=filtros.get("sede_id"),
        grupo_funcional_id=filtros.get("grupo_funcional_id"),
    )

    membership_created = 0
    override_created = 0
    legacy_closed = 0
    legacy_shadowed = 0
    skipped = 0
    affected: list[str] = []

    if tenant_schema is None:
        import os
        tenant_schema = os.environ.get("TENANT_DEFAULT", "istpet")

    with get_connection(tenant_schema) as conn:
        for persona_id in persona_ids:
            # 1a) Detectar shadowing: ¿hay asignaciones_horario 1:1
            # vigentes que serán reemplazadas por el default?
            shadow_row = conn.execute(
                text("""
                    SELECT count(*) FROM asignaciones_horario
                    WHERE persona_id = CAST(:pid AS uuid)
                      AND ciclo_semanas = 1
                      AND fecha_inicio <= :fi
                      AND (fecha_fin IS NULL OR fecha_fin >= :fi)
                """),
                {"pid": persona_id, "fi": fecha_inicio},
            ).scalar() or 0
            if shadow_row > 0:
                legacy_shadowed += 1

            if modo == "asignar_grupo_funcional":
                # Idempotente: si ya tiene pgf vigente con mismo grupo,
                # skip.
                existing = conn.execute(
                    text("""
                        SELECT id FROM grupos_funcionales_personas
                        WHERE persona_id = CAST(:pid AS uuid)
                          AND grupo_funcional_id = CAST(:gf_id AS uuid)
                          AND fecha_inicio <= :fi
                          AND (fecha_fin IS NULL OR fecha_fin >= :fi)
                    """),
                    {
                        "pid": persona_id,
                        "gf_id": grupo_funcional_id_destino,
                        "fi": fecha_inicio,
                    },
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                conn.execute(
                    text("""
                        INSERT INTO grupos_funcionales_personas
                            (persona_id, grupo_funcional_id, fecha_inicio,
                             fecha_fin, es_principal, notas)
                        VALUES (CAST(:pid AS uuid), CAST(:gf_id AS uuid),
                                :fi, :ff, false, :notas)
                    """),
                    {
                        "pid": persona_id,
                        "gf_id": grupo_funcional_id_destino,
                        "fi": fecha_inicio,
                        "ff": fecha_fin,
                        "notas": filtros.get("notas"),
                    },
                )
                membership_created += 1
                affected.append(persona_id)
            elif modo == "crear_override":
                conn.execute(
                    text("""
                        INSERT INTO overrides_horario_persona
                            (persona_id, plantilla_id, fecha_inicio, fecha_fin,
                             notas)
                        VALUES (CAST(:pid AS uuid), CAST(:ph_id AS uuid),
                                :fi, :ff, :notas)
                        ON CONFLICT (persona_id, plantilla_id, fecha_inicio)
                        DO UPDATE SET fecha_fin = EXCLUDED.fecha_fin,
                                      notas = EXCLUDED.notas
                    """),
                    {
                        "pid": persona_id,
                        "ph_id": plantilla_id,
                        "fi": fecha_inicio,
                        "ff": fecha_fin,
                        "notas": filtros.get("notas"),
                    },
                )
                override_created += 1
                affected.append(persona_id)

            # 1b) Si pidieron cerrar legacy, hacerlo a fecha_inicio - 1.
            if cerrar_legacy_en_fecha and shadow_row > 0:
                fecha_cierre_legacy = date.fromordinal(
                    fecha_inicio.toordinal() - 1
                )
                result = conn.execute(
                    text("""
                        UPDATE asignaciones_horario
                        SET fecha_fin = :fc
                        WHERE persona_id = CAST(:pid AS uuid)
                          AND ciclo_semanas = 1
                          AND fecha_inicio <= :fi
                          AND (fecha_fin IS NULL OR fecha_fin >= :fi)
                    """),
                    {
                        "pid": persona_id,
                        "fi": fecha_inicio,
                        "fc": fecha_cierre_legacy,
                    },
                )
                # `rowcount` puede ser MagicMock (tests) o int (psycopg2).
                # Lo normalizamos defensivamente.
                rc = getattr(result, "rowcount", 0)
                try:
                    legacy_closed += int(rc)
                except (TypeError, ValueError):
                    pass

    # 2) Audit log de la operación masiva.
    try:
        from db import registrar_audit
        from flask import g, request

        tenant_id = g.get("tenant_id")
        usuario_id = g.get("usuario_id")
        ip = request.remote_addr
    except (RuntimeError, ImportError):
        tenant_id = None
        usuario_id = None
        ip = None

    try:
        registrar_audit(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            accion="persona_grupo_funcional_asignar_masivo",
            entidad="grupos_funcionales_personas",
            entidad_id=grupo_funcional_id_destino,
            detalle={
                "filtros": filtros,
                "modo": modo,
                "fecha_inicio": fecha_inicio.isoformat(),
                "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
                "cerrar_legacy_en_fecha": cerrar_legacy_en_fecha,
                "matched_count": len(persona_ids),
                "membership_created_count": membership_created,
                "override_created_count": override_created,
                "legacy_shadowed_count": legacy_shadowed,
                "legacy_closed_count": legacy_closed,
                "skipped_count": skipped,
            },
            ip=ip,
        )
    except Exception:  # noqa: BLE001
        # No fallar la operación por un error de auditoría.
        pass

    return {
        "matched_count": len(persona_ids),
        "membership_created_count": membership_created,
        "override_created_count": override_created,
        "legacy_shadowed_count": legacy_shadowed,
        "legacy_closed_count": legacy_closed,
        "skipped_count": skipped,
        "affected_persona_ids": affected,
    }


__all__ = ["aplicar_grupo_funcional_masivo"]
