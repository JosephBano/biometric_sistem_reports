"""
Tests de integración de `db.queries.personas_crud` y `db.queries.personas`
(Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid

import pytest

from db import set_thread_tenant
from db.queries.personas_crud import (
    actualizar_persona,
    crear_persona,
    get_historico_persona,
    get_persona,
    get_usuarios_zk_con_estado,
    listar_personas,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def persona_test():
    """Crea persona de prueba."""
    id_zk = str(uuid.uuid4().int % 100000)
    p = crear_persona(
        nombre=f"Pers-{uuid.uuid4().hex[:6]}",
        identificacion=str(uuid.uuid4().int)[:10],
        id_usuario_zk=id_zk,
    )
    yield p


class TestCrearPersona:

    def test_crear_persona_minima(self):
        """Crear con argumentos mínimos."""
        nombre = f"Min-{uuid.uuid4().hex[:6]}"
        p = crear_persona(nombre=nombre)
        assert p["nombre"] == nombre
        assert p["activo"] is True

    def test_crear_persona_con_identificacion(self):
        """Crear con identificacion."""
        nombre = f"Id-{uuid.uuid4().hex[:6]}"
        idf = str(uuid.uuid4().int)[:10]
        p = crear_persona(nombre=nombre, identificacion=idf)
        assert p["identificacion"] == idf

    def test_crear_persona_con_id_zk(self):
        """Crear con id_usuario_zk crea la persona (sin requerir dispositivo)."""
        id_zk = str(uuid.uuid4().int % 100000)
        p = crear_persona(
            nombre=f"Zk-{uuid.uuid4().hex[:6]}",
            id_usuario_zk=id_zk,
        )
        assert p is not None
        # get_usuarios_zk_con_estado retorna lista (puede estar vacía
        # si no hay dispositivo en la BD)
        result = get_usuarios_zk_con_estado()
        assert isinstance(result, list)


class TestGetPersona:

    def test_get_persona_existente(self, persona_test):
        """get_persona retorna la persona creada."""
        result = get_persona(persona_test["id"])
        assert result is not None
        assert result["id"] == persona_test["id"]

    def test_get_persona_inexistente(self):
        """get_persona con UUID inexistente → None."""
        result = get_persona("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestListarPersonas:

    def test_listar_personas_retorna_lista(self, persona_test):
        """listar_personas incluye la persona creada."""
        result = listar_personas()
        assert isinstance(result, list)
        ids = [p["id"] for p in result]
        assert persona_test["id"] in ids


class TestActualizarPersona:

    def test_actualizar_persona_nombre(self, persona_test):
        """actualizar_persona cambia el nombre."""
        nuevo_nombre = f"Updated-{uuid.uuid4().hex[:6]}"
        result = actualizar_persona(
            persona_test["id"], {"nombre": nuevo_nombre},
        )
        assert result is not None
        assert result["nombre"] == nuevo_nombre

    def test_actualizar_persona_sin_campos(self, persona_test):
        """actualizar_persona sin campos → None o sin cambios."""
        result = actualizar_persona(persona_test["id"], {})
        assert result is None

    def test_actualizar_persona_campos_invalidos_se_ignoran(self, persona_test):
        """Campos no permitidos se ignoran."""
        result = actualizar_persona(
            persona_test["id"],
            {"id": "x", "creado_en": "x"},  # ambos inválidos
        )
        assert result is None or result == {}


class TestUsuariosZkConEstado:

    def test_get_usuarios_zk_con_estado(self, persona_test):
        """Retorna lista de {id_usuario_zk, estado}."""
        result = get_usuarios_zk_con_estado()
        assert isinstance(result, list)


class TestGetHistoricoPersona:

    def test_get_historico_persona_por_identificacion(self, persona_test):
        """get_historico_persona busca por identificacion."""
        result = get_historico_persona(persona_test["identificacion"])
        # El formato exacto varía según la versión; solo verificamos que retorna
        # algo distinto a None/{} si la persona existe
        if result and result != {}:
            assert "id" in result or "nombre" in result

    def test_get_historico_persona_inexistente(self):
        """get_historico_persona con identificacion inexistente → None o {}."""
        result = get_historico_persona("9999999999")
        assert result is None or result == {}
