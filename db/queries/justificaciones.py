"""
Queries de justificaciones con compatibilidad total hacia atrás.

La firma pública usa id_usuario (TEXT) como en el sistema SQLite.
Internamente almacena persona_id (UUID).
"""

from sqlalchemy import text
from db.connection import get_connection
from db.queries.personas import resolver_persona_id, id_usuario_from_persona, _get_dispositivo_id

_SELECT_COLS = """
    j.id,
    COALESCE(pd.id_en_dispositivo, p.id::text) AS id_usuario,
    p.nombre,
    TO_CHAR(j.fecha, 'YYYY-MM-DD') AS fecha,
    j.tipo, j.motivo, j.aprobado_por, j.hora_permitida::text, j.estado,
    j.duracion_permitida_min,
    j.hora_retorno_permiso::text,
    j.incluye_almuerzo,
    TO_CHAR(j.creado_en AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') AS creado_en,
    j.recuperable,
    TO_CHAR(j.fecha_recuperacion, 'YYYY-MM-DD') AS fecha_recuperacion,
    j.hora_recuperacion::text
"""

_FROM_JOINS = """
FROM justificaciones j
JOIN personas p ON p.id = j.persona_id
LEFT JOIN personas_dispositivos pd
    ON pd.persona_id = p.id AND pd.es_principal = true AND pd.activo = true
"""


def insertar_justificacion(
    id_usuario: str,
    nombre: str,
    fecha: str,
    tipo: str,
    motivo: str = "",
    aprobado_por: str = "",
    hora_permitida: str = None,
    estado: str = "aprobada",
    duracion_permitida_min: int = None,
    hora_retorno_permiso: str = None,
    incluye_almuerzo: int = 0,
    recuperable: int = 0,
    fecha_recuperacion: str = None,
    hora_recuperacion: str = None,
) -> dict:
    """Inserta o reemplaza una justificación. fecha debe ser 'YYYY-MM-DD'."""
    with get_connection() as conn:
        dispositivo_id = _get_dispositivo_id(conn)
        persona_id, _ = resolver_persona_id(conn, id_usuario, nombre, dispositivo_id)

        conn.execute(
            text("""
                INSERT INTO justificaciones (
                    persona_id, fecha, tipo, motivo, aprobado_por,
                    hora_permitida, estado, duracion_permitida_min,
                    hora_retorno_permiso, incluye_almuerzo,
                    recuperable, fecha_recuperacion, hora_recuperacion
                ) VALUES (
                    CAST(:persona_id AS uuid), :fecha, :tipo, :motivo, :aprobado_por,
                    CAST(:hora_permitida AS time), :estado, :duracion_permitida_min,
                    CAST(:hora_retorno_permiso AS time), :incluye_almuerzo,
                    :recuperable, CAST(:fecha_recuperacion AS date), CAST(:hora_recuperacion AS time)
                )
                ON CONFLICT (persona_id, fecha, tipo) DO UPDATE SET
                    motivo                 = EXCLUDED.motivo,
                    aprobado_por           = EXCLUDED.aprobado_por,
                    hora_permitida         = EXCLUDED.hora_permitida,
                    estado                 = EXCLUDED.estado,
                    duracion_permitida_min = EXCLUDED.duracion_permitida_min,
                    hora_retorno_permiso   = EXCLUDED.hora_retorno_permiso,
                    incluye_almuerzo       = EXCLUDED.incluye_almuerzo,
                    recuperable            = EXCLUDED.recuperable,
                    fecha_recuperacion     = EXCLUDED.fecha_recuperacion,
                    hora_recuperacion      = EXCLUDED.hora_recuperacion,
                    creado_en              = NOW()
            """),
            {
                "persona_id": persona_id,
                "fecha": fecha,
                "tipo": tipo,
                "motivo": motivo or "",
                "aprobado_por": aprobado_por or "",
                "hora_permitida": hora_permitida,
                "estado": estado,
                "duracion_permitida_min": duracion_permitida_min,
                "hora_retorno_permiso": hora_retorno_permiso,
                "incluye_almuerzo": bool(incluye_almuerzo),
                "recuperable": bool(recuperable),
                "fecha_recuperacion": fecha_recuperacion,
                "hora_recuperacion": hora_recuperacion,
            },
        )

        row = conn.execute(
            text(f"SELECT {_SELECT_COLS} {_FROM_JOINS} WHERE j.persona_id = CAST(:pid AS uuid) AND j.fecha = CAST(:fecha AS date) AND j.tipo = :tipo"),
            {"pid": persona_id, "fecha": fecha, "tipo": tipo},
        ).fetchone()

    return dict(row._mapping) if row else {}


def get_justificaciones(fecha_inicio=None, fecha_fin=None) -> list[dict]:
    """Retorna justificaciones en el rango de fechas (o todas si no se especifica)."""
    with get_connection() as conn:
        if fecha_inicio and fecha_fin:
            fi = fecha_inicio.strftime("%Y-%m-%d") if hasattr(fecha_inicio, "strftime") else fecha_inicio
            ff = fecha_fin.strftime("%Y-%m-%d") if hasattr(fecha_fin, "strftime") else fecha_fin
            rows = conn.execute(
                text(f"""
                    SELECT {_SELECT_COLS} {_FROM_JOINS}
                    WHERE j.fecha >= CAST(:fi AS date) AND j.fecha <= CAST(:ff AS date)
                    ORDER BY j.fecha, p.nombre
                """),
                {"fi": fi, "ff": ff},
            ).fetchall()
        else:
            rows = conn.execute(
                text(f"""
                    SELECT {_SELECT_COLS} {_FROM_JOINS}
                    ORDER BY j.fecha DESC, p.nombre
                """)
            ).fetchall()

    return [dict(r._mapping) for r in rows]


def get_justificaciones_dict(fecha_inicio=None, fecha_fin=None) -> dict:
    """Retorna justificaciones indexadas por (id_usuario, fecha_iso, tipo)."""
    lista = get_justificaciones(fecha_inicio, fecha_fin)
    return {(j["id_usuario"], j["fecha"], j["tipo"]): j for j in lista}


def get_justificaciones_pendientes() -> list:
    """Retorna justificaciones en estado 'pendiente'."""
    with get_connection() as conn:
        rows = conn.execute(
            text(f"""
                SELECT {_SELECT_COLS} {_FROM_JOINS}
                WHERE j.estado = 'pendiente'
                ORDER BY j.fecha, p.nombre
            """)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def actualizar_estado_justificacion(id_justificacion: int, estado: str) -> bool:
    """Cambia el estado de una justificación a 'aprobada' o 'rechazada'."""
    with get_connection() as conn:
        result = conn.execute(
            text("UPDATE justificaciones SET estado = :estado, creado_en = NOW() WHERE id = :id"),
            {"estado": estado, "id": id_justificacion},
        )
    return result.rowcount > 0


def eliminar_justificacion(id_justificacion: int) -> bool:
    """Elimina una justificación por su ID. Retorna True si existía."""
    with get_connection() as conn:
        result = conn.execute(
            text("DELETE FROM justificaciones WHERE id = :id"),
            {"id": id_justificacion},
        )
    return result.rowcount > 0


def get_justificacion_by_id(id_justificacion: int) -> dict:
    """Retorna los datos de una justificación por su ID."""
    with get_connection() as conn:
        row = conn.execute(
            text(f"SELECT {_SELECT_COLS} {_FROM_JOINS} WHERE j.id = :id"),
            {"id": id_justificacion},
        ).fetchone()
    return dict(row._mapping) if row else {}


def actualizar_justificacion_completa(id_justificacion: int, **campos) -> bool:
    """Actualiza campos específicos de una justificación de forma dinámica."""
    if not campos:
        return False

    permitidos = {
        "fecha", "tipo", "motivo", "aprobado_por", "hora_permitida", "estado",
        "duracion_permitida_min", "hora_retorno_permiso",
        "incluye_almuerzo", "recuperable", "fecha_recuperacion", "hora_recuperacion",
    }
    # Tipos que necesitan cast en PostgreSQL
    time_cols = {"hora_permitida", "hora_retorno_permiso", "hora_recuperacion"}
    date_cols = {"fecha", "fecha_recuperacion"}

    set_parts = []
    params = {"id": id_justificacion}

    for k, v in campos.items():
        if k not in permitidos:
            continue
        if k in time_cols:
            set_parts.append(f"{k} = :{k}::time")
        elif k in date_cols:
            set_parts.append(f"{k} = :{k}::date")
        else:
            set_parts.append(f"{k} = :{k}")
        params[k] = v

    if not set_parts:
        return False

    set_parts.append("creado_en = NOW()")
    query = f"UPDATE justificaciones SET {', '.join(set_parts)} WHERE id = :id"

    with get_connection() as conn:
        result = conn.execute(text(query), params)
    return result.rowcount > 0
