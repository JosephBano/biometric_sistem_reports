"""
Blueprint de justificaciones y feriados (`app/web/attendance_bp.py`).

Rutas (11):
  - GET    /api/justificaciones
  - POST   /api/justificaciones
  - PATCH  /api/justificaciones/<int:jid>
  - GET    /api/justificaciones/<int:jid>
  - PUT    /api/justificaciones/<int:jid>
  - DELETE /api/justificaciones/<int:jid>
  - GET    /api/feriados
  - POST   /api/feriados
  - DELETE /api/feriados/<fecha>
  - POST   /api/feriados/importar
  - GET    /api/feriados/exportar
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime

from flask import Blueprint, Response, current_app, jsonify, request
from werkzeug.utils import secure_filename

from app.domain.attendance import (
    actualizar_estado_justificacion,
    actualizar_justificacion_completa,
    eliminar_feriado as svc_eliminar_feriado,
    eliminar_justificacion as svc_eliminar_justificacion,
    get_feriados as svc_get_feriados,
    get_justificacion_by_id,
    get_justificaciones as svc_get_justificaciones,
    importar_feriados_csv,
    insertar_feriado,
    insertar_justificacion,
)
from app.domain.rbac import require_role

bp = Blueprint("attendance", __name__)

_HORA_RE = re.compile(r"^\d{2}:\d{2}$")


# ══════════════════════════════════════════════════════════════════════════
# JUSTIFICACIONES
# ══════════════════════════════════════════════════════════════════════════


@bp.get("/api/justificaciones")
def get_justificaciones():
    fi_str = request.args.get("fecha_inicio")
    ff_str = request.args.get("fecha_fin")
    try:
        fi = datetime.strptime(fi_str, "%Y-%m-%d").date() if fi_str else None
        ff = datetime.strptime(ff_str, "%Y-%m-%d").date() if ff_str else None
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400
    return jsonify({"justificaciones": svc_get_justificaciones(fi, ff)})


@bp.post("/api/justificaciones")
@require_role("superadmin", "admin", "gestor")
def crear_justificacion():

    data = request.json or {}
    id_usuario = str(data.get("id_usuario", "")).strip()
    nombre     = str(data.get("nombre", "")).strip()
    fecha      = str(data.get("fecha", "")).strip()
    tipo       = str(data.get("tipo", "")).strip()
    motivo     = str(data.get("motivo", "")).strip()
    aprobado   = str(data.get("aprobado_por", "")).strip()
    hora_permitida = str(data.get("hora_permitida", "")).strip() or None
    estado     = str(data.get("estado", "aprobada")).strip()
    hora_retorno_permiso = str(data.get("hora_retorno_permiso", "")).strip() or None
    incluye_almuerzo = 1 if data.get("incluye_almuerzo") else 0

    recuperable = 1 if data.get("recuperable") else 0
    fecha_recuperacion = str(data.get("fecha_recuperacion", "")).strip() or None
    hora_recuperacion = str(data.get("hora_recuperacion", "")).strip() or None
    hora_recuperacion_fin = str(data.get("hora_recuperacion_fin", "")).strip() or None

    duracion_permitida_min = data.get("duracion_permitida_min")
    if duracion_permitida_min is not None and str(duracion_permitida_min).strip() != "":
        try:
            duracion_permitida_min = int(duracion_permitida_min)
        except ValueError:
            return jsonify({"error": "duracion_permitida_min debe ser un número entero"}), 400
    else:
        duracion_permitida_min = None

    if not id_usuario or not nombre or not fecha or not tipo:
        return jsonify({"error": "Campos requeridos: id_usuario, nombre, fecha, tipo"}), 400

    if tipo == "permiso":
        if not hora_permitida:
            return jsonify({"error": "Para permisos es obligatoria la hora de salida"}), 400
        if not hora_retorno_permiso:
            return jsonify({"error": "Para permisos es obligatoria la hora de retorno"}), 400
        if not _HORA_RE.match(hora_permitida) or not _HORA_RE.match(hora_retorno_permiso):
            return jsonify({"error": "Las horas deben tener formato HH:MM"}), 400
        if hora_retorno_permiso <= hora_permitida:
            return jsonify({"error": "La hora de retorno debe ser posterior a la de salida"}), 400

    if recuperable:
        if not fecha_recuperacion or not hora_recuperacion or not hora_recuperacion_fin:
            return jsonify({
                "error": "Para justificaciones recuperables es obligatoria la fecha, "
                         "hora inicio y hora fin de recuperación"
            }), 400
        try:
            f_rec = datetime.strptime(fecha_recuperacion, "%Y-%m-%d").date()
            if f_rec < date.today():
                return jsonify({"error": "La fecha de recuperación debe ser futura o el día de hoy"}), 400
        except ValueError:
            return jsonify({"error": "Formato de fecha_recuperacion inválido. Use YYYY-MM-DD"}), 400
        if not _HORA_RE.match(hora_recuperacion) or not _HORA_RE.match(hora_recuperacion_fin):
            return jsonify({"error": "Las horas de recuperación deben tener formato HH:MM"}), 400
        if hora_recuperacion_fin <= hora_recuperacion:
            return jsonify({"error": "La hora de fin de recuperación debe ser posterior a la de inicio"}), 400

    if tipo not in ("ausencia", "tardanza", "almuerzo", "incompleto", "salida_anticipada", "permiso"):
        return jsonify({
            "error": "tipo debe ser: ausencia | tardanza | almuerzo | "
                     "incompleto | salida_anticipada | permiso"
        }), 400
    try:
        result = insertar_justificacion(
            id_usuario, nombre, fecha, tipo, motivo, aprobado,
            hora_permitida, estado, duracion_permitida_min,
            hora_retorno_permiso=hora_retorno_permiso,
            incluye_almuerzo=incluye_almuerzo,
            recuperable=recuperable,
            fecha_recuperacion=fecha_recuperacion,
            hora_recuperacion=hora_recuperacion,
            hora_recuperacion_fin=hora_recuperacion_fin,
        )
        return jsonify({"success": True, "justificacion": result}), 201
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.patch("/api/justificaciones/<int:jid>")
def actualizar_justificacion_estado(jid: int):
    data = request.json or {}
    estado = data.get("estado")
    if estado not in ("aprobada", "rechazada", "pendiente"):
        return jsonify({"error": "Estado inválido"}), 400

    if actualizar_estado_justificacion(jid, estado):
        return jsonify({"success": True})
    return jsonify({"error": f"No existe justificación con ID {jid}"}), 404


@bp.get("/api/justificaciones/<int:jid>")
def get_justificacion(jid: int):
    j = get_justificacion_by_id(jid)
    if not j:
        return jsonify({"error": f"No existe justificación con ID {jid}"}), 404
    return jsonify({"justificacion": j})


@bp.put("/api/justificaciones/<int:jid>")
def actualizar_justificacion(jid: int):

    current = get_justificacion_by_id(jid)
    if not current:
        return jsonify({"error": f"No existe justificación con ID {jid}"}), 404

    data = request.json or {}
    campos: dict = {}

    permitidos = [
        "fecha", "tipo", "motivo", "aprobado_por", "hora_permitida", "estado",
        "duracion_permitida_min", "hora_retorno_permiso",
        "incluye_almuerzo", "recuperable", "fecha_recuperacion",
        "hora_recuperacion", "hora_recuperacion_fin",
    ]
    for k in permitidos:
        if k in data:
            campos[k] = data[k]

    if "duracion_permitida_min" in campos and \
            campos["duracion_permitida_min"] is not None and \
            str(campos["duracion_permitida_min"]).strip() != "":
        try:
            campos["duracion_permitida_min"] = int(campos["duracion_permitida_min"])
        except ValueError:
            return jsonify({"error": "duracion_permitida_min debe ser un número entero"}), 400
    elif "duracion_permitida_min" in campos:
        campos["duracion_permitida_min"] = None

    if "incluye_almuerzo" in campos:
        campos["incluye_almuerzo"] = 1 if campos["incluye_almuerzo"] else 0
    if "recuperable" in campos:
        campos["recuperable"] = 1 if campos["recuperable"] else 0

    rec = campos.get("recuperable", current.get("recuperable", 0))
    if rec:
        f_rec = campos.get("fecha_recuperacion", current.get("fecha_recuperacion"))
        h_rec = campos.get("hora_recuperacion", current.get("hora_recuperacion"))
        h_rec_fin = campos.get("hora_recuperacion_fin", current.get("hora_recuperacion_fin"))
        if not f_rec or not h_rec or not h_rec_fin:
            return jsonify({
                "error": "Para justificaciones recuperables es obligatoria la fecha, "
                         "hora inicio y hora fin de recuperación"
            }), 400
        if not _HORA_RE.match(str(h_rec)) or not _HORA_RE.match(str(h_rec_fin)):
            return jsonify({"error": "Las horas de recuperación deben tener formato HH:MM"}), 400
        if str(h_rec) >= str(h_rec_fin):
            return jsonify({"error": "La hora de fin de recuperación debe ser posterior a la de inicio"}), 400

    try:
        if actualizar_justificacion_completa(jid, **campos):
            return jsonify({"success": True})
        return jsonify({"error": "No se realizaron cambios o campos inválidos"}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Error al actualizar: {str(e)}"}), 500


@bp.delete("/api/justificaciones/<int:jid>")
@require_role("superadmin", "admin")
def eliminar_justificacion(jid: int):
    if not svc_eliminar_justificacion(jid):
        return jsonify({"error": f"No existe justificación con ID {jid}"}), 404
    return jsonify({"success": True})


# ══════════════════════════════════════════════════════════════════════════
# FERIADOS
# ══════════════════════════════════════════════════════════════════════════


@bp.get("/api/feriados")
def get_feriados():
    anio_str = request.args.get("anio")
    if anio_str:
        try:
            anio = int(anio_str)
            fi = date(anio, 1, 1)
            ff = date(anio, 12, 31)
        except ValueError:
            return jsonify({"error": "anio inválido"}), 400
        lista = svc_get_feriados(fi, ff)
    else:
        lista = svc_get_feriados()
    return jsonify({"feriados": lista})


@bp.post("/api/feriados")
@require_role("superadmin", "admin")
def crear_feriado():
    data = request.json or {}
    fecha       = str(data.get("fecha", "")).strip()
    descripcion = str(data.get("descripcion", "")).strip()
    tipo        = str(data.get("tipo", "nacional")).strip() or "nacional"
    if not fecha or not descripcion:
        return jsonify({"error": "Campos requeridos: fecha, descripcion"}), 400
    try:
        result = insertar_feriado(fecha, descripcion, tipo)
        return jsonify({"success": True, "feriado": result}), 201
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.delete("/api/feriados/<fecha>")
@require_role("superadmin", "admin")
def eliminar_feriado(fecha: str):
    if not svc_eliminar_feriado(fecha):
        return jsonify({"error": f"No existe feriado para la fecha {fecha}"}), 404
    return jsonify({"success": True})


@bp.post("/api/feriados/importar")
@require_role("superadmin", "admin")
def importar_feriados():
    if "archivo" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files["archivo"]
    if not file.filename.endswith(".csv"):
        return jsonify({"error": "Solo se aceptan archivos .csv"}), 400
    filename = secure_filename(file.filename)
    filepath = current_app.config["UPLOAD_FOLDER"] + f"/{uuid.uuid4().hex}_{filename}"
    file.save(filepath)
    try:
        count = importar_feriados_csv(filepath)
        return jsonify({"success": True, "total_importados": count})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            import os
            os.remove(filepath)
        except OSError:
            pass


@bp.get("/api/feriados/exportar")
def exportar_feriados():
    lista = svc_get_feriados()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["fecha", "descripcion", "tipo"])
    for f in lista:
        writer.writerow([f["fecha"], f["descripcion"], f["tipo"]])
    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=feriados.csv"},
    )
