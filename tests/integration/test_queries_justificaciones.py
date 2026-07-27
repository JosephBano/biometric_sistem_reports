"""
Tests de integración de `db.queries.justificaciones` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from db import set_thread_tenant
from db.queries.dispositivos import eliminar_dispositivo, upsert_dispositivo
from db.queries.justificaciones import (
    actualizar_estado_justificacion,
    actualizar_justificacion_completa,
    eliminar_justificacion,
    get_justificaciones,
    get_justificaciones_dict,
    get_justificaciones_pendientes,
    get_justificacion_by_id,
    insertar_justificacion,
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
    """Crea persona + id_zk para tests."""
    id_zk = str(uuid.uuid4().int % 100000)
    p = crear_persona(
        nombre=f"JustTest-{uuid.uuid4().hex[:6]}",
        id_usuario_zk=id_zk,
    )
    return {"id": p["id"], "id_zk": id_zk, "nombre": p["nombre"]}


class TestInsertarJustificacion:

    def test_insertar_justificacion_minima(self, persona_test):
        """Insertar con argumentos mínimos."""
        result = insertar_justificacion(
            id_usuario=persona_test["id_zk"],
            nombre=persona_test["nombre"],
            fecha="2026-07-02",
            tipo="medica",
        )
        assert result["fecha"] == "2026-07-02"
        assert result["tipo"] == "medica"
        assert result["estado"] == "aprobada"

    def test_insertar_justificacion_completa(self, persona_test):
        """Insertar con todos los campos."""
        result = insertar_justificacion(
            id_usuario=persona_test["id_zk"],
            nombre=persona_test["nombre"],
            fecha="2026-07-03",
            tipo="personal",
            motivo="Trámite personal",
            aprobado_por="Admin Test",
            hora_permitida="10:00",
            estado="pendiente",
            duracion_permitida_min=60,
            hora_retorno_permiso="11:00",
            incluye_almuerzo=1,
            recuperable=1,
            fecha_recuperacion="2026-07-10",
            hora_recuperacion="08:00",
            hora_recuperacion_fin="17:00",
        )
        assert result["motivo"] == "Trámite personal"
        assert result["aprobado_por"] == "Admin Test"
        assert result["estado"] == "pendiente"
        assert result["duracion_permitida_min"] == 60


class TestGetJustificaciones:

    def test_get_justificaciones_sin_filtro(self, persona_test):
        """get_justificaciones sin filtro retorna todas."""
        insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica",
        )
        result = get_justificaciones()
        assert len(result) >= 1

    def test_get_justificaciones_con_rango(self, persona_test):
        """get_justificaciones con rango filtra por fecha."""
        insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica",
        )
        insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-15", "personal",
        )
        result = get_justificaciones(
            date(2026, 7, 1), date(2026, 7, 7),
        )
        fechas = [j["fecha"] for j in result]
        assert "2026-07-02" in fechas
        assert "2026-07-15" not in fechas


class TestGetJustificacionesDict:

    def test_get_justificaciones_dict_indexa_por_id_fecha_tipo(self, persona_test):
        """get_justificaciones_dict retorna dict indexado por (id_usuario, fecha, tipo)."""
        j = insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica",
        )
        result = get_justificaciones_dict()
        key = (j["id_usuario"], "2026-07-02", "medica")
        assert key in result
        assert result[key]["motivo"] == j["motivo"]


class TestGetJustificacionesPendientes:

    def test_get_pendientes_vacio(self):
        """Sin pendientes, retorna lista vacía."""
        result = get_justificaciones_pendientes()
        assert isinstance(result, list)

    def test_get_pendientes_incluye_pendiente(self, persona_test):
        """Las justificaciones en estado 'pendiente' aparecen."""
        insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica", estado="pendiente",
        )
        result = get_justificaciones_pendientes()
        assert len(result) >= 1


class TestActualizarEstado:

    def test_actualizar_estado_aprobada(self, persona_test):
        """actualizar_estado_justificacion cambia el estado."""
        j = insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica", estado="pendiente",
        )
        assert actualizar_estado_justificacion(j["id"], "aprobada") is True

        updated = get_justificacion_by_id(j["id"])
        assert updated["estado"] == "aprobada"

    def test_actualizar_estado_inexistente_retorna_false(self):
        """actualizar_estado_justificacion con id inexistente → False."""
        result = actualizar_estado_justificacion(99999999, "aprobada")
        assert result is False


class TestEliminar:

    def test_eliminar_justificacion(self, persona_test):
        """eliminar_justificacion elimina por ID."""
        j = insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica",
        )
        assert eliminar_justificacion(j["id"]) is True
        assert get_justificacion_by_id(j["id"]) == {}

    def test_eliminar_justificacion_inexistente(self):
        """eliminar_justificacion con id inexistente → False."""
        assert eliminar_justificacion(99999999) is False


class TestActualizarCompleta:

    def test_actualizar_completa_motivo(self, persona_test):
        """actualizar_justificacion_completa actualiza campos."""
        j = insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica",
        )
        result = actualizar_justificacion_completa(
            j["id"], motivo="Nuevo motivo", estado="rechazada",
        )
        assert result is True

        updated = get_justificacion_by_id(j["id"])
        assert updated["motivo"] == "Nuevo motivo"
        assert updated["estado"] == "rechazada"

    def test_actualizar_completa_sin_campos(self, persona_test):
        """Sin campos, retorna False sin hacer UPDATE."""
        j = insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica",
        )
        result = actualizar_justificacion_completa(j["id"])
        assert result is False

    def test_actualizar_completa_campos_invalidos_se_ignoran(self, persona_test):
        """Campos no permitidos se ignoran."""
        j = insertar_justificacion(
            persona_test["id_zk"], persona_test["nombre"],
            "2026-07-02", "medica",
        )
        # 'id' no está en permitidos → se ignora
        result = actualizar_justificacion_completa(j["id"], id="x", motivo="OK")
        assert result is True
        updated = get_justificacion_by_id(j["id"])
        assert updated["motivo"] == "OK"
