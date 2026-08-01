"""
Blueprint de generación de reportes y backups (`app/web/reports_bp.py`).

Rutas (6):
  - POST /api/generar-desde-db      → genera PDF/DOCX desde la BD
  - POST /api/reportes/enviar-email → genera y envía por correo
  - GET  /api/backup/descargar      → dump pg_dump -Fc descargable (Fase 2)
  - GET  /api/backup/csv            → CSV con todas las marcaciones
  - GET  /api/alertas/tardanzas-severas → personas con ≥3 tardanzas severas
  - GET  /api/analytics             → análisis (compatible Fase 5)
"""
from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Blueprint, Response, current_app, g, jsonify, request, send_file, url_for

from app.domain import ai_narrative
from app.domain import analytics as analytics_svc
from app.domain.backup import generar_dump
from app.domain.emailer import enviar_correo
from app.domain.rbac import require_role
from app.domain.reports import (
    DEFAULT_CONFIG,
    DEFAULT_FILTROS,
    analizar_por_persona,
    build_pdf,
    consultar_asistencias,
    deduplicar,
    get_breaks_categorizados_dict,
    get_feriados_set,
    get_horarios,
    get_justificaciones_dict,
    parse_config,
    registrar_audit,
)
from app.extensions import limiter

bp = Blueprint("reports", __name__)


# ── Generación de reportes ───────────────────────────────────────────────

@bp.post("/api/generar-desde-db")
@require_role("superadmin", "admin", "gestor")
def generar_desde_db():

    data = request.json
    try:
        fecha_inicio = datetime.strptime(data["fecha_inicio"], "%Y-%m-%d").date()
        fecha_fin    = datetime.strptime(data["fecha_fin"],    "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return jsonify({"error": "Fechas requeridas en formato YYYY-MM-DD"}), 400

    modo    = data.get("modo", "general")
    persona = data.get("persona", "")
    formato = data.get("formato", "pdf").lower()
    if formato not in ("pdf", "docx"):
        formato = "pdf"
    config = parse_config(data)
    if modo == "varias":
        config["personas"] = data.get("personas", [])

    filtros_raw = data.get("filtros", {})
    filtros = {k: filtros_raw.get(k, v) for k, v in DEFAULT_FILTROS.items()}

    registros = consultar_asistencias(fecha_inicio, fecha_fin)
    if not registros:
        return jsonify({
            "error": "No hay registros en la base de datos para ese rango de fechas. "
                     "Sincroniza primero desde el dispositivo."
        }), 400

    nombre_origen = (
        f"Base de datos "
        f"({fecha_inicio.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')})"
    )
    ext = f".{formato}"
    rpt_filename = f"reporte_{uuid.uuid4().hex[:8]}{ext}"
    pdf_path = current_app.config["REPORTS_FOLDER"] + "/" + rpt_filename

    try:
        build_pdf(
            registros, config, modo, persona, pdf_path, nombre_origen,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
            filtros=filtros, formato=formato,
        )
        labels = {"general": "General", "persona": "Persona", "varias": "Varias_Personas"}
        label  = labels.get(modo, "Reporte")
        try:
            registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion=f"generar_{formato}",
                detalle={"modo": modo, "fecha_inicio": str(fecha_inicio),
                         "fecha_fin": str(fecha_fin), "formato": formato},
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            pass
        return jsonify({
            "success":      True,
            "download_url": url_for("dashboard.descargar", filename=rpt_filename),
            "filename":     f"Reporte_Biometrico_{label}_DB{ext}",
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.post("/api/reportes/enviar-email")
@require_role("superadmin", "admin", "gestor")
def enviar_reporte_email():
    """
    Genera el reporte de una persona y lo envía por correo electrónico.
    """
    data = request.json or {}
    try:
        fecha_inicio = datetime.strptime(data["fecha_inicio"], "%Y-%m-%d").date()
        fecha_fin    = datetime.strptime(data["fecha_fin"],    "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return jsonify({"error": "Fechas requeridas en formato YYYY-MM-DD"}), 400

    persona      = data.get("persona", "")
    destinatario = data.get("email", "").strip()

    if not persona:
        return jsonify({"error": "Especifique una persona para el reporte."}), 400
    if not destinatario:
        return jsonify({"error": "Especifique un correo electrónico de destino."}), 400
    if "@" not in destinatario or "." not in destinatario:
        return jsonify({"error": "Formato de correo electrónico inválido."}), 400

    config = parse_config(data)
    filtros = data.get("filtros", {})
    registros = consultar_asistencias(fecha_inicio, fecha_fin)
    if not registros:
        return jsonify({"error": "No hay registros en la base de datos para ese rango de fechas."}), 400

    nombre_origen = (
        f"Base de datos "
        f"({fecha_inicio.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')})"
    )
    pdf_filename = f"reporte_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = current_app.config["REPORTS_FOLDER"] + "/" + pdf_filename

    try:
        build_pdf(registros, config, "persona", persona, pdf_path, nombre_origen,
                  fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, filtros=filtros)

        asunto = f"Informe de Asistencia - {persona}"
        cuerpo = (
            f"<p>Estimado/a,</p>"
            f"<p>Adjunto encontrará el informe de asistencia para <b>{persona}</b> "
            f"correspondiente al período "
            f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}.</p>"
            f"<br>"
            f"<p>Saludos cordiales,<br>Sistema de Asistencia</p>"
        )

        exito = enviar_correo(destinatario, asunto, cuerpo, pdf_path)

        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        if exito:
            return jsonify({"success": True, "message": f"Correo enviado correctamente a {destinatario}"})
        else:
            return jsonify({"error": "Error al enviar el correo. Verifique la configuración SMTP."}), 500

    except ValueError as e:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return jsonify({"error": str(e)}), 500


# ── Backups ──────────────────────────────────────────────────────────────

@bp.get("/api/backup/descargar")
@limiter.limit("3 per hour, 1 per 10 minutes")
@require_role("superadmin", "admin")
def descargar_backup_db():
    """
    Genera un backup completo de la BD con `pg_dump -Fc` y lo sirve como descarga.

    Solo accesible para superadmin/admin. Registra la descarga en `audit_log`.

    El archivo se genera en un temporal del sistema y se BORRA al terminar
    la transferencia (security C-1: no dejamos dumps residuales en REPORTS_FOLDER).
    """
    import tempfile

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"backup_completo_{timestamp}.dump"

    # Generar en /tmp con sufijo .dump; se borra en finally.
    fd, tmp_path = tempfile.mkstemp(suffix=".dump", prefix=f"backup_{timestamp}_")
    os.close(fd)
    destino = Path(tmp_path)
    size_bytes = 0

    try:
        ruta = generar_dump(destino)
        size_bytes = ruta.stat().st_size

        # Registrar en audit_log ANTES de servir (si la BD está caída, mejor no servir).
        try:
            registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="backup_db_descargar",
                detalle={
                    "filename": filename,
                    "size_bytes": size_bytes,
                },
                ip=request.remote_addr,
            )
        except Exception:  # noqa: BLE001
            current_app.logger.warning(
                "No se pudo registrar backup en audit_log", exc_info=True,
            )

        return send_file(
            str(ruta),
            as_attachment=True,
            download_name=filename,
            mimetype="application/octet-stream",
        )
    except RuntimeError:
        # Loguear con stacktrace; al cliente devolver mensaje genérico (security B2).
        current_app.logger.exception("pg_dump falló al generar backup")
        return jsonify({
            "error": "No se pudo generar el backup de la base de datos.",
        }), 500
    finally:
        # SIEMPRE borrar el dump, incluso si send_file falló a mitad.
        try:
            if destino.exists():
                destino.unlink()
        except OSError:
            current_app.logger.warning(
                "No se pudo borrar el dump temporal %s", destino, exc_info=True,
            )


@bp.get("/api/backup/csv")
@require_role("superadmin", "admin", "gestor")
def descargar_backup_csv():
    """Descarga CSV con todas las marcaciones."""

    registros = consultar_asistencias(date(2000, 1, 1), date.today())
    if not registros:
        return jsonify({"error": "No hay datos para exportar"}), 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id_usuario", "nombre", "fecha", "hora", "tipo"])
    for r in registros:
        writer.writerow([
            r["id_usuario"],
            r["nombre"],
            r["fecha"].strftime("%Y-%m-%d"),
            r["hora"].strftime("%H:%M:%S"),
            r["tipo"],
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition":
                 f"attachment; filename=asistencias_backup_{datetime.now().strftime('%Y%m%d')}.csv"},
    )


# ── Alertas ──────────────────────────────────────────────────────────────

@bp.get("/api/alertas/tardanzas-severas")
def alertas_tardanzas_severas():
    """Personas con ≥3 tardanzas severas en el rango definido."""
    hoy = date.today()
    fi_str = request.args.get("fecha_inicio")
    ff_str = request.args.get("fecha_fin")

    if fi_str:
        try:
            fecha_inicio = datetime.strptime(fi_str, "%Y-%m-%d").date()
        except ValueError:
            fecha_inicio = hoy.replace(day=1)
    else:
        fecha_inicio = hoy.replace(day=1)
    if ff_str:
        try:
            fecha_fin = datetime.strptime(ff_str, "%Y-%m-%d").date()
        except ValueError:
            fecha_fin = hoy
    else:
        fecha_fin = hoy

    registros = consultar_asistencias(fecha_inicio, fecha_fin)
    if not registros:
        return jsonify({"alertas": []})

    config = {"duplicado_min": DEFAULT_CONFIG["duplicado_min"], "excluidos": []}
    justificaciones = get_justificaciones_dict(fecha_inicio, fecha_fin)
    feriados        = get_feriados_set(fecha_inicio, fecha_fin)
    breaks_cat      = get_breaks_categorizados_dict(fecha_inicio, fecha_fin)
    horarios        = get_horarios()

    if not horarios["by_id"]:
        return jsonify({"alertas": [], "warning": "No hay horarios cargados"})

    try:
        registros_dedup, _ = deduplicar(registros, config["duplicado_min"])
        analisis = analizar_por_persona(
            registros_dedup, config, horarios=horarios,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
            justificaciones=justificaciones, feriados=feriados,
            breaks_categorizados=breaks_cat,
        )

        alertas = []
        for persona, info in analisis.items():
            conteo = info["resumen"].get("tardanza_severa", 0)
            if conteo >= 3:
                id_u = ""
                for r in registros:
                    if r["nombre"] == persona:
                        id_u = r.get("id_usuario") or ""
                        break
                alertas.append({
                    "persona": persona,
                    "id_usuario": id_u,
                    "conteo": conteo,
                })
        return jsonify({"alertas": alertas})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


# ── Analytics (Fase 5) — endpoint JSON ──────────────────────────────────

@bp.get("/api/analytics")
@require_role("admin", "superadmin", "gestor")
def api_analytics():
    """Análisis combinado + narrativo IA (Fase 5)."""
    fecha_inicio_str = request.args.get("fecha_inicio")
    fecha_fin_str    = request.args.get("fecha_fin")
    tipo_persona_id  = request.args.get("tipo_persona_id")
    grupo_id         = request.args.get("grupo_id")

    try:
        fecha_inicio = (
            datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            if fecha_inicio_str else date.today() - timedelta(days=30)
        )
        fecha_fin = (
            datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
            if fecha_fin_str else date.today()
        )
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    hallazgos = analytics_svc.analizar(tipo_persona_id, grupo_id, None, fecha_inicio, fecha_fin)
    narrativo = ai_narrative.generar_narrativo(hallazgos) if hallazgos.get("exito") else ""
    hallazgos["narrativo"] = narrativo
    return jsonify(hallazgos)
