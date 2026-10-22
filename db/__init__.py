"""
Paquete db — capa de acceso a datos PostgreSQL.

Re-exporta todas las funciones públicas con la misma firma que el sistema SQLite anterior.
app.py, script.py y sync.py no requieren ningún cambio.
"""

# ── Conexión ──────────────────────────────────────────────────────────────
from db.connection import clear_thread_tenant, get_connection, set_thread_tenant

# ── Inicialización ────────────────────────────────────────────────────────
from db.init import init_db
from db.queries.asistencia_periodo import calcular_asistencia_periodo

# ── Asistencias ───────────────────────────────────────────────────────────
from db.queries.asistencias import (
    consultar_asistencias,
    get_estado,
    get_personas,
    get_personas_con_id,
    insertar_asistencias,
)

# ── Auth / Usuarios de la app ─────────────────────────────────────────────
from db.queries.auth import (
    activar_usuario_db,
    actualizar_roles_db,
    actualizar_ultimo_acceso,
    contar_intentos_fallidos,
    crear_usuario_db,
    desactivar_usuario_db,
    get_device_password_enc,
    get_tenants_activos,
    get_tipos_persona,
    get_usuario_por_email,
    get_usuario_por_id,
    get_usuarios_all_tenants,
    get_usuarios_tenant,
    registrar_audit,
    registrar_login_intento,
    set_device_password_enc,
)

# ── Breaks categorizados ──────────────────────────────────────────────────
from db.queries.breaks import (
    get_breaks_categorizados_dict,
    insertar_break_categorizado,
)
from db.queries.dispositivos import (
    actualizar_estado_sync_ui,
    actualizar_watermark,
    eliminar_dispositivo,
    get_dispositivo,
    get_dispositivos_activos,
    get_dispositivos_con_fallas_consecutivas,
    get_estado_sync_ui,
    has_alerta_hoy,
    marcar_alerta_enviada,
    upsert_dispositivo,
)

# ── Feriados ──────────────────────────────────────────────────────────────
from db.queries.feriados import (
    eliminar_feriado,
    get_feriados,
    get_feriados_set,
    importar_feriados_csv,
    insertar_feriado,
)
from db.queries.grupos import (
    actualizar_grupo,
    actualizar_grupo_funcional,
    crear_grupo,
    crear_grupo_funcional,
    listar_grupos,
    listar_grupos_funcionales,
)

# ── Horarios ──────────────────────────────────────────────────────────────
from db.queries.horarios import (
    delete_horario,
    get_estado_horarios,
    get_horario,
    get_horarios,
    upsert_horario,
    upsert_horarios,
)

# ── Justificaciones ───────────────────────────────────────────────────────
from db.queries.justificaciones import (
    actualizar_estado_justificacion,
    actualizar_justificacion_completa,
    eliminar_justificacion,
    get_justificacion_by_id,
    get_justificaciones,
    get_justificaciones_dict,
    get_justificaciones_pendientes,
    insertar_justificacion,
)
from db.queries.periodos import (
    agregar_personas_a_periodo_bulk,
    archivar_periodo,
    cerrar_periodo,
    cerrar_periodos_vencidos,
    crear_periodo,
    eliminar_periodo,
    get_periodo,
    listar_periodos_activos,
    listar_periodos_historial,
    procesar_csv_personas_periodo,
    remover_persona_de_periodo,
)

# ── Personas / Usuarios ZK ────────────────────────────────────────────────
from db.queries.personas import (
    get_ids_usuarios_zk,
    upsert_usuarios,
)
from db.queries.personas_crud import (
    actualizar_persona,
    crear_persona,
    get_historico_persona,
    get_persona,
    get_usuarios_zk_con_estado,
    listar_personas,
)

# ── Scheduler runs (Fase 1 — Sync observable) ──────────────────────────────
from db.queries.scheduler_runs import (
    listar_ultimos,
    purgar_mayor_a,
    registrar_run,
)

# ── Sync log ──────────────────────────────────────────────────────────────
from db.queries.sync_log import get_latest_sync_logs_por_dispositivo, registrar_sync
from db.queries.tenants import (
    actualizar_tenant,
    crear_tenant,
    eliminar_tenant_de_public,
    get_tenant_by_slug,
    insertar_tipo_persona,
    listar_tenants,
)
from db.tenant_provisioner import provisionar_schema

__all__ = [
    # conexión
    "get_connection",
    "set_thread_tenant",
    "clear_thread_tenant",
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
    "get_latest_sync_logs_por_dispositivo",
    # scheduler runs
    "registrar_run",
    "listar_ultimos",
    "purgar_mayor_a",
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
    "get_usuarios_all_tenants",
    "get_tenants_activos",
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
    # periodos
    "crear_periodo",
    "get_periodo",
    "listar_periodos_activos",
    "listar_periodos_historial",
    "agregar_personas_a_periodo_bulk",
    "remover_persona_de_periodo",
    "cerrar_periodo",
    "archivar_periodo",
    "eliminar_periodo",
    "cerrar_periodos_vencidos",
    "procesar_csv_personas_periodo",
    "calcular_asistencia_periodo",
    # grupos y grupos funcionales
    "listar_grupos",
    "crear_grupo",
    "actualizar_grupo",
    "listar_grupos_funcionales",
    "crear_grupo_funcional",
    "actualizar_grupo_funcional",
    # personas CRUD
    "listar_personas",
    "get_persona",
    "crear_persona",
    "actualizar_persona",
    "get_historico_persona",
    "get_usuarios_zk_con_estado",
    # dispositivos
    "get_dispositivos_activos",
    "get_dispositivo",
    "actualizar_watermark",
    "get_estado_sync_ui",
    "actualizar_estado_sync_ui",
    "upsert_dispositivo",
    "eliminar_dispositivo",
    "get_dispositivos_con_fallas_consecutivas",
    "has_alerta_hoy",
    "marcar_alerta_enviada",
]
