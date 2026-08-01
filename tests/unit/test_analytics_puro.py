"""
Tests unitarios de `app.domain.analytics` (Fase 7.4 — cobertura).

Solo la función pura `calcular_risk_score` (sin BD ni DataFrame real).
Las funciones que requieren BD se cubren por integración.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.domain.analytics import calcular_risk_score


def _df(rows: list[dict]) -> pd.DataFrame:
    """Helper para crear DataFrames mínimos."""
    return pd.DataFrame(rows)


class TestCalcularRiskScore:

    def test_dataframe_vacio_retorna_0(self):
        """DataFrame vacío → score 0."""
        assert calcular_risk_score(_df([])) == 0

    def test_sin_ausencias_sin_tardanzas_retorna_0(self):
        """Persona sin incidencias → score 0."""
        df = _df([
            {"estado": "presente", "tardanza": False},
            {"estado": "presente", "tardanza": False},
            {"estado": "feriado", "tardanza": False},
        ])
        assert calcular_risk_score(df) == 0

    def test_una_ausencia_15_puntos(self):
        """1 ausencia → 15 puntos."""
        df = _df([
            {"estado": "ausente", "tardanza": False},
            {"estado": "presente", "tardanza": False},
        ])
        assert calcular_risk_score(df) == 15

    def test_una_tardanza_5_puntos(self):
        """1 tardanza → 5 puntos."""
        df = _df([
            {"estado": "presente_tarde", "tardanza": True},
            {"estado": "presente", "tardanza": False},
        ])
        assert calcular_risk_score(df) == 5

    def test_multiples_ausencias_y_tardanzas(self):
        """3 ausencias (45) + 4 tardanzas (20) = 65 puntos."""
        rows = [{"estado": "ausente", "tardanza": False}] * 3
        rows += [{"estado": "presente_tarde", "tardanza": True}] * 4
        rows += [{"estado": "presente", "tardanza": False}] * 3
        assert calcular_risk_score(_df(rows)) == 65

    def test_score_tope_100(self):
        """El score se tope en 100, sin importar cuántas ausencias+tardanzas."""
        rows = [{"estado": "ausente", "tardanza": False}] * 20
        rows += [{"estado": "presente_tarde", "tardanza": True}] * 20
        assert calcular_risk_score(_df(rows)) == 100

    def test_score_zona_roja(self):
        """Score >= 70 = zona roja (consistente con el semáforo)."""
        rows = [{"estado": "ausente", "tardanza": False}] * 5  # 75 pts
        assert calcular_risk_score(_df(rows)) == 75  # zona roja
