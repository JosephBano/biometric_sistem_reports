"""
Blueprint de personas (`app/web/people_bp.py`).

Rutas (4):
  - GET  /personas                  → lista filtrable
  - POST /personas/crear            → crear persona
  - POST /personas/<id>             → editar persona
  - GET  /personas/historico        → vista de histórico
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.domain.people import (
    actualizar_persona,
    crear_persona,
    get_historico_persona,
    listar_grupos,
    listar_personas,
)
from app.domain.rbac import require_role

bp = Blueprint("people", __name__)


@bp.get("/personas")
@require_role("admin", "superadmin", "gestor")
def lista():
    tipo_persona_id = request.args.get("tipo_persona_id", "").strip() or None
    grupo_id = request.args.get("grupo_id", "").strip() or None
    busqueda = request.args.get("q", "").strip() or None
    personas = listar_personas(
        tipo_persona_id=tipo_persona_id, grupo_id=grupo_id,
        activo=None, busqueda=busqueda,
    )
    grupos = listar_grupos(activo=True)
    return render_template(
        "personas/lista.html",
        active_page="personas",
        personas=personas,
        grupos=grupos,
        tipo_persona_id=tipo_persona_id,
        grupo_id=grupo_id,
        busqueda=busqueda or "",
    )


@bp.post("/personas/crear")
@require_role("admin", "superadmin")
def crear():
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("El nombre es requerido", "danger")
        return redirect(url_for("people.lista"))
    try:
        crear_persona(
            nombre=nombre,
            identificacion=request.form.get("identificacion") or None,
            tipo_persona_id=request.form.get("tipo_persona_id") or None,
            grupo_id=request.form.get("grupo_id") or None,
            categoria_id=request.form.get("categoria_id") or None,
            email=request.form.get("email") or None,
            telefono=request.form.get("telefono") or None,
            notas=request.form.get("notas") or None,
            id_usuario_zk=request.form.get("id_usuario_zk") or None,
        )
        flash("Persona creada exitosamente", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error al crear persona: {e}", "danger")
    return redirect(url_for("people.lista"))


@bp.post("/personas/<id>")
@require_role("admin", "superadmin")
def editar(id: str):
    datos: dict = {}
    for campo in ("nombre", "identificacion", "email", "telefono", "notas",
                  "tipo_persona_id", "grupo_id", "categoria_id"):
        v = request.form.get(campo)
        if v is not None:
            datos[campo] = v or None
    activo_val = request.form.get("activo")
    if activo_val is not None:
        datos["activo"] = activo_val == "1"
    if "id_usuario_zk" in request.form:
        datos["id_usuario_zk"] = request.form.get("id_usuario_zk", "").strip() or ""
    try:
        actualizar_persona(id, datos)
        flash("Persona actualizada", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error al actualizar persona: {e}", "danger")
    return redirect(url_for("people.lista"))


@bp.get("/personas/historico")
@require_role("admin", "superadmin", "gestor")
def historico():
    identificacion = request.args.get("identificacion", "").strip()
    historico_data = None
    if identificacion:
        historico_data = get_historico_persona(identificacion)
    return render_template(
        "personas/historico.html",
        active_page="personas",
        identificacion=identificacion,
        historico=historico_data,
    )
