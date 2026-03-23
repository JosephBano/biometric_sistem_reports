"""
Cálculo de asistencia para periodos de vigencia (matrículas/contratos).
Cruza el periodo, las personas de ese periodo, feriados, horarios y marcaciones.
"""

from datetime import date, timedelta
from sqlalchemy import text
from db.connection import get_connection
from db.queries.feriados import get_feriados_set
from db.queries.horarios import get_horario_en_fecha


def calcular_asistencia_periodo(periodo_id: str) -> list[dict]:
    """
    Calcula la asistencia de todas las personas que comparten el mismo nombre
    y rango de fechas que el periodo_id proporcionado.
    
    Retorna una lista con el detalle y resúmenes de cada persona.
    """
    with get_connection() as conn:
        # 1. Intentar leer desde grupos_periodo (Fase 4 UI)
        gp = conn.execute(
            text("SELECT nombre, fecha_inicio, fecha_fin FROM grupos_periodo WHERE id = CAST(:id AS uuid)"),
            {"id": periodo_id},
        ).fetchone()
        if gp:
            p_data = dict(gp._mapping)
        else:
            # fallback: leer desde periodos_vigencia (compatibilidad)
            pv = conn.execute(
                text("SELECT nombre, fecha_inicio, fecha_fin FROM periodos_vigencia WHERE id = CAST(:id AS uuid)"),
                {"id": periodo_id},
            ).fetchone()
            if not pv:
                return []
            p_data = dict(pv._mapping)
        nombre = p_data["nombre"]
        fecha_inicio = p_data["fecha_inicio"]
        fecha_fin = p_data["fecha_fin"] or date.today() # fallback si es indefinido
        
        # 2. Obtener feriados dentro del rango
        feriados = get_feriados_set(fecha_inicio, fecha_fin)
        
        # 3. Obtener todas las personas en este determinado período (mismo nombre y fechas)
        personas = conn.execute(
            text("""
                SELECT 
                    p.id as persona_id, p.nombre, p.identificacion,
                    g.nombre as grupo, c.nombre as categoria
                FROM periodos_vigencia pv
                JOIN personas p ON pv.persona_id = p.id
                LEFT JOIN grupos g ON p.grupo_id = g.id
                LEFT JOIN categorias c ON p.categoria_id = c.id
                WHERE pv.nombre = :nombre
                  AND pv.fecha_inicio = :fecha_inicio
                  AND (pv.fecha_fin = :fecha_fin OR (:fecha_fin IS NULL AND pv.fecha_fin IS NULL))
            """),
            {
                "nombre": nombre,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": p_data["fecha_fin"]
            }
        ).fetchall()
        
        resultado = []
        
        for p in personas:
            p_dict = dict(p._mapping) if hasattr(p, "_mapping") else dict(zip(['persona_id', 'nombre', 'identificacion', 'grupo', 'categoria'], p))
            persona_id = str(p_dict["persona_id"])
            
            # 4. Obtener todas las asistencias de esta persona en el rango
            marcaciones = conn.execute(
                text("""
                    SELECT fecha_hora, tipo
                    FROM asistencias
                    WHERE persona_id = CAST(:persona_id AS uuid)
                      AND fecha_hora >= CAST(:inicio AS timestamp)
                      AND fecha_hora <= CAST(:fin AS timestamp) + interval '1 day'
                    ORDER BY fecha_hora
                """),
                {"persona_id": persona_id, "inicio": fecha_inicio, "fin": fecha_fin}
            ).fetchall()
            
            # Agrupar marcaciones por fecha
            asist_by_date = {}
            for m in marcaciones:
                m_data = m._mapping if hasattr(m, "_mapping") else {"fecha_hora": m[0], "tipo": m[1]}
                d = m_data["fecha_hora"].date()
                if d not in asist_by_date:
                    asist_by_date[d] = []
                asist_by_date[d].append(m_data)
                
            dias_detalle = []
            presentes = 0
            ausentes = 0
            dias_programados = 0
            
            current_date = fecha_inicio
            while current_date <= fecha_fin:
                status = "no_programado"
                entrada_marcada = None
                salida_marcada = None
                entrada_esperada = None
                salida_esperada = None
                tardanza = False
                
                # Check holiday
                if current_date in feriados:
                    status = "feriado"
                else:
                    # Lookup schedule
                    horario = get_horario_en_fecha(conn, persona_id, current_date)
                    current_weekday = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"][current_date.weekday()]
                    
                    if horario and horario.get(current_weekday):
                        dias_programados += 1
                        entrada_esperada = horario[current_weekday]
                        salida_esperada = horario.get(f"{current_weekday}_salida")
                        
                        marcs = asist_by_date.get(current_date, [])
                        if marcs:
                            presentes += 1
                            status = "presente"
                            
                            # Find first entry
                            entries = [m for m in marcs if m["tipo"] in ("entrada", "0")]
                            if entries:
                                entrada_marcada = entries[0]["fecha_hora"].time().strftime("%H:%M")
                                if entrada_esperada and entrada_marcada > entrada_esperada:
                                    status = "presente_tarde"
                                    tardanza = True
                                    
                            # Find last exit
                            exits = [m for m in marcs if m["tipo"] in ("salida", "1")]
                            if exits:
                                salida_marcada = exits[-1]["fecha_hora"].time().strftime("%H:%M")
                        else:
                            ausentes += 1
                            status = "ausente"
                            
                dias_detalle.append({
                    "fecha": current_date.strftime("%Y-%m-%d"),
                    "dia_semana": ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"][current_date.weekday()],
                    "estado": status,
                    "entrada_marcada": entrada_marcada,
                    "salida_marcada": salida_marcada,
                    "entrada_esperada": entrada_esperada,
                    "salida_esperada": salida_esperada,
                    "tardanza": tardanza
                })
                current_date += timedelta(days=1)
                
            # Calcular % y semáforo
            porcentaje = (presentes / dias_programados * 100) if dias_programados > 0 else 100.0
            
            semaforo = "Rojo"
            color = "#E05D5D" # red
            if porcentaje >= 90:
                semaforo = "Verde"
                color = "#5D9E5D" # green
            elif porcentaje >= 75:
                semaforo = "Amarillo"
                color = "#E0C25D" # yellow
                
            p_dict["detalle_asistencia"] = dias_detalle
            p_dict["resumen"] = {
                "presentes": presentes,
                "ausentes": ausentes,
                "dias_programados": dias_programados,
                "porcentaje_asistencia": round(porcentaje, 2),
                "semaforo": semaforo,
                "color": color
            }
            resultado.append(p_dict)
            
        return resultado
