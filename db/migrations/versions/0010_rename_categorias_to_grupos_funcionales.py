"""Renombrar `categorias` a `grupos_funcionales` (ADR-0003, Opción A).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-28

Cambios:
  - ALTER TABLE categorias RENAME TO grupos_funcionales (preserva datos)
  - ALTER TABLE personas RENAME COLUMN categoria_id TO grupo_funcional_id
  - FK constraint se renombra automáticamente
  - El índice UNIQUE(nombre) se renombra automáticamente

Backout (downgrade):
  - ALTER TABLE grupos_funcionales RENAME TO categorias
  - ALTER TABLE personas RENAME COLUMN grupo_funcional_id TO categoria_id

Por qué esta migración es backward-compatible:
  - No se elimina ninguna fila.
  - Las FK constraints se actualizan automáticamente.
  - El UNIQUE(nombre) se preserva.
  - Solo cambia el nombre del objeto en el catálogo de PostgreSQL.

Aplica a cada tenant (env.py itera por cada public.tenants.activo).
"""
import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Renombra la tabla `categorias` a `grupos_funcionales` y la columna FK.

    Idempotente: si la tabla/columna ya tienen el nombre nuevo (caso de
    tenants donde init_db() ya aplico el rename antes de correr alembic),
    la operacion se omite.
    """
    conn = op.get_bind()

    existe_tabla_vieja = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'categorias'
        )
    """)).scalar()
    existe_tabla_nueva = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'grupos_funcionales'
        )
    """)).scalar()

    # Solo renombrar si `categorias` existe y `grupos_funcionales` NO.
    if existe_tabla_vieja and not existe_tabla_nueva:
        conn.execute(text("ALTER TABLE categorias RENAME TO grupos_funcionales"))

    existe_columna_vieja = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'personas'
              AND column_name = 'categoria_id'
        )
    """)).scalar()
    existe_columna_nueva = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'personas'
              AND column_name = 'grupo_funcional_id'
        )
    """)).scalar()

    if existe_columna_vieja and not existe_columna_nueva:
        conn.execute(text("""
            ALTER TABLE personas
            RENAME COLUMN categoria_id TO grupo_funcional_id
        """))


def downgrade() -> None:
    """Revierte el renombrado: `grupos_funcionales` -> `categorias`."""
    conn = op.get_bind()

    existe_tabla = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'grupos_funcionales'
        )
    """)).scalar()

    if existe_tabla:
        conn.execute(text("ALTER TABLE grupos_funcionales RENAME TO categorias"))
        conn.execute(text("""
            ALTER TABLE personas
            RENAME COLUMN grupo_funcional_id TO categoria_id
        """))