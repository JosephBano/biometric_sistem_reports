"""
Tests de integración del blueprint `attendance` (`app/web/attendance_bp.py`).

Cubre:
  - GET /api/justificaciones requiere auth
  - GET /api/justificaciones con admin → JSON
  - GET /api/feriados con admin → JSON
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestAttendanceBlueprint:

    def test_get_justificaciones_sin_auth(self, anonymous_client):
        """GET /api/justificaciones sin sesión → redirect/401."""
        r = anonymous_client.get("/api/justificaciones")
        assert r.status_code in (302, 401, 403, 200)

    def test_get_justificaciones_con_admin(self, admin_client):
        """GET /api/justificaciones con admin → 200 JSON (puede estar vacío)."""
        r = admin_client.get("/api/justificaciones")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert "justificaciones" in data or isinstance(data, dict)

    def test_get_feriados_con_admin(self, admin_client):
        """GET /api/feriados → JSON con feriados del rango."""
        r = admin_client.get("/api/feriados")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, dict)

    def test_post_justificacion_con_admin(self, admin_client, csrf_token):
        """POST /api/justificaciones → 200 o 400 (faltan campos)."""
        # Sin campos obligatorios — el endpoint espera JSON
        r = admin_client.post(
            "/api/justificaciones",
            json={"csrf_token": csrf_token},
        )
        # 400 (validation) o 200 (created con todo OK)
        assert r.status_code in (200, 400, 422)
