"""
Estilos visuales, paleta y utilidades de renderizado PDF ReportLab (`app.domain.reports.pdf_styles`).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import TableStyle

# ══════════════════════════════════════════════════════════════════════════
# COLORES DEL REPORTE
# ══════════════════════════════════════════════════════════════════════════

COLOR_HEADER     = colors.HexColor("#1a3a5c")   # Azul oscuro corporativo
COLOR_SUBHEADER  = colors.HexColor("#2e6da4")   # Azul medio
COLOR_OK         = colors.HexColor("#d4edda")   # Verde suave
COLOR_WARN       = colors.HexColor("#fff3cd")   # Amarillo suave
COLOR_ERROR      = colors.HexColor("#f8d7da")   # Rojo suave
COLOR_TABLA_ALT  = colors.HexColor("#f0f4f8")   # Gris muy suave (fila alterna)
COLOR_TEXTO      = colors.HexColor("#212529")   # Texto oscuro
COLOR_MUTED      = colors.HexColor("#6c757d")   # Texto gris


def _dia_nombre_corto(fecha: Any) -> str:
    """Retorna el nombre del día en español (3 letras)."""
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    return dias[fecha.weekday()]


def _retraso_de_obs(observaciones: list[str]) -> str:
    """Extrae el texto de retraso (ej '+3m') de las observaciones."""
    for o in observaciones:
        m = re.search(r'\+(\d+)m', o)
        if m:
            return f"+{m.group(1)} min"
    return "—"


def _crear_estilos(_base: Any = None) -> dict[str, ParagraphStyle]:
    """Crea y retorna los estilos de tipografía ReportLab para el reporte."""
    return {
        "titulo":      ParagraphStyle("titulo",      fontName="Helvetica-Bold",
                                      fontSize=22, textColor=COLOR_HEADER,
                                      alignment=TA_CENTER, spaceAfter=10, leading=28),
        "subtitulo":   ParagraphStyle("subtitulo",   fontName="Helvetica",
                                      fontSize=11, textColor=COLOR_MUTED,
                                      alignment=TA_CENTER, spaceAfter=10, leading=14),
        "dia_titulo":  ParagraphStyle("dia_titulo",  fontName="Helvetica-Bold",
                                      fontSize=16, textColor=COLOR_HEADER,
                                      spaceBefore=8, spaceAfter=6),
        "seccion":     ParagraphStyle("seccion",     fontName="Helvetica-Bold",
                                      fontSize=11, textColor=COLOR_SUBHEADER,
                                      spaceBefore=10, spaceAfter=4),
        "normal":      ParagraphStyle("normal",      fontName="Helvetica",
                                      fontSize=9,  textColor=COLOR_TEXTO,
                                      spaceAfter=2),
        "pequeño":     ParagraphStyle("pequeño",     fontName="Helvetica",
                                      fontSize=8,  textColor=COLOR_MUTED),
        "ok":          ParagraphStyle("ok",          fontName="Helvetica-Oblique",
                                      fontSize=9,  textColor=colors.HexColor("#28a745")),
        "negrita":     ParagraphStyle("negrita",     fontName="Helvetica-Bold",
                                      fontSize=9,  textColor=COLOR_TEXTO),
        "tabla_head":  ParagraphStyle("tabla_head",  fontName="Helvetica-Bold",
                                      fontSize=8.5, textColor=colors.white,
                                      alignment=TA_CENTER),
        "tabla_cell":  ParagraphStyle("tabla_cell",  fontName="Helvetica",
                                      fontSize=8.5, textColor=COLOR_TEXTO),
        "resumen_num": ParagraphStyle("resumen_num", fontName="Helvetica-Bold",
                                      fontSize=20, textColor=COLOR_HEADER,
                                      alignment=TA_CENTER),
        "resumen_lbl": ParagraphStyle("resumen_lbl", fontName="Helvetica",
                                      fontSize=8,  textColor=COLOR_MUTED,
                                      alignment=TA_CENTER),
    }


def _estilo_tabla_datos(_n_filas: int, color_fila: colors.Color | None = None) -> TableStyle:
    """Genera el TableStyle uniforme para tablas de datos ReportLab."""
    bg = color_fila or COLOR_TABLA_ALT
    estilos = [
        # Encabezado
        ("BACKGROUND",    (0, 0), (-1, 0), COLOR_HEADER),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8.5),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # Cuerpo
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
        ("TEXTCOLOR",     (0, 1), (-1, -1), COLOR_TEXTO),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("BACKGROUND",    (0, 1), (-1, -1), bg),
    ]
    return TableStyle(estilos)


def _pie_pagina(canvas: Any, doc: Any) -> None:
    """Callback de pie de página para SimpleDocTemplate."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(COLOR_MUTED)
    canvas.drawString(
        1.8 * cm, 1.2 * cm,
        f"Reporte Biométrico — Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}",
    )
    canvas.drawRightString(
        A4[0] - 1.8 * cm, 1.2 * cm,
        f"Página {doc.page}",
    )
    canvas.restoreState()
