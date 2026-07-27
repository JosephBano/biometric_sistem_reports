"""
Servicio de scheduler y sincronización (`app.domain.schedule`).

API pública (estable, consumida por `app.web.*` y `tests/*`):

  - `init_scheduler(app)`         — punto de entrada en la factory
  - `get_job_status(job_id)`
  - `ping_dispositivo(dispositivo_id=None) -> bool`
  - `sincronizar_con_reintento(...)`
  - `sincronizar(...)`
  - `sincronizar_dispositivo(...)`
  - `verificar_dispositivos_desconectados()`
  - `limpiar_log_dispositivo(dispositivo_id) -> int`

Estado interno:
  - `_jobs`: dict[str, dict] con el estado en vivo de cada job (UI legacy).
  - `_scheduler_started`: bool, guard singleton para evitar doble init.

Migración (Fase 4e.6 del ADR-0001): el cuerpo de `sync.py` (540 LOC) se
movió íntegramente a este módulo. El módulo top-level `sync.py` será
eliminado en el commit de cierre de Fase 4e.8.

Garantías:
  - **Cero side-effects al importar**: la librería `schedule` se importa solo
    dentro de `init_scheduler(app)`. `_scheduler_started` queda en False.
  - **`init_scheduler(app)`** arranca los jobs solo si `app.config["SYNC_AUTO"]`
    es True. Lee `SYNC_HORA_NOCTURNA`, `SYNC_INTERVALO_HORAS`, `BACKUP_AUTO`,
    `BACKUP_HORA`, `BACKUP_DIR`, `BACKUP_RETENCION_DIAS` de `app.config`.
  - **Idempotencia**: llamar `init_scheduler(app)` dos veces es no-op.

Re-exports de `db.queries.horarios` (cumplen la regla de capas del ADR-0001):
  - `delete_horario`, `get_estado_horarios`, `get_horario`, `get_horarios`,
    `get_ids_usuarios_zk`, `upsert_horario`, `upsert_horarios`.
"""
from __future__ import annotations

import logging
import os
import threading
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Optional

from db import (  # noqa: E402  (re-exports para cumplir regla de capas)
    delete_horario,
    get_estado_horarios,
    get_horario,
    get_horarios,
    get_ids_usuarios_zk,
    upsert_horario,
    upsert_horarios,
)
import db as db_module
from db import connection as _db_connection
from drivers import get_driver

log = logging.getLogger("app.domain.schedule")

# ══════════════════════════════════════════════════════════════════════════
# Estado del módulo (jobs en vivo + guard singleton)
# ══════════════════════════════════════════════════════════════════════════

_jobs: dict = {}
_jobs_lock = threading.Lock()
_scheduler_started: bool = False

# Variables de configuración (defaults si no hay app context).
# Se sobreescriben con `app.config[...]` cuando se llama `init_scheduler(app)`.
SYNC_AUTO: bool = os.getenv("SYNC_AUTO", "false").lower() == "true"
SYNC_HORA_NOCTURNA: str = os.getenv("SYNC_HORA_NOCTURNA", "02:00")
SYNC_INTERVALO_HORAS: int = int(os.getenv("SYNC_INTERVALO_HORAS", "2"))

_backup_auto_env = os.getenv("BACKUP_AUTO", "")
BACKUP_AUTO: bool = (_backup_auto_env.lower() == "true") if _backup_auto_env else SYNC_AUTO
BACKUP_HORA: str = os.getenv("BACKUP_HORA", "03:00")
BACKUP_DIR: str = os.getenv("BACKUP_DIR", "/data/backups")
BACKUP_RETENCION_DIAS: int = int(os.getenv("BACKUP_RETENCION_DIAS", "30"))


# ══════════════════════════════════════════════════════════════════════════
# Helpers de jobs (compatibilidad UI legacy)
# ══════════════════════════════════════════════════════════════════════════


def _set_job(job_id: Optional[str], data: dict) -> None:
    """Guarda `data` en `_jobs[job_id]`. No-op si `job_id` es None."""
    if job_id:
        with _jobs_lock:
            _jobs[job_id] = data


def get_job_status(job_id: str) -> dict:
    """Retorna una COPIA del estado actual del job_id (o `no_encontrado`)."""
    with _jobs_lock:
        return dict(_jobs.get(job_id, {"estado": "no_encontrado"}))


# ══════════════════════════════════════════════════════════════════════════
# Utilidades y ping
# ══════════════════════════════════════════════════════════════════════════


def ping_dispositivo(dispositivo_id: Optional[str] = None) -> bool:
    """
    Verifica si el dispositivo (o el primero activo) responde.
    """
    if not dispositivo_id:
        activos = db_module.get_dispositivos_activos()
        if not activos:
            return False
        disp = activos[0]
    else:
        disp = db_module.get_dispositivo(dispositivo_id)
        if not disp:
            return False

    driver = get_driver(disp)
    return driver.test_conexion()


# ══════════════════════════════════════════════════════════════════════════
# Sincronización
# ══════════════════════════════════════════════════════════════════════════


def sincronizar_dispositivo(
    dispositivo_id: str,
    desde: Optional[datetime] = None,
    force_historico: bool = False,
) -> tuple[int, int]:
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
        db_module.actualizar_estado_sync_ui(
            dispositivo_id, "error", 0, 0,
            "No se pudo conectar al dispositivo",
        )
        db_module.registrar_sync(
            datetime.min, datetime.max, 0, 0, False,
            "Tiempo de espera agotado al comunicar con el dispositivo",
            0, dispositivo_id=dispositivo_id,
        )
        raise ConnectionError(
            f"No se pudo conectar al dispositivo {disp['nombre']}"
        )

    # 1. Traer usuarios
    db_module.actualizar_estado_sync_ui(dispositivo_id, "obteniendo_usuarios", 30)
    usuarios = driver.get_usuarios()
    if usuarios:
        db_module.upsert_usuarios(usuarios, dispositivo_id)

    # 2. Determinar fecha de partición
    if not force_historico and disp.get("watermark_ultima_fecha"):
        rango_desde = disp["watermark_ultima_fecha"]
        # PostgreSQL TIMESTAMPTZ devuelve datetimes timezone-aware;
        # los drivers trabajan con datetimes naive → normalizar aquí.
        if rango_desde.tzinfo is not None:
            rango_desde = rango_desde.replace(tzinfo=None)
    else:
        rango_desde = desde

    # 3. Descargar marcaciones
    db_module.actualizar_estado_sync_ui(
        dispositivo_id, "descargando_marcaciones", 50,
    )
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
        db_module.actualizar_watermark(
            dispositivo_id,
            ultimo_id="0",  # Hikvision no tiene ID auto-incremental único
            ultima_fecha=ultimo_reg["fecha_hora"],
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
        dispositivo_id=dispositivo_id,
    )
    db_module.actualizar_estado_sync_ui(
        dispositivo_id, "completado", 100, insertados,
    )

    return asistencias_count, insertados


def sincronizar_con_reintento(
    dispositivo_id: str,
    desde: Optional[datetime] = None,
    force_historico: bool = False,
    max_intentos: int = 3,
):
    """Intenta sincronizar con un backoff exponencial si falla la conexión."""
    for intento in range(max_intentos):
        try:
            return sincronizar_dispositivo(
                dispositivo_id, desde=desde, force_historico=force_historico,
            )
        except ConnectionError:
            if intento == max_intentos - 1:
                return 0, 0
            espera = 2 ** intento * 5
            db_module.actualizar_estado_sync_ui(
                dispositivo_id, "error", mensaje=f"Reintentando en {espera}s",
            )
            time_module.sleep(espera)
        except Exception as e:  # noqa: BLE001
            db_module.actualizar_estado_sync_ui(
                dispositivo_id, "error", 0, 0, str(e),
            )
            db_module.registrar_sync(
                datetime.min, datetime.max, 0, 0, False, str(e), 0,
                dispositivo_id=dispositivo_id,
            )
            return 0, 0


def sincronizar(
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    job_id: Optional[str] = None,
    force_historico: bool = False,
):
    """
    Sincroniza todos los dispositivos usando ThreadPoolExecutor.
    Mantiene compatibilidad con la estructura `job_id` del frontend.
    """
    dispositivos = db_module.get_dispositivos_activos()

    if not dispositivos:
        _set_job(job_id, {"estado": "error", "detalle": "No hay dispositivos activos"})
        return 0, 0

    _set_job(
        job_id,
        {"estado": "procesando", "registros_procesados": 0, "registros_nuevos": 0},
    )

    # Conversión a datetime para el rango_desde
    desde_dt = (
        datetime.combine(fecha_inicio, dt_time.min) if fecha_inicio else None
    )

    tot_descargados = 0
    tot_insertados = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                sincronizar_con_reintento, d["id"], desde_dt, force_historico,
            ): d
            for d in dispositivos
        }
        for future in as_completed(futures):
            d = futures[future]
            try:
                descargados, insertados = future.result()
                tot_descargados += descargados
                tot_insertados += insertados
            except Exception:  # noqa: BLE001
                # Los errores ya los manejó sincronizar_con_reintento
                pass

            # Informar progreso para compatibilidad Legacy
            _set_job(
                job_id,
                {
                    "estado": "procesando",
                    "registros_procesados": tot_descargados,
                    "registros_nuevos": tot_insertados,
                },
            )

    _set_job(
        job_id,
        {
            "estado": "completado",
            "registros_procesados": tot_descargados,
            "registros_nuevos": tot_insertados,
        },
    )

    # Después de todo proceso enviamos alertas
    verificar_dispositivos_desconectados()

    return tot_descargados, tot_insertados


def verificar_dispositivos_desconectados() -> None:
    """Busca si hay dispositivos con 3+ fallas consecutivas y notifica."""
    # Importación local para evitar ciclo con app.domain.emailer.
    from app.domain.emailer import enviar_correo

    fallos = db_module.get_dispositivos_con_fallas_consecutivas(n=3)
    for d in fallos:
        if not db_module.has_alerta_hoy(d["id"]):
            cuerpo = (
                f"Alerta Crítica: El dispositivo '{d['nombre']}' ha fallado "
                f"en sus últimos 3 intentos de sincronización."
            )
            admin_email = os.getenv("ADMIN_EMAIL", "admin@localhost")
            enviar_correo(
                admin_email,
                "Fallos de Sincronización en Dispositivo",
                cuerpo,
            )
            db_module.marcar_alerta_enviada(d["id"])


def limpiar_log_dispositivo(dispositivo_id: str) -> int:
    """Limpia los registros del dispositivo especificado y retorna el total borrado."""
    disp = db_module.get_dispositivo(dispositivo_id)
    if not disp:
        raise ValueError(f"Dispositivo {dispositivo_id} no encontrado.")

    driver = get_driver(disp)
    if not driver.test_conexion():
        raise ConnectionError(
            f"No se pudo conectar al dispositivo {disp['nombre']}."
        )

    return driver.clear_asistencias()


# ══════════════════════════════════════════════════════════════════════════
# Helpers internos del scheduler
# ══════════════════════════════════════════════════════════════════════════


def _get_tenant_slugs() -> list[str]:
    """Retorna los slugs de todos los tenants activos."""
    from sqlalchemy import text

    try:
        with _db_connection.get_connection("public") as conn:
            rows = conn.execute(
                text("SELECT slug FROM tenants WHERE activo = true ORDER BY slug")
            ).fetchall()
            return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return [os.getenv("TENANT_DEFAULT", "istpet")]


def _redactar_error(mensaje: str) -> str:
    """Redacta posibles secretos de un mensaje de error antes de loguearlo/enviarlo.

    Quita: passwords en connection strings, PGPASSWORD, hostnames internos largos.
    """
    import re

    # Quitar user:password@host de connection strings
    s = re.sub(r"://[^:@]+:[^@]+@", "://***:***@", mensaje)
    # Quitar password=... si aparece
    s = re.sub(r"(?i)(password\s*=\s*)([^\s;&]+)", r"\1***", s)
    # Limitar tamaño (defensa contra logs enormes)
    return s[:500]


def _registrar_corrida_sync(
    job: str,
    tenant_slug: Optional[str],
    inicio: datetime,
    fin: datetime,
    ok: bool,
    descargados: Optional[int],
    insertados: Optional[int],
    detalle: Optional[str],
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
    except Exception:  # noqa: BLE001
        log.exception(
            "No se pudo registrar corrida del scheduler en BD (job=%s)", job
        )


def _backup_diario() -> None:
    """Ejecutado por schedule (BACKUP_HORA) — pg_dump -Fc con retención.

    Si el backup falla, envía email a ADMIN_EMAIL. Si OK, purga los .dump
    con mtime > BACKUP_RETENCION_DIAS. Resultado se registra en
    `public.scheduler_runs` (job=`backup_diario`, tenant_slug=NULL).
    """
    log.info("Iniciando backup diario (scheduler)")

    from app.domain.backup import generar_dump, purgar_backups_viejos
    from app.domain.emailer import enviar_correo

    inicio = datetime.now(timezone.utc)
    timestamp = inicio.strftime("%Y%m%d_%H%M")
    filename = f"backup_completo_{timestamp}.dump"
    destino = Path(BACKUP_DIR) / filename

    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ruta = generar_dump(destino)
        size_mb = ruta.stat().st_size / (1024 * 1024)

        # Retención solo tras éxito (no borrar si el backup del día falló).
        borrados = purgar_backups_viejos(
            Path(BACKUP_DIR), dias=BACKUP_RETENCION_DIAS,
        )
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
    except Exception as e:  # noqa: BLE001
        log.exception("backup_diario falló")
        detalle_redactado = _redactar_error(str(e))
        _registrar_corrida_sync(
            job="backup_diario",
            tenant_slug=None,
            inicio=inicio,
            fin=datetime.now(timezone.utc),
            ok=False,
            descargados=None,
            insertados=None,
            detalle=detalle_redactado,
        )
        # Email de alerta al admin (con secreto redactado).
        admin_email = os.getenv("ADMIN_EMAIL", "")
        if admin_email:
            try:
                enviar_correo(
                    admin_email,
                    "Fallo en backup diario",
                    (
                        f"<p>El backup diario falló: "
                        f"<code>{detalle_redactado}</code></p>"
                        f"<p>Verificar volumen <code>{BACKUP_DIR}</code> "
                        f"y logs del scheduler.</p>"
                    ),
                )
            except Exception:  # noqa: BLE001
                log.exception("No se pudo enviar email de alerta de backup")


def _sync_automatico() -> None:
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
        except Exception as e:  # noqa: BLE001
            log.exception("sync_incremental falló para tenant=%s", slug)
            _registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle=_redactar_error(str(e)),
            )
        finally:
            db_module.clear_thread_tenant()


def _sync_nocturna_completa() -> None:
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
                fecha_inicio=treinta_dias_atras, force_historico=True,
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
        except Exception as e:  # noqa: BLE001
            log.exception("sync_nocturna falló para tenant=%s", slug)
            _registrar_corrida_sync(
                job="sync_nocturna",
                tenant_slug=slug,
                inicio=inicio,
                fin=datetime.now(timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle=_redactar_error(str(e)),
            )
        finally:
            db_module.clear_thread_tenant()

    # Retención de scheduler_runs: borrar filas > 90 días.
    try:
        from db.queries import scheduler_runs

        borradas = scheduler_runs.purgar_mayor_a(dias=90)
        if borradas:
            log.info("scheduler_runs: purgadas %s filas > 90 días", borradas)
    except Exception:  # noqa: BLE001
        log.exception("scheduler_runs purga falló (no crítico)")


# ══════════════════════════════════════════════════════════════════════════
# Entry point del scheduler
# ══════════════════════════════════════════════════════════════════════════


def init_scheduler(app) -> None:
    """Inicia el scheduler en un hilo daemon si `app.config["SYNC_AUTO"]`.

    Loguea siempre su estado al arrancar (ACTIVO/INACTIVO). Es idempotente:
    si ya está activo, ignora la segunda llamada.

    Variables leídas de `app.config` (no de `os.environ` directamente):
      - `SYNC_AUTO`              (bool)
      - `SYNC_HORA_NOCTURNA`     (str, formato "HH:MM")
      - `SYNC_INTERVALO_HORAS`   (int)
      - `BACKUP_AUTO`            (bool)
      - `BACKUP_HORA`            (str)
      - `BACKUP_DIR`             (str, ruta)
      - `BACKUP_RETENCION_DIAS`  (int)

    Variables de entorno que se usan como fallback (compatibilidad hacia
    atrás con `sync.py` legacy): si `app.config` no tiene la clave, se
    usa `os.getenv(...)`.
    """
    global _scheduler_started

    # Override de las variables globales con lo que diga `app.config`.
    sync_auto = app.config.get(
        "SYNC_AUTO",
        os.getenv("SYNC_AUTO", "false"),
    )
    sync_auto = str(sync_auto).lower() == "true"
    sync_hora = app.config.get(
        "SYNC_HORA_NOCTURNA",
        os.getenv("SYNC_HORA_NOCTURNA", "02:00"),
    )
    sync_intervalo = int(
        app.config.get(
            "SYNC_INTERVALO_HORAS",
            os.getenv("SYNC_INTERVALO_HORAS", "2"),
        )
    )
    backup_auto_raw = app.config.get(
        "BACKUP_AUTO",
        os.getenv("BACKUP_AUTO", str(sync_auto).lower()),
    )
    backup_auto = str(backup_auto_raw).lower() == "true"
    backup_hora = app.config.get(
        "BACKUP_HORA", os.getenv("BACKUP_HORA", "03:00"),
    )
    backup_dir = app.config.get(
        "BACKUP_DIR", os.getenv("BACKUP_DIR", "/data/backups"),
    )
    backup_retencion = int(
        app.config.get(
            "BACKUP_RETENCION_DIAS",
            os.getenv("BACKUP_RETENCION_DIAS", "30"),
        )
    )

    # `schedule` se importa solo aquí para no contaminar el namespace al
    # importar el módulo en tests (Fase 4e.6 — ADR-0001).
    try:
        import schedule as _schedule
        schedule_disponible = True
    except ImportError:
        schedule_disponible = False

    if not sync_auto or not schedule_disponible:
        log.info(
            "Scheduler INACTIVO (SYNC_AUTO=%s, schedule_disponible=%s)",
            sync_auto, schedule_disponible,
        )
        return

    if _scheduler_started:
        log.warning("Scheduler ya estaba iniciado; se ignora segunda llamada")
        return

    # Sync nocturna
    _schedule.every().day.at(sync_hora).do(_sync_nocturna_completa)

    # Sync incremental
    _schedule.every(sync_intervalo).hours.do(_sync_automatico)

    # Backup diario (si está activado)
    if backup_auto:
        _schedule.every().day.at(backup_hora).do(_backup_diario)
        log.info(
            "Backup diario ACTIVO a las %s, dir=%s, retención=%sd",
            backup_hora, backup_dir, backup_retencion,
        )
    else:
        log.info("Backup diario INACTIVO (BACKUP_AUTO=false)")

    def _run() -> None:
        # Loop inkillable: cualquier excepción en una corrida NO mata el hilo.
        while True:
            try:
                _schedule.run_pending()
            except Exception:  # noqa: BLE001
                log.exception("scheduler loop falló; continuando")
            time_module.sleep(60)

    threading.Thread(
        target=_run, daemon=True, name="biometrico-scheduler",
    ).start()
    _scheduler_started = True

    log.info(
        "Scheduler ACTIVO: nocturna %s, incremental cada %sh",
        sync_hora, sync_intervalo,
    )


def proxima_corrida() -> Optional[str]:
    """ISO timestamp de la próxima corrida programada, o `None`.

    Encapsula el acceso a la librería `schedule` (paquete de terceros) para
    que `app/web/*` no importe librerías de terceros ni el módulo legacy
    `sync` directamente (ADR-0001).
    """
    try:
        import schedule as _schedule
    except ImportError:
        return None

    proximas = [j.next_run for j in _schedule.get_jobs() if j.next_run]
    return min(proximas).isoformat() if proximas else None


__all__ = [
    "init_scheduler",
    "get_job_status",
    "ping_dispositivo",
    "sincronizar",
    "sincronizar_con_reintento",
    "sincronizar_dispositivo",
    "verificar_dispositivos_desconectados",
    "limpiar_log_dispositivo",
    "_jobs",
    "delete_horario",
    "get_estado_horarios",
    "get_horario",
    "get_horarios",
    "get_ids_usuarios_zk",
    "upsert_horario",
    "upsert_horarios",
]
