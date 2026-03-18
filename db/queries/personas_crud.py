"""CRUD completo de personas para la UI de Fase 4."""

from sqlalchemy import text
from db.connection import get_connection


def listar_personas(tipo_persona_id: str = None, grupo_id: str = None,
                    activo: bool = True, busqueda: str = None) -> list[dict]:
    q = """
        SELECT p.id::text, p.nombre, p.identificacion, p.activo,
               p.email, p.telefono, p.notas,
               t.nombre as tipo_persona, t.id::text as tipo_persona_id,
               g.nombre as grupo, g.id::text as grupo_id,
               c.nombre as categoria, c.id::text as categoria_id
        FROM personas p
        LEFT JOIN tipos_persona t ON p.tipo_persona_id = t.id
        LEFT JOIN grupos g ON p.grupo_id = g.id
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE 1=1
    """
    params = {}
    if activo is not None:
        q += " AND p.activo = :activo"
        params["activo"] = activo
    if tipo_persona_id:
        q += " AND p.tipo_persona_id = CAST(:tipo_persona_id AS uuid)"
        params["tipo_persona_id"] = tipo_persona_id
    if grupo_id:
        q += " AND p.grupo_id = CAST(:grupo_id AS uuid)"
        params["grupo_id"] = grupo_id
    if busqueda:
        q += " AND (UPPER(p.nombre) LIKE UPPER(:busq) OR p.identificacion LIKE :busq)"
        params["busq"] = f"%{busqueda}%"
    q += " ORDER BY p.nombre"
    with get_connection() as conn:
        rows = conn.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]


def get_persona(id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT p.id::text, p.nombre, p.identificacion, p.activo,
                       p.email, p.telefono, p.notas,
                       t.nombre as tipo_persona, t.id::text as tipo_persona_id,
                       g.nombre as grupo, g.id::text as grupo_id,
                       c.nombre as categoria, c.id::text as categoria_id
                FROM personas p
                LEFT JOIN tipos_persona t ON p.tipo_persona_id = t.id
                LEFT JOIN grupos g ON p.grupo_id = g.id
                LEFT JOIN categorias c ON p.categoria_id = c.id
                WHERE p.id = CAST(:id AS uuid)
            """),
            {"id": id},
        ).fetchone()
        return dict(row._mapping) if row else None


def crear_persona(nombre: str, identificacion: str = None, tipo_persona_id: str = None,
                  grupo_id: str = None, categoria_id: str = None,
                  email: str = None, telefono: str = None, notas: str = None) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO personas (nombre, identificacion, tipo_persona_id,
                    grupo_id, categoria_id, email, telefono, notas)
                VALUES (:nombre, :identificacion, CAST(:tipo_persona_id AS uuid),
                        CAST(:grupo_id AS uuid), CAST(:categoria_id AS uuid),
                        :email, :telefono, :notas)
                RETURNING id::text, nombre, identificacion, activo
            """),
            {"nombre": nombre, "identificacion": identificacion or None,
             "tipo_persona_id": tipo_persona_id, "grupo_id": grupo_id,
             "categoria_id": categoria_id, "email": email,
             "telefono": telefono, "notas": notas},
        ).fetchone()
        return dict(row._mapping)


def actualizar_persona(id: str, datos: dict) -> dict | None:
    allowed = {"nombre", "identificacion", "activo", "email", "telefono", "notas"}
    uuid_fields = {"tipo_persona_id", "grupo_id", "categoria_id"}
    sets, params = [], {"id": id}
    for k, v in datos.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
        elif k in uuid_fields:
            sets.append(f"{k} = CAST(:{k} AS uuid)")
            params[k] = v
    if not sets:
        return None
    with get_connection() as conn:
        row = conn.execute(
            text(f"UPDATE personas SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) RETURNING id::text, nombre, identificacion, activo"),
            params,
        ).fetchone()
        return dict(row._mapping) if row else None


def get_historico_persona(identificacion: str) -> dict | None:
    """Busca una persona por identificación y retorna todos sus períodos históricos."""
    with get_connection() as conn:
        p_row = conn.execute(
            text("""
                SELECT p.id::text, p.nombre, p.identificacion,
                       t.nombre as tipo_persona, g.nombre as grupo
                FROM personas p
                LEFT JOIN tipos_persona t ON p.tipo_persona_id = t.id
                LEFT JOIN grupos g ON p.grupo_id = g.id
                WHERE p.identificacion = :ident
                LIMIT 1
            """),
            {"ident": identificacion},
        ).fetchone()
        if not p_row:
            return None
        persona = dict(p_row._mapping)

        periodos = conn.execute(
            text("""
                SELECT pv.id::text, pv.nombre, pv.fecha_inicio, pv.fecha_fin,
                       pv.estado,
                       gp.id::text as grupo_periodo_id
                FROM periodos_vigencia pv
                LEFT JOIN grupos_periodo gp ON (
                    gp.nombre = pv.nombre
                    AND gp.fecha_inicio = pv.fecha_inicio
                    AND (gp.fecha_fin = pv.fecha_fin OR (gp.fecha_fin IS NULL AND pv.fecha_fin IS NULL))
                )
                WHERE pv.persona_id = CAST(:pid AS uuid)
                ORDER BY pv.fecha_inicio DESC
            """),
            {"pid": persona["id"]},
        ).fetchall()
        persona["periodos"] = [dict(r._mapping) for r in periodos]
        return persona
