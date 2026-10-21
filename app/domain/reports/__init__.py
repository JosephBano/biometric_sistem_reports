"""
Motor de generación de reportes (`app.domain.reports`).

Paquete modularizado (Issue #7) que agrupa:
  - `models`: tipos, dataclasses y constantes de configuración.
  - `data_loading`: carga de archivos, filtrado y deduplicación.
  - `justifications`: cruce de justificaciones y normalización de motivos.
  - `rules`: reglas puras de cálculo de asistencia por día y por persona.
  - `pdf_styles`: estilos y paleta de ReportLab.
  - `pdf_general`: renderizado de PDF para reporte general.
  - `pdf_persona`: renderizado de PDF para reporte individual.
  - `pdf_render`: fachada unificada de renderizado PDF.
  - `orchestration`: orquestador `build_pdf` y punto de entrada CLI.
"""
from __future__ import annotations

from app.domain.report_docx import generar_docx, generar_docx_persona
from app.domain.reports.data_loading import (
    _calcular_tiempo_neto_min,
    cargar_archivo,
    deduplicar,
    enriquecer_analisis_con_origen,
    filtrar_excluidos,
)
from app.domain.reports.models import (
    DEFAULT_CONFIG,
    DEFAULT_FILTROS,
    MARGEN_LEVE_MIN,
    _fmt_horas,
    parse_config,
)
from app.domain.reports.orchestration import build_pdf, main
from app.domain.reports.pdf_render import (
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
    generar_pdf,
    generar_pdf_persona,
)
from app.domain.reports.rules import (
    _buscar_horario,
    _get_info_dia,
    _minutos_diferencia,
    analizar_dia,
    analizar_por_persona,
)
from db import (
    consultar_asistencias,
    get_breaks_categorizados_dict,
    get_feriados_set,
    get_horarios,
    get_justificaciones_dict,
    registrar_audit,
)

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_FILTROS",
    "MARGEN_LEVE_MIN",
    "filtrar_excluidos",
    "deduplicar",
    "analizar_dia",
    "analizar_por_persona",
    "generar_pdf",
    "generar_pdf_persona",
    "generar_docx",
    "generar_docx_persona",
    "parse_config",
    "build_pdf",
    "consultar_asistencias",
    "get_breaks_categorizados_dict",
    "get_feriados_set",
    "get_horarios",
    "get_justificaciones_dict",
    "enriquecer_analisis_con_origen",
    "registrar_audit",
    "cargar_archivo",
    "main",
    # Helpers expuestos para compatibilidad con tests unitarios
    "_minutos_diferencia",
    "_dia_nombre_corto",
    "_calcular_tiempo_neto_min",
    "_buscar_horario",
    "_get_info_dia",
    "_fmt_horas",
    "_retraso_de_obs",
    "_crear_estilos",
    "_estilo_tabla_datos",
    "_pie_pagina",
    "COLOR_HEADER",
    "COLOR_SUBHEADER",
    "COLOR_OK",
    "COLOR_WARN",
    "COLOR_ERROR",
    "COLOR_TABLA_ALT",
    "COLOR_TEXTO",
    "COLOR_MUTED",
]
