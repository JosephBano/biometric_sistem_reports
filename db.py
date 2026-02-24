"""
Capa de acceso a la base de datos SQLite.
Todas las rutas se leen desde variables de entorno.
"""

import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "data/asistencias.db")


# ══════════════════════════════════════════════════════════════════════════
# CONEXIÓN
# ══════════════════════════════════════════════════════════════════════════

@contextmanager
def _conn():
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# INICIALIZACIÓN
# ══════════════════════════════════════════════════════════════════════════

def init_db():
    """Crea las tablas si no existen. Seguro para llamar múltiples veces."""
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS asistencias (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario   TEXT    NOT NULL,
                nombre       TEXT    NOT NULL,
                fecha_hora   TEXT    NOT NULL,
                punch_raw    INTEGER,
                tipo         TEXT    NOT NULL,
                fuente       TEXT    NOT NULL DEFAULT 'zk',
                creado_en    TEXT    DEFAULT (datetime('now')),
                UNIQUE (id_usuario, fecha_hora)
            );

            CREATE TABLE IF NOT EXISTS usuarios_zk (
                id_usuario     TEXT PRIMARY KEY,
                nombre         TEXT NOT NULL,
                privilegio     INTEGER,
                actualizado_en TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_sync          TEXT    DEFAULT (datetime('now')),
                fecha_inicio_sync   TEXT,
                fecha_fin_sync      TEXT,
                registros_obtenidos INTEGER DEFAULT 0,
                registros_nuevos    INTEGER DEFAULT 0,
                exito               INTEGER,
                error_detalle       TEXT
            );

            CREATE TABLE IF NOT EXISTS horarios_personal (
                id_usuario     TEXT    PRIMARY KEY,
                nombre         TEXT    NOT NULL,
                lunes          TEXT,
                martes         TEXT,
                miercoles      TEXT,
                jueves         TEXT,
                viernes        TEXT,
                sabado         TEXT,
                domingo        TEXT,
                almuerzo_min   INTEGER DEFAULT 0,
                notas          TEXT,
                fuente         TEXT,
                actualizado_en TEXT    DEFAULT (datetime('now'))
            );
        """)


# ══════════════════════════════════════════════════════════════════════════
# USUARIOS
# ══════════════════════════════════════════════════════════════════════════

def upsert_usuarios(usuarios: list[dict]):
    """Inserta o actualiza usuarios del dispositivo."""
    with _conn() as conn:
        for u in usuarios:
            conn.execute("""
                INSERT INTO usuarios_zk (id_usuario, nombre, privilegio, actualizado_en)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(id_usuario) DO UPDATE SET
                    nombre         = excluded.nombre,
                    privilegio     = excluded.privilegio,
                    actualizado_en = datetime('now')
            """, (str(u["id_usuario"]), str(u["nombre"]).strip(), u.get("privilegio", 0)))


# ══════════════════════════════════════════════════════════════════════════
# ASISTENCIAS
# ══════════════════════════════════════════════════════════════════════════

def insertar_asistencias(registros: list[dict]) -> int:
    """
    Inserta registros ignorando duplicados (UNIQUE id_usuario + fecha_hora).
    Retorna la cantidad de filas realmente insertadas.
    """
    nuevos = 0
    with _conn() as conn:
        for r in registros:
            try:
                conn.execute("""
                    INSERT INTO asistencias
                        (id_usuario, nombre, fecha_hora, punch_raw, tipo, fuente)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(r["id_usuario"]),
                    r["nombre"],
                    r["fecha_hora"],
                    r.get("punch_raw"),
                    r["tipo"],
                    r.get("fuente", "zk"),
                ))
                nuevos += 1
            except sqlite3.IntegrityError:
                pass  # Duplicado, ignorar
    return nuevos


def consultar_asistencias(fecha_inicio, fecha_fin) -> list[dict]:
    """
    Devuelve registros del rango en el formato que espera script.py:
    { id_usuario, nombre, datetime, fecha, hora, tipo }
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id_usuario, nombre, fecha_hora, tipo
            FROM asistencias
            WHERE fecha_hora >= ? AND fecha_hora <= ?
            ORDER BY nombre, fecha_hora
        """, (
            f"{fecha_inicio.strftime('%Y-%m-%d')} 00:00:00",
            f"{fecha_fin.strftime('%Y-%m-%d')} 23:59:59",
        )).fetchall()

    registros = []
    for row in rows:
        dt = datetime.fromisoformat(row["fecha_hora"])
        registros.append({
            "id_usuario": row["id_usuario"],
            "nombre":     row["nombre"],
            "datetime":   dt,
            "fecha":      dt.date(),
            "hora":       dt.time(),
            "tipo":       row["tipo"],
        })
    return registros


def get_personas(fecha_inicio, fecha_fin) -> list[str]:
    """Devuelve nombres únicos en el rango de fechas."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT nombre
            FROM asistencias
            WHERE fecha_hora >= ? AND fecha_hora <= ?
            ORDER BY nombre
        """, (
            f"{fecha_inicio.strftime('%Y-%m-%d')} 00:00:00",
            f"{fecha_fin.strftime('%Y-%m-%d')} 23:59:59",
        )).fetchall()
    return [row["nombre"] for row in rows]


# ══════════════════════════════════════════════════════════════════════════
# ESTADO Y LOG
# ══════════════════════════════════════════════════════════════════════════

def get_estado() -> dict:
    """Retorna estadísticas generales de la base de datos."""
    with _conn() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM asistencias").fetchone()[0]
        personas = conn.execute("SELECT COUNT(DISTINCT nombre) FROM asistencias").fetchone()[0]
        ultima   = conn.execute("""
            SELECT fecha_sync, registros_nuevos, exito, error_detalle
            FROM sync_log ORDER BY id DESC LIMIT 1
        """).fetchone()
    return {
        "total_registros": total,
        "personas_en_db":  personas,
        "ultima_sync":     dict(ultima) if ultima else None,
    }


def registrar_sync(
    fecha_inicio,
    fecha_fin,
    obtenidos: int,
    nuevos: int,
    exito: bool,
    error: str = None,
):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO sync_log
                (fecha_inicio_sync, fecha_fin_sync,
                 registros_obtenidos, registros_nuevos, exito, error_detalle)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            fecha_inicio.isoformat() if fecha_inicio else None,
            fecha_fin.isoformat()    if fecha_fin    else None,
            obtenidos,
            nuevos,
            1 if exito else 0,
            error,
        ))


# ══════════════════════════════════════════════════════════════════════════
# HORARIOS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════

def upsert_horarios(horarios: list[dict], fuente: str = "") -> int:
    """
    Inserta o reemplaza los horarios del lote.
    El campo 'id_usuario' es la clave primaria.

    Args:
        horarios: Lista de dicts con id_usuario, nombre, lunes..sabado,
                  almuerzo_min, notas.
        fuente:   Nombre del archivo origen (para auditoría).

    Returns:
        Cantidad de filas procesadas.
    """
    with _conn() as conn:
        for h in horarios:
            conn.execute("""
                INSERT INTO horarios_personal
                    (id_usuario, nombre, lunes, martes, miercoles, jueves,
                     viernes, sabado, domingo, almuerzo_min, notas, fuente,
                     actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id_usuario) DO UPDATE SET
                    nombre        = excluded.nombre,
                    lunes         = excluded.lunes,
                    martes        = excluded.martes,
                    miercoles     = excluded.miercoles,
                    jueves        = excluded.jueves,
                    viernes       = excluded.viernes,
                    sabado        = excluded.sabado,
                    domingo       = excluded.domingo,
                    almuerzo_min  = excluded.almuerzo_min,
                    notas         = excluded.notas,
                    fuente        = excluded.fuente,
                    actualizado_en = datetime('now')
            """, (
                str(h["id_usuario"]),
                h["nombre"],
                h.get("lunes"),
                h.get("martes"),
                h.get("miercoles"),
                h.get("jueves"),
                h.get("viernes"),
                h.get("sabado"),
                h.get("domingo"),
                int(h.get("almuerzo_min", 0)),
                h.get("notas", ""),
                fuente,
            ))
    return len(horarios)


def get_horarios() -> dict:
    """
    Retorna todos los horarios cargados en dos índices:
      "by_id"     → {id_usuario: horario_dict}
      "by_nombre" → {NOMBRE_UPPER: horario_dict}

    El índice by_nombre permite buscar cuando los registros provienen
    de un archivo .xlsx y no tienen id_usuario.
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id_usuario, nombre, lunes, martes, miercoles, jueves,
                   viernes, sabado, domingo, almuerzo_min, notas
            FROM horarios_personal
        """).fetchall()

    by_id     = {}
    by_nombre = {}

    for row in rows:
        h = dict(row)
        by_id[h["id_usuario"]]          = h
        by_nombre[h["nombre"].upper()]   = h

    return {"by_id": by_id, "by_nombre": by_nombre}


def get_ids_usuarios_zk() -> set:
    """Retorna el conjunto de id_usuario registrados en el dispositivo ZK."""
    with _conn() as conn:
        rows = conn.execute("SELECT id_usuario FROM usuarios_zk").fetchall()
    return {row["id_usuario"] for row in rows}


def get_estado_horarios() -> dict:
    """
    Retorna un resumen del estado de los horarios cargados.
    """
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM horarios_personal"
        ).fetchone()[0]
        ultima = conn.execute("""
            SELECT fuente, actualizado_en
            FROM horarios_personal
            ORDER BY actualizado_en DESC
            LIMIT 1
        """).fetchone()

    return {
        "total":          total,
        "fuente":         ultima["fuente"]        if ultima else None,
        "actualizado_en": ultima["actualizado_en"] if ultima else None,
    }
