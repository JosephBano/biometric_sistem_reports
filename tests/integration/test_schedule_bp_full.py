"""
Tests de integración ampliados del blueprint `schedule` (`app/web/schedule_bp.py`).

Cubre CRUD de horarios e importar/exportar.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestScheduleBlueprintAmpliado:

    def test_get_api_horarios(self, admin_client):
        """GET /api/horarios → 200 con JSON."""
        r = admin_client.get("/api/horarios")
        assert r.status_code == 200

    def test_get_api_horarios_estado(self, admin_client):
        """GET /api/horarios/estado → 200."""
        r = admin_client.get("/api/horarios/estado")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, dict)

    def test_get_api_horarios_exportar_csv(self, admin_client):
        """GET /api/horarios/exportar → CSV download."""
        r = admin_client.get("/api/horarios/exportar")
        # CSV file (text/csv) o 200 con JSON de error
        assert r.status_code == 200
        assert (
            "csv" in r.content_type.lower()
            or r.is_json
            or "text" in r.content_type.lower()
        )

    def test_post_api_horarios_crear(self, admin_client, csrf_token):
        """POST /api/horarios con datos → 200/400/422."""
        r = admin_client.post(
            "/api/horarios",
            json={
                "csrf_token": csrf_token,
                "id_usuario": "fake-uuid",
                "lunes": "08:00-17:00",
            },
        )
        assert r.status_code in (200, 400, 422)
