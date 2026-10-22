"""
Orquestación de reportes y CLI (`app.domain.reports.orchestration`).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from typing import Any

from app.domain.report_docx import generar_docx, generar_docx_persona
from app.domain.reports.data_loading import (
    cargar_archivo,
    deduplicar,
    enriquecer_analisis_con_origen,
    filtrar_excluidos,
)
from app.domain.reports.models import DEFAULT_CONFIG
from app.domain.reports.pdf_render import generar_pdf, generar_pdf_persona
from app.domain.reports.rules import analizar_dia, analizar_por_persona

log = logging.getLogger(__name__)


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
    Lanza `ValueError` si no hay horarios cargados.
    """
    if filtros is None:
        filtros = {}

    if config.get("excluidos"):
        registros = filtrar_excluidos(registros, config["excluidos"])

    from db import get_horarios
    horarios = get_horarios()
    if not horarios["by_id"]:
        raise ValueError(
            "No se pueden generar reportes sin horarios cargados. "
            "Suba el archivo de horarios primero.",
        )

    ids_h = set(horarios["by_id"].keys())
    nom_h = set(horarios["by_nombre"].keys())

    sin_horario: list[str] = []
    if filtros.get("reporte_sin_horario") or filtros.get("reporte_todos_usuarios"):
        nombres_vistos: set[str] = set()
        for r in registros:
            if r["nombre"] not in nombres_vistos:
                nombres_vistos.add(r["nombre"])
                if r.get("id_usuario") not in ids_h and r["nombre"].upper() not in nom_h:
                    sin_horario.append(r["nombre"])
        sin_horario.sort()

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
        else:
            personas_sel = set(config.get("personas", []) or [])
            if not personas_sel:
                raise ValueError("Seleccione al menos una persona.")
            analisis = {k: v for k, v in analisis.items() if k in personas_sel}
            if not analisis:
                raise ValueError(
                    "Ninguna de las personas seleccionadas tiene registros en el período.",
                )

        registros_por_nombre: dict[str, list[dict[str, Any]]] = {}
        for r in registros:
            n = r["nombre"]
            registros_por_nombre.setdefault(n, []).append(r)
        enriquecer_analisis_con_origen(analisis, registros_por_nombre)

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generador de reportes biométricos en PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("archivo",
        help="Archivo biométrico (.xls, .xlsx o .csv)")
    parser.add_argument("--modo", choices=["general", "persona"], default="general",
        help="Modo del reporte (default: general)")
    parser.add_argument("--persona", metavar="NOMBRE",
        help="Si el modo es 'persona', generar reporte solo para esta persona.")
    parser.add_argument("--excluir", nargs="+", metavar="NOMBRE",
        default=[],
        help='Personas a excluir (ej: --excluir "Juan Perez" "Maria Lopez")')
    parser.add_argument("--duplicado-min", type=float,
        default=DEFAULT_CONFIG["duplicado_min"],
        metavar="MINUTOS",
        help=f"Minutos máximos para considerar marcación como duplicado (default: {DEFAULT_CONFIG['duplicado_min']})")
    parser.add_argument("--fecha", type=int, metavar="DIA",
        help="Analizar solo este día del mes (ej: --fecha 15)")
    parser.add_argument("--salida", metavar="ARCHIVO.pdf",
        help="Nombre del PDF de salida (default: reporte_<origen>.pdf)")

    args = parser.parse_args()

    if not os.path.exists(args.archivo):
        print(f"❌ Error: No se encontró el archivo '{args.archivo}'")
        sys.exit(1)

    config = {
        "duplicado_min": args.duplicado_min,
        "excluidos":     args.excluir,
    }

    print(f"\n📂 Cargando archivo: {args.archivo}")
    try:
        registros = cargar_archivo(args.archivo)
    except Exception as e:
        log.exception("No se pudo leer el archivo del reporte")
        print(f"❌ Error al leer el archivo: {e}")
        sys.exit(1)

    print(f"   ✓ {len(registros)} registros encontrados")

    if config["excluidos"]:
        antes = len(set(r["nombre"] for r in registros))
        registros = filtrar_excluidos(registros, config["excluidos"])
        despues = len(set(r["nombre"] for r in registros))
        print(f"   ✓ {antes - despues} persona(s) excluida(s)")

    print(f"\n🔄 Detectando marcaciones duplicadas (umbral: {config['duplicado_min']} min)...")
    registros, log_dup = deduplicar(registros, config["duplicado_min"])
    print(f"   ✓ {len(log_dup)} duplicado(s) eliminado(s)")

    if args.modo == "persona":
        print("\n📊 Analizando registros por persona...")
        analisis_persona = analizar_por_persona(registros, config, {})

        if args.persona:
            if args.persona in analisis_persona:
                analisis_persona = {args.persona: analisis_persona[args.persona]}
            else:
                print(f"❌ No se encontraron registros para la persona '{args.persona}'")
                sys.exit(1)

        if args.salida:
            ruta_pdf = args.salida
        else:
            base = os.path.splitext(os.path.basename(args.archivo))[0]
            persona_suffix = f"_{args.persona.replace(' ', '_')}" if args.persona else ""
            ruta_pdf = f"reporte_persona_{base}{persona_suffix}.pdf"

        print(f"\n📄 Generando PDF por persona: {ruta_pdf}")
        generar_pdf_persona(
            ruta_pdf,
            analisis_persona,
            config,
            args.archivo,
        )
    else:
        por_fecha = defaultdict(list)
        for r in registros:
            por_fecha[r["fecha"]].append(r)

        if args.fecha:
            por_fecha = {
                fecha: regs for fecha, regs in por_fecha.items()
                if fecha.day == args.fecha
            }
            if not por_fecha:
                print(f"❌ No se encontraron registros para el día {args.fecha}")
                sys.exit(1)

        print(f"\n📊 Analizando {len(por_fecha)} día(s)...")
        analisis_por_dia = {}
        for fecha, regs in sorted(por_fecha.items()):
            analisis_por_dia[fecha] = analizar_dia(regs, {})
            r = analisis_por_dia[fecha]["resumen"]
            print(f"   {fecha.strftime('%d/%m/%Y')}  →  "
                  f"{r['total_personas']} personas, "
                  f"{r['tardanza_leve']} tard.leves, "
                  f"{r['tardanza_severa']} tard.severas, "
                  f"{r['almuerzo_largo']} excesos almuerzo")

        if args.salida:
            ruta_pdf = args.salida
        else:
            base = os.path.splitext(os.path.basename(args.archivo))[0]
            ruta_pdf = f"reporte_{base}.pdf"

        print(f"\n📄 Generando PDF: {ruta_pdf}")
        generar_pdf(
            ruta_pdf,
            analisis_por_dia,
            log_dup,
            config,
            args.archivo,
        )

    config_path = ruta_pdf.replace(".pdf", "_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"⚙️  Configuración guardada en: {config_path}")
