"""
Wrapper para `script_docx` (`app.domain.report_docx`).

Re-exporta la API de DOCX desde el módulo top-level `script_docx.py`.
"""
from __future__ import annotations

from script_docx import generar_docx, generar_docx_persona  # noqa: F401  (re-export)

__all__ = ["generar_docx", "generar_docx_persona"]
