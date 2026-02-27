"""
Módulo para gestión de horarios personalizados de personal.

Parsea el archivo .obd/.ods (OpenDocument Spreadsheet) con horarios
individuales por día de la semana y los expone para su uso en el
análisis de asistencia.

Columnas esperadas en el archivo:
  NOMBRES | ID | LUNES | MARTES | MIERCOLES | JUEVES | VIERNES | FIN DE SEMANA | ALMUERZO | NOTAS

Reglas de negocio:
  - Columna día = "NO" → persona no trabaja ese día; sin alertas.
  - FIN DE SEMANA aplica solo al sábado; domingo nunca genera alertas.
  - ALMUERZO: TRUE=60 min | FALSE=sin almuerzo | "30 min"=30 min.
  - El sábado nunca se analiza almuerzo, independientemente de ALMUERZO.
"""

import re
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════════════════

# Mapeo de weekday Python → columna en la tabla horarios_personal
# 0=lunes, 1=martes, ..., 5=sábado, 6=domingo
WEEKDAY_COLUMNA = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",
    6: "domingo",
}


# ══════════════════════════════════════════════════════════════════════════
# PARSING DEL ARCHIVO ODS/OBD
# ══════════════════════════════════════════════════════════════════════════

def parsear_obd(ruta: str) -> list[dict]:
    """
    Lee el archivo .obd/.ods de horarios y retorna una lista de dicts,
    uno por persona, con la hora de entrada por día de la semana.

    Args:
        ruta: Ruta absoluta al archivo .obd o .ods.

    Returns:
        Lista de dicts con keys: id_usuario, nombre, lunes, martes,
        miercoles, jueves, viernes, sabado, domingo, almuerzo_min, notas.

    Raises:
        RuntimeError: Si odfpy no está instalado o el archivo es inválido.
    """
    try:
        from odf.opendocument import load
        from odf.table import Table, TableRow, TableCell
        from odf import teletype
    except ImportError:
        raise RuntimeError(
            "La librería odfpy no está instalada. "
            "Ejecuta: pip install odfpy"
        )

    try:
        doc = load(ruta)
    except Exception as e:
        raise RuntimeError(f"No se pudo leer el archivo de horarios: {e}")

    tablas = doc.spreadsheet.getElementsByType(Table)
    if not tablas:
        raise RuntimeError("El archivo no contiene hojas de cálculo.")

    hoja  = tablas[0]
    filas = hoja.getElementsByType(TableRow)

    horarios = []
    for i, fila in enumerate(filas):
        if i == 0:
            continue  # Saltar encabezado

        celdas  = fila.getElementsByType(TableCell)
        valores = _expandir_celdas(celdas, teletype)

        if len(valores) < 9:
            continue

        nombre = str(valores[0]).strip() if valores[0] is not None else ""
        id_str = str(valores[1]).strip() if valores[1] is not None else ""

        if not nombre or not id_str:
            continue

        # Normalizar ID a string entero (el ODS puede dar float "5.0")
        try:
            id_usuario = str(int(float(id_str)))
        except (ValueError, TypeError):
            continue  # Fila sin ID numérico válido

        horario = {
            "id_usuario":   id_usuario,
            "nombre":       nombre,
            "lunes":        _normalizar_hora(valores[2]),
            "martes":       _normalizar_hora(valores[3]),
            "miercoles":    _normalizar_hora(valores[4]),
            "jueves":       _normalizar_hora(valores[5]),
            "viernes":      _normalizar_hora(valores[6]),
            "sabado":       _normalizar_hora(valores[7]),
            "domingo":      None,  # No aplica; domingo no genera alertas
            "almuerzo_min": _normalizar_almuerzo(valores[8]),
            "notas":        str(valores[9]).strip() if len(valores) > 9 and valores[9] else "",
        }
        horarios.append(horario)

    return horarios


def _expandir_celdas(celdas, teletype) -> list:
    """
    Extrae los valores de una fila ODS, expandiendo celdas repetidas
    (table:number-columns-repeated) y tipando los valores correctamente.

    Usa celda.attributes (dict con claves (namespace, localname)) en lugar
    de getAttribute() para compatibilidad con odfpy 1.4.x.
    """
    from odf.namespaces import OFFICENS, TABLENS

    K_REP    = (TABLENS,  "number-columns-repeated")
    K_TYPE   = (OFFICENS, "value-type")
    K_TIME   = (OFFICENS, "time-value")
    K_BOOL   = (OFFICENS, "boolean-value")
    K_FLOAT  = (OFFICENS, "value")

    valores = []
    for celda in celdas:
        attrs        = celda.attributes
        rep          = attrs.get(K_REP)
        repeticiones = int(rep) if rep else 1

        tipo_val = attrs.get(K_TYPE)

        if tipo_val == "time":
            raw   = attrs.get(K_TIME)
            valor = _iso_duration_to_hhmm(raw)
        elif tipo_val == "boolean":
            raw   = attrs.get(K_BOOL)
            valor = "TRUE" if raw == "true" else "FALSE"
        elif tipo_val == "float":
            raw   = attrs.get(K_FLOAT)
            valor = raw  # string del número
        else:
            texto = teletype.extractText(celda).strip()
            valor = texto if texto else None

        for _ in range(min(repeticiones, 30)):  # límite de seguridad
            valores.append(valor)

    return valores


def _iso_duration_to_hhmm(duration: str) -> str | None:
    """
    Convierte una duración ISO 8601 a formato HH:MM.
    Ejemplos: "PT07H00M00S" → "07:00",  "PT13H55M00S" → "13:55"
    """
    if not duration:
        return None
    m = re.match(r"PT(\d+)H(\d+)M", duration)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    return None


def _normalizar_hora(valor) -> str | None:
    """
    Normaliza un valor de hora al formato HH:MM.
    Retorna None cuando la persona no trabaja ese día.

    Acepta:
      - "07:00"       (ya normalizado desde ISO duration)
      - "7:00:00 AM"  (formato AM/PM)
      - "1:55:00 PM"  (PM tarde)
      - "NO"          → None
      - None / ""     → None
    """
    if valor is None:
        return None

    s = str(valor).strip().upper()

    if s in ("NO", "", "NONE", "-", "N/A"):
        return None

    # Formato HH:MM (desde el parser ISO duration)
    if re.match(r"^\d{1,2}:\d{2}$", s):
        h, mn = s.split(":")
        return f"{int(h):02d}:{int(mn):02d}"

    # Formatos AM/PM y 24h variados
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%H:%M")
        except ValueError:
            continue

    return None  # Valor no reconocido


def _normalizar_almuerzo(valor) -> int:
    """
    Normaliza el valor de la columna ALMUERZO a minutos enteros.
      TRUE      → 60  (1 hora estándar)
      FALSE     → 0   (sin derecho a almuerzo)
      "30 min"  → 30
      número    → int(número)
      None / "" → 0
    """
    if valor is None:
        return 0

    s = str(valor).strip().upper()

    if s == "TRUE":
        return 60
    if s in ("FALSE", "NO", ""):
        return 0

    m = re.search(r"(\d+)", s)
    if m:
        return int(m.group(1))

    return 0


# ══════════════════════════════════════════════════════════════════════════
# PARSING DEL ARCHIVO CSV
# ══════════════════════════════════════════════════════════════════════════

def parsear_csv(ruta: str) -> list[dict]:
    """
    Lee un archivo CSV con horarios de personal y retorna una lista de dicts,
    uno por persona.

    Columnas esperadas (encabezado en primera fila):
      id_usuario, nombre, lunes, martes, miercoles, jueves, viernes, sabado,
      almuerzo_min, notas

    Reglas:
      - encoding utf-8-sig (soporta BOM de Excel)
      - Celda vacía en columna de día → None (persona no trabaja ese día)
      - almuerzo_min: 0, 30 ó 60

    Raises:
        RuntimeError: Si faltan columnas requeridas o no hay datos válidos.
    """
    import csv as _csv

    COLUMNAS_REQ = {
        "id_usuario", "nombre",
        "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
        "almuerzo_min",
    }

    try:
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            reader = _csv.DictReader(f)
            columnas = set(reader.fieldnames or [])
            faltantes = COLUMNAS_REQ - columnas
            if faltantes:
                raise RuntimeError(
                    "El CSV no contiene las columnas requeridas: "
                    + ", ".join(sorted(faltantes))
                )

            horarios = []
            for fila in reader:
                id_str = (fila.get("id_usuario") or "").strip()
                nombre = (fila.get("nombre") or "").strip()
                if not id_str or not nombre:
                    continue
                try:
                    id_usuario = str(int(float(id_str)))
                except (ValueError, TypeError):
                    continue

                horario = {
                    "id_usuario":   id_usuario,
                    "nombre":       nombre,
                    "lunes":        _normalizar_hora(fila.get("lunes")),
                    "martes":       _normalizar_hora(fila.get("martes")),
                    "miercoles":    _normalizar_hora(fila.get("miercoles")),
                    "jueves":       _normalizar_hora(fila.get("jueves")),
                    "viernes":      _normalizar_hora(fila.get("viernes")),
                    "sabado":       _normalizar_hora(fila.get("sabado")),
                    "domingo":      _normalizar_hora(fila.get("domingo")),
                    "almuerzo_min": _normalizar_almuerzo(fila.get("almuerzo_min")),
                    "notas":        (fila.get("notas") or "").strip(),
                }
                horarios.append(horario)

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"No se pudo leer el CSV de horarios: {e}")

    if not horarios:
        raise RuntimeError("El CSV no contiene filas de datos válidas.")

    return horarios


# ══════════════════════════════════════════════════════════════════════════
# CONSULTA DE HORARIO PARA UN DÍA CONCRETO
# ══════════════════════════════════════════════════════════════════════════

def get_info_dia(horario_persona: dict, fecha) -> dict:
    """
    Retorna la información de horario aplicable para una persona en una fecha.

    Args:
        horario_persona: Dict con campos lunes..domingo y almuerzo_min.
        fecha:           date object de Python.

    Returns:
        {
            "trabaja":      bool,          # False si NO trabaja ese día
            "hora_entrada": "HH:MM"|None,  # Hora programada de llegada
            "almuerzo_min": int,           # 0 si sábado o sin almuerzo
            "es_domingo":   bool,
        }
    """
    weekday    = fecha.weekday()
    es_sabado  = weekday == 5
    es_domingo = weekday == 6

    if es_domingo:
        hora_entrada = horario_persona.get("domingo")
        return {
            "trabaja":      hora_entrada is not None,
            "hora_entrada": hora_entrada,
            "almuerzo_min": 0,
            "es_domingo":   True,
        }

    columna      = WEEKDAY_COLUMNA.get(weekday, "viernes")
    hora_entrada = horario_persona.get(columna)
    # Sábado: nunca analizar almuerzo aunque ALMUERZO sea TRUE
    almuerzo_min = 0 if es_sabado else horario_persona.get("almuerzo_min", 0)

    return {
        "trabaja":      hora_entrada is not None,
        "hora_entrada": hora_entrada,
        "almuerzo_min": almuerzo_min,
        "es_domingo":   False,
    }
