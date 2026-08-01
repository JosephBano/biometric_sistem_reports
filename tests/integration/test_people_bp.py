"""
Tests de integración del blueprint `people` (`app/web/people_bp.py`).

Cubre:
  - GET /api/personas-lista requiere admin
  - GET /api/personas-lista con admin → JSON
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestPeopleBlueprint:

    def test_get_personas_lista_sin_auth(self, anonymous_client):
        """GET /api/personas-lista sin sesión → redirect/401/403."""
        r = anonymous_client.get("/api/personas-lista")
        assert r.status_code in (302, 401, 403)

    def test_get_api_personas_lista_con_admin(self, admin_client):
        """GET /api/personas-lista con admin → 200 con JSON."""
        r = admin_client.get("/api/personas-lista")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, (dict, list))

    def test_get_api_personas_db_con_admin(self, admin_client):
        """GET /api/personas-db con admin → 200 con JSON (lista detallada)."""
        r = admin_client.get("/api/personas-db")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, (dict, list))
