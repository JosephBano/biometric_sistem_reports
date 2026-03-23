"""
Consultas SQL para la gestión de Tenants (Fase 3: Multitenancy).

Operan sobre:
  - public.tenants
  - <tenant_schema>.tipos_persona
  - <tenant_schema>.feriados
"""

import json
from sqlalchemy import text

from db.connection import get_engine, get_connection


def get_tenant_by_slug(slug: str) -> dict | None:
    """Busca un tenant por su slug en la tabla global public.tenants."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT id::text, nombre, nombre_corto, slug, zona_horaria, activo, creado_en
                FROM public.tenants
                WHERE slug = :slug
            """),
            {"slug": slug},
        ).fetchone()
    return dict(row._mapping) if row else None


def listar_tenants() -> list[dict]:
    """Retorna todos los tenants registrados en el sistema."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id::text, nombre, nombre_corto, slug, zona_horaria, activo, creado_en
                FROM public.tenants
                ORDER BY nombre
            """)
        ).fetchall()
    return [dict(row._mapping) for row in rows]


def crear_tenant(nombre: str, nombre_corto: str, slug: str, zona_horaria: str = "America/Guayaquil") -> dict:
    """Crea un registro de tenant en public.tenants."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("""
                INSERT INTO public.tenants (nombre, nombre_corto, slug, zona_horaria)
                VALUES (:nombre, :nombre_corto, :slug, :zona_horaria)
                RETURNING id::text, nombre, nombre_corto, slug, zona_horaria, activo, creado_en
            """),
            {
                "nombre": nombre,
                "nombre_corto": nombre_corto,
                "slug": slug,
                "zona_horaria": zona_horaria,
            },
        ).fetchone()
        conn.commit()
    return dict(row._mapping)


def actualizar_tenant(tenant_id: str, datos: dict) -> dict | None:
    """Actualiza campos de un tenant (ej: activo, nombre, etc.)."""
    allowed_fields = ["nombre", "nombre_corto", "zona_horaria", "activo"]
    updates = []
    params = {"id": tenant_id}

    for k in allowed_fields:
        if k in datos:
            updates.append(f"{k} = :{k}")
            params[k] = datos[k]

    if not updates:
        return None

    sql = f"UPDATE public.tenants SET {', '.join(updates)} WHERE id = :id RETURNING id::text, nombre, nombre_corto, slug, zona_horaria, activo"

    with get_engine().connect() as conn:
        row = conn.execute(text(sql), params).fetchone()
        conn.commit()
    return dict(row._mapping) if row else None


def get_tipos_persona(schema: str) -> list[dict]:
    """Retorna los tipos de persona activos del tenant usando su schema."""
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("SELECT id::text, nombre, descripcion, activo FROM tipos_persona WHERE activo = True ORDER BY nombre")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def insertar_tipo_persona(schema: str, nombre: str, descripcion: str = "") -> dict:
    """Inserta un tipo de persona en el schema del tenant."""
    with get_connection(schema) as conn:
        row = conn.execute(
            text("""
                INSERT INTO tipos_persona (nombre, descripcion)
                VALUES (:nombre, :descripcion)
                RETURNING id::text, nombre, descripcion, activo
            """),
            {"nombre": nombre, "descripcion": descripcion},
        ).fetchone()
    return dict(row._mapping)


def eliminar_tenant_de_public(tenant_slug: str) -> bool:
    """Remueve de public.tenants (usado para rollback de provisioning)."""
    with get_engine().connect() as conn:
        res = conn.execute(
            text("DELETE FROM public.tenants WHERE slug = :slug"),
            {"slug": tenant_slug}
        )
        conn.commit()
    return res.rowcount > 0
