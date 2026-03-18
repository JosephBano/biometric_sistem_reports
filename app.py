import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    if os.path.exists('.env'):
        with open('.env', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ.setdefault(k, v)
import uuid
import re
import csv
import io
import sys
import secrets
from email_utils import enviar_correo
import threading
import time
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, Response, g
from werkzeug.utils import secure_filename
from script import (
    DEFAULT_CONFIG, filtrar_excluidos, deduplicar,
    analizar_dia, analizar_por_persona, generar_pdf, generar_pdf_persona,
)
from collections import defaultdict
import db as db_module
import sync as sync_module
import horarios as horarios_module
import auth as auth_module
from decorators import require_role, require_tipo_persona
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.getenv("SESSION_LIFETIME_HOURS", "8")) * 3600
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Rate limiter (memoria; migrable a Redis sin cambios en la lógica)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

@app.errorhandler(429)
def ratelimit_handler(e):
    if request.path.startswith("/api/"):
         return jsonify({"error": "Demasiadas solicitudes. Espere 15 minutos."}), 429
    from flask import flash
    flash("Demasiados intentos. Espere 15 minutos.", "danger")
    return redirect(url_for('login'))

UPLOAD_FOLDER  = os.getenv("UPLOAD_FOLDER",  "data/uploads")
REPORTS_FOLDER = os.getenv("REPORTS_FOLDER", "data/reports")

app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['REPORTS_FOLDER']     = REPORTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

app.config['NOMBRE_SISTEMA'] = os.getenv('NOMBRE_SISTEMA', 'Informes Biométricos')
app.config['NOMBRE_INSTITUCION'] = os.getenv('NOMBRE_INSTITUCION', 'ISTPET')

@app.context_processor
def inject_system_info():
    return dict(
        nombre_sistema=app.config['NOMBRE_SISTEMA'],
        nombre_institucion=app.config['NOMBRE_INSTITUCION'],
    )

try:
    os.makedirs(UPLOAD_FOLDER,  exist_ok=True)
    os.makedirs(REPORTS_FOLDER, exist_ok=True)
except PermissionError:
    UPLOAD_FOLDER = "data/uploads"
    REPORTS_FOLDER = "data/reports"
    os.makedirs(UPLOAD_FOLDER,  exist_ok=True)
    os.makedirs(REPORTS_FOLDER, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['REPORTS_FOLDER'] = REPORTS_FOLDER

# ── Inicializar DB y scheduler ────────────────────────────────────────────
db_module.init_db()
sync_module.iniciar_scheduler()

# ── Limpieza de archivos temporales ──────────────────────────────────────
def _cleanup_temp_files():
    while True:
        try:
            now = time.time()
            for folder in [UPLOAD_FOLDER, REPORTS_FOLDER]:
                for filename in os.listdir(folder):
                    filepath = os.path.join(folder, filename)
                    if os.path.isfile(filepath) and os.stat(filepath).st_mtime < now - 900:
                        os.remove(filepath)
        except Exception:
            pass
        time.sleep(300)

threading.Thread(target=_cleanup_temp_files, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════
# CSRF
# ══════════════════════════════════════════════════════════════════════════

def generate_csrf_token() -> str:
    """Genera (o recupera) el token CSRF de la sesión actual."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf() -> bool:
    """Valida el token CSRF en POST requests no-API."""
    if request.path.startswith("/api/"):
        return True   # Las API usan JSON, no formularios
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    return bool(token and token == session.get("csrf_token"))


app.jinja_env.globals["csrf_token"] = generate_csrf_token


# ══════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN
# ══════════════════════════════════════════════════════════════════════════

_ENDPOINTS_PUBLICOS = {"login", "static"}


@app.before_request
def autenticar_request():
    # Endpoints públicos (login, static) no requieren sesión
    if request.endpoint in _ENDPOINTS_PUBLICOS or request.endpoint is None:
        return

    # Sin sesión → no autenticado
    if "usuario_id" not in session:
        if request.path.startswith("/api/") or \
                "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": "No autenticado"}), 401
        return redirect(url_for("login"))

    # Validar CSRF para todos los POST que no sean API
    if request.method == "POST" and not request.path.startswith("/api/"):
        if not validate_csrf():
            return jsonify({"error": "Token CSRF inválido"}), 403

    # Cargar contexto del usuario
    g.usuario_id    = session["usuario_id"]
    g.tenant_schema = session.get("tenant_schema",
                                  os.environ.get("TENANT_DEFAULT", "istpet"))
    g.roles         = session.get("roles", [])
    g.nombre        = session.get("nombre", "")
    g.tenant_id     = session.get("tenant_id")

    # 4. Validar si el tenant está activo antes de continuar
    if g.tenant_schema != 'public':
        try:
            tenant_info = db_module.get_tenant_by_slug(g.tenant_schema)
            if not tenant_info:
                 # El tenant fue eliminado o no existe
                 session.clear()
                 return jsonify({"error": "Tenant no encontrado"}), 404 if request.path.startswith("/api/") else redirect(url_for("login"))

            if tenant_info and not tenant_info.get("activo", True):
                 # El tenant está inactivo
                 session.clear()
                 if request.path.startswith("/api/"):
                     return jsonify({"error": "Cuenta de institución suspendida"}), 403
                 return render_template("login.html", error="Acceso suspendido. Contacte a soporte."), 403

            # Asignar a variable global
            g.tenant = tenant_info
        except Exception as e:
            # Fallback en caso de problemas con la DB
            g.tenant = {"nombre": "Desconocido", "activo": True, "slug": g.tenant_schema}

    # Cargar tipos de persona del tenant (capacidad para @require_tipo_persona)
    try:
        g.tenant_tipos = db_module.get_tipos_persona(g.tenant_schema)
    except Exception:
        g.tenant_tipos = []


# Helper dinámico para templates Jinja2 y lógica interna
def tenant_tiene_tipo(nombre_tipo: str) -> bool:
    """Helper para validar si un tipo de persona está disponible en el tenant."""
    tipos = getattr(g, "tenant_tipos", []) or []
    return any(t["nombre"].lower() == nombre_tipo.lower() for t in tipos)


@app.context_processor
def inject_user_info():
    """Inyecta datos del usuario autenticado en todos los templates."""
    return dict(
        current_user_nombre=session.get("nombre", ""),
        current_user_roles=session.get("roles", []),
        tenant=getattr(g, "tenant", None),
        tenant_tipos=getattr(g, "tenant_tipos", []),
        tenant_tiene_tipo=tenant_tiene_tipo,
    )


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit(
    "5 per 15 minutes",
    methods=["POST"],
    error_message="Demasiados intentos de inicio de sesión. Espere 15 minutos.",
)
def login():
    if "usuario_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    email_previo = ""

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ip       = request.remote_addr or "desconocida"
        email_previo = email

        # Verificar tasa de intentos fallidos (rate limiting manual sobre BD)
        intentos = db_module.contar_intentos_fallidos(ip, ventana_minutos=15)
        if intentos >= 5:
            error = "Demasiados intentos fallidos. Espere 15 minutos e intente nuevamente."
        else:
            usuario = auth_module.verificar_login(email, password)
            if usuario:
                # Login exitoso
                db_module.registrar_login_intento(ip, email, exitoso=True)
                db_module.actualizar_ultimo_acceso(usuario["id"])

                session.permanent = True
                session["usuario_id"]    = usuario["id"]
                session["tenant_schema"] = usuario["tenant_schema"]
                session["roles"]         = usuario["roles"]
                session["nombre"]        = usuario["nombre"]
                session["tenant_id"]     = usuario["tenant_id"]

                # Audit log
                try:
                    db_module.registrar_audit(
                        tenant_id=usuario["tenant_id"],
                        usuario_id=usuario["id"],
                        accion="login",
                        ip=ip,
                    )
                except Exception:
                    pass

                return redirect(url_for("dashboard"))
            else:
                db_module.registrar_login_intento(ip, email, exitoso=False)
                error = "Credenciales incorrectas. Verifique su email y contraseña."

    return render_template("login.html", error=error, email_previo=email_previo)


@app.route('/logout', methods=['POST'])
def logout():
    # Audit log antes de limpiar la sesión
    try:
        if "usuario_id" in session:
            db_module.registrar_audit(
                tenant_id=session.get("tenant_id"),
                usuario_id=session["usuario_id"],
                accion="logout",
                ip=request.remote_addr,
            )
    except Exception:
        pass
    session.clear()
    return redirect(url_for("login"))


@app.route('/admin/switch-tenant', methods=['POST'])
@require_role('superadmin')
def switch_tenant():
    """Permite al superadmin impersonar otro tenant."""
    slug = request.form.get("tenant_slug")
    if not slug:
        return "Slug requerido", 400
        
    if slug == 'public':
        # Volver al contexto administrativo global
        session["tenant_schema"] = 'public'
        return redirect(url_for("dashboard"))

    tenant = db_module.get_tenant_by_slug(slug)
    if not tenant:
        return "Tenant no encontrado", 404

    session["tenant_schema"] = tenant["slug"]
    session["tenant_id"] = tenant["id"]
    return redirect(url_for("dashboard"))


@app.context_processor
def utility_processor():
    def get_pending_count():
        try:
            return len(db_module.get_justificaciones_pendientes())
        except Exception:
            return 0
    return dict(justificaciones_pendientes_count=get_pending_count())


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

# enviar_correo importada desde email_utils


def _parse_config(data: dict) -> dict:
    return {
        "duplicado_min": DEFAULT_CONFIG["duplicado_min"],
        "excluidos":     data.get("excluidos", []),
    }


def _build_pdf(registros: list, config: dict, modo: str, persona: str,
               pdf_path: str, nombre_origen: str,
               fecha_inicio=None, fecha_fin=None, filtros: dict = None):
    """
    Aplica filtros, deduplicación, análisis y genera el PDF.
    Los horarios son obligatorios; lanza ValueError si no hay ninguno cargado.
    Solo analiza las personas presentes en el archivo de horarios.
    filtros: dict con opciones de secciones/columnas a incluir en el PDF.
    """
    if filtros is None:
        filtros = {}

    if config["excluidos"]:
        registros = filtrar_excluidos(registros, config["excluidos"])

    # Cargar horarios personalizados — obligatorios para generar cualquier reporte
    horarios = db_module.get_horarios()
    if not horarios["by_id"]:
        raise ValueError(
            "No se pueden generar reportes sin horarios cargados. "
            "Suba el archivo de horarios primero."
        )

    # Filtrar al conjunto de personas del archivo de horarios (aplica siempre)
    ids_h = set(horarios["by_id"].keys())
    nom_h = set(horarios["by_nombre"].keys())

    # Personas sin horario (para el reporte especial)
    sin_horario = []
    if filtros.get("reporte_sin_horario") or filtros.get("reporte_todos_usuarios"):
        nombres_vistos = set()
        for r in registros:
            if r["nombre"] not in nombres_vistos:
                nombres_vistos.add(r["nombre"])
                if r.get("id_usuario") not in ids_h and r["nombre"].upper() not in nom_h:
                    sin_horario.append(r["nombre"])
        sin_horario.sort()

    # Si se pide el reporte de "solo sin horario", filtramos para EXCLUIR a los que sí tienen
    if filtros.get("reporte_sin_horario"):
        registros = [
            r for r in registros
            if (r.get("id_usuario") not in ids_h)
               and (r["nombre"].upper() not in nom_h)
        ]
    # Si NO se pide "todos los usuarios" ni "solo sin horario", filtramos para mostrar SOLO los que tienen horario
    elif not filtros.get("reporte_todos_usuarios"):
        registros = [
            r for r in registros
            if (r.get("id_usuario") in ids_h)
               or (r["nombre"].upper() in nom_h)
        ]

    if not registros:
        raise ValueError(
            "No hay registros que coincidan con los filtros aplicados."
        )

    registros, log_dup = deduplicar(registros, config["duplicado_min"])

    if not registros:
        raise ValueError("No quedaron registros después de aplicar los filtros.")

    # Cargar justificaciones y feriados para el período
    justificaciones = db_module.get_justificaciones_dict(fecha_inicio, fecha_fin)
    feriados        = db_module.get_feriados_set(fecha_inicio, fecha_fin)
    breaks_cat      = db_module.get_breaks_categorizados_dict(fecha_inicio, fecha_fin)

    permitir_sin_horario = filtros.get("reporte_sin_horario", False) or filtros.get("reporte_todos_usuarios", False)

    if modo in ("persona", "varias"):
        analisis = analizar_por_persona(
            registros, config, horarios=horarios,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
            justificaciones=justificaciones, feriados=feriados,
            breaks_categorizados=breaks_cat,
            mostrar_todos=filtros.get("mostrar_todos_los_dias", False),
            permitir_sin_horario=permitir_sin_horario,
            verificar_horas=filtros.get("verificar_horas", False),
            mostrar_tiempo_extra=filtros.get("mostrar_tiempo_extra", False),
        )

        if modo == "persona":
            if not persona:
                raise ValueError("Especifique una persona para el modo 'persona'.")
            if persona not in analisis:
                raise ValueError(f"No se encontraron registros para '{persona}'.")
            analisis = {persona: analisis[persona]}
        else:  # varias
            personas_sel = set(config.get("personas", []))
            if not personas_sel:
                raise ValueError("Seleccione al menos una persona.")
            analisis = {k: v for k, v in analisis.items() if k in personas_sel}
            if not analisis:
                raise ValueError(
                    "Ninguna de las personas seleccionadas tiene registros en el período."
                )

        generar_pdf_persona(pdf_path, analisis, config, nombre_origen,
                            filtros=filtros, sin_horario=sin_horario)
    else:
        por_fecha = defaultdict(list)
        for r in registros:
            por_fecha[r["fecha"]].append(r)
        analisis = {}
        for fecha, regs in sorted(por_fecha.items()):
            analisis[fecha] = analizar_dia(regs, horarios,
                                           justificaciones=justificaciones,
                                           feriados=feriados,
                                           permitir_sin_horario=permitir_sin_horario)
        generar_pdf(pdf_path, analisis, log_dup, config, nombre_origen,
                    filtros=filtros, sin_horario=sin_horario)


# ══════════════════════════════════════════════════════════════════════════
# RUTAS EXISTENTES (sin cambios de comportamiento)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/configuracion')
def configuracion_vista():
    return render_template('configuracion.html', active_page='configuracion')

@app.route('/justificaciones-vista')
def justificaciones_vista():
    return render_template('justificaciones.html', active_page='justificaciones')

@app.route('/reportes')
def reportes_vista():
    return render_template('reportes.html', active_page='reportes')


@app.route('/descargar/<filename>')
def descargar(filename):
    file_path = os.path.join(app.config['REPORTS_FOLDER'], filename)
    if not os.path.exists(file_path):
        return "Archivo no encontrado o expirado", 404
    return send_file(file_path, as_attachment=True)


# ══════════════════════════════════════════════════════════════════════════
# RUTAS DEL DISPOSITIVO ZK
# ══════════════════════════════════════════════════════════════════════════

@app.route('/api/estado-sync')
def estado_sync():
    estado = db_module.get_estado()
    # Ahora tenemos múltiples dispositivos, simplificamos el ping global asumiendo True si hay al menos uno
    activos = db_module.get_dispositivos_activos()
    estado['dispositivo_accesible'] = sync_module.ping_dispositivo() if activos else False
    estado['justificaciones_pendientes'] = len(db_module.get_justificaciones_pendientes())
    
    # --- Monitoreo de Capacidad (Fase 1) ---
    capacidad_max = int(os.getenv("ZK_CAPACIDAD_MAX", "80000"))
    estado["capacidad_maxima"] = capacidad_max
    
    ultima = estado.get("ultima_sync")
    # Recuperar registros_en_dispositivo de la DB
    if ultima and ultima.get("registros_en_dispositivo") is not None:
        registros = ultima["registros_en_dispositivo"]
        estado["registros_en_dispositivo"] = registros
        estado["porcentaje_ocupado"] = round((registros / capacidad_max) * 100, 1)
    else:
        estado["registros_en_dispositivo"] = 0
        estado["porcentaje_ocupado"] = 0.0
        
    estado["dias_para_llenado"] = int(max(0, capacidad_max - estado["registros_en_dispositivo"]) / 680)
    
    return jsonify(estado)


@app.route('/api/dispositivos', methods=['GET'])
@require_role('admin', 'superadmin')
def api_get_dispositivos():
    try:
        dispositivos = db_module.get_dispositivos_activos()
        estados = db_module.get_estado_sync_ui()
        for d in dispositivos:
            # Quitamos la pass por seguridad
            d.pop("password", None)
            d.pop("password_enc", None)
            sid = str(d["id"])
            if sid in estados:
                d["sync_estado"] = estados[sid]
        return jsonify({"dispositivos": dispositivos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/dispositivos', methods=['POST'])
@require_role('admin', 'superadmin')
def api_upsert_dispositivo():
    data = request.json or {}
    try:
        if "password_enc" in data and data["password_enc"]:
            from auth import encrypt_device_password
            data["password_enc"] = encrypt_device_password(data["password_enc"])
            
        did = db_module.upsert_dispositivo(data)
        return jsonify({"status": "ok", "id": did})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/dispositivos/<id>/test', methods=['GET'])
@require_role('admin', 'superadmin')
def api_test_dispositivo(id):
    ok = sync_module.ping_dispositivo(id)
    return jsonify({"ok": ok})

@app.route('/api/dispositivos/<id>/sync', methods=['POST'])
@require_role('admin', 'superadmin')
def api_sync_dispositivo(id):
    def _run():
        try:
            sync_module.sincronizar_con_reintento(id, force_historico=False)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "procesando"})


@app.route('/api/sync/estado')
@require_role('admin', 'superadmin')
def api_sync_estado():
    """Estado de sync granular por dispositivo para polling."""
    try:
        estados = db_module.get_estado_sync_ui()
        return jsonify(estados)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/sincronizar', methods=['POST'])
@require_role('admin', 'superadmin')
def sincronizar():
    data             = request.json or {}
    fecha_inicio_str = data.get('fecha_inicio')
    fecha_fin_str    = data.get('fecha_fin')

    try:
        fecha_inicio = (datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
                        if fecha_inicio_str else None)
        fecha_fin    = (datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
                        if fecha_fin_str else None)
    except ValueError:
        return jsonify({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}), 400

    job_id = uuid.uuid4().hex[:12]

    def _run():
        try:
            sync_module.sincronizar(fecha_inicio, fecha_fin, job_id)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'job_id': job_id, 'estado': 'en_progreso'})


@app.route('/api/sync-status/<job_id>')
def sync_status(job_id):
    return jsonify(sync_module.get_job_status(job_id))


@app.route('/api/personas-db')
def personas_db():
    fi_str = request.args.get('fecha_inicio')
    ff_str = request.args.get('fecha_fin')
    try:
        fi = datetime.strptime(fi_str, "%Y-%m-%d").date() if fi_str else date(2000, 1, 1)
        ff = datetime.strptime(ff_str, "%Y-%m-%d").date() if ff_str else date.today()
    except ValueError:
        return jsonify({'error': 'Formato de fecha inválido'}), 400

    # Solo devolver personas que tienen horario cargado
    todas_con_id = db_module.get_personas_con_id(fi, ff)
    horarios = db_module.get_horarios()
    if horarios["by_id"]:
        ids_h = set(horarios["by_id"].keys())
        nom_h = set(horarios["by_nombre"].keys())
        personas = [
            p["nombre"] for p in todas_con_id
            if p["id_usuario"] in ids_h or p["nombre"].upper() in nom_h
        ]
    else:
        personas = [p["nombre"] for p in todas_con_id]
    return jsonify({'personas': personas})


@app.route('/api/alertas/tardanzas-severas')
def alertas_tardanzas_severas():
    """Retorna personas con 3 o más tardanzas severas en el mes actual."""
    hoy = date.today()
    fecha_inicio = hoy.replace(day=1)
    fecha_fin = hoy

    registros = db_module.consultar_asistencias(fecha_inicio, fecha_fin)
    if not registros:
        return jsonify({'alertas': []})

    config = {
        "duplicado_min": DEFAULT_CONFIG["duplicado_min"],
        "excluidos":     [],
    }
    justificaciones = db_module.get_justificaciones_dict(fecha_inicio, fecha_fin)
    feriados = db_module.get_feriados_set(fecha_inicio, fecha_fin)
    breaks_cat = db_module.get_breaks_categorizados_dict(fecha_inicio, fecha_fin)
    horarios = db_module.get_horarios()

    if not horarios["by_id"]:
        return jsonify({'alertas': [], 'warning': 'No hay horarios cargados'})

    try:
        registros_dedup, _ = deduplicar(registros, config["duplicado_min"])
        
        analisis = analizar_por_persona(
            registros_dedup, config, horarios=horarios,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
            justificaciones=justificaciones, feriados=feriados,
            breaks_categorizados=breaks_cat
        )
        
        alertas = []
        for persona, info in analisis.items():
            conteo = info["resumen"].get("tardanza_severa", 0)
            if conteo >= 3:
                # Buscar id_usuario en los registros
                id_u = ""
                for r in registros:
                    if r["nombre"] == persona:
                        id_u = r.get("id_usuario") or ""
                        break
                alertas.append({
                    "persona": persona,
                    "id_usuario": id_u,
                    "conteo": conteo
                })
        return jsonify({'alertas': alertas})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# VISTA DE PRESENCIA CRUDA (Para todos los tenants)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/presencia')
def vista_presencia():
    """Muestra registros crudos de asistencia."""
    fi_str = request.args.get('fecha_inicio')
    ff_str = request.args.get('fecha_fin')
    try:
        fi = datetime.strptime(fi_str, "%Y-%m-%d").date() if fi_str else date.today()
        ff = datetime.strptime(ff_str, "%Y-%m-%d").date() if ff_str else date.today()
    except ValueError:
        return "Formato de fecha inválido", 400

    registros = db_module.consultar_asistencias(fi, ff)
    
    if request.args.get('export') == 'csv':
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID Usuario", "Nombre", "Fecha", "Hora", "Tipo"])
        for r in registros:
            writer.writerow([r["id_usuario"], r["nombre"], r["fecha"].strftime('%Y-%m-%d'), r["hora"].strftime('%H:%M:%S'), r["tipo"]])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=presencia_{fi}_{ff}.csv"})

    return render_template("presencia.html", registros=registros, fecha_inicio=fi, fecha_fin=ff)


@app.route('/api/generar-desde-db', methods=['POST'])
@require_role('superadmin', 'admin', 'gestor')
def generar_desde_db():
    data = request.json
    try:
        fecha_inicio = datetime.strptime(data['fecha_inicio'], "%Y-%m-%d").date()
        fecha_fin    = datetime.strptime(data['fecha_fin'],    "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return jsonify({'error': 'Fechas requeridas en formato YYYY-MM-DD'}), 400

    modo    = data.get('modo', 'general')
    persona = data.get('persona', '')
    config  = _parse_config(data)
    if modo == 'varias':
        config['personas'] = data.get('personas', [])

    # Filtros de secciones/columnas (valores por defecto = activados)
    _DEFAULT_FILTROS = {
        "mostrar_ausencias":          True,
        "mostrar_tardanza_severa":    True,
        "mostrar_tardanza_leve":      True,
        "mostrar_almuerzo":           True,
        "mostrar_incompletos":        True,
        "mostrar_salida_anticipada":  True,
        "mostrar_todos_los_dias":     False,
        "columna_tiempo_dentro":      False,
        "reporte_sin_horario":        False,
        "reporte_todos_usuarios":     False,
        "verificar_horas":            False,
        "mostrar_tiempo_extra":       False,
    }
    filtros_raw = data.get('filtros', {})
    filtros = {k: filtros_raw.get(k, v) for k, v in _DEFAULT_FILTROS.items()}

    registros = db_module.consultar_asistencias(fecha_inicio, fecha_fin)
    if not registros:
        return jsonify({
            'error': 'No hay registros en la base de datos para ese rango de fechas. '
                     'Sincroniza primero desde el dispositivo.'
        }), 400

    nombre_origen = (
        f"Base de datos "
        f"({fecha_inicio.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')})"
    )
    pdf_filename = f"reporte_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path     = os.path.join(app.config['REPORTS_FOLDER'], pdf_filename)

    try:
        _build_pdf(registros, config, modo, persona, pdf_path, nombre_origen,
                   fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, filtros=filtros)
        labels = {'general': 'General', 'persona': 'Persona', 'varias': 'Varias_Personas'}
        label  = labels.get(modo, 'Reporte')
        try:
            db_module.registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="generar_pdf",
                detalle={"modo": modo, "fecha_inicio": str(fecha_inicio),
                         "fecha_fin": str(fecha_fin)},
                ip=request.remote_addr,
            )
        except Exception:
            pass
        return jsonify({
            'success':      True,
            'download_url': f'/descargar/{pdf_filename}',
            'filename':     f'Reporte_Biometrico_{label}_DB.pdf',
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reportes/enviar-email', methods=['POST'])
@require_role('superadmin', 'admin', 'gestor')
def enviar_reporte_email():
    """Genera el reporte de una persona y lo envía por correo electrónico."""
    data = request.json or {}
    try:
        fecha_inicio = datetime.strptime(data['fecha_inicio'], "%Y-%m-%d").date()
        fecha_fin    = datetime.strptime(data['fecha_fin'],    "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return jsonify({'error': 'Fechas requeridas en formato YYYY-MM-DD'}), 400

    persona = data.get('persona', '')
    destinatario = data.get('email', '').strip()

    if not persona:
        return jsonify({'error': 'Especifique una persona para el reporte.'}), 400
    if not destinatario:
        return jsonify({'error': 'Especifique un correo electrónico de destino.'}), 400
    if '@' not in destinatario or '.' not in destinatario:
        return jsonify({'error': 'Formato de correo electrónico inválido.'}), 400

    config = _parse_config(data)
    filtros = data.get('filtros', {})
    registros = db_module.consultar_asistencias(fecha_inicio, fecha_fin)
    if not registros:
        return jsonify({'error': 'No hay registros en la base de datos para ese rango de fechas.'}), 400

    nombre_origen = f"Base de datos ({fecha_inicio.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')})"
    pdf_filename = f"reporte_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path     = os.path.join(app.config['REPORTS_FOLDER'], pdf_filename)

    try:
        _build_pdf(registros, config, "persona", persona, pdf_path, nombre_origen,
                   fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, filtros=filtros)
        
        asunto = f"Informe de Asistencia - {persona}"
        cuerpo = f"""
        <p>Estimado/a,</p>
        <p>Adjunto encontrará el informe de asistencia para <b>{persona}</b> correspondiente al período {fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}.</p>
        <br>
        <p>Saludos cordiales,<br>Sistema de Asistencia</p>
        """
        
        exito = enviar_correo(destinatario, asunto, cuerpo, pdf_path)
        
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
             
        if exito:
            return jsonify({'success': True, 'message': f'Correo enviado correctamente a {destinatario}'})
        else:
            return jsonify({'error': 'Error al enviar el correo. Verifique la configuración SMTP.'}), 500

    except ValueError as e:
        if os.path.exists(pdf_path): os.remove(pdf_path)
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        if os.path.exists(pdf_path): os.remove(pdf_path)
        return jsonify({'error': str(e)}), 500


@app.route('/api/limpiar-dispositivo', methods=['POST'])
@require_role('superadmin', 'admin')
def limpiar_dispositivo():
    data = request.json or {}
    if not data.get('confirmar'):
        return jsonify({
            'error': 'Se requiere { "confirmar": true } en el cuerpo de la solicitud.'
        }), 400
    try:
        total_borrado = sync_module.limpiar_log_dispositivo()
        try:
            db_module.registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="limpiar_dispositivo",
                detalle={"registros_borrados": total_borrado},
                ip=request.remote_addr,
            )
        except Exception:
            pass
        return jsonify({'success': True, 'registros_borrados': total_borrado})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# RUTAS DE RESPALDOS (BACKUPS)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/api/backup/descargar')
@require_role('superadmin', 'admin')
def descargar_backup_db():
    return jsonify({'error': 'Backup de BD PostgreSQL no disponible vía HTTP. Use pg_dump.'}), 501


@app.route('/api/backup/csv')
@require_role('superadmin', 'admin', 'gestor')
def descargar_backup_csv():
    import csv as csv_writer
    import io
    from datetime import date as dt_date
    
    registros = db_module.consultar_asistencias(dt_date(2000, 1, 1), dt_date.today())
    if not registros:
         return jsonify({'error': 'No hay datos para exportar'}), 400
         
    output = io.StringIO()
    writer = csv_writer.writer(output)
    writer.writerow(["id_usuario", "nombre", "fecha", "hora", "tipo"])
    
    for r in registros:
         writer.writerow([
             r["id_usuario"], 
             r["nombre"], 
             r["fecha"].strftime('%Y-%m-%d'), 
             r["hora"].strftime('%H:%M:%S'), 
             r["tipo"]
         ])
         
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=asistencias_backup_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


# ══════════════════════════════════════════════════════════════════════════
# INGESTA DE HISTÓRICOS (.csv / .xlsx)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/api/historicos/importar', methods=['POST'])
@require_role('superadmin', 'admin')
def importar_historicos():
    if 'archivo' not in request.files:
         return jsonify({'error': 'No se envió ningún archivo'}), 400
         
    file = request.files['archivo']
    if file.filename == '':
         return jsonify({'error': 'Archivo no seleccionado'}), 400
         
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.csv', '.xlsx'):
         return jsonify({'error': 'Formato no soportado. Use .csv o .xlsx'}), 400
         
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"historico_{uuid.uuid4().hex}_{filename}")
    file.save(filepath)
    
    registros = []
    try:
         import csv as csv_reader
         if ext == '.csv':
              with open(filepath, newline='', encoding='utf-8-sig') as f:
                   reader = csv_reader.DictReader(f)
                   for row in reader:
                        r_norm = {k.lower().strip(): v for k, v in row.items()}
                        registros.append({
                             "id_usuario": str(r_norm.get("id_usuario") or "").strip(),
                             "nombre":     str(r_norm.get("nombre") or "").strip(),
                             "fecha_hora": str(r_norm.get("fecha_hora") or "").strip(),
                             "tipo":       str(r_norm.get("tipo", "Entrada") or "").strip().title(),
                             "fuente":     "historico"
                        })
         else: # .xlsx
              import openpyxl
              wb = openpyxl.load_workbook(filepath, read_only=True)
              sheet = wb.active
              headers = [str(cell.value).lower().strip() for cell in sheet[1]]
              for row in sheet.iter_rows(min_row=2, values_only=True):
                   if not any(row): continue
                   r_dict = dict(zip(headers, row))
                   f_h = r_dict.get("fecha_hora")
                   if hasattr(f_h, "isoformat"):
                        f_h = f_h.isoformat()
                   registros.append({
                        "id_usuario": str(r_dict.get("id_usuario") or "").strip(),
                        "nombre":     str(r_dict.get("nombre") or "").strip(),
                        "fecha_hora": str(f_h or "").strip(),
                        "tipo":       str(r_dict.get("tipo", "Entrada") or "").strip().title(),
                        "fuente":     "historico"
                   })
                   
         registros_validos = []
         for r in registros:
              if r["nombre"] and r["fecha_hora"]:
                   registros_validos.append(r)
                   
         if not registros_validos:
              return jsonify({'error': 'No se encontraron registros válidos con columnas: nombre, fecha_hora'}), 400
              
         nuevos = db_module.insertar_asistencias(registros_validos)
         return jsonify({
              'success': True,
              'total_leidos': len(registros),
              'total_validos': len(registros_validos),
              'insertados_nuevos': nuevos
         })
         
    except Exception as e:
         return jsonify({'error': f"Error procesando el archivo: {str(e)}"}), 500
    finally:
         if os.path.exists(filepath):
              os.remove(filepath)


# ══════════════════════════════════════════════════════════════════════════
# RUTAS DE HORARIOS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════

ALLOWED_HORARIOS_EXT = {".obd", ".ods", ".csv"}


@app.route('/api/horarios/importar', methods=['POST'])
@require_role('superadmin', 'admin', 'gestor')
def cargar_horarios():
    """
    Recibe un archivo .obd/.ods, lo parsea e inserta los horarios en la DB.
    Retorna cuántos horarios se cargaron y cuántos IDs no se encontraron en ZK.
    """
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['archivo']
    if file.filename == '':
        return jsonify({'error': 'Archivo no seleccionado'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_HORARIOS_EXT:
        return jsonify({'error': 'Formato no soportado. Use .csv, .obd o .ods'}), 400

    filename  = secure_filename(file.filename)
    save_name = f"{uuid.uuid4().hex}_{filename}"
    filepath  = os.path.join(app.config['UPLOAD_FOLDER'], save_name)
    file.save(filepath)

    try:
        if ext == ".csv":
            horarios_lista = horarios_module.parsear_csv(filepath)
        else:
            horarios_lista = horarios_module.parsear_obd(filepath)

        if not horarios_lista:
            return jsonify({'error': 'El archivo no contiene datos de horarios válidos'}), 400

        # Verificar qué IDs del archivo existen en usuarios_zk
        ids_zk = db_module.get_ids_usuarios_zk()

        ids_sin_match = [
            h["id_usuario"]
            for h in horarios_lista
            if h["id_usuario"] not in ids_zk
        ]

        db_module.upsert_horarios(horarios_lista, fuente=file.filename)

        return jsonify({
            'success':        True,
            'total_cargados': len(horarios_lista),
            'sin_match_zk':   ids_sin_match,
            'fuente':         file.filename,
        })

    except RuntimeError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/horarios/estado')
def estado_horarios():
    """Retorna el estado actual de los horarios cargados."""
    return jsonify(db_module.get_estado_horarios())


@app.route('/api/horarios')
def ver_horarios():
    """Retorna todos los horarios cargados (por persona)."""
    horarios = db_module.get_horarios()
    # Convertir a lista ordenada para la UI
    lista = sorted(horarios["by_id"].values(), key=lambda h: h["nombre"])
    return jsonify({'horarios': lista, 'total': len(lista)})


# ══════════════════════════════════════════════════════════════════════════
# HORARIOS — CRUD API + EXPORTAR CSV
# ══════════════════════════════════════════════════════════════════════════

_HORA_RE = re.compile(r"^\d{2}:\d{2}$")
_DIAS    = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _validar_horario_body(data: dict):
    """
    Valida y normaliza el cuerpo JSON para crear/editar un horario.
    Retorna (horario_dict, error_str) — error_str es None si válido.
    """
    id_str = str(data.get("id_usuario", "")).strip()
    nombre = str(data.get("nombre", "")).strip()

    if not id_str:
        return None, "El campo id_usuario es requerido."
    try:
        id_usuario = str(int(float(id_str)))
    except (ValueError, TypeError):
        return None, "id_usuario debe ser un número entero."
    if not nombre:
        return None, "El campo nombre es requerido."

    horario = {
        "id_usuario": id_usuario,
        "nombre":     nombre,
        "domingo":    None,
        "notas":      str(data.get("notas", "")).strip(),
    }
    for dia in _DIAS:
        val = data.get(dia)
        if val is None or str(val).strip() == "":
            horario[dia] = None
        else:
            val_s = str(val).strip()
            if not _HORA_RE.match(val_s):
                return None, f"El campo '{dia}' debe tener formato HH:MM o estar vacío."
            horario[dia] = val_s
            
        col_salida = f"{dia}_salida"
        val_salida = data.get(col_salida)
        if val_salida is None or str(val_salida).strip() == "":
            horario[col_salida] = None
        else:
            val_salida_s = str(val_salida).strip()
            if not _HORA_RE.match(val_salida_s):
                return None, f"El campo '{col_salida}' debe tener formato HH:MM o estar vacío."
            if horario[dia] and val_salida_s <= horario[dia]:
                return None, f"El campo '{col_salida}' debe ser posterior a '{dia}'."
            horario[col_salida] = val_salida_s
            
        col_alm = f"{dia}_almuerzo_min"
        val_alm = data.get(col_alm)
        if val_alm is not None and str(val_alm).strip() != "":
            try:
                horario[col_alm] = int(val_alm)
            except ValueError:
                return None, f"El campo '{col_alm}' debe ser un entero."
        else:
            horario[col_alm] = None

    try:
        almuerzo_min = int(data.get("almuerzo_min", 0))
    except (ValueError, TypeError):
        return None, "almuerzo_min debe ser un entero (0, 30 o 60)."
    if almuerzo_min not in (0, 30, 60):
        return None, "almuerzo_min debe ser 0, 30 o 60."
    horario["almuerzo_min"] = almuerzo_min

    # --- Horas de contrato (Parte I) ---
    horas_semana = data.get("horas_semana")
    horas_mes    = data.get("horas_mes")

    def _parse_horas(val, campo):
        if val is None or str(val).strip() == "":
            return None, None
        try:
            v = float(val)
            if v <= 0:
                raise ValueError
            return v, None
        except (ValueError, TypeError):
            return None, f"'{campo}' debe ser un número positivo."

    hs, err = _parse_horas(horas_semana, "horas_semana")
    if err: return None, err
    hm, err = _parse_horas(horas_mes, "horas_mes")
    if err: return None, err

    if hs is not None and hm is not None:
        return None, "Solo puede especificarse 'horas_semana' O 'horas_mes', no ambas."

    horario["horas_semana"] = hs
    horario["horas_mes"]    = hm

    return horario, None


@app.route('/api/horarios/exportar')
@require_role('superadmin', 'admin', 'gestor')
def exportar_horarios_csv():
    """Genera y descarga los horarios actuales como archivo CSV."""
    horarios = db_module.get_horarios()
    lista = sorted(horarios["by_id"].values(), key=lambda h: h["nombre"])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id_usuario", "nombre", "lunes", "martes", "miercoles",
                     "jueves", "viernes", "sabado", "domingo", 
                     "lunes_salida", "martes_salida", "miercoles_salida", "jueves_salida", "viernes_salida", "sabado_salida", "domingo_salida",
                     "almuerzo_min",
                     "lunes_almuerzo_min", "martes_almuerzo_min", "miercoles_almuerzo_min", "jueves_almuerzo_min", "viernes_almuerzo_min", "sabado_almuerzo_min", "domingo_almuerzo_min",
                     "horas_semana", "horas_mes", "notas"])
    for h in lista:
        writer.writerow([
            h["id_usuario"],
            h["nombre"],
            h.get("lunes")   or "",
            h.get("martes")  or "",
            h.get("miercoles") or "",
            h.get("jueves")  or "",
            h.get("viernes") or "",
            h.get("sabado")  or "",
            h.get("domingo") or "",
            h.get("lunes_salida")   or "",
            h.get("martes_salida")  or "",
            h.get("miercoles_salida") or "",
            h.get("jueves_salida")  or "",
            h.get("viernes_salida") or "",
            h.get("sabado_salida")  or "",
            h.get("domingo_salida") or "",
            h.get("almuerzo_min", 0),
            h.get("lunes_almuerzo_min", ""),
            h.get("martes_almuerzo_min", ""),
            h.get("miercoles_almuerzo_min", ""),
            h.get("jueves_almuerzo_min", ""),
            h.get("viernes_almuerzo_min", ""),
            h.get("sabado_almuerzo_min", ""),
            h.get("domingo_almuerzo_min", ""),
            h.get("horas_semana") or "",
            h.get("horas_mes") or "",
            h.get("notas")   or "",
        ])

    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=horarios.csv"},
    )


@app.route('/api/horarios', methods=['POST'])
@require_role('superadmin', 'admin', 'gestor')
def api_horarios_crear():
    """Crea un nuevo registro de horario. 409 si el ID ya existe."""
    data = request.json or {}
    horario, error = _validar_horario_body(data)
    if error:
        return jsonify({'error': error}), 400

    if db_module.get_horario(horario["id_usuario"]):
        return jsonify({
            'error': f"Ya existe un horario con ID {horario['id_usuario']}. "
                     "Use PUT para actualizar."
        }), 409

    resultado = db_module.upsert_horario(horario, fuente="manual")
    return jsonify({'success': True, 'horario': resultado}), 201


@app.route('/api/horarios/<id_usuario>', methods=['PUT'])
@require_role('superadmin', 'admin', 'gestor')
def api_horarios_actualizar(id_usuario):
    """Actualiza el horario de una persona. 404 si no existe."""
    if not db_module.get_horario(id_usuario):
        return jsonify({'error': f"No existe horario con ID {id_usuario}."}), 404

    data = request.json or {}
    data['id_usuario'] = id_usuario   # asegurar que coincide con la URL
    horario, error = _validar_horario_body(data)
    if error:
        return jsonify({'error': error}), 400

    resultado = db_module.upsert_horario(horario, fuente="manual")
    return jsonify({'success': True, 'horario': resultado})


@app.route('/api/horarios/<id_usuario>', methods=['DELETE'])
@require_role('superadmin', 'admin')
def api_horarios_eliminar(id_usuario):
    """Elimina el horario de una persona. 404 si no existe."""
    if not db_module.delete_horario(id_usuario):
        return jsonify({'error': f"No existe horario con ID {id_usuario}."}), 404
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════════════
# JUSTIFICACIONES
# ══════════════════════════════════════════════════════════════════════════

@app.route('/api/justificaciones', methods=['GET'])
def get_justificaciones():
    fi_str = request.args.get('fecha_inicio')
    ff_str = request.args.get('fecha_fin')
    try:
        fi = datetime.strptime(fi_str, "%Y-%m-%d").date() if fi_str else None
        ff = datetime.strptime(ff_str, "%Y-%m-%d").date() if ff_str else None
    except ValueError:
        return jsonify({'error': 'Formato de fecha inválido'}), 400
    lista = db_module.get_justificaciones(fi, ff)
    return jsonify({'justificaciones': lista})


@app.route('/api/justificaciones', methods=['POST'])
@require_role('superadmin', 'admin', 'gestor')
def crear_justificacion():
    data = request.json or {}
    id_usuario = str(data.get('id_usuario', '')).strip()
    nombre     = str(data.get('nombre', '')).strip()
    fecha      = str(data.get('fecha', '')).strip()
    tipo       = str(data.get('tipo', '')).strip()
    motivo     = str(data.get('motivo', '')).strip()
    aprobado   = str(data.get('aprobado_por', '')).strip()
    hora_permitida = str(data.get('hora_permitida', '')).strip() or None
    estado     = str(data.get('estado', 'aprobada')).strip()
    hora_retorno_permiso = str(data.get('hora_retorno_permiso', '')).strip() or None
    incluye_almuerzo = 1 if data.get('incluye_almuerzo') else 0
    
    recuperable = 1 if data.get('recuperable') else 0
    fecha_recuperacion = str(data.get('fecha_recuperacion', '')).strip() or None
    hora_recuperacion = str(data.get('hora_recuperacion', '')).strip() or None

    duracion_permitida_min = data.get('duracion_permitida_min')
    if duracion_permitida_min is not None and str(duracion_permitida_min).strip() != "":
        try:
            duracion_permitida_min = int(duracion_permitida_min)
        except ValueError:
            return jsonify({'error': 'duracion_permitida_min debe ser un número entero'}), 400
    else:
        duracion_permitida_min = None

    if not id_usuario or not nombre or not fecha or not tipo:
        return jsonify({'error': 'Campos requeridos: id_usuario, nombre, fecha, tipo'}), 400
    
    if tipo == 'permiso':
        if not hora_permitida:
            return jsonify({'error': 'Para permisos es obligatoria la hora de salida'}), 400
        if not hora_retorno_permiso:
            return jsonify({'error': 'Para permisos es obligatoria la hora de retorno'}), 400
        if not _HORA_RE.match(hora_permitida) or not _HORA_RE.match(hora_retorno_permiso):
            return jsonify({'error': 'Las horas deben tener formato HH:MM'}), 400
        if hora_retorno_permiso <= hora_permitida:
            return jsonify({'error': 'La hora de retorno debe ser posterior a la de salida'}), 400
            
    if recuperable:
        if not fecha_recuperacion or not hora_recuperacion:
            return jsonify({'error': 'Para justificaciones recuperables es obligatoria la fecha y hora de recuperación'}), 400
        try:
            f_rec = datetime.strptime(fecha_recuperacion, "%Y-%m-%d").date()
            if f_rec < date.today():
                return jsonify({'error': 'La fecha de recuperación debe ser futura o el día de hoy'}), 400
        except ValueError:
            return jsonify({'error': 'Formato de fecha_recuperacion inválido. Use YYYY-MM-DD'}), 400
        if not _HORA_RE.match(hora_recuperacion):
            return jsonify({'error': 'La hora de recuperación debe tener formato HH:MM'}), 400

    if tipo not in ('ausencia', 'tardanza', 'almuerzo', 'incompleto', 'salida_anticipada', 'permiso'):
        return jsonify({'error': "tipo debe ser: ausencia | tardanza | almuerzo | incompleto | salida_anticipada | permiso"}), 400
    try:
        result = db_module.insertar_justificacion(
            id_usuario, nombre, fecha, tipo, motivo, aprobado,
            hora_permitida, estado, duracion_permitida_min,
            hora_retorno_permiso=hora_retorno_permiso,
            incluye_almuerzo=incluye_almuerzo,
            recuperable=recuperable,
            fecha_recuperacion=fecha_recuperacion,
            hora_recuperacion=hora_recuperacion
        )
        return jsonify({'success': True, 'justificacion': result}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/justificaciones/<int:jid>', methods=['PATCH'])
def actualizar_justificacion_estado(jid):
    """
    Cambia estado de una justificación.
    Body: { "estado": "aprobada" | "rechazada" }
    """
    data = request.json or {}
    estado = data.get('estado')
    if estado not in ('aprobada', 'rechazada', 'pendiente'):
        return jsonify({'error': 'Estado inválido'}), 400
    
    if db_module.actualizar_estado_justificacion(jid, estado):
        return jsonify({'success': True})
    return jsonify({'error': f'No existe justificación con ID {jid}'}), 404


@app.route('/api/justificaciones/<int:jid>', methods=['GET'])
def get_justificacion(jid):
    """Retorna los datos de una justificación por su ID."""
    j = db_module.get_justificacion_by_id(jid)
    if not j:
        return jsonify({'error': f'No existe justificación con ID {jid}'}), 404
    return jsonify({'justificacion': j})


@app.route('/api/justificaciones/<int:jid>', methods=['PUT'])
def actualizar_justificacion(jid):
    """Actualiza una justificación completa por su ID."""
    current = db_module.get_justificacion_by_id(jid)
    if not current:
        return jsonify({'error': f'No existe justificación con ID {jid}'}), 404
        
    data = request.json or {}
    campos = {}
    
    permitidos = [
        'fecha', 'tipo', 'motivo', 'aprobado_por', 'hora_permitida', 'estado', 
        'duracion_permitida_min', 'hora_retorno_permiso', 
        'incluye_almuerzo', 'recuperable', 'fecha_recuperacion', 'hora_recuperacion'
    ]
    for k in permitidos:
        if k in data:
            campos[k] = data[k]
            
    # Validaciones
    if 'duracion_permitida_min' in campos and campos['duracion_permitida_min'] is not None and str(campos['duracion_permitida_min']).strip() != "":
        try:
            campos['duracion_permitida_min'] = int(campos['duracion_permitida_min'])
        except ValueError:
            return jsonify({'error': 'duracion_permitida_min debe ser un número entero'}), 400
    elif 'duracion_permitida_min' in campos:
        campos['duracion_permitida_min'] = None
        
    if 'incluye_almuerzo' in campos:
        campos['incluye_almuerzo'] = 1 if campos['incluye_almuerzo'] else 0
        
    if 'recuperable' in campos:
        campos['recuperable'] = 1 if campos['recuperable'] else 0
        
    rec = campos.get('recuperable', current.get('recuperable', 0))
    if rec:
        f_rec = campos.get('fecha_recuperacion', current.get('fecha_recuperacion'))
        h_rec = campos.get('hora_recuperacion', current.get('hora_recuperacion'))
        if not f_rec or not h_rec:
             return jsonify({'error': 'Para justificaciones recuperables es obligatoria la fecha y hora de recuperación'}), 400
        if not _HORA_RE.match(str(h_rec)):
             return jsonify({'error': 'La hora de recuperación debe tener formato HH:MM'}), 400

    try:
        if db_module.actualizar_justificacion_completa(jid, **campos):
            return jsonify({'success': True})
        return jsonify({'error': 'No se realizaron cambios o campos inválidos'}), 400
    except Exception as e:
        return jsonify({'error': f"Error al actualizar: {str(e)}"}), 500


@app.route('/api/justificaciones/<int:jid>', methods=['DELETE'])
@require_role('superadmin', 'admin')
def eliminar_justificacion(jid):
    if not db_module.eliminar_justificacion(jid):
        return jsonify({'error': f'No existe justificación con ID {jid}'}), 404
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════════════
# FERIADOS
# ══════════════════════════════════════════════════════════════════════════

@app.route('/api/feriados', methods=['GET'])
def get_feriados():
    anio_str = request.args.get('anio')
    if anio_str:
        try:
            anio = int(anio_str)
            fi = date(anio, 1, 1)
            ff = date(anio, 12, 31)
        except ValueError:
            return jsonify({'error': 'anio inválido'}), 400
        lista = db_module.get_feriados(fi, ff)
    else:
        lista = db_module.get_feriados()
    return jsonify({'feriados': lista})


@app.route('/api/feriados', methods=['POST'])
@require_role('superadmin', 'admin')
def crear_feriado():
    data = request.json or {}
    fecha       = str(data.get('fecha', '')).strip()
    descripcion = str(data.get('descripcion', '')).strip()
    tipo        = str(data.get('tipo', 'nacional')).strip() or 'nacional'
    if not fecha or not descripcion:
        return jsonify({'error': 'Campos requeridos: fecha, descripcion'}), 400
    try:
        result = db_module.insertar_feriado(fecha, descripcion, tipo)
        return jsonify({'success': True, 'feriado': result}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/feriados/<fecha>', methods=['DELETE'])
@require_role('superadmin', 'admin')
def eliminar_feriado(fecha):
    if not db_module.eliminar_feriado(fecha):
        return jsonify({'error': f'No existe feriado para la fecha {fecha}'}), 404
    return jsonify({'success': True})


@app.route('/api/feriados/importar', methods=['POST'])
@require_role('superadmin', 'admin')
def importar_feriados():
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    file = request.files['archivo']
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Solo se aceptan archivos .csv'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{filename}")
    file.save(filepath)
    try:
        count = db_module.importar_feriados_csv(filepath)
        return jsonify({'success': True, 'total_importados': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/feriados/exportar', methods=['GET'])
def exportar_feriados():
    lista = db_module.get_feriados()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["fecha", "descripcion", "tipo"])
    for f in lista:
        writer.writerow([f["fecha"], f["descripcion"], f["tipo"]])
    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=feriados.csv"},
    )


@app.route('/api/categorizar-break', methods=['POST'])
@require_role('superadmin', 'admin', 'gestor')
def API_categorizar_break():
    data = request.json or {}
    id_usuario = data.get('id_usuario')
    fecha      = data.get('fecha')
    h_ini      = data.get('hora_inicio')
    h_fin      = data.get('hora_fin')
    cat        = data.get('categoria') # 'almuerzo' | 'permiso' | 'injustificado'
    motivo     = data.get('motivo', '')
    aprobado   = g.get('nombre', session.get('nombre', 'Sistema'))

    if not all([id_usuario, fecha, h_ini, h_fin, cat]):
        return jsonify({'error': 'Faltan campos (id_usuario, fecha, hora_inicio, hora_fin, categoria)'}), 400
    
    if cat not in ('almuerzo', 'permiso', 'injustificado'):
        return jsonify({'error': 'Categoría inválida'}), 400

    try:
        db_module.insertar_break_categorizado(id_usuario, fecha, h_ini, h_fin, cat, motivo, aprobado)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ══════════════════════════════════════════════════════════════════════════
# ADMINISTRACIÓN DE TENANTS (Superadmin)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/admin/tenants', methods=['GET'])
@require_role('superadmin')
def admin_tenants():
    """Lista todos los tenants."""
    tenants = db_module.listar_tenants()
    return render_template("admin/tenants.html", tenants=tenants, active_page="admin_tenants")


@app.route('/admin/tenants', methods=['POST'])
@require_role('superadmin')
def admin_crear_tenant():
    """Crea un nuevo tenant y provisiona su schema."""
    nombre = request.form.get("nombre", "").strip()
    nombre_corto = request.form.get("nombre_corto", "").strip()
    slug = request.form.get("slug", "").strip().lower()
    zona_horaria = request.form.get("zona_horaria", "America/Guayaquil")
    
    # Validaciones básicas
    if not nombre or not slug:
        return "Nombre y Slug son requeridos", 400
        
    if not all(c.isalnum() or c == '_' for c in slug):
        return "Slug debe contener solo letras, números y guiones bajos", 400

    try:
        # 1. Crear registro en public.tenants
        nuevo_tenant = db_module.crear_tenant(nombre, nombre_corto, slug, zona_horaria)
        
        # 2. Provisionar Schema (Tablas y Datos iniciales)
        # Por defecto, habilitar 'Empleado' y 'Practicante'
        db_module.provisionar_schema(slug, tipos_persona=["Empleado", "Practicante"])
        
        return redirect(url_for("admin_tenants") + "?msg=Tenant+creado+con+éxito")
    except Exception as e:
        return f"Error al crear tenant: {str(e)}", 500


@app.route('/admin/tenants/<tenant_id>', methods=['POST'])
@require_role('superadmin')
def admin_actualizar_tenant(tenant_id):
    """Actualiza datos de un tenant (ej: activar/desactivar)."""
    # En HTML los formularios no soportan PUT directamente
    activo = request.form.get("activo") == "1"
    
    try:
        db_module.actualizar_tenant(tenant_id, {"activo": activo})
        return redirect(url_for("admin_tenants") + "?msg=Tenant+actualizado")
    except Exception as e:
         return f"Error: {e}", 500


# ══════════════════════════════════════════════════════════════════════════
# ADMINISTRACIÓN DE USUARIOS
# ══════════════════════════════════════════════════════════════════════════

_ROLES_DISPONIBLES = ["superadmin", "admin", "gestor",
                      "supervisor_grupo", "supervisor_periodo", "readonly"]


def _get_grupos_periodos():
    """Carga grupos y períodos activos para los selects de scope en admin UI."""
    grupos = []
    periodos = []
    try:
        with db_module.get_connection() as conn:
            from sqlalchemy import text as _text
            rows = conn.execute(
                _text("SELECT id::text, nombre FROM grupos WHERE activo = true ORDER BY nombre")
            ).fetchall()
            grupos = [dict(r._mapping) for r in rows]
    except Exception:
        pass
    try:
        with db_module.get_connection() as conn:
            from sqlalchemy import text as _text
            rows = conn.execute(
                _text("""
                    SELECT pv.id::text, p.nombre || ' — ' || pv.nombre AS nombre
                    FROM periodos_vigencia pv
                    JOIN personas p ON p.id = pv.persona_id
                    WHERE pv.estado = 'activo'
                    ORDER BY p.nombre, pv.nombre
                """)
            ).fetchall()
            periodos = [dict(r._mapping) for r in rows]
    except Exception:
        pass
    return grupos, periodos


@app.route('/admin/dispositivos', methods=['GET'])
@require_role('superadmin', 'admin')
def admin_dispositivos():
    return render_template("admin/dispositivos.html", active_page="admin_dispositivos")


@app.route('/admin/usuarios', methods=['GET'])
@require_role('superadmin', 'admin')
def admin_usuarios():
    tenant_id = g.get("tenant_id")
    usuarios = []
    mensaje = request.args.get("msg")
    mensaje_tipo = request.args.get("tipo", "success")
    if tenant_id:
        try:
            usuarios = db_module.get_usuarios_tenant(tenant_id)
        except Exception as e:
            mensaje = f"Error cargando usuarios: {e}"
            mensaje_tipo = "danger"
    grupos, periodos = _get_grupos_periodos()
    return render_template(
        "admin/usuarios.html",
        active_page="admin_usuarios",
        usuarios=usuarios,
        roles_disponibles=_ROLES_DISPONIBLES,
        grupos=grupos,
        periodos=periodos,
        mensaje=mensaje,
        mensaje_tipo=mensaje_tipo,
    )


@app.route('/admin/usuarios', methods=['POST'])
@require_role('superadmin', 'admin')
def admin_crear_usuario():
    nombre   = request.form.get("nombre", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    roles    = request.form.getlist("roles")

    if not nombre or not email or not password:
        return redirect(url_for("admin_usuarios") + "?msg=Campos+requeridos+faltantes&tipo=danger")

    if len(password) < 8:
        return redirect(url_for("admin_usuarios") + "?msg=La+contraseña+debe+tener+al+menos+8+caracteres&tipo=danger")

    # Scopes para supervisores
    configuracion = {}
    if "supervisor_grupo" in roles and request.form.get("supervisor_grupo_id"):
        configuracion["supervisor_grupo_id"] = request.form.get("supervisor_grupo_id")
    if "supervisor_periodo" in roles and request.form.get("supervisor_periodo_id"):
        configuracion["supervisor_periodo_id"] = request.form.get("supervisor_periodo_id")

    # Solo superadmin puede crear otro superadmin
    if "superadmin" in roles and "superadmin" not in g.get("roles", []):
        return redirect(url_for("admin_usuarios") + "?msg=No+tiene+permisos+para+crear+superadmin&tipo=danger")

    try:
        nuevo = auth_module.crear_usuario(
            tenant_id=g.get("tenant_id"),
            email=email,
            password=password,
            nombre=nombre,
            roles=roles,
            configuracion=configuracion,
        )
        try:
            db_module.registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="crear_usuario",
                entidad="usuario",
                entidad_id=nuevo["id"],
                detalle={"email": email, "roles": roles},
                ip=request.remote_addr,
            )
        except Exception:
            pass
        return redirect(url_for("admin_usuarios") + f"?msg=Usuario+'{nombre}'+creado+exitosamente")
    except ValueError as e:
        return redirect(url_for("admin_usuarios") + f"?msg={str(e)}&tipo=danger")
    except Exception as e:
        return redirect(url_for("admin_usuarios") + f"?msg=Error+creando+usuario&tipo=danger")


@app.route('/admin/usuarios/<usuario_id>', methods=['POST'])
@require_role('superadmin', 'admin')
def admin_editar_usuario(usuario_id):
    """Edita roles, scopes y estado activo de un usuario (via POST con _method=PUT)."""
    roles  = request.form.getlist("roles")
    activo = bool(request.form.get("activo"))

    # Solo superadmin puede asignar rol superadmin
    if "superadmin" in roles and "superadmin" not in g.get("roles", []):
        return redirect(url_for("admin_usuarios") + "?msg=No+tiene+permisos+para+asignar+superadmin&tipo=danger")

    configuracion = {}
    if "supervisor_grupo" in roles and request.form.get("supervisor_grupo_id"):
        configuracion["supervisor_grupo_id"] = request.form.get("supervisor_grupo_id")
    if "supervisor_periodo" in roles and request.form.get("supervisor_periodo_id"):
        configuracion["supervisor_periodo_id"] = request.form.get("supervisor_periodo_id")

    try:
        auth_module.actualizar_roles(usuario_id, roles, configuracion)
        if activo:
            auth_module.activar_usuario(usuario_id)
        else:
            auth_module.desactivar_usuario(usuario_id)
            try:
                db_module.registrar_audit(
                    tenant_id=g.get("tenant_id"),
                    usuario_id=g.get("usuario_id"),
                    accion="desactivar_usuario",
                    entidad="usuario",
                    entidad_id=usuario_id,
                    ip=request.remote_addr,
                )
            except Exception:
                pass

        try:
            db_module.registrar_audit(
                tenant_id=g.get("tenant_id"),
                usuario_id=g.get("usuario_id"),
                accion="editar_usuario",
                entidad="usuario",
                entidad_id=usuario_id,
                detalle={"roles": roles, "activo": activo},
                ip=request.remote_addr,
            )
        except Exception:
            pass

        return redirect(url_for("admin_usuarios") + "?msg=Usuario+actualizado+correctamente")
    except Exception as e:
        return redirect(url_for("admin_usuarios") + f"?msg=Error+actualizando+usuario&tipo=danger")


# ══════════════════════════════════════════════════════════════════════════
# PERIODOS Y PERSONAS (FASE 4)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/periodos')
@require_role('admin', 'superadmin', 'gestor')
def periodos_lista():
    tipo_persona_id = request.args.get('tipo_persona_id')
    # Listar periodos activos e historial desde db
    activos = db_module.listar_periodos_activos()
    historial = db_module.listar_periodos_historial()
    return render_template('periodos/lista.html', 
                             active_page='periodos',
                             periodos_activos=activos,
                             periodos_historial=historial)

@app.route('/periodos/crear', methods=['POST'])
@require_role('admin', 'superadmin')
def crear_periodo_route():
    nombre = request.form.get('nombre')
    fecha_inicio_str = request.form.get('fecha_inicio')
    fecha_fin_str = request.form.get('fecha_fin')
    descripcion = request.form.get('descripcion')
    
    if not nombre or not fecha_inicio_str:
        from flask import flash
        flash("Nombre y Fecha Inicio requeridos", "danger")
        return redirect(url_for('periodos_lista'))
        
    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
        fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date() if fecha_fin_str else None
        
        db_module.crear_periodo(nombre=nombre, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, descripcion=descripcion)
        from flask import flash
        flash("Período creado exitosamente", "success")
    except Exception as e:
        from flask import flash
        flash(f"Error: {e}", "danger")
        
    return redirect(url_for('periodos_lista'))

@app.route('/periodos/<id>')
@require_role('admin', 'superadmin', 'gestor')
def periodo_detalle(id):
    periodo = db_module.get_periodo(id)
    if not periodo:
        return "Periodo no encontrado", 404
        
    # Calcular asistencias de las personas asociadas en tiempo real
    personas = db_module.calcular_asistencia_periodo(id)
    
    # Calcular resumen agregado
    total_asistencias = 0
    t_suma = 0
    for p in personas:
        t_suma += p["resumen"]["porcentaje_asistencia"]
    promedio = round(t_suma / len(personas), 2) if personas else 0
    
    resumen_general = {
        "asistencia_promedio": promedio
    }
    
    return render_template('periodos/detalle.html', 
                             active_page='periodos',
                             periodo=periodo,
                             personas=personas,
                             resumen_general=resumen_general)

@app.route('/periodos/<id>/importar-personas', methods=['POST'])
@require_role('admin', 'superadmin')
def periodo_importar_personas_route(id):
    tipo_persona_id = request.form.get('tipo_persona_id')
    file = request.files.get('archivo_csv')
    
    if not file or not tipo_persona_id:
        from flask import flash
        flash("Archivo y Tipo Persona requeridos", "danger")
        return redirect(url_for('periodo_detalle', id=id))
        
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"periodo_{id}_{filename}")
    file.save(filepath)
    
    try:
        resultado = db_module.procesar_csv_personas_periodo(filepath, id, tipo_persona_id)
        from flask import flash
        if resultado.get("exito"):
            msg = f"Cargado: {resultado['procesadas']} personas. Nuevas: {resultado['nuevas']}. Actualizadas: {resultado['actualizadas']}."
            flash(msg, "success")
            if resultado.get("errores"):
                flash(f"Errores en {len(resultado['errores'])} registros.", "warning")
        else:
             flash(f"Error procesando CSV: {resultado.get('error')}", "danger")
    except Exception as e:
         from flask import flash
         flash(f"Error: {e}", "danger")
    finally:
         try: os.remove(filepath) 
         except: pass
         
    return redirect(url_for('periodo_detalle', id=id))

@app.route('/periodos/<id>/cerrar', methods=['POST'])
@require_role('admin', 'superadmin')
def cerrar_periodo_route(id):
    p = db_module.get_periodo(id)
    if p:
         db_module.cerrar_periodo(id)
         from flask import flash
         flash("Período cerrado exitosamente", "success")
    return redirect(url_for('periodos_lista'))


@app.route('/periodos/<id>/archivar', methods=['POST'])
@require_role('admin', 'superadmin')
def archivar_periodo_route(id):
    p = db_module.get_periodo(id)
    if p:
        db_module.archivar_periodo(id)
        from flask import flash
        flash("Período archivado exitosamente", "success")
    return redirect(url_for('periodos_lista'))


# ══════════════════════════════════════════════════════════════════════════
# PERSONAS (FASE 4)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/personas')
@require_role('admin', 'superadmin', 'gestor')
def personas_lista():
    tipo_persona_id = request.args.get('tipo_persona_id')
    grupo_id = request.args.get('grupo_id')
    busqueda = request.args.get('q')
    personas = db_module.listar_personas(tipo_persona_id=tipo_persona_id,
                                         grupo_id=grupo_id,
                                         busqueda=busqueda)
    grupos = db_module.listar_grupos(activo=True)
    return render_template('personas/lista.html',
                           active_page='personas',
                           personas=personas,
                           grupos=grupos,
                           tipo_persona_id=tipo_persona_id,
                           grupo_id=grupo_id,
                           busqueda=busqueda or '')


@app.route('/personas/crear', methods=['POST'])
@require_role('admin', 'superadmin')
def personas_crear():
    from flask import flash
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash("El nombre es requerido", "danger")
        return redirect(url_for('personas_lista'))
    try:
        db_module.crear_persona(
            nombre=nombre,
            identificacion=request.form.get('identificacion') or None,
            tipo_persona_id=request.form.get('tipo_persona_id') or None,
            grupo_id=request.form.get('grupo_id') or None,
            categoria_id=request.form.get('categoria_id') or None,
            email=request.form.get('email') or None,
            telefono=request.form.get('telefono') or None,
            notas=request.form.get('notas') or None,
        )
        flash("Persona creada exitosamente", "success")
    except Exception as e:
        flash(f"Error al crear persona: {e}", "danger")
    return redirect(url_for('personas_lista'))


@app.route('/personas/<id>', methods=['POST'])
@require_role('admin', 'superadmin')
def personas_editar(id):
    from flask import flash
    datos = {}
    for campo in ('nombre', 'identificacion', 'email', 'telefono', 'notas',
                  'tipo_persona_id', 'grupo_id', 'categoria_id'):
        v = request.form.get(campo)
        if v is not None:
            datos[campo] = v or None
    activo_val = request.form.get('activo')
    if activo_val is not None:
        datos['activo'] = activo_val == '1'
    try:
        db_module.actualizar_persona(id, datos)
        flash("Persona actualizada", "success")
    except Exception as e:
        flash(f"Error al actualizar persona: {e}", "danger")
    return redirect(url_for('personas_lista'))


@app.route('/personas/historico')
@require_role('admin', 'superadmin', 'gestor')
def personas_historico():
    identificacion = request.args.get('identificacion', '').strip()
    historico = None
    if identificacion:
        historico = db_module.get_historico_persona(identificacion)
    return render_template('personas/historico.html',
                           active_page='personas',
                           identificacion=identificacion,
                           historico=historico)


# ══════════════════════════════════════════════════════════════════════════
# GRUPOS Y CATEGORÍAS (FASE 4)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/admin/grupos', methods=['GET'])
@require_role('admin', 'superadmin')
def admin_grupos():
    grupos = db_module.listar_grupos()
    return render_template('admin/grupos.html',
                           active_page='admin_grupos',
                           grupos=grupos)


@app.route('/admin/grupos', methods=['POST'])
@require_role('admin', 'superadmin')
def admin_crear_grupo():
    from flask import flash
    nombre = request.form.get('nombre', '').strip()
    tipo_grupo = request.form.get('tipo_grupo', 'general')
    if not nombre:
        flash("El nombre del grupo es requerido", "danger")
        return redirect(url_for('admin_grupos'))
    try:
        db_module.crear_grupo(nombre=nombre, tipo_grupo=tipo_grupo)
        flash("Grupo creado exitosamente", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for('admin_grupos'))


@app.route('/admin/grupos/<id>', methods=['POST'])
@require_role('admin', 'superadmin')
def admin_actualizar_grupo(id):
    from flask import flash
    datos = {}
    if request.form.get('nombre'):
        datos['nombre'] = request.form['nombre'].strip()
    if request.form.get('tipo_grupo'):
        datos['tipo_grupo'] = request.form['tipo_grupo']
    activo_val = request.form.get('activo')
    if activo_val is not None:
        datos['activo'] = activo_val == '1'
    try:
        db_module.actualizar_grupo(id, datos)
        flash("Grupo actualizado", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for('admin_grupos'))


@app.route('/admin/categorias', methods=['GET'])
@require_role('admin', 'superadmin')
def admin_categorias():
    tipo_persona_id = request.args.get('tipo_persona_id')
    categorias = db_module.listar_categorias(tipo_persona_id=tipo_persona_id)
    return render_template('admin/categorias.html',
                           active_page='admin_categorias',
                           categorias=categorias,
                           tipo_persona_id=tipo_persona_id)


@app.route('/admin/categorias', methods=['POST'])
@require_role('admin', 'superadmin')
def admin_crear_categoria():
    from flask import flash
    nombre = request.form.get('nombre', '').strip()
    tipo_persona_id = request.form.get('tipo_persona_id') or None
    if not nombre:
        flash("El nombre de la categoría es requerido", "danger")
        return redirect(url_for('admin_categorias'))
    try:
        db_module.crear_categoria(nombre=nombre, tipo_persona_id=tipo_persona_id)
        flash("Categoría creada exitosamente", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for('admin_categorias'))


@app.route('/admin/categorias/<id>', methods=['POST'])
@require_role('admin', 'superadmin')
def admin_actualizar_categoria(id):
    from flask import flash
    datos = {}
    if request.form.get('nombre'):
        datos['nombre'] = request.form['nombre'].strip()
    activo_val = request.form.get('activo')
    if activo_val is not None:
        datos['activo'] = activo_val == '1'
    try:
        db_module.actualizar_categoria(id, datos)
        flash("Categoría actualizada", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for('admin_categorias'))


# ══════════════════════════════════════════════════════════════════════════
# ANALYTICS E IA (FASE 5)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/analytics')
@require_role('admin', 'superadmin', 'gestor')
def analytics_vista():
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    tipo_persona_id = request.args.get('tipo_persona_id')
    grupo_id = request.args.get('grupo_id')
    
    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date() if fecha_inicio_str else date.today() - timedelta(days=30)
        fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date() if fecha_fin_str else date.today()
    except ValueError:
        return "Formato de fecha inválido", 400
        
    import analytics
    import ia_report
    
    hallazgos = analytics.analizar(
        tipo_persona_id=tipo_persona_id, 
        grupo_id=grupo_id, 
        fecha_inicio=fecha_inicio, 
        fecha_fin=fecha_fin
    )
    
    narrativo = ia_report.generar_narrativo(hallazgos) if hallazgos.get("exito") else ""
        
    grupos = db_module.listar_grupos(activo=True)
    return render_template('analytics.html',
                             active_page='analytics',
                             fecha_inicio=fecha_inicio.strftime('%Y-%m-%d'),
                             fecha_fin=fecha_fin.strftime('%Y-%m-%d'),
                             hallazgos=hallazgos,
                             narrativo=narrativo,
                             grupos=grupos)

@app.route('/analytics/periodo/<periodo_id>')
@require_role('admin', 'superadmin', 'gestor')
def analytics_periodo(periodo_id):
    import analytics as analytics_module
    import ia_report
    periodo = db_module.get_periodo(periodo_id)
    if not periodo:
        return "Período no encontrado", 404
    resumen = analytics_module.resumen_periodo(periodo_id)
    dist = analytics_module.distribucion_asistencia_periodo(periodo_id)
    narrativo = ia_report.generar_narrativo(resumen) if resumen.get("exito") else ""
    return render_template('periodos/detalle.html',
                           active_page='periodos',
                           periodo=periodo,
                           personas=db_module.calcular_asistencia_periodo(periodo_id),
                           resumen_general=resumen.get("resumen_general", {}),
                           distribucion=dist,
                           narrativo=narrativo)


@app.route('/api/analytics/narrativo', methods=['POST'])
@require_role('admin', 'superadmin', 'gestor')
def api_narrativo():
    """Genera narrativo IA on-demand a partir de hallazgos enviados como JSON."""
    import ia_report
    hallazgos = request.json or {}
    if not hallazgos:
        return jsonify({"error": "Se requiere payload de hallazgos"}), 400
    try:
        texto = ia_report.generar_narrativo(hallazgos)
        return jsonify({"narrativo": texto})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/analytics')
@require_role('admin', 'superadmin', 'gestor')
def api_analytics():
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    tipo_persona_id = request.args.get('tipo_persona_id')
    grupo_id = request.args.get('grupo_id')
    
    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date() if fecha_inicio_str else date.today() - timedelta(days=30)
        fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date() if fecha_fin_str else date.today()
    except ValueError:
         return jsonify({"error": "Formato de fecha inválido"}), 400
         
    import analytics
    hallazgos = analytics.analizar(tipo_persona_id, grupo_id, None, fecha_inicio, fecha_fin)
    return jsonify(hallazgos)


# ══════════════════════════════════════════════════════════════════════════
# SEGURIDAD HTTP
# ══════════════════════════════════════════════════════════════════════════

@app.after_request
def agregar_headers_seguridad(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # CSP: permite CDN de Bootstrap, Google Fonts y el propio servidor
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    return response


# ══════════════════════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
