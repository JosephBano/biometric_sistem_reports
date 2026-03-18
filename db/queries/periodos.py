"""
Gestión de períodos de vigencia.

grupos_periodo  → Concepto UI: el período como grupo (nombre, fechas, estado)
periodos_vigencia → Registro por persona en ese período
"""

from sqlalchemy import text
from db.connection import get_connection


# ── Grupos Período (UI) ───────────────────────────────────────────────────────

def crear_periodo(nombre: str, fecha_inicio, fecha_fin=None, descripcion: str = None) -> dict:
    """Crea un grupos_periodo (registro de grupo, sin personas aún)."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                INSERT INTO grupos_periodo (nombre, fecha_inicio, fecha_fin, descripcion)
                VALUES (:nombre, CAST(:fecha_inicio AS date),
                        CAST(:fecha_fin AS date),
                        :descripcion)
                RETURNING id::text, nombre, fecha_inicio, fecha_fin, estado, descripcion, creado_en
            """),
            {"nombre": nombre, "fecha_inicio": str(fecha_inicio),
             "fecha_fin": str(fecha_fin) if fecha_fin else None,
             "descripcion": descripcion},
        ).fetchone()
        return dict(row._mapping)


def get_periodo(id: str) -> dict | None:
    """Retorna un grupos_periodo por UUID."""
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT gp.id::text, gp.nombre, gp.fecha_inicio, gp.fecha_fin,
                       gp.estado, gp.descripcion, gp.creado_en,
                       COUNT(pv.id) as total_personas
                FROM grupos_periodo gp
                LEFT JOIN periodos_vigencia pv ON (
                    pv.nombre = gp.nombre
                    AND pv.fecha_inicio = gp.fecha_inicio
                    AND (pv.fecha_fin = gp.fecha_fin OR (pv.fecha_fin IS NULL AND gp.fecha_fin IS NULL))
                )
                WHERE gp.id = CAST(:id AS uuid)
                GROUP BY gp.id, gp.nombre, gp.fecha_inicio, gp.fecha_fin, gp.estado, gp.descripcion, gp.creado_en
            """),
            {"id": id},
        ).fetchone()
        return dict(row._mapping) if row else None


def listar_periodos_activos(tipo_persona_id: str = None) -> list[dict]:
    """Lista grupos_periodo con estado 'activo' y conteo de personas."""
    query = """
        SELECT gp.id::text, gp.nombre, gp.fecha_inicio, gp.fecha_fin,
               gp.estado, gp.descripcion,
               COUNT(pv.id) as total_personas
        FROM grupos_periodo gp
        LEFT JOIN periodos_vigencia pv ON (
            pv.nombre = gp.nombre
            AND pv.fecha_inicio = gp.fecha_inicio
            AND (pv.fecha_fin = gp.fecha_fin OR (pv.fecha_fin IS NULL AND gp.fecha_fin IS NULL))
            AND pv.estado = 'activo'
        )
        LEFT JOIN personas p ON pv.persona_id = p.id
        WHERE gp.estado = 'activo'
          AND (:tipo_persona_id IS NULL OR p.tipo_persona_id = CAST(:tipo_persona_id AS uuid) OR p.id IS NULL)
        GROUP BY gp.id, gp.nombre, gp.fecha_inicio, gp.fecha_fin, gp.estado, gp.descripcion
        ORDER BY gp.fecha_inicio DESC
    """
    with get_connection() as conn:
        rows = conn.execute(text(query), {"tipo_persona_id": tipo_persona_id}).fetchall()
        return [dict(r._mapping) for r in rows]


def listar_periodos_historial(tipo_persona_id: str = None) -> list[dict]:
    """Lista grupos_periodo cerrados o archivados."""
    query = """
        SELECT gp.id::text, gp.nombre, gp.fecha_inicio, gp.fecha_fin,
               gp.estado, gp.descripcion,
               COUNT(pv.id) as total_personas
        FROM grupos_periodo gp
        LEFT JOIN periodos_vigencia pv ON (
            pv.nombre = gp.nombre
            AND pv.fecha_inicio = gp.fecha_inicio
            AND (pv.fecha_fin = gp.fecha_fin OR (pv.fecha_fin IS NULL AND gp.fecha_fin IS NULL))
        )
        LEFT JOIN personas p ON pv.persona_id = p.id
        WHERE gp.estado IN ('cerrado', 'archivado')
          AND (:tipo_persona_id IS NULL OR p.tipo_persona_id = CAST(:tipo_persona_id AS uuid) OR p.id IS NULL)
        GROUP BY gp.id, gp.nombre, gp.fecha_inicio, gp.fecha_fin, gp.estado, gp.descripcion
        ORDER BY gp.fecha_inicio DESC
    """
    with get_connection() as conn:
        rows = conn.execute(text(query), {"tipo_persona_id": tipo_persona_id}).fetchall()
        return [dict(r._mapping) for r in rows]


def cerrar_periodo(id: str) -> None:
    """Cierra el grupos_periodo y todos sus periodos_vigencia asociados."""
    with get_connection() as conn:
        gp = conn.execute(
            text("SELECT nombre, fecha_inicio, fecha_fin FROM grupos_periodo WHERE id = CAST(:id AS uuid)"),
            {"id": id},
        ).fetchone()
        if not gp:
            return
        d = dict(gp._mapping)
        conn.execute(
            text("UPDATE grupos_periodo SET estado = 'cerrado' WHERE id = CAST(:id AS uuid)"),
            {"id": id},
        )
        conn.execute(
            text("""
                UPDATE periodos_vigencia SET estado = 'cerrado'
                WHERE nombre = :nombre
                  AND fecha_inicio = :fi
                  AND (fecha_fin = :ff OR (:ff IS NULL AND fecha_fin IS NULL))
                  AND estado = 'activo'
            """),
            {"nombre": d["nombre"], "fi": d["fecha_inicio"], "ff": d["fecha_fin"]},
        )


def archivar_periodo(id: str) -> None:
    """Archiva el grupos_periodo y sus periodos_vigencia."""
    with get_connection() as conn:
        gp = conn.execute(
            text("SELECT nombre, fecha_inicio, fecha_fin FROM grupos_periodo WHERE id = CAST(:id AS uuid)"),
            {"id": id},
        ).fetchone()
        if not gp:
            return
        d = dict(gp._mapping)
        conn.execute(
            text("UPDATE grupos_periodo SET estado = 'archivado' WHERE id = CAST(:id AS uuid)"),
            {"id": id},
        )
        conn.execute(
            text("""
                UPDATE periodos_vigencia SET estado = 'archivado'
                WHERE nombre = :nombre
                  AND fecha_inicio = :fi
                  AND (fecha_fin = :ff OR (:ff IS NULL AND fecha_fin IS NULL))
                  AND estado = 'cerrado'
            """),
            {"nombre": d["nombre"], "fi": d["fecha_inicio"], "ff": d["fecha_fin"]},
        )


def cerrar_periodos_vencidos() -> int:
    """Cierra grupos_periodo y periodos_vigencia cuya fecha_fin ya pasó."""
    with get_connection() as conn:
        r1 = conn.execute(
            text("""
                UPDATE grupos_periodo SET estado = 'cerrado'
                WHERE estado = 'activo'
                  AND fecha_fin IS NOT NULL
                  AND fecha_fin < CURRENT_DATE
            """)
        )
        conn.execute(
            text("""
                UPDATE periodos_vigencia SET estado = 'cerrado'
                WHERE estado = 'activo'
                  AND fecha_fin IS NOT NULL
                  AND fecha_fin < CURRENT_DATE
            """)
        )
        return r1.rowcount


def agregar_personas_a_periodo_bulk(periodo_id: str, personas_ids: list[str]) -> dict:
    """Agrega personas a un grupos_periodo copiando sus datos."""
    with get_connection() as conn:
        gp = conn.execute(
            text("SELECT nombre, fecha_inicio, fecha_fin, descripcion FROM grupos_periodo WHERE id = CAST(:id AS uuid)"),
            {"id": periodo_id},
        ).fetchone()
        if not gp:
            return {"exito": False, "error": "Periodo no encontrado"}
        d = dict(gp._mapping)
        creados = 0
        for p_id in personas_ids:
            try:
                conn.execute(
                    text("""
                        INSERT INTO periodos_vigencia (persona_id, nombre, fecha_inicio, fecha_fin, estado, descripcion)
                        VALUES (CAST(:persona_id AS uuid), :nombre,
                                CAST(:fi AS date), CAST(:ff AS date), 'activo', :desc)
                        ON CONFLICT DO NOTHING
                    """),
                    {"persona_id": p_id, "nombre": d["nombre"],
                     "fi": d["fecha_inicio"], "ff": d["fecha_fin"],
                     "desc": d.get("descripcion")},
                )
                creados += 1
            except Exception:
                pass
        return {"exito": True, "creados": creados}


def procesar_csv_personas_periodo(filepath: str, periodo_id: str, tipo_persona_id: str) -> dict:
    """
    Procesa CSV con columnas: identificacion, nombre, grupo, categoria,
    [lunes_entrada, lunes_salida, ..., viernes_salida].
    Crea o actualiza personas y crea sus periodos_vigencia.
    """
    import csv as _csv

    with get_connection() as conn:
        gp = conn.execute(
            text("SELECT nombre, fecha_inicio, fecha_fin FROM grupos_periodo WHERE id = CAST(:id AS uuid)"),
            {"id": periodo_id},
        ).fetchone()
        if not gp:
            return {"exito": False, "error": "Periodo no encontrado"}
        p_data = dict(gp._mapping)
        fecha_inicio = p_data["fecha_inicio"]
        fecha_fin = p_data["fecha_fin"]

        procesadas = nuevas = actualizadas = 0
        errores = []

        try:
            with open(filepath, newline="", encoding="utf-8-sig") as f:
                reader = _csv.DictReader(f)
                for idx, row in enumerate(reader, start=1):
                    try:
                        nombre_p = str(row.get("nombre", "")).strip()
                        identif = str(row.get("identificacion", "")).strip()
                        grupo_name = str(row.get("grupo", "")).strip()
                        cat_name = str(row.get("categoria", "")).strip()

                        if not nombre_p:
                            errores.append(f"Fila {idx}: nombre vacío.")
                            continue

                        # A. Upsert grupo
                        grupo_id = None
                        if grupo_name:
                            g_row = conn.execute(
                                text("SELECT id FROM grupos WHERE UPPER(nombre) = UPPER(:n) LIMIT 1"),
                                {"n": grupo_name},
                            ).fetchone()
                            if g_row:
                                grupo_id = str(g_row[0])
                            else:
                                g_new = conn.execute(
                                    text("INSERT INTO grupos (nombre, tipo_grupo) VALUES (:n, 'general') RETURNING id"),
                                    {"n": grupo_name},
                                ).fetchone()
                                grupo_id = str(g_new[0])

                        # B. Upsert categoría
                        cat_id = None
                        if cat_name:
                            c_row = conn.execute(
                                text("SELECT id FROM categorias WHERE UPPER(nombre) = UPPER(:n) LIMIT 1"),
                                {"n": cat_name},
                            ).fetchone()
                            if c_row:
                                cat_id = str(c_row[0])
                            else:
                                c_new = conn.execute(
                                    text("""
                                        INSERT INTO categorias (nombre, tipo_persona_id)
                                        VALUES (:n, CAST(:t_id AS uuid)) RETURNING id
                                    """),
                                    {"n": cat_name, "t_id": tipo_persona_id},
                                ).fetchone()
                                cat_id = str(c_new[0])

                        # C. Upsert persona
                        persona_id = None
                        if identif:
                            p_row = conn.execute(
                                text("SELECT id FROM personas WHERE identificacion = :ident LIMIT 1"),
                                {"ident": identif},
                            ).fetchone()
                            if p_row:
                                persona_id = str(p_row[0])
                                conn.execute(
                                    text("""
                                        UPDATE personas
                                        SET nombre=:n, grupo_id=CAST(:g AS uuid),
                                            categoria_id=CAST(:c AS uuid), activo=true
                                        WHERE id=CAST(:pid AS uuid)
                                    """),
                                    {"n": nombre_p, "g": grupo_id, "c": cat_id, "pid": persona_id},
                                )
                                actualizadas += 1

                        if not persona_id:
                            p_row = conn.execute(
                                text("SELECT id FROM personas WHERE UPPER(nombre)=UPPER(:n) LIMIT 1"),
                                {"n": nombre_p},
                            ).fetchone()
                            if p_row:
                                persona_id = str(p_row[0])
                                conn.execute(
                                    text("""
                                        UPDATE personas
                                        SET identificacion=:ident, grupo_id=CAST(:g AS uuid),
                                            categoria_id=CAST(:c AS uuid), activo=true
                                        WHERE id=CAST(:pid AS uuid)
                                    """),
                                    {"ident": identif or None, "g": grupo_id, "c": cat_id, "pid": persona_id},
                                )
                                actualizadas += 1
                            else:
                                p_new = conn.execute(
                                    text("""
                                        INSERT INTO personas (nombre, identificacion, tipo_persona_id,
                                            grupo_id, categoria_id)
                                        VALUES (:n, :ident, CAST(:t AS uuid),
                                                CAST(:g AS uuid), CAST(:c AS uuid))
                                        RETURNING id
                                    """),
                                    {"n": nombre_p, "ident": identif or None,
                                     "t": tipo_persona_id, "g": grupo_id, "c": cat_id},
                                ).fetchone()
                                persona_id = str(p_new[0])
                                nuevas += 1

                        # D. Crear periodo_vigencia para la persona
                        conn.execute(
                            text("""
                                INSERT INTO periodos_vigencia
                                    (persona_id, nombre, fecha_inicio, fecha_fin, estado, descripcion)
                                VALUES (CAST(:pid AS uuid), :nombre,
                                        CAST(:fi AS date), CAST(:ff AS date), 'activo', :desc)
                                ON CONFLICT DO NOTHING
                            """),
                            {"pid": persona_id, "nombre": p_data["nombre"],
                             "fi": fecha_inicio, "ff": fecha_fin,
                             "desc": p_data.get("descripcion")},
                        )

                        # E. Horario si viene en CSV
                        dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
                        h_datos = {}
                        tiene_horario = False
                        for d in dias:
                            ent = str(row.get(f"{d}_entrada", "")).strip() or None
                            sal = str(row.get(f"{d}_salida", "")).strip() or None
                            h_datos[d] = ent
                            h_datos[f"{d}_salida"] = sal
                            if ent:
                                tiene_horario = True
                        h_datos["almuerzo_min"] = int(row.get("almuerzo_min", 0) or 0)

                        if tiene_horario:
                            h_name = f"Horario {nombre_p} — {p_data['nombre']}"
                            plant = conn.execute(
                                text("""
                                    INSERT INTO plantillas_horario (
                                        nombre, lunes, martes, miercoles, jueves, viernes,
                                        sabado, domingo, lunes_salida, martes_salida,
                                        miercoles_salida, jueves_salida, viernes_salida,
                                        sabado_salida, domingo_salida, almuerzo_min
                                    ) VALUES (
                                        :nombre, :lunes, :martes, :miercoles, :jueves, :viernes,
                                        :sabado, :domingo, :lunes_salida, :martes_salida,
                                        :miercoles_salida, :jueves_salida, :viernes_salida,
                                        :sabado_salida, :domingo_salida, :almuerzo_min
                                    ) RETURNING id
                                """),
                                {"nombre": h_name, **h_datos},
                            ).fetchone()
                            conn.execute(
                                text("""
                                    INSERT INTO asignaciones_horario
                                        (persona_id, plantilla_id, fecha_inicio, fecha_fin,
                                         ciclo_semanas, posicion_ciclo)
                                    VALUES (CAST(:pid AS uuid), CAST(:plid AS uuid),
                                            CAST(:fi AS date), CAST(:ff AS date), 1, 1)
                                    ON CONFLICT DO NOTHING
                                """),
                                {"pid": persona_id, "plid": str(plant[0]),
                                 "fi": fecha_inicio, "ff": fecha_fin},
                            )

                        procesadas += 1

                    except Exception as e:
                        errores.append(f"Fila {idx} ({row.get('nombre','?')}): {e}")

            return {"exito": True, "procesadas": procesadas,
                    "nuevas": nuevas, "actualizadas": actualizadas,
                    "errores": errores}

        except Exception as e:
            return {"exito": False, "error": f"Error leyendo CSV: {e}"}
