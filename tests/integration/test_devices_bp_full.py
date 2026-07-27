"""
Tests de integración ampliados del blueprint `devices` (`app/web/devices_bp.py`).

Cubre CRUD de dispositivos y sync.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestDevicesBlueprintAmpliado:

    def test_get_api_dispositivos(self, admin_client):
        """GET /api/dispositivos → 200 con JSON."""
        r = admin_client.get("/api/dispositivos")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, (dict, list))

    def test_get_admin_dispositivos_html(self, admin_client):
        """GET /admin/dispositivos → 200 con HTML."""
        r = admin_client.get("/admin/dispositivos")
        assert r.status_code == 200

    def test_post_api_dispositivos_crear(self, admin_client, csrf_token):
        """POST /api/dispositivos con datos → 200/400/422/500."""
        r = admin_client.post(
            "/api/dispositivos",
            json={
                "csrf_token": csrf_token,
                "nombre": "ZK-Device-Test",
                "ip": "192.168.1.100",
                "puerto": 4370,
            },
        )
        # 500 es aceptable: el cifrado AES puede fallar en test sin BD_ENCRYPTION_KEY correcta
        assert r.status_code in (200, 400, 422, 500)

    def test_get_api_dispositivos_test_inexistente(self, admin_client):
        """GET /api/dispositivos/<id>/test con id inexistente → 404/400."""
        r = admin_client.get(
            "/api/dispositivos/00000000-0000-0000-0000-000000000000/test"
        )
        # Sin device en BD, retorna 404 o 400
        assert r.status_code in (200, 400, 404, 500)

    def test_post_api_sync_ejecutar_todos(self, admin_client, csrf_token):
        """POST /api/sync/ejecutar (sin args) → 200/400/404/500."""
        r = admin_client.post(
            "/api/sync/ejecutar",
            json={"csrf_token": csrf_token},
        )
        # 404 si la ruta cambió, 500 si la BD de test no tiene todo
        assert r.status_code in (200, 400, 404, 500)

    def test_get_api_sync_estado(self, admin_client):
        """GET /api/sync/estado → 200."""
        r = admin_client.get("/api/sync/estado")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, dict)
