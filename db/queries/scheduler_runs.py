"""
Persistencia del historial de corridas del scheduler (`db.queries.scheduler_runs`).

Tabla objetivo (migración 0009): `public.scheduler_runs`.
Cada corrida del scheduler (sync nocturna, sync incremental, backup diario) deja
una fila con inicio, fin, ok, contadores y detalle.

Esta capa NUNCA importa de `app/*` ni de Flask (regla ADR-0001).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text

from db.connection import get_engine


def registrar_run(
    job: str,
    tenant_slug: Optional[str],
    inicio: datetime,
    fin: datetime,
    ok: bool,
    descargados: Optional[int],
    insertados: Optional[int],
    detalle: Optional[str],
) -> None:
    """
    Inserta una fila en `public.scheduler_runs`.

    Args:
        job: identificador del job (`sync_nocturna`, `sync_incremental`,
            `backup_diario`, etc.).
        tenant_slug: schema del tenant procesado, o None para jobs globales
            (ej. backup_diario).
        inicio: timestamp de inicio de la corrida.
        fin: timestamp de fin de la corrida.
        ok: True si la corrida fue exitosa.
        descargados: registros descargados del dispositivo (None para backup).
        insertados: registros nuevos insertados en la BD (None para backup).
        detalle: mensaje de error o ruta del archivo generado.
    """
    sql = text("""
        INSERT INTO public.scheduler_runs
            (job, tenant_slug, inicio, fin, ok, descargados, insertados, detalle)
        VALUES
            (:job, :tenant_slug, :inicio, :fin, :ok,
             :descargados, :insertados, :detalle)
    """)
    params = {
        "job": job,
        "tenant_slug": tenant_slug,
        "inicio": inicio,
        "fin": fin,
        "ok": ok,
        "descargados": descargados,
        "insertados": insertados,
        "detalle": detalle,
    }
    with get_engine().connect() as conn:
        conn.execute(sql, params)
        conn.commit()


def listar_ultimos(limit: int = 10) -> list[dict]:
    """
    Retorna las últimas `limit` corridas del scheduler (cualquier job),
    ordenadas por inicio DESC.
    """
    sql = text("""
        SELECT id, job, tenant_slug, inicio, fin, ok,
               descargados, insertados, detalle
        FROM public.scheduler_runs
        ORDER BY inicio DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]


def purgar_mayor_a(dias: int = 90) -> int:
    """
    Borra corridas con `inicio` más antiguo que `NOW() - INTERVAL '... dias'`.

    Retorna el número de filas borradas.
    """
    sql = text(f"""
        DELETE FROM public.scheduler_runs
        WHERE inicio < NOW() - INTERVAL '{int(dias)} days'
    """)
    with get_engine().connect() as conn:
        result = conn.execute(sql)
        conn.commit()
        return result.rowcount or 0