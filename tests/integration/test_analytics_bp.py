"""
Tests de integración del blueprint `analytics` (`app/web/analytics_bp.py`).

Cubre:
  - GET /analytics requiere rol gestor+
  - GET /analytics con admin → 200
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestAnalyticsBlueprint:

    def test_get_analytics_sin_auth(self, anonymous_client):
        """GET /analytics sin sesión → redirect/401/403."""
        r = anonymous_client.get("/analytics")
        assert r.status_code in (302, 401, 403)

    def test_get_analytics_con_admin(self, admin_client):
        """GET /analytics con admin → 200 con HTML."""
        r = admin_client.get("/analytics")
        assert r.status_code == 200
        assert b"<html" in r.data
