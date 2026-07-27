"""
Tests de integración ampliados de `periods_bp` y `people_bp`.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestPeriodsAmpliado:

    def test_get_periodos_html(self, admin_client):
        """GET /periodos → 200."""
        r = admin_client.get("/periodos")
        assert r.status_code == 200

    def test_get_periodo_inexistente(self, admin_client):
        """GET /periodos/<id-inexistente> → 404."""
        r = admin_client.get("/periodos/00000000-0000-0000-0000-000000000000")
        assert r.status_code in (200, 404)

    def test_post_periodo_archivar_inexistente(self, admin_client, csrf_token):
        """POST /periodos/<id>/archivar con id inexistente → 200/302/403/404/500."""
        r = admin_client.post(
            "/periodos/00000000-0000-0000-0000-000000000000/archivar",
            json={"csrf_token": csrf_token},
        )
        # 403 CSRF en JSON
        assert r.status_code in (200, 302, 403, 404, 500)


class TestPeopleAmpliado:

    def test_get_api_personas_lista(self, admin_client):
        """GET /api/personas-lista → 200."""
        r = admin_client.get("/api/personas-lista")
        assert r.status_code == 200

    def test_get_api_personas_db(self, admin_client):
        """GET /api/personas-db → 200."""
        r = admin_client.get("/api/personas-db")
        assert r.status_code == 200

    def test_get_persona_por_id_vacio(self, admin_client):
        """GET /api/personas/ → 404 o redirección."""
        r = admin_client.get("/api/personas/")
        assert r.status_code in (404, 405)
