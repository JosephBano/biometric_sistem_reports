"""
Tests de integración de `db.queries.asistencia_periodo` (Fase 7.4).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from db import set_thread_tenant
from db.queries.asistencia_periodo import calcular_asistencia_periodo
from db.queries.periodos import crear_periodo


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


class TestCalcularAsistenciaPeriodo:

    def test_periodo_inexistente_retorna_lista_vacia(self):
        """Si el período no existe, retorna []."""
        result = calcular_asistencia_periodo("00000000-0000-0000-0000-000000000000")
        assert result == []

    def test_periodo_sin_personas_retorna_lista_vacia(self):
        """Período sin personas asignadas → []."""
        nombre = f"Per-Vacio-{uuid.uuid4().hex[:8]}"
        p = crear_periodo(
            nombre=nombre,
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 7),
        )
        result = calcular_asistencia_periodo(p["id"])
        assert result == []
