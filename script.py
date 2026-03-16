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
import argparse
from datetime import datetime, timedelta, date
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
    # Minutos máximos entre dos marcaciones consecutivas iguales
    # para considerar la segunda como duplicado por error
    "duplicado_min": 0.5,

    # Personas a excluir del reporte (por nombre exacto o parcial)
    "excluidos": [],
}

# Tolerancia fija de entrada: 0–5 min → tardanza leve, >5 min → tardanza severa
MARGEN_LEVE_MIN = 5


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
    Lee un archivo .xlsx o .csv y devuelve una lista de registros.
    Cada registro es un dict con: nombre, fecha, hora, tipo_marcacion.
    """
    ext = os.path.splitext(ruta)[1].lower()

    if ext == ".csv":
        return _leer_csv(ruta)
    elif ext == ".xlsx":
        return _leer_xlsx(ruta)
    else:
        raise ValueError(f"Formato no soportado: {ext}. Usa .xlsx o .csv")


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


def deduplicar(registros: list[dict], max_min: float = 0.5) -> tuple[list[dict], list[dict]]:
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


def _calcular_tiempo_neto_min(marcaciones: list) -> int:
    """
    Suma los minutos netos de presencia sumando cada par Entrada→Salida.
    Ignora registros huérfanos o en orden incorrecto.
    """
    total = 0
    i = 0
    while i < len(marcaciones):
        if marcaciones[i]["type" if "type" in marcaciones[i] else "tipo"] == "Entrada":
            for j in range(i + 1, len(marcaciones)):
                if marcaciones[j]["type" if "type" in marcaciones[j] else "tipo"] == "Salida":
                    delta = int(
                        (marcaciones[j]["datetime"] - marcaciones[i]["datetime"])
                        .total_seconds() / 60
                    )
                    if delta > 0:
                        total += delta
                    i = j
                    break
        i += 1
    return total


# ══════════════════════════════════════════════════════════════════════════
# ANÁLISIS POR DÍA
# ══════════════════════════════════════════════════════════════════════════

def analizar_dia(
    registros_dia: list[dict],
    horarios: dict,
    justificaciones: dict = None,
    feriados: set = None,
    permitir_sin_horario: bool = False,
) -> dict:
    """
    Analiza los registros de UN día y devuelve un dict con:
      - tardanza_leve:   lista de personas con llegada tardía leve (1–5 min)
      - tardanza_severa: lista de personas con llegada tardía severa (>5 min)
      - almuerzo_largo:  lista de personas con almuerzo > su límite individual
      - registros_incompletos: personas con registros que no cuadran
      - resumen: dict con conteos

    Requiere `horarios` (dict con "by_id" y "by_nombre"). Las personas sin
    horario en el documento se omiten del análisis.
    justificaciones: dict (id_usuario, fecha_iso, tipo) → info.
    feriados: set de fechas (date) que no generan alertas.
    """
    if justificaciones is None:
        justificaciones = {}
    if feriados is None:
        feriados = set()
    # Agrupar por persona
    por_persona = defaultdict(list)
    for r in registros_dia:
        por_persona[r["nombre"]].append(r)

    tardanza_leve_lst   = []
    tardanza_severa_lst = []
    salida_anticipada_leve_lst = []
    salida_anticipada_severa_lst = []
    almuerzo_largo      = []
    incompletos         = []

    for nombre, marcaciones in por_persona.items():
        marcaciones.sort(key=lambda x: x["datetime"])

        # ── Obtener horario individual ─────────────────────────────────
        id_usuario      = marcaciones[0].get("id_usuario")
        fecha_dia       = marcaciones[0]["fecha"]
        horario_persona = _buscar_horario(nombre, id_usuario, horarios)

        if horario_persona is None:
            if permitir_sin_horario:
                # Si no tiene horario, lo registramos como "incompleto" pero indicando que no tiene horario
                incompletos.append({
                    "nombre":    nombre,
                    "registros": len(marcaciones),
                    "detalle":   "SIN HORARIO ASIGNADO / " + " / ".join(
                        f"{m['tipo']} {m['hora'].strftime('%H:%M')}"
                        for m in marcaciones
                    ),
                })
            continue  # omitir del análisis regular

        # Feriado → omitir del análisis
        if fecha_dia in feriados:
            continue

        def _justificado_dia(tipo_obs: str) -> bool:
            return (id_usuario, fecha_dia.isoformat(), tipo_obs) in justificaciones

        info = _get_info_dia(horario_persona, fecha_dia)
        if not info["trabaja"]:
            # Marcaciones en día libre — registrar como incompleto
            incompletos.append({
                "nombre":    nombre,
                "registros": len(marcaciones),
                "detalle":   "Día libre según horario / " + " / ".join(
                    f"{m['tipo']} {m['hora'].strftime('%H:%M')}"
                    for m in marcaciones
                ),
            })
            continue
        hora_prog        = info["hora_entrada"]
        max_almuerzo_per = info["almuerzo_min"]

        # ── Análisis de llegada (primer registro) ──────────────────────
        primera = marcaciones[0]
        if primera["tipo"] == "Entrada" and not _justificado_dia("tardanza"):
            hora_llegada = primera["hora"]

            # Lógica relativa al horario individual
            h_prog  = datetime.strptime(hora_prog, "%H:%M").time()
            retraso = _minutos_diferencia(h_prog, hora_llegada)
            if retraso > MARGEN_LEVE_MIN:
                tardanza_severa_lst.append({
                    "nombre":  nombre,
                    "hora":    hora_llegada.strftime("%H:%M"),
                    "retraso": retraso,
                    "programado": hora_prog,
                })
            elif retraso > 0:
                tardanza_leve_lst.append({
                    "nombre":  nombre,
                    "hora":    hora_llegada.strftime("%H:%M"),
                    "retraso": retraso,
                    "programado": hora_prog,
                })

        # ── Análisis de almuerzo ───────────────────────────────────────
        if max_almuerzo_per > 0 and not _justificado_dia("almuerzo"):
            for i, m in enumerate(marcaciones):
                if m["tipo"] == "Salida" and i > 0:
                    for j in range(i + 1, len(marcaciones)):
                        if marcaciones[j]["tipo"] == "Entrada":
                            entrada_alm = marcaciones[j]
                            duracion = int((
                                entrada_alm["datetime"] - m["datetime"]
                            ).total_seconds() / 60)
                            if duracion > max_almuerzo_per:
                                almuerzo_largo.append({
                                    "nombre":   nombre,
                                    "salida":   m["hora"].strftime("%H:%M"),
                                    "regreso":  entrada_alm["hora"].strftime("%H:%M"),
                                    "duracion": round(duracion),
                                    "exceso":   round(duracion - max_almuerzo_per),
                                })
                            break
                    break

        # ── Detectar registros incompletos ────────────────────────────
        n = len(marcaciones)
        _tipos_seq   = [m["tipo"] for m in marcaciones]
        _seq_valida  = _tipos_seq in (
            ["Entrada", "Salida"],
            ["Entrada", "Salida", "Entrada", "Salida"],
        )
        if not _seq_valida:
            if not _justificado_dia("incompleto"):
                incompletos.append({
                    "nombre":    nombre,
                    "registros": n,
                    "detalle":   " / ".join(
                        f"{m['tipo']} {m['hora'].strftime('%H:%M')}"
                        for m in marcaciones
                    ),
                })

        # ── Análisis de salida anticipada ───────────
        hora_salida_prog = info.get("hora_salida")
        if hora_salida_prog and len(marcaciones) >= 2 and not _justificado_dia("salida_anticipada"):
            ultima_salida = None
            for m in reversed(marcaciones):
                if m["tipo"] == "Salida":
                    ultima_salida = m["hora"]
                    break
            if ultima_salida:
                h_salida_t = datetime.strptime(hora_salida_prog, "%H:%M").time()
                salida_diff = -_minutos_diferencia(h_salida_t, ultima_salida)
                if salida_diff > MARGEN_LEVE_MIN:
                    salida_anticipada_severa_lst.append({
                        "nombre": nombre,
                        "hora":   ultima_salida.strftime("%H:%M"),
                        "retraso": salida_diff,
                        "programado": hora_salida_prog,
                    })
                elif salida_diff > 0:
                    salida_anticipada_leve_lst.append({
                        "nombre": nombre,
                        "hora":   ultima_salida.strftime("%H:%M"),
                        "retraso": salida_diff,
                        "programado": hora_salida_prog,
                    })

    return {
        "tardanza_leve":         sorted(tardanza_leve_lst,   key=lambda x: x["hora"]),
        "tardanza_severa":       sorted(tardanza_severa_lst, key=lambda x: x["hora"]),
        "salida_anticipada_leve":sorted(salida_anticipada_leve_lst, key=lambda x: x["hora"]),
        "salida_anticipada_severa": sorted(salida_anticipada_severa_lst, key=lambda x: x["hora"]),
        "almuerzo_largo":        sorted(almuerzo_largo,      key=lambda x: -x["duracion"]),
        "registros_incompletos": sorted(incompletos,         key=lambda x: x["nombre"]),
        "resumen": {
            "total_personas":  len(por_persona),
            "tardanza_leve":   len(tardanza_leve_lst),
            "tardanza_severa": len(tardanza_severa_lst),
            "salida_anticipada_leve": len(salida_anticipada_leve_lst),
            "salida_anticipada_severa": len(salida_anticipada_severa_lst),
            "almuerzo_largo":  len(almuerzo_largo),
            "incompletos":     len(incompletos),
        },
    }



def analizar_por_persona(
    registros: list[dict],
    config: dict,
    horarios: dict = None,
    fecha_inicio=None,
    fecha_fin=None,
    justificaciones: dict = None,
    feriados: set = None,
    breaks_categorizados: dict = None,
    mostrar_todos: bool = False,
    permitir_sin_horario: bool = False,
    verificar_horas: bool = False,
    mostrar_tiempo_extra: bool = False,
) -> dict:
    """
    Analiza los registros de todas las personas, organizados por persona.

    Requiere `horarios` (dict con "by_id" y "by_nombre"). Las personas sin
    horario se omiten del resultado.

    Parámetros opcionales:
      fecha_inicio / fecha_fin : detectar ausencias totales en días sin registros.
      justificaciones          : dict (id_usuario, fecha_iso, tipo) → info.
      feriados                 : set de objetos date que no generan alertas.
      mostrar_todos            : si True, incluye días sin novedad en dias_list.
    """
    if justificaciones is None:
        justificaciones = {}
    if feriados is None:
        feriados = set()
    if breaks_categorizados is None:
        breaks_categorizados = {}

    # Agrupar por persona y luego por fecha
    por_persona_fecha = defaultdict(lambda: defaultdict(list))
    for r in registros:
        por_persona_fecha[r["nombre"]][r["fecha"]].append(r)

    resultado = {}

    for nombre, por_fecha in por_persona_fecha.items():
        # Obtener id_usuario de cualquier registro disponible
        id_usuario = None
        for _, marcaciones_tmp in por_fecha.items():
            if marcaciones_tmp and "id_usuario" in marcaciones_tmp[0]:
                id_usuario = marcaciones_tmp[0]["id_usuario"]
                break

        # Buscar horario del empleado — omitir si no tiene
        horario_persona = _buscar_horario(nombre, id_usuario, horarios)
        if horario_persona is None:
            if permitir_sin_horario:
                # Si se permite sin horario, procesamos lo básico: solo listar marcaciones
                # (sin alertas de tardanza/ausencia que dependen de horario)
                dias_list = []
                for f, ms in sorted(por_fecha.items()):
                    ms.sort(key=lambda x: x["datetime"])
                    dias_list.append({
                        "fecha":             f,
                        "llegada":           ms[0]["hora"].strftime("%H:%M") if ms[0]["tipo"] == "Entrada" else None,
                        "salida":            ms[-1]["hora"].strftime("%H:%M") if ms[-1]["tipo"] == "Salida" else None,
                        "hora_programada":   None,
                        "almuerzo_duracion": None,
                        "detalle_registros": " / ".join(f"{mx['tipo']} {mx['hora'].strftime('%H:%M')}" for mx in ms),
                        "observaciones":     ["Sin horario asignado"],
                        "estado":            "incompleto",  # Marcamos como incompleto por defecto al no haber horario
                    })
                resultado[nombre] = {
                    "dias": dias_list,
                    "resumen": {"total_dias": len(dias_list), "incompletos": len(dias_list)},
                    "sin_novedades": False
                }
            continue

        dias_list = []
        resumen = {
            "total_dias":      0,
            "tardanza_leve":   0,
            "tardanza_severa": 0,
            "almuerzo_largo":  0,
            "incompletos":     0,
            "ausencias":       0,
            "justificadas":    0,
            "salida_anticipada_leve": 0,
            "salida_anticipada_severa": 0,
            "permiso_retorno_tardio":      0,
            "permiso_retorno_tardio_leve": 0,
            "permiso_sin_retorno":         0,
        }

        def _get_justificado(fecha_eval: date, tipo_obs: str) -> dict:
            if not id_usuario:
                return None
            j = justificaciones.get((str(id_usuario), fecha_eval.isoformat(), tipo_obs))
            if j and j.get("recuperable") == 1:
                # Modificar el motivo para incluir la nota
                nota = f" [RECUPERABLE – se compensará {j.get('fecha_recuperacion')} {j.get('hora_recuperacion')}]"
                j = dict(j)  # copiar para no mutar el dict global
                j["motivo"] = (j.get("motivo") or "") + nota
            return j

        for fecha, marcaciones in sorted(por_fecha.items()):
            marcaciones.sort(key=lambda x: x["datetime"])

            # ── Feriado ────────────────────────────────────────────────
            if fecha in feriados:
                if mostrar_todos:
                    dias_list.append({
                        "fecha": fecha, "llegada": None, "salida": None,
                        "hora_programada": None, "almuerzo_duracion": None,
                        "almuerzo_salida": None, "almuerzo_regreso": None,
                        "almuerzo_exceso": None, "tiempo_dentro": None,
                        "n_registros": len(marcaciones),
                        "detalle_registros": "",
                        "observaciones": ["Feriado"], "estado": "feriado",
                    })
                continue

            dia_info = {
                "fecha":             fecha,
                "llegada":           None,
                "salida":            None,
                "hora_programada":   None,
                "almuerzo_duracion": None,
                "almuerzo_salida":   None,
                "almuerzo_regreso":  None,
                "almuerzo_exceso":   None,
                "tiempo_dentro":     None,
                "tiempo_neto_min":   0,
                "permiso_salida":    None,
                "permiso_retorno":   None,
                "permiso_duracion":  None,
                "n_registros":       len(marcaciones),
                "detalle_registros": "",
                "observaciones":     [],
                "estado":            "ok",
            }

            # ── Resolver horario para este día ─────────────────────────
            info = _get_info_dia(horario_persona, fecha)
            dia_info["hora_programada"] = info["hora_entrada"]

            if not info["trabaja"]:
                dia_info["estado"] = "libre"
                dia_info["observaciones"].append("Día libre según horario")
                if marcaciones[0]["tipo"] == "Entrada":
                    dia_info["llegada"] = marcaciones[0]["hora"].strftime("%H:%M")
                dias_list.append(dia_info)
                continue

            hora_prog        = info["hora_entrada"]
            max_almuerzo_per = info["almuerzo_min"]

            n = len(marcaciones)
            resumen["total_dias"] += 1

            dia_info["detalle_registros"] = " / ".join(
                f"{m['tipo']} {m['hora'].strftime('%H:%M')}" for m in marcaciones
            )
            dia_info["n_registros"] = n

            _tipos_seq  = [m["tipo"] for m in marcaciones]
            _seq_valida = _tipos_seq in (
                ["Entrada", "Salida"],
                ["Entrada", "Salida", "Entrada", "Salida"],
            )
            if not _seq_valida:
                just_inc = _get_justificado(fecha, "incompleto")
                dia_info["estado"] = "incompleto"
                if not just_inc:
                    dia_info["observaciones"].append(f"Registros anómalos ({n})")
                    resumen["incompletos"] += 1
                else:
                    dia_info["justificado"] = True
                    dia_info["observaciones"].append(f"ANOMALÍA JUSTIFICADA: {just_inc.get('motivo','(Sin motivo)')}")

                # --- Lógica de Multi-breaks / Pendientes (Parte II) ---
                if n > 4:
                    # Si hay más de 4 registros, es un día con múltiples breaks
                    # Revisamos si ya están categorizados
                    breaks_dia = breaks_categorizados.get(id_usuario, {}).get(fecha, [])
                    if not breaks_dia:
                        dia_info["estado"] = "pendiente_revision"
                        dia_info["observaciones"].append(f"Múltiples registros ({n}). Pendiente categorizar breaks.")
                        resumen["incompletos"] += 1 # Lo contamos como incompleto/novedad por ahora
                    else:
                        dia_info["observaciones"].append(f"Día con {len(breaks_dia)} breaks categorizados.")
                        # Aquí se podría añadir lógica más fina si se desea

                if marcaciones[0]["tipo"] == "Entrada":
                    dia_info["llegada"] = marcaciones[0]["hora"].strftime("%H:%M")
                if len(marcaciones) > 1 and marcaciones[-1]["tipo"] == "Salida":
                    dia_info["salida"] = marcaciones[-1]["hora"].strftime("%H:%M")
                
                dia_info["tiempo_neto_min"] = _calcular_tiempo_neto_min(marcaciones)

            else:
                primera = marcaciones[0]
                ultima  = marcaciones[-1]

                if primera["tipo"] == "Entrada":
                    dia_info["llegada"] = primera["hora"].strftime("%H:%M")

                    # ── Tiempo dentro de la institución ────────────────
                    if ultima["tipo"] == "Salida":
                        td_min = int((ultima["datetime"] - primera["datetime"]).total_seconds() / 60)
                        h_td, m_td = divmod(td_min, 60)
                        dia_info["tiempo_dentro"] = f"{h_td}h {m_td:02d}m"

                    # ── Tardanza relativa al horario individual ────────
                    just_tar = _get_justificado(fecha, "tardanza")
                    if not just_tar:
                        h_prog_t = datetime.strptime(hora_prog, "%H:%M").time()
                        retraso  = _minutos_diferencia(h_prog_t, primera["hora"])
                        if retraso > MARGEN_LEVE_MIN:
                            dia_info["estado"] = "severa"
                            dia_info["observaciones"].append(
                                f"Tardanza severa (+{retraso}m sobre {hora_prog})"
                            )
                            resumen["tardanza_severa"] += 1
                        elif retraso > 0:
                            if dia_info["estado"] == "ok":
                                dia_info["estado"] = "leve"
                            dia_info["observaciones"].append(
                                f"Tardanza leve (+{retraso}m sobre {hora_prog})"
                            )
                            resumen["tardanza_leve"] += 1
                    else:
                        hora_permitida = just_tar.get("hora_permitida")
                        if hora_permitida:
                            h_permitida_t = datetime.strptime(hora_permitida, "%H:%M").time()
                            retraso = _minutos_diferencia(h_permitida_t, primera["hora"])
                            if retraso > MARGEN_LEVE_MIN:
                                dia_info["estado"] = "severa"
                                dia_info["observaciones"].append(
                                    f"Tardanza NO JUSTIF. (+{retraso}m, auth. hasta {hora_permitida})"
                                )
                                resumen["tardanza_severa"] += 1
                            elif retraso > 0:
                                if dia_info["estado"] == "ok":
                                    dia_info["estado"] = "leve"
                                dia_info["observaciones"].append(
                                    f"Tardanza leve NO JUSTIF. (+{retraso}m, auth. hasta {hora_permitida})"
                                )
                                resumen["tardanza_leve"] += 1
                            else:
                                dia_info["justificado"] = True
                                resumen["justificadas"] += 1
                                if dia_info["estado"] == "ok":
                                    dia_info["estado"] = "leve"  # marcamos leve justificada
                                dia_info["observaciones"].append(f"Llegada autorizada hasta {hora_permitida}")
                        else:
                            dia_info["justificado"] = True
                            resumen["justificadas"] += 1
                            if dia_info["estado"] == "ok":
                               dia_info["estado"] = "leve"
                            dia_info["observaciones"].append(f"Tardanza JUSTIFICADA: {just_tar.get('motivo','(Sin motivo)')}")

                if ultima["tipo"] == "Salida":
                    dia_info["salida"] = ultima["hora"].strftime("%H:%M")

                # ── Análisis de almuerzo / Permiso ───────────────────────────────
                just_alm = _get_justificado(fecha, "almuerzo")
                just_per = _get_justificado(fecha, "permiso")
                
                if just_per and just_per.get("estado") == "aprobada":
                    # El permiso reemplaza el análisis de almuerzo (Parte II)
                    found_per = False
                    for i, m in enumerate(marcaciones):
                        if m["tipo"] == "Salida" and i > 0:
                            for j in range(i + 1, len(marcaciones)):
                                if marcaciones[j]["tipo"] == "Entrada":
                                    entrada_per = marcaciones[j]
                                    salida_real = m["hora"]
                                    retorno_real = entrada_per["hora"]
                                    duracion = int((entrada_per["datetime"] - m["datetime"]).total_seconds() / 60)
                                    
                                    dia_info["permiso_salida"]   = salida_real.strftime("%H:%M")
                                    dia_info["permiso_retorno"]  = retorno_real.strftime("%H:%M")
                                    dia_info["permiso_duracion"] = duracion

                                    # Si el permiso incluye almuerzo, calcular neto
                                    if just_per.get("incluye_almuerzo"):
                                        neto = max(0, duracion - max_almuerzo_per)
                                        dia_info["permiso_neto_min"]   = neto
                                        dia_info["permiso_alm_min"]    = max_almuerzo_per
                                    else:
                                        dia_info["permiso_neto_min"]   = duracion
                                        dia_info["permiso_alm_min"]    = 0

                                    h_auth_desde = just_per.get("hora_permitida")
                                    h_auth_hasta = just_per.get("hora_retorno_permiso")
                                    
                                    if h_auth_desde:
                                        h_auth_desde_t = datetime.strptime(h_auth_desde, "%H:%M").time()
                                        if salida_real < h_auth_desde_t:
                                            dia_info["observaciones"].append(f"Salió a permiso anticipado ({salida_real.strftime('%H:%M')}, auth. desde {h_auth_desde})")
                                    
                                    if h_auth_hasta:
                                        h_auth_hasta_t = datetime.strptime(h_auth_hasta, "%H:%M").time()
                                        retardo_retorno = _minutos_diferencia(h_auth_hasta_t, retorno_real)
                                        
                                        if retardo_retorno > MARGEN_LEVE_MIN:
                                            dia_info["estado"] = "severa"
                                            dia_info["observaciones"].append(f"Retorno tardío del permiso (+{retardo_retorno}m sobre límite {h_auth_hasta})")
                                            resumen["permiso_retorno_tardio"] += 1
                                        elif retardo_retorno > 0:
                                            if dia_info["estado"] == "ok":
                                                dia_info["estado"] = "leve"
                                            dia_info["observaciones"].append(f"Retorno tardío leve del permiso (+{retardo_retorno}m sobre límite {h_auth_hasta})")
                                            resumen["permiso_retorno_tardio_leve"] += 1
                                        else:
                                            dia_info["justificado"] = True
                                            alm_txt = ""
                                            if just_per.get("incluye_almuerzo") and max_almuerzo_per:
                                                neto_h, neto_m = divmod(dia_info.get("permiso_neto_min", duracion), 60)
                                                alm_txt = f" (incl. {max_almuerzo_per}min alm., neto {neto_h}h {neto_m:02d}m)"
                                            dia_info["observaciones"].append(f"Permiso OK (retorno {retorno_real.strftime('%H:%M')}, límite {h_auth_hasta}){alm_txt}")
                                    
                                    found_per = True
                                    break
                            if found_per: break
                    
                    if not found_per:
                        dia_info["estado"] = "severa"
                        dia_info["observaciones"].append("PERMISO SIN RETORNO — salió pero no registró regreso")
                        resumen["permiso_sin_retorno"] += 1

                elif n >= 4 and max_almuerzo_per > 0:
                    limite_alm = max_almuerzo_per
                    if just_alm and just_alm.get("duracion_permitida_min"):
                        limite_alm = just_alm["duracion_permitida_min"]
                        
                    for i, m in enumerate(marcaciones):
                        if m["tipo"] == "Salida" and i > 0:
                            for j in range(i + 1, len(marcaciones)):
                                if marcaciones[j]["tipo"] == "Entrada":
                                    entrada_alm = marcaciones[j]
                                    duracion = int((
                                        entrada_alm["datetime"] - m["datetime"]
                                    ).total_seconds() / 60)
                                    dia_info["almuerzo_duracion"] = duracion
                                    dia_info["almuerzo_salida"]   = m["hora"].strftime("%H:%M")
                                    dia_info["almuerzo_regreso"]  = entrada_alm["hora"].strftime("%H:%M")
                                    
                                    if duracion > max_almuerzo_per: # Excedió su límite normal
                                        if just_alm:
                                            if duracion <= limite_alm: # Pero está dentro de la justificación
                                                dia_info["observaciones"].append(f"Exceso almuerzo (+{duracion - max_almuerzo_per}m) JUSTIFICADO: {just_alm.get('motivo','')}")
                                                dia_info["justificado"] = True
                                                resumen["justificadas"] += 1
                                                if dia_info["estado"] == "ok":
                                                    dia_info["estado"] = "leve"
                                            else: # Excedió también la justificación (o el límite por defecto si no lo ajustó)
                                                exceso = duracion - limite_alm
                                                dia_info["almuerzo_exceso"] = exceso
                                                if dia_info["estado"] == "ok":
                                                    dia_info["estado"] = "leve"
                                                dia_info["observaciones"].append(
                                                    f"Exceso almuerzo NO JUSTIF. (+{exceso}m sobre límite autorizado {limite_alm}m)"
                                                )
                                                resumen["almuerzo_largo"] += 1
                                        else:
                                            exceso = duracion - max_almuerzo_per
                                            dia_info["almuerzo_exceso"] = exceso
                                            if dia_info["estado"] == "ok":
                                                dia_info["estado"] = "leve"
                                            dia_info["observaciones"].append(
                                                f"Exceso almuerzo (+{exceso}m)"
                                            )
                                            resumen["almuerzo_largo"] += 1
                                    break
                            break
                
                dia_info["tiempo_neto_min"] = _calcular_tiempo_neto_min(marcaciones)

                # ── Análisis de salida anticipada ─────────────────────────
                hora_salida_prog = info.get("hora_salida")
                if hora_salida_prog and len(marcaciones) >= 2:
                    just_salida = _get_justificado(fecha, "salida_anticipada")
                    
                    ultima_salida = None
                    for m in reversed(marcaciones):
                        if m["tipo"] == "Salida":
                            ultima_salida = m["hora"]
                            break
                            
                    if ultima_salida:
                        if not just_salida:
                            h_salida_t = datetime.strptime(hora_salida_prog, "%H:%M").time()
                            salida_diff = -_minutos_diferencia(h_salida_t, ultima_salida)
                            
                            if salida_diff > 0:  # Salió antes
                                if salida_diff > MARGEN_LEVE_MIN:
                                    dia_info["estado"] = "severa"
                                    dia_info["observaciones"].append(
                                        f"Salida ant. severa (-{salida_diff}m sobre {hora_salida_prog})"
                                    )
                                    resumen["salida_anticipada_severa"] += 1
                                else:
                                    if dia_info["estado"] == "ok":
                                        dia_info["estado"] = "leve"
                                    dia_info["observaciones"].append(
                                        f"Salida ant. leve (-{salida_diff}m sobre {hora_salida_prog})"
                                    )
                                    resumen["salida_anticipada_leve"] += 1
                        else:
                            hora_permitida = just_salida.get("hora_permitida")
                            if hora_permitida:
                                h_permitida_t = datetime.strptime(hora_permitida, "%H:%M").time()
                                salida_diff = -_minutos_diferencia(h_permitida_t, ultima_salida)
                                
                                if salida_diff > 0: # Salió antes de lo permitido
                                    dia_info["estado"] = "severa"
                                    dia_info["observaciones"].append(
                                        f"Salida ant. NO JUSTIF. (-{salida_diff}m, auth. {hora_permitida})"
                                    )
                                    resumen["salida_anticipada_severa"] += 1
                                else:
                                    dia_info["justificado"] = True
                                    resumen["justificadas"] += 1
                                    if dia_info["estado"] == "ok":
                                        dia_info["estado"] = "leve"
                                    dia_info["observaciones"].append(f"Salida JUSTIFICADA: {just_salida.get('motivo','(Sin motivo)')}")
                            else:
                                dia_info["justificado"] = True
                                resumen["justificadas"] += 1
                                if dia_info["estado"] == "ok":
                                    dia_info["estado"] = "leve"
                                dia_info["observaciones"].append(f"Salida JUSTIFICADA: {just_salida.get('motivo','(Sin motivo)')}")

            # Incluir en dias_list si hay novedad, o siempre si mostrar_todos
            if mostrar_todos or dia_info["estado"] != "ok" or dia_info["observaciones"]:
                dias_list.append(dia_info)

        # ── Detectar ausencias: días que debían trabajar sin registros ─
        if fecha_inicio and fecha_fin:
            hoy = date.today()
            # No marcar inasistencia para hoy ni días futuros:
            # se usa hoy-1 para evitar falsos ausentes cuando la jornada
            # aún no ha terminado o el sync del día aún no se ha ejecutado.
            fecha_fin_evaluacion = min(fecha_fin, hoy - timedelta(days=1))
            d = fecha_inicio
            while d <= fecha_fin_evaluacion:
                if d not in por_fecha and d not in feriados:
                    info = _get_info_dia(horario_persona, d)
                    if info["trabaja"]:
                        just_aus = _get_justificado(d, "ausencia")
                        
                        dia_aus = {
                            "fecha": d, "llegada": None, "salida": None,
                            "hora_programada": info["hora_entrada"],
                            "almuerzo_duracion": None,
                            "almuerzo_salida": None, "almuerzo_regreso": None,
                            "almuerzo_exceso": None, "tiempo_dentro": None,
                            "n_registros": 0, "detalle_registros": "",
                            "estado": "ausente",
                            "justificado": bool(just_aus),
                        }
                        
                        if not just_aus:
                            resumen["ausencias"] += 1
                            resumen["total_dias"] += 1
                            dia_aus["observaciones"] = [f"AUSENTE — sin marcaciones (Prog: {info['hora_entrada']})"]
                        else:
                            resumen["justificadas"] += 1
                            resumen["total_dias"] += 1
                            dia_aus["observaciones"] = [f"AUSENCIA JUSTIFICADA: {just_aus.get('motivo','(Sin motivo)')}"]
                        
                        dias_list.append(dia_aus)
                d += timedelta(days=1)
            dias_list.sort(key=lambda x: x["fecha"])

        if (verificar_horas or mostrar_tiempo_extra) and (horario_persona.get("horas_semana") or horario_persona.get("horas_mes")):
            hs = horario_persona.get("horas_semana")
            hm = horario_persona.get("horas_mes")
            total_neto_min = sum(d.get("tiempo_neto_min", 0) for d in dias_list)

            if hs:
                from collections import defaultdict as _dd
                semanas = _dd(int)
                for d in dias_list:
                    if d.get("tiempo_neto_min", 0) > 0:
                        iso = d["fecha"].isocalendar()
                        semanas[(iso[0], iso[1])] += d["tiempo_neto_min"]

                esperado_sem_min = int(hs * 60)
                detalle_semanas, deficit_total_min, excedente_total_min = [], 0, 0
                for (anio, num_sem), worked in sorted(semanas.items()):
                    diff = worked - esperado_sem_min
                    detalle_semanas.append({
                        "semana":         f"{anio}-S{num_sem:02d}",
                        "trabajados_min": worked,
                        "esperados_min":  esperado_sem_min,
                        "diferencia_min": diff,
                    })
                    if diff < 0: deficit_total_min    += abs(diff)
                    else:        excedente_total_min  += diff

                resumen["horas_contrato_tipo"]  = "semana"
                resumen["horas_contrato_valor"] = hs
                resumen["total_neto_min"]       = total_neto_min
                resumen["deficit_horas_min"]    = deficit_total_min
                resumen["excedente_horas_min"]  = excedente_total_min
                resumen["detalle_semanas"]      = detalle_semanas

            elif hm:
                esperado_mes_min = int(hm * 60)
                diff = total_neto_min - esperado_mes_min
                resumen["horas_contrato_tipo"]  = "mes"
                resumen["horas_contrato_valor"] = hm
                resumen["total_neto_min"]       = total_neto_min
                resumen["deficit_horas_min"]    = abs(diff) if diff < 0 else 0
                resumen["excedente_horas_min"]  = diff if diff > 0 else 0
                resumen["detalle_semanas"]      = []

        if resumen.get("total_dias", 0) > 0:
            resultado[nombre] = {
                "dias":          dias_list,
                "resumen":       resumen,
                "sin_novedades": not dias_list,
            }

    return resultado

def _minutos_diferencia(hora_limite, hora_real) -> int:
    """Minutos de diferencia entre hora_limite y hora_real."""
    dt_base = datetime.combine(datetime.today().date(), hora_limite)
    dt_real = datetime.combine(datetime.today().date(), hora_real)
    return int((dt_real - dt_base).total_seconds() / 60)


# ── Helpers de horarios personalizados ────────────────────────────────────

_WEEKDAY_COL = {
    0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
    4: "viernes", 5: "sabado", 6: "domingo",
}


def _buscar_horario(nombre: str, id_usuario, horarios: dict) -> dict | None:
    """
    Busca el horario de un empleado en el dict de horarios.
    Intenta por id_usuario primero; cae en búsqueda por nombre en mayúsculas.
    Retorna el dict de horario o None si no se encuentra.
    """
    if not horarios:
        return None
    by_id     = horarios.get("by_id",     {})
    by_nombre = horarios.get("by_nombre", {})

    if id_usuario and str(id_usuario) in by_id:
        return by_id[str(id_usuario)]

    if nombre:
        return by_nombre.get(nombre.strip().upper())

    return None


def _get_info_dia(horario_persona: dict, fecha) -> dict:
    """
    Retorna la información de horario aplicable para una persona en una fecha.

    Returns:
        {
            "trabaja":      bool,
            "hora_entrada": "HH:MM" | None,
            "hora_salida":  "HH:MM" | None,
            "almuerzo_min": int,
        }
    """
    weekday   = fecha.weekday()
    es_sabado = weekday == 5
    es_domingo = weekday == 6

    if es_domingo:
        columna = "domingo"
        hora_entrada = horario_persona.get("domingo")
        hora_salida = horario_persona.get("domingo_salida")
        return {
            "trabaja":      hora_entrada is not None,
            "hora_entrada": hora_entrada,
            "hora_salida":  hora_salida,
            "almuerzo_min": 0,
        }

    columna      = _WEEKDAY_COL.get(weekday, "viernes")
    hora_entrada = horario_persona.get(columna)
    hora_salida  = horario_persona.get(f"{columna}_salida")
    
    col_almuerzo = f"{columna}_almuerzo_min"
    almuerzo_dia = horario_persona.get(col_almuerzo)
    if almuerzo_dia is None:
        almuerzo_dia = horario_persona.get("almuerzo_min", 0)
        
    almuerzo_min = 0 if es_sabado else almuerzo_dia

    return {
        "trabaja":      hora_entrada is not None,
        "hora_entrada": hora_entrada,
        "hora_salida":  hora_salida,
        "almuerzo_min": almuerzo_min,
    }


# ══════════════════════════════════════════════════════════════════════════
# GENERACIÓN DEL PDF
# ══════════════════════════════════════════════════════════════════════════

def generar_pdf(
    ruta_salida: str,
    analisis_por_dia: dict,
    log_duplicados: list[dict],
    config: dict,
    nombre_archivo_origen: str,
    filtros: dict = None,
    sin_horario: list = None,
):
    """Genera el PDF completo con todos los días y el log de duplicados."""
    if filtros is None:
        filtros = {}
    if sin_horario is None:
        sin_horario = []

    _F = {
        "mostrar_tardanza_leve":      filtros.get("mostrar_tardanza_leve",      True),
        "mostrar_tardanza_severa":    filtros.get("mostrar_tardanza_severa",    True),
        "mostrar_almuerzo":           filtros.get("mostrar_almuerzo",           True),
        "mostrar_incompletos":        filtros.get("mostrar_incompletos",        True),
        "mostrar_salida_anticipada":  filtros.get("mostrar_salida_anticipada",  True),
        "mostrar_todos_los_dias":     filtros.get("mostrar_todos_los_dias",     False),
    }

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
    _claves_activas = []
    if _F["mostrar_tardanza_leve"]:      _claves_activas.append("tardanza_leve")
    if _F["mostrar_tardanza_severa"]:    _claves_activas.append("tardanza_severa")
    if _F["mostrar_almuerzo"]:           _claves_activas.append("almuerzo_largo")
    if _F["mostrar_incompletos"]:        _claves_activas.append("incompletos")
    if _F["mostrar_salida_anticipada"]:
        _claves_activas.append("salida_anticipada_leve")
        _claves_activas.append("salida_anticipada_severa")

    if _F["mostrar_todos_los_dias"]:
        dias_a_mostrar = sorted(analisis_por_dia.keys())
    else:
        dias_a_mostrar = [
            d for d in sorted(analisis_por_dia.keys())
            if any(analisis_por_dia[d]["resumen"].get(k, 0) > 0 for k in _claves_activas)
        ]

    if not dias_a_mostrar:
        total_dias_con_reg = len(analisis_por_dia)
        sufijo = "día con registros" if total_dias_con_reg == 1 else "días con registros"
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph(
            f"✓ Sin novedades en el período consultado "
            f"({total_dias_con_reg} {sufijo}).",
            st["ok"]
        ))
    else:
        for dia in dias_a_mostrar:
            story.append(Spacer(1, 1*cm))
            story += _pagina_dia(st, dia, analisis_por_dia[dia], config, _F)

    # ── Personas sin horario ──────────────────────────────────────────
    if sin_horario:
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph("PERSONAS EN EL BIOMÉTRICO SIN HORARIO ASIGNADO", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3*cm))
        filas_sh = [["#", "Nombre"]]
        for i, n in enumerate(sin_horario, 1):
            filas_sh.append([str(i), n])
        t_sh = Table(filas_sh, colWidths=[1.2*cm, 15.3*cm])
        t_sh.setStyle(_estilo_tabla_datos(len(filas_sh)))
        story.append(t_sh)

    # ── Log de duplicados ─────────────────────────────────────────────
    if log_duplicados:
        story.append(Spacer(1, 1*cm))
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
    filtros: dict = None,
    sin_horario: list = None,
):
    if filtros is None:
        filtros = {}
    if sin_horario is None:
        sin_horario = []
    _F = {
        "mostrar_ausencias":          filtros.get("mostrar_ausencias",          True),
        "mostrar_tardanza_severa":    filtros.get("mostrar_tardanza_severa",    True),
        "mostrar_tardanza_leve":      filtros.get("mostrar_tardanza_leve",      True),
        "mostrar_almuerzo":           filtros.get("mostrar_almuerzo",           True),
        "mostrar_incompletos":        filtros.get("mostrar_incompletos",        True),
        "mostrar_salida_anticipada":  filtros.get("mostrar_salida_anticipada",  True),
        "mostrar_todos_los_dias":     filtros.get("mostrar_todos_los_dias",     False),
        "columna_tiempo_dentro":      filtros.get("columna_tiempo_dentro",      False),
        "verificar_horas":            filtros.get("verificar_horas",            False),
        "mostrar_tiempo_extra":       filtros.get("mostrar_tiempo_extra",       False),
    }

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

    nombre_sistema     = os.getenv("NOMBRE_SISTEMA",     "Informes Biométricos")
    nombre_institucion = os.getenv("NOMBRE_INSTITUCION", "ISTPET")

    # ── Portada ───────────────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph(f"{nombre_sistema.upper()} (POR PERSONA)", st["titulo"]))
    story.append(Paragraph(f"Control Biométrico · {nombre_institucion.upper()}", st["subtitulo"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_HEADER))
    story.append(Spacer(1, 1*cm))

    # Metadata
    if len(analisis_persona) == 1:
        persona_nombre = list(analisis_persona.keys())[0]
        datos_portada = [
            ["Archivo origen:",     nombre_archivo_origen],
            ["Generado el:",        datetime.now().strftime("%d/%m/%Y %H:%M")],
            ["Persona analizada:",  persona_nombre],
        ]
    else:
        datos_portada = [
            ["Archivo origen:",     nombre_archivo_origen],
            ["Generado el:",        datetime.now().strftime("%d/%m/%Y %H:%M")],
            ["Personas analizadas:", str(len(analisis_persona))],
        ]
    t_portada = Table(datos_portada, colWidths=[6*cm, 10*cm])
    t_portada.setStyle(TableStyle([
        ("FONTNAME",     (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",     (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",     (0,0), (-1,-1), 10),
        ("TEXTCOLOR",    (0,0), (0,-1), COLOR_SUBHEADER),
        ("TEXTCOLOR",    (1,0), (1,-1), COLOR_TEXTO),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BACKGROUND",   (0,1), (-1,-1), COLOR_TABLA_ALT),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
    ]))
    story.append(t_portada)
    story.append(PageBreak())

    # ── Resumen General ───────────────────────────────────────────────
    story.append(Paragraph("RESUMEN GENERAL", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.5*cm))

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
    # Ajustar anchos para incluir la nueva columna
    t_res = Table(filas_resumen, colWidths=[3.6*cm, 1.2*cm, 1.6*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm])
    t_res.setStyle(_estilo_tabla_datos(len(filas_resumen)))
    story.append(t_res)

    # ── Sección por persona ───────────────────────────────────────────
    for nombre in sorted(analisis_persona.keys()):
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(f"  {nombre}", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3*cm))

        r = analisis_persona[nombre]["resumen"]
        partes = []
        if r.get("ausencias",       0): partes.append(f"<b>{r['ausencias']}</b> ausencias")
        if r.get("tardanza_severa", 0): partes.append(f"<b>{r['tardanza_severa']}</b> tard. severas")
        if r.get("tardanza_leve",   0): partes.append(f"<b>{r['tardanza_leve']}</b> tard. leves")
        if r.get("almuerzo_largo",  0): partes.append(f"<b>{r['almuerzo_largo']}</b> exc. almuerzo")
        if r.get("incompletos",     0): partes.append(f"<b>{r['incompletos']}</b> anómalos")
        if r.get("justificadas",    0): partes.append(f"<b>{r['justificadas']}</b> justificadas")
        resumen_txt = "  ·  ".join(partes) if partes else "Sin novedades"
        story.append(Paragraph(resumen_txt, st["pequeño"]))
        story.append(Spacer(1, 0.4*cm))

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

        # ── Ausencias ─────────────────────────────────────────────────
        if _F["mostrar_ausencias"]:
            ausentes = [d for d in datos if d.get("estado") == "ausente"]
            story += _seccion_ausencias_persona(st, ausentes)

        # ── Tardanzas Severas ──────────────────────────────────────────
        if _F["mostrar_tardanza_severa"]:
            severas = [d for d in datos if d.get("estado") == "severa"]
            story += _seccion_tardanzas_persona(
                st, "Tardanzas Severas",
                "Llegadas con más de 5 minutos de retraso",
                severas, COLOR_ERROR, _F["columna_tiempo_dentro"]
            )

        # ── Tardanzas Leves ────────────────────────────────────────────
        if _F["mostrar_tardanza_leve"]:
            leves = [d for d in datos if d.get("estado") == "leve"
                     and any("Tardanza leve" in o for o in d.get("observaciones", []))]
            story += _seccion_tardanzas_persona(
                st, "Tardanzas Leves",
                "Llegadas con 1 a 5 minutos de retraso",
                leves, COLOR_WARN, _F["columna_tiempo_dentro"]
            )

        # ── Excesos de Almuerzo ────────────────────────────────────────
        if _F["mostrar_almuerzo"]:
            almuerzos = [d for d in datos if d.get("almuerzo_exceso") is not None
                         and d.get("almuerzo_exceso", 0) > 0]
            story += _seccion_almuerzo_persona(st, almuerzos)

        # ── Registros Incompletos ──────────────────────────────────────
        if _F["mostrar_incompletos"]:
            incompletos = [d for d in datos if d.get("estado") == "incompleto"]
            story += _seccion_incompletos_persona(st, incompletos)

        # ── Salidas Anticipadas ────────────────────────────────────────
        if _F["mostrar_salida_anticipada"]:
            salidas_ant = [d for d in datos if any("Salida ant." in o
                           for o in d.get("observaciones", []) if isinstance(o, str))]
            story += _seccion_salidas_anticipadas_persona(st, salidas_ant)

        # ── Permisos Temporales (Parte II) ──
        permisos = [d for d in datos if d.get("permiso_salida")]
        if permisos:
            story += _seccion_permisos_persona(st, permisos)

        # ── Cumplimiento de Horas de Contrato (Parte I) ──
        if (_F["verificar_horas"] or _F["mostrar_tiempo_extra"]) and r.get("horas_contrato_tipo"):
            story += _seccion_horas_contrato(st, r)

        # ── Detalle Cronológico (Todos los días) ───────────────────────
        if _F["mostrar_todos_los_dias"]:
            story += _seccion_cronologico_persona(st, datos, _F["columna_tiempo_dentro"])

    # ── Personas sin horario ──────────────────────────────────────────
    if sin_horario:
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph("PERSONAS EN EL BIOMÉTRICO SIN HORARIO ASIGNADO", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(
            "Las siguientes personas tienen registros biométricos pero no están en la lista de horarios.",
            st["pequeño"]
        ))
        story.append(Spacer(1, 0.3*cm))
        filas_sh = [["#", "Nombre"]]
        for i, n in enumerate(sin_horario, 1):
            filas_sh.append([str(i), n])
        t_sh = Table(filas_sh, colWidths=[1.2*cm, 15.3*cm])
        t_sh.setStyle(_estilo_tabla_datos(len(filas_sh)))
        story.append(t_sh)

    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    print(f"\n✅ Reporte por persona generado: {ruta_salida}\n")


def _dia_nombre_corto(fecha) -> str:
    """Retorna el nombre del día en español (3 letras)."""
    _DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    return _DIAS[fecha.weekday()]


def _seccion_cronologico_persona(st, datos: list, con_tiempo_dentro: bool) -> list:
    """Muestra todos los días analizados en una tabla cronológica."""
    story = []
    story.append(Paragraph("  DETALLE CRONOLÓGICO DE ASISTENCIA", st["seccion"]))
    story.append(Paragraph("Listado de todos los días laborables analizados en el período", st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))

    if not datos:
        story.append(Paragraph("Sin registros disponibles.", st["ok"]))
    else:
        # Definir encabezados y anchos
        enc = ["Fecha", "Ingreso", "Salida"]
        w   = [4.0*cm, 4.0*cm, 4.0*cm]
        if con_tiempo_dentro:
            enc.append("T. Dentro")
            w.append(4.0*cm)
        
        # Ajustar el último ancho para completar el ancho de página (aprox 17.4cm)
        w[-1] += (17.4*cm - sum(w))

        filas = [enc]
        for d in datos:
            obs_txt = " / ".join(d.get("observaciones", [])) or "—"
            
            fila = [
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("llegada") or "—",
                d.get("salida") or "—",
            ]
            if con_tiempo_dentro:
                fila.append(d.get("tiempo_dentro") or "—")
            
            filas.append(fila)

        t = Table(filas, colWidths=w, repeatRows=1)
        # Estilo base
        t.setStyle(_estilo_tabla_datos(len(filas)))
        
        # Resaltar filas con novedades
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_WARN)]))
            elif d.get("estado") == "severa":
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), colors.HexColor("#f8d7da"))]))
            elif d.get("estado") == "ausente":
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), colors.HexColor("#e2e3e5"))]))
            elif d.get("estado") in ("leve", "incompleto"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), colors.HexColor("#fff3cd"))]))

        story.append(t)
    
    story.append(Spacer(1, 0.5*cm))
    return story


def _seccion_ausencias_persona(st, datos: list) -> list:
    story = []
    story.append(Paragraph("  AUSENCIAS", st["seccion"]))
    story.append(Paragraph("Días en que debía trabajar y no registró ninguna marcación.", st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))
    if not datos:
        story.append(Paragraph("✓ Sin ausencias en el período.", st["ok"]))
    else:
        filas = [["Fecha", "Horario programado"]]
        for d in datos:
            filas.append([
                d["fecha"].strftime("%d/%m/%Y"),
                d.get("hora_programada") or "—",
            ])
        t = Table(filas, colWidths=[8.7*cm, 8.7*cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_ERROR))
        # Resaltar justificadas en amarillo
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5*cm))
    return story


def _seccion_tardanzas_persona(st, titulo: str, desc: str,
                                datos: list, color_bg, con_tiempo_dentro: bool) -> list:
    story = []
    story.append(Paragraph(f"  {titulo.upper()}", st["seccion"]))
    story.append(Paragraph(desc, st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))
    if not datos:
        story.append(Paragraph("✓ Sin novedades.", st["ok"]))
    else:
        enc = ["Fecha", "Programado", "Llegada", "Retraso"]
        w   = [4.5*cm, 4.5*cm, 4*cm, 4.4*cm]
        if con_tiempo_dentro:
            enc.append("Tiempo dentro")
            # Ajustar anchos para que quepan 5 columnas
            w = [3.5*cm, 3.5*cm, 3.5*cm, 3.4*cm, 3.5*cm]

        filas = [enc]
        for d in datos:
            obs_txt = " / ".join(o for o in d.get("observaciones", [])
                                 if "Tardanza" in o) or "—"
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
        # Resaltar justificadas en amarillo
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5*cm))
    return story


def _seccion_almuerzo_persona(st, datos: list) -> list:
    story = []
    story.append(Paragraph("  EXCESOS DE ALMUERZO", st["seccion"]))
    story.append(Paragraph("Días con tiempo de almuerzo superior al límite establecido.", st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))
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
        t = Table(filas, colWidths=[4*cm, 3*cm, 3.4*cm, 3.5*cm, 3.5*cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_WARN))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5*cm))
    return story


def _seccion_incompletos_persona(st, datos: list) -> list:
    story = []
    story.append(Paragraph("  REGISTROS ANÓMALOS / INCOMPLETOS", st["seccion"]))
    story.append(Paragraph("Días con un número inusual de marcaciones (esperado: 2 o 4).", st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))
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
        t = Table(filas, colWidths=[4*cm, 2.5*cm, 10.9*cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_TABLA_ALT))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5*cm))
    return story


def _seccion_salidas_anticipadas_persona(st, datos: list) -> list:
    """Sección de salidas anticipadas en el PDF por persona."""
    story = []
    story.append(Paragraph("  SALIDAS ANTICIPADAS", st["seccion"]))
    story.append(Paragraph(
        "Días en que el empleado salió antes de la hora de salida programada.",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.2*cm))
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
        t = Table(filas, colWidths=[4*cm, 3.5*cm, 9.9*cm])
        t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_ERROR))
        for i, d in enumerate(datos):
            if d.get("justificado"):
                t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_WARN)]))
        story.append(t)
    story.append(Spacer(1, 0.5*cm))
    return story



def _seccion_permisos_persona(st, datos: list) -> list:
    """Sección de permisos temporales en el PDF por persona."""
    story = []
    story.append(Paragraph("  PERMISOS TEMPORALES DURANTE LA JORNADA", st["seccion"]))
    story.append(Paragraph("Ausencias autorizadas por RRHH durante el transcurso del día.", st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))
    
    # Determinar si algún permiso incluye almuerzo para mostrar columna extra
    hay_alm = any(d.get("permiso_alm_min", 0) > 0 for d in datos)

    if hay_alm:
        enc = ["Fecha", "Salida", "Retorno", "Total", "Alm. incl.", "Neto"]
        col_w = [3.2*cm, 2.8*cm, 2.8*cm, 2.3*cm, 2.5*cm, 3.8*cm]
    else:
        enc = ["Fecha", "Salida Permiso", "Regreso Permiso", "Duración"]
        col_w = [4.3*cm, 4.3*cm, 4.3*cm, 4.5*cm]

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
            t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_OK)]))
        elif d.get("estado") == "severa":
            t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_ERROR)]))
        elif d.get("estado") == "leve":
            t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), COLOR_WARN)]))
            
    story.append(t)
    story.append(Spacer(1, 0.5*cm))
    return story


def _seccion_horas_contrato(st, resumen: dict) -> list:
    """Sección de cumplimiento de horas de contrato en el PDF."""
    story = []
    story.append(Paragraph("  CUMPLIMIENTO DE HORAS DE CONTRATO", st["seccion"]))
    
    tipo = resumen.get("horas_contrato_tipo")
    valor = resumen.get("horas_contrato_valor")
    
    subt = f"Horas estipuladas: <b>{valor}h {tipo}</b>"
    story.append(Paragraph(subt, st["pequeño"]))
    story.append(Spacer(1, 0.2*cm))
    
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
        t = Table(filas, colWidths=[4.3*cm, 4.3*cm, 4.3*cm, 4.5*cm])
        t.setStyle(_estilo_tabla_datos(len(filas)))
        
        # Colores por fila basados en diferencia
        for i, s in enumerate(resumen.get("detalle_semanas", [])):
            diff = s["diferencia_min"]
            if diff >= 0:
                bg = COLOR_OK
            elif abs(diff) < 120: # Menos de 2h de déficit
                bg = COLOR_WARN
            else:
                bg = COLOR_ERROR
            t.setStyle(TableStyle([("BACKGROUND", (0, i+1), (-1, i+1), bg)]))
            
        story.append(t)
    else: # mes
        total_trab = resumen.get("total_neto_min", 0)
        esperado = int(valor * 60)
        diff = total_trab - esperado
        
        datos_mes = [
            ["Total Trabajado:", _fmt_horas(total_trab)],
            ["Total Esperado:", _fmt_horas(esperado)],
            ["Diferencia:",     _fmt_horas(diff)]
        ]
        t = Table(datos_mes, colWidths=[6*cm, 4*cm])
        bg = COLOR_OK if diff >= 0 else COLOR_ERROR if abs(diff) > 480 else COLOR_WARN
        t.setStyle(TableStyle([
            ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
            ("BACKGROUND", (0,2), (-1,2), bg),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(t)

    story.append(Spacer(1, 0.5*cm))
    return story


def _retraso_de_obs(observaciones: list) -> str:
    """Extrae el texto de retraso (ej '+3m') de las observaciones."""
    import re
    for o in observaciones:
        m = re.search(r'\+(\d+)m', o)
        if m:
            return f"+{m.group(1)} min"
    return "—"

def _crear_estilos(base):

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


# ── Portada ────────────────────────────────────────────────────────────────

def _portada(st, origen, config, analisis):
    story = []
    nombre_sistema = os.getenv("NOMBRE_SISTEMA", "Informes Biométricos")
    nombre_institucion = os.getenv("NOMBRE_INSTITUCION", "ISTPET")
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph(nombre_sistema.upper(), st["titulo"]))
    story.append(Paragraph(f"Control Biométrico · {nombre_institucion.upper()}", st["subtitulo"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_HEADER))
    story.append(Spacer(1, 1*cm))

    # Metadata
    datos = [
        ["Archivo origen:",    origen],
        ["Generado el:",       datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Días analizados:",   str(len(analisis))],
    ]
    if config.get("excluidos"):
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

    # Tabla resumen por fecha
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

    t2 = Table(filas, colWidths=[3.5*cm, 2.2*cm, 2.5*cm, 2.8*cm, 3.5*cm, 3*cm])
    t2.setStyle(_estilo_tabla_datos(len(filas)))
    story.append(t2)
    return story


# ── Página de un día ───────────────────────────────────────────────────────

def _pagina_dia(st, dia, datos, config, filtros_activos: dict = None):
    if filtros_activos is None:
        filtros_activos = {}
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

    story.append(Paragraph(f"  {nombre_dia.upper()}", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.3*cm))

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
    story.append(Spacer(1, 0.4*cm))

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


def _seccion_almuerzo(st, lista):
    story = []
    story.append(Paragraph("🍽️  Exceso de Almuerzo", st["seccion"]))
    story.append(Paragraph(
        "Personas con exceso de tiempo de almuerzo según horario individual",
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
        det_val = p.get("detalle", "—")
        if det_val and det_val != "—":
            det_val = Paragraph(det_val, st["pequeño"])
        filas.append([p["nombre"], str(p["registros"]), det_val])
    t = Table(filas, colWidths=[5.5*cm, 2.5*cm, 8.5*cm])
    t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_TABLA_ALT))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))
    return story


def _seccion_salida_anticipada_general(st, severas: list, leves: list) -> list:
    """Sección de salidas anticipadas en el reporte general (por día)."""
    story = []
    story.append(Paragraph("🚪  Salidas Anticipadas", st["seccion"]))
    story.append(Paragraph(
        "Personas que salieron antes de su hora de salida programada",
        st["pequeño"]
    ))
    story.append(Spacer(1, 0.2*cm))

    enc = ["#", "Nombre", "Salida real", "Prog. salida", "Adelanto"]
    filas = [enc]
    for i, p in enumerate(severas, 1):
        filas.append([str(i), p["nombre"], p["hora"],
                      p.get("programado", "—"), f"-{p['retraso']} min"])
    offset = len(severas)
    for i, p in enumerate(leves, offset + 1):
        filas.append([str(i), p["nombre"], p["hora"],
                      p.get("programado", "—"), f"-{p['retraso']} min"])

    t = Table(filas, colWidths=[0.8*cm, 7.5*cm, 2.5*cm, 2.7*cm, 2.8*cm])
    t.setStyle(_estilo_tabla_datos(len(filas), color_fila=COLOR_WARN))
    # Severas en rojo, leves en amarillo
    for i in range(1, len(severas) + 1):
        t.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), COLOR_ERROR)]))
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
        ("BACKGROUND",    (0,1), (-1,-1), bg),
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
    parser.add_argument("--duplicado-min", type=float,
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
        "duplicado_min": args.duplicado_min,
        "excluidos":     args.excluir,
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
            analisis_por_dia[fecha] = analizar_dia(regs, {})
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
def _fmt_horas(minutos: int) -> str:
    """Formatea minutos como 'Xh Ym'."""
    if minutos is None: return "—"
    signo = "-" if minutos < 0 else ""
    abs_min = abs(int(minutos))
    h, m = divmod(abs_min, 60)
    if h > 0:
        return f"{signo}{h}h {int(m)}m"
    return f"{signo}{int(m)}m"
