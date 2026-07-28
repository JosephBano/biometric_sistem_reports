"""CRUD de grupos y grupos funcionales del tenant.

Convenciones:
  - `grupos`           → ubicación/departamento operativa (jerarquica).
  - `grupos_funcionales` → rol laboral que define el horario por defecto.
  - `tipos_persona`    → tipo de contrato institucional (Empleado/Practicante).

`grupos_funcionales` reemplaza al antiguo `categorias` (ADR-0003, Opción A).
"""
from sqlalchemy import text
from db.connection import get_connection


# ── Grupos (operativos) ────────────────────────────────────────────────────────

def listar_grupos(activo: bool = None) -> list[dict]:
    with get_connection() as conn:
        q = "SELECT id::text, nombre, tipo_grupo, activo, creado_en FROM grupos"
        params = {}
        if activo is not None:
            q += " WHERE activo = :activo"
            params["activo"] = activo
        q += " ORDER BY nombre"
        rows = conn.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]


def crear_grupo(nombre: str, tipo_grupo: str = "general") -> dict:
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO grupos (nombre, tipo_grupo)
                VALUES (:nombre, :tipo_grupo)
                RETURNING id::text, nombre, tipo_grupo, activo, creado_en
            """),
            {"nombre": nombre, "tipo_grupo": tipo_grupo},
        ).fetchone()
        return dict(row._mapping)


def actualizar_grupo(id: str, datos: dict) -> dict | None:
    allowed = {"nombre": str, "tipo_grupo": str, "activo": bool}
    sets, params = [], {"id": id}
    for k, v in datos.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return None
    with get_connection() as conn:
        row = conn.execute(
            text(f"UPDATE grupos SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) RETURNING id::text, nombre, tipo_grupo, activo"),
            params,
        ).fetchone()
        return dict(row._mapping) if row else None


# ── Grupos Funcionales (rol laboral / horario por defecto) ────────────────────

def listar_grupos_funcionales(
    tipo_persona_id: str = None, activo: bool = None,
) -> list[dict]:
    """Lista los grupos funcionales del tenant.

    `activo=None` (default) devuelve activos e inactivos, igual que
    `listar_grupos`.
    """
    with get_connection() as conn:
        q = """
            SELECT gf.id::text, gf.nombre, gf.activo, gf.tipo_persona_id::text,
                   t.nombre as tipo_persona_nombre
            FROM grupos_funcionales gf
            LEFT JOIN tipos_persona t ON gf.tipo_persona_id = t.id
        """
        where, params = [], {}
        if tipo_persona_id:
            where.append("gf.tipo_persona_id = CAST(:tipo_persona_id AS uuid)")
            params["tipo_persona_id"] = tipo_persona_id
        if activo is not None:
            where.append("gf.activo = :activo")
            params["activo"] = activo
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY gf.nombre"
        rows = conn.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]


def crear_grupo_funcional(nombre: str, tipo_persona_id: str = None) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO grupos_funcionales (nombre, tipo_persona_id)
                VALUES (:nombre, CAST(:tipo_persona_id AS uuid))
                RETURNING id::text, nombre, activo, tipo_persona_id::text
            """),
            {"nombre": nombre, "tipo_persona_id": tipo_persona_id},
        ).fetchone()
        return dict(row._mapping)


def actualizar_grupo_funcional(id: str, datos: dict) -> dict | None:
    allowed = {"nombre": str, "activo": bool}
    sets, params = [], {"id": id}
    for k, v in datos.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return None
    with get_connection() as conn:
        row = conn.execute(
            text(f"UPDATE grupos_funcionales SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) RETURNING id::text, nombre, activo"),
            params,
        ).fetchone()
        return dict(row._mapping) if row else None