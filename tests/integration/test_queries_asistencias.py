"""
Tests de integración de `db.queries.asistencias` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from db import set_thread_tenant
from db.queries.asistencias import (
    consultar_asistencias,
    get_estado,
    get_personas,
    get_personas_con_id,
    insertar_asistencias,
)
from db.queries.dispositivos import eliminar_dispositivo, upsert_dispositivo
from db.queries.personas_crud import crear_persona


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def dispositivo_test():
    """Crea un dispositivo de prueba."""
    nombre = f"ZK-{uuid.uuid4().hex[:8]}"
    did = upsert_dispositivo({
        "nombre": nombre,
        "ip": "192.168.1.100",
        "puerto": 4370,
        "protocolo": "TCP",
        "tipo_driver": "zk",
        "prioridad": 1,
        "timeout_seg": 30,
        "activo": True,
        "password_enc": None,
    })
    yield did
    try:
        eliminar_dispositivo(did)
    except Exception:
        pass


@pytest.fixture()
def persona_test(tenant_id, dispositivo_test):
    """Crea una persona de prueba con id_en_dispositivo."""
    id_zk = uuid.uuid4().int % 100000
    p = crear_persona(
        nombre=f"Test-{uuid.uuid4().hex[:6]}",
        identificacion=str(uuid.uuid4().int)[:10],
        id_usuario_zk=str(id_zk),
        dispositivo_id=dispositivo_test,
    )
    yield {"id": p["id"], "id_zk": id_zk, "data": p}
    # No hay DELETE para personas; queda como dato


class TestInsertarAsistencias:

    def test_insertar_asistencias_lista_vacia(self, dispositivo_test):
        """Sin registros, retorna 0."""
        result = insertar_asistencias([], dispositivo_id=dispositivo_test)
        assert result == 0

    def test_insertar_una_asistencia(self, persona_test, dispositivo_test):
        """Insertar una asistencia retorna 1."""
        fecha_hora = datetime(2026, 7, 2, 8, 0, 0, tzinfo=timezone.utc)
        result = insertar_asistencias([{
            "id_usuario": persona_test["id_zk"],
            "fecha_hora": fecha_hora,
            "tipo": "entrada",
        }], dispositivo_id=dispositivo_test)
        assert result == 1

    def test_insertar_duplicado_no_cuenta(self, persona_test, dispositivo_test):
        """Insertar la misma asistencia 2 veces cuenta solo la primera."""
        fecha_hora = datetime(2026, 7, 2, 8, 0, 0, tzinfo=timezone.utc)
        registro = {
            "id_usuario": persona_test["id_zk"],
            "fecha_hora": fecha_hora,
            "tipo": "entrada",
        }
        r1 = insertar_asistencias([registro], dispositivo_id=dispositivo_test)
        r2 = insertar_asistencias([registro], dispositivo_id=dispositivo_test)
        assert r1 == 1
        assert r2 == 0  # ON CONFLICT DO NOTHING


class TestConsultarAsistencias:

    def test_consultar_asistencias_sin_datos(self):
        """Sin asistencias, retorna lista vacía."""
        result = consultar_asistencias(date(2020, 1, 1), date(2020, 1, 7))
        assert result == []

    def test_consultar_asistencias_con_datos(self, persona_test, dispositivo_test):
        """Consultar retorna registros insertados con formato esperado."""
        fecha_hora = datetime(2026, 7, 2, 8, 0, 0, tzinfo=timezone.utc)
        insertar_asistencias([{
            "id_usuario": persona_test["id_zk"],
            "fecha_hora": fecha_hora,
            "tipo": "entrada",
        }], dispositivo_id=dispositivo_test)

        result = consultar_asistencias(date(2026, 7, 1), date(2026, 7, 7))
        assert len(result) >= 1
        # Verifica el formato esperado por script.py
        r = result[0]
        assert "id_usuario" in r
        assert "nombre" in r
        assert "datetime" in r
        assert "fecha" in r
        assert "hora" in r
        assert "tipo" in r
        assert r["tipo"] == "entrada"


class TestGetPersonas:

    def test_get_personas_sin_datos(self):
        """Sin asistencias, retorna lista vacía."""
        result = get_personas(date(2020, 1, 1), date(2020, 1, 7))
        assert result == []

    def test_get_personas_con_datos(self, persona_test, dispositivo_test):
        """get_personas retorna nombres únicos."""
        fecha_hora = datetime(2026, 7, 2, 8, 0, 0, tzinfo=timezone.utc)
        insertar_asistencias([{
            "id_usuario": persona_test["id_zk"],
            "fecha_hora": fecha_hora,
            "tipo": "entrada",
        }], dispositivo_id=dispositivo_test)

        result = get_personas(date(2026, 7, 1), date(2026, 7, 7))
        assert persona_test["data"]["nombre"] in result


class TestGetPersonasConId:

    def test_get_personas_con_id_sin_datos(self):
        """Sin asistencias, retorna lista vacía."""
        result = get_personas_con_id(date(2020, 1, 1), date(2020, 1, 7))
        assert result == []

    def test_get_personas_con_id_retorna_id_y_nombre(self, persona_test, dispositivo_test):
        """Retorna dict con id_usuario (ZK) y nombre."""
        fecha_hora = datetime(2026, 7, 2, 8, 0, 0, tzinfo=timezone.utc)
        insertar_asistencias([{
            "id_usuario": persona_test["id_zk"],
            "fecha_hora": fecha_hora,
            "tipo": "entrada",
        }], dispositivo_id=dispositivo_test)

        result = get_personas_con_id(date(2026, 7, 1), date(2026, 7, 7))
        assert len(result) >= 1
        nombres = [r["nombre"] for r in result]
        assert persona_test["data"]["nombre"] in nombres


class TestGetEstado:

    def test_get_estado_retorna_dict(self):
        """get_estado retorna dict con total_registros y ultima_sync."""
        result = get_estado()
        assert isinstance(result, dict)
        assert "total_registros" in result
        assert "personas_en_db" in result
        assert "ultima_sync" in result
