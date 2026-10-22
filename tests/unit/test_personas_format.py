"""
Tests unitarios de formateo e inversión de nombres (`db.queries.personas.invertir_nombre_apellido`).
"""
from __future__ import annotations

from db.queries.personas import invertir_nombre_apellido


class TestInvertirNombreApellido:

    def test_nombre_vacio_o_none(self):
        assert invertir_nombre_apellido("") == ""
        assert invertir_nombre_apellido(None) == ""
        assert invertir_nombre_apellido(123) == ""

    def test_una_sola_palabra(self):
        assert invertir_nombre_apellido("Alexander") == "Alexander"

    def test_nombre_con_coma_se_respeta(self):
        assert invertir_nombre_apellido("Martinez, Alexander") == "Martinez, Alexander"

    def test_dos_palabras_nombre_apellido(self):
        # 'Nombre Apellido' -> 'Apellido Nombre'
        assert invertir_nombre_apellido("Alexander Martinez") == "Martinez Alexander"

    def test_tres_palabras_un_nombre_dos_apellidos(self):
        # 'Nombre Apellido1 Apellido2' -> 'Apellido1 Apellido2 Nombre'
        assert invertir_nombre_apellido("Alexander Martinez Gomez") == "Martinez Gomez Alexander"

    def test_cuatro_palabras_dos_nombres_dos_apellidos(self):
        # 'Nombre1 Nombre2 Apellido1 Apellido2' -> 'Apellido1 Apellido2 Nombre1 Nombre2'
        assert (
            invertir_nombre_apellido("Alexander David Martinez Gomez")
            == "Martinez Gomez Alexander David"
        )
