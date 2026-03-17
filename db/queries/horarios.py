"""
Queries de horarios con compatibilidad total hacia atrás.

Internamente usa plantillas_horario + asignaciones_horario, pero las
funciones públicas retornan el mismo formato dict que el sistema SQLite.

En Fase 1:
- ciclo_semanas = 1 (sin rotaciones)
- Cada persona tiene una plantilla personalizada (1:1)
- La asignacion tiene fecha_inicio='2024-01-01', fecha_fin=NULL
"""

from datetime import date
from sqlalchemy import text

from db.connection import get_connection
from db.queries.personas import resolver_persona_id, id_usuario_from_persona, _get_dispositivo_id

# Columnas de horario que se copian directamente entre el dict legacy y la plantilla
_HORARIO_COLS = [
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
    "lunes_salida", "martes_salida", "miercoles_salida", "jueves_salida",
    "viernes_salida", "sabado_salida", "domingo_salida",
    "almuerzo_min",
    "lunes_almuerzo_min", "martes_almuerzo_min", "miercoles_almuerzo_min",
    "jueves_almuerzo_min", "viernes_almuerzo_min", "sabado_almuerzo_min",
    "domingo_almuerzo_min",
    "horas_semana", "horas_mes",
]


def _nombre_plantilla(id_usuario: str, nombre: str) -> str:
    """Genera un nombre único de plantilla para una persona."""
    return f"{nombre} ({id_usuario})"


def _row_to_horario_dict(row) -> dict:
    """Convierte una fila DB a un dict de horario compatible con el sistema anterior."""
    d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    # Normalizar TIME de PostgreSQL a string HH:MM para compatibilidad con script.py
    for col in ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
                "lunes_salida", "martes_salida", "miercoles_salida", "jueves_salida",
                "viernes_salida", "sabado_salida", "domingo_salida"]:
        v = d.get(col)
        if v is not None and not isinstance(v, str):
            # timedelta (lo que psycopg2 devuelve para TIME) o time object
            if hasattr(v, "seconds"):
                # timedelta — convertir a HH:MM
                total = int(v.total_seconds())
                h, m = divmod(total // 60, 60)
                d[col] = f"{h:02d}:{m:02d}"
            elif hasattr(v, "strftime"):
                d[col] = v.strftime("%H:%M")
        # Si es None, queda None (día libre)
    return d


def upsert_horarios(horarios: list[dict], fuente: str = "") -> int:
    """
    Inserta o actualiza horarios en plantillas_horario + asignaciones_horario.

    En Fase 1: cada entrada del dict crea/actualiza una plantilla 1:1 con la persona.
    La asignacion tiene ciclo_semanas=1, fecha_inicio='2024-01-01', fecha_fin=NULL.
    """
    with get_connection() as conn:
        dispositivo_id = _get_dispositivo_id(conn)
        for h in horarios:
            id_usuario = str(h["id_usuario"])
            nombre = h.get("nombre", id_usuario)

            # Obtener/crear persona
            persona_id, _ = resolver_persona_id(conn, id_usuario, nombre, dispositivo_id)

            # Buscar asignación activa existente para esta persona (Fase 1: ciclo=1)
            asig = conn.execute(
                text("""
                    SELECT ah.id, ah.plantilla_id
                    FROM asignaciones_horario ah
                    WHERE ah.persona_id = CAST(:persona_id AS uuid)
                      AND ah.ciclo_semanas = 1
                      AND ah.fecha_fin IS NULL
                    ORDER BY ah.fecha_inicio DESC
                    LIMIT 1
                """),
                {"persona_id": persona_id},
            ).fetchone()

            if asig:
                # Actualizar plantilla existente
                plantilla_id = str(asig[1])
                _update_plantilla(conn, plantilla_id, h, nombre, id_usuario, fuente)
            else:
                # Crear plantilla nueva + asignación
                plantilla_id = _insert_plantilla(conn, h, nombre, id_usuario, fuente)
                conn.execute(
                    text("""
                        INSERT INTO asignaciones_horario
                            (persona_id, plantilla_id, fecha_inicio, fecha_fin,
                             ciclo_semanas, posicion_ciclo, notas)
                        VALUES (
                            CAST(:persona_id AS uuid), CAST(:plantilla_id AS uuid),
                            '2024-01-01', NULL, 1, 1, :notas
                        )
                        ON CONFLICT (persona_id, plantilla_id, fecha_inicio, posicion_ciclo)
                        DO NOTHING
                    """),
                    {
                        "persona_id": persona_id,
                        "plantilla_id": plantilla_id,
                        "notas": h.get("notas", ""),
                    },
                )

    return len(horarios)


def _insert_plantilla(conn, h: dict, nombre: str, id_usuario: str, fuente: str) -> str:
    """Crea una plantilla nueva y retorna su UUID como string."""
    row = conn.execute(
        text("""
            INSERT INTO plantillas_horario (
                nombre,
                lunes, martes, miercoles, jueves, viernes, sabado, domingo,
                lunes_salida, martes_salida, miercoles_salida, jueves_salida,
                viernes_salida, sabado_salida, domingo_salida,
                almuerzo_min,
                lunes_almuerzo_min, martes_almuerzo_min, miercoles_almuerzo_min,
                jueves_almuerzo_min, viernes_almuerzo_min, sabado_almuerzo_min,
                domingo_almuerzo_min,
                horas_semana, horas_mes
            ) VALUES (
                :nombre,
                :lunes, :martes, :miercoles, :jueves, :viernes, :sabado, :domingo,
                :lunes_salida, :martes_salida, :miercoles_salida, :jueves_salida,
                :viernes_salida, :sabado_salida, :domingo_salida,
                :almuerzo_min,
                :lunes_almuerzo_min, :martes_almuerzo_min, :miercoles_almuerzo_min,
                :jueves_almuerzo_min, :viernes_almuerzo_min, :sabado_almuerzo_min,
                :domingo_almuerzo_min,
                :horas_semana, :horas_mes
            )
            RETURNING id
        """),
        _plantilla_params(h, nombre, id_usuario),
    ).fetchone()
    return str(row[0])


def _update_plantilla(conn, plantilla_id: str, h: dict, nombre: str, id_usuario: str, fuente: str):
    """Actualiza los campos de horario de una plantilla existente."""
    params = _plantilla_params(h, nombre, id_usuario)
    params["plantilla_id"] = plantilla_id
    conn.execute(
        text("""
            UPDATE plantillas_horario SET
                nombre = :nombre,
                lunes = :lunes, martes = :martes, miercoles = :miercoles,
                jueves = :jueves, viernes = :viernes, sabado = :sabado, domingo = :domingo,
                lunes_salida = :lunes_salida, martes_salida = :martes_salida,
                miercoles_salida = :miercoles_salida, jueves_salida = :jueves_salida,
                viernes_salida = :viernes_salida, sabado_salida = :sabado_salida,
                domingo_salida = :domingo_salida,
                almuerzo_min = :almuerzo_min,
                lunes_almuerzo_min = :lunes_almuerzo_min,
                martes_almuerzo_min = :martes_almuerzo_min,
                miercoles_almuerzo_min = :miercoles_almuerzo_min,
                jueves_almuerzo_min = :jueves_almuerzo_min,
                viernes_almuerzo_min = :viernes_almuerzo_min,
                sabado_almuerzo_min = :sabado_almuerzo_min,
                domingo_almuerzo_min = :domingo_almuerzo_min,
                horas_semana = :horas_semana, horas_mes = :horas_mes
            WHERE id = CAST(:plantilla_id AS uuid)
        """),
        params,
    )


def _plantilla_params(h: dict, nombre: str, id_usuario: str) -> dict:
    """Construye el dict de parámetros para INSERT/UPDATE de plantilla."""
    def _int(v):
        return int(v) if v is not None else None

    def _float(v):
        return float(v) if v is not None else None

    return {
        "nombre": _nombre_plantilla(id_usuario, nombre),
        "lunes": h.get("lunes"),
        "martes": h.get("martes"),
        "miercoles": h.get("miercoles"),
        "jueves": h.get("jueves"),
        "viernes": h.get("viernes"),
        "sabado": h.get("sabado"),
        "domingo": h.get("domingo"),
        "lunes_salida": h.get("lunes_salida"),
        "martes_salida": h.get("martes_salida"),
        "miercoles_salida": h.get("miercoles_salida"),
        "jueves_salida": h.get("jueves_salida"),
        "viernes_salida": h.get("viernes_salida"),
        "sabado_salida": h.get("sabado_salida"),
        "domingo_salida": h.get("domingo_salida"),
        "almuerzo_min": _int(h.get("almuerzo_min", 0)),
        "lunes_almuerzo_min": _int(h.get("lunes_almuerzo_min")),
        "martes_almuerzo_min": _int(h.get("martes_almuerzo_min")),
        "miercoles_almuerzo_min": _int(h.get("miercoles_almuerzo_min")),
        "jueves_almuerzo_min": _int(h.get("jueves_almuerzo_min")),
        "viernes_almuerzo_min": _int(h.get("viernes_almuerzo_min")),
        "sabado_almuerzo_min": _int(h.get("sabado_almuerzo_min")),
        "domingo_almuerzo_min": _int(h.get("domingo_almuerzo_min")),
        "horas_semana": _float(h.get("horas_semana")),
        "horas_mes": _float(h.get("horas_mes")),
    }


def get_horarios() -> dict:
    """
    Retorna todos los horarios activos en dos índices:
      "by_id"     → {id_usuario: horario_dict}
      "by_nombre" → {NOMBRE_UPPER: horario_dict}

    El dict de horario tiene exactamente las mismas claves que retornaba el
    sistema SQLite (compatible con script.py).
    """
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    COALESCE(pd.id_en_dispositivo, p.id::text) AS id_usuario,
                    p.nombre,
                    ph.lunes, ph.martes, ph.miercoles, ph.jueves, ph.viernes,
                    ph.sabado, ph.domingo,
                    ph.lunes_salida, ph.martes_salida, ph.miercoles_salida,
                    ph.jueves_salida, ph.viernes_salida, ph.sabado_salida,
                    ph.domingo_salida,
                    ph.almuerzo_min,
                    ph.lunes_almuerzo_min, ph.martes_almuerzo_min,
                    ph.miercoles_almuerzo_min, ph.jueves_almuerzo_min,
                    ph.viernes_almuerzo_min, ph.sabado_almuerzo_min,
                    ph.domingo_almuerzo_min,
                    ph.horas_semana, ph.horas_mes,
                    ah.notas
                FROM asignaciones_horario ah
                JOIN plantillas_horario ph ON ph.id = ah.plantilla_id
                JOIN personas p ON p.id = ah.persona_id
                LEFT JOIN personas_dispositivos pd
                    ON pd.persona_id = p.id AND pd.es_principal = true AND pd.activo = true
                WHERE ah.ciclo_semanas = 1
                  AND ah.fecha_fin IS NULL
                  AND ph.activo = true
                ORDER BY p.nombre
            """)
        ).fetchall()

    by_id = {}
    by_nombre = {}

    for row in rows:
        h = _row_to_horario_dict(row)
        # Asegurar campos id_usuario y nombre en el dict
        id_usuario = h.get("id_usuario") or ""
        nombre = h.get("nombre") or ""
        h["id_usuario"] = id_usuario
        h["nombre"] = nombre

        if id_usuario:
            by_id[id_usuario] = h
        by_nombre[nombre.upper()] = h

    return {"by_id": by_id, "by_nombre": by_nombre}


def get_horario(id_usuario: str) -> dict | None:
    """Retorna el horario activo de una persona por su id_usuario, o None si no existe."""
    with get_connection() as conn:
        dispositivo_id = _get_dispositivo_id(conn)
        row = conn.execute(
            text("""
                SELECT
                    COALESCE(pd.id_en_dispositivo, p.id::text) AS id_usuario,
                    p.nombre,
                    ph.lunes, ph.martes, ph.miercoles, ph.jueves, ph.viernes,
                    ph.sabado, ph.domingo,
                    ph.lunes_salida, ph.martes_salida, ph.miercoles_salida,
                    ph.jueves_salida, ph.viernes_salida, ph.sabado_salida,
                    ph.domingo_salida,
                    ph.almuerzo_min,
                    ph.lunes_almuerzo_min, ph.martes_almuerzo_min,
                    ph.miercoles_almuerzo_min, ph.jueves_almuerzo_min,
                    ph.viernes_almuerzo_min, ph.sabado_almuerzo_min,
                    ph.domingo_almuerzo_min,
                    ph.horas_semana, ph.horas_mes,
                    ah.notas
                FROM personas_dispositivos pd
                JOIN personas p ON p.id = pd.persona_id
                JOIN asignaciones_horario ah ON ah.persona_id = p.id
                JOIN plantillas_horario ph ON ph.id = ah.plantilla_id
                WHERE pd.id_en_dispositivo = :id_usuario
                  AND (:dispositivo_id IS NULL OR pd.dispositivo_id = CAST(:dispositivo_id AS uuid))
                  AND pd.activo = true
                  AND ah.ciclo_semanas = 1
                  AND ah.fecha_fin IS NULL
                  AND ph.activo = true
                ORDER BY ah.fecha_inicio DESC
                LIMIT 1
            """),
            {"id_usuario": id_usuario, "dispositivo_id": dispositivo_id},
        ).fetchone()

    if not row:
        return None
    h = _row_to_horario_dict(row)
    h["id_usuario"] = id_usuario
    return h


def upsert_horario(horario: dict, fuente: str = "manual") -> dict:
    """Inserta o actualiza un único registro de horario. Retorna el horario guardado."""
    upsert_horarios([horario], fuente)
    return get_horario(str(horario["id_usuario"]))


def delete_horario(id_usuario: str) -> bool:
    """
    Cierra la asignación activa de una persona (fecha_fin = hoy).
    No borra la plantilla (los datos históricos se conservan).
    Retorna True si existía y fue cerrada.
    """
    with get_connection() as conn:
        dispositivo_id = _get_dispositivo_id(conn)
        # Obtener persona_id
        pd_row = conn.execute(
            text("""
                SELECT persona_id FROM personas_dispositivos
                WHERE id_en_dispositivo = :id_usuario
                  AND (:dispositivo_id IS NULL OR dispositivo_id = CAST(:dispositivo_id AS uuid))
                  AND activo = true
                LIMIT 1
            """),
            {"id_usuario": id_usuario, "dispositivo_id": dispositivo_id},
        ).fetchone()

        if not pd_row:
            return False

        persona_id = str(pd_row[0])
        result = conn.execute(
            text("""
                UPDATE asignaciones_horario
                SET fecha_fin = CURRENT_DATE
                WHERE persona_id = CAST(:persona_id AS uuid)
                  AND ciclo_semanas = 1
                  AND fecha_fin IS NULL
            """),
            {"persona_id": persona_id},
        )
        return result.rowcount > 0


def get_estado_horarios() -> dict:
    """Retorna un resumen del estado de los horarios cargados."""
    with get_connection() as conn:
        total = conn.execute(
            text("""
                SELECT COUNT(DISTINCT ah.persona_id)
                FROM asignaciones_horario ah
                JOIN plantillas_horario ph ON ph.id = ah.plantilla_id
                WHERE ah.ciclo_semanas = 1 AND ah.fecha_fin IS NULL AND ph.activo = true
            """)
        ).fetchone()[0]

        ultima = conn.execute(
            text("""
                SELECT ph.nombre, ph.creado_en
                FROM plantillas_horario ph
                ORDER BY ph.creado_en DESC
                LIMIT 1
            """)
        ).fetchone()

        con_semana = conn.execute(
            text("""
                SELECT COUNT(*) FROM plantillas_horario
                WHERE horas_semana IS NOT NULL AND activo = true
            """)
        ).fetchone()[0]

        con_mes = conn.execute(
            text("""
                SELECT COUNT(*) FROM plantillas_horario
                WHERE horas_mes IS NOT NULL AND activo = true
            """)
        ).fetchone()[0]

        con_almuerzo = conn.execute(
            text("""
                SELECT COUNT(*) FROM plantillas_horario
                WHERE almuerzo_min > 0 AND activo = true
            """)
        ).fetchone()[0]

    return {
        "total": total,
        "cargados": total > 0,
        "fuente": ultima[0] if ultima else None,
        "actualizado_en": str(ultima[1]) if ultima else None,
        "con_semana": con_semana,
        "con_mes": con_mes,
        "con_almuerzo": con_almuerzo,
    }


def get_horario_en_fecha(conn, persona_id: str, fecha: date) -> dict | None:
    """
    Retorna el horario activo de una persona en una fecha específica.
    Maneja horarios fijos (ciclo_semanas=1) y rotaciones cíclicas.
    """
    # Caso 1: horario fijo
    row = conn.execute(
        text("""
            SELECT ph.*
            FROM plantillas_horario ph
            JOIN asignaciones_horario ah ON ah.plantilla_id = ph.id
            WHERE ah.persona_id = CAST(:persona_id AS uuid)
              AND ah.ciclo_semanas = 1
              AND ah.fecha_inicio <= :fecha
              AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
            ORDER BY ah.fecha_inicio DESC
            LIMIT 1
        """),
        {"persona_id": persona_id, "fecha": fecha},
    ).fetchone()

    if row:
        return _row_to_horario_dict(row)

    # Caso 2: rotación cíclica
    ciclo_row = conn.execute(
        text("""
            SELECT cch.fecha_referencia, ah.ciclo_semanas
            FROM asignaciones_horario ah
            JOIN config_ciclo_horario cch ON cch.id = ah.config_ciclo_id
            WHERE ah.persona_id = CAST(:persona_id AS uuid)
              AND ah.ciclo_semanas > 1
              AND ah.fecha_inicio <= :fecha
              AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
            LIMIT 1
        """),
        {"persona_id": persona_id, "fecha": fecha},
    ).fetchone()

    if not ciclo_row:
        return None

    ref = ciclo_row[0]
    if hasattr(ref, "date"):
        ref = ref.date()
    semanas = (fecha - ref).days // 7
    posicion = (semanas % ciclo_row[1]) + 1

    row = conn.execute(
        text("""
            SELECT ph.*
            FROM plantillas_horario ph
            JOIN asignaciones_horario ah ON ah.plantilla_id = ph.id
            WHERE ah.persona_id = CAST(:persona_id AS uuid)
              AND ah.posicion_ciclo = :posicion
              AND ah.fecha_inicio <= :fecha
              AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
            LIMIT 1
        """),
        {"persona_id": persona_id, "posicion": posicion, "fecha": fecha},
    ).fetchone()

    return _row_to_horario_dict(row) if row else None
