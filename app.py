import os
import uuid
import threading
import time
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from script import cargar_archivo, DEFAULT_CONFIG, filtrar_excluidos, deduplicar, analizar_dia, analizar_por_persona, generar_pdf, generar_pdf_persona
from collections import defaultdict

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
REPORTS_FOLDER = 'reports'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['REPORTS_FOLDER'] = REPORTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)

# Limpiar archivos temporales en background
def cleanup_temp_files():
    while True:
        try:
            now = time.time()
            for folder in [UPLOAD_FOLDER, REPORTS_FOLDER]:
                for filename in os.listdir(folder):
                    filepath = os.path.join(folder, filename)
                    # 15 minutes TTL
                    if os.path.isfile(filepath) and os.stat(filepath).st_mtime < now - 900:
                        os.remove(filepath)
        except Exception:
            pass
        time.sleep(300)

thread = threading.Thread(target=cleanup_temp_files, daemon=True)
thread.start()

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
    
    if not (file.filename.endswith('.xls') or file.filename.endswith('.xlsx') or file.filename.endswith('.csv')):
        return jsonify({'error': 'Formato no soportado. Usa .xls, .xlsx o .csv'}), 400

    filename = secure_filename(file.filename)
    unique_id = str(uuid.uuid4())
    save_name = f"{unique_id}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], save_name)
    file.save(filepath)

    try:
        registros = cargar_archivo(filepath)
        nombres = sorted(list(set(r["nombre"] for r in registros)))
        return jsonify({
            'success': True,
            'file_id': save_name,
            'original_name': file.filename,
            'personas': nombres
        })
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500

@app.route('/generar', methods=['POST'])
def generar_reporte():
    data = request.json
    file_id = data.get('file_id')
    original_name = data.get('original_name', 'archivo')
    modo = data.get('modo', 'general') # general, persona
    persona = data.get('persona', '')
    
    config = {
        "tardanza_leve": data.get('tardanza_leve', DEFAULT_CONFIG["tardanza_leve"]),
        "tardanza_severa": data.get('tardanza_severa', DEFAULT_CONFIG["tardanza_severa"]),
        "max_almuerzo_min": int(data.get('max_almuerzo_min', DEFAULT_CONFIG["max_almuerzo_min"])),
        "duplicado_min": DEFAULT_CONFIG["duplicado_min"],
        "excluidos": data.get('excluidos', [])
    }

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Archivo expiró o no existe. Vuelve a subirlo.'}), 400

    try:
        # Re-cargar
        registros = cargar_archivo(filepath)
        if config["excluidos"]:
            registros = filtrar_excluidos(registros, config["excluidos"])
        registros, log_dup = deduplicar(registros, config["duplicado_min"])

        pdf_filename = f"reporte_{uuid.uuid4().hex[:8]}.pdf"
        pdf_path = os.path.join(app.config['REPORTS_FOLDER'], pdf_filename)

        if modo == "persona":
            analisis = analizar_por_persona(registros, config)
            if persona and persona != "TODAS":
                if persona in analisis:
                    analisis = {persona: analisis[persona]}
                else:
                    return jsonify({'error': f'No se encontraron registros para {persona}'}), 400
            
            generar_pdf_persona(
                pdf_path,
                analisis,
                config,
                original_name
            )
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
                    config["max_almuerzo_min"]
                )
            generar_pdf(
                pdf_path,
                analisis,
                log_dup,
                config,
                original_name
            )

        return jsonify({
            'success': True,
            'download_url': f'/descargar/{pdf_filename}',
            'filename': f"Reporte_Biometrico_{'Persona' if modo == 'persona' else 'General'}.pdf"
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/descargar/<filename>')
def descargar(filename):
    file_path = os.path.join(app.config['REPORTS_FOLDER'], filename)
    if not os.path.exists(file_path):
        return "Archivo no encontrado o expirado", 404
    
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
