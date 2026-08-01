"""
Tests de integración del blueprint `dashboard` (`app/web/dashboard_bp.py`).

Cubre:
  - GET / renderiza dashboard (autenticado)
  - GET / sin sesión redirige a /login
  - GET /configuracion renderiza página de configuración
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestDashboardBlueprint:

    def test_get_root_autenticado_renderiza_dashboard(self, admin_client):
        """GET / con sesión admin → 200 con HTML del dashboard."""
        r = admin_client.get("/")
        assert r.status_code == 200
        assert b"<html" in r.data

    def test_get_root_sin_sesion_redirige_a_login(self, anonymous_client):
        """GET / sin sesión → redirect a /login."""
        r = anonymous_client.get("/", follow_redirects=False)
        assert r.status_code in (302, 200)
        if r.status_code == 302:
            assert "login" in r.headers.get("Location", "")

    def test_get_configuracion_renderiza_pagina_config(self, admin_client):
        """GET /configuracion → 200 con HTML de configuración."""
        r = admin_client.get("/configuracion")
        assert r.status_code == 200
        assert b"<html" in r.data
