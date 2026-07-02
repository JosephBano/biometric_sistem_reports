"""
Persistencia del historial de corridas del scheduler (`db.queries.scheduler_runs`).

Tabla objetivo (migración 0009): `public.scheduler_runs`.
Cada corrida del scheduler (sync nocturna, sync incremental, backup diario) deja
una fila con inicio, fin, ok, contadores y detalle.

Esta capa NUNCA importa de `app/*` ni de Flask (regla ADR-0001).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from db.connection import get_engine

# Patrón de validación de tenant_slug (security A-3).
# Coincide con `validate_schema_name()` de db/connection.py: solo alfanumérico y `_`,
# empezando con letra. Cualquier otro valor es rechazado antes de tocar la BD.
_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_JOBS_VALIDOS = {"sync_nocturna", "sync_incremental", "backup_diario"}


def _validar_tenant_slug(slug: Optional[str]) -> Optional[str]:
    """Valida que tenant_slug (si presente) cumpla el patrón seguro.

    Retorna el slug validado, o None si el argumento era None.
    Lanza ValueError si el slug no es válido.
    """
    if slug is None:
        return None
    if not _SLUG_PATTERN.match(slug):
        raise ValueError(
            f"tenant_slug inválido: {slug!r}. Debe coincidir con { _SLUG_PATTERN.pattern }"
        )
    return slug


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
            (ej. backup_diario). Validado contra `_SLUG_PATTERN`.
        inicio: timestamp de inicio de la corrida.
        fin: timestamp de fin de la corrida.
        ok: True si la corrida fue exitosa.
        descargados: registros descargados del dispositivo (None para backup).
        insertados: registros nuevos insertados en la BD (None para backup).
        detalle: mensaje de error o ruta del archivo generado.

    Raises:
        ValueError: si `job` no es uno de los conocidos o `tenant_slug` no
            cumple el patrón seguro.
    """
    if job not in _JOBS_VALIDOS:
        raise ValueError(
            f"job inválido: {job!r}. Valores permitidos: {sorted(_JOBS_VALIDOS)}"
        )
    tenant_slug_validado = _validar_tenant_slug(tenant_slug)

    sql = text("""
        INSERT INTO public.scheduler_runs
            (job, tenant_slug, inicio, fin, ok, descargados, insertados, detalle)
        VALUES
            (:job, :tenant_slug, :inicio, :fin, :ok,
             :descargados, :insertados, :detalle)
    """)
    params = {
        "job": job,
        "tenant_slug": tenant_slug_validado,
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
    Borra corridas con `inicio` más antiguo que `NOW() - make_interval(days => :dias)`.

    Retorna el número de filas borradas.
    """
    if not isinstance(dias, int) or dias < 1:
        raise ValueError(f"dias debe ser int >= 1; recibí {dias!r}")

    sql = text(
        "DELETE FROM public.scheduler_runs "
        "WHERE inicio < NOW() - make_interval(days => :dias)"
    )
    with get_engine().connect() as conn:
        result = conn.execute(sql, {"dias": dias})
        conn.commit()
        return result.rowcount or 0