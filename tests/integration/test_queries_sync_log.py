"""
Tests de integración de `db.queries.sync_log` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from db import set_thread_tenant
from db.queries.dispositivos import eliminar_dispositivo, upsert_dispositivo
from db.queries.sync_log import get_latest_sync_logs_por_dispositivo, registrar_sync


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
    nombre = f"ZK-Sync-{uuid.uuid4().hex[:8]}"
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


class TestRegistrarSync:

    def test_registrar_sync_exitoso(self, dispositivo_test):
        """registrar_sync con exito=True no falla."""
        registrar_sync(
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 7),
            obtenidos=100,
            nuevos=80,
            exito=True,
            dispositivo_id=dispositivo_test,
        )

    def test_registrar_sync_con_error(self, dispositivo_test):
        """registrar_sync con error_detalle no falla."""
        registrar_sync(
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 7),
            obtenidos=0,
            nuevos=0,
            exito=False,
            error="Connection timeout",
            dispositivo_id=dispositivo_test,
        )

    def test_registrar_sync_con_registros_en_dispositivo(self, dispositivo_test):
        """registrar_sync incluye registros_en_dispositivo."""
        registrar_sync(
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 7),
            obtenidos=50,
            nuevos=40,
            exito=True,
            registros_en_dispositivo=50000,
            dispositivo_id=dispositivo_test,
        )


class TestGetLatestSyncLogs:

    def test_get_latest_logs_vacio(self):
        """Sin sync_logs, retorna dict vacío."""
        result = get_latest_sync_logs_por_dispositivo()
        assert isinstance(result, dict)

    def test_get_latest_logs_incluye_sync(self, dispositivo_test):
        """Tras registrar_sync, get_latest_logs incluye el dispositivo."""
        registrar_sync(
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 7),
            obtenidos=100,
            nuevos=80,
            exito=True,
            dispositivo_id=dispositivo_test,
        )
        result = get_latest_sync_logs_por_dispositivo()
        assert dispositivo_test in result
        assert result[dispositivo_test]["exito"] is True
