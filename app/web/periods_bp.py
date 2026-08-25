"""
Blueprint de períodos (`app/web/periods_bp.py`).

Rutas:
  - GET    /periodos                        → vista de lista
  - POST   /periodos/crear                  → crear grupo de período
  - GET    /periodos/<id>                   → detalle y asistencia
  - POST   /periodos/<id>/importar-personas  → importar CSV de personas
  - POST   /periodos/<id>/agregar-manual     → agregar personas existentes o crear nueva
  - POST   /periodos/<id>/remover-persona/<persona_id> → quitar persona del período
  - POST   /periodos/<id>/cerrar            → cerrar período
  - POST   /periodos/<id>/archivar          → archivar
  - POST   /periodos/<id>/eliminar          → eliminar (superadmin)
"""
from __future__ import annotations

import os
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from app.domain.periods import (
    agregar_personas_a_periodo_bulk,
    archivar_periodo,
    calcular_asistencia_periodo,
    cerrar_periodo,
    crear_periodo,
    crear_persona,
    eliminar_periodo,
    get_periodo,
    listar_grupos,
    listar_grupos_funcionales,
    listar_periodos_activos,
    listar_periodos_historial,
    listar_personas,
    procesar_csv_personas_periodo,
    remover_persona_de_periodo,
    reordenar_a_apellido_nombre,
)
from app.domain.rbac import require_role

bp = Blueprint("periods", __name__)


@bp.get("/periodos")
@require_role("admin", "superadmin", "gestor")
def lista():
    tipo_persona_id = request.args.get("tipo_persona_id", "").strip() or None
    q = request.args.get("q", "").strip() or None

    activos = listar_periodos_activos(tipo_persona_id=tipo_persona_id)
    historial = listar_periodos_historial(tipo_persona_id=tipo_persona_id)

    if q:
        q_upper = q.upper()
        activos = [
            p for p in activos
            if q_upper in (p.get("nombre") or "").upper()
            or q_upper in (p.get("descripcion") or "").upper()
        ]
        historial = [
            p for p in historial
            if q_upper in (p.get("nombre") or "").upper()
            or q_upper in (p.get("descripcion") or "").upper()
        ]

    return render_template(
        "periodos/lista.html",
        active_page="periodos",
        periodos_activos=activos,
        periodos_historial=historial,
        tipo_persona_id=tipo_persona_id or "",
        busqueda=q or "",
    )


@bp.post("/periodos/crear")
@require_role("admin", "superadmin")
def crear():
    nombre = request.form.get("nombre", "").strip()
    fecha_inicio_str = request.form.get("fecha_inicio", "").strip()
    fecha_fin_str = request.form.get("fecha_fin", "").strip()
    descripcion = request.form.get("descripcion", "").strip() or None

    if not nombre or not fecha_inicio_str:
        flash("El nombre y la fecha de inicio son obligatorios", "danger")
        return redirect(url_for("periods.lista"))

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
        fecha_fin = (
            datetime.strptime(fecha_fin_str, "%Y-%m-%d").date() if fecha_fin_str else None
        )
        if fecha_fin and fecha_fin < fecha_inicio:
            flash("La fecha de fin no puede ser anterior a la fecha de inicio", "danger")
            return redirect(url_for("periods.lista"))

        crear_periodo(
            nombre=nombre, fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin, descripcion=descripcion,
        )
        flash("Período de seguimiento creado exitosamente", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error al crear período: {e}", "danger")

    return redirect(url_for("periods.lista"))


@bp.get("/periodos/<id>")
@require_role("admin", "superadmin", "gestor")
def detalle(id: str):
    periodo = get_periodo(id)
    if not periodo:
        return "Período no encontrado", 404

    personas = calcular_asistencia_periodo(id)

    t_suma = 0
    con_alertas = 0
    sin_horario = 0
    for p in personas:
        t_suma += p["resumen"]["porcentaje_asistencia"]
        if p["resumen"].get("ausentes", 0) > 2:
            con_alertas += 1
        if p["resumen"].get("sin_horario"):
            sin_horario += 1

    promedio = round(t_suma / len(personas), 1) if personas else 0

    resumen_general = {
        "asistencia_promedio": promedio,
        "total_personas": len(personas),
        "con_alertas": con_alertas,
        "sin_horario": sin_horario,
    }

    # Formatear nombres como 'Apellidos Nombres' y ordenar alfabéticamente
    for p in personas:
        p["nombre_mostrar"] = reordenar_a_apellido_nombre(p.get("nombre") or "")
    personas.sort(key=lambda x: (x.get("nombre_mostrar") or "").upper())

    # Obtener catálogo de personas del sistema para permitir selección manual
    ids_en_periodo = {str(p["persona_id"]) for p in personas}
    catalogo_personas = listar_personas(activo=True)
    personas_disponibles = []
    for p in catalogo_personas:
        if str(p["id"]) not in ids_en_periodo:
            p["nombre_mostrar"] = reordenar_a_apellido_nombre(p.get("nombre") or "")
            personas_disponibles.append(p)

    personas_disponibles.sort(key=lambda x: (x.get("nombre_mostrar") or "").upper())

    grupos = listar_grupos(activo=True)
    grupos_funcionales = listar_grupos_funcionales(activo=True)

    return render_template(
        "periodos/detalle.html",
        active_page="periodos",
        periodo=periodo,
        personas=personas,
        resumen_general=resumen_general,
        personas_disponibles=personas_disponibles,
        grupos=grupos,
        grupos_funcionales=grupos_funcionales,
    )


@bp.post("/periodos/<id>/agregar-manual")
@require_role("admin", "superadmin")
def agregar_manual(id: str):
    periodo = get_periodo(id)
    if not periodo:
        flash("Período no encontrado", "danger")
        return redirect(url_for("periods.lista"))

    modo = request.form.get("modo", "existentes")

    if modo == "existentes":
        personas_ids = request.form.getlist("personas_ids")
        if not personas_ids:
            # Intentar leer selector individual o separado por comas
            persona_id_single = request.form.get("persona_id")
            if persona_id_single:
                personas_ids = [persona_id_single]

        if not personas_ids:
            flash("Debe seleccionar al menos una persona para agregar.", "warning")
            return redirect(url_for("periods.detalle", id=id))

        resultado = agregar_personas_a_periodo_bulk(id, personas_ids)
        if resultado.get("exito"):
            creados = resultado.get("creados", 0)
            flash(f"Se agregaron {creados} persona(s) al período correctamente.", "success")
        else:
            flash(f"Error al agregar personas: {resultado.get('error')}", "danger")

    elif modo == "nueva":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("El nombre de la persona es obligatorio.", "danger")
            return redirect(url_for("periods.detalle", id=id))

        try:
            nueva_persona = crear_persona(
                nombre=nombre,
                identificacion=request.form.get("identificacion", "").strip() or None,
                tipo_persona_id=request.form.get("tipo_persona_id", "").strip() or None,
                grupo_id=request.form.get("grupo_id", "").strip() or None,
                grupo_funcional_id=request.form.get("grupo_funcional_id", "").strip() or None,
                email=request.form.get("email", "").strip() or None,
                telefono=request.form.get("telefono", "").strip() or None,
                notas=request.form.get("notas", "").strip() or None,
                id_usuario_zk=request.form.get("id_usuario_zk", "").strip() or None,
            )
            agregar_personas_a_periodo_bulk(id, [nueva_persona["id"]])
            flash(f"Persona «{nombre}» creada y agregada al período exitosamente.", "success")
        except Exception as e:  # noqa: BLE001
            flash(f"Error al registrar y agregar persona: {e}", "danger")

    return redirect(url_for("periods.detalle", id=id))


@bp.post("/periodos/<id>/remover-persona/<persona_id>")
@require_role("admin", "superadmin")
def remover_persona(id: str, persona_id: str):
    periodo = get_periodo(id)
    if not periodo:
        flash("Período no encontrado", "danger")
        return redirect(url_for("periods.lista"))

    removido = remover_persona_de_periodo(id, persona_id)
    if removido:
        flash("Persona desvinculada del período.", "success")
    else:
        flash("No se pudo desvincular a la persona del período.", "warning")

    return redirect(url_for("periods.detalle", id=id))


@bp.post("/periodos/<id>/importar-personas")
@require_role("admin", "superadmin")
def importar_personas(id: str):
    tipo_persona_id = request.form.get("tipo_persona_id")
    file = request.files.get("archivo_csv")

    if not file or not tipo_persona_id:
        flash("Archivo CSV y Tipo de Persona requeridos", "danger")
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
