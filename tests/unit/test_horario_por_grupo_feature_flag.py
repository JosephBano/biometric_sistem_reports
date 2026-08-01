"""
Tests del helper `get_horario_por_grupo_enabled` (TDD, Tarea 3.1).

El resolver canónico consulta este helper para decidir si aplica la
precedencia `personalizado > legacy > default > sin_horario` o si cae
al camino legacy. Por seguridad, debe retornar `False` en cualquier
contexto inválido: tests, scheduler en background, CLI.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.tenant import (
    get_horario_por_grupo_enabled,
    get_horario_desempate,
)


class TestGetHorarioPorGrupoEnabled:

    def test_true_si_configuracion_activa(self):
        fake_tenant = {"configuracion": {"horario_por_grupo": True}}
        # `new=MagicMock()` evita que patch() intente inspeccionar el
        # LocalProxy real (que falla fuera de un app context).
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = fake_tenant
            assert get_horario_por_grupo_enabled() is True

    def test_false_si_configuracion_vacia(self):
        fake_tenant = {"configuracion": {}}
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = fake_tenant
            assert get_horario_por_grupo_enabled() is False

    def test_false_si_configuracion_explicitamente_false(self):
        fake_tenant = {"configuracion": {"horario_por_grupo": False}}
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = fake_tenant
            assert get_horario_por_grupo_enabled() is False

    def test_false_si_no_hay_tenant(self):
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = None
            assert get_horario_por_grupo_enabled() is False

    def test_false_si_tenant_no_tiene_configuracion(self):
        """Tenants sin la clave `configuracion` no deben romper."""
        fake_tenant = {}  # sin clave configuracion
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = fake_tenant
            assert get_horario_por_grupo_enabled() is False

    def test_false_si_tenant_tiene_otras_claves(self):
        """Otra clave no debe disparar el flag accidentalmente."""
        fake_tenant = {
            "configuracion": {"timezone": "America/Guayaquil"},
        }
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = fake_tenant
            assert get_horario_por_grupo_enabled() is False

    def test_false_fuera_de_contexto_flask(self):
        """Sin contexto Flask (RuntimeError) → False (caminos seguros)."""
        # Reemplazamos `app.tenant.g` por un objeto que siempre lance
        # RuntimeError al acceder a atributos.
        class _GExplota:
            def __getattr__(self, _):
                raise RuntimeError(
                    "Working outside of application context."
                )

        import app.tenant as tenant_mod

        g_original = tenant_mod.g
        tenant_mod.g = _GExplota()
        try:
            assert get_horario_por_grupo_enabled() is False
        finally:
            tenant_mod.g = g_original


class TestGetHorarioDesempate:

    @pytest.mark.parametrize("valor_config,esperado", [
        ("prioridad", "prioridad"),
        ("orden_grupo", "orden_grupo"),
        ("error", "error"),
        ("invalido", "prioridad"),  # fallback defensivo
        (None, "prioridad"),        # default
    ])
    def test_devuelve_valor_o_default(self, valor_config, esperado):
        cfg = {"configuracion": {"horario_desempate": valor_config}}
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = cfg
            assert get_horario_desempate() == esperado

    def test_default_si_sin_tenant(self):
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = None
            assert get_horario_desempate() == "prioridad"

    def test_default_si_sin_configuracion(self):
        with patch("app.tenant.g", new=MagicMock()) as mock_g:
            mock_g.tenant = {}
            assert get_horario_desempate() == "prioridad"
