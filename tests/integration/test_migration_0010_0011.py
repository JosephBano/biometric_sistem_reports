"""
Tests de la migración 0011 (ADR-0003 — Fase 1, plan Tarea 1.1).

Esta migración crea las 3 tablas del modelo de horarios por grupo
funcional:

  - grupos_funcionales_personas (N:M persona ↔ grupo funcional con vigencia)
  - horarios_default_grupo (default_grupo funcional con prioridad)
  - overrides_horario_persona (override individual)

Regla arquitectónica clave (ADR-0003 P12): los índices B-tree NO pueden
tener predicados no inmutables (`fecha_fin >= CURRENT_DATE` es
no inmutable), así que usamos predicados inmutables o B-tree completos.

Estos tests verifican contra la BD de tests ya inicializada por el
conftest.py del directorio de integración. La fixture `app` levanta el
PostgreSQL embebido con pgserver y deja las tablas del modelo listas
(tanto si vienen del DDL legacy de init_db como de Alembic).
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa


# Tablas del modelo de horarios por grupo funcional (creadas por 0011)
TABLAS_0011 = (
    "grupos_funcionales_personas",
    "horarios_default_grupo",
    "overrides_horario_persona",
)


class TestMigracion0011TablasCreadas:

    @pytest.mark.parametrize("tabla", TABLAS_0011)
    def test_tabla_0011_existe_en_tenant(self, app, tenant_id, tabla):
        """Cada tabla de la 0011 existe en el schema del tenant."""
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            existe = conn.execute(sa.text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'istpet' AND table_name = '{tabla}'
                )
            """)).scalar()
            assert bool(existe), f"Tabla esperada por la migración 0011: {tabla!r}"

    def test_tabla_persona_existe(self, app, tenant_id):
        """Sanity check: la tabla `personas` existe (precondición)."""
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            existe = conn.execute(sa.text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'istpet' AND table_name = 'personas'
                )
            """)).scalar()
            assert bool(existe), "Precondición rota: `personas` debe existir."


class TestMigracion0011ColumnasEsenciales:

    """Verifica columnas esperadas por el modelo (ADR-0003 tabla-modelo)."""

    @pytest.mark.parametrize("columna", [
        "persona_id",
        "grupo_funcional_id",
        "fecha_inicio",
        "fecha_fin",
        "es_principal",
    ])
    def test_grupos_funcionales_personas_tiene_columnas(
        self, app, tenant_id, columna
    ):
        """Las columnas esperadas existen en `grupos_funcionales_personas`."""
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'istpet'
                      AND table_name = 'grupos_funcionales_personas'
                      AND column_name = '{columna}'
                )
            """)).scalar()
            assert bool(row), (
                f"grupos_funcionales_personas debe tener la columna {columna!r}."
            )

    @pytest.mark.parametrize("columna", [
        "grupo_funcional_id",
        "plantilla_id",
        "fecha_inicio",
        "fecha_fin",
        "prioridad",
    ])
    def test_horarios_default_grupo_tiene_columnas(
        self, app, tenant_id, columna
    ):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'istpet'
                      AND table_name = 'horarios_default_grupo'
                      AND column_name = '{columna}'
                )
            """)).scalar()
            assert bool(row), (
                f"horarios_default_grupo debe tener la columna {columna!r}."
            )

    @pytest.mark.parametrize("columna", [
        "persona_id",
        "plantilla_id",
        "fecha_inicio",
        "fecha_fin",
    ])
    def test_overrides_horario_persona_tiene_columnas(
        self, app, tenant_id, columna
    ):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'istpet'
                      AND table_name = 'overrides_horario_persona'
                      AND column_name = '{columna}'
                )
            """)).scalar()
            assert bool(row), (
                f"overrides_horario_persona debe tener la columna {columna!r}."
            )


class TestMigracion0011TiposSqlAlchemyCorrectos:

    """Verifica que los tipos son los esperados (UUID, DATE, BOOLEAN, etc.)."""

    def test_es_principal_es_boolean_en_pgf(self, app, tenant_id):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text("""
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'istpet'
                  AND table_name = 'grupos_funcionales_personas'
                  AND column_name = 'es_principal'
            """)).fetchone()
            assert row is not None, "Columna debe existir."
            assert "boolean" in (row[0] or "").lower(), (
                f"'es_principal' debe ser BOOLEAN. Got: {row[0]}"
            )

    def test_persona_id_es_uuid_en_pgf(self, app, tenant_id):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text("""
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'istpet'
                  AND table_name = 'grupos_funcionales_personas'
                  AND column_name = 'persona_id'
            """)).fetchone()
            assert "uuid" in (row[0] or "").lower(), (
                f"'persona_id' debe ser UUID. Got: {row[0]}"
            )

    def test_fecha_inicio_es_date_en_todas_las_tablas(self, app, tenant_id):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            for tabla in TABLAS_0011:
                row = conn.execute(sa.text(f"""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_schema = 'istpet'
                      AND table_name = '{tabla}'
                      AND column_name = 'fecha_inicio'
                """)).fetchone()
                assert row is not None, f"{tabla} debe tener 'fecha_inicio'."
                assert "date" in (row[0] or "").lower(), (
                    f"{tabla}.fecha_inicio debe ser DATE. Got: {row[0]}"
                )


class TestMigracion0011FKS:

    """Verifica foreign keys del modelo (ADR-0003 integridad referencial)."""

    def test_pgf_fk_a_personas_existe(self, app, tenant_id):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_type = 'FOREIGN KEY'
                      AND table_schema = 'istpet'
                      AND table_name = 'grupos_funcionales_personas'
                      AND constraint_name LIKE '%persona%'
                )
            """)).scalar()
            assert bool(row), (
                "grupos_funcionales_personas debe tener FK a personas."
            )

    def test_hdg_fk_a_grupos_funcionales_existe(self, app, tenant_id):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_type = 'FOREIGN KEY'
                      AND table_schema = 'istpet'
                      AND table_name = 'horarios_default_grupo'
                      AND constraint_name LIKE '%grupo_funcional%'
                )
            """)).scalar()
            assert bool(row), (
                "horarios_default_grupo debe tener FK a grupos_funcionales."
            )

    def test_hdg_fk_a_plantillas_horario_existe(self, app, tenant_id):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            row = conn.execute(sa.text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_type = 'FOREIGN KEY'
                      AND table_schema = 'istpet'
                      AND table_name = 'horarios_default_grupo'
                      AND constraint_name LIKE '%plantilla%'
                )
            """)).scalar()
            assert bool(row), (
                "horarios_default_grupo debe tener FK a plantillas_horario."
            )


class TestIndicesNoUsanPredicadosNoInmutables:

    """Regla ADR-0003 P12: ningún índice parcial con CURRENT_DATE.

    Verifica contra todos los índices de las 3 tablas del modelo que el
    predicado del índice parcial (si existe) NO contiene CURRENT_DATE u
    otras funciones no inmutables. PostgreSQL rechazaría tales índices en
    el CREATE INDEX, así que la verificación es defensiva.
    """

    @pytest.mark.parametrize("tabla", TABLAS_0011)
    def test_indices_sin_predicados_no_inmutables(self, app, tenant_id, tabla):
        engine = sa.create_engine(app.config["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(sa.text('SET search_path TO "istpet", public'))
            # Query SQL robusta con nombre de tabla hardcoded (paramsetrized).
            rows = conn.execute(
                sa.text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'istpet' "
                    "  AND tablename = '" + tabla + "' "
                    "  AND indexdef LIKE '%WHERE%'"
                )
            ).fetchall()
            predicados_invalidos = (
                "CURRENT_DATE", "CURRENT_TIMESTAMP", "NOW(",
                "TIMESTAMP WITHOUT TIME ZONE 'NOW'",
            )
            for row in rows:
                indexdef = row[0]
                upper = indexdef.upper()
                for mal in predicados_invalidos:
                    assert mal.upper() not in upper, (
                        f"Índice en {tabla!r} usa predicado no inmutable "
                        f"{mal!r}: {indexdef}"
                    )
