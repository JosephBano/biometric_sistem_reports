"""
Blueprint de períodos (`app/web/periods_bp.py`).

Rutas (8):
  - GET    /periodos                       → vista de lista
  - POST   /periodos/crear                 → crear grupo de período
  - GET    /periodos/<id>                  → detalle
  - POST   /periodos/<id>/importar-personas → importar CSV de personas
  - POST   /periodos/<id>/cerrar           → cerrar período
  - POST   /periodos/<id>/archivar         → archivar
  - POST   /periodos/<id>/eliminar         → eliminar (superadmin)
"""
from __future__ import annotations

import os
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from app.domain.periods import (
    archivar_periodo,
    calcular_asistencia_periodo,
    cerrar_periodo,
    crear_periodo,
    eliminar_periodo,
    get_periodo,
    listar_periodos_activos,
    listar_periodos_historial,
    procesar_csv_personas_periodo,
)
from app.domain.rbac import require_role

bp = Blueprint("periods", __name__)


@bp.get("/periodos")
@require_role("admin", "superadmin", "gestor")
def lista():
    activos = listar_periodos_activos()
    historial = listar_periodos_historial()
    return render_template(
        "periodos/lista.html",
        active_page="periodos",
        periodos_activos=activos,
        periodos_historial=historial,
    )


@bp.post("/periodos/crear")
@require_role("admin", "superadmin")
def crear():

    nombre = request.form.get("nombre")
    fecha_inicio_str = request.form.get("fecha_inicio")
    fecha_fin_str = request.form.get("fecha_fin")
    descripcion = request.form.get("descripcion")

    if not nombre or not fecha_inicio_str:
        flash("Nombre y Fecha Inicio requeridos", "danger")
        return redirect(url_for("periods.lista"))

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
        fecha_fin = (
            datetime.strptime(fecha_fin_str, "%Y-%m-%d").date() if fecha_fin_str else None
        )
        crear_periodo(
            nombre=nombre, fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin, descripcion=descripcion,
        )
        flash("Período creado exitosamente", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")

    return redirect(url_for("periods.lista"))


@bp.get("/periodos/<id>")
@require_role("admin", "superadmin", "gestor")
def detalle(id: str):

    periodo = get_periodo(id)
    if not periodo:
        return "Periodo no encontrado", 404

    personas = calcular_asistencia_periodo(id)

    t_suma = 0
    for p in personas:
        t_suma += p["resumen"]["porcentaje_asistencia"]
    promedio = round(t_suma / len(personas), 2) if personas else 0

    resumen_general = {"asistencia_promedio": promedio}

    return render_template(
        "periodos/detalle.html",
        active_page="periodos",
        periodo=periodo,
        personas=personas,
        resumen_general=resumen_general,
    )


@bp.post("/periodos/<id>/importar-personas")
@require_role("admin", "superadmin")
def importar_personas(id: str):

    tipo_persona_id = request.form.get("tipo_persona_id")
    file = request.files.get("archivo_csv")

    if not file or not tipo_persona_id:
        flash("Archivo y Tipo Persona requeridos", "danger")
        return redirect(url_for("periods.detalle", id=id))

    filename = secure_filename(file.filename)
    filepath = current_app.config["UPLOAD_FOLDER"] + f"/periodo_{id}_{filename}"
    file.save(filepath)

    try:
        resultado = procesar_csv_personas_periodo(filepath, id, tipo_persona_id)
        if resultado.get("exito"):
            msg = (f"Cargado: {resultado['procesadas']} personas. "
                   f"Nuevas: {resultado['nuevas']}. "
                   f"Actualizadas: {resultado['actualizadas']}.")
            flash(msg, "success")
            if resultado.get("errores"):
                flash(f"Errores en {len(resultado['errores'])} registros.", "warning")
        else:
            flash(f"Error procesando CSV: {resultado.get('error')}", "danger")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass

    return redirect(url_for("periods.detalle", id=id))


@bp.post("/periodos/<id>/cerrar")
@require_role("admin", "superadmin")
def cerrar(id: str):
    if get_periodo(id):
        cerrar_periodo(id)
        flash("Período cerrado exitosamente", "success")
    return redirect(url_for("periods.lista"))


@bp.post("/periodos/<id>/archivar")
@require_role("admin", "superadmin")
def archivar(id: str):
    if get_periodo(id):
        archivar_periodo(id)
        flash("Período archivado exitosamente", "success")
    return redirect(url_for("periods.lista"))


@bp.post("/periodos/<id>/eliminar")
@require_role("superadmin")
def eliminar(id: str):
    eliminado = eliminar_periodo(id)
    if eliminado:
        flash("Período eliminado permanentemente.", "success")
    else:
        flash("Período no encontrado.", "danger")
    return redirect(url_for("periods.lista"))
