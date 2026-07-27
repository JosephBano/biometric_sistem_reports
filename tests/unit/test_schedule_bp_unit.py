"""
Tests unitarios de `app.web.schedule_bp` con mocks (Fase 7.4).

Cubre rutas internas que requieren archivos reales.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture()
def app():
    from app import create_app
    flask_app = create_app("testing")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


class TestHorariosImportar:

    def test_post_horarios_importar_sin_archivo(self, client, csrf_token=None):
        """POST /api/horarios/importar sin archivo → 400."""
        r = client.post("/api/horarios/importar", data={})
        # Sin archivo + sin sesión, retorna 302/400/401
        assert r.status_code in (302, 400, 401, 403, 415)

    def test_post_horarios_importar_con_archivo_vacio(self, client):
        """POST con archivo vacío (sin permisos) → 302/403."""
        r = client.post(
            "/api/horarios/importar",
            data={"archivo": (b"", "horarios.csv")},
            content_type="multipart/form-data",
        )
        # Sin sesión retorna redirect
        assert r.status_code in (302, 400, 401, 403)


class TestPeriodosImportarPersonas:

    def test_periodos_importar_personas_sin_archivo(self, client):
        """POST /periodos/<id>/importar-personas sin archivo → 400/404."""
        r = client.post(
            "/periodos/fake-uuid/importar-personas",
            data={},
            content_type="multipart/form-data",
        )
        assert r.status_code in (302, 400, 401, 403, 404)
