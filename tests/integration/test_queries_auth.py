"""
Tests de integración de `db.queries.auth` (Fase 7.4 — cobertura).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from db import set_thread_tenant
from db.queries.auth import (
    activar_usuario_db,
    actualizar_roles_db,
    actualizar_ultimo_acceso,
    contar_intentos_fallidos,
    crear_usuario_db,
    desactivar_usuario_db,
    get_tenants_activos,
    get_tipos_persona,
    get_usuario_por_email,
    get_usuario_por_id,
    get_usuarios_all_tenants,
    get_usuarios_tenant,
    registrar_audit,
    registrar_login_intento,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def usuario_test(tenant_id):
    """Crea un usuario de prueba con email único."""
    email = f"test-{uuid.uuid4().hex[:8]}@biometrico.local"
    user = crear_usuario_db(
        tenant_id=tenant_id,
        email=email,
        password_hash="$2b$12$fakehashfakehashfakehashfakehashfakehashfake",
        nombre="Test User",
        roles=["readonly"],
        configuracion={},
    )
    yield user
    # Cleanup via desactivar (no hay DELETE)
    try:
        desactivar_usuario_db(user["id"])
    except Exception:
        pass


class TestGetUsuario:

    def test_get_usuario_por_email_existente(self, usuario_test):
        """get_usuario_por_email retorna el usuario si existe."""
        result = get_usuario_por_email(usuario_test["email"])
        assert result is not None
        assert result["id"] == usuario_test["id"]

    def test_get_usuario_por_email_inexistente(self):
        """get_usuario_por_email con email que no existe → None."""
        result = get_usuario_por_email("noexiste@biometrico.local")
        assert result is None

    def test_get_usuario_por_id(self, usuario_test):
        """get_usuario_por_id retorna el usuario correcto."""
        result = get_usuario_por_id(usuario_test["id"])
        assert result is not None
        assert result["email"] == usuario_test["email"]

    def test_get_usuario_por_id_inexistente(self):
        """get_usuario_por_id con UUID inexistente → None."""
        result = get_usuario_por_id("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestListarUsuarios:

    def test_get_usuarios_tenant_incluye_test(self, tenant_id, usuario_test):
        """get_usuarios_tenant retorna al menos el usuario de prueba."""
        result = get_usuarios_tenant(tenant_id)
        assert len(result) >= 1
        emails = [u["email"] for u in result]
        assert usuario_test["email"] in emails

    def test_get_usuarios_all_tenants(self, usuario_test):
        """get_usuarios_all_tenants retorna todos los usuarios."""
        result = get_usuarios_all_tenants()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_get_tenants_activos(self):
        """get_tenants_activos retorna lista (istpet debe estar)."""
        result = get_tenants_activos()
        slugs = [t["slug"] for t in result]
        assert "istpet" in slugs


class TestCrearUsuario:

    def test_crear_usuario_db_retorna_dict(self, tenant_id):
        """crear_usuario_db retorna el usuario creado."""
        email = f"new-{uuid.uuid4().hex[:8]}@biometrico.local"
        result = crear_usuario_db(
            tenant_id=tenant_id,
            email=email,
            password_hash="$2b$12$fake",
            nombre="New User",
            roles=["admin"],
            configuracion={},
        )
        assert result["email"] == email
        assert result["nombre"] == "New User"
        assert "admin" in result["roles"]
        assert result["activo"] is True

    def test_crear_usuario_email_duplicado_falla(self, tenant_id, usuario_test):
        """Email duplicado lanza excepción."""
        with pytest.raises(Exception):
            crear_usuario_db(
                tenant_id=tenant_id,
                email=usuario_test["email"],
                password_hash="hash",
                nombre="Duplicado",
                roles=["readonly"],
                configuracion={},
            )


class TestActualizarRoles:

    def test_actualizar_roles_cambia_roles(self, usuario_test):
        """actualizar_roles_db cambia los roles del usuario."""
        result = actualizar_roles_db(
            usuario_test["id"],
            roles=["admin", "gestor"],
            configuracion={},
        )
        assert result is True

        # Verificar
        u = get_usuario_por_id(usuario_test["id"])
        assert "admin" in u["roles"]
        assert "gestor" in u["roles"]


class TestActivarDesactivar:

    def test_desactivar_usuario(self, usuario_test):
        """desactivar_usuario_db pone activo=False."""
        result = desactivar_usuario_db(usuario_test["id"])
        assert result is True

        u = get_usuario_por_id(usuario_test["id"])
        assert u["activo"] is False

    def test_activar_usuario(self, usuario_test):
        """activar_usuario_db pone activo=True (incluso si ya está activo)."""
        desactivar_usuario_db(usuario_test["id"])  # primero desactivar
        result = activar_usuario_db(usuario_test["id"])
        assert result is True

        u = get_usuario_por_id(usuario_test["id"])
        assert u["activo"] is True


class TestActualizarUltimoAcceso:

    def test_actualizar_ultimo_acceso_no_falla(self, usuario_test):
        """actualizar_ultimo_acceso ejecuta sin error."""
        # No retorna nada, solo verifica que no lance excepción
        actualizar_ultimo_acceso(usuario_test["id"])
        # Si llega aquí sin excepción, pasa


class TestRegistrarAudit:

    def test_registrar_audit_con_detalle(self, tenant_id, usuario_test):
        """registrar_audit con detalle JSONB no falla."""
        import sqlalchemy as sa
        from db.connection import get_engine

        registrar_audit(
            tenant_id=tenant_id,
            usuario_id=usuario_test["id"],
            accion="login",
            detalle={"ip": "192.168.1.1", "exito": True},
        )

        # Verificar que se insertó
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT accion FROM public.audit_log "
                    "WHERE usuario_id = CAST(:uid AS uuid) "
                    "ORDER BY creado_en DESC LIMIT 1"
                ),
                {"uid": usuario_test["id"]},
            ).fetchall()
        assert rows[0][0] == "login"

    def test_registrar_audit_sin_detalle(self, tenant_id, usuario_test):
        """registrar_audit sin detalle no falla."""
        registrar_audit(
            tenant_id=tenant_id,
            usuario_id=usuario_test["id"],
            accion="logout",
        )
        # Solo verifica que no lance


class TestLoginIntentos:

    def test_registrar_y_contar_intentos_fallidos(self):
        """registrar_login_intento + contar_intentos_fallidos."""
        ip = f"192.168.99.{uuid.uuid4().int % 255}"

        # Estado limpio
        assert contar_intentos_fallidos(ip, ventana_minutos=15) == 0

        # Registrar 3 intentos fallidos
        for _ in range(3):
            registrar_login_intento(ip, "test@x.com", exitoso=False)

        assert contar_intentos_fallidos(ip, ventana_minutos=15) == 3

    def test_registrar_login_exitoso_no_cuenta_como_fallo(self):
        """Un login exitoso no incrementa el contador de fallos."""
        ip = f"192.168.99.{uuid.uuid4().int % 255}"

        registrar_login_intento(ip, "test@x.com", exitoso=True)
        assert contar_intentos_fallidos(ip, ventana_minutos=15) == 0

    def test_ventana_minutos_filtra_intentos_viejos(self):
        """Intentos fuera de la ventana no se cuentan."""
        ip = f"192.168.99.{uuid.uuid4().int % 255}"

        # Registrar 2 intentos fallidos (dentro de ventana por defecto)
        for _ in range(2):
            registrar_login_intento(ip, "test@x.com", exitoso=False)

        # Contar con ventana de 0 minutos (no debería contar nada)
        assert contar_intentos_fallidos(ip, ventana_minutos=0) == 0


class TestTiposPersona:

    def test_get_tipos_persona_istpet(self):
        """istpet tiene tipos de persona sembrados."""
        result = get_tipos_persona("istpet")
        assert isinstance(result, list)
        assert len(result) >= 1
