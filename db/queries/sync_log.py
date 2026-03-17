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
):
    """Registra el resultado de una sincronización."""
    with get_connection() as conn:
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
