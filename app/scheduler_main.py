"""Entry point for the dedicated scheduler process."""
from __future__ import annotations

import logging
import os
import signal
import threading

from db.queries import scheduler_lock

log = logging.getLogger(__name__)
_RETRY_SECONDS = 15


def main() -> int:
    """Wait for the distributed leader lock, then start the scheduler once."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_args: stop.set())

    if os.environ.get("SYNC_AUTO", "false").lower() != "true":
        log.info("Scheduler desactivado (SYNC_AUTO=false); proceso en espera")
        stop.wait()
        return 0

    if os.environ.get("SCHEDULER_PROCESS", "false").lower() != "true":
        log.error("Este proceso requiere SCHEDULER_PROCESS=true")
        return 2

    leader_conn = None
    while not stop.is_set() and leader_conn is None:
        try:
            leader_conn = scheduler_lock.try_acquire(
                scheduler_lock.SCHEDULER_LEADER_LOCK,
            )
        except Exception:
            log.exception("No se pudo adquirir el lock líder del scheduler")

        if leader_conn is None and not stop.is_set():
            log.warning(
                "Otro scheduler tiene el lock o PostgreSQL no está disponible; "
                "reintentando en %ss",
                _RETRY_SECONDS,
            )
            stop.wait(_RETRY_SECONDS)

    if leader_conn is None:
        return 0

    try:
        # create_app starts jobs only with both flags enabled. Keep the leader
        # connection open for the lifetime of this process.
        from app import create_app

        app = create_app("production")
        log.info("Proceso scheduler líder activo (%s)", app.name)
        stop.wait()
        return 0
    except Exception:
        log.exception("No se pudo iniciar el proceso scheduler")
        return 1
    finally:
        try:
            scheduler_lock.release(
                leader_conn,
                scheduler_lock.SCHEDULER_LEADER_LOCK,
            )
        except Exception:
            log.exception("No se pudo liberar el lock líder del scheduler")


if __name__ == "__main__":
    raise SystemExit(main())
