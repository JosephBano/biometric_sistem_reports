"""
Módulo de reportes narrativos utilizando IA (DeepSeek) o Fallback Reglado.
Genera explicaciones textuales legibles sobre los hallazgos de analytics.py.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

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
              else:
                   logger.warning(f"DeepSeek API error {response.status_code}: {response.text[:200]}")

         except Exception as e:
              logger.warning(f"DeepSeek API falló, usando fallback: {e}")
              
    # --- FALLBACK REGLA-BASE ---
    rango_inicio = hallazgos['rango']['inicio']
    rango_fin = hallazgos['rango']['fin']
    tasa = resumen['tasa_asistencia_promedio']
    total = resumen['total_registros']
    ausentes = resumen['ausentes']
    tardanzas = resumen['tardanzas']
    presentes = resumen.get('presentes', total - ausentes - tardanzas)

    text = f"**Reporte de Desempeño — {rango_inicio} al {rango_fin}**\n\n"

    # Párrafo 1: Resumen general con cifras concretas
    text += f"Durante este período se analizaron **{total} registros diarios**. "
    text += f"La tasa de asistencia promedio fue del **{tasa}%** "
    text += f"({presentes} presentes, {ausentes} ausencias, {tardanzas} tardanzas). "

    if tasa >= 90:
        text += "El equipo mantiene un nivel de asistencia **excelente**.\n\n"
    elif tasa >= 75:
        text += "El nivel es **aceptable** pero se detectan oportunidades de mejora en puntualidad.\n\n"
    else:
        text += "La tasa está **por debajo del estándar mínimo (75%)** y requiere intervención inmediata.\n\n"

    # Párrafo 2: Personas en riesgo alto con nombres
    if riesgos_altos:
        nombres_riesgo = [r['nombre'] for r in riesgos_altos[:5]]
        text += f"**Personas en riesgo alto ({len(riesgos_altos)} detectadas):**\n"
        for r in riesgos_altos[:5]:
            grupo_str = f" — {r['grupo']}" if r.get('grupo') else ""
            text += f"- **{r['nombre']}**{grupo_str}: Score {r['score']}/100\n"
        if len(riesgos_altos) > 5:
            text += f"- _(y {len(riesgos_altos) - 5} más)_\n"
        text += "\n"
    else:
        text += "No se identificaron personas en zona de riesgo alto. El equipo muestra un cumplimiento consistente.\n\n"

    # Párrafo 3: Anomalías estadísticas con detalle
    if anomalias:
        text += f"**Anomalías estadísticas detectadas ({len(anomalias)}):**\n"
        for a in anomalias[:5]:
            text += f"- **{a['nombre']}**: {a['detalle']}\n"
        if len(anomalias) > 5:
            text += f"- _(y {len(anomalias) - 5} más)_\n"
        text += "\n"

    # Párrafo 4: Recomendaciones específicas
    text += "**Recomendaciones:**\n"
    if riesgos_altos:
        nombres_top = ", ".join([r['nombre'] for r in riesgos_altos[:3]])
        text += f"1. Citar a entrevista de seguimiento a: {nombres_top}.\n"
    else:
        text += "1. Mantener el seguimiento habitual — no hay casos críticos urgentes.\n"

    if tardanzas > 0:
        pct_tard = round(tardanzas / total * 100, 1) if total > 0 else 0
        text += f"2. Las tardanzas representan el **{pct_tard}%** de los registros. "
        if pct_tard > 15:
            text += "Revisar horarios de ingreso y considerar medidas correctivas.\n"
        else:
            text += "Nivel aceptable; monitorear preventivamente.\n"

    if ausentes > 0:
        pct_aus = round(ausentes / total * 100, 1) if total > 0 else 0
        text += f"3. Las ausencias representan el **{pct_aus}%** del período. "
        if pct_aus > 10:
            text += "Verificar justificaciones y evaluar medidas de incentivo a la asistencia.\n"
        else:
            text += "Nivel dentro del rango esperado.\n"

    return text
