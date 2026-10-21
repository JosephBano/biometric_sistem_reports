"""
Reglas de análisis para un solo día (`app.domain.reports.day_rules`).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from app.domain.reports.justifications import es_justificado_dia
from app.domain.reports.models import MARGEN_LEVE_MIN
from app.domain.reports.schedules import (
    _buscar_horario,
    _get_info_dia,
    _minutos_diferencia,
)


def analizar_dia(
    registros_dia: list[dict[str, Any]],
    horarios: dict[str, Any],
    justificaciones: dict[tuple[Any, str, str], Any] | None = None,
    feriados: set[date] | None = None,
    permitir_sin_horario: bool = False,
) -> dict[str, Any]:
    """Analiza los registros de UN día y devuelve estructura de resumen."""
    if justificaciones is None:
        justificaciones = {}
    if feriados is None:
        feriados = set()

    por_persona = defaultdict(list)
    for r in registros_dia:
        por_persona[r["nombre"]].append(r)

    tardanza_leve_lst: list[dict[str, Any]] = []
    tardanza_severa_lst: list[dict[str, Any]] = []
    salida_anticipada_leve_lst: list[dict[str, Any]] = []
    salida_anticipada_severa_lst: list[dict[str, Any]] = []
    almuerzo_largo: list[dict[str, Any]] = []
    incompletos: list[dict[str, Any]] = []

    for nombre, marcaciones in por_persona.items():
        marcaciones.sort(key=lambda x: x["datetime"])

        id_usuario      = marcaciones[0].get("id_usuario")
        fecha_dia       = marcaciones[0]["fecha"]
        horario_persona = _buscar_horario(nombre, id_usuario, horarios)

        if horario_persona is None:
            if permitir_sin_horario:
                incompletos.append({
                    "nombre":    nombre,
                    "registros": len(marcaciones),
                    "detalle":   "SIN HORARIO ASIGNADO / " + " / ".join(
                        f"{m['tipo']} {m['hora'].strftime('%H:%M')}"
                        for m in marcaciones
                    ),
                })
            continue

        if fecha_dia in feriados:
            continue

        info = _get_info_dia(horario_persona, fecha_dia)
        if not info["trabaja"]:
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

        primera = marcaciones[0]
        if primera["tipo"] == "Entrada" and not es_justificado_dia(justificaciones, id_usuario, fecha_dia, "tardanza"):
            hora_llegada = primera["hora"]
            h_prog  = datetime.strptime(hora_prog, "%H:%M").time()
            retraso = _minutos_diferencia(h_prog, hora_llegada)
            if retraso > MARGEN_LEVE_MIN:
                tardanza_severa_lst.append({
                    "nombre":     nombre,
                    "hora":       hora_llegada.strftime("%H:%M"),
                    "retraso":    retraso,
                    "programado": hora_prog,
                })
            elif retraso > 0:
                tardanza_leve_lst.append({
                    "nombre":     nombre,
                    "hora":       hora_llegada.strftime("%H:%M"),
                    "retraso":    retraso,
                    "programado": hora_prog,
                })

        if max_almuerzo_per > 0 and not es_justificado_dia(justificaciones, id_usuario, fecha_dia, "almuerzo"):
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

        n = len(marcaciones)
        _tipos_seq   = [m["tipo"] for m in marcaciones]
        _seq_valida  = _tipos_seq in (
            ["Entrada", "Salida"],
            ["Entrada", "Salida", "Entrada", "Salida"],
        )
        if not _seq_valida:
            if not es_justificado_dia(justificaciones, id_usuario, fecha_dia, "incompleto"):
                incompletos.append({
                    "nombre":    nombre,
                    "registros": n,
                    "detalle":   " / ".join(
                        f"{m['tipo']} {m['hora'].strftime('%H:%M')}"
                        for m in marcaciones
                    ),
                })

        hora_salida_prog = info.get("hora_salida")
        if hora_salida_prog and len(marcaciones) >= 2 and not es_justificado_dia(justificaciones, id_usuario, fecha_dia, "salida_anticipada"):
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
                        "nombre":     nombre,
                        "hora":       ultima_salida.strftime("%H:%M"),
                        "retraso":    salida_diff,
                        "programado": hora_salida_prog,
                    })
                elif salida_diff > 0:
                    salida_anticipada_leve_lst.append({
                        "nombre":     nombre,
                        "hora":       ultima_salida.strftime("%H:%M"),
                        "retraso":    salida_diff,
                        "programado": hora_salida_prog,
                    })

    return {
        "tardanza_leve":            sorted(tardanza_leve_lst,            key=lambda x: x["hora"]),
        "tardanza_severa":          sorted(tardanza_severa_lst,          key=lambda x: x["hora"]),
        "salida_anticipada_leve":   sorted(salida_anticipada_leve_lst,   key=lambda x: x["hora"]),
        "salida_anticipada_severa": sorted(salida_anticipada_severa_lst, key=lambda x: x["hora"]),
        "almuerzo_largo":           sorted(almuerzo_largo,               key=lambda x: -x["duracion"]),
        "registros_incompletos":    sorted(incompletos,                  key=lambda x: x["nombre"]),
        "resumen": {
            "total_personas":           len(por_persona),
            "tardanza_leve":            len(tardanza_leve_lst),
            "tardanza_severa":          len(tardanza_severa_lst),
            "salida_anticipada_leve":   len(salida_anticipada_leve_lst),
            "salida_anticipada_severa": len(salida_anticipada_severa_lst),
            "almuerzo_largo":           len(almuerzo_largo),
            "incompletos":              len(incompletos),
        },
    }
