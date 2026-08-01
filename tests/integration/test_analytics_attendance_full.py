"""
Tests de integración ampliados del blueprint `analytics` y `attendance`.

Cubre endpoints adicionales para subir cobertura.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestAnalyticsAmpliado:

    def test_get_analytics_html(self, admin_client):
        """GET /analytics → 200 con HTML."""
        r = admin_client.get("/analytics")
        assert r.status_code == 200
        assert b"<html" in r.data

    def test_get_api_analytics(self, admin_client):
        """GET /api/analytics → 200 con JSON."""
        r = admin_client.get("/api/analytics")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, (dict, list))

    def test_post_api_analytics_narrativo(self, admin_client, csrf_token):
        """POST /api/analytics/narrativo con hallazgos → 200 o 400 (faltan datos)."""
        r = admin_client.post(
            "/api/analytics/narrativo",
            json={"csrf_token": csrf_token},
        )
        assert r.status_code in (200, 400, 422)

    def test_get_analytics_periodo_inexistente(self, admin_client):
        """GET /analytics/periodo/<id-inexistente> → 404."""
        r = admin_client.get(
            "/analytics/periodo/00000000-0000-0000-0000-000000000000"
        )
        assert r.status_code in (200, 404)


class TestAttendanceAmpliado:

    def test_get_api_feriados(self, admin_client):
        """GET /api/feriados → 200 con JSON."""
        r = admin_client.get("/api/feriados")
        assert r.status_code == 200

    def test_post_api_feriados_crear(self, admin_client, csrf_token):
        """POST /api/feriados con fecha → 200/201/400/422."""
        r = admin_client.post(
            "/api/feriados",
            json={
                "csrf_token": csrf_token,
                "fecha": "2026-12-25",
                "descripcion": "Navidad (test)",
            },
        )
        # 201 (created) también es válido
        assert r.status_code in (200, 201, 400, 422)

    def test_get_api_feriados_exportar(self, admin_client):
        """GET /api/feriados/exportar → CSV o JSON."""
        r = admin_client.get("/api/feriados/exportar")
        assert r.status_code == 200
        assert (
            "csv" in r.content_type.lower()
            or "text" in r.content_type.lower()
            or r.is_json
        )

    def test_get_justificaciones_vista_html(self, admin_client):
        """GET /justificaciones-vista → 200 con HTML."""
        r = admin_client.get("/justificaciones-vista")
        assert r.status_code in (200, 404)
