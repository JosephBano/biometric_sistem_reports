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
    listar_grupos_funcionales,
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
    grupos_funcionales = listar_grupos_funcionales(activo=True)
    return render_template(
        "personas/lista.html",
        active_page="personas",
        personas=personas,
        grupos=grupos,
        grupos_funcionales=grupos_funcionales,
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
            grupo_funcional_id=request.form.get("grupo_funcional_id") or None,
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
                  "tipo_persona_id", "grupo_id", "grupo_funcional_id"):
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
    from datetime import date as _date

    identificacion = request.args.get("identificacion", "").strip()
    historico_data = None
    if identificacion:
        historico_data = get_historico_persona(identificacion)

        # Tarea 6.5 (plan): enriquecer cada periodo con `horario_origen`
        # calculado por el resolver canónico del ADR-0003 (P11).
        # Solo se calcula si los registros tienen `fecha_inicio` (date o
        # string ISO); si no, no enriquecemos esa fila.
        if historico_data:
            try:
                from app.domain.horarios_resolucion import (
                    resolver_horario_vigente_para_persona,
                )
                persona_id = historico_data.get("id")
                if persona_id:
                    for periodo in (
                        historico_data.get("periodos") or []
                    ):
                        fecha_inicio = periodo.get("fecha_inicio")
                        if not fecha_inicio:
                            periodo["horario_origen"] = None
                            continue
                        if isinstance(fecha_inicio, str):
                            try:
                                fecha_dt = _date.fromisoformat(
                                    fecha_inicio
                                )
                            except ValueError:
                                periodo["horario_origen"] = None
                                continue
                        else:
                            fecha_dt = fecha_inicio
                        try:
                            resultado = resolver_horario_vigente_para_persona(
                                persona_id, fecha_dt,
                            )
                            periodo["horario_origen"] = resultado.get(
                                "origen"
                            )
                        except Exception:  # noqa: BLE001
                            periodo["horario_origen"] = None
            except Exception:  # noqa: BLE001
                # Enriquecimiento opcional; nunca debe romper la vista.
                pass

    return render_template(
        "personas/historico.html",
        active_page="personas",
        identificacion=identificacion,
        historico=historico_data,
    )
