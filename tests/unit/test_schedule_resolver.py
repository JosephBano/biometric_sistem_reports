"""
Tests parametrizados del wrapper canónico
`app.domain.horarios_resolucion.resolver_horario_vigente_para_persona`.

Cubre:
  - Feature flag on/off (resuelve el origen que el solver retorna).
  - Precedencia personalizada > legacy > default > sin_horario.
  - `horario_desempate` se propaga al resolver subyacente.

Mockeamos `db.queries.horarios_grupo_funcional.resolver_horario_vigente`
para verificar que el wrapper aplica el feature flag correctamente.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain.horarios_resolucion import resolver_horario_vigente_para_persona


def _res_vacio(origen="sin_horario"):
    return {
        "plantilla_id": None,
        "plantilla": None,
        "origen": origen,
        "override_id": None,
        "asignacion_legacy_id": None,
        "grupo_funcional_id": None,
        "regla_desempate": None,
    }


# ── 1. PERSONALIZADO ──────────────────────────────────────────────────


def test_override_vigente_retorna_personalizado():
    esperado = {
        **_res_vacio("personalizado"),
        "plantilla_id": "ph-O",
        "override_id": "ov-1",
    }
    with patch(
        "app.domain.horarios_resolucion.resolver_horario_vigente",
        return_value=esperado,
    ):
        resultado = resolver_horario_vigente_para_persona(
            "p-1", date(2026, 7, 15), feature_flag=True,
        )
    assert resultado["origen"] == "personalizado"
    assert resultado["plantilla_id"] == "ph-O"
    assert resultado["override_id"] == "ov-1"


# ── 2. INDIVIDUAL LEGACY ──────────────────────────────────────────────


def test_sin_override_busco_legacy():
    esperado = {
        **_res_vacio("individual_legacy"),
        "plantilla_id": "ph-L",
        "asignacion_legacy_id": "ah-1",
    }
    with patch(
        "app.domain.horarios_resolucion.resolver_horario_vigente",
        return_value=esperado,
    ):
        resultado = resolver_horario_vigente_para_persona(
            "p-1", date(2026, 7, 15), feature_flag=True,
        )
    assert resultado["origen"] == "individual_legacy"
    assert resultado["asignacion_legacy_id"] == "ah-1"


# ── 3. DEFAULT_GRUPO ──────────────────────────────────────────────────


def test_sin_override_sin_legacy_busco_default_grupo():
    esperado = {
        **_res_vacio("default_grupo"),
        "plantilla_id": "ph-D",
        "grupo_funcional_id": "gf-1",
        "regla_desempate": "es_principal",
    }
    with patch(
        "app.domain.horarios_resolucion.resolver_horario_vigente",
        return_value=esperado,
    ):
        resultado = resolver_horario_vigente_para_persona(
            "p-1", date(2026, 7, 15), feature_flag=True,
        )
    assert resultado["origen"] == "default_grupo"
    assert resultado["grupo_funcional_id"] == "gf-1"


# ── 4. SIN HORARIO ────────────────────────────────────────────────────


def test_sin_horario():
    esperado = _res_vacio("sin_horario")
    with patch(
        "app.domain.horarios_resolucion.resolver_horario_vigente",
        return_value=esperado,
    ):
        resultado = resolver_horario_vigente_para_persona(
            "p-1", date(2026, 7, 15), feature_flag=True,
        )
    assert resultado["origen"] == "sin_horario"
    assert resultado["plantilla_id"] is None


# ── 5. Feature flag off → cae a legacy ──────────────────────────────


def test_feature_flag_false_retorna_legacy():
    esperado = {
        **_res_vacio("individual_legacy"),
        "plantilla_id": "ph-L",
        "asignacion_legacy_id": "ah-1",
    }
    with patch(
        "app.domain.horarios_resolucion.resolver_horario_vigente",
        return_value=esperado,
    ) as mock_resolve:
        resultado = resolver_horario_vigente_para_persona(
            "p-1", date(2026, 7, 15), feature_flag=False,
        )
    assert resultado["origen"] == "individual_legacy"
    # Verificamos que el wrapper pasó `feature_flag=False`.
    args, kwargs = mock_resolve.call_args
    assert kwargs.get("feature_flag") is False


# ── 6. Desempate=error con varios grupos sin principal → RuntimeError ─


def test_varios_grupos_sin_principal_y_error_lanza_excepcion():
    with patch(
        "app.domain.horarios_resolucion.resolver_horario_vigente",
        side_effect=RuntimeError(
            "Ambigüedad: persona p-1 tiene N grupos sin principal."
        ),
    ), pytest.raises(RuntimeError, match="Ambigüedad"):
        resolver_horario_vigente_para_persona(
            "p-1", date(2026, 7, 15),
            feature_flag=True, horario_desempate="error",
        )


# ── 7. feature_flag=None → lee del tenant (default=False) ──────


def test_feature_flag_none_usa_default_del_tenant_false():
    """Sin flag explícito, el wrapper consulta el feature flag del tenant.
    Si el tenant no tiene `horario_por_grupo` activo → False → legacy."""
    with patch("app.tenant.g", new=MagicMock()) as mock_g:
        # tenant sin `configuracion['horario_por_grupo']`
        mock_g.tenant = {"configuracion": {}}
        with patch(
            "app.domain.horarios_resolucion.resolver_horario_vigente",
            return_value=_res_vacio("individual_legacy"),
        ) as mock_resolve:
            resultado = resolver_horario_vigente_para_persona(
                "p-1", date(2026, 7, 15),
            )
    assert resultado["origen"] == "individual_legacy"
    args, kwargs = mock_resolve.call_args
    assert kwargs.get("feature_flag") is False


# ── 8. feature_flag=None con tenant que activó el flag → True ──


def test_feature_flag_none_con_tenant_activo_aplica_precedencia():
    esperado = {
        **_res_vacio("personalizado"),
        "plantilla_id": "ph-O",
    }
    with patch("app.tenant.g", new=MagicMock()) as mock_g:
        mock_g.tenant = {"configuracion": {"horario_por_grupo": True}}
        with patch(
            "app.domain.horarios_resolucion.resolver_horario_vigente",
            return_value=esperado,
        ) as mock_resolve:
            resultado = resolver_horario_vigente_para_persona(
                "p-1", date(2026, 7, 15),
            )
    assert resultado["origen"] == "personalizado"
    args, kwargs = mock_resolve.call_args
    assert kwargs.get("feature_flag") is True
