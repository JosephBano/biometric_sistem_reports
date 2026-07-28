"""
Queries para el modelo de horarios por grupo funcional (ADR-0003).

API:
  - listar_grupos_funcionales_de_persona(persona_id)
  - asignar_persona_a_grupo_funcional(persona_id, gf_id, fecha_inicio, es_principal)
  - cerrar_vinculo_persona_grupo_funcional(persona_id, gf_id, fecha_fin)
  - listar_horarios_default_grupo(gf_id)
  - asignar_horario_default_grupo(gf_id, plantilla_id, fecha_inicio, prioridad)
  - listar_overrides_horario_persona(persona_id)
  - asignar_override_horario_persona(persona_id, plantilla_id, fecha_inicio, fecha_fin)
  - resolver_horario_vigente(persona_id, fecha)  → dict o None

Precedencia (resolutor, de mayor a menor):
  1. override_horario_persona vigente en la fecha
  2. asignaciones_horario legacy (1:1 persona-plantilla) vigente
  3. horarios_default_grupo del grupo funcional principal de la persona
  4. sin_horario
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from db.connection import get_connection
from db.queries.horarios import _row_to_horario_dict


# ── N:M persona ↔ grupo funcional ─────────────────────────────────────────────

def listar_grupos_funcionales_de_persona(persona_id: str, schema: str = None) -> list[dict]:
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT gfp.id::text, gfp.persona_id::text, gfp.grupo_funcional_id::text,
                       gfp.fecha_inicio, gfp.fecha_fin, gfp.es_principal,
                       gf.nombre AS grupo_funcional_nombre,
                       gf.tipo_persona_id::text AS tipo_persona_id
                FROM grupos_funcionales_personas gfp
                JOIN grupos_funcionales gf ON gf.id = gfp.grupo_funcional_id
                WHERE gfp.persona_id = CAST(:pid AS uuid)
                ORDER BY gfp.es_principal DESC, gfp.fecha_inicio DESC
            """),
            {"pid": persona_id},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def asignar_persona_a_grupo_funcional(
    persona_id: str,
    grupo_funcional_id: str,
    fecha_inicio: date,
    es_principal: bool = False,
    schema: str = None,
) -> dict:
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        # Si es_principal=True, desmarcar el principal anterior.
        if es_principal:
            conn.execute(
                text("""
                    UPDATE grupos_funcionales_personas
                    SET es_principal = false
                    WHERE persona_id = CAST(:pid AS uuid) AND es_principal = true
                """),
                {"pid": persona_id},
            )
        row = conn.execute(
            text("""
                INSERT INTO grupos_funcionales_personas
                    (persona_id, grupo_funcional_id, fecha_inicio, es_principal)
                VALUES (CAST(:pid AS uuid), CAST(:gfid AS uuid), :fi, :ep)
                RETURNING id::text, persona_id::text, grupo_funcional_id::text,
                          fecha_inicio, fecha_fin, es_principal
            """),
            {"pid": persona_id, "gfid": grupo_funcional_id, "fi": fecha_inicio, "ep": es_principal},
        ).fetchone()
        return dict(row._mapping)


def cerrar_vinculo_persona_grupo_funcional(
    persona_id: str, grupo_funcional_id: str, fecha_fin: date, schema: str = None
) -> bool:
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        result = conn.execute(
            text("""
                UPDATE grupos_funcionales_personas
                SET fecha_fin = :ff
                WHERE persona_id = CAST(:pid AS uuid)
                  AND grupo_funcional_id = CAST(:gfid AS uuid)
                  AND fecha_fin IS NULL
            """),
            {"pid": persona_id, "gfid": grupo_funcional_id, "ff": fecha_fin},
        )
        return result.rowcount > 0


# ── horarios_default_grupo ────────────────────────────────────────────────────

def listar_horarios_default_grupo(grupo_funcional_id: str, schema: str = None) -> list[dict]:
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text, hdg.grupo_funcional_id::text, hdg.plantilla_id::text,
                       hdg.fecha_inicio, hdg.fecha_fin, hdg.prioridad, hdg.notas,
                       ph.nombre AS plantilla_nombre
                FROM horarios_default_grupo hdg
                JOIN plantillas_horario ph ON ph.id = hdg.plantilla_id
                WHERE hdg.grupo_funcional_id = CAST(:gfid AS uuid)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
            """),
            {"gfid": grupo_funcional_id},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def asignar_horario_default_grupo(
    grupo_funcional_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    prioridad: int = 0,
    schema: str = None,
) -> dict:
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                INSERT INTO horarios_default_grupo
                    (grupo_funcional_id, plantilla_id, fecha_inicio, prioridad)
                VALUES (CAST(:gfid AS uuid), CAST(:pid AS uuid), :fi, :prio)
                RETURNING id::text, grupo_funcional_id::text, plantilla_id::text,
                          fecha_inicio, fecha_fin, prioridad, notas
            """),
            {"gfid": grupo_funcional_id, "pid": plantilla_id, "fi": fecha_inicio, "prio": prioridad},
        ).fetchone()
        return dict(row._mapping)


# ── overrides_horario_persona ──────────────────────────────────────────────────

def listar_overrides_horario_persona(persona_id: str, schema: str = None) -> list[dict]:
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT ohp.id::text, ohp.persona_id::text, ohp.plantilla_id::text,
                       ohp.fecha_inicio, ohp.fecha_fin, ohp.notas,
                       ph.nombre AS plantilla_nombre
                FROM overrides_horario_persona ohp
                JOIN plantillas_horario ph ON ph.id = ohp.plantilla_id
                WHERE ohp.persona_id = CAST(:pid AS uuid)
                ORDER BY ohp.fecha_inicio DESC
            """),
            {"pid": persona_id},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def asignar_override_horario_persona(
    persona_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    schema: str = None,
) -> dict:
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                INSERT INTO overrides_horario_persona
                    (persona_id, plantilla_id, fecha_inicio, fecha_fin)
                VALUES (CAST(:pid AS uuid), CAST(:plid AS uuid), :fi, :ff)
                RETURNING id::text, persona_id::text, plantilla_id::text,
                          fecha_inicio, fecha_fin, notas
            """),
            {"pid": persona_id, "plid": plantilla_id, "fi": fecha_inicio, "ff": fecha_fin},
        ).fetchone()
        return dict(row._mapping)


# ── Resolutor canonico de horario vigente ──────────────────────────────────────

def resolver_horario_vigente(persona_id: str, fecha: date, schema: str = None) -> Optional[dict]:
    """
    Devuelve la plantilla de horario vigente para una persona en una fecha,
    segun la precedencia:
      1. override_horario_persona vigente
      2. asignaciones_horario legacy (1:1) vigente
      3. horarios_default_grupo del grupo funcional principal
      4. None (sin horario)
    """
    schema = schema or "istpet"
    with get_connection(schema) as conn:
        # 1. Override por persona
        row = conn.execute(
            text("""
                SELECT ph.*
                FROM overrides_horario_persona ohp
                JOIN plantillas_horario ph ON ph.id = ohp.plantilla_id
                WHERE ohp.persona_id = CAST(:pid AS uuid)
                  AND ohp.fecha_inicio <= CAST(:f AS date)
                  AND (ohp.fecha_fin IS NULL OR ohp.fecha_fin >= CAST(:f AS date))
                  AND ph.activo = true
                ORDER BY ohp.fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "f": fecha},
        ).fetchone()
        if row:
            d = _row_to_horario_dict(row)
            d["origen"] = "override_persona"
            return d

        # 2. Asignacion legacy 1:1
        row = conn.execute(
            text("""
                SELECT ph.*
                FROM asignaciones_horario ah
                JOIN plantillas_horario ph ON ph.id = ah.plantilla_id
                WHERE ah.persona_id = CAST(:pid AS uuid)
                  AND ah.ciclo_semanas = 1
                  AND ah.fecha_inicio <= CAST(:f AS date)
                  AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= CAST(:f AS date))
                  AND ph.activo = true
                ORDER BY ah.fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "f": fecha},
        ).fetchone()
        if row:
            d = _row_to_horario_dict(row)
            d["origen"] = "asignacion_legacy"
            return d

        # 3. Default del grupo funcional principal
        row = conn.execute(
            text("""
                SELECT ph.*
                FROM grupos_funcionales_personas gfp
                JOIN horarios_default_grupo hdg
                  ON hdg.grupo_funcional_id = gfp.grupo_funcional_id
                JOIN plantillas_horario ph ON ph.id = hdg.plantilla_id
                WHERE gfp.persona_id = CAST(:pid AS uuid)
                  AND gfp.es_principal = true
                  AND (gfp.fecha_fin IS NULL OR gfp.fecha_fin >= CAST(:f AS date))
                  AND gfp.fecha_inicio <= CAST(:f AS date)
                  AND hdg.fecha_inicio <= CAST(:f AS date)
                  AND (hdg.fecha_fin IS NULL OR hdg.fecha_fin >= CAST(:f AS date))
                  AND ph.activo = true
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "f": fecha},
        ).fetchone()
        if row:
            d = _row_to_horario_dict(row)
            d["origen"] = "default_grupo_funcional"
            return d

        return None


__all__ = [
    "listar_grupos_funcionales_de_persona",
    "asignar_persona_a_grupo_funcional",
    "cerrar_vinculo_persona_grupo_funcional",
    "listar_horarios_default_grupo",
    "asignar_horario_default_grupo",
    "listar_overrides_horario_persona",
    "asignar_override_horario_persona",
    "resolver_horario_vigente",
]