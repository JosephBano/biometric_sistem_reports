"""Initial schema: public + tenant schemas (Fase 1 PostgreSQL)

Revision ID: 0001
Revises:
Create Date: 2026-03-17

Aplica el schema completo de la Fase 1.
Es idempotente: usa CREATE TABLE IF NOT EXISTS.
"""

import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from db.schema import PUBLIC_DDL, get_tenant_ddl

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Schema público
    conn.execute(text(PUBLIC_DDL))

    # Obtener tenants activos (o usar TENANT_DEFAULT si la tabla aún no existe)
    try:
        rows = conn.execute(
            text("SELECT slug FROM public.tenants WHERE activo = true ORDER BY slug")
        ).fetchall()
        slugs = [r[0] for r in rows] if rows else [os.environ.get("TENANT_DEFAULT", "istpet")]
    except Exception:
        slugs = [os.environ.get("TENANT_DEFAULT", "istpet")]

    for slug in slugs:
        if not all(c.isalnum() or c == "_" for c in slug):
            continue
        conn.execute(text(get_tenant_ddl(slug)))


def downgrade() -> None:
    """
    PELIGROSO: elimina todos los datos del tenant y el schema público.
    Solo para entornos de desarrollo.
    """
    conn = op.get_bind()
    tenant = os.environ.get("TENANT_DEFAULT", "istpet")

    confirm = os.environ.get("ALEMBIC_ALLOW_DOWNGRADE_0001", "false")
    if confirm.lower() != "true":
        raise RuntimeError(
            "Downgrade de 0001 deshabilitado por seguridad. "
            "Setea ALEMBIC_ALLOW_DOWNGRADE_0001=true para confirmar."
        )

    conn.execute(text(f"DROP SCHEMA IF EXISTS {tenant} CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS public.login_intentos CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS public.audit_log CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS public.usuarios CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS public.tenants CASCADE"))
