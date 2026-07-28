"""
Lookup y gestión de personas y su vinculación con dispositivos ZK.

Traduce entre id_usuario (TEXT del ZK) ↔ persona_id (UUID de personas).
Esta traducción es el núcleo del cambio SQLite → PostgreSQL.
"""

from sqlalchemy import text
from db.connection import get_connection


def _get_dispositivo_id(conn) -> str | None:
    """Retorna el ID del dispositivo activo (primero encontrado). None si no hay ninguno."""
    row = conn.execute(
        text("SELECT id FROM dispositivos WHERE activo = true ORDER BY creado_en LIMIT 1")
    ).fetchone()
    return str(row[0]) if row else None


def resolver_persona_id(
    conn, id_usuario: str, nombre: str = None, dispositivo_id: str = None
) -> tuple[str, str]:
    """
    Dado un id_usuario del ZK, retorna (persona_id UUID, nombre canónico).
    Si la persona no existe, la crea automáticamente en personas + personas_dispositivos.
    """
    if dispositivo_id is None:
        dispositivo_id = _get_dispositivo_id(conn)

    row = conn.execute(
        text("""
            SELECT p.id, p.nombre
            FROM personas p
            JOIN personas_dispositivos pd ON pd.persona_id = p.id
            WHERE pd.id_en_dispositivo = :id_usuario
              AND (:dispositivo_id IS NULL OR pd.dispositivo_id = CAST(:dispositivo_id AS uuid))
              AND pd.activo = true
            ORDER BY pd.es_principal DESC
            LIMIT 1
        """),
        {"id_usuario": id_usuario, "dispositivo_id": dispositivo_id},
    ).fetchone()

    if row:
        return str(row[0]), row[1]

    return _crear_persona_desde_zk(conn, id_usuario, nombre or id_usuario, dispositivo_id)


def _crear_persona_desde_zk(
    conn, id_usuario: str, nombre: str, dispositivo_id: str = None
) -> tuple[str, str]:
    """
    Crea una persona mínima a partir de datos del ZK.
    Retorna (persona_id, nombre).
    """
    # Obtener el tipo_persona_id por defecto (primero activo)
    tipo_row = conn.execute(
        text("SELECT id FROM tipos_persona WHERE activo = true ORDER BY creado_en LIMIT 1")
    ).fetchone()
    tipo_id = str(tipo_row[0]) if tipo_row else None

    if tipo_id:
        persona_row = conn.execute(
            text("""
                INSERT INTO personas (nombre, tipo_persona_id)
                VALUES (:nombre, CAST(:tipo_id AS uuid))
                RETURNING id
            """),
            {"nombre": nombre, "tipo_id": tipo_id},
        ).fetchone()
    else:
        # Sin tipo configurado — crear persona sin tipo (debería evitarse en prod)
        persona_row = conn.execute(
            text("INSERT INTO personas (nombre) VALUES (:nombre) RETURNING id"),
            {"nombre": nombre},
        ).fetchone()

    persona_id = str(persona_row[0])

    # Crear vinculación con el dispositivo
    if dispositivo_id:
        conn.execute(
            text("""
                INSERT INTO personas_dispositivos
                    (persona_id, dispositivo_id, id_en_dispositivo, es_principal)
                VALUES (CAST(:persona_id AS uuid), CAST(:dispositivo_id AS uuid), :id_en_dispositivo, true)
                ON CONFLICT (dispositivo_id, id_en_dispositivo) DO NOTHING
            """),
            {
                "persona_id": persona_id,
                "dispositivo_id": dispositivo_id,
                "id_en_dispositivo": id_usuario,
            },
        )

    return persona_id, nombre


def id_usuario_from_persona(
    conn, persona_id: str, dispositivo_id: str = None
) -> str:
    """
    Dado un persona_id UUID, retorna el id_usuario TEXT del ZK (dispositivo principal).
    Retorna el persona_id como fallback si no hay vinculación.
    """
    if dispositivo_id is None:
        dispositivo_id = _get_dispositivo_id(conn)

    row = conn.execute(
        text("""
            SELECT id_en_dispositivo
            FROM personas_dispositivos
            WHERE persona_id = CAST(:persona_id AS uuid)
              AND (:dispositivo_id IS NULL OR dispositivo_id = CAST(:dispositivo_id AS uuid))
              AND activo = true
            ORDER BY es_principal DESC
            LIMIT 1
        """),
        {"persona_id": persona_id, "dispositivo_id": dispositivo_id},
    ).fetchone()
    return row[0] if row else persona_id


def upsert_usuarios(usuarios: list[dict], dispositivo_id: str = None):
    """
    Inserta o actualiza usuarios del dispositivo ZK en usuarios_zk y personas_dispositivos.
    Crea personas mínimas si no existen.
    """
    with get_connection() as conn:
        if not dispositivo_id:
            dispositivo_id = _get_dispositivo_id(conn)
        for u in usuarios:
            id_usuario = str(u["id_usuario"])
            nombre = str(u["nombre"]).strip()

            # Actualizar tabla espejo del dispositivo
            conn.execute(
                text("""
                    INSERT INTO usuarios_zk (id_usuario, nombre, privilegio, actualizado_en)
                    VALUES (:id_usuario, :nombre, :privilegio, NOW())
                    ON CONFLICT (id_usuario) DO UPDATE SET
                        nombre         = EXCLUDED.nombre,
                        privilegio     = EXCLUDED.privilegio,
                        actualizado_en = NOW()
                """),
                {
                    "id_usuario": id_usuario,
                    "nombre": nombre,
                    "privilegio": u.get("privilegio", 0),
                },
            )

            # Asegurar que existe la persona vinculada
            resolver_persona_id(conn, id_usuario, nombre, dispositivo_id)


def get_ids_usuarios_zk() -> set:
    """Retorna el conjunto de id_usuario registrados en usuarios_zk."""
    with get_connection() as conn:
        rows = conn.execute(text("SELECT id_usuario FROM usuarios_zk")).fetchall()
    return {row[0] for row in rows}


# ═════════════════════════════════════════════════════════════════════════
# Asignación masiva con filtros (ADR-0003, Tarea 4.2)
# ═════════════════════════════════════════════════════════════════════════


def listar_personas_para_filtros(
    *,
    grupo_id: str | None = None,
    tipo_persona_id: str | None = None,
    categoria_id: str | None = None,
    sede_id: str | None = None,
    grupo_funcional_id: str | None = None,
    activo: bool = True,
) -> list[str]:
    """Retorna persona_id de personas que matchean los filtros combinables.

    Filtros:
      - grupo_id            → persona.grupo_id (operativo/departamental)
      - tipo_persona_id     → persona.tipo_persona_id
      - categoria_id        → persona.categoria_id (compat legado)
      - sede_id             → persona.sede_id
      - grupo_funcional_id  → la persona tiene un gf vigente (hoy)
      - activo             → filtra por estado de la persona

    Si no se pasa ningún filtro (todos None), retorna TODAS las
    personas activas (uso de admin para "aplicar a todos").

    Returns:
        Lista de `persona_id` (TEXT, uuid como string) ordenadas por nombre.
    """
    from datetime import date as _date

    where_clauses = ["p.activo = :activo"]
    params: dict = {"activo": activo}

    if grupo_id:
        where_clauses.append("p.grupo_id = CAST(:grupo_id AS uuid)")
        params["grupo_id"] = grupo_id
    if tipo_persona_id:
        where_clauses.append("p.tipo_persona_id = CAST(:tipo_persona_id AS uuid)")
        params["tipo_persona_id"] = tipo_persona_id
    if categoria_id:
        where_clauses.append("p.categoria_id = CAST(:categoria_id AS uuid)")
        params["categoria_id"] = categoria_id
    if sede_id:
        where_clauses.append("p.sede_id = CAST(:sede_id AS uuid)")
        params["sede_id"] = sede_id

    where_sql = " AND ".join(where_clauses)
    hoy = _date.today().isoformat()

    if grupo_funcional_id:
        where_sql += """
            AND EXISTS (
                SELECT 1 FROM grupos_funcionales_personas pgf
                WHERE pgf.persona_id = p.id
                  AND pgf.grupo_funcional_id = CAST(:gf_id AS uuid)
                  AND pgf.fecha_inicio <= :hoy
                  AND (pgf.fecha_fin IS NULL OR pgf.fecha_fin >= :hoy)
            )
        """
        params["gf_id"] = grupo_funcional_id
        params["hoy"] = hoy

    sql = f"""
        SELECT p.id::text
        FROM personas p
        WHERE {where_sql}
        ORDER BY p.nombre, p.id
    """

    with get_connection() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [r[0] for r in rows]


__all__ = [
    "resolver_persona_id",
    "id_usuario_from_persona",
    "upsert_usuarios",
    "get_ids_usuarios_zk",
    "listar_personas_para_filtros",
]
