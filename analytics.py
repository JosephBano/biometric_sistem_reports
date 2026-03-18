"""
Motor unificado de Analytics para el sistema de asistencia.
Consolida análisis continuo (empleados) y análisis de periodos (contratistas/practicantes).
Usa Pandas para agregaciones y estadísticas.
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta
from sqlalchemy import text
from db.connection import get_connection
from db.queries.asistencia_periodo import calcular_asistencia_periodo

def load_data_asistencia_dataframe(fecha_inicio: date, fecha_fin: date, grupo_id: str = None, tipo_persona_id: str = None) -> pd.DataFrame:
    """
    Carga el detalle diario de asistencia en un DataFrame de Pandas para análisis.
    Cruza personas, grupos, categorías y sus estados diarios.
    """
    with get_connection() as conn:
        # Recuperar periodo ID de referencia o crear una vista virtual
        query = """
            SELECT pv.id
            FROM periodos_vigencia pv
            JOIN personas p ON pv.persona_id = p.id
            WHERE pv.fecha_inicio <= :fin AND (pv.fecha_fin IS NULL OR pv.fecha_fin >= :inicio)
              AND pv.estado = 'activo'
        """
        params = {"inicio": fecha_inicio, "fin": fecha_fin}
        
        if grupo_id:
            query += " AND p.grupo_id = CAST(:grupo_id AS uuid)"
            params["grupo_id"] = grupo_id
        if tipo_persona_id:
            query += " AND p.tipo_persona_id = CAST(:tipo_id AS uuid)"
            params["tipo_id"] = tipo_persona_id
            
        periodos = conn.execute(text(query), params).fetchall()
        periodos_ids = [str(r[0]) for r in periodos]
        
    all_rows = []
    # Usar el algoritmo de asistencia diaria por periodo
    for pid in periodos_ids:
        for p_asist in calcular_asistencia_periodo(pid):
            for d in p_asist.get("detalle_asistencia", []):
                all_rows.append({
                    "persona_id": p_asist["persona_id"],
                    "nombre": p_asist["nombre"],
                    "identificacion": p_asist.get("identificacion"),
                    "grupo": p_asist.get("grupo") or "Sin Grupo",
                    "categoria": p_asist.get("categoria") or "Sin Categoría",
                    "fecha": d["fecha"],
                    "estado": d["estado"],
                    "tardanza": d["tardanza"],
                    "entrada_marcada": d.get("entrada_marcada"),
                })
                
    if not all_rows:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_rows)
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df


def calcular_risk_score(persona_df: pd.DataFrame) -> int:
    """
    Calcula el risk score (0-100) para una persona basado en su dataframe diario.
    Ponderación:
      - Ausencia en día programado: 15 pts
      - Tardanza en entrada: 5 pts
    Tope máximo 100.
    """
    if persona_df.empty:
         return 0
         
    ausencias = len(persona_df[persona_df['estado'] == 'ausente'])
    tardanzas = len(persona_df[persona_df['tardanza'] == True])
    
    score = (ausencias * 15) + (tardanzas * 5)
    return min(100, score)


def analizar(tipo_persona_id: str = None, grupo_id: str = None, periodo_vigencia_id: str = None, fecha_inicio: date = None, fecha_fin: date = None) -> dict:
    """
    Punto de entrada unificado para obtener estadísticas y anomalías.
    """
    if not fecha_inicio:
         fecha_inicio = date.today() - timedelta(days=30)
    if not fecha_fin:
         fecha_fin = date.today()
         
    df = load_data_asistencia_dataframe(fecha_inicio, fecha_fin, grupo_id, tipo_persona_id)
    
    if df.empty:
         return {"exito": False, "error": "No hay datos para el rango y filtros especificados"}
         
    # 1. Estadísticas Generales
    total_dias = len(df)
    asistencias = df[df['estado'].isin(['presente', 'presente_tarde'])]
    ausencias = df[df['estado'] == 'ausente']
    tardanzas = df[df['tardanza'] == True]
    
    tasa_asistencia = round((len(asistencias) / len(df[df['estado'] != 'no_programado'])) * 100, 2) if len(df[df['estado'] != 'no_programado']) > 0 else 100.0
    
    # 2. Risk Score por Persona
    risk_scores = []
    for p_id, p_df in df.groupby('persona_id'):
         score = calcular_risk_score(p_df)
         risk_scores.append({
             "persona_id": p_id,
             "nombre": p_df['nombre'].iloc[0],
             "grupo": p_df['grupo'].iloc[0],
             "score": score,
             "semaforo": "Rojo" if score >= 70 else ("Amarillo" if score >= 40 else "Verde")
         })
         
    # 3. Anomalías Estadísticas (Personas que exceden la desviación estándar promedio de tardanzas)
    conteo_tardanzas = df.groupby('persona_id')['tardanza'].sum().reset_index()
    promedio_tardanzas = conteo_tardanzas['tardanza'].mean()
    std_tardanzas = conteo_tardanzas['tardanza'].std()
    
    anomalias = []
    if std_tardanzas > 0:
         limite = promedio_tardanzas + (1.5 * std_tardanzas)
         for _, row in conteo_tardanzas[conteo_tardanzas['tardanza'] > limite].iterrows():
              p_name = df[df['persona_id'] == row['persona_id']]['nombre'].iloc[0]
              anomalias.append({
                  "persona_id": row['persona_id'],
                  "nombre": p_name,
                  "tipo": "Exceso de Tardanzas",
                  "detalle": f"Tiene {int(row['tardanza'])} tardanzas (Promedio del grupo: {round(promedio_tardanzas, 1)})"
              })
              
    # 4. Dimensiones: Agregación por Grupo
    grupo_stats = []
    for g_name, g_df in df.groupby('grupo'):
         g_program = g_df[g_df['estado'] != 'no_programado']
         g_asist = g_df[g_df['estado'].isin(['presente', 'presente_tarde'])]
         asist_p = round((len(g_asist) / len(g_program)) * 100, 1) if len(g_program) > 0 else 0.0
         grupo_stats.append({
              "grupo": g_name,
              "tasa_asistencia": asist_p,
              "total_personas": len(g_df['persona_id'].unique())
         })
         
    return {
         "exito": True,
         "rango": {"inicio": fecha_inicio.strftime('%Y-%m-%d'), "fin": fecha_fin.strftime('%Y-%m-%d')},
         "resumen_general": {
              "total_registros": total_dias,
              "presentes": len(asistencias),
              "ausentes": len(ausencias),
              "tardanzas": len(tardanzas),
              "tasa_asistencia_promedio": tasa_asistencia
         },
         "riesgos": sorted(risk_scores, key=lambda x: x['score'], reverse=True)[:10], # Top 10 critic
         "anomalias": anomalias,
         "dimensiones": {
              "por_grupo": sorted(grupo_stats, key=lambda x: x['tasa_asistencia'])
         }
    }


# ── Funciones de análisis avanzado (Fase 5) ───────────────────────────────────

def patron_semanal(persona_id: str, semanas: int = 8) -> dict:
    """
    Analiza el patrón de asistencia semanal de una persona durante las últimas N semanas.
    Retorna asistencia y tardanzas por día de semana.
    """
    from datetime import date, timedelta
    from db.connection import get_connection
    from sqlalchemy import text

    fecha_fin = date.today()
    fecha_inicio = fecha_fin - timedelta(weeks=semanas)

    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT EXTRACT(DOW FROM fecha_hora)::int as dow,
                       tipo, fecha_hora
                FROM asistencias
                WHERE persona_id = CAST(:pid AS uuid)
                  AND fecha_hora >= CAST(:fi AS timestamp)
                  AND fecha_hora <= CAST(:ff AS timestamp) + interval '1 day'
                ORDER BY fecha_hora
            """),
            {"pid": persona_id, "fi": fecha_inicio, "ff": fecha_fin},
        ).fetchall()

    nombres_dia = {1: "Lunes", 2: "Martes", 3: "Miércoles",
                   4: "Jueves", 5: "Viernes", 6: "Sábado", 0: "Domingo"}
    conteo = {d: {"marcaciones": 0} for d in range(7)}
    for r in rows:
        dow = r[0]
        conteo[dow]["marcaciones"] = conteo[dow].get("marcaciones", 0) + 1

    resultado = []
    for dow in [1, 2, 3, 4, 5, 6, 0]:
        resultado.append({
            "dia": nombres_dia[dow],
            "marcaciones": conteo[dow]["marcaciones"],
        })
    return {"persona_id": persona_id, "semanas": semanas,
            "fecha_inicio": str(fecha_inicio), "fecha_fin": str(fecha_fin),
            "patron": resultado}


def comparar_grupos(grupo_ids: list[str], fecha_inicio, fecha_fin) -> list[dict]:
    """
    Compara la tasa de asistencia entre varios grupos en un rango de fechas.
    Retorna lista ordenada de peor a mejor asistencia.
    """
    from db.connection import get_connection
    from sqlalchemy import text

    if not grupo_ids:
        return []

    placeholders = ", ".join([f"CAST(:g{i} AS uuid)" for i in range(len(grupo_ids))])
    params = {"fi": fecha_inicio, "ff": fecha_fin}
    for i, gid in enumerate(grupo_ids):
        params[f"g{i}"] = gid

    with get_connection() as conn:
        rows = conn.execute(
            text(f"""
                SELECT g.id::text, g.nombre,
                       COUNT(DISTINCT p.id) as total_personas,
                       COUNT(a.id) as total_marcaciones
                FROM grupos g
                LEFT JOIN personas p ON p.grupo_id = g.id AND p.activo = true
                LEFT JOIN asistencias a ON a.persona_id = p.id
                    AND a.fecha_hora >= CAST(:fi AS timestamp)
                    AND a.fecha_hora <= CAST(:ff AS timestamp) + interval '1 day'
                WHERE g.id IN ({placeholders})
                GROUP BY g.id, g.nombre
                ORDER BY total_marcaciones DESC
            """),
            params,
        ).fetchall()

    return [dict(r._mapping) for r in rows]


def ranking_departamento(grupo_id: str, fecha_inicio, fecha_fin) -> list[dict]:
    """
    Ranking de personas dentro de un grupo por tasa de asistencia en el período.
    Retorna lista ordenada de mejor a peor asistencia.
    """
    from datetime import timedelta
    from db.connection import get_connection
    from db.queries.asistencia_periodo import calcular_asistencia_periodo
    from sqlalchemy import text

    with get_connection() as conn:
        # Obtener personas del grupo con periodos activos en el rango
        periodos = conn.execute(
            text("""
                SELECT DISTINCT gp.id::text
                FROM grupos_periodo gp
                JOIN periodos_vigencia pv ON (
                    pv.nombre = gp.nombre
                    AND pv.fecha_inicio = gp.fecha_inicio
                    AND (pv.fecha_fin = gp.fecha_fin OR (pv.fecha_fin IS NULL AND gp.fecha_fin IS NULL))
                )
                JOIN personas p ON pv.persona_id = p.id
                WHERE p.grupo_id = CAST(:gid AS uuid)
                  AND gp.fecha_inicio <= CAST(:ff AS date)
                  AND (gp.fecha_fin IS NULL OR gp.fecha_fin >= CAST(:fi AS date))
            """),
            {"gid": grupo_id, "fi": fecha_inicio, "ff": fecha_fin},
        ).fetchall()

    ranking = []
    visto = set()
    for p_row in periodos:
        pid = p_row[0]
        if pid in visto:
            continue
        visto.add(pid)
        try:
            personas_asist = calcular_asistencia_periodo(pid)
            for pa in personas_asist:
                ranking.append({
                    "persona_id": pa["persona_id"],
                    "nombre": pa["nombre"],
                    "identificacion": pa.get("identificacion"),
                    "porcentaje_asistencia": pa["resumen"]["porcentaje_asistencia"],
                    "semaforo": pa["resumen"]["semaforo"],
                    "dias_presentes": pa["resumen"]["presentes"],
                    "dias_programados": pa["resumen"]["dias_programados"],
                })
        except Exception:
            pass

    ranking.sort(key=lambda x: x["porcentaje_asistencia"], reverse=True)
    return ranking


def tendencia_mensual(tipo_persona_id: str = None, meses: int = 6) -> list[dict]:
    """
    Tasa de asistencia mensual durante los últimos N meses.
    Agrupa por mes y calcula la tasa promedio.
    """
    from datetime import date
    from db.connection import get_connection
    from sqlalchemy import text

    fecha_fin = date.today().replace(day=1)
    # Calculate fecha_inicio manually without dateutil
    meses_atras = []
    for i in range(meses - 1, -1, -1):
        m = (fecha_fin.month - i - 1) % 12 + 1
        y = fecha_fin.year + (fecha_fin.month - i - 2) // 12
        meses_atras.append(date(y, m, 1))
    fecha_inicio = meses_atras[0]

    q = """
        SELECT DATE_TRUNC('month', a.fecha_hora)::date as mes,
               COUNT(DISTINCT p.id) as personas,
               COUNT(a.id) as marcaciones
        FROM asistencias a
        JOIN personas p ON a.persona_id = p.id
        WHERE a.fecha_hora >= CAST(:fi AS timestamp)
    """
    params = {"fi": fecha_inicio}
    if tipo_persona_id:
        q += " AND p.tipo_persona_id = CAST(:tipo_id AS uuid)"
        params["tipo_id"] = tipo_persona_id
    q += " GROUP BY mes ORDER BY mes"

    with get_connection() as conn:
        rows = conn.execute(text(q), params).fetchall()

    return [
        {"mes": str(r[0]), "personas": r[1], "marcaciones": r[2]}
        for r in rows
    ]


def resumen_periodo(periodo_id: str) -> dict:
    """
    Resumen de cumplimiento para un grupos_periodo específico.
    """
    from db.queries.asistencia_periodo import calcular_asistencia_periodo

    personas = calcular_asistencia_periodo(periodo_id)
    if not personas:
        return {"exito": False, "error": "No hay datos para este período"}

    total = len(personas)
    verdes = sum(1 for p in personas if p["resumen"]["semaforo"] == "Verde")
    amarillos = sum(1 for p in personas if p["resumen"]["semaforo"] == "Amarillo")
    rojos = sum(1 for p in personas if p["resumen"]["semaforo"] == "Rojo")
    promedio = round(
        sum(p["resumen"]["porcentaje_asistencia"] for p in personas) / total, 2
    ) if total > 0 else 0.0

    return {
        "exito": True,
        "periodo_id": periodo_id,
        "total_personas": total,
        "promedio_asistencia": promedio,
        "distribucion_semaforo": {"Verde": verdes, "Amarillo": amarillos, "Rojo": rojos},
        "personas_riesgo": [
            {"nombre": p["nombre"], "porcentaje": p["resumen"]["porcentaje_asistencia"],
             "semaforo": p["resumen"]["semaforo"]}
            for p in personas if p["resumen"]["semaforo"] == "Rojo"
        ],
    }


def distribucion_asistencia_periodo(periodo_id: str) -> dict:
    """
    Distribución de días de asistencia por estado dentro de un período.
    """
    from db.queries.asistencia_periodo import calcular_asistencia_periodo

    personas = calcular_asistencia_periodo(periodo_id)
    conteo = {"presente": 0, "presente_tarde": 0, "ausente": 0,
              "feriado": 0, "no_programado": 0}
    for p in personas:
        for d in p.get("detalle_asistencia", []):
            estado = d.get("estado", "no_programado")
            conteo[estado] = conteo.get(estado, 0) + 1

    total_programados = conteo["presente"] + conteo["presente_tarde"] + conteo["ausente"]
    tasa = round(
        (conteo["presente"] + conteo["presente_tarde"]) / total_programados * 100, 2
    ) if total_programados > 0 else 0.0

    return {"periodo_id": periodo_id, "distribucion": conteo,
            "tasa_asistencia": tasa, "total_personas": len(personas)}


def comparar_periodos_historicos(tipo_persona_id: str = None, n: int = 5) -> list[dict]:
    """
    Compara los últimos N períodos cerrados del mismo tipo de persona.
    """
    from db.connection import get_connection
    from db.queries.asistencia_periodo import calcular_asistencia_periodo
    from sqlalchemy import text

    q = """
        SELECT gp.id::text, gp.nombre, gp.fecha_inicio, gp.fecha_fin
        FROM grupos_periodo gp
        WHERE gp.estado IN ('cerrado', 'archivado')
        ORDER BY gp.fecha_inicio DESC
        LIMIT :n
    """
    with get_connection() as conn:
        rows = conn.execute(text(q), {"n": n}).fetchall()

    resultado = []
    for r in rows:
        try:
            resumen = resumen_periodo(r[0])
            if resumen.get("exito"):
                resultado.append({
                    "periodo_id": r[0],
                    "nombre": r[1],
                    "fecha_inicio": str(r[2]),
                    "fecha_fin": str(r[3]) if r[3] else None,
                    "promedio_asistencia": resumen["promedio_asistencia"],
                    "total_personas": resumen["total_personas"],
                    "distribucion_semaforo": resumen["distribucion_semaforo"],
                })
        except Exception:
            pass
    return resultado


def tasa_riesgo_por_grupo(grupo_id: str) -> dict:
    """
    Porcentaje de personas en riesgo (Rojo) dentro de un grupo.
    """
    from db.connection import get_connection
    from sqlalchemy import text
    from datetime import date, timedelta

    fecha_fin = date.today()
    fecha_inicio = fecha_fin - timedelta(days=30)

    df = load_data_asistencia_dataframe(fecha_inicio, fecha_fin, grupo_id=grupo_id)
    if df.empty:
        return {"grupo_id": grupo_id, "tasa_riesgo": 0.0, "total_personas": 0,
                "personas_en_riesgo": 0}

    total = df["persona_id"].nunique()
    en_riesgo = 0
    for _, p_df in df.groupby("persona_id"):
        if calcular_risk_score(p_df) >= 70:
            en_riesgo += 1

    return {
        "grupo_id": grupo_id,
        "tasa_riesgo": round(en_riesgo / total * 100, 2) if total > 0 else 0.0,
        "total_personas": total,
        "personas_en_riesgo": en_riesgo,
    }
