"""
Blueprint de categorización de breaks (`app/web/breaks_bp.py`).

Rutas (1):
  - POST /api/categorizar-break
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request, session

from app.domain.breaks import insertar_break_categorizado
from app.domain.rbac import require_role

bp = Blueprint("breaks", __name__)


@bp.post("/api/categorizar-break")
@require_role("superadmin", "admin", "gestor")
def categorizar_break():
    data = request.json or {}
    id_usuario = data.get("id_usuario")
    fecha      = data.get("fecha")
    h_ini      = data.get("hora_inicio")
    h_fin      = data.get("hora_fin")
    cat        = data.get("categoria")  # 'almuerzo' | 'permiso' | 'injustificado'
    motivo     = data.get("motivo", "")
    aprobado   = g.get("nombre", session.get("nombre", "Sistema"))

    if not all([id_usuario, fecha, h_ini, h_fin, cat]):
        return jsonify({"error": "Faltan campos (id_usuario, fecha, hora_inicio, hora_fin, categoria)"}), 400

    if cat not in ("almuerzo", "permiso", "injustificado"):
        return jsonify({"error": "Categoría inválida"}), 400

    try:
        insertar_break_categorizado(id_usuario, fecha, h_ini, h_fin, cat, motivo, aprobado)
        return jsonify({"success": True})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500
