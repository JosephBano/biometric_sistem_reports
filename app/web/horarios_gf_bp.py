"""
Blueprint de horarios por grupo funcional (`app/web/horarios_gf_bp.py`).

Rutas:
  - GET  /admin/horarios-grupo-funcional                 → lista grupos con sus defaults e integrantes
  - POST /admin/horarios-grupo-funcional/crear           → crea nuevo grupo (+ horario base opcional)
  - POST /admin/horarios-grupo-funcional/<id>/default    → asigna plantilla default
  - POST /admin/horarios-grupo-funcional/<id>/personas/agregar → asigna personas existentes al grupo
  - POST /admin/horarios-grupo-funcional/<id>/personas/crear   → crea nueva persona y la asigna al grupo
  - POST /admin/horarios-grupo-funcional/<id>/personas/csv     → carga masiva CSV para este grupo
  - POST /admin/personas/<id>/grupo-funcional/cerrar     → desvincula persona del grupo
"""
from __future__ import annotations

from datetime import date
import os
import tempfile
from werkzeug.utils import secure_filename

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.domain.horarios_grupo_funcional import (
    asignar_horario_default_grupo,
    asignar_persona_a_grupo_funcional,
    asignar_personas_masivo_a_grupo_funcional,
    cerrar_vinculo_persona_grupo_funcional,
    listar_horarios_default_grupo,
    listar_horarios as listar_horarios_activos,
    listar_personas_detalladas_en_grupo_funcional,
    procesar_csv_personas_grupo_funcional,
)
from app.domain.grupos_funcionales import (
    crear as crear_grupo_funcional,
    listar as listar_grupos_funcionales_domain,
)
from app.domain.people import (
    crear_persona,
    listar_grupos_funcionales,
    listar_personas,
    listar_tipos_persona,
    reordenar_a_apellido_nombre,
)
from app.domain.rbac import require_role

bp = Blueprint("horarios_gf", __name__)


@bp.get("/admin/horarios-grupo-funcional")
@require_role("admin", "superadmin")
def vista_horarios_gf():
    """Vista que muestra cada grupo funcional con sus horarios default asignados e integrantes."""
    grupos_funcionales = listar_grupos_funcionales(activo=True)
    detalles = []
    for gf in grupos_funcionales:
        defaults = listar_horarios_default_grupo(gf["id"])
        personas_gf = listar_personas_detalladas_en_grupo_funcional(gf["id"])
        for p in personas_gf:
            p["nombre_mostrar"] = reordenar_a_apellido_nombre(p.get("nombre") or "")
        personas_gf.sort(key=lambda x: (x.get("nombre_mostrar") or "").upper())
        detalles.append({
            "gf": gf,
            "defaults": defaults,
            "personas": personas_gf,
            "total_personas": len(personas_gf),
        })

    plantillas = listar_horarios_activos()
    tipos_persona = listar_tipos_persona()

    # Todas las personas activas para asignación manual
    todas_personas = listar_personas(activo=True)
    for p in todas_personas:
        p["nombre_mostrar"] = reordenar_a_apellido_nombre(p.get("nombre") or "")
    todas_personas.sort(key=lambda x: (x.get("nombre_mostrar") or "").upper())

    return render_template(
        "admin/horarios_grupo_funcional.html",
        active_page="admin_horarios_gf",
        detalles=detalles,
        plantillas=plantillas,
        tipos_persona=tipos_persona,
        todas_personas=todas_personas,
    )


@bp.post("/admin/horarios-grupo-funcional/crear")
@require_role("admin", "superadmin")
def crear_grupo():
    """Crea un nuevo grupo funcional con opción de asignar horario base inicial."""
    nombre = (request.form.get("nombre") or "").strip()
    codigo = (request.form.get("codigo") or nombre).strip()
    tipo_persona_id = request.form.get("tipo_persona_id") or None
    plantilla_id = request.form.get("plantilla_id") or None
    fecha_inicio_str = request.form.get("fecha_inicio")
    fecha_inicio = date.fromisoformat(fecha_inicio_str) if fecha_inicio_str else date.today()

    if not nombre:
        flash("El nombre del grupo es obligatorio", "danger")
        return redirect(url_for("horarios_gf.vista_horarios_gf"))

    try:
        gf = crear_grupo_funcional(
            codigo=codigo,
            nombre=nombre,
            tipo_persona_id=tipo_persona_id,
        )
        if gf and plantilla_id:
            asignar_horario_default_grupo(
                grupo_funcional_id=gf["id"],
                plantilla_id=plantilla_id,
                fecha_inicio=fecha_inicio,
                prioridad=0,
            )
        flash(f"Grupo '{nombre}' creado exitosamente", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error al crear grupo: {e}", "danger")

    return redirect(url_for("horarios_gf.vista_horarios_gf"))


@bp.post("/admin/horarios-grupo-funcional/<id>/default")
@require_role("admin", "superadmin")
def asignar_default(id: str):
    """Asigna una plantilla como horario default de un grupo funcional."""
    plantilla_id = request.form.get("plantilla_id")
    prioridad = int(request.form.get("prioridad", "0") or "0")
    fecha_inicio_str = request.form.get("fecha_inicio")
    fecha_inicio = date.fromisoformat(fecha_inicio_str) if fecha_inicio_str else date.today()
    if not plantilla_id:
        flash("Selecciona una plantilla", "danger")
        return redirect(url_for("horarios_gf.vista_horarios_gf"))
    try:
        asignar_horario_default_grupo(
            grupo_funcional_id=id,
            plantilla_id=plantilla_id,
            fecha_inicio=fecha_inicio,
            prioridad=prioridad,
        )
        flash("Horario asignado al grupo", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("horarios_gf.vista_horarios_gf"))


@bp.post("/admin/horarios-grupo-funcional/<id>/personas/agregar")
@require_role("admin", "superadmin")
def agregar_personas_manual(id: str):
    """Asigna personas seleccionadas manualmente a este grupo funcional."""
    persona_ids = request.form.getlist("persona_ids")
    fecha_inicio_str = request.form.get("fecha_inicio")
    fecha_inicio = date.fromisoformat(fecha_inicio_str) if fecha_inicio_str else date.today()

    if not persona_ids:
        flash("Debes seleccionar al menos una persona para agregar al grupo", "warning")
        return redirect(url_for("horarios_gf.vista_horarios_gf"))

    try:
        count = asignar_personas_masivo_a_grupo_funcional(
            grupo_funcional_id=id,
            persona_ids=persona_ids,
            fecha_inicio=fecha_inicio,
            es_principal=True,
        )
        flash(f"Se agregaron {count} personas al grupo correctamente", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error al asignar personas: {e}", "danger")

    return redirect(url_for("horarios_gf.vista_horarios_gf"))


@bp.post("/admin/horarios-grupo-funcional/<id>/personas/crear")
@require_role("admin", "superadmin")
def crear_persona_en_grupo(id: str):
    """Crea una nueva persona desde cero y la asigna inmediatamente a este grupo."""
    nombre = (request.form.get("nombre") or "").strip()
    identificacion = (request.form.get("identificacion") or "").strip() or None
    id_usuario_zk = (request.form.get("id_usuario_zk") or "").strip() or None
    email = (request.form.get("email") or "").strip() or None
    telefono = (request.form.get("telefono") or "").strip() or None
    tipo_persona_id = request.form.get("tipo_persona_id") or None
    fecha_inicio_str = request.form.get("fecha_inicio")
    fecha_inicio = date.fromisoformat(fecha_inicio_str) if fecha_inicio_str else date.today()

    if not nombre:
        flash("El nombre de la persona es obligatorio", "danger")
        return redirect(url_for("horarios_gf.vista_horarios_gf"))

    try:
        p = crear_persona(
            nombre=nombre,
            identificacion=identificacion,
            tipo_persona_id=tipo_persona_id,
            email=email,
            telefono=telefono,
            id_usuario_zk=id_usuario_zk,
        )
        if p and p.get("id"):
            asignar_persona_a_grupo_funcional(
                persona_id=p["id"],
                grupo_funcional_id=id,
                fecha_inicio=fecha_inicio,
                es_principal=True,
            )
            flash(f"Persona '{nombre}' creada y asignada al grupo", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error al crear persona: {e}", "danger")

    return redirect(url_for("horarios_gf.vista_horarios_gf"))


@bp.post("/admin/horarios-grupo-funcional/<id>/personas/csv")
@require_role("admin", "superadmin")
def importar_csv_personas_gf(id: str):
    """Carga masiva mediante archivo CSV para este grupo funcional."""
    if "archivo_csv" not in request.files:
        flash("No se subió ningún archivo CSV", "danger")
        return redirect(url_for("horarios_gf.vista_horarios_gf"))

    file = request.files["archivo_csv"]
    if not file.filename or not file.filename.lower().endswith(".csv"):
        flash("El archivo debe tener formato .CSV", "warning")
        return redirect(url_for("horarios_gf.vista_horarios_gf"))

    fecha_inicio_str = request.form.get("fecha_inicio")
    fecha_inicio = date.fromisoformat(fecha_inicio_str) if fecha_inicio_str else date.today()

    tmp_dir = tempfile.gettempdir()
    filepath = os.path.join(tmp_dir, secure_filename(file.filename))
    file.save(filepath)

    try:
        res = procesar_csv_personas_grupo_funcional(
            filepath=filepath,
            grupo_funcional_id=id,
            fecha_inicio=fecha_inicio,
        )
        if res.get("exito"):
            flash(
                f"CSV procesado: {res['procesadas']} personas asignadas al grupo "
                f"({res['nuevas']} nuevas, {res['asociadas']} vinculadas).",
                "success",
            )
            if res.get("errores"):
                flash(f"Advertencias ({len(res['errores'])}): " + "; ".join(res["errores"][:3]), "warning")
        else:
            flash(f"Error en CSV: {res.get('error')}", "danger")
    except Exception as e:  # noqa: BLE001
        flash(f"Error procesando CSV: {e}", "danger")
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

    return redirect(url_for("horarios_gf.vista_horarios_gf"))


@bp.post("/admin/personas/<id>/grupo-funcional/cerrar")
@require_role("admin", "superadmin")
def cerrar_persona_gf(id: str):
    """Cierra el vinculo persona-grupo_funcional (fecha_fin = hoy)."""
    grupo_funcional_id = request.form.get("grupo_funcional_id")
    if not grupo_funcional_id:
        flash("Falta grupo_funcional_id", "danger")
        return redirect(url_for("horarios_gf.vista_horarios_gf"))
    try:
        cerrar_vinculo_persona_grupo_funcional(
            persona_id=id,
            grupo_funcional_id=grupo_funcional_id,
            fecha_fin=date.today(),
        )
        flash("Persona desvinculada del grupo", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("horarios_gf.vista_horarios_gf"))