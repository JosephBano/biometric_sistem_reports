"""
Tests de la factory de drivers (`drivers/__init__.py`).

Motivación (regresión 2026-07-28): tras la Fase 4e del ADR-0001 el módulo
top-level `auth.py` se movió a `app/domain/auth.py`, pero
`drivers/zk_driver.py` y `drivers/hikvision_driver.py` conservaron
`from auth import decrypt_device_password` dentro de `__init__`. Como los
drivers solo se instancian cuando hay un dispositivo activo real, ningún
test lo ejercitaba y el `ModuleNotFoundError` solo aparecía en producción
(500 en `/api/estado-sync` y `/api/dispositivos/<id>/test`).

Estos tests instancian los drivers para que el import se ejecute.
"""
from __future__ import annotations

import pytest

from app.domain.auth import encrypt_device_password
from drivers import get_driver
from drivers.hikvision_driver import HikvisionDriver
from drivers.zk_driver import ZKDriver


def _dispositivo(tipo_driver: str, password_enc: str | None = None) -> dict:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "nombre": f"Test-{tipo_driver}",
        "ip": "192.168.1.100",
        "puerto": 4370,
        "protocolo": "TCP",
        "tipo_driver": tipo_driver,
        "timeout_seg": 30,
        "password_enc": password_enc,
    }


class TestGetDriver:

    @pytest.mark.parametrize(
        ("tipo", "esperado"),
        [("zk", ZKDriver), ("hikvision", HikvisionDriver)],
    )
    def test_retorna_el_driver_del_tipo(self, tipo, esperado):
        assert isinstance(get_driver(_dispositivo(tipo)), esperado)

    def test_tipo_desconocido_cae_a_zk(self):
        assert isinstance(get_driver(_dispositivo("marca_inexistente")), ZKDriver)


class TestPasswordDelDispositivo:
    """Ejercita la rama que importa `decrypt_device_password`.

    Sin `password_enc` el import no llega a usarse, pero sí se ejecuta:
    basta con instanciar para detectar un módulo inexistente.
    """

    def test_sin_password_enc_usa_default(self):
        assert get_driver(_dispositivo("zk", password_enc=None)).password == 0

    def test_zk_desencripta_el_password(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "clave-de-prueba-para-tests-1234567890")
        driver = get_driver(_dispositivo("zk", encrypt_device_password("1234")))
        assert driver.password == 1234

    def test_hikvision_desencripta_el_password(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "clave-de-prueba-para-tests-1234567890")
        driver = get_driver(
            _dispositivo("hikvision", encrypt_device_password("s3cr3t"))
        )
        assert driver.password == "s3cr3t"
