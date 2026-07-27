"""
Tests de integración de `db.queries.grupos` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid

import pytest

from db import set_thread_tenant
from db.queries.grupos import (
    actualizar_categoria,
    actualizar_grupo,
    crear_categoria,
    crear_grupo,
    listar_categorias,
    listar_grupos,
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


class TestCategorias:

    def test_crear_categoria_sin_tipo_persona(self):
        """Crear categoría sin tipo_persona_id lo permite (es opcional)."""
        nombre = f"Cat {uuid.uuid4().hex[:8]}"
        result = crear_categoria(nombre)
        assert result["nombre"] == nombre
        assert result["activo"] is True

    def test_crear_categoria_con_tipo_persona(self, tipo_persona_test):
        """Crear categoría con tipo_persona_id lo asocia."""
        nombre = f"Cat {uuid.uuid4().hex[:8]}"
        result = crear_categoria(nombre, tipo_persona_test["id"])
        assert result["nombre"] == nombre
        assert result["tipo_persona_id"] == tipo_persona_test["id"]

    def test_listar_categorias_todas(self):
        """listar_categorias sin filtro retorna todas."""
        result = listar_categorias()
        assert isinstance(result, list)

    def test_listar_categorias_filtradas_por_tipo(self, tipo_persona_test):
        """listar_categorias(tipo_persona_id=X) filtra por tipo."""
        # Crear 2 categorías, una con tipo y otra sin
        crear_categoria(f"ConTipo-{uuid.uuid4().hex[:8]}", tipo_persona_test["id"])
        crear_categoria(f"SinTipo-{uuid.uuid4().hex[:8]}")

        result = listar_categorias(tipo_persona_id=tipo_persona_test["id"])
        # Solo la primera debe aparecer
        assert all(
            c["tipo_persona_id"] == tipo_persona_test["id"]
            for c in result
        )

    def test_actualizar_categoria_nombre(self):
        """actualizar_categoria cambia el nombre."""
        c = crear_categoria(f"Orig {uuid.uuid4().hex[:8]}")
        result = actualizar_categoria(c["id"], {"nombre": "Updated"})
        assert result["nombre"] == "Updated"

    def test_actualizar_categoria_sin_campos_validos(self):
        """actualizar_categoria con datos vacíos → None."""
        c = crear_categoria(f"Cat {uuid.uuid4().hex[:8]}")
        result = actualizar_categoria(c["id"], {"campo_invalido": "x"})
        assert result is None
