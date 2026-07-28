"""
Queries para el modelo de horarios por grupo funcional (ADR-0003, Tarea 2).

Modelo de datos (4 tablas + id heredado):
  - grupos_funcionales                       (catálogo del tenant)
  - grupos_funcionales_personas              (N:M persona ↔ grupo funcional, con vigencia y `es_principal`)
  - horarios_default_grupo                   (default de plantilla por grupo funcional, con prioridad)
  - overrides_horario_persona               (override individual, con vigencia)

API canónica del resolver:
  - resolver_horario_vigente(persona_id, fecha, *, feature_flag, horario_desempate)
    → dict SIEMPRE (con `origen` ∈ {personalizado, individual_legacy,
      default_grupo, sin_horario}).

Precedencia (ADR-0003 r2 / P11):
  1. PERSONALIZADO        (overrides_horario_persona vigente)
  2. INDIVIDUAL_LEGACY    (asignaciones_horario 1:1, ciclo=1, vigente)
  3. DEFAULT_GRUPO        (horarios_default_grupo del gf principal
                          o desempate por tenant.configuracion['horario_desempate'])
  4. SIN_HORARIO          (no hay match; `origen='sin_horario'`)

Reglas arquitectónicas (no negociables):
  - Sin imports de `app/*` ni de Flask.
  - SQL parametrizado (psycopg2 / sqlalchemy.text).
  - Filtros `fecha_fin` en el WHERE (P12: NO en el índice).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from db.connection import get_connection
from db.queries.horarios import _row_to_horario_dict


# ═════════════════════════════════════════════════════════════════════════
# N:M persona ↔ grupo funcional
# ═════════════════════════════════════════════════════════════════════════


def listar_grupos_funcionales_de_persona(
    persona_id: str, schema: str | None = None,
) -> list[dict]:
    """Lista TODAS las asignaciones persona↔grupo funcional (vigentes o no).

    Para resolver el horario vigente en una fecha, use
    `listar_grupos_funcionales_vigentes_para_persona`.
    """
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT gfp.id::text, gfp.persona_id::text,
                       gfp.grupo_funcional_id::text,
                       gfp.fecha_inicio, gfp.fecha_fin, gfp.es_principal,
                       gfp.notas, gfp.creado_en,
                       gf.nombre AS grupo_funcional_nombre,
                       gf.orden AS orden_gf
                FROM grupos_funcionales_personas gfp
                JOIN grupos_funcionales gf ON gf.id = gfp.grupo_funcional_id
                WHERE gfp.persona_id = CAST(:pid AS uuid)
                ORDER BY gfp.es_principal DESC, gfp.fecha_inicio DESC
            """),
            {"pid": persona_id},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def listar_grupos_funcionales_vigentes_para_persona(
    persona_id: str, fecha: date, schema: str | None = None,
) -> list[dict]:
    """Lista los grupos funcionales activos para una persona en una fecha.

    El filtro `fecha_fin` se aplica en el WHERE (P12 del ADR: no se puede
    usar como predicado de índice parcial porque `>= CURRENT_DATE` no es
    inmutable).
    """
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT gfp.id::text, gfp.persona_id::text,
                       gfp.grupo_funcional_id::text,
                       gfp.fecha_inicio, gfp.fecha_fin, gfp.es_principal,
                       gf.nombre AS grupo_funcional_nombre,
                       gf.orden AS orden_gf
                FROM grupos_funcionales_personas gfp
                JOIN grupos_funcionales gf ON gf.id = gfp.grupo_funcional_id
                WHERE gfp.persona_id = CAST(:pid AS uuid)
                  AND gfp.fecha_inicio <= :fecha
                  AND (gfp.fecha_fin IS NULL OR gfp.fecha_fin >= :fecha)
                ORDER BY gfp.es_principal DESC, gf.orden ASC, gf.nombre ASC
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def asignar_persona_a_grupo_funcional(
    persona_id: str,
    grupo_funcional_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    es_principal: bool = False,
    notas: Optional[str] = None,
    schema: str | None = None,
) -> dict | None:
    """Asigna una persona a un grupo funcional con vigencia.

    Idempotente via UNIQUE (persona_id, grupo_funcional_id, fecha_inicio).
    Si `es_principal=True`, desmarca cualquier otro principal vigente de
    la misma persona (manteniendo la regla "1 principal activo").
    """
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        if es_principal:
            conn.execute(
                text("""
                    UPDATE grupos_funcionales_personas
                    SET es_principal = false
                    WHERE persona_id = CAST(:pid AS uuid)
                      AND es_principal = true
                """),
                {"pid": persona_id},
            )
        row = conn.execute(
            text("""
                INSERT INTO grupos_funcionales_personas
                    (persona_id, grupo_funcional_id, fecha_inicio, fecha_fin,
                     es_principal, notas)
                VALUES (CAST(:pid AS uuid), CAST(:gfid AS uuid),
                        :fi, :ff, :ep, :notas)
                ON CONFLICT (persona_id, grupo_funcional_id, fecha_inicio)
                DO NOTHING
                RETURNING id::text, persona_id::text, grupo_funcional_id::text,
                          fecha_inicio, fecha_fin, es_principal, notas
            """),
            {
                "pid": persona_id, "gfid": grupo_funcional_id,
                "fi": fecha_inicio, "ff": fecha_fin, "ep": es_principal,
                "notas": notas,
            },
        ).fetchone()
    return dict(row._mapping) if row else None


def cerrar_vinculo_persona_grupo_funcional(
    persona_id: str,
    grupo_funcional_id: str,
    fecha_fin: date,
    schema: str | None = None,
) -> bool:
    """Cierra la asignación poniendo `fecha_fin` (no DELETE: conserva histórico)."""
    schema = schema or _tenant_default()
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


def listar_personas_en_grupo_funcional(
    grupo_funcional_id: str, fecha: date, schema: str | None = None,
) -> list[str]:
    """Retorna los `persona_id` con un grupo funcional vigente en la fecha."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT gfp.persona_id::text
                FROM grupos_funcionales_personas gfp
                WHERE gfp.grupo_funcional_id = CAST(:gfid AS uuid)
                  AND gfp.fecha_inicio <= :fecha
                  AND (gfp.fecha_fin IS NULL OR gfp.fecha_fin >= :fecha)
            """),
            {"gfid": grupo_funcional_id, "fecha": fecha},
        ).fetchall()
    return [r[0] for r in rows]


# ═════════════════════════════════════════════════════════════════════════
# horarios_default_grupo
# ═════════════════════════════════════════════════════════════════════════


def listar_horarios_default_grupo(
    grupo_funcional_id: str, schema: str | None = None,
) -> list[dict]:
    """Lista TODOS los defaults (vigentes o no) de un grupo funcional."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text, hdg.grupo_funcional_id::text,
                       hdg.plantilla_id::text,
                       hdg.fecha_inicio, hdg.fecha_fin,
                       hdg.prioridad, hdg.notas,
                       ph.nombre AS plantilla_nombre,
                       gf.nombre AS grupo_funcional_nombre
                FROM horarios_default_grupo hdg
                JOIN grupos_funcionales gf ON gf.id = hdg.grupo_funcional_id
                JOIN plantillas_horario ph ON ph.id = hdg.plantilla_id
                WHERE hdg.grupo_funcional_id = CAST(:gfid AS uuid)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
            """),
            {"gfid": grupo_funcional_id},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def listar_horarios_vigentes_para_grupo_funcional(
    grupo_funcional_id: str, fecha: date, schema: str | None = None,
) -> list[dict]:
    """Lista los defaults vigentes de un grupo funcional en una fecha."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text, hdg.plantilla_id::text,
                       hdg.grupo_funcional_id::text,
                       hdg.fecha_inicio, hdg.fecha_fin, hdg.prioridad
                FROM horarios_default_grupo hdg
                WHERE hdg.grupo_funcional_id = CAST(:gfid AS uuid)
                  AND hdg.fecha_inicio <= :fecha
                  AND (hdg.fecha_fin IS NULL OR hdg.fecha_fin >= :fecha)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
            """),
            {"gfid": grupo_funcional_id, "fecha": fecha},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def resolver_default_para_grupos_funcionales(
    grupo_funcional_ids: list[str], fecha: date,
    schema: str | None = None,
) -> dict | None:
    """Dado N grupos funcionales activos para una persona en una fecha,
    retorna el default con mayor prioridad global entre los grupos.

    Returns:
        dict con `plantilla_id`, `grupo_funcional_id`, `prioridad`, `id` (hdg).
        None si ninguno tiene default vigente.
    """
    if not grupo_funcional_ids:
        return None
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT hdg.id::text AS id, hdg.plantilla_id,
                       hdg.grupo_funcional_id::text AS grupo_funcional_id,
                       hdg.prioridad, hdg.fecha_inicio
                FROM horarios_default_grupo hdg
                WHERE hdg.grupo_funcional_id = ANY(CAST(:gfids AS uuid[]))
                  AND hdg.fecha_inicio <= :fecha
                  AND (hdg.fecha_fin IS NULL OR hdg.fecha_fin >= :fecha)
                ORDER BY hdg.prioridad DESC, hdg.fecha_inicio DESC
                LIMIT 1
            """),
            {"gfids": grupo_funcional_ids, "fecha": fecha},
        ).fetchall()
    return dict(rows[0]._mapping) if rows else None


def crear_horario_default_grupo(
    grupo_funcional_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    prioridad: int = 0,
    notas: Optional[str] = None,
    schema: str | None = None,
) -> dict | None:
    """Crea un default para un grupo funcional. Idempotente por UNIQUE compuesto."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                INSERT INTO horarios_default_grupo
                    (grupo_funcional_id, plantilla_id, fecha_inicio, fecha_fin,
                     prioridad, notas)
                VALUES (CAST(:gfid AS uuid), CAST(:phid AS uuid),
                        :fi, :ff, :prioridad, :notas)
                ON CONFLICT (grupo_funcional_id, plantilla_id, fecha_inicio)
                DO NOTHING
                RETURNING id::text, grupo_funcional_id::text,
                          plantilla_id::text, fecha_inicio, fecha_fin,
                          prioridad, notas
            """),
            {
                "gfid": grupo_funcional_id, "phid": plantilla_id,
                "fi": fecha_inicio, "ff": fecha_fin,
                "prioridad": prioridad, "notas": notas,
            },
        ).fetchone()
    return dict(row._mapping) if row else None


def cerrar_horario_default_grupo(
    hdg_id: str, fecha_fin: date, schema: str | None = None,
) -> bool:
    """Cierra un default poniendo `fecha_fin` (no DELETE: conserva histórico)."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        result = conn.execute(
            text("""
                UPDATE horarios_default_grupo
                SET fecha_fin = :ff
                WHERE id = CAST(:id AS uuid)
                  AND fecha_fin IS NULL
            """),
            {"id": hdg_id, "ff": fecha_fin},
        )
    return result.rowcount > 0


# ═════════════════════════════════════════════════════════════════════════
# overrides_horario_persona
# ═════════════════════════════════════════════════════════════════════════


def listar_overrides_por_persona(
    persona_id: str, schema: str | None = None,
) -> list[dict]:
    """Lista TODOS los overrides (vigentes o no) de una persona."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT ohp.id::text, ohp.persona_id::text,
                       ohp.plantilla_id::text,
                       ohp.fecha_inicio, ohp.fecha_fin,
                       ohp.notas, ohp.creado_en,
                       ph.nombre AS plantilla_nombre
                FROM overrides_horario_persona ohp
                JOIN plantillas_horario ph ON ph.id = ohp.plantilla_id
                WHERE ohp.persona_id = CAST(:pid AS uuid)
                ORDER BY ohp.fecha_inicio DESC
            """),
            {"pid": persona_id},
        ).fetchall()
        return [dict(r._mapping) for r in rows]


def obtener_override_vigente_para_persona(
    persona_id: str, fecha: date, schema: str | None = None,
) -> dict | None:
    """Retorna el override vigente de una persona en una fecha, o None."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                SELECT ohp.id::text, ohp.persona_id::text,
                       ohp.plantilla_id::text,
                       ohp.fecha_inicio, ohp.fecha_fin,
                       ohp.notas, ohp.creado_por, ohp.creado_en
                FROM overrides_horario_persona ohp
                WHERE ohp.persona_id = CAST(:pid AS uuid)
                  AND ohp.fecha_inicio <= :fecha
                  AND (ohp.fecha_fin IS NULL OR ohp.fecha_fin >= :fecha)
                ORDER BY ohp.fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchone()
    return dict(row._mapping) if row else None


def crear_override_horario(
    persona_id: str,
    plantilla_id: str,
    fecha_inicio: date,
    fecha_fin: Optional[date] = None,
    notas: Optional[str] = None,
    creado_por: Optional[str] = None,
    schema: str | None = None,
) -> dict:
    """Crea un override por persona. Idempotente por UNIQUE compuesto."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                INSERT INTO overrides_horario_persona
                    (persona_id, plantilla_id, fecha_inicio, fecha_fin,
                     notas, creado_por)
                VALUES (CAST(:pid AS uuid), CAST(:phid AS uuid),
                        :fi, :ff, :notas, CAST(:creado_por AS uuid))
                ON CONFLICT (persona_id, plantilla_id, fecha_inicio)
                DO UPDATE SET notas = EXCLUDED.notas,
                              fecha_fin = EXCLUDED.fecha_fin
                RETURNING id::text, persona_id::text, plantilla_id::text,
                          fecha_inicio, fecha_fin, notas, creado_por
            """),
            {
                "pid": persona_id, "phid": plantilla_id,
                "fi": fecha_inicio, "ff": fecha_fin,
                "notas": notas, "creado_por": creado_por,
            },
        ).fetchone()
    return dict(row._mapping)


def cerrar_override_horario(
    ohp_id: str, fecha_fin: date, schema: str | None = None,
) -> bool:
    """Cierra el override poniendo `fecha_fin` (no DELETE)."""
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        result = conn.execute(
            text("""
                UPDATE overrides_horario_persona
                SET fecha_fin = :ff
                WHERE id = CAST(:id AS uuid)
                  AND fecha_fin IS NULL
            """),
            {"id": ohp_id, "ff": fecha_fin},
        )
    return result.rowcount > 0


# ═════════════════════════════════════════════════════════════════════════
# ASIGNACIONES HORARIO (legacy 1:1) - SOLO LECTURA por el resolver
# ═════════════════════════════════════════════════════════════════════════


def obtener_asignacion_legacy_vigente(
    persona_id: str, fecha: date, schema: str | None = None,
) -> dict | None:
    """Retorna la asignación legacy `ciclo_semanas=1` vigente, o None.

    El resolver usa esta función para el paso 2 de la precedencia
    (INDIVIDUAL_LEGACY). NO crea nuevas asignaciones aquí — esa es
    responsabilidad del importador `.obd/.csv`.
    """
    schema = schema or _tenant_default()
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                SELECT ah.id::text, ah.persona_id::text,
                       ah.plantilla_id::text,
                       ah.fecha_inicio, ah.fecha_fin
                FROM asignaciones_horario ah
                WHERE ah.persona_id = CAST(:pid AS uuid)
                  AND ah.ciclo_semanas = 1
                  AND ah.fecha_inicio <= :fecha
                  AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
                ORDER BY ah.fecha_inicio DESC
                LIMIT 1
            """),
            {"pid": persona_id, "fecha": fecha},
        ).fetchone()
    return dict(row._mapping) if row else None


# ═════════════════════════════════════════════════════════════════════════
# RESOLVER CANÓNICO — precedencia personalizada > legacy > default > sin
# ═════════════════════════════════════════════════════════════════════════


def resolver_horario_vigente(
    persona_id: str,
    fecha: date,
    *,
    feature_flag: bool = False,
    horario_desempate: str = "prioridad",
    schema: str | None = None,
) -> dict:
    """Resuelve el horario aplicable a una persona en una fecha.

    Precedencia (ADR-0003 r2 / P11):
      1. PERSONALIZADO     (overrides_horario_persona vigente)
      2. INDIVIDUAL_LEGACY (asignaciones_horario 1:1 vigente)
      3. DEFAULT_GRUPO     (default vigente del gf principal,
                            o desempate por `horario_desempate`)
      4. SIN_HORARIO       (no hay match)

    Returns:
        dict con claves garantizadas:
          - plantilla_id:        str | None
          - plantilla:           dict | None   (fila de plantillas_horario)
          - origen:              'personalizado' | 'individual_legacy'
                                 | 'default_grupo' | 'sin_horario'
          - override_id:         str | None (si origen='personalizado')
          - asignacion_legacy_id:str | None (si origen='individual_legacy')
          - grupo_funcional_id:  str | None (si origen='default_grupo')
          - regla_desempate:     str | None ('es_principal' | 'prioridad'
                                              | 'orden_grupo')
    """
    schema = schema or _tenant_default()

    def _vacio(origen_: str, **extras) -> dict:
        base = {
            "plantilla_id": None,
            "plantilla": None,
            "origen": origen_,
            "override_id": None,
            "asignacion_legacy_id": None,
            "grupo_funcional_id": None,
            "regla_desempate": None,
        }
        base.update(extras)
        return base

    # ── 1. PERSONALIZADO (override) ─────────────────────────────
    override = obtener_override_vigente_para_persona(persona_id, fecha, schema)
    if override is not None:
        plantilla = _cargar_plantilla(override["plantilla_id"], schema)
        return _vacio(
            "personalizado",
            plantilla_id=override["plantilla_id"],
            plantilla=plantilla,
            override_id=override["id"],
        )

    # ── 2. INDIVIDUAL LEGACY (asignaciones_horario 1:1) ──────────
    legacy = obtener_asignacion_legacy_vigente(persona_id, fecha, schema)
    if legacy is not None:
        plantilla = _cargar_plantilla(legacy["plantilla_id"], schema)
        return _vacio(
            "individual_legacy",
            plantilla_id=legacy["plantilla_id"],
            plantilla=plantilla,
            asignacion_legacy_id=legacy["id"],
        )

    # ── 3. DEFAULT_GRUPO (gf principal o desempate por config) ──
    grupos = listar_grupos_funcionales_vigentes_para_persona(
        persona_id, fecha, schema
    )
    if not grupos:
        return _vacio("sin_horario")

    if any(g["es_principal"] for g in grupos):
        # Hay un grupo principal vigente → usar SOLO ese.
        principales = [g for g in grupos if g["es_principal"]]
        gf_ids = [principales[0]["grupo_funcional_id"]]
        regla = "es_principal"
    elif horario_desempate == "error":
        ids = [g["grupo_funcional_id"] for g in grupos]
        raise RuntimeError(
            f"Ambigüedad: persona {persona_id} tiene N grupos "
            f"funcionales sin principal y horario_desempate='error'. "
            f"Grupos: {ids}."
        )
    else:
        # Pasamos TODOS los gf al resolver_para_grupos para que elija el
        # de mayor prioridad global entre los grupos.
        gf_ids = [g["grupo_funcional_id"] for g in grupos]
        regla = horario_desempate

    default = resolver_default_para_grupos_funcionales(gf_ids, fecha, schema)
    if default is None:
        return _vacio("sin_horario")

    plantilla = _cargar_plantilla(default["plantilla_id"], schema)
    return _vacio(
        "default_grupo",
        plantilla_id=default["plantilla_id"],
        plantilla=plantilla,
        grupo_funcional_id=default["grupo_funcional_id"],
        regla_desempate=regla,
    )


# ═════════════════════════════════════════════════════════════════════════
# Helpers internos
# ═════════════════════════════════════════════════════════════════════════


def _tenant_default() -> str:
    """Schema por defecto del tenant actual.

    Si hay contexto Flask (`g.tenant_schema`), usa ese; si no, usa
    `os.environ['TENANT_DEFAULT']`. Esto permite llamadas fuera de
    request (background jobs, scripts) sin necesidad de pasar
    `schema` explícito.
    """
    import os
    try:
        from flask import g  # type: ignore
        schema = getattr(g, "tenant_schema", None)
        if schema:
            return schema
    except RuntimeError:
        pass
    return os.environ.get("TENANT_DEFAULT", "istpet")


def _cargar_plantilla(plantilla_id: str, schema: str) -> dict | None:
    """Carga la fila de `plantillas_horario` por ID y la convierte a dict.

    Devuelve None si la plantilla no existe (huérfano tras DELETE).
    """
    with get_connection(schema) as conn:
        row = conn.execute(
            text("SELECT * FROM plantillas_horario WHERE id = CAST(:id AS uuid)"),
            {"id": plantilla_id},
        ).fetchone()
    if row is None:
        return None
    return _row_to_horario_dict(row)


__all__ = [
    # persona_grupo_funcional
    "listar_grupos_funcionales_de_persona",
    "listar_grupos_funcionales_vigentes_para_persona",
    "asignar_persona_a_grupo_funcional",
    "cerrar_vinculo_persona_grupo_funcional",
    "listar_personas_en_grupo_funcional",
    # horarios_default_grupo
    "listar_horarios_default_grupo",
    "listar_horarios_vigentes_para_grupo_funcional",
    "resolver_default_para_grupos_funcionales",
    "crear_horario_default_grupo",
    "cerrar_horario_default_grupo",
    # horarios_override
    "listar_overrides_por_persona",
    "obtener_override_vigente_para_persona",
    "crear_override_horario",
    "cerrar_override_horario",
    # legacy (uso interno del resolver)
    "obtener_asignacion_legacy_vigente",
    # resolver canónico
    "resolver_horario_vigente",
]


# ═════════════════════════════════════════════════════════════════════════
# Aliases de compatibilidad con Fase 1 inicial
# ═════════════════════════════════════════════════════════════════════════
# El blueprint `app/web/horarios_gf_bp.py` (Fase 1) importaba los nombres
# verb-based `asignar_*`. Mantenerlos como alias no rompe la nueva API
# `crear_*` que requiere el plan (Tarea 4.1). En Fase 8 se migra el BP
# y se eliminan los alias.

asignar_horario_default_grupo = crear_horario_default_grupo
asignar_override_horario_persona = crear_override_horario

# Extender `__all__` con los aliases.
__all__ = list(__all__) + [
    "asignar_horario_default_grupo",
    "asignar_override_horario_persona",
]


# Aliases adicionales para compatibilidad con la Fase 1 original y para
# que `app/domain/horarios_grupo_funcional` no necesite reescritura en
# este commit. Si el plan lo renombra en Tar. 4.1, ajustamos el dominio.

listar_overrides_horario_persona = listar_overrides_por_persona

__all__ = list(__all__) + [
    "listar_overrides_horario_persona",
]
