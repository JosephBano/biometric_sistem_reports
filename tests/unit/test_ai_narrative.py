"""
Tests de `app.domain.ai_narrative` (Fase 4e.4 — migración de ia_report.py).

Mockeamos requests para no llamar a la API real de DeepSeek.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain import ai_narrative


def _hallazgos_base(**overrides):
    """Hallazgos base que cumplen el contrato esperado por `generar_narrativo`."""
    base = {
        "exito": True,
        "rango": {"inicio": "2026-07-01", "fin": "2026-07-07"},
        "resumen_general": {
            "total_registros": 100,
            "tasa_asistencia_promedio": 85.0,
            "ausentes": 5,
            "tardanzas": 10,
        },
        "riesgos": [],
        "anomalias": [],
    }
    base.update(overrides)
    return base


class TestFallbackReglas:

    def test_sin_datos_devuelve_mensaje_generico(self):
        """Sin hallazgos o con `exito=False`, retornar mensaje genérico."""
        assert ai_narrative.generar_narrativo({}) == (
            "No hay suficientes datos analíticos para generar un reporte narrativo."
        )
        assert ai_narrative.generar_narrativo({"exito": False}) == (
            "No hay suficientes datos analíticos para generar un reporte narrativo."
        )

    def test_sin_api_key_usa_fallback_reglas(self):
        """Sin DEEPSEEK_API_KEY en env, usar motor regla-base."""
        hallazgos = _hallazgos_base()
        with patch.dict("os.environ", {}, clear=False):
            # Asegurar que no haya DEEPSEEK_API_KEY en el env del test.
            import os
            os.environ.pop("DEEPSEEK_API_KEY", None)
            texto = ai_narrative.generar_narrativo(hallazgos)

        assert "Reporte de Desempeño" in texto
        assert "2026-07-01" in texto
        assert "2026-07-07" in texto
        assert "85" in texto  # tasa_asistencia_promedio
        assert "**" in texto  # énfasis markdown

    def test_fallback_incluye_personas_riesgo_alto(self):
        """Cuando hay riesgos altos, el reporte los lista."""
        hallazgos = _hallazgos_base(
            riesgos=[
                {"nombre": "Juan Pérez", "grupo": "Docentes", "score": 85,
                 "semaforo": "Rojo"},
                {"nombre": "María López", "grupo": "Administrativos",
                 "score": 90, "semaforo": "Rojo"},
            ],
        )
        import os
        os.environ.pop("DEEPSEEK_API_KEY", None)
        texto = ai_narrative.generar_narrativo(hallazgos)

        assert "Juan Pérez" in texto
        assert "María López" in texto
        assert "Personas en riesgo alto" in texto
        assert "2 detectadas" in texto

    def test_fallback_incluye_anomalias(self):
        """Cuando hay anomalías, el reporte las lista."""
        hallazgos = _hallazgos_base(
            anomalias=[
                {"nombre": "Carlos Ruiz", "detalle": "Salida 3h antes"},
                {"nombre": "Ana Vega", "detalle": "Sin marcación de salida"},
            ],
        )
        import os
        os.environ.pop("DEEPSEEK_API_KEY", None)
        texto = ai_narrative.generar_narrativo(hallazgos)

        assert "Carlos Ruiz" in texto
        assert "Ana Vega" in texto
        assert "Anomalías" in texto

    def test_fallback_califica_asistencia_segun_tasa(self):
        """Tasa ≥90 = excelente; ≥75 = aceptable; <75 = requiere intervención."""
        import os
        os.environ.pop("DEEPSEEK_API_KEY", None)

        # Tasa excelente
        hallazgos_excelente = _hallazgos_base(
            resumen_general={
                "total_registros": 100, "tasa_asistencia_promedio": 95.0,
                "ausentes": 0, "tardanzas": 5,
            }
        )
        texto = ai_narrative.generar_narrativo(hallazgos_excelente)
        assert "excelente" in texto.lower()

        # Tasa baja → debe decir "por debajo del estándar"
        hallazgos_bajo = _hallazgos_base(
            resumen_general={
                "total_registros": 100, "tasa_asistencia_promedio": 60.0,
                "ausentes": 30, "tardanzas": 10,
            }
        )
        texto = ai_narrative.generar_narrativo(hallazgos_bajo)
        assert "por debajo del estándar" in texto.lower()


class TestApiDeepSeek:

    def test_con_api_key_llama_deepseek_y_retorna_respuesta(self):
        """Con DEEPSEEK_API_KEY configurada, llamar a la API y devolver respuesta."""
        hallazgos = _hallazgos_base()

        mock_response = type(
            "_R", (), {"status_code": 200, "json": lambda self: {
                "choices": [{"message": {"content": "Narrativa de DeepSeek."}}
                ]}}
        )()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake-key"}), \
             patch("app.domain.ai_narrative.requests.post",
                   return_value=mock_response) as mock_post:
            texto = ai_narrative.generar_narrativo(hallazgos, contexto="ctx")

        assert texto == "Narrativa de DeepSeek."
        mock_post.assert_called_once()
        # Verificar que el prompt contiene el rango
        call_kwargs = mock_post.call_args.kwargs
        prompt_enviado = call_kwargs["json"]["messages"][0]["content"]
        assert "2026-07-01" in prompt_enviado
        assert "ctx" in prompt_enviado

    def test_si_deepseek_falla_usa_fallback(self):
        """Si la API falla (status != 200), usar fallback sin lanzar."""
        hallazgos = _hallazgos_base()

        mock_response = type(
            "_R", (), {"status_code": 500, "text": "Internal Error"}
        )()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake-key"}), \
             patch("app.domain.ai_narrative.requests.post",
                   return_value=mock_response):
            texto = ai_narrative.generar_narrativo(hallazgos)

        # Cayó al fallback
        assert "Reporte de Desempeño" in texto

    def test_si_deepseek_lanza_excepcion_usa_fallback(self):
        """Si requests.post lanza excepción, usar fallback."""
        hallazgos = _hallazgos_base()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake-key"}), \
             patch("app.domain.ai_narrative.requests.post",
                   side_effect=ConnectionError("timeout")):
            texto = ai_narrative.generar_narrativo(hallazgos)

        assert "Reporte de Desempeño" in texto
