"""CRUD de grupos y categorías del tenant."""

from sqlalchemy import text
from db.connection import get_connection


# ── Grupos ────────────────────────────────────────────────────────────────────

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


# ── Categorías ────────────────────────────────────────────────────────────────

def listar_categorias(tipo_persona_id: str = None) -> list[dict]:
    with get_connection() as conn:
        q = """
            SELECT c.id::text, c.nombre, c.activo, c.tipo_persona_id::text,
                   t.nombre as tipo_persona_nombre
            FROM categorias c
            LEFT JOIN tipos_persona t ON c.tipo_persona_id = t.id
        """
        params = {}
        if tipo_persona_id:
            q += " WHERE c.tipo_persona_id = CAST(:tipo_persona_id AS uuid)"
            params["tipo_persona_id"] = tipo_persona_id
        q += " ORDER BY c.nombre"
        rows = conn.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]


def crear_categoria(nombre: str, tipo_persona_id: str = None) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO categorias (nombre, tipo_persona_id)
                VALUES (:nombre, CAST(:tipo_persona_id AS uuid))
                RETURNING id::text, nombre, activo, tipo_persona_id::text
            """),
            {"nombre": nombre, "tipo_persona_id": tipo_persona_id},
        ).fetchone()
        return dict(row._mapping)


def actualizar_categoria(id: str, datos: dict) -> dict | None:
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
            text(f"UPDATE categorias SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) RETURNING id::text, nombre, activo"),
            params,
        ).fetchone()
        return dict(row._mapping) if row else None
