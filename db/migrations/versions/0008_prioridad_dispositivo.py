from alembic import op
from sqlalchemy.sql import text

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'dispositivos' AND table_schema = current_schema()
            ) THEN
                ALTER TABLE dispositivos
                    ADD COLUMN IF NOT EXISTS prioridad INTEGER NOT NULL DEFAULT 5;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'dispositivos' AND table_schema = current_schema()
            ) THEN
                ALTER TABLE dispositivos DROP COLUMN IF EXISTS prioridad;
            END IF;
        END $$;
    """))
