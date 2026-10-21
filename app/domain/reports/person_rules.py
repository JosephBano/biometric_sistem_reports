"""
Reglas de análisis organizadas por persona (`app.domain.reports.person_rules`).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.domain.reports.data_loading import _calcular_tiempo_neto_min
from app.domain.reports.justifications import obtener_justificacion_persona
from app.domain.reports.models import MARGEN_LEVE_MIN
from app.domain.reports.schedules import (
    _buscar_horario,
    _get_info_dia,
    _minutos_diferencia,
)


def _procesar_persona_sin_horario(por_fecha: dict[date, list[dict[str, Any]]]) -> dict[str, Any]:
    """Genera el bloque de análisis para colaboradores sin horario configurado."""
    dias_list = []
    ms_count = 0
    for f, ms in sorted(por_fecha.items()):
        ms.sort(key=lambda x: x["datetime"])
        entradas = [m for m in ms if m.get("tipo") == "Entrada"]
        salidas = [m for m in ms if m.get("tipo") == "Salida"]
        llegada = entradas[0]["hora"].strftime("%H:%M") if entradas else (ms[0]["hora"].strftime("%H:%M") if ms else None)
        salida = salidas[-1]["hora"].strftime("%H:%M") if salidas else (ms[-1]["hora"].strftime("%H:%M") if len(ms) > 1 else None)

        tiempo_dentro = None
        if len(ms) >= 2:
            primera_dt = ms[0]["datetime"]
            ultima_dt = ms[-1]["datetime"]
            if ultima_dt > primera_dt:
                td_min = int((ultima_dt - primera_dt).total_seconds() / 60)
                h_td, m_td = divmod(td_min, 60)
                tiempo_dentro = f"{h_td}h {m_td:02d}m"

        tiempo_neto = _calcular_tiempo_neto_min(ms)
        horas_trabajadas = None
        if tiempo_neto > 0:
            h_t, m_t = divmod(tiempo_neto, 60)
            horas_trabajadas = f"{h_t}h {m_t:02d}m"
        elif tiempo_dentro:
            horas_trabajadas = tiempo_dentro

        ms_count = len(ms)
        dias_list.append({
            "fecha":             f,
            "llegada":           llegada,
            "salida":            salida,
            "hora_programada":   "—",
            "almuerzo_duracion": None,
            "tiempo_dentro":     tiempo_dentro,
            "tiempo_neto_min":   tiempo_neto,
            "horas_trabajadas":  horas_trabajadas,
            "n_registros":       len(ms),
            "detalle_registros": " / ".join(f"{mx['tipo']} {mx['hora'].strftime('%H:%M')}" for mx in ms),
            "observaciones":     ["Sin horario individual configurado"],
            "estado":            "sin_horario",
        })

    return {
        "dias": dias_list,
        "resumen": {
            "total_dias":               len(dias_list),
            "dias_laborables":          len(dias_list),
            "tardanza_leve":            0,
            "tardanza_severa":          0,
            "almuerzo_largo":           0,
            "incompletos":              sum(1 for _ in dias_list if ms_count < 2),
            "ausencias":                0,
            "justificadas":             0,
            "salida_anticipada_leve":   0,
            "salida_anticipada_severa": 0,
        },
        "sin_novedades": True,
        "horario_info": {
            "tipo":        "Sin horario individual",
            "descripcion": "El colaborador registra marcaciones pero no tiene un turno configurado.",
        },
    }


def _calcular_horas_contrato(
    horario_persona: dict[str, Any],
    todos_los_dias: list[dict[str, Any]],
    fecha_inicio: date | None,
    fecha_fin: date | None,
    feriados: set[date],
    resumen: dict[str, Any],
) -> None:
    """Calcula el balance semanal o mensual según horas de contrato configuradas."""
    hs_val = horario_persona.get("horas_semana")
    hm_val = horario_persona.get("horas_mes")
    hs = float(hs_val) if hs_val is not None else None
    hm = float(hm_val) if hm_val is not None else None
    total_neto_min = sum(d.get("tiempo_neto_min", 0) for d in todos_los_dias)

    if hs:
        semanas = defaultdict(int)
        for d in todos_los_dias:
            iso = d["fecha"].isocalendar()
            semanas[(iso[0], iso[1])] += d.get("tiempo_neto_min", 0)

        detalle_semanas, deficit_total_min, excedente_total_min = [], 0, 0
        for (anio, num_sem), worked in sorted(semanas.items()):
            monday = date.fromisocalendar(anio, num_sem, 1)
            sunday = date.fromisocalendar(anio, num_sem, 7)

            start_eval = max(monday, fecha_inicio) if fecha_inicio else monday
            end_eval = min(sunday, fecha_fin) if fecha_fin else sunday

            total_scheduled_days = 0
            scheduled_days_in_period = 0

            d_eval = monday
            while d_eval <= sunday:
                info = _get_info_dia(horario_persona, d_eval)
                if info["trabaja"]:
                    total_scheduled_days += 1
                    if (not fecha_inicio or d_eval >= fecha_inicio) and \
                       (not fecha_fin or d_eval <= fecha_fin) and \
                       (d_eval not in feriados):
                        scheduled_days_in_period += 1
                d_eval += timedelta(days=1)

            if total_scheduled_days > 0:
                prop = scheduled_days_in_period / total_scheduled_days
                esperado_sem_min = int(hs * 60 * prop)
            else:
                esperado_sem_min = 0

            diff = worked - esperado_sem_min
            start_str = start_eval.strftime("%d/%m/%Y")
            end_str = end_eval.strftime("%d/%m/%Y")
            semana_rango = f"{start_str} - {end_str}"

            detalle_semanas.append({
                "semana":         semana_rango,
                "trabajados_min": worked,
                "esperados_min":  esperado_sem_min,
                "diferencia_min": diff,
            })
            if diff < 0:
                deficit_total_min += abs(diff)
            else:
                excedente_total_min += diff

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


def analizar_por_persona(
    registros: list[dict[str, Any]],
    config: dict[str, Any],
    horarios: dict[str, Any] | None = None,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    justificaciones: dict[tuple[str, str, str], Any] | None = None,
    feriados: set[date] | None = None,
    breaks_categorizados: dict[Any, Any] | None = None,
    mostrar_todos: bool = False,
    permitir_sin_horario: bool = False,
    verificar_horas: bool = False,
    mostrar_tiempo_extra: bool = False,
) -> dict[str, Any]:
    """Analiza registros organizados por persona a lo largo de un período."""
    if justificaciones is None:
        justificaciones = {}
    if feriados is None:
        feriados = set()
    if breaks_categorizados is None:
        breaks_categorizados = {}

    por_persona_fecha = defaultdict(lambda: defaultdict(list))
    for r in registros:
        por_persona_fecha[r["nombre"]][r["fecha"]].append(r)

    resultado = {}

    for nombre, por_fecha in por_persona_fecha.items():
        id_usuario = None
        for _, marcaciones_tmp in por_fecha.items():
            if marcaciones_tmp and "id_usuario" in marcaciones_tmp[0]:
                id_usuario = marcaciones_tmp[0]["id_usuario"]
                break

        horario_persona = _buscar_horario(nombre, id_usuario, horarios)
        if horario_persona is None:
            if permitir_sin_horario:
                resultado[nombre] = _procesar_persona_sin_horario(por_fecha)
            continue

        dias_list: list[dict[str, Any]] = []
        todos_los_dias: list[dict[str, Any]] = []
        resumen: dict[str, Any] = {
            "total_dias":                  0,
            "tardanza_leve":               0,
            "tardanza_severa":             0,
            "almuerzo_largo":              0,
            "incompletos":                 0,
            "ausencias":                   0,
            "justificadas":                0,
            "salida_anticipada_leve":      0,
            "salida_anticipada_severa":    0,
            "permiso_retorno_tardio":      0,
            "permiso_retorno_tardio_leve": 0,
            "permiso_sin_retorno":         0,
        }

        for fecha, marcaciones in sorted(por_fecha.items()):
            marcaciones.sort(key=lambda x: x["datetime"])

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

            dia_info: dict[str, Any] = {
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
                "marcaciones": [
                    {
                        "hora": m["hora"].strftime("%H:%M:%S") if hasattr(m["hora"], "strftime") else str(m["hora"]),
                        "tipo": m.get("tipo", "").lower(),
                        "tipo_raw": m.get("tipo_raw") or m.get("tipo", ""),
                        "fuente": m.get("fuente", "Biométrico"),
                        "dispositivo_id": m.get("dispositivo_id", ""),
                    }
                    for m in marcaciones
                ],
            }

            info = _get_info_dia(horario_persona, fecha)
            dia_info["hora_programada"] = info["hora_entrada"]

            if not info["trabaja"]:
                dia_info["estado"] = "extra"
                if marcaciones:
                    if marcaciones[0]["tipo"] == "Entrada":
                        dia_info["llegada"] = marcaciones[0]["hora"].strftime("%H:%M")
                    if marcaciones[-1]["tipo"] == "Salida":
                        dia_info["salida"] = marcaciones[-1]["hora"].strftime("%H:%M")
                dia_info["detalle_registros"] = " / ".join(
                    f"{m['tipo']} {m['hora'].strftime('%H:%M')}" for m in marcaciones
                )
                dia_info["observaciones"].append("Día libre según horario (trabajo excepcional)")
                dias_list.append(dia_info)
                resumen["total_dias"] += 1
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
                just_inc = obtener_justificacion_persona(justificaciones, id_usuario, fecha, "incompleto")
                dia_info["estado"] = "incompleto"
                if not just_inc:
                    dia_info["observaciones"].append(f"Registros anómalos ({n})")
                    resumen["incompletos"] += 1
                else:
                    dia_info["justificado"] = True
                    dia_info["observaciones"].append(f"ANOMALÍA JUSTIFICADA: {just_inc.get('motivo','(Sin motivo)')}")

                if n > 4:
                    breaks_dia = breaks_categorizados.get(id_usuario, {}).get(fecha, [])
                    if not breaks_dia:
                        dia_info["estado"] = "pendiente_revision"
                        dia_info["observaciones"].append(f"Múltiples registros ({n}). Pendiente categorizar breaks.")
                        resumen["incompletos"] += 1
                    else:
                        dia_info["observaciones"].append(f"Día con {len(breaks_dia)} breaks categorizados.")

                entradas = [m for m in marcaciones if m.get("tipo") == "Entrada"]
                salidas = [m for m in marcaciones if m.get("tipo") == "Salida"]
                if entradas:
                    dia_info["llegada"] = entradas[0]["hora"].strftime("%H:%M")
                elif marcaciones:
                    dia_info["llegada"] = marcaciones[0]["hora"].strftime("%H:%M")

                if salidas:
                    dia_info["salida"] = salidas[-1]["hora"].strftime("%H:%M")
                elif len(marcaciones) > 1:
                    dia_info["salida"] = marcaciones[-1]["hora"].strftime("%H:%M")

                if len(marcaciones) >= 2:
                    primera_dt = marcaciones[0]["datetime"]
                    ultima_dt = marcaciones[-1]["datetime"]
                    if ultima_dt > primera_dt:
                        td_min = int((ultima_dt - primera_dt).total_seconds() / 60)
                        h_td, m_td = divmod(td_min, 60)
                        dia_info["tiempo_dentro"] = f"{h_td}h {m_td:02d}m"

                dia_info["tiempo_neto_min"] = _calcular_tiempo_neto_min(marcaciones)

            else:
                primera = marcaciones[0]
                ultima  = marcaciones[-1]
                entradas = [m for m in marcaciones if m.get("tipo") == "Entrada"]
                salidas = [m for m in marcaciones if m.get("tipo") == "Salida"]

                if entradas:
                    dia_info["llegada"] = entradas[0]["hora"].strftime("%H:%M")
                elif marcaciones:
                    dia_info["llegada"] = marcaciones[0]["hora"].strftime("%H:%M")

                if salidas:
                    dia_info["salida"] = salidas[-1]["hora"].strftime("%H:%M")
                elif len(marcaciones) > 1:
                    dia_info["salida"] = marcaciones[-1]["hora"].strftime("%H:%M")

                if len(marcaciones) >= 2:
                    primera_dt = marcaciones[0]["datetime"]
                    ultima_dt = marcaciones[-1]["datetime"]
                    if ultima_dt > primera_dt:
                        td_min = int((ultima_dt - primera_dt).total_seconds() / 60)
                        h_td, m_td = divmod(td_min, 60)
                        dia_info["tiempo_dentro"] = f"{h_td}h {m_td:02d}m"

                    just_tar = obtener_justificacion_persona(justificaciones, id_usuario, fecha, "tardanza")
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
                                    dia_info["estado"] = "leve"
                                dia_info["observaciones"].append(f"Llegada autorizada hasta {hora_permitida}")
                        else:
                            dia_info["justificado"] = True
                            resumen["justificadas"] += 1
                            if dia_info["estado"] == "ok":
                                dia_info["estado"] = "leve"
                            dia_info["observaciones"].append(f"Tardanza JUSTIFICADA: {just_tar.get('motivo','(Sin motivo)')}")

                if ultima["tipo"] == "Salida":
                    dia_info["salida"] = ultima["hora"].strftime("%H:%M")

                just_alm = obtener_justificacion_persona(justificaciones, id_usuario, fecha, "almuerzo")
                just_per = obtener_justificacion_persona(justificaciones, id_usuario, fecha, "permiso")

                if just_per and just_per.get("estado") == "aprobada":
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
                            if found_per:
                                break

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

                                    if duracion > max_almuerzo_per:
                                        if just_alm:
                                            if duracion <= limite_alm:
                                                dia_info["observaciones"].append(f"Exceso almuerzo (+{duracion - max_almuerzo_per}m) JUSTIFICADO: {just_alm.get('motivo','')}")
                                                dia_info["justificado"] = True
                                                resumen["justificadas"] += 1
                                                if dia_info["estado"] == "ok":
                                                    dia_info["estado"] = "leve"
                                            else:
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

                if n == 2 and max_almuerzo_per > 0:
                    td_min = int((ultima["datetime"] - primera["datetime"]).total_seconds() / 60)
                    if td_min > 360:
                        dia_info["tiempo_neto_min"] = max(0, dia_info["tiempo_neto_min"] - max_almuerzo_per)
                        dia_info["observaciones"].append(f"Almuerzo deducido autom. (-{max_almuerzo_per}m) por falta de marcaciones.")

                hora_salida_prog = info.get("hora_salida")
                if hora_salida_prog and len(marcaciones) >= 2:
                    just_salida = obtener_justificacion_persona(justificaciones, id_usuario, fecha, "salida_anticipada")
                    ultima_salida = None
                    for m in reversed(marcaciones):
                        if m["tipo"] == "Salida":
                            ultima_salida = m["hora"]
                            break

                    if ultima_salida:
                        if not just_salida:
                            h_salida_t = datetime.strptime(hora_salida_prog, "%H:%M").time()
                            salida_diff = -_minutos_diferencia(h_salida_t, ultima_salida)

                            if salida_diff > 0:
                                if salida_diff > MARGEN_LEVE_MIN:
                                    if dia_info["estado"] in ("ok", "leve", "tardanza_leve"):
                                        dia_info["estado"] = "salida_anticipada_severa"
                                    dia_info["observaciones"].append(
                                        f"Salida ant. severa (-{salida_diff}m sobre {hora_salida_prog})"
                                    )
                                    resumen["salida_anticipada_severa"] += 1
                                else:
                                    if dia_info["estado"] == "ok":
                                        dia_info["estado"] = "salida_anticipada_leve"
                                    dia_info["observaciones"].append(
                                        f"Salida ant. leve (-{salida_diff}m sobre {hora_salida_prog})"
                                    )
                                    resumen["salida_anticipada_leve"] += 1
                        else:
                            hora_permitida = just_salida.get("hora_permitida")
                            if hora_permitida:
                                h_permitida_t = datetime.strptime(hora_permitida, "%H:%M").time()
                                salida_diff = -_minutos_diferencia(h_permitida_t, ultima_salida)

                                if salida_diff > 0:
                                    if dia_info["estado"] in ("ok", "leve", "tardanza_leve"):
                                        dia_info["estado"] = "salida_anticipada_severa"
                                    dia_info["observaciones"].append(
                                        f"Salida ant. NO JUSTIF. (-{salida_diff}m, auth. {hora_permitida})"
                                    )
                                    resumen["salida_anticipada_severa"] += 1
                                else:
                                    dia_info["justificado"] = True
                                    resumen["justificadas"] += 1
                                    if dia_info["estado"] == "ok":
                                        dia_info["estado"] = "salida_anticipada_leve"
                                    dia_info["observaciones"].append(f"Salida JUSTIFICADA: {just_salida.get('motivo','(Sin motivo)')}")
                            else:
                                dia_info["justificado"] = True
                                resumen["justificadas"] += 1
                                if dia_info["estado"] == "ok":
                                    dia_info["estado"] = "salida_anticipada_leve"
                                dia_info["observaciones"].append(f"Salida JUSTIFICADA: {just_salida.get('motivo','(Sin motivo)')}")

            todos_los_dias.append(dia_info)
            if mostrar_todos or dia_info["estado"] != "ok" or dia_info["observaciones"]:
                dias_list.append(dia_info)

        if fecha_inicio and fecha_fin:
            hoy = date.today()
            fecha_fin_evaluacion = min(fecha_fin, hoy - timedelta(days=1))
            d = fecha_inicio
            while d <= fecha_fin_evaluacion:
                if d not in por_fecha and d not in feriados:
                    info = _get_info_dia(horario_persona, d)
                    if info["trabaja"]:
                        just_aus = obtener_justificacion_persona(justificaciones, id_usuario, d, "ausencia")

                        dia_aus: dict[str, Any] = {
                            "fecha":             d,
                            "llegada":           None,
                            "salida":            None,
                            "hora_programada":   info["hora_entrada"],
                            "almuerzo_duracion": None,
                            "almuerzo_salida":   None,
                            "almuerzo_regreso":  None,
                            "almuerzo_exceso":   None,
                            "tiempo_dentro":     None,
                            "n_registros":       0,
                            "detalle_registros": "",
                            "estado":            "ausente",
                            "justificado":       bool(just_aus),
                        }

                        if not just_aus:
                            resumen["ausencias"] += 1
                            resumen["total_dias"] += 1
                            dia_aus["observaciones"] = [f"AUSENTE — sin marcaciones (Prog: {info['hora_entrada']})"]
                        else:
                            resumen["justificadas"] += 1
                            resumen["total_dias"] += 1
                            dia_aus["observaciones"] = [f"AUSENCIA JUSTIFICADA: {just_aus.get('motivo','(Sin motivo)')}"]

                        todos_los_dias.append(dia_aus)
                        dias_list.append(dia_aus)
                d += timedelta(days=1)
            dias_list.sort(key=lambda x: x["fecha"])
            todos_los_dias.sort(key=lambda x: x["fecha"])

        if (verificar_horas or mostrar_tiempo_extra) and (horario_persona.get("horas_semana") or horario_persona.get("horas_mes")):
            _calcular_horas_contrato(horario_persona, todos_los_dias, fecha_inicio, fecha_fin, feriados, resumen)

        if resumen.get("total_dias", 0) > 0:
            resultado[nombre] = {
                "dias":          dias_list,
                "resumen":       resumen,
                "sin_novedades": not dias_list,
            }

    return resultado
