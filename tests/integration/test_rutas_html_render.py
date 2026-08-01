"""
Smoke tests de las vistas HTML que no tenían cobertura de ruta.

Motivación (incidente de producción 2026-07-28): tras el rename
`categorias -> grupos_funcionales`, `/personas` y
`/admin/horarios-grupo-funcional` devolvían 500 con

    TypeError: listar_grupos_funcionales() got an unexpected keyword
    argument 'activo'

Los blueprints llamaban `listar_grupos_funcionales(activo=True)` pero la
query no aceptaba ese parámetro. Ningún test ejercitaba esas rutas, así
que el desajuste de firma solo se detectó en producción.

Estos tests solo verifican que la vista renderiza (no 500). Es
deliberadamente superficial: su valor está en cubrir el hueco de "la ruta
ni siquiera se llama en los tests", que es lo que dejó pasar el bug.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


# Vistas HTML accesibles con rol admin. Se listan explícitamente en vez de
# descubrirlas del url_map para que agregar una ruta nueva sin test sea
# una decisión consciente.
RUTAS_ADMIN = [
    "/personas",
    "/personas/historico",
    "/admin/grupos-funcionales",
    "/admin/horarios-grupo-funcional",
    "/admin/horarios-default-grupo",
    "/admin/asignacion-masiva-grupo-funcional",
    "/admin/grupos",
    "/admin/usuarios",
    "/admin/dispositivos",
    "/configuracion",
    "/periodos",
    "/reportes",
    "/analytics",
]


class TestVistasHtmlRenderizan:

    @pytest.mark.parametrize("ruta", RUTAS_ADMIN)
    def test_ruta_no_devuelve_500(self, admin_client, ruta):
        r = admin_client.get(ruta)
        assert r.status_code != 500, (
            f"{ruta} devolvió 500:\n{r.get_data(as_text=True)[:1200]}"
        )
        # 200 (render) o 302 (redirect por estado del tenant) son válidos;
        # lo que no puede pasar es una excepción no controlada.
        assert r.status_code in (200, 302), (
            f"{ruta} devolvió {r.status_code} inesperado."
        )


class TestFiltroActivoEnGruposFuncionales:
    """Cubre la firma que rompió en producción."""

    def test_acepta_filtro_activo(self, app, tenant_id):
        from db import set_thread_tenant
        from db.connection import clear_thread_tenant
        from db.queries.grupos import listar_grupos_funcionales

        set_thread_tenant("istpet")
        try:
            # La llamada exacta que hacen people_bp y horarios_gf_bp.
            solo_activos = listar_grupos_funcionales(activo=True)
            todos = listar_grupos_funcionales()
        finally:
            clear_thread_tenant()

        assert all(g["activo"] for g in solo_activos), (
            "activo=True devolvió grupos inactivos."
        )
        assert len(solo_activos) <= len(todos)

    def test_servicio_de_dominio_respeta_solo_activos(self, app, tenant_id):
        """`grupos_funcionales.listar()` ignoraba su propio parámetro."""
        from db import set_thread_tenant
        from db.connection import clear_thread_tenant
        from app.domain import grupos_funcionales as gf_svc

        set_thread_tenant("istpet")
        try:
            solo_activos = gf_svc.listar(solo_activos=True)
            todos = gf_svc.listar(solo_activos=False)
        finally:
            clear_thread_tenant()

        assert all(g["activo"] for g in solo_activos)
        assert len(solo_activos) <= len(todos)
