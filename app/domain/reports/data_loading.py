"""
Carga de archivos, filtrado, deduplicación y resolución canónica (`app.domain.reports.data_loading`).
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.domain.reports.models import DEFAULT_CONFIG


def cargar_archivo(ruta: str) -> list[dict[str, Any]]:
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


def _leer_csv(ruta: str) -> list[dict[str, Any]]:
    """
    Lee el CSV exportado del sistema biométrico.
    Formato esperado de columnas: ,ID,Nombre,Fecha/Hora,Estado,...,Tipo
    """
    registros = []
    with open(ruta, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for fila in reader:
            if len(fila) < 5:
                continue
            estado = fila[4].strip() if len(fila) > 4 else ""
            if estado not in ("Entrada", "Salida"):
                continue

            nombre    = fila[2].strip()
            fecha_str = fila[3].strip()
            tipo      = estado

            if not nombre or not fecha_str:
                continue

            try:
                dt = datetime.strptime(fecha_str, "%d/%m/%Y %H:%M")
            except ValueError:
                try:
                    dt = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

            registros.append({
                "nombre": nombre,
                "datetime": dt,
                "fecha": dt.date(),
                "hora": dt.time(),
                "tipo": tipo,
            })

    return registros


def _leer_xlsx(ruta: str) -> list[dict[str, Any]]:
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


def filtrar_excluidos(registros: list[dict[str, Any]], excluidos: list[str]) -> list[dict[str, Any]]:
    """Elimina del análisis a las personas en la lista de excluidos."""
    if not excluidos:
        return registros
    excluidos_lower = [e.lower() for e in excluidos]
    return [
        r for r in registros
        if not any(ex in r["nombre"].lower() for ex in excluidos_lower)
    ]


def deduplicar(
    registros: list[dict[str, Any]],
    max_min: float = DEFAULT_CONFIG["duplicado_min"],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Elimina marcaciones duplicadas por error humano.

    Regla: si una persona tiene dos marcaciones CONSECUTIVAS del mismo tipo
    (Entrada→Entrada o Salida→Salida) separadas por menos de `max_min` minutos,
    la segunda se descarta como error.

    Devuelve (registros_limpios, log_duplicados).
    """
    grupos = defaultdict(list)
    for r in registros:
        grupos[(r["nombre"], r["fecha"])].append(r)

    limpios = []
    log_dup = []

    for _clave, marcaciones in grupos.items():
        marcaciones.sort(key=lambda x: x["datetime"])
        resultado = [marcaciones[0]]

        for actual in marcaciones[1:]:
            anterior = resultado[-1]
            delta = (actual["datetime"] - anterior["datetime"]).total_seconds() / 60

            if actual["tipo"] == anterior["tipo"] and delta <= max_min:
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


def _calcular_tiempo_neto_min(marcaciones: list[dict[str, Any]]) -> int:
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


def _persona_id_para_marcacion(registro: dict[str, Any]) -> str | None:
    """Extrae el `persona_id` de un registro si el motor lo expone."""
    return registro.get("persona_id")


def enriquecer_analisis_con_origen(
    analisis: dict[str, Any],
    registros_por_persona: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Para cada (persona, día) en `analisis`, añade `horario_origen`."""
    if not registros_por_persona:
        return analisis

    from app.domain.horarios_resolucion import (
        resolver_horario_vigente_para_persona,
    )

    for nombre, por_fecha_registros in registros_por_persona.items():
        if nombre not in analisis:
            continue
        persona_id = _persona_id_para_marcacion(por_fecha_registros[0])
        if not persona_id:
            continue
        for dia in analisis[nombre].get("dias", []):
            fecha_dia = dia.get("fecha")
            if not fecha_dia:
                continue
            try:
                if isinstance(fecha_dia, str):
                    from datetime import date as _date
                    fecha_dia = _date.fromisoformat(fecha_dia)
                resuelto = resolver_horario_vigente_para_persona(
                    persona_id, fecha_dia,
                )
                dia["horario_origen"] = resuelto.get("origen")
                if not dia.get("plantilla_id") and resuelto.get("plantilla_id"):
                    dia["plantilla_id"] = resuelto["plantilla_id"]
            except Exception:  # noqa: BLE001
                dia["horario_origen"] = None

    return analisis
