"""
Tests del helper `db.queries.scheduler_runs` (TDD).

Mockeamos `db.connection.get_engine()` para no tocar BD real.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from db.queries import scheduler_runs


def _make_engine_mock(mock_conn: MagicMock) -> MagicMock:
    """Helper: crea un mock de engine donde `with engine.connect() as conn` devuelve mock_conn."""
    mock_engine = MagicMock()

    # El context manager `with engine.connect() as conn` usa __enter__/__exit__
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_conn)
    cm.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = cm
    return mock_engine


class TestRegistrarRun:

    def test_registrar_run_exitoso_inserta_fila(self):
        """Una corrida ok=true debe ejecutar INSERT con todos los campos."""
        mock_conn = MagicMock()
        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            scheduler_runs.registrar_run(
                job="sync_incremental",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=42,
                insertados=37,
                detalle=None,
            )

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        # El primer argumento posicional es la sentencia SQL (text object)
        sql = mock_conn.execute.call_args[0][0]
        params = mock_conn.execute.call_args[0][1]
        assert "INSERT INTO public.scheduler_runs" in str(sql)
        assert params["job"] == "sync_incremental"
        assert params["tenant_slug"] == "istpet"
        assert params["ok"] is True
        assert params["descargados"] == 42
        assert params["insertados"] == 37

    def test_registrar_run_error_guarda_detalle_y_ok_false(self):
        """Fallo: ok=False, detalle con mensaje de error, contadores NULL."""
        mock_conn = MagicMock()
        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            scheduler_runs.registrar_run(
                job="sync_nocturna",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 2, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 2, 1, tzinfo=timezone.utc),
                ok=False,
                descargados=None,
                insertados=None,
                detalle="Timeout connecting to dispositivo 3",
            )

        params = mock_conn.execute.call_args[0][1]
        assert params["ok"] is False
        assert params["descargados"] is None
        assert params["insertados"] is None
        assert "Timeout" in params["detalle"]

    def test_registrar_run_backup_diario_tenant_slug_null(self):
        """Job global (backup_diario) lleva tenant_slug=None."""
        mock_conn = MagicMock()
        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            scheduler_runs.registrar_run(
                job="backup_diario",
                tenant_slug=None,
                inicio=datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 3, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=None,
                insertados=None,
                detalle="/data/backups/backup_completo_20260702_0300.dump (124 MB)",
            )

        params = mock_conn.execute.call_args[0][1]
        assert params["job"] == "backup_diario"
        assert params["tenant_slug"] is None
        assert params["detalle"].startswith("/data/backups/")

    def test_registrar_run_rechaza_tenant_slug_invalido(self):
        """tenant_slug que no cumple patrón ^[a-z][a-z0-9_]{0,30}$ → ValueError."""
        with pytest.raises(ValueError) as exc_info:
            scheduler_runs.registrar_run(
                job="sync_incremental",
                tenant_slug="../../etc/passwd",  # path traversal attempt
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=10,
                insertados=8,
                detalle=None,
            )
        assert "tenant_slug" in str(exc_info.value).lower()

    def test_registrar_run_rechaza_job_desconocido(self):
        """job que no está en el conjunto permitido → ValueError."""
        with pytest.raises(ValueError) as exc_info:
            scheduler_runs.registrar_run(
                job="job_malicioso_xyz",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=10,
                insertados=8,
                detalle=None,
            )
        assert "job" in str(exc_info.value).lower()

    def test_registrar_run_acepta_tenant_slug_none(self):
        """tenant_slug=None es válido (jobs globales como backup_diario)."""
        mock_conn = MagicMock()
        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            scheduler_runs.registrar_run(
                job="backup_diario",
                tenant_slug=None,
                inicio=datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc),
                fin=datetime(2026, 7, 2, 3, 5, tzinfo=timezone.utc),
                ok=True,
                descargados=None,
                insertados=None,
                detalle="ok",
            )
        # No levantó excepción — test pasa si llegamos aquí


class TestListarUltimosRuns:

    def test_listar_ultimos_devuelve_dicts_con_campos_esperados(self):
        """Cada fila viene como dict con id, job, tenant_slug, ok, etc."""
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": 1,
            "job": "sync_incremental",
            "tenant_slug": "istpet",
            "inicio": datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
            "fin": datetime(2026, 7, 2, 10, 5, tzinfo=timezone.utc),
            "ok": True,
            "descargados": 10,
            "insertados": 8,
            "detalle": None,
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [mock_row]

        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            resultado = scheduler_runs.listar_ultimos(limit=10)

        assert len(resultado) == 1
        fila = resultado[0]
        assert fila["job"] == "sync_incremental"
        assert fila["tenant_slug"] == "istpet"
        assert fila["ok"] is True
        assert fila["descargados"] == 10

    def test_listar_ultimos_pasa_limit_al_sql(self):
        """El parámetro limit se pasa como parámetro al SQL."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            scheduler_runs.listar_ultimos(limit=5)

        params = mock_conn.execute.call_args[0][1]
        assert params["limit"] == 5


class TestPurgarMayorA:

    def test_purgar_borra_filas_viejas_y_devuelve_conteo(self):
        """DELETE con WHERE inicio < NOW() - make_interval(...) y retorna rowcount."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 7
        mock_conn.execute.return_value = mock_result

        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            borradas = scheduler_runs.purgar_mayor_a(dias=90)

        assert borradas == 7
        mock_conn.commit.assert_called_once()
        # Verificar SQL y parámetros
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        # conn.execute(sql, {"dias": 90}) → args = (sql, {"dias": 90})
        params = call_args[0][1] if len(call_args[0]) > 1 else {}
        assert "DELETE FROM public.scheduler_runs" in str(sql)
        assert "make_interval" in str(sql)
        assert params.get("dias") == 90

    def test_purgar_parametriza_dias_via_bindparam(self):
        """El parámetro dias viaja como :dias (no hardcoded en el literal)."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_conn.execute.return_value = mock_result

        mock_engine = _make_engine_mock(mock_conn)

        with patch("db.queries.scheduler_runs.get_engine", return_value=mock_engine):
            scheduler_runs.purgar_mayor_a(dias=45)

        # El SQL crudo NO debe contener "45" en el literal (debe estar en bindparam)
        sql = str(mock_conn.execute.call_args[0][0])
        assert "45" not in sql, "dias debe venir por bindparam, no por literal"
        assert ":dias" in sql

    def test_purgar_rechaza_dias_invalidos(self):
        """dias debe ser int >= 1; cualquier otra cosa lanza ValueError."""
        with pytest.raises(ValueError):
            scheduler_runs.purgar_mayor_a(dias=0)
        with pytest.raises(ValueError):
            scheduler_runs.purgar_mayor_a(dias=-1)
        with pytest.raises(ValueError):
            scheduler_runs.purgar_mayor_a(dias="hola")  # type: ignore[arg-type]