"""
Tests del helper `aplicar_grupo_funcional_masivo` (TDD, Tarea 4.2).

Mockeamos `db.queries.personas.listar_personas_para_filtros` y
`db.connection.get_connection` para no tocar BD real. Verifica la
lógica de filtros combinables, idempotencia, shadowing y confirmar.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain.asignacion_masiva import aplicar_grupo_funcional_masivo


# ── 1. Confirmar=True es obligatorio ───────────────────────────────


def test_masivo_requiere_confirmar_true():
    """`confirmar=False` lanza `ValueError` antes de tocar nada."""
    with pytest.raises(ValueError, match="confirmar"):
        aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id=None,
            fecha_inicio=date(2026, 8, 1),
            modo="asignar_grupo_funcional",
            confirmar=False,
        )


def test_crear_override_requiere_plantilla_id():
    """`modo='crear_override'` exige plantilla_id explícito."""
    with pytest.raises(ValueError, match="plantilla_id"):
        aplicar_grupo_funcional_masivo(
            filtros={},
            grupo_funcional_id_destino="gf-1",
            plantilla_id=None,
            fecha_inicio=date(2026, 8, 1),
            modo="crear_override",
            confirmar=True,
        )


def test_modo_invalido_rechazado():
    with pytest.raises(ValueError, match="modo"):
        aplicar_grupo_funcional_masivo(
            filtros={},
            grupo_funcional_id_destino="gf-1",
            plantilla_id="ph-1",
            fecha_inicio=date(2026, 8, 1),
            modo="otro_modo_invalido",
            confirmar=True,
        )


# ── 2. Lógica de filtros y contadores ──────────────────────────────


def test_masivo_filtra_por_grupo_operativo():
    """Si `filtros.grupo_id` está presente, solo se asigna a esas personas."""
    # Mockear listar_personas_para_filtros → retorna 2 IDs.
    with patch(
        "app.domain.asignacion_masiva.listar_personas_para_filtros",
        return_value=["p-1", "p-2"],
    ), patch(
        "app.domain.asignacion_masiva.get_connection",
    ) as mock_get_conn:
        # Mockear la conexión para no escribir nada real.
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        conn.execute.return_value.scalar.return_value = 0
        conn.execute.return_value.rowcount = 0

        @contextmanager
        def _fake_conn(*_a, **_kw):
            yield conn

        mock_get_conn.side_effect = _fake_conn

        resultado = aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id=None,
            fecha_inicio=date(2026, 8, 1),
            modo="asignar_grupo_funcional",
            confirmar=True,
        )
    assert resultado["matched_count"] == 2
    assert resultado["membership_created_count"] == 2
    assert resultado["skipped_count"] == 0
    assert sorted(resultado["affected_persona_ids"]) == ["p-1", "p-2"]


def test_masivo_idempotente_no_duplica_grupos_vigentes():
    """Si la persona ya tiene el gf vigente, NO crea duplicado."""
    # La query EXISTS retorna una fila (ya tiene pgf vigente) → skip.
    # El segundo execute (shadow check) retorna 0.
    call_count = {"n": 0}

    def _execute(sql, params=None, *args, **kwargs):
        sql_text = str(sql.text if hasattr(sql, "text") else sql)
        if "SELECT count(*) FROM asignaciones_horario" in sql_text:
            return MagicMock(scalar=lambda: 0)
        if "SELECT id FROM grupos_funcionales_personas" in sql_text:
            # Persona ya tiene pgf → id no-None → skip
            return MagicMock(fetchone=lambda: ("pgf-existing",))
        return MagicMock()

    conn = MagicMock()
    conn.execute.side_effect = _execute

    @contextmanager
    def _fake_conn(*_a, **_kw):
        yield conn

    with patch(
        "app.domain.asignacion_masiva.listar_personas_para_filtros",
        return_value=["p-1"],
    ), patch(
        "app.domain.asignacion_masiva.get_connection",
        _fake_conn,
    ):
        resultado = aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id=None,
            fecha_inicio=date(2026, 8, 1),
            modo="asignar_grupo_funcional",
            confirmar=True,
        )
    assert resultado["membership_created_count"] == 0
    assert resultado["skipped_count"] == 1
    assert resultado["affected_persona_ids"] == []


def test_masivo_con_cerrar_legacy_aplica_update():
    """`cerrar_legacy_en_fecha=True` cierra el legacy 1:1 antes del new."""
    updates_llamados: list[str] = []

    def _execute(sql, params=None, *args, **kwargs):
        sql_text = str(sql.text if hasattr(sql, "text") else sql)
        if "SELECT count(*) FROM asignaciones_horario" in sql_text:
            # 1 fila legacy en la fecha_inicio → shadow_row = 1
            mock = MagicMock()
            mock.scalar.return_value = 1
            return mock
        if "SELECT id FROM grupos_funcionales_personas" in sql_text:
            # No existe pgf vigente → no skip
            mock = MagicMock()
            mock.fetchone.return_value = None
            return mock
        if "UPDATE asignaciones_horario" in sql_text and "fecha_fin" in sql_text:
            updates_llamados.append(sql_text)
            mock = MagicMock()
            mock.rowcount = 1
            return mock
        if "INSERT INTO grupos_funcionales_personas" in sql_text:
            return MagicMock()
        return MagicMock()

    conn = MagicMock()
    conn.execute.side_effect = _execute

    @contextmanager
    def _fake_conn(*_a, **_kw):
        yield conn

    with patch(
        "app.domain.asignacion_masiva.listar_personas_para_filtros",
        return_value=["p-1"],
    ), patch(
        "app.domain.asignacion_masiva.get_connection",
        _fake_conn,
    ):
        resultado = aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id=None,
            fecha_inicio=date(2026, 8, 1),
            modo="asignar_grupo_funcional",
            cerrar_legacy_en_fecha=True,
            confirmar=True,
        )
    assert resultado["legacy_shadowed_count"] == 1
    assert resultado["legacy_closed_count"] == 1
    assert resultado["membership_created_count"] == 1
    assert updates_llamados, "Debió ejecutar UPDATE sobre legacy"


def test_masivo_crear_override_inserta_en_overrides():
    """modo='crear_override' usa `overrides_horario_persona`."""
    inserts: list[str] = []

    def _execute(sql, params=None, *args, **kwargs):
        sql_text = str(sql.text if hasattr(sql, "text") else sql)
        if "SELECT count(*) FROM asignaciones_horario" in sql_text:
            # Sin legacy → no shadowing.
            mock = MagicMock()
            mock.scalar.return_value = 0
            return mock
        if "INSERT INTO overrides_horario_persona" in sql_text:
            inserts.append(sql_text)
            return MagicMock()
        return MagicMock()

    conn = MagicMock()
    conn.execute.side_effect = _execute

    @contextmanager
    def _fake_conn(*_a, **_kw):
        yield conn

    with patch(
        "app.domain.asignacion_masiva.listar_personas_para_filtros",
        return_value=["p-1", "p-2"],
    ), patch(
        "app.domain.asignacion_masiva.get_connection",
        _fake_conn,
    ):
        resultado = aplicar_grupo_funcional_masivo(
            filtros={"grupo_id": "g-1"},
            grupo_funcional_id_destino="gf-1",
            plantilla_id="ph-X",
            fecha_inicio=date(2026, 8, 1),
            modo="crear_override",
            confirmar=True,
        )
    assert resultado["override_created_count"] == 2
    assert resultado["membership_created_count"] == 0
    assert len(inserts) == 2, (
        "Debió emitir 2 INSERTs en overrides_horario_persona."
    )
