"""
Acceso a datos para el dominio periods (`app/domain/periods.py`).

Re-exporta funciones de `db` (capa de datos) para que `app/web/periods_bp.py`
no importe `db` directamente, cumpliendo la regla de capas del ADR-0001
(`app/web/*` solo importa de `app/domain/*`).
"""
from __future__ import annotations

from db import (
    agregar_personas_a_periodo_bulk,
    archivar_periodo,
    calcular_asistencia_periodo,
    cerrar_periodo,
    crear_periodo,
    crear_persona,
    eliminar_periodo,
    get_periodo,
    listar_grupos,
    listar_grupos_funcionales,
    listar_periodos_activos,
    listar_periodos_historial,
    listar_personas,
    procesar_csv_personas_periodo,
    remover_persona_de_periodo,
)

def reordenar_a_apellido_nombre(nombre: str) -> str:
    """
    Normaliza el nombre a formato 'Apellidos Nombres' para visualización y ordenamiento
    institucional cuando los datos provienen en formato 'Nombres Apellidos'.
    """
    if not nombre:
        return ""
    nombre = nombre.strip()
    # Si ya contiene coma "Acosta, Alejandra", retornar "Acosta Alejandra"
    if "," in nombre:
        partes = [p.strip() for p in nombre.split(",", 1)]
        return f"{partes[0]} {partes[1]}".strip()

    partes = nombre.split()
    if len(partes) == 2:
        # [Nombre, Apellido] -> "Apellido Nombre" (ej: "Alejandra Acosta" -> "Acosta Alejandra")
        return f"{partes[1]} {partes[0]}"
    elif len(partes) == 3:
        # [Nombre, Apellido1, Apellido2] -> "Apellido1 Apellido2 Nombre"
        return f"{partes[1]} {partes[2]} {partes[0]}"
    elif len(partes) >= 4:
        # [Nombre1, Nombre2, Apellido1, Apellido2] -> "Apellido1 Apellido2 Nombre1 Nombre2"
        return f"{partes[2]} {partes[3]} {partes[0]} {partes[1]}"
    return nombre


__all__ = [
    "agregar_personas_a_periodo_bulk",
    "archivar_periodo",
    "calcular_asistencia_periodo",
    "cerrar_periodo",
    "crear_periodo",
    "crear_persona",
    "eliminar_periodo",
    "get_periodo",
    "listar_grupos",
    "listar_grupos_funcionales",
    "listar_periodos_activos",
    "listar_periodos_historial",
    "listar_personas",
    "procesar_csv_personas_periodo",
    "remover_persona_de_periodo",
    "reordenar_a_apellido_nombre",
]
