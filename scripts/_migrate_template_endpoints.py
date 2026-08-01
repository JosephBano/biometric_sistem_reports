#!/usr/bin/env python3
"""
Migración de templates para usar nombres de endpoint con prefijo de Blueprint.

Cambia:
  url_for('dashboard')               → url_for('dashboard.index')
  url_for('login')                  → url_for('auth.login')
  ...etc

Mapeo completo en `ENDPOINT_MAP`. Aplicado a todos los *.html bajo `templates/`.
"""
from __future__ import annotations

import pathlib

ENDPOINT_MAP = {
    # auth_bp
    "'login'":        "'auth.login'",
    '"login"':        '"auth.login"',
    "'logout'":       "'auth.logout'",
    "'switch_tenant'": "'auth.switch_tenant'",

    # dashboard_bp
    "'dashboard'":               "'dashboard.index'",
    "'configuracion_vista'":     "'dashboard.configuracion'",
    "'justificaciones_vista'":   "'dashboard.justificaciones'",
    "'reportes_vista'":          "'dashboard.reportes'",
    "'vista_presencia'":         "'dashboard.presencia'",
    "'descargar'":               "'dashboard.descargar'",

    # devices_bp
    "'estado_sync'":             "'devices.estado_sync'",
    "'api_get_dispositivos'":    "'devices.api_get_dispositivos'",
    "'api_usuarios_zk'":         "'devices.api_usuarios_zk'",
    "'api_sync_estado'":         "'devices.api_sync_estado'",
    "'sincronizar'":             "'devices.sincronizar'",
    "'sync_status'":             "'devices.sync_status'",
    "'limpiar_dispositivo'":     "'devices.limpiar_dispositivo'",
    "'api_personas_db'":         "'devices.personas_db'",
    "'api_personas_lista'":      "'devices.api_personas_lista'",

    # schedule_bp
    "'cargar_horarios'":         "'schedule.cargar_horarios'",
    "'estado_horarios'":         "'schedule.estado_horarios'",
    "'ver_horarios'":            "'schedule.ver_horarios'",
    "'exportar_horarios_csv'":   "'schedule.exportar_horarios_csv'",
    "'api_horarios_crear'":      "'schedule.api_horarios_crear'",
    "'api_horarios_actualizar'": "'schedule.api_horarios_actualizar'",
    "'api_horarios_eliminar'":   "'schedule.api_horarios_eliminar'",

    # attendance_bp
    "'get_justificaciones'":           "'attendance.get_justificaciones'",
    "'crear_justificacion'":           "'attendance.crear_justificacion'",
    "'actualizar_justificacion_estado'": "'attendance.actualizar_justificacion_estado'",
    "'get_justificacion'":             "'attendance.get_justificacion'",
    "'actualizar_justificacion'":      "'attendance.actualizar_justificacion'",
    "'eliminar_justificacion'":        "'attendance.eliminar_justificacion'",
    "'get_feriados'":                  "'attendance.get_feriados'",
    "'crear_feriado'":                 "'attendance.crear_feriado'",
    "'eliminar_feriado'":              "'attendance.eliminar_feriado'",
    "'importar_feriados'":             "'attendance.importar_feriados'",
    "'exportar_feriados'":             "'attendance.exportar_feriados'",

    # breaks_bp
    "'API_categorizar_break'":         "'breaks.categorizar_break'",

    # reports_bp
    "'generar_desde_db'":              "'reports.generar_desde_db'",
    "'enviar_reporte_email'":          "'reports.enviar_reporte_email'",
    "'descargar_backup_db'":           "'reports.descargar_backup_db'",
    "'descargar_backup_csv'":          "'reports.descargar_backup_csv'",
    "'alertas_tardanzas_severas'":     "'reports.alertas_tardanzas_severas'",
    "'api_analytics'":                 "'reports.api_analytics'",

    # periods_bp
    "'periodos_lista'":                "'periods.lista'",
    "'crear_periodo_route'":           "'periods.crear'",
    "'periodo_detalle'":               "'periods.detalle'",
    "'periodo_importar_personas_route'": "'periods.importar_personas'",
    "'cerrar_periodo_route'":          "'periods.cerrar'",
    "'archivar_periodo_route'":        "'periods.archivar'",
    "'eliminar_periodo_route'":        "'periods.eliminar'",

    # people_bp
    "'personas_lista'":                "'people.lista'",
    "'personas_crear'":                "'people.crear'",
    "'personas_editar'":               "'people.editar'",
    "'personas_historico'":            "'people.historico'",

    # groups_bp
    "'admin_grupos'":                  "'groups.listar_grupos'",
    "'admin_crear_grupo'":             "'groups.crear_grupo'",
    "'admin_actualizar_grupo'":        "'groups.actualizar_grupo'",
    "'admin_categorias'":              "'groups.listar_categorias'",
    "'admin_crear_categoria'":         "'groups.crear_categoria'",
    "'admin_actualizar_categoria'":    "'groups.actualizar_categoria'",

    # admin_bp
    "'admin_tenants'":                 "'admin.listar_tenants'",
    "'admin_crear_tenant'":            "'admin.crear_tenant'",
    "'admin_actualizar_tenant'":       "'admin.actualizar_tenant'",
    "'admin_dispositivos'":            "'admin.admin_dispositivos'",
    "'admin_usuarios'":                "'admin.listar_usuarios'",
    "'admin_crear_usuario'":           "'admin.crear_usuario'",
    "'admin_editar_usuario'":          "'admin.editar_usuario'",
    "'superadmin_usuarios'":           "'admin.superadmin_usuarios'",
    "'api_superadmin_mover_usuario'":  "'admin.api_superadmin_mover_usuario'",
    "'api_superadmin_eliminar_usuario'": "'admin.api_superadmin_eliminar_usuario'",
    "'api_superadmin_crear_usuario'":  "'admin.api_superadmin_crear_usuario'",

    # analytics_bp
    "'analytics_vista'":               "'analytics.vista'",
    "'analytics_periodo'":             "'analytics.analytics_periodo'",
    "'api_narrativo'":                 "'analytics.api_narrativo'",
}


def main() -> None:
    tpl_dir = pathlib.Path("templates")
    total_changes = 0
    for f in tpl_dir.rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        original = text
        for old, new in ENDPOINT_MAP.items():
            text = text.replace(old, new)
        if text != original:
            f.write_text(text, encoding="utf-8")
            n = sum(1 for old in ENDPOINT_MAP if old in original)
            total_changes += n
            print(f"  {f}: {n} cambios")
    print(f"\nTotal: {total_changes} reemplazos en {sum(1 for _ in tpl_dir.rglob('*.html'))} templates")


if __name__ == "__main__":
    main()
