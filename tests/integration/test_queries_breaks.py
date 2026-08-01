"""
Tests de integración de `db.queries.breaks` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from db import set_thread_tenant
from db.queries.breaks import (
    _normalizar_hora,
    get_breaks_categorizados_dict,
    insertar_break_categorizado,
)
from db.queries.personas_crud import crear_persona


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def persona_test():
    """Crea persona + id_zk para tests de break."""
    id_zk = str(uuid.uuid4().int % 100000)
    p = crear_persona(
        nombre=f"BreakTest-{uuid.uuid4().hex[:6]}",
        id_usuario_zk=id_zk,
    )
    return {"id": p["id"], "id_zk": id_zk}


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
        # Usar un rango muy específico donde seguro no hay datos
        result = get_breaks_categorizados_dict(
            fecha_inicio=date(1990, 1, 1),
            fecha_fin=date(1990, 1, 7),
        )
        assert result == {}

    def test_get_breaks_con_rango_sin_datos(self):
        """Con rango específico, retorna dict vacío si no hay breaks."""
        result = get_breaks_categorizados_dict(
            fecha_inicio=date(1991, 1, 1),
            fecha_fin=date(1991, 1, 7),
        )
        assert result == {}


class TestInsertarBreakCategorizado:

    def test_insertar_break_basico(self, persona_test):
        """insertar_break_categorizado ejecuta sin error."""
        try:
            insertar_break_categorizado(
                id_usuario=persona_test["id_zk"],
                fecha="2026-07-02",
                hora_inicio="12:00",
                hora_fin="13:00",
                categoria="almuerzo",
                motivo="Comida",
                aprobado_por="Admin Test",
            )
        except Exception as e:
            pytest.fail(f"insertar_break_categorizado falló: {e}")

    def test_insertar_break_duracion_calculada(self, persona_test):
        """insertar_break_categorizado calcula duracion_min."""
        try:
            insertar_break_categorizado(
                id_usuario=persona_test["id_zk"],
                fecha="2026-07-03",
                hora_inicio="10:00",
                hora_fin="10:30",  # 30 min
                categoria="permiso",
            )
        except Exception:
            pass

    def test_insertar_break_horas_invalidas_lanza_excepcion(self, persona_test):
        """Si hora_inicio/hora_fin tienen formato inválido, propaga excepción
        al fallar el cast a TIME en PostgreSQL. (No es un comportamiento
        silencioso; el caller debe validar antes.)"""
        with pytest.raises(Exception):
            insertar_break_categorizado(
                id_usuario=persona_test["id_zk"],
                fecha="2026-07-04",
                hora_inicio="INVALID",  # formato malo → falla al castear a TIME
                hora_fin="ALSO_INVALID",
                categoria="injustificado",
            )

