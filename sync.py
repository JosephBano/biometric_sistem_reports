"""
Módulo de sincronización con el dispositivo biométrico ZK.
Gestiona la conexión, descarga de marcaciones, transformación de datos
y sincronización incremental hacia la base de datos local.
"""

import os
import threading
import time as time_module
from datetime import datetime, date
from datetime import time as dt_time

try:
    from zk import ZK
    ZK_DISPONIBLE = True
except ImportError:
    ZK_DISPONIBLE = False

try:
    import schedule
    SCHEDULE_DISPONIBLE = True
except ImportError:
    SCHEDULE_DISPONIBLE = False


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DESDE VARIABLES DE ENTORNO
# ══════════════════════════════════════════════════════════════════════════

ZK_IP       = os.getenv("ZK_IP",       "192.168.7.129")
ZK_PORT     = int(os.getenv("ZK_PORT",     "4370"))
ZK_PASSWORD = int(os.getenv("ZK_PASSWORD", "0"))
ZK_TIMEOUT  = int(os.getenv("ZK_TIMEOUT",  "5"))
ZK_UDP      = os.getenv("ZK_UDP", "false").lower() == "true"

SYNC_AUTO          = os.getenv("SYNC_AUTO",          "false").lower() == "true"
SYNC_HORA_NOCTURNA = os.getenv("SYNC_HORA_NOCTURNA", "00:30")
SYNC_INTERVALO_MIN = int(os.getenv("SYNC_INTERVALO_MIN", "480"))


# ══════════════════════════════════════════════════════════════════════════
# TRACKING DE JOBS EN MEMORIA
# ══════════════════════════════════════════════════════════════════════════

_jobs: dict       = {}
_jobs_lock        = threading.Lock()


def _set_job(job_id: str | None, data: dict):
    if job_id:
        with _jobs_lock:
            _jobs[job_id] = data


def get_job_status(job_id: str) -> dict:
    with _jobs_lock:
        return dict(_jobs.get(job_id, {"estado": "no_encontrado"}))


# ══════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════════

def _make_zk() -> "ZK":
    return ZK(
        ZK_IP,
        port=ZK_PORT,
        timeout=ZK_TIMEOUT,
        password=ZK_PASSWORD,
        force_udp=ZK_UDP,
        ommit_ping=True,
    )


def _punch_to_tipo(punch) -> str | None:
    """
    Convierte att.punch al tipo de marcación según estándar ZK:
      0 = Check-In        → Entrada
      1 = Check-Out       → Salida
      2 = Break-Out       → Salida  (salida de pausa/almuerzo)
      3 = Break-In        → Entrada (regreso de pausa/almuerzo)
      4 = Overtime-In     → Entrada (inicio de horas extra)
      5 = Overtime-Out    → Salida  (fin de horas extra)
    Cualquier otro valor se descarta (retorna None).
    """
    _MAPA = {0: "Entrada", 1: "Salida", 2: "Salida",
             3: "Entrada", 4: "Entrada", 5: "Salida"}
    return _MAPA.get(punch)


# ══════════════════════════════════════════════════════════════════════════
# PING
# ══════════════════════════════════════════════════════════════════════════

def ping_dispositivo() -> bool:
    """
    Verifica si el dispositivo responde.
    Usa timeout corto (2 s) para no bloquear la UI.
    """
    if not ZK_DISPONIBLE:
        return False
    try:
        zk = ZK(
            ZK_IP, port=ZK_PORT, timeout=2,
            password=ZK_PASSWORD, force_udp=ZK_UDP, ommit_ping=True,
        )
        conn = zk.connect()
        conn.disconnect()
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# SINCRONIZACIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

def sincronizar(
    fecha_inicio: date | None = None,
    fecha_fin:    date | None = None,
    job_id:       str  | None = None,
) -> tuple[int, int]:
    """
    Descarga todas las marcaciones del dispositivo, filtra por rango de fechas
    en Python (el protocolo ZK no filtra en el dispositivo), y guarda los
    registros nuevos en la base de datos local.

    Actualiza _jobs[job_id] para que el cliente pueda hacer polling.
    Retorna (registros_en_rango, registros_nuevos_en_db).
    """
    import db as db_module

    if not ZK_DISPONIBLE:
        raise RuntimeError(
            "La librería pyzk no está instalada. "
            "Ejecuta: pip install pyzk"
        )

    if fecha_inicio is None:
        fecha_inicio = date(2000, 1, 1)
    if fecha_fin is None:
        fecha_fin = date.today()

    _set_job(job_id, {
        "estado": "conectando",
        "registros_procesados": 0,
        "registros_nuevos": 0,
    })

    zk   = _make_zk()
    conn = None
    try:
        conn = zk.connect()

        # ── Sincronizar usuarios ───────────────────────────────────────
        _set_job(job_id, {
            "estado": "obteniendo_usuarios",
            "registros_procesados": 0,
            "registros_nuevos": 0,
        })
        usuarios   = conn.get_users()
        user_dict  = {str(u.user_id): str(u.name).strip() for u in usuarios}
        db_module.upsert_usuarios([
            {
                "id_usuario": str(u.user_id),
                "nombre":     str(u.name).strip(),
                "privilegio": u.privilege,
            }
            for u in usuarios
        ])

        # ── Descargar todas las marcaciones ────────────────────────────
        _set_job(job_id, {
            "estado": "descargando_marcaciones",
            "registros_procesados": 0,
            "registros_nuevos": 0,
        })
        attendances      = conn.get_attendance()
        total_dispositivo = len(attendances)

        # ── Transformar y filtrar ──────────────────────────────────────
        _set_job(job_id, {
            "estado": "procesando",
            "registros_procesados": 0,
            "total_dispositivo": total_dispositivo,
            "registros_nuevos": 0,
        })

        registros = []
        for i, att in enumerate(attendances):
            ts = att.timestamp
            if not isinstance(ts, datetime):
                try:
                    ts = datetime.combine(ts, dt_time.min)
                except Exception:
                    continue
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)

            # Filtro de rango (el dispositivo devuelve todo)
            if ts.date() < fecha_inicio or ts.date() > fecha_fin:
                continue

            tipo = _punch_to_tipo(att.punch)
            if tipo is None:
                continue

            nombre = user_dict.get(str(att.user_id), f"Usuario {att.user_id}")
            registros.append({
                "id_usuario": str(att.user_id),
                "nombre":     nombre,
                "fecha_hora": ts.isoformat(),
                "punch_raw":  att.punch,
                "tipo":       tipo,
                "fuente":     "zk",
            })

            # Actualizar progreso cada 500 registros
            if job_id and i % 500 == 0:
                _set_job(job_id, {
                    "estado": "procesando",
                    "registros_procesados": i,
                    "total_dispositivo": total_dispositivo,
                    "registros_nuevos": 0,
                })

        # ── Insertar en DB ─────────────────────────────────────────────
        nuevos = db_module.insertar_asistencias(registros)
        db_module.registrar_sync(
            datetime.combine(fecha_inicio, dt_time.min),
            datetime.combine(fecha_fin,    dt_time(23, 59, 59)),
            len(registros),
            nuevos,
            True,
        )

        _set_job(job_id, {
            "estado": "completado",
            "registros_procesados": len(registros),
            "total_dispositivo": total_dispositivo,
            "registros_nuevos": nuevos,
        })

        return len(registros), nuevos

    except Exception as e:
        _set_job(job_id, {"estado": "error", "detalle": str(e)})
        try:
            db_module.registrar_sync(
                datetime.combine(fecha_inicio, dt_time.min),
                datetime.combine(fecha_fin,    dt_time(23, 59, 59)),
                0, 0, False, str(e),
            )
        except Exception:
            pass
        raise

    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════
# LIMPIEZA DEL DISPOSITIVO
# ══════════════════════════════════════════════════════════════════════════

def limpiar_log_dispositivo() -> int:
    """
    Borra TODOS los registros de asistencia del dispositivo ZK.
    Retorna cuántos registros había antes de borrar.

    IRREVERSIBLE. Solo llamar después de confirmar que la DB tiene todos los datos.
    """
    if not ZK_DISPONIBLE:
        raise RuntimeError("La librería pyzk no está instalada.")

    zk   = _make_zk()
    conn = None
    try:
        conn = zk.connect()
        total_antes = len(conn.get_attendance())
        conn.clear_attendance()
        return total_antes
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════
# SYNC AUTOMÁTICO (scheduler)
# ══════════════════════════════════════════════════════════════════════════

def _sync_automatico():
    """Llamado por el scheduler. Sincroniza todo sin filtro de fechas."""
    try:
        sincronizar()
    except Exception:
        pass


def iniciar_scheduler():
    """
    Inicia el scheduler en un hilo daemon si SYNC_AUTO=true.
    Programa:
      - Un sync completo diario a SYNC_HORA_NOCTURNA
      - Un sync parcial cada SYNC_INTERVALO_MIN minutos
    """
    if not SYNC_AUTO or not SCHEDULE_DISPONIBLE:
        return

    schedule.every().day.at(SYNC_HORA_NOCTURNA).do(_sync_automatico)
    schedule.every(SYNC_INTERVALO_MIN).minutes.do(_sync_automatico)

    def _run():
        while True:
            schedule.run_pending()
            time_module.sleep(60)

    threading.Thread(target=_run, daemon=True).start()
