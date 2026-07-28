"""
Consultas y helpers para la vista analítica de entradas/salidas por persona
(`db/queries/asistencias_entradas_salidas.py`).

Caso de uso: requisito `docs/superpowers/specs/2026-07-27-requisito-analitica-grupo-funcional.md`.
NO depende del ADR 0003 (modelo de horarios por grupo funcional). Cuando ese
ADR esté aplicado, las queries contra `persona_grupos_funcionales` empiezan
a tener sentido (filtrado por grupo funcional vigente).

API pública:
  - `normalizar_tipo_marcacion(raw)`             → helper puro (testeable sin BD)
  - `grupos_funcionales_disponibles(schema)`     → bool (lee information_schema)
  - `listar_marcaciones_por_persona(...)`        → list[dict]
  - `contar_marcaciones_por_persona(...)`        → int
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from db.connection import get_connection, validate_schema_name


# Mapeo canónico de valores crudos a tipo normalizado.
# El ZK típicamente envía 0 (entrada) / 1 (salida) en punch_raw, mientras
# que el campo `tipo` puede venir como "entrada"/"salida" o "ENTRADA"/"SALIDA"
# dependiendo del driver. Mantenemos una tabla explícita en vez de heurísticas.
_TIPO_CANONICO = {
    "entrada": "entrada",
    "in": "entrada",
    "check-in": "entrada",
    "check_in": "entrada",
    "0": "entrada",
    "1": "salida",
    "salida": "salida",
    "out": "salida",
    "check-out": "salida",
    "check_out": "salida",
}


def normalizar_tipo_marcacion(raw: Optional[str]) -> str:
    """
    Convierte el valor crudo de `asistencias.tipo` en uno de: `"entrada"`,
    `"salida"`, `"otro"`.

    - Compara en minúsculas con strip.
    - Si el valor no está en el mapeo canónico → `"otro"` (defensivo).
    - NO lanza excepciones; siempre retorna string.
    """
    if raw is None:
        return "otro"
    key = str(raw).strip().lower()
    if not key:
        return "otro"
    return _TIPO_CANONICO.get(key, "otro")


def grupos_funcionales_disponibles(schema: str = None) -> bool:
    """
    Detecta si la tabla `persona_grupos_funcionales` existe en el schema
    del tenant (vía information_schema). Usado para habilitar o no el
    filtro por grupo funcional en la UI de analitica.

    Fail-safe: si la conexion falla (BD no disponible, schema inexistente),
    retorna False. Asi nunca se ofrece un filtro que daria error.
    """
    schema = schema or "istpet"
    try:
        schema = validate_schema_name(schema)
    except ValueError:
        return False
    try:
        with get_connection(schema) as conn:
            row = conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = :schema
                          AND table_name = 'persona_grupos_funcionales'
                    )
                """),
                {"schema": schema},
            ).fetchone()
            return bool(row[0]) if row else False
    except Exception:  # noqa: BLE001
        return False


def listar_marcaciones_por_persona(
    persona_id: str,
    fecha_inicio: date,
    fecha_fin: date,
    page: int = 1,
    per_page: int = 50,
    schema: str = None,
) -> list[dict]:
    """
    Lista las marcaciones de una persona en un rango, paginadas server-side.
    Retorna dicts con: id_usuario, nombre, fecha_hora, fecha, hora, tipo_norm.

    Rango semiabierto: [fecha_inicio 00:00 UTC, fecha_fin+1 00:00 UTC).
    """
    schema = schema or "istpet"
    schema = validate_schema_name(schema)
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 50
    if per_page > 200:
        per_page = 200
    offset = (page - 1) * per_page
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT
                    COALESCE(pd.id_en_dispositivo, p.id::text) AS id_usuario,
                    p.nombre,
                    a.fecha_hora,
                    a.tipo,
                    a.fuente,
                    a.dispositivo_id::text AS dispositivo_id
                FROM asistencias a
                JOIN personas p ON p.id = a.persona_id
                LEFT JOIN personas_dispositivos pd
                    ON pd.persona_id = p.id AND pd.es_principal = true AND pd.activo = true
                WHERE a.persona_id = CAST(:persona_id AS uuid)
                  AND a.fecha_hora >= :inicio AND a.fecha_hora < :fin
                ORDER BY a.fecha_hora ASC
                LIMIT :limit OFFSET :offset
            """),
            {
                "persona_id": persona_id,
                "inicio": inicio_str,
                "fin": fin_str,
                "limit": per_page,
                "offset": offset,
            },
        ).fetchall()
    out = []
    for r in rows:
        fh = r[2]
        if hasattr(fh, "tzinfo") and fh.tzinfo is not None:
            fh = fh.replace(tzinfo=None)
        out.append({
            "id_usuario": r[0] or "",
            "nombre": r[1],
            "datetime": fh,
            "fecha": fh.date() if hasattr(fh, "date") else fh,
            "hora": fh.time() if hasattr(fh, "time") else None,
            "tipo_norm": normalizar_tipo_marcacion(r[3]),
            "tipo_raw": r[3],
            "fuente": r[4],
            "dispositivo_id": r[5],
        })
    return out


def contar_marcaciones_por_persona(
    persona_id: str,
    fecha_inicio: date,
    fecha_fin: date,
    schema: str = None,
) -> int:
    schema = schema or "istpet"
    schema = validate_schema_name(schema)
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                SELECT count(*)
                FROM asistencias a
                WHERE a.persona_id = CAST(:persona_id AS uuid)
                  AND a.fecha_hora >= :inicio AND a.fecha_hora < :fin
            """),
            {"persona_id": persona_id, "inicio": inicio_str, "fin": fin_str},
        ).fetchone()
        return int(row[0]) if row else 0


__all__ = [
    "normalizar_tipo_marcacion",
    "grupos_funcionales_disponibles",
    "listar_marcaciones_por_persona",
    "contar_marcaciones_por_persona",
]