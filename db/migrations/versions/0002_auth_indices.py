"""Fase 2: Agregar configuracion a usuarios + índices de autenticación

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-17

Cambios:
- ADD COLUMN IF NOT EXISTS configuracion JSONB a public.usuarios
- CREATE INDEX en public.usuarios(email)
- CREATE INDEX en public.usuarios(tenant_id)
- CREATE INDEX en public.login_intentos(ip, creado_en)
"""

from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Columna configuracion en public.usuarios (scopes de supervisores)
    conn.execute(text("""
        ALTER TABLE public.usuarios
        ADD COLUMN IF NOT EXISTS configuracion JSONB NOT NULL DEFAULT '{}'
    """))

    # Índices de rendimiento para autenticación
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_usuarios_email
            ON public.usuarios(email)
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_usuarios_tenant
            ON public.usuarios(tenant_id)
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_login_intentos_ip_fecha
            ON public.login_intentos(ip, creado_en DESC)
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_fecha
            ON public.audit_log(tenant_id, creado_en DESC)
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS public.idx_audit_log_tenant_fecha"))
    conn.execute(text("DROP INDEX IF EXISTS public.idx_login_intentos_ip_fecha"))
    conn.execute(text("DROP INDEX IF EXISTS public.idx_usuarios_tenant"))
    conn.execute(text("DROP INDEX IF EXISTS public.idx_usuarios_email"))
    conn.execute(text(
        "ALTER TABLE public.usuarios DROP COLUMN IF EXISTS configuracion"
    ))
