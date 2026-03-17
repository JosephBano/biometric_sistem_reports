"""Queries de feriados. Sin cambios conceptuales respecto al sistema SQLite."""

from datetime import date as _date
from sqlalchemy import text

from db.connection import get_connection


def insertar_feriado(fecha: str, descripcion: str, tipo: str = "nacional") -> dict:
    """Inserta o reemplaza un feriado. fecha debe ser 'YYYY-MM-DD'."""
    with get_connection() as conn:
        conn.execute(
            text("""
                INSERT INTO feriados (fecha, descripcion, tipo)
                VALUES (CAST(:fecha AS date), :descripcion, :tipo)
                ON CONFLICT (fecha) DO UPDATE SET
                    descripcion = EXCLUDED.descripcion,
                    tipo        = EXCLUDED.tipo
            """),
            {"fecha": fecha, "descripcion": descripcion, "tipo": tipo},
        )
        row = conn.execute(
            text("SELECT TO_CHAR(fecha,'YYYY-MM-DD') AS fecha, descripcion, tipo FROM feriados WHERE fecha = CAST(:fecha AS date)"),
            {"fecha": fecha},
        ).fetchone()
    return dict(row._mapping) if row else {}


def get_feriados(fecha_inicio=None, fecha_fin=None) -> list[dict]:
    """Retorna feriados en el rango dado (o todos si no se especifica)."""
    with get_connection() as conn:
        if fecha_inicio and fecha_fin:
            fi = fecha_inicio.strftime("%Y-%m-%d") if hasattr(fecha_inicio, "strftime") else fecha_inicio
            ff = fecha_fin.strftime("%Y-%m-%d") if hasattr(fecha_fin, "strftime") else fecha_fin
            rows = conn.execute(
                text("""
                    SELECT TO_CHAR(fecha,'YYYY-MM-DD') AS fecha, descripcion, tipo
                    FROM feriados
                    WHERE fecha >= CAST(:fi AS date) AND fecha <= CAST(:ff AS date)
                    ORDER BY fecha
                """),
                {"fi": fi, "ff": ff},
            ).fetchall()
        else:
            rows = conn.execute(
                text("SELECT TO_CHAR(fecha,'YYYY-MM-DD') AS fecha, descripcion, tipo FROM feriados ORDER BY fecha")
            ).fetchall()
    return [dict(r._mapping) for r in rows]


def get_feriados_set(fecha_inicio=None, fecha_fin=None) -> set:
    """Retorna un set de objetos date para lookup rápido en el análisis."""
    lista = get_feriados(fecha_inicio, fecha_fin)
    result = set()
    for f in lista:
        try:
            y, m, d = f["fecha"].split("-")
            result.add(_date(int(y), int(m), int(d)))
        except (ValueError, KeyError):
            pass
    return result


def eliminar_feriado(fecha: str) -> bool:
    """Elimina un feriado por su fecha. Retorna True si existía."""
    with get_connection() as conn:
        result = conn.execute(
            text("DELETE FROM feriados WHERE fecha = CAST(:fecha AS date)"),
            {"fecha": fecha},
        )
    return result.rowcount > 0


def importar_feriados_csv(filepath: str) -> int:
    """
    Importa feriados desde un CSV con columnas: fecha, descripcion, tipo.
    Retorna la cantidad de feriados cargados.
    """
    import csv as _csv
    count = 0
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            fecha = str(row.get("fecha", "")).strip()
            desc = str(row.get("descripcion", "")).strip()
            tipo = str(row.get("tipo", "nacional")).strip() or "nacional"
            if fecha and desc:
                insertar_feriado(fecha, desc, tipo)
                count += 1
    return count
