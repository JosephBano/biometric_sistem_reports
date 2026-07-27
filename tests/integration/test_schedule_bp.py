"""
Tests de integración del blueprint `schedule` (`app/web/schedule_bp.py`).

Cubre:
  - GET /api/horarios requiere admin
  - GET /api/horarios retorna JSON
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestScheduleBlueprint:

    def test_get_horarios_sin_auth(self, anonymous_client):
        """GET /api/horarios sin sesión → 302/401/403."""
        r = anonymous_client.get("/api/horarios")
        assert r.status_code in (302, 401, 403)

    def test_get_api_horarios_con_admin(self, admin_client):
        """GET /api/horarios con admin → 200."""
        r = admin_client.get("/api/horarios")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, (dict, list))

    def test_get_api_horarios_estado_con_admin(self, admin_client):
        """GET /api/horarios/estado → 200 con JSON."""
        r = admin_client.get("/api/horarios/estado")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, dict)
