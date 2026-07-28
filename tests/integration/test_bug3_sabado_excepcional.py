"""
Test de regresion para el bug 3: sabado excepcional con horario sin almuerzo
solo mostraba entrada, no salida en el reporte por persona.

Cubre:
  - Persona con horario lunes a viernes con almuerzo (60 min).
  - Sabado y domingo libres en el horario.
  - El sabado la persona timbre 2 veces (Entrada + Salida, sin almuerzo).
  - El reporte debe mostrar tanto la entrada como la salida,
    con estado 'extra' (no 'libre' con dia ignorado).
  - Si la persona tiene solo dias libres con marcaciones (sin dias
    normales), debe aparecer en el reporte (no quedar filtrada por
    el guard `total_dias > 0`).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, time

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration


def _seed_basico(e):
    """Crea sede, tipo, grupo y dispositivo."""
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


def _seed_persona_lv_con_almuerzo(e, base, nombre_prefijo):
    """Crea persona con horario L-V con almuerzo 60 min; sabado/domingo NULL (libres)."""
    identificacion = f"{nombre_prefijo}-{uuid.uuid4().hex[:8]}"
    pid = str(uuid.uuid4())
    plantilla_id = str(uuid.uuid4())
    zk_id = str(uuid.uuid4().int % 1000000 + 100000)
    nombre = f"{nombre_prefijo}-{uuid.uuid4().hex[:6]}"

    with e.connect() as c:
        c.execute(sa.text("""
            INSERT INTO istpet.plantillas_horario (
                id, nombre,
                lunes, lunes_salida, lunes_almuerzo_min,
                martes, martes_salida, martes_almuerzo_min,
                miercoles, miercoles_salida, miercoles_almuerzo_min,
                jueves, jueves_salida, jueves_almuerzo_min,
                viernes, viernes_salida, viernes_almuerzo_min,
                sabado, sabado_salida, sabado_almuerzo_min,
                domingo, domingo_salida, domingo_almuerzo_min,
                almuerzo_min, activo
            ) VALUES (
                CAST(:id AS uuid), 'P',
                '08:00', '17:00', 60,
                '08:00', '17:00', 60,
                '08:00', '17:00', 60,
                '08:00', '17:00', 60,
                '08:00', '17:00', 60,
                NULL, NULL, NULL,
                NULL, NULL, NULL,
                60, true
            )
        """), {"id": plantilla_id})

        c.execute(sa.text(
            "INSERT INTO istpet.personas (id, nombre, identificacion, tipo_persona_id, grupo_id, activo) "
            "VALUES (CAST(:id AS uuid), :n, :ci, CAST(:t AS uuid), CAST(:g AS uuid), true)"
        ), {"id": pid, "n": nombre, "ci": identificacion, "t": base["tipo_id"], "g": base["grupo_id"]})

        c.execute(sa.text(
            "INSERT INTO istpet.personas_dispositivos (persona_id, dispositivo_id, id_en_dispositivo, es_principal, activo) "
            "VALUES (CAST(:p AS uuid), CAST(:d AS uuid), :zk, true, true)"
        ), {"p": pid, "d": base["dev_id"], "zk": zk_id})

        c.execute(sa.text(
            "INSERT INTO istpet.asignaciones_horario (persona_id, plantilla_id, fecha_inicio, ciclo_semanas, posicion_ciclo) "
            "VALUES (CAST(:p AS uuid), CAST(:pl AS uuid), '2024-01-01', 1, 1)"
        ), {"p": pid, "pl": plantilla_id})
        c.commit()

    return pid, nombre, zk_id


def _insertar_marcaciones(e, pid, fecha_iso, hora_entrada, hora_salida):
    """Inserta Entrada y Salida para una persona en una fecha.

    Usa timestamps naive (sin tz) para que PostgreSQL los interprete en la
    zona horaria de la sesion (UTC en pgserver). Asi el sistema ve las
    horas como locales.
    """
    with e.connect() as c:
        for hora_str, tipo in ((hora_entrada, "Entrada"), (hora_salida, "Salida")):
            fh = f"{fecha_iso} {hora_str}:00"  # naive, sin tz
            c.execute(sa.text(
                "INSERT INTO istpet.asistencias (persona_id, fecha_hora, tipo, fuente, dispositivo_id) "
                "VALUES (CAST(:p AS uuid), CAST(:fh AS timestamptz), :t, 'zk', "
                "  CAST((SELECT dispositivo_id FROM istpet.personas_dispositivos WHERE persona_id = CAST(:p AS uuid) AND es_principal = true LIMIT 1) AS uuid))"
            ), {"p": pid, "fh": fh, "t": tipo})
        c.commit()


class TestBug3SabadoExcepcional:

    def test_sabado_excepcional_sin_almuerzo_muestra_entrada_y_salida(self, admin_client, tenant_id):
        """Sabado con horario L-V (almuerzo) + marcaciones Entrada/Salida sin almuerzo.

        Antes del fix: el reporte mostraba 'Dia libre segun horario' con solo
        la entrada. La salida se perdia.

        Despues del fix: el reporte muestra entrada, salida, y el estado es
        'extra' para indicar que la persona trabajo excepcionalmente en un dia
        que su horario marca como libre."""
        from db.connection import get_engine
        from app.domain.reports import analizar_por_persona
        from db.queries.horarios import get_horarios
        from db.queries.asistencias import consultar_asistencias

        e = get_engine()
        base = _seed_basico(e)
        pid, nombre, zk_id = _seed_persona_lv_con_almuerzo(e, base, "SabExc")

        # Sabado 2025-07-12 con marcaciones Entrada 08:00 / Salida 12:00 (sin almuerzo)
        fecha_sabado_iso = "2025-07-12"
        _insertar_marcaciones(e, pid, fecha_sabado_iso, "08:00", "12:00")

        # Cargar registros solo de esta persona
        registros_all = consultar_asistencias(date(2025, 7, 12), date(2025, 7, 12))
        registros = [r for r in registros_all if r["nombre"] == nombre]

        horarios = get_horarios()
        resultado = analizar_por_persona(
            registros=registros,
            config={},
            horarios=horarios,
        )

        # La persona debe aparecer en el resultado (antes del fix se filtraba)
        assert nombre in resultado, (
            f"BUG 3: la persona {nombre} no aparece en el reporte tras "
            f"trabajar un sabado excepcional. resultado keys: {list(resultado.keys())}"
        )
        dias = resultado[nombre]["dias"]
        assert len(dias) == 1, f"Debe haber exactamente 1 dia (el sabado), hubo {len(dias)}"

        sabado = dias[0]
        assert str(sabado["fecha"]) == fecha_sabado_iso
        # El bug especifico: la salida debe estar presente
        assert sabado.get("salida") is not None, (
            f"BUG 3: salida debe estar presente (se timbro 12:00). "
            f"Obtenido: {sabado}"
        )
        assert sabado.get("llegada") == "08:00", f"Llegada esperada 08:00. Obtenido: {sabado.get('llegada')}"
        assert sabado.get("salida") == "12:00", f"Salida esperada 12:00. Obtenido: {sabado.get('salida')}"
        # El estado debe distinguirse de un dia normal 'ok'
        assert sabado.get("estado") == "extra", (
            f"Estado esperado 'extra' (trabajo excepcional). Obtenido: {sabado.get('estado')}"
        )
        # El detalle debe listar ambas marcaciones
        detalle = sabado.get("detalle_registros", "")
        assert "Entrada" in detalle and "Salida" in detalle, (
            f"detalle_registros debe contener Entrada y Salida. Obtenido: {detalle!r}"
        )

    def test_dia_libre_con_marcaciones_suma_total_dias(self, admin_client, tenant_id):
        """Cuando una persona SOLO tiene marcaciones en un dia libre (sin dias
        normales en el rango), debe aparecer en el reporte (no quedar filtrada
        por el guard `resumen['total_dias'] > 0`)."""
        from db.connection import get_engine
        from app.domain.reports import analizar_por_persona
        from db.queries.horarios import get_horarios
        from db.queries.asistencias import consultar_asistencias

        e = get_engine()
        base = _seed_basico(e)
        pid, nombre, zk_id = _seed_persona_lv_con_almuerzo(e, base, "SoloExc")

        # Insertar SOLO una marcacion en domingo (dia libre)
        fecha_domingo_iso = "2025-07-13"  # domingo
        _insertar_marcaciones(e, pid, fecha_domingo_iso, "09:00", "13:00")

        registros_all = consultar_asistencias(date(2025, 7, 13), date(2025, 7, 13))
        registros = [r for r in registros_all if r["nombre"] == nombre]

        horarios = get_horarios()
        resultado = analizar_por_persona(
            registros=registros,
            config={},
            horarios=horarios,
        )

        assert nombre in resultado, (
            f"BUG 3: persona con unica marcacion en domingo debe aparecer. "
            f"resultado keys: {list(resultado.keys())}"
        )
        assert resultado[nombre]["resumen"]["total_dias"] == 1

    def test_dia_normal_seguira_siendo_ok(self, admin_client, tenant_id):
        """Los dias normales (L-V con horario) deben seguir mostrandose como
        'ok' con la salida correcta, sin regresion del bug 3."""
        from db.connection import get_engine
        from app.domain.reports import analizar_por_persona
        from db.queries.horarios import get_horarios
        from db.queries.asistencias import consultar_asistencias

        e = get_engine()
        base = _seed_basico(e)
        pid, nombre, zk_id = _seed_persona_lv_con_almuerzo(e, base, "Normal")

        # Lunes 2025-07-14 con horario normal (08:00 entrada, 17:00 salida, 60 min almuerzo)
        # 4 marcaciones: E, S_almuerzo, E_almuerzo, S
        fecha_lunes_iso = "2025-07-14"
        for hora_str, tipo in (
            ("08:00", "Entrada"),
            ("12:00", "Salida"),
            ("13:00", "Entrada"),
            ("17:00", "Salida"),
        ):
            fh = f"{fecha_lunes_iso} {hora_str}:00"  # naive
            with e.connect() as c:
                c.execute(sa.text(
                    "INSERT INTO istpet.asistencias (persona_id, fecha_hora, tipo, fuente, dispositivo_id) "
                    "VALUES (CAST(:p AS uuid), CAST(:fh AS timestamptz), :t, 'zk', "
                    "  CAST((SELECT dispositivo_id FROM istpet.personas_dispositivos WHERE persona_id = CAST(:p AS uuid) AND es_principal = true LIMIT 1) AS uuid))"
                ), {"p": pid, "fh": fh, "t": tipo})
                c.commit()

        registros_all = consultar_asistencias(date(2025, 7, 14), date(2025, 7, 14))
        registros = [r for r in registros_all if r["nombre"] == nombre]

        horarios = get_horarios()
        resultado = analizar_por_persona(
            registros=registros,
            config={},
            horarios=horarios,
            mostrar_todos=True,  # para ver dias sin novedad
        )

        assert nombre in resultado
        # El lunes debe estar en dias_list (mostrar_todos=True)
        dias_con_lunes = [d for d in resultado[nombre]["dias"] if str(d["fecha"]) == "2025-07-14"]
        assert len(dias_con_lunes) == 1, f"Debe haber el lunes 2025-07-14, hubo {dias_con_lunes}"
        lunes = dias_con_lunes[0]
        assert lunes.get("estado") == "ok", f"Lunes normal debe seguir siendo 'ok'. Obtenido: {lunes.get('estado')}"
        assert lunes.get("llegada") == "08:00"
        assert lunes.get("salida") == "17:00"