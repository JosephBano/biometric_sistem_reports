"""Fase 1 — Horarios por grupo funcional (ADR-0003, Opción A).

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-28

Crea las 3 tablas que faltan para el modelo de horarios por grupo funcional:

  - grupos_funcionales_personas (N:M persona ↔ grupo funcional con vigencia)
    Antes del rename la tabla era 'categorias' (ahora 'grupos_funcionales');
    esta es la relacion N:M persona↔grupo_funcional. No confundir con la
    FK personas.grupo_funcional_id (que es solo el grupo principal).

  - horarios_default_grupo (plantilla_id + grupo_funcional_id con vigencia)
    Define el horario predeterminado para un grupo funcional.

  - overrides_horario_persona (persona_id + plantilla_id + fecha_inicio/fin)
    Override individual por encima del default del grupo funcional.

Precedencia (resolutor):
  1. override_horario_persona vigente en la fecha
  2. asignaciones_horario legacy (1:1 persona-plantilla) vigente
  3. horarios_default_grupo del grupo funcional principal de la persona
  4. sin_horario

Backout (downgrade):
  - DROP de las 3 tablas (rollback completo; no hay datos de producción
    todavía porque el feature flag `horario_por_grupo` esta en False).
"""
import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea las 3 tablas de Fase 1 del ADR-0003 (solo en schema del tenant)."""
    conn = op.get_bind()

    # Solo crear en el schema del tenant. env.py aplica esta migracion
    # primero en public (donde no existen las tablas referenciadas) y luego
    # en cada tenant (donde si existen). El bloque DO bloquea la ejecucion
    # en public.
    conn.execute(text("""
        DO $$
        BEGIN
            IF current_schema() != 'public' THEN
                CREATE TABLE IF NOT EXISTS grupos_funcionales_personas (
                    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    persona_id        UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                    grupo_funcional_id UUID       NOT NULL REFERENCES grupos_funcionales(id) ON DELETE CASCADE,
                    fecha_inicio      DATE        NOT NULL,
                    fecha_fin         DATE,
                    es_principal      BOOLEAN     NOT NULL DEFAULT false,
                    creado_en         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (persona_id, grupo_funcional_id, fecha_inicio)
                );

                CREATE INDEX IF NOT EXISTS idx_gfp_persona_activo
                    ON grupos_funcionales_personas (persona_id, fecha_inicio DESC)
                    WHERE fecha_fin IS NULL;

                CREATE INDEX IF NOT EXISTS idx_gfp_grupo_fecha
                    ON grupos_funcionales_personas (grupo_funcional_id, fecha_inicio DESC);

                CREATE TABLE IF NOT EXISTS horarios_default_grupo (
                    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    grupo_funcional_id UUID        NOT NULL REFERENCES grupos_funcionales(id) ON DELETE CASCADE,
                    plantilla_id       UUID        NOT NULL REFERENCES plantillas_horario(id) ON DELETE RESTRICT,
                    fecha_inicio       DATE        NOT NULL,
                    fecha_fin          DATE,
                    prioridad          INTEGER     NOT NULL DEFAULT 0,
                    notas              TEXT,
                    creado_en          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (grupo_funcional_id, plantilla_id, fecha_inicio)
                );

                CREATE INDEX IF NOT EXISTS idx_hdg_grupo_fecha
                    ON horarios_default_grupo (grupo_funcional_id, fecha_inicio DESC, prioridad DESC);

                CREATE TABLE IF NOT EXISTS overrides_horario_persona (
                    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    persona_id   UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                    plantilla_id UUID        NOT NULL REFERENCES plantillas_horario(id) ON DELETE RESTRICT,
                    fecha_inicio DATE        NOT NULL,
                    fecha_fin    DATE,
                    notas        TEXT,
                    creado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (persona_id, plantilla_id, fecha_inicio)
                );
            END IF;
        END $$;
    """))


def downgrade() -> None:
    """Borra las 3 tablas (rollback completo, no hay datos en prod)."""
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS overrides_horario_persona"))
    conn.execute(text("DROP TABLE IF EXISTS horarios_default_grupo"))
    conn.execute(text("DROP TABLE IF EXISTS grupos_funcionales_personas"))