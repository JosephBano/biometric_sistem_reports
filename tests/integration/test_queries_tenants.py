"""
Tests de integración de `db.queries.tenants` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import uuid

import pytest

from db import set_thread_tenant
from db.queries.tenants import (
    actualizar_tenant,
    crear_tenant,
    eliminar_tenant_de_public,
    get_tenant_by_slug,
    get_tipos_persona,
    insertar_tipo_persona,
    listar_tenants,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def tenant_test():
    """Crea un tenant de prueba y lo limpia al final."""
    slug = f"test-{uuid.uuid4().hex[:8]}"
    t = crear_tenant(
        nombre="Tenant Test",
        nombre_corto="Test",
        slug=slug,
    )
    yield t
    eliminar_tenant_de_public(slug)


class TestCrearTenant:

    def test_crear_tenant_retorna_dict(self, tenant_test):
        """Crear tenant retorna dict con id, nombre, slug."""
        assert tenant_test["nombre"] == "Tenant Test"
        assert tenant_test["nombre_corto"] == "Test"
        assert tenant_test["slug"].startswith("test-")
        assert tenant_test["activo"] is True

    def test_crear_tenant_zona_horaria_default(self, tenant_test):
        """Sin zona_horaria, usa 'America/Guayaquil'."""
        assert tenant_test["zona_horaria"] == "America/Guayaquil"


class TestGetTenantBySlug:

    def test_get_tenant_by_slug_existente(self, tenant_test):
        """get_tenant_by_slug retorna el tenant si existe."""
        result = get_tenant_by_slug(tenant_test["slug"])
        assert result is not None
        assert result["id"] == tenant_test["id"]

    def test_get_tenant_by_slug_inexistente_retorna_none(self):
        """get_tenant_by_slug con slug inexistente → None."""
        result = get_tenant_by_slug("slug-que-no-existe-9999")
        assert result is None


class TestListarTenants:

    def test_listar_tenants_incluye_istpet(self, tenant_test):
        """listar_tenants siempre incluye al menos el tenant 'istpet'."""
        result = listar_tenants()
        assert len(result) >= 1
        slugs = [t["slug"] for t in result]
        # istpet fue creado por init_db()
        assert "istpet" in slugs

    def test_listar_tenants_ordenados_por_nombre(self, tenant_test):
        """Los tenants vienen ordenados por nombre."""
        result = listar_tenants()
        nombres = [t["nombre"] for t in result]
        assert nombres == sorted(nombres)


class TestActualizarTenant:

    def test_actualizar_nombre(self, tenant_test):
        """actualizar_tenant cambia el campo 'nombre'."""
        result = actualizar_tenant(
            tenant_test["id"],
            {"nombre": "Nuevo Nombre"},
        )
        assert result["nombre"] == "Nuevo Nombre"
        # Y se persiste
        result2 = get_tenant_by_slug(tenant_test["slug"])
        assert result2["nombre"] == "Nuevo Nombre"

    def test_actualizar_activo(self, tenant_test):
        """actualizar_tenant puede cambiar 'activo'."""
        result = actualizar_tenant(
            tenant_test["id"],
            {"activo": False},
        )
        assert result["activo"] is False

    def test_actualizar_sin_campos_retorna_none(self, tenant_test):
        """Sin campos válidos en `datos`, retorna None sin tocar la BD."""
        result = actualizar_tenant(
            tenant_test["id"],
            {"slug": "nuevo-slug"},  # 'slug' no está en allowed_fields
        )
        assert result is None

    def test_actualizar_tenant_inexistente_retorna_none(self):
        """actualizar_tenant con id inexistente retorna None."""
        result = actualizar_tenant(
            "00000000-0000-0000-0000-000000000000",
            {"nombre": "X"},
        )
        assert result is None


class TestEliminarTenant:

    def test_eliminar_tenant_existente_retorna_true(self, tenant_test):
        """Eliminar un tenant que existe retorna True."""
        result = eliminar_tenant_de_public(tenant_test["slug"])
        assert result is True
        # Ya no existe
        assert get_tenant_by_slug(tenant_test["slug"]) is None

    def test_eliminar_tenant_inexistente_retorna_false(self):
        """Eliminar un tenant que no existe retorna False."""
        result = eliminar_tenant_de_public("no-existe-12345")
        assert result is False


class TestTiposPersona:

    def test_get_tipos_persona_istpet(self):
        """istpet tiene tipos de persona sembrados por init_db()."""
        result = get_tipos_persona("istpet")
        # init_db() crea 'empleado' y 'contratista' o similar
        assert isinstance(result, list)
        nombres = [t["nombre"] for t in result]
        assert len(nombres) >= 1

    def test_insertar_tipo_persona_nuevo(self):
        """Insertar un tipo de persona nuevo lo agrega a la lista."""
        nombre = f"test-tipo-{uuid.uuid4().hex[:8]}"
        result = insertar_tipo_persona("istpet", nombre, "Test")
        assert result["nombre"] == nombre
        assert result["activo"] is True

        # Aparece en get_tipos_persona
        tipos = get_tipos_persona("istpet")
        nombres = [t["nombre"] for t in tipos]
        assert nombre in nombres
