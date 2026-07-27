"""
Tests de integración del blueprint `system` (`app/web/system_bp.py`).

Cubre:
  - GET /api/scheduler/estado requiere admin
  - GET /api/scheduler/estado con admin → JSON
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestSystemBlueprint:

    def test_get_scheduler_estado_sin_auth(self, anonymous_client):
        """GET /api/scheduler/estado sin sesión → redirect/401/403."""
        r = anonymous_client.get("/api/scheduler/estado")
        assert r.status_code in (302, 401, 403)

    def test_get_scheduler_estado_con_admin(self, admin_client):
        """GET /api/scheduler/estado con admin → 200 con JSON."""
        r = admin_client.get("/api/scheduler/estado")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, dict)
            # El endpoint expone 'proxima_corrida' y 'ultimas_corridas'
            # (ver docs/API.md)
            assert "proxima_corrida" in data or "ultimas_corridas" in data
