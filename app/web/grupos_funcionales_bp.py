"""
Blueprint de gestión de grupos funcionales y horarios por grupo (ADR-0003).

13 endpoints JSON API + 3 vistas HTML. Las funciones son delgadas:
serializan request → llaman a `app.domain.*` → serializan response.

RBAC:
  - Lectura (GET):             gestor, admin, superadmin.
  - Escritura (POST/PUT/DELETE): admin, superadmin.

Los cambios se registran en `public.audit_log` vía `db.queries.audit_log`
con `accion` siguiendo el prefijo documentado en el ADR-0003 R9.
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, g, jsonify, render_template, request

from app.domain import (
    asignacion_masiva as masiva_svc,
    grupos_funcionales as grupos_svc,
    horario_por_grupo_flag as flag_svc,
    horarios_default_grupo as defaults_svc,
    horarios_override as overrides_svc,
    persona_grupo_funcional as memberships_svc,
)
from app.domain.admin import registrar_audit  # noqa: E402  (capa de dominio)
from app.domain.rbac import require_role
from app.domain.horarios_resolucion import resolver_horario_vigente_para_persona

bp = Blueprint("functional_groups", __name__)


READ_ROLES = ("gestor", "admin", "superadmin")
WRITE_ROLES = ("admin", "superadmin")


# ── Helpers ────────────────────────────────────────────────────────────


def _json() -> dict:
    """Lee el JSON body; tolerante a payloads vacíos."""
    return request.get_json(silent=True) or {}


def _audit(accion: str, entidad: str, entidad_id: str | None,
           antes: dict | None, despues: dict | None) -> None:
    """Persiste cambio en `public.audit_log`. Fallo silencioso."""
    try:
        registrar_audit(  # desde app.domain.admin
            tenant_id=g.get("tenant_id"),
            usuario_id=g.get("usuario_id"),
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id) if entidad_id else None,
            detalle={"antes": antes, "despues": despues},
            ip=request.remote_addr,
        )
    except Exception:  # noqa: BLE001
        # No fallar el request por error de auditoría.
        pass


def _parse_date_or_today(value, field_name):
    """Parsea un `YYYY-MM-DD` o retorna `date.today()`."""
    if not value:
        return date.today()
    return date.fromisoformat(value)


def _parse_date_or_none(value):
    if not value:
        return None
    return date.fromisoformat(value)


# ═════════════════════════════════════════════════════════════════════════
# API: catálogo de grupos funcionales
# ═════════════════════════════════════════════════════════════════════════


@bp.get("/api/grupos-funcionales")
@require_role(*READ_ROLES)
def listar_grupos():
    return jsonify({"grupos": grupos_svc.listar(solo_activos=False)})


@bp.post("/api/grupos-funcionales")
@require_role(*WRITE_ROLES)
def crear_grupo():
    data = _json()
    grupo = grupos_svc.crear(
        codigo=data["codigo"],
        nombre=data["nombre"],
        descripcion=data.get("descripcion"),
        color=data.get("color"),
        orden=data.get("orden", 0),
    )
    _audit("grupo_funcional_crear", "grupos_funcionales", grupo["id"],
           None, grupo)
    return jsonify({"grupo": grupo}), 201


@bp.put("/api/grupos-funcionales/<grupo_id>")
@require_role(*WRITE_ROLES)
def actualizar_grupo(grupo_id: str):
    antes = grupos_svc.get(grupo_id)
    actualizado = grupos_svc.actualizar(grupo_id, _json())
    if actualizado is None:
        return jsonify({"error": "grupo_funcional_no_encontrado"}), 404
    _audit("grupo_funcional_actualizar", "grupos_funcionales", grupo_id,
           antes, actualizado)
    return jsonify({"grupo": actualizado})


@bp.delete("/api/grupos-funcionales/<grupo_id>")
@require_role(*WRITE_ROLES)
def desactivar_grupo(grupo_id: str):
    """Soft-delete: marca activo=false (no DELETE por histórico)."""
    antes = grupos_svc.get(grupo_id)
    if antes is None:
        return jsonify({"error": "grupo_funcional_no_encontrado"}), 404
    ok = grupos_svc.desactivar(grupo_id)
    if not ok:
        return jsonify({"error": "grupo_funcional_no_encontrado"}), 404
    _audit("grupo_funcional_cerrar", "grupos_funcionales", grupo_id,
           antes, {"activo": False})
    return jsonify({"ok": True})


# ═════════════════════════════════════════════════════════════════════════
# API: defaults por grupo
# ═════════════════════════════════════════════════════════════════════════


@bp.get("/api/horarios-default-grupo")
@require_role(*READ_ROLES)
def listar_defaults():
    gf_id = request.args.get("grupo_funcional_id")
    return jsonify({"defaults": defaults_svc.listar(gf_id)})


@bp.post("/api/horarios-default-grupo")
@require_role(*WRITE_ROLES)
def crear_default():
    data = _json()
    hdg = defaults_svc.crear(
        grupo_funcional_id=data["grupo_funcional_id"],
        plantilla_id=data["plantilla_id"],
        fecha_inicio=_parse_date_or_today(
            data.get("fecha_inicio"), "fecha_inicio"
        ),
        fecha_fin=_parse_date_or_none(data.get("fecha_fin")),
        prioridad=int(data.get("prioridad", 0)),
        notas=data.get("notas"),
    )
    if hdg is None:
        return jsonify({"error": "horario_default_duplicado_o_invalido"}), 409
    _audit("horario_default_crear", "horarios_default_grupo", hdg["id"],
           None, hdg)
    return jsonify({"default": hdg}), 201


@bp.put("/api/horarios-default-grupo/<hdg_id>")
@require_role(*WRITE_ROLES)
def cerrar_default(hdg_id: str):
    fecha_fin = _parse_date_or_today(_json().get("fecha_fin"), "fecha_fin")
    if defaults_svc.cerrar(hdg_id, fecha_fin):
        _audit("horario_default_cerrar", "horarios_default_grupo", hdg_id,
               None, {"fecha_fin": fecha_fin.isoformat()})
        return jsonify({"ok": True})
    return jsonify({"error": "horario_default_no_encontrado"}), 404


# ═════════════════════════════════════════════════════════════════════════
# API: personalizado (override) por persona
# ═════════════════════════════════════════════════════════════════════════


@bp.get("/api/horarios-override")
@require_role(*READ_ROLES)
def listar_overrides():
    pid = request.args.get("persona_id", "")
    if not pid:
        return jsonify({"overrides": []})
    return jsonify({"overrides": overrides_svc.listar_de_persona(pid)})


@bp.post("/api/horarios-override")
@require_role(*WRITE_ROLES)
def crear_override():
    data = _json()
    ohp = overrides_svc.crear(
        persona_id=data["persona_id"],
        plantilla_id=data["plantilla_id"],
        fecha_inicio=_parse_date_or_today(
            data.get("fecha_inicio"), "fecha_inicio"
        ),
        fecha_fin=_parse_date_or_none(data.get("fecha_fin")),
        motivo=data.get("motivo"),
        creado_por=g.get("usuario_id"),
    )
    _audit("horario_override_crear", "overrides_horario_persona", ohp["id"],
           None, ohp)
    return jsonify({"override": ohp}), 201


@bp.put("/api/horarios-override/<ohp_id>")
@require_role(*WRITE_ROLES)
def cerrar_override(ohp_id: str):
    fecha_fin = _parse_date_or_today(_json().get("fecha_fin"), "fecha_fin")
    if overrides_svc.cerrar(ohp_id, fecha_fin):
        _audit("horario_override_cerrar", "overrides_horario_persona", ohp_id,
               None, {"fecha_fin": fecha_fin.isoformat()})
        return jsonify({"ok": True})
    return jsonify({"error": "horario_override_no_encontrado"}), 404


# ═════════════════════════════════════════════════════════════════════════
# API: Persona ↔ Grupo funcional (N:M con vigencia)
# ═════════════════════════════════════════════════════════════════════════


@bp.post("/api/personas/<persona_id>/grupos-funcionales")
@require_role(*WRITE_ROLES)
def asignar_grupo_a_persona(persona_id: str):
    data = _json()
    fila = memberships_svc.asignar(
        persona_id=persona_id,
        grupo_funcional_id=data["grupo_funcional_id"],
        fecha_inicio=_parse_date_or_today(
            data.get("fecha_inicio"), "fecha_inicio"
        ),
        fecha_fin=_parse_date_or_none(data.get("fecha_fin")),
        es_principal=bool(data.get("es_principal", False)),
        notas=data.get("notas"),
    )
    if fila is None:
        return jsonify({"error": "asignacion_duplicada"}), 409
    _audit("persona_grupo_funcional_asignar", "persona_grupos_funcionales",
           fila["id"], None, fila)
    return jsonify({"membership": fila}), 201


@bp.delete("/api/personas/<persona_id>/grupos-funcionales/<pgf_id>")
@require_role(*WRITE_ROLES)
def cerrar_grupo_de_persona(persona_id: str, pgf_id: str):
    fecha_fin = _parse_date_or_today(
        _json().get("fecha_fin"), "fecha_fin"
    )
    if memberships_svc.cerrar_por_id(pgf_id, fecha_fin):
        _audit("persona_grupo_funcional_cerrar", "persona_grupos_funcionales",
               pgf_id, None, {"fecha_fin": fecha_fin.isoformat()})
        return jsonify({"ok": True})
    return jsonify({"error": "persona_grupo_funcional_no_encontrado"}), 404


# ═════════════════════════════════════════════════════════════════════════
# API: Asignación masiva con filtros
# ═════════════════════════════════════════════════════════════════════════


@bp.post("/api/asignacion-masiva/grupo-funcional/preview")
@require_role(*WRITE_ROLES)
def preview_masiva():
    """Calcula cuántos y cuáles personas serán afectadas, SIN escribir."""
    data = _json()
    filtros = data.get("filtros", {})
    persona_ids = masiva_svc.listar_personas_para_filtros(
        grupo_id=filtros.get("grupo_id"),
        tipo_persona_id=filtros.get("tipo_persona_id"),
        categoria_id=filtros.get("categoria_id"),
        sede_id=filtros.get("sede_id"),
        grupo_funcional_id=filtros.get("grupo_funcional_id"),
    )
    return jsonify({
        "matched_count": len(persona_ids),
        "affected_persona_ids": persona_ids[:50],  # muestra 50
        "requires_confirm": True,
    })


@bp.post("/api/asignacion-masiva/grupo-funcional")
@require_role(*WRITE_ROLES)
def ejecutar_masiva():
    """Ejecuta la asignación masiva con `confirmar=True`."""
    data = _json()
    resultado = masiva_svc.aplicar_grupo_funcional_masivo(
        filtros=data.get("filtros", {}),
        grupo_funcional_id_destino=data["grupo_funcional_id_destino"],
        plantilla_id=data.get("plantilla_id"),
        fecha_inicio=_parse_date_or_today(
            data.get("fecha_inicio"), "fecha_inicio"
        ),
        fecha_fin=_parse_date_or_none(data.get("fecha_fin")),
        modo=data.get("modo", "asignar_grupo_funcional"),
        cerrar_legacy_en_fecha=bool(
            data.get("cerrar_legacy_en_fecha", False)
        ),
        confirmar=bool(data.get("confirmar", False)),
    )
    return jsonify(resultado)


# ═════════════════════════════════════════════════════════════════════════
# API: Resolver horario (consulta — precedencia del ADR-0003 r2)
# ═════════════════════════════════════════════════════════════════════════


@bp.get("/api/horarios/resolver")
@require_role(*READ_ROLES)
def resolver():
    pid = request.args.get("persona_id", "")
    fecha = request.args.get("fecha", "")
    if not pid:
        return jsonify({"error": "persona_id requerido"}), 400
    try:
        fecha_dt = date.fromisoformat(fecha) if fecha else date.today()
        resultado = resolver_horario_vigente_para_persona(pid, fecha_dt)
        return jsonify(resultado)
    except (ValueError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 400


# ═════════════════════════════════════════════════════════════════════════
# API: Feature flag del tenant
# ═════════════════════════════════════════════════════════════════════════


@bp.get("/api/configuracion/horario-por-grupo")
@require_role(*READ_ROLES)
def get_flag():
    from app.tenant import (
        get_horario_desempate,
        get_horario_por_grupo_enabled,
    )
    return jsonify({
        "horario_por_grupo": get_horario_por_grupo_enabled(),
        "horario_desempate": get_horario_desempate(),
    })


@bp.put("/api/configuracion/horario-por-grupo")
@require_role(*WRITE_ROLES)
def set_flag():
    data = _json()
    try:
        actualizado = flag_svc.set_horario_por_grupo_flag(
            tenant_id=g.get("tenant_id"),
            usuario_id=g.get("usuario_id"),
            ip=request.remote_addr,
            enabled=bool(data.get("horario_por_grupo")),
            horario_desempate=data.get("horario_desempate", "prioridad"),
            tenant_schema=g.get("tenant_schema"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(actualizado)


@bp.get("/api/configuracion/horario-por-grupo/preflight")
@require_role(*READ_ROLES)
def get_preflight():
    resultado = flag_svc.preflight(
        tenant_id=g.get("tenant_id"),
        fecha=date.today(),
    )
    return jsonify(resultado)


# ═════════════════════════════════════════════════════════════════════════
# Vistas HTML (admin)
# ═════════════════════════════════════════════════════════════════════════


@bp.get("/admin/grupos-funcionales")
@require_role(*READ_ROLES)
def vista_grupos():
    return render_template(
        "admin/grupos_funcionales.html",
        active_page="functional_groups",
    )


@bp.get("/admin/horarios-default-grupo")
@require_role(*READ_ROLES)
def vista_defaults():
    return render_template(
        "admin/horarios_default_grupo.html",
        active_page="functional_groups",
    )


@bp.get("/admin/asignacion-masiva-grupo-funcional")
@require_role(*WRITE_ROLES)
def vista_asignacion_masiva():
    return render_template(
        "admin/asignacion_masiva.html",
        active_page="functional_groups",
    )
