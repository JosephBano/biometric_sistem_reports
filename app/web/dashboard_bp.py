"""
Blueprint de vistas estáticas (`app/web/dashboard_bp.py`).

Rutas HTML sin lógica de negocio (sólo renderizan templates):
  - GET /                                  → dashboard principal
  - GET /configuracion                     → vista de configuración del tenant
  - GET /justificaciones-vista             → vista de justificaciones
  - GET /reportes                          → vista de generación de reportes
  - GET /descargar/<filename:filename>     → descarga de un reporte PDF/DOCX
  - GET /presencia                         → vista cruda de marcaciones (soporta ?export=csv)

Endpoint names: `dashboard.index`, `dashboard.configuracion`, etc.
"""
from __future__ import annotations

import csv
import io
import os

from flask import Blueprint, Response, current_app, render_template, request, send_file

from app.domain.dashboard import consultar_asistencias

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    return render_template("dashboard.html", active_page="dashboard")


@bp.route("/configuracion")
def configuracion():
    return render_template("configuracion.html", active_page="configuracion")


@bp.route("/justificaciones-vista")
def justificaciones():
    return render_template("justificaciones.html", active_page="justificaciones")


@bp.route("/reportes")
def reportes():
    return render_template("reportes.html", active_page="reportes")


@bp.route("/descargar/<path:filename>")
def descargar(filename: str):
    """Descarga un archivo previamente generado de `REPORTS_FOLDER`. 404 si expirado."""
    folder = current_app.config.get("REPORTS_FOLDER", "data/reports")
    file_path = os.path.join(folder, filename)
    if not os.path.exists(file_path):
        return "Archivo no encontrado o expirado", 404
    return send_file(file_path, as_attachment=True)


@bp.route("/presencia")
def presencia():
    """
    Vista cruda de marcaciones.
    Soporta `?export=csv` para descarga directa.
    """

    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")

    registros = []
    try:
        registros = consultar_asistencias(fecha_inicio, fecha_fin) or []
    except Exception:  # noqa: BLE001
        registros = []

    if request.args.get("export") == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id_usuario", "nombre", "fecha_hora", "tipo"])
        for r in registros:
            writer.writerow([
                r.get("id_usuario", ""),
                r.get("nombre", ""),
                r.get("fecha_hora", ""),
                r.get("tipo", ""),
            ])
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=presencia.csv"},
        )

    return render_template("presencia.html", registros=registros, active_page="presencia")
