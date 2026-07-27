"""
Tests de integración del blueprint `breaks` (`app/web/breaks_bp.py`).

Cubre:
  - POST /api/categorizar-break requiere rol gestor+
  - POST /api/categorizar-break con datos inválidos → 400
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestBreaksBlueprint:

    def test_categorizar_break_sin_auth(self, anonymous_client, csrf_token):
        """POST /api/categorizar-break sin sesión → 401/403."""
        r = anonymous_client.post(
            "/api/categorizar-break",
            data={"csrf_token": csrf_token},
            content_type="multipart/form-data",
        )
        assert r.status_code in (302, 401, 403)

    def test_categorizar_break_sin_campos_obligatorios(self, admin_client, csrf_token):
        """POST /api/categorizar-break sin campos → 400."""
        r = admin_client.post(
            "/api/categorizar-break",
            json={"csrf_token": csrf_token},
        )
        assert r.status_code == 400

    def test_categorizar_break_categoria_invalida(self, admin_client, csrf_token):
        """POST con categoría inválida → 400."""
        r = admin_client.post(
            "/api/categorizar-break",
            json={
                "csrf_token": csrf_token,
                "id_usuario": "fake-id",
                "fecha": "2026-07-02",
                "hora_inicio": "10:00",
                "hora_fin": "11:00",
                "categoria": "invalida",
            },
        )
        assert r.status_code == 400
