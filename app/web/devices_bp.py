"""
Blueprint de dispositivos biométricos y sync (`app/web/devices_bp.py`).

Rutas (12):
  - GET   /api/estado-sync                       → estado global de sync
  - GET   /api/dispositivos                      → lista de dispositivos
  - POST  /api/dispositivos                      → crear/reemplazar dispositivo
  - PUT   /api/dispositivos/<id>                 → editar dispositivo
  - DELETE /api/dispositivos/<id>                → soft-delete
  - GET   /api/dispositivos/<id>/test            → ping al dispositivo
  - POST  /api/dispositivos/<id>/sync            → lanzar sync en background
  - GET   /api/usuarios-zk                       → usuarios ZK con estado
  - POST  /api/usuarios-zk/<id_usuario>/vincular → vincular ZK con persona
  - GET   /api/personas-lista                    → lista simple de personas
  - GET   /api/sync/estado                       → estado granular por dispositivo
  - POST  /api/sincronizar                       → sync global con job_id
  - GET   /api/sync-status/<job_id>              → estado de un job
  - POST  /api/limpiar-dispositivo               → borrar log del dispositivo
"""
from __future__ import annotations

import threading
import uuid
from datetime import date, datetime

from flask import Blueprint, current_app, g, jsonify, request

from app.domain import schedule as schedule_svc
from app.domain.auth import encrypt_device_password
from app.domain.devices import (
    actualizar_persona,
    clear_thread_tenant,
    eliminar_dispositivo,
    get_dispositivos_activos,
    get_estado,
    get_estado_sync_ui,
    get_horarios,
    get_justificaciones_pendientes,
    get_latest_sync_logs_por_dispositivo,
    get_personas_con_id,
    get_usuarios_zk_con_estado,
    listar_personas,
    registrar_audit,
    set_thread_tenant,
    upsert_dispositivo,
)
from app.domain.rbac import require_role

bp = Blueprint("devices", __name__)


# ── Helpers ──────────────────────────────────────────────────────────────

def _set_thread_tenant_and_run(schema: str, fn, *args, **kwargs):
    """Lanza `fn` en un hilo daemon fijando el tenant en el thread-local."""
    def _run():
        set_thread_tenant(schema)
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("background sync failed")
        finally:
            clear_thread_tenant()

    threading.Thread(target=_run, daemon=True).start()


# ── Estado global de sync ────────────────────────────────────────────────

@bp.get("/api/estado-sync")
def estado_sync():
    estado = get_estado()
    activos = get_dispositivos_activos()
    estado["dispositivo_accesible"] = schedule_svc.ping_dispositivo() if activos else False
    estado["justificaciones_pendientes"] = len(get_justificaciones_pendientes())

    logs = get_latest_sync_logs_por_dispositivo()

    capacidad_total = sum(d.get("capacidad_max", 100000) for d in activos) if activos else 100000
    registros_totales = sum(
        (logs[str(d["id"])].get("registros_en_dispositivo") or 0)
        for d in activos if str(d["id"]) in logs
    )

    estado["capacidad_maxima"] = capacidad_total
    estado["registros_en_dispositivo"] = registros_totales
    estado["porcentaje_ocupado"] = round(
        (registros_totales / capacidad_total) * 100, 1
    ) if capacidad_total > 0 else 0
    estado["dias_para_llenado"] = int(max(0, capacidad_total - registros_totales) / 680)

    return jsonify(estado)


# ── CRUD de dispositivos ─────────────────────────────────────────────────

@bp.get("/api/dispositivos")
@require_role("admin", "superadmin")
def api_get_dispositivos():
    try:
        dispositivos = get_dispositivos_activos()
        estados = get_estado_sync_ui()
        logs = get_latest_sync_logs_por_dispositivo()

        for d in dispositivos:
            d.pop("password", None)
            d.pop("password_enc", None)
            sid = str(d["id"])
            if sid in estados:
                d["sync_estado"] = estados[sid]

            cap = d.get("capacidad_max") or 100000
            d["capacidad_max"] = cap
            if sid in logs:
                en_disp = logs[sid].get("registros_en_dispositivo") or 0
                d["registros_en_dispositivo"] = en_disp
                d["porcentaje_ocupado"] = round((en_disp / cap) * 100, 1) if cap > 0 else 0
            else:
                d["registros_en_dispositivo"] = 0
                d["porcentaje_ocupado"] = 0.0

        return jsonify({"dispositivos": dispositivos})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.post("/api/dispositivos")
@require_role("admin", "superadmin")
def api_upsert_dispositivo():
    data = request.json or {}
    try:
        if "password_enc" in data and data["password_enc"]:
            data["password_enc"] = encrypt_device_password(data["password_enc"])
        did = upsert_dispositivo(data)
        return jsonify({"status": "ok", "id": did})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.put("/api/dispositivos/<id>")
@require_role("admin", "superadmin")
def api_editar_dispositivo(id: str):
    data = request.json or {}
    data["id"] = id
    try:
        if "password_enc" in data and data["password_enc"]:
            data["password_enc"] = encrypt_device_password(data["password_enc"])
        did = upsert_dispositivo(data)
        return jsonify({"status": "ok", "id": did})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.delete("/api/dispositivos/<id>")
@require_role("superadmin")
def api_eliminar_dispositivo(id: str):
    try:
        if not eliminar_dispositivo(id):
            return jsonify({"error": "Dispositivo no encontrado"}), 404
        return jsonify({"status": "ok"})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.get("/api/dispositivos/<id>/test")
@require_role("admin", "superadmin")
def api_test_dispositivo(id: str):
    return jsonify({"ok": schedule_svc.ping_dispositivo(id)})


@bp.post("/api/dispositivos/<id>/sync")
@require_role("admin", "superadmin")
def api_sync_dispositivo(id: str):
    tenant_schema = g.tenant_schema
    _set_thread_tenant_and_run(
        tenant_schema, schedule_svc.sincronizar_con_reintento,
        id, force_historico=False,
    )
    return jsonify({"status": "procesando"})


# ── Usuarios ZK ──────────────────────────────────────────────────────────

@bp.get("/api/usuarios-zk")
@require_role("admin", "superadmin")
def api_usuarios_zk():
    try:
        usuarios = get_usuarios_zk_con_estado()
        vinculados = sum(1 for u in usuarios if u.get("persona_id"))
        return jsonify({
            "usuarios": usuarios,
            "total": len(usuarios),
            "vinculados": vinculados,
            "sin_vincular": len(usuarios) - vinculados,
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.post("/api/usuarios-zk/<id_usuario>/vincular")
@require_role("admin", "superadmin")
def api_vincular_usuario_zk(id_usuario: str):
    data = request.get_json() or {}
    persona_id = (data.get("persona_id") or "").strip()
    if not persona_id:
        return jsonify({"error": "persona_id requerido"}), 400
    try:
        actualizar_persona(persona_id, {"id_usuario_zk": id_usuario})
        return jsonify({"ok": True})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.get("/api/personas-lista")
@require_role("admin", "superadmin")
def api_personas_lista():
    try:
        personas = listar_personas(activo=None)
        return jsonify({"personas": [
            {"id": p["id"], "nombre": p["nombre"],
             "identificacion": p.get("identificacion"),
             "id_usuario_zk": p.get("id_usuario_zk")}
            for p in personas
        ]})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


# ── Sync global ──────────────────────────────────────────────────────────

@bp.get("/api/sync/estado")
@require_role("admin", "superadmin")
def api_sync_estado():
    try:
        return jsonify(get_estado_sync_ui())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.post("/api/sincronizar")
@require_role("admin", "superadmin")
def sincronizar():
    data = request.json or {}
    fecha_inicio_str = data.get("fecha_inicio")
    fecha_fin_str = data.get("fecha_fin")

    try:
        fecha_inicio = (
            datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            if fecha_inicio_str else None
        )
        fecha_fin = (
            datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
            if fecha_fin_str else None
        )
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400

    job_id = uuid.uuid4().hex[:12]
    tenant_schema = g.tenant_schema
    _set_thread_tenant_and_run(
        tenant_schema, schedule_svc.sincronizar,
        fecha_inicio, fecha_fin, job_id,
    )
    return jsonify({"job_id": job_id, "estado": "en_progreso"})


@bp.get("/api/sync-status/<job_id>")
def sync_status(job_id: str):
    return jsonify(schedule_svc.get_job_status(job_id))


# ── Limpiar dispositivo ──────────────────────────────────────────────────

@bp.post("/api/limpiar-dispositivo")
@require_role("superadmin", "admin")
def limpiar_dispositivo():
    data = request.json or {}
    dispositivo_id = data.get("dispositivo_id")

    if not data.get("confirmar") or not dispositivo_id:
        return jsonify({
            "error": 'Se requiere { "confirmar": true, "dispositivo_id": "uuid" } '
                     "en el cuerpo de la solicitud."
        }), 400
    try:
        total_borrado = schedule_svc.limpiar_log_dispositivo(dispositivo_id)
        try:
            registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="limpiar_dispositivo",
                detalle={"registros_borrados": total_borrado, "dispositivo_id": dispositivo_id},
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            pass
        return jsonify({"success": True, "registros_borrados": total_borrado})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


# ── Auxiliar para reportes: personas con horario cargado ─────────────────
# (Esta ruta pertenecía a app.py; la movemos aquí porque es de catálogo
# pero se usa desde reports_bp vía helpers. La conservamos para
# retrocompatibilidad de la URL.)

@bp.get("/api/personas-db")
def personas_db():
    fi_str = request.args.get("fecha_inicio")
    ff_str = request.args.get("fecha_fin")
    try:
        fi = datetime.strptime(fi_str, "%Y-%m-%d").date() if fi_str else date(2000, 1, 1)
        ff = datetime.strptime(ff_str, "%Y-%m-%d").date() if ff_str else date.today()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    todas_con_id = get_personas_con_id(fi, ff)
    horarios = get_horarios()
    if horarios["by_id"]:
        ids_h = set(horarios["by_id"].keys())
        nom_h = set(horarios["by_nombre"].keys())
        personas = [
            p["nombre"] for p in todas_con_id
            if p["id_usuario"] in ids_h or p["nombre"].upper() in nom_h
        ]
    else:
        personas = [p["nombre"] for p in todas_con_id]
    return jsonify({"personas": personas})
