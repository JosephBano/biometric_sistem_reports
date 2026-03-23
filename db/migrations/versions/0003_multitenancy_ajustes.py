"""Fase 3: Ajustes menores de Multitenancy
Revision ID: 0003
Revises: 0002
Create Date: 2026-03-17
"""

from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Esta migración puede quedar vacía si no hay cambios estructurales
    # Se crea para mantener la secuencialidad de las fases
    pass


def downgrade() -> None:
    pass
