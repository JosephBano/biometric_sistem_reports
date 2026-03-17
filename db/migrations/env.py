"""
Alembic env.py — configurado para schema-por-tenant.

- Las migraciones se aplican primero al schema public y luego a cada
  schema de tenant activo en public.tenants.
- En Fase 1, solo existe el tenant TENANT_DEFAULT.
- DATABASE_URL se lee desde la variable de entorno (cargada via python-dotenv
  o directamente del entorno del proceso).
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# Asegurar que el raíz del proyecto está en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Cargar .env si existe (útil para correr alembic desde CLI fuera de Docker)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Leer DATABASE_URL del entorno
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL no está configurado en el entorno.")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = None  # usamos SQL crudo, no ORM metadata


def _get_tenant_slugs(connection) -> list[str]:
    """Retorna la lista de slugs de tenants activos."""
    try:
        rows = connection.execute(
            text("SELECT slug FROM public.tenants WHERE activo = true ORDER BY slug")
        ).fetchall()
        return [row[0] for row in rows]
    except Exception:
        # Si la tabla tenants aún no existe, usar solo TENANT_DEFAULT
        return [os.environ.get("TENANT_DEFAULT", "istpet")]


def run_migrations_offline() -> None:
    """Genera SQL sin conectar a la base de datos."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica migraciones con conexión activa, para todos los tenants."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Paso 1: migraciones del schema public
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="public",
        )
        with context.begin_transaction():
            context.run_migrations()

        # Paso 2: migraciones para cada tenant
        tenant_slugs = _get_tenant_slugs(connection)
        for slug in tenant_slugs:
            # Validar slug (previene inyección SQL)
            if not all(c.isalnum() or c == "_" for c in slug):
                continue

            connection.execute(text(f"SET search_path TO {slug}, public"))
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_schemas=True,
                version_table="alembic_version",
                version_table_schema=slug,
                # Usar el slug como sufijo para distinguir versiones por tenant
                x_apply_env={"CURRENT_TENANT": slug},
            )
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
