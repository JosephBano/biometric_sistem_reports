from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dispositivos' AND table_schema = current_schema()) THEN
                ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS capacidad_max INTEGER NOT NULL DEFAULT 100000;
            END IF;
        END $$;
    """))

def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dispositivos' AND table_schema = current_schema()) THEN
                ALTER TABLE dispositivos DROP COLUMN IF EXISTS capacidad_max;
            END IF;
        END $$;
    """))
