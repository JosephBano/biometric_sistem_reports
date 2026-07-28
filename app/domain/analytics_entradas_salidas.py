"""
Servicio de analitica entradas/salidas por persona (`app/domain/analytics_entradas_salidas.py`).

Puro (sin acceso directo a Flask): recibe parametros, devuelve dicts.
La capa `app/web/analytics_bp.py` envuelve esto con RBAC, alcance,
auditoria y serializacion a JSON.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import date
from typing import Optional

from db.queries.asistencias_entradas_salidas import (
    contar_marcaciones_por_persona,
    grupos_funcionales_disponibles,
    listar_marcaciones_por_persona,
    normalizar_tipo_marcacion,
)


def consultar_entradas_salidas(
    persona_id: str,
    fecha_inicio: date,
    fecha_fin: date,
    page: int = 1,
    per_page: int = 50,
    schema: str = None,
) -> dict:
    """
    Orquestacion del caso de uso entradas/salidas para una persona.

    Valida parametros, consulta BD, pagina y devuelve:
      {
        "persona_id": str,
        "fecha_inicio": str,
        "fecha_fin": str,
        "page": int,
        "per_page": int,
        "total": int,
        "total_pages": int,
        "marcaciones": list[dict],
        "grupos_funcionales_disponibles": bool,
      }
    """
    if not persona_id:
        raise ValueError("persona_id es requerido")
    # `persona_id` se interpola como uuid en SQL: sin esta validación, un
    # valor no-UUID (p. ej. el ID del biométrico, "30") llega a Postgres y
    # revienta con DataError → 500. Validando aquí, el blueprint lo
    # traduce a un 400 con mensaje útil.
    try:
        _uuid.UUID(str(persona_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(
            f"persona_id debe ser un UUID; se recibió {persona_id!r}. "
            "Si tienes el ID del biométrico, búscalo primero en Personas."
        ) from None
    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio debe ser <= fecha_fin")
    if (fecha_fin - fecha_inicio).days > 366:
        raise ValueError("El rango no puede superar 366 dias")
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 50
    if per_page > 200:
        per_page = 200

    total = contar_marcaciones_por_persona(persona_id, fecha_inicio, fecha_fin, schema=schema)
    marcaciones = listar_marcaciones_por_persona(
        persona_id, fecha_inicio, fecha_fin, page=page, per_page=per_page, schema=schema,
    )
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    # Convertir datetime/date a string para JSON
    marc_json = []
    for m in marcaciones:
        marc_json.append({
            "id_usuario":  m["id_usuario"],
            "nombre":      m["nombre"],
            "datetime":    m["datetime"].isoformat() if m.get("datetime") else None,
            "fecha":       m["fecha"].isoformat() if hasattr(m.get("fecha"), "isoformat") else str(m.get("fecha")),
            "hora":        m["hora"].strftime("%H:%M:%S") if m.get("hora") else None,
            "tipo":        m["tipo_norm"],
            "tipo_raw":    m["tipo_raw"],
            "fuente":      m["fuente"],
            "dispositivo_id": m["dispositivo_id"],
        })

    return {
        "persona_id": persona_id,
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "marcaciones": marc_json,
        "grupos_funcionales_disponibles": grupos_funcionales_disponibles(schema),
    }


__all__ = ["consultar_entradas_salidas"]