"""
Tests de integración ampliados: schedules, grupos, attendance CRUD.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestScheduleEndpoints:

    def test_get_api_horarios(self, admin_client):
        """GET /api/horarios → 200."""
        r = admin_client.get("/api/horarios")
        assert r.status_code == 200

    def test_get_api_horarios_estado(self, admin_client):
        """GET /api/horarios/estado → 200."""
        r = admin_client.get("/api/horarios/estado")
        assert r.status_code == 200

    def test_get_api_horarios_exportar(self, admin_client):
        """GET /api/horarios/exportar → 200."""
        r = admin_client.get("/api/horarios/exportar")
        assert r.status_code == 200

    def test_post_api_horarios(self, admin_client, csrf_token):
        """POST /api/horarios → 200/400/422/403."""
        r = admin_client.post(
            "/api/horarios",
            json={
                "csrf_token": csrf_token,
                "id_usuario": "fake-uuid",
                "lunes": "08:00",
            },
        )
        assert r.status_code in (200, 201, 400, 403, 422)

    def test_put_api_horarios(self, admin_client, csrf_token):
        """PUT /api/horarios/<id> → 200/400/403/404."""
        r = admin_client.put(
            "/api/horarios/fake-uuid",
            json={"csrf_token": csrf_token, "lunes": "09:00"},
        )
        assert r.status_code in (200, 400, 403, 404)

    def test_delete_api_horarios(self, admin_client, csrf_token):
        """DELETE /api/horarios/<id> → 200/400/403/404."""
        r = admin_client.delete(
            "/api/horarios/fake-uuid",
            json={"csrf_token": csrf_token},
        )
        assert r.status_code in (200, 400, 403, 404)


class TestAttendanceEndpoints:

    def test_get_justificaciones(self, admin_client):
        """GET /api/justificaciones → 200."""
        r = admin_client.get("/api/justificaciones")
        assert r.status_code == 200

    def test_post_justificaciones_sin_datos(self, admin_client, csrf_token):
        """POST /api/justificaciones sin datos → 400/403/422."""
        r = admin_client.post(
            "/api/justificaciones",
            json={"csrf_token": csrf_token},
        )
        assert r.status_code in (400, 403, 422)

    def test_get_feriados(self, admin_client):
        """GET /api/feriados → 200."""
        r = admin_client.get("/api/feriados")
        assert r.status_code == 200

    def test_get_feriados_exportar(self, admin_client):
        """GET /api/feriados/exportar → 200 CSV."""
        r = admin_client.get("/api/feriados/exportar")
        assert r.status_code == 200

    def test_post_feriados(self, admin_client, csrf_token):
        """POST /api/feriados con datos → 200/201/400/403/422."""
        r = admin_client.post(
            "/api/feriados",
            json={
                "csrf_token": csrf_token,
                "fecha": "2026-12-25",
                "descripcion": "Navidad test",
            },
        )
        assert r.status_code in (200, 201, 400, 403, 422)


class TestGroupsEndpoints:

    def test_get_admin_grupos(self, admin_client):
        """GET /admin/grupos → 200."""
        r = admin_client.get("/admin/grupos")
        assert r.status_code == 200

    def test_post_grupos_crear(self, admin_client, csrf_token):
        """POST /admin/grupos → 200/201/400/403/422."""
        r = admin_client.post(
            "/admin/grupos",
            json={
                "csrf_token": csrf_token,
                "nombre": "Grupo Test",
            },
        )
        assert r.status_code in (200, 201, 400, 403, 422)

    def test_post_grupos_actualizar(self, admin_client, csrf_token):
        """POST /admin/grupos/<id> → 200/400/403/404."""
        r = admin_client.post(
            "/admin/grupos/fake-uuid",
            json={"csrf_token": csrf_token, "nombre": "Updated"},
        )
        assert r.status_code in (200, 400, 403, 404)

    def test_get_admin_grupos_funcionales(self, admin_client):
        """GET /admin/grupos-funcionales → 200."""
        r = admin_client.get("/admin/grupos-funcionales")
        assert r.status_code == 200

    def test_post_grupos_funcionales_crear(self, admin_client, csrf_token):
        """POST /admin/grupos-funcionales → 200/201/400/403/422."""
        r = admin_client.post(
            "/admin/grupos-funcionales",
            json={
                "csrf_token": csrf_token,
                "nombre": "Grupo Funcional Test",
            },
        )
        assert r.status_code in (200, 201, 400, 403, 422)
