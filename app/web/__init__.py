"""
Blueprints de routing (`app/web/*`).

Cada Blueprint cubre un dominio del sistema (auth, devices, schedules, etc.).
Las funciones aquí son delgadas: serializan request → llaman a `app.domain.*`
→ serializan response. **Nunca** importan `db.queries.*` directamente.

`all_blueprints` es la lista ordenada que `create_app()` itera para `register_blueprint`.
El orden no afecta el routing (Flask resuelve por endpoint), pero se mantiene
un orden lógico para futuros grep/tests.
"""
from __future__ import annotations


# Lazy import para evitar ciclos cuando `app/__init__.py` aún está cargando.
def _collect_blueprints() -> list:
    from app.web.admin_bp import bp as admin_bp
    from app.web.analytics_bp import bp as analytics_bp
    from app.web.attendance_bp import bp as attendance_bp
    from app.web.auth_bp import bp as auth_bp
    from app.web.breaks_bp import bp as breaks_bp
    from app.web.dashboard_bp import bp as dashboard_bp
    from app.web.devices_bp import bp as devices_bp
    from app.web.groups_bp import bp as groups_bp
    from app.web.people_bp import bp as people_bp
    from app.web.periods_bp import bp as periods_bp
    from app.web.reports_bp import bp as reports_bp
    from app.web.schedule_bp import bp as schedule_bp
    from app.web.system_bp import bp as system_bp

    return [
        auth_bp,
        dashboard_bp,
        devices_bp,
        schedule_bp,
        attendance_bp,
        breaks_bp,
        reports_bp,
        periods_bp,
        people_bp,
        groups_bp,
        admin_bp,
        analytics_bp,
        system_bp,
    ]


# Se resuelve en tiempo de carga de `create_app()`.
all_blueprints = _collect_blueprints()


__all__ = ["all_blueprints"]
