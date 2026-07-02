"""
Módulo de sincronización con dispositivos biométricos.
Gestiona la conexión, descarga de marcaciones, transformación de datos
y sincronización incremental hacia la base de datos local usando drivers.

Fase 1 (2026-07): sync observable
- Logger propio (`log`).
- Helper `_registrar_corrida_sync` que persiste cada corrida del scheduler
  en `public.scheduler_runs`.
- Loop `_run()` inkillable: una excepción interna NO mata el hilo.
- Flag singleton `_scheduler_started` para evitar doble inicialización.
"""

import logging
import os
import threading
import time as time_module
from datetime import datetime, date, timedelta, timezone
from datetime import time as dt_time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Para enviar reportes de fallo
from smtplib import SMTPException
from email_utils import enviar_correo
import db as db_module
from drivers import get_driver

try:
    import schedule
    SCHEDULE_DISPONIBLE = True
except ImportError:
    SCHEDULE_DISPONIBLE = False

log = logging.getLogger(__name__)  # nombre: "sync"

SYNC_AUTO          = os.getenv("SYNC_AUTO",          "false").lower() == "true"
SYNC_HORA_NOCTURNA = os.getenv("SYNC_HORA_NOCTURNA", "02:00")
SYNC_INTERVALO_HORAS = int(os.getenv("SYNC_INTERVALO_HORAS", "2"))

# Variables de backup (resueltas también en app/config.py; aquí se duplican
# porque sync.py no depende de Flask).
_backup_auto_env = os.getenv("BACKUP_AUTO", "")
if _backup_auto_env == "":
    BACKUP_AUTO = SYNC_AUTO
else:
    BACKUP_AUTO = _backup_auto_env.lower() == "true"
BACKUP_HORA          = os.getenv("BACKUP_HORA",          "03:00")
BACKUP_DIR           = os.getenv("BACKUP_DIR",           "/data/backups")
BACKUP_RETENCION_DIAS = int(os.getenv("BACKUP_RETENCION_DIAS", "30"))

# ══════════════════════════════════════════════════════════════════════════
# COMPATIBILIDAD JOBS (Para la UI antigua, aunque Fase 7 usa sync_estado)
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
# UTILIDADES Y PING
# ══════════════════════════════════════════════════════════════════════════
def ping_dispositivo(dispositivo_id: str = None) -> bool:
    """
    Verifica si el dispositivo (o el primero activo) responde.
    """
    # Si no se provee ID, agarramos el primero como fallback
    if not dispositivo_id:
        activos = db_module.get_dispositivos_activos()
        if not activos: return False
        disp = activos[0]
    else:
        disp = db_module.get_dispositivo(dispositivo_id)
        if not disp: return False
        
    driver = get_driver(disp)
    return driver.test_conexion()


# ══════════════════════════════════════════════════════════════════════════
# SINCRONIZACIÓN
# ══════════════════════════════════════════════════════════════════════════

def sincronizar_dispositivo(dispositivo_id: str, desde: datetime = None, force_historico: bool = False) -> tuple[int, int]:
    """
    Sincroniza un dispositivo específico.
    Retorna (descargados, insertados_nuevos).
    """
    disp = db_module.get_dispositivo(dispositivo_id)
    if not disp:
        raise ValueError(f"Dispositivo {dispositivo_id} no encontrado")
        
    driver = get_driver(disp)
    
    db_module.actualizar_estado_sync_ui(dispositivo_id, "conectando", 10)
    
    if not driver.test_conexion():
        db_module.actualizar_estado_sync_ui(dispositivo_id, "error", 0, 0, "No se pudo conectar al dispositivo")
        db_module.registrar_sync(
            datetime.min, datetime.max, 0, 0, False, 
            "Tiempo de espera agotado al comunicar con el dispositivo", 0, dispositivo_id=dispositivo_id
        )
        raise ConnectionError(f"No se pudo conectar al dispositivo {disp['nombre']}")

    # 1. Traer usuarios
    db_module.actualizar_estado_sync_ui(dispositivo_id, "obteniendo_usuarios", 30)
    usuarios = driver.get_usuarios()
    if usuarios:
        db_module.upsert_usuarios(usuarios, dispositivo_id)

    # 2. Determinar fecha de partición 
    # Usar incremental si no se fuerza y hay watermark
    if not force_historico and disp.get("watermark_ultima_fecha"):
        rango_desde = disp["watermark_ultima_fecha"]
        # PostgreSQL TIMESTAMPTZ devuelve datetimes timezone-aware;
        # los drivers trabajan con datetimes naive → normalizar aquí.
        if rango_desde.tzinfo is not None:
            rango_desde = rango_desde.replace(tzinfo=None)
    else:
        rango_desde = desde

    # 3. Descargar marcaciones
    db_module.actualizar_estado_sync_ui(dispositivo_id, "descargando_marcaciones", 50)
    asistencias_raw = driver.get_asistencias(desde=rango_desde)
    
    capacidad = driver.get_capacidad()
    total_dispositivo = capacidad.get("total_registros", 0)

    # 4. Procesar e insertar
    if asistencias_raw:
        db_module.actualizar_estado_sync_ui(dispositivo_id, "procesando", 70)
        # La BD hará resolve del id_usuario a persona_id en insertar_asistencias
        insertados = db_module.insertar_asistencias(asistencias_raw, dispositivo_id)
        
        # Actualizar watermark con el registro más reciente
        ultimo_reg = max(asistencias_raw, key=lambda x: x["fecha_hora"])
        # Asumiendo que punch_raw o algo no es único, PostgreSQL se banca la idempotencia
        db_module.actualizar_watermark(
            dispositivo_id,
            ultimo_id="0", # Hikvision no tiene ID auto-incremental único, usamos fecha
            ultima_fecha=ultimo_reg["fecha_hora"]
        )
    else:
        insertados = 0
        
    asistencias_count = len(asistencias_raw) if asistencias_raw else 0

    # 5. Guardar Log y Estado
    db_module.registrar_sync(
        rango_desde or datetime.min, 
        datetime.max, 
        asistencias_count, 
        insertados, 
        True, 
        None, 
        total_dispositivo,
        dispositivo_id=dispositivo_id
    )
    db_module.actualizar_estado_sync_ui(dispositivo_id, "completado", 100, insertados)
    
    return asistencias_count, insertados

def sincronizar_con_reintento(dispositivo_id: str, desde: datetime = None, force_historico: bool = False, max_intentos: int = 3):
    """Intenta sincronizar con un backoff exponencial si falla la conexión."""
    for intento in range(max_intentos):
        try:
            return sincronizar_dispositivo(dispositivo_id, desde=desde, force_historico=force_historico)
        except ConnectionError as e:
            if intento == max_intentos - 1:
                # Ya registró el error el hijo
                return 0, 0
            espera = 2 ** intento * 5
            db_module.actualizar_estado_sync_ui(dispositivo_id, "error", mensaje=f"Reintentando en {espera}s")
            time_module.sleep(espera)
        except Exception as e:
            db_module.actualizar_estado_sync_ui(dispositivo_id, "error", 0, 0, str(e))
            db_module.registrar_sync(
                datetime.min, datetime.max, 0, 0, False, str(e), 0, dispositivo_id=dispositivo_id
            )
            return 0, 0

def sincronizar(fecha_inicio: date | None = None, fecha_fin: date | None = None, job_id: str | None = None, force_historico: bool = False):
    """
    Sincroniza todos los dispositivos usando ThreadPoolExecutor.
    Mantiene compatibilidad con la estructura `job_id` del frontend.
    """
    dispositivos = db_module.get_dispositivos_activos()
    
    if not dispositivos:
        _set_job(job_id, {"estado": "error", "detalle": "No hay dispositivos activos"})
        return 0, 0
        
    _set_job(job_id, {"estado": "procesando", "registros_procesados": 0, "registros_nuevos": 0})
    
    # Conversión a datetime para el rango_desde
    desde_dt = datetime.combine(fecha_inicio, dt_time.min) if fecha_inicio else None
    
    tot_descargados = 0
    tot_insertados = 0
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(sincronizar_con_reintento, d['id'], desde_dt, force_historico): d
            for d in dispositivos
        }
        for future in as_completed(futures):
            d = futures[future]
            try:
                descargados, insertados = future.result()
                tot_descargados += descargados
                tot_insertados += insertados
            except Exception as e:
                # Los errores ya los manejó sincronizar_con_reintento, pero atajamos por si acaso
                pass

            # Informar progreso para compatibilidad Legacy
            _set_job(job_id, {
                "estado": "procesando", 
                "registros_procesados": tot_descargados, 
                "registros_nuevos": tot_insertados
            })
            
    _set_job(job_id, {
        "estado": "completado",
        "registros_procesados": tot_descargados,
        "registros_nuevos": tot_insertados
    })
    
    # Después de todo proceso enviamos alertas (Fase 7)
    verificar_dispositivos_desconectados()
            
    return tot_descargados, tot_insertados


def verificar_dispositivos_desconectados():
    """Busca si hay dispositivos con 3+ fallas consecutivas y notifica."""
    fallos = db_module.get_dispositivos_con_fallas_consecutivas(n=3)
    for d in fallos:
        if not db_module.has_alerta_hoy(d['id']):
            cuerpo = (f"Alerta Crítica: El dispositivo '{d['nombre']}' ha fallado "
                     f"en sus últimos 3 intentos de sincronización.")
            # Correo al admin (obtenido de env)
            admin_email = os.getenv("ADMIN_EMAIL", "admin@localhost")
            enviar_correo(admin_email, "Fallos de Sincronización en Dispositivo", cuerpo)
            db_module.marcar_alerta_enviada(d['id'])

def limpiar_log_dispositivo(dispositivo_id: str) -> int:
    """Limpia los registros del dispositivo especificado y retorna el total borrado."""
    disp = db_module.get_dispositivo(dispositivo_id)
    if not disp:
        raise ValueError(f"Dispositivo {dispositivo_id} no encontrado.")
    
    driver = get_driver(disp)
    if not driver.test_conexion():
        raise ConnectionError(f"No se pudo conectar al dispositivo {disp['nombre']}.")
        
    return driver.clear_asistencias()


def _get_tenant_slugs() -> list[str]:
    """Retorna los slugs de todos los tenants activos."""
    from db.connection import get_connection
    from sqlalchemy import text
    try:
        with get_connection("public") as conn:
            rows = conn.execute(
                text("SELECT slug FROM tenants WHERE activo = true ORDER BY slug")
            ).fetchall()
            return [r[0] for r in rows]
    except Exception:
        return [os.getenv("TENANT_DEFAULT", "istpet")]


# ══════════════════════════════════════════════════════════════════════════
# SCHEDULER OBSERVABLE (Fase 1)
# ══════════════════════════════════════════════════════════════════════════

def _backup_diario():
    """Ejecutado por schedule (BACKUP_HORA) — pg_dump -Fc con retención.

    Si el backup falla, envía email a ADMIN_EMAIL. Si OK, purga los .dump
    con mtime > BACKUP_RETENCION_DIAS. Resultado se registra en
    `public.scheduler_runs` (job=`backup_diario`, tenant_slug=NULL).
    """
    log.info("Iniciando backup diario (scheduler)")

    from backup import generar_dump, purgar_backups_viejos
    from email_utils import enviar_correo

    inicio = datetime.now(timezone.utc)
    timestamp = inicio.strftime("%Y%m%d_%H%M")
    filename = f"backup_completo_{timestamp}.dump"
    destino = Path(BACKUP_DIR) / filename

    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ruta = generar_dump(destino)
        size_mb = ruta.stat().st_size / (1024 * 1024)

        # Retención solo tras éxito (no borrar si el backup del día falló).
        borrados = purgar_backups_viejos(Path(BACKUP_DIR), dias=BACKUP_RETENCION_DIAS)
        log.info(
            "backup_diario OK: %s (%.1f MB), purgados=%s",
            ruta, size_mb, borrados,
        )

        _registrar_corrida_sync(
            job="backup_diario",
            tenant_slug=None,
            inicio=inicio,
            fin=datetime.now(timezone.utc),
            ok=True,
            descargados=None,
            insertados=None,
            detalle=f"{ruta} ({size_mb:.1f} MB)",
        )
    except Exception as e:
        log.exception("backup_diario falló")
        _registrar_corrida_sync(
            job="backup_diario",
            tenant_slug=None,
            inicio=inicio,
            fin=datetime.now(timezone.utc),
            ok=False,
            descargados=None,
            insertados=None,
            detalle=str(e)[:500],
        )
        # Email de alerta al admin.
        admin_email = os.getenv("ADMIN_EMAIL", "")
        if admin_email:
            try:
                enviar_correo(
                    admin_email,
                    "Fallo en backup diario",
                    f"<p>El backup diario falló: <code>{e}</code></p>"
                    f"<p>Verificar volumen <code>{BACKUP_DIR}</code> y logs del scheduler.</p>",
                )
            except Exception:
                log.exception("No se pudo enviar email de alerta de backup")


def _registrar_corrida_sync(
    job: str,
    tenant_slug: str | None,
    inicio: datetime,
    fin: datetime,
    ok: bool,
    descargados: int | None,
    insertados: int | None,
    detalle: str | None,
) -> None:
    """Wrapper que no propaga excepciones del helper de persistencia.

    Si la BD está caída durante una corrida, el scheduler NO debe morir.
    """
    try:
        from db.queries import scheduler_runs
        scheduler_runs.registrar_run(
            job=job,
            tenant_slug=tenant_slug,
            inicio=inicio,
            fin=fin,
            ok=ok,
            descargados=descargados,
            insertados=insertados,
            detalle=detalle,
        )
    except Exception:
        log.exception(
            "No se pudo registrar corrida del scheduler en BD (job=%s)", job
        )


def _sync_automatico():
    """Ejecutado por schedule (incremental) — itera todos los tenants activos.

    Cada tenant se procesa de forma independiente: un fallo en uno NO afecta
    a los demás. Cada corrida se registra en `public.scheduler_runs`.
    """
    log.info("Iniciando sync incremental (scheduler)")
    for slug in _get_tenant_slugs():
        db_module.set_thread_tenant(slug)
        inicio = datetime.now(timezone.utc)
        try:
            descargados, insertados = sincronizar(force_historico=False)
            from db.queries.periodos import cerrar_periodos_vencidos
            cerrar_periodos_vencidos()
            _registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=True,
                descargados=descargados,
                insertados=insertados,
                detalle=None,
            )
        except Exception as e:
            log.exception("sync_incremental falló para tenant=%s", slug)
            _registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle=str(e)[:500],
            )
        finally:
            db_module.clear_thread_tenant()


def _sync_nocturna_completa():
    """Ejecutado a SYNC_HORA_NOCTURNA — itera todos los tenants activos.

    Al cierre, purga filas > 90 días de `public.scheduler_runs`.
    """
    log.info("Iniciando sync nocturna completa (scheduler)")
    treinta_dias_atras = date.today() - timedelta(days=30)
    for slug in _get_tenant_slugs():
        db_module.set_thread_tenant(slug)
        inicio = datetime.now(timezone.utc)
        try:
            descargados, insertados = sincronizar(
                fecha_inicio=treinta_dias_atras, force_historico=True
            )
            _registrar_corrida_sync(
                job="sync_nocturna",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=True,
                descargados=descargados,
                insertados=insertados,
                detalle=None,
            )
        except Exception as e:
            log.exception("sync_nocturna falló para tenant=%s", slug)
            _registrar_corrida_sync(
                job="sync_nocturna",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle=str(e)[:500],
            )
        finally:
            db_module.clear_thread_tenant()

    # Retención de scheduler_runs: borrar filas > 90 días.
    try:
        from db.queries import scheduler_runs
        borradas = scheduler_runs.purgar_mayor_a(dias=90)
        if borradas:
            log.info("scheduler_runs: purgadas %s filas > 90 días", borradas)
    except Exception:
        log.exception("scheduler_runs purga falló (no crítico)")


_scheduler_started = False  # guard singleton


def iniciar_scheduler():
    """Inicia el scheduler en un hilo daemon si SYNC_AUTO=true.

    Loguea siempre su estado al arrancar (ACTIVO/INACTIVO) para que el operador
    sepa sin tener que mirar procesos. Es idempotente: si ya está activo,
    ignora la segunda llamada.
    """
    global _scheduler_started

    if not SYNC_AUTO or not SCHEDULE_DISPONIBLE:
        log.info("Scheduler INACTIVO (SYNC_AUTO=false o schedule no disponible)")
        return

    if _scheduler_started:
        log.warning("Scheduler ya estaba iniciado; se ignora segunda llamada")
        return

    # Sync nocturna
    schedule.every().day.at(SYNC_HORA_NOCTURNA).do(_sync_nocturna_completa)

    # Sync incremental
    schedule.every(SYNC_INTERVALO_HORAS).hours.do(_sync_automatico)

    # Backup diario (si está activado)
    if BACKUP_AUTO:
        schedule.every().day.at(BACKUP_HORA).do(_backup_diario)
        log.info(
            "Backup diario ACTIVO a las %s, dir=%s, retención=%sd",
            BACKUP_HORA, BACKUP_DIR, BACKUP_RETENCION_DIAS,
        )
    else:
        log.info("Backup diario INACTIVO (BACKUP_AUTO=false)")

    def _run():
        # Loop inkillable: cualquier excepción en una corrida NO mata el hilo.
        while True:
            try:
                schedule.run_pending()
            except Exception:
                log.exception("scheduler loop falló; continuando")
            time_module.sleep(60)

    threading.Thread(
        target=_run, daemon=True, name="biometrico-scheduler"
    ).start()
    _scheduler_started = True

    log.info(
        "Scheduler ACTIVO: nocturna %s, incremental cada %sh",
        SYNC_HORA_NOCTURNA, SYNC_INTERVALO_HORAS,
    )