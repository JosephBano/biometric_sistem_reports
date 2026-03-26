"""Queries de sync_log."""

from sqlalchemy import text
from db.connection import get_connection
from db.queries.personas import _get_dispositivo_id


def registrar_sync(
    fecha_inicio,
    fecha_fin,
    obtenidos: int,
    nuevos: int,
    exito: bool,
    error: str = None,
    registros_en_dispositivo: int = 0,
    dispositivo_id: str = None,
):
    """Registra el resultado de una sincronización."""
    with get_connection() as conn:
        if not dispositivo_id:
            dispositivo_id = _get_dispositivo_id(conn)
        conn.execute(
            text("""
                INSERT INTO sync_log (
                    dispositivo_id,
                    fecha_inicio_rango, fecha_fin_rango,
                    registros_obtenidos, registros_nuevos,
                    registros_en_dispositivo, exito, error_detalle
                ) VALUES (
                    CAST(:dispositivo_id AS uuid),
                    :fecha_inicio, :fecha_fin,
                    :obtenidos, :nuevos,
                    :en_dispositivo, :exito, :error
                )
            """),
            {
                "dispositivo_id": dispositivo_id,
                "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
                "obtenidos": obtenidos,
                "nuevos": nuevos,
                "en_dispositivo": registros_en_dispositivo,
                "exito": exito,
                "error": error,
            },
        )
        conn.commit()

def get_latest_sync_logs_por_dispositivo():
    """Obtiene el último sync_log de cada dispositivo activo."""
    with get_connection() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT ON (s.dispositivo_id)
                   s.dispositivo_id, s.fecha_sync, s.exito, s.registros_en_dispositivo
            FROM sync_log s
            JOIN dispositivos d ON s.dispositivo_id = d.id
            WHERE d.activo = true
            ORDER BY s.dispositivo_id, s.fecha_sync DESC
        """)).mappings().all()
        return {str(r["dispositivo_id"]): dict(r) for r in rows}
