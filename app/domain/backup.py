"""
Wrapper para `backup` (`app.domain.backup`).

Re-exporta la API de backups portables desde el módulo top-level `backup.py`
(pendiente de migración física — ver ADR-0001 Fase 4e).

API pública:
  - `generar_dump(destino: str) -> None`
"""
from __future__ import annotations

from backup import generar_dump  # noqa: F401  (re-export)

__all__ = ["generar_dump"]
