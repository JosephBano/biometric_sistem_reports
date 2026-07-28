"""
Tests del catálogo de personas para selectores (`GET /api/personas/buscar`).

Motivación: la vista de analítica de entradas/salidas pedía al operador
escribir el UUID de la persona en un campo de texto libre. Nadie conoce
ese dato de memoria: en producción alguien escribió el ID del biométrico
("30") y el endpoint devolvió 500.

Este endpoint alimenta el selector con búsqueda por nombre, cédula o ID
del biométrico, y devuelve el UUID por detrás.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa


pytestmark = pytest.mark.integration


def _seed_persona(e, *, nombre, identificacion, zk_id):
    """Crea una persona con su vínculo al dispositivo activo."""
    pid = str(uuid.uuid4())
    with e.connect() as c:
        dev = c.execute(sa.text(
            "SELECT id::text FROM istpet.dispositivos WHERE activo = true "
            "ORDER BY creado_en LIMIT 1"
        )).fetchone()
        if dev is None:
            dev_id = str(uuid.uuid4())
            c.execute(sa.text(
                "INSERT INTO istpet.dispositivos "
                "(id, nombre, ip, puerto, tipo_driver, protocolo, activo, prioridad) "
                "VALUES (CAST(:id AS uuid), 'D', '127.0.0.1', 4370, 'zk', 'tcp', true, 1)"
            ), {"id": dev_id})
        else:
            dev_id = dev[0]

        c.execute(sa.text(
            "INSERT INTO istpet.personas (id, nombre, identificacion, activo) "
            "VALUES (CAST(:id AS uuid), :n, :ci, true)"
        ), {"id": pid, "n": nombre, "ci": identificacion})
        c.execute(sa.text(
            "INSERT INTO istpet.personas_dispositivos "
            "(persona_id, dispositivo_id, id_en_dispositivo, es_principal, activo) "
            "VALUES (CAST(:p AS uuid), CAST(:d AS uuid), :zk, true, true)"
        ), {"p": pid, "d": dev_id, "zk": zk_id})
        c.commit()
    return pid


@pytest.fixture()
def persona_buscable(app, tenant_id):
    from db.connection import get_engine

    sufijo = uuid.uuid4().hex[:8]
    datos = {
        "nombre": f"Zoraida Buscable {sufijo}",
        "identificacion": f"CI{sufijo}",
        "zk_id": str(uuid.uuid4().int % 900000 + 100000),
    }
    datos["id"] = _seed_persona(get_engine(), **datos)
    return datos


class TestBuscarPersonas:

    def test_devuelve_uuid_y_datos_buscables(self, admin_client, persona_buscable):
        r = admin_client.get("/api/personas/buscar")
        assert r.status_code == 200
        personas = r.get_json()["personas"]

        match = [p for p in personas if p["id"] == persona_buscable["id"]]
        assert match, "La persona sembrada no aparece en el catálogo."
        p = match[0]
        # El selector necesita el UUID para enviarlo, y los tres campos
        # por los que el operador sabe buscar.
        assert p["nombre"] == persona_buscable["nombre"]
        assert p["identificacion"] == persona_buscable["identificacion"]
        assert p["id_usuario_zk"] == persona_buscable["zk_id"]

    def test_busca_por_nombre(self, admin_client, persona_buscable):
        r = admin_client.get("/api/personas/buscar?q=Zoraida")
        assert r.status_code == 200
        ids = [p["id"] for p in r.get_json()["personas"]]
        assert persona_buscable["id"] in ids

    def test_busca_por_identificacion(self, admin_client, persona_buscable):
        r = admin_client.get(
            f"/api/personas/buscar?q={persona_buscable['identificacion']}"
        )
        assert r.status_code == 200
        ids = [p["id"] for p in r.get_json()["personas"]]
        assert persona_buscable["id"] in ids

    def test_busca_por_id_del_biometrico(self, admin_client, persona_buscable):
        """El caso que motivó el cambio: buscar con el ID del ZK."""
        r = admin_client.get(
            f"/api/personas/buscar?q={persona_buscable['zk_id']}"
        )
        assert r.status_code == 200
        ids = [p["id"] for p in r.get_json()["personas"]]
        assert persona_buscable["id"] in ids, (
            "Buscar por ID del biométrico no encontró a la persona."
        )

    def test_busqueda_sin_coincidencias_devuelve_lista_vacia(self, admin_client):
        r = admin_client.get("/api/personas/buscar?q=zzz-no-existe-zzz")
        assert r.status_code == 200
        assert r.get_json()["personas"] == []

    def test_requiere_autenticacion(self, client):
        r = client.get("/api/personas/buscar")
        assert r.status_code in (401, 302)


class TestFlujoCompletoSelector:
    """El UUID que entrega el selector debe servir para consultar."""

    def test_el_uuid_del_selector_sirve_para_entradas_salidas(
        self, admin_client, persona_buscable,
    ):
        r = admin_client.get(
            f"/api/personas/buscar?q={persona_buscable['zk_id']}"
        )
        persona = r.get_json()["personas"][0]

        r2 = admin_client.get(
            "/api/analytics/entradas-salidas"
            f"?persona_id={persona['id']}"
            "&fecha_inicio=2025-07-01&fecha_fin=2025-07-31"
        )
        assert r2.status_code == 200, (
            f"El UUID del selector fue rechazado: {r2.get_data(as_text=True)[:300]}"
        )
