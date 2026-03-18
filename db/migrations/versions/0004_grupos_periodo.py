"""Fase 4: grupos_periodo table
Revision ID: 0004
Revises: 0003
Create Date: 2026-03-17
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS grupos_periodo (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            nombre       TEXT        NOT NULL,
            fecha_inicio DATE        NOT NULL,
            fecha_fin    DATE,
            descripcion  TEXT,
            estado       TEXT        NOT NULL DEFAULT 'activo',
            creado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS grupos_periodo"))
