"""
Módulo de reportes narrativos utilizando IA (DeepSeek) o Fallback Reglado.
Genera explicaciones textuales legibles sobre los hallazgos de analytics.py.
"""

import os
import requests

def generar_narrativo(hallazgos: dict, contexto: str = "") -> str:
    """
    Toma un diccionario de hallazgos estadísticos de analytics.py
    y devuelve una narrativa explicativa.
    Utiliza la API de DeepSeek si la clave está disponible; de lo contrario, 
    utiliza un motor relgla-base determinista.
    """
    if not hallazgos or not hallazgos.get("exito"):
         return "No hay suficientes datos analíticos para generar un reporte narrativo."

    api_key = os.getenv("DEEPSEEK_API_KEY")
    resumen = hallazgos["resumen_general"]
    riesgos_altos = [r for r in hallazgos.get("riesgos", []) if r.get("semaforo") == "Rojo"]
    anomalias = hallazgos.get("anomalias", [])

    if api_key:
         try:
              # Construir Prompt
              prompt = f"""
              Eres un analista de recursos humanos experto. Genera un reporte narrativo ejecutivo
              basado en los siguientes datos de asistencia. 
              {contexto}
              
              DATOS:
              - Rango de fechas: {hallazgos['rango']['inicio']} a {hallazgos['rango']['fin']}
              - Total registros diarios analizados: {resumen['total_registros']}
              - Tasa de asistencia promedio: {resumen['tasa_asistencia_promedio']}%
              - Ausencias totales: {resumen['ausentes']}
              - Tardanzas totales: {resumen['tardanzas']}
              
              HALLAZGOS CRÍTICOS:
              - Personas Riesgo Alto (Score >= 70): {[{ "nombre": r['nombre'], "grupo": r['grupo'] } for r in riesgos_altos]}
              - Anomalías detectadas: {[a['detalle'] for a in anomalias]}
              
              INSTRUCCIONES:
              1. Escribe 3 párrafos: (A) Resumen general de desempeño, (B) Alertas críticas, (C) Recomendaciones de acción para el supervisor.
              2. Sé profesional, directo y enfocado en la mejora continua de la puntualidad.
              """
              
              headers = {
                   "Authorization": f"Bearer {api_key}",
                   "Content-Type": "application/json"
              }
              data = {
                   "model": "deepseek-chat",
                   "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.7
              }
              
              response = requests.post(
                   "https://api.deepseek.com/v1/chat/completions",
                   headers=headers,
                   json=data,
                   timeout=15
              )
              
              if response.status_code == 200:
                   return response.json()['choices'][0]['message']['content']
                   
         except Exception:
              pass # Fallback a regla-base si falla la API
              
    # --- FALLBACK REGLA-BASE ---
    text = f"💡 **Reporte de Desempeño Ejecutivo ({hallazgos['rango']['inicio']} — {hallazgos['rango']['fin']})**\n\n"
    text += f"Durante este período, se ha registrado una asistencia promedio del **{resumen['tasa_asistencia_promedio']}%** sobre la jornada laboral programada. "
    
    if resumen['tasa_asistencia_promedio'] >= 90:
         text += "El comportamiento general se mantiene en niveles satisfactorios y óptimos.\n\n"
    elif resumen['tasa_asistencia_promedio'] >= 75:
         text += "Se observa una disminución ligera en la puntualidad que requiere seguimiento preventivo.\n\n"
    else:
         text += "⚠️ **Alerta:** La tasa de asistencia actual está por debajo del estándar mínimo aceptable. Se requiere intervención inmediata.\n\n"
         
    if riesgos_altos or anomalias:
         text += "🚨 **Señales de Alerta Críticas:**\n"
         if riesgos_altos:
              text += f"- Se identificaron **{len(riesgos_altos)} personas** en zona de riesgo alto de incumplimiento por acumulación de inasistencias o tardanzas constantes.\n"
         if anomalias:
              text += f"- Se han detectado **{len(anomalias)} comportamientos anómalos** estadísticamente (exceso puntual de tardanzas no habituales).\n"
         text += "\n"
         
    text += "📋 **Recomendaciones para Supervisión:**\n"
    text += "1. Entrevistar a las personas con mayor Risk Score para mitigar ausentismo.\n"
    text += "2. Monitorear los horarios asignados para descartar desconfiguraciones administrativas.\n"
    
    return text
