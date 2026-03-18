"""Fase 6 y 7: Sync mejoras y estado
Revision ID: 0005
Revises: 0004
Create Date: 2026-03-17
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adding prioridad to dispositivos
    # Note: Alembic doesn't natively support "ADD COLUMN IF NOT EXISTS" everywhere, 
    # but we will use raw SQL to handle potential re-runs.
    op.execute(text("""
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dispositivos' AND table_schema = current_schema()) THEN
                BEGIN
                    EXECUTE 'ALTER TABLE dispositivos ADD COLUMN prioridad INTEGER NOT NULL DEFAULT 5;';
                EXCEPTION
                    WHEN duplicate_column THEN RAISE NOTICE 'column prioriy already exists.';
                END;
            END IF;
        END $$;
    """))

    # Creating sync_estado table
    op.execute(text("""
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dispositivos' AND table_schema = current_schema()) THEN
                EXECUTE 'CREATE TABLE IF NOT EXISTS sync_estado (
                    dispositivo_id UUID        PRIMARY KEY REFERENCES dispositivos(id) ON DELETE CASCADE,
                    estado         TEXT        NOT NULL DEFAULT ''idle'',
                    progreso_pct   INTEGER     NOT NULL DEFAULT 0,
                    registros_proc INTEGER     NOT NULL DEFAULT 0,
                    mensaje        TEXT,
                    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )';
            END IF;
        END $$;
    """))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS sync_estado"))
    op.execute(text("ALTER TABLE dispositivos DROP COLUMN IF EXISTS prioridad"))
