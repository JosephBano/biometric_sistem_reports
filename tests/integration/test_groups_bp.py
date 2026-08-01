"""
Tests de integración del blueprint `groups` (`app/web/groups_bp.py`).

Cubre:
  - GET /admin/grupos requiere admin
  - GET /admin/grupos con admin → 200 con JSON o HTML
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestGroupsBlueprint:

    def test_get_grupos_sin_auth(self, anonymous_client):
        """GET /admin/grupos sin sesión → redirect/401/403."""
        r = anonymous_client.get("/admin/grupos")
        assert r.status_code in (302, 401, 403)

    def test_get_admin_grupos_con_admin(self, admin_client):
        """GET /admin/grupos → 200 con JSON o HTML."""
        r = admin_client.get("/admin/grupos")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, (dict, list))
