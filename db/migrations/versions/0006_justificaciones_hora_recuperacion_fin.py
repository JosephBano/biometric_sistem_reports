"""Agrega columna hora_recuperacion_fin a la tabla justificaciones
Revision ID: 0006
Revises: 0005
Create Date: 2026-03-23
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'justificaciones' AND table_schema = current_schema()) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'justificaciones'
                      AND column_name = 'hora_recuperacion_fin'
                      AND table_schema = current_schema()
                ) THEN
                    ALTER TABLE justificaciones ADD COLUMN hora_recuperacion_fin TIME;
                END IF;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    op.execute(text(
        "ALTER TABLE justificaciones DROP COLUMN IF EXISTS hora_recuperacion_fin"
    ))
