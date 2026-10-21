"""
Modelos de datos, tipos y configuraciones para el motor de reportes (`app.domain.reports.models`).
"""
from __future__ import annotations

from datetime import date, time
from typing import Any, NotRequired, TypedDict

# ══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN POR DEFECTO
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG: dict[str, Any] = {
    # Minutos máximos entre dos marcaciones consecutivas iguales
    # para considerar la segunda como duplicado por error
    "duplicado_min": 0.5,
    # Personas a excluir del reporte (por nombre exacto o parcial)
    "excluidos": [],
}

# Tolerancia fija de entrada: 0–5 min → tardanza leve, >5 min → tardanza severa
MARGEN_LEVE_MIN: int = 5

# Filtros por defecto para los reportes (secciones y columnas a incluir).
DEFAULT_FILTROS: dict[str, bool] = {
    "mostrar_ausencias":         True,
    "mostrar_tardanza_severa":   True,
    "mostrar_tardanza_leve":     True,
    "mostrar_almuerzo":          True,
    "mostrar_incompletos":       True,
    "mostrar_salida_anticipada": True,
    "mostrar_todos_los_dias":    False,
    "columna_tiempo_dentro":     False,
    "reporte_sin_horario":       False,
    "reporte_todos_usuarios":    False,
    "verificar_horas":           False,
    "mostrar_tiempo_extra":      False,
}


# ══════════════════════════════════════════════════════════════════════════
# TIPOS Y MODELOS ESTRUCTURADOS
# ══════════════════════════════════════════════════════════════════════════

class MarcacionDetalle(TypedDict, total=False):
    hora: str
    tipo: str
    tipo_raw: str
    fuente: str
    dispositivo_id: str


class DiaInfo(TypedDict, total=False):
    fecha: date | str
    llegada: str | None
    salida: str | None
    hora_programada: str | None
    almuerzo_duracion: int | None
    almuerzo_salida: str | None
    almuerzo_regreso: str | None
    almuerzo_exceso: int | None
    tiempo_dentro: str | None
    tiempo_neto_min: int
    permiso_salida: str | None
    permiso_retorno: str | None
    permiso_duracion: int | None
    permiso_neto_min: NotRequired[int]
    permiso_alm_min: NotRequired[int]
    n_registros: int
    detalle_registros: str
    observaciones: list[str]
    estado: str
    marcaciones: list[MarcacionDetalle]
    justificado: NotRequired[bool]
    horario_origen: NotRequired[str | None]
    plantilla_id: NotRequired[int | None]
    horas_trabajadas: NotRequired[str | None]


class ResumenAnalisis(TypedDict, total=False):
    total_dias: int
    dias_laborables: NotRequired[int]
    tardanza_leve: int
    tardanza_severa: int
    almuerzo_largo: int
    incompletos: int
    ausencias: int
    justificadas: int
    salida_anticipada_leve: int
    salida_anticipada_severa: int
    permiso_retorno_tardio: NotRequired[int]
    permiso_retorno_tardio_leve: NotRequired[int]
    permiso_sin_retorno: NotRequired[int]
    horas_contrato_tipo: NotRequired[str]
    horas_contrato_valor: NotRequired[float]
    total_neto_min: NotRequired[int]
    deficit_horas_min: NotRequired[int]
    excedente_horas_min: NotRequired[int]
    detalle_semanas: NotRequired[list[dict[str, Any]]]


class ResultadoPersona(TypedDict, total=False):
    dias: list[DiaInfo]
    resumen: ResumenAnalisis
    sin_novedades: bool
    horario_info: NotRequired[dict[str, str]]


class InfoDiaHorario(TypedDict):
    trabaja: bool
    hora_entrada: str | None
    hora_salida: str | None
    almuerzo_min: int


class RegistroMarcacion(TypedDict, total=False):
    nombre: str
    datetime: Any
    fecha: date
    hora: time
    tipo: str
    id_usuario: NotRequired[Any]
    persona_id: NotRequired[str | None]


# ══════════════════════════════════════════════════════════════════════════
# UTILIDADES DE PARSEO Y FORMATO
# ══════════════════════════════════════════════════════════════════════════

def _fmt_horas(minutos: int | None) -> str:
    """Formatea minutos como 'Xh Ym'."""
    if minutos is None:
        return "—"
    signo = "-" if minutos < 0 else ""
    abs_min = abs(int(minutos))
    h, m = divmod(abs_min, 60)
    if h > 0:
        return f"{signo}{h}h {int(m)}m"
    return f"{signo}{int(m)}m"


def parse_config(data: dict[str, Any]) -> dict[str, Any]:
    """Extrae y normaliza la config de generación de reportes del request."""
    return {
        "duplicado_min": DEFAULT_CONFIG["duplicado_min"],
        "excluidos":     data.get("excluidos", []) or [],
    }
