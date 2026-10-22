"""
Tests de integración del blueprint `periods` (`app/web/periods_bp.py`).

Cubre:
  - GET /periodos requiere admin
  - GET /periodos con admin → 200
  - POST /periodos/<id>/agregar-manual (existentes y nueva)
  - POST /periodos/<id>/remover-persona/<persona_id>
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from db.queries.periodos import crear_periodo
from db.queries.personas_crud import crear_persona

pytestmark = pytest.mark.integration


class TestPeriodsBlueprint:

    def test_get_periodos_sin_auth(self, anonymous_client):
        """GET /periodos sin sesión → redirect/401/403."""
        r = anonymous_client.get("/periodos")
        assert r.status_code in (302, 401, 403)

    def test_get_periodos_con_admin(self, admin_client):
        """GET /periodos con admin → 200."""
        r = admin_client.get("/periodos")
        assert r.status_code == 200
        assert b"<html" in r.data or r.is_json

    def test_agregar_manual_existentes(self, admin_client):
        """POST /periodos/<id>/agregar-manual con modo='existentes'."""
        periodo = crear_periodo(
            nombre=f"Per-{uuid.uuid4().hex[:6]}",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 1, 31),
        )
        persona = crear_persona(nombre=f"Persona {uuid.uuid4().hex[:6]}")

        r = admin_client.post(
            f"/periodos/{periodo['id']}/agregar-manual",
            data={
                "modo": "existentes",
                "personas_ids": [persona["id"]],
            },
            follow_redirects=True,
        )
        assert r.status_code == 200

    def test_agregar_manual_nueva(self, admin_client):
        """POST /periodos/<id>/agregar-manual con modo='nueva' crea y asocia persona."""
        periodo = crear_periodo(
            nombre=f"Per-{uuid.uuid4().hex[:6]}",
            fecha_inicio=date(2026, 2, 1),
            fecha_fin=date(2026, 2, 28),
        )
        nombre_persona = f"Colaborador {uuid.uuid4().hex[:6]}"

        r = admin_client.post(
            f"/periodos/{periodo['id']}/agregar-manual",
            data={
                "modo": "nueva",
                "nombre": nombre_persona,
                "identificacion": "998877",
            },
            follow_redirects=True,
        )
        assert r.status_code == 200

    def test_remover_persona_endpoint(self, admin_client):
        """POST /periodos/<id>/remover-persona/<persona_id> desvincula del período."""
        periodo = crear_periodo(
            nombre=f"Per-{uuid.uuid4().hex[:6]}",
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 3, 31),
        )
        persona = crear_persona(nombre=f"Persona {uuid.uuid4().hex[:6]}")
        # Primero agregar
        admin_client.post(
            f"/periodos/{periodo['id']}/agregar-manual",
            data={"modo": "existentes", "personas_ids": [persona["id"]]},
            follow_redirects=True,
        )

        # Luego remover
        r = admin_client.post(
            f"/periodos/{periodo['id']}/remover-persona/{persona['id']}",
            follow_redirects=True,
        )
        assert r.status_code == 200
