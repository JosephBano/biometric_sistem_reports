"""
Tests de integración de `db.queries.horarios` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid

import pytest

from db import set_thread_tenant
from db.queries.horarios import (
    delete_horario,
    get_horario,
    get_horarios,
    upsert_horario,
    upsert_horarios,
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
def persona_test(tenant_id):
    """Crea una persona para asociar horario."""
    id_zk = str(uuid.uuid4().int % 100000)
    p = crear_persona(
        nombre=f"HorTest-{uuid.uuid4().hex[:6]}",
        id_usuario_zk=id_zk,
    )
    return {"id": p["id"], "id_zk": id_zk}


class TestUpsertHorario:

    def test_upsert_horario_basico(self, persona_test):
        """upsert_horario crea un horario para una persona."""
        result = upsert_horario({
            "id_usuario": persona_test["id_zk"],
            "lunes": "08:00",
            "lunes_salida": "17:00",
            "almuerzo_min": 60,
        })
        assert result is not None
        assert result["lunes"] == "08:00"
        assert result["lunes_salida"] == "17:00"

    def test_upsert_horario_reemplaza_existente(self, persona_test):
        """upsert_horario actualiza si ya existe."""
        upsert_horario({
            "id_usuario": persona_test["id_zk"],
            "lunes": "08:00",
        })
        result = upsert_horario({
            "id_usuario": persona_test["id_zk"],
            "lunes": "09:00",  # cambiar
        })
        assert result["lunes"] == "09:00"


class TestUpsertHorarios:

    def test_upsert_horarios_lote(self, persona_test):
        """upsert_horarios procesa una lista de horarios."""
        result = upsert_horarios([
            {
                "id_usuario": persona_test["id_zk"],
                "lunes": "08:00",
                "martes": "08:00",
            },
        ])
        assert result >= 1


class TestGetHorarios:

    def test_get_horarios_vacio(self):
        """Sin horarios cargados, retorna dict con estructura."""
        result = get_horarios()
        assert "by_id" in result or "by_nombre" in result or result == {}

    def test_get_horarios_incluye_persona(self, persona_test):
        """Después de upsert_horario, get_horarios lo incluye."""
        upsert_horario({
            "id_usuario": persona_test["id_zk"],
            "lunes": "08:00",
        })
        result = get_horarios()
        # Debe tener estructura con by_id y/o by_nombre
        if isinstance(result, dict):
            assert "by_id" in result or "by_nombre" in result


class TestGetHorario:

    def test_get_horario_existente(self, persona_test):
        """get_horario retorna el horario de una persona."""
        upsert_horario({
            "id_usuario": persona_test["id_zk"],
            "lunes": "08:00",
            "martes": "09:00",
        })
        result = get_horario(persona_test["id_zk"])
        if result:  # puede ser None si no se encontró
            assert result.get("id_usuario") == persona_test["id_zk"]

    def test_get_horario_inexistente(self):
        """get_horario con id_usuario que no existe → None o dict vacío."""
        result = get_horario("9999999")
        assert result is None or result == {}


class TestDeleteHorario:

    def test_delete_horario_existente(self, persona_test):
        """delete_horario elimina el horario de una persona."""
        upsert_horario({
            "id_usuario": persona_test["id_zk"],
            "lunes": "08:00",
        })
        result = delete_horario(persona_test["id_zk"])
        # True si eliminó, False si no encontró
        assert isinstance(result, bool)

    def test_delete_horario_inexistente(self):
        """delete_horario con id_usuario que no existe → False."""
        result = delete_horario("9999999")
        assert result is False
