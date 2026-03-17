"""
Wrapper de compatibilidad — Fase 1: migración SQLite → PostgreSQL.

Este módulo re-exporta todas las funciones de db/ con la misma firma
que tenían en el sistema SQLite. app.py, script.py y sync.py no requieren cambios.
"""
from db import *  # noqa: F401, F403
from db import init_db  # noqa: F401 — importación explícita para `import db as db_module; db_module.init_db()`
