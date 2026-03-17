"""
Queries de breaks_categorizados con compatibilidad total hacia atrás.
"""

from datetime import datetime, date
from sqlalchemy import text

from db.connection import get_connection
from db.queries.personas import resolver_persona_id, _get_dispositivo_id


def get_breaks_categorizados_dict(
    fecha_inicio: date = None, fecha_fin: date = None
) -> dict:
    """
    Retorna { id_usuario: { fecha_iso: [ {hora_inicio, hora_fin, ...} ] } }
    """
    with get_connection() as conn:
        params = {}
        where = ""
        if fecha_inicio and fecha_fin:
            where = "WHERE bc.fecha >= CAST(:fi AS date) AND bc.fecha <= CAST(:ff AS date)"
            params = {
                "fi": fecha_inicio.isoformat(),
                "ff": fecha_fin.isoformat(),
            }

        rows = conn.execute(
            text(f"""
                SELECT
                    COALESCE(pd.id_en_dispositivo, p.id::text) AS id_usuario,
                    TO_CHAR(bc.fecha, 'YYYY-MM-DD') AS fecha,
                    bc.hora_inicio::text,
                    bc.hora_fin::text,
                    bc.duracion_min,
                    bc.categoria,
                    bc.motivo,
                    bc.aprobado_por
                FROM breaks_categorizados bc
                JOIN personas p ON p.id = bc.persona_id
                LEFT JOIN personas_dispositivos pd
                    ON pd.persona_id = p.id AND pd.es_principal = true AND pd.activo = true
                {where}
                ORDER BY bc.fecha, bc.hora_inicio
            """),
            params,
        ).fetchall()

    res = {}
    for r in rows:
        uid = r[0]
        fec = r[1]
        if uid not in res:
            res[uid] = {}
        if fec not in res[uid]:
            res[uid][fec] = []
        # hora_inicio / hora_fin: timedelta o string → normalizar a HH:MM
        hi = _normalizar_hora(r[2])
        hf = _normalizar_hora(r[3])
        res[uid][fec].append({
            "id_usuario": uid,
            "fecha": fec,
            "hora_inicio": hi,
            "hora_fin": hf,
            "duracion_min": r[4],
            "categoria": r[5],
            "motivo": r[6],
            "aprobado_por": r[7],
        })
    return res


def _normalizar_hora(v) -> str | None:
    """Convierte timedelta, time object o string a 'HH:MM'."""
    if v is None:
        return None
    if isinstance(v, str):
        return v[:5]  # tomar HH:MM si viene con segundos
    if hasattr(v, "seconds"):
        # timedelta
        total = int(v.total_seconds())
        h, m = divmod(total // 60, 60)
        return f"{h:02d}:{m:02d}"
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    return str(v)


def insertar_break_categorizado(
    id_usuario,
    fecha,
    hora_inicio,
    hora_fin,
    categoria,
    motivo: str = "",
    aprobado_por: str = "",
):
    """Inserta o actualiza la categorización de un break."""
    duracion = None
    try:
        t1 = datetime.strptime(hora_inicio, "%H:%M")
        t2 = datetime.strptime(hora_fin, "%H:%M")
        duracion = int((t2 - t1).total_seconds() / 60)
    except Exception:
        pass

    with get_connection() as conn:
        dispositivo_id = _get_dispositivo_id(conn)
        persona_id, _ = resolver_persona_id(conn, str(id_usuario), None, dispositivo_id)

        conn.execute(
            text("""
                INSERT INTO breaks_categorizados
                    (persona_id, fecha, hora_inicio, hora_fin, duracion_min,
                     categoria, motivo, aprobado_por)
                VALUES (
                    CAST(:persona_id AS uuid), CAST(:fecha AS date),
                    CAST(:hora_inicio AS time), CAST(:hora_fin AS time), :duracion_min,
                    :categoria, :motivo, :aprobado_por
                )
                ON CONFLICT (persona_id, fecha, hora_inicio) DO UPDATE SET
                    hora_fin     = EXCLUDED.hora_fin,
                    duracion_min = EXCLUDED.duracion_min,
                    categoria    = EXCLUDED.categoria,
                    motivo       = EXCLUDED.motivo,
                    aprobado_por = EXCLUDED.aprobado_por
            """),
            {
                "persona_id": persona_id,
                "fecha": fecha,
                "hora_inicio": hora_inicio,
                "hora_fin": hora_fin,
                "duracion_min": duracion,
                "categoria": categoria,
                "motivo": motivo,
                "aprobado_por": aprobado_por,
            },
        )
