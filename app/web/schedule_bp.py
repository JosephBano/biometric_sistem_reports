"""
Blueprint de horarios personalizados (`app/web/schedule_bp.py`).

Rutas (7):
  - POST /api/horarios/importar          → carga .csv/.obd/.ods
  - GET  /api/horarios/estado            → estado actual
  - GET  /api/horarios                   → lista de horarios
  - GET  /api/horarios/exportar          → CSV de todos los horarios
  - POST /api/horarios                   → crear un horario
  - PUT  /api/horarios/<id_usuario>      → actualizar
  - DELETE /api/horarios/<id_usuario>    → eliminar
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request
from werkzeug.utils import secure_filename

from app.domain import attendance as attendance_svc
from app.domain.rbac import require_role
from app.domain.schedule import (
    delete_horario,
    get_estado_horarios,
    get_horario,
    get_horarios,
    get_ids_usuarios_zk,
    upsert_horario,
    upsert_horarios,
)

bp = Blueprint("schedule", __name__)

ALLOWED_EXT = {".obd", ".ods", ".csv"}

_HORA_RE = re.compile(r"^\d{2}:\d{2}$")
_DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _validar_horario_body(data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """
    Valida y normaliza el cuerpo JSON para crear/editar un horario.
    Retorna (horario_dict, error_str) — error_str es None si válido.
    """
    id_str = str(data.get("id_usuario", "")).strip()
    nombre = str(data.get("nombre", "")).strip()

    if not id_str:
        return None, "El campo id_usuario es requerido."
    try:
        id_usuario = str(int(float(id_str)))
    except (ValueError, TypeError):
        return None, "id_usuario debe ser un número entero."
    if not nombre:
        return None, "El campo nombre es requerido."

    horario: dict[str, Any] = {
        "id_usuario": id_usuario,
        "nombre":     nombre,
        "domingo":    None,
        "notas":      str(data.get("notas", "")).strip(),
    }

    for dia in _DIAS:
        val = data.get(dia)
        if val is None or str(val).strip() == "":
            horario[dia] = None
        else:
            val_s = str(val).strip()
            if not _HORA_RE.match(val_s):
                return None, f"El campo '{dia}' debe tener formato HH:MM o estar vacío."
            horario[dia] = val_s

        col_salida = f"{dia}_salida"
        val_salida = data.get(col_salida)
        if val_salida is None or str(val_salida).strip() == "":
            horario[col_salida] = None
        else:
            val_salida_s = str(val_salida).strip()
            if not _HORA_RE.match(val_salida_s):
                return None, f"El campo '{col_salida}' debe tener formato HH:MM o estar vacío."
            if horario[dia] and val_salida_s <= horario[dia]:
                return None, f"El campo '{col_salida}' debe ser posterior a '{dia}'."
            horario[col_salida] = val_salida_s

        col_alm = f"{dia}_almuerzo_min"
        val_alm = data.get(col_alm)
        if val_alm is not None and str(val_alm).strip() != "":
            try:
                horario[col_alm] = int(val_alm)
            except ValueError:
                return None, f"El campo '{col_alm}' debe ser un entero."
        else:
            horario[col_alm] = None

    try:
        almuerzo_min = int(data.get("almuerzo_min", 0))
    except (ValueError, TypeError):
        return None, "almuerzo_min debe ser un entero (0, 30 o 60)."
    if almuerzo_min not in (0, 30, 60):
        return None, "almuerzo_min debe ser 0, 30 o 60."
    horario["almuerzo_min"] = almuerzo_min

    # Horas de contrato (Parte I)
    horas_semana = data.get("horas_semana")
    horas_mes    = data.get("horas_mes")

    def _parse_horas(val, campo):
        if val is None or str(val).strip() == "":
            return None, None
        try:
            v = float(val)
            if v <= 0:
                raise ValueError
            return v, None
        except (ValueError, TypeError):
            return None, f"'{campo}' debe ser un número positivo."

    hs, err = _parse_horas(horas_semana, "horas_semana")
    if err:
        return None, err
    hm, err = _parse_horas(horas_mes, "horas_mes")
    if err:
        return None, err
    if hs is not None and hm is not None:
        return None, "Solo puede especificarse 'horas_semana' O 'horas_mes', no ambas."

    horario["horas_semana"] = hs
    horario["horas_mes"]    = hm

    return horario, None


# ── Importar ─────────────────────────────────────────────────────────────

@bp.post("/api/horarios/importar")
@require_role("superadmin", "admin", "gestor")
def cargar_horarios():
    """
    Recibe un archivo .obd/.ods/.csv, lo parsea e inserta los horarios.
    Retorna cuántos horarios se cargaron y cuántos IDs no se encontraron en ZK.
    """

    if "archivo" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400

    file = request.files["archivo"]
    if file.filename == "":
        return jsonify({"error": "Archivo no seleccionado"}), 400

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "Formato no soportado. Use .csv, .obd o .ods"}), 400

    filename  = secure_filename(file.filename)
    save_name = f"{uuid.uuid4().hex}_{filename}"
    filepath  = current_app.config["UPLOAD_FOLDER"] + "/" + save_name
    file.save(filepath)

    try:
        if ext == ".csv":
            horarios_lista = attendance_svc.parsear_csv(filepath)
        else:
            horarios_lista = attendance_svc.parsear_obd(filepath)

        if not horarios_lista:
            return jsonify({"error": "El archivo no contiene datos de horarios válidos"}), 400

        ids_zk = get_ids_usuarios_zk()
        ids_sin_match = [
            h["id_usuario"] for h in horarios_lista
            if h["id_usuario"] not in ids_zk
        ]
        upsert_horarios(horarios_lista, fuente=file.filename)

        return jsonify({
            "success":        True,
            "total_cargados": len(horarios_lista),
            "sin_match_zk":   ids_sin_match,
            "fuente":         file.filename,
        })
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            import os
            os.remove(filepath)
        except OSError:
            pass


# ── Estado y listado ─────────────────────────────────────────────────────

@bp.get("/api/horarios/estado")
def estado_horarios():
    return jsonify(get_estado_horarios())


@bp.get("/api/horarios")
def ver_horarios():
    horarios = get_horarios()
    lista = sorted(horarios["by_id"].values(), key=lambda h: h["nombre"])
    return jsonify({"horarios": lista, "total": len(lista)})


# ── Exportar ─────────────────────────────────────────────────────────────

@bp.get("/api/horarios/exportar")
@require_role("superadmin", "admin", "gestor")
def exportar_horarios_csv():
    horarios = get_horarios()
    lista = sorted(horarios["by_id"].values(), key=lambda h: h["nombre"])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id_usuario", "nombre", "lunes", "martes", "miercoles",
        "jueves", "viernes", "sabado", "domingo",
        "lunes_salida", "martes_salida", "miercoles_salida", "jueves_salida",
        "viernes_salida", "sabado_salida", "domingo_salida",
        "almuerzo_min",
        "lunes_almuerzo_min", "martes_almuerzo_min", "miercoles_almuerzo_min",
        "jueves_almuerzo_min", "viernes_almuerzo_min", "sabado_almuerzo_min",
        "domingo_almuerzo_min",
        "horas_semana", "horas_mes", "notas",
    ])
    for h in lista:
        writer.writerow([
            h["id_usuario"], h["nombre"],
            h.get("lunes") or "", h.get("martes") or "", h.get("miercoles") or "",
            h.get("jueves") or "", h.get("viernes") or "", h.get("sabado") or "",
            h.get("domingo") or "",
            h.get("lunes_salida") or "", h.get("martes_salida") or "",
            h.get("miercoles_salida") or "", h.get("jueves_salida") or "",
            h.get("viernes_salida") or "", h.get("sabado_salida") or "",
            h.get("domingo_salida") or "",
            h.get("almuerzo_min", 0),
            h.get("lunes_almuerzo_min", ""), h.get("martes_almuerzo_min", ""),
            h.get("miercoles_almuerzo_min", ""), h.get("jueves_almuerzo_min", ""),
            h.get("viernes_almuerzo_min", ""), h.get("sabado_almuerzo_min", ""),
            h.get("domingo_almuerzo_min", ""),
            h.get("horas_semana") or "", h.get("horas_mes") or "",
            h.get("notas") or "",
        ])

    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=horarios.csv"},
    )


# ── CRUD ─────────────────────────────────────────────────────────────────

@bp.post("/api/horarios")
@require_role("superadmin", "admin", "gestor")
def api_horarios_crear():
    data = request.json or {}
    horario, error = _validar_horario_body(data)
    if error:
        return jsonify({"error": error}), 400

    if get_horario(horario["id_usuario"]):
        return jsonify({
            "error": f"Ya existe un horario con ID {horario['id_usuario']}. "
                     "Use PUT para actualizar."
        }), 409

    resultado = upsert_horario(horario, fuente="manual")
    return jsonify({"success": True, "horario": resultado}), 201


@bp.put("/api/horarios/<id_usuario>")
@require_role("superadmin", "admin", "gestor")
def api_horarios_actualizar(id_usuario: str):
    if not get_horario(id_usuario):
        return jsonify({"error": f"No existe horario con ID {id_usuario}."}), 404

    data = request.json or {}
    data["id_usuario"] = id_usuario
    horario, error = _validar_horario_body(data)
    if error:
        return jsonify({"error": error}), 400

    resultado = upsert_horario(horario, fuente="manual")
    return jsonify({"success": True, "horario": resultado})


@bp.delete("/api/horarios/<id_usuario>")
@require_role("superadmin", "admin")
def api_horarios_eliminar(id_usuario: str):
    if not delete_horario(id_usuario):
        return jsonify({"error": f"No existe horario con ID {id_usuario}."}), 404
    return jsonify({"success": True})
