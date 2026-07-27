"""
Wrapper para `script` + helpers de construcción de PDF/DOCX (`app.domain.reports`).

Re-exporta el motor de generación de reportes PDF desde el módulo top-level
`script.py` (2 281 LOC), y añade las funciones `_parse_config` y `_build_pdf`
que en `app.py` actúan de pegamento entre el request HTTP y el motor.

API pública (estable, documentada en `docs/ARQUITECTURA.md`):
  - `DEFAULT_CONFIG`
  - `filtrar_excluidos(registros, excluidos) -> list`
  - `deduplicar(registros, duplicado_min) -> tuple[list, log]`
  - `analizar_dia(registros, horarios, ...) -> dict`
  - `analizar_por_persona(registros, config, ...) -> dict`
  - `generar_pdf(...)` y `generar_pdf_persona(...)`
  - `parse_config(data: dict) -> dict`
  - `build_pdf(registros, config, modo, persona, pdf_path, nombre_origen,
              fecha_inicio=None, fecha_fin=None, filtros=None, formato='pdf')`
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from script import (  # noqa: F401  (re-export)
    DEFAULT_CONFIG,
    analizar_dia,
    analizar_por_persona,
    deduplicar,
    filtrar_excluidos,
    generar_pdf,
    generar_pdf_persona,
)
from app.domain.report_docx import generar_docx, generar_docx_persona  # noqa: F401  (re-export)


def parse_config(data: dict[str, Any]) -> dict[str, Any]:
    """Extrae y normaliza la config de generación de reportes del request."""
    return {
        "duplicado_min": DEFAULT_CONFIG["duplicado_min"],
        "excluidos":     data.get("excluidos", []) or [],
    }


# Filtros por defecto para los reportes (secciones y columnas a incluir).
DEFAULT_FILTROS: dict[str, bool] = {
    "mostrar_ausencias":          True,
    "mostrar_tardanza_severa":    True,
    "mostrar_tardanza_leve":      True,
    "mostrar_almuerzo":           True,
    "mostrar_incompletos":        True,
    "mostrar_salida_anticipada":  True,
    "mostrar_todos_los_dias":     False,
    "columna_tiempo_dentro":      False,
    "reporte_sin_horario":        False,
    "reporte_todos_usuarios":     False,
    "verificar_horas":            False,
    "mostrar_tiempo_extra":       False,
}


def build_pdf(
    registros: list[dict[str, Any]],
    config: dict[str, Any],
    modo: str,
    persona: str,
    pdf_path: str,
    nombre_origen: str,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
    filtros: dict[str, Any] | None = None,
    formato: str = "pdf",
) -> None:
    """
    Aplica filtros, deduplicación, análisis y genera el reporte (PDF o DOCX).

    Migrado desde `app.py:349-470` (`_build_pdf`). Lanza `ValueError` si no
    hay horarios cargados (los horarios son obligatorios para reportar).
    """
    if filtros is None:
        filtros = {}

    if config.get("excluidos"):
        registros = filtrar_excluidos(registros, config["excluidos"])

    # Cargar horarios personalizados (obligatorios)
    from db import get_horarios  # lazy import para evitar ciclo con create_app
    horarios = get_horarios()
    if not horarios["by_id"]:
        raise ValueError(
            "No se pueden generar reportes sin horarios cargados. "
            "Suba el archivo de horarios primero."
        )

    ids_h = set(horarios["by_id"].keys())
    nom_h = set(horarios["by_nombre"].keys())

    # Personas sin horario (para el reporte especial)
    sin_horario: list[str] = []
    if filtros.get("reporte_sin_horario") or filtros.get("reporte_todos_usuarios"):
        nombres_vistos: set[str] = set()
        for r in registros:
            if r["nombre"] not in nombres_vistos:
                nombres_vistos.add(r["nombre"])
                if r.get("id_usuario") not in ids_h and r["nombre"].upper() not in nom_h:
                    sin_horario.append(r["nombre"])
        sin_horario.sort()

    # Filtro por horario, según modo
    if filtros.get("reporte_sin_horario"):
        registros = [
            r for r in registros
            if (r.get("id_usuario") not in ids_h)
               and (r["nombre"].upper() not in nom_h)
        ]
    elif not filtros.get("reporte_todos_usuarios"):
        registros = [
            r for r in registros
            if (r.get("id_usuario") in ids_h)
               or (r["nombre"].upper() in nom_h)
        ]

    if not registros:
        raise ValueError("No hay registros que coincidan con los filtros aplicados.")

    registros, log_dup = deduplicar(registros, config["duplicado_min"])
    if not registros:
        raise ValueError("No quedaron registros después de aplicar los filtros.")

    # Cargar justificaciones y feriados para el período
    from db import (
        get_breaks_categorizados_dict,
        get_feriados_set,
        get_justificaciones_dict,
    )
    justificaciones = get_justificaciones_dict(fecha_inicio, fecha_fin)
    feriados        = get_feriados_set(fecha_inicio, fecha_fin)
    breaks_cat      = get_breaks_categorizados_dict(fecha_inicio, fecha_fin)

    permitir_sin_horario = (
        filtros.get("reporte_sin_horario", False)
        or filtros.get("reporte_todos_usuarios", False)
    )

    if modo in ("persona", "varias"):
        analisis = analizar_por_persona(
            registros, config, horarios=horarios,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
            justificaciones=justificaciones, feriados=feriados,
            breaks_categorizados=breaks_cat,
            mostrar_todos=filtros.get("mostrar_todos_los_dias", False),
            permitir_sin_horario=permitir_sin_horario,
            verificar_horas=filtros.get("verificar_horas", False),
            mostrar_tiempo_extra=filtros.get("mostrar_tiempo_extra", False),
        )

        if modo == "persona":
            if not persona:
                raise ValueError("Especifique una persona para el modo 'persona'.")
            if persona not in analisis:
                raise ValueError(f"No se encontraron registros para '{persona}'.")
            analisis = {persona: analisis[persona]}
        else:  # varias
            personas_sel = set(config.get("personas", []) or [])
            if not personas_sel:
                raise ValueError("Seleccione al menos una persona.")
            analisis = {k: v for k, v in analisis.items() if k in personas_sel}
            if not analisis:
                raise ValueError(
                    "Ninguna de las personas seleccionadas tiene registros en el período."
                )

        if formato == "docx":
            generar_docx_persona(pdf_path, analisis, config, nombre_origen,
                                 filtros=filtros, sin_horario=sin_horario)
        else:
            generar_pdf_persona(pdf_path, analisis, config, nombre_origen,
                                filtros=filtros, sin_horario=sin_horario)
    else:
        por_fecha: dict[Any, list] = defaultdict(list)
        for r in registros:
            por_fecha[r["fecha"]].append(r)
        analisis = {}
        for fecha, regs in sorted(por_fecha.items()):
            analisis[fecha] = analizar_dia(
                regs, horarios,
                justificaciones=justificaciones,
                feriados=feriados,
                permitir_sin_horario=permitir_sin_horario,
            )
        if formato == "docx":
            generar_docx(pdf_path, analisis, log_dup, config, nombre_origen,
                         filtros=filtros, sin_horario=sin_horario)
        else:
            generar_pdf(pdf_path, analisis, log_dup, config, nombre_origen,
                        filtros=filtros, sin_horario=sin_horario)


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_FILTROS",
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
    "registrar_audit",
]

# Re-exports de `db` (capa de datos), añadidos para cumplir la regla de
# capas del ADR-0001 (antes: `app/web/reports_bp.py` importaba `db` directo).
from db import (  # noqa: E402
    consultar_asistencias,
    get_breaks_categorizados_dict,
    get_feriados_set,
    get_horarios,
    get_justificaciones_dict,
    registrar_audit,
)
