"""
Acceso a datos para el dominio admin (`app/domain/admin.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/admin_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    actualizar_tenant,
    crear_tenant,
    get_connection,
    get_tenants_activos,
    get_usuario_por_id,
    get_usuarios_all_tenants,
    get_usuarios_tenant,
    listar_tenants,
    provisionar_schema,
    registrar_audit,
)

__all__ = [
    "actualizar_tenant",
    "crear_tenant",
    "get_connection",
    "get_tenants_activos",
    "get_usuario_por_id",
    "get_usuarios_all_tenants",
    "get_usuarios_tenant",
    "listar_tenants",
    "provisionar_schema",
    "registrar_audit",
]
