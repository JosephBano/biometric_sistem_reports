"""
Blueprint de horarios por grupo funcional (`app/web/horarios_gf_bp.py`).

Rutas:
  - GET  /admin/horarios-grupo-funcional          → lista grupos con sus defaults
  - POST /admin/horarios-grupo-funcional          → crea un grupo + horario default
  - POST /admin/horarios-grupo-funcional/<id>     → actualiza grupo (nombre, activo)
  - POST /admin/personas/<id>/grupo-funcional     → asigna gf a persona
  - POST /api/horarios-grupo-funcional/<id>/default → asigna plantilla default
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.domain.horarios_grupo_funcional import (
    asignar_horario_default_grupo,
    asignar_persona_a_grupo_funcional,
    cerrar_vinculo_persona_grupo_funcional,
    listar_horarios_default_grupo,
    listar_horarios as listar_horarios_activos,
)
from app.domain.people import listar_grupos_funcionales
from app.domain.rbac import require_role

bp = Blueprint("horarios_gf", __name__)


@bp.get("/admin/horarios-grupo-funcional")
@require_role("admin", "superadmin")
def vista_horarios_gf():
    """Vista que muestra cada grupo funcional con sus horarios default asignados."""
    grupos_funcionales = listar_grupos_funcionales(activo=True)
    detalles = []
    for gf in grupos_funcionales:
        defaults = listar_horarios_default_grupo(gf["id"])
        detalles.append({"gf": gf, "defaults": defaults})
    plantillas = listar_horarios_activos()
    return render_template(
        "admin/horarios_grupo_funcional.html",
        active_page="admin_horarios_gf",
        detalles=detalles,
        plantillas=plantillas,
    )


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
        flash("Horario default asignado", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("horarios_gf.vista_horarios_gf"))


@bp.post("/admin/personas/<id>/grupo-funcional")
@require_role("admin", "superadmin")
def asignar_persona_gf(id: str):
    """Asigna una persona a un grupo funcional (N:M con vigencia)."""
    grupo_funcional_id = request.form.get("grupo_funcional_id")
    es_principal = request.form.get("es_principal") == "1"
    fecha_inicio_str = request.form.get("fecha_inicio")
    fecha_inicio = date.fromisoformat(fecha_inicio_str) if fecha_inicio_str else date.today()
    if not grupo_funcional_id:
        flash("Selecciona un grupo funcional", "danger")
        return redirect(request.referrer or url_for("people.lista"))
    try:
        asignar_persona_a_grupo_funcional(
            persona_id=id,
            grupo_funcional_id=grupo_funcional_id,
            fecha_inicio=fecha_inicio,
            es_principal=es_principal,
        )
        flash("Persona asignada al grupo funcional", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(request.referrer or url_for("people.lista"))


@bp.post("/admin/personas/<id>/grupo-funcional/cerrar")
@require_role("admin", "superadmin")
def cerrar_persona_gf(id: str):
    """Cierra el vinculo persona-grupo_funcional (fecha_fin = hoy)."""
    grupo_funcional_id = request.form.get("grupo_funcional_id")
    if not grupo_funcional_id:
        flash("Falta grupo_funcional_id", "danger")
        return redirect(request.referrer or url_for("people.lista"))
    try:
        cerrar_vinculo_persona_grupo_funcional(
            persona_id=id,
            grupo_funcional_id=grupo_funcional_id,
            fecha_fin=date.today(),
        )
        flash("Vinculo cerrado", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(request.referrer or url_for("people.lista"))