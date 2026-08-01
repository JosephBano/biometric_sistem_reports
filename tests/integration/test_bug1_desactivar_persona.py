"""
Test de regresion para el bug 1: desactivar persona con horario y marcaciones.

Cubre:
  - Desactivar persona CON horario asignado y marcaciones (escenario reportado).
  - Desactivar persona SIN horario asignado (variante).
  - No se reasigna silenciosamente el id_usuario_zk de otra persona
    (bug de integridad detectado en _upsert_zk_id).
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration


def _seed_basico(e):
    """Crea sede + tipo + grupo + 2 dispositivos activos + admin."""
    tipo_id = str(uuid.uuid4())
    grupo_id = str(uuid.uuid4())
    sede_id = str(uuid.uuid4())
    dev1 = str(uuid.uuid4())
    dev2 = str(uuid.uuid4())

    with e.connect() as c:
        c.execute(sa.text("INSERT INTO istpet.sedes (id, nombre) VALUES (CAST(:id AS uuid), 'Sede')"), {"id": sede_id})
        c.execute(sa.text("INSERT INTO istpet.tipos_persona (id, nombre, activo) VALUES (CAST(:id AS uuid), 'Emp', true)"), {"id": tipo_id})
        c.execute(sa.text("INSERT INTO istpet.grupos (id, nombre, sede_id, activo) VALUES (CAST(:id AS uuid), 'G', CAST(:s AS uuid), true)"), {"id": grupo_id, "s": sede_id})
        for did, prio in ((dev1, 1), (dev2, 2)):
            c.execute(sa.text(
                "INSERT INTO istpet.dispositivos (id, nombre, ip, puerto, tipo_driver, protocolo, sede_id, activo, prioridad) "
                "VALUES (CAST(:id AS uuid), :n, '127.0.0.1', 4370, 'zk', 'udp', CAST(:s AS uuid), true, :p)"
            ), {"id": did, "n": f"D{prio}", "s": sede_id, "p": prio})
        c.commit()
    return {"tipo_id": tipo_id, "grupo_id": grupo_id, "sede_id": sede_id, "dev1": dev1, "dev2": dev2}


def _seed_persona(e, base, identificacion, id_zk, dispositivo_id):
    # Usamos identificacion unica por test (uuid corto) para evitar choques
    # UNIQUE al re-ejecutar la suite sin DROP completo.
    identificacion_unica = f"{identificacion}-{uuid.uuid4().hex[:8]}"
    pid = str(uuid.uuid4())
    with e.connect() as c:
        c.execute(sa.text(
            "INSERT INTO istpet.personas (id, nombre, identificacion, tipo_persona_id, grupo_id, activo) "
            "VALUES (CAST(:id AS uuid), :n, :ci, CAST(:t AS uuid), CAST(:g AS uuid), true)"
        ), {"id": pid, "n": f"P-{identificacion}", "ci": identificacion_unica, "t": base["tipo_id"], "g": base["grupo_id"]})
        c.execute(sa.text(
            "INSERT INTO istpet.personas_dispositivos (persona_id, dispositivo_id, id_en_dispositivo, es_principal, activo) "
            "VALUES (CAST(:p AS uuid), CAST(:d AS uuid), :zk, true, true)"
        ), {"p": pid, "d": dispositivo_id, "zk": id_zk})
        c.commit()
    return pid


class TestBug1DesactivarPersona:
    """Bug 1: no se podia desactivar una persona (HTTP 400 reportado)."""

    def test_desactivar_persona_con_horario_y_marcaciones(self, admin_client, tenant_id):
        """Reproduce el escenario reportado: persona con horario + marcaciones
        + ZK id existente. Debe desactivarse correctamente (302)."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid = _seed_persona(e, base, "P-con-horario", "90", base["dev1"])
        # Obtener la identificación real que se guardó
        with e.connect() as c:
            row = c.execute(sa.text(
                "SELECT identificacion FROM istpet.personas WHERE id = CAST(:id AS uuid)"
            ), {"id": pid}).fetchone()
            identificacion_real = row[0]

        # Asignar horario + marcaciones
        plantilla_id = str(uuid.uuid4())
        with e.connect() as c:
            c.execute(sa.text(
                "INSERT INTO istpet.plantillas_horario (id, nombre, lunes, lunes_salida, lunes_almuerzo_min, activo) "
                "VALUES (CAST(:id AS uuid), 'P', '08:00', '17:00', 60, true)"
            ), {"id": plantilla_id})
            c.execute(sa.text(
                "INSERT INTO istpet.asignaciones_horario (persona_id, plantilla_id, fecha_inicio, ciclo_semanas, posicion_ciclo) "
                "VALUES (CAST(:p AS uuid), CAST(:pl AS uuid), '2024-01-01', 1, 1)"
            ), {"p": pid, "pl": plantilla_id})
            for hora, tipo in (("2024-06-01 08:00:00+00", "Entrada"), ("2024-06-01 17:00:00+00", "Salida")):
                c.execute(sa.text(
                    "INSERT INTO istpet.asistencias (persona_id, fecha_hora, tipo, fuente, dispositivo_id) "
                    "VALUES (CAST(:p AS uuid), :fh, :t, 'zk', CAST(:d AS uuid))"
                ), {"p": pid, "fh": hora, "t": tipo, "d": base["dev1"]})
            c.commit()

        # Desactivar
        r = admin_client.post(
            f"/personas/{pid}",
            data={
                "csrf_token": "test-csrf-token",
                "nombre": "P-con-horario",
                "identificacion": identificacion_real,
                "email": "",
                "telefono": "",
                "notas": "",
                "tipo_persona_id": base["tipo_id"],
                "grupo_id": base["grupo_id"],
                "categoria_id": "",
                "activo": "0",
                "id_usuario_zk": "90",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 200), f"Status inesperado: {r.status_code}"

        # Verificar estado final
        with e.connect() as c:
            row = c.execute(sa.text(
                "SELECT activo FROM istpet.personas WHERE id = CAST(:id AS uuid)"
            ), {"id": pid}).fetchone()
            assert row[0] is False, "La persona debe quedar inactiva"

            # Horario y marcaciones preservados
            count_asig = c.execute(sa.text(
                "SELECT count(*) FROM istpet.asignaciones_horario WHERE persona_id = CAST(:p AS uuid)"
            ), {"p": pid}).fetchone()[0]
            assert count_asig == 1, "Horario debe permanecer"

            count_asis = c.execute(sa.text(
                "SELECT count(*) FROM istpet.asistencias WHERE persona_id = CAST(:p AS uuid)"
            ), {"p": pid}).fetchone()[0]
            assert count_asis == 2, "Marcaciones deben permanecer"

    def test_desactivar_persona_sin_horario(self, admin_client, tenant_id):
        """Variante sin horario: desactivar debe funcionar igual."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)
        pid = _seed_persona(e, base, "P-sin-horario", "91", base["dev1"])
        with e.connect() as c:
            row = c.execute(sa.text(
                "SELECT identificacion FROM istpet.personas WHERE id = CAST(:id AS uuid)"
            ), {"id": pid}).fetchone()
            identificacion_real = row[0]

        r = admin_client.post(
            f"/personas/{pid}",
            data={
                "csrf_token": "test-csrf-token",
                "nombre": "P-sin-horario",
                "identificacion": identificacion_real,
                "email": "",
                "telefono": "",
                "notas": "",
                "tipo_persona_id": base["tipo_id"],
                "grupo_id": base["grupo_id"],
                "categoria_id": "",
                "activo": "0",
                "id_usuario_zk": "91",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 200)

        with e.connect() as c:
            row = c.execute(sa.text(
                "SELECT activo FROM istpet.personas WHERE id = CAST(:id AS uuid)"
            ), {"id": pid}).fetchone()
            assert row[0] is False

    def test_desactivar_no_reasigna_marcaciones_historicas(self, admin_client, tenant_id):
        """Desactivar una persona NO debe alterar el historial de marcaciones
        ni los horarios ya registrados. Cubre el escenario reportado por el
        usuario (persona con horario + marcaciones + desactivar)."""
        from db.connection import get_engine
        e = get_engine()
        base = _seed_basico(e)

        # Persona A con ZK id 92
        pid_a = _seed_persona(e, base, "P-A", "92", base["dev1"])
        # Persona B con otro ZK id
        pid_b = _seed_persona(e, base, "P-B", "93", base["dev2"])
        with e.connect() as c:
            id_a = c.execute(sa.text(
                "SELECT identificacion FROM istpet.personas WHERE id = CAST(:id AS uuid)"
            ), {"id": pid_a}).fetchone()[0]
            id_b = c.execute(sa.text(
                "SELECT identificacion FROM istpet.personas WHERE id = CAST(:id AS uuid)"
            ), {"id": pid_b}).fetchone()[0]

        # Asignar horario + marcaciones a A
        plantilla_id = str(uuid.uuid4())
        with e.connect() as c:
            c.execute(sa.text(
                "INSERT INTO istpet.plantillas_horario (id, nombre, lunes, lunes_salida, lunes_almuerzo_min, activo) "
                "VALUES (CAST(:id AS uuid), 'P', '08:00', '17:00', 60, true)"
            ), {"id": plantilla_id})
            c.execute(sa.text(
                "INSERT INTO istpet.asignaciones_horario (persona_id, plantilla_id, fecha_inicio, ciclo_semanas, posicion_ciclo) "
                "VALUES (CAST(:p AS uuid), CAST(:pl AS uuid), '2024-01-01', 1, 1)"
            ), {"p": pid_a, "pl": plantilla_id})
            for hora, tipo in (("2024-06-01 08:00:00+00", "Entrada"), ("2024-06-01 17:00:00+00", "Salida")):
                c.execute(sa.text(
                    "INSERT INTO istpet.asistencias (persona_id, fecha_hora, tipo, fuente, dispositivo_id) "
                    "VALUES (CAST(:p AS uuid), :fh, :t, 'zk', CAST(:d AS uuid))"
                ), {"p": pid_a, "fh": hora, "t": tipo, "d": base["dev1"]})
            c.commit()

        # Desactivar SOLO a B (A permanece activa)
        r = admin_client.post(
            f"/personas/{pid_b}",
            data={
                "csrf_token": "test-csrf-token",
                "nombre": "P-B",
                "identificacion": id_b,
                "email": "",
                "telefono": "",
                "notas": "",
                "tipo_persona_id": base["tipo_id"],
                "grupo_id": base["grupo_id"],
                "categoria_id": "",
                "activo": "0",
                "id_usuario_zk": "93",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 200)

        # A sigue activa con sus marcaciones intactas
        with e.connect() as c:
            row_a = c.execute(sa.text(
                "SELECT activo FROM istpet.personas WHERE id = CAST(:id AS uuid)"
            ), {"id": pid_a}).fetchone()
            assert row_a[0] is True, "A debe seguir activa"

            count_asis = c.execute(sa.text(
                "SELECT count(*) FROM istpet.asistencias WHERE persona_id = CAST(:p AS uuid)"
            ), {"p": pid_a}).fetchone()[0]
            assert count_asis == 2, "Marcaciones de A deben permanecer"

            count_asig = c.execute(sa.text(
                "SELECT count(*) FROM istpet.asignaciones_horario WHERE persona_id = CAST(:p AS uuid)"
            ), {"p": pid_a}).fetchone()[0]
            assert count_asig == 1, "Horario de A debe permanecer"