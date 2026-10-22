"""
Generador de reportes PDF para el modo individual o por persona (`app.domain.reports.pdf_persona`).
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

from app.domain.reports.models import _fmt_horas
from app.domain.reports.pdf_styles import (
    COLOR_ERROR,
    COLOR_HEADER,
    COLOR_OK,
    COLOR_SUBHEADER,
    COLOR_TABLA_ALT,
    COLOR_TEXTO,
    COLOR_WARN,
    _crear_estilos,
    _estilo_tabla_datos,
    _pie_pagina,
    _retraso_de_obs,
)


def _seccion_cronologico_persona(st: dict, datos: list, con_tiempo_dentro: bool) -> list[Any]:
    """Muestra todos los días analizados en una tabla cronológica."""
    story = []
    story.append(Paragraph("  DETALLE CRONOLÓGICO DE ASISTENCIA", st["seccion"]))
    story.append(Paragraph("Listado de todos los días laborables analizados en el período", st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))

    if not datos:
        story.append(Paragraph("Sin registros disponibles.", st["ok"]))
    else:
        enc = ["Fecha", "Ingreso", "Salida"]
        w   = [4.0 * cm, 4.0 * cm, 4.0 * cm]
        if con_tiempo_dentro:
            enc.append("T. Dentro")
            w.append(4.0 * cm)

        w[-1] += (17.4 * cm - sum(w))

        filas = [enc]
        for d in datos:
            fila = [
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("llegada") or "—",
                d.get("salida") or "—",
            ]
            if con_tiempo_dentro:
                fila.append(d.get("tiempo_dentro") or "—")
            filas.append(fila)

        t = Table(filas, colWidths=w, repeatRows=1)
        t.setStyle(_estilo_tabla_datos(len(filas)))

        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_WARN)]))
            elif d.get("estado") == "severa":
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#f8d7da"))]))
            elif d.get("estado") == "ausente":
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#e2e3e5"))]))
            elif d.get("estado") in ("leve", "incompleto"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#fff3cd"))]))

        story.append(t)

    story.append(Spacer(1, 0.5 * cm))
    return story


def _seccion_ausencias_persona(st: dict, datos: list) -> list[Any]:
    story = []
    story.append(Paragraph("  AUSENCIAS", st["seccion"]))
    story.append(Paragraph("Días en que debía trabajar y no registró ninguna marcación.", st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))
    if not datos:
        story.append(Paragraph("✓ Sin ausencias en el período.", st["ok"]))
    else:
        filas = [["Fecha", "Horario programado"]]
        for d in datos:
            filas.append([
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("hora_programada") or "—",
            ])
        t = Table(filas, colWidths=[8.7 * cm, 8.7 * cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_ERROR))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5 * cm))
    return story


def _seccion_tardanzas_persona(
    st: dict,
    titulo: str,
    desc: str,
    datos: list,
    color_bg: colors.Color,
    con_tiempo_dentro: bool,
) -> list[Any]:
    story = []
    story.append(Paragraph(f"  {titulo.upper()}", st["seccion"]))
    story.append(Paragraph(desc, st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))
    if not datos:
        story.append(Paragraph("✓ Sin novedades.", st["ok"]))
    else:
        enc = ["Fecha", "Programado", "Llegada", "Retraso"]
        w   = [4.5 * cm, 4.5 * cm, 4 * cm, 4.4 * cm]
        if con_tiempo_dentro:
            enc.append("Tiempo dentro")
            w = [3.5 * cm, 3.5 * cm, 3.5 * cm, 3.4 * cm, 3.5 * cm]

        filas = [enc]
        for d in datos:
            fila = [
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("hora_programada") or "—",
                d.get("llegada") or "—",
                _retraso_de_obs(d.get("observaciones", [])),
            ]
            if con_tiempo_dentro:
                fila.append(d.get("tiempo_dentro") or "—")
            filas.append(fila)
        t = Table(filas, colWidths=w)
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=color_bg))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5 * cm))
    return story


def _seccion_almuerzo_persona(st: dict, datos: list) -> list[Any]:
    story = []
    story.append(Paragraph("  EXCESOS DE ALMUERZO", st["seccion"]))
    story.append(Paragraph("Días con tiempo de almuerzo superior al límite establecido.", st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))
    if not datos:
        story.append(Paragraph("✓ Sin excesos de almuerzo.", st["ok"]))
    else:
        filas = [["Fecha", "Salida", "Regreso", "Duración", "Exceso"]]
        for d in datos:
            filas.append([
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("almuerzo_salida")  or "—",
                d.get("almuerzo_regreso") or "—",
                f"{d['almuerzo_duracion']} min" if d.get("almuerzo_duracion") else "—",
                f"+{d['almuerzo_exceso']} min"  if d.get("almuerzo_exceso")   else "—",
            ])
        t = Table(filas, colWidths=[4 * cm, 3 * cm, 3.4 * cm, 3.5 * cm, 3.5 * cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_WARN))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5 * cm))
    return story


def _seccion_incompletos_persona(st: dict, datos: list) -> list[Any]:
    story = []
    story.append(Paragraph("  REGISTROS ANÓMALOS / INCOMPLETOS", st["seccion"]))
    story.append(Paragraph("Días con un número inusual de marcaciones (esperado: 2 o 4).", st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))
    if not datos:
        story.append(Paragraph("✓ Sin registros anómalos.", st["ok"]))
    else:
        filas = [["Fecha", "# Reg.", "Detalle de marcaciones"]]
        for d in datos:
            det_val = d.get("detalle_registros") or "—"
            if det_val != "—":
                det_val = Paragraph(det_val, st["pequeño"])

            filas.append([
                d["fecha"].strftime("%d/%m/%Y"),
                str(d.get("n_registros", "?")),
                det_val,
            ])
        t = Table(filas, colWidths=[4 * cm, 2.5 * cm, 10.9 * cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_TABLA_ALT))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5 * cm))
    return story


def _seccion_salidas_anticipadas_persona(st: dict, datos: list) -> list[Any]:
    story = []
    story.append(Paragraph("  SALIDAS ANTICIPADAS", st["seccion"]))
    story.append(Paragraph("Días en que el empleado salió antes de la hora de salida programada.", st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))
    if not datos:
        story.append(Paragraph("✓ Sin salidas anticipadas.", st["ok"]))
    else:
        filas = [["Fecha", "Salida real", "Observación"]]
        for d in datos:
            obs_filtradas = [o for o in d.get("observaciones", []) if "Salida ant." in o]
            obs_txt = " / ".join(obs_filtradas) or "—"
            filas.append([
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("salida") or "—",
                Paragraph(obs_txt, st["pequeño"]),
            ])
        t = Table(filas, colWidths=[4 * cm, 3.5 * cm, 9.9 * cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_ERROR))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5 * cm))
    return story


def _seccion_permisos_persona(st: dict, datos: list) -> list[Any]:
    story = []
    story.append(Paragraph("  PERMISOS TEMPORALES DURANTE LA JORNADA", st["seccion"]))
    story.append(Paragraph("Ausencias autorizadas por RRHH durante el transcurso del día.", st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))

    hay_alm = any(d.get("permiso_alm_min", 0) > 0 for d in datos)

    if hay_alm:
        enc = ["Fecha", "Salida", "Retorno", "Total", "Alm. incl.", "Neto"]
        col_w = [3.2 * cm, 2.8 * cm, 2.8 * cm, 2.3 * cm, 2.5 * cm, 3.8 * cm]
    else:
        enc = ["Fecha", "Salida Permiso", "Regreso Permiso", "Duración"]
        col_w = [4.3 * cm, 4.3 * cm, 4.3 * cm, 4.5 * cm]

    filas = [enc]
    for d in datos:
        dur = d.get("permiso_duracion") or 0
        neto = d.get("permiso_neto_min", dur)
        alm = d.get("permiso_alm_min", 0)
        neto_h, neto_m = divmod(neto, 60)
        neto_str = f"{neto_h}h {neto_m:02d}m"
        if hay_alm:
            filas.append([
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("permiso_salida") or "—",
                d.get("permiso_retorno") or "—",
                f"{dur} min",
                f"{alm} min" if alm else "—",
                neto_str,
            ])
        else:
            filas.append([
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("permiso_salida") or "—",
                d.get("permiso_retorno") or "—",
                f"{dur} min",
            ])
    t = Table(filas, colWidths=col_w)
    t.setStyle(_estilo_tabla_datos(len(filas), color_fila=colors.HexColor("#e9ecef")))

    for i, d in enumerate(datos):
        if d.get("justificado") and d.get("estado") == "ok":
            t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_OK)]))
        elif d.get("estado") == "severa":
            t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_ERROR)]))
        elif d.get("estado") == "leve":
            t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COLOR_WARN)]))

    story.append(t)
    story.append(Spacer(1, 0.5 * cm))
    return story


def _seccion_horas_contrato(st: dict, resumen: dict) -> list[Any]:
    story = []
    story.append(Paragraph("  CUMPLIMIENTO DE HORAS DE CONTRATO", st["seccion"]))

    tipo = resumen.get("horas_contrato_tipo")
    valor = resumen.get("horas_contrato_valor")

    subt = f"Horas estipuladas: <b>{valor}h {tipo}</b>"
    story.append(Paragraph(subt, st["pequeño"]))
    story.append(Spacer(1, 0.2 * cm))

    if tipo == "semana":
        enc = ["Semana", "Esperadas", "Trabajadas", "Diferencia"]
        filas = [enc]
        for s in resumen.get("detalle_semanas", []):
            diff = s["diferencia_min"]
            filas.append([
                s["semana"],
                _fmt_horas(s["esperados_min"]),
                _fmt_horas(s["trabajados_min"]),
                _fmt_horas(diff),
            ])
        t = Table(filas, colWidths=[4.3 * cm, 4.3 * cm, 4.3 * cm, 4.5 * cm])
        t.setStyle(_estilo_tabla_datos(len(filas)))

        for i, s in enumerate(resumen.get("detalle_semanas", [])):
            diff = s["diferencia_min"]
            if diff >= 0:
                bg = COLOR_OK
            elif abs(diff) < 120:
                bg = COLOR_WARN
            else:
                bg = COLOR_ERROR
            t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), bg)]))

        story.append(t)
    else:
        total_trab = resumen.get("total_neto_min", 0)
        esperado = int(float(valor) * 60)
        diff = total_trab - esperado

        datos_mes = [
            ["Total Trabajado:", _fmt_horas(total_trab)],
            ["Total Esperado:", _fmt_horas(esperado)],
            ["Diferencia:",     _fmt_horas(diff)],
        ]
        t = Table(datos_mes, colWidths=[6 * cm, 4 * cm])
        bg = COLOR_OK if diff >= 0 else COLOR_ERROR if abs(diff) > 480 else COLOR_WARN
        t.setStyle(TableStyle([
            ("FONTNAME",   (0, 0), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 2), (-1, 2), bg),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(t)

    story.append(Spacer(1, 0.5 * cm))
    return story


def generar_pdf_persona(
    ruta_salida: str,
    analisis_persona: dict,
    config: dict,
    nombre_archivo_origen: str,
    filtros: dict | None = None,
    sin_horario: list[str] | None = None,
) -> None:
    if filtros is None:
        filtros = {}
    if sin_horario is None:
        sin_horario = []

    f_activos = {
        "mostrar_ausencias":         filtros.get("mostrar_ausencias",         True),
        "mostrar_tardanza_severa":   filtros.get("mostrar_tardanza_severa",   True),
        "mostrar_tardanza_leve":     filtros.get("mostrar_tardanza_leve",     True),
        "mostrar_almuerzo":          filtros.get("mostrar_almuerzo",          True),
        "mostrar_incompletos":       filtros.get("mostrar_incompletos",       True),
        "mostrar_salida_anticipada": filtros.get("mostrar_salida_anticipada", True),
        "mostrar_todos_los_dias":    filtros.get("mostrar_todos_los_dias",    False),
        "columna_tiempo_dentro":     filtros.get("columna_tiempo_dentro",     False),
        "verificar_horas":           filtros.get("verificar_horas",           False),
        "mostrar_tiempo_extra":      filtros.get("mostrar_tiempo_extra",      False),
    }

    doc = SimpleDocTemplate(
        ruta_salida,
        pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Reporte Biométrico por Persona",
        author="Sistema de Control de Asistencia",
    )

    styles  = getSampleStyleSheet()
    story   = []
    st      = _crear_estilos(styles)

    nombre_sistema     = os.getenv("NOMBRE_SISTEMA",     "Informes Biométricos")
    nombre_institucion = os.getenv("NOMBRE_INSTITUCION", "ISTPET")

    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph(f"{nombre_sistema.upper()} (POR PERSONA)", st["titulo"]))
    story.append(Paragraph(f"Control Biométrico · {nombre_institucion.upper()}", st["subtitulo"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_HEADER))
    story.append(Spacer(1, 1 * cm))

    if len(analisis_persona) == 1:
        persona_nombre = list(analisis_persona.keys())[0]
        datos_portada = [
            ["Archivo origen:",     nombre_archivo_origen],
            ["Generado el:",        datetime.now().strftime("%d/%m/%Y %H:%M")],
            ["Persona analizada:",  persona_nombre],
        ]
    else:
        datos_portada = [
            ["Archivo origen:",      nombre_archivo_origen],
            ["Generado el:",         datetime.now().strftime("%d/%m/%Y %H:%M")],
            ["Personas analizadas:", str(len(analisis_persona))],
        ]
    t_portada = Table(datos_portada, colWidths=[6 * cm, 10 * cm])
    t_portada.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",      (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TEXTCOLOR",     (0, 0), (0, -1), COLOR_SUBHEADER),
        ("TEXTCOLOR",     (1, 0), (1, -1), COLOR_TEXTO),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BACKGROUND",    (0, 1), (-1, -1), COLOR_TABLA_ALT),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
    ]))
    story.append(t_portada)
    story.append(PageBreak())

    story.append(Paragraph("RESUMEN GENERAL", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.5 * cm))

    enc_res = ["Persona", "Días", "Ausencias", "Tard. Sev.",
               "Tard. Lev.", "Sal. Ant.", "Exc. Alm.", "Anóm.", "Justif."]
    filas_resumen = [enc_res]
    for nombre in sorted(analisis_persona.keys()):
        r = analisis_persona[nombre]["resumen"]
        tot_salida = r.get("salida_anticipada_severa", 0) + r.get("salida_anticipada_leve", 0)
        filas_resumen.append([
            nombre,
            str(r.get("total_dias", 0)),
            str(r.get("ausencias", 0)),
            str(r.get("tardanza_severa", 0)),
            str(r.get("tardanza_leve",  0)),
            str(tot_salida),
            str(r.get("almuerzo_largo", 0)),
            str(r.get("incompletos",    0)),
            str(r.get("justificadas",   0)),
        ])
    t_res = Table(filas_resumen, colWidths=[3.6 * cm, 1.2 * cm, 1.6 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm])
    t_res.setStyle(_estilo_tabla_datos(len(filas_resumen)))
    story.append(t_res)

    for nombre in sorted(analisis_persona.keys()):
        story.append(Spacer(1, 1 * cm))
        story.append(Paragraph(f"  {nombre}", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3 * cm))

        r = analisis_persona[nombre]["resumen"]
        partes = []
        if r.get("ausencias",       0):
            partes.append(f"<b>{r['ausencias']}</b> ausencias")
        if r.get("tardanza_severa", 0):
            partes.append(f"<b>{r['tardanza_severa']}</b> tard. severas")
        if r.get("tardanza_leve",   0):
            partes.append(f"<b>{r['tardanza_leve']}</b> tard. leves")
        if r.get("almuerzo_largo",  0):
            partes.append(f"<b>{r['almuerzo_largo']}</b> exc. almuerzo")
        if r.get("incompletos",     0):
            partes.append(f"<b>{r['incompletos']}</b> anómalos")
        if r.get("justificadas",    0):
            partes.append(f"<b>{r['justificadas']}</b> justificadas")
        resumen_txt = "  ·  ".join(partes) if partes else "Sin novedades"
        story.append(Paragraph(resumen_txt, st["pequeño"]))
        story.append(Spacer(1, 0.4 * cm))

        datos = analisis_persona[nombre]["dias"]
        if analisis_persona[nombre].get("sin_novedades") or not datos:
            total_d = r.get("total_dias", 0)
            sufijo  = "día analizado" if total_d == 1 else "días analizados"
            story.append(Paragraph(
                f"✓ Sin novedades en el período consultado "
                f"({total_d} {sufijo} con registros).",
                st["ok"]
            ))
            continue

        if f_activos["mostrar_ausencias"]:
            ausentes = [d for d in datos if d.get("estado") == "ausente"]
            story += _seccion_ausencias_persona(st, ausentes)

        if f_activos["mostrar_tardanza_severa"]:
            severas = [d for d in datos if d.get("estado") == "severa"]
            story += _seccion_tardanzas_persona(
                st, "Tardanzas Severas",
                "Llegadas con más de 5 minutos de retraso",
                severas, COLOR_ERROR, f_activos["columna_tiempo_dentro"]
            )

        if f_activos["mostrar_tardanza_leve"]:
            leves = [d for d in datos if d.get("estado") == "leve"
                     and any("Tardanza leve" in o for o in d.get("observaciones", []))]
            story += _seccion_tardanzas_persona(
                st, "Tardanzas Leves",
                "Llegadas con 1 a 5 minutos de retraso",
                leves, COLOR_WARN, f_activos["columna_tiempo_dentro"]
            )

        if f_activos["mostrar_almuerzo"]:
            almuerzos = [d for d in datos if d.get("almuerzo_exceso") is not None
                         and d.get("almuerzo_exceso", 0) > 0]
            story += _seccion_almuerzo_persona(st, almuerzos)

        if f_activos["mostrar_incompletos"]:
            incompletos = [d for d in datos if d.get("estado") == "incompleto"]
            story += _seccion_incompletos_persona(st, incompletos)

        if f_activos["mostrar_salida_anticipada"]:
            salidas_ant = [d for d in datos if any("Salida ant." in o
                           for o in d.get("observaciones", []) if isinstance(o, str))]
            story += _seccion_salidas_anticipadas_persona(st, salidas_ant)

        permisos = [d for d in datos if d.get("permiso_salida")]
        if permisos:
            story += _seccion_permisos_persona(st, permisos)

        if (f_activos["verificar_horas"] or f_activos["mostrar_tiempo_extra"]) and r.get("horas_contrato_tipo"):
            story += _seccion_horas_contrato(st, r)

        if f_activos["mostrar_todos_los_dias"]:
            story += _seccion_cronologico_persona(st, datos, f_activos["columna_tiempo_dentro"])

    if sin_horario:
        story.append(Spacer(1, 1 * cm))
        story.append(Paragraph("PERSONAS EN EL BIOMÉTRICO SIN HORARIO ASIGNADO", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            "Las siguientes personas tienen registros biométricos pero no están en la lista de horarios.",
            st["pequeño"]
        ))
        story.append(Spacer(1, 0.3 * cm))
        filas_sh = [["#", "Nombre"]]
        for i, n in enumerate(sin_horario, 1):
            filas_sh.append([str(i), n])
        t_sh = Table(filas_sh, colWidths=[1.2 * cm, 15.3 * cm])
        t_sh.setStyle(_estilo_tabla_datos(len(filas_sh)))
        story.append(t_sh)

    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    print(f"\n✅ Reporte por persona generado: {ruta_salida}\n")
