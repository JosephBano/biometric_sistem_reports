"""
Tests de integracion para la nueva ruta /api/analytics/entradas-salidas.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration


def _seed_basico(e):
    tipo_id = str(uuid.uuid4())
    grupo_id = str(uuid.uuid4())
    sede_id = str(uuid.uuid4())
    with e.connect() as c:
        dev_row = c.execute(sa.text(
            "SELECT id::text FROM istpet.dispositivos WHERE activo = true ORDER BY creado_en LIMIT 1"
        )).fetchone()
        if dev_row is None:
            dev_id = str(uuid.uuid4())
            c.execute(sa.text(
                "INSERT INTO istpet.dispositivos (id, nombre, ip, puerto, tipo_driver, protocolo, activo, prioridad) "
                "VALUES (CAST(:id AS uuid), 'D', '127.0.0.1', 4370, 'zk', 'tcp', true, 1)"
            ), {"id": dev_id})
        else:
            dev_id = dev_row[0]
        c.execute(sa.text("INSERT INTO istpet.sedes (id, nombre) VALUES (CAST(:id AS uuid), 'Sede')"), {"id": sede_id})
        c.execute(sa.text("INSERT INTO istpet.tipos_persona (id, nombre, activo) VALUES (CAST(:id AS uuid), 'Emp', true)"), {"id": tipo_id})
        c.execute(sa.text("INSERT INTO istpet.grupos (id, nombre, sede_id, activo) VALUES (CAST(:id AS uuid), 'G', CAST(:s AS uuid), true)"), {"id": grupo_id, "s": sede_id})
        c.commit()
    return {"tipo_id": tipo_id, "grupo_id": grupo_id, "sede_id": sede_id, "dev_id": dev_id}


def _seed_persona_con_marcaciones(e, base, n=3):
    identificacion = f"AES-{uuid.uuid4().hex[:8]}"
    pid = str(uuid.uuid4())
    zk_id = str(uuid.uuid4().int % 1000000 + 100000)
    with e.connect() as c:
        c.execute(sa.text(
            "INSERT INTO istpet.personas (id, nombre, identificacion, tipo_persona_id, grupo_id, activo) "
            "VALUES (CAST(:id AS uuid), :n, :ci, CAST(:t AS uuid), CAST(:g AS uuid), true)"
        ), {"id": pid, "n": f"P-AES-{zk_id}", "ci": identificacion, "t": base["tipo_id"], "g": base["grupo_id"]})
        c.execute(sa.text(
            "INSERT INTO istpet.personas_dispositivos (persona_id, dispositivo_id, id_en_dispositivo, es_principal, activo) "
            "VALUES (CAST(:p AS uuid), CAST(:d AS uuid), :zk, true, true)"
        ), {"p": pid, "d": base["dev_id"], "zk": zk_id})
        for i in range(n):
            fh = f"2025-07-15 {8 + i*2:02d}:00:00"
            tipo = "Entrada" if i % 2 == 0 else "Salida"
            c.execute(sa.text(
                "INSERT INTO istpet.asistencias (persona_id, fecha_hora, tipo, fuente, dispositivo_id) "
                "VALUES (CAST(:p AS uuid), CAST(:fh AS timestamptz), :t, 'zk', CAST(:d AS uuid))"
            ), {"p": pid, "fh": fh, "t": tipo, "d": base["dev_id"]})
        c.commit()
    return pid, identificacion, zk_id


class TestAnalyticsEntradasSalidas:

    def test_get_api_sin_persona_id_retorna_400(self, admin_client, tenant_id):
        r = admin_client.get("/api/analytics/entradas-salidas")
        assert r.status_code == 400
        data = r.get_json()
        assert "persona_id" in (data.get("error") or "").lower()

    def test_get_api_con_persona_vacia(self, admin_client, tenant_id):
        r = admin_client.get("/api/analytics/entradas-salidas?persona_id=&fecha_inicio=2025-07-01&fecha_fin=2025-07-31")
        assert r.status_code == 400

    def test_get_api_con_persona_sin_marcaciones(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, ident, zk = _seed_persona_con_marcaciones(e, base, n=0)

        r = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-07-31"
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 0
        assert data["marcaciones"] == []
        assert data["page"] == 1
        assert data["per_page"] == 50
        assert data["total_pages"] == 0

    def test_get_api_con_marcaciones_devuelve_ordenadas(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, ident, zk = _seed_persona_con_marcaciones(e, base, n=4)

        r = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-07-31"
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 4
        assert len(data["marcaciones"]) == 4
        # Verificar orden ascendente por fecha_hora
        for i in range(len(data["marcaciones"]) - 1):
            assert data["marcaciones"][i]["datetime"] <= data["marcaciones"][i + 1]["datetime"]

    def test_get_api_normaliza_tipos(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, ident, zk = _seed_persona_con_marcaciones(e, base, n=2)

        r = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-07-31"
        )
        assert r.status_code == 200
        data = r.get_json()
        tipos_norm = {m["tipo"] for m in data["marcaciones"]}
        assert tipos_norm <= {"entrada", "salida"}

    def test_paginacion_por_page(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, ident, zk = _seed_persona_con_marcaciones(e, base, n=6)

        r = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-07-31&page=1&per_page=3"
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 6
        assert data["per_page"] == 3
        assert data["page"] == 1
        assert data["total_pages"] == 2
        assert len(data["marcaciones"]) == 3

        r2 = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-07-31&page=2&per_page=3"
        )
        data2 = r2.get_json()
        assert data2["page"] == 2
        assert len(data2["marcaciones"]) == 3

    def test_per_page_se_clampa_al_maximo(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, ident, zk = _seed_persona_con_marcaciones(e, base, n=2)

        # per_page=500 debe clamparse a 200
        r = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-07-31&per_page=500"
        )
        data = r.get_json()
        assert data["per_page"] == 200

    def test_rango_invalido_retorna_400(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, ident, zk = _seed_persona_con_marcaciones(e, base, n=1)

        # fecha_inicio > fecha_fin
        r = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2025-07-31&fecha_fin=2025-07-01"
        )
        assert r.status_code == 400

    def test_rango_mayor_a_366_dias_retorna_400(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, ident, zk = _seed_persona_con_marcaciones(e, base, n=1)

        r = admin_client.get(
            f"/api/analytics/entradas-salidas?persona_id={pid}&fecha_inicio=2024-01-01&fecha_fin=2025-12-31"
        )
        assert r.status_code == 400

    def test_persona_id_no_uuid_retorna_400(self, admin_client, tenant_id):
        """Un persona_id no-UUID debe dar 400, no 500.

        Regresión de producción (2026-07-28): el campo es texto libre y un
        operador escribió el ID del biométrico ("30"). Al interpolarse como
        uuid en SQL, Postgres lanzaba DataError y el endpoint devolvía 500.
        """
        r = admin_client.get(
            "/api/analytics/entradas-salidas"
            "?persona_id=30&fecha_inicio=2026-07-21&fecha_fin=2026-07-28"
        )
        assert r.status_code == 400, (
            f"Esperado 400, obtuve {r.status_code}: {r.get_data(as_text=True)[:400]}"
        )
        assert "error" in r.get_json()

    def test_persona_id_texto_arbitrario_retorna_400(self, admin_client, tenant_id):
        r = admin_client.get(
            "/api/analytics/entradas-salidas"
            "?persona_id=no-soy-un-uuid&fecha_inicio=2026-07-21&fecha_fin=2026-07-28"
        )
        assert r.status_code == 400

    def test_vista_entradas_salidas_200(self, admin_client, tenant_id):
        r = admin_client.get("/analytics/entradas-salidas")
        assert r.status_code == 200
        assert b"Entradas y Salidas" in r.data or b"Entradas / Salidas" in r.data or b"entradas-salidas" in r.data

    def test_normalizar_tipo_marcacion_puro(self):
        from db.queries.asistencias_entradas_salidas import normalizar_tipo_marcacion
        assert normalizar_tipo_marcacion("Entrada") == "entrada"
        assert normalizar_tipo_marcacion("SALIDA") == "salida"
        assert normalizar_tipo_marcacion("  entrada  ") == "entrada"
        assert normalizar_tipo_marcacion("0") == "entrada"
        assert normalizar_tipo_marcacion("1") == "salida"
        assert normalizar_tipo_marcacion(None) == "otro"
        assert normalizar_tipo_marcacion("xyz") == "otro"

class TestResumenDiario:
    """
    Endpoint /api/analytics/entradas-salidas/resumen-diario: una fila por dia.

    Spec: docs/superpowers/specs/2026-07-30-resumen-diario-entradas-salidas-design.md
    """

    RUTA = "/api/analytics/entradas-salidas/resumen-diario"

    def test_sin_persona_id_retorna_400(self, admin_client, tenant_id):
        r = admin_client.get(self.RUTA)
        assert r.status_code == 400
        assert "persona_id" in (r.get_json().get("error") or "").lower()

    def test_persona_id_no_uuid_retorna_400(self, admin_client, tenant_id):
        r = admin_client.get(
            f"{self.RUTA}?persona_id=30&fecha_inicio=2025-07-01&fecha_fin=2025-07-31"
        )
        assert r.status_code == 400

    def test_rango_invertido_retorna_400(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, _, _ = _seed_persona_con_marcaciones(e, base, n=0)
        r = admin_client.get(
            f"{self.RUTA}?persona_id={pid}&fecha_inicio=2025-07-31&fecha_fin=2025-07-01"
        )
        assert r.status_code == 400

    def test_persona_sin_marcaciones_devuelve_todos_los_dias(self, admin_client, tenant_id):
        """Los dias vacios igual aparecen: es como se ven las ausencias."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, _, _ = _seed_persona_con_marcaciones(e, base, n=0)

        r = admin_client.get(
            f"{self.RUTA}?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-07-05"
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_dias"] == 5
        assert len(data["dias"]) == 5
        assert [d["fecha"] for d in data["dias"]] == [
            "2025-07-01", "2025-07-02", "2025-07-03", "2025-07-04", "2025-07-05",
        ]
        assert all(d["estado"] == "sin_marcaciones" for d in data["dias"])
        assert all(d["permanencia"] is None for d in data["dias"])

    def test_cuatro_marcaciones_calcula_permanencia_y_efectivo(self, admin_client, tenant_id):
        """El seed crea 08:00 E, 10:00 S, 12:00 E, 14:00 S el 2025-07-15."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, _, _ = _seed_persona_con_marcaciones(e, base, n=4)

        r = admin_client.get(
            f"{self.RUTA}?persona_id={pid}&fecha_inicio=2025-07-15&fecha_fin=2025-07-15"
        )
        assert r.status_code == 200
        dia = r.get_json()["dias"][0]
        assert dia["total_marcaciones"] == 4
        assert dia["primer_marcaje"] == "08:00:00"
        assert dia["ultimo_marcaje"] == "14:00:00"
        assert dia["permanencia"] == "6h 00m"   # 08:00 -> 14:00
        assert dia["efectivo"] == "4h 00m"      # 2h + 2h, descuenta el intermedio
        assert dia["estado"] == "ok"
        assert dia["con_alerta"] is False

    def test_dia_impar_marca_alerta(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, _, _ = _seed_persona_con_marcaciones(e, base, n=3)

        r = admin_client.get(
            f"{self.RUTA}?persona_id={pid}&fecha_inicio=2025-07-15&fecha_fin=2025-07-15"
        )
        dia = r.get_json()["dias"][0]
        assert dia["total_marcaciones"] == 3
        assert dia["estado"] == "impar"
        assert dia["con_alerta"] is True

    def test_marcaciones_embebidas_para_el_popup(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, _, _ = _seed_persona_con_marcaciones(e, base, n=2)

        r = admin_client.get(
            f"{self.RUTA}?persona_id={pid}&fecha_inicio=2025-07-15&fecha_fin=2025-07-15"
        )
        marcaciones = r.get_json()["dias"][0]["marcaciones"]
        assert [m["hora"] for m in marcaciones] == ["08:00:00", "10:00:00"]
        assert [m["tipo"] for m in marcaciones] == ["entrada", "salida"]
        assert marcaciones[0]["tipo_raw"] == "Entrada"

    def test_pagina_por_dia_31_por_pagina(self, admin_client, tenant_id):
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, _, _ = _seed_persona_con_marcaciones(e, base, n=0)

        r = admin_client.get(
            f"{self.RUTA}?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-08-31"
        )
        data = r.get_json()
        assert data["total_dias"] == 62
        assert data["total_pages"] == 2
        assert data["per_page"] == 31
        assert len(data["dias"]) == 31
        assert data["dias"][0]["fecha"] == "2025-07-01"

        r2 = admin_client.get(
            f"{self.RUTA}?persona_id={pid}&fecha_inicio=2025-07-01&fecha_fin=2025-08-31&page=2"
        )
        data2 = r2.get_json()
        assert data2["dias"][0]["fecha"] == "2025-08-01"
        assert len(data2["dias"]) == 31
