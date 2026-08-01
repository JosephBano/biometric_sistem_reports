"""
Blueprint de autenticación (`app/web/auth_bp.py`).

Rutas:
  - GET, POST /login                  → formulario de login (rate-limit 5/15min)
  - POST /logout                       → cierra sesión + audit
  - POST /admin/switch-tenant          → superadmin impersona otro tenant

Endpoint name: `auth.login`, `auth.logout`, `auth.switch_tenant`.
"""
from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.domain import auth as auth_svc
from app.domain.auth import (
    actualizar_ultimo_acceso,
    contar_intentos_fallidos,
    get_tenant_by_slug,
    registrar_audit,
    registrar_login_intento,
)
from app.domain.rbac import require_role
from app.extensions import limiter

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(
    "5 per 15 minutes",
    methods=["POST"],
    error_message="Demasiados intentos de inicio de sesión. Espere 15 minutos.",
)
def login():
    """Formulario de login. POST verifica credenciales y abre sesión."""

    if "usuario_id" in session:
        return redirect(url_for("dashboard.index"))

    error = None
    email_previo = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ip = request.remote_addr or "desconocida"
        email_previo = email

        # Rate limit manual sobre BD (5 fallos / 15 min por IP)
        intentos = contar_intentos_fallidos(ip, ventana_minutos=15)
        if intentos >= 5:
            error = "Demasiados intentos fallidos. Espere 15 minutos e intente nuevamente."
        else:
            usuario = auth_svc.verificar_login(email, password)
            if usuario:
                registrar_login_intento(ip, email, exitoso=True)
                actualizar_ultimo_acceso(usuario["id"])

                session.permanent = True
                session["usuario_id"] = usuario["id"]
                session["tenant_schema"] = usuario["tenant_schema"]
                session["roles"] = usuario["roles"]
                session["nombre"] = usuario["nombre"]
                session["tenant_id"] = usuario["tenant_id"]

                try:
                    registrar_audit(
                        tenant_id=usuario["tenant_id"],
                        usuario_id=usuario["id"],
                        accion="login",
                        ip=ip,
                    )
                except Exception:  # noqa: BLE001
                    pass

                return redirect(url_for("dashboard.index"))
            else:
                registrar_login_intento(ip, email, exitoso=False)
                error = "Credenciales incorrectas. Verifique su email y contraseña."

    return render_template("login.html", error=error, email_previo=email_previo)


@bp.route("/logout", methods=["POST"])
def logout():
    """Cierra sesión y registra audit `logout`."""

    try:
        if "usuario_id" in session:
            registrar_audit(
                tenant_id=session.get("tenant_id"),
                usuario_id=session["usuario_id"],
                accion="logout",
                ip=request.remote_addr,
            )
    except Exception:  # noqa: BLE001
        pass
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/admin/switch-tenant", methods=["POST"])
@require_role("superadmin")
def switch_tenant():
    """Permite al superadmin impersonar otro tenant."""

    slug = request.form.get("tenant_slug")
    if not slug:
        return "Slug requerido", 400

    if slug == "public":
        # Volver al contexto administrativo global
        session["tenant_schema"] = "public"
        return redirect(url_for("dashboard.index"))

    tenant = get_tenant_by_slug(slug)
    if not tenant:
        return "Tenant no encontrado", 404

    session["tenant_schema"] = tenant["slug"]
    session["tenant_id"] = tenant["id"]
    return redirect(url_for("dashboard.index"))
