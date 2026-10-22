"""
Fachada de renderizado PDF ReportLab (`app.domain.reports.pdf_render`).
"""
from __future__ import annotations

from app.domain.reports.pdf_general import generar_pdf
from app.domain.reports.pdf_persona import generar_pdf_persona
from app.domain.reports.pdf_styles import (
    COLOR_ERROR,
    COLOR_HEADER,
    COLOR_MUTED,
    COLOR_OK,
    COLOR_SUBHEADER,
    COLOR_TABLA_ALT,
    COLOR_TEXTO,
    COLOR_WARN,
    _crear_estilos,
    _dia_nombre_corto,
    _estilo_tabla_datos,
    _pie_pagina,
    _retraso_de_obs,
)

__all__ = [
    "generar_pdf",
    "generar_pdf_persona",
    "COLOR_HEADER",
    "COLOR_SUBHEADER",
    "COLOR_OK",
    "COLOR_WARN",
    "COLOR_ERROR",
    "COLOR_TABLA_ALT",
    "COLOR_TEXTO",
    "COLOR_MUTED",
    "_crear_estilos",
    "_estilo_tabla_datos",
    "_pie_pagina",
    "_dia_nombre_corto",
    "_retraso_de_obs",
]
