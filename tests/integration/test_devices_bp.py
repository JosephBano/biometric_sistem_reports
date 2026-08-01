"""
Tests de integración del blueprint `devices` (`app/web/devices_bp.py`).

Cubre:
  - GET /api/dispositivos requiere admin
  - GET /api/dispositivos retorna JSON con lista
  - GET /api/sync/estado retorna estado del scheduler
  - POST /api/sync/ejecutar dispara sync
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestDevicesBlueprint:

    def test_get_api_dispositivos_sin_auth_redirige(self, anonymous_client):
        """GET /api/dispositivos sin sesión → 401/403/302."""
        r = anonymous_client.get("/api/dispositivos")
        assert r.status_code in (302, 401, 403)

    def test_get_api_dispositivos_con_admin_retorna_json(self, admin_client):
        """GET /api/dispositivos con admin → 200 con JSON (lista vacía OK)."""
        r = admin_client.get("/api/dispositivos")
        assert r.status_code == 200
        # JSON o HTML acceptable si no hay dispositivos
        assert r.is_json or r.content_type.startswith("application/json")

    def test_get_api_sync_estado_con_admin(self, admin_client):
        """GET /api/sync/estado → 200 con JSON de estado."""
        r = admin_client.get("/api/sync/estado")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            # El endpoint expone campos conocidos (ver docs/API.md Fase 1+2)
            assert isinstance(data, dict)

    def test_post_api_sync_ejecutar_con_admin(self, admin_client, csrf_token):
        """POST /api/sync/ejecutar → 200 (sin dispositivos = no-op) o 4xx."""
        r = admin_client.post(
            "/api/sync/ejecutar",
            data={"csrf_token": csrf_token},
            content_type="multipart/form-data",
        )
        # Sin dispositivos, el sync retorna 200 con 'no devices' o 400
        assert r.status_code in (200, 400, 404)
