"""
Test de regresion para el bug 2: quitar el horario de una persona.

Cubre:
  - Backend: PUT /api/horarios/<id> con todos los dias vacios debe devolver 200.
  - Backend: PUT /api/horarios/<id> con todos los dias null debe devolver 200.
  - Backend: PUT /api/horarios/<id> solo con campos basicos (caso del
    offcanvas cuando todos los dias quedan como 'Libre') debe devolver 200.
  - DELETE /api/horarios/<id> cierra la asignacion con fecha_fin=hoy.

El bloqueo JS `countActivos === 0` se quitó del front
(static/js/configuracion.js) y se reemplazo por una confirmacion
explicita, por lo que el usuario puede guardar un horario sin dias
laborables si asi lo necesita.
"""
from __future__ import annotations

import uuid

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


def _seed_persona_con_horario(e, base, id_zk=None):
    # id_zk unico por ejecucion para evitar choques UNIQUE en re-runs.
    if id_zk is None:
        id_zk = str(uuid.uuid4().int % 1000000 + 100000)
    identificacion = f"P-{uuid.uuid4().hex[:8]}"
    pid = str(uuid.uuid4())
    plantilla_id = str(uuid.uuid4())
    with e.connect() as c:
        c.execute(sa.text(
            "INSERT INTO istpet.personas (id, nombre, identificacion, tipo_persona_id, grupo_id, activo) "
            "VALUES (CAST(:id AS uuid), :n, :ci, CAST(:t AS uuid), CAST(:g AS uuid), true)"
        ), {"id": pid, "n": f"P-{id_zk}", "ci": identificacion, "t": base["tipo_id"], "g": base["grupo_id"]})
        c.execute(sa.text(
            "INSERT INTO istpet.personas_dispositivos (persona_id, dispositivo_id, id_en_dispositivo, es_principal, activo) "
            "VALUES (CAST(:p AS uuid), CAST(:d AS uuid), :zk, true, true)"
        ), {"p": pid, "d": base["dev_id"], "zk": id_zk})
        c.execute(sa.text(
            "INSERT INTO istpet.plantillas_horario (id, nombre, lunes, lunes_salida, lunes_almuerzo_min, martes, martes_salida, miercoles, miercoles_salida, jueves, jueves_salida, viernes, viernes_salida, sabado, sabado_salida, domingo, domingo_salida, almuerzo_min, activo) "
            "VALUES (CAST(:id AS uuid), 'P', '08:00', '17:00', 60, '08:00', '17:00', '08:00', '17:00', '08:00', '17:00', '08:00', '17:00', NULL, NULL, NULL, NULL, 60, true)"
        ), {"id": plantilla_id})
        c.execute(sa.text(
            "INSERT INTO istpet.asignaciones_horario (persona_id, plantilla_id, fecha_inicio, ciclo_semanas, posicion_ciclo) "
            "VALUES (CAST(:p AS uuid), CAST(:pl AS uuid), '2024-01-01', 1, 1)"
        ), {"p": pid, "pl": plantilla_id})
        c.commit()
    return pid, id_zk


def _payload_sin_dias(id_zk):
    """Payload equivalente al que manda el offcanvas cuando todos los
    dias quedan marcados como 'Libre'."""
    return {
        "id_usuario": id_zk,
        "nombre": f"P-{id_zk}",
        "almuerzo_min": 0,
        "notas": "",
    }


class TestBug2QuitarHorario:

    def test_put_horario_sin_dias_devuelve_200(self, admin_client, tenant_id):
        """El backend ya aceptaba un horario con todos los dias null.
        Antes del fix JS bloqueaba 'countActivos === 0' y nunca llegaba
        al backend. Con el fix JS (confirmacion explicita), el usuario
        puede guardar un horario vacio y el backend responde 200."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, id_zk = _seed_persona_con_horario(e, base)

        r = admin_client.put(f"/api/horarios/{id_zk}", json=_payload_sin_dias(id_zk))
        assert r.status_code == 200, f"Status inesperado: {r.status_code}, body: {r.get_data(as_text=True)}"

        # Verificar que la plantilla quedo con todos los dias en null
        with e.connect() as c:
            row = c.execute(sa.text(
                "SELECT lunes, martes, miercoles, jueves, viernes, sabado, domingo "
                "FROM istpet.plantillas_horario WHERE id = ("
                "  SELECT plantilla_id FROM istpet.asignaciones_horario "
                "  WHERE persona_id = CAST(:p AS uuid) AND fecha_fin IS NULL LIMIT 1"
                ")"
            ), {"p": pid}).fetchone()
            for i, dia in enumerate(("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")):
                assert row[i] is None, f"{dia} debe ser NULL tras quitar el horario"

    def test_put_con_dias_null_explicitos(self, admin_client, tenant_id):
        """PUT con cada dia explicitamente null tambien debe funcionar."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, id_zk = _seed_persona_con_horario(e, base)

        payload = {
            "id_usuario": id_zk,
            "nombre": f"P-{id_zk}",
            "lunes": None,
            "lunes_salida": None,
            "martes": None,
            "martes_salida": None,
            "miercoles": None,
            "miercoles_salida": None,
            "jueves": None,
            "jueves_salida": None,
            "viernes": None,
            "viernes_salida": None,
            "sabado": None,
            "sabado_salida": None,
            "domingo": None,
            "domingo_salida": None,
            "almuerzo_min": 0,
            "notas": "",
        }
        r = admin_client.put(f"/api/horarios/{id_zk}", json=payload)
        assert r.status_code == 200

    def test_delete_horario_cierra_asignacion(self, admin_client, tenant_id):
        """DELETE /api/horarios/<id> es la via directa para quitar el
        horario: cierra la asignacion vigente con fecha_fin = hoy."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, id_zk = _seed_persona_con_horario(e, base)

        r = admin_client.delete(f"/api/horarios/{id_zk}")
        assert r.status_code == 200

        with e.connect() as c:
            row = c.execute(sa.text(
                "SELECT fecha_fin FROM istpet.asignaciones_horario WHERE persona_id = CAST(:p AS uuid)"
            ), {"p": pid}).fetchone()
            assert row[0] is not None, "La asignacion debe haber quedado con fecha_fin"
            assert str(row[0]) <= "2026-07-28", f"fecha_fin esperada <= hoy, fue {row[0]}"

    def test_horario_sin_dias_no_bloquea_consulta(self, admin_client, tenant_id):
        """Tras quitar el horario (todos los dias NULL), GET /api/horarios
        sigue devolviendo la persona para que aparezca en la lista de
        horarios (que sirve para detectar este estado y reasignar)."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid, id_zk = _seed_persona_con_horario(e, base)

        # Quitar horario via PUT
        r = admin_client.put(f"/api/horarios/{id_zk}", json=_payload_sin_dias(id_zk))
        assert r.status_code == 200

        # Verificar via GET que sigue apareciendo (sin filtrar por dias)
        r2 = admin_client.get("/api/horarios")
        assert r2.status_code == 200
        data = r2.get_json()
        horarios_ids = [h.get("id_usuario") for h in data.get("horarios", [])]
        assert id_zk in horarios_ids, f"La persona {id_zk} debe seguir listada tras quitar su horario"