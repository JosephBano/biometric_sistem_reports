"""
Servicio de dominio para el scheduler (`app.domain.scheduler`).

Wrapper sobre `db.queries.scheduler_runs` para que `app/web/*` no importe
directamente de `db.queries/*` (regla del ADR-0001).

Fase 1 — Sync automática observable.
"""
from __future__ import annotations

from datetime import datetime

from db.queries import scheduler_runs as _sr_queries


def registrar_corrida(
    job: str,
    tenant_slug: str | None,
    inicio: datetime,
    fin: datetime,
    ok: bool,
    descargados: int | None,
    insertados: int | None,
    detalle: str | None,
) -> None:
    """Inserta una fila en `public.scheduler_runs`. Wrapper de `db.queries.scheduler_runs.registrar_run`."""
    _sr_queries.registrar_run(
        job=job,
        tenant_slug=tenant_slug,
        inicio=inicio,
        fin=fin,
        ok=ok,
        descargados=descargados,
        insertados=insertados,
        detalle=detalle,
    )


def listar_ultimas_corridas(limit: int = 10) -> list[dict]:
    """Retorna las últimas `limit` corridas del scheduler."""
    return _sr_queries.listar_ultimos(limit=limit)


def purgar_corridas_mayores_a(dias: int = 90) -> int:
    """Borra corridas con inicio más antiguo que `dias` días. Retorna filas borradas."""
    return _sr_queries.purgar_mayor_a(dias=dias)


def proxima_corrida() -> str | None:
    """
    ISO timestamp de la próxima corrida programada del scheduler `sync.py`,
    o `None` si el scheduler no está disponible/cargado.

    Encapsula el acceso a `sync.schedule` (paquete de terceros) para que
    `app/web/*` no importe el módulo legacy `sync` directamente (ADR-0001).
    """
    import sync as _sync_module

    if not _sync_module.SCHEDULE_DISPONIBLE:
        return None
    proximas = [j.next_run for j in _sync_module.schedule.get_jobs() if j.next_run]
    return min(proximas).isoformat() if proximas else None
