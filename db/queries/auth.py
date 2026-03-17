"""
Consultas SQL para el subsistema de autenticación (Fase 2).

Operan sobre:
  - public.usuarios
  - public.audit_log
  - public.login_intentos
  - <tenant>.tipos_persona  (para @require_tipo_persona)
"""

import json
from sqlalchemy import text

from db.connection import get_engine, get_tenant_schema, get_connection


# ── Usuarios ──────────────────────────────────────────────────────────────

def get_usuario_por_email(email: str) -> dict | None:
    """Busca usuario activo por email. Incluye password_hash para verificación."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT u.id::text, u.tenant_id::text, u.email, u.password_hash,
                       u.nombre, u.roles, u.activo,
                       u.ultimo_acceso, u.configuracion,
                       t.slug AS tenant_schema
                FROM public.usuarios u
                LEFT JOIN public.tenants t ON t.id = u.tenant_id
                WHERE u.email = :email AND u.activo = true
            """),
            {"email": email},
        ).fetchone()
    if not row:
        return None
    d = dict(row._mapping)
    d["roles"] = list(d.get("roles") or [])
    d["configuracion"] = d.get("configuracion") or {}
    return d


def get_usuario_por_id(usuario_id: str) -> dict | None:
    """Retorna usuario por ID sin exponer password_hash."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT u.id::text, u.tenant_id::text, u.email, u.nombre,
                       u.roles, u.activo, u.ultimo_acceso, u.configuracion,
                       t.slug AS tenant_schema
                FROM public.usuarios u
                LEFT JOIN public.tenants t ON t.id = u.tenant_id
                WHERE u.id = :id
            """),
            {"id": usuario_id},
        ).fetchone()
    if not row:
        return None
    d = dict(row._mapping)
    d["roles"] = list(d.get("roles") or [])
    d["configuracion"] = d.get("configuracion") or {}
    return d


def get_usuarios_tenant(tenant_id: str) -> list:
    """Retorna todos los usuarios del tenant, sin password_hash."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id::text, tenant_id::text, email, nombre,
                       roles, activo, ultimo_acceso, configuracion, creado_en
                FROM public.usuarios
                WHERE tenant_id = :tenant_id
                ORDER BY nombre
            """),
            {"tenant_id": tenant_id},
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row._mapping)
        d["roles"] = list(d.get("roles") or [])
        d["configuracion"] = d.get("configuracion") or {}
        result.append(d)
    return result


def crear_usuario_db(tenant_id: str, email: str, password_hash: str, nombre: str,
                     roles: list, configuracion: dict) -> dict:
    """Inserta un nuevo usuario. Retorna el usuario creado (sin password_hash)."""
    roles_pg = "{" + ",".join(roles) + "}"
    with get_engine().connect() as conn:
        row = conn.execute(
            text("""
                INSERT INTO public.usuarios
                    (tenant_id, email, password_hash, nombre, roles, configuracion)
                VALUES
                    (:tenant_id, :email, :password_hash, :nombre,
                     :roles::text[], :configuracion::jsonb)
                RETURNING id::text, tenant_id::text, email, nombre,
                          roles, activo, configuracion, creado_en
            """),
            {
                "tenant_id": tenant_id,
                "email": email,
                "password_hash": password_hash,
                "nombre": nombre,
                "roles": roles_pg,
                "configuracion": json.dumps(configuracion),
            },
        ).fetchone()
        conn.commit()
    d = dict(row._mapping)
    d["roles"] = list(d.get("roles") or [])
    d["configuracion"] = d.get("configuracion") or {}
    return d


def actualizar_roles_db(usuario_id: str, roles: list,
                        configuracion: dict | None) -> bool:
    """Actualiza roles y opcionalmente configuración de scopes."""
    roles_pg = "{" + ",".join(roles) + "}"
    if configuracion is not None:
        sql = """
            UPDATE public.usuarios
               SET roles = :roles::text[],
                   configuracion = :configuracion::jsonb
             WHERE id = :id
        """
        params = {"id": usuario_id, "roles": roles_pg,
                  "configuracion": json.dumps(configuracion)}
    else:
        sql = "UPDATE public.usuarios SET roles = :roles::text[] WHERE id = :id"
        params = {"id": usuario_id, "roles": roles_pg}

    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params)
        conn.commit()
    return result.rowcount > 0


def desactivar_usuario_db(usuario_id: str) -> bool:
    """Establece activo=false para el usuario."""
    with get_engine().connect() as conn:
        result = conn.execute(
            text("UPDATE public.usuarios SET activo = false WHERE id = :id"),
            {"id": usuario_id},
        )
        conn.commit()
    return result.rowcount > 0


def activar_usuario_db(usuario_id: str) -> bool:
    """Establece activo=true para el usuario."""
    with get_engine().connect() as conn:
        result = conn.execute(
            text("UPDATE public.usuarios SET activo = true WHERE id = :id"),
            {"id": usuario_id},
        )
        conn.commit()
    return result.rowcount > 0


def actualizar_ultimo_acceso(usuario_id: str) -> None:
    """Registra la fecha/hora del último acceso exitoso."""
    with get_engine().connect() as conn:
        conn.execute(
            text("UPDATE public.usuarios SET ultimo_acceso = NOW() WHERE id = :id"),
            {"id": usuario_id},
        )
        conn.commit()


# ── Audit log ──────────────────────────────────────────────────────────────

def registrar_audit(tenant_id, usuario_id, accion: str,
                    entidad=None, entidad_id=None,
                    detalle=None, ip=None) -> None:
    """Inserta una entrada en public.audit_log."""
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO public.audit_log
                    (tenant_id, usuario_id, accion, entidad, entidad_id, detalle, ip)
                VALUES
                    (:tenant_id, :usuario_id, :accion,
                     :entidad, :entidad_id, :detalle::jsonb, :ip)
            """),
            {
                "tenant_id": tenant_id,
                "usuario_id": usuario_id,
                "accion": accion,
                "entidad": entidad,
                "entidad_id": str(entidad_id) if entidad_id else None,
                "detalle": json.dumps(detalle) if detalle else None,
                "ip": ip,
            },
        )
        conn.commit()


# ── Rate limiting ──────────────────────────────────────────────────────────

def registrar_login_intento(ip: str, email: str, exitoso: bool) -> None:
    """Registra un intento de login (exitoso o fallido)."""
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO public.login_intentos (ip, email, exitoso)
                VALUES (:ip, :email, :exitoso)
            """),
            {"ip": ip, "email": email, "exitoso": exitoso},
        )
        conn.commit()


def contar_intentos_fallidos(ip: str, ventana_minutos: int = 15) -> int:
    """Cuenta intentos fallidos desde una IP en la ventana de tiempo."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*) FROM public.login_intentos
                WHERE ip = :ip
                  AND exitoso = false
                  AND creado_en > NOW() - (:mins || ' minutes')::interval
            """),
            {"ip": ip, "mins": str(ventana_minutos)},
        ).fetchone()
    return int(row[0]) if row else 0


# ── Tipos de persona (para @require_tipo_persona) ─────────────────────────

def get_tipos_persona(schema: str = None) -> list:
    """Retorna los tipos de persona activos del tenant."""
    schema = schema or get_tenant_schema()
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("SELECT id::text, nombre FROM tipos_persona WHERE activo = true ORDER BY nombre")
        ).fetchall()
    return [dict(row._mapping) for row in rows]


# ── Dispositivos (contraseña cifrada) ─────────────────────────────────────

def get_device_password_enc(schema: str = None) -> str | None:
    """Retorna password_enc del primer dispositivo activo, o None."""
    schema = schema or get_tenant_schema()
    try:
        with get_connection(schema) as conn:
            row = conn.execute(
                text("""
                    SELECT password_enc FROM dispositivos
                    WHERE activo = true
                    ORDER BY creado_en
                    LIMIT 1
                """)
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def set_device_password_enc(password_enc: str, schema: str = None) -> bool:
    """Actualiza password_enc del primer dispositivo activo."""
    schema = schema or get_tenant_schema()
    with get_connection(schema) as conn:
        result = conn.execute(
            text("""
                UPDATE dispositivos SET password_enc = :enc
                WHERE id = (
                    SELECT id FROM dispositivos WHERE activo = true
                    ORDER BY creado_en LIMIT 1
                )
            """),
            {"enc": password_enc},
        )
    return result.rowcount > 0
