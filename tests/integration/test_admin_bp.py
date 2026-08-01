"""
Tests de integración del blueprint `admin` (`app/web/admin_bp.py`).

Cubre:
  - GET /admin/usuarios requiere superadmin
  - GET /admin/tenants con admin → 200
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestAdminBlueprint:

    def test_get_admin_usuarios_sin_auth(self, anonymous_client):
        """GET /admin/usuarios sin sesión → redirect/401/403."""
        r = anonymous_client.get("/admin/usuarios")
        assert r.status_code in (302, 401, 403)

    def test_get_admin_tenants_con_admin(self, admin_client):
        """GET /admin/tenants con admin → 200."""
        r = admin_client.get("/admin/tenants")
        assert r.status_code == 200
        assert b"<html" in r.data or r.is_json

    def test_get_admin_grupos_con_admin(self, admin_client):
        """GET /admin/grupos con admin → 200."""
        r = admin_client.get("/admin/grupos")
        assert r.status_code == 200
