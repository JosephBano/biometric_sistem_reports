"""
Tests del endpoint GET /api/scheduler/estado (`app.web.system_bp`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest


# Mockeamos las llamadas a BD del `before_request cargar_contexto_usuario`
# para evitar tocar la BD real en tests.
@pytest.fixture(autouse=True)
def _mock_tenant_loader(monkeypatch):
    """Parcha db.get_tenant_by_slug y db.get_tipos_persona para tests aislados."""
    import db as db_module
    monkeypatch.setattr(
        db_module,
        "get_tenant_by_slug",
        lambda slug: {"id": "t-1", "slug": slug, "activo": True, "nombre": "Test"},
    )
    monkeypatch.setattr(
        db_module,
        "get_tipos_persona",
        lambda schema=None: [{"id": "tp-1", "nombre": "Empleado"}],
    )


class TestSchedulerEstado:

    def test_endpoint_requiere_autenticacion(self, client):
        """Sin sesión → 401 (JSON)."""
        resp = client.get("/api/scheduler/estado")
        assert resp.status_code == 401
        assert resp.is_json

    def test_endpoint_requiere_rol_admin_o_superior(self, client):
        """Sesión sin rol suficiente → 403."""
        with client.session_transaction() as sess:
            sess["usuario_id"] = "u"
            sess["tenant_schema"] = "istpet"
            sess["tenant_id"] = "t"
            sess["nombre"] = "user"
            sess["roles"] = ["readonly"]  # NO es admin
            sess["csrf_token"] = "x"
        resp = client.get("/api/scheduler/estado")
        assert resp.status_code == 403

    def test_endpoint_admin_devuelve_json_con_campos_esperados(self, admin_session):
        """admin → 200 + JSON con sync_activo, hora_nocturna, ultimas_corridas, etc."""
        with patch("db.queries.scheduler_runs.listar_ultimos", return_value=[]):
            resp = admin_session.get("/api/scheduler/estado")

        assert resp.status_code == 200
        data = resp.get_json()
        assert "sync_activo" in data
        assert "sync_hora_nocturna" in data
        assert "sync_intervalo_horas" in data
        assert "ultimas_corridas" in data
        assert isinstance(data["ultimas_corridas"], list)

    def test_endpoint_incluye_corridas_en_ultimas_corridas(self, admin_session):
        """Si hay corridas en BD, deben venir en el JSON."""
        corrida_mock = {
            "id": 1,
            "job": "sync_incremental",
            "tenant_slug": "istpet",
            "inicio": "2026-07-02T10:00:00+00:00",
            "fin": "2026-07-02T10:05:00+00:00",
            "ok": True,
            "descargados": 10,
            "insertados": 8,
            "detalle": None,
        }
        with patch(
            "db.queries.scheduler_runs.listar_ultimos",
            return_value=[corrida_mock],
        ):
            resp = admin_session.get("/api/scheduler/estado")

        data = resp.get_json()
        assert len(data["ultimas_corridas"]) == 1
        assert data["ultimas_corridas"][0]["job"] == "sync_incremental"

    def test_endpoint_serializa_datetimes_a_iso(self, admin_session):
        """Datetimes en filas vienen como ISO string (no objetos)."""
        corrida_mock = {
            "id": 1,
            "job": "sync_incremental",
            "tenant_slug": "istpet",
            "inicio": datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
            "fin": datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
            "ok": True,
            "descargados": 10,
            "insertados": 8,
            "detalle": None,
        }
        with patch(
            "db.queries.scheduler_runs.listar_ultimos",
            return_value=[corrida_mock],
        ):
            resp = admin_session.get("/api/scheduler/estado")

        data = resp.get_json()
        inicio_str = data["ultimas_corridas"][0]["inicio"]
        assert isinstance(inicio_str, str)
        assert "2026-07-02" in inicio_str

    def test_endpoint_no_falla_si_listar_ultimos_explota(self, admin_session):
        """Si la BD falla al listar corridas, devuelve ultimas_corridas=[]."""
        with patch(
            "db.queries.scheduler_runs.listar_ultimos",
            side_effect=RuntimeError("BD caída"),
        ):
            resp = admin_session.get("/api/scheduler/estado")

        # No debe propagar el error; responde 200 con lista vacía
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ultimas_corridas"] == []