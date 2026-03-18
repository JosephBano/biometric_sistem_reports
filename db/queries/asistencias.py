"""
Queries de asistencias con compatibilidad total hacia atrás.

Internamente usa persona_id (UUID) pero las funciones públicas
siguen aceptando y retornando id_usuario (TEXT) como el sistema SQLite.
"""

from datetime import datetime, timedelta
from sqlalchemy import text

from db.connection import get_connection
from db.queries.personas import resolver_persona_id, _get_dispositivo_id


def insertar_asistencias(registros: list[dict], dispositivo_id: str = None) -> int:
    """
    Inserta registros ignorando duplicados (UNIQUE persona_id + fecha_hora).
    Retorna la cantidad de filas realmente insertadas.

    Cada registro debe tener: id_usuario, nombre, fecha_hora, tipo.
    Opcionales: punch_raw, fuente.
    """
    if not registros:
        return 0

    count = 0
    with get_connection() as conn:
        if not dispositivo_id:
            dispositivo_id = _get_dispositivo_id(conn)
        for r in registros:
            id_usuario = str(r["id_usuario"])
            nombre = r.get("nombre", id_usuario)

            persona_id, _ = resolver_persona_id(conn, id_usuario, nombre, dispositivo_id)

            # Resolver periodo_vigencia_id activo para la fecha
            fecha_dt = r["fecha_hora"]
            fecha_solo = fecha_dt.strftime("%Y-%m-%d") if hasattr(fecha_dt, "strftime") else str(fecha_dt)[:10]

            periodo_row = conn.execute(
                text("""
                    SELECT id FROM periodos_vigencia
                    WHERE persona_id = CAST(:persona_id AS uuid)
                      AND estado = 'activo'
                      AND fecha_inicio <= CAST(:fecha AS date)
                      AND (fecha_fin IS NULL OR fecha_fin >= CAST(:fecha AS date))
                    LIMIT 1
                """),
                {"persona_id": persona_id, "fecha": fecha_solo},
            ).fetchone()
            periodo_id = str(periodo_row[0]) if periodo_row else None

            result = conn.execute(
                text("""
                    INSERT INTO asistencias
                        (persona_id, periodo_vigencia_id, fecha_hora, punch_raw, tipo, fuente, dispositivo_id)
                    VALUES (
                        CAST(:persona_id AS uuid),
                        CAST(:periodo_id AS uuid),
                        CAST(:fecha_hora AS timestamptz),
                        :punch_raw,
                        :tipo,
                        :fuente,
                        CAST(:dispositivo_id AS uuid)
                    )
                    ON CONFLICT (persona_id, fecha_hora) DO NOTHING
                """),
                {
                    "persona_id": persona_id,
                    "periodo_id": periodo_id,
                    "fecha_hora": r["fecha_hora"],
                    "punch_raw": r.get("punch_raw"),
                    "tipo": r["tipo"],
                    "fuente": r.get("fuente", "zk"),
                    "dispositivo_id": dispositivo_id,
                },
            )
            count += result.rowcount
        conn.commit()

    return count


def consultar_asistencias(fecha_inicio, fecha_fin) -> list[dict]:
    """
    Retorna registros del rango en el formato que espera script.py:
    { id_usuario, nombre, datetime, fecha, hora, tipo }

    fecha_inicio y fecha_fin son objetos date.
    """
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"

    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    COALESCE(pd.id_en_dispositivo, p.id::text) AS id_usuario,
                    p.nombre,
                    a.fecha_hora,
                    a.tipo
                FROM asistencias a
                JOIN personas p ON p.id = a.persona_id
                LEFT JOIN personas_dispositivos pd
                    ON pd.persona_id = p.id AND pd.es_principal = true AND pd.activo = true
                WHERE a.fecha_hora >= :inicio AND a.fecha_hora < :fin
                ORDER BY p.nombre, a.fecha_hora
            """),
            {"inicio": inicio_str, "fin": fin_str},
        ).fetchall()

    registros = []
    for row in rows:
        fh = row[2]
        # PostgreSQL devuelve datetime aware; normalizamos a naive para script.py
        if hasattr(fh, "tzinfo") and fh.tzinfo is not None:
            fh = fh.replace(tzinfo=None)
        elif isinstance(fh, str):
            fh = datetime.fromisoformat(fh.replace("Z", "+00:00"))
            fh = fh.replace(tzinfo=None)
        registros.append({
            "id_usuario": row[0] or "",
            "nombre": row[1],
            "datetime": fh,
            "fecha": fh.date(),
            "hora": fh.time(),
            "tipo": row[3],
        })
    return registros


def get_personas(fecha_inicio, fecha_fin) -> list[str]:
    """Devuelve nombres únicos en el rango de fechas."""
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"

    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT p.nombre
                FROM asistencias a
                JOIN personas p ON p.id = a.persona_id
                WHERE a.fecha_hora >= :inicio AND a.fecha_hora < :fin
                ORDER BY p.nombre
            """),
            {"inicio": inicio_str, "fin": fin_str},
        ).fetchall()

    return [row[0] for row in rows]


def get_personas_con_id(fecha_inicio, fecha_fin) -> list[dict]:
    """
    Devuelve lista de {id_usuario, nombre} únicos en el rango de fechas.
    id_usuario es el ID del ZK (para compatibilidad con el frontend).
    """
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"

    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT ON (p.nombre)
                    COALESCE(pd.id_en_dispositivo, p.id::text) AS id_usuario,
                    p.nombre
                FROM asistencias a
                JOIN personas p ON p.id = a.persona_id
                LEFT JOIN personas_dispositivos pd
                    ON pd.persona_id = p.id AND pd.es_principal = true AND pd.activo = true
                WHERE a.fecha_hora >= :inicio AND a.fecha_hora < :fin
                ORDER BY p.nombre
            """),
            {"inicio": inicio_str, "fin": fin_str},
        ).fetchall()

    return [{"id_usuario": row[0], "nombre": row[1]} for row in rows]


def get_estado() -> dict:
    """Retorna estadísticas generales de la base de datos."""
    with get_connection() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM asistencias")).fetchone()[0]
        personas = conn.execute(
            text("SELECT COUNT(DISTINCT persona_id) FROM asistencias")
        ).fetchone()[0]
        ultima = conn.execute(
            text("""
                SELECT fecha_sync, registros_nuevos, exito, error_detalle,
                       registros_en_dispositivo
                FROM sync_log
                ORDER BY id DESC
                LIMIT 1
            """)
        ).fetchone()

    ultima_dict = None
    if ultima:
        ultima_dict = {
            "fecha_sync": str(ultima[0]) if ultima[0] else None,
            "registros_nuevos": ultima[1],
            "exito": bool(ultima[2]),
            "error_detalle": ultima[3],
            "registros_en_dispositivo": ultima[4] or 0,
        }

    return {
        "total_registros": total,
        "personas_en_db": personas,
        "ultima_sync": ultima_dict,
    }
