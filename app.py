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
import threading
import time
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, Response
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from script import (
    DEFAULT_CONFIG, filtrar_excluidos, deduplicar,
    analizar_dia, analizar_por_persona, generar_pdf, generar_pdf_persona,
)
from collections import defaultdict
import db as db_module
import sync as sync_module
import horarios as horarios_module

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH", "").strip()
APP_MAINTENANCE_PASSWORD_HASH = os.getenv("APP_MAINTENANCE_PASSWORD_HASH", "").strip()

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
        auth_enabled=bool(APP_PASSWORD_HASH)
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
# AUTENTICACIÓN
# ══════════════════════════════════════════════════════════════════════════

@app.before_request
def _require_auth():
    if not APP_PASSWORD_HASH:          # auth deshabilitada (modo dev)
        return None
    if request.endpoint in ("login", "logout", "static"):
        return None
    if not session.get("autenticado"):
        # If it's an AJAX/fetch request (like API routes) return 401
        # otherwise redirect to login page
        if (request.headers.get("Accept") and "application/json" in request.headers.get("Accept")) or request.path.startswith("/api/") or request.endpoint not in ["dashboard", "configuracion_vista", "justificaciones_vista", "reportes_vista", "descargar"]:
            return jsonify({"error": "No autenticado"}), 401
        return redirect(url_for("login"))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not APP_PASSWORD_HASH:
        return redirect(url_for("dashboard"))
    if APP_PASSWORD_HASH and session.get("autenticado"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == 'POST':
        password = request.form.get("password", "")
        if check_password_hash(APP_PASSWORD_HASH, password):
            session["autenticado"] = True
            return redirect(url_for("dashboard"))
        error = "Contraseña incorrecta. Intente nuevamente."
    return render_template("login.html", error=error)


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.context_processor
def utility_processor():
    def get_pending_count():
        return len(db_module.get_justificaciones_pendientes())
    return dict(justificaciones_pendientes_count=get_pending_count())


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

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
    estado['dispositivo_accesible'] = sync_module.ping_dispositivo()
    estado['justificaciones_pendientes'] = len(db_module.get_justificaciones_pendientes())
    return jsonify(estado)


@app.route('/api/sincronizar', methods=['POST'])
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


@app.route('/api/generar-desde-db', methods=['POST'])
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
        return jsonify({
            'success':      True,
            'download_url': f'/descargar/{pdf_filename}',
            'filename':     f'Reporte_Biometrico_{label}_DB.pdf',
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/limpiar-dispositivo', methods=['POST'])
def limpiar_dispositivo():
    data = request.json or {}
    if not data.get('confirmar'):
        return jsonify({
            'error': 'Se requiere { "confirmar": true } en el cuerpo de la solicitud.'
        }), 400
    # Verificar contraseña si la autenticación está habilitada
    pwd_hash_check = APP_MAINTENANCE_PASSWORD_HASH or APP_PASSWORD_HASH
    if pwd_hash_check:
        password = data.get('password', '')
        if not password or not check_password_hash(pwd_hash_check, password):
            return jsonify({'error': 'Contraseña incorrecta. Esta acción requiere autenticación.'}), 403
    try:
        total_borrado = sync_module.limpiar_log_dispositivo()
        return jsonify({'success': True, 'registros_borrados': total_borrado})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# RUTAS DE HORARIOS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════

ALLOWED_HORARIOS_EXT = {".obd", ".ods", ".csv"}


@app.route('/api/horarios/importar', methods=['POST'])
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
            
    if tipo not in ('ausencia', 'tardanza', 'almuerzo', 'incompleto', 'salida_anticipada', 'permiso'):
        return jsonify({'error': "tipo debe ser: ausencia | tardanza | almuerzo | incompleto | salida_anticipada | permiso"}), 400
    try:
        result = db_module.insertar_justificacion(
            id_usuario, nombre, fecha, tipo, motivo, aprobado,
            hora_permitida, estado, duracion_permitida_min,
            hora_retorno_permiso=hora_retorno_permiso,
            incluye_almuerzo=incluye_almuerzo
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


@app.route('/api/justificaciones/<int:jid>', methods=['DELETE'])
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
def eliminar_feriado(fecha):
    if not db_module.eliminar_feriado(fecha):
        return jsonify({'error': f'No existe feriado para la fecha {fecha}'}), 404
    return jsonify({'success': True})


@app.route('/api/feriados/importar', methods=['POST'])
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


# ══════════════════════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════════════════════

@app.route('/api/categorizar-break', methods=['POST'])
def API_categorizar_break():
    data = request.json or {}
    id_usuario = data.get('id_usuario')
    fecha      = data.get('fecha')
    h_ini      = data.get('hora_inicio')
    h_fin      = data.get('hora_fin')
    cat        = data.get('categoria') # 'almuerzo' | 'permiso' | 'injustificado'
    motivo     = data.get('motivo', '')
    aprobado   = session.get('usuario', 'Admin')

    if not all([id_usuario, fecha, h_ini, h_fin, cat]):
        return jsonify({'error': 'Faltan campos (id_usuario, fecha, hora_inicio, hora_fin, categoria)'}), 400
    
    if cat not in ('almuerzo', 'permiso', 'injustificado'):
        return jsonify({'error': 'Categoría inválida'}), 400

    try:
        db_module.insertar_break_categorizado(id_usuario, fecha, h_ini, h_fin, cat, motivo, aprobado)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
