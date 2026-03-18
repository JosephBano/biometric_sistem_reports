"""
Módulo de sincronización con dispositivos biométricos.
Gestiona la conexión, descarga de marcaciones, transformación de datos
y sincronización incremental hacia la base de datos local usando drivers.
"""

import os
import threading
import time as time_module
from datetime import datetime, date, timedelta
from datetime import time as dt_time
from concurrent.futures import ThreadPoolExecutor, as_completed

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

SYNC_AUTO          = os.getenv("SYNC_AUTO",          "false").lower() == "true"
SYNC_HORA_NOCTURNA = os.getenv("SYNC_HORA_NOCTURNA", "02:00")
SYNC_INTERVALO_HORAS = int(os.getenv("SYNC_INTERVALO_HORAS", "2"))

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
        # Agregarle 1 segundo para no repetir el último registro
        # O dejar que el DO NOTHING del insert se encargue, pero optimizamos
        rango_desde = disp["watermark_ultima_fecha"]
    else:
        # Descarga total o desde fecha_inicio provista
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


def _sync_automatico():
    """Ejecutado por schedule (incremental)"""
    try:
        sincronizar(force_historico=False)
        from db.queries.periodos import cerrar_periodos_vencidos
        cerrar_periodos_vencidos()
    except Exception:
        pass


def _sync_nocturna_completa():
    """Ejecutado a las 2 AM (descarga el historial si no es gigante, o force true)."""
    try:
        # Idealmente bajamos todo, pero podemos rellenar huecos bajando ultimos 30 días
        treinta_dias_atras = date.today() - timedelta(days=30)
        sincronizar(fecha_inicio=treinta_dias_atras, force_historico=True)
    except Exception:
        pass


def iniciar_scheduler():
    """Inicia el scheduler en un hilo daemon si SYNC_AUTO=true."""
    if not SYNC_AUTO or not SCHEDULE_DISPONIBLE:
        return

    # Sync nocturna
    schedule.every().day.at(SYNC_HORA_NOCTURNA).do(_sync_nocturna_completa)
    
    # Sync incremental diaria (cada N minutos / horas)
    # Por defecto está configurado a N minutos en dotenv, 
    # pero el plan hablaba de prioridades cada 15m. Aquí para facilidad:
    schedule.every(SYNC_INTERVALO_HORAS).hours.do(_sync_automatico)

    def _run():
        while True:
            schedule.run_pending()
            time_module.sleep(60)

    threading.Thread(target=_run, daemon=True).start()
