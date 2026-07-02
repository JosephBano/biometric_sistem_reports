"""
Servicio de dominio para el scheduler (`app.domain.scheduler`).

Wrapper sobre `db.queries.scheduler_runs` para que `app/web/*` no importe
directamente de `db.queries/*` (regla del ADR-0001).

Fase 1 — Sync automática observable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from db.queries import scheduler_runs as _sr_queries


def registrar_corrida(
    job: str,
    tenant_slug: Optional[str],
    inicio: datetime,
    fin: datetime,
    ok: bool,
    descargados: Optional[int],
    insertados: Optional[int],
    detalle: Optional[str],
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