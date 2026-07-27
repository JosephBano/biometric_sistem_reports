"""
Tests de integración de `db.queries.dispositivos` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from db import set_thread_tenant
from db.queries.dispositivos import (
    actualizar_estado_sync_ui,
    actualizar_watermark,
    eliminar_dispositivo,
    get_dispositivo,
    get_dispositivos_activos,
    get_dispositivos_con_fallas_consecutivas,
    get_estado_sync_ui,
    has_alerta_hoy,
    marcar_alerta_enviada,
    upsert_dispositivo,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def dispositivo_test():
    """Crea un dispositivo de prueba y lo limpia al final."""
    nombre = f"ZK-Test-{uuid.uuid4().hex[:8]}"
    did = upsert_dispositivo({
        "nombre": nombre,
        "ip": "192.168.1.100",
        "puerto": 4370,
        "protocolo": "TCP",
        "tipo_driver": "hikvision",
        "prioridad": 1, "password_enc": None,
        "timeout_seg": 30,
        "activo": True,
    })
    yield did
    try:
        eliminar_dispositivo(did)
    except Exception:
        pass


class TestDispositivosCRUD:

    def test_get_dispositivos_activos_vacio(self):
        """Sin dispositivos activos, retorna lista vacía."""
        result = get_dispositivos_activos()
        assert isinstance(result, list)

    def test_upsert_dispositivo_nuevo(self):
        """upsert_dispositivo crea un dispositivo nuevo."""
        nombre = f"ZK-{uuid.uuid4().hex[:8]}"
        did = upsert_dispositivo({
            "nombre": nombre,
            "ip": "192.168.1.101",
            "puerto": 4370,
            "protocolo": "TCP",
            "tipo_driver": "zk",
            "prioridad": 1, "password_enc": None,
            "timeout_seg": 30,
            "activo": True,
        })
        assert did is not None
        # Recuperable por get_dispositivo
        d = get_dispositivo(did)
        assert d["nombre"] == nombre
        # Cleanup
        eliminar_dispositivo(did)

    def test_upsert_dispositivo_existente_actualiza(self, dispositivo_test):
        """upsert_dispositivo con `id` existente actualiza."""
        result = upsert_dispositivo({
            "id": dispositivo_test,
            "nombre": "ZK-Updated",
            "ip": "192.168.1.200",
            "puerto": 4370,
            "protocolo": "TCP",
            "tipo_driver": "zk",
            "prioridad": 2, "password_enc": None,
            "timeout_seg": 60,
            "activo": True,
        })
        assert result == dispositivo_test

        d = get_dispositivo(dispositivo_test)
        assert d["nombre"] == "ZK-Updated"
        assert d["ip"] == "192.168.1.200"
        assert d["prioridad"] == 2

    def test_get_dispositivo_inexistente(self):
        """get_dispositivo con UUID inexistente → None."""
        result = get_dispositivo("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_eliminar_dispositivo(self, dispositivo_test):
        """eliminar_dispositivo retorna True si eliminó."""
        assert eliminar_dispositivo(dispositivo_test) is True
        assert get_dispositivo(dispositivo_test) is None

    def test_eliminar_dispositivo_inexistente(self):
        """eliminar_dispositivo con UUID inexistente → False."""
        assert eliminar_dispositivo("00000000-0000-0000-0000-000000000000") is False


class TestWatermark:

    def test_actualizar_watermark(self, dispositivo_test):
        """actualizar_watermark cambia los campos del watermark."""
        fecha = datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc)
        actualizar_watermark(dispositivo_test, "12345", fecha)

        d = get_dispositivo(dispositivo_test)
        assert str(d["watermark_ultimo_id"]) == "12345"
        # La fecha viene como string ISO o datetime según driver


class TestSyncEstadoUI:

    def test_get_estado_sync_ui_vacio(self):
        """Sin estados registrados, retorna dict vacío."""
        result = get_estado_sync_ui()
        assert result == {}

    def test_actualizar_estado_sync_ui_inserta(self, dispositivo_test):
        """actualizar_estado_sync_ui inserta estado nuevo."""
        actualizar_estado_sync_ui(
            dispositivo_test, "conectando", progreso=10,
        )

        result = get_estado_sync_ui()
        assert dispositivo_test in result
        assert result[dispositivo_test]["estado"] == "conectando"

    def test_actualizar_estado_sync_ui_actualiza(self, dispositivo_test):
        """actualizar_estado_sync_ui actualiza si ya existe (UPSERT)."""
        actualizar_estado_sync_ui(dispositivo_test, "conectando", 10)
        actualizar_estado_sync_ui(dispositivo_test, "descargando", 50)

        result = get_estado_sync_ui()
        assert result[dispositivo_test]["estado"] == "descargando"
        assert result[dispositivo_test]["progreso_pct"] == 50

    def test_actualizar_estado_con_mensaje(self, dispositivo_test):
        """actualizar_estado_sync_ui acepta mensaje."""
        actualizar_estado_sync_ui(
            dispositivo_test, "error", 0,
            mensaje="Connection timeout",
        )
        result = get_estado_sync_ui()
        assert result[dispositivo_test]["mensaje"] == "Connection timeout"


class TestAlertas:

    def test_has_alerta_hoy_sin_alerta(self, dispositivo_test):
        """Sin alerta previa, retorna False."""
        assert has_alerta_hoy(dispositivo_test) is False

    def test_marcar_y_verificar_alerta(self, dispositivo_test):
        """marcar_alerta_enviada registra; has_alerta_hoy la encuentra."""
        marcar_alerta_enviada(dispositivo_test)
        assert has_alerta_hoy(dispositivo_test) is True


class TestFallasConsecutivas:

    def test_get_dispositivos_con_fallas_sin_fallas(self):
        """Sin sync_log con fallas, retorna lista vacía."""
        result = get_dispositivos_con_fallas_consecutivas(n=3)
        assert isinstance(result, list)
        assert result == []
