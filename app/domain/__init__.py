"""
Capa de servicios de dominio (`app/domain/*`).

Reglas arquitectónicas:
  - Servicios PUROS en lo posible (sin Flask) — facilita tests y REPL.
  - Sólo lo que requiere `flask.g`, `session` o `request` (RBAC, tenant
    loader, schedule) importa Flask explícitamente.
  - Pueden importar `db.queries.*` libremente; nunca `app.web.*`.
"""
