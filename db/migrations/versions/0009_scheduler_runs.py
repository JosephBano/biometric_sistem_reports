"""Scheduler runs observability (Fase 1 — Sync automática confiable).

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-02

Crea la tabla `public.scheduler_runs` para persistir el resultado de cada
corrida del scheduler (sync nocturna, sync incremental, backup diario).
Aditiva, idempotente, sin impacto en datos existentes.

Nota: `env.py` aplica esta migración primero en `public` y luego en cada
tenant (con search_path ajustado). El prefijo `public.` y la guarda sobre
`current_schema()` la hacen portable y evitan duplicación por tenant.
"""
import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DO $$
        BEGIN
            -- Solo crear la tabla cuando se ejecuta en el schema public.
            -- (env.py aplica esta migración una vez en public y otra por cada tenant;
            --  en los tenants no debe existir esta tabla.)
            IF current_schema() = 'public' THEN
                CREATE TABLE IF NOT EXISTS public.scheduler_runs (
                    id              BIGSERIAL   PRIMARY KEY,
                    job             TEXT        NOT NULL,
                    tenant_slug     TEXT,
                    inicio          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    fin             TIMESTAMPTZ,
                    ok              BOOLEAN     NOT NULL,
                    descargados     INTEGER,
                    insertados      INTEGER,
                    detalle         TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job_inicio
                    ON public.scheduler_runs (job, inicio DESC);

                CREATE INDEX IF NOT EXISTS idx_scheduler_runs_tenant_inicio
                    ON public.scheduler_runs (tenant_slug, inicio DESC)
                    WHERE tenant_slug IS NOT NULL;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    """
    PELIGROSO: elimina historial de corridas del scheduler.
    Solo para entornos de desarrollo.
    """
    confirm = os.environ.get("ALEMBIC_ALLOW_DOWNGRADE_0009", "false")
    if confirm.lower() != "true":
        raise RuntimeError(
            "Downgrade de 0009 deshabilitado por seguridad. "
            "Setea ALEMBIC_ALLOW_DOWNGRADE_0009=true para confirmar."
        )
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS public.scheduler_runs CASCADE"))