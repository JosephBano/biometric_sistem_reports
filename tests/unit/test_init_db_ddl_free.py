"""
Verifica el contrato de `db.init.init_db()` tras la Tarea 0.3 del plan
ADR-0003 (Fase -1): Alembic es la única fuente de verdad del schema, y
`init_db()` se limita a SEED idempotente.

Reglas no negociables:
  - Si `public.alembic_version` existe: `init_db()` NO ejecuta DDL.
  - Si NO existe: se ejecuta la rama DDL legacy (modo compat para pgserver/dev).
  - El seed (public.tenants, public.usuarios, sedes, dispositivos,
    tipos_persona, feriados) SIEMPRE se ejecuta, sea cual sea el modo.

Este test no requiere una BD real: mockeamos `get_engine` y `get_connection`
para capturar las sentencias SQL ejecutadas.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


def _ejecutar_init_db_mockeado(monkeypatch, alembic_present: bool):
    """Ejecuta `init_db()` con BD mockeada; retorna lista de SQLs ejecutados."""
    sql_ejecutado: list[str] = []

    # Mock get_engine para simular respuesta a _alembic_applied()
    engine = MagicMock()
    engine_conn = MagicMock()

    def _execute(sql_text, *args, **kwargs):
        s = str(sql_text.text if hasattr(sql_text, "text") else sql_text)
        sql_ejecutado.append(s)
        # Primera llamada: detectar alembic_version
        if "alembic_version" in s:
            mock_result = MagicMock()
            mock_result.scalar.return_value = alembic_present
            return mock_result
        # Default fetchall / scalar
        return MagicMock(fetchall=lambda: [], scalar=lambda: 0)

    engine_conn.execute.side_effect = _execute
    engine.connect.return_value.__enter__ = lambda self: engine_conn
    engine.connect.return_value.__exit__ = lambda self, *args: None

    # Mock get_connection (tenant scope)
    tenant_conn = MagicMock()
    tenant_conn.execute.side_effect = lambda sql, *a, **kw: (
        sql_ejecutado.append(
            str(sql.text if hasattr(sql, "text") else sql)
        )
        or MagicMock(fetchall=lambda: [], fetchone=lambda: None,
                     rowcount=0, scalar=lambda: 0)
    )

    @contextmanager
    def _fake_get_connection(schema=None):
        yield tenant_conn

    monkeypatch.setattr("db.init.get_engine", lambda: engine)
    monkeypatch.setattr("db.init.get_connection", _fake_get_connection)
    monkeypatch.setattr(
        "db.init._seed_datos_iniciales", lambda tenant: None,
    )

    # Importar y ejecutar.
    from db.init import init_db
    init_db()

    return sql_ejecutado


class TestInitDbSinDdlCuandoAlembicMigrado:

    def test_init_db_no_ejecuta_create_table_si_alembic_esta(self, monkeypatch):
        """Con `alembic_version` presente: NO debe ejecutar CREATE/ALTER TABLE."""
        sqls = _ejecutar_init_db_mockeado(monkeypatch, alembic_present=True)

        peligrosos = [
            s for s in sqls
            if "CREATE TABLE" in s.upper() or "ALTER TABLE" in s.upper()
        ]
        assert peligrosos == [], (
            f"init_db ejecutó DDL cuando Alembic ya está aplicado: {peligrosos}. "
            "Esto viola el contrato de la Tarea 0.3."
        )


class TestInitDbRamaLegacy:

    def test_init_db_rama_legacy_detecta_alembic_y_salta(self, monkeypatch):
        """Con `alembic_version` ausente: cae a la rama legacy.

        No validamos exactamente qué DDL se aplica (eso está cubierto por
        tests de Alembic), sino que la función no crashea y termina."""
        sqls = _ejecutar_init_db_mockeado(monkeypatch, alembic_present=False)
        # En la rama legacy sí ejecuta DDL. No fallamos por DDL presente.
        assert any("CREATE TABLE" in s.upper() for s in sqls) or any(
            "ALTER TABLE" in s.upper() for s in sqls
        ), (
            "Se esperaba DDL legacy (CREATE/ALTER) cuando Alembic NO migró."
        )


class TestInitDbSeedIdempotente:

    def test_seed_siempre_se_ejecuta_independiente_del_modo(self, monkeypatch):
        """El seed es idempotente y se ejecuta aunque Alembic ya haya migrado.

        Verificamos que `_seed_datos_iniciales` es SIEMPRE invocado, sea cual
        sea el resultado de `_alembic_applied()`.
        """
        from db.init import init_db

        # Modo Alembic presente: NO DDL → SI seed.
        llamadas = []

        def _contar_seed(tenant):
            llamadas.append(("alembic_applied", tenant))

        # Mockear get_engine para responder alembic=True (camino feliz).
        engine = MagicMock()
        engine_conn = MagicMock()

        def _execute(sql_text, *args, **kwargs):
            s = str(sql_text.text if hasattr(sql_text, "text") else sql_text)
            if "alembic_version" in s:
                return MagicMock(scalar=lambda: True)
            return MagicMock(fetchall=lambda: [], scalar=lambda: 0)

        engine_conn.execute.side_effect = _execute
        engine.connect.return_value.__enter__ = lambda self: engine_conn
        engine.connect.return_value.__exit__ = lambda self, *args: None

        @contextmanager
        def _fake_get_connection(schema=None):
            yield MagicMock(execute=lambda *a, **kw: MagicMock(
                fetchall=lambda: [], fetchone=lambda: None,
                rowcount=0, scalar=lambda: 0,
            ))

        monkeypatch.setattr("db.init.get_engine", lambda: engine)
        monkeypatch.setattr("db.init.get_connection", _fake_get_connection)
        monkeypatch.setattr("db.init._seed_datos_iniciales", _contar_seed)

        init_db()
        assert ("alembic_applied", "istpet") in llamadas, (
            "Se esperaba invocar _seed_datos_iniciales con tenant='istpet'"
        )

        # Modo Alembic ausente (legacy): también se llama el seed (idempotente).
        llamadas.clear()

        def _execute_legacy(sql_text, *args, **kwargs):
            s = str(sql_text.text if hasattr(sql_text, "text") else sql_text)
            if "alembic_version" in s:
                return MagicMock(scalar=lambda: False)
            return MagicMock(
                fetchall=lambda: [("istpet",)] if "public.tenants" in s else [],
                scalar=lambda: 0,
            )

        engine_conn.execute.side_effect = _execute_legacy
        init_db()
        assert ("alembic_applied", "istpet") in llamadas, (
            "Se esperaba invocar _seed_datos_iniciales también en modo legacy."
        )
