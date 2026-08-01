"""
Acceso a datos para el dominio devices (`app/domain/devices.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/devices_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    actualizar_persona,
    clear_thread_tenant,
    eliminar_dispositivo,
    get_dispositivos_activos,
    get_estado,
    get_estado_sync_ui,
    get_horarios,
    get_justificaciones_pendientes,
    get_latest_sync_logs_por_dispositivo,
    get_personas_con_id,
    get_usuarios_zk_con_estado,
    listar_personas,
    registrar_audit,
    set_thread_tenant,
    upsert_dispositivo,
)

__all__ = [
    "actualizar_persona",
    "clear_thread_tenant",
    "eliminar_dispositivo",
    "get_dispositivos_activos",
    "get_estado",
    "get_estado_sync_ui",
    "get_horarios",
    "get_justificaciones_pendientes",
    "get_latest_sync_logs_por_dispositivo",
    "get_personas_con_id",
    "get_usuarios_zk_con_estado",
    "listar_personas",
    "registrar_audit",
    "set_thread_tenant",
    "upsert_dispositivo",
]
