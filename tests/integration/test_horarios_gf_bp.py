"""
Tests de integración del blueprint `horarios_gf` (`app/web/horarios_gf_bp.py`).

Cubre:
  - GET /admin/horarios-grupo-funcional (requiere admin)
  - POST /admin/horarios-grupo-funcional/<id>/personas/asignar
  - POST /admin/horarios-grupo-funcional/<id>/personas/crear
  - POST /admin/personas/<id>/grupo-funcional/cerrar
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from db.queries.grupos import crear_grupo_funcional
from db.queries.personas_crud import crear_persona
from db.queries.tenants import insertar_tipo_persona

pytestmark = pytest.mark.integration


@pytest.fixture()
def grupo_funcional_fixture():
    tipo = insertar_tipo_persona("istpet", f"tipo-hgf-{uuid.uuid4().hex[:6]}")
    gf = crear_grupo_funcional(
        nombre=f"GF-H-{uuid.uuid4().hex[:6]}",
        tipo_persona_id=tipo["id"],
    )
    return gf


class TestHorariosGFBlueprint:

    def test_vista_sin_auth(self, anonymous_client):
        """GET /admin/horarios-grupo-funcional sin sesión redirige o rechaza."""
        r = anonymous_client.get("/admin/horarios-grupo-funcional")
        assert r.status_code in (302, 401, 403)

    def test_vista_con_admin(self, admin_client):
        """GET /admin/horarios-grupo-funcional con admin retorna 200."""
        r = admin_client.get("/admin/horarios-grupo-funcional")
        assert r.status_code == 200
        assert b"<html" in r.data

    def test_asignar_personas_a_grupo_funcional(self, admin_client, grupo_funcional_fixture):
        """POST /admin/horarios-grupo-funcional/<id>/personas/asignar asocia personas."""
        p = crear_persona(nombre=f"PerGF-{uuid.uuid4().hex[:6]}")
        r = admin_client.post(
            f"/admin/horarios-grupo-funcional/{grupo_funcional_fixture['id']}/personas/asignar",
            data={
                "persona_ids": [p["id"]],
                "fecha_inicio": date.today().isoformat(),
            },
            follow_redirects=True,
        )
        assert r.status_code == 200

    def test_crear_persona_en_grupo(self, admin_client, grupo_funcional_fixture):
        """POST /admin/horarios-grupo-funcional/<id>/personas/crear crea y asocia."""
        r = admin_client.post(
            f"/admin/horarios-grupo-funcional/{grupo_funcional_fixture['id']}/personas/crear",
            data={
                "nombre": f"Nuevo En Grupo {uuid.uuid4().hex[:6]}",
                "identificacion": "88776655",
                "fecha_inicio": date.today().isoformat(),
            },
            follow_redirects=True,
        )
        assert r.status_code == 200

    def test_cerrar_persona_gf(self, admin_client, grupo_funcional_fixture):
        """POST /admin/personas/<id>/grupo-funcional/cerrar finaliza vigencia."""
        p = crear_persona(nombre=f"PerCerrar-{uuid.uuid4().hex[:6]}")
        # Asignar primero
        admin_client.post(
            f"/admin/horarios-grupo-funcional/{grupo_funcional_fixture['id']}/personas/asignar",
            data={"persona_ids": [p["id"]], "fecha_inicio": date.today().isoformat()},
            follow_redirects=True,
        )
        # Cerrar vínculo
        r = admin_client.post(
            f"/admin/personas/{p['id']}/grupo-funcional/cerrar",
            data={"grupo_funcional_id": grupo_funcional_fixture["id"]},
            follow_redirects=True,
        )
        assert r.status_code == 200
