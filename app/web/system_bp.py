"""
Blueprint misceláneo (`app/web/system_bp.py`).

Rutas (2):
  - POST /api/historicos/importar   → ingesta histórica desde CSV/XLSX
  - GET  /api/scheduler/estado      → estado del scheduler + últimas corridas (Fase 1)

Agrupa endpoints que no encajan en otros blueprints por dominio.
"""
from __future__ import annotations

import os
import uuid

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from app.domain import scheduler as scheduler_svc
from app.domain.rbac import require_role

bp = Blueprint("system", __name__)


@bp.post("/api/historicos/importar")
@require_role("superadmin", "admin")
def importar_historicos():
    from db import insertar_asistencias

    if "archivo" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400

    file = request.files["archivo"]
    if file.filename == "":
        return jsonify({"error": "Archivo no seleccionado"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".csv", ".xlsx"):
        return jsonify({"error": "Formato no soportado. Use .csv o .xlsx"}), 400

    filename = secure_filename(file.filename)
    filepath = current_app.config["UPLOAD_FOLDER"] + f"/historico_{uuid.uuid4().hex}_{filename}"
    file.save(filepath)

    registros = []
    try:
        if ext == ".csv":
            import csv as csv_reader
            with open(filepath, newline="", encoding="utf-8-sig") as f:
                reader = csv_reader.DictReader(f)
                for row in reader:
                    r_norm = {k.lower().strip(): v for k, v in row.items()}
                    registros.append({
                        "id_usuario": str(r_norm.get("id_usuario") or "").strip(),
                        "nombre":     str(r_norm.get("nombre") or "").strip(),
                        "fecha_hora": str(r_norm.get("fecha_hora") or "").strip(),
                        "tipo":       str(r_norm.get("tipo", "Entrada") or "").strip().title(),
                        "fuente":     "historico",
                    })
        else:  # .xlsx
            import openpyxl
            wb = openpyxl.load_workbook(filepath, read_only=True)
            sheet = wb.active
            headers = [str(cell.value).lower().strip() for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not any(row):
                    continue
                r_dict = dict(zip(headers, row))
                f_h = r_dict.get("fecha_hora")
                if hasattr(f_h, "isoformat"):
                    f_h = f_h.isoformat()
                registros.append({
                    "id_usuario": str(r_dict.get("id_usuario") or "").strip(),
                    "nombre":     str(r_dict.get("nombre") or "").strip(),
                    "fecha_hora": str(f_h or "").strip(),
                    "tipo":       str(r_dict.get("tipo", "Entrada") or "").strip().title(),
                    "fuente":     "historico",
                })

        registros_validos = [
            r for r in registros if r["nombre"] and r["fecha_hora"]
        ]
        if not registros_validos:
            return jsonify({"error": "No se encontraron registros válidos con columnas: nombre, fecha_hora"}), 400

        nuevos = insertar_asistencias(registros_validos)
        return jsonify({
            "success": True,
            "total_leidos": len(registros),
            "total_validos": len(registros_validos),
            "insertados_nuevos": nuevos,
        })

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Error procesando el archivo: {str(e)}"}), 500
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass


@bp.get("/api/scheduler/estado")
@require_role("superadmin", "admin")
def scheduler_estado():
    """
    Devuelve el estado actual del scheduler y las últimas 10 corridas.

    Útil para la card 'Sincronización automática' en /configuracion.
    """
    sync_activo = os.environ.get("SYNC_AUTO", "false").lower() == "true"
    hora_nocturna = os.environ.get("SYNC_HORA_NOCTURNA", "02:00")
    try:
        intervalo = int(os.environ.get("SYNC_INTERVALO_HORAS", "2"))
    except ValueError:
        intervalo = 2

    # Próxima corrida (si el scheduler está cargado): consultamos `schedule` del módulo sync.
    proxima = None
    try:
        import sync as sync_module
        if sync_module.SCHEDULE_DISPONIBLE:
            proximas = [j.next_run for j in sync_module.schedule.get_jobs() if j.next_run]
            if proximas:
                proxima = min(proximas).isoformat()
    except Exception:  # noqa: BLE001
        proxima = None

    try:
        ultimas = scheduler_svc.listar_ultimas_corridas(limit=10)
    except Exception as e:  # noqa: BLE001
        current_app.logger.warning("scheduler_runs.listar_ultimos falló: %s", e)
        ultimas = []

    # Serializar datetimes a ISO string (jsonify no sabe hacerlo solo).
    for fila in ultimas:
        for k in ("inicio", "fin"):
            v = fila.get(k)
            if hasattr(v, "isoformat"):
                fila[k] = v.isoformat()

    return jsonify({
        "sync_activo": sync_activo,
        "sync_hora_nocturna": hora_nocturna,
        "sync_intervalo_horas": intervalo,
        "proxima_corrida": proxima,
        "ultimas_corridas": ultimas,
    })