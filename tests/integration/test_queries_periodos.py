"""
Tests de integración de `db.queries.periodos` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from db import set_thread_tenant
from db.queries.periodos import (
    agregar_personas_a_periodo_bulk,
    archivar_periodo,
    cerrar_periodo,
    cerrar_periodos_vencidos,
    crear_periodo,
    eliminar_periodo,
    get_periodo,
    listar_periodos_activos,
    listar_periodos_historial,
    procesar_csv_personas_periodo,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def periodo_test():
    """Crea un período de prueba."""
    nombre = f"Per-Test-{uuid.uuid4().hex[:8]}"
    p = crear_periodo(
        nombre=nombre,
        fecha_inicio=date(2026, 7, 1),
        fecha_fin=date(2026, 12, 31),
        descripcion="Período de prueba",
    )
    yield p


class TestCrearPeriodo:

    def test_crear_periodo_minimo(self):
        """Crear un período con argumentos mínimos."""
        nombre = f"Per-{uuid.uuid4().hex[:8]}"
        p = crear_periodo(
            nombre=nombre,
            fecha_inicio=date(2026, 7, 1),
        )
        assert p["nombre"] == nombre
        assert p["estado"] == "activo"
        # fecha_fin opcional → puede ser None

    def test_crear_periodo_con_descripcion(self):
        """Crear un período con descripción."""
        nombre = f"Per-{uuid.uuid4().hex[:8]}"
        p = crear_periodo(
            nombre=nombre,
            fecha_inicio=date(2026, 8, 1),
            fecha_fin=date(2026, 12, 31),
            descripcion="Período docentes",
        )
        assert p["descripcion"] == "Período docentes"


class TestGetPeriodo:

    def test_get_periodo_existente(self, periodo_test):
        """get_periodo retorna el período creado."""
        result = get_periodo(periodo_test["id"])
        assert result is not None
        assert result["id"] == periodo_test["id"]
        assert result["nombre"] == periodo_test["nombre"]

    def test_get_periodo_inexistente(self):
        """get_periodo con UUID inexistente → None."""
        result = get_periodo("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestListarPeriodos:

    def test_listar_periodos_activos(self, periodo_test):
        """listar_periodos_activos incluye el período de prueba."""
        result = listar_periodos_activos()
        nombres = [p["nombre"] for p in result]
        assert periodo_test["nombre"] in nombres

    def test_listar_periodos_historial(self, periodo_test):
        """listar_periodos_historial retorna la lista completa."""
        result = listar_periodos_historial()
        assert isinstance(result, list)
        # El período de prueba debe estar en el historial (puede estar como activo también)


class TestCerrarArchivar:

    def test_cerrar_periodo(self, periodo_test):
        """cerrar_periodo cambia el estado a 'cerrado' (no retorna nada)."""
        cerrar_periodo(periodo_test["id"])
        p = get_periodo(periodo_test["id"])
        assert p["estado"] == "cerrado"

    def test_archivar_periodo(self, periodo_test):
        """archivar_periodo cambia el estado a 'archivado' (no retorna nada)."""
        archivar_periodo(periodo_test["id"])
        p = get_periodo(periodo_test["id"])
        assert p["estado"] == "archivado"


class TestEliminarPeriodo:

    def test_eliminar_periodo(self, periodo_test):
        """eliminar_periodo borra el período."""
        result = eliminar_periodo(periodo_test["id"])
        assert result is True
        assert get_periodo(periodo_test["id"]) is None

    def test_eliminar_periodo_inexistente(self):
        """eliminar_periodo con id inexistente → False."""
        result = eliminar_periodo("00000000-0000-0000-0000-000000000000")
        assert result is False


class TestCerrarVencidos:

    def test_cerrar_periodos_vencidos_ejecuta_sin_error(self):
        """cerrar_periodos_vencidos ejecuta sin lanzar excepciones."""
        # Solo verifica que la función existe y no falla
        try:
            cerrar_periodos_vencidos()
        except Exception as e:
            pytest.fail(f"cerrar_periodos_vencidos falló: {e}")


class TestProcesarCsv:

    def test_procesar_csv_personas_periodo_csv_vacio(self, tmp_path, periodo_test):
        """CSV vacío retorna dict con exito=True y procesadas=0."""
        csv_path = tmp_path / "personas.csv"
        csv_path.write_text("id_usuario,nombre\n", encoding="utf-8")

        result = procesar_csv_personas_periodo(
            str(csv_path), periodo_test["id"], tipo_persona_id=None,
        )
        assert result["exito"] is True
        assert result["procesadas"] == 0

    def test_procesar_csv_personas_periodo_basico(self, tmp_path, periodo_test):
        """CSV con personas retorna dict con exito=True."""
        csv_path = tmp_path / "personas.csv"
        csv_path.write_text(
            "id_usuario,nombre\n"
            "123,Persona Test\n"
            "456,Otra Persona\n",
            encoding="utf-8",
        )

        result = procesar_csv_personas_periodo(
            str(csv_path), periodo_test["id"], tipo_persona_id=None,
        )
        assert result["exito"] is True


class TestAgregarPersonasBulk:

    def test_agregar_personas_bulk_ejecuta(self, periodo_test):
        """agregar_personas_a_periodo_bulk acepta lista vacía."""
        # Con lista vacía, retorna dict sin error
        result = agregar_personas_a_periodo_bulk(
            periodo_id=periodo_test["id"],
            personas_ids=[],
        )
        assert isinstance(result, dict)
