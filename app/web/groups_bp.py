"""
Blueprint de grupos y categorías (`app/web/groups_bp.py`).

Rutas (6):
  - GET   /admin/grupos
  - POST  /admin/grupos
  - POST  /admin/grupos/<id>
  - GET   /admin/categorias
  - POST  /admin/categorias
  - POST  /admin/categorias/<id>
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.domain.groups import (
    actualizar_categoria,
    actualizar_grupo,
    crear_categoria,
    crear_grupo,
)
from app.domain.groups import listar_categorias as svc_listar_categorias
from app.domain.groups import listar_grupos as svc_listar_grupos
from app.domain.rbac import require_role

bp = Blueprint("groups", __name__)


# ── Grupos ───────────────────────────────────────────────────────────────

@bp.get("/admin/grupos")
@require_role("admin", "superadmin")
def listar_grupos():
    grupos = svc_listar_grupos()
    return render_template(
        "admin/grupos.html", active_page="admin_grupos", grupos=grupos,
    )


@bp.post("/admin/grupos")
@require_role("admin", "superadmin")
def crear_grupo():
    nombre = request.form.get("nombre", "").strip()
    tipo_grupo = request.form.get("tipo_grupo", "general")
    if not nombre:
        flash("El nombre del grupo es requerido", "danger")
        return redirect(url_for("groups.listar_grupos"))
    try:
        crear_grupo(nombre=nombre, tipo_grupo=tipo_grupo)
        flash("Grupo creado exitosamente", "success")
    except Exception as e:  # noqa: BLE001
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
        actualizar_grupo(id, datos)
        flash("Grupo actualizado", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("groups.listar_grupos"))


# ── Categorías ───────────────────────────────────────────────────────────

@bp.get("/admin/categorias")
@require_role("admin", "superadmin")
def listar_categorias():
    tipo_persona_id = request.args.get("tipo_persona_id")
    categorias = svc_listar_categorias(tipo_persona_id=tipo_persona_id)
    return render_template(
        "admin/categorias.html",
        active_page="admin_categorias",
        categorias=categorias,
        tipo_persona_id=tipo_persona_id,
    )


@bp.post("/admin/categorias")
@require_role("admin", "superadmin")
def crear_categoria():
    nombre = request.form.get("nombre", "").strip()
    tipo_persona_id = request.form.get("tipo_persona_id") or None
    if not nombre:
        flash("El nombre de la categoría es requerido", "danger")
        return redirect(url_for("groups.listar_categorias"))
    try:
        crear_categoria(nombre=nombre, tipo_persona_id=tipo_persona_id)
        flash("Categoría creada exitosamente", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("groups.listar_categorias"))


@bp.post("/admin/categorias/<id>")
@require_role("admin", "superadmin")
def actualizar_categoria(id: str):
    datos: dict = {}
    if request.form.get("nombre"):
        datos["nombre"] = request.form["nombre"].strip()
    activo_val = request.form.get("activo")
    if activo_val is not None:
        datos["activo"] = activo_val == "1"
    try:
        actualizar_categoria(id, datos)
        flash("Categoría actualizada", "success")
    except Exception as e:  # noqa: BLE001
        flash(f"Error: {e}", "danger")
    return redirect(url_for("groups.listar_categorias"))
