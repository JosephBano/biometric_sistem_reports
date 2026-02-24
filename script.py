"""
=============================================================================
GENERADOR DE REPORTES BIOMÉTRICOS
=============================================================================
Procesa archivos .xls/.xlsx de control biométrico y genera reportes PDF
diarios con análisis de tardanzas y excesos de almuerzo.

Uso:
    python reporte_biometrico.py archivo.xls
    python reporte_biometrico.py archivo.xls --excluir "Juan Perez" "Maria Lopez"
    python reporte_biometrico.py archivo.xls --fecha 15  # Solo el día 15
    python reporte_biometrico.py archivo.xls --tardanza1 7:05 --tardanza2 8:05
    python reporte_biometrico.py archivo.xls --almuerzo 60

Requisitos:
    pip install reportlab openpyxl
    (Para .xls antiguo se necesita LibreOffice instalado o xlrd)
=============================================================================
"""

import os
import sys
import csv
import json
import shutil
import argparse
import subprocess
import tempfile
from datetime import datetime, timedelta
from collections import defaultdict

# ── ReportLab ──────────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.platypus import KeepTogether


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    # Horas límite de llegada (HH:MM)
    "tardanza_leve":    "08:00",   # Llegada después → tardanza leve
    "tardanza_severa":  "08:05",   # Llegada después → tardanza severa

    # Minutos máximos de almuerzo antes de reportar exceso
    "max_almuerzo_min": 60,

    # Minutos máximos entre dos marcaciones consecutivas iguales
    # para considerar la segunda como duplicado por error
    "duplicado_min": 10,

    # Personas a excluir del reporte (por nombre exacto o parcial)
    "excluidos": [],
}


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


# ══════════════════════════════════════════════════════════════════════════
# LECTURA DEL ARCHIVO
# ══════════════════════════════════════════════════════════════════════════

def cargar_archivo(ruta: str) -> list[dict]:
    """
    Lee un archivo .xls, .xlsx o .csv y devuelve una lista de registros.
    Cada registro es un dict con: nombre, fecha, hora, tipo_marcacion.
    """
    ext = os.path.splitext(ruta)[1].lower()

    if ext == ".csv":
        return _leer_csv(ruta)
    elif ext in (".xls", ".xlsx"):
        # Intentar con openpyxl primero (sólo funciona con .xlsx)
        if ext == ".xlsx":
            try:
                return _leer_xlsx(ruta)
            except Exception:
                pass
        # Para .xls convertir con LibreOffice
        csv_tmp = _convertir_xls_a_csv(ruta)
        registros = _leer_csv(csv_tmp)
        os.unlink(csv_tmp)
        return registros
    else:
        raise ValueError(f"Formato no soportado: {ext}. Usa .xls, .xlsx o .csv")


def _convertir_xls_a_csv(ruta_xls: str) -> str:
    """Convierte .xls a .csv usando LibreOffice y devuelve la ruta del CSV."""
    directorio_tmp = tempfile.mkdtemp()
    try:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "csv",
             ruta_xls, "--outdir", directorio_tmp],
            check=True, capture_output=True
        )
    except FileNotFoundError:
        raise RuntimeError(
            "LibreOffice no está instalado. Instálalo con:\n"
            "  sudo apt install libreoffice\n"
            "O convierte el archivo a .xlsx manualmente."
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error convirtiendo el archivo: {e.stderr.decode()}")

    nombre_base = os.path.splitext(os.path.basename(ruta_xls))[0]
    csv_path = os.path.join(directorio_tmp, nombre_base + ".csv")
    if not os.path.exists(csv_path):
        archivos = os.listdir(directorio_tmp)
        if archivos:
            csv_path = os.path.join(directorio_tmp, archivos[0])
        else:
            raise RuntimeError("No se generó el CSV desde el XLS.")

    # Copiar a /tmp para que no se pierda al borrar el directorio
    destino = tempfile.mktemp(suffix=".csv")
    shutil.copy(csv_path, destino)
    shutil.rmtree(directorio_tmp, ignore_errors=True)
    return destino


def _leer_csv(ruta: str) -> list[dict]:
    """
    Lee el CSV exportado del sistema biométrico.
    Formato esperado de columnas: ,ID,Nombre,Fecha/Hora,Estado,...,Tipo
    """
    registros = []
    with open(ruta, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for fila in reader:
            # Filtrar filas sin datos útiles
            if len(fila) < 5:
                continue
            # La columna Estado tiene "Entrada" o "Salida"
            # Buscamos filas que tengan una fecha y un tipo conocido
            estado = fila[4].strip() if len(fila) > 4 else ""
            if estado not in ("Entrada", "Salida"):
                continue

            nombre    = fila[2].strip()
            fecha_str = fila[3].strip()   # "05/01/2026 07:01"
            tipo      = estado            # "Entrada" o "Salida"

            if not nombre or not fecha_str:
                continue

            try:
                dt = datetime.strptime(fecha_str, "%d/%m/%Y %H:%M")
            except ValueError:
                try:
                    dt = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue  # Formato desconocido, ignorar fila

            registros.append({
                "nombre": nombre,
                "datetime": dt,
                "fecha": dt.date(),
                "hora": dt.time(),
                "tipo": tipo,
            })

    return registros


def _leer_xlsx(ruta: str) -> list[dict]:
    """Lee un .xlsx directamente con openpyxl."""
    import openpyxl
    wb = openpyxl.load_workbook(ruta, data_only=True)
    ws = wb.active
    registros = []
    for fila in ws.iter_rows(values_only=True):
        if not fila or len(fila) < 5:
            continue
        estado = str(fila[4]).strip() if fila[4] else ""
        if estado not in ("Entrada", "Salida"):
            continue
        nombre    = str(fila[2]).strip() if fila[2] else ""
        fecha_val = fila[3]
        if not nombre or not fecha_val:
            continue
        if isinstance(fecha_val, datetime):
            dt = fecha_val
        else:
            try:
                dt = datetime.strptime(str(fecha_val), "%d/%m/%Y %H:%M")
            except ValueError:
                continue
        registros.append({
            "nombre": nombre,
            "datetime": dt,
            "fecha": dt.date(),
            "hora": dt.time(),
            "tipo": str(estado),
        })
    return registros


# ══════════════════════════════════════════════════════════════════════════
# FILTRADO Y DEDUPLICACIÓN
# ══════════════════════════════════════════════════════════════════════════

def filtrar_excluidos(registros: list[dict], excluidos: list[str]) -> list[dict]:
    """Elimina del análisis a las personas en la lista de excluidos."""
    if not excluidos:
        return registros
    excluidos_lower = [e.lower() for e in excluidos]
    return [
        r for r in registros
        if not any(ex in r["nombre"].lower() for ex in excluidos_lower)
    ]


def deduplicar(registros: list[dict], max_min: int = 10) -> tuple[list[dict], list[dict]]:
    """
    Elimina marcaciones duplicadas por error humano.

    Regla: si una persona tiene dos marcaciones CONSECUTIVAS del mismo tipo
    (Entrada→Entrada o Salida→Salida) separadas por menos de `max_min` minutos,
    la segunda se descarta como error.

    Devuelve (registros_limpios, log_duplicados).
    """
    # Agrupar por persona + fecha
    grupos = defaultdict(list)
    for r in registros:
        grupos[(r["nombre"], r["fecha"])].append(r)

    limpios = []
    log_dup = []

    for clave, marcaciones in grupos.items():
        marcaciones.sort(key=lambda x: x["datetime"])
        resultado = [marcaciones[0]]

        for actual in marcaciones[1:]:
            anterior = resultado[-1]
            delta = (actual["datetime"] - anterior["datetime"]).total_seconds() / 60

            if actual["tipo"] == anterior["tipo"] and delta <= max_min:
                # Es un duplicado — descartar y registrar en el log
                log_dup.append({
                    "nombre":     actual["nombre"],
                    "fecha":      actual["fecha"],
                    "hora_orig":  anterior["hora"].strftime("%H:%M"),
                    "hora_dup":   actual["hora"].strftime("%H:%M"),
                    "tipo":       actual["tipo"],
                    "diferencia": round(delta, 1),
                })
            else:
                resultado.append(actual)

        limpios.extend(resultado)

    limpios.sort(key=lambda x: (x["nombre"], x["datetime"]))
    return limpios, log_dup


# ══════════════════════════════════════════════════════════════════════════
# ANÁLISIS POR DÍA
# ══════════════════════════════════════════════════════════════════════════

def analizar_dia(
    registros_dia: list[dict],
    hora_tardanza_leve: str,
    hora_tardanza_severa: str,
    max_almuerzo_min: int,
) -> dict:
    """
    Analiza los registros de UN día y devuelve un dict con:
      - tardanza_leve:   lista de personas con llegada tardía leve
      - tardanza_severa: lista de personas con llegada tardía severa
      - almuerzo_largo:  lista de personas con almuerzo > max_almuerzo_min
      - registros_incompletos: personas con registros que no cuadran
      - resumen: dict con conteos
    """
    h_leve   = datetime.strptime(hora_tardanza_leve,   "%H:%M").time()
    h_severa = datetime.strptime(hora_tardanza_severa, "%H:%M").time()

    # Agrupar por persona
    por_persona = defaultdict(list)
    for r in registros_dia:
        por_persona[r["nombre"]].append(r)

    tardanza_leve   = []
    tardanza_severa = []
    almuerzo_largo  = []
    incompletos     = []

    for nombre, marcaciones in por_persona.items():
        marcaciones.sort(key=lambda x: x["datetime"])
        tipos = [m["tipo"] for m in marcaciones]

        # ── Análisis de llegada (primer registro) ──────────────────────
        primera = marcaciones[0]
        if primera["tipo"] == "Entrada":
            hora_llegada = primera["hora"]
            if hora_llegada > h_severa:
                tardanza_severa.append({
                    "nombre": nombre,
                    "hora":   hora_llegada.strftime("%H:%M"),
                    "retraso": _minutos_diferencia(h_severa, hora_llegada),
                })
            elif hora_llegada > h_leve:
                tardanza_leve.append({
                    "nombre": nombre,
                    "hora":   hora_llegada.strftime("%H:%M"),
                    "retraso": _minutos_diferencia(h_leve, hora_llegada),
                })

        # ── Análisis de almuerzo ───────────────────────────────────────
        # Buscar el patrón Entrada → Salida → Entrada (almuerzo)
        # El primer "Salida" después de una "Entrada" es la salida a almorzar.
        # El siguiente "Entrada" es el regreso.
        salida_almuerzo = None
        for i, m in enumerate(marcaciones):
            if m["tipo"] == "Salida" and i > 0:
                salida_almuerzo = m
                # Buscar la siguiente Entrada
                for j in range(i + 1, len(marcaciones)):
                    if marcaciones[j]["tipo"] == "Entrada":
                        entrada_almuerzo = marcaciones[j]
                        duracion = (
                            entrada_almuerzo["datetime"] - salida_almuerzo["datetime"]
                        ).total_seconds() / 60
                        if duracion > max_almuerzo_min:
                            almuerzo_largo.append({
                                "nombre":   nombre,
                                "salida":   salida_almuerzo["hora"].strftime("%H:%M"),
                                "regreso":  entrada_almuerzo["hora"].strftime("%H:%M"),
                                "duracion": round(duracion),
                                "exceso":   round(duracion - max_almuerzo_min),
                            })
                        break
                break  # Solo analizar el primer almuerzo del día

        # ── Detectar registros incompletos ────────────────────────────
        n = len(marcaciones)
        if n < 2:
            incompletos.append({
                "nombre":   nombre,
                "registros": n,
                "detalle":  " / ".join(
                    f"{m['tipo']} {m['hora'].strftime('%H:%M')}"
                    for m in marcaciones
                ),
            })
        elif n not in (2, 4):
            # Número inusual de registros
            incompletos.append({
                "nombre":   nombre,
                "registros": n,
                "detalle":  " / ".join(
                    f"{m['tipo']} {m['hora'].strftime('%H:%M')}"
                    for m in marcaciones
                ),
            })

    return {
        "tardanza_leve":         sorted(tardanza_leve,   key=lambda x: x["hora"]),
        "tardanza_severa":       sorted(tardanza_severa, key=lambda x: x["hora"]),
        "almuerzo_largo":        sorted(almuerzo_largo,  key=lambda x: -x["duracion"]),
        "registros_incompletos": sorted(incompletos,     key=lambda x: x["nombre"]),
        "resumen": {
            "total_personas":      len(por_persona),
            "tardanza_leve":       len(tardanza_leve),
            "tardanza_severa":     len(tardanza_severa),
            "almuerzo_largo":      len(almuerzo_largo),
            "incompletos":         len(incompletos),
        },
    }



def analizar_por_persona(registros: list[dict], config: dict) -> dict:
    """
    Analiza los registros de todas las personas, organizados por persona.
    """
    h_leve   = datetime.strptime(config["tardanza_leve"],   "%H:%M").time()
    h_severa = datetime.strptime(config["tardanza_severa"], "%H:%M").time()
    max_almuerzo_min = config.get("max_almuerzo_min", 60)

    # Agrupar por persona y luego por fecha
    por_persona_fecha = defaultdict(lambda: defaultdict(list))
    for r in registros:
        por_persona_fecha[r["nombre"]][r["fecha"]].append(r)

    resultado = {}

    for nombre, por_fecha in por_persona_fecha.items():
        dias_list = []
        resumen = {
            "total_dias": 0,
            "tardanza_leve": 0,
            "tardanza_severa": 0,
            "almuerzo_largo": 0,
            "incompletos": 0
        }

        for fecha, marcaciones in sorted(por_fecha.items()):
            marcaciones.sort(key=lambda x: x["datetime"])
            
            dia_info = {
                "fecha": fecha,
                "llegada": None,
                "salida": None,
                "almuerzo_duracion": None,
                "almuerzo_exceso": None,
                "observaciones": [],
                "estado": "ok"
            }
            
            n = len(marcaciones)
            resumen["total_dias"] += 1

            if n < 2 or n not in (2, 4):
                dia_info["estado"] = "incompleto"
                dia_info["observaciones"].append(f"Registros anómalos ({n})")
                resumen["incompletos"] += 1
                
                # Intentamos sacar llegada de todas formas
                if marcaciones[0]["tipo"] == "Entrada":
                     dia_info["llegada"] = marcaciones[0]["hora"].strftime("%H:%M")
                # Intentamos sacar salida si hay varios
                if len(marcaciones) > 1 and marcaciones[-1]["tipo"] == "Salida":
                     dia_info["salida"] = marcaciones[-1]["hora"].strftime("%H:%M")

            else:
                primera = marcaciones[0]
                ultima = marcaciones[-1]
                if primera["tipo"] == "Entrada":
                    dia_info["llegada"] = primera["hora"].strftime("%H:%M")
                    if primera["hora"] > h_severa:
                        dia_info["estado"] = "severa"
                        dia_info["observaciones"].append("Tardanza severa")
                        resumen["tardanza_severa"] += 1
                    elif primera["hora"] > h_leve:
                        if dia_info["estado"] == "ok":
                            dia_info["estado"] = "leve"
                        dia_info["observaciones"].append("Tardanza leve")
                        resumen["tardanza_leve"] += 1
                
                if ultima["tipo"] == "Salida":
                    dia_info["salida"] = ultima["hora"].strftime("%H:%M")

                # Analizar almuerzo si hay >= 4 marcaciones
                if n >= 4:
                    salida_almuerzo = None
                    for i, m in enumerate(marcaciones):
                        if m["tipo"] == "Salida" and i > 0:
                            salida_almuerzo = m
                            for j in range(i + 1, len(marcaciones)):
                                if marcaciones[j]["tipo"] == "Entrada":
                                    entrada_almuerzo = marcaciones[j]
                                    duracion = (entrada_almuerzo["datetime"] - salida_almuerzo["datetime"]).total_seconds() / 60
                                    dia_info["almuerzo_duracion"] = round(duracion)
                                    if duracion > max_almuerzo_min:
                                        exceso = round(duracion - max_almuerzo_min)
                                        dia_info["almuerzo_exceso"] = exceso
                                        if dia_info["estado"] == "ok":
                                            dia_info["estado"] = "leve"
                                        dia_info["observaciones"].append(f"Exceso almuerzo (+{exceso}m)")
                                        resumen["almuerzo_largo"] += 1
                                    break
                            break

            dias_list.append(dia_info)

        if dias_list:
            resultado[nombre] = {
                "dias": dias_list,
                "resumen": resumen
            }

    return resultado

def _minutos_diferencia(hora_limite, hora_real) -> int:

    """Minutos de diferencia entre hora_limite y hora_real."""
    dt_base  = datetime.combine(datetime.today().date(), hora_limite)
    dt_real  = datetime.combine(datetime.today().date(), hora_real)
    return round((dt_real - dt_base).total_seconds() / 60)


# ══════════════════════════════════════════════════════════════════════════
# GENERACIÓN DEL PDF
# ══════════════════════════════════════════════════════════════════════════

def generar_pdf(
    ruta_salida: str,
    analisis_por_dia: dict,
    log_duplicados: list[dict],
    config: dict,
    nombre_archivo_origen: str,
):
    """Genera el PDF completo con todos los días y el log de duplicados."""

    doc = SimpleDocTemplate(
        ruta_salida,
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Reporte Biométrico",
        author="Sistema de Control de Asistencia",
    )

    styles  = getSampleStyleSheet()
    story   = []

    # ── Estilos personalizados ─────────────────────────────────────────
    st = _crear_estilos(styles)

    # ── Portada ───────────────────────────────────────────────────────
    story += _portada(st, nombre_archivo_origen, config, analisis_por_dia)

    # ── Resumen ejecutivo del mes ──────────────────────────────────────
    story += _resumen_mensual(st, analisis_por_dia, config)

    # ── Página por día ────────────────────────────────────────────────
    dias_ordenados = sorted(analisis_por_dia.keys())
    for i, dia in enumerate(dias_ordenados):
        story.append(PageBreak())
        story += _pagina_dia(st, dia, analisis_por_dia[dia], config)

    # ── Log de duplicados ─────────────────────────────────────────────
    if log_duplicados:
        story.append(PageBreak())
        story += _pagina_duplicados(st, log_duplicados)

    # Construir PDF
    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    print(f"\n✅ Reporte generado: {ruta_salida}\n")


# ── Estilos ────────────────────────────────────────────────────────────────

def generar_pdf_persona(
    ruta_salida: str,
    analisis_persona: dict,
    config: dict,
    nombre_archivo_origen: str,
):
    doc = SimpleDocTemplate(
        ruta_salida,
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Reporte Biométrico por Persona",
        author="Sistema de Control de Asistencia",
    )

    styles  = getSampleStyleSheet()
    story   = []
    st = _crear_estilos(styles)

    # ── Portada ───────────────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("REPORTE DE ASISTENCIA (POR PERSONA)", st["titulo"]))
    story.append(Paragraph("Control Biométrico de Personal", st["subtitulo"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_HEADER))
    story.append(Spacer(1, 1*cm))

    datos_portada = [
        ["Archivo origen:",  os.path.basename(nombre_archivo_origen)],
        ["Generado el:",     datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Personas total:",  str(len(analisis_persona))],
        ["Tardanza leve desde:", config.get("tardanza_leve", "")],
        ["Tardanza severa desde:", config.get("tardanza_severa", "")],
        ["Almuerzo máximo:", f"{config.get('max_almuerzo_min', '')} minutos"],
    ]
    t_portada = Table(datos_portada, colWidths=[6*cm, 10*cm])
    t_portada.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("TEXTCOLOR",   (0,0), (0,-1), COLOR_SUBHEADER),
        ("TEXTCOLOR",   (1,0), (1,-1), COLOR_TEXTO),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",  (0,0),(-1,-1), 6),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white, COLOR_TABLA_ALT]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(t_portada)
    story.append(PageBreak())

    # ── Resumen General ───────────────────────────────────────────────
    story.append(Paragraph("RESUMEN GENERAL", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.5*cm))

    encabezado_resumen = ["Persona", "Días", "Tard. Leves", "Tard. Severas", "Exceso Almuerzo", "Incompletos"]
    filas_resumen = [encabezado_resumen]
    
    for nombre in sorted(analisis_persona.keys()):
        r = analisis_persona[nombre]["resumen"]
        filas_resumen.append([
            nombre,
            str(r["total_dias"]),
            str(r["tardanza_leve"]),
            str(r["tardanza_severa"]),
            str(r["almuerzo_largo"]),
            str(r["incompletos"]),
        ])
    
    t_resumen = Table(filas_resumen, colWidths=[5*cm, 2*cm, 2.5*cm, 2.8*cm, 3.2*cm, 2.5*cm])
    t_resumen.setStyle(_estilo_tabla_datos(len(filas_resumen)))
    story.append(t_resumen)

    # ── Sección por persona ───────────────────────────────────────────
    for nombre in sorted(analisis_persona.keys()):
        story.append(PageBreak())
        story.append(Paragraph(f"👤 {nombre}", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3*cm))
        
        r = analisis_persona[nombre]["resumen"]
        story.append(Paragraph(
            f"<b>{r['total_dias']}</b> días registrados  |  "
            f"<b>{r['tardanza_leve']}</b> tard. leves  |  "
            f"<b>{r['tardanza_severa']}</b> tard. severas  |  "
            f"<b>{r['almuerzo_largo']}</b> exc. almuerzo  |  "
            f"<b>{r['incompletos']}</b> anómalos",
            st["pequeño"]
        ))
        story.append(Spacer(1, 0.4*cm))

        datos = analisis_persona[nombre]["dias"]
        if not datos:
            story.append(Paragraph("Sin registros.", st["normal"]))
            continue

        encabezado_dias = ["Día", "Llegada", "Salida", "Dur. Almuerzo", "Observaciones"]
        filas_dias = [encabezado_dias]
        
        row_colors = []
        for i, d in enumerate(datos, 1):
            fecha_str = d["fecha"].strftime("%d/%m/%Y")
            llegada = d["llegada"] or "—"
            salida = d["salida"] or "—"
            dur_almuerzo = f"{d['almuerzo_duracion']} min" if d["almuerzo_duracion"] else "—"
            obs = ", ".join(d["observaciones"]) if d["observaciones"] else "✓ Ok"
            
            filas_dias.append([fecha_str, llegada, salida, dur_almuerzo, obs])
            
            estado = d["estado"]
            if estado == "ok":
                row_colors.append(COLOR_OK)
            elif estado == "leve":
                row_colors.append(COLOR_WARN)
            elif estado == "severa":
                row_colors.append(COLOR_ERROR)
            elif estado == "incompleto":
                row_colors.append(COLOR_TABLA_ALT)
            else:
                row_colors.append(colors.white)

        t_dias = Table(filas_dias, colWidths=[2.5*cm, 2.2*cm, 2.2*cm, 3*cm, 7.5*cm])
        
        estilos_base = [
            ("BACKGROUND",    (0,0), (-1,0), COLOR_HEADER),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,0), 8.5),
            ("ALIGN",         (0,0), (-1,0), "CENTER"),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE",      (0,1), (-1,-1), 8.5),
            ("TEXTCOLOR",     (0,1), (-1,-1), COLOR_TEXTO),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
            ("RIGHTPADDING",  (0,0), (-1,-1), 6),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ]
        
        for i, color_ in enumerate(row_colors, 1):
            estilos_base.append(("BACKGROUND", (0,i), (-1,i), color_))
            
        t_dias.setStyle(TableStyle(estilos_base))
        story.append(t_dias)

    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    print(f"\n✅ Reporte por persona generado: {ruta_salida}\n")

def _crear_estilos(base):

    return {
        "titulo":      ParagraphStyle("titulo",      fontName="Helvetica-Bold",
                                      fontSize=22, textColor=COLOR_HEADER,
                                      alignment=TA_CENTER, spaceAfter=6),
        "subtitulo":   ParagraphStyle("subtitulo",   fontName="Helvetica",
                                      fontSize=11, textColor=COLOR_MUTED,
                                      alignment=TA_CENTER, spaceAfter=4),
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


# ── Portada ────────────────────────────────────────────────────────────────

def _portada(st, origen, config, analisis):
    story = []
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("REPORTE DE ASISTENCIA", st["titulo"]))
    story.append(Paragraph("Control Biométrico de Personal", st["subtitulo"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_HEADER))
    story.append(Spacer(1, 1*cm))

    # Metadata
    datos = [
        ["Archivo origen:",  os.path.basename(origen)],
        ["Generado el:",     datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Días analizados:", str(len(analisis))],
        ["Tardanza leve desde:", config["tardanza_leve"]],
        ["Tardanza severa desde:", config["tardanza_severa"]],
        ["Tiempo máximo de almuerzo:", f"{config['max_almuerzo_min']} minutos"],
    ]
    if config["excluidos"]:
        datos.append(["Personas excluidas:", ", ".join(config["excluidos"])])

    t = Table(datos, colWidths=[6*cm, 10*cm])
    t.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("TEXTCOLOR",   (0,0), (0,-1), COLOR_SUBHEADER),
        ("TEXTCOLOR",   (1,0), (1,-1), COLOR_TEXTO),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",  (0,0),(-1,-1), 6),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white, COLOR_TABLA_ALT]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(t)
    return story


# ── Resumen mensual ────────────────────────────────────────────────────────

def _resumen_mensual(st, analisis, config):
    story = []
    story.append(PageBreak())
    story.append(Paragraph("RESUMEN DEL MES", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.5*cm))

    # Acumular totales
    tot_leve = tot_severa = tot_almuerzo = tot_incompleto = 0
    for d in analisis.values():
        tot_leve      += d["resumen"]["tardanza_leve"]
        tot_severa    += d["resumen"]["tardanza_severa"]
        tot_almuerzo  += d["resumen"]["almuerzo_largo"]
        tot_incompleto += d["resumen"]["incompletos"]

    kpis = [
        (str(tot_leve),       "Tardanzas leves",     COLOR_WARN),
        (str(tot_severa),     "Tardanzas severas",   COLOR_ERROR),
        (str(tot_almuerzo),   "Excesos de almuerzo", COLOR_WARN),
        (str(tot_incompleto), "Registros anómalos",  COLOR_TABLA_ALT),
    ]

    # KPI boxes en una tabla
    cabeceras = [Paragraph(k[0], st["resumen_num"]) for k in kpis]
    etiquetas = [Paragraph(k[1], st["resumen_lbl"]) for k in kpis]
    t = Table([cabeceras, etiquetas], colWidths=[4.2*cm]*4)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (i,0), (i,1), kpis[i][2]) for i in range(4)
    ] + [
        ("BOX",         (i,0), (i,1), 1, colors.HexColor("#dee2e6")) for i in range(4)
    ] + [
        ("TOPPADDING",  (0,0), (-1,-1), 12),
        ("BOTTOMPADDING",(0,0),(-1,-1), 12),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 1*cm))

    # Tabla resumen por día
    story.append(Paragraph("Detalle por día", st["seccion"]))
    encabezado = ["Día", "Personas", "Tard. Leve", "Tard. Severa",
                  "Exceso Almuerzo", "Reg. Anómalos"]
    filas = [encabezado]
    for dia in sorted(analisis.keys()):
        r = analisis[dia]["resumen"]
        filas.append([
            dia.strftime("%d/%m/%Y (%a)").replace("Mon","Lun").replace("Tue","Mar")
              .replace("Wed","Mié").replace("Thu","Jue").replace("Fri","Vie")
              .replace("Sat","Sáb").replace("Sun","Dom"),
            str(r["total_personas"]),
            str(r["tardanza_leve"])   or "—",
            str(r["tardanza_severa"]) or "—",
            str(r["almuerzo_largo"])  or "—",
            str(r["incompletos"])     or "—",
        ])

    t2 = Table(filas, colWidths=[3.5*cm, 2.2*cm, 2.5*cm, 2.8*cm, 3.5*cm, 3*cm])
    t2.setStyle(_estilo_tabla_datos(len(filas)))
    story.append(t2)
    return story


# ── Página de un día ───────────────────────────────────────────────────────

def _pagina_dia(st, dia, datos, config):
    story = []

    # Título del día
    nombre_dia = dia.strftime("%A %d de %B de %Y")
    nombre_dia = (nombre_dia
                  .replace("Monday","Lunes").replace("Tuesday","Martes")
                  .replace("Wednesday","Miércoles").replace("Thursday","Jueves")
                  .replace("Friday","Viernes").replace("Saturday","Sábado")
                  .replace("Sunday","Domingo")
                  .replace("January","Enero").replace("February","Febrero")
                  .replace("March","Marzo").replace("April","Abril")
                  .replace("May","Mayo").replace("June","Junio")
                  .replace("July","Julio").replace("August","Agosto")
                  .replace("September","Septiembre").replace("October","Octubre")
                  .replace("November","Noviembre").replace("December","Diciembre"))

    story.append(Paragraph(f"📅  {nombre_dia.upper()}", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.3*cm))

    r = datos["resumen"]
    story.append(Paragraph(
        f"<b>{r['total_personas']}</b> personas registradas  |  "
        f"<b>{r['tardanza_leve']}</b> tard. leves  |  "
        f"<b>{r['tardanza_severa']}</b> tard. severas  |  "
        f"<b>{r['almuerzo_largo']}</b> excesos almuerzo",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.4*cm))

    # ── Tardanza severa ────────────────────────────────────────────────
    story += _seccion_tardanza(
        st, "Tardanza Severa",
        f"Llegadas después de las {config['tardanza_severa']}",
        datos["tardanza_severa"],
        COLOR_ERROR, "🔴"
    )

    # ── Tardanza leve ──────────────────────────────────────────────────
    story += _seccion_tardanza(
        st, "Tardanza Leve",
        f"Llegadas entre {config['tardanza_leve']} y {config['tardanza_severa']}",
        datos["tardanza_leve"],
        COLOR_WARN, "🟡"
    )

    # ── Exceso de almuerzo ─────────────────────────────────────────────
    story += _seccion_almuerzo(st, datos["almuerzo_largo"], config)

    # ── Registros incompletos ──────────────────────────────────────────
    story += _seccion_incompletos(st, datos["registros_incompletos"])

    return story


def _seccion_tardanza(st, titulo, descripcion, lista, color_bg, icono):
    story = []
    story.append(Paragraph(f"{icono}  {titulo}", st["seccion"]))
    story.append(Paragraph(descripcion, st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))

    if not lista:
        story.append(Paragraph("✓ Sin novedades", st["ok"]))
    else:
        encabezado = ["#", "Nombre", "Hora de llegada", "Retraso (min)"]
        filas = [encabezado]
        for i, p in enumerate(lista, 1):
            filas.append([str(i), p["nombre"], p["hora"], f"+{p['retraso']} min"])
        t = Table(filas, colWidths=[0.8*cm, 9*cm, 3.5*cm, 3.2*cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=color_bg))
        story.append(t)

    story.append(Spacer(1, 0.4*cm))
    return story


def _seccion_almuerzo(st, lista, config):
    story = []
    story.append(Paragraph("🍽️  Exceso de Almuerzo", st["seccion"]))
    story.append(Paragraph(
        f"Personas cuyo almuerzo superó los {config['max_almuerzo_min']} minutos",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.2*cm))

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
        t = Table(filas, colWidths=[0.8*cm, 6.5*cm, 2*cm, 2*cm, 2.5*cm, 2.7*cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_WARN))
        story.append(t)

    story.append(Spacer(1, 0.4*cm))
    return story


def _seccion_incompletos(st, lista):
    story = []
    if not lista:
        return story
    story.append(Paragraph("⚠️  Registros Anómalos / Incompletos", st["seccion"]))
    story.append(Paragraph(
        "Personas con número inusual de marcaciones (esperado: 2 o 4 por día)",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.2*cm))

    encabezado = ["Nombre", "# Registros", "Detalle"]
    filas = [encabezado]
    for p in lista:
        filas.append([p["nombre"], str(p["registros"]), p["detalle"]])
    t = Table(filas, colWidths=[5.5*cm, 2.5*cm, 8.5*cm])
    t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_TABLA_ALT))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))
    return story


# ── Log de duplicados ──────────────────────────────────────────────────────

def _pagina_duplicados(st, log):
    story = []
    story.append(Paragraph("🔄  LOG DE MARCACIONES DUPLICADAS CORREGIDAS", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Las siguientes marcaciones fueron detectadas como duplicados por error humano "
        "y excluidas del análisis. Se conservó la primera marcación de cada par.",
        st["normal"]
    ))
    story.append(Spacer(1, 0.4*cm))

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
    t = Table(filas, colWidths=[5*cm, 2.5*cm, 2*cm, 2.8*cm, 3*cm, 2.2*cm])
    t.setStyle(_estilo_tabla_datos(len(filas)))
    story.append(t)
    return story


# ── Estilos de tabla ───────────────────────────────────────────────────────

def _estilo_tabla_datos(n_filas, color_fila=None):
    bg = color_fila or COLOR_TABLA_ALT
    estilos = [
        # Encabezado
        ("BACKGROUND",    (0,0), (-1,0), COLOR_HEADER),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 8.5),
        ("ALIGN",         (0,0), (-1,0), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        # Cuerpo
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 8.5),
        ("TEXTCOLOR",     (0,1), (-1,-1), COLOR_TEXTO),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, bg]),
    ]
    return TableStyle(estilos)


# ── Pie de página ──────────────────────────────────────────────────────────

def _pie_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(COLOR_MUTED)
    canvas.drawString(1.8*cm, 1.2*cm,
                      f"Reporte Biométrico — Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas.drawRightString(
        A4[0] - 1.8*cm, 1.2*cm,
        f"Página {doc.page}"
    )
    canvas.restoreState()


# ══════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generador de reportes biométricos en PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
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
    parser.add_argument("--tardanza1", default=DEFAULT_CONFIG["tardanza_leve"],
        metavar="HH:MM",
        help=f"Hora de tardanza leve (default: {DEFAULT_CONFIG['tardanza_leve']})")
    parser.add_argument("--tardanza2", default=DEFAULT_CONFIG["tardanza_severa"],
        metavar="HH:MM",
        help=f"Hora de tardanza severa (default: {DEFAULT_CONFIG['tardanza_severa']})")
    parser.add_argument("--almuerzo", type=int,
        default=DEFAULT_CONFIG["max_almuerzo_min"],
        metavar="MINUTOS",
        help=f"Minutos máximos de almuerzo (default: {DEFAULT_CONFIG['max_almuerzo_min']})")
    parser.add_argument("--duplicado-min", type=int,
        default=DEFAULT_CONFIG["duplicado_min"],
        metavar="MINUTOS",
        help=f"Minutos máximos para considerar marcación como duplicado (default: {DEFAULT_CONFIG['duplicado_min']})")
    parser.add_argument("--fecha", type=int, metavar="DIA",
        help="Analizar solo este día del mes (ej: --fecha 15)")
    parser.add_argument("--salida", metavar="ARCHIVO.pdf",
        help="Nombre del PDF de salida (default: reporte_<origen>.pdf)")

    args = parser.parse_args()

    # Validar archivo
    if not os.path.exists(args.archivo):
        print(f"❌ Error: No se encontró el archivo '{args.archivo}'")
        sys.exit(1)

    config = {
        "tardanza_leve":    args.tardanza1,
        "tardanza_severa":  args.tardanza2,
        "max_almuerzo_min": args.almuerzo,
        "duplicado_min":    args.duplicado_min,
        "excluidos":        args.excluir,
    }

    # ── Cargar datos ───────────────────────────────────────────────────
    print(f"\n📂 Cargando archivo: {args.archivo}")
    try:
        registros = cargar_archivo(args.archivo)
    except Exception as e:
        print(f"❌ Error al leer el archivo: {e}")
        sys.exit(1)

    print(f"   ✓ {len(registros)} registros encontrados")

    # ── Excluir personas ───────────────────────────────────────────────
    if config["excluidos"]:
        antes = len(set(r["nombre"] for r in registros))
        registros = filtrar_excluidos(registros, config["excluidos"])
        despues = len(set(r["nombre"] for r in registros))
        print(f"   ✓ {antes - despues} persona(s) excluida(s)")

    # ── Deduplicar ─────────────────────────────────────────────────────
    print(f"\n🔄 Detectando marcaciones duplicadas (umbral: {config['duplicado_min']} min)...")
    registros, log_dup = deduplicar(registros, config["duplicado_min"])
    print(f"   ✓ {len(log_dup)} duplicado(s) eliminado(s)")

    if args.modo == "persona":
        print(f"\n📊 Analizando registros por persona...")
        analisis_persona = analizar_por_persona(registros, config)
        
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
        # ── Agrupar por fecha ──────────────────────────────────────────────
        por_fecha = defaultdict(list)
        for r in registros:
            por_fecha[r["fecha"]].append(r)

        # Filtrar por día si se especificó
        if args.fecha:
            por_fecha = {
                fecha: regs for fecha, regs in por_fecha.items()
                if fecha.day == args.fecha
            }
            if not por_fecha:
                print(f"❌ No se encontraron registros para el día {args.fecha}")
                sys.exit(1)

        # ── Analizar ───────────────────────────────────────────────────────
        print(f"\n📊 Analizando {len(por_fecha)} día(s)...")
        analisis_por_dia = {}
        for fecha, regs in sorted(por_fecha.items()):
            analisis_por_dia[fecha] = analizar_dia(
                regs,
                config["tardanza_leve"],
                config["tardanza_severa"],
                config["max_almuerzo_min"],
            )
            r = analisis_por_dia[fecha]["resumen"]
            print(f"   {fecha.strftime('%d/%m/%Y')}  →  "
                  f"{r['total_personas']} personas, "
                  f"{r['tardanza_leve']} tard.leves, "
                  f"{r['tardanza_severa']} tard.severas, "
                  f"{r['almuerzo_largo']} excesos almuerzo")

        # ── Generar PDF ────────────────────────────────────────────────────
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

    # ── Guardar config usada (opcional) ───────────────────────────────
    config_path = ruta_pdf.replace(".pdf", "_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"⚙️  Configuración guardada en: {config_path}")


if __name__ == "__main__":
    main()