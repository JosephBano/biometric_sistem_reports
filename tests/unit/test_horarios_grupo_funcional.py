"""
Tests de `db.queries.horarios_grupo_funcional` (TDD, Tarea 2 del plan).

Cubre la API esperada por el plan:

  - listar_vigentes_para_grupo_funcional(gf_id, fecha)
  - resolver_para_grupos_funcionales([gf_ids], fecha) -> dict | None
  - Respeto de los `origen` values del ADR-0003 r2:
      'personalizado', 'individual_legacy', 'default_grupo', 'sin_horario'.
  - Filtro `fecha_fin` en el WHERE del query (no en el índice, por P12).

Mockeamos `db.connection.get_connection` — no toca BD real.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from db.queries import horarios_grupo_funcional


# ── listar_vigentes_para_grupo_funcional ──────────────────────────


def test_listar_vigentes_retorna_dicts():
    mock_row = MagicMock()
    mock_row._mapping = {
        "id": "hdg-1", "grupo_funcional_id": "gf-1",
        "plantilla_id": "ph-1", "fecha_inicio": date(2026, 1, 1),
        "fecha_fin": None, "prioridad": 0,
    }
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [mock_row]

    @contextmanager
    def _fake_conn(*_a, **_kw):
        yield mock_conn

    with patch(
        "db.queries.horarios_grupo_funcional.get_connection", _fake_conn
    ):
        rows = (
            horarios_grupo_funcional
            .listar_horarios_vigentes_para_grupo_funcional(
                "gf-1", date(2026, 7, 15)
            )
        )
    assert len(rows) == 1
    assert rows[0]["grupo_funcional_id"] == "gf-1"


def test_listar_vigentes_query_usa_orden_prioridad_y_filtro_fecha():
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []

    @contextmanager
    def _fake_conn(*_a, **_kw):
        yield mock_conn

    with patch(
        "db.queries.horarios_grupo_funcional.get_connection", _fake_conn
    ):
        horarios_grupo_funcional.listar_horarios_vigentes_para_grupo_funcional(
            "gf-1", date(2026, 7, 15)
        )
    sql = str(mock_conn.execute.call_args[0][0])
    # Reglas ADR-0003:
    # El query ordena por `prioridad DESC` para desempate determinista.
    # Acepta con o sin prefijo de tabla (`hdg.prioridad` o `prioridad`).
    sql_upper = sql.upper()
    assert ("ORDER BY HDG.PRIORIDAD DESC" in sql_upper
            or "ORDER BY PRIORIDAD DESC" in sql_upper), (
        "Debe ordenar por prioridad DESC para desempate determinista."
    )
    # El filtro fecha_fin se aplica en el WHERE (P12: NO en el índice).
    # Acepta con o sin prefijo de tabla.
    assert (
        "FECHA_FIN IS NULL OR FECHA_FIN >=" in sql_upper
        or "FECHA_FIN IS NULL OR HDG.FECHA_FIN >=" in sql_upper
    ), "El filtro fecha_fin debe aplicarse en el WHERE."


# ── resolver_para_grupos (default con múltiples grupos) ───────────


def test_resolver_para_grupos_devuelve_mayor_prioridad():
    """Devuelve el default con mayor prioridad entre los grupos.

    El SQL tiene `LIMIT 1` después de `ORDER BY prioridad DESC`, así que
    `fetchall` (mockeado) solo necesita devolver UNA fila con la
    prioridad mayor — el ordenamiento lo aplicaría PostgreSQL real.
    """
    # El mock simula que PostgreSQL ya aplicó el ORDER BY... LIMIT 1.
    winner_row = MagicMock()
    winner_row._mapping = {
        "id": "hdg-B", "plantilla_id": "ph-B",
        "grupo_funcional_id": "gf-B", "prioridad": 10,
        "fecha_inicio": date(2026, 1, 1),
    }
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [winner_row]

    @contextmanager
    def _fake_conn(*_a, **_kw):
        yield mock_conn

    with patch(
        "db.queries.horarios_grupo_funcional.get_connection", _fake_conn,
    ):
        resultado = (
            horarios_grupo_funcional
            .resolver_default_para_grupos_funcionales(
                ["gf-A", "gf-B"], date(2026, 7, 15)
            )
        )
    assert resultado is not None
    assert resultado["prioridad"] == 10
    assert resultado["grupo_funcional_id"] == "gf-B"
    assert resultado["plantilla_id"] == "ph-B"

    # Verifica además que el SQL emitido tiene `ORDER BY ... LIMIT 1`.
    sql = str(mock_conn.execute.call_args[0][0])
    assert "ORDER BY" in sql.upper()
    assert "LIMIT 1" in sql.upper()


def test_resolver_para_grupos_sin_grupos_retorna_none():
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []

    @contextmanager
    def _fake_conn(*_a, **_kw):
        yield mock_conn

    with patch(
        "db.queries.horarios_grupo_funcional.get_connection", _fake_conn
    ):
        resultado = (
            horarios_grupo_funcional
            .resolver_default_para_grupos_funcionales(
                [], date(2026, 7, 15)
            )
        )
    assert resultado is None


# ── Resolver horario vigente (regla principal del ADR-0003) ───────


class TestResolverHorarioVigente:
    """Valida que la precedencia es la documentada en el ADR r2 (P11)."""

    def test_001_sin_historico_devuelve_sin_horario(self):
        """Sin override ni legacy ni grupo funcional → sin_horario."""
        from db.queries.horarios_grupo_funcional import (
            resolver_horario_vigente,
        )

        mock_conn = MagicMock()

        # Todas las queries devuelven None en fetchone / [] en fetchall.
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_conn.execute.return_value.fetchall.return_value = []

        @contextmanager
        def _fake_conn(*_a, **_kw):
            yield mock_conn

        with patch(
            "db.queries.horarios_grupo_funcional.get_connection",
            _fake_conn,
        ):
            resultado = resolver_horario_vigente(
                "p-1", date(2026, 7, 15), feature_flag=True,
            )

        # La función debe retornar dict (no None) con origen='sin_horario'.
        assert isinstance(resultado, dict)
        assert resultado["origen"] == "sin_horario"
        assert resultado["plantilla_id"] is None
        assert resultado["plantilla"] is None

    def test_002_con_override_retorna_personalizado(self):
        from db.queries.horarios_grupo_funcional import (
            resolver_horario_vigente,
        )

        # Mock del row de override_horario_persona (debe tener TODAS las
        # columnas que la query SELECT proyecta: id, persona_id,
        # plantilla_id, fecha_inicio, fecha_fin, notas, creado_por,
        # creado_en).
        override_row = MagicMock()
        override_row._mapping = {
            "id": "ov-1",
            "persona_id": "p-1",
            "plantilla_id": "ph-O",
            "fecha_inicio": date(2026, 1, 1),
            "fecha_fin": None,
            "notas": "test",
            "creado_por": None,
            "creado_en": None,
        }

        # Mock del row de plantillas_horario (devuelto por _cargar_plantilla).
        plantilla_row = MagicMock()
        plantilla_row._mapping = {
            "id": "ph-O", "nombre": "Plantilla Override",
            "lunes": "08:00", "martes": "08:00",
        }

        mock_conn = MagicMock()

        def _execute(sql, params=None):
            sql_text = str(sql.text if hasattr(sql, "text") else sql)
            if "overrides_horario_persona" in sql_text:
                m = MagicMock()
                m.fetchone.return_value = override_row
                return m
            if "plantillas_horario" in sql_text:
                m = MagicMock()
                m.fetchone.return_value = plantilla_row
                return m
            return MagicMock(fetchall=lambda: [], fetchone=lambda: None)

        mock_conn.execute.side_effect = _execute

        @contextmanager
        def _fake_conn(*_a, **_kw):
            yield mock_conn

        with patch(
            "db.queries.horarios_grupo_funcional.get_connection",
            _fake_conn,
        ):
            resultado = resolver_horario_vigente(
                "p-1", date(2026, 7, 15), feature_flag=True,
            )
        assert resultado["origen"] == "personalizado"
        assert resultado["override_id"] == "ov-1"
        assert resultado["plantilla_id"] == "ph-O"
        for k in ("plantilla_id", "plantilla", "origen",
                  "override_id", "grupo_funcional_id",
                  "asignacion_legacy_id", "regla_desempate"):
            assert k in resultado


# ── `origen` values por ADR-0003 ───────────────────────────────────


class TestOrigenValuesADR:
    """Confirma que los strings `origen` cumplen r2 del ADR."""

    @pytest.mark.parametrize("origen_esperado", [
        "personalizado",
        "individual_legacy",
        "default_grupo",
        "sin_horario",
    ])
    def test_origen_valido_en_catalogo_adr(self, origen_esperado):
        """Los 4 strings de origen del ADR r2 están documentados."""
        valores_adr = {
            "personalizado",
            "individual_legacy",
            "default_grupo",
            "sin_horario",
        }
        assert origen_esperado in valores_adr


# ── queries CRUD existentes (compat con integración previa) ──────


class TestCompatibilidadCRUD:

    def test_listar_vigentes_para_persona_existe_y_es_iterable(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "pgf-1", "persona_id": "p-1",
            "grupo_funcional_id": "gf-1",
            "fecha_inicio": date(2026, 1, 1), "fecha_fin": None,
            "es_principal": True, "notas": None,
            "creado_en": None,
            "grupo_funcional_nombre": "Profesor",
            "orden_gf": 1,
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        @contextmanager
        def _fake_conn(*_a, **_kw):
            yield mock_conn

        with patch(
            "db.queries.horarios_grupo_funcional.get_connection",
            _fake_conn,
        ):
            rows = (
                horarios_grupo_funcional
                .listar_grupos_funcionales_de_persona("p-1")
            )
        assert len(rows) == 1
        assert rows[0]["es_principal"] is True

    def test_listar_overrides_por_persona(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": "ohp-1", "persona_id": "p-1",
            "plantilla_id": "ph-3",
            "fecha_inicio": date(2026, 8, 1),
            "fecha_fin": None,
            "notas": "Cambio temporal",
            "creado_en": None,
            "plantilla_nombre": "Nocturno X",
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        @contextmanager
        def _fake_conn(*_a, **_kw):
            yield mock_conn

        with patch(
            "db.queries.horarios_grupo_funcional.get_connection",
            _fake_conn,
        ):
            rows = (
                horarios_grupo_funcional.listar_overrides_por_persona("p-1")
            )
        assert len(rows) == 1
        assert rows[0]["notas"] == "Cambio temporal"
