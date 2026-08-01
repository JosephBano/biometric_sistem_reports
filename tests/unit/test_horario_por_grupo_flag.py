"""Tests del servicio de activación del feature flag (TDD, Tar. 4.3).

Mockeamos las dependencias (`registrar_audit`, `actualizar_tenant`)
para verificar la API sin tocar BD real.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain.horario_por_grupo_flag import (
    POLITICAS_VALIDAS,
    preflight,
    set_horario_por_grupo_flag,
)


class TestSetFlag:

    def test_admin_puede_activar(self):
        actualizado = {
            "id": "t-1",
            "slug": "istpet",
            "configuracion": {
                "horario_por_grupo": True,
                "horario_desempate": "prioridad",
            },
        }
        with patch(
            "app.domain.horario_por_grupo_flag.registrar_audit",
        ) as mock_audit:
            resultado = set_horario_por_grupo_flag(
                tenant_id="t-1",
                usuario_id="u-1",
                ip="127.0.0.1",
                enabled=True,
                horario_desempate="prioridad",
                tenant_schema="istpet",
                # Inyectamos mocks para no tocar BD ni audit real.
                actualizar_configuracion_tenant_fn=lambda tid, cfg: actualizado,
                registrar_audit_fn=mock_audit,
            )
        assert resultado["configuracion"]["horario_por_grupo"] is True
        assert resultado["configuracion"]["horario_desempate"] == "prioridad"
        mock_audit.assert_called_once()
        accion = mock_audit.call_args.kwargs["accion"]
        assert accion == "horario_por_grupo_activar"

    def test_admin_puede_desactivar(self):
        actualizado = {
            "id": "t-1",
            "configuracion": {"horario_por_grupo": False},
        }
        with patch(
            "app.domain.horario_por_grupo_flag.registrar_audit",
        ) as mock_audit:
            set_horario_por_grupo_flag(
                tenant_id="t-1",
                usuario_id="u-1",
                ip=None,
                enabled=False,
                horario_desempate="prioridad",
                tenant_schema="istpet",
                actualizar_configuracion_tenant_fn=lambda tid, cfg: actualizado,
                registrar_audit_fn=mock_audit,
            )
        accion = mock_audit.call_args.kwargs["accion"]
        assert accion == "horario_por_grupo_desactivar"
        assert (
            mock_audit.call_args.kwargs["detalle"]["horario_por_grupo"]
            is False
        )

    @pytest.mark.parametrize("valor_invalido", ["", "foo", "PRIORIDAD", None])
    def test_politica_invalida_rechaza(self, valor_invalido):
        with pytest.raises(ValueError, match="horario_desempate"):
            set_horario_por_grupo_flag(
                tenant_id="t-1",
                usuario_id="u-1",
                ip=None,
                enabled=True,
                horario_desempate=valor_invalido,
                actualizar_configuracion_tenant_fn=lambda *a, **kw: {},
                registrar_audit_fn=MagicMock(),
            )

    @pytest.mark.parametrize("valor_valido", ["prioridad", "orden_grupo", "error"])
    def test_politicas_validas_aceptadas(self, valor_valido):
        # No debe lanzar.
        with patch(
            "app.domain.horario_por_grupo_flag.registrar_audit",
        ):
            set_horario_por_grupo_flag(
                tenant_id="t-1",
                usuario_id="u-1",
                ip=None,
                enabled=True,
                horario_desempate=valor_valido,
                actualizar_configuracion_tenant_fn=lambda *a, **kw: {},
                registrar_audit_fn=MagicMock(),
            )


class TestPreflight:

    def test_preflight_devuelve_counters(self):
        """Smoke: preflight retorna los 5 contadores esperados."""
        with patch(
            "app.domain.horario_por_grupo_flag.listar_grupos_funcionales_vigentes_para_persona",
        ) as mock_grupos, patch(
            "app.domain.horario_por_grupo_flag.obtener_override_vigente_para_persona",
        ) as mock_ov, patch(
            "app.domain.horario_por_grupo_flag.obtener_asignacion_legacy_vigente",
        ) as mock_legacy, patch(
            "app.domain.horario_por_grupo_flag.listar_personas_para_filtros",
            return_value=[f"p-{i}" for i in range(5)],
        ):
            # Para p-0, p-1 → override, p-2 → legacy, p-3 → gf, p-4 → sin.
            mock_ov.side_effect = lambda pid, f: (
                {"id": "ov"} if pid in ("p-0", "p-1") else None
            )
            mock_legacy.side_effect = lambda pid, f: (
                {"id": "ah"} if pid == "p-2" else None
            )
            mock_grupos.side_effect = lambda pid, f: (
                [{"id": "pgf"}] if pid == "p-3" else []
            )

            resultado = preflight(
                tenant_id="t-1", fecha=date(2026, 8, 1),
            )

        assert resultado["personas_activas"] == 5
        assert resultado["con_override"] == 2
        assert resultado["con_horario_legacy"] == 1
        assert resultado["con_default_grupo"] == 1
        assert resultado["sin_horario"] == 1
        # Hay 1 persona sin horario → safe_to_enable debe ser False.
        assert resultado["safe_to_enable"] is False

    def test_preflight_safe_cuando_todas_tienen_capa(self):
        """Si TODAS las personas tienen al menos una capa, safe_to_enable=True."""
        with patch(
            "app.domain.horario_por_grupo_flag.listar_grupos_funcionales_vigentes_para_persona",
            return_value=[{"id": "pgf"}],
        ), patch(
            "app.domain.horario_por_grupo_flag.obtener_override_vigente_para_persona",
            return_value=None,
        ), patch(
            "app.domain.horario_por_grupo_flag.obtener_asignacion_legacy_vigente",
            return_value={"id": "ah"},
        ), patch(
            "app.domain.horario_por_grupo_flag.listar_personas_para_filtros",
            return_value=["p-1", "p-2"],
        ):
            resultado = preflight(
                tenant_id="t-1", fecha=date(2026, 8, 1),
            )

        assert resultado["safe_to_enable"] is True
        assert resultado["sin_horario"] == 0


class TestPoliticasConstant:

    def test_politicas_validas_constante(self):
        """La constante exportada debe coincidir con el contrato ADR-0003."""
        assert POLITICAS_VALIDAS == {"prioridad", "orden_grupo", "error"}
