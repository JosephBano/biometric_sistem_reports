"""
Inicialización de la base de datos PostgreSQL.

Tras el cierre de Fase −1 (ADR-0001 + ADR-0003 Tarea 0.3), `init_db()`
SOLO ejecuta seed idempotente. La fuente de verdad del schema es Alembic
(`db/migrations/versions/*`). El deploy debe correr `alembic upgrade head`
antes de que la app levante, o el seed fallará porque las tablas no
existirán.

Modos:
  - Modo Alembic-aware (recomendado en producción):
    `init_db()` detecta `public.alembic_version`, salta el DDL legacy y
    solo siembra datos de referencia. Esto es lo que ocurre tras
    `alembic upgrade head`.
  - Modo legacy (compat):
    Si `alembic_version` no existe, aplica `PUBLIC_DDL` + `get_tenant_ddl`
    para crear el schema desde cero. Útil en CI con pgserver donde Alembic
    no corre, y en entornos de desarrollo sin migraciones aplicadas.

El seed vive en `db.init_seed` (Tarea 0.3 del plan), separado para que
`init_db` solo orqueste. Esto garantiza que `db.init` no ejecute DDL nuevo
(idempotente con Alembic) por accidente y que las migraciones futuras
no divergan del DDL que `init_db` aplicaría en el siguiente arranque.
"""
import os
import logging
from sqlalchemy import text

from db.connection import get_engine, get_connection, validate_schema_name
from db.schema import PUBLIC_DDL, get_tenant_ddl
from db.init_seed import _seed_datos_iniciales

log = logging.getLogger(__name__)


def _alembic_applied() -> bool:
    """Detecta si Alembic ya aplicó migraciones (existe `alembic_version`)."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'alembic_version'
                )
            """)).scalar()
        return bool(row)
    except Exception:
        return False


def init_db():
    """Orquesta la inicialización: DDL legacy (si Alembic no migró) + seed idempotente.

    Tras el cierre de Fase -1, el seed es lo ÚNICO que esta función debería
    ejecutar contra una BD ya migrada por Alembic. El DDL legacy solo se
    ejecuta si Alembic NO ha migrado (modo compat de pgserver / dev fresco).
    """
    tenant = validate_schema_name(os.environ.get("TENANT_DEFAULT", "istpet"))
    engine = get_engine()
    alembic_done = _alembic_applied()

    with engine.connect() as conn:
        if alembic_done:
            log.info(
                "Alembic ya aplicó migraciones (alembic_version existe). "
                "Saltando DDL legacy, solo seed."
            )
        else:
            # Modo compat: Alembic no ha migrado, aplicamos el DDL legacy.
            # Esta rama está cubierta por los tests de pgserver/development.
            log.warning(
                "Alembic NO aplicado: ejecutando DDL legacy (PUBLIC_DDL + "
                "get_tenant_ddl). Esto desaparecerá cuando el deploy corra "
                "`alembic upgrade head` explícitamente."
            )
            conn.execute(text(PUBLIC_DDL))
            conn.commit()
            conn.execute(text(get_tenant_ddl(tenant)))
            conn.commit()

            tenant_slugs = [r[0] for r in conn.execute(
                text("SELECT slug FROM public.tenants WHERE activo = true")
            ).fetchall()] or [tenant]

            for slug in tenant_slugs:
                validate_schema_name(slug)
                conn.execute(text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'dispositivos'
                              AND column_name = 'prioridad'
                        ) THEN
                            ALTER TABLE {slug}.dispositivos ADD COLUMN prioridad INTEGER NOT NULL DEFAULT 5;
                        END IF;

                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'dispositivos'
                              AND column_name = 'capacidad_max'
                        ) THEN
                            ALTER TABLE {slug}.dispositivos ADD COLUMN capacidad_max INTEGER NOT NULL DEFAULT 100000;
                        END IF;

                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'justificaciones'
                              AND column_name = 'hora_recuperacion_fin'
                        ) THEN
                            ALTER TABLE {slug}.justificaciones ADD COLUMN hora_recuperacion_fin TIME;
                        END IF;

                        -- Renombrar categorias -> grupos_funcionales (compat prod).
                        IF EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = '{slug}' AND table_name = 'categorias'
                        ) AND NOT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = '{slug}' AND table_name = 'grupos_funcionales'
                        ) THEN
                            ALTER TABLE {slug}.categorias RENAME TO grupos_funcionales;
                        END IF;

                        IF EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'personas'
                              AND column_name = 'categoria_id'
                        ) AND NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'personas'
                              AND column_name = 'grupo_funcional_id'
                        ) THEN
                            ALTER TABLE {slug}.personas
                                RENAME COLUMN categoria_id TO grupo_funcional_id;
                        END IF;
                    END $$;
                """))
            conn.commit()

    # Seed SIEMPRE (incluso si Alembic ya migró). Es idempotente.
    _seed_datos_iniciales(tenant)
    log.info(
        "init_db completado para tenant=%s (alembic=%s)", tenant, alembic_done
    )


__all__ = ["init_db"]
