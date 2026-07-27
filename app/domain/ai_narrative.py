"""
Wrapper para `ia_report` (`app.domain.ai_narrative`).

Re-exporta la función generadora de narrativos IA desde el módulo top-level
`ia_report.py`.

API pública:
  - `generar_narrativo(hallazgos: dict) -> str`  — usa DeepSeek si hay API key,
    si no, fallback basado en reglas.
"""
from __future__ import annotations

from ia_report import generar_narrativo  # noqa: F401  (re-export)

__all__ = ["generar_narrativo"]
