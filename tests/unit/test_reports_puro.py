"""
Tests unitarios de funciones puras en `app.domain.reports` (Fase 7.4).

Estas son las funciones con mayor peso en LOC que no requieren BD ni
dispositivos. Apuntan a subir la cobertura global al ≥60% sin agregar
complejidad de fixtures.
"""
from __future__ import annotations

import pytest

from app.domain.reports import (
    DEFAULT_CONFIG,
    DEFAULT_FILTROS,
    deduplicar,
    filtrar_excluidos,
    parse_config,
)


class TestParseConfig:

    def test_parse_config_con_excluidos(self):
        """parse_config extrae excluidos del dict de entrada."""
        cfg = parse_config({"excluidos": ["juan", "maria"]})
        assert cfg["excluidos"] == ["juan", "maria"]
        assert cfg["duplicado_min"] == DEFAULT_CONFIG["duplicado_min"]

    def test_parse_config_sin_excluidos(self):
        """parse_config sin excluidos → lista vacía."""
        cfg = parse_config({})
        assert cfg["excluidos"] == []

    def test_parse_config_excluidos_none(self):
        """parse_config con excluidos=None → lista vacía."""
        cfg = parse_config({"excluidos": None})
        assert cfg["excluidos"] == []


class TestFiltrarExcluidos:

    def test_filtrar_excluidos_elimina_nombres(self):
        """Los nombres en `excluidos` se eliminan case-insensitive."""
        registros = [
            {"nombre": "Juan Perez"},
            {"nombre": "Maria Lopez"},
            {"nombre": "Carlos Ruiz"},
        ]
        resultado = filtrar_excluidos(registros, ["juan"])
        assert len(resultado) == 2
        assert all(r["nombre"] != "Juan Perez" for r in resultado)

    def test_filtrar_excluidos_lista_vacia(self):
        """Sin excluidos, retorna todos los registros."""
        registros = [{"nombre": "Juan"}, {"nombre": "Maria"}]
        assert filtrar_excluidos(registros, []) == registros

    def test_filtrar_excluidos_no_encontrados(self):
        """Si el nombre no existe en registros, no afecta nada."""
        registros = [{"nombre": "Juan"}]
        resultado = filtrar_excluidos(registros, ["pedro", "maria"])
        assert resultado == registros


class TestDeduplicar:

    def test_deduplicar_mezcla_marcaciones_cercanas(self):
        """Dos marcaciones dentro de max_min se consolidan en una."""
        from datetime import datetime, timedelta

        base = datetime(2026, 7, 2, 8, 0, 0)
        registros = [
            {
                "nombre": "Juan",
                "id_usuario": "1",
                "fecha": "2026-07-02",
                "datetime": base,
                "hora": base.time(),
                "tipo": "entrada",
            },
            {
                "nombre": "Juan",
                "id_usuario": "1",
                "fecha": "2026-07-02",
                "datetime": base + timedelta(seconds=10),
                "hora": (base + timedelta(seconds=10)).time(),
                "tipo": "entrada",
            },
        ]
        resultado, log = deduplicar(registros, max_min=0.5)
        # Solo queda una marcación consolidada
        assert len(resultado) == 1
        assert log  # log no vacío

    def test_deduplicar_respeta_marcaciones_separadas(self):
        """Marcaciones con >max_min entre sí se conservan."""
        from datetime import datetime, timedelta

        base = datetime(2026, 7, 2, 8, 0, 0)
        registros = [
            {
                "nombre": "Juan",
                "id_usuario": "1",
                "fecha": "2026-07-02",
                "datetime": base,
                "hora": base.time(),
                "tipo": "entrada",
            },
            {
                "nombre": "Juan",
                "id_usuario": "1",
                "fecha": "2026-07-02",
                "datetime": base + timedelta(hours=1),
                "hora": (base + timedelta(hours=1)).time(),
                "tipo": "salida",
            },
        ]
        resultado, log = deduplicar(registros, max_min=0.5)
        # Las dos marcaciones están a 1h de distancia → se conservan
        assert len(resultado) == 2
        assert not log

    def test_deduplicar_lista_vacia(self):
        """Sin registros, retorna lista vacía y log vacío."""
        resultado, log = deduplicar([], max_min=0.5)
        assert resultado == []
        assert not log


class TestDefaultConfig:

    def test_default_config_tiene_claves_esperadas(self):
        """DEFAULT_CONFIG debe tener las claves mínimas del sistema."""
        assert "duplicado_min" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["duplicado_min"], (int, float))

    def test_default_filtros_tiene_claves_esperadas(self):
        """DEFAULT_FILTROS tiene todas las flags de secciones."""
        claves_esperadas = {
            "mostrar_ausencias",
            "mostrar_tardanza_severa",
            "mostrar_almuerzo",
            "mostrar_incompletos",
        }
        assert claves_esperadas.issubset(DEFAULT_FILTROS.keys())

    def test_default_filtros_son_booleanos(self):
        """Todos los valores de DEFAULT_FILTROS son bool."""
        for k, v in DEFAULT_FILTROS.items():
            assert isinstance(v, bool), f"{k} debe ser bool, es {type(v)}"
