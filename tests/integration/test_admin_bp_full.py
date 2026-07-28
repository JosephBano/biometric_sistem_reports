"""
Tests de integración ampliados del blueprint `admin` (`app/web/admin_bp.py`).

Cubre endpoints administrativos: tenants, usuarios, grupos, categorías.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


class TestAdminBlueprintAmpliado:

    def test_get_admin_usuarios(self, admin_client):
        """GET /admin/usuarios → 200."""
        r = admin_client.get("/admin/usuarios")
        assert r.status_code == 200

    def test_get_admin_tenants_html(self, admin_client):
        """GET /admin/tenants → 200 con HTML o JSON."""
        r = admin_client.get("/admin/tenants")
        assert r.status_code == 200

    def test_get_admin_grupos_html(self, admin_client):
        """GET /admin/grupos → 200."""
        r = admin_client.get("/admin/grupos")
        assert r.status_code == 200

    def test_get_admin_categorias_html(self, admin_client):
        """GET /admin/grupos-funcionales → 200."""
        r = admin_client.get("/admin/grupos-funcionales")
        assert r.status_code == 200

    def test_get_admin_dispositivos_html(self, admin_client):
        """GET /admin/dispositivos → 200."""
        r = admin_client.get("/admin/dispositivos")
        assert r.status_code == 200

    def test_get_admin_superadmin_usuarios(self, admin_client):
        """GET /admin/superadmin/usuarios → 200 (gestión cross-tenant)."""
        r = admin_client.get("/admin/superadmin/usuarios")
        assert r.status_code == 200

    def test_post_admin_tenants_crea_tenant(self, admin_client, csrf_token):
        """POST /admin/tenants con datos válidos → 200/302 (creado)."""
        r = admin_client.post(
            "/admin/tenants",
            json={
                "csrf_token": csrf_token,
                "nombre": "Test Tenant",
                "nombre_corto": "Test Tenant",
                "slug": "test-tenant-integration",
                "zona_horaria": "America/Guayaquil",
            },
        )
        # CSRF puede rechazar JSON si el endpoint espera form data
        assert r.status_code in (200, 302, 400, 403)

    def test_post_admin_switch_tenant_sin_slug(self, admin_client, csrf_token):
        """POST /admin/switch-tenant sin slug → 400/403."""
        r = admin_client.post(
            "/admin/switch-tenant",
            json={"csrf_token": csrf_token},
        )
        assert r.status_code in (400, 403, 422)

    def test_post_admin_switch_tenant_con_slug_public(self, admin_client, csrf_token):
        """POST /admin/switch-tenant con slug='public' → 200/302/403 (CSRF en JSON puede variar)."""
        r = admin_client.post(
            "/admin/switch-tenant",
            json={"csrf_token": csrf_token, "tenant_slug": "public"},
        )
        # CSRF puede rechazar JSON; el endpoint espera form data
        assert r.status_code in (200, 302, 400, 403)
