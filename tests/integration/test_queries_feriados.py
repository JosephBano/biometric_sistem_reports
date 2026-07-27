"""
Tests de integración de `db.queries.feriados` (Fase 7.4 — cobertura).

Usa `pgserver` (fixture `app` definida en `tests/integration/conftest.py`).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from db import set_thread_tenant
from db.queries.feriados import (
    eliminar_feriado,
    get_feriados,
    get_feriados_set,
    importar_feriados_csv,
    insertar_feriado,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant(app):
    """Asegura que la conexión use el tenant `istpet` para todas las queries."""
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


class TestInsertarFeriado:

    def test_insertar_feriado_devuelve_dict(self):
        """Insertar retorna dict con fecha, descripcion, tipo."""
        result = insertar_feriado("2026-12-25", "Navidad", "nacional")
        assert result["fecha"] == "2026-12-25"
        assert result["descripcion"] == "Navidad"
        assert result["tipo"] == "nacional"

    def test_insertar_feriado_tipo_default(self):
        """Sin `tipo`, usa 'nacional' por default."""
        result = insertar_feriado("2026-01-01", "Año Nuevo")
        assert result["tipo"] == "nacional"

    def test_insertar_feriado_duplicado_reemplaza(self):
        """Insertar dos veces la misma fecha reemplaza (UPSERT)."""
        insertar_feriado("2026-12-25", "Navidad v1", "nacional")
        result = insertar_feriado("2026-12-25", "Navidad v2", "religioso")
        assert result["descripcion"] == "Navidad v2"
        assert result["tipo"] == "religioso"


class TestGetFeriados:

    def test_get_feriados_sin_filtros(self):
        """Sin filtros, retorna todos los feriados ordenados por fecha."""
        insertar_feriado("2026-07-01", "F1")
        insertar_feriado("2026-07-02", "F2")
        insertar_feriado("2026-06-15", "F0")

        result = get_feriados()
        assert len(result) >= 3
        fechas = [f["fecha"] for f in result]
        assert fechas == sorted(fechas)  # ordenados

    def test_get_feriados_con_rango(self):
        """Con rango, filtra por fecha_inicio/fecha_fin."""
        insertar_feriado("2026-01-01", "Inicio")
        insertar_feriado("2026-06-15", "Mitad")
        insertar_feriado("2026-12-25", "Fin")

        result = get_feriados("2026-05-01", "2026-08-01")
        fechas = [f["fecha"] for f in result]
        assert "2026-06-15" in fechas
        assert "2026-01-01" not in fechas
        assert "2026-12-25" not in fechas


class TestGetFeriadosSet:

    def test_get_feriados_set_retorna_set_de_dates(self):
        """`get_feriados_set` retorna set de objetos `date`."""
        insertar_feriado("2026-12-25", "Navidad")
        insertar_feriado("2027-01-01", "Año Nuevo")

        result = get_feriados_set()
        assert isinstance(result, set)
        assert date(2026, 12, 25) in result
        assert date(2027, 1, 1) in result

    def test_get_feriados_set_lookup_rapido(self):
        """`in` sobre el set debe ser O(1)."""
        insertar_feriado("2026-12-25", "Navidad")
        result = get_feriados_set()
        # Uso típico en análisis de asistencia: ¿esta fecha es feriado?
        assert date(2026, 12, 25) in result
        assert date(2026, 12, 26) not in result


class TestEliminarFeriado:

    def test_eliminar_feriado_existente_retorna_true(self):
        """Eliminar un feriado existente retorna True."""
        insertar_feriado("2026-12-25", "Navidad")
        assert eliminar_feriado("2026-12-25") is True
        # Ya no existe
        fechas = [f["fecha"] for f in get_feriados()]
        assert "2026-12-25" not in fechas

    def test_eliminar_feriado_inexistente_retorna_false(self):
        """Eliminar un feriado que no existe retorna False."""
        assert eliminar_feriado("2099-01-01") is False


class TestImportarFeriadosCsv:

    def test_importar_csv_basico(self, tmp_path):
        """Importar un CSV con formato correcto carga todos los feriados."""
        csv_path = tmp_path / "feriados.csv"
        csv_path.write_text(
            "fecha,descripcion,tipo\n"
            "2026-12-25,Navidad,religioso\n"
            "2027-01-01,Año Nuevo,nacional\n"
            "2027-05-01,Día del Trabajo,nacional\n",
            encoding="utf-8",
        )

        count = importar_feriados_csv(str(csv_path))
        assert count == 3

        # Verificar que están cargados
        fechas = [f["fecha"] for f in get_feriados()]
        assert "2026-12-25" in fechas
        assert "2027-01-01" in fechas
        assert "2027-05-01" in fechas

    def test_importar_csv_salta_filas_vacias(self, tmp_path):
        """Filas sin fecha o descripcion se saltan."""
        csv_path = tmp_path / "feriados.csv"
        csv_path.write_text(
            "fecha,descripcion,tipo\n"
            "2026-12-25,Navidad,nacional\n"
            ",Sin Fecha,\n"  # sin fecha → skip
            "2026-07-01,,nacional\n"  # sin descripcion → skip
            "2026-08-01,F3,nacional\n",
            encoding="utf-8",
        )

        count = importar_feriados_csv(str(csv_path))
        # Solo se cargan 2 (Navidad y F3)
        assert count == 2

    def test_importar_csv_tipo_default(self, tmp_path):
        """Si `tipo` está vacío, usa 'nacional' como default."""
        csv_path = tmp_path / "feriados.csv"
        csv_path.write_text(
            "fecha,descripcion,tipo\n"
            "2026-09-01,Sin tipo,\n",  # tipo vacío
            encoding="utf-8",
        )

        importar_feriados_csv(str(csv_path))
        result = get_feriados("2026-09-01", "2026-09-01")
        assert result[0]["tipo"] == "nacional"
