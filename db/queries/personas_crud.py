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
               c.nombre as categoria, c.id::text as categoria_id,
               pd.id_en_dispositivo as id_usuario_zk,
               pd.dispositivo_id::text as dispositivo_id_principal
        FROM personas p
        LEFT JOIN tipos_persona t ON p.tipo_persona_id = t.id
        LEFT JOIN grupos g ON p.grupo_id = g.id
        LEFT JOIN categorias c ON p.categoria_id = c.id
        LEFT JOIN LATERAL (
            SELECT id_en_dispositivo, dispositivo_id
            FROM personas_dispositivos
            WHERE persona_id = p.id AND activo = true
            ORDER BY es_principal DESC, creado_en ASC
            LIMIT 1
        ) pd ON true
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
                       c.nombre as categoria, c.id::text as categoria_id,
                       pd.id_en_dispositivo as id_usuario_zk
                FROM personas p
                LEFT JOIN tipos_persona t ON p.tipo_persona_id = t.id
                LEFT JOIN grupos g ON p.grupo_id = g.id
                LEFT JOIN categorias c ON p.categoria_id = c.id
                LEFT JOIN LATERAL (
                    SELECT id_en_dispositivo FROM personas_dispositivos
                    WHERE persona_id = p.id AND activo = true
                    ORDER BY es_principal DESC LIMIT 1
                ) pd ON true
                WHERE p.id = CAST(:id AS uuid)
            """),
            {"id": id},
        ).fetchone()
        return dict(row._mapping) if row else None


def _upsert_zk_id(conn, persona_id: str, id_usuario_zk: str | None) -> None:
    """Inserta o actualiza el ID del biométrico para la persona.
    Si id_usuario_zk es None o vacío, desactiva la entrada principal existente."""
    if id_usuario_zk:
        dev = conn.execute(
            text("SELECT id::text FROM dispositivos WHERE activo = true ORDER BY prioridad ASC LIMIT 1")
        ).fetchone()
        if not dev:
            return
        # Desactivar entrada principal previa de ESTA persona (para evitar dos principales)
        conn.execute(
            text("UPDATE personas_dispositivos SET es_principal = false WHERE persona_id = CAST(:pid AS uuid) AND es_principal = true"),
            {"pid": persona_id},
        )
        conn.execute(
            text("""
                INSERT INTO personas_dispositivos (persona_id, dispositivo_id, id_en_dispositivo, es_principal)
                VALUES (CAST(:pid AS uuid), CAST(:did AS uuid), :zk_id, true)
                ON CONFLICT (dispositivo_id, id_en_dispositivo)
                DO UPDATE SET persona_id = EXCLUDED.persona_id,
                              es_principal = true,
                              activo = true
            """),
            {"pid": persona_id, "did": dev[0], "zk_id": str(id_usuario_zk)},
        )
    else:
        conn.execute(
            text("UPDATE personas_dispositivos SET activo = false, es_principal = false WHERE persona_id = CAST(:pid AS uuid) AND es_principal = true"),
            {"pid": persona_id},
        )


def crear_persona(nombre: str, identificacion: str = None, tipo_persona_id: str = None,
                  grupo_id: str = None, categoria_id: str = None,
                  email: str = None, telefono: str = None, notas: str = None,
                  id_usuario_zk: str = None) -> dict:
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
        persona = dict(row._mapping)
        if id_usuario_zk:
            _upsert_zk_id(conn, persona["id"], id_usuario_zk)
        return persona


def actualizar_persona(id: str, datos: dict) -> dict | None:
    has_zk_update = "id_usuario_zk" in datos
    id_usuario_zk = datos.get("id_usuario_zk")
    datos_persona = {k: v for k, v in datos.items() if k != "id_usuario_zk"}

    allowed = {"nombre", "identificacion", "activo", "email", "telefono", "notas"}
    uuid_fields = {"tipo_persona_id", "grupo_id", "categoria_id"}
    sets, params = [], {"id": id}
    for k, v in datos_persona.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
        elif k in uuid_fields:
            sets.append(f"{k} = CAST(:{k} AS uuid)")
            params[k] = v

    with get_connection() as conn:
        result = None
        if sets:
            row = conn.execute(
                text(f"UPDATE personas SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) RETURNING id::text, nombre, identificacion, activo"),
                params,
            ).fetchone()
            result = dict(row._mapping) if row else None
        if has_zk_update:
            _upsert_zk_id(conn, id, id_usuario_zk or None)
    return result


def get_usuarios_zk_con_estado() -> list[dict]:
    """Retorna todos los usuarios registrados en usuarios_zk con su estado de vinculación a persona."""
    with get_connection() as conn:
        rows = conn.execute(text("""
            SELECT
                uz.id_usuario,
                uz.nombre AS nombre_zk,
                p.id::text AS persona_id,
                p.nombre AS persona_nombre,
                p.identificacion,
                pd.dispositivo_id::text AS dispositivo_id
            FROM usuarios_zk uz
            LEFT JOIN personas_dispositivos pd
                ON pd.id_en_dispositivo = uz.id_usuario AND pd.activo = true
            LEFT JOIN personas p ON p.id = pd.persona_id
            ORDER BY
                CASE WHEN uz.id_usuario ~ '^[0-9]+$' THEN uz.id_usuario::integer ELSE NULL END NULLS LAST,
                uz.id_usuario
        """)).fetchall()
        return [dict(r._mapping) for r in rows]


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
