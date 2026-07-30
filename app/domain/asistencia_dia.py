"""
Resumen diario de marcaciones (`app/domain/asistencia_dia.py`).

Módulo PURO: sin Flask, sin base de datos, sin reloj. Recibe marcaciones,
devuelve una fila por día con tiempos calculados y el estado del marcaje.

Dos decisiones de diseño que conviene tener presentes al leer el código
(spec: docs/superpowers/specs/2026-07-30-resumen-diario-entradas-salidas-design.md):

1. Los tiempos se calculan **por posición**, ignorando el campo `tipo`. El
   biométrico manda tipos poco confiables (hay días con dos "Salida" seguidas
   y ninguna entrada); la hora, en cambio, siempre es correcta. El estado
   avisa aparte de que la secuencia es sospechosa.

2. El agrupamiento es por **fecha calendario**. Un turno nocturno queda
   partido en dos días. Con el horario actual (07:00–14:30) no aplica.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

# Prioridad de estados: se reporta el primero que se cumpla. Los duplicados
# consecutivos van antes que `empieza_salida` porque son el diagnóstico más
# accionable cuando el día cumple ambas condiciones.
ESTADO_OK = "ok"
ESTADO_SIN_MARCACIONES = "sin_marcaciones"
ESTADO_TIPO_DESCONOCIDO = "tipo_desconocido"
ESTADO_DOS_ENTRADAS = "dos_entradas"
ESTADO_DOS_SALIDAS = "dos_salidas"
ESTADO_EMPIEZA_SALIDA = "empieza_salida"
ESTADO_IMPAR = "impar"

# Estados que la UI pinta como advertencia.
ESTADOS_CON_ALERTA = frozenset({
    ESTADO_TIPO_DESCONOCIDO,
    ESTADO_DOS_ENTRADAS,
    ESTADO_DOS_SALIDAS,
    ESTADO_EMPIEZA_SALIDA,
    ESTADO_IMPAR,
})


def formatear_duracion(segundos: int | None) -> str | None:
    """
    Convierte segundos en `"7h 16m"`. Trunca, no redondea: mostrar 17m para
    16m 53s haría que los minutos no cuadren al sumar días.
    """
    if segundos is None:
        return None
    horas, resto = divmod(int(segundos), 3600)
    return f"{horas}h {resto // 60:02d}m"


def _hora(marcacion: dict) -> str:
    return marcacion["datetime"].strftime("%H:%M:%S")


def _evaluar_secuencia(marcaciones: list[dict]) -> tuple[str, str]:
    """
    Clasifica la secuencia de tipos del día. Retorna `(estado, mensaje)`.

    `marcaciones` viene ordenada por hora ascendente y no vacía.
    """
    tipos = [m.get("tipo") for m in marcaciones]

    for i, tipo in enumerate(tipos):
        if tipo not in ("entrada", "salida"):
            crudo = marcaciones[i].get("tipo_raw") or tipo
            return (
                ESTADO_TIPO_DESCONOCIDO,
                f"Tipo no reconocido ({crudo}) a las {_hora(marcaciones[i])}",
            )

    for i in range(1, len(tipos)):
        if tipos[i] == tipos[i - 1]:
            estado = ESTADO_DOS_ENTRADAS if tipos[i] == "entrada" else ESTADO_DOS_SALIDAS
            etiqueta = "entradas" if tipos[i] == "entrada" else "salidas"
            return (
                estado,
                f"Dos {etiqueta} seguidas a las {_hora(marcaciones[i])}",
            )

    if tipos[0] == "salida":
        return (
            ESTADO_EMPIEZA_SALIDA,
            f"El día empieza con una salida ({_hora(marcaciones[0])})",
        )

    if len(tipos) % 2 == 1:
        falta = "salida" if tipos[-1] == "entrada" else "entrada"
        return (
            ESTADO_IMPAR,
            f"Marcajes impares ({len(tipos)}): falta un marcaje de {falta}",
        )

    return (ESTADO_OK, "Marcaje correcto")


def resumir_dia(fecha: date, marcaciones: list[dict]) -> dict:
    """
    Resume las marcaciones de un día en una fila de la tabla.

    Args:
        fecha: día calendario que representa la fila.
        marcaciones: marcaciones de ese día, cada una con `datetime`, `tipo`
            (ya normalizado a entrada/salida/otro) y opcionalmente `tipo_raw`
            y `fuente`. No necesitan venir ordenadas.

    Returns:
        dict con las columnas de la tabla más `marcaciones` para el popup.
    """
    ordenadas = sorted(marcaciones, key=lambda m: m["datetime"])

    if not ordenadas:
        estado, mensaje = ESTADO_SIN_MARCACIONES, "Sin marcaciones"
        permanencia_seg = efectivo_seg = None
        primer = ultimo = None
    else:
        estado, mensaje = _evaluar_secuencia(ordenadas)
        primer = _hora(ordenadas[0])
        # Con un solo marcaje no hay "última": mostrar la misma hora en ambas
        # columnas sugeriría una jornada de duración cero que no ocurrió.
        ultimo = _hora(ordenadas[-1]) if len(ordenadas) >= 2 else None

        if len(ordenadas) >= 2:
            permanencia_seg = int(
                (ordenadas[-1]["datetime"] - ordenadas[0]["datetime"]).total_seconds()
            )
            efectivo_seg = sum(
                int((ordenadas[i + 1]["datetime"] - ordenadas[i]["datetime"]).total_seconds())
                for i in range(0, len(ordenadas) - 1, 2)
            )
        else:
            permanencia_seg = efectivo_seg = None

    return {
        "fecha": fecha.isoformat(),
        "primer_marcaje": primer,
        "ultimo_marcaje": ultimo,
        "permanencia_segundos": permanencia_seg,
        "permanencia": formatear_duracion(permanencia_seg),
        "efectivo_segundos": efectivo_seg,
        "efectivo": formatear_duracion(efectivo_seg),
        "total_marcaciones": len(ordenadas),
        "estado": estado,
        "mensaje": mensaje,
        "con_alerta": estado in ESTADOS_CON_ALERTA,
        "marcaciones": [
            {
                "hora": _hora(m),
                "tipo": m.get("tipo"),
                "tipo_raw": m.get("tipo_raw"),
                "fuente": m.get("fuente"),
            }
            for m in ordenadas
        ],
    }


def resumir_rango(
    fecha_inicio: date,
    fecha_fin: date,
    marcaciones: list[dict],
) -> list[dict]:
    """
    Agrupa las marcaciones por fecha calendario y devuelve una fila por cada
    día del rango, incluidos los que no tienen ninguna marcación.

    Las marcaciones fuera del rango se descartan. Si `fecha_inicio` es
    posterior a `fecha_fin`, devuelve lista vacía.
    """
    por_fecha: dict[date, list[dict]] = {}
    for m in marcaciones:
        dia = m["datetime"].date() if isinstance(m["datetime"], datetime) else m["datetime"]
        if fecha_inicio <= dia <= fecha_fin:
            por_fecha.setdefault(dia, []).append(m)

    filas = []
    dia = fecha_inicio
    while dia <= fecha_fin:
        filas.append(resumir_dia(dia, por_fecha.get(dia, [])))
        dia += timedelta(days=1)
    return filas


__all__ = [
    "ESTADOS_CON_ALERTA",
    "formatear_duracion",
    "resumir_dia",
    "resumir_rango",
]
