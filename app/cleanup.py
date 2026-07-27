"""
Cleanup thread (`app/cleanup.py`).

Migrado desde `app.py:111-124`. Elimina archivos > 15 min en `UPLOAD_FOLDER`
y `REPORTS_FOLDER` cada 5 minutos en un hilo daemon.

Se arranca desde `create_app()` SOLO si la config indica producción
(`SYNC_AUTO=true` o, mejor, una flag dedicada). En tests no se ejecuta
de forma automática — usar el fixture de pytest si hace falta.
"""
from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def _cleanup_loop(app: Flask) -> None:
    """Loop daemon: cada 5 min borra archivos > 15 min de antigüedad."""
    upload = app.config.get("UPLOAD_FOLDER", "data/uploads")
    reports = app.config.get("REPORTS_FOLDER", "data/reports")
    ttl_seconds = 15 * 60  # 15 minutos
    period = 5 * 60        # cada 5 min

    while True:
        try:
            now = time.time()
            for folder in (upload, reports):
                if not os.path.isdir(folder):
                    continue
                for filename in os.listdir(folder):
                    filepath = os.path.join(folder, filename)
                    try:
                        if os.path.isfile(filepath) and \
                                os.stat(filepath).st_mtime < now - ttl_seconds:
                            os.remove(filepath)
                    except OSError:
                        # Archivo puede haber sido borrado por otro hilo; ignorar.
                        pass
        except Exception as e:  # noqa: BLE001
            # No matar el hilo bajo ningún concepto.
            app.logger.debug("cleanup loop: %s", e)
        time.sleep(period)


def start_cleanup_thread(app: Flask) -> None:
    """
    Lanza el cleanup thread daemon.

    Se ejecuta siempre en producción/dev; **no** en testing (la flag
    `app.config["TESTING"]` lo desactiva).
    """
    if app.config.get("TESTING"):
        return

    thread = threading.Thread(
        target=_cleanup_loop,
        args=(app,),
        daemon=True,
        name="biometrico-cleanup",
    )
    thread.start()
