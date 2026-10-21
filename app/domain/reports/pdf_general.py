"""
Generador de reportes PDF para el modo general (`app.domain.reports.pdf_general`).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.reports.pdf_styles import (
    COLOR_ERROR,
    COLOR_HEADER,
    COLOR_SUBHEADER,
    COLOR_TABLA_ALT,
    COLOR_TEXTO,
    COLOR_WARN,
    _crear_estilos,
    _estilo_tabla_datos,
    _pie_pagina,
)


def _portada(st: dict, origen: str, config: dict, analisis: dict) -> list[Any]:
    story = []
    nombre_sistema = os.getenv("NOMBRE_SISTEMA", "Informes Biométricos")
    nombre_institucion = os.getenv("NOMBRE_INSTITUCION", "ISTPET")
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph(nombre_sistema.upper(), st["titulo"]))
    story.append(Paragraph(f"Control Biométrico · {nombre_institucion.upper()}", st["subtitulo"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_HEADER))
    story.append(Spacer(1, 1 * cm))

    datos = [
        ["Archivo origen:",    origen],
        ["Generado el:",       datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Días analizados:",   str(len(analisis))],
    ]
    if config.get("excluidos"):
        datos.append(["Personas excluidas:", ", ".join(config["excluidos"])])

    t = Table(datos, colWidths=[6 * cm, 10 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME",       (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",       (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",       (0, 0), (-1, -1), 10),
        ("TEXTCOLOR",      (0, 0), (0, -1), COLOR_SUBHEADER),
        ("TEXTCOLOR",      (1, 0), (1, -1), COLOR_TEXTO),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",     (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, COLOR_TABLA_ALT]),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(t)
    return story


def _resumen_mensual(st: dict, analisis: dict, _config: dict) -> list[Any]:
    story = []
    story.append(PageBreak())
    story.append(Paragraph("RESUMEN DEL MES", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.5 * cm))

    tot_leve = tot_severa = tot_almuerzo = tot_incompleto = 0
    for d in analisis.values():
        tot_leve       += d["resumen"]["tardanza_leve"]
        tot_severa     += d["resumen"]["tardanza_severa"]
        tot_almuerzo   += d["resumen"]["almuerzo_largo"]
        tot_incompleto += d["resumen"]["incompletos"]

    kpis = [
        (str(tot_leve),       "Tardanzas leves",     COLOR_WARN),
        (str(tot_severa),     "Tardanzas severas",   COLOR_ERROR),
        (str(tot_almuerzo),   "Excesos de almuerzo", COLOR_WARN),
        (str(tot_incompleto), "Registros anómalos",  COLOR_TABLA_ALT),
    ]

    cabeceras = [Paragraph(k[0], st["resumen_num"]) for k in kpis]
    etiquetas = [Paragraph(k[1], st["resumen_lbl"]) for k in kpis]
    t = Table([cabeceras, etiquetas], colWidths=[4.2 * cm] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (i, 0), (i, 1), kpis[i][2]) for i in range(4)
    ] + [
        ("BOX",         (i, 0), (i, 1), 1, colors.HexColor("#dee2e6")) for i in range(4)
    ] + [
        ("TOPPADDING",  (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING",(0, 0),(-1, -1), 12),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 1 * cm))

    story.append(Paragraph("Detalle por fecha", st["seccion"]))
    encabezado = ["Fecha", "Personas", "Tard. Leve", "Tard. Severa",
                  "Exceso Almuerzo", "Reg. Anómalos"]
    filas = [encabezado]
    for dia in sorted(analisis.keys()):
        r = analisis[dia]["resumen"]
        filas.append([
            dia.strftime("%d/%m/%Y"),
            str(r["total_personas"]),
            str(r["tardanza_leve"])   or "—",
            str(r["tardanza_severa"]) or "—",
            str(r["almuerzo_largo"])  or "—",
            str(r["incompletos"])     or "—",
        ])

    t2 = Table(filas, colWidths=[3.5 * cm, 2.2 * cm, 2.5 * cm, 2.8 * cm, 3.5 * cm, 3 * cm])
    t2.setStyle(_estilo_tabla_datos(len(filas)))
    story.append(t2)
    return story


def _pagina_dia(st: dict, dia: Any, datos: dict, _config: dict, filtros_activos: dict | None = None) -> list[Any]:
    if filtros_activos is None:
        filtros_activos = {}
    story = []

    nombre_dia = dia.strftime("%A %d de %B de %Y")
    nombre_dia = (nombre_dia
                  .replace("Monday", "Lunes").replace("Tuesday", "Martes")
                  .replace("Wednesday", "Miércoles").replace("Thursday", "Jueves")
                  .replace("Friday", "Viernes").replace("Saturday", "Sábado")
                  .replace("Sunday", "Domingo")
                  .replace("January", "Enero").replace("February", "Febrero")
                  .replace("March", "Marzo").replace("April", "Abril")
                  .replace("May", "Mayo").replace("June", "Junio")
                  .replace("July", "Julio").replace("August", "Agosto")
                  .replace("September", "Septiembre").replace("October", "Octubre")
                  .replace("November", "Noviembre").replace("December", "Diciembre"))

    story.append(Paragraph(f"  {nombre_dia.upper()}", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.3 * cm))

    r = datos["resumen"]
    sal_ant = r.get("salida_anticipada_leve", 0) + r.get("salida_anticipada_severa", 0)
    story.append(Paragraph(
        f"<b>{r['total_personas']}</b> personas registradas  |  "
        f"<b>{r['tardanza_leve']}</b> tard. leves  |  "
        f"<b>{r['tardanza_severa']}</b> tard. severas  |  "
        f"<b>{r['almuerzo_largo']}</b> excesos almuerzo  |  "
        f"<b>{sal_ant}</b> salidas ant.",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.4 * cm))

    if filtros_activos.get("mostrar_tardanza_severa", True):
        story += _seccion_tardanza(
            st, "Tardanza Severa",
            "Llegadas con más de 5 minutos de retraso sobre el horario programado",
            datos["tardanza_severa"], COLOR_ERROR, "🔴"
        )

    if filtros_activos.get("mostrar_tardanza_leve", True):
        story += _seccion_tardanza(
            st, "Tardanza Leve",
            "Llegadas con 1 a 5 minutos de retraso sobre el horario programado",
            datos["tardanza_leve"], COLOR_WARN, "🟡"
        )

    if filtros_activos.get("mostrar_almuerzo", True):
        story += _seccion_almuerzo(st, datos["almuerzo_largo"])

    if filtros_activos.get("mostrar_incompletos", True):
        story += _seccion_incompletos(st, datos["registros_incompletos"])

    if filtros_activos.get("mostrar_salida_anticipada", True):
        sal_sev = datos.get("salida_anticipada_severa", [])
        sal_lev = datos.get("salida_anticipada_leve", [])
        if sal_sev or sal_lev:
            story += _seccion_salida_anticipada_general(st, sal_sev, sal_lev)

    return story


def _seccion_tardanza(st: dict, titulo: str, descripcion: str, lista: list, color_bg: colors.Color, icono: str) -> list[Any]:
    story = []
    story.append(Paragraph(f"{icono}  {titulo}", st["seccion"]))
    story.append(Paragraph(descripcion, st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))

    if not lista:
        story.append(Paragraph("✓ Sin novedades", st["ok"]))
    else:
        encabezado = ["#", "Nombre", "Hora de llegada", "Retraso (min)"]
        filas = [encabezado]
        for i, p in enumerate(lista, 1):
            filas.append([str(i), p["nombre"], p["hora"], f"+{p['retraso']} min"])
        t = Table(filas, colWidths=[0.8 * cm, 9 * cm, 3.5 * cm, 3.2 * cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=color_bg))
        story.append(t)

    story.append(Spacer(1, 0.4 * cm))
    return story


def _seccion_almuerzo(st: dict, lista: list) -> list[Any]:
    story = []
    story.append(Paragraph("🍽️  Exceso de Almuerzo", st["seccion"]))
    story.append(Paragraph(
        "Personas con exceso de tiempo de almuerzo según horario individual",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    if not lista:
        story.append(Paragraph("✓ Sin novedades", st["ok"]))
    else:
        encabezado = ["#", "Nombre", "Salida", "Regreso", "Duración", "Exceso"]
        filas = [encabezado]
        for i, p in enumerate(lista, 1):
            filas.append([
                str(i), p["nombre"], p["salida"], p["regreso"],
                f"{p['duracion']} min", f"+{p['exceso']} min"
            ])
        t = Table(filas, colWidths=[0.8 * cm, 6.5 * cm, 2 * cm, 2 * cm, 2.5 * cm, 2.7 * cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_WARN))
        story.append(t)

    story.append(Spacer(1, 0.4 * cm))
    return story


def _seccion_incompletos(st: dict, lista: list) -> list[Any]:
    story = []
    if not lista:
        return story
    story.append(Paragraph("⚠️  Registros Anómalos / Incompletos", st["seccion"]))
    story.append(Paragraph(
        "Personas con número inusual de marcaciones (esperado: 2 o 4 por día)",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    encabezado = ["Nombre", "# Registros", "Detalle"]
    filas = [encabezado]
    for p in lista:
        det_val = p.get("detalle", "—")
        if det_val and det_val != "—":
            det_val = Paragraph(det_val, st["pequeño"])
        filas.append([p["nombre"], str(p["registros"]), det_val])
    t = Table(filas, colWidths=[5.5 * cm, 2.5 * cm, 8.5 * cm])
    t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_TABLA_ALT))
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))
    return story


def _seccion_salida_anticipada_general(st: dict, severas: list, leves: list) -> list[Any]:
    """Sección de salidas anticipadas en el reporte general (por día)."""
    story = []
    story.append(Paragraph("🚪  Salidas Anticipadas", st["seccion"]))
    story.append(Paragraph(
        "Personas que salieron antes de su hora de salida programada",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    enc = ["#", "Nombre", "Salida real", "Prog. salida", "Adelanto"]
    filas = [enc]
    for i, p in enumerate(severas, 1):
        filas.append([str(i), p["nombre"], p["hora"],
                      p.get("programado", "—"), f"-{p['retraso']} min"])
    offset = len(severas)
    for i, p in enumerate(leves, offset + 1):
        filas.append([str(i), p["nombre"], p["hora"],
                      p.get("programado", "—"), f"-{p['retraso']} min"])

    t = Table(filas, colWidths=[0.8 * cm, 7.5 * cm, 2.5 * cm, 2.7 * cm, 2.8 * cm])
    t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_WARN))
    for i in range(1, len(severas) + 1):
        t.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), COLOR_ERROR)]))
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))
    return story


def _pagina_duplicados(st: dict, log: list) -> list[Any]:
    story = []
    story.append(Paragraph("🔄  LOG DE MARCACIONES DUPLICADAS CORREGIDAS", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Las siguientes marcaciones fueron detectadas como duplicados por error humano "
        "y excluidas del análisis. Se conservó la primera marcación de cada par.",
        st["normal"]
    ))
    story.append(Spacer(1, 0.4 * cm))

    encabezado = ["Nombre", "Fecha", "Tipo", "Hora original", "Hora duplicada", "Diferencia"]
    filas = [encabezado]
    for d in sorted(log, key=lambda x: (x["fecha"], x["nombre"])):
        filas.append([
            d["nombre"],
            d["fecha"].strftime("%d/%m/%Y"),
            d["tipo"],
            d["hora_orig"],
            d["hora_dup"],
            f"{d['diferencia']} min",
        ])
    t = Table(filas, colWidths=[5 * cm, 2.5 * cm, 2 * cm, 2.8 * cm, 3 * cm, 2.2 * cm])
    t.setStyle(_estilo_tabla_datos(len(filas)))
    story.append(t)
    return story


def generar_pdf(
    ruta_salida: str,
    analisis_por_dia: dict,
    log_duplicados: list[dict],
    config: dict,
    nombre_archivo_origen: str,
    filtros: dict | None = None,
    sin_horario: list[str] | None = None,
) -> None:
    """Genera el PDF completo con todos los días y el log de duplicados."""
    if filtros is None:
        filtros = {}
    if sin_horario is None:
        sin_horario = []

    f_activos = {
        "mostrar_tardanza_leve":     filtros.get("mostrar_tardanza_leve",     True),
        "mostrar_tardanza_severa":   filtros.get("mostrar_tardanza_severa",   True),
        "mostrar_almuerzo":          filtros.get("mostrar_almuerzo",          True),
        "mostrar_incompletos":       filtros.get("mostrar_incompletos",       True),
        "mostrar_salida_anticipada": filtros.get("mostrar_salida_anticipada", True),
        "mostrar_todos_los_dias":    filtros.get("mostrar_todos_los_dias",    False),
    }

    doc = SimpleDocTemplate(
        ruta_salida,
        pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Reporte Biométrico",
        author="Sistema de Control de Asistencia",
    )

    styles  = getSampleStyleSheet()
    story   = []
    st      = _crear_estilos(styles)

    story += _portada(st, nombre_archivo_origen, config, analisis_por_dia)
    story += _resumen_mensual(st, analisis_por_dia, config)

    claves_activas = []
    if f_activos["mostrar_tardanza_leve"]:
        claves_activas.append("tardanza_leve")
    if f_activos["mostrar_tardanza_severa"]:
        claves_activas.append("tardanza_severa")
    if f_activos["mostrar_almuerzo"]:
        claves_activas.append("almuerzo_largo")
    if f_activos["mostrar_incompletos"]:
        claves_activas.append("incompletos")
    if f_activos["mostrar_salida_anticipada"]:
        claves_activas.append("salida_anticipada_leve")
        claves_activas.append("salida_anticipada_severa")

    if f_activos["mostrar_todos_los_dias"]:
        dias_a_mostrar = sorted(analisis_por_dia.keys())
    else:
        dias_a_mostrar = [
            d for d in sorted(analisis_por_dia.keys())
            if any(analisis_por_dia[d]["resumen"].get(k, 0) > 0 for k in claves_activas)
        ]

    if not dias_a_mostrar:
        total_dias_con_reg = len(analisis_por_dia)
        sufijo = "día con registros" if total_dias_con_reg == 1 else "días con registros"
        story.append(Spacer(1, 2 * cm))
        story.append(Paragraph(
            f"✓ Sin novedades en el período consultado "
            f"({total_dias_con_reg} {sufijo}).",
            st["ok"]
        ))
    else:
        for dia in dias_a_mostrar:
            story.append(Spacer(1, 1 * cm))
            story += _pagina_dia(st, dia, analisis_por_dia[dia], config, f_activos)

    if sin_horario:
        story.append(Spacer(1, 1 * cm))
        story.append(Paragraph("PERSONAS EN EL BIOMÉTRICO SIN HORARIO ASIGNADO", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3 * cm))
        filas_sh = [["#", "Nombre"]]
        for i, n in enumerate(sin_horario, 1):
            filas_sh.append([str(i), n])
        t_sh = Table(filas_sh, colWidths=[1.2 * cm, 15.3 * cm])
        t_sh.setStyle(_estilo_tabla_datos(len(filas_sh)))
        story.append(t_sh)

    if log_duplicados:
        story.append(Spacer(1, 1 * cm))
        story += _pagina_duplicados(st, log_duplicados)

    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    print(f"\n✅ Reporte generado: {ruta_salida}\n")
