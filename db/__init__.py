"""
Paquete db — capa de acceso a datos PostgreSQL.

Re-exporta todas las funciones públicas con la misma firma que el sistema SQLite anterior.
app.py, script.py y sync.py no requieren ningún cambio.
"""

# ── Conexión ──────────────────────────────────────────────────────────────
from db.connection import get_connection

# ── Inicialización ────────────────────────────────────────────────────────
from db.init import init_db

# ── Personas / Usuarios ZK ────────────────────────────────────────────────
from db.queries.personas import (
    upsert_usuarios,
    get_ids_usuarios_zk,
)

# ── Asistencias ───────────────────────────────────────────────────────────
from db.queries.asistencias import (
    insertar_asistencias,
    consultar_asistencias,
    get_personas,
    get_personas_con_id,
    get_estado,
)

# ── Horarios ──────────────────────────────────────────────────────────────
from db.queries.horarios import (
    upsert_horarios,
    upsert_horario,
    get_horarios,
    get_horario,
    delete_horario,
    get_estado_horarios,
)

# ── Sync log ──────────────────────────────────────────────────────────────
from db.queries.sync_log import registrar_sync

# ── Justificaciones ───────────────────────────────────────────────────────
from db.queries.justificaciones import (
    insertar_justificacion,
    get_justificaciones,
    get_justificaciones_dict,
    get_justificaciones_pendientes,
    actualizar_estado_justificacion,
    eliminar_justificacion,
    get_justificacion_by_id,
    actualizar_justificacion_completa,
)

# ── Breaks categorizados ──────────────────────────────────────────────────
from db.queries.breaks import (
    get_breaks_categorizados_dict,
    insertar_break_categorizado,
)

# ── Feriados ──────────────────────────────────────────────────────────────
from db.queries.feriados import (
    insertar_feriado,
    get_feriados,
    get_feriados_set,
    eliminar_feriado,
    importar_feriados_csv,
)

# ── Auth / Usuarios de la app ─────────────────────────────────────────────
from db.queries.auth import (
    get_usuario_por_email,
    get_usuario_por_id,
    get_usuarios_tenant,
    crear_usuario_db,
    actualizar_roles_db,
    desactivar_usuario_db,
    activar_usuario_db,
    actualizar_ultimo_acceso,
    registrar_audit,
    registrar_login_intento,
    contar_intentos_fallidos,
    get_tipos_persona,
    get_device_password_enc,
    set_device_password_enc,
)

from db.queries.tenants import (
    get_tenant_by_slug,
    listar_tenants,
    crear_tenant,
    actualizar_tenant,
    insertar_tipo_persona,
    eliminar_tenant_de_public,
)

from db.tenant_provisioner import provisionar_schema

__all__ = [
    # conexión
    "get_connection",
    # init
    "init_db",
    # personas
    "upsert_usuarios",
    "get_ids_usuarios_zk",
    # asistencias
    "insertar_asistencias",
    "consultar_asistencias",
    "get_personas",
    "get_personas_con_id",
    "get_estado",
    # horarios
    "upsert_horarios",
    "upsert_horario",
    "get_horarios",
    "get_horario",
    "delete_horario",
    "get_estado_horarios",
    # sync
    "registrar_sync",
    # justificaciones
    "insertar_justificacion",
    "get_justificaciones",
    "get_justificaciones_dict",
    "get_justificaciones_pendientes",
    "actualizar_estado_justificacion",
    "eliminar_justificacion",
    "get_justificacion_by_id",
    "actualizar_justificacion_completa",
    # breaks
    "get_breaks_categorizados_dict",
    "insertar_break_categorizado",
    # feriados
    "insertar_feriado",
    "get_feriados",
    "get_feriados_set",
    "eliminar_feriado",
    "importar_feriados_csv",
    # auth
    "get_usuario_por_email",
    "get_usuario_por_id",
    "get_usuarios_tenant",
    "crear_usuario_db",
    "actualizar_roles_db",
    "desactivar_usuario_db",
    "activar_usuario_db",
    "actualizar_ultimo_acceso",
    "registrar_audit",
    "registrar_login_intento",
    "contar_intentos_fallidos",
    "get_tipos_persona",
    "get_device_password_enc",
    "set_device_password_enc",
    # tenants
    "get_tenant_by_slug",
    "listar_tenants",
    "crear_tenant",
    "actualizar_tenant",
    "insertar_tipo_persona",
    "eliminar_tenant_de_public",
    "provisionar_schema",
]
