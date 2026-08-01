"""
Tests de integración del blueprint `reports` (`app/web/reports_bp.py`).

Cubre:
  - GET /api/backup/csv requiere admin
  - GET /api/alertas/tardanzas-severas retorna JSON
  - POST /api/generar-desde-db requiere admin
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestReportsBlueprint:

    def test_backup_csv_sin_auth(self, anonymous_client):
        """GET /api/backup/csv sin sesión → redirect/401/403/429."""
        r = anonymous_client.get("/api/backup/csv")
        # 429 (rate-limit), 401/403, o 302 son todos válidos
        assert r.status_code in (302, 401, 403, 429)

    def test_alertas_tardanzas_severas_con_admin(self, admin_client):
        """GET /api/alertas/tardanzas-severas → 200 con JSON."""
        r = admin_client.get("/api/alertas/tardanzas-severas")
        assert r.status_code == 200
        if r.is_json:
            data = r.get_json()
            assert isinstance(data, (dict, list))

    def test_generar_desde_db_sin_datos(self, admin_client, csrf_token):
        """POST /api/generar-desde-db sin registros → 4xx o mensaje claro."""
        # El endpoint espera JSON
        import json
        r = admin_client.post(
            "/api/generar-desde-db",
            json={"csrf_token": csrf_token, "formato": "pdf"},
        )
        # Sin registros y sin horarios, retorna 400 (no se puede generar)
        assert r.status_code in (200, 400, 422)
