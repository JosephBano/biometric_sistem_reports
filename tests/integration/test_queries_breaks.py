"""
Tests de integración de `db.queries.breaks` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from db import set_thread_tenant
from db.queries.breaks import _normalizar_hora, get_breaks_categorizados_dict


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


class TestNormalizarHora:

    def test_normalizar_hora_none(self):
        """None → None."""
        assert _normalizar_hora(None) is None

    def test_normalizar_hora_string_sin_segundos(self):
        """String 'HH:MM' se retorna tal cual."""
        assert _normalizar_hora("08:30") == "08:30"

    def test_normalizar_hora_string_con_segundos(self):
        """String 'HH:MM:SS' se trunca a HH:MM."""
        assert _normalizar_hora("08:30:45") == "08:30"

    def test_normalizar_hora_time_object(self):
        """Objeto time → 'HH:MM'."""
        assert _normalizar_hora(time(8, 30)) == "08:30"
        assert _normalizar_hora(time(15, 5)) == "15:05"

    def test_normalizar_hora_timedelta(self):
        """timedelta (que viene de Postgres)::time → 'HH:MM'."""
        td = timedelta(hours=8, minutes=30)
        assert _normalizar_hora(td) == "08:30"

    def test_normalizar_hora_timedelta_cero(self):
        """timedelta 0 → '00:00'."""
        assert _normalizar_hora(timedelta(0)) == "00:00"

    def test_normalizar_hora_timedelta_mayor_a_24h(self):
        """timedelta >24h (caso patológico) sigue funcionando."""
        td = timedelta(hours=25)
        # 25 horas = 25*60 = 1500 min, divmod(1500//60, 60) = (25, 0)
        assert _normalizar_hora(td) == "25:00"


class TestGetBreaksCategorizadosDict:

    def test_get_breaks_sin_datos_retorna_dict_vacio(self):
        """Sin breaks, retorna dict vacío."""
        result = get_breaks_categorizados_dict()
        assert result == {}

    def test_get_breaks_con_rango_sin_datos(self):
        """Con rango específico, retorna dict vacío si no hay breaks."""
        result = get_breaks_categorizados_dict(
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 7),
        )
        assert result == {}
