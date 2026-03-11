"""
Capa de acceso a la base de datos SQLite.
Todas las rutas se leen desde variables de entorno.
"""

import os
import sqlite3
from datetime import datetime, timedelta, date
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
                lunes_salida   TEXT,
                martes_salida  TEXT,
                miercoles_salida TEXT,
                jueves_salida  TEXT,
                viernes_salida TEXT,
                sabado_salida  TEXT,
                domingo_salida TEXT,
                almuerzo_min   INTEGER DEFAULT 0,
                lunes_almuerzo_min    INTEGER,
                martes_almuerzo_min   INTEGER,
                miercoles_almuerzo_min INTEGER,
                jueves_almuerzo_min   INTEGER,
                viernes_almuerzo_min  INTEGER,
                sabado_almuerzo_min   INTEGER,
                domingo_almuerzo_min  INTEGER,
                notas          TEXT,
                fuente         TEXT,
                horas_semana   REAL,   -- Horas contrato por semana (ej: 40). NULL si usa horas_mes.
                horas_mes      REAL,   -- Horas contrato por mes (ej: 160). NULL si usa horas_semana.
                actualizado_en TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS justificaciones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario    TEXT    NOT NULL,
                nombre        TEXT    NOT NULL,
                fecha         TEXT    NOT NULL,
                tipo          TEXT    NOT NULL,
                motivo        TEXT,
                aprobado_por  TEXT,
                hora_permitida TEXT,
                estado        TEXT    DEFAULT 'aprobada',
                duracion_permitida_min INTEGER,
                creado_en     TEXT    DEFAULT (datetime('now')),
                UNIQUE (id_usuario, fecha, tipo)
            );

            CREATE TABLE IF NOT EXISTS breaks_categorizados (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario   TEXT    NOT NULL,
                fecha        TEXT    NOT NULL,
                hora_inicio  TEXT    NOT NULL,   -- HH:MM — hora de Salida del break
                hora_fin     TEXT    NOT NULL,   -- HH:MM — hora de Entrada de retorno
                duracion_min INTEGER,
                categoria    TEXT    NOT NULL CHECK(categoria IN ('almuerzo','permiso','injustificado')),
                motivo       TEXT,
                aprobado_por TEXT,
                creado_en    TEXT    DEFAULT (datetime('now')),
                UNIQUE (id_usuario, fecha, hora_inicio)
            );

            CREATE TABLE IF NOT EXISTS feriados (
                fecha        TEXT PRIMARY KEY,
                descripcion  TEXT NOT NULL,
                tipo         TEXT DEFAULT 'nacional'
            );
        """)
        
        # Migraciones (Sección 8.1)
        _migrar_columna(conn, "justificaciones", "hora_permitida", "TEXT")
        _migrar_columna(conn, "justificaciones", "estado",         "TEXT DEFAULT 'aprobada'")
        _migrar_columna(conn, "justificaciones", "duracion_permitida_min", "INTEGER")
        _migrar_columna(conn, "justificaciones", "hora_retorno_permiso", "TEXT")
        _migrar_columna(conn, "justificaciones", "incluye_almuerzo",    "INTEGER DEFAULT 0")
        _migrar_columna(conn, "horarios_personal", "horas_semana", "REAL")
        _migrar_columna(conn, "horarios_personal", "horas_mes",    "REAL")


def _migrar_columna(conn, tabla, columna, tipo):
    """Agrega una columna si no existe (Sección 8.1 del plan)."""
    try:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
    except sqlite3.OperationalError:
        pass  # La columna ya existe


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
    Usa INSERT OR IGNORE + executemany para rendimiento óptimo.
    Retorna la cantidad de filas realmente insertadas.
    """
    if not registros:
        return 0
    params = [
        (
            str(r["id_usuario"]),
            r["nombre"],
            r["fecha_hora"],
            r.get("punch_raw"),
            r["tipo"],
            r.get("fuente", "zk"),
        )
        for r in registros
    ]
    with _conn() as conn:
        antes = conn.total_changes
        conn.executemany("""
            INSERT OR IGNORE INTO asistencias
                (id_usuario, nombre, fecha_hora, punch_raw, tipo, fuente)
            VALUES (?, ?, ?, ?, ?, ?)
        """, params)
        return conn.total_changes - antes


def consultar_asistencias(fecha_inicio, fecha_fin) -> list[dict]:
    """
    Devuelve registros del rango en el formato que espera script.py:
    { id_usuario, nombre, datetime, fecha, hora, tipo }
    """
    fecha_tope = (fecha_fin + timedelta(days=1)).strftime('%Y-%m-%d')
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id_usuario, nombre, fecha_hora, tipo
            FROM asistencias
            WHERE fecha_hora >= ? AND fecha_hora < ?
            ORDER BY nombre, fecha_hora
        """, (
            f"{fecha_inicio.strftime('%Y-%m-%d')}T00:00:00",
            f"{fecha_tope}T00:00:00",
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
    fecha_tope = (fecha_fin + timedelta(days=1)).strftime('%Y-%m-%d')
    with _conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT nombre
            FROM asistencias
            WHERE fecha_hora >= ? AND fecha_hora < ?
            ORDER BY nombre
        """, (
            f"{fecha_inicio.strftime('%Y-%m-%d')}T00:00:00",
            f"{fecha_tope}T00:00:00",
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
                     viernes, sabado, domingo, 
                     lunes_salida, martes_salida, miercoles_salida, jueves_salida, viernes_salida, sabado_salida, domingo_salida,
                     almuerzo_min, 
                     lunes_almuerzo_min, martes_almuerzo_min, miercoles_almuerzo_min, jueves_almuerzo_min, viernes_almuerzo_min, sabado_almuerzo_min, domingo_almuerzo_min,
                     notas, fuente, horas_semana, horas_mes, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id_usuario) DO UPDATE SET
                    nombre        = excluded.nombre,
                    lunes         = excluded.lunes,
                    martes        = excluded.martes,
                    miercoles     = excluded.miercoles,
                    jueves        = excluded.jueves,
                    viernes       = excluded.viernes,
                    sabado        = excluded.sabado,
                    domingo       = excluded.domingo,
                    lunes_salida  = excluded.lunes_salida,
                    martes_salida = excluded.martes_salida,
                    miercoles_salida = excluded.miercoles_salida,
                    jueves_salida = excluded.jueves_salida,
                    viernes_salida = excluded.viernes_salida,
                    sabado_salida = excluded.sabado_salida,
                    domingo_salida = excluded.domingo_salida,
                    almuerzo_min  = excluded.almuerzo_min,
                    lunes_almuerzo_min = excluded.lunes_almuerzo_min,
                    martes_almuerzo_min = excluded.martes_almuerzo_min,
                    miercoles_almuerzo_min = excluded.miercoles_almuerzo_min,
                    jueves_almuerzo_min = excluded.jueves_almuerzo_min,
                    viernes_almuerzo_min = excluded.viernes_almuerzo_min,
                    sabado_almuerzo_min = excluded.sabado_almuerzo_min,
                    domingo_almuerzo_min = excluded.domingo_almuerzo_min,
                    notas         = excluded.notas,
                    fuente        = excluded.fuente,
                    horas_semana  = excluded.horas_semana,
                    horas_mes     = excluded.horas_mes,
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
                h.get("lunes_salida"),
                h.get("martes_salida"),
                h.get("miercoles_salida"),
                h.get("jueves_salida"),
                h.get("viernes_salida"),
                h.get("sabado_salida"),
                h.get("domingo_salida"),
                int(h.get("almuerzo_min", 0)),
                int(h["lunes_almuerzo_min"]) if h.get("lunes_almuerzo_min") is not None else None,
                int(h["martes_almuerzo_min"]) if h.get("martes_almuerzo_min") is not None else None,
                int(h["miercoles_almuerzo_min"]) if h.get("miercoles_almuerzo_min") is not None else None,
                int(h["jueves_almuerzo_min"]) if h.get("jueves_almuerzo_min") is not None else None,
                int(h["viernes_almuerzo_min"]) if h.get("viernes_almuerzo_min") is not None else None,
                int(h["sabado_almuerzo_min"]) if h.get("sabado_almuerzo_min") is not None else None,
                int(h["domingo_almuerzo_min"]) if h.get("domingo_almuerzo_min") is not None else None,
                h.get("notas", ""),
                fuente,
                h.get("horas_semana"),
                h.get("horas_mes"),
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
                   viernes, sabado, domingo, 
                   lunes_salida, martes_salida, miercoles_salida, jueves_salida, viernes_salida, sabado_salida, domingo_salida,
                   almuerzo_min, 
                   lunes_almuerzo_min, martes_almuerzo_min, miercoles_almuerzo_min, jueves_almuerzo_min, viernes_almuerzo_min, sabado_almuerzo_min, domingo_almuerzo_min,
                   notas, horas_semana, horas_mes
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


def get_horario(id_usuario: str) -> dict | None:
    """Retorna el horario de una persona por su id_usuario, o None si no existe."""
    with _conn() as conn:
        row = conn.execute("""
            SELECT id_usuario, nombre, lunes, martes, miercoles, jueves,
                   viernes, sabado, domingo, 
                   lunes_salida, martes_salida, miercoles_salida, jueves_salida, viernes_salida, sabado_salida, domingo_salida,
                   almuerzo_min, 
                   lunes_almuerzo_min, martes_almuerzo_min, miercoles_almuerzo_min, jueves_almuerzo_min, viernes_almuerzo_min, sabado_almuerzo_min, domingo_almuerzo_min,
                   notas, horas_semana, horas_mes
            FROM horarios_personal
            WHERE id_usuario = ?
        """, (str(id_usuario),)).fetchone()
    return dict(row) if row else None


def upsert_horario(horario: dict, fuente: str = "manual") -> dict:
    """
    Inserta o actualiza un único registro de horario.
    Retorna el horario tal como quedó en la DB.
    """
    upsert_horarios([horario], fuente)
    return get_horario(str(horario["id_usuario"]))


def delete_horario(id_usuario: str) -> bool:
    """Elimina el horario de una persona. Retorna True si existía y fue eliminado."""
    with _conn() as conn:
        cursor = conn.execute(
            "DELETE FROM horarios_personal WHERE id_usuario = ?",
            (str(id_usuario),),
        )
        deleted = cursor.rowcount > 0
    return deleted


# ══════════════════════════════════════════════════════════════════════════
# PERSONAS CON ID (para filtrado)
# ══════════════════════════════════════════════════════════════════════════

def get_personas_con_id(fecha_inicio, fecha_fin) -> list[dict]:
    """Devuelve lista de {id_usuario, nombre} únicos en el rango de fechas."""
    fecha_tope = (fecha_fin + timedelta(days=1)).strftime('%Y-%m-%d')
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id_usuario, nombre
            FROM asistencias
            WHERE fecha_hora >= ? AND fecha_hora < ?
            GROUP BY nombre
            ORDER BY nombre
        """, (
            f"{fecha_inicio.strftime('%Y-%m-%d')}T00:00:00",
            f"{fecha_tope}T00:00:00",
        )).fetchall()
    return [{"id_usuario": row["id_usuario"], "nombre": row["nombre"]} for row in rows]


# ══════════════════════════════════════════════════════════════════════════
# JUSTIFICACIONES
# ══════════════════════════════════════════════════════════════════════════

def insertar_justificacion(id_usuario: str, nombre: str, fecha: str,
                           tipo: str, motivo: str = "", aprobado_por: str = "",
                           hora_permitida: str = None, estado: str = "aprobada",
                           duracion_permitida_min: int = None,
                           hora_retorno_permiso: str = None,
                           incluye_almuerzo: int = 0) -> dict:
    """
    Inserta o reemplaza una justificación.
    fecha debe ser string 'YYYY-MM-DD'.
    tipo: 'ausencia' | 'tardanza' | 'almuerzo' | 'incompleto' | 'salida_anticipada' | 'permiso'
    incluye_almuerzo: 1 si el permiso absorbe el almuerzo habitual del empleado.
    """
    with _conn() as conn:
        conn.execute("""
            INSERT INTO justificaciones
                (id_usuario, nombre, fecha, tipo, motivo, aprobado_por,
                 hora_permitida, estado, duracion_permitida_min,
                 hora_retorno_permiso, incluye_almuerzo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_usuario, fecha, tipo) DO UPDATE SET
                nombre                 = excluded.nombre,
                motivo                 = excluded.motivo,
                aprobado_por           = excluded.aprobado_por,
                hora_permitida         = excluded.hora_permitida,
                estado                 = excluded.estado,
                duracion_permitida_min = excluded.duracion_permitida_min,
                hora_retorno_permiso   = excluded.hora_retorno_permiso,
                incluye_almuerzo       = excluded.incluye_almuerzo,
                creado_en              = datetime('now')
        """, (str(id_usuario), nombre, fecha, tipo, motivo or "", aprobado_por or "",
              hora_permitida, estado, duracion_permitida_min,
              hora_retorno_permiso, 1 if incluye_almuerzo else 0))
        row = conn.execute("""
            SELECT id, id_usuario, nombre, fecha, tipo, motivo, aprobado_por,
                   hora_permitida, estado, duracion_permitida_min,
                   hora_retorno_permiso, incluye_almuerzo, creado_en
            FROM justificaciones WHERE id_usuario=? AND fecha=? AND tipo=?
        """, (str(id_usuario), fecha, tipo)).fetchone()
    return dict(row) if row else {}


def get_justificaciones(fecha_inicio=None, fecha_fin=None) -> list[dict]:
    """Retorna justificaciones en el rango de fechas (o todas si no se especifica rango)."""
    with _conn() as conn:
        if fecha_inicio and fecha_fin:
            rows = conn.execute("""
                SELECT id, id_usuario, nombre, fecha, tipo, motivo, aprobado_por, hora_permitida, estado, duracion_permitida_min, hora_retorno_permiso, incluye_almuerzo, creado_en
                FROM justificaciones
                WHERE fecha >= ? AND fecha <= ?
                ORDER BY fecha, nombre
            """, (
                fecha_inicio.strftime('%Y-%m-%d') if hasattr(fecha_inicio, 'strftime') else fecha_inicio,
                fecha_fin.strftime('%Y-%m-%d')    if hasattr(fecha_fin,    'strftime') else fecha_fin,
            )).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, id_usuario, nombre, fecha, tipo, motivo, aprobado_por, hora_permitida, estado, duracion_permitida_min, hora_retorno_permiso, incluye_almuerzo, creado_en
                FROM justificaciones ORDER BY fecha DESC, nombre
            """).fetchall()
    return [dict(r) for r in rows]


def get_justificaciones_dict(fecha_inicio=None, fecha_fin=None) -> dict:
    """
    Retorna justificaciones indexadas por (id_usuario, fecha_iso, tipo).
    Útil para lookup rápido durante el análisis.
    """
    lista = get_justificaciones(fecha_inicio, fecha_fin)
    return {(j["id_usuario"], j["fecha"], j["tipo"]): j for j in lista}


def get_justificaciones_pendientes() -> list:
    """
    Retorna justificaciones en estado 'pendiente'.
    Usada por el dashboard para mostrar el badge de cantidad.
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id, id_usuario, nombre, fecha, tipo, motivo, aprobado_por, hora_permitida, estado, hora_retorno_permiso, creado_en
            FROM justificaciones
            WHERE estado = 'pendiente'
            ORDER BY fecha, nombre
        """).fetchall()
    return [dict(r) for r in rows]


def actualizar_estado_justificacion(id_justificacion: int, estado: str) -> bool:
    """
    Cambia estado de 'pendiente' a 'aprobada' o 'rechazada'.
    """
    with _conn() as conn:
        cursor = conn.execute(
            "UPDATE justificaciones SET estado = ?, creado_en = datetime('now') WHERE id = ?",
            (estado, id_justificacion)
        )
    return cursor.rowcount > 0


def eliminar_justificacion(id_justificacion: int) -> bool:
    """Elimina una justificación por su ID. Retorna True si existía."""
    with _conn() as conn:
        cursor = conn.execute(
            "DELETE FROM justificaciones WHERE id = ?", (id_justificacion,)
        )
    return cursor.rowcount > 0


# ══════════════════════════════════════════════════════════════════════════
# FERIADOS
# ══════════════════════════════════════════════════════════════════════════

def insertar_feriado(fecha: str, descripcion: str, tipo: str = "nacional") -> dict:
    """Inserta o reemplaza un feriado. fecha debe ser 'YYYY-MM-DD'."""
    with _conn() as conn:
        conn.execute("""
            INSERT INTO feriados (fecha, descripcion, tipo)
            VALUES (?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                descripcion = excluded.descripcion,
                tipo        = excluded.tipo
        """, (fecha, descripcion, tipo))
        row = conn.execute(
            "SELECT fecha, descripcion, tipo FROM feriados WHERE fecha=?", (fecha,)
        ).fetchone()
    return dict(row) if row else {}


def get_feriados(fecha_inicio=None, fecha_fin=None) -> list[dict]:
    """Retorna feriados en el rango dado (o todos si no se especifica)."""
    with _conn() as conn:
        if fecha_inicio and fecha_fin:
            fi = fecha_inicio.strftime('%Y-%m-%d') if hasattr(fecha_inicio, 'strftime') else fecha_inicio
            ff = fecha_fin.strftime('%Y-%m-%d')    if hasattr(fecha_fin,    'strftime') else fecha_fin
            rows = conn.execute(
                "SELECT fecha, descripcion, tipo FROM feriados WHERE fecha >= ? AND fecha <= ? ORDER BY fecha",
                (fi, ff)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT fecha, descripcion, tipo FROM feriados ORDER BY fecha"
            ).fetchall()
    return [dict(r) for r in rows]


def get_feriados_set(fecha_inicio=None, fecha_fin=None) -> set:
    """Retorna un set de objetos date para lookup rápido en el análisis."""
    from datetime import date as _date
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
    with _conn() as conn:
        cursor = conn.execute("DELETE FROM feriados WHERE fecha = ?", (fecha,))
    return cursor.rowcount > 0


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
            desc  = str(row.get("descripcion", "")).strip()
            tipo  = str(row.get("tipo", "nacional")).strip() or "nacional"
            if fecha and desc:
                insertar_feriado(fecha, desc, tipo)
                count += 1
    return count

def get_estado_horarios() -> dict:
    """
    Retorna un resumen del estado de los horarios cargados.
    """
    with _conn() as conn:
        row_total = conn.execute("SELECT COUNT(*) FROM horarios_personal").fetchone()
        total = row_total[0] if row_total else 0
        
        ultima = conn.execute("""
            SELECT fuente, actualizado_en
            FROM horarios_personal
            ORDER BY actualizado_en DESC
            LIMIT 1
        """).fetchone()

        con_semana = conn.execute("SELECT COUNT(*) FROM horarios_personal WHERE horas_semana IS NOT NULL").fetchone()[0]
        con_mes    = conn.execute("SELECT COUNT(*) FROM horarios_personal WHERE horas_mes IS NOT NULL").fetchone()[0]
        con_almuerzo = conn.execute("SELECT COUNT(*) FROM horarios_personal WHERE almuerzo_min > 0").fetchone()[0]

    return {
        "total":          total,
        "cargados":       total > 0,
        "fuente":         ultima["fuente"] if ultima else None,
        "actualizado_en": ultima["actualizado_en"] if ultima else None,
        "con_semana":     con_semana,
        "con_mes":        con_mes,
        "con_almuerzo":   con_almuerzo
    }

# --- Múltiples Breaks / Categorización (Parte II) ---

def get_breaks_categorizados_dict(fecha_inicio: date = None, fecha_fin: date = None) -> dict:
    """
    Retorna { id_usuario: { fecha_iso: [ {hora_inicio, hora_fin, categoria, ...}, ... ] } }
    """
    with _conn() as conn:
        query = "SELECT id_usuario, fecha, hora_inicio, hora_fin, duracion_min, categoria, motivo, aprobado_por FROM breaks_categorizados"
        params = []
        if fecha_inicio and fecha_fin:
            query += " WHERE fecha >= ? AND fecha <= ?"
            params = [fecha_inicio.isoformat(), fecha_fin.isoformat()]
        
        rows = conn.execute(query, params).fetchall()
        
        res = {}
        for r in rows:
            uid = r["id_usuario"]
            fec = r["fecha"]
            if uid not in res: res[uid] = {}
            if fec not in res[uid]: res[uid][fec] = []
            res[uid][fec].append(dict(r))
        return res

def insertar_break_categorizado(id_usuario, fecha, hora_inicio, hora_fin, categoria, motivo="", aprobado_por=""):
    """Inserta o actualiza la categorización de un break."""
    duracion = None
    try:
        from datetime import datetime
        t1 = datetime.strptime(hora_inicio, "%H:%M")
        t2 = datetime.strptime(hora_fin, "%H:%M")
        duracion = int((t2 - t1).total_seconds() / 60)
    except: pass
    
    with _conn() as conn:
        conn.execute("""
            INSERT INTO breaks_categorizados (id_usuario, fecha, hora_inicio, hora_fin, duracion_min, categoria, motivo, aprobado_por)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_usuario, fecha, hora_inicio) DO UPDATE SET
                hora_fin = excluded.hora_fin,
                duracion_min = excluded.duracion_min,
                categoria = excluded.categoria,
                motivo = excluded.motivo,
                aprobado_por = excluded.aprobado_por
        """, (str(id_usuario), fecha, hora_inicio, hora_fin, duracion, categoria, motivo, aprobado_por))
