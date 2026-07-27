"""
Tests de integración del blueprint `periods` (`app/web/periods_bp.py`).

Cubre:
  - GET /periodos requiere admin
  - GET /periodos con admin → 200
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestPeriodsBlueprint:

    def test_get_periodos_sin_auth(self, anonymous_client):
        """GET /periodos sin sesión → redirect/401/403."""
        r = anonymous_client.get("/periodos")
        assert r.status_code in (302, 401, 403)

    def test_get_periodos_con_admin(self, admin_client):
        """GET /periodos con admin → 200."""
        r = admin_client.get("/periodos")
        assert r.status_code == 200
        assert b"<html" in r.data or r.is_json
