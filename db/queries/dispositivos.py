"""
Consultas a la base de datos relacionadas a los dispositivos y su estado de sincronización.
"""
from sqlalchemy import text
from db.connection import get_connection

def get_dispositivos_activos():
    with get_connection() as conn:
        rows = conn.execute(text("SELECT * FROM dispositivos WHERE activo = true")).mappings().all()
        return [dict(r) for r in rows]

def get_dispositivo(dispositivo_id: str):
    with get_connection() as conn:
        r = conn.execute(
            text("SELECT * FROM dispositivos WHERE id = CAST(:id AS uuid)"), 
            {"id": dispositivo_id}
        ).mappings().first()
        return dict(r) if r else None

def actualizar_watermark(dispositivo_id: str, ultimo_id: str, ultima_fecha):
    with get_connection() as conn:
        conn.execute(
            text("""
                UPDATE dispositivos 
                SET watermark_ultimo_id = :ultimo_id, watermark_ultima_fecha = :ultima_fecha 
                WHERE id = CAST(:id AS uuid)
            """),
            {"id": dispositivo_id, "ultimo_id": str(ultimo_id), "ultima_fecha": ultima_fecha}
        )
        conn.commit()

def get_estado_sync_ui():
    """Retorna el progreso actual para todos los dispositivos en la UI"""
    with get_connection() as conn:
        rows = conn.execute(text("""
            SELECT e.*, d.nombre 
            FROM sync_estado e
            JOIN dispositivos d ON d.id = e.dispositivo_id
        """)).mappings().all()
        return {str(r["dispositivo_id"]): dict(r) for r in rows}

def actualizar_estado_sync_ui(dispositivo_id: str, estado: str, progreso: int = 0, registros_proc: int = 0, mensaje: str = None):
    with get_connection() as conn:
        conn.execute(text("""
            INSERT INTO sync_estado (dispositivo_id, estado, progreso_pct, registros_proc, mensaje, actualizado_en)
            VALUES (CAST(:id AS uuid), :estado, :progreso, :registros, :mensaje, NOW())
            ON CONFLICT (dispositivo_id) DO UPDATE SET
                estado = EXCLUDED.estado,
                progreso_pct = EXCLUDED.progreso_pct,
                registros_proc = EXCLUDED.registros_proc,
                mensaje = EXCLUDED.mensaje,
                actualizado_en = NOW()
        """), {
            "id": dispositivo_id,
            "estado": estado,
            "progreso": progreso,
            "registros": registros_proc,
            "mensaje": mensaje
        })
        conn.commit()

def upsert_dispositivo(data: dict) -> str:
    """Inserta o actualiza un dispositivo"""
    with get_connection() as conn:
        if data.get("id"):
            conn.execute(text("""
                UPDATE dispositivos SET 
                    nombre = :nombre, ip = :ip, puerto = :puerto, 
                    protocolo = :protocolo, tipo_driver = :tipo_driver, 
                    prioridad = :prioridad, timeout_seg = :timeout_seg,
                    activo = :activo
                    """ + (", password_enc = :password_enc" if data.get("password_enc") else "") + """
                WHERE id = CAST(:id AS uuid)
            """), data)
            conn.commit()
            return data["id"]
        else:
            row = conn.execute(text("""
                INSERT INTO dispositivos (nombre, ip, puerto, protocolo, tipo_driver, prioridad, timeout_seg, password_enc)
                VALUES (:nombre, :ip, :puerto, :protocolo, :tipo_driver, :prioridad, :timeout_seg, :password_enc)
                RETURNING id
            """), data).fetchone()
            conn.commit()
            return str(row[0])


def has_alerta_hoy(dispositivo_id: str) -> bool:
    """Retorna True si ya se envió una alerta hoy para este dispositivo."""
    with get_connection() as conn:
        r = conn.execute(text("""
            SELECT 1 FROM sync_log
            WHERE dispositivo_id = CAST(:id AS uuid)
              AND error_detalle = 'alerta_enviada'
              AND fecha_sync::date = CURRENT_DATE
            LIMIT 1
        """), {"id": dispositivo_id}).fetchone()
        return r is not None


def marcar_alerta_enviada(dispositivo_id: str) -> None:
    """Registra en sync_log que se envió una alerta hoy para este dispositivo."""
    with get_connection() as conn:
        conn.execute(text("""
            INSERT INTO sync_log (dispositivo_id, exito, error_detalle)
            VALUES (CAST(:id AS uuid), true, 'alerta_enviada')
        """), {"id": dispositivo_id})
        conn.commit()


def get_dispositivos_con_fallas_consecutivas(n: int = 3):
    """Obtiene dispositivos que fallaron las últimas N veces consecutivas."""
    # Para ser simple, veremos los ultimos N logs por dispositivo
    with get_connection() as conn:
        rows = conn.execute(text("""
            WITH UltimosLogs AS (
                SELECT dispositivo_id, exito, 
                       ROW_NUMBER() OVER(PARTITION BY dispositivo_id ORDER BY fecha_sync DESC) as rn
                FROM sync_log
            ),
            FallasConsecutivas AS (
                SELECT dispositivo_id
                FROM UltimosLogs
                WHERE rn <= :n AND exito = false
                GROUP BY dispositivo_id
                HAVING COUNT(*) = :n
            )
            SELECT d.* 
            FROM dispositivos d
            JOIN FallasConsecutivas f ON f.dispositivo_id = d.id
            WHERE d.activo = true
        """), {"n": n}).mappings().all()
        return [dict(r) for r in rows]
