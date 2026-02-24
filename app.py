import os
import uuid
import threading
import time
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from script import (
    cargar_archivo, DEFAULT_CONFIG, filtrar_excluidos, deduplicar,
    analizar_dia, analizar_por_persona, generar_pdf, generar_pdf_persona,
)
from collections import defaultdict
import db as db_module
import sync as sync_module
import horarios as horarios_module

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

UPLOAD_FOLDER  = os.getenv("UPLOAD_FOLDER",  "data/uploads")
REPORTS_FOLDER = os.getenv("REPORTS_FOLDER", "data/reports")

app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['REPORTS_FOLDER']     = REPORTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

os.makedirs(UPLOAD_FOLDER,  exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)

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
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

ALLOWED_EXT = {".xls", ".xlsx", ".csv"}


def _parse_config(data: dict) -> dict:
    return {
        "tardanza_leve":    data.get("tardanza_leve",    DEFAULT_CONFIG["tardanza_leve"]),
        "tardanza_severa":  data.get("tardanza_severa",  DEFAULT_CONFIG["tardanza_severa"]),
        "max_almuerzo_min": int(data.get("max_almuerzo_min", DEFAULT_CONFIG["max_almuerzo_min"])),
        "duplicado_min":    DEFAULT_CONFIG["duplicado_min"],
        "excluidos":        data.get("excluidos", []),
    }


def _build_pdf(registros: list, config: dict, modo: str, persona: str,
               pdf_path: str, nombre_origen: str):
    """
    Aplica filtros, deduplicación, análisis y genera el PDF.
    Centraliza la lógica compartida entre /generar y /generar-desde-db.

    Carga automáticamente los horarios personalizados desde la DB si existen.
    En modo 'general', si hay horarios cargados, solo incluye a las personas
    presentes en el archivo de horarios.
    """
    if config["excluidos"]:
        registros = filtrar_excluidos(registros, config["excluidos"])

    # Cargar horarios personalizados (None si no hay ninguno cargado)
    horarios = db_module.get_horarios()
    if not horarios["by_id"]:
        horarios = None  # Sin horarios → modo global (comportamiento original)

    # Filtrar al conjunto de personas del archivo de horarios (solo modo general)
    if horarios is not None and modo == "general":
        ids_h    = set(horarios["by_id"].keys())
        nom_h    = set(horarios["by_nombre"].keys())
        registros = [
            r for r in registros
            if (r.get("id_usuario") in ids_h)
               or (r["nombre"].upper() in nom_h)
        ]
        if not registros:
            raise ValueError(
                "Ningún registro del período pertenece a personas "
                "del archivo de horarios cargado."
            )

    registros, log_dup = deduplicar(registros, config["duplicado_min"])

    if not registros:
        raise ValueError("No quedaron registros después de aplicar los filtros.")

    if modo == "persona":
        analisis = analizar_por_persona(registros, config, horarios=horarios)
        if persona and persona != "TODAS":
            if persona not in analisis:
                raise ValueError(f"No se encontraron registros para '{persona}'")
            analisis = {persona: analisis[persona]}
        generar_pdf_persona(pdf_path, analisis, config, nombre_origen)
    else:
        por_fecha = defaultdict(list)
        for r in registros:
            por_fecha[r["fecha"]].append(r)
        analisis = {}
        for fecha, regs in sorted(por_fecha.items()):
            analisis[fecha] = analizar_dia(
                regs,
                config["tardanza_leve"],
                config["tardanza_severa"],
                config["max_almuerzo_min"],
                horarios=horarios,
            )
        generar_pdf(pdf_path, analisis, log_dup, config, nombre_origen)


# ══════════════════════════════════════════════════════════════════════════
# RUTAS EXISTENTES (sin cambios de comportamiento)
# ══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/subir', methods=['POST'])
def subir_archivo():
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['archivo']
    if file.filename == '':
        return jsonify({'error': 'Archivo no seleccionado'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Formato no soportado. Usa .xls, .xlsx o .csv'}), 400

    filename  = secure_filename(file.filename)
    save_name = f"{uuid.uuid4().hex}_{filename}"
    filepath  = os.path.join(app.config['UPLOAD_FOLDER'], save_name)
    file.save(filepath)

    try:
        registros = cargar_archivo(filepath)
        nombres   = sorted(set(r["nombre"] for r in registros))
        return jsonify({
            'success':       True,
            'file_id':       save_name,
            'original_name': file.filename,
            'personas':      nombres,
        })
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500


@app.route('/generar', methods=['POST'])
def generar_reporte():
    data    = request.json
    file_id = data.get('file_id')
    modo    = data.get('modo', 'general')
    persona = data.get('persona', '')
    config  = _parse_config(data)

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Archivo expiró o no existe. Vuelve a subirlo.'}), 400

    try:
        registros    = cargar_archivo(filepath)
        pdf_filename = f"reporte_{uuid.uuid4().hex[:8]}.pdf"
        pdf_path     = os.path.join(app.config['REPORTS_FOLDER'], pdf_filename)

        _build_pdf(registros, config, modo, persona, pdf_path,
                   data.get('original_name', 'archivo'))

        label = 'Persona' if modo == 'persona' else 'General'
        return jsonify({
            'success':      True,
            'download_url': f'/descargar/{pdf_filename}',
            'filename':     f'Reporte_Biometrico_{label}.pdf',
        })
    except (ValueError, Exception) as e:
        return jsonify({'error': str(e)}), 500


@app.route('/descargar/<filename>')
def descargar(filename):
    file_path = os.path.join(app.config['REPORTS_FOLDER'], filename)
    if not os.path.exists(file_path):
        return "Archivo no encontrado o expirado", 404
    return send_file(file_path, as_attachment=True)


# ══════════════════════════════════════════════════════════════════════════
# RUTAS DEL DISPOSITIVO ZK
# ══════════════════════════════════════════════════════════════════════════

@app.route('/estado-sync')
def estado_sync():
    estado = db_module.get_estado()
    estado['dispositivo_accesible'] = sync_module.ping_dispositivo()
    return jsonify(estado)


@app.route('/sincronizar', methods=['POST'])
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


@app.route('/sync-status/<job_id>')
def sync_status(job_id):
    return jsonify(sync_module.get_job_status(job_id))


@app.route('/personas-db')
def personas_db():
    fi_str = request.args.get('fecha_inicio')
    ff_str = request.args.get('fecha_fin')
    try:
        fi = datetime.strptime(fi_str, "%Y-%m-%d").date() if fi_str else date(2000, 1, 1)
        ff = datetime.strptime(ff_str, "%Y-%m-%d").date() if ff_str else date.today()
    except ValueError:
        return jsonify({'error': 'Formato de fecha inválido'}), 400
    return jsonify({'personas': db_module.get_personas(fi, ff)})


@app.route('/generar-desde-db', methods=['POST'])
def generar_desde_db():
    data = request.json
    try:
        fecha_inicio = datetime.strptime(data['fecha_inicio'], "%Y-%m-%d").date()
        fecha_fin    = datetime.strptime(data['fecha_fin'],    "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return jsonify({'error': 'Fechas requeridas en formato YYYY-MM-DD'}), 400

    modo    = data.get('modo', 'general')
    persona = data.get('persona', 'TODAS')
    config  = _parse_config(data)

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
        _build_pdf(registros, config, modo, persona, pdf_path, nombre_origen)
        label = 'Persona' if modo == 'persona' else 'General'
        return jsonify({
            'success':      True,
            'download_url': f'/descargar/{pdf_filename}',
            'filename':     f'Reporte_Biometrico_{label}_DB.pdf',
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/limpiar-dispositivo', methods=['POST'])
def limpiar_dispositivo():
    data = request.json or {}
    if not data.get('confirmar'):
        return jsonify({
            'error': 'Se requiere { "confirmar": true } en el cuerpo de la solicitud.'
        }), 400
    try:
        total_borrado = sync_module.limpiar_log_dispositivo()
        return jsonify({'success': True, 'registros_borrados': total_borrado})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# RUTAS DE HORARIOS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════

ALLOWED_HORARIOS_EXT = {".obd", ".ods"}


@app.route('/cargar-horarios', methods=['POST'])
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
        return jsonify({'error': 'Formato no soportado. Use .obd o .ods'}), 400

    filename  = secure_filename(file.filename)
    save_name = f"{uuid.uuid4().hex}_{filename}"
    filepath  = os.path.join(app.config['UPLOAD_FOLDER'], save_name)
    file.save(filepath)

    try:
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


@app.route('/estado-horarios')
def estado_horarios():
    """Retorna el estado actual de los horarios cargados."""
    return jsonify(db_module.get_estado_horarios())


@app.route('/horarios')
def ver_horarios():
    """Retorna todos los horarios cargados (por persona)."""
    horarios = db_module.get_horarios()
    # Convertir a lista ordenada para la UI
    lista = sorted(horarios["by_id"].values(), key=lambda h: h["nombre"])
    return jsonify({'horarios': lista, 'total': len(lista)})


# ══════════════════════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
