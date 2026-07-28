"""
Tests de integración de `db.queries.grupos` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid

import pytest

from db import set_thread_tenant
from db.queries.grupos import (
    actualizar_grupo,
    actualizar_grupo_funcional,
    crear_grupo,
    crear_grupo_funcional,
    listar_grupos,
    listar_grupos_funcionales,
)
from db.queries.tenants import get_tipos_persona, insertar_tipo_persona


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def tipo_persona_test():
    """Crea un tipo de persona para asociar categorías."""
    nombre = f"tipo-test-{uuid.uuid4().hex[:8]}"
    result = insertar_tipo_persona("istpet", nombre)
    yield result
    # No hay función para borrar tipo_persona; queda como dato de prueba


class TestGrupos:

    def test_listar_grupos_vacio_al_inicio(self):
        """Sin grupos creados, retorna lista (puede tener los sembrados)."""
        result = listar_grupos()
        assert isinstance(result, list)

    def test_crear_grupo_retorna_dict(self):
        """Crear grupo retorna dict con id, nombre, tipo_grupo, activo."""
        nombre = f"Grupo Test {uuid.uuid4().hex[:8]}"
        result = crear_grupo(nombre, "docente")
        assert result["nombre"] == nombre
        assert result["tipo_grupo"] == "docente"
        assert result["activo"] is True

    def test_crear_grupo_tipo_default(self):
        """Sin tipo_grupo, usa 'general' por default."""
        nombre = f"G {uuid.uuid4().hex[:8]}"
        result = crear_grupo(nombre)
        assert result["tipo_grupo"] == "general"

    def test_listar_grupos_activo_true(self):
        """listar_grupos(activo=True) solo retorna grupos activos."""
        nombre = f"G {uuid.uuid4().hex[:8]}"
        crear_grupo(nombre)
        result = listar_grupos(activo=True)
        assert all(g["activo"] for g in result)

    def test_listar_grupos_ordenados_por_nombre(self):
        """Los grupos vienen ordenados alfabéticamente."""
        nombres = [f"ZZZ-{uuid.uuid4().hex[:8]}", f"AAA-{uuid.uuid4().hex[:8]}"]
        for n in nombres:
            crear_grupo(n)
        result = listar_grupos()
        lista_nombres = [g["nombre"] for g in result]
        # Verificar ordenamiento
        assert lista_nombres == sorted(lista_nombres)

    def test_actualizar_grupo_nombre(self):
        """actualizar_grupo cambia el nombre."""
        nombre_orig = f"Orig {uuid.uuid4().hex[:8]}"
        g = crear_grupo(nombre_orig)

        result = actualizar_grupo(g["id"], {"nombre": "Nuevo Nombre"})
        assert result["nombre"] == "Nuevo Nombre"

    def test_actualizar_grupo_activo_false(self):
        """actualizar_grupo puede desactivar."""
        g = crear_grupo(f"G {uuid.uuid4().hex[:8]}")
        result = actualizar_grupo(g["id"], {"activo": False})
        assert result["activo"] is False

    def test_actualizar_grupo_sin_campos_validos(self):
        """actualizar_grupo con datos vacíos → None."""
        g = crear_grupo(f"G {uuid.uuid4().hex[:8]}")
        result = actualizar_grupo(g["id"], {"campo_invalido": "x"})
        assert result is None


class TestGruposFuncionales:

    def test_crear_grupo_funcional_sin_tipo_persona(self):
        """Crear grupo funcional sin tipo_persona_id lo permite (es opcional)."""
        nombre = f"GF {uuid.uuid4().hex[:8]}"
        result = crear_grupo_funcional(nombre)
        assert result["nombre"] == nombre
        assert result["activo"] is True

    def test_crear_grupo_funcional_con_tipo_persona(self, tipo_persona_test):
        """Crear grupo funcional con tipo_persona_id lo asocia."""
        nombre = f"GF {uuid.uuid4().hex[:8]}"
        result = crear_grupo_funcional(nombre, tipo_persona_test["id"])
        assert result["nombre"] == nombre
        assert result["tipo_persona_id"] == tipo_persona_test["id"]

    def test_listar_grupos_funcionales_todos(self):
        """listar_grupos_funcionales sin filtro retorna todos."""
        result = listar_grupos_funcionales()
        assert isinstance(result, list)

    def test_listar_grupos_funcionales_filtrados_por_tipo(self, tipo_persona_test):
        """listar_grupos_funcionales(tipo_persona_id=X) filtra por tipo."""
        crear_grupo_funcional(f"ConTipo-{uuid.uuid4().hex[:8]}", tipo_persona_test["id"])
        crear_grupo_funcional(f"SinTipo-{uuid.uuid4().hex[:8]}")

        result = listar_grupos_funcionales(tipo_persona_id=tipo_persona_test["id"])
        assert all(
            gf["tipo_persona_id"] == tipo_persona_test["id"]
            for gf in result
        )

    def test_actualizar_grupo_funcional_nombre(self):
        """actualizar_grupo_funcional cambia el nombre."""
        gf = crear_grupo_funcional(f"Orig {uuid.uuid4().hex[:8]}")
        result = actualizar_grupo_funcional(gf["id"], {"nombre": "Updated"})
        assert result["nombre"] == "Updated"

    def test_actualizar_grupo_funcional_sin_campos_validos(self):
        """actualizar_grupo_funcional con datos vacíos → None."""
        gf = crear_grupo_funcional(f"GF {uuid.uuid4().hex[:8]}")
        result = actualizar_grupo_funcional(gf["id"], {"campo_invalido": "x"})
        assert result is None
