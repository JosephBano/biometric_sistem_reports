"""
Tests de integración de las queries de asignación masiva y detalle de horarios por grupo funcional
(`db.queries.horarios_grupo_funcional`).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from db import set_thread_tenant
from db.queries.grupos import crear_grupo_funcional
from db.queries.horarios_grupo_funcional import (
    asignar_personas_masivo_a_grupo_funcional,
    listar_personas_detalladas_en_grupo_funcional,
    procesar_csv_personas_grupo_funcional,
)
from db.queries.personas_crud import crear_persona
from db.queries.tenants import insertar_tipo_persona

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def grupo_funcional_test():
    """Crea un grupo funcional de prueba."""
    tipo = insertar_tipo_persona("istpet", f"tipo-gf-{uuid.uuid4().hex[:6]}")
    gf = crear_grupo_funcional(
        nombre=f"GF-Test-{uuid.uuid4().hex[:6]}",
        tipo_persona_id=tipo["id"],
    )
    return gf


class TestAsignacionMasivaYDetalleGF:

    def test_asignar_personas_masivo_y_listar_detalladas(self, grupo_funcional_test):
        """Asigna múltiples personas y verifica listar_personas_detalladas_en_grupo_funcional."""
        p1 = crear_persona(nombre=f"Persona A {uuid.uuid4().hex[:4]}", identificacion="1101")
        p2 = crear_persona(nombre=f"Persona B {uuid.uuid4().hex[:4]}", identificacion="1102")

        count = asignar_personas_masivo_a_grupo_funcional(
            grupo_funcional_id=grupo_funcional_test["id"],
            persona_ids=[p1["id"], p2["id"]],
            fecha_inicio=date.today(),
            es_principal=True,
        )
        assert count == 2

        personas_gf = listar_personas_detalladas_en_grupo_funcional(grupo_funcional_test["id"])
        ids_en_gf = [p["persona_id"] for p in personas_gf]
        assert p1["id"] in ids_en_gf
        assert p2["id"] in ids_en_gf

    def test_asignar_masivo_lista_vacia(self, grupo_funcional_test):
        """Asignar lista vacía retorna 0 sin fallar."""
        res = asignar_personas_masivo_a_grupo_funcional(
            grupo_funcional_id=grupo_funcional_test["id"],
            persona_ids=[],
            fecha_inicio=date.today(),
        )
        assert res == 0

    def test_procesar_csv_personas_grupo_funcional(self, tmp_path, grupo_funcional_test):
        """Procesa CSV vinculando y creando personas para el grupo funcional."""
        csv_file = tmp_path / "personas_gf.csv"
        csv_file.write_text(
            "nombre,identificacion,id_biometrico\n"
            f"Colaborador Uno {uuid.uuid4().hex[:4]},99001,101\n"
            f"Colaborador Dos {uuid.uuid4().hex[:4]},99002,102\n",
            encoding="utf-8",
        )

        res = procesar_csv_personas_grupo_funcional(
            filepath=str(csv_file),
            grupo_funcional_id=grupo_funcional_test["id"],
            fecha_inicio=date.today(),
        )
        assert res["exito"] is True
        assert res["procesadas"] == 2
        assert len(res["errores"]) == 0

    def test_procesar_csv_grupo_inexistente(self, tmp_path):
        """Si el grupo no existe, retorna error controlado."""
        csv_file = tmp_path / "dummy.csv"
        csv_file.write_text("nombre,identificacion\nTest,123\n", encoding="utf-8")
        fake_id = str(uuid.uuid4())
        res = procesar_csv_personas_grupo_funcional(
            filepath=str(csv_file),
            grupo_funcional_id=fake_id,
            fecha_inicio=date.today(),
        )
        assert res["exito"] is False
        assert "Grupo no encontrado" in res["error"]
