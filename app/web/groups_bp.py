"""
Blueprint de grupos y grupos funcionales (`app/web/groups_bp.py`).

Rutas (6):
  - GET   /admin/grupos
  - POST  /admin/grupos
  - POST  /admin/grupos/<id>
  - GET   /admin/grupos-funcionales
  - POST  /admin/grupos-funcionales
  - POST  /admin/grupos-funcionales/<id>
"""
from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.domain.groups import (
    actualizar_grupo as svc_actualizar_grupo,
    actualizar_grupo_funcional as svc_actualizar_grupo_funcional,
    crear_grupo as svc_crear_grupo,
    crear_grupo_funcional as svc_crear_grupo_funcional,
    listar_grupos as svc_listar_grupos,
    listar_grupos_funcionales as svc_listar_grupos_funcionales,
)
from app.domain.rbac import require_role

bp = Blueprint("groups", __name__)


# ── Grupos (operativos) ────────────────────────────────────────────────────────

@bp.get("/admin/grupos")
@require_role("admin", "superadmin")
def listar_grupos():
    grupos = svc_listar_grupos()
    return render_template(
        "admin/grupos.html", active_page="admin_grupos", grupos=grupos,
    )


@bp.post("/admin/grupos")
@require_role("admin", "superadmin", "gestor")
def crear_grupo():
    is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json"
    if request.is_json:
        data = request.get_json() or {}
        nombre = str(data.get("nombre", "")).strip()
        tipo_grupo = str(data.get("tipo_grupo", "general"))
    else:
        nombre = request.form.get("nombre", "").strip()
        tipo_grupo = request.form.get("tipo_grupo", "general")
    if not nombre:
        if is_ajax:
            return jsonify({"ok": False, "error": "El nombre del grupo es requerido"}), 400
        flash("El nombre del grupo es requerido", "danger")
        return redirect(url_for("groups.listar_grupos"))
    try:
        nuevo = svc_crear_grupo(nombre=nombre, tipo_grupo=tipo_grupo)
        if is_ajax:
            return jsonify({"ok": True, "grupo": nuevo})
        flash("Grupo creado exitosamente", "success")
    except Exception as e:  # noqa: BLE001
        if is_ajax:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(f"Error: {e}", "danger")
    return redirect(url_for("groups.listar_grupos"))


@bp.post("/admin/grupos/<id>")
@require_role("admin", "superadmin")
def actualizar_grupo(id: str):
    datos: dict = {}
    if request.form.get("nombre"):
        datos["nombre"] = request.form["nombre"].strip()
    if request.form.get("tipo_grupo"):
        datos["tipo_grupo"] = request.form["tipo_grupo"]
    activo_val = request.form.get("activo")
    if activo_val is not None:
        datos["activo"] = activo_val == "1"
    try:
        svc_actualizar_grupo(id, datos)
        flash("Grupo actualizado", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("groups.listar_grupos"))


# ── Grupos Funcionales (rol laboral / horario por defecto) ────────────────────

@bp.get("/admin/grupos-funcionales")
@require_role("admin", "superadmin")
def listar_grupos_funcionales():
    tipo_persona_id = request.args.get("tipo_persona_id")
    grupos_funcionales = svc_listar_grupos_funcionales(tipo_persona_id=tipo_persona_id)
    return render_template(
        "admin/grupos_funcionales.html",
        active_page="admin_grupos_funcionales",
        grupos_funcionales=grupos_funcionales,
        tipo_persona_id=tipo_persona_id,
    )


@bp.post("/admin/grupos-funcionales")
@require_role("admin", "superadmin", "gestor")
def crear_grupo_funcional():
    is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json"
    if request.is_json:
        data = request.get_json() or {}
        nombre = str(data.get("nombre", "")).strip()
        tipo_persona_id = data.get("tipo_persona_id") or None
    else:
        nombre = request.form.get("nombre", "").strip()
        tipo_persona_id = request.form.get("tipo_persona_id") or None
    if not nombre:
        if is_ajax:
            return jsonify({"ok": False, "error": "El nombre del grupo funcional es requerido"}), 400
        flash("El nombre del grupo funcional es requerido", "danger")
        return redirect(url_for("groups.listar_grupos_funcionales"))
    try:
        nuevo = svc_crear_grupo_funcional(nombre=nombre, tipo_persona_id=tipo_persona_id)
        if is_ajax:
            return jsonify({"ok": True, "grupo_funcional": nuevo})
        flash("Grupo funcional creado exitosamente", "success")
    except Exception as e:  # noqa: BLE001
        if is_ajax:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(f"Error: {e}", "danger")
    return redirect(url_for("groups.listar_grupos_funcionales"))


@bp.post("/admin/grupos-funcionales/<id>")
@require_role("admin", "superadmin")
def actualizar_grupo_funcional(id: str):
    datos: dict = {}
    if request.form.get("nombre"):
        datos["nombre"] = request.form["nombre"].strip()
    activo_val = request.form.get("activo")
    if activo_val is not None:
        datos["activo"] = activo_val == "1"
    try:
        svc_actualizar_grupo_funcional(id, datos)
        flash("Grupo funcional actualizado", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("groups.listar_grupos_funcionales"))