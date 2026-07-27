"""
Blueprint de analytics (`app/web/analytics_bp.py`).

Rutas (4):
  - GET  /analytics                         → vista principal
  - GET  /analytics/periodo/<periodo_id>     → detalle de un período con IA
  - POST /api/analytics/narrativo            → narrativo IA on-demand
  - GET  /api/analytics                     → hallazgos JSON (en reports_bp, no duplicado aquí)
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, request

from app.domain import ai_narrative
from app.domain import analytics as analytics_svc
from app.domain.analytics import calcular_asistencia_periodo, get_periodo, listar_grupos
from app.domain.rbac import require_role

bp = Blueprint("analytics", __name__)


@bp.get("/analytics")
@require_role("admin", "superadmin", "gestor")
def vista():
    hoy = date.today()
    fecha_inicio = (hoy - timedelta(days=30)).strftime("%Y-%m-%d")
    fecha_fin = hoy.strftime("%Y-%m-%d")
    grupos = listar_grupos(activo=True)
    return render_template(
        "analytics.html",
        active_page="analytics",
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        grupos=grupos,
    )


@bp.get("/analytics/periodo/<periodo_id>")
@require_role("admin", "superadmin", "gestor")
def analytics_periodo(periodo_id: str):
    periodo = get_periodo(periodo_id)
    if not periodo:
        return "Período no encontrado", 404
    resumen = analytics_svc.resumen_periodo(periodo_id)
    dist = analytics_svc.distribucion_asistencia_periodo(periodo_id)
    narrativo = ai_narrative.generar_narrativo(resumen) if resumen.get("exito") else ""
    return render_template(
        "periodos/detalle.html",
        active_page="periodos",
        periodo=periodo,
        personas=calcular_asistencia_periodo(periodo_id),
        resumen_general=resumen.get("resumen_general", {}),
        distribucion=dist,
        narrativo=narrativo,
    )


@bp.post("/api/analytics/narrativo")
@require_role("admin", "superadmin", "gestor")
def api_narrativo():
    """Genera narrativo IA on-demand a partir de hallazgos enviados como JSON."""
    hallazgos = request.json or {}
    if not hallazgos:
        return jsonify({"error": "Se requiere payload de hallazgos"}), 400
    try:
        texto = ai_narrative.generar_narrativo(hallazgos)
        return jsonify({"narrativo": texto})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500
