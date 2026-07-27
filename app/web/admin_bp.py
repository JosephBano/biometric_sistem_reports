"""
Blueprint de administración (superadmin) (`app/web/admin_bp.py`).

Rutas (8):
  - GET    /admin/tenants                  → vista lista de tenants
  - POST   /admin/tenants                  → crear tenant + provisionar schema
  - POST   /admin/tenants/<tenant_id>      → actualizar tenant
  - GET    /admin/dispositivos             → vista admin de dispositivos
  - GET    /admin/usuarios                 → vista de usuarios del tenant
  - POST   /admin/usuarios                 → crear usuario
  - POST   /admin/usuarios/<usuario_id>    → editar usuario
  - GET    /admin/superadmin/usuarios      → vista global cross-tenant
  - DELETE /api/superadmin/usuarios/<id>   → soft-delete
  - POST   /api/superadmin/usuarios        → crear usuario cross-tenant
  - POST   /api/superadmin/usuarios/mover  → mover entre tenants
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import text

from app.domain import auth as auth_svc
from app.domain.admin import (
    actualizar_tenant as svc_actualizar_tenant,
    crear_tenant as svc_crear_tenant,
    get_connection,
    get_tenants_activos,
    get_usuario_por_id,
    get_usuarios_all_tenants,
    get_usuarios_tenant,
    listar_tenants as svc_listar_tenants,
    provisionar_schema,
    registrar_audit,
)
from app.domain.rbac import require_role

bp = Blueprint("admin", __name__)

_ROLES_DISPONIBLES = [
    "superadmin", "admin", "gestor",
    "supervisor_grupo", "supervisor_periodo", "readonly",
]


def _get_grupos_periodos():
    """Carga grupos y períodos activos para los selects de scope en admin UI."""
    grupos = []
    periodos = []
    try:
        with get_connection() as conn:
            rows = conn.execute(
                text("SELECT id::text, nombre FROM grupos WHERE activo = true ORDER BY nombre")
            ).fetchall()
            grupos = [dict(r._mapping) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    try:
        with get_connection() as conn:
            rows = conn.execute(
                text("""
                    SELECT pv.id::text, p.nombre || ' — ' || pv.nombre AS nombre
                    FROM periodos_vigencia pv
                    JOIN personas p ON p.id = pv.persona_id
                    WHERE pv.estado = 'activo'
                    ORDER BY p.nombre, pv.nombre
                """)
            ).fetchall()
            periodos = [dict(r._mapping) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return grupos, periodos


# ── Tenants ──────────────────────────────────────────────────────────────

@bp.get("/admin/tenants")
@require_role("superadmin")
def listar_tenants():
    tenants = svc_listar_tenants()
    return render_template(
        "admin/tenants.html", tenants=tenants, active_page="admin_tenants",
    )


@bp.post("/admin/tenants")
@require_role("superadmin")
def crear_tenant():
    nombre = request.form.get("nombre", "").strip()
    nombre_corto = request.form.get("nombre_corto", "").strip()
    slug = request.form.get("slug", "").strip().lower()
    zona_horaria = request.form.get("zona_horaria", "America/Guayaquil")

    if not nombre or not slug:
        return "Nombre y Slug son requeridos", 400
    if not all(c.isalnum() or c == "_" for c in slug):
        return "Slug debe contener solo letras, números y guiones bajos", 400

    try:
        svc_crear_tenant(nombre, nombre_corto, slug, zona_horaria)
        provisionar_schema(slug, tipos_persona=["Empleado", "Practicante"])
        return redirect(url_for("admin.listar_tenants") + "?msg=Tenant+creado+con+éxito")
    except Exception as e:  # noqa: BLE001
        return f"Error al crear tenant: {str(e)}", 500


@bp.post("/admin/tenants/<tenant_id>")
@require_role("superadmin")
def actualizar_tenant(tenant_id: str):
    activo = request.form.get("activo") == "1"
    try:
        svc_actualizar_tenant(tenant_id, {"activo": activo})
        return redirect(url_for("admin.listar_tenants") + "?msg=Tenant+actualizado")
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}", 500


# ── Vista admin de dispositivos (placeholder UI) ────────────────────────

@bp.get("/admin/dispositivos")
@require_role("superadmin", "admin")
def admin_dispositivos():
    return render_template("admin/dispositivos.html", active_page="admin_dispositivos")


# ── Usuarios del tenant ──────────────────────────────────────────────────

@bp.get("/admin/usuarios")
@require_role("superadmin", "admin")
def listar_usuarios():
    tenant_id = g.get("tenant_id")
    usuarios = []
    mensaje = request.args.get("msg")
    mensaje_tipo = request.args.get("tipo", "success")
    if tenant_id:
        try:
            usuarios = get_usuarios_tenant(tenant_id)
        except Exception as e:  # noqa: BLE001
            mensaje = f"Error cargando usuarios: {e}"
            mensaje_tipo = "danger"
    grupos, periodos = _get_grupos_periodos()
    return render_template(
        "admin/usuarios.html",
        active_page="admin_usuarios",
        usuarios=usuarios,
        roles_disponibles=_ROLES_DISPONIBLES,
        grupos=grupos,
        periodos=periodos,
        mensaje=mensaje,
        mensaje_tipo=mensaje_tipo,
    )


@bp.post("/admin/usuarios")
@require_role("superadmin", "admin")
def crear_usuario():
    nombre   = request.form.get("nombre", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    roles    = request.form.getlist("roles")

    if not nombre or not email or not password:
        return redirect(url_for("admin.listar_usuarios") + "?msg=Campos+requeridos+faltantes&tipo=danger")
    if len(password) < 8:
        return redirect(url_for("admin.listar_usuarios") + "?msg=La+contraseña+debe+tener+al+menos+8+caracteres&tipo=danger")

    configuracion: dict = {}
    if "supervisor_grupo" in roles and request.form.get("supervisor_grupo_id"):
        configuracion["supervisor_grupo_id"] = request.form.get("supervisor_grupo_id")
    if "supervisor_periodo" in roles and request.form.get("supervisor_periodo_id"):
        configuracion["supervisor_periodo_id"] = request.form.get("supervisor_periodo_id")

    if "superadmin" in roles and "superadmin" not in g.get("roles", []):
        return redirect(url_for("admin.listar_usuarios") + "?msg=No+tiene+permisos+para+crear+superadmin&tipo=danger")

    try:
        nuevo = auth_svc.crear_usuario(
            tenant_id=g.get("tenant_id"),
            email=email, password=password, nombre=nombre,
            roles=roles, configuracion=configuracion,
        )
        try:
            registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="crear_usuario",
                entidad="usuario",
                entidad_id=nuevo["id"],
                detalle={"email": email, "roles": roles},
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            pass
        return redirect(url_for("admin.listar_usuarios") + f"?msg=Usuario+'{nombre}'+creado+exitosamente")
    except ValueError as e:
        return redirect(url_for("admin.listar_usuarios") + f"?msg={str(e)}&tipo=danger")
    except Exception:  # noqa: BLE001
        return redirect(url_for("admin.listar_usuarios") + "?msg=Error+creando+usuario&tipo=danger")


@bp.post("/admin/usuarios/<usuario_id>")
@require_role("superadmin", "admin")
def editar_usuario(usuario_id: str):
    roles  = request.form.getlist("roles")
    activo = bool(request.form.get("activo"))

    if "superadmin" in roles and "superadmin" not in g.get("roles", []):
        return redirect(url_for("admin.listar_usuarios") + "?msg=No+tiene+permisos+para+asignar+superadmin&tipo=danger")

    configuracion: dict = {}
    if "supervisor_grupo" in roles and request.form.get("supervisor_grupo_id"):
        configuracion["supervisor_grupo_id"] = request.form.get("supervisor_grupo_id")
    if "supervisor_periodo" in roles and request.form.get("supervisor_periodo_id"):
        configuracion["supervisor_periodo_id"] = request.form.get("supervisor_periodo_id")

    try:
        auth_svc.actualizar_roles(usuario_id, roles, configuracion)
        if activo:
            auth_svc.activar_usuario(usuario_id)
        else:
            auth_svc.desactivar_usuario(usuario_id)
            try:
                registrar_audit(
                    tenant_id=g.get("tenant_id"),
                    usuario_id=g.get("usuario_id"),
                    accion="desactivar_usuario",
                    entidad="usuario",
                    entidad_id=usuario_id,
                    ip=request.remote_addr,
                )
            except Exception:  # noqa: BLE001
                pass

        try:
            registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="editar_usuario",
                entidad="usuario",
                entidad_id=usuario_id,
                detalle={"roles": roles, "activo": activo},
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            pass

        return redirect(url_for("admin.listar_usuarios") + "?msg=Usuario+actualizado+correctamente")
    except Exception:  # noqa: BLE001
        return redirect(url_for("admin.listar_usuarios") + "?msg=Error+actualizando+usuario&tipo=danger")


# ── Superadmin global ────────────────────────────────────────────────────

@bp.get("/admin/superadmin/usuarios")
@require_role("superadmin")
def superadmin_usuarios():
    tenants = get_tenants_activos()
    usuarios = get_usuarios_all_tenants()
    mensaje = request.args.get("msg")
    mensaje_tipo = request.args.get("tipo", "success")
    return render_template(
        "admin/superadmin_usuarios.html",
        active_page="superadmin_usuarios",
        usuarios=usuarios,
        tenants=tenants,
        roles_disponibles=_ROLES_DISPONIBLES,
        mensaje=mensaje,
        mensaje_tipo=mensaje_tipo,
    )


@bp.delete("/api/superadmin/usuarios/<usuario_id>")
@require_role("superadmin")
def api_superadmin_eliminar_usuario(usuario_id: str):
    try:
        auth_svc.desactivar_usuario(usuario_id)
        try:
            registrar_audit(
                tenant_id=None,
                usuario_id=g.get("usuario_id"),
                accion="superadmin_eliminar_usuario",
                entidad="usuario",
                entidad_id=usuario_id,
                detalle={"operacion": "soft-delete"},
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            pass
        return jsonify({"ok": True, "mensaje": "Usuario eliminado"}), 200
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/superadmin/usuarios")
@require_role("superadmin")
def api_superadmin_crear_usuario():
    """Crea un usuario en un tenant específico (para re-registro tras movimiento)."""
    data = request.get_json() or {}
    tenant_id   = data.get("tenant_id")
    email       = data.get("email", "").strip().lower()
    nombre      = data.get("nombre", "").strip()
    roles       = data.get("roles", [])
    generar_pass = data.get("generar_password", True)

    if not tenant_id or not email or not nombre:
        return jsonify({"ok": False, "error": "tenant_id, email y nombre son requeridos"}), 400

    if "superadmin" in roles and "superadmin" not in g.get("roles", []):
        return jsonify({"ok": False, "error": "No tienes permisos para crear superadmin"}), 403

    try:
        if generar_pass:
            temp_pass = auth_svc.generar_temporary_password()
            password = temp_pass
        else:
            password = data.get("password", "")
            if len(password) < 8:
                return jsonify({"ok": False, "error": "La contraseña debe tener al menos 8 caracteres"}), 400

        nuevo = auth_svc.crear_usuario(
            tenant_id=tenant_id, email=email, password=password,
            nombre=nombre, roles=roles,
        )
        try:
            registrar_audit(
                tenant_id=None,
                usuario_id=g.get("usuario_id"),
                accion="superadmin_crear_usuario",
                entidad="usuario",
                entidad_id=nuevo["id"],
                detalle={"email": email, "tenant_id": tenant_id, "roles": roles},
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            pass
        return jsonify({
            "ok": True,
            "usuario": {k: v for k, v in nuevo.items() if k != "password_hash"},
            "password_temporal": temp_pass if generar_pass else None,
        }), 201
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/superadmin/usuarios/mover")
@require_role("superadmin")
def api_superadmin_mover_usuario():
    """Mueve un usuario de un tenant a otro: soft-delete en origen + crea en destino."""
    data = request.get_json() or {}
    usuario_id    = data.get("usuario_id")
    tenant_id_destino = data.get("tenant_id_destino")
    generar_pass  = data.get("generar_password", True)

    if not usuario_id or not tenant_id_destino:
        return jsonify({"ok": False, "error": "usuario_id y tenant_id_destino son requeridos"}), 400

    try:
        usuario_origen = get_usuario_por_id(usuario_id)
        if not usuario_origen:
            return jsonify({"ok": False, "error": "Usuario no encontrado"}), 404

        email  = usuario_origen["email"]
        nombre = usuario_origen["nombre"]
        roles  = usuario_origen["roles"]

        auth_svc.desactivar_usuario(usuario_id)

        temp_pass = (
            auth_svc.generar_temporary_password() if generar_pass else data.get("password", "")
        )
        if generar_pass and not data.get("password"):
            pass_val = temp_pass
        else:
            pass_val = temp_pass if generar_pass else data.get("password", "")

        nuevo = auth_svc.crear_usuario(
            tenant_id=tenant_id_destino, email=email, password=pass_val,
            nombre=nombre, roles=roles,
        )
        try:
            registrar_audit(
                tenant_id=None,
                usuario_id=g.get("usuario_id"),
                accion="superadmin_mover_usuario",
                entidad="usuario",
                entidad_id=usuario_id,
                detalle={
                    "desde_tenant": usuario_origen.get("tenant_id"),
                    "hacia_tenant": tenant_id_destino,
                    "nuevo_usuario_id": nuevo["id"],
                },
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            pass
        return jsonify({
            "ok": True,
            "password_temporal": temp_pass if generar_pass else None,
        }), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500
