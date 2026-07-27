"""
Wrapper para `sync` (`app.domain.schedule`).

Re-exporta la API pública de `sync.py` con la firma documentada en
`docs/ARQUITECTURA.md`. La idea es que las blueprints y tests importen
desde `app.domain.schedule` y nunca toquen el módulo top-level.

Decisión de diseño (transición):
  Mientras no se complete la migración total de `sync.py` → `app/domain/schedule.py`,
  este archivo es un **re-export** del módulo top-level. La firma se mantiene
  estable (ver tests/unit/test_schedule.py). El plan es mover la implementación
  física en una iteración posterior (Fase 4e del roadmap), preservando la API.

API pública:
  - `init_scheduler(app)`  — punto de entrada en la factory (sustituye a `iniciar_scheduler`)
  - `get_job_status(job_id)`
  - `ping_dispositivo(dispositivo_id=None) -> bool`
  - `sincronizar_con_reintento(...)`
  - `sincronizar(...)`
  - `limpiar_log_dispositivo(dispositivo_id) -> int`
"""
from __future__ import annotations

from sync import (
    _jobs,
    get_job_status,
    limpiar_log_dispositivo,
    ping_dispositivo,
    sincronizar,
    sincronizar_con_reintento,
    sincronizar_dispositivo,
    verificar_dispositivos_desconectados,
)

# Re-export del módulo top-level por ahora.
# TODO(Fase 4e): mover físicamente la implementación a este archivo y
#               eliminar la dependencia del módulo top-level.
from sync import (  # noqa: F401  (re-export)
    iniciar_scheduler as _legacy_iniciar_scheduler,
)


def init_scheduler(app) -> None:
    """
    Punto de entrada para la factory. Sustituye al `iniciar_scheduler()` legacy.

    El módulo top-level `sync.py` arranca side-effects al importarse
    (lee `os.environ` y define `_jobs` a nivel módulo). Esto no se puede
    deshacer trivialmente — la versión "limpia" del refactor (Fase 4e)
    reescribirá `sync.py` para que el scheduler solo arranque al llamar
    `init_scheduler(app)`.

    Mientras tanto, la factory llama esta función que delega al original
    (que respeta `SYNC_AUTO=false` por defecto).
    """
    _legacy_iniciar_scheduler()


__all__ = [
    "init_scheduler",
    "get_job_status",
    "ping_dispositivo",
    "sincronizar",
    "sincronizar_con_reintento",
    "sincronizar_dispositivo",
    "limpiar_log_dispositivo",
    "verificar_dispositivos_desconectados",
    "_jobs",
    "delete_horario",
    "get_estado_horarios",
    "get_horario",
    "get_horarios",
    "get_ids_usuarios_zk",
    "upsert_horario",
    "upsert_horarios",
]

# Re-exports de `db` (capa de datos), añadidos para cumplir la regla de
# capas del ADR-0001 (antes: `app/web/schedule_bp.py` importaba `db` directo).
from db import (  # noqa: E402
    delete_horario,
    get_estado_horarios,
    get_horario,
    get_horarios,
    get_ids_usuarios_zk,
    upsert_horario,
    upsert_horarios,
)
