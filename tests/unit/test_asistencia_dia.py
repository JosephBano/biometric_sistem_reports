"""
Tests del resumen diario de marcaciones (`app.domain.asistencia_dia`).

Módulo puro: sin BD, sin Flask, sin reloj. Toda la lógica delicada del
requisito vive acá, así que se cubre a fondo.

Spec: docs/superpowers/specs/2026-07-30-resumen-diario-entradas-salidas-design.md
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.domain.asistencia_dia import (
    formatear_duracion,
    resumir_dia,
    resumir_rango,
)


def marca(fecha: str, hora: str, tipo: str = "entrada") -> dict:
    """Construye una marcación con la forma que entrega la capa db."""
    dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M:%S")
    return {"datetime": dt, "tipo": tipo, "tipo_raw": tipo.capitalize(), "fuente": "zk"}


# ══════════════════════════════════════════════════════════════════════════
# formatear_duracion
# ══════════════════════════════════════════════════════════════════════════

class TestFormatearDuracion:

    @pytest.mark.parametrize("segundos,esperado", [
        (0, "0h 00m"),
        (59, "0h 00m"),          # trunca, no redondea
        (60, "0h 01m"),
        (2700, "0h 45m"),
        (3600, "1h 00m"),
        (26213, "7h 16m"),       # caso real: 07:13:14 → 14:30:07 (7h 16m 53s)
        (93900, "26h 05m"),      # más de un día
    ])
    def test_formatos(self, segundos, esperado):
        assert formatear_duracion(segundos) == esperado

    def test_none_devuelve_none(self):
        assert formatear_duracion(None) is None


# ══════════════════════════════════════════════════════════════════════════
# resumir_dia — cálculo de tiempos
# ══════════════════════════════════════════════════════════════════════════

class TestTiempos:

    def test_sin_marcaciones(self):
        r = resumir_dia(date(2026, 7, 25), [])
        assert r["total_marcaciones"] == 0
        assert r["primer_marcaje"] is None
        assert r["ultimo_marcaje"] is None
        assert r["permanencia"] is None
        assert r["efectivo"] is None
        assert r["estado"] == "sin_marcaciones"

    def test_una_marcacion_no_calcula_tiempos(self):
        r = resumir_dia(date(2026, 7, 29), [marca("2026-07-29", "07:18:26")])
        assert r["total_marcaciones"] == 1
        assert r["primer_marcaje"] == "07:18:26"
        assert r["ultimo_marcaje"] is None
        assert r["permanencia"] is None
        assert r["efectivo"] is None

    def test_dos_marcaciones_permanencia_igual_efectivo(self):
        """Caso real 2026-07-23: 07:13:14 entrada, 14:30:07 salida."""
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:13:14", "entrada"),
            marca("2026-07-23", "14:30:07", "salida"),
        ])
        assert r["primer_marcaje"] == "07:13:14"
        assert r["ultimo_marcaje"] == "14:30:07"
        assert r["permanencia"] == "7h 16m"
        assert r["efectivo"] == r["permanencia"]

    def test_cuatro_marcaciones_efectivo_descuenta_almuerzo(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "entrada"),
            marca("2026-07-23", "12:00:00", "salida"),
            marca("2026-07-23", "13:00:00", "entrada"),
            marca("2026-07-23", "16:00:00", "salida"),
        ])
        assert r["permanencia"] == "9h 00m"   # 07:00 → 16:00
        assert r["efectivo"] == "8h 00m"      # 5h + 3h, sin la hora de almuerzo

    def test_tres_marcaciones_ignora_la_impar_en_efectivo(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "entrada"),
            marca("2026-07-23", "12:00:00", "salida"),
            marca("2026-07-23", "13:00:00", "entrada"),
        ])
        assert r["permanencia"] == "6h 00m"   # 07:00 → 13:00
        assert r["efectivo"] == "5h 00m"      # solo el par completo

    def test_seis_marcaciones_suma_tres_tramos(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "entrada"),
            marca("2026-07-23", "09:00:00", "salida"),
            marca("2026-07-23", "10:00:00", "entrada"),
            marca("2026-07-23", "12:00:00", "salida"),
            marca("2026-07-23", "13:00:00", "entrada"),
            marca("2026-07-23", "16:00:00", "salida"),
        ])
        assert r["permanencia"] == "9h 00m"
        assert r["efectivo"] == "7h 00m"      # 2h + 2h + 3h

    def test_calcula_por_posicion_aunque_los_tipos_esten_mal(self):
        """Caso real 2026-07-24: dos 'Salida' seguidas. Igual se calcula."""
        r = resumir_dia(date(2026, 7, 24), [
            marca("2026-07-24", "07:13:22", "salida"),
            marca("2026-07-24", "14:31:23", "salida"),
        ])
        assert r["permanencia"] == "7h 18m"
        assert r["efectivo"] == "7h 18m"
        assert r["estado"] == "dos_salidas"

    def test_ordena_por_hora_aunque_lleguen_desordenadas(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "14:30:07", "salida"),
            marca("2026-07-23", "07:13:14", "entrada"),
        ])
        assert r["primer_marcaje"] == "07:13:14"
        assert r["ultimo_marcaje"] == "14:30:07"
        assert r["estado"] == "ok"


# ══════════════════════════════════════════════════════════════════════════
# resumir_dia — validación de secuencia
# ══════════════════════════════════════════════════════════════════════════

class TestEstados:

    def test_ok_dos_marcaciones(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "entrada"),
            marca("2026-07-23", "14:00:00", "salida"),
        ])
        assert r["estado"] == "ok"
        assert r["mensaje"]

    def test_ok_cuatro_marcaciones(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "entrada"),
            marca("2026-07-23", "12:00:00", "salida"),
            marca("2026-07-23", "13:00:00", "entrada"),
            marca("2026-07-23", "16:00:00", "salida"),
        ])
        assert r["estado"] == "ok"

    def test_dos_entradas_seguidas(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "entrada"),
            marca("2026-07-23", "08:30:00", "entrada"),
        ])
        assert r["estado"] == "dos_entradas"
        assert "08:30:00" in r["mensaje"]

    def test_dos_salidas_seguidas_reporta_la_hora_del_conflicto(self):
        r = resumir_dia(date(2026, 7, 24), [
            marca("2026-07-24", "07:13:22", "salida"),
            marca("2026-07-24", "14:31:23", "salida"),
        ])
        assert r["estado"] == "dos_salidas"
        assert "14:31:23" in r["mensaje"]

    def test_empieza_con_salida(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "salida"),
            marca("2026-07-23", "14:00:00", "entrada"),
        ])
        assert r["estado"] == "empieza_salida"

    def test_impar_con_una_marcacion(self):
        r = resumir_dia(date(2026, 7, 29), [marca("2026-07-29", "07:18:26", "entrada")])
        assert r["estado"] == "impar"

    def test_impar_con_tres_marcaciones(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "entrada"),
            marca("2026-07-23", "12:00:00", "salida"),
            marca("2026-07-23", "13:00:00", "entrada"),
        ])
        assert r["estado"] == "impar"

    def test_tipo_desconocido_gana_sobre_el_resto(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "07:00:00", "otro"),
            marca("2026-07-23", "14:00:00", "salida"),
        ])
        assert r["estado"] == "tipo_desconocido"

    def test_duplicados_ganan_sobre_empieza_salida(self):
        """El 07-24 cumple las dos condiciones; lo accionable es el duplicado."""
        r = resumir_dia(date(2026, 7, 24), [
            marca("2026-07-24", "07:13:22", "salida"),
            marca("2026-07-24", "14:31:23", "salida"),
        ])
        assert r["estado"] == "dos_salidas"

    def test_marcaciones_se_devuelven_para_el_popup(self):
        r = resumir_dia(date(2026, 7, 23), [
            marca("2026-07-23", "14:30:07", "salida"),
            marca("2026-07-23", "07:13:14", "entrada"),
        ])
        assert [m["hora"] for m in r["marcaciones"]] == ["07:13:14", "14:30:07"]
        assert [m["tipo"] for m in r["marcaciones"]] == ["entrada", "salida"]


# ══════════════════════════════════════════════════════════════════════════
# resumir_rango — agrupamiento y relleno
# ══════════════════════════════════════════════════════════════════════════

class TestResumirRango:

    def test_rellena_todos_los_dias_del_rango(self):
        filas = resumir_rango(date(2026, 7, 23), date(2026, 7, 26), [])
        assert [f["fecha"] for f in filas] == [
            "2026-07-23", "2026-07-24", "2026-07-25", "2026-07-26",
        ]
        assert all(f["estado"] == "sin_marcaciones" for f in filas)

    def test_agrupa_por_fecha_calendario(self):
        filas = resumir_rango(date(2026, 7, 23), date(2026, 7, 24), [
            marca("2026-07-23", "07:13:14", "entrada"),
            marca("2026-07-23", "14:30:07", "salida"),
            marca("2026-07-24", "07:13:22", "salida"),
            marca("2026-07-24", "14:31:23", "salida"),
        ])
        assert len(filas) == 2
        assert filas[0]["total_marcaciones"] == 2
        assert filas[0]["estado"] == "ok"
        assert filas[1]["estado"] == "dos_salidas"

    def test_dias_vacios_intercalados(self):
        """Fin de semana en el medio del rango: sábado 25 y domingo 26."""
        filas = resumir_rango(date(2026, 7, 24), date(2026, 7, 27), [
            marca("2026-07-24", "07:13:22", "salida"),
            marca("2026-07-27", "07:09:46", "entrada"),
            marca("2026-07-27", "14:35:26", "salida"),
        ])
        estados = [f["estado"] for f in filas]
        # El 24 tiene un único marcaje de tipo salida: `empieza_salida` tiene
        # prioridad sobre `impar` (ver orden declarado en el módulo).
        assert estados == ["empieza_salida", "sin_marcaciones", "sin_marcaciones", "ok"]

    def test_un_solo_dia(self):
        filas = resumir_rango(date(2026, 7, 23), date(2026, 7, 23), [
            marca("2026-07-23", "07:13:14", "entrada"),
            marca("2026-07-23", "14:30:07", "salida"),
        ])
        assert len(filas) == 1

    def test_ignora_marcaciones_fuera_del_rango(self):
        filas = resumir_rango(date(2026, 7, 23), date(2026, 7, 23), [
            marca("2026-07-22", "07:00:00", "entrada"),
            marca("2026-07-23", "07:13:14", "entrada"),
        ])
        assert len(filas) == 1
        assert filas[0]["total_marcaciones"] == 1

    def test_rango_invertido_devuelve_vacio(self):
        assert resumir_rango(date(2026, 7, 25), date(2026, 7, 23), []) == []
